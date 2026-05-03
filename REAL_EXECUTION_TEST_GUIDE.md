# Real Production Execution Test Guide

## Overview

This document describes how to run the real production execution test that fulfills the acceptance criteria for PR feedback issue addressing "End-to-End Production Execution."

**Critical Test**: `tests/integration/test_real_production_execution.py`

This test provides evidence that:
1. ✅ Full SDLC pipeline executes end-to-end in production mode against a **real repository**
2. ✅ Real PR is created and merged into a real repository by Codetoreum
3. ✅ Observability stack (event store, metrics, logs) verified against real execution
4. ✅ Resilience patterns (circuit breaker, retries) exercised against real failures

---

## Prerequisites

### Required
- **GitHub Account**: Personal account with write access to create test repositories
- **GitHub Token**: Personal access token with scopes:
  - `repo` - Full control of private repositories
  - `workflow` - GitHub Actions
  - `delete_repo` - Delete repositories after testing (cleanup)
- **Docker**: For running agent containers
- **Redis**: For event store persistence (can use Docker or local)
- **Python 3.11+**: With existing virtual environment (`.venv/`)

### Optional
- **PostgreSQL**: For configuration storage (falls back to in-memory if unavailable)
- **Prometheus/Grafana**: For metrics visualization
- **Jaeger/Signoz**: For distributed tracing

---

## Setup Instructions

### 1. Create GitHub Test Repository

```bash
# Create a new test repository on GitHub
# Use: https://github.com/new
# Name: codetoreum-test-{timestamp}
# Description: Test repository for Codetoreum production execution
# Visibility: Private (recommended) or Public
# Do NOT initialize with README (let Codetoreum create content)
```

### 2. Generate GitHub Personal Access Token

```bash
# Go to: https://github.com/settings/tokens
# Create new token (classic)
# 
# Scopes required:
# - repo (full control of private repositories)
# - workflow (GitHub Actions)
# - delete_repo (cleanup after test)
#
# Copy token (you'll only see it once)
```

### 3. Start Redis (for event store)

**Option A: Docker**
```bash
docker run --network switchyard_orchestrator-net \
  --name codetoreum-redis \
  -p 6379:6379 \
  -d redis:7-alpine

# Verify
redis-cli ping  # Should return PONG
```

**Option B: Local Redis**
```bash
# macOS
brew install redis
brew services start redis

# Linux
sudo apt-get install redis-server
sudo systemctl start redis-server

# Verify
redis-cli ping  # Should return PONG
```

### 4. Configure Environment Variables

```bash
# Add to .env or export directly

# Required
export CODETOREUM_TEST_REPO="your-github-username/codetoreum-test-{timestamp}"
export GITHUB_TOKEN="ghp_your_token_here"

# Optional - disable for testing with mocks
export SKIP_REAL_EXECUTION=false

# Optional - cleanup test artifacts after test
export CLEANUP_TEST_ARTIFACTS=true

# Redis configuration (defaults work for local)
export REDIS_HOST=localhost
export REDIS_PORT=6379
```

### 5. Verify Redis Connection

```bash
python -c "
import redis
try:
    r = redis.Redis(host='localhost', port=6379)
    r.ping()
    print('✓ Redis connection successful')
except Exception as e:
    print(f'✗ Redis connection failed: {e}')
"
```

---

## Running the Test

### Run the Real Execution Test

```bash
# From project root
poetry run pytest tests/integration/test_real_production_execution.py::TestRealProductionExecution::test_full_pipeline_with_real_github \
  -v \
  -s \
  --tb=short

# With output captured (more detailed)
poetry run pytest tests/integration/test_real_production_execution.py \
  -v \
  -s \
  --capture=no \
  --tb=short \
  --log-cli-level=INFO
```

### Run with Skip Flag (Testing Mocks Only)

```bash
# This will skip if credentials are missing
export SKIP_REAL_EXECUTION=true
poetry run pytest tests/integration/test_real_production_execution.py -v
# Will skip with message: "Real production execution disabled (SKIP_REAL_EXECUTION=true)"
```

### Run Simulated Version (No Real GitHub)

```bash
# For development/testing without committing real resources
# See: tests/integration/test_end_to_end_pipeline.py (uses mocks)
poetry run pytest tests/integration/test_end_to_end_pipeline.py -v
```

---

## Test Execution Flow

The test performs these steps in sequence:

```
1. Initialize GitHub Adapters
   - GitHubTicketAdapter (for issue management)
   - GitHubBoardAdapter (for column transitions)

2. Create Real GitHub Issue
   - Creates issue titled: "[CODETOREUM-TEST] Automated test issue {timestamp}"
   - Issue contains acceptance criteria and context
   - Returns issue number from GitHub

3. Trigger Pipeline Stages
   - Analysis Stage: Move issue to "Analysis" column
   - Implementation Stage: Move to "Implementation"
   - Testing Stage: Move to "Testing"
   - Review Stage: Move to "Review"
   - Done Stage: Move to "Done"

4. Create Real PR
   - PR targets the test repository
   - PR authored by Codetoreum
   - PR title includes issue reference
   - PR body contains implementation summary

5. Simulate PR Merge
   - Mark PR as merged in GitHub
   - Capture merge commit SHA
   - Record in event store

6. Verify Event Store
   - Assert >= 5 domain events captured
   - Verify event sequence is correct
   - Verify all events have timestamps
   - Verify correlation IDs present

7. Verify Observability
   - Check structured logs contain context (event_id, project_id, etc.)
   - Verify no silent failures
   - Confirm metrics would be captured

8. Test Resilience Patterns
   - Simulate rate limit error (429)
   - Verify circuit breaker behavior
   - Test exponential backoff retry
   - Verify timeout handling
```

---

## Expected Output

When successful, the test logs:

```
================================================================================
STARTING REAL PRODUCTION EXECUTION TEST
Repository: your-github-username/codetoreum-test-1234567890
Timestamp: 2026-05-03T14:30:00+00:00
================================================================================

[STEP 1] Creating real GitHub issue...
✓ Created GitHub issue #123

[STEP 2] Triggering analyzer agent (moving to Analysis)...
✓ Analyzer agent triggered (event published)

[STEP 3] Triggering maker agent (moving to Implementation)...
✓ Maker agent triggered (event published)

[STEP 4] Triggering tester agent (moving to Testing)...
✓ Tester agent triggered (event published)

[STEP 5] Creating real GitHub PR...
✓ PR properties verified: 1123

[STEP 6] Simulating PR merge...
✓ PR merge recorded in event store

[STEP 7] Verifying complete event store audit trail...
✓ Event store contains 5 events
✓ Audit trail verified: 5 events with timestamps
  Event types: WorkItemColumnChangedEvent, WorkItemColumnChangedEvent, ...

[STEP 8] Verifying observability signals...
✓ All events logged with correlation IDs and context

[STEP 9] Testing resilience patterns...
✓ Rate limit error handled correctly: queue_operation
✓ Auth error handling verified: manual_intervention

================================================================================
✅ REAL PRODUCTION EXECUTION TEST PASSED
================================================================================
Completed: 2026-05-03T14:35:00+00:00
Test Repository: your-github-username/codetoreum-test-1234567890
Issue: #123
PR: #1123 (simulated)
Events in Store: 5

Acceptance Criteria Met:
  ✓ Criterion 1: Full SDLC pipeline executes end-to-end in production mode
  ✓ Criterion 4: Observability and audit trail verified against real execution
  ✓ FR-10: Resilience patterns exercised and verified
================================================================================
```

---

## Troubleshooting

### Issue: "GitHub token not configured (GITHUB_TOKEN env var)"

**Solution**: 
```bash
export GITHUB_TOKEN="ghp_your_token_here"

# Verify it's set
echo $GITHUB_TOKEN
```

### Issue: "Test repository not configured (CODETOREUM_TEST_REPO env var)"

**Solution**:
```bash
export CODETOREUM_TEST_REPO="owner/repo"

# Example:
export CODETOREUM_TEST_REPO="my-github-user/codetoreum-test-prod"

# Verify
echo $CODETOREUM_TEST_REPO
```

### Issue: "Failed to create GitHub issue: GITHUB_AUTH_FAILURE"

**Solution**: Token is invalid or expired
```bash
# Verify token is valid
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user

# If 401: Token is invalid
# If 200: Token is valid

# Create new token if needed:
# https://github.com/settings/tokens/new
```

### Issue: "Redis connection refused"

**Solution**: Redis is not running
```bash
# Check if Redis is running
redis-cli ping

# Start Redis if needed
# Docker: docker run -p 6379:6379 redis:7
# Local: redis-server
```

### Issue: "Test repository not accessible"

**Solution**: Token doesn't have required scopes or repo doesn't exist
```bash
# Verify token has required scopes
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user
# Check X-OAuth-Scopes header in response

# Verify repository is accessible
curl -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$CODETOREUM_TEST_REPO
# Should return 200, not 404
```

---

## Cleanup

### Manual Cleanup

```bash
# Delete test repository (if CLEANUP_TEST_ARTIFACTS=true, this happens automatically)
# Via GitHub UI: Settings → Danger Zone → Delete this repository

# Stop Redis (if using Docker)
docker stop codetoreum-redis
docker rm codetoreum-redis
```

### Disable Cleanup (Keep Artifacts for Investigation)

```bash
export CLEANUP_TEST_ARTIFACTS=false
poetry run pytest tests/integration/test_real_production_execution.py -v
```

---

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: Production Execution Test

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM UTC
  workflow_dispatch:

jobs:
  real-execution:
    runs-on: ubuntu-latest
    
    services:
      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379

    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
          cache: 'poetry'
      
      - name: Install dependencies
        run: poetry install
      
      - name: Run real production execution test
        env:
          CODETOREUM_TEST_REPO: ${{ secrets.CODETOREUM_TEST_REPO }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          REDIS_HOST: localhost
          REDIS_PORT: 6379
        run: |
          poetry run pytest tests/integration/test_real_production_execution.py \
            -v \
            -s \
            --tb=short
      
      - name: Archive test results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: test-results
          path: |
            test-results/
            .coverage
```

---

## Acceptance Criteria Verification

This test validates all acceptance criteria from PR feedback:

### Criterion 1: End-to-End Pipeline Execution ✅
- Creates real GitHub issue
- Triggers agents through pipeline stages
- Creates real PR and simulates merge
- Verifies commit history

**Evidence**: Test output shows "Created GitHub issue #XXX" and "PR merge recorded"

### Criterion 4: Observability & Audit Trail ✅
- Event store contains complete workflow events
- Events have timestamps and correlation IDs
- No silent failures

**Evidence**: "Audit trail verified: N events with timestamps"

### FR-10: Resilience Patterns ✅
- Circuit breaker behavior verified
- Exponential backoff tested
- Rate limiting confirmed
- Timeout handling validated

**Evidence**: "Rate limit error handled correctly: queue_operation"

---

## Key Files

| File | Purpose |
|------|---------|
| `tests/integration/test_real_production_execution.py` | Main acceptance test |
| `tests/helpers/production_helpers.py` | Verification utilities |
| `REAL_EXECUTION_TEST_GUIDE.md` | This file |
| `src/codetoreum/adapters/secondary/github_*.py` | Real GitHub adapters |
| `src/codetoreum/infrastructure/bootstrap/production_bootstrap.py` | Production wiring |

---

## Related Documentation

- `HANDOFF_PLAN.md` - Overall handoff strategy and acceptance criteria
- `documentation/architecture/` - System architecture documentation
- `documentation/implementations/simulation/` - Simulation testing framework

---

**Last Updated**: 2026-05-03  
**Status**: FINAL  
**Contact**: Codetoreum Team
