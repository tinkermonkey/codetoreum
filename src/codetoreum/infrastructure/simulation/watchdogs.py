"""Watchdogs for simulation monitoring and health checks.

Watchdogs are background tasks that periodically scan simulation state and emit
domain events for conditions that need attention (e.g., stale locks, timed-out executions).

Design Principles:
- Use clock.now() exclusively for time comparisons (never datetime.now())
- Self-reschedule via clock.schedule_callback() to pause with auto-advance
- Log all errors with exc_info=True but always reschedule (fail-safe)
- Emit immutable domain events for all detections
- Force-release/cancel resources when detected stale or timed out
"""

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from codetoreum.adapters.secondary.in_memory_queue_lock_service import (
    InMemoryLockService,
)
from codetoreum.domain.events.execution_events import ExecutionTimedOutEvent
from codetoreum.domain.events.lock_events import LockStaleDetectedEvent
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.output.event_emitter import IEventEmitter

if TYPE_CHECKING:
    from codetoreum.adapters.testing.execution_service_agent_executor import (
        ExecutionServiceAgentExecutor,
    )

logger = logging.getLogger(__name__)


class StaleLockWatchdog:
    """Proactively detects and force-releases stale pipeline locks.

    On each clock tick interval, scans all held pipeline locks and emits
    LockStaleDetectedEvent for locks older than the stale threshold.
    Automatically force-releases stale locks via the lock service.

    This extends the existing reactive stale lock detection (which only fires
    on new lock acquisition) into a proactive, clock-driven check.

    Design:
    - Clock-driven: Calls clock.schedule_callback() to self-reschedule
    - Time-aware: Uses clock.now() exclusively for comparisons
    - Fail-safe: Errors logged but don't stop future checks
    - Event-driven: Emits LockStaleDetectedEvent for audit trail
    - Force-release: Calls lock_service.release_lock() to clean up

    Attributes:
        _lock_service: InMemoryLockService for lock iteration and release
        _event_emitter: IEventEmitter for domain event publication
        _clock: SimulationClock for time access and callback scheduling
        _stale_threshold: Age (timedelta) beyond which locks are stale
        _check_interval: Frequency (timedelta) of stale lock checks
    """

    def __init__(
        self,
        lock_service: InMemoryLockService,
        event_emitter: IEventEmitter,
        clock: SimulationClock,
        stale_threshold_seconds: int = 7200,
        check_interval: timedelta = timedelta(seconds=60),
    ):
        """Initialize stale lock watchdog.

        Args:
            lock_service: InMemoryLockService instance for lock access
            event_emitter: IEventEmitter for domain event publication
            clock: SimulationClock for time and callback scheduling
            stale_threshold_seconds: Age in seconds before lock is considered stale
                                    (default 7200 = 2 hours, must match lock_service threshold)
            check_interval: Frequency of checks (default 60 seconds simulated time)
        """
        self._lock_service = lock_service
        self._event_emitter = event_emitter
        self._clock = clock
        self._stale_threshold = timedelta(seconds=stale_threshold_seconds)
        self._check_interval = check_interval
        self._logger = logger

    def start(self) -> None:
        """Schedule first watchdog check.

        Registers a callback with the clock to run _tick() after _check_interval.
        This callback will reschedule itself, creating a continuous background check.

        Call this after the simulation engine and adapters are initialized.
        """
        self._clock.schedule_callback(self._tick, after_delta=self._check_interval)
        self._logger.info(
            "StaleLockWatchdog started: checking every %s simulated seconds",
            self._check_interval.total_seconds(),
        )

    async def _tick(self, scheduled_time: datetime) -> None:
        """Check for stale locks, always reschedule.

        This is the main watchdog loop callback. It:
        1. Calls _check_stale_locks() to scan and release stale locks
        2. Logs any errors with exc_info=True
        3. Always reschedules itself (even on error) via clock.schedule_callback()

        The always-reschedule pattern ensures that a single error doesn't stop
        the watchdog from future checks. This is critical for production-like robustness.

        Args:
            scheduled_time: The time when this callback was triggered (provided by clock)
        """
        try:
            await self._check_stale_locks()
        except Exception:
            self._logger.error(
                "StaleLockWatchdog check failed, will retry next interval",
                exc_info=True,
            )
        finally:
            # Always reschedule, even on error - fail-safe pattern
            self._clock.schedule_callback(self._tick, after_delta=self._check_interval)

    async def _check_stale_locks(self) -> None:
        """Scan all locks and force-release any that are stale.

        Gets all current lock states from the lock service, checks each held lock's age
        against the stale threshold, and for stale ones:
        1. Emits LockStaleDetectedEvent with timestamp for audit trail
        2. Force-releases the lock via lock_service.release_lock()
        3. Logs the stale lock at warning level

        Uses clock.now() exclusively for time comparisons, ensuring the watchdog
        pauses when auto-advance pauses and works with simulated time.

        Raises:
            Any exception from event emission or lock release (caught and logged by _tick())
        """
        now = self._clock.now()
        all_states = self._lock_service.get_all_lock_states()

        for key, state in all_states.items():
            # Only check locks that are currently held
            if state.lock_holder and state.lock_acquired_at:
                age = now - state.lock_acquired_at
                if age > self._stale_threshold:
                    # Parse composite key to get project_id and board_id
                    project_id, board_id = key.split(":", 1)

                    self._logger.warning(
                        "Stale lock detected: %s held by %s for %s",
                        key,
                        state.lock_holder,
                        age,
                    )

                    # Emit domain event with lock acquisition time for audit trail
                    stale_event = LockStaleDetectedEvent(
                        type="lock.stale_detected",
                        timestamp=now.isoformat(),
                        source="stale_lock_watchdog",
                        project_id=project_id,
                        board_id=board_id,
                        work_item_id=state.lock_holder,
                        lock_acquired_at=state.lock_acquired_at.isoformat(),
                    )
                    self._event_emitter.emit(stale_event)

                    # Force-release the stale lock
                    try:
                        await self._lock_service.release_lock(
                            project_id,
                            board_id,
                            state.lock_holder,
                        )
                        self._logger.info(
                            "Stale lock force-released: %s (was held for %s)",
                            key,
                            age,
                        )
                    except Exception:
                        self._logger.error(
                            "Failed to force-release stale lock %s",
                            key,
                            exc_info=True,
                        )


class ExecutionTimeoutWatchdog:
    """Proactively detects and cancels executions that exceed their timeout.

    On each clock tick interval, scans all active agent executions and checks
    if any have exceeded their configured timeout. For timed-out executions:
    1. Emits ExecutionTimedOutEvent for audit trail
    2. Cancels the asyncio task to stop stuck execution

    This extends the reactive timeout detection (legacy ExecutionTimeout event)
    with proactive monitoring in simulation environments.

    Design:
    - Clock-driven: Calls clock.schedule_callback() to self-reschedule
    - Time-aware: Uses clock.now() exclusively for comparisons
    - Fail-safe: Errors logged but don't stop future checks
    - Event-driven: Emits ExecutionTimedOutEvent for audit trail
    - Cancellation: Calls task.cancel() to stop stuck execution

    Attributes:
        _executor: ExecutionServiceAgentExecutor to scan active executions
        _event_emitter: IEventEmitter for domain event publication
        _clock: SimulationClock for time access and callback scheduling
        _check_interval: Frequency (timedelta) of timeout checks
    """

    def __init__(
        self,
        executor: "ExecutionServiceAgentExecutor",
        event_emitter: IEventEmitter,
        clock: SimulationClock,
        check_interval: timedelta = timedelta(seconds=30),
    ):
        """Initialize execution timeout watchdog.

        Args:
            executor: ExecutionServiceAgentExecutor to monitor
            event_emitter: IEventEmitter for domain event publication
            clock: SimulationClock for time and callback scheduling
            check_interval: Frequency of checks (default 30 seconds simulated time)
        """
        self._executor = executor
        self._event_emitter = event_emitter
        self._clock = clock
        self._check_interval = check_interval
        self._logger = logger

    def start(self) -> None:
        """Schedule first watchdog check.

        Registers a callback with the clock to run _tick() after _check_interval.
        This callback will reschedule itself, creating a continuous background check.

        Call this after the simulation engine and adapters are initialized.
        """
        self._clock.schedule_callback(self._tick, after_delta=self._check_interval)
        self._logger.info(
            "ExecutionTimeoutWatchdog started: checking every %s simulated seconds",
            self._check_interval.total_seconds(),
        )

    async def _tick(self, scheduled_time: datetime) -> None:
        """Check for timed-out executions, always reschedule.

        This is the main watchdog loop callback. It:
        1. Calls _check_timeouts() to scan and cancel timed-out executions
        2. Logs any errors with exc_info=True
        3. Always reschedules itself (even on error) via clock.schedule_callback()

        The always-reschedule pattern ensures that a single error doesn't stop
        the watchdog from future checks. This is critical for production-like robustness.

        Args:
            scheduled_time: The time when this callback was triggered (provided by clock)
        """
        try:
            await self._check_timeouts()
        except Exception:
            self._logger.error(
                "ExecutionTimeoutWatchdog check failed, will retry next interval",
                exc_info=True,
            )
        finally:
            # Always reschedule, even on error - fail-safe pattern
            self._clock.schedule_callback(self._tick, after_delta=self._check_interval)

    async def _check_timeouts(self) -> None:
        """Scan all active executions and cancel any that are timed out.

        Gets all current active executions from the executor, checks each execution's
        age against its timeout threshold, and for timed-out ones:
        1. Emits ExecutionTimedOutEvent with timestamp for audit trail
        2. Cancels the task via task.cancel()
        3. Logs the timeout at warning level

        Uses clock.now() exclusively for time comparisons, ensuring the watchdog
        pauses when auto-advance pauses and works with simulated time.

        Raises:
            Any exception from event emission or task cancellation (caught and logged by _tick())
        """
        now = self._clock.now()
        active_executions = self._executor.get_active_executions()

        for exec_info in active_executions:
            deadline = exec_info.started_at + timedelta(seconds=exec_info.timeout_seconds)
            if now > deadline:
                age = now - exec_info.started_at

                self._logger.warning(
                    "Execution %s timed out (started: %s, timeout: %ds, age: %s)",
                    exec_info.execution_id,
                    exec_info.started_at,
                    exec_info.timeout_seconds,
                    age,
                )

                # Emit domain event with timeout details for audit trail
                timeout_event = ExecutionTimedOutEvent(
                    type="execution.timed_out",
                    timestamp=now.isoformat(),
                    source="execution_timeout_watchdog",
                    execution_id=exec_info.execution_id,
                    work_item_id=exec_info.work_item_id,
                    timeout_seconds=exec_info.timeout_seconds,
                    started_at=exec_info.started_at.isoformat(),
                )
                self._event_emitter.emit(timeout_event)

                # Cancel the stuck task
                try:
                    exec_info.task.cancel()
                    self._logger.info(
                        "Execution %s task cancelled (was running for %s)",
                        exec_info.execution_id,
                        age,
                    )
                except Exception:
                    self._logger.error(
                        "Failed to cancel timed-out execution %s",
                        exec_info.execution_id,
                        exc_info=True,
                    )
