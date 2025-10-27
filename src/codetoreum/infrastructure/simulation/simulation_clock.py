"""Simulation clock for deterministic time manipulation in tests."""

import asyncio
import threading
import traceback
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional, Tuple, Union


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
            raise ValueError("Speed multiplier must be positive")

        self._speed_multiplier = speed_multiplier
        self._auto_advance = auto_advance

        # Current simulated time
        self._current_time: datetime = datetime.now(timezone.utc)

        # Callbacks scheduled for specific times
        self._scheduled_callbacks: List[Tuple[datetime, Callable]] = []

        # Thread safety
        self._lock = threading.RLock()

        # Auto-advance task
        self._auto_advance_task: Optional[asyncio.Task] = None
        self._running = False

    def start_at(self, start_time: datetime) -> None:
        """
        Set the starting time for simulation.

        Args:
            start_time: Starting datetime (will be converted to UTC)
        """
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        elif start_time.tzinfo != timezone.utc:
            start_time = start_time.astimezone(timezone.utc)

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
            raise ValueError("Cannot advance time backwards")

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
            target_time = target_time.replace(tzinfo=timezone.utc)
        elif target_time.tzinfo != timezone.utc:
            target_time = target_time.astimezone(timezone.utc)

        with self._lock:
            if target_time < self._current_time:
                raise ValueError("Cannot advance time backwards")

            delta = target_time - self._current_time

        await self.advance(delta)

    async def _advance_to(self, target_time: datetime) -> None:
        """
        Internal method to advance to a specific time and trigger callbacks.

        Args:
            target_time: Target datetime
        """
        with self._lock:
            old_time = self._current_time
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
                print(f"Error in scheduled {callback_type} callback: {e}")
                print(traceback.format_exc())

    def schedule_callback(
        self,
        callback: Callable,
        at_time: Optional[datetime] = None,
        after_delta: Optional[timedelta] = None,
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
            raise ValueError("Must provide exactly one of at_time or after_delta")

        with self._lock:
            if after_delta is not None:
                trigger_time = self._current_time + after_delta
            else:
                trigger_time = at_time
                if trigger_time.tzinfo is None:
                    trigger_time = trigger_time.replace(tzinfo=timezone.utc)
                elif trigger_time.tzinfo != timezone.utc:
                    trigger_time = trigger_time.astimezone(timezone.utc)

            self._scheduled_callbacks.append((trigger_time, callback))
            self._scheduled_callbacks.sort(key=lambda x: x[0])

    def get_scheduled_callbacks(self) -> List[Tuple[datetime, Callable]]:
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
            raise ValueError("Speed multiplier must be positive")

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
                print(f"Error in auto-advance loop: {e}")

    def reset(self) -> None:
        """Reset clock to current real time and clear all callbacks."""
        with self._lock:
            self._current_time = datetime.now(timezone.utc)
            self._scheduled_callbacks.clear()

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"SimulationClock(current_time={self._current_time.isoformat()}, "
            f"speed={self._speed_multiplier}x)"
        )


class RealTimeClock:
    """
    Real-time clock adapter that matches the SimulationClock interface.

    This is used in production to provide the same interface as SimulationClock
    but using actual system time.
    """

    def now(self) -> datetime:
        """
        Get current real time.

        Returns:
            Current datetime in UTC
        """
        return datetime.now(timezone.utc)

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
_global_clock: Optional[Union[SimulationClock, RealTimeClock]] = None


def get_clock() -> Union[SimulationClock, RealTimeClock]:
    """
    Get the global clock instance.

    Returns:
        Global clock (SimulationClock or RealTimeClock)
    """
    global _global_clock
    if _global_clock is None:
        _global_clock = RealTimeClock()
    return _global_clock


def set_clock(clock: Union[SimulationClock, RealTimeClock]) -> None:
    """
    Set the global clock instance.

    Args:
        clock: Clock instance to use globally
    """
    global _global_clock
    _global_clock = clock


def reset_clock() -> None:
    """Reset the global clock to real time."""
    global _global_clock
    _global_clock = RealTimeClock()
