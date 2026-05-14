"""End-to-end multi-project parallel simulation test.

Exercises simultaneous execution of two independent projects (Alpha and Beta)
through the full board automation cascade. Verifies that:
- Alpha agents only process Alpha work items
- Beta agents only process Beta work items
- Both projects complete independently without cross-contamination
- EventStore events carry the correct work_item_id values
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
from tests.conftest import assert_condition
from tests.simulation.helpers import wait_for_column

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def multi_project_env():
    """Bootstrap + seed two independent projects with fast agent execution."""
    config = SimulationConfig.create_fast_config("multi_project_e2e")
    bootstrap = SimulationApplicationBootstrap(config)
    await bootstrap.setup()

    adapters = cast("SimulationAdapters", bootstrap.adapters)
    if adapters.agent_executor is not None:
        adapters.agent_executor._execution_delay = 0.1

    seeder = SimulationDataSeeder(
        bootstrap,
        track_items=True,
        agent_repository=adapters.agent_repository,
        work_item_service=adapters.work_item_service,
    )
    alpha_id, beta_id = await seeder.seed_two_project_scenario()

    yield bootstrap, seeder, alpha_id, beta_id

    await bootstrap.teardown()


# ============================================================================
# Tests
# ============================================================================


@pytest.mark.asyncio
async def test_both_projects_cascade_to_done(multi_project_env):
    """Both Alpha and Beta work items should independently cascade to Done.

    Each project has its own board, workflow template, and agents.
    Triggering both simultaneously should result in both reaching Done
    without any cross-project interference.
    """
    bootstrap, seeder, alpha_id, beta_id = multi_project_env
    adapters = cast("SimulationAdapters", bootstrap.adapters)
    board = adapters.board

    # Trigger both projects simultaneously
    await asyncio.gather(
        board.move_item_to_column(alpha_id, "Ready", MovedByType.HUMAN),
        board.move_item_to_column(beta_id, "Ready", MovedByType.HUMAN),
    )

    # Wait for both to reach Done
    alpha_done, beta_done = await asyncio.gather(
        wait_for_column(board, alpha_id, "Done", timeout=15.0),
        wait_for_column(board, beta_id, "Done", timeout=15.0),
    )

    # Wait for async event handlers (e.g., _complete_workflow_run) to finish
    async def both_workflows_completed():
        executor = adapters.agent_executor
        alpha_execs = [e for e in executor.executions if e["work_item_id"] == alpha_id]
        beta_execs = [e for e in executor.executions if e["work_item_id"] == beta_id]
        # Each should have 3 executions (architect, coder, tester)
        return len(alpha_execs) >= 3 and len(beta_execs) >= 3

    await assert_condition(
        both_workflows_completed,
        timeout=5.0,
        poll_interval=0.05,
        message="Both workflows should complete with all agents executed",
    )

    assert alpha_done, (
        f"Alpha item did not reach 'Done' within timeout. "
        f"Current: {(await board.get_item_position(alpha_id)).column_name}"
    )
    assert beta_done, (
        f"Beta item did not reach 'Done' within timeout. "
        f"Current: {(await board.get_item_position(beta_id)).column_name}"
    )


@pytest.mark.asyncio
async def test_agent_isolation(multi_project_env):
    """Alpha agents should only process Alpha items; Beta agents only Beta items.

    Verifies that board_id is correctly propagated through execute() so that
    each project's agents are called exclusively for their own work items.
    """
    bootstrap, seeder, alpha_id, beta_id = multi_project_env
    adapters = cast("SimulationAdapters", bootstrap.adapters)
    board = adapters.board
    executor = adapters.agent_executor

    # Trigger both
    await asyncio.gather(
        board.move_item_to_column(alpha_id, "Ready", MovedByType.HUMAN),
        board.move_item_to_column(beta_id, "Ready", MovedByType.HUMAN),
    )

    # Wait for both to reach Done
    await asyncio.gather(
        wait_for_column(board, alpha_id, "Done", timeout=15.0),
        wait_for_column(board, beta_id, "Done", timeout=15.0),
    )

    # Wait for all executions to be recorded
    async def all_executions_recorded():
        alpha_executions = [e for e in executor.executions if e["work_item_id"] == alpha_id]
        beta_executions = [e for e in executor.executions if e["work_item_id"] == beta_id]
        # Each should have 3 executions (architect, coder, tester)
        return len(alpha_executions) >= 3 and len(beta_executions) >= 3

    await assert_condition(
        all_executions_recorded, timeout=5.0, poll_interval=0.05, message="All agent executions should be recorded"
    )

    executions = executor.executions

    # Alpha agents should only process alpha items
    alpha_executions = [e for e in executions if e["work_item_id"] == alpha_id]
    beta_executions = [e for e in executions if e["work_item_id"] == beta_id]

    assert len(alpha_executions) == 3, (
        f"Expected 3 alpha executions (architect, coder, tester), got {len(alpha_executions)}: "
        f"{[e['agent_id'] for e in alpha_executions]}"
    )
    assert len(beta_executions) == 3, (
        f"Expected 3 beta executions (architect, coder, tester), got {len(beta_executions)}: "
        f"{[e['agent_id'] for e in beta_executions]}"
    )

    # Verify alpha used alpha-prefixed agents only
    alpha_agent_ids = {e["agent_id"] for e in alpha_executions}
    assert alpha_agent_ids == {
        "alpha-architect",
        "alpha-coder",
        "alpha-tester",
    }, f"Alpha item should only use alpha agents, got: {alpha_agent_ids}"

    # Verify beta used beta-prefixed agents only
    beta_agent_ids = {e["agent_id"] for e in beta_executions}
    assert beta_agent_ids == {
        "beta-architect",
        "beta-coder",
        "beta-tester",
    }, f"Beta item should only use beta agents, got: {beta_agent_ids}"

    # Verify board_id isolation: alpha executions use board-alpha, beta use board-beta
    alpha_board_ids = {e["board_id"] for e in alpha_executions}
    beta_board_ids = {e["board_id"] for e in beta_executions}

    assert alpha_board_ids == {"board-alpha"}, f"Alpha executions should use board-alpha, got: {alpha_board_ids}"
    assert beta_board_ids == {"board-beta"}, f"Beta executions should use board-beta, got: {beta_board_ids}"


@pytest.mark.asyncio
async def test_event_store_work_item_ids(multi_project_env):
    """EventStore workflow lifecycle events should carry correct work_item_id values.

    Verifies that WorkflowCreated/WorkflowStarted/WorkflowCompleted events
    for alpha items reference alpha_id and beta events reference beta_id.
    """
    bootstrap, seeder, alpha_id, beta_id = multi_project_env
    adapters = cast("SimulationAdapters", bootstrap.adapters)
    board = adapters.board
    event_store = adapters.event_store

    # Trigger both
    await asyncio.gather(
        board.move_item_to_column(alpha_id, "Ready", MovedByType.HUMAN),
        board.move_item_to_column(beta_id, "Ready", MovedByType.HUMAN),
    )

    # Wait for both to reach Done
    await asyncio.gather(
        wait_for_column(board, alpha_id, "Done", timeout=15.0),
        wait_for_column(board, beta_id, "Done", timeout=15.0),
    )

    # Wait for events to be recorded in EventStore
    async def workflow_events_recorded_for_both():
        all_events = event_store.get_all_events_list()
        alpha_workflow_events = [
            e for e in all_events if e.aggregate_type == "Workflow" and e.payload.get("work_item_id") == alpha_id
        ]
        beta_workflow_events = [
            e for e in all_events if e.aggregate_type == "Workflow" and e.payload.get("work_item_id") == beta_id
        ]
        return len(alpha_workflow_events) > 0 and len(beta_workflow_events) > 0

    await assert_condition(
        workflow_events_recorded_for_both,
        timeout=5.0,
        poll_interval=0.05,
        message="Workflow events should be recorded for both projects",
    )

    all_events = event_store.get_all_events_list()

    # Find workflow lifecycle events for each work item
    alpha_workflow_events = [
        e for e in all_events if e.aggregate_type == "Workflow" and e.payload.get("work_item_id") == alpha_id
    ]
    beta_workflow_events = [
        e for e in all_events if e.aggregate_type == "Workflow" and e.payload.get("work_item_id") == beta_id
    ]

    assert len(alpha_workflow_events) > 0, f"No workflow lifecycle events found for alpha item {alpha_id}"
    assert len(beta_workflow_events) > 0, f"No workflow lifecycle events found for beta item {beta_id}"

    # Verify alpha events have the correct work_item_id (not beta)
    for event in alpha_workflow_events:
        assert (
            event.payload.get("work_item_id") == alpha_id
        ), f"Alpha workflow event has wrong work_item_id: {event.payload.get('work_item_id')}"

    # Verify beta events have the correct work_item_id (not alpha)
    for event in beta_workflow_events:
        assert (
            event.payload.get("work_item_id") == beta_id
        ), f"Beta workflow event has wrong work_item_id: {event.payload.get('work_item_id')}"

    # Verify both runs have WorkflowCompleted events
    alpha_run_id = alpha_workflow_events[0].aggregate_id
    beta_run_id = beta_workflow_events[0].aggregate_id

    alpha_run_events = [e for e in all_events if e.aggregate_id == alpha_run_id]
    beta_run_events = [e for e in all_events if e.aggregate_id == beta_run_id]

    alpha_event_types = [e.event_type for e in alpha_run_events]
    beta_event_types = [e.event_type for e in beta_run_events]

    assert "WorkflowCompletedEvent" in alpha_event_types, f"Alpha run missing WorkflowCompleted, got: {alpha_event_types}"
    assert "WorkflowCompletedEvent" in beta_event_types, f"Beta run missing WorkflowCompleted, got: {beta_event_types}"

    # Verify the two runs are independent (different aggregate_ids)
    assert alpha_run_id != beta_run_id, "Alpha and Beta should have separate workflow run IDs"
