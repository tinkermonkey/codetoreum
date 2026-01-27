"""Unit tests for ContainerRecoveryService application service.

These tests verify:
- Service lifecycle and initialization
- Recovery cycle coordination
- Event emission on recovery actions
- Error handling and recovery
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codetoreum.adapters.testing.mock_container_recovery_adapter import (
    MockContainerRecoveryAdapter,
)
from codetoreum.application.container_recovery_service import (
    ContainerRecoveryService,
)
from codetoreum.domain.events.container_recovery_events import (
    ContainerKilledEvent,
    ContainerRecoveredEvent,
    ContainerRecoveryCompletedEvent,
)
from codetoreum.ports.output.container_recovery import ContainerMetadata


class TestContainerRecoveryServiceInitialization:
    """Tests for service initialization."""

    def test_service_initialization(self):
        """Service should initialize with required dependencies."""
        recovery_adapter = MockContainerRecoveryAdapter()
        event_emitter = MagicMock()

        service = ContainerRecoveryService(
            recovery_adapter=recovery_adapter,
            event_emitter=event_emitter,
            container_timeout_hours=3,
        )

        assert service.recovery_adapter is recovery_adapter
        assert service.event_emitter is event_emitter
        assert service.container_timeout_hours == 3

    def test_service_default_timeout(self):
        """Service should use default timeout of 2 hours."""
        recovery_adapter = MockContainerRecoveryAdapter()
        event_emitter = MagicMock()

        service = ContainerRecoveryService(
            recovery_adapter=recovery_adapter,
            event_emitter=event_emitter,
        )

        assert service.container_timeout_hours == 2


class TestContainerRecoveryServiceWithMock:
    """Integration tests using mock adapter."""

    @pytest.mark.asyncio
    async def test_recover_or_cleanup_containers_empty(self):
        """Service should handle empty container list."""
        mock_adapter = MockContainerRecoveryAdapter()
        event_emitter = MagicMock()

        service = ContainerRecoveryService(
            recovery_adapter=mock_adapter,
            event_emitter=event_emitter,
        )

        result = await service.recover_or_cleanup_containers()

        assert result.recovered == 0
        assert result.killed == 0
        assert result.errors == 0
        assert result.repair_cycles_processed == 0

    @pytest.mark.asyncio
    async def test_recover_or_cleanup_containers_with_recovery(self):
        """Service should emit recovery events when containers are recovered."""
        mock_adapter = MockContainerRecoveryAdapter()
        event_emitter = MagicMock()

        service = ContainerRecoveryService(
            recovery_adapter=mock_adapter,
            event_emitter=event_emitter,
        )

        # Add a container that will be recovered
        container = mock_adapter.add_container(
            container_id="container-123",
            container_name="test-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            work_item_id="work-123",
            execution_id="exec-456",
            age_hours=1.0,  # 1 hour old
        )

        # Set assessment to reconnect
        mock_adapter.set_assessment(
            container_id="container-123",
            action="reconnect",
            reason="valid_execution",
            with_monitoring=True,
            execution_id="exec-456",
        )

        result = await service.recover_or_cleanup_containers()

        assert result.recovered == 1
        assert result.killed == 0
        assert result.errors == 0

        # Verify recovery event was emitted
        calls = event_emitter.emit.call_args_list
        recovery_event = None
        for call in calls:
            event = call[0][0]
            if isinstance(event, ContainerRecoveredEvent):
                recovery_event = event
                break

        assert recovery_event is not None
        assert recovery_event.container_id == "container-123"
        assert recovery_event.recovery_action == "reconnect_with_monitoring"

    @pytest.mark.asyncio
    async def test_recover_or_cleanup_containers_with_kill(self):
        """Service should emit kill events when containers are cleaned up."""
        mock_adapter = MockContainerRecoveryAdapter()
        event_emitter = MagicMock()

        service = ContainerRecoveryService(
            recovery_adapter=mock_adapter,
            event_emitter=event_emitter,
        )

        # Add a container that will be killed
        container = mock_adapter.add_container(
            container_id="container-456",
            container_name="old-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            age_hours=3.0,  # 3 hours old
        )

        # Set assessment to kill
        mock_adapter.set_assessment(
            container_id="container-456",
            action="kill",
            reason="container_timeout",
            with_monitoring=False,
        )

        result = await service.recover_or_cleanup_containers()

        assert result.recovered == 0
        assert result.killed == 1
        assert result.errors == 0

        # Verify kill event was emitted
        calls = event_emitter.emit.call_args_list
        kill_event = None
        for call in calls:
            event = call[0][0]
            if isinstance(event, ContainerKilledEvent):
                kill_event = event
                break

        assert kill_event is not None
        assert kill_event.container_id == "container-456"
        assert kill_event.kill_reason == "container_timeout"

    @pytest.mark.asyncio
    async def test_recover_or_cleanup_containers_with_failures(self):
        """Service should handle action failures gracefully."""
        mock_adapter = MockContainerRecoveryAdapter()
        event_emitter = MagicMock()

        service = ContainerRecoveryService(
            recovery_adapter=mock_adapter,
            event_emitter=event_emitter,
        )

        # Add containers
        container1 = mock_adapter.add_container(
            container_id="container-1",
            container_name="test-1",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            age_hours=1.0,
        )

        container2 = mock_adapter.add_container(
            container_id="container-2",
            container_name="test-2",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-2",
            age_hours=1.0,
        )

        # Set assessments
        mock_adapter.set_assessment(
            container_id="container-1",
            action="reconnect",
            reason="valid_execution",
            with_monitoring=False,
            execution_id="exec-1",
        )

        mock_adapter.set_assessment(
            container_id="container-2",
            action="reconnect",
            reason="valid_execution",
            with_monitoring=False,
            execution_id="exec-2",
        )

        # Mark one as failing
        mock_adapter.set_action_failure("container-1")

        result = await service.recover_or_cleanup_containers()

        assert result.recovered == 1
        assert result.killed == 0
        assert result.errors == 1

    @pytest.mark.asyncio
    async def test_recovery_completion_event(self):
        """Service should emit completion event with summary."""
        mock_adapter = MockContainerRecoveryAdapter()
        event_emitter = MagicMock()

        service = ContainerRecoveryService(
            recovery_adapter=mock_adapter,
            event_emitter=event_emitter,
        )

        # Add mixed containers
        mock_adapter.add_container(
            container_id="container-1",
            container_name="test-1",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            age_hours=1.0,
        )

        mock_adapter.set_assessment(
            container_id="container-1",
            action="reconnect",
            reason="valid_execution",
            with_monitoring=False,
            execution_id="exec-1",
        )

        mock_adapter.add_container(
            container_id="container-2",
            container_name="test-2",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-2",
            age_hours=3.0,
        )

        mock_adapter.set_assessment(
            container_id="container-2",
            action="kill",
            reason="container_timeout",
            with_monitoring=False,
        )

        mock_adapter.repair_cycles_to_process = 2

        result = await service.recover_or_cleanup_containers()

        # Check result
        assert result.recovered == 1
        assert result.killed == 1
        assert result.repair_cycles_processed == 2

        # Find completion event
        calls = event_emitter.emit.call_args_list
        completion_event = None
        for call in calls:
            event = call[0][0]
            if isinstance(event, ContainerRecoveryCompletedEvent):
                completion_event = event
                break

        assert completion_event is not None
        assert completion_event.containers_recovered == 1
        assert completion_event.containers_killed == 1
        assert completion_event.repair_cycles_processed == 2


class TestCalculateUptimeSeconds:
    """Tests for uptime calculation utility."""

    def test_calculate_uptime_seconds_current(self):
        """Should calculate uptime correctly for recently created container."""
        now = datetime.now(timezone.utc)
        created_at = now - timedelta(seconds=30)

        uptime = ContainerRecoveryService._calculate_uptime_seconds(created_at)

        assert uptime >= 29
        assert uptime <= 31

    def test_calculate_uptime_seconds_hours(self):
        """Should calculate uptime correctly for container hours old."""
        now = datetime.now(timezone.utc)
        created_at = now - timedelta(hours=2)

        uptime = ContainerRecoveryService._calculate_uptime_seconds(created_at)

        expected = 2 * 3600  # 2 hours in seconds
        assert uptime >= expected - 10
        assert uptime <= expected + 10

    def test_calculate_uptime_seconds_very_new(self):
        """Should handle containers created less than a second ago."""
        now = datetime.now(timezone.utc)
        created_at = now

        uptime = ContainerRecoveryService._calculate_uptime_seconds(created_at)

        assert uptime >= 0
        assert uptime < 1
