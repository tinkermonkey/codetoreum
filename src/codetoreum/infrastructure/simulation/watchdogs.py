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

from codetoreum.domain.events.board_events import ColumnSLAExceededEvent
from codetoreum.domain.events.execution_events import ExecutionTimedOutEvent
from codetoreum.domain.events.lock_events import StaleLockDetectedEvent
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.output.board_service import IBoardService
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.pipeline_lock_service import IPipelineLockService
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService

if TYPE_CHECKING:
    from codetoreum.adapters.testing.execution_service_agent_executor import (
        ExecutionServiceAgentExecutor,
    )

logger = logging.getLogger(__name__)


class StaleLockWatchdog:
    """Proactively detects and force-releases stale pipeline locks.

    On each clock tick interval, scans all held pipeline locks and emits
    StaleLockDetectedEvent for locks older than the stale threshold.
    Automatically force-releases stale locks via the lock service.

    This extends the existing reactive stale lock detection (which only fires
    on new lock acquisition) into a proactive, clock-driven check.

    Design:
    - Clock-driven: Calls clock.schedule_callback() to self-reschedule
    - Time-aware: Uses clock.now() exclusively for comparisons
    - Fail-safe: Errors logged but don't stop future checks
    - Event-driven: Emits StaleLockDetectedEvent for audit trail
    - Force-release: Calls lock_service.release_lock() to clean up
    - Deduplication: Tracks detected stale locks to emit events once per recovery

    Deduplication Design:
    Prevents duplicate StaleLockDetectedEvent emissions for the same lock.
    When a lock is detected as stale and recovered, it's marked in
    _recovered_locks. If release_lock() fails (transient error), the event
    is still emitted but the lock isn't recovered - the next tick will retry
    and re-emit. Once successfully recovered, future ticks skip the lock
    until it's re-acquired (cleared when a new lock.acquired event is
    observed via the on_lock_acquired() event handler, which must be
    registered with the event bus in bootstrap.py).

    Attributes:
        _lock_service: IPipelineLockService for lock iteration and release
        _event_emitter: IEventEmitter for domain event publication
        _clock: SimulationClock for time access and callback scheduling
        _stale_threshold: Age (timedelta) beyond which locks are stale
        _check_interval: Frequency (timedelta) of stale lock checks
        _recovered_locks: Set of "project_id:board_id" keys already recovered
        _stopped: Flag to prevent future checks
    """

    def __init__(
        self,
        lock_service: IPipelineLockService,
        event_emitter: IEventEmitter,
        clock: SimulationClock,
        stale_threshold_seconds: int = 7200,
        check_interval: timedelta = timedelta(seconds=60),
    ):
        """Initialize stale lock watchdog.

        Args:
            lock_service: IPipelineLockService instance for lock access
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
        self._recovered_locks: set[str] = set()
        self._stopped = False

    def start(self) -> None:
        """Schedule first watchdog check.

        Registers a callback with the clock to run _tick() after _check_interval.
        This callback will reschedule itself, creating a continuous background check.

        Call this after the simulation engine and adapters are initialized.
        """
        self._stopped = False
        self._clock.schedule_callback(self._tick, after_delta=self._check_interval)
        self._logger.info(
            "StaleLockWatchdog started: checking every %s simulated seconds",
            self._check_interval.total_seconds(),
        )

    def stop(self) -> None:
        """Stop the watchdog.

        Sets a flag to prevent future checks. The scheduled callback will
        still fire, but will return early if the stop flag is set.
        """
        self._stopped = True
        self._recovered_locks.clear()
        self._logger.info("StaleLockWatchdog stopped")

    def on_lock_acquired(self, event: object) -> None:
        """Handle lock acquired event to clear deduplication tracking.

        When a lock is newly acquired, remove it from _recovered_locks to allow
        re-detection if it becomes stale in the future. This resets the
        deduplication state when a previously-recovered lock is re-acquired.

        Args:
            event: LockAcquiredEvent (dynamically typed to support event bus)
        """
        # Extract key from event attributes
        try:
            project_id = getattr(event, "project_id", None)
            board_id = getattr(event, "board_id", None)
            if project_id and board_id:
                key = f"{project_id}:{board_id}"
                self._recovered_locks.discard(key)
                self._logger.debug(
                    "Cleared deduplication tracking for lock %s on new acquisition",
                    key,
                )
        except Exception:
            self._logger.error(
                "Failed to process lock acquired event in watchdog",
                exc_info=True,
            )

    async def _tick(self, scheduled_time: datetime) -> None:
        """Check for stale locks, always reschedule.

        This is the main watchdog loop callback. It:
        1. Checks if watchdog has been stopped (early return if so)
        2. Calls _check_stale_locks() to scan and release stale locks
        3. Logs any errors with exc_info=True
        4. Always reschedules itself (even on error) via clock.schedule_callback()

        The always-reschedule pattern ensures that a single error doesn't stop
        the watchdog from future checks. This is critical for production-like robustness.

        Args:
            scheduled_time: The time when this callback was triggered (provided by clock)
        """
        if self._stopped:
            return

        try:
            await self._check_stale_locks()
        except Exception:
            self._logger.error(
                "StaleLockWatchdog check failed, will retry next interval",
                exc_info=True,
            )
        finally:
            # Always reschedule if not stopped
            if not self._stopped:
                self._clock.schedule_callback(self._tick, after_delta=self._check_interval)

    async def _check_stale_locks(self) -> None:
        """Scan all locks and force-release any that are stale.

        Gets all current lock states from the lock service, checks each held lock's age
        against the stale threshold, and for stale ones:
        1. Emits StaleLockDetectedEvent with timestamp for audit trail
        2. Force-releases the lock via lock_service.release_lock()
        3. Tracks detection to avoid duplicate event emission
        4. Logs the stale lock at warning level

        Uses clock.now() exclusively for time comparisons, ensuring the watchdog
        pauses when auto-advance pauses and works with simulated time.

        Deduplication: If emit() succeeds but release_lock() fails (transient error),
        the event was emitted but the lock wasn't recovered. The lock will be
        detected again on the next tick and will re-emit. Once successfully released,
        the key is added to _recovered_locks and future ticks skip it.

        Raises:
            Any exception from event emission or lock release (caught and logged by _tick())
        """
        now = self._clock.now()

        # Get all lock states from the port interface method
        all_states = self._lock_service.get_all_lock_states()

        for key, state in all_states.items():
            # Only check locks that are currently held
            if state.lock_holder and state.lock_acquired_at:
                age = now - state.lock_acquired_at
                if age > self._stale_threshold:
                    # Skip if already recovered
                    if key in self._recovered_locks:
                        continue

                    # Parse composite key to get project_id and board_id
                    project_id, board_id = key.split(":", 1)

                    self._logger.warning(
                        "Stale lock detected: %s held by %s for %s",
                        key,
                        state.lock_holder,
                        age,
                    )

                    # Emit domain event with lock acquisition time for audit trail
                    stale_event = StaleLockDetectedEvent(
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
                        # Mark as recovered only after successful release
                        self._recovered_locks.add(key)
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
    - Per-item error handling: Each execution processed independently
    - Event-driven: Emits ExecutionTimedOutEvent for audit trail
    - Cancellation: Calls task.cancel() to stop stuck execution

    Per-Item Error Handling:
    If event emission fails for one execution, the exception is logged and
    that execution is skipped, but subsequent executions continue to be
    processed and cancelled. This prevents a single emit() failure from
    preventing cancellation of all remaining timed-out executions.

    Attributes:
        _executor: ExecutionServiceAgentExecutor to scan active executions
        _event_emitter: IEventEmitter for domain event publication
        _clock: SimulationClock for time access and callback scheduling
        _check_interval: Frequency (timedelta) of timeout checks
        _stopped: Flag to stop the watchdog
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
        self._stopped = False

    def start(self) -> None:
        """Schedule first watchdog check.

        Registers a callback with the clock to run _tick() after _check_interval.
        This callback will reschedule itself, creating a continuous background check.

        Call this after the simulation engine and adapters are initialized.
        """
        self._stopped = False
        self._clock.schedule_callback(self._tick, after_delta=self._check_interval)
        self._logger.info(
            "ExecutionTimeoutWatchdog started: checking every %s simulated seconds",
            self._check_interval.total_seconds(),
        )

    def stop(self) -> None:
        """Stop the watchdog.

        Sets a flag to prevent future checks. The scheduled callback will
        still fire, but will return early if the stop flag is set.
        """
        self._stopped = True
        self._logger.info("ExecutionTimeoutWatchdog stopped")

    async def _tick(self, scheduled_time: datetime) -> None:
        """Check for timed-out executions, always reschedule.

        This is the main watchdog loop callback. It:
        1. Checks if watchdog has been stopped (early return if so)
        2. Calls _check_timeouts() to scan and cancel timed-out executions
        3. Logs any errors with exc_info=True
        4. Always reschedules itself (even on error) via clock.schedule_callback()

        The always-reschedule pattern ensures that a single error doesn't stop
        the watchdog from future checks. This is critical for production-like robustness.

        Args:
            scheduled_time: The time when this callback was triggered (provided by clock)
        """
        if self._stopped:
            return

        try:
            await self._check_timeouts()
        except Exception:
            self._logger.error(
                "ExecutionTimeoutWatchdog check failed, will retry next interval",
                exc_info=True,
            )
        finally:
            # Always reschedule if not stopped
            if not self._stopped:
                self._clock.schedule_callback(self._tick, after_delta=self._check_interval)

    async def _check_timeouts(self) -> None:
        """Scan all active executions and cancel any that are timed out.

        Gets all current active executions from the executor, checks each execution's
        age against its timeout threshold, and for timed-out ones:
        1. Emits ExecutionTimedOutEvent with timestamp for audit trail
        2. Cancels the task via task.cancel()
        3. Logs the timeout at warning level

        Per-item error handling: Each execution is processed independently.
        If event emission fails for one execution, that execution is logged and
        skipped, but cancellation and subsequent executions continue.

        Uses clock.now() exclusively for time comparisons, ensuring the watchdog
        pauses when auto-advance pauses and works with simulated time.

        Raises:
            Never directly raised - all per-item exceptions are caught and logged
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
                # Wrapped in try/except to not block subsequent executions
                try:
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
                except Exception:
                    self._logger.error(
                        "Failed to emit timeout event for execution %s",
                        exec_info.execution_id,
                        exc_info=True,
                    )

                # Cancel the stuck task (separate try/except)
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


class SLAExpiryWatchdog:
    """Proactively detects work items that exceed their column's SLA threshold.

    On each clock tick interval, scans all work items on all boards and checks
    if any have remained in their current column longer than the column's configured
    SLA threshold. For items exceeding SLA:
    1. Emits ColumnSLAExceededEvent for audit trail
    2. Records the detection to prevent duplicate events

    This watchdog enables SLA-driven monitoring and escalation workflows. Once
    detected, the system can decide on escalation actions (notify, reassign, etc.)
    based on the ColumnSLAExceededEvent.

    Design:
    - Clock-driven: Calls clock.schedule_callback() to self-reschedule
    - Time-aware: Uses clock.now() exclusively for comparisons
    - Fail-safe: Errors logged but don't stop future checks
    - Event-driven: Emits ColumnSLAExceededEvent for audit trail
    - Deduplication: Tracks detected items to emit once per SLA expiry per column
    - Cleanup: Automatically removes items from detection when they leave column

    Deduplication Design:
    The detection key includes work_item_id, project_id, board_id, AND column_name.
    This ensures that if a work item exceeds SLA in one column, then moves to
    another column and exceeds SLA there, both violations are reported (different
    keys). Once an item leaves a column (column_name changes), it's automatically
    removed from _detected_items during the next scan.

    Attributes:
        _board_service: IBoardService for work item and column querying
        _workflow_config_service: IWorkflowConfigService for SLA configuration
        _event_emitter: IEventEmitter for domain event publication
        _clock: SimulationClock for time access and callback scheduling
        _check_interval: Frequency (timedelta) of SLA checks
        _detected_items: Set of (work_item_id, project_id, board_id, column_name) tuples
                        tracking which items have already been reported per column
        _stopped: Flag to stop the watchdog
    """

    def __init__(
        self,
        board_service: IBoardService,
        workflow_config_service: IWorkflowConfigService,
        event_emitter: IEventEmitter,
        clock: SimulationClock,
        check_interval: timedelta = timedelta(seconds=60),
    ):
        """Initialize SLA expiry watchdog.

        Args:
            board_service: IBoardService for work item queries
            workflow_config_service: IWorkflowConfigService for SLA config
            event_emitter: IEventEmitter for domain event publication
            clock: SimulationClock for time and callback scheduling
            check_interval: Frequency of checks (default 60 seconds simulated time)
        """
        self._board_service = board_service
        self._workflow_config_service = workflow_config_service
        self._event_emitter = event_emitter
        self._clock = clock
        self._check_interval = check_interval
        self._logger = logger
        # Track (work_item_id, project_id, board_id, column_name) to detect SLA expiry once per column
        self._detected_items: set[tuple[str, str, str, str]] = set()
        self._stopped = False

    def start(self) -> None:
        """Schedule first watchdog check.

        Registers a callback with the clock to run _tick() after _check_interval.
        This callback will reschedule itself, creating a continuous background check.

        Call this after the simulation engine and adapters are initialized.
        """
        self._stopped = False
        self._clock.schedule_callback(self._tick, after_delta=self._check_interval)
        self._logger.info(
            "SLAExpiryWatchdog started: checking every %s simulated seconds",
            self._check_interval.total_seconds(),
        )

    def stop(self) -> None:
        """Stop the watchdog.

        Sets a flag to prevent future checks. The scheduled callback will
        still fire, but will return early if the stop flag is set.
        Clears all detected items to reset tracking on next start.
        """
        self._stopped = True
        self._detected_items.clear()
        self._logger.info("SLAExpiryWatchdog stopped")

    async def _tick(self, scheduled_time: datetime) -> None:
        """Check for SLA-exceeded work items, always reschedule.

        This is the main watchdog loop callback. It:
        1. Checks if watchdog has been stopped (early return if so)
        2. Calls _check_sla_expiry() to scan items and emit events
        3. Logs any errors with exc_info=True
        4. Always reschedules itself (even on error) via clock.schedule_callback()

        The always-reschedule pattern ensures that a single error doesn't stop
        the watchdog from future checks. This is critical for production-like robustness.

        Args:
            scheduled_time: The time when this callback was triggered (provided by clock)
        """
        if self._stopped:
            return

        try:
            await self._check_sla_expiry()
        except Exception:
            self._logger.error(
                "SLAExpiryWatchdog check failed, will retry next interval",
                exc_info=True,
            )
        finally:
            # Always reschedule if not stopped
            if not self._stopped:
                self._clock.schedule_callback(self._tick, after_delta=self._check_interval)

    async def _check_sla_expiry(self) -> None:
        """Scan all work items and emit events for those exceeding SLA.

        Retrieves all boards and work items, checks each item's time in column
        against the column's SLA configuration, and for items exceeding threshold:
        1. Emits ColumnSLAExceededEvent with timestamp and SLA details
        2. Records detection to prevent duplicate event emission per column
        3. Logs the SLA expiry at warning level
        4. Cleans up detections for items that have moved to different columns

        Deduplication Key (work_item_id, project_id, board_id, column_name):
        Includes column_name to distinguish SLA violations in different columns.
        If a work item exceeds SLA in "In Progress" then moves to "Review" and
        exceeds SLA there, both violations are reported (different keys).

        Cleanup: Items that have moved to a different column are automatically
        removed from _detected_items, allowing re-detection if they exceed SLA
        in the new column.

        Uses clock.now() exclusively for time comparisons, ensuring the watchdog
        pauses when auto-advance pauses and works with simulated time.

        Raises:
            Any exception from board service or event emission (caught and logged by _tick())
        """
        now = self._clock.now()

        # Get all boards from board service
        try:
            all_boards = await self._board_service.get_all_boards()
        except Exception:
            self._logger.error(
                "Failed to retrieve boards for SLA checking",
                exc_info=True,
            )
            return

        # Track all currently-detected items on this scan pass to identify moved items
        current_items: set[tuple[str, str, str, str]] = set()

        for board in all_boards:
            # Get workflow template for this board to check SLA config
            try:
                template = await self._workflow_config_service.get_board_workflow_template(board.id)
            except Exception:
                self._logger.error(
                    "Failed to retrieve workflow template for board %s",
                    board.id,
                    exc_info=True,
                )
                continue

            if not template:
                continue

            # Get all work items on board
            try:
                items = await self._board_service.get_board_items(board.project_id, board.id)
            except Exception:
                self._logger.error(
                    "Failed to retrieve items for board %s",
                    board.id,
                    exc_info=True,
                )
                continue

            # Check each item's time in column against SLA
            for item in items:
                if not item.column_name or not item.entered_column_at:
                    # Item not yet placed in column or no entry time
                    continue

                # Get column configuration
                column_config = template.get_column_config(item.column_name)
                if not column_config or not column_config.sla_seconds:
                    # Column has no SLA configured
                    continue

                # Check if item exceeds SLA
                elapsed = now - item.entered_column_at
                elapsed_seconds = int(elapsed.total_seconds())
                sla_seconds = column_config.sla_seconds

                if elapsed_seconds > sla_seconds:
                    # Item has exceeded SLA threshold
                    detection_key = (item.work_item_id, board.project_id, board.id, item.column_name)
                    current_items.add(detection_key)

                    # Emit only once per item per column per SLA expiry
                    if detection_key not in self._detected_items:
                        self._detected_items.add(detection_key)

                        self._logger.warning(
                            "SLA exceeded: work item %s in column '%s' (elapsed: %ds, threshold: %ds)",
                            item.work_item_id,
                            item.column_name,
                            elapsed_seconds,
                            sla_seconds,
                        )

                        # Emit domain event for audit trail
                        sla_event = ColumnSLAExceededEvent(
                            type="column.sla_exceeded",
                            timestamp=now.isoformat(),
                            source="sla_expiry_watchdog",
                            work_item_id=item.work_item_id,
                            project_id=board.project_id,
                            board_id=board.id,
                            column_name=item.column_name,
                            elapsed_seconds=elapsed_seconds,
                            sla_threshold_seconds=sla_seconds,
                            entered_at=item.entered_column_at.isoformat(),
                        )
                        self._event_emitter.emit(sla_event)

        # Clean up detections for items that have moved to a different column.
        # Unconditionally remove any key in moved_items since it's no longer detected
        # in the current scan. This prevents memory leak of stale detection keys.
        moved_items = self._detected_items - current_items
        if moved_items:
            for item_key in moved_items:
                self._detected_items.discard(item_key)
                work_item_id = item_key[0]
                column_name = item_key[3]
                self._logger.debug(
                    "Cleaned up SLA detection for work item %s (no longer in column '%s')",
                    work_item_id,
                    column_name,
                )
