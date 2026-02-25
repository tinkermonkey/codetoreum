"""End-to-end board automation cascade test.

Exercises the full fire-and-forget cascade through the bootstrap's plumbing:
human move → event bridge → handler → agent execution → completion callback →
auto-progress → repeat.

Unlike scenario tests A–E which manually call handle_column_change() and
handle_agent_completion() at each step, this test uses SimulationApplicationBootstrap
and SimulationDataSeeder to prove the wiring actually works end-to-end.
"""

import asyncio
from typing import cast

import pytest

from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationAdapters,
    SimulationApplicationBootstrap,
)
from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig
from codetoreum.ports.output.board_service import MovedByType

# ============================================================================
# Helpers
# ============================================================================


async def wait_for_column(board, work_item_id, target_column, timeout=5.0):
    """Poll item position until it reaches target column or timeout."""
    elapsed = 0.0
    interval = 0.05
    while elapsed < timeout:
        await asyncio.sleep(interval)
        elapsed += interval
        pos = await board.get_item_position(work_item_id)
        if pos.column_name == target_column:
            return True
    return False


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def e2e_env():
    """Bootstrap + seed, with fast agent execution delay."""
    config = SimulationConfig.create_fast_config("e2e_cascade")
    bootstrap = SimulationApplicationBootstrap(config)
    await bootstrap.setup()
    adapters = cast("SimulationAdapters", bootstrap.adapters)
    adapters.agent_executor._execution_delay = 0.1
    seeder = SimulationDataSeeder(bootstrap)
    await seeder.seed_default_scenario()
    yield bootstrap, seeder
    await bootstrap.teardown()


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

    # Verify all 3 agents were triggered in order
    executions = adapters.agent_executor.executions
    item_executions = [e for e in executions if e["work_item_id"] == work_item_id]
    agent_order = [e["agent_id"] for e in item_executions]
    assert agent_order == ["architect", "coder", "tester"], (
        f"Expected agents [architect, coder, tester], got {agent_order}"
    )

    # Verify movement history
    history = board.get_movement_history(work_item_id)
    assert len(history) == 4, (
        f"Expected 4 movements (Backlog→Ready, Ready→In Progress, "
        f"In Progress→Review, Review→Done), got {len(history)}"
    )

    # First move is HUMAN, rest are ORCHESTRATOR
    assert history[0].moved_by == MovedByType.HUMAN
    for move in history[1:]:
        assert move.moved_by == MovedByType.ORCHESTRATOR, (
            f"Expected ORCHESTRATOR for {move.from_column}→{move.to_column}, "
            f"got {move.moved_by}"
        )

    # Verify column progression path
    columns_visited = [history[0].from_column] + [m.to_column for m in history]
    assert columns_visited == ["Backlog", "Ready", "In Progress", "Review", "Done"]


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
    # Give the event loop time to process the exit-column handler that releases the lock.
    await asyncio.sleep(0.3)

    # Verify lock is released (lock_holder should be None)
    queue_state = await lock_service.get_queue_state(project_id, "board-1")
    assert queue_state.lock_holder is None, (
        f"Lock should be released after cascade, but holder is {queue_state.lock_holder}"
    )


@pytest.mark.asyncio
async def test_cascade_stops_on_agent_failure(e2e_env):
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
    original_simulate = executor._simulate_execution
    call_count = 0

    async def failing_simulate(work_item_id, agent_id, execution_id, started_at):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            # Second agent (coder) fails
            raise RuntimeError("Simulated coder failure")
        return await original_simulate(work_item_id, agent_id, execution_id, started_at)

    executor._simulate_execution = failing_simulate

    # Move item to trigger cascade
    await board.move_item_to_column(work_item_id, "Ready", MovedByType.HUMAN)

    # Wait for first agent to complete and item to move to In Progress
    reached_in_progress = await wait_for_column(
        board, work_item_id, "In Progress", timeout=5.0
    )
    assert reached_in_progress, "Item did not reach 'In Progress'"

    # Give time for the second agent to fail and not progress further
    await asyncio.sleep(0.5)

    # Item should still be in "In Progress" (coder failed, no auto-progress)
    pos = await board.get_item_position(work_item_id)
    assert pos.column_name == "In Progress", (
        f"Expected item to stay in 'In Progress' after coder failure, "
        f"but found in '{pos.column_name}'"
    )

    # Verify architect executed but cascade stopped after coder failure
    item_executions = [
        e for e in executor.executions if e["work_item_id"] == work_item_id
    ]
    agent_ids = [e["agent_id"] for e in item_executions]
    assert "architect" in agent_ids, "Architect should have been triggered"
    assert "coder" in agent_ids, "Coder should have been triggered (and failed)"
    assert "tester" not in agent_ids, "Tester should NOT have been triggered"
