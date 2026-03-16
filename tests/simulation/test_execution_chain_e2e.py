"""End-to-end test for the ExecutionService execution chain.

Exercises the full fire-and-forget chain when ExecutionServiceAgentExecutor
is active:

  human move → event bridge → BoardColumnEventHandler → ExecutionServiceAgentExecutor
     → ExecutionService (LLM path) → WorkspaceRouter (VCS ops) → completion callback
     → auto-progress → repeat.

Unlike the board automation tests that use MockAgentExecutor, these tests
exercise the real ExecutionService + WorkspaceRouter + InMemoryVersionControlService
path and verify that VCS events are emitted and the workflow lifecycle reaches
completion.
"""

from __future__ import annotations

import asyncio
from typing import cast

import pytest

from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationAdapters,
    SimulationApplicationBootstrap,
)
from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder
from codetoreum.ports.output.board_service import MovedByType
from tests.simulation.helpers import wait_for_column

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def exec_chain_env(
    simulation_bootstrap: SimulationApplicationBootstrap,
):
    """Bootstrap ExecutionServiceAgentExecutor + seed, with fast delay."""
    adapters = cast("SimulationAdapters", simulation_bootstrap.adapters)

    # ExecutionServiceAgentExecutor is the default executor (wired in SimulationApplicationBootstrap)
    # Set execution delay to 0.0 for fast tests
    if adapters.agent_executor is not None:
        adapters.agent_executor._execution_delay = 0.0

    # Seed using the agent_repository and work_item_service so domain objects
    # are available to the executor chain
    seeder = SimulationDataSeeder(
        simulation_bootstrap,
        track_items=True,
        agent_repository=adapters.agent_repository,
        work_item_service=adapters.work_item_service,
    )
    await seeder.seed_default_scenario()

    return simulation_bootstrap, seeder, adapters


# ============================================================================
# Tests
# ============================================================================


@pytest.mark.asyncio
async def test_execution_chain_llm_path_reaches_done(exec_chain_env):
    """When ExecutionServiceAgentExecutor is active, an item triggered by a
    human move should cascade through all stages and reach Done, with the
    MockLLMAdapter receiving at least one call per stage.
    """
    bootstrap, seeder, adapters = exec_chain_env
    board = adapters.board
    work_item_id = seeder.created_items.work_items[0]

    # Human moves item from Backlog → Ready (pipeline trigger)
    await board.move_item_to_column(work_item_id, "Ready", MovedByType.HUMAN)

    # Wait for cascade to reach Done (longer timeout: real execution chain)
    reached_done = await wait_for_column(board, work_item_id, "Done", timeout=30.0)
    assert reached_done, (
        f"Item did not reach 'Done' within timeout. "
        f"Current position: {(await board.get_item_position(work_item_id)).column_name}"
    )

    # Allow background cleanup tasks to settle
    await asyncio.sleep(0.3)

    # The LLM should have been called at least once (one call per stage: architect, coder, tester)
    llm_call_count = adapters.llm_provider.get_request_count()
    assert llm_call_count >= 1, f"Expected at least 1 LLM call via ExecutionService, got {llm_call_count}"

    # Verify movement history: Backlog → Ready → In Progress → Review → Done
    history = board.get_movement_history(work_item_id)
    assert len(history) == 4, (
        f"Expected 4 movements (Backlog→Ready, Ready→In Progress, "
        f"In Progress→Review, Review→Done), got {len(history)}"
    )
    columns_visited = [history[0].from_column] + [m.to_column for m in history]
    assert columns_visited == ["Backlog", "Ready", "In Progress", "Review", "Done"]


@pytest.mark.asyncio
async def test_execution_chain_emits_vcs_events(exec_chain_env):
    """When ExecutionServiceAgentExecutor drives an item to Done, the
    InMemoryVersionControlService should emit BranchCreatedEvent and
    CommitCreatedEvent for each stage that processes the item.
    """
    bootstrap, seeder, adapters = exec_chain_env
    board = adapters.board
    event_emitter = adapters.event_emitter
    work_item_id = seeder.created_items.work_items[0]

    # Human trigger
    await board.move_item_to_column(work_item_id, "Ready", MovedByType.HUMAN)

    # Wait for cascade to complete
    reached_done = await wait_for_column(board, work_item_id, "Done", timeout=30.0)
    assert reached_done, (
        f"Item did not reach 'Done'. " f"Current position: {(await board.get_item_position(work_item_id)).column_name}"
    )
    await asyncio.sleep(0.3)

    # Verify VCS events were emitted (branch created for at least one stage)
    branch_events = event_emitter.get_events_by_type("repository.branch_created")
    assert len(branch_events) >= 1, (
        f"Expected at least 1 BranchCreatedEvent, got {len(branch_events)}. "
        f"All emitted event types: {[getattr(e, 'type', None) for e in event_emitter.get_events()]}"
    )

    # Verify commit events were emitted (at least one commit per stage)
    commit_events = event_emitter.get_events_by_type("repository.commit_created")
    assert len(commit_events) >= 1, (
        f"Expected at least 1 CommitCreatedEvent, got {len(commit_events)}. "
        f"All emitted event types: {[getattr(e, 'type', None) for e in event_emitter.get_events()]}"
    )


@pytest.mark.asyncio
async def test_execution_chain_workflow_completes(exec_chain_env):
    """When ExecutionServiceAgentExecutor drives an item to Done, the
    EventStore should contain a complete workflow lifecycle:
    WorkflowCreated → WorkflowStarted → (stage advances) → WorkflowCompleted.
    """
    bootstrap, seeder, adapters = exec_chain_env
    board = adapters.board
    event_store = adapters.event_store
    work_item_id = seeder.created_items.work_items[0]

    # Human trigger
    await board.move_item_to_column(work_item_id, "Ready", MovedByType.HUMAN)

    # Wait for cascade to complete
    reached_done = await wait_for_column(board, work_item_id, "Done", timeout=30.0)
    assert reached_done, (
        f"Item did not reach 'Done'. " f"Current position: {(await board.get_item_position(work_item_id)).column_name}"
    )
    await asyncio.sleep(0.3)

    # Find workflow events for this work item
    all_events = event_store.get_all_events_list()
    workflow_events_for_item = [
        e for e in all_events if e.aggregate_type == "Workflow" and e.payload.get("work_item_id") == work_item_id
    ]
    assert len(workflow_events_for_item) > 0, (
        f"No Workflow events found for work_item_id={work_item_id!r} in EventStore. "
        f"Aggregate types present: {sorted({e.aggregate_type for e in all_events})}"
    )

    # All workflow events for this run share the same aggregate_id (workflow_run_id)
    workflow_run_id = workflow_events_for_item[0].aggregate_id
    run_events = [e for e in all_events if e.aggregate_id == workflow_run_id]
    event_types = [e.event_type for e in run_events]

    assert "WorkflowCreated" in event_types, f"WorkflowCreated missing; got: {event_types}"
    assert "WorkflowStarted" in event_types, f"WorkflowStarted missing; got: {event_types}"
    assert "WorkflowCompleted" in event_types, f"WorkflowCompleted missing; got: {event_types}"


@pytest.mark.asyncio
async def test_executions_endpoint_visibility(exec_chain_env):
    """Verify that the GET /api/v2/executions endpoint returns execution data
    after a simulation cascade (issue #371).

    This test ensures that ExecutionServiceAgentExecutor executions are visible
    through the REST API by:
    1. Running a simulation cascade with ExecutionServiceAgentExecutor
    2. Querying the /api/v2/executions endpoint
    3. Verifying that execution records are returned with correct data
    """
    bootstrap, seeder, adapters = exec_chain_env
    board = adapters.board
    work_item_id = seeder.created_items.work_items[0]

    # Human moves item from Backlog → Ready (pipeline trigger)
    await board.move_item_to_column(work_item_id, "Ready", MovedByType.HUMAN)

    # Wait for cascade to reach Done
    reached_done = await wait_for_column(board, work_item_id, "Done", timeout=30.0)
    assert reached_done, (
        f"Item did not reach 'Done' within timeout. "
        f"Current position: {(await board.get_item_position(work_item_id)).column_name}"
    )

    # Allow background cleanup tasks to settle
    await asyncio.sleep(0.3)

    # Query the executions endpoint via the execution query port
    execution_query_port = bootstrap.ports.execution_query
    assert execution_query_port is not None, "execution_query port not available"

    # List all executions
    result = await execution_query_port.list_executions()

    # Verify that executions were recorded
    # The default 3-stage pipeline (architect, coder, tester) should produce 3 execution records
    assert result.total_count >= 3, (
        f"Expected at least 3 executions from the 3-stage pipeline, "
        f"but got {result.total_count} for work_item_id={work_item_id}."
    )

    # Verify that the execution records contain the expected work item
    # All executions should be for the same work_item_id but different agents
    executions_for_work_item = [exe for exe in result.executions if exe.work_item_id == work_item_id]
    assert len(executions_for_work_item) >= 3, (
        f"Expected at least 3 executions for work_item_id={work_item_id}, "
        f"but got {len(executions_for_work_item)}. "
        f"All executions: {[(e.work_item_id, e.agent_id) for e in result.executions]}"
    )

    # Verify we have different agents (architect, coder, tester)
    agent_ids_for_work_item = {exe.agent_id for exe in executions_for_work_item}
    assert len(agent_ids_for_work_item) >= 3, (
        f"Expected executions for at least 3 different agents, "
        f"but got: {agent_ids_for_work_item}"
    )

    # Verify each execution has the expected fields populated
    for execution in executions_for_work_item:
        assert execution.id is not None, "Execution ID should not be None"
        assert execution.agent_id is not None, "Agent ID should not be None"
        assert execution.initialized_at is not None, "Initialized timestamp should not be None"
        assert execution.status is not None, "Status should not be None"
        assert execution.workflow_id is not None, "Workflow ID should not be None"
        assert execution.stage_name is not None, "Stage name should not be None"

        # Verify each execution can be retrieved by its unique ID
        single_execution = await execution_query_port.get_execution(execution.id)
        assert single_execution.id == execution.id
        assert single_execution.work_item_id == work_item_id
