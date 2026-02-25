"""Unit tests for ContainerRecoveryService application service.

These tests verify:
- Service lifecycle and initialization
- Recovery cycle coordination
- Event emission on recovery actions
- Error handling and recovery
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

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

    @pytest.mark.asyncio
    async def test_recovery_event_emission_failure_handling(self):
        """Service should handle event emission failures gracefully."""
        mock_adapter = MockContainerRecoveryAdapter()
        event_emitter = MagicMock()

        # Configure event_emitter to fail on first call
        event_emitter.emit.side_effect = [
            Exception("Event store connection error"),  # Fails for recovery event
            None,  # Succeeds for kill event
            None,  # Succeeds for completion event
        ]

        service = ContainerRecoveryService(
            recovery_adapter=mock_adapter,
            event_emitter=event_emitter,
        )

        # Add a container that will be recovered
        mock_adapter.add_container(
            container_id="container-123",
            container_name="test-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            work_item_id="work-123",
            execution_id="exec-456",
            age_hours=1.0,
        )

        mock_adapter.set_assessment(
            container_id="container-123",
            action="reconnect",
            reason="valid_execution",
            with_monitoring=True,
            execution_id="exec-456",
        )

        # Should not raise - recovery should succeed even if event emission fails
        result = await service.recover_or_cleanup_containers()

        assert result.recovered == 1
        assert result.killed == 0
        assert result.errors == 0

    @pytest.mark.asyncio
    async def test_kill_event_emission_failure_handling(self):
        """Service should handle kill event emission failures gracefully."""
        mock_adapter = MockContainerRecoveryAdapter()
        event_emitter = MagicMock()

        # Configure event_emitter to fail on kill event
        event_emitter.emit.side_effect = [
            None,  # Succeeds for no recovery events in this test
            Exception("Event serialization error"),  # Fails for kill event
            None,  # Succeeds for completion event
        ]

        service = ContainerRecoveryService(
            recovery_adapter=mock_adapter,
            event_emitter=event_emitter,
        )

        # Add a container that will be killed
        mock_adapter.add_container(
            container_id="container-456",
            container_name="old-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            age_hours=3.0,
        )

        mock_adapter.set_assessment(
            container_id="container-456",
            action="kill",
            reason="container_timeout",
            with_monitoring=False,
        )

        # Should not raise - kill should succeed even if event emission fails
        result = await service.recover_or_cleanup_containers()

        assert result.recovered == 0
        assert result.killed == 1
        assert result.errors == 0

    @pytest.mark.asyncio
    async def test_completion_event_emission_failure_handling(self):
        """Service should handle completion event emission failures gracefully."""
        mock_adapter = MockContainerRecoveryAdapter()
        event_emitter = MagicMock()

        # Configure event_emitter to fail on completion event
        event_emitter.emit.side_effect = Exception("Event bus unavailable")

        service = ContainerRecoveryService(
            recovery_adapter=mock_adapter,
            event_emitter=event_emitter,
        )

        # Add a container that will be recovered
        mock_adapter.add_container(
            container_id="container-123",
            container_name="test-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            work_item_id="work-123",
            execution_id="exec-456",
            age_hours=1.0,
        )

        mock_adapter.set_assessment(
            container_id="container-123",
            action="reconnect",
            reason="valid_execution",
            with_monitoring=True,
            execution_id="exec-456",
        )

        # Should not raise - completion should succeed even if event emission fails
        result = await service.recover_or_cleanup_containers()

        assert result.recovered == 1
        assert result.killed == 0
        assert result.errors == 0


class TestCalculateUptimeSeconds:
    """Tests for uptime calculation utility."""

    def test_calculate_uptime_seconds_current(self):
        """Should calculate uptime correctly for recently created container."""
        now = datetime.now(UTC)
        created_at = now - timedelta(seconds=30)

        uptime = ContainerRecoveryService._calculate_uptime_seconds(created_at)

        assert uptime >= 29
        assert uptime <= 31

    def test_calculate_uptime_seconds_hours(self):
        """Should calculate uptime correctly for container hours old."""
        now = datetime.now(UTC)
        created_at = now - timedelta(hours=2)

        uptime = ContainerRecoveryService._calculate_uptime_seconds(created_at)

        expected = 2 * 3600  # 2 hours in seconds
        assert uptime >= expected - 10
        assert uptime <= expected + 10

    def test_calculate_uptime_seconds_very_new(self):
        """Should handle containers created less than a second ago."""
        now = datetime.now(UTC)
        created_at = now

        uptime = ContainerRecoveryService._calculate_uptime_seconds(created_at)

        assert uptime >= 0
        assert uptime < 1


class TestCriticalEdgeCases:
    """Tests for critical edge cases that could cause production failures."""

    @pytest.mark.asyncio
    async def test_docker_daemon_failure_during_recovery_partial_processing(self):
        """Test Docker API failure mid-recovery after processing some containers.

        Criticality: 10/10
        Scenario: Docker daemon becomes unavailable mid-recovery after processing 5 out of 10 containers

        Expected behavior:
        - First 5 containers are processed successfully
        - Remaining 5 containers result in errors (cannot reach Docker)
        - RecoveryResult shows: recovered=2, killed=3, errors=5
        - Completion event is still emitted with partial results
        - Service doesn't crash
        """
        mock_adapter = MockContainerRecoveryAdapter()
        event_emitter = MagicMock()

        service = ContainerRecoveryService(
            recovery_adapter=mock_adapter,
            event_emitter=event_emitter,
        )

        # Setup: Add 10 containers to process
        for i in range(10):
            mock_adapter.add_container(
                container_id=f"container-{i}",
                container_name=f"test-container-{i}",
                project_id="proj-1",
                agent_id=f"agent-{i % 2}",
                task_id=f"task-{i}",
                age_hours=1.0,
            )

        # First 2 reconnect, next 3 kill
        for i in range(2):
            mock_adapter.set_assessment(
                container_id=f"container-{i}",
                action="reconnect",
                reason="valid_execution",
                with_monitoring=True,
                execution_id=f"exec-{i}",
            )

        for i in range(2, 5):
            mock_adapter.set_assessment(
                container_id=f"container-{i}",
                action="kill",
                reason="container_timeout",
                with_monitoring=False,
            )

        # Simulate Docker daemon failure after processing 5 containers
        mock_adapter.set_docker_failure_after_count(5)

        # Execute recovery
        result = await service.recover_or_cleanup_containers()

        # Verify partial recovery: 2 recovered, 3 killed, 5 errors
        assert result.recovered == 2
        assert result.killed == 3
        assert result.errors == 5

        # Verify completion event was still emitted despite partial failure
        calls = event_emitter.emit.call_args_list
        completion_events = [call[0][0] for call in calls if isinstance(call[0][0], ContainerRecoveryCompletedEvent)]
        assert len(completion_events) == 1
        completion_event = completion_events[0]
        assert completion_event.containers_recovered == 2
        assert completion_event.containers_killed == 3
        assert completion_event.errors_encountered == 5

    @pytest.mark.asyncio
    async def test_concurrent_container_state_change_between_assessment_and_execution(self):
        """Test container killed externally between assessment and execution.

        Criticality: 9/10
        Scenario: Container is killed by external process between assessment and execution

        Expected behavior:
        - Service attempts to reconnect container
        - Docker API raises ContainerNotFound during execution
        - Error is caught and recorded as error count
        - Recovery continues with remaining containers
        - Event shows error state
        """
        mock_adapter = MockContainerRecoveryAdapter()
        event_emitter = MagicMock()

        service = ContainerRecoveryService(
            recovery_adapter=mock_adapter,
            event_emitter=event_emitter,
        )

        # Add container that will pass assessment
        mock_adapter.add_container(
            container_id="container-vanishing",
            container_name="vanishing-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            work_item_id="work-1",
            execution_id="exec-1",
            age_hours=1.0,
        )

        # Assessment says reconnect
        mock_adapter.set_assessment(
            container_id="container-vanishing",
            action="reconnect",
            reason="valid_execution",
            with_monitoring=True,
            execution_id="exec-1",
        )

        # But execution fails because container is gone
        mock_adapter.set_action_failure("container-vanishing")

        result = await service.recover_or_cleanup_containers()

        # Verify error is recorded
        assert result.recovered == 0
        assert result.killed == 0
        assert result.errors == 1

        # Verify completion event shows error
        calls = event_emitter.emit.call_args_list
        completion_events = [call[0][0] for call in calls if isinstance(call[0][0], ContainerRecoveryCompletedEvent)]
        assert len(completion_events) == 1
        assert completion_events[0].errors_encountered == 1

    @pytest.mark.asyncio
    async def test_storage_scan_malformed_keys_during_repair_cycle_processing(self):
        """Test storage returns keys that don't match expected format.

        Criticality: 8/10
        Scenario: Storage returns malformed keys during repair cycle result processing

        Expected behavior:
        - Service attempts to process storage keys
        - Malformed key is skipped with warning
        - Valid keys are processed normally
        - Recovery continues without crashing
        - Error count reflects processing failures
        """
        mock_adapter = MockContainerRecoveryAdapter()
        event_emitter = MagicMock()

        service = ContainerRecoveryService(
            recovery_adapter=mock_adapter,
            event_emitter=event_emitter,
        )

        # Simulate storage with malformed keys
        # The adapter will try to process "malformed_key_xyz" which doesn't match pattern
        mock_adapter.add_malformed_storage_key("malformed_key_xyz")
        mock_adapter.repair_cycles_to_process = 1  # One valid cycle despite malformed key

        result = await service.recover_or_cleanup_containers()

        # Service should still complete without crashing
        assert result.repair_cycles_processed == 1
        # Malformed keys should be logged but not counted as errors (internal detail)
        assert result.errors == 0

        # Completion event should still be emitted
        calls = event_emitter.emit.call_args_list
        completion_events = [call[0][0] for call in calls if isinstance(call[0][0], ContainerRecoveryCompletedEvent)]
        assert len(completion_events) == 1

    @pytest.mark.asyncio
    async def test_checkpoint_store_unavailable_during_repair_cycle_assessment(self):
        """Test checkpoint store failure during repair cycle container assessment.

        Criticality: 8/10
        Scenario: Checkpoint store becomes unavailable when assessing repair cycle containers

        Expected behavior:
        - Service attempts to assess repair cycle container
        - Checkpoint store raises StorageError
        - Error is caught and recorded
        - Recovery continues
        - Completion event is emitted with error count
        """
        mock_adapter = MockContainerRecoveryAdapter()
        event_emitter = MagicMock()

        service = ContainerRecoveryService(
            recovery_adapter=mock_adapter,
            event_emitter=event_emitter,
        )

        # Add a repair cycle container
        mock_adapter.add_container(
            container_id="repair-cycle-123",
            container_name="repair-cycle",
            project_id="proj-1",
            agent_id="repair_engine",
            task_id="task-1",
            age_hours=1.0,
            container_type="repair-cycle",
        )

        # Simulate checkpoint store failure
        mock_adapter.set_checkpoint_store_failure("repair-cycle-123")

        result = await service.recover_or_cleanup_containers()

        # Verify error is recorded
        assert result.errors == 1

        # Verify completion event shows error
        calls = event_emitter.emit.call_args_list
        completion_events = [call[0][0] for call in calls if isinstance(call[0][0], ContainerRecoveryCompletedEvent)]
        assert len(completion_events) == 1
        assert completion_events[0].errors_encountered == 1

    @pytest.mark.asyncio
    async def test_asyncio_gather_exception_handling_uncaught_exception(self):
        """Test asyncio.gather exception handling when container processing raises unexpected exception.

        Criticality: 9/10
        Scenario: One container processing raises unexpected exception type that isn't caught

        Expected behavior:
        - asyncio.gather collects exception with return_exceptions=True
        - Service processes exception and records as error
        - Other containers continue processing
        - RecoveryResult shows partial success + error count
        - Completion event is emitted
        - Service doesn't crash
        """
        mock_adapter = MockContainerRecoveryAdapter()
        event_emitter = MagicMock()

        service = ContainerRecoveryService(
            recovery_adapter=mock_adapter,
            event_emitter=event_emitter,
        )

        # Add multiple containers, one will raise an unexpected exception
        for i in range(3):
            mock_adapter.add_container(
                container_id=f"container-{i}",
                container_name=f"test-{i}",
                project_id="proj-1",
                agent_id="agent-1",
                task_id=f"task-{i}",
                age_hours=1.0,
            )

        # First container reconnects successfully
        mock_adapter.set_assessment(
            container_id="container-0",
            action="reconnect",
            reason="valid_execution",
            with_monitoring=True,
            execution_id="exec-0",
        )

        # Second container raises unexpected exception during assessment
        mock_adapter.set_assessment_exception("container-1", RuntimeError("Unexpected error"))

        # Third container kills successfully
        mock_adapter.set_assessment(
            container_id="container-2",
            action="kill",
            reason="container_timeout",
            with_monitoring=False,
        )

        result = await service.recover_or_cleanup_containers()

        # Verify partial recovery: 1 recovered, 1 killed, 1 error
        assert result.recovered == 1
        assert result.killed == 1
        assert result.errors == 1

        # Verify completion event shows all outcomes
        calls = event_emitter.emit.call_args_list
        completion_events = [call[0][0] for call in calls if isinstance(call[0][0], ContainerRecoveryCompletedEvent)]
        assert len(completion_events) == 1
        assert completion_events[0].containers_recovered == 1
        assert completion_events[0].containers_killed == 1
        assert completion_events[0].errors_encountered == 1

    @pytest.mark.asyncio
    async def test_event_emission_failures_partial_emission_success(self):
        """Test recovery continues when event emission partially fails.

        Criticality: 7/10
        Scenario: Event emitter fails on some events but succeeds on others

        Expected behavior:
        - Recovery continues despite event emission failures
        - Actions are recorded in results even if events fail
        - Completion event is always attempted
        - No recovery actions are lost
        """
        mock_adapter = MockContainerRecoveryAdapter()
        event_emitter = MagicMock()

        service = ContainerRecoveryService(
            recovery_adapter=mock_adapter,
            event_emitter=event_emitter,
        )

        # Add containers
        mock_adapter.add_container(
            container_id="container-1",
            container_name="test-1",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            work_item_id="work-1",
            execution_id="exec-1",
            age_hours=1.0,
        )

        mock_adapter.add_container(
            container_id="container-2",
            container_name="test-2",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-2",
            age_hours=3.0,
        )

        # Set assessments
        mock_adapter.set_assessment(
            container_id="container-1",
            action="reconnect",
            reason="valid_execution",
            with_monitoring=True,
            execution_id="exec-1",
        )

        mock_adapter.set_assessment(
            container_id="container-2",
            action="kill",
            reason="container_timeout",
            with_monitoring=False,
        )

        # Simulate event emitter failing on recovery event, succeeding on kill event
        event_emitter.emit.side_effect = [
            Exception("Event store down"),  # Fails for recovery event
            None,  # Succeeds for kill event
            None,  # Succeeds for completion event
        ]

        result = await service.recover_or_cleanup_containers()

        # Verify both actions succeeded despite event failures
        assert result.recovered == 1
        assert result.killed == 1
        assert result.errors == 0

    @pytest.mark.asyncio
    async def test_malformed_execution_state_in_metadata(self):
        """Test execution state with unexpected structure is handled gracefully.

        Criticality: 7/10
        Scenario: Container metadata has partial/missing optional fields

        Expected behavior:
        - Service handles containers with missing optional metadata gracefully
        - Assessment succeeds even when work_item_id is missing
        - Container is reconnected with limited monitoring
        - Events are emitted with None values for missing optional fields
        - No crashes or stack traces
        """
        mock_adapter = MockContainerRecoveryAdapter()
        event_emitter = MagicMock()

        service = ContainerRecoveryService(
            recovery_adapter=mock_adapter,
            event_emitter=event_emitter,
        )

        # Add container with incomplete metadata (no work_item_id, no execution_id)
        # This simulates a container created without full context
        container = mock_adapter.add_container(
            container_id="container-malformed",
            container_name="malformed-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            # Intentionally omit work_item_id and execution_id to simulate partial metadata
            work_item_id=None,
            execution_id=None,
            age_hours=1.0,
        )

        # Service should default to kill for containers without execution_id
        # and handle gracefully
        result = await service.recover_or_cleanup_containers()

        # Service should handle gracefully and kill the container (no execution_id)
        assert result.recovered == 0
        assert result.killed == 1
        assert result.errors == 0

        # Verify kill event was emitted with None for optional fields
        calls = event_emitter.emit.call_args_list
        kill_events = [call[0][0] for call in calls if isinstance(call[0][0], ContainerKilledEvent)]
        assert len(kill_events) == 1
        # Event should have None for missing fields, not crash
        assert kill_events[0].work_item_id is None
        assert kill_events[0].execution_marked_failed is False  # No work_item_id

    @pytest.mark.asyncio
    async def test_all_critical_errors_combined_scenario(self):
        """Test recovery continues when multiple critical failures occur.

        Combined criticality test: Docker failure, malformed data, event emission failure

        Expected behavior:
        - Service processes 20 containers
        - Docker fails after 8 containers
        - Some containers have malformed data
        - Event emission fails intermittently
        - Service completes and reports summary: recovered, killed, errors
        - Completion event is always emitted
        """
        mock_adapter = MockContainerRecoveryAdapter()
        event_emitter = MagicMock()

        service = ContainerRecoveryService(
            recovery_adapter=mock_adapter,
            event_emitter=event_emitter,
        )

        # Add 20 containers
        for i in range(20):
            mock_adapter.add_container(
                container_id=f"container-{i}",
                container_name=f"test-{i}",
                project_id="proj-1",
                agent_id=f"agent-{i % 3}",
                task_id=f"task-{i}",
                work_item_id=f"work-{i}" if i % 2 == 0 else None,
                execution_id=f"exec-{i}" if i % 3 != 0 else None,
                age_hours=float(i % 4),
            )

        # Set assessments for first 8 containers
        for i in range(8):
            action = "reconnect" if i % 2 == 0 else "kill"
            reason = "valid_execution" if action == "reconnect" else "container_timeout"
            mock_adapter.set_assessment(
                container_id=f"container-{i}",
                action=action,
                reason=reason,
                with_monitoring=i % 2 == 0,
                execution_id=f"exec-{i}" if i % 2 == 0 else None,
            )

        # Simulate Docker failure after 8 containers
        mock_adapter.set_docker_failure_after_count(8)

        # Simulate intermittent event emission failures
        event_emitter.emit.side_effect = [
            None,  # recovery 0
            None,  # kill 1
            None,  # recovery 2
            Exception("Event bus temporary failure"),  # kill 3 - fails
            None,  # recovery 4
            None,  # kill 5
            None,  # recovery 6
            None,  # kill 7
            # From here on, Docker failures mean no events
            None,  # Completion event
        ]

        result = await service.recover_or_cleanup_containers()

        # Verify results: 4 recovered, 4 killed, 12 errors (Docker failures)
        assert result.recovered == 4
        assert result.killed == 4
        assert result.errors == 12

        # Verify completion event was always emitted
        calls = event_emitter.emit.call_args_list
        completion_events = [call[0][0] for call in calls if isinstance(call[0][0], ContainerRecoveryCompletedEvent)]
        assert len(completion_events) == 1
        assert completion_events[0].containers_recovered == 4
        assert completion_events[0].containers_killed == 4
        assert completion_events[0].errors_encountered == 12
