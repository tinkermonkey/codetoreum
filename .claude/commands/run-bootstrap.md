---
description: End-to-end bootstrap test-fix cycle. Starts Codetoreum, finds or creates a GitHub issue on tinkermonkey/rounds, works it via the agent pipeline, then reports on the run.
argument-hint: "[--project rounds] [--issue <number>]"
---

You are driving an end-to-end test-fix cycle for Codetoreum against the `tinkermonkey/rounds` repository.

## Your Goal

Execute a real work item through the full Codetoreum pipeline:
1. Ensure infrastructure is running
2. Register the rounds project
3. Start the Codetoreum server
4. Find or create a GitHub issue on `tinkermonkey/rounds`
5. Create a work item and trigger execution
6. Monitor until completion or failure
7. If Codetoreum fails, diagnose and fix it (following the architecture), then retry
8. If execution succeeds, analyze the logs and report deficiencies

Work through this systematically. Fix real problems as you encounter them — do not skip or paper over failures.

---

## Step 1 — Start infrastructure

Check if Elasticsearch and Redis are running. Start them if not:

```bash
docker compose ps
docker compose up elasticsearch redis -d
# Wait for ES to be healthy (up to 60s)
until curl -s http://localhost:9200/_cluster/health | grep -q '"status":"green"\|"status":"yellow"'; do sleep 3; done
echo "ES ready"
```

---

## Step 2 — Register the rounds project

```bash
# Register rounds project config to ES
ELASTICSEARCH_URL=http://localhost:9200 .venv/bin/python bootstrap/register_project.py bootstrap/rounds.json
```

If this fails, investigate and fix `bootstrap/register_project.py` or `bootstrap/rounds.json`.

---

## Step 3 — Start the Codetoreum server

Start the server in the background and capture its logs:

```bash
ELASTICSEARCH_URL=http://localhost:9200 .venv/bin/codetoreum-server > /tmp/codetoreum.log 2>&1 &
CODETOREUM_PID=$!
echo "Server PID: $CODETOREUM_PID"

# Wait for it to be ready
sleep 5
until curl -s http://localhost:8000/health | grep -q '"status"'; do
  sleep 2
  # Check it hasn't crashed
  if ! kill -0 $CODETOREUM_PID 2>/dev/null; then
    echo "Server crashed. Last logs:"
    tail -50 /tmp/codetoreum.log
    exit 1
  fi
done
echo "Server ready"
```

If the server crashes or fails to start, read the logs at `/tmp/codetoreum.log`, diagnose the problem, and fix it. Common issues:
- Missing bootstrap Phase 5c (check `production_bootstrap.py`)
- Missing `project_bootstrap_loader.py`
- Import errors

Verify Phase 5c loaded correctly:
```bash
grep -E "Phase 5c|Loaded.*bootstrap|Loaded agent|Loaded board" /tmp/codetoreum.log
```

---

## Step 4 — Find or create a GitHub issue

Check for open issues on `tinkermonkey/rounds`:

```bash
gh issue list --repo tinkermonkey/rounds --state open --json number,title,body,labels
```

**Priority order for selecting an issue:**
1. Issue #65 — "test_cli_reads_and_executes_commands hangs indefinitely" — this is a well-scoped bug fix (add timeout + proper stdin closure to a subprocess test)
2. Any other open bug with a clear description
3. Issue #49 — "Prepare for first project" (only if more specific issues are exhausted)

**If no suitable issue exists**, analyze the rounds codebase to find a small, well-scoped improvement:

```bash
gh repo clone tinkermonkey/rounds /tmp/rounds-analysis 2>/dev/null || true
# Look at the test suite, README, and source for obvious gaps
ls /tmp/rounds-analysis/
cat /tmp/rounds-analysis/README.md
```

Then create a GitHub issue:
```bash
gh issue create --repo tinkermonkey/rounds \
  --title "..." \
  --body "..." \
  --label "bug"  # or enhancement
```

Record the issue number as `ISSUE_NUMBER` and the issue body as `ISSUE_BODY`.

---

## Step 5 — Create a work item

```bash
ISSUE_NUMBER=<number from above>
ISSUE_TITLE="<issue title>"
ISSUE_BODY="<issue body — this becomes Claude's prompt, so include all detail>"

WORK_ITEM_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v2/work-items \
  -H "Content-Type: application/json" \
  -d "{
    \"project_id\": \"rounds\",
    \"title\": \"$ISSUE_TITLE\",
    \"description\": \"$ISSUE_BODY\",
    \"external_id\": \"$ISSUE_NUMBER\",
    \"external_url\": \"https://github.com/tinkermonkey/rounds/issues/$ISSUE_NUMBER\",
    \"priority\": \"HIGH\"
  }")

echo "$WORK_ITEM_RESPONSE" | python3 -m json.tool
WORK_ITEM_ID=$(echo "$WORK_ITEM_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "Work item ID: $WORK_ITEM_ID"
```

If the API returns an error, read the server logs and fix the underlying problem.

---

## Step 6 — Trigger execution

```bash
TRIGGER_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v2/trigger/column-change \
  -H "Content-Type: application/json" \
  -d "{
    \"work_item_id\": \"$WORK_ITEM_ID\",
    \"to_column\": \"In Progress\",
    \"project_id\": \"rounds\",
    \"board_id\": \"rounds-board-1\"
  }")

echo "$TRIGGER_RESPONSE"
```

Expect HTTP 202. If you get an error, read the logs and fix it.

---

## Step 7 — Monitor execution

Tail the logs and poll work item status until the execution completes or fails:

```bash
# Tail recent logs
tail -f /tmp/codetoreum.log &
TAIL_PID=$!

# Poll work item status (up to 20 minutes)
for i in $(seq 1 120); do
  sleep 10
  STATUS=$(curl -s "http://localhost:8000/api/v2/work-items/$WORK_ITEM_ID" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('current_column','?'), d.get('status','?'))" 2>/dev/null)
  echo "[$i] Status: $STATUS"

  # Check for terminal states
  if echo "$STATUS" | grep -qE "In Review|Done|Backlog"; then
    echo "Terminal state reached: $STATUS"
    break
  fi
done

kill $TAIL_PID 2>/dev/null || true
```

Key log patterns to watch for:
- `scheduling agent 'senior_software_engineer'` — agent started
- `ClaudeCodeAdapter.*execute` — Claude subprocess running
- `completed.*success=True` — agent succeeded
- `completed.*success=False` — agent failed
- `WorkItemColumnChangedEvent` — column transitions

---

## Step 8 — Fix Codetoreum problems

If execution fails or gets stuck, diagnose from the logs:

```bash
# Get full logs
cat /tmp/codetoreum.log

# Look for errors
grep -E "ERROR|CRITICAL|Traceback|Exception|ERR_" /tmp/codetoreum.log | head -50

# Check the work item state
curl -s "http://localhost:8000/api/v2/work-items/$WORK_ITEM_ID" | python3 -m json.tool
```

**Fix the root cause**, following the architecture:
- Domain layer bugs → fix domain models/events
- Application service bugs → fix application services
- Adapter bugs → fix the adapter, not the port
- Resilience bugs → fix infrastructure/resilience layer
- Bootstrap/wiring bugs → fix `production_bootstrap.py` or loader

After fixing, stop and restart the server, re-register the project, and retry from Step 3.

**Retry budget**: Up to 3 fix-retry cycles before reporting blocked.

---

## Step 9 — Report results

After execution completes (or you exhaust retries):

### On success:

1. Read the full execution logs:
   ```bash
   cat /tmp/codetoreum.log
   ```

2. Check what Claude did in the rounds repo workspace:
   ```bash
   ls $AGENT_WORKSPACE_BASE/rounds/  # or check default workspace path
   ```

3. Analyze the logs for:
   - Slow phases (prompt building, cloning, LLM execution)
   - Missing observability (events not emitted, metrics not recorded)
   - Error handling gaps (silent failures, missing exc_info)
   - Architecture violations in the execution path
   - Any TODO/FIXME logged during execution

4. Report to the user:
   - What issue was worked
   - What Claude produced (commits, changes)
   - Codetoreum deficiencies observed, with specific log evidence
   - Recommended next fixes

### On failure (retries exhausted):

Report:
- Which step failed
- Root cause from logs
- What fixes were attempted
- What's still broken and why

---

## Architecture Constraints (MUST FOLLOW when fixing)

- Domain layer has NO external dependencies
- All external interactions go through port interfaces
- All state changes emit domain events (frozen dataclasses)
- Resilience patterns (retries, circuit breakers) live in infrastructure, not adapters
- Adapters stay pure — no resilience logic embedded
- No silent error handling — all errors logged with `exc_info=True`
- Simulation-only routes mount in `SimulationApplicationBootstrap`, NEVER in production `create_app()`
- Application services implementing output ports MUST explicitly inherit the port ABC

When in doubt about architecture decisions, consult the codetoreum-architect agent.
