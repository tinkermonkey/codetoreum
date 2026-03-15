"""End-to-end failure recovery and resilience tests.

Phase 4 of the E2E simulation roadmap:
  4a – Agent failure with EventStore assertions (WorkflowFailed / NOT WorkflowCompleted)
  4b – Repair cycle: direct adapter invocation emits the expected lifecycle events
  4c – Review rejection cycle: request-changes-then-approve path emits iteration events
"""

import asyncio
from dataclasses import dataclass
from typing import Any, cast

import pytest

from codetoreum.domain.repair_cycle_types import RepairTestRunConfig, RepairTestType
from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationAdapters,
    SimulationApplicationBootstrap,
)
from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder
from codetoreum.ports.output.board_service import MovedByType
from codetoreum.ports.output.review_cycle_service import ReviewCycleRequest
from tests.simulation.helpers import wait_for_column

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def e2e_env(
    simulation_bootstrap: SimulationApplicationBootstrap,
    simulation_seeder: SimulationDataSeeder,
):
    """Bootstrap + seed, with fast agent execution delay."""
    adapters = cast("SimulationAdapters", simulation_bootstrap.adapters)
    adapters.agent_executor._execution_delay = 0.1
    await simulation_seeder.seed_default_scenario()
    return simulation_bootstrap, simulation_seeder


# ============================================================================
# 4a: Agent failure with EventStore assertions
# ============================================================================


@pytest.mark.asyncio
async def test_agent_failure_emits_workflow_failed_event(
    e2e_env: Any,
    monkeypatch: Any,
) -> None:
    """Agent failure persists WorkflowFailed (not WorkflowCompleted) in EventStore.

    Extends test_cascade_stops_on_agent_failure with EventStore assertions:
    - WorkflowFailed must exist in EventStore for this work item's run
    - WorkflowCompleted must NOT exist
    """
    bootstrap, seeder = e2e_env
    adapters = cast("SimulationAdapters", bootstrap.adapters)
    board = adapters.board
    executor = adapters.agent_executor
    event_store = adapters.event_store
    work_item_id = seeder.created_items.work_items[0]

    # Patch the second agent execution (coder) to simulate failure.
    # _simulate_execution signature: (work_item_id, agent_id, execution_id, started_at, board_id)
    # When monkeypatched on the instance, self is NOT passed; the call site passes 5 positional args.
    # We must NOT raise inside the task (that bypasses the completion callback).
    # Instead, we call the completion callback with success=False to properly persist WorkflowFailed.
    original_simulate = executor._simulate_execution
    call_count = 0

    async def failing_simulate(
        work_item_id_arg: str,
        agent_id: str,
        execution_id: str,
        started_at: Any,
        board_id: str,
    ) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            # Simulate coder failure by invoking completion callback with success=False.
            # This mirrors what _simulate_execution does in its except block, ensuring
            # the board_event_handler's _fail_workflow_run() is called and persists WorkflowFailed.
            if executor._completion_callback:
                await executor._completion_callback(work_item_id_arg, board_id, False)
            return
        await original_simulate(work_item_id_arg, agent_id, execution_id, started_at, board_id)

    monkeypatch.setattr(executor, "_simulate_execution", failing_simulate)

    # Trigger cascade: Backlog → Ready (pipeline trigger)
    await board.move_item_to_column(work_item_id, "Ready", MovedByType.HUMAN)

    # Wait for architect to succeed and item to reach In Progress
    reached_in_progress = await wait_for_column(board, work_item_id, "In Progress", timeout=5.0)
    assert reached_in_progress, "Item did not reach 'In Progress'"

    # Poll until WorkflowFailed appears in EventStore (or timeout).
    # The coder runs asynchronously; after it fails the board_event_handler calls
    # _fail_workflow_run() which persists the WorkflowFailed event.
    workflow_failed_appeared = False
    for _ in range(30):  # up to 3 seconds
        await asyncio.sleep(0.1)
        all_events_poll = event_store.get_all_events_list()
        if any(e.event_type == "WorkflowFailed" and e.aggregate_type == "Workflow" for e in all_events_poll):
            workflow_failed_appeared = True
            break
    assert workflow_failed_appeared, "WorkflowFailed event did not appear in EventStore within timeout"

    # Item stays in In Progress (cascade stopped)
    pos = await board.get_item_position(work_item_id)
    assert pos.column_name == "In Progress", f"Expected item in 'In Progress', got '{pos.column_name}'"

    # ----- EventStore assertions -----
    all_events = event_store.get_all_events_list()

    # Find workflow lifecycle events for this work item
    workflow_events_for_item = [
        e for e in all_events if e.aggregate_type == "Workflow" and e.payload.get("work_item_id") == work_item_id
    ]
    assert len(workflow_events_for_item) > 0, "No Workflow-aggregate events found for this work item in EventStore"

    # All events for this run share the same aggregate_id (workflow_run_id)
    workflow_run_id = workflow_events_for_item[0].aggregate_id
    run_events = [e for e in all_events if e.aggregate_id == workflow_run_id]
    run_event_types = [e.event_type for e in run_events]

    # WorkflowFailed MUST be present
    assert "WorkflowFailed" in run_event_types, (
        f"Expected WorkflowFailed in EventStore for run {workflow_run_id}, " f"but only found: {run_event_types}"
    )

    # WorkflowCompleted must NOT be present (cascade did not finish)
    assert "WorkflowCompleted" not in run_event_types, (
        f"WorkflowCompleted should NOT be in EventStore after agent failure, " f"but found it in: {run_event_types}"
    )


# ============================================================================
# 4b: Repair cycle
# ============================================================================


@dataclass
class _SimpleRepairContext:
    """Minimal implementation of RepairCycleContext Protocol for testing."""

    stage_name: str
    workflow_run_id: str
    test_configs: tuple[RepairTestRunConfig, ...]
    agent_name: str
    max_total_agent_calls: int
    checkpoint_interval: int


@pytest.mark.asyncio
async def test_repair_cycle_emits_started_and_completed_events(
    simulation_bootstrap: SimulationApplicationBootstrap,
    simulation_seeder: SimulationDataSeeder,
) -> None:
    """Directly invoking execute() on MockRepairCycleAdapter emits lifecycle events.

    The default-seeded board has no dedicated Repair column, so this test invokes
    the repair cycle adapter directly rather than through a board column move.
    It verifies that the adapter emits REPAIR_CYCLE_STARTED and REPAIR_CYCLE_COMPLETED
    events in its internal event log when current_project is set.
    """
    await simulation_seeder.seed_default_scenario()
    adapters = cast("SimulationAdapters", simulation_bootstrap.adapters)
    repair_cycle = adapters.repair_cycle

    # A project must be set so the adapter emits events
    project_id = simulation_seeder._current_project_id
    repair_cycle.current_project = project_id

    # Configure a single UNIT test type to pass on the first iteration
    repair_cycle.set_iterations_until_success(RepairTestType.UNIT, iterations=1)

    context = _SimpleRepairContext(
        stage_name="fix_failures",
        workflow_run_id="test-run-repair-001",
        test_configs=(
            RepairTestRunConfig(
                test_type=RepairTestType.UNIT,
                max_iterations=3,
                review_warnings=False,
            ),
        ),
        agent_name="repair-agent",
        max_total_agent_calls=20,
        checkpoint_interval=5,
    )

    result = await repair_cycle.execute(context)

    # The cycle should have succeeded (1 iteration, all passing)
    assert result.overall_success, f"Expected repair cycle to succeed, got overall_success={result.overall_success}"

    # Check internal event log for lifecycle events
    event_log = repair_cycle.get_all_events_log()
    event_types_logged = [e.get("type") for e in event_log]

    assert (
        "REPAIR_CYCLE_STARTED" in event_types_logged
    ), f"Expected REPAIR_CYCLE_STARTED in event log, got: {event_types_logged}"
    assert (
        "REPAIR_CYCLE_COMPLETED" in event_types_logged
    ), f"Expected REPAIR_CYCLE_COMPLETED in event log, got: {event_types_logged}"

    # Check _events list (via get_all_events) for domain event objects emitted
    all_events = repair_cycle.get_all_events()
    emitted_types = [e.get("type") for e in all_events]

    assert (
        "repair_cycle.started" in emitted_types
    ), f"Expected repair_cycle.started in emitted events, got: {emitted_types}"
    assert (
        "repair_cycle.completed" in emitted_types
    ), f"Expected repair_cycle.completed in emitted events, got: {emitted_types}"


@pytest.mark.asyncio
async def test_repair_cycle_emits_fast_fail_on_persistent_failure(
    simulation_bootstrap: SimulationApplicationBootstrap,
    simulation_seeder: SimulationDataSeeder,
) -> None:
    """When tests always fail, the repair cycle emits a fast-fail event.

    Configures UNIT tests to always fail so the adapter's fast-fail logic triggers
    and emits the repair_cycle.fast_fail event.
    """
    await simulation_seeder.seed_default_scenario()
    adapters = cast("SimulationAdapters", simulation_bootstrap.adapters)
    repair_cycle = adapters.repair_cycle

    project_id = simulation_seeder._current_project_id
    repair_cycle.current_project = project_id

    # Configure UNIT tests to always fail for 2 iterations
    repair_cycle.set_always_fail(RepairTestType.UNIT, max_iterations=2)

    context = _SimpleRepairContext(
        stage_name="fix_failures",
        workflow_run_id="test-run-repair-002",
        test_configs=(
            RepairTestRunConfig(
                test_type=RepairTestType.UNIT,
                max_iterations=2,
                review_warnings=False,
            ),
        ),
        agent_name="repair-agent",
        max_total_agent_calls=20,
        checkpoint_interval=5,
    )

    result = await repair_cycle.execute(context)

    # Cycle should have failed
    assert not result.overall_success, "Expected repair cycle to fail with always-failing tests"

    # fast_fail event should be emitted via _emit_event (in _events / get_all_events)
    all_events = repair_cycle.get_all_events()
    emitted_types = [e.get("type") for e in all_events]
    assert "repair_cycle.fast_fail" in emitted_types, f"Expected repair_cycle.fast_fail event, got: {emitted_types}"


# ============================================================================
# 4c: Review rejection cycle
# ============================================================================


@pytest.mark.asyncio
async def test_review_rejection_then_approval_emits_iteration_events(
    simulation_bootstrap: SimulationApplicationBootstrap,
    simulation_seeder: SimulationDataSeeder,
) -> None:
    """set_request_changes_then_approve produces iteration + maker_revision + approved events.

    Configures the review cycle adapter to request changes on the first iteration
    and approve on the second. Verifies that all expected review lifecycle events
    are emitted (review_cycle.started, review_cycle.iteration_completed,
    review_cycle.maker_revision, review_cycle.approved).
    """
    await simulation_seeder.seed_default_scenario()
    adapters = cast("SimulationAdapters", simulation_bootstrap.adapters)
    review_cycle = adapters.review_cycle

    project_id = simulation_seeder._current_project_id
    work_item_id = simulation_seeder.created_items.work_items[0]
    board_id = "board-1"

    # Set current_project so events are emitted
    review_cycle.current_project = project_id

    # Configure: 1 request-changes iteration then 1 approval (total 2 iterations)
    review_cycle.set_request_changes_then_approve(work_item_id, iterations=2)

    request = ReviewCycleRequest(
        work_item_id=work_item_id,
        project_id=project_id,
        board_id=board_id,
        maker_agent="coder",
        reviewer_agent="tester",
        max_iterations=5,
        auto_advance_on_approval=False,
        escalate_on_blocked=False,
        previous_stage_output="Initial implementation complete",
    )

    result = await review_cycle.start_review_cycle(request)

    # Cycle should end with approval
    assert result.final_status == "APPROVED", f"Expected review cycle to be APPROVED, got {result.final_status}"

    # Check emitted events (stored in _events via _emit_event)
    events_log = review_cycle.get_all_events_log()
    emitted_event_types = [e.get("type") for e in events_log]

    assert "review_cycle.started" in emitted_event_types, f"Expected review_cycle.started, got: {emitted_event_types}"
    # First iteration: CHANGES_REQUESTED → should emit iteration_completed + maker_revision
    assert (
        "review_cycle.iteration_completed" in emitted_event_types
    ), f"Expected review_cycle.iteration_completed, got: {emitted_event_types}"
    assert (
        "review_cycle.maker_revision" in emitted_event_types
    ), f"Expected review_cycle.maker_revision (changes requested), got: {emitted_event_types}"
    # Final iteration: APPROVED
    assert "review_cycle.approved" in emitted_event_types, f"Expected review_cycle.approved, got: {emitted_event_types}"

    # There should be at least 2 iteration_completed events (one per iteration)
    iteration_events = [e for e in events_log if e.get("type") == "review_cycle.iteration_completed"]
    assert len(iteration_events) >= 2, (
        f"Expected at least 2 iteration_completed events (1 rejection + 1 approval), " f"got {len(iteration_events)}"
    )

    # Verify the adapter's built-in assertion helper also passes
    review_cycle.assert_iteration_count(work_item_id, expected=2)
    review_cycle.assert_final_status(work_item_id, expected_status="APPROVED")


@pytest.mark.asyncio
async def test_review_approve_immediately_emits_minimal_events(
    simulation_bootstrap: SimulationApplicationBootstrap,
    simulation_seeder: SimulationDataSeeder,
) -> None:
    """Immediate approval path: only started + one iteration_completed + approved events.

    No maker_revision events should be emitted when the first review is an approval.
    """
    await simulation_seeder.seed_default_scenario()
    adapters = cast("SimulationAdapters", simulation_bootstrap.adapters)
    review_cycle = adapters.review_cycle

    project_id = simulation_seeder._current_project_id
    work_item_id = simulation_seeder.created_items.work_items[1]
    board_id = "board-1"

    review_cycle.current_project = project_id
    review_cycle.set_approve_immediately(work_item_id)

    request = ReviewCycleRequest(
        work_item_id=work_item_id,
        project_id=project_id,
        board_id=board_id,
        maker_agent="coder",
        reviewer_agent="tester",
        max_iterations=5,
        auto_advance_on_approval=False,
        escalate_on_blocked=False,
        previous_stage_output="All tests pass, ready for review",
    )

    result = await review_cycle.start_review_cycle(request)

    assert result.final_status == "APPROVED", f"Expected APPROVED, got {result.final_status}"

    events_log = review_cycle.get_all_events_log()
    emitted_types = [e.get("type") for e in events_log]

    assert "review_cycle.started" in emitted_types
    assert "review_cycle.approved" in emitted_types

    # No maker_revision because first review approved immediately
    maker_revision_events = [e for e in events_log if e.get("type") == "review_cycle.maker_revision"]
    assert len(maker_revision_events) == 0, (
        f"Expected no maker_revision events for immediate approval, " f"but found {len(maker_revision_events)}"
    )
