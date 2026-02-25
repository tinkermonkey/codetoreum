"""Repair cycle metrics collector for comprehensive monitoring.

Subscribes to repair cycle domain events and records detailed metrics:
- Cycle execution (start, completion, success/failure)
- Test execution metrics (test type, duration, pass/fail counts)
- File fixing metrics (file paths, iterations, success rate)
- Warning review metrics (warnings processed, severity)
- Performance metrics (durations, iterations, agent calls)
- Per-agent breakdown of repair cycle activity

Supports multiple metrics backends (in-memory, Prometheus, etc.)
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from codetoreum.domain.events import DomainEvent
from codetoreum.domain.events.repair_cycle_events import (
    RepairCycleMetricsBackendFailedEvent,
)
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.event_types import EventTypes
from codetoreum.ports.output.metrics import IMetrics

logger = logging.getLogger(__name__)

__all__ = [
    "RepairCycleMetrics",
    "RepairCycleMetricsCollector",
]


@dataclass
class RepairCycleMetrics:
    """Container for repair cycle metrics."""

    # Cycle-level metrics
    cycles_started: int = 0
    cycles_completed: int = 0
    cycles_successful: int = 0
    cycles_failed: int = 0
    cycles_fast_failed: int = 0

    # Duration metrics
    cycle_durations: list[float] = None  # seconds
    total_duration_seconds: float = 0.0

    # Test execution metrics
    test_executions_by_type: dict[str, int] = None  # {test_type: count}
    test_failures_by_type: dict[str, int] = None  # {test_type: failure_count}
    test_iterations_by_type: dict[str, list[int]] = None  # {test_type: [iteration_counts]}

    # File fixing metrics
    files_fixed_total: int = 0
    unique_files_fixed: dict[str, int] = None  # {file_path: fix_count}
    file_fix_durations_by_type: dict[str, list[float]] = None  # {file_ext: [durations]}

    # Warning metrics
    warnings_reviewed_total: int = 0
    warnings_by_severity: dict[str, int] = None  # {severity: count}

    # Agent call metrics
    agent_calls_per_cycle: list[int] = None  # agent call counts per cycle
    total_agent_calls: int = 0

    # Per-agent breakdown
    per_agent_metrics: dict[str, "RepairCycleMetrics"] = None

    # Error tracking
    fast_fail_reasons: dict[str, int] = None  # {reason: count}

    def __post_init__(self):
        """Initialize list/dict fields."""
        if self.cycle_durations is None:
            self.cycle_durations = []
        if self.test_executions_by_type is None:
            self.test_executions_by_type = {}
        if self.test_failures_by_type is None:
            self.test_failures_by_type = {}
        if self.test_iterations_by_type is None:
            self.test_iterations_by_type = {}
        if self.unique_files_fixed is None:
            self.unique_files_fixed = {}
        if self.file_fix_durations_by_type is None:
            self.file_fix_durations_by_type = {}
        if self.warnings_by_severity is None:
            self.warnings_by_severity = {}
        if self.agent_calls_per_cycle is None:
            self.agent_calls_per_cycle = []
        if self.per_agent_metrics is None:
            self.per_agent_metrics = {}
        if self.fast_fail_reasons is None:
            self.fast_fail_reasons = {}

    def get_success_rate_percent(self) -> float | None:
        """Calculate success rate percentage."""
        if self.cycles_completed == 0:
            return None
        return (self.cycles_successful / self.cycles_completed) * 100

    def get_avg_duration_seconds(self) -> float | None:
        """Calculate average cycle duration."""
        if not self.cycle_durations:
            return None
        return sum(self.cycle_durations) / len(self.cycle_durations)

    def get_avg_agent_calls(self) -> float | None:
        """Calculate average agent calls per cycle."""
        if not self.agent_calls_per_cycle:
            return None
        return sum(self.agent_calls_per_cycle) / len(self.agent_calls_per_cycle)

    def get_avg_iterations_by_test_type(self, test_type: str) -> float | None:
        """Calculate average iterations for a specific test type."""
        iterations = self.test_iterations_by_type.get(test_type, [])
        if not iterations:
            return None
        return sum(iterations) / len(iterations)

    def get_test_failure_rate_percent(self, test_type: str) -> float | None:
        """Calculate failure rate for a specific test type."""
        executions = self.test_executions_by_type.get(test_type, 0)
        failures = self.test_failures_by_type.get(test_type, 0)
        if executions == 0:
            return None
        return (failures / executions) * 100


class RepairCycleMetricsCollector:
    """Collects and aggregates repair cycle metrics from domain events."""

    def __init__(
        self,
        event_bus: EventBus | None = None,
        metrics_backend: IMetrics | None = None,
    ):
        """
        Initialize repair cycle metrics collector.

        Args:
            event_bus: Event bus to subscribe to for events
            metrics_backend: Optional metrics backend (e.g., Prometheus)
        """
        self.event_bus = event_bus
        self.metrics_backend = metrics_backend

        # In-memory metrics aggregation
        self._metrics = RepairCycleMetrics()

        # Track active cycles for gauges
        self._active_cycles_by_agent: dict[str, int] = {}

        # Circuit breaker for metrics backend
        self._backend_consecutive_failures = 0
        self._backend_circuit_open = False
        self._max_consecutive_failures = 5

        # Subscribe to events if bus provided
        if self.event_bus:
            self._subscribe_to_events()

        logger.info("RepairCycleMetricsCollector initialized")

    def _subscribe_to_events(self) -> None:
        """Subscribe to repair cycle domain events."""
        if not self.event_bus:
            return

        # Cycle lifecycle events
        self.event_bus.subscribe(EventTypes.REPAIR_CYCLE_STARTED, self._on_repair_cycle_started)
        self.event_bus.subscribe(EventTypes.REPAIR_CYCLE_COMPLETED, self._on_repair_cycle_completed)
        self.event_bus.subscribe(EventTypes.REPAIR_CYCLE_FAST_FAIL, self._on_repair_cycle_fast_fail)

        # Test execution events
        self.event_bus.subscribe(EventTypes.REPAIR_CYCLE_TEST_EXECUTION_STARTED, self._on_test_execution_started)
        self.event_bus.subscribe(EventTypes.REPAIR_CYCLE_TEST_EXECUTION_COMPLETED, self._on_test_execution_completed)

        # File fixing events
        self.event_bus.subscribe(EventTypes.REPAIR_CYCLE_FILE_FIX_STARTED, self._on_file_fix_started)
        self.event_bus.subscribe(EventTypes.REPAIR_CYCLE_FILE_FIX_COMPLETED, self._on_file_fix_completed)

        # Warning review events
        self.event_bus.subscribe(EventTypes.REPAIR_CYCLE_WARNING_REVIEW_STARTED, self._on_warning_review_started)
        self.event_bus.subscribe(EventTypes.REPAIR_CYCLE_WARNING_REVIEW_COMPLETED, self._on_warning_review_completed)

        logger.info("RepairCycleMetricsCollector subscribed to events")

    def _get_event_attribute(self, event: DomainEvent, attribute: str, default: Any = None) -> Any:
        """Extract attribute from event."""
        if hasattr(event, attribute):
            return getattr(event, attribute, default)
        if hasattr(event, "payload") and isinstance(event.payload, dict):
            return event.payload.get(attribute, default)
        return default

    def _get_or_create_agent_metrics(self, agent_name: str) -> RepairCycleMetrics:
        """Get or create metrics container for an agent."""
        if agent_name not in self._metrics.per_agent_metrics:
            self._metrics.per_agent_metrics[agent_name] = RepairCycleMetrics()
        return self._metrics.per_agent_metrics[agent_name]

    def _record_backend_success(self) -> None:
        """Record successful backend call and potentially close circuit."""
        if self._backend_circuit_open:
            self._backend_consecutive_failures = 0
            self._backend_circuit_open = False
            logger.info("Metrics backend circuit breaker closed - backend recovered")

    def _record_backend_failure(self, operation: str, error: Exception) -> None:
        """Record backend failure and emit event for visibility."""
        self._backend_consecutive_failures += 1

        if not self._backend_circuit_open and self._backend_consecutive_failures >= self._max_consecutive_failures:
            self._backend_circuit_open = True
            logger.error(
                f"Metrics backend circuit breaker OPENED after {self._max_consecutive_failures} consecutive failures",
                extra={
                    "last_operation": operation,
                    "last_error": str(error),
                    "error_id": ErrorRegistry.ERR_METRICS_ERROR,
                },
                exc_info=True,
            )

        # Emit event for external visibility (alerting, monitoring)
        if self.event_bus:
            self.event_bus.emit(
                RepairCycleMetricsBackendFailedEvent(
                    type="repair_cycle.metrics_backend_failed",
                    timestamp=datetime.now(UTC).isoformat(),
                    source="repair_cycle_metrics_collector",
                    operation=operation,
                    error_type=type(error).__name__,
                    error_message=str(error),
                    consecutive_failures=self._backend_consecutive_failures,
                    circuit_breaker_open=self._backend_circuit_open,
                    workflow_run_id=getattr(error, "workflow_run_id", ""),
                )
            )

    def is_backend_healthy(self) -> bool:
        """Check if metrics backend is healthy (circuit closed)."""
        return not self._backend_circuit_open

    async def _on_repair_cycle_started(self, event: DomainEvent) -> None:
        """Record repair cycle started."""
        try:
            agent_name = self._get_event_attribute(event, "agent_name", "unknown")
            stage_name = self._get_event_attribute(event, "stage_name", "unknown")

            self._metrics.cycles_started += 1
            self._get_or_create_agent_metrics(agent_name).cycles_started += 1

            # Increment active cycles gauge
            self._active_cycles_by_agent[agent_name] = self._active_cycles_by_agent.get(agent_name, 0) + 1

            if self.metrics_backend:
                await self.metrics_backend.increment_counter(
                    f"{self.metrics_backend.namespace}_{self.metrics_backend.subsystem}_started_total",
                    labels={"agent_name": agent_name, "stage_name": stage_name},
                )
                await self.metrics_backend.set_gauge(
                    f"{self.metrics_backend.namespace}_{self.metrics_backend.subsystem}_active_count",
                    float(self._active_cycles_by_agent.get(agent_name, 0)),
                    labels={"agent_name": agent_name},
                )
                self._record_backend_success()

            logger.debug(f"Repair cycle started: agent={agent_name}, stage={stage_name}")

        except Exception as e:
            self._record_backend_failure("repair_cycle_started", e)

            # Use ERROR level if circuit is open (critical degradation)
            log_level = logger.error if self._backend_circuit_open else logger.warning
            log_level(
                f"Metrics backend failure during repair_cycle_started: {e}",
                exc_info=True,
                extra={
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_METRICS_ERROR,
                    "circuit_breaker_open": self._backend_circuit_open,
                    "consecutive_failures": self._backend_consecutive_failures,
                },
            )

    async def _on_repair_cycle_completed(self, event: DomainEvent) -> None:
        """Record repair cycle completed."""
        try:
            agent_name = self._get_event_attribute(event, "agent_name", "unknown")
            stage_name = self._get_event_attribute(event, "stage_name", "unknown")
            overall_success = self._get_event_attribute(event, "overall_success", False)
            duration_seconds = self._get_event_attribute(event, "duration_seconds", 0.0)
            total_agent_calls = self._get_event_attribute(event, "total_agent_calls", 0)

            self._metrics.cycles_completed += 1
            self._metrics.cycle_durations.append(duration_seconds)
            self._metrics.total_duration_seconds += duration_seconds
            self._metrics.agent_calls_per_cycle.append(total_agent_calls)
            self._metrics.total_agent_calls += total_agent_calls

            agent_metrics = self._get_or_create_agent_metrics(agent_name)
            agent_metrics.cycles_completed += 1
            agent_metrics.cycle_durations.append(duration_seconds)
            agent_metrics.agent_calls_per_cycle.append(total_agent_calls)

            if overall_success:
                self._metrics.cycles_successful += 1
                agent_metrics.cycles_successful += 1
                status = "success"
            else:
                self._metrics.cycles_failed += 1
                agent_metrics.cycles_failed += 1
                status = "failed"

            # Decrement active cycles gauge
            self._active_cycles_by_agent[agent_name] = max(0, self._active_cycles_by_agent.get(agent_name, 1) - 1)

            if self.metrics_backend:
                await self.metrics_backend.increment_counter(
                    f"{self.metrics_backend.namespace}_{self.metrics_backend.subsystem}_completed_total",
                    labels={"agent_name": agent_name, "stage_name": stage_name, "status": status},
                )
                await self.metrics_backend.record_duration(
                    f"{self.metrics_backend.namespace}_{self.metrics_backend.subsystem}_duration_seconds",
                    duration_seconds,
                    labels={"agent_name": agent_name, "status": status},
                )
                await self.metrics_backend.record_summary(
                    f"{self.metrics_backend.namespace}_{self.metrics_backend.subsystem}_agent_calls_per_cycle",
                    float(total_agent_calls),
                    labels={"agent_name": agent_name},
                )
                await self.metrics_backend.set_gauge(
                    f"{self.metrics_backend.namespace}_{self.metrics_backend.subsystem}_active_count",
                    float(self._active_cycles_by_agent.get(agent_name, 0)),
                    labels={"agent_name": agent_name},
                )
                self._record_backend_success()

            logger.debug(
                f"Repair cycle completed: agent={agent_name}, status={status}, "
                f"duration={duration_seconds}s, agent_calls={total_agent_calls}"
            )

        except Exception as e:
            self._record_backend_failure("repair_cycle_completed", e)

            # Use ERROR level if circuit is open (critical degradation)
            log_level = logger.error if self._backend_circuit_open else logger.warning
            log_level(
                f"Metrics backend failure during repair_cycle_completed: {e}",
                exc_info=True,
                extra={
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_METRICS_ERROR,
                    "circuit_breaker_open": self._backend_circuit_open,
                    "consecutive_failures": self._backend_consecutive_failures,
                },
            )

    async def _on_repair_cycle_fast_fail(self, event: DomainEvent) -> None:
        """Record repair cycle fast-fail."""
        try:
            agent_name = self._get_event_attribute(event, "agent_name", "unknown")
            reason = self._get_event_attribute(event, "reason", "unknown")

            self._metrics.cycles_fast_failed += 1
            self._metrics.cycles_completed += 1
            self._metrics.cycles_failed += 1
            self._metrics.fast_fail_reasons[reason] = self._metrics.fast_fail_reasons.get(reason, 0) + 1

            agent_metrics = self._get_or_create_agent_metrics(agent_name)
            agent_metrics.cycles_fast_failed += 1
            agent_metrics.cycles_completed += 1
            agent_metrics.cycles_failed += 1

            # Decrement active cycles
            self._active_cycles_by_agent[agent_name] = max(0, self._active_cycles_by_agent.get(agent_name, 1) - 1)

            if self.metrics_backend:
                await self.metrics_backend.increment_counter(
                    f"{self.metrics_backend.namespace}_{self.metrics_backend.subsystem}_fast_failed_total",
                    labels={"agent_name": agent_name, "reason": reason},
                )
                self._record_backend_success()

            logger.warning(f"Repair cycle fast-failed: agent={agent_name}, reason={reason}")

        except Exception as e:
            self._record_backend_failure("repair_cycle_fast_fail", e)

            # Use ERROR level if circuit is open (critical degradation)
            log_level = logger.error if self._backend_circuit_open else logger.warning
            log_level(
                f"Metrics backend failure during repair_cycle_fast_fail: {e}",
                exc_info=True,
                extra={
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_METRICS_ERROR,
                    "circuit_breaker_open": self._backend_circuit_open,
                    "consecutive_failures": self._backend_consecutive_failures,
                },
            )

    async def _on_test_execution_started(self, event: DomainEvent) -> None:
        """Record test execution started."""
        try:
            test_type = self._get_event_attribute(event, "test_type", "unknown")
            iteration = self._get_event_attribute(event, "iteration", 0)

            logger.debug(f"Test execution started: test_type={test_type}, iteration={iteration}")

        except Exception as e:
            self._record_backend_failure("test_execution_started", e)

            # Use ERROR level if circuit is open (critical degradation)
            log_level = logger.error if self._backend_circuit_open else logger.warning
            log_level(
                f"Metrics backend failure during test_execution_started: {e}",
                exc_info=True,
                extra={
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_METRICS_ERROR,
                    "circuit_breaker_open": self._backend_circuit_open,
                    "consecutive_failures": self._backend_consecutive_failures,
                },
            )

    async def _on_test_execution_completed(self, event: DomainEvent) -> None:
        """Record test execution completed."""
        try:
            test_type = self._get_event_attribute(event, "test_type", "unknown")
            passed_count = self._get_event_attribute(event, "passed_count", 0)
            failed_count = self._get_event_attribute(event, "failed_count", 0)
            iteration = self._get_event_attribute(event, "iteration", 0)
            duration_seconds = self._get_event_attribute(event, "duration_seconds", 0.0)

            # Aggregate test execution metrics
            self._metrics.test_executions_by_type[test_type] = (
                self._metrics.test_executions_by_type.get(test_type, 0) + 1
            )

            if failed_count > 0:
                self._metrics.test_failures_by_type[test_type] = (
                    self._metrics.test_failures_by_type.get(test_type, 0) + failed_count
                )

            if test_type not in self._metrics.test_iterations_by_type:
                self._metrics.test_iterations_by_type[test_type] = []
            self._metrics.test_iterations_by_type[test_type].append(iteration)

            status = "passed" if failed_count == 0 else "failed"

            if self.metrics_backend:
                await self.metrics_backend.increment_counter(
                    f"{self.metrics_backend.namespace}_{self.metrics_backend.subsystem}_test_executions_total",
                    labels={"test_type": test_type, "status": status},
                )
                if failed_count > 0:
                    await self.metrics_backend.increment_counter(
                        f"{self.metrics_backend.namespace}_{self.metrics_backend.subsystem}_test_failures_total",
                        failed_count,
                        labels={"test_type": test_type},
                    )
                if duration_seconds > 0:
                    await self.metrics_backend.record_histogram(
                        f"{self.metrics_backend.namespace}_{self.metrics_backend.subsystem}_test_execution_duration_seconds",
                        duration_seconds,
                        labels={"test_type": test_type},
                    )
                self._record_backend_success()

            logger.debug(
                f"Test execution completed: test_type={test_type}, passed={passed_count}, "
                f"failed={failed_count}, duration={duration_seconds}s"
            )

        except Exception as e:
            self._record_backend_failure("test_execution_completed", e)

            # Use ERROR level if circuit is open (critical degradation)
            log_level = logger.error if self._backend_circuit_open else logger.warning
            log_level(
                f"Metrics backend failure during test_execution_completed: {e}",
                exc_info=True,
                extra={
                    "circuit_breaker_open": self._backend_circuit_open,
                    "consecutive_failures": self._backend_consecutive_failures,
                },
            )

    async def _on_file_fix_started(self, event: DomainEvent) -> None:
        """Record file fix started."""
        try:
            file_path = self._get_event_attribute(event, "file_path", "unknown")
            failure_count = self._get_event_attribute(event, "failure_count", 0)

            logger.debug(f"File fix started: file_path={file_path}, failures={failure_count}")

        except Exception as e:
            self._record_backend_failure("file_fix_started", e)

            # Use ERROR level if circuit is open (critical degradation)
            log_level = logger.error if self._backend_circuit_open else logger.warning
            log_level(
                f"Metrics backend failure during file_fix_started: {e}",
                exc_info=True,
                extra={
                    "circuit_breaker_open": self._backend_circuit_open,
                    "consecutive_failures": self._backend_consecutive_failures,
                },
            )

    async def _on_file_fix_completed(self, event: DomainEvent) -> None:
        """Record file fix completed."""
        try:
            file_path = self._get_event_attribute(event, "file_path", "unknown")
            fixed = self._get_event_attribute(event, "fixed", False)
            duration_seconds = self._get_event_attribute(event, "duration_seconds", 0.0)

            if fixed:
                self._metrics.files_fixed_total += 1
                self._metrics.unique_files_fixed[file_path] = self._metrics.unique_files_fixed.get(file_path, 0) + 1

                # Extract file extension for metrics
                file_ext = file_path.split(".")[-1] if "." in file_path else "unknown"

                if file_ext not in self._metrics.file_fix_durations_by_type:
                    self._metrics.file_fix_durations_by_type[file_ext] = []
                if duration_seconds > 0:
                    self._metrics.file_fix_durations_by_type[file_ext].append(duration_seconds)

                if self.metrics_backend:
                    await self.metrics_backend.increment_counter(
                        f"{self.metrics_backend.namespace}_{self.metrics_backend.subsystem}_files_fixed_total",
                        labels={"file_extension": file_ext},
                    )
                    if duration_seconds > 0:
                        await self.metrics_backend.record_histogram(
                            f"{self.metrics_backend.namespace}_{self.metrics_backend.subsystem}_file_fix_duration_seconds",
                            duration_seconds,
                            labels={"file_extension": file_ext},
                        )
                    self._record_backend_success()

            logger.debug(f"File fix completed: file_path={file_path}, fixed={fixed}")

        except Exception as e:
            self._record_backend_failure("file_fix_completed", e)

            # Use ERROR level if circuit is open (critical degradation)
            log_level = logger.error if self._backend_circuit_open else logger.warning
            log_level(
                f"Metrics backend failure during file_fix_completed: {e}",
                exc_info=True,
                extra={
                    "circuit_breaker_open": self._backend_circuit_open,
                    "consecutive_failures": self._backend_consecutive_failures,
                },
            )

    async def _on_warning_review_started(self, event: DomainEvent) -> None:
        """Record warning review started."""
        try:
            source_file = self._get_event_attribute(event, "source_file", "unknown")
            warning_count = self._get_event_attribute(event, "warning_count", 0)

            logger.debug(f"Warning review started: file={source_file}, warnings={warning_count}")

        except Exception as e:
            self._record_backend_failure("warning_review_started", e)

            # Use ERROR level if circuit is open (critical degradation)
            log_level = logger.error if self._backend_circuit_open else logger.warning
            log_level(
                f"Metrics backend failure during warning_review_started: {e}",
                exc_info=True,
                extra={
                    "circuit_breaker_open": self._backend_circuit_open,
                    "consecutive_failures": self._backend_consecutive_failures,
                },
            )

    async def _on_warning_review_completed(self, event: DomainEvent) -> None:
        """Record warning review completed."""
        try:
            warnings_reviewed = self._get_event_attribute(event, "warnings_reviewed", 0)
            warnings = self._get_event_attribute(event, "warnings", ())

            self._metrics.warnings_reviewed_total += warnings_reviewed

            # Track warnings by severity
            for warning in warnings:
                severity = getattr(warning, "severity", "info")
                self._metrics.warnings_by_severity[severity] = self._metrics.warnings_by_severity.get(severity, 0) + 1

                if self.metrics_backend:
                    await self.metrics_backend.increment_counter(
                        f"{self.metrics_backend.namespace}_{self.metrics_backend.subsystem}_warnings_reviewed_total",
                        labels={"severity": severity},
                    )

            if self.metrics_backend and warnings:
                self._record_backend_success()

            logger.debug(f"Warning review completed: warnings_reviewed={warnings_reviewed}")

        except Exception as e:
            self._record_backend_failure("warning_review_completed", e)

            # Use ERROR level if circuit is open (critical degradation)
            log_level = logger.error if self._backend_circuit_open else logger.warning
            log_level(
                f"Metrics backend failure during warning_review_completed: {e}",
                exc_info=True,
                extra={
                    "circuit_breaker_open": self._backend_circuit_open,
                    "consecutive_failures": self._backend_consecutive_failures,
                },
            )

    def get_metrics(self) -> RepairCycleMetrics:
        """Get aggregated repair cycle metrics."""
        return self._metrics

    def reset_metrics(self) -> None:
        """Reset all metrics (for testing)."""
        self._metrics = RepairCycleMetrics()
        self._active_cycles_by_agent.clear()
        logger.info("Repair cycle metrics reset")
