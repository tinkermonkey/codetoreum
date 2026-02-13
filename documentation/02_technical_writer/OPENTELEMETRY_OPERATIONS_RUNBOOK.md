# OpenTelemetry Operations Runbook

**Project:** Codetoreum
**Audience:** Platform Operators, SREs, DevOps Engineers
**Last Updated:** February 2026

---

## Table of Contents

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Deployment Configurations](#deployment-configurations)
3. [Health Monitoring](#health-monitoring)
4. [Incident Response](#incident-response)
5. [Capacity Planning](#capacity-planning)
6. [Cost Optimization](#cost-optimization)

---

## Pre-Deployment Checklist

### Infrastructure Requirements

- [ ] Signoz or compatible OTLP backend deployed
- [ ] Network connectivity to OTLP endpoints (ports 4317, 4318)
- [ ] TLS certificates configured (production)
- [ ] Firewall rules allow outbound connections to OTLP endpoints
- [ ] DNS resolution working for observability backend
- [ ] Resource limits configured (CPU, memory) for application

### Configuration Validation

```bash
# 1. Check all required environment variables are set
./scripts/check-otel-config.sh

# 2. Test endpoint connectivity
grpcurl -plaintext $SIGNOZ_HOST:4317 list
curl -v http://$SIGNOZ_HOST:4318/v1/logs

# 3. Validate configuration
python -c "
from codetoreum.infrastructure.observability.config import ObservabilityConfig
config = ObservabilityConfig.from_env()
config.validate()
print('Configuration valid ✓')
"

# 4. Check dependencies installed
pip list | grep opentelemetry
```

### Monitoring Setup

- [ ] Alerts configured for `otel.trace.export.failures`
- [ ] Alerts configured for `otel.log.export.failures`
- [ ] Dashboard created for OTEL metrics
- [ ] Runbook distributed to on-call team
- [ ] Contact information for observability backend support

---

## Deployment Configurations

### Environment: Development

**Purpose:** Local development, debugging, maximum visibility

```bash
# Master switches
export OTEL_ENABLED=true
export OTEL_TRACES_ENABLED=true
export OTEL_LOGS_ENABLED=true

# Local Signoz
export SIGNOZ_ENABLED=true
export SIGNOZ_HOST=http://localhost
export SIGNOZ_GRPC_PORT=4317
export SIGNOZ_HTTP_PORT=4318
export SIGNOZ_INSECURE=true

# Service identification
export SIGNOZ_SERVICE_NAME=codetoreum-dev
export CODETOREUM_ENV=development

# 100% sampling
export OTEL_TRACES_SAMPLER=always_on

# Standard batch configuration
export OTEL_BATCH_SPAN_PROCESSOR_MAX_QUEUE_SIZE=2048
export OTEL_BATCH_SPAN_PROCESSOR_MAX_EXPORT_BATCH_SIZE=512
export OTEL_BATCH_SPAN_PROCESSOR_SCHEDULE_DELAY_MILLIS=5000

# Debug logging
export OTEL_LOG_LEVEL=debug
```

**Expected Metrics:**
- Trace export success rate: 100%
- Log export success rate: 100%
- Memory overhead: ~10-15MB

---

### Environment: Staging

**Purpose:** Pre-production testing, realistic load

```bash
# Master switches
export OTEL_ENABLED=true
export OTEL_TRACES_ENABLED=true
export OTEL_LOGS_ENABLED=true

# Staging Signoz
export SIGNOZ_ENABLED=true
export SIGNOZ_HOST=https://signoz-staging.example.com
export SIGNOZ_GRPC_PORT=4317
export SIGNOZ_HTTP_PORT=4318
export SIGNOZ_INSECURE=false

# Service identification
export SIGNOZ_SERVICE_NAME=codetoreum-staging
export CODETOREUM_ENV=staging

# 50% sampling (testing sampling behavior)
export OTEL_TRACES_SAMPLER=parentbased_always_on
export OTEL_TRACES_SAMPLER_ARG=0.5

# Standard batch configuration
export OTEL_BATCH_SPAN_PROCESSOR_MAX_QUEUE_SIZE=2048
export OTEL_BATCH_SPAN_PROCESSOR_MAX_EXPORT_BATCH_SIZE=512
export OTEL_BATCH_SPAN_PROCESSOR_SCHEDULE_DELAY_MILLIS=5000

# Info logging
export OTEL_LOG_LEVEL=info
```

**Expected Metrics:**
- Trace export success rate: >99%
- Log export success rate: >99%
- ~50% of requests traced

---

### Environment: Production

**Purpose:** Production workload, cost-optimized, reliable

```bash
# Master switches
export OTEL_ENABLED=true
export OTEL_TRACES_ENABLED=true
export OTEL_LOGS_ENABLED=true  # Set to false if logs not needed

# Production Signoz
export SIGNOZ_ENABLED=true
export SIGNOZ_HOST=https://signoz-prod.example.com
export SIGNOZ_GRPC_PORT=4317
export SIGNOZ_HTTP_PORT=4318
export SIGNOZ_INSECURE=false
export SIGNOZ_API_KEY=${SIGNOZ_API_KEY}  # From secrets manager

# Service identification
export SIGNOZ_SERVICE_NAME=codetoreum-prod
export CODETOREUM_ENV=production

# 10% sampling (cost optimization)
export OTEL_TRACES_SAMPLER=parentbased_always_on
export OTEL_TRACES_SAMPLER_ARG=0.1

# High throughput batch configuration
export OTEL_BATCH_SPAN_PROCESSOR_MAX_QUEUE_SIZE=4096
export OTEL_BATCH_SPAN_PROCESSOR_MAX_EXPORT_BATCH_SIZE=1024
export OTEL_BATCH_SPAN_PROCESSOR_SCHEDULE_DELAY_MILLIS=3000

# Warning logging only
export OTEL_LOG_LEVEL=warning
```

**Expected Metrics:**
- Trace export success rate: >99.9%
- Log export success rate: >99.9%
- ~10% of requests traced
- Memory overhead: ~20-30MB

---

### Environment: Production (High Throughput)

**Purpose:** >10,000 events/second

```bash
# Same as production, with tuned batch parameters

# Larger queues for spike buffering
export OTEL_BATCH_SPAN_PROCESSOR_MAX_QUEUE_SIZE=8192

# Larger batches for network efficiency
export OTEL_BATCH_SPAN_PROCESSOR_MAX_EXPORT_BATCH_SIZE=2048

# More frequent exports to prevent queue buildup
export OTEL_BATCH_SPAN_PROCESSOR_SCHEDULE_DELAY_MILLIS=2000

# More aggressive sampling (1%)
export OTEL_TRACES_SAMPLER_ARG=0.01
```

**Resource Requirements:**
- Memory: +50-100MB (larger queues)
- CPU: +5-10% (more frequent exports)
- Network: ~5-10 MB/sec to OTLP endpoint

---

## Health Monitoring

### Key Performance Indicators (KPIs)

| Metric | Target | Warning | Critical |
|--------|--------|---------|----------|
| Trace export success rate | >99.9% | <99% | <95% |
| Log export success rate | >99.9% | <99% | <95% |
| Trace export latency (p95) | <1s | >2s | >5s |
| Span queue depth | <1500 | >1800 | >2000 |
| Log queue depth | <1500 | >1800 | >2000 |
| Memory overhead | <50MB | >100MB | >200MB |

### Prometheus Queries

```promql
# Trace export failure rate
rate(otel_trace_export_failures_total[5m])

# Log export failure rate
rate(otel_log_export_failures_total[5m])

# Span queue depth
otel_trace_queue_size

# Trace export latency (p95)
histogram_quantile(0.95, rate(otel_trace_export_duration_bucket[5m]))

# Memory usage (application-wide)
process_resident_memory_bytes{service="codetoreum"}
```

### Health Check Endpoint

```bash
# Check observability health
curl http://localhost:8000/health/observability

# Expected response:
{
  "status": "healthy",
  "traces_enabled": true,
  "logs_enabled": true,
  "traces_endpoint": "signoz-prod.example.com:4317",
  "logs_endpoint": "https://signoz-prod.example.com:4318/v1/logs",
  "trace_export_failures_last_5m": 0,
  "log_export_failures_last_5m": 0,
  "span_queue_size": 142,
  "log_queue_size": 89
}
```

### Alert Rules

**Alert: High Trace Export Failure Rate**

```yaml
alert: HighTraceExportFailureRate
expr: rate(otel_trace_export_failures_total[5m]) > 0.1
for: 5m
severity: warning
annotations:
  summary: "High trace export failure rate ({{ $value }}/sec)"
  description: "Traces are failing to export to OTLP endpoint. Check network connectivity and backend health."
```

**Alert: Trace Export Critical Failure**

```yaml
alert: TraceExportCriticalFailure
expr: rate(otel_trace_export_failures_total[5m]) > 1.0
for: 2m
severity: critical
annotations:
  summary: "Critical trace export failure ({{ $value }}/sec)"
  description: "IMMEDIATE ACTION REQUIRED: Traces are failing to export. Application may be experiencing observability outage."
```

**Alert: Span Queue Near Capacity**

```yaml
alert: SpanQueueNearCapacity
expr: otel_trace_queue_size > 1800
for: 5m
severity: warning
annotations:
  summary: "Span queue at {{ $value }} (75% capacity)"
  description: "Span queue is filling up. May indicate export slowness or high traffic."
```

**Alert: Observability Memory Leak**

```yaml
alert: ObservabilityMemoryLeak
expr: |
  (
    process_resident_memory_bytes{service="codetoreum"} -
    process_resident_memory_bytes{service="codetoreum"} offset 1h
  ) > 100e6
for: 30m
severity: warning
annotations:
  summary: "Memory grew by {{ $value | humanize }}B in 1 hour"
  description: "Possible memory leak in observability stack. Check queue sizes and export rates."
```

---

## Incident Response

### Incident: Traces Not Appearing in Backend

**Severity:** P2 (High)

**Symptoms:**
- No traces in Signoz UI for recent requests
- Application logs show spans being created
- No error messages in application logs

**Diagnosis:**

```bash
# Step 1: Verify application configuration
./scripts/diagnose-otel.sh

# Step 2: Check backend connectivity
grpcurl -plaintext $SIGNOZ_HOST:4317 list
# Expected: List of gRPC services

# Step 3: Check firewall/network
telnet $SIGNOZ_HOST 4317
# Expected: Connection successful

# Step 4: Check application logs
grep -i "trace export" /var/log/codetoreum/application.log | tail -50

# Step 5: Query health endpoint
curl http://localhost:8000/health/observability
```

**Resolution Steps:**

1. **Network Issue:**
   ```bash
   # Check firewall rules
   sudo ufw status | grep 4317
   sudo iptables -L | grep 4317

   # Allow if blocked
   sudo ufw allow out 4317/tcp
   ```

2. **Backend Down:**
   ```bash
   # Check backend health
   curl https://$SIGNOZ_HOST:8900/api/v1/version

   # If down, fail over to backup
   export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=backup-signoz:4317
   kubectl rollout restart deployment/codetoreum
   ```

3. **Configuration Error:**
   ```bash
   # Verify environment variables propagated to pods
   kubectl exec -it codetoreum-pod -- env | grep OTEL

   # Recreate pods if stale
   kubectl rollout restart deployment/codetoreum
   ```

4. **Certificate Issue (TLS):**
   ```bash
   # Test TLS connection
   openssl s_client -connect $SIGNOZ_HOST:4317

   # Use insecure temporarily (not for production)
   export SIGNOZ_INSECURE=true
   ```

**Escalation:** If issue persists after 15 minutes, escalate to observability backend support.

---

### Incident: High Memory Usage

**Severity:** P1 (Critical)

**Symptoms:**
- Application memory growing over time
- Kubernetes pod OOMKilled
- Slow application performance

**Diagnosis:**

```bash
# Step 1: Check memory metrics
kubectl top pod codetoreum-pod

# Step 2: Check OTEL queue sizes
curl http://localhost:8000/metrics | grep otel_queue_size

# Step 3: Dump memory profile
curl http://localhost:8000/debug/pprof/heap > heap.prof
```

**Resolution Steps:**

1. **OTEL Queues Full (Most Common):**
   ```bash
   # Reduce queue sizes immediately
   kubectl set env deployment/codetoreum \
     OTEL_BATCH_SPAN_PROCESSOR_MAX_QUEUE_SIZE=1024 \
     OTEL_BATCH_LOG_PROCESSOR_MAX_QUEUE_SIZE=1024

   # Increase export frequency
   kubectl set env deployment/codetoreum \
     OTEL_BATCH_SPAN_PROCESSOR_SCHEDULE_DELAY_MILLIS=2000
   ```

2. **High Traffic Spike:**
   ```bash
   # Enable aggressive sampling
   kubectl set env deployment/codetoreum \
     OTEL_TRACES_SAMPLER=traceidratio \
     OTEL_TRACES_SAMPLER_ARG=0.01
   ```

3. **Memory Leak in OTEL:**
   ```bash
   # Disable observability temporarily
   kubectl set env deployment/codetoreum OTEL_ENABLED=false

   # File bug report with memory profile
   ```

4. **Emergency: Scale Out:**
   ```bash
   # Increase replicas to distribute load
   kubectl scale deployment/codetoreum --replicas=5
   ```

**Post-Incident:**
- Review traffic patterns
- Adjust queue sizes for normal load + 50% buffer
- Consider horizontal pod autoscaling (HPA)

---

### Incident: Export Failures After Deployment

**Severity:** P2 (High)

**Symptoms:**
- Trace/log export failures spike immediately after deployment
- `otel.trace.export.failures` metric elevated
- Application otherwise healthy

**Diagnosis:**

```bash
# Step 1: Check what changed
git diff HEAD~1 HEAD -- config/

# Step 2: Compare environment variables
kubectl describe deployment/codetoreum | grep -A 50 "Environment:"

# Step 3: Check new endpoints
echo $OTEL_EXPORTER_OTLP_TRACES_ENDPOINT
echo $OTEL_EXPORTER_OTLP_LOGS_ENDPOINT
```

**Resolution Steps:**

1. **Configuration Typo:**
   ```bash
   # Fix typo in endpoint
   kubectl set env deployment/codetoreum \
     OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=correct-endpoint:4317
   ```

2. **New Environment Variable Not Applied:**
   ```bash
   # Verify ConfigMap/Secret updated
   kubectl get configmap codetoreum-config -o yaml

   # Restart to pick up changes
   kubectl rollout restart deployment/codetoreum
   ```

3. **Backend Migration:**
   ```bash
   # If migrating to new backend, verify both endpoints work
   grpcurl -plaintext old-signoz:4317 list
   grpcurl -plaintext new-signoz:4317 list
   ```

4. **Rollback:**
   ```bash
   # If issue persists, rollback deployment
   kubectl rollout undo deployment/codetoreum
   ```

---

## Capacity Planning

### Traffic Growth Projections

**Current State (Baseline):**
- 1,000 requests/minute
- 10,000 spans/minute
- 2,000 log records/minute
- Memory: 50MB
- CPU: 5% overhead

**Growth Scenario: 10x Traffic**

| Metric | Baseline | 10x Traffic | Action Required |
|--------|----------|-------------|-----------------|
| Requests/min | 1,000 | 10,000 | Scale horizontally |
| Spans/min | 10,000 | 100,000 | Increase queue sizes |
| Logs/min | 2,000 | 20,000 | Consider sampling |
| Memory | 50MB | 200-300MB | Increase pod memory limits |
| CPU | 5% | 15-20% | Increase CPU limits |
| Network | 1 MB/sec | 10 MB/sec | Verify backend can handle |

**Recommended Actions:**

1. **Horizontal Scaling:**
   ```bash
   # Increase replicas
   kubectl scale deployment/codetoreum --replicas=10

   # Enable HPA
   kubectl autoscale deployment codetoreum --min=5 --max=20 --cpu-percent=70
   ```

2. **Increase Resource Limits:**
   ```yaml
   resources:
     limits:
       memory: 512Mi  # Was 256Mi
       cpu: 1000m     # Was 500m
     requests:
       memory: 256Mi  # Was 128Mi
       cpu: 500m      # Was 250m
   ```

3. **Tune Batch Processing:**
   ```bash
   # Larger batches for efficiency
   export OTEL_BATCH_SPAN_PROCESSOR_MAX_QUEUE_SIZE=8192
   export OTEL_BATCH_SPAN_PROCESSOR_MAX_EXPORT_BATCH_SIZE=2048
   ```

4. **Enable Sampling:**
   ```bash
   # Reduce to 10% sampling
   export OTEL_TRACES_SAMPLER=traceidratio
   export OTEL_TRACES_SAMPLER_ARG=0.1
   ```

---

### Backend Capacity Planning

**Signoz Requirements (10,000 spans/min):**
- Storage: ~5-10 GB/day (depends on retention)
- Memory: 4-8 GB
- CPU: 2-4 cores
- Network: ~10 MB/sec ingestion

**Growth Planning:**

| Metric | Current | 6 Months | 12 Months | Backend Action |
|--------|---------|----------|-----------|----------------|
| Daily Spans | 14M | 70M | 140M | Scale Signoz horizontally |
| Storage/Day | 5 GB | 25 GB | 50 GB | Increase disk capacity |
| Retention | 30 days | 30 days | 15 days | Reduce retention or add storage |

---

## Cost Optimization

### Cost Breakdown

**Observability Costs (Estimated Monthly):**
- Backend infrastructure (Signoz): $500-2,000
- Network egress: $50-200
- Storage: $100-500
- **Total:** $650-2,700/month

### Optimization Strategies

#### Strategy 1: Sampling (50-90% cost reduction)

```bash
# From 100% to 10% sampling
export OTEL_TRACES_SAMPLER=traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.1

# Cost reduction: ~90%
# Trade-off: Miss 90% of traces (still good for debugging patterns)
```

#### Strategy 2: Disable Logs (30-50% cost reduction)

```bash
# Keep traces, disable log export
export OTEL_LOGS_ENABLED=false

# Cost reduction: ~30-50%
# Trade-off: No centralized logs (local logs still work)
```

#### Strategy 3: Reduce Retention (20-40% cost reduction)

```yaml
# In Signoz configuration
retention:
  traces: 7d     # Was 30d
  logs: 3d       # Was 30d
  metrics: 30d   # Keep metrics longer
```

#### Strategy 4: Smart Sampling (Head-based)

```python
# Custom sampler: Always sample errors, 10% for success
from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio

class ErrorAwareSampler(ParentBasedTraceIdRatio):
    def should_sample(self, context, trace_id, name, kind, attributes, links):
        # Always sample if error
        if attributes.get("http.status_code", 0) >= 400:
            return SamplingResult(Decision.RECORD_AND_SAMPLE)

        # Otherwise, sample 10%
        return super().should_sample(context, trace_id, name, kind, attributes, links)
```

#### Strategy 5: Tail-based Sampling (Advanced)

```bash
# Use OpenTelemetry Collector with tail-based sampling
# Sample 100% of errors, 10% of successes
# Requires OTLP Collector deployment
```

**Cost Optimization Recommendations by Environment:**

| Environment | Sampling | Logs | Retention | Est. Monthly Cost |
|-------------|----------|------|-----------|-------------------|
| Development | 100% | Enabled | 7 days | $100 |
| Staging | 50% | Enabled | 14 days | $300 |
| Production | 10% | Enabled | 30 days | $1,000 |
| Production (Optimized) | 10% | Disabled | 14 days | $400 |

---

## Maintenance Tasks

### Weekly Tasks

- [ ] Review trace export failure rate
- [ ] Check queue size trends
- [ ] Review memory usage trends
- [ ] Verify all alerts firing correctly
- [ ] Check backend disk usage

### Monthly Tasks

- [ ] Review sampling strategy effectiveness
- [ ] Analyze cost trends
- [ ] Review retention policy
- [ ] Update runbook with new learnings
- [ ] Test backup/DR procedures

### Quarterly Tasks

- [ ] Capacity planning review
- [ ] Backend upgrade planning
- [ ] Cost optimization review
- [ ] Disaster recovery drill
- [ ] Security audit (TLS certificates, API keys)

---

## Emergency Contacts

| Role | Contact | Escalation Time |
|------|---------|-----------------|
| Platform Team Lead | platform-lead@example.com | Immediate |
| Observability Team | observability@example.com | 15 minutes |
| Signoz Support | support@signoz.io | 30 minutes |
| On-Call SRE | +1-555-0123 | Immediate |

---

## Appendix: Scripts

### Script: Health Check

```bash
#!/bin/bash
# scripts/check-otel-health.sh

echo "Checking OpenTelemetry Health..."

# Check configuration
if [ "$OTEL_ENABLED" != "true" ]; then
  echo "❌ OTEL_ENABLED is not true"
  exit 1
fi

# Check endpoints
if ! grpcurl -plaintext $SIGNOZ_HOST:4317 list > /dev/null 2>&1; then
  echo "❌ Cannot connect to traces endpoint"
  exit 1
fi

if ! curl -s http://$SIGNOZ_HOST:4318/v1/logs > /dev/null 2>&1; then
  echo "❌ Cannot connect to logs endpoint"
  exit 1
fi

# Check queue sizes
QUEUE_SIZE=$(curl -s http://localhost:8000/metrics | grep "otel_trace_queue_size" | awk '{print $2}')
if [ "$QUEUE_SIZE" -gt 1800 ]; then
  echo "⚠️  Queue size high: $QUEUE_SIZE"
fi

echo "✅ OpenTelemetry health check passed"
```

### Script: Export Metrics

```bash
#!/bin/bash
# scripts/export-otel-metrics.sh

curl -s http://localhost:8000/metrics | grep "^otel_" | \
  awk '{print $1, $2}' | \
  column -t
```

---

_OpenTelemetry Operations Runbook for Codetoreum. For developer documentation, see OPENTELEMETRY_INSTRUMENTATION_COMPLETE.md._
