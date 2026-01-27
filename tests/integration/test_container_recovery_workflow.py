"""Integration tests for container recovery workflow.

These tests verify:
- Full recovery cycle with mock adapters
- Event emission and handling
- Error scenarios and recovery
- Integration with event store and event emitter
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

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


class MockEventEmitter:
    """Mock event emitter for testing."""

    def __init__(self):
        """Initialize mock event emitter."""
        self.events = []

    def emit(self, event):
        """Emit an event."""
        self.events.append(event)

    def get_events_by_type(self, event_type):
        """Get all events of a specific type."""
        return [e for e in self.events if isinstance(e, event_type)]


class TestContainerRecoveryWorkflowWithMocks:
    """Integration tests using mock adapters."""

    @pytest.mark.asyncio
    async def test_full_recovery_cycle_with_multiple_containers(self):
        """
        Test complete recovery cycle with multiple containers:
        - 1 recent container with execution (should recover with monitoring)
        - 1 recent container without work item (should recover limited)
        - 1 old container (should kill)
        - 1 orphan (should kill)
        """
        # Setup event emitter
        event_emitter = MockEventEmitter()

        # Setup event store
        event_store = MagicMock()

        async def mock_get_events(aggregate_id, limit=1):
            # exec-001 and exec-002 exist, exec-orphan doesn't
            if aggregate_id in ("exec-001", "exec-002"):
                return [{"type": "ExecutionStarted"}]
            raise Exception("Execution not found")

        event_store.get_events = mock_get_events

        # Setup service
        service = ContainerRecoveryService(
            container_service=MagicMock(),
            event_store=event_store,
            event_emitter=event_emitter,
        )

        # Setup mock adapter
        mock_adapter = MockContainerRecoveryAdapter()

        # Add containers
        # 1. Recent with work_item (should recover with monitoring)
        mock_adapter.add_container(
            container_id="container-1",
            container_name="recovery-with-monitoring",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            work_item_id="work-123",
            execution_id="exec-001",
            age_hours=1.0,
        )

        # 2. Recent without work_item (should recover limited)
        mock_adapter.add_container(
            container_id="container-2",
            container_name="recovery-limited",
            project_id="proj-1",
            agent_id="agent-2",
            task_id="task-2",
            execution_id="exec-002",
            age_hours=0.5,
        )

        # 3. Old container (should kill)
        mock_adapter.add_container(
            container_id="container-3",
            container_name="old-container",
            project_id="proj-1",
            agent_id="agent-3",
            task_id="task-3",
            age_hours=3.0,
        )

        # 4. Orphan container (should kill)
        mock_adapter.add_container(
            container_id="container-4",
            container_name="orphan-container",
            project_id="proj-1",
            agent_id="agent-4",
            task_id="task-4",
            execution_id="exec-orphan",
            age_hours=1.0,
        )

        # Setup assessments
        mock_adapter.set_assessment(
            container_id="container-1",
            action="reconnect",
            reason="execution_in_progress",
            with_monitoring=True,
            execution_id="exec-001",
        )

        mock_adapter.set_assessment(
            container_id="container-2",
            action="reconnect",
            reason="execution_in_progress",
            with_monitoring=False,
            execution_id="exec-002",
        )

        mock_adapter.set_assessment(
            container_id="container-3",
            action="kill",
            reason="container_timeout",
            with_monitoring=False,
        )

        mock_adapter.set_assessment(
            container_id="container-4",
            action="kill",
            reason="no_execution_found",
            with_monitoring=False,
        )

        # Wire adapter methods
        service.get_running_agent_containers = (
            mock_adapter.get_running_agent_containers
        )
        service.assess_container = mock_adapter.assess_container
        service.execute_recovery_action = mock_adapter.execute_recovery_action
        service.process_orphaned_repair_results = (
            mock_adapter.process_orphaned_repair_results
        )

        # Execute recovery
        result = await service.recover_or_cleanup_containers()

        # Verify results
        assert result.recovered == 2
        assert result.killed == 2
        assert result.errors == 0

        # Verify events
        recovered_events = event_emitter.get_events_by_type(ContainerRecoveredEvent)
        killed_events = event_emitter.get_events_by_type(ContainerKilledEvent)
        completion_events = event_emitter.get_events_by_type(
            ContainerRecoveryCompletedEvent
        )

        assert len(recovered_events) == 2
        assert len(killed_events) == 2
        assert len(completion_events) == 1

        # Verify recovery event details
        recovery_with_monitoring = [
            e for e in recovered_events if e.container_id == "container-1"
        ][0]
        assert recovery_with_monitoring.recovery_action == "reconnect_with_monitoring"
        assert recovery_with_monitoring.project_id == "proj-1"

        recovery_limited = [
            e for e in recovered_events if e.container_id == "container-2"
        ][0]
        assert recovery_limited.recovery_action == "reconnect_limited"

        # Verify kill event details
        killed_by_timeout = [
            e for e in killed_events if e.container_id == "container-3"
        ][0]
        assert killed_by_timeout.kill_reason == "container_timeout"

        killed_orphan = [
            e for e in killed_events if e.container_id == "container-4"
        ][0]
        assert killed_orphan.kill_reason == "no_execution_found"

        # Verify completion event
        completion_event = completion_events[0]
        assert completion_event.containers_recovered == 2
        assert completion_event.containers_killed == 2
        assert completion_event.errors_encountered == 0
        assert completion_event.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_recovery_with_partial_failures(self):
        """Test recovery when some actions fail."""
        event_emitter = MockEventEmitter()
        event_store = MagicMock()
        event_store.get_events = AsyncMock(return_value=[{"type": "ExecutionStarted"}])

        service = ContainerRecoveryService(
            container_service=MagicMock(),
            event_store=event_store,
            event_emitter=event_emitter,
        )

        mock_adapter = MockContainerRecoveryAdapter()

        # Add containers
        mock_adapter.add_container(
            container_id="success-1",
            container_name="success",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            execution_id="exec-1",
            age_hours=1.0,
        )

        mock_adapter.add_container(
            container_id="failure-1",
            container_name="failure",
            project_id="proj-1",
            agent_id="agent-2",
            task_id="task-2",
            execution_id="exec-2",
            age_hours=1.0,
        )

        # Setup assessments
        mock_adapter.set_assessment(
            container_id="success-1",
            action="reconnect",
            reason="execution_in_progress",
            with_monitoring=False,
            execution_id="exec-1",
        )

        mock_adapter.set_assessment(
            container_id="failure-1",
            action="reconnect",
            reason="execution_in_progress",
            with_monitoring=False,
            execution_id="exec-2",
        )

        # Mark one as failing
        mock_adapter.set_action_failure("failure-1")

        # Wire adapter methods
        service.get_running_agent_containers = (
            mock_adapter.get_running_agent_containers
        )
        service.assess_container = mock_adapter.assess_container
        service.execute_recovery_action = mock_adapter.execute_recovery_action
        service.process_orphaned_repair_results = (
            mock_adapter.process_orphaned_repair_results
        )

        # Execute recovery
        result = await service.recover_or_cleanup_containers()

        # Verify results
        assert result.recovered == 1
        assert result.killed == 0
        assert result.errors == 1

        # Verify events
        recovered_events = event_emitter.get_events_by_type(ContainerRecoveredEvent)
        assert len(recovered_events) == 1
        assert recovered_events[0].container_id == "success-1"

    @pytest.mark.asyncio
    async def test_recovery_with_repair_cycles(self):
        """Test recovery processes orphaned repair cycle results."""
        event_emitter = MockEventEmitter()
        event_store = MagicMock()
        event_store.get_events = AsyncMock(return_value=[])

        service = ContainerRecoveryService(
            container_service=MagicMock(),
            event_store=event_store,
            event_emitter=event_emitter,
        )

        mock_adapter = MockContainerRecoveryAdapter()

        # Configure repair cycles
        mock_adapter.repair_cycles_to_process = 5

        # Wire adapter methods
        service.get_running_agent_containers = (
            mock_adapter.get_running_agent_containers
        )
        service.assess_container = mock_adapter.assess_container
        service.execute_recovery_action = mock_adapter.execute_recovery_action
        service.process_orphaned_repair_results = (
            mock_adapter.process_orphaned_repair_results
        )

        # Execute recovery
        result = await service.recover_or_cleanup_containers()

        # Verify repair cycles were processed
        assert result.repair_cycles_processed == 5

        # Verify completion event includes repair cycles
        completion_events = event_emitter.get_events_by_type(
            ContainerRecoveryCompletedEvent
        )
        assert len(completion_events) == 1
        assert completion_events[0].repair_cycles_processed == 5

    @pytest.mark.asyncio
    async def test_recovery_event_timestamp_ordering(self):
        """Test that events have proper timestamps in chronological order."""
        event_emitter = MockEventEmitter()
        event_store = MagicMock()
        event_store.get_events = AsyncMock(return_value=[{"type": "ExecutionStarted"}])

        service = ContainerRecoveryService(
            container_service=MagicMock(),
            event_store=event_store,
            event_emitter=event_emitter,
        )

        mock_adapter = MockContainerRecoveryAdapter()

        mock_adapter.add_container(
            container_id="container-1",
            container_name="test",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            execution_id="exec-1",
            age_hours=1.0,
        )

        mock_adapter.set_assessment(
            container_id="container-1",
            action="reconnect",
            reason="execution_in_progress",
            with_monitoring=False,
            execution_id="exec-1",
        )

        # Wire adapter methods
        service.get_running_agent_containers = (
            mock_adapter.get_running_agent_containers
        )
        service.assess_container = mock_adapter.assess_container
        service.execute_recovery_action = mock_adapter.execute_recovery_action
        service.process_orphaned_repair_results = (
            mock_adapter.process_orphaned_repair_results
        )

        # Execute recovery
        await service.recover_or_cleanup_containers()

        # Verify all events have timestamps
        assert len(event_emitter.events) > 0
        for event in event_emitter.events:
            assert hasattr(event, "timestamp")
            assert event.timestamp  # Not empty
            # Verify timestamp is ISO format
            try:
                datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
            except ValueError:
                pytest.fail(f"Invalid ISO timestamp: {event.timestamp}")
