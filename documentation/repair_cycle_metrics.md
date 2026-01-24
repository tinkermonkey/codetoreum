# Repair Cycle Metrics and Monitoring

This document describes the metrics and monitoring capabilities for the repair cycle feature in Codetoreum.

## Overview

Repair cycles are test-driven automated repair operations where agents iteratively run tests, identify failures, and fix code. Comprehensive metrics and monitoring have been added to track repair cycle execution, success rates, performance, and resource usage.

## Architecture

### Event-Driven Metrics Collection

Repair cycle metrics are collected through the event-driven architecture:

1. **Repair Cycle Events**: Domain events emitted during the repair cycle lifecycle
2. **Event Bus**: Pub/sub infrastructure that routes events to subscribers
3. **MetricsCollector**: Subscribes to repair cycle events and aggregates metrics
4. **REST API**: Exposes repair cycle metrics via `/api/v2/metrics/repair-cycles` endpoint

### Event Types

The following repair cycle events drive metrics collection:

| Event Type | When | Data Collected |
|-----------|------|---|
| `repair_cycle.started` | Cycle begins | Cycle started count |
| `repair_cycle.test_execution_completed` | Test run completes | Test type executions, test counts |
| `repair_cycle.file_fix_started` | File fix begins | File path, failure count |
| `repair_cycle.file_fix_completed` | File fix ends | Fixed status, iterations used |
| `repair_cycle.warning_review_started` | Warning review begins | Warning count |
| `repair_cycle.warning_review_completed` | Warning review ends | Warnings reviewed count |
| `repair_cycle.fast_fail` | Circuit breaker triggers | Fast-fail reason |
| `repair_cycle.completed` | Cycle finishes | Success status, durations, agent calls |

## Metrics Collected

### Overall Cycle Metrics

- **Cycles Started**: Total number of repair cycles started
- **Cycles Completed**: Total cycles that finished (success or failure)
- **Cycles Successful**: Cycles where all tests passed
- **Cycles Failed**: Cycles where tests failed after max iterations
- **Cycles Fast-Failed**: Cycles stopped by circuit breaker
- **Success Rate**: `(successful / completed) × 100`

### Duration Metrics

- **Average Duration**: Mean repair cycle duration in seconds
- **Min Duration**: Shortest repair cycle duration
- **Max Duration**: Longest repair cycle duration
- **Duration Distribution**: List of all cycle durations for statistical analysis

### Test Metrics (Per Test Type)

For each test type (unit, integration, e2e):

- **Total Executions**: Number of test runs for this type
- **Total Iterations**: Sum of all iterations across cycles
- **Average Iterations per Cycle**: `iterations / executions`

### File Fixing Metrics

- **Files Fixed Total**: Total number of files successfully fixed
- **Unique Files Fixed**: Count of distinct files that were repaired
- **Fixes Per File**: Count of how many times each file was fixed

### Agent Call Metrics

- **Average Agent Calls per Cycle**: Mean number of agent invocations per cycle
- **Total Agent Calls**: Sum of all agent executions across cycles

### Warning Metrics

- **Warnings Reviewed Total**: Total test warnings reviewed post-fix

### Per-Agent Metrics

Breakdown of metrics by agent:

- Cycles started/completed/successful/failed/fast-failed per agent
- Success rate per agent
- Agent-specific performance trends

## REST API Endpoint

### GET `/api/v2/metrics/repair-cycles`

Returns comprehensive repair cycle metrics for a given time range.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|---|
| `agent_name` | string | No | Filter metrics by specific agent |
| `start_time` | datetime | No | Start of time range (default: 1 hour ago) |
| `end_time` | datetime | No | End of time range (default: now) |

**Response Schema:**

```json
{
  "cycles_started": 10,
  "cycles_completed": 10,
  "cycles_successful": 8,
  "cycles_failed": 2,
  "cycles_fast_failed": 0,
  "overall_success_rate_percent": 80.0,
  "avg_duration_seconds": 45.5,
  "min_duration_seconds": 25.0,
  "max_duration_seconds": 120.0,
  "test_type_metrics": [
    {
      "test_type": "unit",
      "total_executions": 10,
      "total_iterations": 20,
      "avg_iterations_per_cycle": 2.0
    },
    {
      "test_type": "integration",
      "total_executions": 8,
      "total_iterations": 15,
      "avg_iterations_per_cycle": 1.875
    },
    {
      "test_type": "e2e",
      "total_executions": 5,
      "total_iterations": 10,
      "avg_iterations_per_cycle": 2.0
    }
  ],
  "avg_agent_calls_per_cycle": 1.8,
  "files_fixed_total": 4,
  "unique_files_fixed": 3,
  "warnings_reviewed_total": 12,
  "agent_metrics": [
    {
      "agent_name": "reviewer",
      "cycles_started": 10,
      "cycles_completed": 10,
      "cycles_successful": 8,
      "cycles_failed": 2,
      "cycles_fast_failed": 0,
      "success_rate_percent": 80.0
    }
  ],
  "start_time": "2025-01-23T18:00:00+00:00",
  "end_time": "2025-01-23T19:00:00+00:00"
}
```

**Example Requests:**

```bash
# Get last hour of metrics
curl http://localhost:8000/api/v2/metrics/repair-cycles \
  -H "Authorization: Bearer YOUR_TOKEN"

# Get metrics for specific agent
curl "http://localhost:8000/api/v2/metrics/repair-cycles?agent_name=reviewer" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Get metrics for specific time range
curl "http://localhost:8000/api/v2/metrics/repair-cycles?start_time=2025-01-23T12:00:00Z&end_time=2025-01-23T18:00:00Z" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## MetricsCollector Integration

The `MetricsCollector` in `src/codetoreum/infrastructure/metrics_collector.py` handles event subscription and aggregation:

```python
# Initialize metrics collector with event bus
metrics_collector = MetricsCollector(event_bus=event_bus)

# Get aggregated metrics
metrics = metrics_collector.get_metrics()

# Repair cycle metrics available in response:
# - repair_cycles_started
# - repair_cycles_completed
# - repair_cycles_successful
# - repair_cycles_failed
# - repair_cycles_fast_failed
# - repair_cycle_success_rate_percent
# - avg_repair_cycle_duration_seconds
# - repair_cycle_test_executions (by test type)
# - repair_cycle_test_iterations (by iteration count)
# - avg_repair_cycle_agent_calls
# - repair_cycle_file_fixes (by file path)
# - repair_cycle_warnings_reviewed
```

## Key Metrics Use Cases

### 1. Monitor Repair Success Rates

Track how often repair cycles successfully resolve test failures:

```bash
curl "http://localhost:8000/api/v2/metrics/repair-cycles" | jq '.overall_success_rate_percent'
```

Set alerts if success rate drops below threshold:

```
Alert: Repair cycle success rate below 80%
Value: 65%
Action: Investigate agent performance or test brittleness
```

### 2. Analyze Performance Trends

Monitor average repair cycle duration to identify bottlenecks:

```bash
# Compare duration across agents
curl "http://localhost:8000/api/v2/metrics/repair-cycles" | jq '.agent_metrics[] | {agent_name, success_rate_percent}'
```

### 3. Identify Problematic Tests

Use file fix metrics to identify tests that frequently fail:

```bash
curl "http://localhost:8000/api/v2/metrics/repair-cycles" | jq '.agent_metrics[] | select(.success_rate_percent < 50)'
```

### 4. Capacity Planning

Monitor agent call rates and iterations to plan infrastructure scaling:

```bash
curl "http://localhost:8000/api/v2/metrics/repair-cycles" | jq '.avg_agent_calls_per_cycle'
```

### 5. Test Suite Health

Track test execution metrics to monitor test suite efficiency:

```bash
curl "http://localhost:8000/api/v2/metrics/repair-cycles" | jq '.test_type_metrics'
```

## Implementation Details

### Files Modified

1. **`src/codetoreum/infrastructure/metrics_collector.py`**
   - Added repair cycle event subscriptions
   - Added repair cycle event handlers
   - Extended metrics dictionary with repair cycle metrics
   - Added repair cycle statistics calculations

2. **`src/codetoreum/infrastructure/event_types.py`**
   - Added repair cycle event type constants

3. **`src/codetoreum/adapters/primary/routers/metrics.py`**
   - Added `/api/v2/metrics/repair-cycles` endpoint
   - Integrated with IMetricsQueryPort interface

4. **`src/codetoreum/adapters/primary/metrics_dtos.py`**
   - Added repair cycle metrics DTOs (RepairCycleMetricsResponse, etc.)

5. **`src/codetoreum/ports/input/metrics_query.py`**
   - Added get_repair_cycle_metrics() to IMetricsQueryPort interface

6. **`src/codetoreum/application/metrics_service.py`**
   - Implemented get_repair_cycle_metrics() method
   - Added repair cycle event query logic

7. **`src/codetoreum/adapters/primary/fastapi_app.py`**
   - Added get_repair_cycle_metrics() to MockMetricsQueryPort

8. **`src/codetoreum/adapters/primary/input_port_adapters/mock/mock_metrics_query_adapter.py`**
   - Added get_repair_cycle_metrics() to MockMetricsQueryAdapter

## Event Flow Example

A complete repair cycle generates this event sequence:

```
1. RepairCycleStartedEvent
   └─ Metrics: cycles_started += 1

2. RepairCycleTestExecutionCompletedEvent (unit iteration 1)
   └─ Metrics: repair_cycle_test_executions[unit] += 1

3. RepairCycleFileFixStartedEvent
   └─ Metrics: (tracking start)

4. RepairCycleFileFixCompletedEvent
   └─ Metrics: repair_cycle_file_fixes[file_path] += 1 (if fixed)

5. RepairCycleWarningReviewCompletedEvent
   └─ Metrics: repair_cycle_warnings_reviewed += 3

6. RepairCycleCompletedEvent
   └─ Metrics:
      - cycles_completed += 1
      - cycles_successful += 1 (if overall_success)
      - repair_cycle_duration_seconds.append(45.5)
      - avg_repair_cycle_duration_seconds = 45.5
      - repair_cycle_agent_calls.append(2)
      - avg_repair_cycle_agent_calls = 2.0
      - repair_cycle_success_rate_percent = 100%
```

## Performance Considerations

### Metric Aggregation

- Metrics are aggregated in-memory by MetricsCollector
- No external dependencies required for basic collection
- Optional persistence to event store via Event Bus
- Time-based filtering done in-memory (efficient for typical time ranges)

### Scalability

For high-volume scenarios:

1. **Event Sampling**: Sample repair cycle events if volume exceeds processing capacity
2. **Time Window Rotation**: Archive old metrics periodically
3. **Distributed Aggregation**: Forward metrics to Prometheus/Grafana for long-term storage
4. **Query Caching**: Cache metrics queries with TTL to reduce computation

## Future Enhancements

1. **Predictive Metrics**: ML-based prediction of cycle success rates
2. **Anomaly Detection**: Alert on unusual repair cycle patterns
3. **Cost Analysis**: Track agent execution costs and resource usage
4. **Comparative Analysis**: Compare success rates across agents/projects
5. **Trend Analysis**: Identify improvement trends over time
6. **Integration with Grafana**: Pre-built dashboards for repair metrics
7. **Alert Rules**: Configurable thresholds for automated alerts

## Troubleshooting

### No Metrics Being Collected

1. Verify repair cycle events are being emitted
2. Check event bus subscription:
   ```python
   assert EventTypes.REPAIR_CYCLE_STARTED in metrics_collector.get_metrics()
   ```
3. Verify MetricsCollector is initialized with event bus

### Incorrect Metric Values

1. Check event handler error logs
2. Verify event payload matches expected structure
3. Check metric calculation logic in MetricsCollector handlers

### Missing Per-Agent Metrics

1. Ensure agent_name is included in repair cycle events
2. Verify agent filtering logic in MetricsService
3. Check query parameters in REST endpoint call

## Related Documentation

- [Repair Cycle Design](../documentation/01_design/events/pipeline_and_repair_events_design.md)
- [Event-Driven Architecture](../documentation/01_design/02_high_level_arch.md)
- [Metrics Infrastructure](../documentation/01_design/infrastructure/metrics_infrastructure_design.md)
