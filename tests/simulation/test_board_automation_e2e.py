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
        poll_interval=0.05
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
        lock_is_released,
        timeout=2.0,
        poll_interval=0.05,
        message="Lock should be released after cascade"
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
        coder_has_executed,
        timeout=5.0,
        poll_interval=0.05,
        message="Coder should have been executed"
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

    cascade_stable = await wait_for_condition(
        cascade_has_stopped,
        timeout=0.5,
        poll_interval=0.05
    )
    assert cascade_stable, "Cascade should have stopped (executor execution count stabilized)"

    # Verify architect executed but cascade stopped after coder failure
    item_executions = [e for e in executor.executions if e["work_item_id"] == work_item_id]
    agent_ids = [e["agent_id"] for e in item_executions]
    assert "architect" in agent_ids, "Architect should have been triggered"
    assert "coder" in agent_ids, "Coder should have been triggered (and failed)"
    assert "tester" not in agent_ids, (
        f"Tester should NOT have been triggered after coder failure. "
        f"Executions: {agent_ids}"
    )
