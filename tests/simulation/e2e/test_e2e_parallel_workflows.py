"""
E2E Test: Parallel Workflow Execution

Tests concurrent workflow execution with:
- Multiple work items executing simultaneously
- Agent scheduling and queuing
- Concurrent WebSocket connections
- Performance under parallel load
"""

import pytest
import asyncio
from datetime import timedelta
from typing import List, Dict, Any

from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder


@pytest.mark.asyncio
@pytest.mark.simulation
async def test_parallel_workflows_10_items(e2e_client, simulation_seeder):
    """
    Test 10 work items executing in parallel.

    Verifies:
    - All work items complete successfully
    - No resource conflicts
    - Proper agent scheduling
    - Metrics for all executions
    """
    # ========================================================================
    # Setup: Seed project and workflow
    # ========================================================================
    seeder: SimulationDataSeeder = simulation_seeder

    project = await seeder.create_project(
        project_id="parallel-test-project",
        name="Parallel Test Project",
        repository_url="https://github.com/test/parallel-repo",
    )

    # Create agents
    agents = []
    for i in range(3):
        agent = await seeder.create_agent(
            agent_id=f"agent-{i}",
            name=f"Agent {i}",
            capabilities=["coding", "testing"],
        )
        agents.append(agent)

    # Create workflow
    workflow = await seeder.create_workflow(
        workflow_id="parallel-workflow",
        name="Parallel Workflow",
        project_id=project["id"],
        stages=[
            {"name": "stage1", "agent_id": agents[0]["id"], "order": 0},
            {"name": "stage2", "agent_id": agents[1]["id"], "order": 1},
            {"name": "stage3", "agent_id": agents[2]["id"], "order": 2},
        ],
    )

    # ========================================================================
    # Test: Create 10 work items
    # ========================================================================
    work_items = []
    for i in range(10):
        work_item = e2e_client.create_work_item(
            project_id=project["id"],
            title=f"Parallel work item {i}",
            description=f"Work item {i} for parallel execution test",
            labels=["parallel-test"],
            priority="MEDIUM",
        )
        work_items.append(work_item)

    assert len(work_items) == 10

    # ========================================================================
    # Test: Trigger all workflows in parallel
    # ========================================================================
    trigger_results = []
    for work_item in work_items:
        result = e2e_client.trigger_workflow(
            work_item_id=work_item["id"],
            workflow_id=workflow["id"],
        )
        trigger_results.append(result)

    # All triggers should succeed
    assert all(r["success"] for r in trigger_results)

    # ========================================================================
    # Test: Advance time to allow all workflows to complete
    # ========================================================================
    # Advance time in chunks to simulate realistic execution
    for _ in range(10):
        e2e_client.advance_minutes(5)
        await asyncio.sleep(0.1)  # Allow event processing

    # ========================================================================
    # Test: Wait for all work items to complete
    # ========================================================================
    completed_items = []
    for work_item in work_items:
        try:
            completed = await e2e_client.wait_for_work_item_status(
                work_item_id=work_item["id"],
                expected_status="COMPLETED",
                timeout=10.0,
            )
            completed_items.append(completed)
        except TimeoutError:
            # Get current status for debugging
            current = e2e_client.get_work_item(work_item["id"])
            pytest.fail(
                f"Work item {work_item['id']} did not complete. "
                f"Current status: {current['status']}"
            )

    # All should complete
    assert len(completed_items) == 10

    # ========================================================================
    # Test: Verify all executions
    # ========================================================================
    all_executions = e2e_client.get_executions()

    # Should have 30 executions (10 work items × 3 stages)
    assert len(all_executions) >= 30

    # Count completed executions
    completed_executions = [
        e for e in all_executions if e["status"] == "COMPLETED"
    ]
    assert len(completed_executions) >= 30

    # ========================================================================
    # Test: Verify metrics
    # ========================================================================
    e2e_client.assert_metrics_recorded(
        metric_name="execution_count",
        min_count=30,
    )

    # Each work item should have metrics
    for work_item in work_items:
        e2e_client.assert_events_recorded(
            event_type="WorkflowCompleted",
            aggregate_id=work_item["id"],
            min_count=1,
        )


@pytest.mark.asyncio
@pytest.mark.simulation
async def test_parallel_workflows_with_websocket_monitoring(e2e_client, simulation_seeder):
    """
    Test parallel workflows with WebSocket monitoring.

    Verifies:
    - WebSocket receives events from all workflows
    - No events are lost during parallel execution
    - Events are properly filtered by work item
    """
    # ========================================================================
    # Setup
    # ========================================================================
    seeder: SimulationDataSeeder = simulation_seeder
    await seeder.seed_default_scenario()

    # ========================================================================
    # Test: Create 5 work items
    # ========================================================================
    work_items = []
    ws_collectors = []

    for i in range(5):
        work_item = e2e_client.create_work_item(
            project_id="default-project",
            title=f"WS monitored item {i}",
            description=f"Work item {i} with WebSocket monitoring",
        )
        work_items.append(work_item)

        # Connect WebSocket for each work item
        ws_collector = e2e_client.connect_websocket(
            subscription_type="all_events",
            work_item_id=work_item["id"],
        )
        ws_collectors.append(ws_collector)

    # ========================================================================
    # Test: Trigger all workflows
    # ========================================================================
    for work_item in work_items:
        e2e_client.trigger_workflow(
            work_item_id=work_item["id"],
            workflow_id="default-workflow",
        )

    # ========================================================================
    # Test: Advance time
    # ========================================================================
    e2e_client.advance_time(timedelta(hours=1))

    # ========================================================================
    # Test: Wait for completion and collect WebSocket events
    # ========================================================================
    for i, work_item in enumerate(work_items):
        # Wait for completion
        await e2e_client.wait_for_work_item_status(
            work_item_id=work_item["id"],
            expected_status="COMPLETED",
            timeout=10.0,
        )

        # Verify WebSocket received workflow started event
        ws_collectors[i].assert_event_received(
            event_type="workflow_started",
            filter_fn=lambda e: e["data"].get("work_item_id") == work_item["id"],
        )

        # Verify WebSocket received workflow completed event
        ws_collectors[i].assert_event_received(
            event_type="workflow_completed",
            filter_fn=lambda e: e["data"].get("work_item_id") == work_item["id"],
        )

    # ========================================================================
    # Test: Verify event counts
    # ========================================================================
    for i, ws_collector in enumerate(ws_collectors):
        # Each work item should receive multiple events
        assert len(ws_collector.received_events) >= 2  # At least start and complete


@pytest.mark.asyncio
@pytest.mark.simulation
async def test_concurrent_workflow_triggers_no_race_conditions(e2e_client, simulation_seeder):
    """
    Test that concurrent workflow triggers don't cause race conditions.

    Verifies:
    - Work items can be triggered simultaneously
    - No duplicate executions
    - Proper state management under concurrency
    """
    # ========================================================================
    # Setup
    # ========================================================================
    seeder: SimulationDataSeeder = simulation_seeder
    await seeder.seed_default_scenario()

    # ========================================================================
    # Test: Create work item
    # ========================================================================
    work_item = e2e_client.create_work_item(
        project_id="default-project",
        title="Concurrent trigger test",
        description="Test concurrent workflow triggers",
    )

    # ========================================================================
    # Test: Try to trigger workflow multiple times simultaneously
    # ========================================================================
    # Note: Only the first trigger should succeed
    # Subsequent triggers should be idempotent or rejected

    async def trigger_workflow():
        """Helper to trigger workflow."""
        try:
            result = e2e_client.trigger_workflow(
                work_item_id=work_item["id"],
                workflow_id="default-workflow",
            )
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    # Trigger 5 times concurrently
    results = await asyncio.gather(*[trigger_workflow() for _ in range(5)])

    # Count successful triggers
    successful_triggers = [r for r in results if r.get("success")]

    # Should have exactly 1 successful trigger
    # (or all 5 if idempotent, but no duplicate executions)
    assert len(successful_triggers) >= 1

    # ========================================================================
    # Test: Advance time and complete workflow
    # ========================================================================
    e2e_client.advance_time(timedelta(hours=1))

    await e2e_client.wait_for_work_item_status(
        work_item_id=work_item["id"],
        expected_status="COMPLETED",
        timeout=10.0,
    )

    # ========================================================================
    # Test: Verify no duplicate executions
    # ========================================================================
    executions = e2e_client.get_executions(work_item_id=work_item["id"])

    # Count executions by stage
    stage_execution_counts: Dict[str, int] = {}
    for execution in executions:
        stage = execution.get("stage_name", "unknown")
        stage_execution_counts[stage] = stage_execution_counts.get(stage, 0) + 1

    # Each stage should be executed exactly once
    for stage, count in stage_execution_counts.items():
        assert count == 1, f"Stage {stage} executed {count} times (expected 1)"


@pytest.mark.asyncio
@pytest.mark.simulation
async def test_agent_scheduling_under_parallel_load(e2e_client, simulation_seeder):
    """
    Test agent scheduling behavior under parallel load.

    Verifies:
    - Agents handle multiple work items correctly
    - Queue management works properly
    - No agent starvation
    """
    # ========================================================================
    # Setup: Single agent workflow
    # ========================================================================
    seeder: SimulationDataSeeder = simulation_seeder

    project = await seeder.create_project(
        project_id="scheduling-test-project",
        name="Scheduling Test Project",
    )

    # Single agent that will be shared
    agent = await seeder.create_agent(
        agent_id="shared-agent",
        name="Shared Agent",
        capabilities=["coding"],
    )

    # Single-stage workflow using the shared agent
    workflow = await seeder.create_workflow(
        workflow_id="single-agent-workflow",
        name="Single Agent Workflow",
        project_id=project["id"],
        stages=[
            {"name": "coding", "agent_id": agent["id"], "order": 0},
        ],
    )

    # ========================================================================
    # Test: Create 10 work items (all will compete for same agent)
    # ========================================================================
    work_items = []
    for i in range(10):
        work_item = e2e_client.create_work_item(
            project_id=project["id"],
            title=f"Scheduled item {i}",
            description=f"Work item {i} for agent scheduling test",
        )
        work_items.append(work_item)

    # ========================================================================
    # Test: Trigger all workflows
    # ========================================================================
    for work_item in work_items:
        e2e_client.trigger_workflow(
            work_item_id=work_item["id"],
            workflow_id=workflow["id"],
        )

    # ========================================================================
    # Test: Advance time to allow sequential execution
    # ========================================================================
    # Each execution takes some time, so advance enough for all 10
    e2e_client.advance_time(timedelta(hours=3))

    # ========================================================================
    # Test: Verify all work items complete
    # ========================================================================
    for work_item in work_items:
        completed = await e2e_client.wait_for_work_item_status(
            work_item_id=work_item["id"],
            expected_status="COMPLETED",
            timeout=10.0,
        )
        assert completed["status"] == "COMPLETED"

    # ========================================================================
    # Test: Verify scheduler metrics
    # ========================================================================
    e2e_client.assert_metrics_recorded(
        metric_name="agent_queue_depth",
        labels={"agent_id": agent["id"]},
        min_count=1,
    )

    # All executions should complete
    executions = e2e_client.get_executions()
    assert len([e for e in executions if e["status"] == "COMPLETED"]) == 10
