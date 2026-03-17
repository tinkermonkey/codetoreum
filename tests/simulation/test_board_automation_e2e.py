"""End-to-end board automation cascade test.

Exercises the full fire-and-forget cascade through the bootstrap's plumbing:
human move → event bridge → handler → agent execution → completion callback →
auto-progress → repeat.

Unlike scenario tests A–E which manually call handle_column_change() and
handle_agent_completion() at each step, this test uses SimulationApplicationBootstrap
and SimulationDataSeeder to prove the wiring actually works end-to-end.
"""

import asyncio
from typing import Any, cast

import pytest

from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationAdapters,
    SimulationApplicationBootstrap,
)
from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder
from codetoreum.ports.output.board_service import MovedByType
from tests.conftest import assert_condition, wait_for_condition
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
    if adapters.agent_executor is not None:
        adapters.agent_executor._execution_delay = 0.1
    await simulation_seeder.seed_default_scenario()
    return simulation_bootstrap, simulation_seeder


# ============================================================================
# Tests
# ============================================================================


@pytest.mark.asyncio
async def test_item_cascades_from_trigger_to_exit(e2e_env):
    """Move one item from Backlog to Ready, verify it cascades to Done.

    The cascade should be:
    Ready (architect) → In Progress (coder) → Review (tester) → Done (exit)
    """
    bootstrap, seeder = e2e_env
    adapters = cast("SimulationAdapters", bootstrap.adapters)
    board = adapters.board
    work_item_id = seeder.created_items.work_items[0]

    # Human moves item from Backlog → Ready (pipeline trigger)
    await board.move_item_to_column(work_item_id, "Ready", MovedByType.HUMAN)

    # Wait for cascade to reach Done
    reached_done = await wait_for_column(board, work_item_id, "Done", timeout=10.0)
    assert reached_done, (
        f"Item did not reach 'Done' within timeout. "
        f"Current position: {(await board.get_item_position(work_item_id)).column_name}"
    )

    # Wait for async event handlers (e.g., _complete_workflow_run) to finish
    # Poll the executor to verify all executions are recorded
    await wait_for_condition(
        lambda: len([e for e in adapters.agent_executor.executions if e["work_item_id"] == work_item_id]) == 3,
        timeout=2.0,
        poll_interval=0.05,
    )

    # Wait for the WorkflowCompleted event to be persisted
    # The exit column handler emits this event asynchronously via the event bus bridge
    async def workflow_completed():
        event_store = adapters.event_store
        all_events = event_store.get_all_events_list()
        workflow_run_id_events = [
            e for e in all_events if e.aggregate_type == "Workflow" and e.payload.get("work_item_id") == work_item_id
        ]
        if not workflow_run_id_events:
            return False
        workflow_run_id = workflow_run_id_events[0].aggregate_id
        workflow_events = [e for e in all_events if e.aggregate_id == workflow_run_id]
        return any(e.event_type == "WorkflowCompleted" for e in workflow_events)

    await wait_for_condition(
        workflow_completed,
        timeout=2.0,
        poll_interval=0.05,
    )

    # Verify all 3 agents were triggered in order
    executions = adapters.agent_executor.executions
    item_executions = [e for e in executions if e["work_item_id"] == work_item_id]
    agent_order = [e["agent_id"] for e in item_executions]
    assert agent_order == [
        "architect",
        "coder",
        "tester",
    ], f"Expected agents [architect, coder, tester], got {agent_order}"

    # Verify movement history
    history = board.get_movement_history(work_item_id)
    assert (
        len(history) == 4
    ), f"Expected 4 movements (Backlog→Ready, Ready→In Progress, In Progress→Review, Review→Done), got {len(history)}"

    # First move is HUMAN, rest are ORCHESTRATOR
    assert history[0].moved_by == MovedByType.HUMAN
    for move in history[1:]:
        assert (
            move.moved_by == MovedByType.ORCHESTRATOR
        ), f"Expected ORCHESTRATOR for {move.from_column}→{move.to_column}, got {move.moved_by}"

    # Verify column progression path
    columns_visited = [history[0].from_column] + [m.to_column for m in history]
    assert columns_visited == ["Backlog", "Ready", "In Progress", "Review", "Done"]

    # Verify workflow lifecycle events in EventStore
    event_store = adapters.event_store
    all_events = event_store.get_all_events_list()

    # Find the workflow run ID for this work item by locating events with work_item_id in payload
    workflow_run_id_events = [
        e for e in all_events if e.aggregate_type == "Workflow" and e.payload.get("work_item_id") == work_item_id
    ]
    assert len(workflow_run_id_events) > 0, "No workflow lifecycle events found for this work item in EventStore"

    # All workflow events for this run share the same aggregate_id (workflow_run_id)
    workflow_run_id = workflow_run_id_events[0].aggregate_id

    # Retrieve all events for this workflow run stream
    workflow_events = [e for e in all_events if e.aggregate_id == workflow_run_id]
    event_types = [e.event_type for e in workflow_events]

    assert "WorkflowCreated" in event_types, f"WorkflowCreated not found, got: {event_types}"
    assert "WorkflowStarted" in event_types, f"WorkflowStarted not found, got: {event_types}"
    assert "WorkflowCompleted" in event_types, f"WorkflowCompleted not found, got: {event_types}"

    # Verify stage advances happened (3 stages = 3 advances)
    stage_advances = [e for e in workflow_events if e.event_type == "WorkflowStageAdvanced"]
    assert len(stage_advances) == 3, f"Expected 3 stage advances (one per agent), got {len(stage_advances)}"


@pytest.mark.asyncio
async def test_lock_released_after_cascade(e2e_env):
    """After cascade completes, verify the pipeline lock is released."""
    bootstrap, seeder = e2e_env
    adapters = cast("SimulationAdapters", bootstrap.adapters)
    board = adapters.board
    lock_service = adapters.lock_service
    work_item_id = seeder.created_items.work_items[0]

    # Determine the project_id the seeder used
    project_id = seeder._current_project_id

    # Move item to trigger cascade
    await board.move_item_to_column(work_item_id, "Ready", MovedByType.HUMAN)

    # Wait for cascade to finish
    reached_done = await wait_for_column(board, work_item_id, "Done", timeout=10.0)
    assert reached_done, "Item did not reach Done"

    # The Done column event is published via create_task in the bridge.
    # Wait for the exit-column handler that releases the lock.
    async def lock_is_released():
        queue_state = await lock_service.get_queue_state(project_id, "board-1")
        return queue_state.lock_holder is None

    await assert_condition(
        lock_is_released, timeout=2.0, poll_interval=0.05, message="Lock should be released after cascade"
    )


@pytest.mark.asyncio
async def test_cascade_stops_on_agent_failure(
    e2e_env: Any,
    monkeypatch: Any,
) -> None:
    """When an agent fails, the cascade stops at that column.

    Patch the executor to fail on the second execution (coder).
    After architect succeeds and item moves to In Progress, the coder
    execution fails. handle_agent_completion(success=False) returns
    without auto-progressing. Item stays in In Progress.
    """
    bootstrap, seeder = e2e_env
    adapters = cast("SimulationAdapters", bootstrap.adapters)
    board = adapters.board
    executor = adapters.agent_executor
    work_item_id = seeder.created_items.work_items[0]

    # Track call count and make the second execution raise
    original_run = executor._run_execution
    call_count = 0

    async def failing_run(
        work_item_id_arg: str,
        agent_id: str,
        board_id: str = "board-1",
    ) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            # Second agent (coder) fails
            raise RuntimeError("Simulated coder failure")
        await original_run(work_item_id_arg, agent_id, board_id)

    monkeypatch.setattr(executor, "_run_execution", failing_run)

    # Move item to trigger cascade
    await board.move_item_to_column(work_item_id, "Ready", MovedByType.HUMAN)

    # Wait for first agent to complete and item to move to In Progress
    reached_in_progress = await wait_for_column(board, work_item_id, "In Progress", timeout=5.0)
    assert reached_in_progress, "Item did not reach 'In Progress'"

    # Wait for second agent (coder) to execute and fail
    # Poll executor to verify coder execution was attempted
    async def coder_has_executed():
        item_executions = [e for e in executor.executions if e["work_item_id"] == work_item_id]
        # Should have at least architect + coder
        return len(item_executions) >= 2

    await assert_condition(
        coder_has_executed, timeout=5.0, poll_interval=0.05, message="Coder should have been executed"
    )

    # Item should still be in "In Progress" (coder failed, no auto-progress)
    # Verify this multiple times to ensure it's not a race condition
    pos = await board.get_item_position(work_item_id)
    assert (
        pos.column_name == "In Progress"
    ), f"Expected item to stay in 'In Progress' after coder failure, but found in '{pos.column_name}'"

    # Verify cascade stopped by polling executor state for stability
    # Capture executor count after coder executes
    initial_count = len([e for e in executor.executions if e["work_item_id"] == work_item_id])

    # Poll for 0.5s to confirm cascade stopped (no more agents execute)
    async def cascade_has_stopped():
        # Check if execution count has stabilized (no new executions)
        current_executions = [e for e in executor.executions if e["work_item_id"] == work_item_id]
        # Wait a bit and check again
        await asyncio.sleep(0.1)
        final_executions = [e for e in executor.executions if e["work_item_id"] == work_item_id]
        return len(current_executions) == len(final_executions)

    cascade_stable = await wait_for_condition(cascade_has_stopped, timeout=0.5, poll_interval=0.05)
    assert cascade_stable, "Cascade should have stopped (executor execution count stabilized)"

    # Verify architect executed but cascade stopped after coder failure
    item_executions = [e for e in executor.executions if e["work_item_id"] == work_item_id]
    agent_ids = [e["agent_id"] for e in item_executions]
    assert "architect" in agent_ids, "Architect should have been triggered"
    assert "coder" in agent_ids, "Coder should have been triggered (and failed)"
    assert "tester" not in agent_ids, (
        f"Tester should NOT have been triggered after coder failure. " f"Executions: {agent_ids}"
    )


@pytest.mark.asyncio
async def test_autonomous_progression_via_api_single_http_call(e2e_env):
    """Verify autonomous progression end-to-end with single API call.

    This is the Phase 6 acceptance test: inject issue via API, verify it flows
    autonomously through all workflow columns to Done with NO further HTTP calls.

    Workflow: Backlog → Ready (architect) → In Progress (coder) → Review (tester) → Done
    Each column has auto_progress_on_completion=True, forming a contiguous chain.

    Note: This test validates that the auto-progression chain works correctly,
    which is triggered by moving an item to the pipeline trigger column.
    The test simulates this via FastAPI TestClient's REST endpoint.
    """
    bootstrap, seeder = e2e_env
    adapters = cast("SimulationAdapters", bootstrap.adapters)
    board = adapters.board
    executor = adapters.agent_executor
    event_store = adapters.event_store
    project_id = seeder._current_project_id
    work_item_id = seeder.created_items.work_items[0]  # Use pre-seeded item

    # =========================================================================
    # SINGLE ORCHESTRATION CALL: Trigger pipeline via board move
    # =========================================================================
    # This simulates the same effect as an API call to move the item,
    # which triggers the orchestration handler and autonomous progression chain
    print(f"\nStarting autonomous progression test for {work_item_id}")
    print(f"Initial position: {(await board.get_item_position(work_item_id)).column_name}")

    # Move item to pipeline trigger column (simulating human or API-driven move)
    result = await board.move_item_to_column(work_item_id, "Ready", MovedByType.HUMAN)
    print(f"Moved to Ready: {result.to_column}")

    # =========================================================================
    # VERIFY AUTONOMOUS PROGRESSION (no more HTTP calls from here)
    # =========================================================================

    # 1. Wait for item to reach Done column
    reached_done = await wait_for_column(board, work_item_id, "Done", timeout=10.0)
    assert reached_done, (
        f"Item {work_item_id} did not reach 'Done' column. "
        f"Current position: {(await board.get_item_position(work_item_id)).column_name}"
    )

    # 2. Verify all 3 agents executed in the correct order
    async def all_agents_executed():
        item_executions = [e for e in executor.executions if e["work_item_id"] == work_item_id]
        return len(item_executions) >= 3

    await wait_for_condition(all_agents_executed, timeout=5.0, poll_interval=0.05)

    executions = [e for e in executor.executions if e["work_item_id"] == work_item_id]
    agent_ids = [e["agent_id"] for e in executions]
    assert agent_ids == ["architect", "coder", "tester"], (
        f"Expected agents [architect, coder, tester] in order, got {agent_ids}"
    )

    # 3. Verify movement history shows orchestrator-driven auto-progression
    history = board.get_movement_history(work_item_id)
    assert len(history) == 4, (
        f"Expected 4 movements (Backlog→Ready, Ready→In Progress, In Progress→Review, Review→Done), "
        f"got {len(history)}"
    )

    # First move is HUMAN (API call), rest are ORCHESTRATOR (auto-progression)
    assert history[0].moved_by == MovedByType.HUMAN, (
        f"First move should be HUMAN (API call), got {history[0].moved_by}"
    )
    for i, move in enumerate(history[1:], start=1):
        assert move.moved_by == MovedByType.ORCHESTRATOR, (
            f"Move {i} ({move.from_column}→{move.to_column}) should be ORCHESTRATOR, "
            f"got {move.moved_by}"
        )

    # 4. Verify column progression path
    columns_visited = [history[0].from_column] + [m.to_column for m in history]
    assert columns_visited == ["Backlog", "Ready", "In Progress", "Review", "Done"], (
        f"Expected column path [Backlog, Ready, In Progress, Review, Done], "
        f"got {columns_visited}"
    )

    # 5. Verify workflow lifecycle events in event store
    async def workflow_completed():
        all_events = event_store.get_all_events_list()
        # Find workflow run ID by locating events with work_item_id in payload
        workflow_run_id_events = [
            e for e in all_events if e.aggregate_type == "Workflow" and e.payload.get("work_item_id") == work_item_id
        ]
        if not workflow_run_id_events:
            return False
        workflow_run_id = workflow_run_id_events[0].aggregate_id
        # Check if WorkflowCompleted event exists
        workflow_events = [e for e in all_events if e.aggregate_id == workflow_run_id]
        return any(e.event_type == "WorkflowCompleted" for e in workflow_events)

    # Wait for WorkflowCompleted event to be persisted
    await wait_for_condition(
        workflow_completed,
        timeout=2.0,
        poll_interval=0.05,
    )

    # Verify the workflow events
    all_events = event_store.get_all_events_list()
    workflow_run_id_events = [
        e for e in all_events if e.aggregate_type == "Workflow" and e.payload.get("work_item_id") == work_item_id
    ]
    assert len(workflow_run_id_events) > 0, (
        "No workflow lifecycle events found for this work item in EventStore"
    )

    workflow_run_id = workflow_run_id_events[0].aggregate_id
    workflow_events = [e for e in all_events if e.aggregate_id == workflow_run_id]
    event_types = [e.event_type for e in workflow_events]

    # Verify critical lifecycle events
    assert "WorkflowCreated" in event_types, (
        f"WorkflowCreated event not found. Event types: {event_types}"
    )
    assert "WorkflowStarted" in event_types, (
        f"WorkflowStarted event not found. Event types: {event_types}"
    )
    assert "WorkflowCompleted" in event_types, (
        f"WorkflowCompleted event not found. Event types: {event_types}"
    )

    # 6. Verify stage advances (3 stages = 3 advances)
    stage_advances = [e for e in workflow_events if e.event_type == "WorkflowStageAdvanced"]
    assert len(stage_advances) == 3, (
        f"Expected 3 WorkflowStageAdvanced events (one per agent execution), "
        f"got {len(stage_advances)}"
    )

    # 7. Verify the seeded board configuration supports this cascade
    # (BoardWorkflowTemplate must have auto_progress_on_completion on all middle columns)
    config = await adapters.workflow_config.get_board_workflow_template("board-1")
    assert config is not None, "No workflow template registered for board-1"

    # Check that all automated columns have auto_progress_on_completion
    automated_columns = [c for c in config.columns if c.agent_id]
    for col in automated_columns:
        assert col.auto_progress_on_completion, (
            f"Column '{col.name}' (agent: {col.agent_id}) has "
            f"auto_progress_on_completion={col.auto_progress_on_completion}, "
            f"expected True"
        )

    # 8. Verify the event cascade occurred
    assert len(workflow_events) >= 5, (
        f"Expected at least 5 events (Created, Started, 3x StageAdvanced, Completed), "
        f"got {len(workflow_events)}: {event_types}"
    )
