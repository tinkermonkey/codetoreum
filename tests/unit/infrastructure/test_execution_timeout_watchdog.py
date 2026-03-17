"""Unit tests for ExecutionTimeoutWatchdog."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codetoreum.adapters.testing.execution_service_agent_executor import (
    ActiveExecutionInfo,
    ExecutionServiceAgentExecutor,
)
from codetoreum.domain.events.execution_events import ExecutionTimedOutEvent
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.infrastructure.simulation.watchdogs import ExecutionTimeoutWatchdog


@pytest.fixture
def simulation_clock():
    """Create a simulation clock."""
    return SimulationClock(speed_multiplier=100.0)


@pytest.fixture
def mock_event_emitter():
    """Create mock event emitter."""
    emitter = AsyncMock()
    emitter.emit = AsyncMock()
    return emitter


@pytest.fixture
def mock_executor():
    """Create mock executor."""
    executor = MagicMock(spec=ExecutionServiceAgentExecutor)
    executor.get_active_executions = MagicMock(return_value=[])
    return executor


@pytest.fixture
def watchdog(mock_executor, mock_event_emitter, simulation_clock):
    """Create watchdog instance."""
    return ExecutionTimeoutWatchdog(
        executor=mock_executor,
        event_emitter=mock_event_emitter,
        clock=simulation_clock,
        check_interval=timedelta(seconds=30),
    )


class TestExecutionTimeoutWatchdogInitialization:
    """Test watchdog initialization."""

    def test_watchdog_creation(self, mock_executor, mock_event_emitter, simulation_clock):
        """Should create watchdog with all dependencies."""
        watchdog = ExecutionTimeoutWatchdog(
            executor=mock_executor,
            event_emitter=mock_event_emitter,
            clock=simulation_clock,
            check_interval=timedelta(seconds=30),
        )
        assert watchdog._executor is mock_executor
        assert watchdog._event_emitter is mock_event_emitter
        assert watchdog._clock is simulation_clock
        assert watchdog._check_interval == timedelta(seconds=30)


class TestWatchdogStartAndScheduling:
    """Test watchdog start and callback scheduling."""

    def test_start_schedules_callback(self, watchdog, simulation_clock):
        """Should schedule first callback when started."""
        # Arrange
        callbacks_before = len(simulation_clock.get_scheduled_callbacks())

        # Act
        watchdog.start()

        # Assert
        callbacks_after = len(simulation_clock.get_scheduled_callbacks())
        assert callbacks_after == callbacks_before + 1

        # Verify the callback is scheduled at the right time
        scheduled = simulation_clock.get_scheduled_callbacks()
        assert len(scheduled) > 0
        scheduled_time, callback = scheduled[-1]
        expected_time = simulation_clock.now() + timedelta(seconds=30)
        assert scheduled_time == expected_time


class TestTimeoutDetection:
    """Test timeout detection logic."""

    @pytest.mark.asyncio
    async def test_detects_timed_out_execution(self, mock_executor, watchdog, mock_event_emitter, simulation_clock):
        """Should detect an execution older than its timeout."""
        # Arrange: Create a timed-out execution
        now = simulation_clock.now()
        started_at = now - timedelta(seconds=3700)  # 1 hour before
        timeout_seconds = 3600  # 1 hour timeout

        fake_task = asyncio.Task(asyncio.sleep(0))
        exec_info = ActiveExecutionInfo(
            execution_id="exec-1",
            work_item_id="item-1",
            started_at=started_at,
            timeout_seconds=timeout_seconds,
            task=fake_task,
        )
        mock_executor.get_active_executions.return_value = [exec_info]

        # Act
        await watchdog._check_timeouts()

        # Assert: Event should be emitted
        mock_event_emitter.emit.assert_called_once()
        event = mock_event_emitter.emit.call_args[0][0]
        assert isinstance(event, ExecutionTimedOutEvent)
        assert event.execution_id == "exec-1"
        assert event.work_item_id == "item-1"
        assert event.timeout_seconds == 3600

        # Cleanup
        fake_task.cancel()
        try:
            await fake_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_does_not_detect_active_execution(
        self, mock_executor, watchdog, mock_event_emitter, simulation_clock
    ):
        """Should not detect an execution within its timeout."""
        # Arrange: Create a fresh execution
        now = simulation_clock.now()
        started_at = now - timedelta(seconds=1800)  # 30 minutes before
        timeout_seconds = 3600  # 1 hour timeout

        fake_task = asyncio.Task(asyncio.sleep(0))
        exec_info = ActiveExecutionInfo(
            execution_id="exec-1",
            work_item_id="item-1",
            started_at=started_at,
            timeout_seconds=timeout_seconds,
            task=fake_task,
        )
        mock_executor.get_active_executions.return_value = [exec_info]

        # Act
        await watchdog._check_timeouts()

        # Assert: No event should be emitted
        mock_event_emitter.emit.assert_not_called()

        # Cleanup
        fake_task.cancel()
        try:
            await fake_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_cancels_timed_out_task(self, mock_executor, watchdog, mock_event_emitter):
        """Should cancel the task of a timed-out execution."""
        # Arrange
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=3700)
        timeout_seconds = 3600

        # Create a real async task so we can verify cancellation
        async def dummy_execution():
            await asyncio.sleep(10)

        fake_task = asyncio.create_task(dummy_execution())
        exec_info = ActiveExecutionInfo(
            execution_id="exec-1",
            work_item_id="item-1",
            started_at=started_at,
            timeout_seconds=timeout_seconds,
            task=fake_task,
        )
        mock_executor.get_active_executions.return_value = [exec_info]

        # Mock the clock
        watchdog._clock.now = MagicMock(return_value=now)

        # Act
        await watchdog._check_timeouts()

        # Assert: Task should be cancelled
        await asyncio.sleep(0.1)  # Give task time to process cancellation
        assert fake_task.cancelled()

    @pytest.mark.asyncio
    async def test_multiple_timed_out_executions(self, mock_executor, watchdog, mock_event_emitter, simulation_clock):
        """Should detect multiple timed-out executions."""
        # Arrange
        now = simulation_clock.now()
        started_at = now - timedelta(seconds=3700)

        async def dummy():
            await asyncio.sleep(0)

        exec_info_1 = ActiveExecutionInfo(
            execution_id="exec-1",
            work_item_id="item-1",
            started_at=started_at,
            timeout_seconds=3600,
            task=asyncio.create_task(dummy()),
        )
        exec_info_2 = ActiveExecutionInfo(
            execution_id="exec-2",
            work_item_id="item-2",
            started_at=started_at,
            timeout_seconds=3600,
            task=asyncio.create_task(dummy()),
        )
        mock_executor.get_active_executions.return_value = [exec_info_1, exec_info_2]

        # Act
        await watchdog._check_timeouts()

        # Assert: Two events should be emitted
        assert mock_event_emitter.emit.call_count == 2
        events = [call[0][0] for call in mock_event_emitter.emit.call_args_list]
        assert all(isinstance(e, ExecutionTimedOutEvent) for e in events)
        assert events[0].execution_id == "exec-1"
        assert events[1].execution_id == "exec-2"

    @pytest.mark.asyncio
    async def test_ignores_no_executions(self, mock_executor, watchdog, mock_event_emitter):
        """Should handle case with no active executions."""
        # Arrange
        mock_executor.get_active_executions.return_value = []

        # Act
        await watchdog._check_timeouts()

        # Assert: No events emitted
        mock_event_emitter.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_clock_now_for_time(self, mock_executor, watchdog, simulation_clock):
        """Should use clock.now() exclusively, not datetime.now()."""
        # Arrange
        now = simulation_clock.now()
        started_at = now - timedelta(seconds=3700)

        async def dummy():
            await asyncio.sleep(0)

        exec_info = ActiveExecutionInfo(
            execution_id="exec-1",
            work_item_id="item-1",
            started_at=started_at,
            timeout_seconds=3600,
            task=asyncio.create_task(dummy()),
        )
        mock_executor.get_active_executions.return_value = [exec_info]

        # Mock datetime.now to ensure it's not used
        with patch("codetoreum.infrastructure.simulation.watchdogs.datetime") as mock_datetime:
            mock_datetime.UTC = UTC
            mock_datetime.now.side_effect = Exception("Should not call datetime.now()")

            # Act & Assert: Should not raise, proving we use clock.now()
            try:
                await watchdog._check_timeouts()
            except Exception as e:
                if "Should not call datetime.now()" in str(e):
                    pytest.fail("Watchdog should use clock.now(), not datetime.now()")
                raise


class TestTickAndRescheduling:
    """Test the tick method and self-rescheduling behavior."""

    @pytest.mark.asyncio
    async def test_tick_reschedules_on_success(self, watchdog, simulation_clock):
        """Should reschedule even after successful check."""
        # Arrange
        callbacks_before = len(simulation_clock.get_scheduled_callbacks())

        # Act
        await watchdog._tick(simulation_clock.now())

        # Assert: Should have scheduled the next tick
        callbacks_after = len(simulation_clock.get_scheduled_callbacks())
        assert callbacks_after == callbacks_before + 1

    @pytest.mark.asyncio
    async def test_tick_reschedules_on_error(self, watchdog, simulation_clock, mock_event_emitter):
        """Should reschedule even if check fails."""
        # Arrange: Make the check fail
        mock_event_emitter.emit.side_effect = Exception("Test error")

        callbacks_before = len(simulation_clock.get_scheduled_callbacks())

        # Act: Should not raise despite the error
        await watchdog._tick(simulation_clock.now())

        # Assert: Should still have scheduled the next tick
        callbacks_after = len(simulation_clock.get_scheduled_callbacks())
        assert callbacks_after == callbacks_before + 1

    @pytest.mark.asyncio
    async def test_error_logged_with_exc_info(
        self, mock_executor, watchdog, mock_event_emitter, caplog, simulation_clock
    ):
        """Should log errors with exc_info=True and continue."""
        # Arrange: Create a timed-out execution so emit will be called and fail
        now = simulation_clock.now()
        started_at = now - timedelta(seconds=3700)

        async def dummy():
            await asyncio.sleep(0)

        exec_info = ActiveExecutionInfo(
            execution_id="exec-1",
            work_item_id="item-1",
            started_at=started_at,
            timeout_seconds=3600,
            task=asyncio.create_task(dummy()),
        )
        mock_executor.get_active_executions.return_value = [exec_info]

        # Make the emit call fail
        mock_event_emitter.emit.side_effect = Exception("Test error")

        # Act: Should not raise despite the error
        await watchdog._tick(simulation_clock.now())

        # Assert: Error should be logged
        assert "ExecutionTimeoutWatchdog check failed" in caplog.text
        # Verify error was logged with exc_info
        assert "Traceback" in caplog.text  # Indicates exc_info was captured


class TestEventEmission:
    """Test domain event emission."""

    @pytest.mark.asyncio
    async def test_timeout_event_has_correct_fields(
        self, mock_executor, watchdog, mock_event_emitter, simulation_clock
    ):
        """Should emit ExecutionTimedOutEvent with all required fields."""
        # Arrange
        now = simulation_clock.now()
        started_at = now - timedelta(seconds=3700)

        async def dummy():
            await asyncio.sleep(0)

        exec_info = ActiveExecutionInfo(
            execution_id="exec-123",
            work_item_id="item-456",
            started_at=started_at,
            timeout_seconds=3600,
            task=asyncio.create_task(dummy()),
        )
        mock_executor.get_active_executions.return_value = [exec_info]

        # Act
        await watchdog._check_timeouts()

        # Assert
        mock_event_emitter.emit.assert_called_once()
        event = mock_event_emitter.emit.call_args[0][0]

        assert event.type == "execution.timed_out"
        assert event.execution_id == "exec-123"
        assert event.work_item_id == "item-456"
        assert event.timeout_seconds == 3600
        assert event.started_at == started_at.isoformat()
        assert event.source == "execution_timeout_watchdog"


class TestEndToEndWatchdogFlow:
    """Test complete watchdog flow."""

    @pytest.mark.asyncio
    async def test_complete_watchdog_cycle(self, mock_executor, watchdog, mock_event_emitter, simulation_clock):
        """Test a complete watchdog cycle: start, track execution, detect timeout."""
        # Arrange
        watchdog.start()

        # Add a timed-out execution
        now = simulation_clock.now()
        started_at = now - timedelta(seconds=3700)

        async def dummy():
            await asyncio.sleep(0)

        exec_info = ActiveExecutionInfo(
            execution_id="exec-1",
            work_item_id="item-1",
            started_at=started_at,
            timeout_seconds=3600,
            task=asyncio.create_task(dummy()),
        )
        mock_executor.get_active_executions.return_value = [exec_info]

        # Advance time to trigger watchdog tick
        await simulation_clock.advance(timedelta(seconds=30))

        # Assert: Event should have been emitted
        assert mock_event_emitter.emit.called

    @pytest.mark.asyncio
    async def test_execution_info_dataclass(self):
        """Test ActiveExecutionInfo dataclass construction."""
        # Arrange
        now = datetime.now(UTC)

        async def dummy():
            await asyncio.sleep(0)

        task = asyncio.create_task(dummy())

        # Act
        exec_info = ActiveExecutionInfo(
            execution_id="exec-1",
            work_item_id="item-1",
            started_at=now,
            timeout_seconds=3600,
            task=task,
        )

        # Assert
        assert exec_info.execution_id == "exec-1"
        assert exec_info.work_item_id == "item-1"
        assert exec_info.started_at == now
        assert exec_info.timeout_seconds == 3600
        assert exec_info.task is task

        # Cleanup
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
