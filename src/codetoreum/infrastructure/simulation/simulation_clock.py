"""Simulation clock for deterministic time manipulation in tests."""

import asyncio
import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class ClockProtocol(Protocol):
    """
    Formal interface for clock implementations (Protocol).

    Defines the minimal contract that all clock implementations must satisfy for
    general time-related operations. This protocol enables type-safe polymorphism
    between RealTimeClock and SimulationClock without relying on union types.

    The protocol defines only operations that are meaningful in both real and
    simulated time contexts. Simulation-specific operations (like advance(),
    schedule_callback(), etc.) are not included in this protocol and require
    using SimulationClock directly.

    Implementations:
    - RealTimeClock: Uses system time for production
    - SimulationClock: Uses virtual time for deterministic testing

    Usage:
        async def wait_for_completion(clock: ClockProtocol, timeout_seconds: float) -> bool:
            '''Wait for an async operation using either real or simulated time.'''
            start = clock.now()
            await clock.sleep(timeout_seconds)
            return (clock.now() - start).total_seconds() >= timeout_seconds

    Migration Guide:
    When updating code to use ClockProtocol, check which clock methods are called:
    - If code only calls now(), sleep(), or wait_for(): Use ClockProtocol
    - If code calls advance(), schedule_callback(), or other simulation methods: Use SimulationClock
    This distinction ensures components remain portable across real and simulated time contexts.
    """

    def now(self) -> datetime:
        """
        Get current time (real or simulated).

        Returns:
            Current datetime in UTC
        """
        ...

    async def sleep(self, seconds: float) -> None:
        """
        Sleep for a number of seconds (real or simulated time).

        Args:
            seconds: Number of seconds to sleep
        """
        ...

    async def wait_for(self, delta: timedelta) -> None:
        """
        Wait for a time delta (real or simulated time).

        Args:
            delta: Amount of time to wait
        """
        ...


class SimulationClock:
    """
    Simulated clock for deterministic time in tests.

    Allows fast-forwarding time, scheduling callbacks, and manipulating
    the current time for testing time-dependent behavior.

    This enables simulation tests to run 10-100x faster than real time
    by advancing the clock programmatically.

    Thread-safe for concurrent test execution.

    Example:
        >>> clock = SimulationClock(speed_multiplier=10.0)
        >>> clock.start_at(datetime(2025, 1, 1, 12, 0, 0))
        >>> await clock.advance(timedelta(hours=1))  # Advances in seconds
        >>> clock.now()  # Returns 2025-01-01 13:00:00
    """

    def __init__(
        self,
        speed_multiplier: float = 1.0,
        auto_advance: bool = False,
    ):
        """
        Initialize simulation clock.

        Args:
            speed_multiplier: How much faster than real time (1.0 = real time)
            auto_advance: If True, clock advances automatically in real time

        Raises:
            ValueError: If speed_multiplier is <= 0
        """
        if speed_multiplier <= 0:
            message = "Speed multiplier must be positive"
            raise ValueError(message)

        self._speed_multiplier = speed_multiplier
        self._auto_advance = auto_advance

        # Current simulated time
        self._current_time: datetime = datetime.now(UTC)

        # Callbacks scheduled for specific times
        self._scheduled_callbacks: list[tuple[datetime, Callable]] = []

        # Thread safety
        self._lock = threading.RLock()

        # Auto-advance task
        self._auto_advance_task: asyncio.Task | None = None
        self._running = False

    def start_at(self, start_time: datetime) -> None:
        """
        Set the starting time for simulation.

        Args:
            start_time: Starting datetime (will be converted to UTC)
        """
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=UTC)
        elif start_time.tzinfo != UTC:
            start_time = start_time.astimezone(UTC)

        with self._lock:
            self._current_time = start_time

    def now(self) -> datetime:
        """
        Get current simulated time.

        Returns:
            Current datetime in UTC
        """
        with self._lock:
            return self._current_time

    async def advance(self, delta: timedelta) -> None:
        """
        Advance the clock by a time delta.

        This is the primary method for fast-forwarding time in simulations.
        The actual wall-clock time taken is: delta / speed_multiplier

        Args:
            delta: Amount of time to advance

        Raises:
            ValueError: If delta is negative
        """
        if delta.total_seconds() < 0:
            message = "Cannot advance time backwards"
            raise ValueError(message)

        # Calculate real-world delay
        real_delay_seconds = delta.total_seconds() / self._speed_multiplier

        # Advance time
        with self._lock:
            target_time = self._current_time + delta

        # Sleep for the real-world delay (simulates time passing)
        if real_delay_seconds > 0:
            await asyncio.sleep(real_delay_seconds)

        # Update current time and trigger callbacks
        await self._advance_to(target_time)

    async def advance_to(self, target_time: datetime) -> None:
        """
        Advance the clock to a specific time.

        Args:
            target_time: Target datetime

        Raises:
            ValueError: If target_time is before current time
        """
        if target_time.tzinfo is None:
            target_time = target_time.replace(tzinfo=UTC)
        elif target_time.tzinfo != UTC:
            target_time = target_time.astimezone(UTC)

        with self._lock:
            if target_time < self._current_time:
                message = "Cannot advance time backwards"
                raise ValueError(message)

            delta = target_time - self._current_time

        await self.advance(delta)

    async def _advance_to(self, target_time: datetime) -> None:
        """
        Internal method to advance to a specific time and trigger callbacks.

        Args:
            target_time: Target datetime
        """
        with self._lock:
            self._current_time = target_time

            # Find callbacks to trigger
            callbacks_to_trigger = []
            remaining_callbacks = []

            for scheduled_time, callback in self._scheduled_callbacks:
                if scheduled_time <= target_time:
                    callbacks_to_trigger.append((scheduled_time, callback))
                else:
                    remaining_callbacks.append((scheduled_time, callback))

            self._scheduled_callbacks = remaining_callbacks

        # Trigger callbacks outside the lock
        for scheduled_time, callback in sorted(callbacks_to_trigger, key=lambda x: x[0]):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(scheduled_time)
                else:
                    callback(scheduled_time)
            except Exception as e:
                # Log but don't stop advancing - distinguish between sync and async errors
                callback_type = "async" if asyncio.iscoroutinefunction(callback) else "sync"
                logger.error(
                    f"Error in scheduled {callback_type} callback at {scheduled_time}: {e}",
                    exc_info=True,
                )

    def schedule_callback(
        self,
        callback: Callable,
        at_time: datetime | None = None,
        after_delta: timedelta | None = None,
    ) -> None:
        """
        Schedule a callback to be triggered at a specific time.

        Args:
            callback: Function to call (can be sync or async)
            at_time: Absolute time to trigger (mutually exclusive with after_delta)
            after_delta: Relative time from now (mutually exclusive with at_time)

        Raises:
            ValueError: If neither or both time parameters are provided
        """
        if (at_time is None) == (after_delta is None):
            message = "Must provide exactly one of at_time or after_delta"
            raise ValueError(message)

        with self._lock:
            if after_delta is not None:
                trigger_time = self._current_time + after_delta
            else:
                trigger_time = at_time
                if trigger_time.tzinfo is None:
                    trigger_time = trigger_time.replace(tzinfo=UTC)
                elif trigger_time.tzinfo != UTC:
                    trigger_time = trigger_time.astimezone(UTC)

            self._scheduled_callbacks.append((trigger_time, callback))
            self._scheduled_callbacks.sort(key=lambda x: x[0])

    def get_scheduled_callbacks(self) -> list[tuple[datetime, Callable]]:
        """
        Get all scheduled callbacks.

        Returns:
            List of (datetime, callback) tuples
        """
        with self._lock:
            return list(self._scheduled_callbacks)

    def clear_scheduled_callbacks(self) -> None:
        """Clear all scheduled callbacks."""
        with self._lock:
            self._scheduled_callbacks.clear()

    async def wait_for(self, delta: timedelta) -> None:
        """
        Wait for a time delta (in simulated time).

        This is similar to asyncio.sleep but uses simulated time.

        Args:
            delta: Amount of time to wait
        """
        await self.advance(delta)

    async def sleep(self, seconds: float) -> None:
        """
        Sleep for a number of seconds (in simulated time).

        Args:
            seconds: Number of seconds to sleep
        """
        await self.advance(timedelta(seconds=seconds))

    def set_speed_multiplier(self, multiplier: float) -> None:
        """
        Change the speed multiplier.

        Args:
            multiplier: New speed multiplier (must be > 0)

        Raises:
            ValueError: If multiplier is <= 0
        """
        if multiplier <= 0:
            message = "Speed multiplier must be positive"
            raise ValueError(message)

        with self._lock:
            self._speed_multiplier = multiplier

    def get_speed_multiplier(self) -> float:
        """
        Get current speed multiplier.

        Returns:
            Current speed multiplier
        """
        with self._lock:
            return self._speed_multiplier

    async def start_auto_advance(self) -> None:
        """
        Start automatic clock advancement.

        When auto-advance is enabled, the clock advances automatically
        in real time multiplied by the speed multiplier.
        """
        with self._lock:
            if self._running:
                return

            self._running = True
            self._auto_advance_task = asyncio.create_task(self._auto_advance_loop())

    async def stop_auto_advance(self) -> None:
        """Stop automatic clock advancement."""
        with self._lock:
            self._running = False

            if self._auto_advance_task:
                self._auto_advance_task.cancel()
                try:
                    await self._auto_advance_task
                except asyncio.CancelledError:
                    pass
                self._auto_advance_task = None

    async def _auto_advance_loop(self) -> None:
        """Internal loop for automatic clock advancement."""
        while self._running:
            try:
                # Advance by 1 second of simulated time every (1 / multiplier) real seconds
                await asyncio.sleep(1.0 / self._speed_multiplier)
                await self._advance_to(self._current_time + timedelta(seconds=1))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in auto-advance loop: {e}", exc_info=True)

    def reset(self) -> None:
        """Reset clock to current real time and clear all callbacks."""
        with self._lock:
            self._current_time = datetime.now(UTC)
            self._scheduled_callbacks.clear()

    def __repr__(self) -> str:
        """String representation."""
        return f"SimulationClock(current_time={self._current_time.isoformat()}, speed={self._speed_multiplier}x)"


class RealTimeClock:
    """
    Real-time clock adapter that implements the ClockProtocol.

    This is used in production to provide the same interface as defined by
    ClockProtocol but using actual system time instead of simulated time.
    """

    def now(self) -> datetime:
        """
        Get current real time.

        Returns:
            Current datetime in UTC
        """
        return datetime.now(UTC)

    async def sleep(self, seconds: float) -> None:
        """
        Sleep for a number of seconds (real time).

        Args:
            seconds: Number of seconds to sleep
        """
        await asyncio.sleep(seconds)

    async def wait_for(self, delta: timedelta) -> None:
        """
        Wait for a time delta (real time).

        Args:
            delta: Amount of time to wait
        """
        await asyncio.sleep(delta.total_seconds())


# Global clock instance that can be swapped for testing
_global_clock: ClockProtocol | None = None


def get_clock() -> ClockProtocol:
    """
    Get the global clock instance.

    Returns:
        Global clock instance (SimulationClock or RealTimeClock)
    """
    global _global_clock
    if _global_clock is None:
        _global_clock = RealTimeClock()
    return _global_clock


def set_clock(clock: ClockProtocol) -> None:
    """
    Set the global clock instance.

    Args:
        clock: Clock instance to use globally (must implement ClockProtocol)
    """
    global _global_clock
    _global_clock = clock


def reset_clock() -> None:
    """Reset the global clock to real time."""
    global _global_clock
    _global_clock = RealTimeClock()
