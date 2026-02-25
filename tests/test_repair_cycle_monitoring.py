"""Tests for repair cycle monitoring and observability.

Tests cover:
- Prometheus metrics adapter
- Repair cycle metrics collector
- Structured logging
- OpenTelemetry tracing
- Performance profiling
"""

import logging
from unittest.mock import MagicMock

import pytest

from codetoreum.adapters.testing.in_memory_metrics_adapter import (
    InMemoryMetricsAdapter,
)
from codetoreum.infrastructure.repair_cycle_logging import (
    RepairCycleErrorLogger,
    RepairCycleLogContext,
    RepairCycleLogger,
    RepairCycleLoggingContext,
    RepairCyclePerformanceLogger,
)
from codetoreum.infrastructure.repair_cycle_metrics_collector import (
    RepairCycleMetrics,
    RepairCycleMetricsCollector,
)
from codetoreum.infrastructure.repair_cycle_profiling import (
    PerformanceThresholdMonitor,
    ProfileData,
    RepairCycleProfiler,
)
from codetoreum.infrastructure.repair_cycle_tracing import (
    NullRepairCycleTracer,
    RepairCycleTracer,
)

# ============================================================================
# Metrics Adapter Interface Tests
# ============================================================================


class TestMetricsAdapter:
    """Test metrics adapter interface (using InMemoryMetricsAdapter)."""

    async def test_increment_counter(self):
        """Test counter increment."""
        adapter = InMemoryMetricsAdapter()
        await adapter.increment_counter(
            "repair_cycle_started_total",
            labels={"agent_name": "test_agent"},
        )
        assert await adapter.health_check()

    async def test_set_gauge(self):
        """Test gauge setting."""
        adapter = InMemoryMetricsAdapter()
        await adapter.set_gauge(
            "repair_cycle_active_count",
            5.0,
            labels={"agent_name": "test_agent"},
        )
        assert await adapter.health_check()

    async def test_record_histogram(self):
        """Test histogram recording."""
        adapter = InMemoryMetricsAdapter()
        await adapter.record_histogram(
            "repair_cycle_duration_seconds",
            45.5,
            labels={"agent_name": "test_agent", "status": "success"},
        )
        assert await adapter.health_check()

    async def test_timer_context(self):
        """Test timer functionality."""
        adapter = InMemoryMetricsAdapter()
        timer_id = await adapter.start_timer("test_operation")
        assert timer_id
        duration = await adapter.stop_timer(timer_id, labels={"operation": "test"})
        assert duration >= 0

    async def test_batch_recording(self):
        """Test batch metric recording."""
        adapter = InMemoryMetricsAdapter()
        metrics = [
            {"name": "metric1", "value": 10, "type": "counter"},
            {"name": "metric2", "value": 20.5, "type": "gauge"},
        ]
        await adapter.record_batch(metrics)
        assert await adapter.health_check()

    async def test_metrics_registry(self):
        """Test metrics registry."""
        adapter = InMemoryMetricsAdapter()
        await adapter.increment_counter("repair_cycle_started")
        names = await adapter.get_metric_names()
        assert len(names) > 0
        assert "repair_cycle_started" in names

    async def test_health_check(self):
        """Test health check."""
        adapter = InMemoryMetricsAdapter()
        health = await adapter.health_check()
        assert health is True


# ============================================================================
# Repair Cycle Metrics Collector Tests
# ============================================================================


class TestRepairCycleMetricsCollector:
    """Test repair cycle metrics collector."""

    def test_initialization(self):
        """Test collector initialization."""
        collector = RepairCycleMetricsCollector()
        assert collector._metrics.cycles_started == 0
        assert collector._metrics.cycles_completed == 0
        assert collector._metrics.cycles_successful == 0

    async def test_cycle_started_event(self):
        """Test repair cycle started event recording."""
        collector = RepairCycleMetricsCollector()
        event = MagicMock()
        event.agent_name = "test_agent"
        event.stage_name = "repair"

        await collector._on_repair_cycle_started(event)

        assert collector._metrics.cycles_started == 1
        assert "test_agent" in collector._metrics.per_agent_metrics

    async def test_cycle_completed_event_success(self):
        """Test repair cycle completed event (success)."""
        collector = RepairCycleMetricsCollector()
        event = MagicMock()
        event.agent_name = "test_agent"
        event.stage_name = "repair"
        event.overall_success = True
        event.duration_seconds = 45.5
        event.total_agent_calls = 2
        event.total_iterations = 2

        await collector._on_repair_cycle_completed(event)

        assert collector._metrics.cycles_completed == 1
        assert collector._metrics.cycles_successful == 1
        assert len(collector._metrics.cycle_durations) == 1
        assert collector._metrics.cycle_durations[0] == 45.5

    async def test_cycle_completed_event_failure(self):
        """Test repair cycle completed event (failure)."""
        collector = RepairCycleMetricsCollector()
        event = MagicMock()
        event.agent_name = "test_agent"
        event.stage_name = "repair"
        event.overall_success = False
        event.duration_seconds = 120.0
        event.total_agent_calls = 5
        event.total_iterations = 5

        await collector._on_repair_cycle_completed(event)

        assert collector._metrics.cycles_completed == 1
        assert collector._metrics.cycles_failed == 1
        assert len(collector._metrics.cycle_durations) == 1

    async def test_fast_fail_event(self):
        """Test fast fail event recording."""
        collector = RepairCycleMetricsCollector()
        event = MagicMock()
        event.agent_name = "test_agent"
        event.reason = "max_iterations_exceeded"

        await collector._on_repair_cycle_fast_fail(event)

        assert collector._metrics.cycles_fast_failed == 1
        assert collector._metrics.fast_fail_reasons["max_iterations_exceeded"] == 1

    async def test_test_execution_completed_event(self):
        """Test test execution completed event."""
        collector = RepairCycleMetricsCollector()
        event = MagicMock()
        event.test_type = "unit"
        event.passed_count = 10
        event.failed_count = 0
        event.iteration = 1
        event.duration_seconds = 30.0

        await collector._on_test_execution_completed(event)

        assert collector._metrics.test_executions_by_type["unit"] == 1
        assert "unit" in collector._metrics.test_iterations_by_type

    async def test_file_fix_completed_event(self):
        """Test file fix completed event."""
        collector = RepairCycleMetricsCollector()
        event = MagicMock()
        event.file_path = "src/main.py"
        event.fixed = True
        event.duration_seconds = 15.0

        await collector._on_file_fix_completed(event)

        assert collector._metrics.files_fixed_total == 1
        assert "src/main.py" in collector._metrics.unique_files_fixed

    async def test_warning_review_completed_event(self):
        """Test warning review completed event."""
        collector = RepairCycleMetricsCollector()
        warning = MagicMock()
        warning.severity = "warning"

        event = MagicMock()
        event.warnings_reviewed = 1
        event.warnings = (warning,)

        await collector._on_warning_review_completed(event)

        assert collector._metrics.warnings_reviewed_total == 1
        assert collector._metrics.warnings_by_severity.get("warning", 0) == 1

    def test_metrics_aggregation(self):
        """Test metrics aggregation."""
        metrics = RepairCycleMetrics()
        metrics.cycles_completed = 10
        metrics.cycles_successful = 8
        metrics.cycle_durations = [30.0, 45.0, 60.0]
        metrics.agent_calls_per_cycle = [1, 2, 1]

        assert metrics.get_success_rate_percent() == 80.0
        assert metrics.get_avg_duration_seconds() == 45.0
        assert metrics.get_avg_agent_calls() == pytest.approx(1.33, rel=0.01)

    def test_reset_metrics(self):
        """Test metrics reset."""
        collector = RepairCycleMetricsCollector()
        collector._metrics.cycles_started = 10
        collector.reset_metrics()
        assert collector._metrics.cycles_started == 0


# ============================================================================
# Structured Logging Tests
# ============================================================================


class TestRepairCycleLogging:
    """Test repair cycle structured logging."""

    def test_log_context_creation(self):
        """Test log context creation."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="repair",
            agent_name="test_agent",
        )
        assert context.workflow_run_id == "run-123"
        assert context.stage_name == "repair"

    def test_log_context_to_dict(self):
        """Test log context to_dict conversion."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="repair",
            agent_name="test_agent",
            test_type="unit",
        )
        data = context.to_dict()
        assert data["workflow_run_id"] == "run-123"
        assert data["test_type"] == "unit"

    def test_repair_cycle_logger(self, caplog):
        """Test repair cycle logger."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="repair",
            agent_name="test_agent",
        )
        logger = RepairCycleLogger(context)

        with caplog.at_level(logging.INFO):
            logger.info("Test message", {"key": "value"})

        assert "Test message" in caplog.text
        assert "run-123" in caplog.text

    def test_performance_logger(self):
        """Test performance logger."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="repair",
            agent_name="test_agent",
        )
        logger = RepairCyclePerformanceLogger(context)

        logger.record_timing("test_operation", 10.5)
        logger.record_timing("test_operation", 12.3)

        stats = logger.get_statistics()
        assert "test_operation" in stats
        assert stats["test_operation"]["count"] == 2

    def test_error_logger(self):
        """Test error logger."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="repair",
            agent_name="test_agent",
        )
        logger = RepairCycleErrorLogger(context)

        logger.log_test_failure(
            test_type="unit",
            test_file="test_main.py",
            failure_message="AssertionError",
        )

        summary = logger.get_error_summary()
        assert summary.get("test_failure", 0) == 1

    def test_logging_context_manager(self, caplog):
        """Test logging context manager."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="repair",
            agent_name="test_agent",
        )

        with caplog.at_level(logging.INFO), RepairCycleLoggingContext(context) as ctx:
            ctx.logger.info("Test operation")

        assert "repair_cycle_context_started" in caplog.text
        assert "Test operation" in caplog.text


# ============================================================================
# OpenTelemetry Tracing Tests
# ============================================================================


class TestRepairCycleTracing:
    """Test OpenTelemetry tracing."""

    def test_null_tracer(self):
        """Test null tracer (when OTel unavailable)."""
        tracer = NullRepairCycleTracer()

        with tracer.trace_cycle("test_cycle"):
            pass  # No-op

        with tracer.trace_stage("test_stage"):
            pass  # No-op

        tracer.shutdown()

    def test_tracer_disabled(self):
        """Test tracer when disabled."""
        tracer = RepairCycleTracer(enabled=False)
        assert tracer.tracer is None

    def test_serialize_attribute(self):
        """Test attribute serialization."""
        assert RepairCycleTracer._serialize_attribute("test") == "test"
        assert RepairCycleTracer._serialize_attribute(42) == 42
        assert RepairCycleTracer._serialize_attribute(3.14) == 3.14
        assert RepairCycleTracer._serialize_attribute([1, 2, 3]) == [1, 2, 3]


# ============================================================================
# Performance Profiling Tests
# ============================================================================


class TestRepairCycleProfiler:
    """Test performance profiler."""

    def test_profiler_initialization(self):
        """Test profiler initialization."""
        profiler = RepairCycleProfiler()
        assert profiler.enable_memory_tracking
        assert profiler.enable_cpu_tracking

    def test_profile_operation(self):
        """Test operation profiling."""
        profiler = RepairCycleProfiler()

        with profiler.profile_operation("test_operation"):
            pass

        profiles = profiler.get_profiles()
        assert len(profiles) == 1
        assert profiles[0].operation == "test_operation"
        assert profiles[0].duration_seconds >= 0

    def test_profile_summary(self):
        """Test profile summary generation."""
        profiler = RepairCycleProfiler()

        with profiler.profile_operation("test_op"):
            pass

        with profiler.profile_operation("test_op"):
            pass

        summary = profiler.get_profile_summary()
        assert "test_op" in summary
        assert summary["test_op"]["count"] == 2

    def test_slowest_operations(self):
        """Test slowest operations ranking."""
        profiler = RepairCycleProfiler()

        for i in range(3):
            with profiler.profile_operation(f"op_{i}"):
                pass

        slowest = profiler.get_slowest_operations(2)
        assert len(slowest) <= 2

    def test_profiler_reset(self):
        """Test profiler reset."""
        profiler = RepairCycleProfiler()

        with profiler.profile_operation("test_op"):
            pass

        assert len(profiler.get_profiles()) == 1
        profiler.reset()
        assert len(profiler.get_profiles()) == 0

    def test_profiler_exception_handling(self):
        """Test profiler handles exceptions."""
        profiler = RepairCycleProfiler()

        with pytest.raises(ValueError), profiler.profile_operation("failing_op"):
            raise ValueError("Test error")

        profiles = profiler.get_profiles()
        assert profiles[0].exceptions == 1


# ============================================================================
# Performance Threshold Monitoring Tests
# ============================================================================


class TestPerformanceThresholdMonitor:
    """Test performance threshold monitoring."""

    def test_default_thresholds(self):
        """Test default threshold configuration."""
        monitor = PerformanceThresholdMonitor()
        assert "test_execution" in monitor.thresholds
        assert "repair_cycle" in monitor.thresholds

    def test_threshold_violation_detection(self):
        """Test threshold violation detection."""
        monitor = PerformanceThresholdMonitor(
            thresholds={"test_op": {"duration_seconds": 10.0}}
        )

        profile = ProfileData(
            operation="test_op",
            start_time=0,
            end_time=15.0,
        )

        violations = monitor.check_thresholds(profile)
        assert len(violations) > 0
        assert "Duration threshold exceeded" in violations[0]

    def test_no_violations(self):
        """Test when no violations occur."""
        monitor = PerformanceThresholdMonitor(
            thresholds={"test_op": {"duration_seconds": 100.0}}
        )

        profile = ProfileData(
            operation="test_op",
            start_time=0,
            end_time=5.0,
        )

        violations = monitor.check_thresholds(profile)
        assert len(violations) == 0

    def test_violations_history(self):
        """Test violations history tracking."""
        monitor = PerformanceThresholdMonitor(
            thresholds={"test_op": {"duration_seconds": 10.0}}
        )

        profile = ProfileData(
            operation="test_op",
            start_time=0,
            end_time=15.0,
        )

        monitor.check_thresholds(profile)
        violations = monitor.get_violations()
        assert len(violations) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
