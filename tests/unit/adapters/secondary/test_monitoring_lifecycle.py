"""Unit tests for monitoring lifecycle edge cases.

Tests verify that:
1. Start monitoring twice is idempotent (no error, no duplicate state)
2. Stop when not started returns success (no error)
3. Status when never started returns not active
4. Start-stop-restart sequence works correctly
5. Multiple projects can be monitored simultaneously
"""

import pytest

from codetoreum.adapters.testing.mock_board_adapter import MockBoardAdapter
from codetoreum.ports.output.monitoring import MonitoringConfig, MonitoringState


@pytest.fixture
def mock_monitored_adapter():
    """Create a mock board adapter that supports monitoring."""
    adapter = MockBoardAdapter()
    return adapter


@pytest.mark.asyncio
class TestMonitoringLifecycleEdgeCases:
    """Test suite for monitoring lifecycle edge cases."""

    async def test_start_monitoring_twice_is_idempotent(self, mock_monitored_adapter):
        """Test that starting monitoring twice is idempotent."""
        adapter = mock_monitored_adapter

        config = MonitoringConfig(project_id="proj-1")

        # First start
        await adapter.start_monitoring("proj-1", config)
        status1 = await adapter.get_monitoring_status("proj-1")

        # Second start (should not error or create duplicate state)
        await adapter.start_monitoring("proj-1", config)
        status2 = await adapter.get_monitoring_status("proj-1")

        # Status should be unchanged
        assert status1.state == status2.state
        assert status1.project_id == status2.project_id

    async def test_stop_monitoring_when_not_started_succeeds(self, mock_monitored_adapter):
        """Test that stopping when not started returns success."""
        adapter = mock_monitored_adapter

        # Stop without starting (should not error)
        await adapter.stop_monitoring("proj-1")

        # Should be in stopped state
        status = await adapter.get_monitoring_status("proj-1")
        assert status.state in (MonitoringState.STOPPED, MonitoringState.STOPPING)

    async def test_status_when_never_started_returns_not_active(self, mock_monitored_adapter):
        """Test that status when never started returns not active."""
        adapter = mock_monitored_adapter

        # Get status without starting
        status = await adapter.get_monitoring_status("proj-99")

        # Should indicate not active
        assert status.state != MonitoringState.ACTIVE
        assert status.started_at is None

    async def test_start_stop_restart_sequence_works(self, mock_monitored_adapter):
        """Test that start-stop-restart sequence works correctly."""
        adapter = mock_monitored_adapter

        config = MonitoringConfig(project_id="proj-1")

        # Start
        await adapter.start_monitoring("proj-1", config)
        status1 = await adapter.get_monitoring_status("proj-1")
        assert status1.state == MonitoringState.ACTIVE

        # Stop
        await adapter.stop_monitoring("proj-1")
        status2 = await adapter.get_monitoring_status("proj-1")
        assert status2.state in (MonitoringState.STOPPED, MonitoringState.STOPPING)

        # Restart
        await adapter.start_monitoring("proj-1", config)
        status3 = await adapter.get_monitoring_status("proj-1")
        assert status3.state == MonitoringState.ACTIVE

    async def test_monitor_multiple_projects_simultaneously(self, mock_monitored_adapter):
        """Test that multiple projects can be monitored simultaneously."""
        adapter = mock_monitored_adapter

        configs = [
            MonitoringConfig(project_id="proj-1"),
            MonitoringConfig(project_id="proj-2"),
            MonitoringConfig(project_id="proj-3"),
        ]

        # Start monitoring multiple projects
        for config in configs:
            await adapter.start_monitoring(config.project_id, config)

        # Verify all are active
        status1 = await adapter.get_monitoring_status("proj-1")
        status2 = await adapter.get_monitoring_status("proj-2")
        status3 = await adapter.get_monitoring_status("proj-3")

        assert status1.state == MonitoringState.ACTIVE
        assert status2.state == MonitoringState.ACTIVE
        assert status3.state == MonitoringState.ACTIVE

        # Stop one project
        await adapter.stop_monitoring("proj-2")

        # Verify others still active
        status1 = await adapter.get_monitoring_status("proj-1")
        status2 = await adapter.get_monitoring_status("proj-2")
        status3 = await adapter.get_monitoring_status("proj-3")

        assert status1.state == MonitoringState.ACTIVE
        assert status2.state in (MonitoringState.STOPPED, MonitoringState.STOPPING)
        assert status3.state == MonitoringState.ACTIVE
