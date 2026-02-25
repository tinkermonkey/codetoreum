"""IMetrics output port interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from codetoreum.domain.types import MetricName

# ============================================================================
# Data Models
# ============================================================================


@dataclass
class MetricData:
    """Metric data point."""

    timestamp: datetime
    name: MetricName
    value: float
    labels: Dict[str, str]
    metric_type: str  # counter, gauge, histogram, summary


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
        labels: Optional[Dict[str, str]] = None,
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
        pass

    @abstractmethod
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

        Raises:
            ValidationError: Invalid metric name or labels
            MetricsError: Recording failed
        """
        pass

    @abstractmethod
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

        Raises:
            ValidationError: Invalid metric name or labels
            MetricsError: Recording failed
        """
        pass

    @abstractmethod
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

        Raises:
            ValidationError: Invalid metric name or labels
            MetricsError: Recording failed
        """
        pass

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
        pass

    @abstractmethod
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

        Raises:
            ResourceNotFoundError: Timer doesn't exist
            MetricsError: Recording failed
        """
        pass

    @abstractmethod
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

        Raises:
            ValidationError: Invalid metric name or duration
            MetricsError: Recording failed
        """
        pass

    @abstractmethod
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

        Raises:
            ValidationError: Invalid metric configuration
            MetricsError: Recording failed
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    async def get_metric_names(
        self,
        prefix: Optional[str] = None,
    ) -> List[str]:
        """
        Get list of metric names.

        Args:
            prefix: Optional prefix filter

        Returns:
            List[str]: List of metric names

        Raises:
            MetricsError: Query failed
        """
        pass

    @abstractmethod
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

        Raises:
            MetricsError: Query failed
        """
        pass

    @abstractmethod
    async def delete_metric(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
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
        pass

    @abstractmethod
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

        Raises:
            ResourceNotFoundError: Metric doesn't exist
            MetricsError: Query failed
        """
        pass

    @abstractmethod
    async def record_batch(
        self,
        metrics: List[Dict[str, Any]],
    ) -> None:
        """
        Record multiple metrics in a batch.

        Args:
            metrics: List of metric definitions with name, value, type, labels

        Raises:
            ValidationError: Invalid metric data
            MetricsError: Batch recording failed
        """
        pass

    @abstractmethod
    async def flush(self) -> None:
        """
        Flush any buffered metrics.

        Raises:
            MetricsError: Flush failed
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check metrics system health.

        Returns:
            bool: True if healthy

        Raises:
            MetricsError: Health check failed
        """
        pass
