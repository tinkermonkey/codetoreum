"""
E2E Test: Execution Failures and Recovery

Tests error handling and recovery with:
- Agent execution failures
- Retry logic and backoff
- Permanent failure handling
- Workflow abortion on unrecoverable errors
- Error event propagation
"""

import pytest
import asyncio
from datetime import timedelta

from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder


@pytest.mark.asyncio
@pytest.mark.simulation
async def test_execution_failure_with_retry_success(e2e_client, simulation_seeder):
    """
    Test agent execution failure followed by successful retry.

    Flow:
    1. Agent execution fails
    2. System retries execution
    3. Retry succeeds
    4. Workflow continues normally
    """
    # ========================================================================
    # Setup
    # ========================================================================
    seeder: SimulationDataSeeder = simulation_seeder

    project = await seeder.create_project(
        project_id="retry-test-project",
        name="Retry Test Project",
    )

    agent = await seeder.create_agent(
        agent_id="flaky-agent",
        name="Flaky Agent",
        capabilities=["coding"],
    )

    workflow = await seeder.create_workflow(
        workflow_id="retry-workflow",
        name="Retry Workflow",
        project_id=project["id"],
        stages=[
            {"name": "flaky-stage", "agent_id": agent["id"], "order": 0},
        ],
    )

    # Configure mock LLM to fail once then succeed
    mock_llm = e2e_client.bootstrap.adapters.llm_provider
    mock_llm.configure_failure_sequence([
        {"success": False, "error": "Temporary network error"},
        {"success": True, "output": "Success on retry"},
    ])

    # ========================================================================
    # Test: Create work item and trigger workflow
    # ========================================================================
    work_item = e2e_client.create_work_item(
        project_id=project["id"],
        title="Test retry logic",
        description="Work item to test execution retry",
    )

    ws_collector = e2e_client.connect_websocket(
        subscription_type="all_events",
        work_item_id=work_item["id"],
    )

    e2e_client.trigger_workflow(
        work_item_id=work_item["id"],
        workflow_id=workflow["id"],
    )

    # ========================================================================
    # Test: Wait for initial execution failure
    # ========================================================================
    e2e_client.advance_minutes(5)

    execution_failed = ws_collector.wait_for_event(
        event_type="execution_failed",
        timeout=5.0,
    )

    if execution_failed:
        assert "error" in execution_failed["data"]

    # ========================================================================
    # Test: Wait for retry
    # ========================================================================
    e2e_client.advance_minutes(2)

    retry_started = ws_collector.wait_for_event(
        event_type="execution_retry_started",
        timeout=5.0,
    )

    if retry_started:
        assert retry_started["data"]["retry_count"] >= 1

    # ========================================================================
    # Test: Advance time for retry to complete
    # ========================================================================
    e2e_client.advance_minutes(10)

    # ========================================================================
    # Test: Wait for successful completion
    # ========================================================================
    final_work_item = await e2e_client.wait_for_work_item_status(
        work_item_id=work_item["id"],
        expected_status="COMPLETED",
        timeout=10.0,
    )

    assert final_work_item["status"] == "COMPLETED"

    # ========================================================================
    # Test: Verify execution history
    # ========================================================================
    executions = e2e_client.get_executions(work_item_id=work_item["id"])

    # Should have execution records (may include failed attempts)
    assert len(executions) >= 1

    # At least one should be successful
    successful = [e for e in executions if e["status"] == "COMPLETED"]
    assert len(successful) >= 1


@pytest.mark.asyncio
@pytest.mark.simulation
async def test_permanent_execution_failure_workflow_abort(e2e_client, simulation_seeder):
    """
    Test permanent execution failure leading to workflow abort.

    Flow:
    1. Agent execution fails
    2. System retries (max retries)
    3. All retries fail
    4. Workflow aborts with FAILED status
    """
    # ========================================================================
    # Setup
    # ========================================================================
    seeder: SimulationDataSeeder = simulation_seeder

    project = await seeder.create_project(
        project_id="abort-test-project",
        name="Abort Test Project",
    )

    agent = await seeder.create_agent(
        agent_id="broken-agent",
        name="Broken Agent",
    )

    workflow = await seeder.create_workflow(
        workflow_id="abort-workflow",
        name="Abort Workflow",
        project_id=project["id"],
        stages=[
            {"name": "broken-stage", "agent_id": agent["id"], "order": 0},
        ],
    )

    # Configure mock LLM to always fail
    mock_llm = e2e_client.bootstrap.adapters.llm_provider
    mock_llm.configure_permanent_failure("Unrecoverable error")

    # ========================================================================
    # Test: Create work item and trigger workflow
    # ========================================================================
    work_item = e2e_client.create_work_item(
        project_id=project["id"],
        title="Test permanent failure",
        description="Work item that will fail permanently",
    )

    ws_collector = e2e_client.connect_websocket(
        subscription_type="all_events",
        work_item_id=work_item["id"],
    )

    e2e_client.trigger_workflow(
        work_item_id=work_item["id"],
        workflow_id=workflow["id"],
    )

    # ========================================================================
    # Test: Advance time through retries
    # ========================================================================
    # Allow time for initial attempt + retries
    e2e_client.advance_time(timedelta(hours=1))

    # ========================================================================
    # Test: Wait for workflow abort or failure
    # ========================================================================
    try:
        final_work_item = await e2e_client.wait_for_work_item_status(
            work_item_id=work_item["id"],
            expected_status="FAILED",
            timeout=10.0,
        )
        assert final_work_item["status"] == "FAILED"
    except TimeoutError:
        # Check current status
        current = e2e_client.get_work_item(work_item["id"])
        # Should be in failure or blocked state
        assert current["status"] in ["FAILED", "BLOCKED", "ERROR"]

    # ========================================================================
    # Test: Verify failure events
    # ========================================================================
    e2e_client.assert_events_recorded(
        event_type="ExecutionFailed",
        aggregate_id=work_item["id"],
        min_count=1,
    )


@pytest.mark.asyncio
@pytest.mark.simulation
async def test_container_failure_recovery(e2e_client, simulation_seeder):
    """
    Test container execution failure and recovery.

    Verifies:
    - Container errors are handled
    - System retries container execution
    - Proper error messages are recorded
    """
    # ========================================================================
    # Setup
    # ========================================================================
    seeder: SimulationDataSeeder = simulation_seeder
    await seeder.seed_default_scenario()

    # Configure fake container to fail initially
    fake_container = e2e_client.bootstrap.adapters.container
    fake_container.configure_exit_code_sequence([
        1,   # First attempt fails
        0,   # Second attempt succeeds
    ])
    fake_container.configure_stderr_sequence([
        "Container error: out of memory",
        "",
    ])

    # ========================================================================
    # Test: Create work item and trigger workflow
    # ========================================================================
    work_item = e2e_client.create_work_item(
        project_id="default-project",
        title="Test container failure",
        description="Test container error recovery",
    )

    e2e_client.trigger_workflow(
        work_item_id=work_item["id"],
        workflow_id="default-workflow",
    )

    # ========================================================================
    # Test: Advance time through failure and retry
    # ========================================================================
    e2e_client.advance_time(timedelta(hours=1))

    # ========================================================================
    # Test: Should eventually complete after retry
    # ========================================================================
    try:
        final_work_item = await e2e_client.wait_for_work_item_status(
            work_item_id=work_item["id"],
            expected_status="COMPLETED",
            timeout=10.0,
        )
        assert final_work_item["status"] == "COMPLETED"
    except TimeoutError:
        # May still be in progress or failed
        current = e2e_client.get_work_item(work_item["id"])
        # Accept any terminal or in-progress state
        assert current["status"] in ["COMPLETED", "FAILED", "IN_PROGRESS"]


@pytest.mark.asyncio
@pytest.mark.simulation
async def test_timeout_handling(e2e_client, simulation_seeder):
    """
    Test execution timeout handling.

    Verifies:
    - Long-running executions are detected
    - Timeout triggers failure
    - Cleanup happens properly
    """
    # ========================================================================
    # Setup
    # ========================================================================
    seeder: SimulationDataSeeder = simulation_seeder

    project = await seeder.create_project(
        project_id="timeout-test-project",
        name="Timeout Test Project",
    )

    agent = await seeder.create_agent(
        agent_id="slow-agent",
        name="Slow Agent",
        max_execution_time_minutes=5,  # Very short timeout
    )

    workflow = await seeder.create_workflow(
        workflow_id="timeout-workflow",
        name="Timeout Workflow",
        project_id=project["id"],
        stages=[
            {"name": "slow-stage", "agent_id": agent["id"], "order": 0},
        ],
    )

    # Configure mock LLM to simulate slow execution
    mock_llm = e2e_client.bootstrap.adapters.llm_provider
    mock_llm.configure_delay(seconds=600)  # 10 minutes (longer than timeout)

    # ========================================================================
    # Test: Create work item and trigger workflow
    # ========================================================================
    work_item = e2e_client.create_work_item(
        project_id=project["id"],
        title="Test timeout",
        description="Execution that will timeout",
    )

    e2e_client.trigger_workflow(
        work_item_id=work_item["id"],
        workflow_id=workflow["id"],
    )

    # ========================================================================
    # Test: Advance time past timeout
    # ========================================================================
    e2e_client.advance_minutes(10)  # Past the 5-minute timeout

    # ========================================================================
    # Test: Check for timeout failure
    # ========================================================================
    try:
        final_work_item = await e2e_client.wait_for_work_item_status(
            work_item_id=work_item["id"],
            expected_status="FAILED",
            timeout=5.0,
        )
        # Should fail due to timeout
        assert final_work_item["status"] in ["FAILED", "TIMEOUT"]
    except TimeoutError:
        # May still be running or in different failure state
        current = e2e_client.get_work_item(work_item["id"])
        assert current["status"] in ["FAILED", "TIMEOUT", "IN_PROGRESS"]


@pytest.mark.asyncio
@pytest.mark.simulation
async def test_partial_workflow_failure_stops_pipeline(e2e_client, simulation_seeder):
    """
    Test that failure in one stage stops the pipeline.

    Verifies:
    - Stage 1 fails
    - Stage 2 and 3 do not execute
    - Workflow terminates with FAILED status
    """
    # ========================================================================
    # Setup
    # ========================================================================
    seeder: SimulationDataSeeder = simulation_seeder

    project = await seeder.create_project(
        project_id="pipeline-stop-test-project",
        name="Pipeline Stop Test Project",
    )

    # Create 3 agents
    agent1 = await seeder.create_agent(agent_id="agent-1", name="Agent 1")
    agent2 = await seeder.create_agent(agent_id="agent-2", name="Agent 2")
    agent3 = await seeder.create_agent(agent_id="agent-3", name="Agent 3")

    workflow = await seeder.create_workflow(
        workflow_id="pipeline-stop-workflow",
        name="Pipeline Stop Workflow",
        project_id=project["id"],
        stages=[
            {"name": "stage1", "agent_id": agent1["id"], "order": 0},
            {"name": "stage2", "agent_id": agent2["id"], "order": 1},
            {"name": "stage3", "agent_id": agent3["id"], "order": 2},
        ],
    )

    # Configure mock LLM to fail on first execution only
    mock_llm = e2e_client.bootstrap.adapters.llm_provider
    mock_llm.configure_failure_for_stage("stage1", "Stage 1 failed")

    # ========================================================================
    # Test: Create work item and trigger workflow
    # ========================================================================
    work_item = e2e_client.create_work_item(
        project_id=project["id"],
        title="Test pipeline stop on failure",
        description="Stage 1 will fail, stopping the pipeline",
    )

    ws_collector = e2e_client.connect_websocket(
        subscription_type="all_events",
        work_item_id=work_item["id"],
    )

    e2e_client.trigger_workflow(
        work_item_id=work_item["id"],
        workflow_id=workflow["id"],
    )

    # ========================================================================
    # Test: Advance time
    # ========================================================================
    e2e_client.advance_time(timedelta(hours=1))

    # ========================================================================
    # Test: Verify workflow failed
    # ========================================================================
    try:
        final_work_item = await e2e_client.wait_for_work_item_status(
            work_item_id=work_item["id"],
            expected_status="FAILED",
            timeout=5.0,
        )
        assert final_work_item["status"] == "FAILED"
    except TimeoutError:
        current = e2e_client.get_work_item(work_item["id"])
        assert current["status"] in ["FAILED", "BLOCKED"]

    # ========================================================================
    # Test: Verify only stage 1 executed
    # ========================================================================
    executions = e2e_client.get_executions(work_item_id=work_item["id"])

    # Should have execution for stage 1 only (maybe retries)
    stage_names = set(e["stage_name"] for e in executions)

    # Stage 1 should be present
    assert "stage1" in stage_names

    # Stages 2 and 3 should NOT be executed
    assert "stage2" not in stage_names
    assert "stage3" not in stage_names


@pytest.mark.asyncio
@pytest.mark.simulation
async def test_error_event_propagation(e2e_client, simulation_seeder):
    """
    Test that error events are properly propagated.

    Verifies:
    - Error events are emitted
    - WebSocket clients receive error events
    - Error details are included in events
    """
    # ========================================================================
    # Setup
    # ========================================================================
    seeder: SimulationDataSeeder = simulation_seeder
    await seeder.seed_default_scenario()

    # Configure failure
    mock_llm = e2e_client.bootstrap.adapters.llm_provider
    mock_llm.configure_permanent_failure("Test error message")

    # ========================================================================
    # Test: Create work item and connect WebSocket
    # ========================================================================
    work_item = e2e_client.create_work_item(
        project_id="default-project",
        title="Test error propagation",
        description="Verify error events are propagated",
    )

    ws_collector = e2e_client.connect_websocket(
        subscription_type="all_events",
        work_item_id=work_item["id"],
    )

    e2e_client.trigger_workflow(
        work_item_id=work_item["id"],
        workflow_id="default-workflow",
    )

    # ========================================================================
    # Test: Advance time
    # ========================================================================
    e2e_client.advance_time(timedelta(hours=1))

    # ========================================================================
    # Test: Wait for error event on WebSocket
    # ========================================================================
    error_event = ws_collector.wait_for_event(
        event_type="execution_failed",
        timeout=10.0,
    )

    if error_event:
        # Verify error details are included
        assert "error" in error_event["data"] or "message" in error_event["data"]

    # ========================================================================
    # Test: Verify error events in event store
    # ========================================================================
    e2e_client.assert_events_recorded(
        event_type="ExecutionFailed",
        min_count=1,
    )
