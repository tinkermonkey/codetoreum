# Real Production Execution Guide

## Overview

This guide explains how to execute actual real-world SDLC pipelines with Codetoreum using production adapters and real external services (GitHub, Docker, Elasticsearch).

**IMPORTANT**: Real production execution differs fundamentally from simulation testing:
- **Simulation Testing**: Fast, deterministic, no external dependencies (~30 seconds per scenario)
- **Production Execution**: Real external services, network delays, actual resource consumption (minutes to hours)

## Acceptance Criteria

Real production execution must satisfy:

1. **FR-6: Full SDLC Pipeline Execution**
   - Real GitHub repository with actual issues
   - Real Docker containers executing agents
   - Real code commits and pull requests
   - Complete stage-by-stage progression

2. **FR-8: Event Store Audit Trail**
   - All events persisted to Elasticsearch event store (not in-memory)
   - Complete event sequence captured
   - Timestamps for all state changes
   - Correlation IDs linking related events

3. **FR-9: Observability**
   - Structured logging with context
   - Metrics collection (Prometheus)
   - Distributed tracing (OpenTelemetry)
   - Dead letter queue for failed events

4. **FR-10: Resilience Patterns**
   - Circuit breakers on external service calls
   - Rate limiting on GitHub API
   - Retry logic with exponential backoff
   - Timeout protection on Docker execution

## Infrastructure Requirements

### GitHub

1. **Test Repository**
   - Create a test repository: `owner/codetoreum-test-repo`
   - Enable GitHub Projects v2 (for board functionality)
   - Configure webhook endpoint

2. **GitHub App**
   - Create a GitHub App with permissions:
     - `issues:read,write`
     - `contents:read,write`
     - `pull_requests:read,write`
     - `workflows:read,write`
   - Generate and store private key
   - Record App ID and webhook secret

### Docker

1. **Daemon Configuration**
   - Docker daemon must be running
   - Unix socket at `/var/run/docker.sock` (or configure DOCKER_HOST)
   - Sufficient disk space for agent execution (~1GB per agent run)
   - Memory limits configured for agent containers

2. **Network Configuration**
   - Containers must access internet for:
     - GitHub API (github.com)
     - PyPI for Python dependencies
     - Claude API (api.anthropic.com)

### Elasticsearch

1. **Cluster Setup**
   - Single-node cluster sufficient for testing
   - Default port: 9200
   - Index template auto-creation enabled
   - 1-2GB heap memory minimum

2. **Data Retention**
   - Keep at least 90 days of event data
   - Index lifecycle management (ILM) for cleanup

### APIs & Credentials

1. **GitHub Personal Access Token / App**
   - Required for: issue creation, PR operations, commit/push
   - Store securely in GITHUB_PRIVATE_KEY_PATH

2. **Anthropic API Key**
   - Required for Claude Code LLM operations
   - Store in ANTHROPIC_API_KEY environment variable

3. **JWT Secret Key**
   - Required for: authentication token signing
   - Generate with: `python -c 'import secrets; print(secrets.token_urlsafe(64))'`
   - Store in CODETOREUM_AUTH_SECRET_KEY

## Environment Setup

### 1. Set Required Environment Variables

```bash
# GitHub Integration
export GITHUB_APP_ID="<your-app-id>"
export GITHUB_PRIVATE_KEY_PATH="/path/to/private-key.pem"
export GITHUB_WEBHOOK_SECRET="<your-webhook-secret>"

# Elasticsearch Event Store
export ELASTICSEARCH_URL="http://localhost:9200"

# Anthropic API
export ANTHROPIC_API_KEY="sk-ant-..."

# Security
export CODETOREUM_AUTH_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')"

# Test Configuration
export TEST_GITHUB_REPO="owner/codetoreum-test-repo"
export TEST_AGENT_TIMEOUT="300"  # 5 minutes

# Optional
export DOCKER_HOST="unix:///var/run/docker.sock"
export AGENT_WORKSPACE_BASE="/tmp/codetoreum/workspaces"
```

### 2. Start Elasticsearch

```bash
# Docker (recommended)
docker run -d \
  --name elasticsearch \
  -e discovery.type=single-node \
  -e xpack.security.enabled=false \
  -p 9200:9200 \
  docker.elastic.co/elasticsearch/elasticsearch:8.0.0

# Or with docker-compose
docker-compose up -d elasticsearch
```

### 3. Verify Docker Access

```bash
docker info
# Should show Docker daemon info without errors
```

## Running Real Production Execution Tests

### Quick Start

```bash
# Verify environment setup
source /workspace/.env  # or export required variables

# Run the real production execution test
pytest tests/integration/test_real_end_to_end_production_execution.py::TestRealProductionExecution::test_full_sdlc_pipeline_with_real_adapters -v -s

# Expected output:
# - Multiple STEPS logged (1-9)
# - Real PR number in GitHub
# - Events persisted to Elasticsearch
# - Audit trail verified
# - Test completes with ✅ success
```

### What Happens During Execution

1. **Phase 0**: Environment validation
   - Checks all required env vars are set
   - Verifies credentials

2. **Phase 1**: Production bootstrap
   - Initializes all adapters (real GitHub, Docker, Elasticsearch)
   - Applies resilience decorators
   - Creates application services

3. **Phase 2-6**: SDLC Pipeline Execution
   - **Analysis Stage**: Analyzer agent runs in Docker, produces analysis
   - **Implementation Stage**: Maker agent runs, creates code changes
   - **Testing Stage**: Tester agent runs, validates changes
   - **Review Stage**: Creates real GitHub PR
   - **Completion**: Pipeline moves to Done

4. **Phase 7**: Event Audit Trail Verification
   - Queries Elasticsearch for all events
   - Verifies complete sequence
   - Checks timestamps and correlation IDs

5. **Phase 8**: Observability Verification
   - Checks structured logging
   - Verifies correlation IDs
   - Tests tracing support

6. **Phase 9**: Resilience Pattern Verification
   - Tests error classification
   - Verifies recovery strategies
   - Checks circuit breaker logic

### Expected Output

```
========================================================================
REAL PRODUCTION EXECUTION - FULL SDLC PIPELINE
========================================================================
Test Repository: owner/codetoreum-test-repo
Start Time: 2026-05-03T10:30:00+00:00
Event Store Backend: ElasticsearchEventStore

[INIT] Test Run Configuration
  Run ID: f47ac10b-58cc-4372-a567-0e02b2c3d479
  Correlation ID: e3f3e8f0-d8b5-4f8b-9b3c-3e3f3e8f0d8b
  Work Item ID: issue-1234567890

[STEP 1] Simulating GitHub issue creation...
  ✓ Issue creation event published and stored

[STEP 2] Analysis Stage - Analyzer Agent Execution
  ✓ Analysis stage initiated
  Agent executed with real Docker container

[STEP 3] Implementation Stage - Maker Agent Execution
  ✓ Implementation stage initiated
  Code changes committed to real repository

[STEP 4] Testing Stage - Tester Agent Execution
  ✓ Testing stage initiated
  Tests executed against real code changes

[STEP 5] Review Stage - Code Review Agent Execution
  ✓ Review stage initiated
  Real PR created: #5678
  PR URL: https://github.com/owner/codetoreum-test-repo/pull/5678

[STEP 6] Completion Stage - Pipeline Finished
  ✓ Pipeline completed successfully

[STEP 7] Verifying Event Store Audit Trail (FR-8)
  ✓ Event store audit trail verified:
    Total events: 6
    Has start event: true
    Has completion event: true
    All events timestamped: true
    Pipeline duration: 45.2 seconds

[STEP 8] Verifying Observability (FR-9)
  ✓ Structured logging verified
  ✓ Tracing support verified

[STEP 9] Verifying Resilience Patterns (FR-10)
  ✓ Resilience infrastructure verified
  ✓ Error classification working

========================================================================
✅ REAL PRODUCTION EXECUTION TEST PASSED
========================================================================
```

## Troubleshooting

### Connection Issues

**Elasticsearch Connection Failed**
```
ERROR: Failed to initialize Elasticsearch connection
  SOLUTION: Verify ELASTICSEARCH_URL is correct and Elasticsearch is running
  Check: curl http://localhost:9200/
```

**Docker Connection Failed**
```
ERROR: Docker health check failed
  SOLUTION: Verify Docker daemon is running and socket is accessible
  Check: docker info
```

**GitHub API Failed (401)**
```
ERROR: GitHub authentication failed
  SOLUTION: Verify GITHUB_APP_ID and GITHUB_PRIVATE_KEY_PATH are correct
  Check: Private key has correct permissions (600)
```

### Event Store Issues

**No Events in Elasticsearch**
```
Problem: Events not appearing after execution
  SOLUTION 1: Check if events are being appended (look for append errors in logs)
  SOLUTION 2: Verify Elasticsearch index was created: curl http://localhost:9200/_cat/indices
  SOLUTION 3: Query events directly:
    curl -X GET "http://localhost:9200/events-*/_search?q=work_item_id:<your-work-item-id>"
```

**Elasticsearch Index Errors**
```
Problem: Index creation failed
  SOLUTION: Reset Elasticsearch and retry
  docker-compose restart elasticsearch
  # Or reset data:
  docker volume rm codetoreum_elasticsearch_data
```

### Docker Execution Issues

**Container Fails to Start**
```
Problem: Agent container fails to run
  SOLUTION 1: Check Docker daemon logs
  SOLUTION 2: Verify agent image exists: docker images
  SOLUTION 3: Check available memory: docker info | grep Memory
  SOLUTION 4: Check disk space: docker system df
```

**Container Timeout**
```
Problem: Agent execution times out after 300 seconds
  SOLUTION 1: Increase TEST_AGENT_TIMEOUT
  SOLUTION 2: Check if agent is stuck: docker ps
  SOLUTION 3: Monitor memory: docker stats
```

## Advanced Configuration

### Running Multiple Pipelines in Sequence

```bash
# Run 3 full pipelines
for i in 1 2 3; do
  echo "Running pipeline $i..."
  pytest tests/integration/test_real_end_to_end_production_execution.py -v -s
  sleep 60  # Wait between runs
done
```

### Inspecting Events in Elasticsearch

```bash
# Get all events for a work item
curl -X GET "http://localhost:9200/events-*/_search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": {
      "term": {
        "work_item_id": "issue-1234567890"
      }
    },
    "sort": [{"timestamp": "asc"}]
  }'

# Get events by correlation ID
curl -X GET "http://localhost:9200/events-*/_search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": {
      "term": {
        "correlation_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479"
      }
    }
  }'
```

### Cleaning Up Test Data

```bash
# Delete test events from Elasticsearch
curl -X DELETE "http://localhost:9200/events-*/_doc" \
  -H "Content-Type: application/json" \
  -d '{
    "query": {
      "range": {
        "timestamp": {
          "gte": "2026-05-03T00:00:00Z"
        }
      }
    }
  }'

# Delete test GitHub issues/PRs
# (Must be done manually via GitHub web interface)
```

## CI/CD Integration

### GitHub Actions

```yaml
name: Real Production Execution

on:
  workflow_dispatch:  # Manual trigger only
  schedule:
    - cron: '0 2 * * 0'  # Weekly at 2 AM UTC

jobs:
  production-execution:
    runs-on: ubuntu-latest
    services:
      elasticsearch:
        image: docker.elastic.co/elasticsearch/elasticsearch:8.0.0
        env:
          discovery.type: single-node
          xpack.security.enabled: false
        options: >-
          --health-cmd "curl http://localhost:9200"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 9200:9200

    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Set environment variables
        run: |
          echo "GITHUB_APP_ID=${{ secrets.GITHUB_APP_ID }}" >> $GITHUB_ENV
          echo "GITHUB_PRIVATE_KEY_PATH=${{ secrets.GITHUB_PRIVATE_KEY }}" >> $GITHUB_ENV
          echo "ANTHROPIC_API_KEY=${{ secrets.ANTHROPIC_API_KEY }}" >> $GITHUB_ENV
          # ... other env vars
      
      - name: Run production execution test
        run: |
          pip install -e .
          pytest tests/integration/test_real_end_to_end_production_execution.py -v
      
      - name: Archive results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: production-execution-results
          path: test-results/
```

## Performance Expectations

| Stage | Time | Notes |
|-------|------|-------|
| Setup | 5-10 sec | Bootstrap, adapt initialization |
| Analysis | 2-5 min | Docker image pull (first run), agent execution |
| Implementation | 3-8 min | Code generation, repository operations |
| Testing | 2-5 min | Test execution in container |
| Review | 1-2 min | PR creation, validation |
| **Total** | **10-30 min** | First run longer due to Docker image pulls |

## Next Steps

1. Set up test infrastructure (GitHub repo, app, credentials)
2. Configure environment variables
3. Start Elasticsearch
4. Run initial test: `pytest tests/integration/test_real_end_to_end_production_execution.py -v -s`
5. Inspect results in Elasticsearch
6. Configure for CI/CD if desired
7. Monitor production execution patterns

## Support & Debugging

For detailed debugging:
1. Enable verbose logging: `LOG_LEVEL=DEBUG`
2. Check event store state: Query Elasticsearch directly
3. Monitor Docker: `docker stats`, `docker logs <container-id>`
4. Review GitHub for created issues/PRs
5. Check error classification: Review ProductionErrorHandler logs

## Related Documentation

- `documentation/architecture/` - Architecture specifications
- `documentation/implementations/production-bootstrap.md` - Bootstrap details
- `tests/integration/` - Other integration tests
- `CLAUDE.md` - Project guidelines and constraints
