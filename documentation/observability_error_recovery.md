# Observability Error Recovery Guide

## Overview

This guide explains how to diagnose and recover from observability infrastructure failures in Codetoreum. The observability system is designed with graceful degradation, meaning **observability failures will not crash the application** - the service continues running even if tracing, metrics, or logging export fails.

## Quick Reference

| Symptom | Likely Cause | Recovery Action |
|---------|--------------|-----------------|
| "OTLP endpoint is not reachable" warning | Signoz is down or network issue | Verify Signoz is running, check network connectivity |
| "Failed to export spans" error | OTLP endpoint unreachable during export | Check Signoz logs, verify gRPC endpoint |
| "Observability enabled but no signals enabled" error | Configuration error | Enable at least one signal (traces/metrics/logs) |
| "Traces enabled but traces_endpoint not configured" error | Missing endpoint configuration | Set OTEL_EXPORTER_OTLP_TRACES_ENDPOINT |
| No spans appear in Signoz | Sampling disabled or sampler misconfigured | Check OTEL_SAMPLER_TYPE setting |
| High export latency | Network latency or Signoz overload | Check network, increase batch delay, reduce sampling |

---

## Configuration Errors (Fail Fast)

### Error: Observability Enabled But No Signals Configured

**What Happened:**
```
ValueError: Observability enabled but no signals (traces/metrics/logs) are enabled.
Either enable at least one signal or disable observability entirely (set OTEL_ENABLED=false).
```

**Root Cause:**
OTEL_ENABLED=true but all three signals are disabled:
- OTEL_TRACES_ENABLED=false
- OTEL_METRICS_ENABLED=false
- OTEL_LOGS_ENABLED=false

**Recovery:**
```bash
# Option 1: Enable at least one signal
export OTEL_TRACES_ENABLED=true

# Option 2: Disable observability entirely
export OTEL_ENABLED=false
```

---

### Error: Signal Enabled Without Endpoint

**What Happened:**
```
ValueError: Traces enabled but traces_endpoint is not configured.
Check OTEL_EXPORTER_OTLP_TRACES_ENDPOINT or Signoz gRPC configuration.
```

**Root Cause:**
A signal is enabled but its corresponding endpoint is not set.

**Recovery:**
```bash
# For traces (gRPC endpoint)
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://signoz:4317

# For logs (HTTP endpoint)
export OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://signoz:4318/v1/logs

# For metrics (HTTP endpoint)
export OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://signoz:4318/v1/metrics

# Or use Signoz-specific config
export SIGNOZ_GRPC_ENDPOINT=signoz:4317
export SIGNOZ_HTTP_ENDPOINT=http://signoz:4318
```

---

## Runtime Errors (Graceful Degradation)

### Warning: OTLP Endpoint Not Reachable (Startup)

**What Happened:**
```
WARNING: OTLP endpoint signoz:4317 is not reachable (connection failed with code 111).
Observability will be degraded until endpoint is available.
Verify that Signoz is running and accessible.
```

**Root Cause:**
During startup, the health check detected that Signoz is not reachable. This is a pre-flight check before attempting to export data.

**Impact:**
- Application continues to start normally
- Spans/logs/metrics will be queued in memory
- Export attempts will fail until Signoz is available
- Batch processor may drop data if queue fills up

**Recovery Steps:**

1. **Verify Signoz is Running**
   ```bash
   # Check if Signoz container is running
   docker ps | grep signoz

   # Check Signoz logs
   docker logs signoz-otel-collector
   ```

2. **Test Network Connectivity**
   ```bash
   # From the Codetoreum container, test connectivity
   telnet signoz 4317

   # Or use nc
   nc -zv signoz 4317
   ```

3. **Restart Application (Optional)**
   ```bash
   # If Signoz is now available, restart to clear the warning
   docker-compose restart codetoreum
   ```

**Note:** The application will continue to attempt exports even if the health check fails. If Signoz becomes available later, exports will succeed automatically without restart.

---

### Error: Failed to Export Spans

**What Happened:**
```
ERROR: Failed to export 32 spans to OTLP endpoint: [Errno 111] Connection refused
```

**Root Cause:**
The batch processor attempted to export spans but the OTLP endpoint was unreachable.

**Impact:**
- Exported spans are LOST (OTLP exporter does not retry)
- Application continues running normally
- Metric `otel.trace.export.failures` is incremented
- Gaps will appear in distributed traces

**Recovery Steps:**

1. **Check Signoz Status**
   ```bash
   docker ps | grep signoz
   docker logs signoz-otel-collector --tail 50
   ```

2. **Verify Endpoint Configuration**
   ```bash
   # Print current configuration
   env | grep OTEL
   env | grep SIGNOZ
   ```

3. **Check Network**
   ```bash
   # DNS resolution
   nslookup signoz

   # Network path
   traceroute signoz
   ```

4. **Monitor Recovery**
   ```bash
   # Watch application logs for successful exports
   docker logs -f codetoreum | grep "export"
   ```

**Prevention:**
- Set up monitoring alerts on `otel.trace.export.failures` metric
- Configure higher batch queue size to buffer during brief outages
- Use sampling to reduce export volume

---

### Warning: Failed to Initialize OpenTelemetry

**What Happened:**
```
ERROR: Failed to initialize OpenTelemetry: <error details>
WARNING: Application will continue without distributed tracing and log export
```

**Root Cause:**
OpenTelemetry setup failed during initialization (exporter creation, tracer provider setup, etc.).

**Impact:**
- **No distributed tracing** - spans are not created
- **No OTLP log export** - logs only go to stdout
- **No OTLP metrics export** - metrics are not collected
- Application continues running with degraded observability

**Recovery Steps:**

1. **Check Error Details**
   Look at the error message for specific failure:
   - ImportError: OpenTelemetry packages not installed
   - ConnectionError: Cannot reach OTLP endpoint
   - ConfigurationError: Invalid configuration values

2. **Verify OpenTelemetry Installation**
   ```bash
   python -c "from opentelemetry import trace; print('OK')"
   ```

3. **Restart with Debug Logging**
   ```bash
   export LOG_LEVEL=DEBUG
   docker-compose restart codetoreum
   ```

4. **Temporary Workaround - Disable Observability**
   ```bash
   export OTEL_ENABLED=false
   docker-compose restart codetoreum
   ```

---

## Verifying Observability is Working

### 1. Check Application Logs

**Successful Initialization:**
```
INFO: OpenTelemetry initialized successfully. Sending traces to Signoz at signoz:4317
(service: codetoreum, env: production, sampler: always_on)
INFO: OTLP log export enabled, sending logs to http://signoz:4318/v1/logs
INFO: OTLP metrics export enabled, sending metrics to http://signoz:4318/v1/metrics
```

**Health Check Passed:**
```
DEBUG: OTLP endpoint signoz:4317 connectivity check passed
```

### 2. Check Metrics

Query these metrics to verify observability health:

```python
# Successful span exports
otel.trace.export.success

# Failed span exports (should be 0 or very low)
otel.trace.export.failures

# Export duration (should be < 100ms typically)
otel.trace.export.duration
```

### 3. Verify Spans in Signoz

1. Open Signoz UI (usually http://localhost:3301)
2. Navigate to "Traces" tab
3. Filter by service: `codetoreum`
4. Verify recent traces appear

### 4. Test End-to-End Tracing

```bash
# Trigger a traced operation
curl -X GET http://localhost:8000/api/v1/projects

# Check Signoz for the corresponding trace
# Should see spans like:
# - GET /api/v1/projects (FastAPI auto-instrumentation)
# - event.handle.WorkflowStarted (event bus instrumentation)
```

---

## Diagnosing Observability Failures

### Problem: No Spans Appear in Signoz

**Diagnosis Steps:**

1. **Check if tracing is enabled**
   ```bash
   env | grep OTEL_TRACES_ENABLED
   # Should be "true"
   ```

2. **Check sampler configuration**
   ```bash
   env | grep OTEL_SAMPLER_TYPE
   # Should NOT be "always_off"
   ```

3. **Check application logs for export errors**
   ```bash
   docker logs codetoreum | grep -i "export.*failed"
   ```

4. **Verify spans are being created**
   ```bash
   # Enable DEBUG logging
   export LOG_LEVEL=DEBUG
   docker-compose restart codetoreum

   # Look for span creation logs
   docker logs codetoreum | grep "Created CONSUMER span"
   ```

5. **Check Signoz collector logs**
   ```bash
   docker logs signoz-otel-collector | grep -i error
   ```

---

### Problem: High Export Latency

**Symptoms:**
- `otel.trace.export.duration` metric > 200ms
- Application feels slow
- Export errors in logs

**Diagnosis:**

1. **Check network latency**
   ```bash
   ping signoz
   ```

2. **Check Signoz resource usage**
   ```bash
   docker stats signoz-otel-collector
   ```

3. **Review batch processor settings**
   ```bash
   env | grep OTEL_BATCH
   # OTEL_BATCH_MAX_QUEUE_SIZE (default: 2048)
   # OTEL_BATCH_MAX_EXPORT_BATCH_SIZE (default: 512)
   # OTEL_BATCH_SCHEDULE_DELAY_MILLIS (default: 5000)
   ```

**Solutions:**

- **Increase batch delay** to reduce export frequency:
  ```bash
  export OTEL_BATCH_SCHEDULE_DELAY_MILLIS=10000  # 10 seconds
  ```

- **Reduce sampling** to decrease volume:
  ```bash
  export OTEL_SAMPLER_TYPE=traceidratio
  export OTEL_SAMPLER_ARG=0.1  # Sample 10% of traces
  ```

- **Increase queue size** to buffer more spans:
  ```bash
  export OTEL_BATCH_MAX_QUEUE_SIZE=4096
  ```

---

## Error Categories

### Infrastructure Errors (error_id: ERR_INFRASTRUCTURE_ERROR)

**Characteristics:**
- Logged with `error_id: ErrorRegistry.ERR_INFRASTRUCTURE_ERROR`
- Indicate problems with observability infrastructure itself
- Application continues running (graceful degradation)

**Examples:**
- OTLP endpoint unreachable
- Span export failures
- Metrics export failures
- Trace context parsing errors
- Observability setup failures

**Impact:**
- Observability data may be incomplete or missing
- Application functionality is NOT affected
- No user-facing impact

**Recovery:**
- Fix infrastructure (Signoz, network, configuration)
- Application automatically resumes exporting when infrastructure recovers
- No application restart required (in most cases)

---

### Application Errors (error_id: ERR_HANDLER_EXECUTION, etc.)

**Characteristics:**
- Logged with application-specific error IDs
- Indicate problems in business logic or event handlers
- May affect application functionality

**Examples:**
- Event handler failures
- Domain logic errors
- External API failures

**Impact:**
- May affect specific features or workflows
- User-facing impact possible
- Requires investigation and code fixes

**Recovery:**
- Investigate root cause
- Deploy code fixes
- Review event sourcing logs for replay

---

## Monitoring and Alerting

### Recommended Alerts

1. **Export Failure Rate**
   ```
   Alert: otel.trace.export.failures > 10 per minute
   Severity: Warning
   Action: Check Signoz availability and network connectivity
   ```

2. **Export Latency**
   ```
   Alert: p95(otel.trace.export.duration) > 500ms
   Severity: Warning
   Action: Check network latency and Signoz performance
   ```

3. **Observability Disabled**
   ```
   Alert: Application started with OTEL_ENABLED=false
   Severity: Info
   Action: Verify this is intentional
   ```

---

## Common Configuration Patterns

### Development (Full Observability, All Sampling)
```bash
export OTEL_ENABLED=true
export OTEL_TRACES_ENABLED=true
export OTEL_METRICS_ENABLED=true
export OTEL_LOGS_ENABLED=true
export OTEL_SAMPLER_TYPE=always_on
export SIGNOZ_GRPC_ENDPOINT=localhost:4317
export SIGNOZ_HTTP_ENDPOINT=http://localhost:4318
```

### Production (Optimized Sampling)
```bash
export OTEL_ENABLED=true
export OTEL_TRACES_ENABLED=true
export OTEL_METRICS_ENABLED=true
export OTEL_LOGS_ENABLED=true
export OTEL_SAMPLER_TYPE=traceidratio
export OTEL_SAMPLER_ARG=0.1  # 10% sampling
export SIGNOZ_GRPC_ENDPOINT=signoz:4317
export SIGNOZ_HTTP_ENDPOINT=http://signoz:4318
```

### Testing (Observability Disabled)
```bash
export OTEL_ENABLED=false
```

---

## FAQs

### Q: Will observability failures crash my application?

**A:** No. The observability system uses graceful degradation. If tracing, metrics, or logging export fails, the application continues running normally. You'll see warnings in logs but no user-facing impact.

### Q: What happens to spans when Signoz is down?

**A:** Spans are queued in memory (up to `OTEL_BATCH_MAX_QUEUE_SIZE`). If the queue fills up, older spans are dropped. When Signoz recovers, new spans export successfully, but dropped spans are lost.

### Q: Do I need to restart the application after fixing Signoz?

**A:** Usually no. The exporter will automatically resume exports when Signoz becomes available. However, if you changed configuration environment variables, you'll need to restart.

### Q: How do I temporarily disable observability?

**A:** Set `OTEL_ENABLED=false` and restart. The application will run without any observability overhead.

### Q: Can I enable only metrics without tracing?

**A:** Yes. Set:
```bash
export OTEL_ENABLED=true
export OTEL_TRACES_ENABLED=false
export OTEL_METRICS_ENABLED=true
export OTEL_LOGS_ENABLED=false
```

### Q: What's the performance impact of always_on sampling?

**A:** Minimal in development. In production with high traffic, use `traceidratio` sampler (e.g., 0.1 for 10% sampling) to reduce overhead while maintaining statistical observability.

---

## Related Documentation

- `/workspace/src/codetoreum/infrastructure/observability/config.py` - Configuration options
- `/workspace/src/codetoreum/infrastructure/observability/otel_setup.py` - Setup and error handling
- `/workspace/ERROR_HANDLING_AUDIT_REPORT.md` - Error handling audit findings
- OpenTelemetry Python SDK: https://opentelemetry.io/docs/instrumentation/python/
- Signoz Documentation: https://signoz.io/docs/

---

## Support

For additional help:
1. Check application logs with DEBUG level enabled
2. Review Signoz collector logs
3. Consult the error handling audit report for specific error patterns
4. Refer to OpenTelemetry documentation for OTLP export issues
