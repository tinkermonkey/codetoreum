# Repair Cycle Monitoring & Observability

Complete metrics and monitoring infrastructure for the repair cycle system with Prometheus, Grafana, OpenTelemetry, and comprehensive logging.

## Quick Links

### Implementation Files

**Core Infrastructure**:
- [`src/codetoreum/adapters/secondary/prometheus_metrics_adapter.py`](../../src/codetoreum/adapters/secondary/prometheus_metrics_adapter.py) - Prometheus metrics adapter
- [`src/codetoreum/infrastructure/repair_cycle_metrics_collector.py`](../../src/codetoreum/infrastructure/repair_cycle_metrics_collector.py) - Event-driven metrics collection
- [`src/codetoreum/infrastructure/repair_cycle_logging.py`](../../src/codetoreum/infrastructure/repair_cycle_logging.py) - Structured logging
- [`src/codetoreum/infrastructure/repair_cycle_tracing.py`](../../src/codetoreum/infrastructure/repair_cycle_tracing.py) - OpenTelemetry tracing
- [`src/codetoreum/infrastructure/repair_cycle_profiling.py`](../../src/codetoreum/infrastructure/repair_cycle_profiling.py) - Performance profiling

**Testing**:
- [`tests/test_repair_cycle_monitoring.py`](../../tests/test_repair_cycle_monitoring.py) - Comprehensive test suite

### Configuration & Documentation

**Dashboards & Alerting**:
- [`repair_cycle_grafana_dashboard.json`](repair_cycle_grafana_dashboard.json) - Grafana dashboard definition
- [`repair_cycle_alerting_rules.yaml`](repair_cycle_alerting_rules.yaml) - Prometheus alerting rules

**Guides & Documentation**:
- [`repair_cycle_monitoring_guide.md`](repair_cycle_monitoring_guide.md) - Complete setup and usage guide
- [`IMPLEMENTATION_SUMMARY.md`](IMPLEMENTATION_SUMMARY.md) - Detailed implementation overview

## Features

### ✅ Prometheus Metrics
- 17+ repair cycle-specific metrics
- Counters, gauges, histograms, and summaries
- Multi-dimensional labels for analysis
- Full async/await support

### ✅ Event-Driven Collection
- Automatic metric aggregation from domain events
- Per-agent breakdown
- Real-time aggregation
- Optional backend integration

### ✅ Structured Logging
- Correlation ID propagation
- Context-rich log formatting
- Performance logging with aggregation
- Error tracking and categorization

### ✅ Distributed Tracing
- OpenTelemetry integration
- Optional Jaeger export
- Span hierarchy for cycle stages
- Exception tracking in spans

### ✅ Performance Profiling
- Memory and CPU tracking
- Bottleneck identification
- Threshold-based alerts
- Performance reports

### ✅ Grafana Dashboards
- 15-panel comprehensive dashboard
- Real-time metrics updates
- Per-agent and per-test-type analysis
- Success rate, duration, and efficiency views

### ✅ Alerting Rules
- 25+ Prometheus alerting rules
- Multi-severity alerts (critical/warning/info)
- Fast-fail detection
- Performance anomalies
- Infrastructure health

## Architecture

```
┌─────────────────────────────────────────┐
│       Repair Cycle Execution            │
├─────────────────────────────────────────┤
│  Domain Events (RepairCycleStartedEvent)
└──────────────────┬──────────────────────┘
                   │
    ┌──────────────┼──────────────┐
    ▼              ▼              ▼
┌─────────┐ ┌─────────┐ ┌──────────────┐
│Metrics  │ │Logging  │ │  Tracing     │
│Collector│ │         │ │              │
└─────────┘ └─────────┘ └──────────────┘
    │              │            │
    ▼              ▼            ▼
┌──────────┐ ┌────────┐ ┌──────────────┐
│Prometheus│ │Log     │ │ OpenTelemetry│
│          │ │Files   │ │ (Jaeger)     │
└──────────┘ └────────┘ └──────────────┘
    │              │            │
    ▼              ▼            ▼
┌──────────┐ ┌──────────┐ ┌──────────────┐
│Grafana   │ │ELK Stack │ │ Jaeger UI    │
│Dashboards│ │(logs)    │ │              │
└──────────┘ └──────────┘ └──────────────┘
```

## Getting Started

### 1. Install Dependencies

```bash
# Optional: Prometheus metrics
pip install prometheus-client

# Optional: OpenTelemetry tracing
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-jaeger

# Optional: Performance profiling
pip install psutil
```

### 2. Initialize Monitoring

```python
from codetoreum.infrastructure.repair_cycle_metrics_collector import RepairCycleMetricsCollector

# Basic usage (in-memory metrics)
collector = RepairCycleMetricsCollector(event_bus=event_bus)

# With Prometheus backend
from codetoreum.adapters.secondary.prometheus_metrics_adapter import PrometheusMetricsAdapter

prometheus = PrometheusMetricsAdapter()
collector = RepairCycleMetricsCollector(event_bus=event_bus, metrics_backend=prometheus)
```

### 3. View Metrics

**In-Memory**:
```python
metrics = collector.get_metrics()
print(f"Success rate: {metrics.get_success_rate_percent()}%")
```

**Prometheus**:
```
# Visit http://localhost:9090/graph
# Query: codetoreum_repair_cycle_success_rate_percent
```

**Grafana**:
```
# Import dashboard from repair_cycle_grafana_dashboard.json
# Visit http://localhost:3000/d/repair-cycle-monitoring
```

## Key Metrics

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `repair_cycle_started_total` | Counter | agent_name, stage_name | Track cycle initiation |
| `repair_cycle_completed_total` | Counter | agent_name, stage_name, status | Track completion |
| `repair_cycle_successful_total` | Counter | agent_name, stage_name | Track successes |
| `repair_cycle_duration_seconds` | Histogram | agent_name, status | Measure performance |
| `test_executions_total` | Counter | test_type, status | Track test runs |
| `test_failures_total` | Counter | test_type | Track test failures |
| `files_fixed_total` | Counter | agent_name, file_extension | Track file fixes |
| `warnings_reviewed_total` | Counter | agent_name, severity | Track warnings |
| `agent_calls_per_cycle` | Summary | agent_name | Measure efficiency |
| `active_count` | Gauge | agent_name | Track concurrency |

## Alerts

**Critical**:
- `RepairCycleCriticalFailureRate` - Success rate < 50%
- `RepairCycleDurationCritical` - Duration > 20 minutes
- `MaxAgentCallsExceeded` - Max calls exceeded frequently
- `StuckRepairCycle` - No completions in 60+ minutes
- `RepairCycleMetricsUnavailable` - Metrics service down

**Warning**:
- `RepairCycleSuccessRateLow` - Success rate < 70%
- `RepairCycleDurationHigh` - Duration > 10 minutes
- `TestExecutionFailureRate` - Failure rate > 50%
- `FileFixDurationHigh` - Fix duration > 2 minutes
- `HighNumberOfActiveCycles` - > 20 active cycles

## Configuration

### Prometheus Scrape Job

```yaml
scrape_configs:
  - job_name: 'repair_cycle'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
    scrape_interval: 15s
```

### Alertmanager Rules

```yaml
rule_files:
  - 'repair_cycle_alerting_rules.yaml'
```

### Jaeger Exporter

```python
tracer = RepairCycleTracer(
    service_name="codetoreum",
    jaeger_host="localhost",
    jaeger_port=6831,
)
```

## Monitoring Dashboard

The Grafana dashboard includes:

1. **Overview Panels** (top row)
   - Success rate gauge
   - Total cycles
   - Active cycles
   - Fast failures count

2. **Performance Panels** (middle rows)
   - Cycle duration trends (p50, p95)
   - Cycles by status (pie chart)
   - Test execution distribution
   - Agent efficiency metrics

3. **Detailed Analytics** (bottom rows)
   - Test failures by type
   - File fix statistics
   - Warning review metrics
   - Per-agent success rates

## Troubleshooting

### Missing Metrics

1. **Check event bus**: Ensure events are being emitted
2. **Check adapter**: Verify metrics adapter is initialized
3. **Check Prometheus**: Confirm scrape job is running
4. **Check firewall**: Allow Prometheus access

### High Memory Usage

1. **Review cardinality**: Check for unbounded label values
2. **Check retention**: Prometheus retention setting
3. **Monitor profiler**: Disable profiling if not needed

### Slow Queries

1. **Use time windows**: Don't query too large ranges
2. **Add filters**: Use labels to reduce query scope
3. **Downsample**: Use aggregation rules for long-term storage

## Performance Impact

- **Memory**: ~15-60MB for metrics/logging/tracing
- **CPU**: < 5% overhead during typical execution
- **Network**: ~100-200KB per minute for exports

## Best Practices

1. **Correlation IDs**: Always propagate for distributed tracing
2. **Label Cardinality**: Avoid high-cardinality labels
3. **Alert Tuning**: Baseline measurements before setting thresholds
4. **Log Rotation**: Configure for disk space management
5. **Retention Policy**: Keep metrics for 15+ days minimum

## Support & Troubleshooting

See [`repair_cycle_monitoring_guide.md`](repair_cycle_monitoring_guide.md) for:
- Complete setup instructions
- Detailed troubleshooting
- Log aggregation setup
- Performance analysis
- Best practices

## References

- [Implementation Summary](IMPLEMENTATION_SUMMARY.md)
- [Monitoring Guide](repair_cycle_monitoring_guide.md)
- [Prometheus Docs](https://prometheus.io/docs/)
- [Grafana Docs](https://grafana.com/docs/)
- [OpenTelemetry Docs](https://opentelemetry.io/docs/)
- [Jaeger Docs](https://www.jaegertracing.io/docs/)

## Files Created

### Core Implementation (5 files)
- ✅ Prometheus metrics adapter
- ✅ Metrics collector with event subscription
- ✅ Structured logging system
- ✅ OpenTelemetry tracing
- ✅ Performance profiling

### Configuration (2 files)
- ✅ Grafana dashboard (15 panels)
- ✅ Prometheus alerting rules (25+ alerts)

### Documentation (3 files)
- ✅ Setup guide (300+ lines)
- ✅ Implementation summary (400+ lines)
- ✅ README (this file)

### Testing (1 file)
- ✅ Comprehensive test suite (25+ tests)

**Total**: 11 files, 2000+ lines of implementation and documentation
