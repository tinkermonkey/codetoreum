"""Prometheus metrics adapter for repair cycle monitoring.

Implements IMetrics interface using Prometheus client library.
Provides detailed metrics for:
- Repair cycle execution (counts, durations, success rates)
- Test execution metrics (pass/fail counts, iterations)
- File fixing metrics (files fixed, iterations per file)
- Warning review metrics
- Per-agent repair cycle statistics
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from prometheus_client import Counter, Gauge, Histogram, Summary
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

from codetoreum.ports.output.metrics import IMetrics, MetricData

logger = logging.getLogger(__name__)

__all__ = [
    "PrometheusMetricsAdapter",
    "PROMETHEUS_AVAILABLE",
]


class PrometheusMetricsAdapter(IMetrics):
    """Prometheus-backed metrics adapter for repair cycle monitoring."""

    def __init__(self, namespace: str = "codetoreum", subsystem: str = "repair_cycle"):
        """
        Initialize Prometheus metrics adapter.

        Args:
            namespace: Prometheus metric namespace
            subsystem: Prometheus metric subsystem
        """
        if not PROMETHEUS_AVAILABLE:
            raise RuntimeError("prometheus_client library not installed")

        self.namespace = namespace
        self.subsystem = subsystem
        self._timers: Dict[str, float] = {}
        self._metrics_registry: Dict[str, Any] = {}

        # Initialize repair cycle metrics
        self._init_repair_cycle_metrics()

    def _init_repair_cycle_metrics(self) -> None:
        """Initialize all repair cycle-related Prometheus metrics."""
        prefix = f"{self.namespace}_{self.subsystem}"

        # Counters
        self._repair_cycles_started = Counter(
            f"{prefix}_started_total",
            "Total repair cycles started",
            ["agent_name", "stage_name"],
        )
        self._repair_cycles_completed = Counter(
            f"{prefix}_completed_total",
            "Total repair cycles completed",
            ["agent_name", "stage_name", "status"],
        )
        self._repair_cycles_successful = Counter(
            f"{prefix}_successful_total",
            "Total successful repair cycles",
            ["agent_name", "stage_name"],
        )
        self._repair_cycles_failed = Counter(
            f"{prefix}_failed_total",
            "Total failed repair cycles",
            ["agent_name", "stage_name", "reason"],
        )
        self._repair_cycles_fast_failed = Counter(
            f"{prefix}_fast_failed_total",
            "Total repair cycles fast-failed",
            ["agent_name", "reason"],
        )
        self._test_executions_total = Counter(
            f"{prefix}_test_executions_total",
            "Total test executions",
            ["test_type", "status"],
        )
        self._test_failures_total = Counter(
            f"{prefix}_test_failures_total",
            "Total test failures",
            ["test_type"],
        )
        self._files_fixed_total = Counter(
            f"{prefix}_files_fixed_total",
            "Total files fixed",
            ["file_extension"],
        )
        self._warnings_reviewed_total = Counter(
            f"{prefix}_warnings_reviewed_total",
            "Total warnings reviewed",
            ["severity"],
        )

        # Gauges
        self._active_cycles = Gauge(
            f"{prefix}_active_count",
            "Number of active repair cycles",
            ["agent_name"],
        )
        self._max_iterations_reached = Gauge(
            f"{prefix}_max_iterations_reached_total",
            "Cycles reaching max iterations",
            ["test_type"],
        )

        # Histograms
        self._cycle_duration_histogram = Histogram(
            f"{prefix}_duration_seconds",
            "Repair cycle duration in seconds",
            ["agent_name", "status"],
            buckets=(1, 5, 10, 30, 60, 120, 300, 600, 900),
        )
        self._test_execution_duration_histogram = Histogram(
            f"{prefix}_test_execution_duration_seconds",
            "Test execution duration in seconds",
            ["test_type"],
            buckets=(1, 5, 10, 30, 60, 120, 300),
        )
        self._file_fix_duration_histogram = Histogram(
            f"{prefix}_file_fix_duration_seconds",
            "File fix duration in seconds",
            ["file_extension"],
            buckets=(5, 10, 30, 60, 120, 300, 600),
        )
        self._iterations_histogram = Histogram(
            f"{prefix}_iterations_count",
            "Iterations needed per cycle",
            ["test_type", "status"],
            buckets=(1, 2, 3, 5, 10, 20),
        )

        # Summaries
        self._agent_calls_summary = Summary(
            f"{prefix}_agent_calls_per_cycle",
            "Agent calls per repair cycle",
            ["agent_name"],
        )
        self._files_fixed_per_cycle_summary = Summary(
            f"{prefix}_files_fixed_per_cycle",
            "Files fixed per repair cycle",
            ["agent_name"],
        )

        # Register metrics for later retrieval
        self._metrics_registry.update({
            f"{prefix}_started_total": self._repair_cycles_started,
            f"{prefix}_completed_total": self._repair_cycles_completed,
            f"{prefix}_successful_total": self._repair_cycles_successful,
            f"{prefix}_failed_total": self._repair_cycles_failed,
            f"{prefix}_fast_failed_total": self._repair_cycles_fast_failed,
            f"{prefix}_test_executions_total": self._test_executions_total,
            f"{prefix}_test_failures_total": self._test_failures_total,
            f"{prefix}_files_fixed_total": self._files_fixed_total,
            f"{prefix}_warnings_reviewed_total": self._warnings_reviewed_total,
            f"{prefix}_active_count": self._active_cycles,
            f"{prefix}_max_iterations_reached_total": self._max_iterations_reached,
            f"{prefix}_duration_seconds": self._cycle_duration_histogram,
            f"{prefix}_test_execution_duration_seconds": self._test_execution_duration_histogram,
            f"{prefix}_file_fix_duration_seconds": self._file_fix_duration_histogram,
            f"{prefix}_iterations_count": self._iterations_histogram,
            f"{prefix}_agent_calls_per_cycle": self._agent_calls_summary,
            f"{prefix}_files_fixed_per_cycle": self._files_fixed_per_cycle_summary,
        })

        logger.info("Prometheus metrics adapter initialized with %d metrics", len(self._metrics_registry))

    async def increment_counter(
        self,
        name: str,
        value: int = 1,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Increment a counter metric.

        Args:
            name: Metric name
            value: Amount to increment by
            labels: Optional labels/tags
        """
        try:
            metric = self._metrics_registry.get(name)
            if metric and hasattr(metric, "labels"):
                if labels:
                    metric.labels(**labels).inc(value)
                else:
                    metric.inc(value)
            else:
                logger.warning(f"Counter metric not found: {name}")
        except Exception as e:
            logger.error(f"Error incrementing counter {name}: {e}", exc_info=True)

    async def set_gauge(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Set a gauge metric.

        Args:
            name: Metric name
            value: Gauge value
            labels: Optional labels/tags
        """
        try:
            metric = self._metrics_registry.get(name)
            if metric and hasattr(metric, "labels"):
                if labels:
                    metric.labels(**labels).set(value)
                else:
                    metric.set(value)
            else:
                logger.warning(f"Gauge metric not found: {name}")
        except Exception as e:
            logger.error(f"Error setting gauge {name}: {e}", exc_info=True)

    async def record_histogram(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Record a histogram value.

        Args:
            name: Metric name
            value: Value to record
            labels: Optional labels/tags
        """
        try:
            metric = self._metrics_registry.get(name)
            if metric and hasattr(metric, "labels"):
                if labels:
                    metric.labels(**labels).observe(value)
                else:
                    metric.observe(value)
            else:
                logger.warning(f"Histogram metric not found: {name}")
        except Exception as e:
            logger.error(f"Error recording histogram {name}: {e}", exc_info=True)

    async def record_summary(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Record a summary value.

        Args:
            name: Metric name
            value: Value to record
            labels: Optional labels/tags
        """
        try:
            metric = self._metrics_registry.get(name)
            if metric and hasattr(metric, "labels"):
                if labels:
                    metric.labels(**labels).observe(value)
                else:
                    metric.observe(value)
            else:
                logger.warning(f"Summary metric not found: {name}")
        except Exception as e:
            logger.error(f"Error recording summary {name}: {e}", exc_info=True)

    async def start_timer(self, name: str) -> str:
        """
        Start a timer.

        Args:
            name: Timer name

        Returns:
            str: Timer ID
        """
        timer_id = f"{name}_{id(self)}_{datetime.utcnow().timestamp()}"
        self._timers[timer_id] = datetime.utcnow().timestamp()
        return timer_id

    async def stop_timer(
        self,
        timer_id: str,
        labels: Optional[Dict[str, str]] = None,
    ) -> float:
        """
        Stop a timer and record duration.

        Args:
            timer_id: Timer ID from start_timer
            labels: Optional labels/tags

        Returns:
            float: Duration in seconds
        """
        if timer_id not in self._timers:
            logger.warning(f"Timer not found: {timer_id}")
            return 0.0

        start_time = self._timers.pop(timer_id)
        duration = datetime.utcnow().timestamp() - start_time

        return duration

    async def record_duration(
        self,
        name: str,
        duration_seconds: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Record a duration metric.

        Args:
            name: Metric name
            duration_seconds: Duration in seconds
            labels: Optional labels/tags
        """
        await self.record_histogram(name, duration_seconds, labels)

    async def record_custom_metric(
        self,
        name: str,
        value: Any,
        metric_type: str,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Record a custom metric.

        Args:
            name: Metric name
            value: Metric value
            metric_type: Type of metric (counter, gauge, histogram, etc.)
            labels: Optional labels/tags
        """
        if metric_type == "counter":
            await self.increment_counter(name, int(value), labels)
        elif metric_type == "gauge":
            await self.set_gauge(name, float(value), labels)
        elif metric_type in ("histogram", "summary"):
            await self.record_histogram(name, float(value), labels)
        else:
            logger.warning(f"Unknown metric type: {metric_type}")

    async def query_metrics(
        self,
        name: str,
        start_time: datetime,
        end_time: datetime,
        labels: Optional[Dict[str, str]] = None,
        aggregation: Optional[str] = None,
    ) -> List[MetricData]:
        """
        Query metric data.

        Note: Prometheus adapter provides point-in-time metrics.
        For full time-series queries, use Prometheus HTTP API directly.

        Args:
            name: Metric name
            start_time: Start of time range
            end_time: End of time range
            labels: Optional label filters
            aggregation: Optional aggregation (sum, avg, min, max)

        Returns:
            List[MetricData]: List of metric data points
        """
        # Prometheus client library doesn't provide query capabilities
        # Use Prometheus HTTP API for time-series queries
        logger.warning(
            f"query_metrics not implemented for Prometheus adapter. "
            "Use Prometheus HTTP API /api/v1/query_range instead."
        )
        return []

    async def get_metric_names(self, prefix: Optional[str] = None) -> List[str]:
        """
        Get list of metric names.

        Args:
            prefix: Optional prefix filter

        Returns:
            List[str]: List of metric names
        """
        names = list(self._metrics_registry.keys())
        if prefix:
            names = [n for n in names if n.startswith(prefix)]
        return sorted(names)

    async def get_label_values(
        self,
        label_name: str,
        metric_name: Optional[str] = None,
    ) -> List[str]:
        """
        Get all values for a label.

        Args:
            label_name: Label name
            metric_name: Optional metric name filter

        Returns:
            List[str]: List of label values
        """
        # Prometheus client library doesn't expose label values
        # Use Prometheus HTTP API for this
        logger.warning(
            f"get_label_values not implemented for Prometheus adapter. "
            "Use Prometheus HTTP API /api/v1/label/{label_name}/values instead."
        )
        return []

    async def delete_metric(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Delete a metric or metric series.

        Note: Prometheus client library doesn't support deletion.
        Metrics are managed by Prometheus server retention policies.

        Args:
            name: Metric name
            labels: Optional labels to delete specific series
        """
        logger.warning(
            f"delete_metric not supported for Prometheus adapter. "
            "Metrics are managed by Prometheus retention policies."
        )

    async def get_statistics(
        self,
        name: str,
        start_time: datetime,
        end_time: datetime,
        labels: Optional[Dict[str, str]] = None,
    ) -> Dict[str, float]:
        """
        Get statistics for a metric.

        Args:
            name: Metric name
            start_time: Start of time range
            end_time: End of time range
            labels: Optional label filters

        Returns:
            Dict[str, float]: Statistics (min, max, avg, sum, count)
        """
        logger.warning(
            f"get_statistics not fully implemented for Prometheus adapter. "
            "Use Prometheus HTTP API /api/v1/query_range for historical data."
        )
        return {}

    async def record_batch(
        self,
        metrics: List[Dict[str, Any]],
    ) -> None:
        """
        Record multiple metrics in a batch.

        Args:
            metrics: List of metric definitions with name, value, type, labels
        """
        for metric in metrics:
            try:
                name = metric.get("name")
                value = metric.get("value")
                metric_type = metric.get("type", "gauge")
                labels = metric.get("labels")

                await self.record_custom_metric(name, value, metric_type, labels)
            except Exception as e:
                logger.error(f"Error recording batch metric: {e}", exc_info=True)

    async def flush(self) -> None:
        """Flush any buffered metrics."""
        # Prometheus client handles flushing automatically
        logger.debug("Prometheus metrics flushed (no-op)")

    async def health_check(self) -> bool:
        """
        Check metrics system health.

        Returns:
            bool: True if healthy
        """
        try:
            # Verify we can access the metrics registry
            return len(self._metrics_registry) > 0
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return False
