# Observability Infrastructure - Error Recovery Guide

## Overview

The observability infrastructure provides distributed tracing, metrics, and logging via OpenTelemetry and Signoz. This guide explains what happens when observability components fail and how to diagnose and recover from issues.

## Table of Contents

1. [Graceful Degradation](#graceful-degradation)
2. [Error Scenarios](#error-scenarios)
3. [Diagnostic Procedures](#diagnostic-procedures)
4. [Recovery Procedures](#recovery-procedures)
5. [Health Verification](#health-verification)
6. [Common Issues](#common-issues)

---

## Graceful Degradation

### Design Principle

The observability infrastructure is designed to **never crash the application**. If observability components fail, the application continues running with reduced visibility.

### Degradation Behavior

When observability fails:
- **Application continues normally** - No user-facing impact
- **Local metrics still collected** - In-memory aggregation continues
- **Application logs still written** - Standard logging works
- **Error logged with context** - Operators see failure in logs
- **Automatic retry on restart** - Next restart attempts full setup

### What You'll See

```log
[ERROR] Failed to initialize OpenTelemetry: Connection refused
[WARNING] Application will continue without distributed tracing and log export
[INFO] Local metrics collection unaffected
```

---

## Error Scenarios

### 1. OTLP Endpoint Unreachable

**Symptom**: Cannot connect to Signoz/OTLP endpoint

**What Happens**:
- Connectivity check fails with warning
- Span export attempts fail
- Metrics export fails
- Logs export fails
- Application continues without remote observability

**Log Messages**:
```log
[WARNING] OTLP endpoint signoz:4317 is not reachable (connection failed with code 111).
          Observability will be degraded until endpoint is available.
          Verify that Signoz is running and accessible.
```

**Impact**:
- ❌ No traces sent to Signoz
- ❌ No metrics exported to Signoz
- ❌ No logs exported to Signoz
- ✅ Application functions normally
- ✅ Local metrics still collected
- ✅ Application logs still written

**Recovery**: See [OTLP Endpoint Recovery](#otlp-endpoint-recovery)

---

### 2. Span Export Failure

**Symptom**: Traces created but export fails

**What Happens**:
- Spans created locally
- Batch processor queues spans
- Export to OTLP endpoint fails
- Failure metric recorded
- Error logged with full context
- Spans dropped after queue fills

**Log Messages**:
```log
[ERROR] Failed to export 128 spans to OTLP endpoint: [Errno 111] Connection refused
```

**Metrics**:
- `otel.trace.export.failures` counter increments
- `otel.trace.export.success` stops incrementing
- `otel.trace.export.duration` histogram shows no new samples

**Impact**:
- ❌ Distributed tracing incomplete
- ❌ Cannot correlate requests across services
- ✅ Span attributes still logged locally (DEBUG level)
- ✅ Application unaffected

**Recovery**: See [Export Failure Recovery](#export-failure-recovery)

---

### 3. Batch Processor Queue Full

**Symptom**: Too many spans queued, queue overflow

**What Happens**:
- Batch processor queue reaches `max_queue_size` (default: 2048)
- New spans dropped silently by OpenTelemetry SDK
- No explicit error from SDK
- Export latency metrics show degradation

**Log Messages**:
```log
# No explicit log message - this is an SDK behavior
# Look for export duration spikes or missing spans
```

**Impact**:
- ❌ Spans dropped (data loss)
- ❌ Incomplete traces in Signoz
- ✅ Application continues normally

**Recovery**: See [Queue Overflow Recovery](#queue-overflow-recovery)

---

### 4. Metrics Export Failure

**Symptom**: Metrics collected but not exported

**What Happens**:
- Metrics created and recorded locally
- Periodic exporter attempts to send to OTLP endpoint
- Export fails
- Error logged with context
- In-memory metrics still available

**Log Messages**:
```log
[ERROR] Failed to configure metrics export to Signoz: Connection refused
[INFO] Metrics export to Signoz disabled due to setup failure.
       Application will continue without remote metrics export.
       Local metrics collection is unaffected.
       To enable metrics export, verify endpoint accessibility and restart the service: http://signoz:4318/v1/metrics
```

**Impact**:
- ❌ Metrics not visible in Signoz dashboards
- ✅ Local metrics API still works (`/metrics` endpoint if Prometheus adapter enabled)
- ✅ Application continues normally

**Recovery**: See [Metrics Export Recovery](#metrics-export-recovery)

---

### 5. Log Export Failure

**Symptom**: Application logs not appearing in Signoz

**What Happens**:
- Logs written to application logger
- OTLP log exporter attempts to send to Signoz
- Export fails
- Logs still written to local files/stdout
- Application continues

**Log Messages**:
```log
[ERROR] Failed to configure log export to Signoz: Connection refused
[INFO] Application will continue without remote log export.
       Local logging is unaffected.
```

**Impact**:
- ❌ Logs not centralized in Signoz
- ✅ Local logs still written (stdout, files)
- ✅ Application log statements still execute
- ✅ ELK/Loki ingestion from log files still works

**Recovery**: See [Log Export Recovery](#log-export-recovery)

---

### 6. Invalid Configuration

**Symptom**: Observability enabled but misconfigured

**What Happens**:
- Configuration validation runs on startup
- Invalid config detected
- ValueError raised with descriptive message
- Application fails to start (fail-fast)

**Error Messages**:
```python
ValueError: Observability enabled but no signals (traces/metrics/logs) are enabled.
           Either enable at least one signal or disable observability entirely (set OTEL_ENABLED=false).
```

**Impact**:
- ❌ Application won't start
- ✅ Clear error message explains the issue
- ✅ No silent misconfiguration

**Recovery**: See [Configuration Recovery](#configuration-recovery)

---

## Diagnostic Procedures

### 1. Check if Observability is Working

**Quick Health Check**:
```bash
# Check application logs for observability status
tail -f /var/log/codetoreum/app.log | grep -i "opentelemetry\|signoz\|otlp"

# Expected success messages:
# [INFO] OpenTelemetry initialized successfully
# [INFO] OTLP metrics export configured
# [INFO] OTLP log export configured
```

**Verify Metrics Export**:
```bash
# Check if metrics are being recorded
curl http://localhost:8000/internal/health | jq '.observability'

# Expected output:
# {
#   "traces_enabled": true,
#   "metrics_enabled": true,
#   "logs_enabled": true,
#   "exporter_health": "healthy"
# }
```

**Verify Trace Export**:
```bash
# Trigger a traced operation
curl http://localhost:8000/api/v1/workflows

# Check Signoz for trace (UI or API)
curl http://signoz:3301/api/v1/traces?service=codetoreum

# Or check export failure counter
curl http://localhost:8000/metrics | grep otel_trace_export_failures
```

---

### 2. Diagnose Export Failures

**Check Network Connectivity**:
```bash
# Test OTLP endpoint reachability
nc -zv signoz 4317  # gRPC endpoint for traces
nc -zv signoz 4318  # HTTP endpoint for metrics/logs

# Or use telnet
telnet signoz 4317
```

**Check Signoz Health**:
```bash
# Verify Signoz is running
curl http://signoz:3301/api/v1/health

# Check Signoz logs for ingestion errors
docker logs signoz-otel-collector | tail -100
```

**Check Application Metrics**:
```bash
# Export failure count
curl http://localhost:8000/metrics | grep otel_trace_export_failures

# Export success count
curl http://localhost:8000/metrics | grep otel_trace_export_success

# Export duration
curl http://localhost:8000/metrics | grep otel_trace_export_duration
```

---

### 3. Determine if Issue is Infrastructure or Application

**Infrastructure Issues** (Signoz/Network):
- Connectivity check fails
- All export types fail (traces, metrics, logs)
- Network errors in logs
- Signoz container not running

**Application Issues** (Code/Config):
- Connectivity check passes but exports fail
- Only specific signal types fail
- Configuration validation errors
- Wrong endpoint URLs

**Use This Decision Tree**:
```
Can connect to OTLP endpoint?
├─ NO → Infrastructure issue (Signoz down, network blocked)
└─ YES → Application issue (wrong endpoint, auth, format)

Are errors consistent across all signals?
├─ YES → Infrastructure issue (OTLP collector problem)
└─ NO → Application issue (specific exporter misconfigured)

Does Signoz report receiving data?
├─ YES → Application data format issue
└─ NO → Network/firewall issue
```

---

## Recovery Procedures

### OTLP Endpoint Recovery

**Problem**: Signoz/OTLP endpoint not reachable

**Steps**:

1. **Verify Signoz is running**:
   ```bash
   docker ps | grep signoz
   # Should show signoz-otel-collector, signoz-query-service, signoz-frontend
   ```

2. **Start Signoz if not running**:
   ```bash
   cd /path/to/signoz
   docker-compose up -d
   ```

3. **Verify network connectivity**:
   ```bash
   # From application container/host
   ping signoz
   nc -zv signoz 4317  # gRPC
   nc -zv signoz 4318  # HTTP
   ```

4. **Check firewall rules**:
   ```bash
   # Allow OTLP ports
   sudo ufw allow 4317/tcp  # gRPC
   sudo ufw allow 4318/tcp  # HTTP
   ```

5. **Restart application** (observability auto-reconnects):
   ```bash
   systemctl restart codetoreum
   # Or docker restart if containerized
   ```

6. **Verify recovery**:
   ```bash
   # Check logs for success message
   tail -f /var/log/codetoreum/app.log | grep "OpenTelemetry initialized successfully"

   # Verify traces appear in Signoz
   curl http://signoz:3301/api/v1/traces?service=codetoreum
   ```

---

### Export Failure Recovery

**Problem**: Exports failing despite connectivity

**Steps**:

1. **Check endpoint URLs** in environment variables:
   ```bash
   echo $OTEL_EXPORTER_OTLP_TRACES_ENDPOINT  # Should be: http://signoz:4317
   echo $OTEL_EXPORTER_OTLP_METRICS_ENDPOINT # Should be: http://signoz:4318/v1/metrics
   echo $OTEL_EXPORTER_OTLP_LOGS_ENDPOINT    # Should be: http://signoz:4318/v1/logs
   ```

2. **Verify protocol** (gRPC vs HTTP):
   ```bash
   # Traces use gRPC (port 4317)
   # Metrics/Logs use HTTP (port 4318)

   # Check if endpoint URL matches protocol
   # gRPC: http://signoz:4317 (no path)
   # HTTP: http://signoz:4318/v1/metrics (with path)
   ```

3. **Check timeout settings**:
   ```python
   # In otel_setup.py, exporters have 5-second timeout
   # If Signoz is slow, exports may timeout

   # Increase timeout in configuration:
   OTEL_EXPORTER_OTLP_TIMEOUT=10  # 10 seconds
   ```

4. **Review Signoz logs** for ingestion errors:
   ```bash
   docker logs signoz-otel-collector 2>&1 | grep -i error
   # Look for format errors, schema violations, auth failures
   ```

5. **Enable debug logging** to see export details:
   ```bash
   # Set environment variable
   OTEL_LOG_LEVEL=debug

   # Restart application and check logs
   tail -f /var/log/codetoreum/app.log | grep "export"
   ```

---

### Queue Overflow Recovery

**Problem**: Batch processor queue full, spans dropped

**Symptoms**:
- `otel.trace.export.duration` histogram shows high percentiles
- Signoz shows gaps in traces
- No explicit error logs (SDK behavior)

**Steps**:

1. **Increase queue size** (if export is slow):
   ```bash
   # Set environment variables
   OTEL_BSP_MAX_QUEUE_SIZE=4096        # Default: 2048
   OTEL_BSP_MAX_EXPORT_BATCH_SIZE=1024 # Default: 512
   OTEL_BSP_SCHEDULE_DELAY=2000        # Export every 2s (default: 5s)
   ```

2. **Reduce export delay** (process queue faster):
   ```bash
   OTEL_BSP_SCHEDULE_DELAY=1000  # Export every 1 second
   ```

3. **Reduce sampling** (create fewer spans):
   ```bash
   OTEL_TRACES_SAMPLER=traceidratio
   OTEL_TRACES_SAMPLER_ARG=0.1  # Sample 10% of traces
   ```

4. **Improve export performance**:
   - Ensure Signoz has sufficient resources (CPU/memory)
   - Check network latency between app and Signoz
   - Consider increasing Signoz ingestion limits

5. **Monitor queue health**:
   ```bash
   # Check export duration metrics
   curl http://localhost:8000/metrics | grep otel_trace_export_duration

   # High p95/p99 indicates queue backup
   # Target: p95 < 100ms, p99 < 500ms
   ```

---

### Metrics Export Recovery

**Problem**: Metrics not appearing in Signoz

**Steps**:

1. **Verify metrics endpoint**:
   ```bash
   echo $OTEL_EXPORTER_OTLP_METRICS_ENDPOINT
   # Should be: http://signoz:4318/v1/metrics
   ```

2. **Check if metrics are enabled**:
   ```bash
   echo $OTEL_METRICS_ENABLED  # Should be: true
   ```

3. **Verify export interval**:
   ```python
   # In otel_setup.py, metrics export every 60 seconds
   # Allow 60s for first metric batch to appear
   ```

4. **Test local metrics collection**:
   ```bash
   # If Prometheus adapter enabled
   curl http://localhost:8000/metrics

   # Should show metrics like:
   # codetoreum_repair_cycle_started_total{...} 42
   ```

5. **Check Signoz metrics ingestion**:
   ```bash
   # Query Signoz for metrics
   curl http://signoz:3301/api/v1/query?query=codetoreum_repair_cycle_started_total
   ```

6. **Restart with debug logging**:
   ```bash
   OTEL_LOG_LEVEL=debug systemctl restart codetoreum
   tail -f /var/log/codetoreum/app.log | grep metric
   ```

---

### Log Export Recovery

**Problem**: Application logs not in Signoz

**Steps**:

1. **Verify logs endpoint**:
   ```bash
   echo $OTEL_EXPORTER_OTLP_LOGS_ENDPOINT
   # Should be: http://signoz:4318/v1/logs
   ```

2. **Check if logs are enabled**:
   ```bash
   echo $OTEL_LOGS_ENABLED  # Should be: true
   ```

3. **Verify local logs work**:
   ```bash
   # Check application log files
   tail -f /var/log/codetoreum/app.log

   # Should show log entries
   ```

4. **Check log correlation** with traces:
   ```python
   # Logs should include trace_id and span_id
   # Format: [INFO] [trace_id=abc123 span_id=def456] Message here
   ```

5. **Query Signoz logs API**:
   ```bash
   curl 'http://signoz:3301/api/v1/logs?service=codetoreum&limit=100'
   ```

6. **Fallback to file-based ingestion**:
   ```bash
   # Configure Fluentd/Logstash to read log files
   # Point to Signoz logs API
   # More reliable than OTLP log export
   ```

---

### Configuration Recovery

**Problem**: Invalid observability configuration

**Symptoms**:
```
ValueError: Observability enabled but no signals (traces/metrics/logs) are enabled
```

**Steps**:

1. **Review configuration** in `.env` or environment:
   ```bash
   # Master switch
   OTEL_ENABLED=true  # Must be true

   # At least one signal must be enabled
   OTEL_TRACES_ENABLED=true
   OTEL_METRICS_ENABLED=true
   OTEL_LOGS_ENABLED=true

   # Signoz integration
   SIGNOZ_ENABLED=true
   ```

2. **Common misconfigurations**:
   ```bash
   # Wrong: Observability on but all signals off
   OTEL_ENABLED=true
   OTEL_TRACES_ENABLED=false
   OTEL_METRICS_ENABLED=false
   OTEL_LOGS_ENABLED=false
   # Fix: Enable at least one signal

   # Wrong: Signal enabled without endpoint
   OTEL_TRACES_ENABLED=true
   OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=""  # Empty!
   # Fix: Set endpoint URL

   # Wrong: Mismatched protocol and port
   OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://signoz:4318  # HTTP port for gRPC
   # Fix: Use port 4317 for traces (gRPC)
   ```

3. **Validate configuration**:
   ```bash
   # Run validation script
   python -c "
   from codetoreum.infrastructure.observability.config import ObservabilityConfig
   config = ObservabilityConfig.from_env()
   config.validate()
   print('Configuration valid!')
   "
   ```

4. **Use minimal working config**:
   ```bash
   # .env file (minimal)
   OTEL_ENABLED=true
   OTEL_TRACES_ENABLED=true
   OTEL_METRICS_ENABLED=true
   OTEL_LOGS_ENABLED=true

   SIGNOZ_ENABLED=true
   SIGNOZ_SERVICE_NAME=codetoreum
   SIGNOZ_ENVIRONMENT=production
   SIGNOZ_GRPC_ENDPOINT=http://signoz:4317
   SIGNOZ_HTTP_ENDPOINT=http://signoz:4318
   ```

5. **Restart and verify**:
   ```bash
   systemctl restart codetoreum
   tail -f /var/log/codetoreum/app.log | grep "OpenTelemetry initialized"
   ```

---

## Health Verification

### Post-Recovery Checklist

After applying recovery procedures, verify observability is working:

**1. Check Startup Logs**:
```bash
tail -100 /var/log/codetoreum/app.log | grep -i opentelemetry

# Expected messages:
✅ [INFO] OTLP endpoint signoz:4317 connectivity check passed
✅ [INFO] OpenTelemetry initialized successfully
✅ [INFO] OTLP metrics export configured. Sending metrics to http://signoz:4318/v1/metrics
✅ [INFO] OTLP log export configured. Sending logs to http://signoz:4318/v1/logs
✅ [INFO] FastAPI auto-instrumentation enabled
```

**2. Verify Metrics**:
```bash
# Check export success counter
curl -s http://localhost:8000/metrics | grep 'otel_trace_export_success'
# otel_trace_export_success 42.0

# Check export failures (should be 0 or not increasing)
curl -s http://localhost:8000/metrics | grep 'otel_trace_export_failures'
# otel_trace_export_failures 0.0
```

**3. Verify Traces in Signoz**:
```bash
# Trigger a traced operation
curl http://localhost:8000/api/v1/workflows

# Wait 5-10 seconds for batch export

# Check Signoz UI or API
curl http://signoz:3301/api/v1/traces?service=codetoreum&limit=1
# Should return recent trace
```

**4. Verify Metrics in Signoz**:
```bash
# Wait 60 seconds for first metric export

# Query Signoz for metrics
curl 'http://signoz:3301/api/v1/query?query=codetoreum_repair_cycle_started_total'
# Should return metric data points
```

**5. Verify Logs in Signoz**:
```bash
# Trigger log entries
curl http://localhost:8000/api/v1/workflows

# Query Signoz logs
curl 'http://signoz:3301/api/v1/logs?service=codetoreum&limit=10'
# Should show recent log entries with trace correlation
```

---

## Common Issues

### Issue: "OTLP endpoint not reachable"

**Cause**: Signoz not running or network unreachable

**Solution**:
1. Start Signoz: `docker-compose -f signoz/docker-compose.yml up -d`
2. Check network: `docker network inspect signoz_network`
3. Verify DNS: `nslookup signoz` or `ping signoz`

---

### Issue: "Spans exported but not visible in Signoz"

**Cause**: Wrong service name, sampling disabled, time range issue

**Solution**:
1. Check service name matches: `SIGNOZ_SERVICE_NAME=codetoreum`
2. Verify sampling: `OTEL_TRACES_SAMPLER=always_on` (for testing)
3. Expand time range in Signoz UI (check "Last 1 hour")
4. Check Signoz ingestion logs: `docker logs signoz-otel-collector`

---

### Issue: "High memory usage with observability enabled"

**Cause**: Queue backlog, too many spans, memory leak

**Solution**:
1. Reduce queue size: `OTEL_BSP_MAX_QUEUE_SIZE=1024`
2. Increase sampling: `OTEL_TRACES_SAMPLER_ARG=0.1` (10% sampling)
3. Reduce export delay: `OTEL_BSP_SCHEDULE_DELAY=2000` (2 seconds)
4. Monitor metrics: `curl http://localhost:8000/metrics | grep otel_trace_export_duration`

---

### Issue: "Traces missing after Signoz restart"

**Cause**: Signoz data not persisted, volume mount missing

**Solution**:
1. Check Signoz volumes: `docker-compose -f signoz/docker-compose.yml config | grep volumes`
2. Verify persistence: `docker volume ls | grep signoz`
3. Check retention policy in Signoz config
4. Traces are temporary by nature - ensure continuous export

---

### Issue: "Error logs not appearing"

**Cause**: Error occurred before log export setup, or logger not configured

**Solution**:
1. Check application logs locally first: `tail -f /var/log/codetoreum/app.log`
2. Verify OTLP log handler attached: Look for "OTLP log export configured"
3. Check log level: `LOG_LEVEL=DEBUG` or `LOG_LEVEL=ERROR`
4. Ensure errors are logged with: `logger.error(..., exc_info=True)`

---

## Configuration Reference

### Environment Variables

**Master Switches**:
```bash
OTEL_ENABLED=true                    # Enable/disable all observability
OTEL_TRACES_ENABLED=true             # Enable distributed tracing
OTEL_METRICS_ENABLED=true            # Enable metrics export
OTEL_LOGS_ENABLED=true               # Enable log export
```

**Signoz Configuration**:
```bash
SIGNOZ_ENABLED=true                  # Enable Signoz integration
SIGNOZ_SERVICE_NAME=codetoreum       # Service name in Signoz
SIGNOZ_ENVIRONMENT=production        # Environment tag
SIGNOZ_GRPC_ENDPOINT=http://signoz:4317    # For traces (gRPC)
SIGNOZ_HTTP_ENDPOINT=http://signoz:4318    # For metrics/logs (HTTP)
SIGNOZ_INSECURE=true                 # Use insecure connection (dev only)
```

**Sampling**:
```bash
OTEL_TRACES_SAMPLER=always_on        # always_on, always_off, traceidratio, parentbased_always_on
OTEL_TRACES_SAMPLER_ARG=1.0          # 1.0 = 100%, 0.1 = 10%
```

**Batch Processing**:
```bash
OTEL_BSP_MAX_QUEUE_SIZE=2048         # Max queued spans
OTEL_BSP_MAX_EXPORT_BATCH_SIZE=512   # Max spans per export
OTEL_BSP_SCHEDULE_DELAY=5000         # Export interval (ms)
```

**Timeouts**:
```bash
OTEL_EXPORTER_OTLP_TIMEOUT=5         # Export timeout (seconds)
```

**Debugging**:
```bash
OTEL_LOG_LEVEL=debug                 # debug, info, warning, error
LOG_LEVEL=DEBUG                      # Application log level
```

---

## Monitoring Observability Health

### Key Metrics to Track

**Export Success Rate**:
```promql
# PromQL query
rate(otel_trace_export_success[5m]) /
(rate(otel_trace_export_success[5m]) + rate(otel_trace_export_failures[5m]))

# Target: > 99%
```

**Export Duration**:
```promql
# p95 export latency
histogram_quantile(0.95, rate(otel_trace_export_duration_bucket[5m]))

# Target: < 100ms
```

**Export Failures**:
```promql
# Failure rate
rate(otel_trace_export_failures[5m])

# Target: 0
```

### Alerting Rules

```yaml
# Prometheus alerting rules
groups:
  - name: observability_health
    rules:
      - alert: OTLPExportFailureHigh
        expr: rate(otel_trace_export_failures[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "OTLP export failures detected"
          description: "{{ $value }} exports/sec failing for service {{ $labels.service }}"

      - alert: OTLPExportDurationHigh
        expr: histogram_quantile(0.95, rate(otel_trace_export_duration_bucket[5m])) > 0.5
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "OTLP export latency high"
          description: "p95 export duration {{ $value }}s for service {{ $labels.service }}"
```

---

## Support and Resources

### Internal Resources
- Observability source code: `/workspace/src/codetoreum/infrastructure/observability/`
- Configuration module: `config.py`
- Setup module: `otel_setup.py`
- Monitoring guide: `/workspace/documentation/monitoring/README.md`

### External Resources
- [OpenTelemetry Python Docs](https://opentelemetry.io/docs/languages/python/)
- [Signoz Documentation](https://signoz.io/docs/)
- [OTLP Specification](https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/protocol/otlp.md)
- [OpenTelemetry Troubleshooting](https://opentelemetry.io/docs/languages/python/troubleshooting/)

### Getting Help
- Check application logs: `tail -f /var/log/codetoreum/app.log | grep -i otel`
- Check Signoz logs: `docker logs signoz-otel-collector`
- Enable debug logging: `OTEL_LOG_LEVEL=debug`
- Review error IDs: All errors include `error_id` for Sentry tracking

---

## Appendix: Error Message Reference

### Application Error Messages

| Log Message | Severity | Meaning | Action |
|-------------|----------|---------|--------|
| "OTLP endpoint X is not reachable" | WARNING | Connectivity check failed | Verify Signoz running, check network |
| "Failed to export N spans to OTLP endpoint" | ERROR | Span export failed | Check Signoz ingestion, network |
| "Metrics export to Signoz disabled" | INFO | Metrics setup failed | Check endpoint URL, restart to retry |
| "Application will continue without distributed tracing" | WARNING | Tracing disabled due to error | Application works, limited observability |
| "Observability enabled but no signals enabled" | ERROR (ValueError) | Invalid configuration | Enable at least one signal or disable observability |

### OpenTelemetry SDK Messages

| Message Pattern | Meaning | Action |
|-----------------|---------|--------|
| "Failed to export spans" | OTLP exporter error | Check connectivity |
| "Dropping span" | Queue overflow | Increase queue size or reduce sampling |
| "Connection refused" | Signoz not reachable | Start Signoz |
| "timeout" | Export timeout | Increase timeout or check Signoz performance |

---

**Last Updated**: 2026-02-20
**Version**: 1.0
**Author**: Codetoreum Development Team
