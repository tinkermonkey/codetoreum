"""In-memory metrics adapter for testing."""

import threading
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from codetoreum.ports.exceptions import (
    ResourceNotFoundError,
    ValidationError,
)
from codetoreum.ports.output.metrics import (
    IMetrics,
    MetricData,
)


class InMemoryMetricsAdapter(IMetrics):
    """
    In-memory metrics storage for testing.

    Stores all metrics in memory for querying and verification in tests.
    Supports all standard metric types: counters, gauges, histograms, summaries.

    This adapter is thread-safe for concurrent test execution. All shared
    state modifications are protected by a lock.

    Attributes:
        _metrics: Dictionary of metric name -> list of data points
        _timers: Dictionary of timer_id -> start time
        _counters: Dictionary tracking counter values
        _gauges: Dictionary tracking gauge values
    """

    def __init__(self):
        """Initialize the in-memory metrics adapter."""
        # All metrics data
        self._metrics: dict[str, list[MetricData]] = defaultdict(list)

        # Counters (accumulated values)
        self._counters: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        # Gauges (current values)
        self._gauges: dict[str, dict[str, float]] = defaultdict(dict)

        # Active timers (timer_id -> (timer_name, start_time))
        self._timers: dict[str, tuple[str, datetime]] = {}

        # Thread safety
        self._lock = threading.Lock()

    def _get_label_key(self, labels: dict[str, str] | None) -> str:
        """
        Generate a unique key for a set of labels.

        Args:
            labels: Label dictionary

        Returns:
            String key representing the labels
        """
        if not labels:
            return "__default__"
        return ",".join(f"{k}={v}" for k, v in sorted(labels.items()))

    def _validate_metric_name(self, name: str) -> None:
        """
        Validate metric name.

        Args:
            name: Metric name

        Raises:
            ValidationError: If name is invalid
        """
        if not name or not name.strip():
            raise ValidationError("Metric name cannot be empty")

    def _validate_labels(self, labels: dict[str, str] | None) -> None:
        """
        Validate labels dictionary.

        Args:
            labels: Labels to validate

        Raises:
            ValidationError: If labels are invalid
        """
        if labels is None:
            return

        if not isinstance(labels, dict):
            raise ValidationError("Labels must be a dictionary")

        for key, value in labels.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValidationError("Label keys and values must be strings")

    def _record_metric(
        self,
        name: str,
        value: float,
        metric_type: str,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Record a metric data point.

        Args:
            name: Metric name
            value: Metric value
            metric_type: Type of metric
            labels: Optional labels
        """
        labels = labels or {}
        data_point = MetricData(
            timestamp=datetime.now(UTC),
            name=name,
            value=value,
            labels=labels,
            metric_type=metric_type,
        )

        with self._lock:
            self._metrics[name].append(data_point)

    async def increment_counter(
        self,
        name: str,
        value: int = 1,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Increment a counter metric.

        Args:
            name: Metric name
            value: Amount to increment by
            labels: Optional labels/tags

        Raises:
            ValidationError: Invalid metric name or labels
        """
        self._validate_metric_name(name)
        self._validate_labels(labels)

        if value < 0:
            raise ValidationError("Counter increment value cannot be negative")

        label_key = self._get_label_key(labels)

        with self._lock:
            self._counters[name][label_key] += value

        self._record_metric(name, float(value), "counter", labels)

    async def set_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Set a gauge metric.

        Args:
            name: Metric name
            value: Gauge value
            labels: Optional labels/tags

        Raises:
            ValidationError: Invalid metric name or labels
        """
        self._validate_metric_name(name)
        self._validate_labels(labels)

        label_key = self._get_label_key(labels)

        with self._lock:
            self._gauges[name][label_key] = value

        self._record_metric(name, value, "gauge", labels)

    async def record_histogram(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Record a histogram value.

        Args:
            name: Metric name
            value: Value to record
            labels: Optional labels/tags

        Raises:
            ValidationError: Invalid metric name or labels
        """
        self._validate_metric_name(name)
        self._validate_labels(labels)

        self._record_metric(name, value, "histogram", labels)

    async def record_summary(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Record a summary value.

        Args:
            name: Metric name
            value: Value to record
            labels: Optional labels/tags

        Raises:
            ValidationError: Invalid metric name or labels
        """
        self._validate_metric_name(name)
        self._validate_labels(labels)

        self._record_metric(name, value, "summary", labels)

    async def start_timer(self, name: str) -> str:
        """
        Start a timer.

        Args:
            name: Timer name

        Returns:
            str: Timer ID

        Raises:
            ValidationError: If name is empty
        """
        if not name or not name.strip():
            raise ValidationError("Timer name cannot be empty")

        timer_id = str(uuid4())

        with self._lock:
            self._timers[timer_id] = (name, datetime.now(UTC))

        return timer_id

    async def stop_timer(
        self,
        timer_id: str,
        labels: dict[str, str] | None = None,
    ) -> float:
        """
        Stop a timer and record duration.

        Args:
            timer_id: Timer ID from start_timer
            labels: Optional labels/tags

        Returns:
            float: Duration in seconds

        Raises:
            ResourceNotFoundError: Timer doesn't exist
        """
        with self._lock:
            if timer_id not in self._timers:
                raise ResourceNotFoundError("Timer", timer_id)

            timer_name, start_time = self._timers.pop(timer_id)

        end_time = datetime.now(UTC)
        duration = (end_time - start_time).total_seconds()

        # Use the timer name from when it was started
        self._record_metric(timer_name, duration, "histogram", labels)

        return duration

    async def record_duration(
        self,
        name: str,
        duration_seconds: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Record a duration metric.

        Args:
            name: Metric name
            duration_seconds: Duration in seconds
            labels: Optional labels/tags

        Raises:
            ValidationError: Invalid metric name or duration
        """
        self._validate_metric_name(name)
        self._validate_labels(labels)

        if duration_seconds < 0:
            raise ValidationError("Duration cannot be negative")

        self._record_metric(name, duration_seconds, "histogram", labels)

    async def record_custom_metric(
        self,
        name: str,
        value: Any,
        metric_type: str,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Record a custom metric.

        Args:
            name: Metric name
            value: Metric value
            metric_type: Type of metric (counter, gauge, histogram, etc.)
            labels: Optional labels/tags

        Raises:
            ValidationError: Invalid metric configuration
        """
        self._validate_metric_name(name)
        self._validate_labels(labels)

        valid_types = {"counter", "gauge", "histogram", "summary"}
        if metric_type not in valid_types:
            raise ValidationError(f"Invalid metric type: {metric_type}. Must be one of {valid_types}")

        try:
            float_value = float(value)
        except (TypeError, ValueError):
            raise ValidationError(f"Metric value must be numeric, got {type(value)}")

        self._record_metric(name, float_value, metric_type, labels)

    async def query_metrics(
        self,
        name: str,
        start_time: datetime,
        end_time: datetime,
        labels: dict[str, str] | None = None,
        aggregation: str | None = None,
    ) -> list[MetricData]:
        """
        Query metric data.

        Args:
            name: Metric name
            start_time: Start of time range
            end_time: End of time range
            labels: Optional label filters
            aggregation: Optional aggregation (sum, avg, min, max)

        Returns:
            List[MetricData]: List of metric data points

        Raises:
            ValidationError: Invalid query parameters
        """
        self._validate_metric_name(name)
        self._validate_labels(labels)

        if start_time > end_time:
            raise ValidationError("start_time must be before end_time")

        with self._lock:
            if name not in self._metrics:
                return []

            # Filter by time range
            results = [
                m for m in self._metrics[name]
                if start_time <= m.timestamp <= end_time
            ]

            # Filter by labels if provided
            if labels:
                results = [
                    m for m in results
                    if all(m.labels.get(k) == v for k, v in labels.items())
                ]

            # Apply aggregation if requested
            if aggregation and results:
                values = [m.value for m in results]
                if aggregation == "sum":
                    agg_value = sum(values)
                elif aggregation == "avg":
                    agg_value = sum(values) / len(values)
                elif aggregation == "min":
                    agg_value = min(values)
                elif aggregation == "max":
                    agg_value = max(values)
                else:
                    raise ValidationError(f"Unknown aggregation: {aggregation}")

                # Return single aggregated result
                return [MetricData(
                    timestamp=results[-1].timestamp,
                    name=name,
                    value=agg_value,
                    labels=labels or {},
                    metric_type=results[0].metric_type,
                )]

            return results

    async def get_metric_names(
        self,
        prefix: str | None = None,
    ) -> list[str]:
        """
        Get list of metric names.

        Args:
            prefix: Optional prefix filter

        Returns:
            List[str]: List of metric names
        """
        with self._lock:
            names = list(self._metrics.keys())

        if prefix:
            names = [n for n in names if n.startswith(prefix)]

        return sorted(names)

    async def get_label_values(
        self,
        label_name: str,
        metric_name: str | None = None,
    ) -> list[str]:
        """
        Get all values for a label.

        Args:
            label_name: Label name
            metric_name: Optional metric name filter

        Returns:
            List[str]: List of label values
        """
        if not label_name:
            raise ValidationError("Label name cannot be empty")

        values = set()

        with self._lock:
            metrics_to_check = [metric_name] if metric_name else self._metrics.keys()

            for name in metrics_to_check:
                if name not in self._metrics:
                    continue

                for data_point in self._metrics[name]:
                    if label_name in data_point.labels:
                        values.add(data_point.labels[label_name])

        return sorted(list(values))

    async def delete_metric(
        self,
        name: str,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Delete a metric or metric series.

        Args:
            name: Metric name
            labels: Optional labels to delete specific series

        Raises:
            ResourceNotFoundError: Metric doesn't exist
        """
        self._validate_metric_name(name)

        with self._lock:
            if name not in self._metrics:
                raise ResourceNotFoundError("Metric", name)

            if labels:
                # Delete specific series
                self._metrics[name] = [
                    m for m in self._metrics[name]
                    if not all(m.labels.get(k) == v for k, v in labels.items())
                ]
                if not self._metrics[name]:
                    del self._metrics[name]
            else:
                # Delete entire metric
                del self._metrics[name]

            # Also clean up counters and gauges
            if name in self._counters:
                if labels:
                    label_key = self._get_label_key(labels)
                    if label_key in self._counters[name]:
                        del self._counters[name][label_key]
                else:
                    del self._counters[name]

            if name in self._gauges:
                if labels:
                    label_key = self._get_label_key(labels)
                    if label_key in self._gauges[name]:
                        del self._gauges[name][label_key]
                else:
                    del self._gauges[name]

    async def get_statistics(
        self,
        name: str,
        start_time: datetime,
        end_time: datetime,
        labels: dict[str, str] | None = None,
    ) -> dict[str, float]:
        """
        Get statistics for a metric.

        Args:
            name: Metric name
            start_time: Start of time range
            end_time: End of time range
            labels: Optional label filters

        Returns:
            Dict[str, float]: Statistics (min, max, avg, sum, count)

        Raises:
            ResourceNotFoundError: Metric doesn't exist
        """
        metrics = await self.query_metrics(name, start_time, end_time, labels)

        if not metrics:
            raise ResourceNotFoundError("Metric", name)

        values = [m.value for m in metrics]

        return {
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
            "sum": sum(values),
            "count": float(len(values)),
        }

    async def record_batch(
        self,
        metrics: list[dict[str, Any]],
    ) -> None:
        """
        Record multiple metrics in a batch.

        Args:
            metrics: List of metric definitions with name, value, type, labels

        Raises:
            ValidationError: Invalid metric data
        """
        if not metrics:
            raise ValidationError("Metrics list cannot be empty")

        for metric_def in metrics:
            if not isinstance(metric_def, dict):
                raise ValidationError("Each metric must be a dictionary")

            required_keys = {"name", "value", "type"}
            if not required_keys.issubset(metric_def.keys()):
                raise ValidationError(f"Metric must have keys: {required_keys}")

            await self.record_custom_metric(
                name=metric_def["name"],
                value=metric_def["value"],
                metric_type=metric_def["type"],
                labels=metric_def.get("labels"),
            )

    async def flush(self) -> None:
        """
        Flush any buffered metrics.

        For in-memory adapter, this is a no-op as all writes are immediate.
        """

    async def health_check(self) -> bool:
        """
        Check metrics system health.

        Returns:
            bool: Always True for in-memory adapter
        """
        return True

    # Helper methods for testing

    def clear(self) -> None:
        """Clear all metrics data."""
        with self._lock:
            self._metrics.clear()
            self._counters.clear()
            self._gauges.clear()
            self._timers.clear()

    def get_counter_value(
        self,
        name: str,
        labels: dict[str, str] | None = None,
    ) -> int:
        """
        Get current counter value.

        Args:
            name: Counter name
            labels: Optional labels

        Returns:
            Current counter value (0 if not found)
        """
        with self._lock:
            label_key = self._get_label_key(labels)
            return self._counters[name].get(label_key, 0)

    def get_gauge_value(
        self,
        name: str,
        labels: dict[str, str] | None = None,
    ) -> float | None:
        """
        Get current gauge value.

        Args:
            name: Gauge name
            labels: Optional labels

        Returns:
            Current gauge value (None if not found)
        """
        with self._lock:
            label_key = self._get_label_key(labels)
            return self._gauges[name].get(label_key)

    def get_metric_count(self, name: str) -> int:
        """
        Get number of data points for a metric.

        Args:
            name: Metric name

        Returns:
            Number of data points
        """
        with self._lock:
            return len(self._metrics.get(name, []))

    def get_all_metrics(self) -> dict[str, list[MetricData]]:
        """
        Get all metrics data.

        Returns:
            Dictionary of all metrics
        """
        with self._lock:
            return {k: list(v) for k, v in self._metrics.items()}
