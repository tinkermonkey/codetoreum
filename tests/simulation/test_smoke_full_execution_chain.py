"""Smoke test: full execution chain triggered via the HTTP trigger endpoint.

Validates the path exercised by ``codetoreum-trigger`` CLI:

    POST /api/v2/trigger/column-change
    → EventBus.publish(WorkItemColumnChangedEvent)
    → BoardColumnEventHandler (acquires pipeline lock for "Ready" column)
    → ExecutionServiceAgentExecutor._run_execution()
    → InMemoryVersionControlService.clone_repository()  ← creates workspace dir on disk
    → WorkspaceRouter.prepare_workspace()
    → ExecutionService.execute()  ← Phase D4 unified path
    → MockClaudeCodeAdapter.execute()  ← records (work_item, agent, mode, model)
    → completion callback → auto-progress: In Progress → Review → Done

This test is distinct from ``test_execution_chain_e2e.py``, which triggers
the board directly via ``MockBoardAdapter.move_item_to_column``.  Here the
trigger boundary is the HTTP API, matching the production CLI path.

Board layout created by ``seed_default_scenario()``:

    Backlog (MANUAL) → Ready* (AUTOMATED, architect, pipeline trigger)
    → In Progress (AUTOMATED, coder) → Review (AUTOMATED, tester)
    → Done (MANUAL, exit)

Items start in Backlog.  The HTTP trigger fires a WorkItemColumnChangedEvent
for ``to_column="Ready"``; the cascade completes without any direct adapter
manipulation after the initial POST.
"""

from __future__ import annotations

from typing import cast

import httpx
import pytest

from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationAdapters,
    SimulationApplicationBootstrap,
)
from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder
from tests.conftest import assert_condition
from tests.simulation.helpers import wait_for_column

# ---------------------------------------------------------------------------
# Constants matching seed_default_scenario() setup
# ---------------------------------------------------------------------------

_PROJECT_ID = "default-project"
_BOARD_ID = "board-1"
# "Ready" is the first AUTOMATED column — architect agent, is_pipeline_trigger=True
_TRIGGER_COLUMN = "Ready"


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def smoke_env(simulation_bootstrap: SimulationApplicationBootstrap):
    """Bootstrap + default scenario seed + zero-delay execution + async HTTP client.

    Mirrors the ``exec_chain_env`` fixture from ``test_execution_chain_e2e.py``
    but exposes an ``httpx.AsyncClient`` (ASGI transport) instead of the board
    adapter, so tests trigger the cascade via HTTP rather than the adapter
    directly.

    Using httpx.AsyncClient (not starlette.testclient.TestClient) is critical:
    the async ASGI transport runs in the SAME event loop as the test, so the
    event bus handler fires in the same loop and the board state can be polled
    from both the test and the handler without cross-loop races.
    """
    adapters = cast("SimulationAdapters", simulation_bootstrap.adapters)

    # Zero-delay so tests don't wait on artificial execution pauses
    if adapters.agent_executor is not None:
        adapters.agent_executor._execution_delay = 0.0

    seeder = SimulationDataSeeder(
        simulation_bootstrap,
        track_items=True,
        agent_repository=adapters.agent_repository,
        work_item_service=adapters.work_item_service,
    )
    await seeder.seed_default_scenario()

    # Stop AgentScheduler so WorkflowOrchestrator's enqueued tasks are never
    # consumed — prevents double-dispatch (BCEH + WO both handle the same
    # WorkItemColumnChangedEvent; only BCEH's direct execute() path should run).
    if simulation_bootstrap.services and simulation_bootstrap.services.agent_scheduler:
        await simulation_bootstrap.services.agent_scheduler.stop()

    # Pre-position all items in "Ready" so that handle_agent_completion(True)
    # sees the correct column when it checks the board after execution.
    # The HTTP trigger represents an external webhook fired AFTER the user moved
    # the card — in production the board adapter reads from the external system
    # and would correctly return "Ready".  In simulation we must set this manually.
    board_mock = adapters.board_as_mock()
    for item_id in seeder.created_items.work_items:
        board_mock.set_item_column_silent(item_id, "Backlog", _TRIGGER_COLUMN, _BOARD_ID, _PROJECT_ID)

    app = simulation_bootstrap.app
    if app is None:
        raise RuntimeError("SimulationApplicationBootstrap.app not initialised")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield simulation_bootstrap, seeder, adapters, client


# ============================================================================
# Tests
# ============================================================================


@pytest.mark.asyncio
async def test_http_trigger_returns_202_with_event_id(smoke_env):
    """POST /api/v2/trigger/column-change returns 202 Accepted with all required fields."""
    _, seeder, _, client = smoke_env
    work_item_id = seeder.created_items.work_items[0]

    response = await client.post(
        "/api/v2/trigger/column-change",
        json={
            "work_item_id": work_item_id,
            "to_column": _TRIGGER_COLUMN,
            "from_column": "Backlog",
            "project_id": _PROJECT_ID,
            "board_id": _BOARD_ID,
        },
    )

    assert response.status_code == 202, f"Expected 202 Accepted, got {response.status_code}: {response.text}"
    body = response.json()
    assert body["work_item_id"] == work_item_id
    assert body["to_column"] == _TRIGGER_COLUMN
    assert body["status"] == "published"
    assert (
        isinstance(body.get("event_id"), str) and body["event_id"]
    ), "event_id must be a non-empty string in the 202 response"


@pytest.mark.asyncio
async def test_http_trigger_drives_full_execution_chain(smoke_env):
    """HTTP trigger fires the full board automation cascade; work item reaches Done.

    Five key assertions are checked in order:

    1. Coding agent invocation was recorded — MockClaudeCodeAdapter captured
       at least one (work_item_id, agent_id, invocation_mode, model) tuple,
       which means ExecutionService.execute() dispatched through the new
       unified D4 path.
    2. Workspace directory exists on disk — InMemoryVersionControlService.clone_repository()
       creates the directory so that prepare_workspace() can write context files.
    3. Invocation references the right work item — at least one invocation
       carries the work_item_id that was triggered.
    4. Execution domain events are present — ExecutionCreatedEvent, ExecutionStartedEvent,
       and ExecutionCompletedEvent must all appear in the InMemoryEventStore.
    5. Work item reaches Done column — the cascade auto-progresses through all
       automated columns and completes.

    Note: The domain event emitted by AgentExecution.create() is
    ``ExecutionInitializedEvent`` (not "ExecutionCreatedEvent").
    """
    from codetoreum.adapters.testing.mock_claude_code_adapter import (
        MockClaudeCodeAdapter,
    )

    bootstrap, seeder, adapters, client = smoke_env
    board_mock = adapters.board_as_mock()
    coding_agent_mock = adapters.coding_agent
    assert isinstance(coding_agent_mock, MockClaudeCodeAdapter), (
        "Simulation bootstrap must wire MockClaudeCodeAdapter as the " "coding_agent slot (Phase D3/D4)."
    )
    work_item_id = seeder.created_items.work_items[0]

    # Fire the trigger — simulates `codetoreum-trigger --work-item-id X --column Ready`
    response = await client.post(
        "/api/v2/trigger/column-change",
        json={
            "work_item_id": work_item_id,
            "to_column": _TRIGGER_COLUMN,
            "from_column": "Backlog",
            "project_id": _PROJECT_ID,
            "board_id": _BOARD_ID,
        },
    )
    assert response.status_code == 202, f"Trigger endpoint rejected the request: {response.status_code} {response.text}"

    # --- Assertion 5: work item reaches Done ---
    reached_done = await wait_for_column(board_mock, work_item_id, "Done", timeout=30.0)
    assert reached_done, (
        f"Work item {work_item_id!r} did not reach 'Done' within timeout. "
        f"Current column: {(await board_mock.get_item_position(work_item_id)).column_name}"
    )

    # Wait for the coding agent to capture at least one invocation
    async def coding_agent_was_called():
        return len(coding_agent_mock.invocations) >= 1

    await assert_condition(
        coding_agent_was_called,
        timeout=5.0,
        poll_interval=0.05,
        message=(
            "MockClaudeCodeAdapter.execute() should have been invoked at "
            "least once via ExecutionService.execute() (Phase D4 path)."
        ),
    )

    # --- Assertion 1: at least one coding agent invocation recorded ---
    invocations = coding_agent_mock.invocations
    assert len(invocations) >= 1, (
        "MockClaudeCodeAdapter recorded no invocations — ExecutionService.execute() "
        "did not reach the coding-agent adapter."
    )

    # --- Assertion 2: workspace directory exists on disk ---
    # The executor clones into {workspace_base_dir}/{work_item_id}; the base
    # dir is configured in the simulation bootstrap (tempdir-rooted).
    from pathlib import Path

    executor = bootstrap.adapters.agent_executor
    workspace_path = Path(executor._workspace_base_dir) / work_item_id
    assert workspace_path.exists(), (
        f"Workspace directory does not exist on disk: {workspace_path}\n"
        "InMemoryVersionControlService.clone_repository() must call os.makedirs(target_path) "
        "so that WorkspaceRouter.prepare_workspace() can write /context/issue.txt and siblings."
    )

    # --- Assertion 3: invocation references the triggered work item ---
    triggered_invocations = [inv for inv in invocations if inv.work_item_id == work_item_id]
    assert triggered_invocations, (
        f"None of the coding-agent invocations reference work item {work_item_id!r}. "
        f"Recorded work_item_ids: {[inv.work_item_id for inv in invocations]}"
    )

    # --- Assertion 4: execution domain events ---
    event_store = adapters.event_store_as_memory()

    async def execution_events_recorded():
        return "ExecutionInitializedEvent" in {e.event_type for e in event_store.get_all_events_list()}

    await assert_condition(
        execution_events_recorded,
        timeout=5.0,
        poll_interval=0.05,
        message="ExecutionInitializedEvent must appear in the InMemoryEventStore",
    )

    all_events = event_store.get_all_events_list()
    event_types = {e.event_type for e in all_events}

    assert (
        "ExecutionInitializedEvent" in event_types
    ), f"ExecutionInitializedEvent missing. Event types present: {sorted(event_types)}"
    assert (
        "ExecutionStartedEvent" in event_types
    ), f"ExecutionStartedEvent missing. Event types present: {sorted(event_types)}"
    assert (
        "ExecutionCompletedEvent" in event_types
    ), f"ExecutionCompletedEvent missing. Event types present: {sorted(event_types)}"


@pytest.mark.asyncio
async def test_http_trigger_context_carries_execution_id(smoke_env):
    """The invocation passed to MockClaudeCodeAdapter carries an execution_id.

    This confirms that ExecutionService.create_execution() produced a persisted
    AgentExecution before ExecutionService.execute() was called — i.e., the
    full create → start → execute lifecycle ran correctly through the D4
    unified path.
    """
    from codetoreum.adapters.testing.mock_claude_code_adapter import (
        MockClaudeCodeAdapter,
    )

    _, seeder, adapters, client = smoke_env
    board_mock = adapters.board_as_mock()
    coding_agent_mock = adapters.coding_agent
    assert isinstance(coding_agent_mock, MockClaudeCodeAdapter)
    work_item_id = seeder.created_items.work_items[0]

    response = await client.post(
        "/api/v2/trigger/column-change",
        json={
            "work_item_id": work_item_id,
            "to_column": _TRIGGER_COLUMN,
            "from_column": "Backlog",
            "project_id": _PROJECT_ID,
            "board_id": _BOARD_ID,
        },
    )
    assert response.status_code == 202

    reached_done = await wait_for_column(board_mock, work_item_id, "Done", timeout=30.0)
    assert reached_done

    async def invocation_has_execution_id():
        return any(
            inv.execution_id is not None and inv.work_item_id == work_item_id for inv in coding_agent_mock.invocations
        )

    await assert_condition(
        invocation_has_execution_id,
        timeout=5.0,
        poll_interval=0.05,
        message=(
            "MockClaudeCodeAdapter invocations should carry execution_id "
            "after ExecutionService.create_execution() persists the AgentExecution."
        ),
    )

    matching = [inv for inv in coding_agent_mock.invocations if inv.work_item_id == work_item_id]
    assert matching, "No invocations recorded for the triggered work item"
    assert matching[0].execution_id is not None, (
        "MockClaudeCodeAdapter invocation has execution_id=None — ExecutionService "
        "did not wire the AgentExecution id through to the coding-agent dispatch."
    )


@pytest.mark.asyncio
async def test_http_trigger_sequential_items_both_reach_done(smoke_env):
    """Two items triggered sequentially via HTTP each complete the full cascade.

    Verifies the pipeline lock serialises concurrent work: item A completes
    before item B is triggered, ensuring no lock contention in this scenario.
    """
    _, seeder, adapters, client = smoke_env
    board_mock = adapters.board_as_mock()

    item_a = seeder.created_items.work_items[0]
    item_b = seeder.created_items.work_items[1]

    # Trigger item A
    resp_a = await client.post(
        "/api/v2/trigger/column-change",
        json={
            "work_item_id": item_a,
            "to_column": _TRIGGER_COLUMN,
            "from_column": "Backlog",
            "project_id": _PROJECT_ID,
            "board_id": _BOARD_ID,
        },
    )
    assert resp_a.status_code == 202

    # Wait for A to complete before triggering B (sequential ordering)
    reached_done_a = await wait_for_column(board_mock, item_a, "Done", timeout=30.0)
    assert reached_done_a, (
        f"Item A did not reach Done. " f"Current: {(await board_mock.get_item_position(item_a)).column_name}"
    )

    # Trigger item B
    resp_b = await client.post(
        "/api/v2/trigger/column-change",
        json={
            "work_item_id": item_b,
            "to_column": _TRIGGER_COLUMN,
            "from_column": "Backlog",
            "project_id": _PROJECT_ID,
            "board_id": _BOARD_ID,
        },
    )
    assert resp_b.status_code == 202

    reached_done_b = await wait_for_column(board_mock, item_b, "Done", timeout=30.0)
    assert reached_done_b, (
        f"Item B did not reach Done. " f"Current: {(await board_mock.get_item_position(item_b)).column_name}"
    )

    # Both items completed — the coding agent was invoked at least once per item
    from codetoreum.adapters.testing.mock_claude_code_adapter import (
        MockClaudeCodeAdapter,
    )

    coding_agent_mock = adapters.coding_agent
    assert isinstance(coding_agent_mock, MockClaudeCodeAdapter)
    assert len(coding_agent_mock.invocations) >= 2, (
        f"Expected at least 2 coding-agent invocations (one cascade per item), "
        f"got {len(coding_agent_mock.invocations)}"
    )
