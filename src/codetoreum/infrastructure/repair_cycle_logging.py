"""Repair cycle structured logging for observability.

Provides structured logging for repair cycle stages with:
- Correlation IDs for request tracing
- Structured fields for log aggregation (workflow_run_id, test_type, agent_name, etc.)
- Performance timing for each stage
- Detailed error logging with context
- Log levels appropriate to severity
"""

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from enum import Enum
from codetoreum.infrastructure.error_ids import ErrorRegistry

logger = logging.getLogger(__name__)

__all__ = [
    "RepairCycleLogLevel",
    "RepairCycleLogContext",
    "RepairCycleLogger",
    "RepairCyclePerformanceLogger",
    "RepairCycleErrorLogger",
    "RepairCycleLoggingContext",
]


class RepairCycleLogLevel(str, Enum):
    """Log levels for repair cycle stages."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class RepairCycleLogContext:
    """Structured context for repair cycle logging."""

    workflow_run_id: str
    stage_name: str
    agent_name: str
    test_type: Optional[str] = None
    iteration: int = 0
    file_path: Optional[str] = None
    correlation_id: Optional[str] = None
    user_id: Optional[str] = None
    project_id: Optional[str] = None
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        """Initialize timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary for structured logging."""
        data = asdict(self)
        data["timestamp"] = data["timestamp"].isoformat()
        return {k: v for k, v in data.items() if v is not None}


class RepairCycleLogger:
    """Structured logger for repair cycle stages."""

    def __init__(self, context: RepairCycleLogContext):
        """
        Initialize repair cycle logger.

        Args:
            context: Structured logging context
        """
        self.context = context
        self.logger = logging.getLogger(f"repair_cycle.{context.stage_name}")

    def _format_message(self, message: str, data: Optional[Dict[str, Any]] = None) -> str:
        """Format structured message with context."""
        context_dict = self.context.to_dict()
        context_str = " | ".join(f"{k}={v}" for k, v in context_dict.items())

        if data:
            data_str = " | ".join(f"{k}={v}" for k, v in data.items())
            return f"{message} | {context_str} | {data_str}"
        return f"{message} | {context_str}"

    def debug(self, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Log debug message."""
        self.logger.debug(self._format_message(message, data))

    def info(self, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Log info message."""
        self.logger.info(self._format_message(message, data))

    def warning(self, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Log warning message."""
        self.logger.warning(self._format_message(message, data))

    def error(self, message: str, data: Optional[Dict[str, Any]] = None, exc_info: bool = False) -> None:
        """Log error message."""
        self.logger.error(self._format_message(message, data), exc_info=exc_info, extra={"error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR})

    def critical(self, message: str, data: Optional[Dict[str, Any]] = None, exc_info: bool = False) -> None:
        """Log critical message."""
        self.logger.critical(self._format_message(message, data), exc_info=exc_info)

    @contextmanager
    def log_duration(self, operation: str, data: Optional[Dict[str, Any]] = None):
        """
        Context manager to log operation duration.

        Usage:
            with logger.log_duration("test_execution", {"test_type": "unit"}):
                # ... perform operation ...
        """
        start_time = time.time()
        self.info(f"{operation} started", data)

        try:
            yield
            duration = time.time() - start_time
            self.info(
                f"{operation} completed",
                {**(data or {}), "duration_seconds": round(duration, 3), "status": "success"}
            )
        except Exception as e:
            duration = time.time() - start_time
            self.error(
                f"{operation} failed",
                {**(data or {}), "duration_seconds": round(duration, 3), "status": "failed", "error": str(e)},
                exc_info=True
            )
            raise

    @contextmanager
    def log_stage(self, stage_name: str, data: Optional[Dict[str, Any]] = None):
        """
        Context manager to log repair cycle stage execution.

        Usage:
            with logger.log_stage("fix_failures", {"file_count": 3}):
                # ... fix failures ...
        """
        with self.log_duration(f"stage:{stage_name}", data):
            yield


class RepairCyclePerformanceLogger:
    """Logs performance metrics for repair cycle stages."""

    def __init__(self, context: RepairCycleLogContext):
        """
        Initialize performance logger.

        Args:
            context: Structured logging context
        """
        self.context = context
        self.logger = logging.getLogger(f"repair_cycle.performance.{context.stage_name}")
        self._timings: Dict[str, List[float]] = {}

    def record_timing(self, operation: str, duration_seconds: float) -> None:
        """
        Record operation timing.

        Args:
            operation: Operation name
            duration_seconds: Duration in seconds
        """
        if operation not in self._timings:
            self._timings[operation] = []
        self._timings[operation].append(duration_seconds)

        self.logger.info(
            f"performance_timing | operation={operation} | duration={duration_seconds}s | "
            f"count={len(self._timings[operation])} | "
            f"avg={sum(self._timings[operation]) / len(self._timings[operation]):.3f}s"
        )

    def log_slow_operation(
        self,
        operation: str,
        duration_seconds: float,
        threshold_seconds: float,
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log slow operation warning.

        Args:
            operation: Operation name
            duration_seconds: Actual duration
            threshold_seconds: Performance threshold
            data: Additional context data
        """
        if duration_seconds > threshold_seconds:
            context_dict = self.context.to_dict()
            msg = (
                f"slow_operation_detected | operation={operation} | "
                f"duration={duration_seconds}s | threshold={threshold_seconds}s"
            )
            if data:
                msg += " | " + " | ".join(f"{k}={v}" for k, v in data.items())
            self.logger.warning(msg)

    def log_resource_usage(self, data: Dict[str, Any]) -> None:
        """
        Log resource usage during repair cycle.

        Args:
            data: Resource usage data (cpu_percent, memory_mb, etc.)
        """
        msg = "resource_usage | " + " | ".join(f"{k}={v}" for k, v in data.items())
        self.logger.debug(msg)

    def get_statistics(self) -> Dict[str, Dict[str, float]]:
        """
        Get timing statistics.

        Returns:
            Dict mapping operation to statistics (min, max, avg, count)
        """
        stats = {}
        for operation, durations in self._timings.items():
            if durations:
                stats[operation] = {
                    "count": len(durations),
                    "min": min(durations),
                    "max": max(durations),
                    "avg": sum(durations) / len(durations),
                    "total": sum(durations),
                }
        return stats


class RepairCycleErrorLogger:
    """Logs errors and failures during repair cycle."""

    def __init__(self, context: RepairCycleLogContext):
        """
        Initialize error logger.

        Args:
            context: Structured logging context
        """
        self.context = context
        self.logger = logging.getLogger(f"repair_cycle.errors.{context.stage_name}")
        self._error_counts: Dict[str, int] = {}

    def log_test_failure(
        self,
        test_type: str,
        test_file: str,
        failure_message: str,
        failure_details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log test failure.

        Args:
            test_type: Type of test (unit, integration, e2e)
            test_file: Test file path
            failure_message: Failure message
            failure_details: Additional failure details
        """
        self._error_counts["test_failure"] = self._error_counts.get("test_failure", 0) + 1

        msg = (
            f"test_failure | test_type={test_type} | test_file={test_file} | "
            f"message={failure_message}"
        )
        if failure_details:
            msg += " | " + " | ".join(f"{k}={v}" for k, v in failure_details.items())

        self.logger.error(msg, extra={"error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR})

    def log_fix_attempt(
        self,
        file_path: str,
        attempt_number: int,
        success: bool,
        agent_response: Optional[str] = None,
        error: Optional[str] = None
    ) -> None:
        """
        Log file fix attempt.

        Args:
            file_path: File being fixed
            attempt_number: Attempt number
            success: Whether fix was successful
            agent_response: Agent's response
            error: Error message if failed
        """
        status = "success" if success else "failed"
        msg = (
            f"fix_attempt | file={file_path} | attempt={attempt_number} | "
            f"status={status}"
        )

        if agent_response:
            msg += f" | response_len={len(agent_response)}"
        if error:
            msg += f" | error={error}"
            self._error_counts["fix_attempt_failed"] = self._error_counts.get("fix_attempt_failed", 0) + 1

        level = "info" if success else "warning"
        getattr(self.logger, level)(msg)

    def log_circuit_breaker_triggered(self, reason: str, context_data: Optional[Dict[str, Any]] = None) -> None:
        """
        Log circuit breaker triggered.

        Args:
            reason: Reason for circuit breaker
            context_data: Additional context data
        """
        self._error_counts["circuit_breaker"] = self._error_counts.get("circuit_breaker", 0) + 1

        msg = f"circuit_breaker_triggered | reason={reason}"
        if context_data:
            msg += " | " + " | ".join(f"{k}={v}" for k, v in context_data.items())

        self.logger.critical(msg)

    def log_checkpoint_created(self, checkpoint_id: str, data: Dict[str, Any]) -> None:
        """
        Log checkpoint creation.

        Args:
            checkpoint_id: Checkpoint identifier
            data: Checkpoint data
        """
        msg = f"checkpoint_created | checkpoint_id={checkpoint_id} | " + " | ".join(
            f"{k}={v}" for k, v in data.items()
        )
        self.logger.info(msg)

    def log_checkpoint_restored(self, checkpoint_id: str, data: Dict[str, Any]) -> None:
        """
        Log checkpoint restoration.

        Args:
            checkpoint_id: Checkpoint identifier
            data: Checkpoint data
        """
        msg = f"checkpoint_restored | checkpoint_id={checkpoint_id} | " + " | ".join(
            f"{k}={v}" for k, v in data.items()
        )
        self.logger.info(msg)

    def get_error_summary(self) -> Dict[str, int]:
        """Get summary of errors encountered."""
        return self._error_counts.copy()


class RepairCycleLoggingContext:
    """Context manager for structured logging across repair cycle."""

    def __init__(self, context: RepairCycleLogContext):
        """Initialize logging context."""
        self.context = context
        self.logger = RepairCycleLogger(context)
        self.perf_logger = RepairCyclePerformanceLogger(context)
        self.error_logger = RepairCycleErrorLogger(context)

    def __enter__(self):
        """Enter context."""
        self.logger.info("repair_cycle_context_started")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context."""
        if exc_type:
            self.error_logger.logger.error(
                f"repair_cycle_context_failed | error_type={exc_type.__name__} | error={str(exc_val)}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR}
            )
        else:
            self.logger.info("repair_cycle_context_completed")

    def log_operation(self, operation: str, data: Optional[Dict[str, Any]] = None):
        """Context manager to log operation with timing."""
        return self.logger.log_duration(operation, data)
