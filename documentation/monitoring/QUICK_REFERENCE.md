# Repair Cycle Monitoring - Quick Reference

## Files Created

### Core Implementation

| File | Purpose | Lines |
|------|---------|-------|
| `prometheus_metrics_adapter.py` | Prometheus metrics collection | 380 |
| `repair_cycle_metrics_collector.py` | Event-driven metrics aggregation | 520 |
| `repair_cycle_logging.py` | Structured logging with context | 450 |
| `repair_cycle_tracing.py` | OpenTelemetry distributed tracing | 420 |
| `repair_cycle_profiling.py` | Performance profiling & analysis | 480 |

### Configuration & Dashboards

| File | Purpose |
|------|---------|
| `repair_cycle_grafana_dashboard.json` | 15-panel Grafana dashboard |
| `repair_cycle_alerting_rules.yaml` | 25+ Prometheus alerting rules |

### Documentation

| File | Purpose | Lines |
|------|---------|-------|
| `repair_cycle_monitoring_guide.md` | Complete setup & usage guide | 400+ |
| `IMPLEMENTATION_SUMMARY.md` | Detailed implementation overview | 400+ |
| `README.md` | Quick start & overview | 300+ |
| `QUICK_REFERENCE.md` | This file |

### Testing

| File | Purpose | Tests |
|------|---------|-------|
| `test_repair_cycle_monitoring.py` | Comprehensive test suite | 25+ |

## Quick Start

### 1. Basic Metrics Collection

```python
from codetoreum.infrastructure.repair_cycle_metrics_collector import RepairCycleMetricsCollector

collector = RepairCycleMetricsCollector(event_bus=event_bus)
metrics = collector.get_metrics()
print(f"Success rate: {metrics.get_success_rate_percent()}%")
```

### 2. With Prometheus

```python
from codetoreum.adapters.secondary.prometheus_metrics_adapter import PrometheusMetricsAdapter

prometheus = PrometheusMetricsAdapter()
collector = RepairCycleMetricsCollector(event_bus=event_bus, metrics_backend=prometheus)
```

### 3. Structured Logging

```python
from codetoreum.infrastructure.repair_cycle_logging import RepairCycleLoggingContext, RepairCycleLogContext

context = RepairCycleLogContext(
    pipeline_run_id="run-123",
    stage_name="repair",
    agent_name="developer",
)
with RepairCycleLoggingContext(context) as ctx:
    with ctx.log_operation("test_execution"):
        # Your code here
        pass
```

### 4. Distributed Tracing

```python
from codetoreum.infrastructure.repair_cycle_tracing import get_repair_cycle_tracer

tracer = get_repair_cycle_tracer(jaeger_host="localhost")
with tracer.trace_cycle("repair_cycle"):
    with tracer.trace_test_execution("unit"):
        pass
```

### 5. Performance Profiling

```python
from codetoreum.infrastructure.repair_cycle_profiling import RepairCycleProfilerContext

profiler = RepairCycleProfilerContext()
with profiler.profile("test_execution"):
    pass
report = profiler.get_report()
```

## Key Metrics

### Success Rate
```promql
(codetoreum_repair_cycle_successful_total / codetoreum_repair_cycle_completed_total) * 100
```
Target: > 80%

### Average Duration
```promql
histogram_quantile(0.95, rate(codetoreum_repair_cycle_duration_seconds_bucket[5m]))
```
Target: < 600s (10 minutes)

### Agent Efficiency
```promql
codetoreum_repair_cycle_agent_calls_per_cycle
```
Target: < 2 calls per cycle

### Test Failure Rate
```promql
(codetoreum_repair_cycle_test_failures_total / codetoreum_repair_cycle_test_executions_total) * 100
```
Target: < 20%

### File Fix Success
```promql
(codetoreum_repair_cycle_files_fixed_total / codetoreum_repair_cycle_completed_total)
```
Target: > 80%

## Critical Alerts

| Alert | Threshold | Action |
|-------|-----------|--------|
| Success Rate Critical | < 50% | Investigate immediately |
| Duration Critical | > 20 min | Check performance |
| Max Calls Exceeded | > 5/hour | Review agent config |
| Cycles Stuck | 60+ min active | Manual intervention |
| Metrics Unavailable | Service down | Restart service |

## Setup Commands

### Prometheus

```bash
# Install prometheus_client
pip install prometheus-client

# Configure scrape job in prometheus.yml
scrape_configs:
  - job_name: 'repair_cycle'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
```

### Grafana

```bash
# Import dashboard
curl -X POST http://localhost:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -d @documentation/monitoring/repair_cycle_grafana_dashboard.json
```

### Jaeger

```bash
# Run Jaeger locally
docker run -d --name jaeger \
  -p 16686:16686 \
  -p 6831:6831/udp \
  jaegertracing/all-in-one:latest
```

### OpenTelemetry

```bash
# Install OTel
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-jaeger
```

## Log Format

```
[2025-11-04 10:30:00] INFO: Operation started | \
  pipeline_run_id=run-123 | \
  stage_name=repair | \
  agent_name=developer | \
  correlation_id=corr-456 | \
  duration_seconds=45.3
```

## Event Subscriptions

The metrics collector automatically subscribes to:

1. `REPAIR_CYCLE_STARTED` - Track initiation
2. `REPAIR_CYCLE_COMPLETED` - Track completion
3. `REPAIR_CYCLE_FAST_FAIL` - Track early termination
4. `REPAIR_CYCLE_TEST_EXECUTION_COMPLETED` - Track tests
5. `REPAIR_CYCLE_FILE_FIX_COMPLETED` - Track fixes
6. `REPAIR_CYCLE_WARNING_REVIEW_COMPLETED` - Track warnings

## Span Hierarchy (Tracing)

```
repair_cycle (root)
├── repair_cycle_stage.test_execution
│   └── test_execution.unit
├── repair_cycle_stage.file_fixing
│   ├── file_fix.main.py
│   └── agent_call.developer
└── repair_cycle_stage.warning_review
```

## Performance Thresholds

| Operation | Duration | Memory | CPU |
|-----------|----------|--------|-----|
| test_execution | 300s | 500MB | - |
| file_fix | 120s | 200MB | - |
| agent_call | 60s | 100MB | - |
| repair_cycle | 600s | 1000MB | - |

## Dashboard Panels

1. Success Rate (gauge)
2. Total Cycles (stat)
3. Active Cycles (stat)
4. Fast Failures (stat)
5. Duration Trends (graph)
6. Status Distribution (pie)
7. Test Execution Count (bar)
8. Agent Calls (graph)
9. Files Fixed (stat)
10. Test Failures (table)
11. Fast-Fail Reasons (table)
12. Test Duration (graph)
13. File Fix Duration (graph)
14. Warnings Reviewed (stat)
15. Per-Agent Success (table)

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| No metrics | Event bus not connected | Check event_bus parameter |
| Missing data | Collector not initialized | Initialize before cycle runs |
| High memory | High cardinality labels | Reduce label combinations |
| Slow queries | Large time range | Use shorter time windows |
| Missing logs | Log level too high | Set to DEBUG/INFO |

## Dependencies

**Required**:
- Python 3.11+
- Event bus
- Domain models

**Optional**:
- prometheus-client (metrics export)
- opentelemetry-api (tracing)
- opentelemetry-exporter-jaeger (Jaeger)
- psutil (performance profiling)

## Performance Impact

- **Memory**: 15-60MB
- **CPU**: < 5% overhead
- **Network**: 100-200KB/min

## Testing

```bash
# Run all monitoring tests
pytest tests/test_repair_cycle_monitoring.py -v

# Run specific test class
pytest tests/test_repair_cycle_monitoring.py::TestPrometheusMetricsAdapter -v

# With coverage
pytest tests/test_repair_cycle_monitoring.py --cov=src/codetoreum/infrastructure --cov=src/codetoreum/adapters/secondary
```

## Configuration Options

### Metrics Collector

```python
RepairCycleMetricsCollector(
    event_bus=event_bus,              # EventBus instance
    metrics_backend=prometheus,        # Optional IMetrics backend
)
```

### Prometheus Adapter

```python
PrometheusMetricsAdapter(
    namespace="codetoreum",            # Metric namespace
    subsystem="repair_cycle",          # Metric subsystem
)
```

### Tracer

```python
get_repair_cycle_tracer(
    service_name="codetoreum",         # Service name
    jaeger_host="localhost",           # Optional Jaeger host
    jaeger_port=6831,                  # Jaeger port
    enabled=True,                      # Enable tracing
)
```

### Profiler

```python
RepairCycleProfilerContext(
    enable_memory_tracking=True,       # Track memory
    enable_cpu_tracking=True,          # Track CPU
    threshold_monitoring=True,         # Check thresholds
)
```

## Documentation Links

- [Setup Guide](repair_cycle_monitoring_guide.md)
- [Implementation Summary](IMPLEMENTATION_SUMMARY.md)
- [README](README.md)
- [Test Suite](../../tests/test_repair_cycle_monitoring.py)

## Support

For detailed information, see the [Repair Cycle Monitoring Guide](repair_cycle_monitoring_guide.md).

For implementation details, see [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md).
