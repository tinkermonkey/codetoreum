"""IMetrics output port interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any

from codetoreum.domain.types import MetricName

# ============================================================================
# Data Models
# ============================================================================


@dataclass(frozen=True)
class MetricData:
    """Metric data point.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation. Labels dict is converted
    to MappingProxyType for immutability.
    """

    timestamp: datetime
    name: MetricName
    value: float
    labels: MappingProxyType
    metric_type: str  # counter, gauge, histogram, summary

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not isinstance(self.timestamp, datetime):
            msg = "timestamp must be a datetime instance"
            raise ValueError(msg)

        if not isinstance(self.name, str) or not self.name:
            msg = "name must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.value, (int, float)):
            msg = "value must be a number"
            raise ValueError(msg)

        if not isinstance(self.labels, MappingProxyType):
            msg = "labels must be a MappingProxyType"
            raise ValueError(msg)

        for k, v in self.labels.items():
            if not isinstance(k, str) or not isinstance(v, str):
                msg = "all label keys and values must be strings"
                raise ValueError(msg)

        if self.metric_type not in ("counter", "gauge", "histogram", "summary"):
            msg = f"metric_type must be one of: counter, gauge, histogram, summary. Got: {self.metric_type}"
            raise ValueError(msg)


# ============================================================================
# Port Interface
# ============================================================================


class IMetrics(ABC):
    """Interface for metrics collection."""

    @abstractmethod
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
            MetricsError: Recording failed
        """

    @abstractmethod
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
            MetricsError: Recording failed
        """

    @abstractmethod
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
            MetricsError: Recording failed
        """

    @abstractmethod
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
            MetricsError: Recording failed
        """

    @abstractmethod
    async def start_timer(self, name: str) -> str:
        """
        Start a timer.

        Args:
            name: Timer name

        Returns:
            str: Timer ID

        Raises:
            MetricsError: Timer creation failed
        """

    @abstractmethod
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
            MetricsError: Recording failed
        """

    @abstractmethod
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
            MetricsError: Recording failed
        """

    @abstractmethod
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
            MetricsError: Recording failed
        """

    @abstractmethod
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
            MetricsError: Query failed
        """

    @abstractmethod
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

        Raises:
            MetricsError: Query failed
        """

    @abstractmethod
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

        Raises:
            MetricsError: Query failed
        """

    @abstractmethod
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
            MetricsError: Delete failed
        """

    @abstractmethod
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
            MetricsError: Query failed
        """

    @abstractmethod
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
            MetricsError: Batch recording failed
        """

    @abstractmethod
    async def flush(self) -> None:
        """
        Flush any buffered metrics.

        Raises:
            MetricsError: Flush failed
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check metrics system health.

        Returns:
            bool: True if healthy

        Raises:
            MetricsError: Health check failed
        """
