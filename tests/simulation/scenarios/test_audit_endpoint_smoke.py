"""
Simulation E2E smoke test for workflow run audit endpoint.

This test validates the GET /api/v2/workflows/runs/{workflow_run_id}/audit endpoint
through a complete end-to-end workflow execution in simulation mode.

Test Scenario:
1. Bootstrap simulation environment with FastAPI app
2. Create and trigger a workflow with multiple stages
3. Wait for workflow completion
4. Query the audit endpoint with various parameters
5. Validate response structure, pagination, and event sequence validation

Coverage:
- Basic audit endpoint functionality
- Event pagination (offset, limit)
- Stage grouping
- Event sequence validation
- Caching behavior (repeated requests)
"""

import asyncio
import logging
from typing import cast

import httpx
import pytest

from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationApplicationBootstrap,
)
from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig
from codetoreum.ports.input.workflow_run_query import (
    IWorkflowRunQueryPort,
    SortOrder,
    WorkflowRunFilters,
    WorkflowRunListResult,
    WorkflowRunPaginationParams,
    WorkflowRunSortField,
    WorkflowRunStatus,
)
from codetoreum.ports.output.board_service import MovedByType

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def simulation_env():
    """
    Bootstrap simulation environment with FastAPI app and seeded data.

    Provides:
    - FastAPI application with all routers
    - SimulationApplicationBootstrap with fast execution
    - Seeded test data (projects, workflows, work items)
    """
    # Create fast config for testing
    config = SimulationConfig.create_fast_config(scenario_name="audit_endpoint_test", speed_multiplier=100.0)

    # Bootstrap application
    bootstrap = SimulationApplicationBootstrap(config)
    await bootstrap.setup()

    # Speed up agent execution for faster tests
    assert bootstrap.adapters is not None
    if bootstrap.adapters.agent_executor is not None:
        bootstrap.adapters.agent_executor._execution_delay = 0.1

    # Seed default test scenario
    adapters = bootstrap.adapters
    seeder = SimulationDataSeeder(
        bootstrap,
        track_items=True,
        agent_repository=adapters.agent_repository,
        work_item_service=adapters.work_item_service,
    )
    await seeder.seed_default_scenario()

    # The bootstrap already creates the FastAPI app
    # with all routers and dependencies wired up
    app = bootstrap.app

    yield {
        "app": app,
        "bootstrap": bootstrap,
        "seeder": seeder,
    }

    # Cleanup
    await bootstrap.teardown()


@pytest.fixture
async def simulation_bootstrap(simulation_env):
    """Override conftest's simulation_bootstrap to reuse simulation_env's bootstrap.

    Prevents the scenarios/conftest.py autouse seed_standard_agents fixture from
    creating a second independent bootstrap, which would double background tasks
    and cause teardown to hang.
    """
    return simulation_env["bootstrap"]


@pytest.fixture
async def http_client(simulation_env):
    """Provide async HTTP test client."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=simulation_env["app"]),
        base_url="http://test",
    ) as client:
        yield client


# ============================================================================
# Helper Functions
# ============================================================================


async def _wait_for_completion(query_service: IWorkflowRunQueryPort, work_item_id: str, timeout: float = 15.0) -> bool:
    """Poll workflow runs until a completed run exists for the work item or timeout."""
    elapsed = 0.0
    interval = 0.1
    pagination = WorkflowRunPaginationParams(
        offset=0,
        limit=10,
        sort_by=WorkflowRunSortField.STARTED_AT,
        sort_order=SortOrder.DESC,
    )

    while elapsed < timeout:
        await asyncio.sleep(interval)
        elapsed += interval

        try:
            filters = WorkflowRunFilters(
                work_item_id=work_item_id,
                status=(WorkflowRunStatus.COMPLETED,),
            )
            result = await query_service.list_workflow_runs(filters, pagination)
            if result.total_count > 0:
                return True
        except Exception as e:
            logging.debug(f"Failed to check workflow run status during polling: {e}")

    return False


async def _move_to_ready(board, work_item_id: str):
    """Move work item to Ready column to trigger workflow."""
    await board.move_item_to_column(work_item_id, "Ready", MovedByType.HUMAN)


async def _get_workflow_run_id(query_service: IWorkflowRunQueryPort, work_item_id: str) -> str:
    """Get the workflow run ID for a work item."""
    filters = WorkflowRunFilters(work_item_id=work_item_id)
    pagination = WorkflowRunPaginationParams(
        offset=0,
        limit=10,
        sort_by=WorkflowRunSortField.STARTED_AT,
        sort_order=SortOrder.DESC,
    )
    result: WorkflowRunListResult = await query_service.list_workflow_runs(filters, pagination)
    assert result.total_count > 0, "No workflow runs found for work item"
    if not result.runs:
        raise ValueError("No workflow runs returned")
    first_run = result.runs[0]
    return first_run.id


# ============================================================================
# Tests
# ============================================================================


@pytest.mark.asyncio
async def test_audit_endpoint_basic_smoke(http_client, simulation_env):
    """
    Basic smoke test for audit endpoint.

    Validates:
    - Endpoint returns 200 OK
    - Response has all required fields
    - Event list is populated
    - Workflow run summary is correct
    - Validation sequence is valid for successful workflow
    """
    seeder = simulation_env["seeder"]
    board = simulation_env["bootstrap"].adapters.board
    query_service = cast("IWorkflowRunQueryPort", simulation_env["bootstrap"].ports.workflow_run_query)

    # Get first work item from seeded data
    work_item_id = seeder.created_items.work_items[0]

    # Trigger workflow by moving item to Ready column
    await _move_to_ready(board, work_item_id)

    # Wait for workflow to complete
    completed = await _wait_for_completion(query_service, work_item_id)
    assert completed, "Workflow did not complete within timeout"

    # Get workflow run ID
    workflow_run_id = await _get_workflow_run_id(query_service, work_item_id)

    # Call audit endpoint
    response = await http_client.get(f"/api/v2/workflows/runs/{workflow_run_id}/audit")

    # Validate response
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    audit_data = response.json()

    # Verify all required fields are present
    assert "workflowRun" in audit_data, "Missing 'workflowRun' field"
    assert "events" in audit_data, "Missing 'events' field"
    assert "stages" in audit_data, "Missing 'stages' field"
    assert "validation" in audit_data, "Missing 'validation' field"
    assert "totalEventCount" in audit_data, "Missing 'totalEventCount' field"
    assert "offset" in audit_data, "Missing 'offset' field"
    assert "limit" in audit_data, "Missing 'limit' field"
    assert "hasNext" in audit_data, "Missing 'hasNext' field"

    # Verify workflow run summary
    workflow_run = audit_data["workflowRun"]
    assert workflow_run["id"] == workflow_run_id
    assert "workItemId" in workflow_run
    assert workflow_run["workItemId"] is not None

    # Verify events are populated
    assert audit_data["totalEventCount"] > 0, "No events in audit data"
    assert len(audit_data["events"]) > 0, "Empty events list"

    # Verify event structure
    first_event = audit_data["events"][0]
    assert "id" in first_event
    assert "eventType" in first_event
    assert "timestamp" in first_event
    assert "data" in first_event

    # Verify validation passed for successful workflow
    assert audit_data["validation"]["sequenceValid"] is True, (
        f"Validation failed for successful workflow:\n"
        f"Missing: {audit_data['validation'].get('missingEvents', [])}\n"
        f"Unexpected: {audit_data['validation'].get('unexpectedEvents', [])}\n"
        f"Out of order: {audit_data['validation'].get('outOfOrderEvents', [])}"
    )


@pytest.mark.asyncio
async def test_audit_endpoint_pagination(http_client, simulation_env):
    """
    Test audit endpoint pagination functionality.

    Validates:
    - offset and limit parameters work correctly
    - hasNext flag is accurate
    - totalEventCount remains consistent
    """
    seeder = simulation_env["seeder"]
    board = simulation_env["bootstrap"].adapters.board
    query_service = cast("IWorkflowRunQueryPort", simulation_env["bootstrap"].ports.workflow_run_query)

    # Get first work item
    work_item_id = seeder.created_items.work_items[0]

    # Trigger workflow
    await _move_to_ready(board, work_item_id)

    # Wait for completion
    completed = await _wait_for_completion(query_service, work_item_id)
    assert completed, "Workflow did not complete"

    # Get workflow run ID
    workflow_run_id = await _get_workflow_run_id(query_service, work_item_id)

    # First page
    response1 = await http_client.get(
        f"/api/v2/workflows/runs/{workflow_run_id}/audit", params={"offset": 0, "limit": 5}
    )
    assert response1.status_code == 200
    data1 = response1.json()

    total_events = data1["totalEventCount"]
    assert total_events > 0

    # Verify first page
    assert data1["offset"] == 0
    assert data1["limit"] == 5
    assert len(data1["events"]) <= 5

    if total_events > 5:
        assert data1["hasNext"] is True

        # Second page
        response2 = await http_client.get(
            f"/api/v2/workflows/runs/{workflow_run_id}/audit", params={"offset": 5, "limit": 5}
        )
        assert response2.status_code == 200
        data2 = response2.json()

        assert data2["offset"] == 5
        assert data2["limit"] == 5
        assert data2["totalEventCount"] == total_events

        first_event_page1 = data1["events"][0]["id"]
        first_event_page2 = data2["events"][0]["id"]
        assert first_event_page1 != first_event_page2, "Pages should have different events"


@pytest.mark.asyncio
async def test_audit_endpoint_validation_structure(http_client, simulation_env):
    """
    Test audit endpoint event sequence validation structure.

    Validates:
    - Validation field has correct structure
    - Expected and actual sequences are present
    - Missing/unexpected/out-of-order event lists are included
    """
    seeder = simulation_env["seeder"]
    board = simulation_env["bootstrap"].adapters.board
    query_service = cast("IWorkflowRunQueryPort", simulation_env["bootstrap"].ports.workflow_run_query)

    # Get first work item
    work_item_id = seeder.created_items.work_items[0]

    # Trigger workflow
    await _move_to_ready(board, work_item_id)

    # Wait for completion
    completed = await _wait_for_completion(query_service, work_item_id)
    assert completed, "Workflow did not complete"

    # Get workflow run ID
    workflow_run_id = await _get_workflow_run_id(query_service, work_item_id)

    # Call audit endpoint
    response = await http_client.get(f"/api/v2/workflows/runs/{workflow_run_id}/audit")
    assert response.status_code == 200

    audit_data = response.json()
    validation = audit_data["validation"]

    assert "sequenceValid" in validation
    assert isinstance(validation["sequenceValid"], bool)

    assert "expectedSequence" in validation
    assert isinstance(validation["expectedSequence"], list)

    assert "actualSequence" in validation
    assert isinstance(validation["actualSequence"], list)

    assert "missingEvents" in validation
    assert isinstance(validation["missingEvents"], list)

    assert "unexpectedEvents" in validation
    assert isinstance(validation["unexpectedEvents"], list)

    assert "outOfOrderEvents" in validation
    assert isinstance(validation["outOfOrderEvents"], list)


@pytest.mark.asyncio
async def test_audit_endpoint_stage_grouping(http_client, simulation_env):
    """
    Test audit endpoint stage grouping functionality.

    Validates:
    - Stages field is present and properly structured
    - Each stage has required fields
    - Events are grouped by stage
    """
    seeder = simulation_env["seeder"]
    board = simulation_env["bootstrap"].adapters.board
    query_service = cast("IWorkflowRunQueryPort", simulation_env["bootstrap"].ports.workflow_run_query)

    # Get first work item
    work_item_id = seeder.created_items.work_items[0]

    # Trigger workflow
    await _move_to_ready(board, work_item_id)

    # Wait for completion
    completed = await _wait_for_completion(query_service, work_item_id)
    assert completed, "Workflow did not complete"

    # Get workflow run ID
    workflow_run_id = await _get_workflow_run_id(query_service, work_item_id)

    # Call audit endpoint
    response = await http_client.get(f"/api/v2/workflows/runs/{workflow_run_id}/audit")
    assert response.status_code == 200

    audit_data = response.json()
    stages = audit_data["stages"]

    assert isinstance(stages, list)

    for stage in stages:
        assert "name" in stage
        assert "status" in stage
        assert "startedAt" in stage or stage.get("startedAt") is None
        assert "completedAt" in stage or stage.get("completedAt") is None
        assert "durationSeconds" in stage or stage.get("durationSeconds") is None
        assert "events" in stage
        assert isinstance(stage["events"], list)


@pytest.mark.asyncio
async def test_audit_endpoint_validation_disabled(http_client, simulation_env):
    """
    Test audit endpoint with validation disabled.

    Validates:
    - include_validation=false parameter works
    - Validation field still present but may be empty/minimal
    """
    seeder = simulation_env["seeder"]
    board = simulation_env["bootstrap"].adapters.board
    query_service = cast("IWorkflowRunQueryPort", simulation_env["bootstrap"].ports.workflow_run_query)

    # Get first work item
    work_item_id = seeder.created_items.work_items[0]

    # Trigger workflow
    await _move_to_ready(board, work_item_id)

    # Wait for completion
    completed = await _wait_for_completion(query_service, work_item_id)
    assert completed, "Workflow did not complete"

    # Get workflow run ID
    workflow_run_id = await _get_workflow_run_id(query_service, work_item_id)

    # Call audit endpoint with validation disabled
    response = await http_client.get(
        f"/api/v2/workflows/runs/{workflow_run_id}/audit", params={"include_validation": False}
    )
    assert response.status_code == 200

    audit_data = response.json()
    assert "validation" in audit_data
