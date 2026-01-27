"""Performance profiling instrumentation for repair cycle analysis.

Provides detailed performance metrics including:
- Memory usage tracking
- CPU usage monitoring
- Call graph profiling
- Timeline analysis
- Bottleneck identification
"""

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import psutil
import tracemalloc
from codetoreum.infrastructure.error_ids import ErrorRegistry

logger = logging.getLogger(__name__)

__all__ = [
    "ProfileData",
    "RepairCycleProfiler",
    "PerformanceThresholdMonitor",
    "RepairCycleProfilerContext",
    "ThresholdCheckingContext",
]


class ThresholdCheckingContext:
    """Context manager to check performance thresholds on profile completion."""

    def __init__(self, ctx, monitor):
        """Initialize threshold checking context."""
        self.ctx = ctx
        self.monitor = monitor
        self.profile = None

    def __enter__(self):
        """Enter context and get profile."""
        self.profile = self.ctx.__enter__()
        return self.profile

    def __exit__(self, *args):
        """Exit context and check thresholds."""
        result = self.ctx.__exit__(*args)
        if self.profile:
            violations = self.monitor.check_thresholds(self.profile)
            if violations:
                operation = self.profile.operation
                logger.warning(f"Performance threshold violations for {operation}: {violations}")
        return result


@dataclass
class ProfileData:
    """Performance profile data."""

    operation: str
    start_time: float
    end_time: Optional[float] = None
    start_memory_bytes: int = 0
    end_memory_bytes: int = 0
    peak_memory_bytes: int = 0
    cpu_percent: float = 0.0
    exceptions: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        """Get operation duration in seconds."""
        if self.end_time is None:
            return time.time() - self.start_time
        return self.end_time - self.start_time

    @property
    def memory_delta_bytes(self) -> int:
        """Get memory delta in bytes."""
        return self.end_memory_bytes - self.start_memory_bytes

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "operation": self.operation,
            "duration_seconds": round(self.duration_seconds, 3),
            "memory_delta_mb": round(self.memory_delta_bytes / 1024 / 1024, 2),
            "peak_memory_mb": round(self.peak_memory_bytes / 1024 / 1024, 2),
            "cpu_percent": round(self.cpu_percent, 2),
            "exceptions": self.exceptions,
            "metadata": self.metadata,
        }


class RepairCycleProfiler:
    """Performance profiler for repair cycle stages."""

    def __init__(
        self,
        enable_memory_tracking: bool = True,
        enable_cpu_tracking: bool = True,
        max_profiles: int = 1000,
    ):
        """
        Initialize repair cycle profiler.

        Args:
            enable_memory_tracking: Enable memory profiling
            enable_cpu_tracking: Enable CPU profiling
            max_profiles: Maximum number of profiles to keep (prevents memory leaks)
        """
        self.enable_memory_tracking = enable_memory_tracking
        self.enable_cpu_tracking = enable_cpu_tracking
        self.max_profiles = max_profiles
        self._profiles: List[ProfileData] = []
        self._process = psutil.Process()
        self._memory_tracker = None
        self._active_profiles: Dict[str, ProfileData] = {}

        if self.enable_memory_tracking:
            tracemalloc.start()
            self._memory_tracker = True

    @contextmanager
    def profile_operation(
        self,
        operation: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Context manager to profile an operation.

        Args:
            operation: Operation name
            metadata: Optional metadata to attach to profile
        """
        start_time = time.time()
        start_memory = 0
        peak_memory = 0

        if self.enable_memory_tracking:
            tracemalloc.reset_peak()
            start_memory = tracemalloc.get_traced_memory()[0]

        profile = ProfileData(
            operation=operation,
            start_time=start_time,
            start_memory_bytes=start_memory,
            metadata=metadata or {},
        )

        self._active_profiles[operation] = profile

        try:
            yield profile
        except Exception as e:
            profile.exceptions += 1
            logger.error(f"Exception during profiled operation {operation}: {e}", exc_info=True, extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR})
            raise
        finally:
            profile.end_time = time.time()

            if self.enable_memory_tracking:
                end_memory, peak_memory = tracemalloc.get_traced_memory()
                profile.end_memory_bytes = end_memory
                profile.peak_memory_bytes = peak_memory

            if self.enable_cpu_tracking:
                try:
                    profile.cpu_percent = self._process.cpu_percent(interval=0.1)
                except Exception as e:
                    logger.debug(f"Error getting CPU percent: {e}")

            self._profiles.append(profile)

            # Prevent memory leak by maintaining ring buffer
            if len(self._profiles) > self.max_profiles:
                self._profiles.pop(0)

            del self._active_profiles[operation]

            duration = profile.duration_seconds
            memory_delta_mb = profile.memory_delta_bytes / 1024 / 1024
            logger.debug(
                f"Profiled operation {operation}: duration={duration:.3f}s, "
                f"memory_delta={memory_delta_mb:.2f}MB, cpu={profile.cpu_percent:.1f}%"
            )

    def get_profiles(self) -> List[ProfileData]:
        """Get all recorded profiles."""
        return self._profiles.copy()

    def get_profile_summary(self) -> Dict[str, Dict[str, float]]:
        """
        Get summary statistics for all profiles.

        Returns:
            Dict mapping operation to statistics
        """
        summary: Dict[str, Dict[str, Any]] = {}

        for profile in self._profiles:
            if profile.operation not in summary:
                summary[profile.operation] = {
                    "count": 0,
                    "total_duration": 0.0,
                    "min_duration": float("inf"),
                    "max_duration": 0.0,
                    "total_memory_delta": 0,
                    "peak_memory_max": 0,
                    "avg_cpu_percent": 0.0,
                }

            stats = summary[profile.operation]
            stats["count"] += 1
            stats["total_duration"] += profile.duration_seconds
            stats["min_duration"] = min(stats["min_duration"], profile.duration_seconds)
            stats["max_duration"] = max(stats["max_duration"], profile.duration_seconds)
            stats["total_memory_delta"] += profile.memory_delta_bytes
            stats["peak_memory_max"] = max(stats["peak_memory_max"], profile.peak_memory_bytes)

        # Calculate averages
        for op_stats in summary.values():
            if op_stats["count"] > 0:
                op_stats["avg_duration"] = op_stats["total_duration"] / op_stats["count"]
                op_stats["avg_memory_delta_mb"] = op_stats["total_memory_delta"] / 1024 / 1024 / op_stats["count"]
                op_stats["peak_memory_mb"] = op_stats["peak_memory_max"] / 1024 / 1024

        return summary

    def get_slowest_operations(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """
        Get slowest operations.

        Args:
            top_n: Number of top slow operations to return

        Returns:
            List of slowest operations with their profile data
        """
        sorted_profiles = sorted(self._profiles, key=lambda p: p.duration_seconds, reverse=True)
        return [p.to_dict() for p in sorted_profiles[:top_n]]

    def get_heaviest_operations(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """
        Get operations with highest memory delta.

        Args:
            top_n: Number of top heavy operations to return

        Returns:
            List of heaviest operations with their profile data
        """
        if not self.enable_memory_tracking:
            return []

        sorted_profiles = sorted(
            self._profiles,
            key=lambda p: p.memory_delta_bytes,
            reverse=True
        )
        return [p.to_dict() for p in sorted_profiles[:top_n]]

    def get_hottest_operations(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """
        Get operations with highest CPU usage.

        Args:
            top_n: Number of top CPU operations to return

        Returns:
            List of hottest operations with their profile data
        """
        if not self.enable_cpu_tracking:
            return []

        sorted_profiles = sorted(self._profiles, key=lambda p: p.cpu_percent, reverse=True)
        return [p.to_dict() for p in sorted_profiles[:top_n]]

    def reset(self) -> None:
        """Reset profiler."""
        self._profiles.clear()
        self._active_profiles.clear()
        if self.enable_memory_tracking:
            tracemalloc.reset_peak()
        logger.info("Profiler reset")

    def shutdown(self) -> None:
        """Shutdown profiler."""
        if self.enable_memory_tracking:
            tracemalloc.stop()
        logger.debug("Profiler shutdown")


class PerformanceThresholdMonitor:
    """Monitor for performance threshold violations."""

    def __init__(self, thresholds: Optional[Dict[str, Dict[str, float]]] = None):
        """
        Initialize performance threshold monitor.

        Args:
            thresholds: Dict mapping operation to thresholds (duration_seconds, memory_delta_mb, etc.).
                       If None, uses default thresholds.
                       Example: {"test_execution": {"duration_seconds": 300.0, "memory_delta_mb": 500.0}}
        """
        self.thresholds = thresholds if thresholds is not None else self._default_thresholds()
        self._violations: List[Dict[str, Any]] = []

    @staticmethod
    def _default_thresholds() -> Dict[str, Dict[str, float]]:
        """Get default performance thresholds."""
        return {
            "test_execution": {
                "duration_seconds": 300.0,  # 5 minutes
                "memory_delta_mb": 500.0,
            },
            "file_fix": {
                "duration_seconds": 120.0,  # 2 minutes
                "memory_delta_mb": 200.0,
            },
            "agent_call": {
                "duration_seconds": 60.0,  # 1 minute
                "memory_delta_mb": 100.0,
            },
            "repair_cycle": {
                "duration_seconds": 600.0,  # 10 minutes
                "memory_delta_mb": 1000.0,
            },
        }

    def check_thresholds(self, profile: ProfileData) -> List[str]:
        """
        Check profile against thresholds.

        Args:
            profile: Profile data to check

        Returns:
            List of threshold violations
        """
        violations = []
        op_thresholds = self.thresholds.get(profile.operation, {})

        if not op_thresholds:
            return violations

        # Check duration
        duration_threshold = op_thresholds.get("duration_seconds")
        if duration_threshold and profile.duration_seconds > duration_threshold:
            violations.append(
                f"Duration threshold exceeded: {profile.duration_seconds:.2f}s > {duration_threshold}s"
            )

        # Check memory delta
        memory_delta_mb = profile.memory_delta_bytes / 1024 / 1024
        memory_threshold = op_thresholds.get("memory_delta_mb")
        if memory_threshold and memory_delta_mb > memory_threshold:
            violations.append(
                f"Memory threshold exceeded: {memory_delta_mb:.2f}MB > {memory_threshold}MB"
            )

        # Check peak memory
        peak_memory_mb = profile.peak_memory_bytes / 1024 / 1024
        peak_threshold = op_thresholds.get("peak_memory_mb")
        if peak_threshold and peak_memory_mb > peak_threshold:
            violations.append(
                f"Peak memory threshold exceeded: {peak_memory_mb:.2f}MB > {peak_threshold}MB"
            )

        if violations:
            self._violations.append({
                "operation": profile.operation,
                "violations": violations,
                "timestamp": datetime.utcnow().isoformat(),
            })

        return violations

    def get_violations(self) -> List[Dict[str, Any]]:
        """Get all threshold violations."""
        return self._violations.copy()

    def reset(self) -> None:
        """Reset violations."""
        self._violations.clear()


class RepairCycleProfilerContext:
    """Convenience context for profiling an entire repair cycle."""

    def __init__(
        self,
        enable_memory_tracking: bool = True,
        enable_cpu_tracking: bool = True,
        threshold_monitoring: bool = True,
        custom_thresholds: Optional[Dict[str, Dict[str, float]]] = None,
        max_profiles: int = 1000,
    ):
        """
        Initialize profiler context.

        Args:
            enable_memory_tracking: Enable memory profiling
            enable_cpu_tracking: Enable CPU profiling
            threshold_monitoring: Enable threshold monitoring
            custom_thresholds: Optional custom performance thresholds
            max_profiles: Maximum number of profiles to keep in memory
        """
        self.profiler = RepairCycleProfiler(
            enable_memory_tracking,
            enable_cpu_tracking,
            max_profiles=max_profiles,
        )
        threshold_monitor = None
        if threshold_monitoring:
            threshold_monitor = PerformanceThresholdMonitor(thresholds=custom_thresholds)
        self.threshold_monitor = threshold_monitor

    def profile(self, operation: str, metadata: Optional[Dict[str, Any]] = None):
        """Profile an operation."""
        context = self.profiler.profile_operation(operation, metadata)

        if self.threshold_monitor:
            return ThresholdCheckingContext(context, self.threshold_monitor)
        else:
            return context

    def get_report(self) -> Dict[str, Any]:
        """Get profiling report."""
        report = {
            "summary": self.profiler.get_profile_summary(),
            "slowest": self.profiler.get_slowest_operations(10),
            "heaviest": self.profiler.get_heaviest_operations(10),
            "hottest": self.profiler.get_hottest_operations(10),
        }

        if self.threshold_monitor:
            report["violations"] = self.threshold_monitor.get_violations()

        return report

    def shutdown(self) -> None:
        """Shutdown profiler."""
        self.profiler.shutdown()
