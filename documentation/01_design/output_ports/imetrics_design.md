# IMetrics Output Port Design

## Overview

The `IMetrics` port provides an abstraction for metrics collection and reporting. This port enables observability and performance monitoring across the system.

## Port Interface

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

class IMetrics(ABC):
    """Interface for metrics collection."""

    @abstractmethod
    async def increment_counter(self,
                               name: str,
                               value: int = 1,
                               labels: Optional[Dict[str, str]] = None) -> None:
        """Increment a counter metric."""
        pass

    @abstractmethod
    async def set_gauge(self,
                       name: str,
                       value: float,
                       labels: Optional[Dict[str, str]] = None) -> None:
        """Set a gauge metric."""
        pass

    @abstractmethod
    async def record_histogram(self,
                              name: str,
                              value: float,
                              labels: Optional[Dict[str, str]] = None) -> None:
        """Record a histogram value."""
        pass

    @abstractmethod
    async def start_timer(self, name: str) -> str:
        """Start a timer. Returns timer ID."""
        pass

    @abstractmethod
    async def stop_timer(self,
                        timer_id: str,
                        labels: Optional[Dict[str, str]] = None) -> float:
        """Stop a timer. Returns duration in seconds."""
        pass

    @abstractmethod
    async def record_custom_metric(self,
                                   name: str,
                                   value: Any,
                                   metric_type: str,
                                   labels: Optional[Dict[str, str]] = None) -> None:
        """Record a custom metric."""
        pass

    @abstractmethod
    async def query_metrics(self,
                           name: str,
                           start_time: datetime,
                           end_time: datetime,
                           labels: Optional[Dict[str, str]] = None) -> List[MetricData]:
        """Query metric data."""
        pass
```

## Data Models

```python
@dataclass
class MetricData:
    """Metric data point."""
    timestamp: datetime
    name: str
    value: float
    labels: Dict[str, str]
    metric_type: str
```

## Adapter Implementations

### Elasticsearch Metrics

```python
class ElasticsearchMetrics(IMetrics):
    """Elasticsearch-based metrics."""

    def __init__(self, es_client, index_prefix: str = "metrics"):
        self.es = es_client
        self.index_prefix = index_prefix

    async def increment_counter(self,
                               name: str,
                               value: int = 1,
                               labels: Optional[Dict[str, str]] = None) -> None:
        """Store counter in Elasticsearch."""
        await self.es.index(
            index=f"{self.index_prefix}-{datetime.utcnow():%Y.%m.%d}",
            document={
                'timestamp': datetime.utcnow(),
                'name': name,
                'value': value,
                'type': 'counter',
                'labels': labels or {}
            }
        )
```

### In-Memory Metrics (Testing)

```python
class InMemoryMetrics(IMetrics):
    """In-memory metrics for testing."""

    def __init__(self):
        self.counters: Dict[str, int] = {}
        self.gauges: Dict[str, float] = {}
        self.histograms: Dict[str, List[float]] = {}
        self.timers: Dict[str, datetime] = {}

    async def increment_counter(self,
                               name: str,
                               value: int = 1,
                               labels: Optional[Dict[str, str]] = None) -> None:
        """Increment in-memory counter."""
        key = self._make_key(name, labels)
        self.counters[key] = self.counters.get(key, 0) + value
```

## Common Metrics

### Agent Execution
- `agent.execution.count` (counter)
- `agent.execution.duration` (histogram)
- `agent.execution.tokens` (histogram)
- `agent.execution.errors` (counter)

### Work Items
- `workitem.created` (counter)
- `workitem.completed` (counter)
- `workitem.age` (gauge)

### System Resources
- `container.count` (gauge)
- `container.cpu_usage` (gauge)
- `container.memory_usage` (gauge)

## Integration Points

### Used By
- All Application Services
- Monitoring Dashboard
- Alerting System

### Dependencies
- None (standalone port)

## Implementation Notes

1. **Batching**: Batch metrics for better performance
2. **Cardinality**: Limit label cardinality to prevent explosion
3. **Sampling**: Sample high-frequency metrics
4. **Retention**: Configure appropriate retention policies
5. **Alerting**: Integrate with alerting systems
