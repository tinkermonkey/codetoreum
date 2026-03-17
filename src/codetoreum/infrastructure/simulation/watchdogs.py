"""Watchdogs for simulation monitoring and health checks.

Watchdogs are background tasks that periodically scan simulation state and emit
domain events for conditions that need attention (e.g., stale locks).

Design Principles:
- Use clock.now() exclusively for time comparisons (never datetime.now())
- Self-reschedule via clock.schedule_callback() to pause with auto-advance
- Log all errors with exc_info=True but always reschedule (fail-safe)
- Emit immutable domain events for all detections
- Force-release resources when detected stale
"""

import logging
from datetime import datetime, timedelta

from codetoreum.adapters.secondary.in_memory_queue_lock_service import (
    InMemoryLockService,
)
from codetoreum.domain.events.lock_events import LockStaleDetectedEvent
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.output.event_emitter import IEventEmitter

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
                    await self._event_emitter.emit(stale_event)

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
