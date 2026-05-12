"""
Test suite for audit trail causal chain and query filters

Tests for:
- GET /api/v2/audit/events/{event_id}/causal-chain endpoint
- GET /api/v2/audit/events?since=<timestamp> filter
- GET /api/v2/audit/events?workItemId=<id> filter
- AuditEventFilters dataclass with new work_item_id field
- Causal chain traversal through domain events
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from codetoreum.domain.events import (
    WorkflowCompletedEvent,
    WorkflowStartedEvent,
    WorkItemColumnChangedEvent,
    now_iso,
)
from codetoreum.infrastructure.simulation.bootstrap import SimulationApplicationBootstrap
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig
from codetoreum.ports.input.audit_query import AuditEventFilters

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def bootstrap():
    """Create and setup simulation bootstrap."""
    config = SimulationConfig.create_fast_config("test_audit_causal_chain")
    bootstrap = SimulationApplicationBootstrap(config)
    await bootstrap.setup()
    yield bootstrap
    await bootstrap.teardown()


@pytest.fixture
async def client(bootstrap):
    """Create a test client."""
    return TestClient(bootstrap.app)


async def _create_test_causal_chain(event_store):
    """
    Create a chain of domain events with causation links for testing.

    Returns the event IDs: (root_event_id, middle_event_id, leaf_event_id, base_time)
    """
    base_time = datetime(2026, 3, 20, 10, 0, 0, tzinfo=UTC)

    # Root event: WorkItemColumnChanged (no causation)
    correlation_id = str(uuid4())
    root_event = WorkItemColumnChangedEvent(
        type="workitem.column_changed",
        timestamp=base_time.isoformat(),
        source="test",
        correlation_id=correlation_id,
        work_item_id="WI-001",
        project_id="test-project",
        board_id="test-board",
        from_column="TODO",
        to_column="IN_PROGRESS",
        moved_by="system",
    )
    await event_store.append("WI-001", [root_event])
    root_event_id = root_event.event_id

    # Middle event: WorkflowStarted (caused by root)
    middle_event = WorkflowStartedEvent(
        type="workflow.started",
        timestamp=(base_time + timedelta(seconds=10)).isoformat(),
        source="test",
        correlation_id=correlation_id,
        workflow_id="WF-001",
        work_item_id="WI-001",
    )
    await event_store.append("WF-001", [middle_event])
    middle_event_id = middle_event.event_id

    # Leaf event: WorkflowCompleted (caused by middle)
    leaf_event = WorkflowCompletedEvent(
        type="workflow.completed",
        timestamp=(base_time + timedelta(seconds=30)).isoformat(),
        source="test",
        correlation_id=correlation_id,
        workflow_id="WF-001",
        work_item_id="WI-001",
        completion_status="success",
    )
    await event_store.append("WF-001", [leaf_event])
    leaf_event_id = leaf_event.event_id

    return root_event_id, middle_event_id, leaf_event_id, base_time


# ============================================================================
# Tests for Causal Chain Endpoint
# ============================================================================


@pytest.mark.asyncio
async def test_causal_chain_full_chain(bootstrap, client):
    """Test GET /api/v2/audit/events/{event_id}/causal-chain returns full chain."""
    event_store = bootstrap.adapters.event_store
    root_id, middle_id, leaf_id, base_time = await _create_test_causal_chain(event_store)

    # Query causal chain for the leaf event
    response = client.get(f"/api/v2/audit/events/{leaf_id}/causal-chain")

    assert response.status_code == 200
    data = response.json()

    # Should have 3 events in the chain (leaf, middle, root)
    assert data["hopCount"] == 3
    assert len(data["chain"]) == 3
    assert data["truncated"] is False

    # Verify order: leaf -> middle -> root
    assert data["chain"][0]["eventId"] == str(leaf_id)
    assert data["chain"][1]["eventId"] == str(middle_id)
    assert data["chain"][2]["eventId"] == str(root_id)

    # Root event should have no causation
    assert data["chain"][2]["causationId"] is None

    # Verify root event ID
    assert data["rootEventId"] == str(root_id)


@pytest.mark.asyncio
async def test_causal_chain_middle_event(bootstrap, client):
    """Test causal chain for middle event returns partial chain."""
    event_store = bootstrap.adapters.event_store
    root_id, middle_id, leaf_id, base_time = await _create_test_causal_chain(event_store)

    # Query causal chain for the middle event
    response = client.get(f"/api/v2/audit/events/{middle_id}/causal-chain")

    assert response.status_code == 200
    data = response.json()

    # Should have 2 events (middle and root)
    assert data["hopCount"] == 2
    assert len(data["chain"]) == 2

    assert data["chain"][0]["eventId"] == str(middle_id)
    assert data["chain"][1]["eventId"] == str(root_id)


@pytest.mark.asyncio
async def test_causal_chain_root_event(bootstrap, client):
    """Test causal chain for root event returns single event."""
    event_store = bootstrap.adapters.event_store
    root_id, middle_id, leaf_id, base_time = await _create_test_causal_chain(event_store)

    # Query causal chain for the root event
    response = client.get(f"/api/v2/audit/events/{root_id}/causal-chain")

    assert response.status_code == 200
    data = response.json()

    # Should have 1 event (root)
    assert data["hopCount"] == 1
    assert len(data["chain"]) == 1
    assert data["chain"][0]["eventId"] == str(root_id)
    assert data["chain"][0]["causationId"] is None


@pytest.mark.asyncio
async def test_causal_chain_nonexistent_event(bootstrap, client):
    """Test causal chain endpoint returns 404 for non-existent event."""
    response = client.get(f"/api/v2/audit/events/{uuid4()}/causal-chain")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_causal_chain_payload_summary(bootstrap, client):
    """Test that causal chain includes payload summary."""
    event_store = bootstrap.adapters.event_store
    root_id, middle_id, leaf_id, base_time = await _create_test_causal_chain(event_store)

    response = client.get(f"/api/v2/audit/events/{leaf_id}/causal-chain")

    assert response.status_code == 200
    data = response.json()

    # All events should have payload summary (can be empty dict if no matching key fields)
    for event in data["chain"]:
        assert "payloadSummary" in event
        assert isinstance(event["payloadSummary"], dict)
        # Leaf and middle events should have work_item_id in payload summary
        if event["eventId"] in (str(leaf_id), str(middle_id)):
            assert "work_item_id" in event["payloadSummary"]


@pytest.mark.asyncio
async def test_causal_chain_truncation(bootstrap, client):
    """Test causal chain truncation at 100 hops limit."""
    event_store = bootstrap.adapters.event_store
    base_time = datetime(2026, 3, 20, 10, 0, 0, tzinfo=UTC)

    # Create a long chain of events (>100)
    first_event_id = None
    prev_causation_id = None

    for i in range(105):
        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=(base_time + timedelta(seconds=i)).isoformat(),
            source="test",
            work_item_id=f"WI-{i}",
            project_id="test-project",
            board_id="test-board",
            from_column=f"stage-{i-1}" if i > 0 else None,
            to_column=f"stage-{i}",
            moved_by="system",
            correlation_id=str(uuid4()),
        )
        await event_store.append(f"WI-{i}", [event])

        if i == 0:
            first_event_id = event.event_id
        prev_causation_id = event.event_id

    # Query the leaf event
    response = client.get(f"/api/v2/audit/events/{prev_causation_id}/causal-chain")

    assert response.status_code == 200
    data = response.json()

    # Should be truncated at 100 hops
    assert data["truncated"] is True
    assert data["hopCount"] == 100


# ============================================================================
# Tests for AuditEventFilters with new work_item_id field
# ============================================================================


def test_audit_event_filters_frozen():
    """Test that AuditEventFilters dataclass is frozen."""
    filters = AuditEventFilters(
        work_item_id="WI-001",
        start_time=datetime.now(UTC),
    )

    # Attempt to modify should raise AttributeError
    with pytest.raises((AttributeError, Exception)):
        filters.work_item_id = "WI-002"

    with pytest.raises((AttributeError, Exception)):
        filters.start_time = datetime.now(UTC)


def test_audit_event_filters_with_all_fields():
    """Test that AuditEventFilters can be created with all fields."""
    now = datetime.now(UTC)
    filters = AuditEventFilters(
        event_type="test_event",
        resource_type="test_resource",
        resource_id="test-123",
        user_id="user-123",
        action="update",
        success=True,
        start_time=now,
        end_time=now + timedelta(hours=1),
        work_item_id="WI-001",  # New field
    )

    # Verify all fields are set
    assert filters.event_type == "test_event"
    assert filters.work_item_id == "WI-001"
    assert filters.start_time == now


def test_audit_event_filters_defaults():
    """Test that AuditEventFilters has proper defaults."""
    filters = AuditEventFilters()

    # All fields should default to None
    assert filters.event_type is None
    assert filters.work_item_id is None
    assert filters.start_time is None
    assert filters.end_time is None


def test_audit_event_filters_work_item_id_field():
    """Test that work_item_id field exists and works correctly."""
    filters = AuditEventFilters(work_item_id="WI-001")

    assert filters.work_item_id == "WI-001"
    assert filters.event_type is None  # Other fields should be None


def test_audit_event_filters_with_dataclasses_replace():
    """Test that filters can be modified using dataclasses.replace."""
    import dataclasses

    original = AuditEventFilters(work_item_id="WI-001", event_type="test")
    modified = dataclasses.replace(original, work_item_id="WI-002")

    assert original.work_item_id == "WI-001"
    assert modified.work_item_id == "WI-002"
    assert modified.event_type == "test"


# ============================================================================
# Tests for Causal Chain Response Structure
# ============================================================================


@pytest.mark.asyncio
async def test_causal_chain_response_structure(bootstrap, client):
    """Test that causal chain response has correct structure."""
    event_store = bootstrap.adapters.event_store
    root_id, middle_id, leaf_id, base_time = await _create_test_causal_chain(event_store)

    response = client.get(f"/api/v2/audit/events/{leaf_id}/causal-chain")

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "rootEventId" in data
    assert "chain" in data
    assert "truncated" in data
    assert "hopCount" in data

    # Verify chain event structure
    for event in data["chain"]:
        assert "eventId" in event
        assert "eventType" in event
        assert "occurredAt" in event
        assert "causationId" in event
        assert "payloadSummary" in event


@pytest.mark.asyncio
async def test_causal_chain_chain_ordering(bootstrap, client):
    """Test that causal chain is ordered from queried event to root."""
    event_store = bootstrap.adapters.event_store
    root_id, middle_id, leaf_id, base_time = await _create_test_causal_chain(event_store)

    response = client.get(f"/api/v2/audit/events/{leaf_id}/causal-chain")

    assert response.status_code == 200
    data = response.json()
    chain = data["chain"]

    # Verify temporal ordering: each event's timestamp should be >= previous event's
    for i in range(len(chain) - 1):
        current_time = datetime.fromisoformat(chain[i]["occurredAt"].replace("Z", "+00:00"))
        next_time = datetime.fromisoformat(chain[i + 1]["occurredAt"].replace("Z", "+00:00"))
        assert current_time >= next_time  # Going backward in time from leaf to root


@pytest.mark.asyncio
async def test_causal_chain_causation_links(bootstrap, client):
    """Test that causal chain maintains correct causation links."""
    event_store = bootstrap.adapters.event_store
    root_id, middle_id, leaf_id, base_time = await _create_test_causal_chain(event_store)

    response = client.get(f"/api/v2/audit/events/{leaf_id}/causal-chain")

    assert response.status_code == 200
    data = response.json()
    chain = data["chain"]

    # Verify causation links
    # chain[0] (leaf) causationId should point to chain[1] (middle)
    assert chain[0]["causationId"] == chain[1]["eventId"]

    # chain[1] (middle) causationId should point to chain[2] (root)
    assert chain[1]["causationId"] == chain[2]["eventId"]

    # chain[2] (root) causationId should be None
    assert chain[2]["causationId"] is None


# ============================================================================
# Tests for Query Filters (since, workItemId)
# ============================================================================


async def _seed_audit_events_for_filters(bootstrap):
    """Seed the audit store with test data for filter tests."""
    audit_store = bootstrap.adapters.audit_store
    base_time = datetime(2026, 3, 20, 10, 0, 0, tzinfo=UTC)

    # Event 1: work item created
    await audit_store.store_event(
        timestamp=base_time,
        event_type="work_item_created",
        resource_type="work_item",
        resource_id="WI-001",
        action="create",
        user_id="system",
        correlation_id="corr-001",
        metadata={"work_item_id": "WI-001", "title": "Test Work Item 1"},
        success=True,
    )

    # Event 2: workflow started for WI-001 (5 seconds later)
    await audit_store.store_event(
        timestamp=base_time + timedelta(seconds=5),
        event_type="workflow_started",
        resource_type="workflow",
        resource_id="WF-001",
        action="start",
        user_id="system",
        correlation_id="corr-002",
        metadata={"work_item_id": "WI-001", "workflow_id": "WF-001"},
        success=True,
    )

    # Event 3: different work item created
    await audit_store.store_event(
        timestamp=base_time + timedelta(seconds=10),
        event_type="work_item_created",
        resource_type="work_item",
        resource_id="WI-002",
        action="create",
        user_id="system",
        correlation_id="corr-003",
        metadata={"work_item_id": "WI-002", "title": "Test Work Item 2"},
        success=True,
    )

    # Event 4: work item updated for WI-002
    await audit_store.store_event(
        timestamp=base_time + timedelta(seconds=15),
        event_type="work_item_updated",
        resource_type="work_item",
        resource_id="WI-002",
        action="update",
        user_id="system",
        correlation_id="corr-004",
        metadata={"work_item_id": "WI-002", "field": "status"},
        success=True,
    )


@pytest.mark.asyncio
async def test_audit_events_since_filter(bootstrap, client):
    """Test GET /api/v2/audit/events?since=<timestamp> filters by start time."""
    # Seed the audit store with test data
    await _seed_audit_events_for_filters(bootstrap)

    # Query without any filters to get baseline
    response = client.get("/api/v2/audit/events")
    assert response.status_code == 200
    events = response.json()["events"]
    initial_count = len(events)
    assert initial_count >= 4, "Should have at least 4 seeded events"

    # Get the timestamp of the first event for testing
    first_event_time = datetime.fromisoformat(events[-1]["timestamp"].replace("Z", "+00:00"))

    # Query for events since a future time (should have no events)
    future_time = datetime.now(UTC) + timedelta(hours=1)
    future_iso = future_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    response = client.get(f"/api/v2/audit/events?since={future_iso}")
    assert response.status_code == 200
    future_events = response.json()["events"]

    # Should have no events in the future
    assert len(future_events) == 0

    # Query for events since the middle of our test period (should exclude oldest event)
    since_time = first_event_time + timedelta(seconds=3)
    since_iso = since_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    response = client.get(f"/api/v2/audit/events?since={since_iso}")
    assert response.status_code == 200
    since_events = response.json()["events"]

    # Should have fewer events than baseline (excluding the first event)
    assert len(since_events) < initial_count, f"Expected fewer than {initial_count}, got {len(since_events)}"

    # Query for events since a past time (should include all events)
    past_time = datetime(2020, 1, 1, tzinfo=UTC)
    past_iso = past_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    response = client.get(f"/api/v2/audit/events?since={past_iso}")
    assert response.status_code == 200
    past_events = response.json()["events"]

    # Should have all of the initial events
    assert len(past_events) >= initial_count


@pytest.mark.asyncio
async def test_audit_events_work_item_id_filter(bootstrap, client):
    """Test GET /api/v2/audit/events?workItemId=<id> filters by work item."""
    # Seed the audit store with test data
    await _seed_audit_events_for_filters(bootstrap)

    # Query for WI-001 (should return 2 events: work_item_created + workflow_started)
    response = client.get("/api/v2/audit/events?workItemId=WI-001")
    assert response.status_code == 200
    events_wi001 = response.json()["events"]

    # Should have events related to WI-001
    assert len(events_wi001) > 0, "Should have at least one event for WI-001"

    # All returned events should be associated with WI-001
    for event in events_wi001:
        # Check if work item ID appears in resource_id, metadata, or correlation_id
        assert (
            event["resourceId"] == "WI-001"
            or "WI-001" in str(event.get("metadata", {}))
            or "WI-001" in str(event.get("correlationId", ""))
        ), f"Event {event['id']} should be related to WI-001"

    # Query for WI-002 (should return 2 events)
    response = client.get("/api/v2/audit/events?workItemId=WI-002")
    assert response.status_code == 200
    events_wi002 = response.json()["events"]

    assert len(events_wi002) > 0, "Should have at least one event for WI-002"

    # All returned events should be associated with WI-002
    for event in events_wi002:
        assert (
            event["resourceId"] == "WI-002"
            or "WI-002" in str(event.get("metadata", {}))
            or "WI-002" in str(event.get("correlationId", ""))
        ), f"Event {event['id']} should be related to WI-002"

    # The two result sets should be different
    assert events_wi001 != events_wi002, "Events for different work items should be different"


@pytest.mark.asyncio
async def test_audit_events_since_and_start_time_conflict(bootstrap, client):
    """Test that providing both since and startTime parameters returns 400."""
    past_time = datetime(2020, 1, 1, tzinfo=UTC)
    iso_time = past_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Try to provide both since and startTime
    response = client.get(f"/api/v2/audit/events?since={iso_time}&startTime={iso_time}")

    # Should return 400 Bad Request
    assert response.status_code == 400
    assert "both" in response.json()["detail"].lower()
