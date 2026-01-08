"""Contract tests for IMonitoredService interface.

These abstract tests verify that all IMonitoredService implementations
follow the monitoring lifecycle contract correctly.
"""

from abc import ABC, abstractmethod

import pytest

from codetoreum.ports.output.monitoring import (
    IMonitoredService,
    MonitoringConfig,
    MonitoringState,
)


class TestMonitoredServiceContract(ABC):
    """Abstract contract tests for IMonitoredService implementations.

    Subclasses must implement create_service() to provide a concrete
    IMonitoredService implementation to test.
    """

    @abstractmethod
    async def create_service(self) -> IMonitoredService:
        """Create and return an IMonitoredService instance for testing."""
        pass

    @pytest.mark.asyncio
    async def test_start_monitoring_changes_state_to_active(self):
        """Starting monitoring should transition to ACTIVE state."""
        service = await self.create_service()
        config = MonitoringConfig(project_id="proj-123")

        await service.start_monitoring("proj-123", config)
        status = await service.get_monitoring_status("proj-123")

        assert status.state == MonitoringState.ACTIVE
        assert status.project_id == "proj-123"
        assert status.started_at is not None

    @pytest.mark.asyncio
    async def test_stop_monitoring_changes_state_to_stopped(self):
        """Stopping monitoring should transition to STOPPED state."""
        service = await self.create_service()
        config = MonitoringConfig(project_id="proj-123")

        await service.start_monitoring("proj-123", config)
        await service.stop_monitoring("proj-123")
        status = await service.get_monitoring_status("proj-123")

        assert status.state == MonitoringState.STOPPED
        assert status.started_at is None

    @pytest.mark.asyncio
    async def test_get_monitoring_status_when_not_started(self):
        """Querying status before start should show STOPPED state."""
        service = await self.create_service()

        status = await service.get_monitoring_status("proj-123")

        assert status.state == MonitoringState.STOPPED
        assert status.project_id == "proj-123"

    @pytest.mark.asyncio
    async def test_stop_monitoring_not_started_raises_error(self):
        """Stopping monitoring that wasn't started should raise error."""
        service = await self.create_service()

        with pytest.raises(Exception):  # ResourceNotFoundError
            await service.stop_monitoring("proj-123")

    @pytest.mark.asyncio
    async def test_monitoring_respects_config_settings(self):
        """Monitoring should respect configuration parameters."""
        service = await self.create_service()
        config = MonitoringConfig(
            project_id="proj-123",
            poll_interval_seconds=30,
            webhook_enabled=False,
        )

        await service.start_monitoring("proj-123", config)
        status = await service.get_monitoring_status("proj-123")

        assert status.state == MonitoringState.ACTIVE

    @pytest.mark.asyncio
    async def test_multiple_projects_independent(self):
        """Monitoring state should be independent per project."""
        service = await self.create_service()
        config1 = MonitoringConfig(project_id="proj-1")
        config2 = MonitoringConfig(project_id="proj-2")

        await service.start_monitoring("proj-1", config1)
        status2 = await service.get_monitoring_status("proj-2")

        # proj-1 should be ACTIVE
        status1 = await service.get_monitoring_status("proj-1")
        assert status1.state == MonitoringState.ACTIVE

        # proj-2 should still be STOPPED
        assert status2.state == MonitoringState.STOPPED

    @pytest.mark.asyncio
    async def test_restart_monitoring_allowed(self):
        """Should be able to restart monitoring after stop."""
        service = await self.create_service()
        config = MonitoringConfig(project_id="proj-123")

        await service.start_monitoring("proj-123", config)
        await service.stop_monitoring("proj-123")

        # Should be able to start again
        await service.start_monitoring("proj-123", config)
        status = await service.get_monitoring_status("proj-123")

        assert status.state == MonitoringState.ACTIVE
