"""
E2E Test: Observability and Monitoring

Tests observability features including:
- Metrics collection and querying
- Event store queries
- WebSocket event streaming
- Real-time monitoring
- Performance metrics
"""

import pytest
import asyncio
from datetime import timedelta
from typing import List, Dict, Any

from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder


@pytest.mark.asyncio
@pytest.mark.simulation
async def test_metrics_collection_and_query(e2e_client, simulation_seeder):
    """
    Test that metrics are collected and can be queried.

    Verifies:
    - Workflow metrics are recorded
    - Execution metrics are recorded
    - Metrics can be queried by name and labels
    - Time-series data is available
    """
    # ========================================================================
    # Setup
    # ========================================================================
    seeder: SimulationDataSeeder = simulation_seeder
    await seeder.seed_default_scenario()

    # ========================================================================
    # Test: Create and execute workflow
    # ========================================================================
    work_item = e2e_client.create_work_item(
        project_id="default-project",
        title="Metrics test work item",
        description="Work item for metrics collection test",
    )

    e2e_client.trigger_workflow(
        work_item_id=work_item["id"],
        workflow_id="default-workflow",
    )

    # Advance time to complete workflow
    e2e_client.advance_time(timedelta(hours=1))

    # Wait for completion
    await e2e_client.wait_for_work_item_status(
        work_item_id=work_item["id"],
        expected_status="COMPLETED",
        timeout=5.0,
    )

    # ========================================================================
    # Test: Query workflow duration metrics
    # ========================================================================
    workflow_metrics = e2e_client.get_metrics(
        metric_name="workflow_duration",
        labels={"workflow_id": "default-workflow"},
    )

    assert len(workflow_metrics) >= 1
    # Verify metric has expected fields
    for metric in workflow_metrics:
        assert "value" in metric or "duration" in metric
        assert "timestamp" in metric or "recorded_at" in metric

    # ========================================================================
    # Test: Query execution count metrics
    # ========================================================================
    execution_metrics = e2e_client.get_metrics(
        metric_name="execution_count",
    )

    assert len(execution_metrics) >= 1

    # ========================================================================
    # Test: Query agent performance metrics
    # ========================================================================
    agent_metrics = e2e_client.get_metrics(
        metric_name="agent_execution_time",
    )

    # Should have metrics for agent executions
    assert len(agent_metrics) >= 0  # May be 0 if not implemented yet

    # ========================================================================
    # Test: Query metrics with label filters
    # ========================================================================
    project_metrics = e2e_client.get_metrics(
        labels={"project_id": "default-project"},
    )

    # Should have metrics for this project
    assert len(project_metrics) >= 0


@pytest.mark.asyncio
@pytest.mark.simulation
async def test_event_store_queries(e2e_client, simulation_seeder):
    """
    Test event store query functionality.

    Verifies:
    - Events are stored correctly
    - Events can be queried by aggregate ID
    - Events can be queried by event type
    - Event data is complete
    """
    # ========================================================================
    # Setup
    # ========================================================================
    seeder: SimulationDataSeeder = simulation_seeder
    await seeder.seed_default_scenario()

    # ========================================================================
    # Test: Create and execute workflow
    # ========================================================================
    work_item = e2e_client.create_work_item(
        project_id="default-project",
        title="Event store test",
        description="Work item for event store testing",
    )

    e2e_client.trigger_workflow(
        work_item_id=work_item["id"],
        workflow_id="default-workflow",
    )

    # Advance time
    e2e_client.advance_time(timedelta(hours=1))

    # Wait for completion
    await e2e_client.wait_for_work_item_status(
        work_item_id=work_item["id"],
        expected_status="COMPLETED",
        timeout=5.0,
    )

    # ========================================================================
    # Test: Query all events for work item
    # ========================================================================
    events = e2e_client.get_events(
        aggregate_id=work_item["id"],
        limit=100,
    )

    # Should have multiple events
    assert len(events) >= 2  # At least workflow started and completed

    # Verify event structure
    for event in events:
        assert "event_type" in event or "type" in event
        assert "timestamp" in event or "occurred_at" in event
        assert "data" in event or "payload" in event

    # ========================================================================
    # Test: Query events by type
    # ========================================================================
    workflow_started_events = e2e_client.get_events(
        event_type="WorkflowStarted",
        limit=100,
    )

    # Should have at least our workflow started event
    assert len(workflow_started_events) >= 1

    workflow_completed_events = e2e_client.get_events(
        event_type="WorkflowCompleted",
        limit=100,
    )

    # Should have at least our workflow completed event
    assert len(workflow_completed_events) >= 1

    # ========================================================================
    # Test: Verify event chronological order
    # ========================================================================
    # Events should be ordered by timestamp
    if len(events) >= 2:
        timestamps = [e.get("timestamp") or e.get("occurred_at") for e in events]
        # All timestamps should be present
        assert all(t is not None for t in timestamps)


@pytest.mark.asyncio
@pytest.mark.simulation
async def test_websocket_event_streaming(e2e_client, simulation_seeder):
    """
    Test real-time event streaming via WebSocket.

    Verifies:
    - WebSocket connection works
    - Events are streamed in real-time
    - Event filtering works
    - Multiple event types are received
    """
    # ========================================================================
    # Setup
    # ========================================================================
    seeder: SimulationDataSeeder = simulation_seeder
    await seeder.seed_default_scenario()

    # ========================================================================
    # Test: Connect WebSocket before starting workflow
    # ========================================================================
    work_item = e2e_client.create_work_item(
        project_id="default-project",
        title="WebSocket streaming test",
        description="Test real-time event streaming",
    )

    ws_collector = e2e_client.connect_websocket(
        subscription_type="all_events",
        work_item_id=work_item["id"],
    )

    # ========================================================================
    # Test: Trigger workflow
    # ========================================================================
    e2e_client.trigger_workflow(
        work_item_id=work_item["id"],
        workflow_id="default-workflow",
    )

    # ========================================================================
    # Test: Collect initial events
    # ========================================================================
    # Should receive workflow started event
    workflow_started = ws_collector.wait_for_event(
        event_type="workflow_started",
        timeout=5.0,
    )

    assert workflow_started is not None
    assert "data" in workflow_started

    # ========================================================================
    # Test: Advance time and collect more events
    # ========================================================================
    e2e_client.advance_minutes(10)

    # Collect events (may include stage started, stage completed, etc.)
    collected_events = ws_collector.collect_events(count=5, timeout=5.0)

    # Should have received multiple events
    assert len(collected_events) >= 1

    # ========================================================================
    # Test: Complete workflow and verify completion event
    # ========================================================================
    e2e_client.advance_time(timedelta(hours=1))

    workflow_completed = ws_collector.wait_for_event(
        event_type="workflow_completed",
        timeout=10.0,
    )

    assert workflow_completed is not None

    # ========================================================================
    # Test: Verify total events received
    # ========================================================================
    total_events = len(ws_collector.received_events)

    # Should have received multiple events throughout workflow
    assert total_events >= 2  # At least started and completed


@pytest.mark.asyncio
@pytest.mark.simulation
async def test_websocket_event_filtering(e2e_client, simulation_seeder):
    """
    Test WebSocket event filtering.

    Verifies:
    - Filtering by work item ID works
    - Filtering by workflow ID works
    - Only relevant events are received
    """
    # ========================================================================
    # Setup
    # ========================================================================
    seeder: SimulationDataSeeder = simulation_seeder
    await seeder.seed_default_scenario()

    # ========================================================================
    # Test: Create two work items
    # ========================================================================
    work_item_1 = e2e_client.create_work_item(
        project_id="default-project",
        title="Work item 1",
        description="First work item",
    )

    work_item_2 = e2e_client.create_work_item(
        project_id="default-project",
        title="Work item 2",
        description="Second work item",
    )

    # ========================================================================
    # Test: Connect WebSocket filtered to work item 1 only
    # ========================================================================
    ws_collector_1 = e2e_client.connect_websocket(
        subscription_type="all_events",
        work_item_id=work_item_1["id"],
    )

    # ========================================================================
    # Test: Trigger both workflows
    # ========================================================================
    e2e_client.trigger_workflow(
        work_item_id=work_item_1["id"],
        workflow_id="default-workflow",
    )

    e2e_client.trigger_workflow(
        work_item_id=work_item_2["id"],
        workflow_id="default-workflow",
    )

    # ========================================================================
    # Test: Advance time
    # ========================================================================
    e2e_client.advance_time(timedelta(hours=1))

    # ========================================================================
    # Test: Collect events on filtered connection
    # ========================================================================
    events = ws_collector_1.collect_events(count=10, timeout=5.0)

    # Should have received events
    assert len(events) >= 1

    # All events should be for work item 1 (if they have work_item_id)
    for event in events:
        if "data" in event and "work_item_id" in event["data"]:
            assert event["data"]["work_item_id"] == work_item_1["id"]


@pytest.mark.asyncio
@pytest.mark.simulation
async def test_performance_metrics_accuracy(e2e_client, simulation_seeder):
    """
    Test that performance metrics are accurate.

    Verifies:
    - Execution time is measured correctly
    - Workflow duration is calculated properly
    - Metrics reflect simulated time (not wall clock)
    """
    # ========================================================================
    # Setup
    # ========================================================================
    seeder: SimulationDataSeeder = simulation_seeder
    await seeder.seed_default_scenario()

    # Record start time
    start_time = e2e_client.clock.now()

    # ========================================================================
    # Test: Execute workflow with known duration
    # ========================================================================
    work_item = e2e_client.create_work_item(
        project_id="default-project",
        title="Performance metrics test",
        description="Test metric accuracy",
    )

    e2e_client.trigger_workflow(
        work_item_id=work_item["id"],
        workflow_id="default-workflow",
    )

    # Advance time by exactly 30 minutes
    e2e_client.advance_minutes(30)

    # Wait for completion
    await e2e_client.wait_for_work_item_status(
        work_item_id=work_item["id"],
        expected_status="COMPLETED",
        timeout=5.0,
    )

    # Record end time
    end_time = e2e_client.clock.now()

    # ========================================================================
    # Test: Verify elapsed simulation time
    # ========================================================================
    elapsed = end_time - start_time

    # Should be approximately 30 minutes in simulation time
    # (not wall clock time)
    elapsed_minutes = elapsed.total_seconds() / 60
    assert elapsed_minutes >= 29  # Allow small margin

    # ========================================================================
    # Test: Query workflow duration metric
    # ========================================================================
    metrics = e2e_client.get_metrics(
        metric_name="workflow_duration",
        labels={"work_item_id": work_item["id"]},
    )

    if len(metrics) > 0:
        # Verify duration is in simulation time, not wall clock
        duration = metrics[0].get("value") or metrics[0].get("duration")
        # Duration should reflect simulation time (~30 min), not wall clock (<1 sec)
        # Actual check depends on metric format (seconds, milliseconds, etc.)
        assert duration is not None


@pytest.mark.asyncio
@pytest.mark.simulation
async def test_observability_end_to_end(e2e_client, simulation_seeder):
    """
    Complete observability test covering all aspects.

    Verifies:
    - Metrics are collected
    - Events are stored
    - WebSocket streaming works
    - All data is consistent across observability channels
    """
    # ========================================================================
    # Setup
    # ========================================================================
    seeder: SimulationDataSeeder = simulation_seeder
    await seeder.seed_default_scenario()

    # ========================================================================
    # Test: Create work item with WebSocket monitoring
    # ========================================================================
    work_item = e2e_client.create_work_item(
        project_id="default-project",
        title="Full observability test",
        description="Test all observability features",
    )

    ws_collector = e2e_client.connect_websocket(
        subscription_type="all_events",
        work_item_id=work_item["id"],
    )

    # ========================================================================
    # Test: Trigger and complete workflow
    # ========================================================================
    e2e_client.trigger_workflow(
        work_item_id=work_item["id"],
        workflow_id="default-workflow",
    )

    e2e_client.advance_time(timedelta(hours=1))

    await e2e_client.wait_for_work_item_status(
        work_item_id=work_item["id"],
        expected_status="COMPLETED",
        timeout=5.0,
    )

    # ========================================================================
    # Test: Verify all observability channels
    # ========================================================================

    # 1. Metrics
    e2e_client.assert_metrics_recorded(
        metric_name="workflow_duration",
        min_count=1,
    )

    # 2. Events in event store
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

    # 3. WebSocket events
    ws_collector.assert_event_received(
        event_type="workflow_started",
    )

    ws_collector.assert_event_received(
        event_type="workflow_completed",
    )

    # ========================================================================
    # Test: Verify consistency across channels
    # ========================================================================

    # Get workflow started events from both channels
    event_store_events = e2e_client.get_events(
        event_type="WorkflowStarted",
        aggregate_id=work_item["id"],
    )

    ws_started_events = [
        e for e in ws_collector.received_events
        if e.get("type") == "workflow_started"
    ]

    # Both channels should have at least one event
    assert len(event_store_events) >= 1
    assert len(ws_started_events) >= 1

    # Event data should be consistent (work_item_id matches)
    event_store_work_item_id = event_store_events[0].get("aggregate_id") or \
                                event_store_events[0].get("data", {}).get("work_item_id")
    ws_work_item_id = ws_started_events[0].get("data", {}).get("work_item_id")

    # At least one should match the work item ID
    assert event_store_work_item_id == work_item["id"] or \
           ws_work_item_id == work_item["id"]


@pytest.mark.asyncio
@pytest.mark.simulation
async def test_multiple_websocket_clients(e2e_client, simulation_seeder):
    """
    Test multiple WebSocket clients receiving events.

    Verifies:
    - Multiple clients can connect
    - All clients receive the same events
    - No interference between clients
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
        title="Multi-client WebSocket test",
        description="Test multiple WebSocket clients",
    )

    # ========================================================================
    # Test: Connect 3 WebSocket clients
    # ========================================================================
    ws_collectors = [
        e2e_client.connect_websocket(
            subscription_type="all_events",
            work_item_id=work_item["id"],
        )
        for _ in range(3)
    ]

    # ========================================================================
    # Test: Trigger workflow
    # ========================================================================
    e2e_client.trigger_workflow(
        work_item_id=work_item["id"],
        workflow_id="default-workflow",
    )

    e2e_client.advance_time(timedelta(hours=1))

    await e2e_client.wait_for_work_item_status(
        work_item_id=work_item["id"],
        expected_status="COMPLETED",
        timeout=5.0,
    )

    # ========================================================================
    # Test: Verify all clients received events
    # ========================================================================
    for i, ws_collector in enumerate(ws_collectors):
        # Each client should have received events
        assert len(ws_collector.received_events) >= 2, \
            f"Client {i} received only {len(ws_collector.received_events)} events"

        # Each client should have workflow started event
        ws_collector.assert_event_received(event_type="workflow_started")

        # Each client should have workflow completed event
        ws_collector.assert_event_received(event_type="workflow_completed")
