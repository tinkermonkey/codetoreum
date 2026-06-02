"""Integration tests for trigger lifecycle endpoint."""

from datetime import UTC, datetime

import pytest

from codetoreum.infrastructure.simulation.bootstrap import SimulationApplicationBootstrap
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig


@pytest.fixture
async def test_app():
    """Create a test FastAPI app using simulation bootstrap."""
    config = SimulationConfig.create_fast_config("test_trigger_lifecycle")
    bootstrap = SimulationApplicationBootstrap(config)
    await bootstrap.setup()
    yield bootstrap
    await bootstrap.teardown()


@pytest.mark.asyncio
async def test_trigger_lifecycle_not_found(test_app):
    """Test that non-existent event returns 404."""
    from fastapi.testclient import TestClient

    client = TestClient(test_app.app)

    response = client.get("/api/v2/triggers/nonexistent-event-id")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_trigger_lifecycle_response_structure_on_not_found(test_app):
    """Test trigger lifecycle endpoint error handling."""
    from fastapi.testclient import TestClient

    client = TestClient(test_app.app)

    # Request for a non-existent event
    response = client.get("/api/v2/triggers/test-event-456")

    # Should get 404 for non-existent events
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_trigger_lifecycle_enum_statuses(test_app):
    """Test that trigger lifecycle endpoint uses proper status enum values."""
    from fastapi.testclient import TestClient

    from codetoreum.adapters.primary.routers.diagnostics import TriggerStatus

    client = TestClient(test_app.app)

    # Verify enum values are correct (these will be used in responses)
    assert TriggerStatus.RECEIVED.value == "received"
    assert TriggerStatus.QUEUED.value == "queued"
    assert TriggerStatus.IN_PROGRESS.value == "in-progress"
    assert TriggerStatus.COMPLETED.value == "completed"
    assert TriggerStatus.FAILED.value == "failed"

    # Verify enum members exist
    assert hasattr(TriggerStatus, "RECEIVED")
    assert hasattr(TriggerStatus, "QUEUED")
    assert hasattr(TriggerStatus, "IN_PROGRESS")
    assert hasattr(TriggerStatus, "COMPLETED")
    assert hasattr(TriggerStatus, "FAILED")
