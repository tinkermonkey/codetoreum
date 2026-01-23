# Repair Cycle Monitoring & Observability Guide

Comprehensive guide for monitoring and observability of the repair cycle system.

## Overview

The repair cycle monitoring system provides:

- **Metrics Collection**: Prometheus metrics for cycles, tests, and performance
- **Structured Logging**: Detailed logs with correlation IDs and context
- **Distributed Tracing**: OpenTelemetry integration for end-to-end tracing
- **Performance Profiling**: Detailed performance analysis and bottleneck identification
- **Alerting**: Prometheus alerting rules for failures and performance issues

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Repair Cycle Execution                     │
└─────────────────────────────────────────────────────────────┘
                            │
                ┌───────────┼───────────┐
                ▼           ▼           ▼
        ┌────────────┐ ┌──────────┐ ┌─────────────┐
        │ Metrics    │ │ Logging  │ │   Tracing   │
        │ Collector  │ │          │ │             │
        └────────────┘ └──────────┘ └─────────────┘
                │           │            │
        ┌───────┴───────┬───┴────┐      │
        ▼               ▼        ▼      ▼
    ┌────────────┐ ┌──────┐ ┌──────────────┐
    │Prometheus  │ │Logs  │ │ OpenTelemetry│
    │ Metrics    │ │      │ │ (Jaeger)     │
    └────────────┘ └──────┘ └──────────────┘
        │               │            │
        ▼               ▼            ▼
    ┌────────────┐ ┌──────────┐ ┌──────────────┐
    │ Grafana    │ │ ELK/     │ │ Jaeger UI    │
    │ Dashboards │ │ Splunk   │ │ (distributed │
    │            │ │ (logs)   │ │  trace view) │
    └────────────┘ └──────────┘ └──────────────┘
```

## Components

### 1. Prometheus Metrics Adapter

Provides Prometheus-compatible metrics collection.

**Location**: `src/codetoreum/adapters/secondary/prometheus_metrics_adapter.py`

**Key Metrics**:

```
# Cycle lifecycle
codetoreum_repair_cycle_started_total{agent_name, stage_name}
codetoreum_repair_cycle_completed_total{agent_name, stage_name, status}
codetoreum_repair_cycle_successful_total{agent_name, stage_name}
codetoreum_repair_cycle_failed_total{agent_name, stage_name, reason}
codetoreum_repair_cycle_fast_failed_total{agent_name, reason}

# Durations (histogram)
codetoreum_repair_cycle_duration_seconds{agent_name, status}
codetoreum_repair_cycle_test_execution_duration_seconds{test_type}
codetoreum_repair_cycle_file_fix_duration_seconds{file_extension}

# Test execution
codetoreum_repair_cycle_test_executions_total{test_type, status}
codetoreum_repair_cycle_test_failures_total{test_type}

# File fixing
codetoreum_repair_cycle_files_fixed_total{agent_name, file_extension}

# Warnings
codetoreum_repair_cycle_warnings_reviewed_total{agent_name, severity}

# Performance
codetoreum_repair_cycle_agent_calls_per_cycle{agent_name} (summary)
codetoreum_repair_cycle_active_count{agent_name} (gauge)
```

### 2. Repair Cycle Metrics Collector

Subscribes to domain events and aggregates metrics.

**Location**: `src/codetoreum/infrastructure/repair_cycle_metrics_collector.py`

**Features**:
- Event-driven metrics collection
- Per-agent breakdown
- Automatic aggregation
- Optional Prometheus backend

**Usage**:

```python
from codetoreum.infrastructure.repair_cycle_metrics_collector import RepairCycleMetricsCollector
from codetoreum.adapters.secondary.prometheus_metrics_adapter import PrometheusMetricsAdapter

metrics_backend = PrometheusMetricsAdapter()
collector = RepairCycleMetricsCollector(event_bus=event_bus, metrics_backend=metrics_backend)

# Metrics automatically collected from events
# Access collected metrics
metrics = collector.get_metrics()
print(f"Success rate: {metrics.get_success_rate_percent()}%")
```

### 3. Structured Logging

Provides structured, context-rich logging with correlation IDs.

**Location**: `src/codetoreum/infrastructure/repair_cycle_logging.py`

**Components**:

- `RepairCycleLogContext`: Container for structured logging context
- `RepairCycleLogger`: Main logger with context
- `RepairCyclePerformanceLogger`: Performance-specific logging
- `RepairCycleErrorLogger`: Error and failure tracking

**Usage**:

```python
from codetoreum.infrastructure.repair_cycle_logging import (
    RepairCycleLogContext,
    RepairCycleLogger,
    RepairCycleLoggingContext,
)

context = RepairCycleLogContext(
    pipeline_run_id="run-123",
    stage_name="repair",
    agent_name="developer",
    correlation_id="corr-456",
)

with RepairCycleLoggingContext(context) as ctx:
    with ctx.log_operation("test_execution", {"test_type": "unit"}):
        # Operation code here
        pass

# Logs will include:
# - pipeline_run_id for request tracing
# - correlation_id for distributed tracing
# - timing information
# - error details if exceptions occur
```

**Log Format**:

```
[2025-11-04 10:30:00] INFO: Test execution started | \
  pipeline_run_id=run-123 | \
  stage_name=repair | \
  agent_name=developer | \
  correlation_id=corr-456 | \
  test_type=unit
```

### 4. OpenTelemetry Tracing

Provides distributed tracing with optional Jaeger export.

**Location**: `src/codetoreum/infrastructure/repair_cycle_tracing.py`

**Features**:
- Automatic span creation for operations
- Span context propagation
- Exception recording
- Optional Jaeger integration

**Usage**:

```python
from codetoreum.infrastructure.repair_cycle_tracing import get_repair_cycle_tracer

tracer = get_repair_cycle_tracer(
    service_name="codetoreum",
    jaeger_host="localhost",  # Optional
    jaeger_port=6831,
)

# Trace cycle execution
with tracer.trace_cycle(
    "repair_cycle",
    {"agent_name": "developer", "stage_name": "repair"}
) as span:
    # Trace test execution
    with tracer.trace_test_execution("unit", iteration=1) as test_span:
        # Run tests
        pass

    # Trace file fixes
    with tracer.trace_file_fix("src/main.py") as file_span:
        # Fix file
        pass

tracer.shutdown()
```

**Span Hierarchy**:

```
repair_cycle (root span)
├── repair_cycle_stage.test_execution
│   └── test_execution.unit
├── repair_cycle_stage.file_fixing
│   ├── file_fix.main.py
│   └── agent_call.developer
└── repair_cycle_stage.warning_review
    └── ...
```

### 5. Performance Profiling

Detailed performance analysis with memory and CPU tracking.

**Location**: `src/codetoreum/infrastructure/repair_cycle_profiling.py`

**Features**:
- Operation timing
- Memory tracking (delta and peak)
- CPU usage monitoring
- Performance threshold alerts

**Usage**:

```python
from codetoreum.infrastructure.repair_cycle_profiling import (
    RepairCycleProfilerContext,
    PerformanceThresholdMonitor,
)

profiler_context = RepairCycleProfilerContext(
    enable_memory_tracking=True,
    enable_cpu_tracking=True,
    threshold_monitoring=True,
)

# Profile operations
with profiler_context.profile("test_execution", {"test_type": "unit"}):
    # Execute tests
    pass

with profiler_context.profile("file_fix", {"file_path": "src/main.py"}):
    # Fix file
    pass

# Get performance report
report = profiler_context.get_report()
print(f"Slowest operations: {report['slowest']}")
print(f"Memory-heavy operations: {report['heaviest']}")
print(f"CPU-intensive operations: {report['hottest']}")
print(f"Threshold violations: {report['violations']}")

profiler_context.shutdown()
```

## Setup & Configuration

### Prometheus Integration

1. **Install Prometheus client**:

```bash
pip install prometheus-client
```

2. **Configure Prometheus scrape job**:

```yaml
# /etc/prometheus/prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'repair_cycle'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
```

3. **Expose metrics endpoint**:

```python
from prometheus_client import generate_latest
from fastapi import FastAPI

app = FastAPI()

@app.get("/metrics")
def metrics():
    return generate_latest()
```

### Grafana Setup

1. **Import dashboard**:

```bash
# Load dashboard from JSON
curl -X POST http://localhost:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -d @documentation/monitoring/repair_cycle_grafana_dashboard.json
```

2. **Available dashboard**: `documentation/monitoring/repair_cycle_grafana_dashboard.json`

### Alerting Rules

1. **Install alerting rules**:

```bash
cp documentation/monitoring/repair_cycle_alerting_rules.yaml /etc/prometheus/rules/
```

2. **Configure Prometheus to load rules**:

```yaml
# /etc/prometheus/prometheus.yml
rule_files:
  - '/etc/prometheus/rules/repair_cycle_alerts.yaml'

alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - 'localhost:9093'
```

### OpenTelemetry/Jaeger Setup

1. **Install OpenTelemetry**:

```bash
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-jaeger
```

2. **Run Jaeger (Docker)**:

```bash
docker run -d --name jaeger \
  -e COLLECTOR_ZIPKIN_HTTP_PORT=9411 \
  -p 5775:5775/udp \
  -p 6831:6831/udp \
  -p 6832:6832/udp \
  -p 5778:5778 \
  -p 16686:16686 \
  -p 14268:14268 \
  -p 14250:14250 \
  jaegertracing/all-in-one:latest
```

3. **Access Jaeger UI**: http://localhost:16686

## Monitoring Dashboards

### Key Metrics to Monitor

1. **Success Rate**: Target > 80%
2. **Average Duration**: Target < 5 minutes (p95)
3. **Test Failure Rate**: Target < 20%
4. **Agent Efficiency**: Target < 2 calls per cycle
5. **File Fix Success**: Target > 80%

### Alerts

**Critical**:
- Success rate < 50%
- Cycles taking > 20 minutes
- Repeated max iteration exceeds
- Metrics unavailable

**Warning**:
- Success rate < 70%
- Cycles taking > 10 minutes
- High test failure rate
- Many fast-fails

See `repair_cycle_alerting_rules.yaml` for complete alerting configuration.

## Log Aggregation

### ELK Stack Setup

1. **Logstash configuration**:

```logstash
input {
  file {
    path => "/var/log/codetoreum/repair_cycle/*.log"
    start_position => "beginning"
  }
}

filter {
  grok {
    match => { "message" => "%{TIMESTAMP_ISO8601:timestamp} %{LOGLEVEL:level}: %{DATA:message} \| %{GREEDYDATA:context}" }
  }
  kv {
    source => "context"
    field_split => " \| "
    value_split => "="
  }
}

output {
  elasticsearch {
    hosts => ["localhost:9200"]
    index => "repair-cycle-%{+YYYY.MM.dd}"
  }
}
```

2. **Search queries**:

```
# Find all failures for an agent
agent_name:developer AND level:ERROR

# Track repair cycles by stage
stage_name:repair | stats count by overall_success

# Find slow operations
operation:test_execution AND duration_seconds > 300
```

## Distributed Tracing

### Jaeger UI Navigation

1. **Service Selection**: Select "codetoreum" service
2. **Trace View**: Shows complete repair cycle execution
3. **Latency Analysis**: Identify slow stages
4. **Error Tracking**: Find failed operations

### Trace Analysis

```
Example trace:
repair_cycle (1.2s total)
├── stage:test_execution (900ms)
│   └── test:unit (800ms) - FAILED
│       ├── test_execution (50ms)
│       └── agent_call:fix (750ms)
├── stage:file_fixing (250ms)
│   └── file_fix:main.py (200ms)
└── stage:warning_review (50ms)
```

## Performance Profiling

### Identifying Bottlenecks

1. **Slowest Operations**: Operations exceeding duration thresholds
2. **Memory Leaks**: Operations with increasing memory consumption
3. **CPU Hotspots**: Operations with high CPU usage

### Example Report

```python
{
  "summary": {
    "test_execution": {
      "count": 100,
      "avg_duration": 45.2,
      "min_duration": 20.5,
      "max_duration": 180.3,
      "avg_memory_delta_mb": 125.4
    }
  },
  "slowest": [
    {
      "operation": "test_execution",
      "duration_seconds": 180.3,
      "memory_delta_mb": 250.0
    }
  ],
  "violations": [
    {
      "operation": "test_execution",
      "violations": ["Duration threshold exceeded: 180.3s > 120s"]
    }
  ]
}
```

## Best Practices

1. **Correlation IDs**: Always propagate correlation IDs for distributed tracing
2. **Context Cardinality**: Avoid high-cardinality labels (e.g., don't use file paths as labels)
3. **Performance Thresholds**: Set realistic thresholds based on baseline measurements
4. **Alert Tuning**: Adjust alert thresholds to reduce false positives
5. **Log Retention**: Keep logs for 30 days minimum for analysis
6. **Metric Retention**: Configure Prometheus with 15-day retention for analysis

## Troubleshooting

### Missing Metrics

1. Check metrics adapter is initialized
2. Verify event bus is connected
3. Ensure metrics backend (Prometheus) is running
4. Check firewall rules for Prometheus scrape

### High Memory Usage

1. Review memory-heavy operations profile
2. Check for unbounded collections in metrics
3. Verify log rotation is configured

### Slow Query Performance

1. Use appropriate time windows in queries
2. Aggregate data before returning
3. Consider downsampling for long-term storage

## References

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)
- [Jaeger Documentation](https://www.jaegertracing.io/docs/)
