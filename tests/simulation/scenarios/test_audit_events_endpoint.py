"""
Test suite for GET /api/v2/audit/events endpoint

Tests the audit events API endpoint for querying system-wide audit logs.
"""

import pytest
from datetime import UTC, datetime
from fastapi.testclient import TestClient

from codetoreum.infrastructure.simulation.bootstrap import SimulationApplicationBootstrap
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def bootstrap():
    """Create and setup simulation bootstrap."""
    config = SimulationConfig.create_fast_config("test_audit_events")
    bootstrap = SimulationApplicationBootstrap(config)
    await bootstrap.setup()
    yield bootstrap
    await bootstrap.teardown()


async def _seed_audit_events(bootstrap):
    """Seed the audit store with test data."""
    audit_store = bootstrap.adapters.audit_store

    # Create test events with various combinations
    base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

    # Event 1: agent_created (successful)
    await audit_store.store_event(
        timestamp=base_time,
        event_type="agent_created",
        resource_type="agent",
        resource_id="agent-001",
        action="create",
        user_id="system",
        correlation_id="corr-001",
        metadata={"name": "TestAgent"},
        success=True,
    )

    # Event 2: agent_updated (successful)
    await audit_store.store_event(
        timestamp=base_time.replace(minute=1),
        event_type="agent_updated",
        resource_type="agent",
        resource_id="agent-001",
        action="update",
        user_id="system",
        correlation_id="corr-002",
        metadata={"field": "description"},
        success=True,
    )

    # Event 3: workflow_created (successful)
    await audit_store.store_event(
        timestamp=base_time.replace(minute=2),
        event_type="workflow_created",
        resource_type="workflow",
        resource_id="workflow-001",
        action="create",
        user_id="system",
        correlation_id="corr-003",
        metadata={"name": "TestWorkflow"},
        success=True,
    )

    # Event 4: agent_deleted (failed)
    await audit_store.store_event(
        timestamp=base_time.replace(minute=3),
        event_type="agent_deleted",
        resource_type="agent",
        resource_id="agent-002",
        action="delete",
        user_id="user123",
        correlation_id="corr-004",
        metadata={},
        success=False,
        error_message="Agent in use",
    )


# ============================================================================
# Tests
# ============================================================================


@pytest.mark.asyncio
async def test_audit_events_endpoint_basic(bootstrap):
    """Test basic audit events endpoint functionality."""
    client = TestClient(bootstrap.app)

    # Query audit events
    response = client.get("/api/v2/audit/events")

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "events" in data
    assert "totalEventCount" in data
    assert "offset" in data
    assert "limit" in data
    assert "hasNext" in data

    # Verify pagination defaults
    assert data["offset"] == 0
    assert data["limit"] == 20
    assert isinstance(data["events"], list)
    assert isinstance(data["totalEventCount"], int)
    assert isinstance(data["hasNext"], bool)


@pytest.mark.asyncio
async def test_audit_events_endpoint_pagination(bootstrap):
    """Test audit events endpoint pagination."""
    client = TestClient(bootstrap.app)

    # Query with custom pagination
    response = client.get("/api/v2/audit/events?offset=10&limit=50")

    assert response.status_code == 200
    data = response.json()

    # Verify pagination parameters were applied
    assert data["offset"] == 10
    assert data["limit"] == 50


@pytest.mark.asyncio
async def test_audit_events_endpoint_max_limit(bootstrap):
    """Test audit events endpoint rejects exceeding max limit."""
    client = TestClient(bootstrap.app)

    # Try to exceed max limit (200)
    response = client.get("/api/v2/audit/events?limit=999")

    # Should reject with validation error
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_audit_events_endpoint_filtering(bootstrap):
    """Test audit events endpoint filtering."""
    # Seed test data
    await _seed_audit_events(bootstrap)
    client = TestClient(bootstrap.app)

    # Query with filters
    response = client.get("/api/v2/audit/events?eventType=agent_created&resourceType=agent&action=create")

    assert response.status_code == 200
    data = response.json()

    # Should return at least one matching event
    assert len(data["events"]) > 0

    # All returned events should match the filters
    for event in data["events"]:
        assert event["eventType"] == "agent_created"
        assert event["resourceType"] == "agent"
        assert event["action"] == "create"


@pytest.mark.asyncio
async def test_audit_events_endpoint_response_format(bootstrap):
    """Test audit events endpoint response format."""
    # Seed test data
    await _seed_audit_events(bootstrap)
    client = TestClient(bootstrap.app)

    response = client.get("/api/v2/audit/events")

    assert response.status_code == 200
    data = response.json()

    # Should return at least one event
    assert len(data["events"]) > 0

    # Verify event response format
    for event in data["events"]:
        assert "id" in event
        assert "timestamp" in event
        assert "eventType" in event
        assert "resourceType" in event
        assert "resourceId" in event
        assert "action" in event
        assert "userId" in event
        assert "success" in event
        assert "metadata" in event

        # Verify types
        assert isinstance(event["id"], str)
        assert isinstance(event["eventType"], str)
        assert isinstance(event["resourceType"], str)
        assert isinstance(event["resourceId"], str)
        assert isinstance(event["action"], str)
        assert isinstance(event["userId"], str)
        assert isinstance(event["success"], bool)
        assert isinstance(event["metadata"], dict)


@pytest.mark.asyncio
async def test_audit_events_endpoint_success_filter(bootstrap):
    """Test audit events endpoint success status filter."""
    # Seed test data
    await _seed_audit_events(bootstrap)
    client = TestClient(bootstrap.app)

    # Query only successful events
    response = client.get("/api/v2/audit/events?success=true")

    assert response.status_code == 200
    data = response.json()

    # Should return at least one successful event
    assert len(data["events"]) > 0

    # All returned events should have success=true
    for event in data["events"]:
        assert event["success"] is True


@pytest.mark.asyncio
async def test_audit_events_endpoint_user_filter(bootstrap):
    """Test audit events endpoint user ID filter."""
    # Seed test data
    await _seed_audit_events(bootstrap)
    client = TestClient(bootstrap.app)

    # Query by user ID
    response = client.get("/api/v2/audit/events?userId=system")

    assert response.status_code == 200
    data = response.json()

    # Should return at least one event for "system" user
    assert len(data["events"]) > 0

    # All returned events should have matching userId
    for event in data["events"]:
        assert event["userId"] == "system"


@pytest.mark.asyncio
async def test_audit_events_endpoint_has_next(bootstrap):
    """Test audit events endpoint hasNext pagination flag."""
    client = TestClient(bootstrap.app)

    # Query with limit 1
    response = client.get("/api/v2/audit/events?limit=1")

    assert response.status_code == 200
    data = response.json()

    # If there are more than 1 events, hasNext should be True
    if data["totalEventCount"] > 1:
        assert data["hasNext"] is True
    else:
        assert data["hasNext"] is False


@pytest.mark.asyncio
async def test_audit_events_endpoint_offset_bounds(bootstrap):
    """Test audit events endpoint offset boundary handling."""
    client = TestClient(bootstrap.app)

    # Query with large offset
    response = client.get("/api/v2/audit/events?offset=99999&limit=20")

    assert response.status_code == 200
    data = response.json()

    # Should return empty list but valid response
    assert isinstance(data["events"], list)
    assert data["hasNext"] is False


@pytest.mark.asyncio
async def test_audit_events_endpoint_invalid_offset(bootstrap):
    """Test audit events endpoint rejects negative offset."""
    client = TestClient(bootstrap.app)

    # Query with negative offset
    response = client.get("/api/v2/audit/events?offset=-1")

    # Should return 422 validation error
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_audit_events_endpoint_invalid_limit(bootstrap):
    """Test audit events endpoint rejects invalid limit."""
    client = TestClient(bootstrap.app)

    # Query with zero limit
    response = client.get("/api/v2/audit/events?limit=0")

    # Should return 422 validation error
    assert response.status_code == 422
