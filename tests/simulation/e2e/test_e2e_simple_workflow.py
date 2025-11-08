"""
E2E Test: Simple 3-Stage Workflow

Tests a complete end-to-end workflow execution with:
- Work item creation
- Workflow triggering
- Monitoring via WebSocket
- Status verification
- Metrics collection
"""

import pytest
from datetime import timedelta

from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder


@pytest.mark.asyncio
@pytest.mark.simulation
async def test_simple_workflow_success(e2e_client, simulation_seeder):
    """
    Test complete 3-stage workflow execution from start to finish.

    Flow:
    1. Seed project, workflow, and agents
    2. Create work item
    3. Trigger workflow
    4. Monitor progress via WebSocket
    5. Verify completion
    6. Check metrics and events
    """
    # ========================================================================
    # Setup: Seed test data
    # ========================================================================
    seeder: SimulationDataSeeder = simulation_seeder

    # Create project with 3-stage workflow
    project = await seeder.create_project(
        project_id="test-project",
        name="Test Project",
        repository_url="https://github.com/test/repo",
    )

    # Create 3 agents for the workflow
    analyzer = await seeder.create_agent(
        agent_id="agent-analyzer",
        name="Analyzer Agent",
        capabilities=["analysis", "planning"],
    )

    coder = await seeder.create_agent(
        agent_id="agent-coder",
        name="Coder Agent",
        capabilities=["implementation", "coding"],
    )

    reviewer = await seeder.create_agent(
        agent_id="agent-reviewer",
        name="Reviewer Agent",
        capabilities=["review", "quality-check"],
    )

    # Create 3-stage workflow
    workflow = await seeder.create_workflow(
        workflow_id="test-workflow",
        name="3-Stage Development Workflow",
        project_id=project["id"],
        stages=[
            {"name": "analysis", "agent_id": analyzer["id"], "order": 0},
            {"name": "implementation", "agent_id": coder["id"], "order": 1},
            {"name": "review", "agent_id": reviewer["id"], "order": 2},
        ],
    )

    # ========================================================================
    # Test: Create work item
    # ========================================================================
    work_item = e2e_client.create_work_item(
        project_id=project["id"],
        title="Add user authentication",
        description="Implement JWT-based authentication for the API",
        labels=["feature", "security"],
        priority="HIGH",
    )

    assert work_item["id"] is not None
    assert work_item["status"] == "PENDING"
    assert work_item["title"] == "Add user authentication"

    # ========================================================================
    # Test: Connect WebSocket for real-time updates
    # ========================================================================
    ws_collector = e2e_client.connect_websocket(
        subscription_type="all_events",
        work_item_id=work_item["id"],
    )

    # ========================================================================
    # Test: Trigger workflow
    # ========================================================================
    trigger_result = e2e_client.trigger_workflow(
        work_item_id=work_item["id"],
        workflow_id=workflow["id"],
    )

    assert trigger_result["success"] is True
    assert "workflow_run_id" in trigger_result

    # ========================================================================
    # Test: Monitor progress
    # ========================================================================

    # Wait for workflow started event
    workflow_started = ws_collector.wait_for_event(
        event_type="workflow_started",
        timeout=5.0,
    )
    assert workflow_started is not None
    assert workflow_started["data"]["work_item_id"] == work_item["id"]

    # Advance time to allow stage 1 to complete
    e2e_client.advance_minutes(5)

    # Wait for stage 1 completion
    stage1_complete = ws_collector.wait_for_event(
        event_type="stage_completed",
        timeout=5.0,
        filter_fn=lambda e: e["data"].get("stage_name") == "analysis",
    )
    assert stage1_complete is not None

    # Advance time for stage 2
    e2e_client.advance_minutes(10)

    # Wait for stage 2 completion
    stage2_complete = ws_collector.wait_for_event(
        event_type="stage_completed",
        timeout=5.0,
        filter_fn=lambda e: e["data"].get("stage_name") == "implementation",
    )
    assert stage2_complete is not None

    # Advance time for stage 3
    e2e_client.advance_minutes(5)

    # Wait for stage 3 completion
    stage3_complete = ws_collector.wait_for_event(
        event_type="stage_completed",
        timeout=5.0,
        filter_fn=lambda e: e["data"].get("stage_name") == "review",
    )
    assert stage3_complete is not None

    # Wait for workflow completion
    workflow_complete = ws_collector.wait_for_event(
        event_type="workflow_completed",
        timeout=5.0,
    )
    assert workflow_complete is not None

    # ========================================================================
    # Test: Verify final status
    # ========================================================================
    final_work_item = await e2e_client.wait_for_work_item_status(
        work_item_id=work_item["id"],
        expected_status="COMPLETED",
        timeout=5.0,
    )

    assert final_work_item["status"] == "COMPLETED"
    assert final_work_item["workflow_id"] == workflow["id"]

    # ========================================================================
    # Test: Verify executions
    # ========================================================================
    executions = e2e_client.get_executions(work_item_id=work_item["id"])

    # Should have 3 executions (one per stage)
    assert len(executions) == 3

    # All should be successful
    for execution in executions:
        assert execution["status"] == "COMPLETED"

    # ========================================================================
    # Test: Verify metrics
    # ========================================================================
    e2e_client.assert_metrics_recorded(
        metric_name="workflow_duration",
        labels={"workflow_id": workflow["id"]},
        min_count=1,
    )

    e2e_client.assert_metrics_recorded(
        metric_name="execution_count",
        min_count=3,  # 3 stage executions
    )

    # ========================================================================
    # Test: Verify events
    # ========================================================================
    e2e_client.assert_events_recorded(
        event_type="WorkflowStarted",
        aggregate_id=work_item["id"],
        min_count=1,
    )

    e2e_client.assert_events_recorded(
        event_type="WorkflowCompleted",
        aggregate_id=work_item["id"],
        min_count=1,
    )


@pytest.mark.asyncio
@pytest.mark.simulation
async def test_simple_workflow_with_time_acceleration(e2e_client, simulation_seeder):
    """
    Test workflow with aggressive time acceleration.

    Verifies that time manipulation works correctly and workflow
    progresses as expected when time is advanced rapidly.
    """
    # ========================================================================
    # Setup: Use default scenario
    # ========================================================================
    seeder: SimulationDataSeeder = simulation_seeder
    await seeder.seed_default_scenario()

    # Get seeded project and workflow
    projects = e2e_client.list_work_items()
    assert len(projects) > 0

    # ========================================================================
    # Test: Create work item and trigger workflow
    # ========================================================================
    work_item = e2e_client.create_work_item(
        project_id="default-project",
        title="Test time acceleration",
        description="Verify time manipulation works correctly",
    )

    e2e_client.trigger_workflow(
        work_item_id=work_item["id"],
        workflow_id="default-workflow",
    )

    # ========================================================================
    # Test: Aggressive time advancement
    # ========================================================================

    # Advance time in large chunks
    e2e_client.advance_time(timedelta(hours=1))

    # Wait for completion with short timeout
    # (should complete quickly due to time acceleration)
    final_work_item = await e2e_client.wait_for_work_item_status(
        work_item_id=work_item["id"],
        expected_status="COMPLETED",
        timeout=5.0,
    )

    assert final_work_item["status"] == "COMPLETED"

    # Verify time was actually advanced
    current_time = e2e_client.clock.now()
    start_time = e2e_client.clock._start_time
    elapsed = current_time - start_time
    assert elapsed >= timedelta(hours=1)


@pytest.mark.asyncio
@pytest.mark.simulation
async def test_workflow_status_transitions(e2e_client, simulation_seeder):
    """
    Test that work item status transitions correctly through workflow.

    Verifies:
    - PENDING -> IN_PROGRESS -> COMPLETED
    - Status changes are reflected in API
    - Events are emitted for each transition
    """
    # ========================================================================
    # Setup
    # ========================================================================
    seeder: SimulationDataSeeder = simulation_seeder
    await seeder.seed_simple_scenario()

    # ========================================================================
    # Test: Create work item
    # ========================================================================
    work_item = e2e_client.create_work_item(
        project_id="simple-project",
        title="Test status transitions",
        description="Verify status changes",
    )

    # Initial status
    assert work_item["status"] == "PENDING"

    # ========================================================================
    # Test: Trigger workflow
    # ========================================================================
    e2e_client.trigger_workflow(
        work_item_id=work_item["id"],
        workflow_id="simple-workflow",
    )

    # Status should transition to IN_PROGRESS
    in_progress = await e2e_client.wait_for_work_item_status(
        work_item_id=work_item["id"],
        expected_status="IN_PROGRESS",
        timeout=5.0,
    )
    assert in_progress["status"] == "IN_PROGRESS"

    # ========================================================================
    # Test: Advance time to complete workflow
    # ========================================================================
    e2e_client.advance_time(timedelta(hours=2))

    # Status should transition to COMPLETED
    completed = await e2e_client.wait_for_work_item_status(
        work_item_id=work_item["id"],
        expected_status="COMPLETED",
        timeout=5.0,
    )
    assert completed["status"] == "COMPLETED"

    # ========================================================================
    # Test: Verify status change events
    # ========================================================================
    e2e_client.assert_events_recorded(
        event_type="WorkItemStatusChanged",
        aggregate_id=work_item["id"],
        min_count=2,  # PENDING->IN_PROGRESS, IN_PROGRESS->COMPLETED
    )
