---
description: End-to-end bootstrap test-fix cycle. Proves the Codetoreum production code path against real services by executing a GitHub issue through the full agent pipeline, then reports deficiencies found.
argument-hint: "[--project rounds] [--issue <number>]"
---

You are running the Codetoreum bootstrap harness — a deliberately minimal production run that uses real services (GitHub, Elasticsearch, Redis, Docker) to find deficiencies that simulation cannot expose.

## Mission

Drive one work item through the complete production pipeline:
- Real GitHub issue on `tinkermonkey/rounds`
- Real Claude Code agent executing inside a Docker container (`codetoreum-agent:latest`)
- Real Elasticsearch event store, Redis, and GitHub board operations
- MultiProjectOrchestrator as the polling orchestration entry point

**Success** means the agent ran in a container, produced a commit, and the work item auto-advanced to "In Review". **Failure** is a signal — diagnose it, fix the Codetoreum deficiency (not the symptom), and retry. Do not skip or paper over failures.

Retry budget: 3 fix-retry cycles before reporting blocked.

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

# Wait for health endpoint
sleep 5
until curl -s http://localhost:8000/api/v2/health | grep -q '"status"'; do
  sleep 2
  if ! kill -0 $CODETOREUM_PID 2>/dev/null; then
    echo "Server crashed. Last logs:"
    tail -50 /tmp/codetoreum.log
    exit 1
  fi
done
echo "Server ready"
```

Extract the authentication token — all REST API calls require it:
```bash
AUTH_TOKEN=$(grep "Authentication token:" /tmp/codetoreum.log | sed 's/.*Authentication token: //' | tr -d '[:space:]')
echo "Auth token: $AUTH_TOKEN"
```
If `AUTH_TOKEN` is empty, wait a moment and retry — the token is printed near the end of Phase 7.

If the server crashes or fails to start, read `/tmp/codetoreum.log`, diagnose, and fix. Common causes:
- Missing credentials (`GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, `ELASTICSEARCH_URL`)
- Bootstrap phase failure (check phase-specific log lines)
- Import errors

Verify the critical bootstrap phases completed:
```bash
grep -E "Phase 5c|Phase 5e|Loaded agent|Loaded board|multi.project.orchestrator.*started|Production bootstrap completed" /tmp/codetoreum.log
```

Phase 5c must show `Loaded agent 'senior_software_engineer'` and Phase 5e must show the MPO poll loop started. Both are required before triggering work.

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
  -H "Authorization: Bearer $AUTH_TOKEN" \
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
  -H "Authorization: Bearer $AUTH_TOKEN" \
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
  STATUS=$(curl -s -H "Authorization: Bearer $AUTH_TOKEN" "http://localhost:8000/api/v2/work-items/$WORK_ITEM_ID" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('current_column','?'), d.get('status','?'))" 2>/dev/null)
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
- `scheduling agent 'senior_software_engineer'` — agent queued
- `DockerContainerAdapter.*starting\|container.*created` — container launching
- `codetoreum-agent:latest` — container image pulled/started
- `ClaudeCodeAdapter.*execute\|claude.*--print` — agent running inside container
- `completed.*success=True` — agent succeeded, commit pushed
- `completed.*success=False` — agent failed
- `WorkItemColumnChangedEvent` — column transitions
- `Auto-progressing.*In Review` — successful auto-advance

---

## Step 8 — Fix Codetoreum problems

If execution fails or gets stuck, diagnose from the logs:

```bash
# Get full logs
cat /tmp/codetoreum.log

# Look for errors
grep -E "ERROR|CRITICAL|Traceback|Exception|ERR_" /tmp/codetoreum.log | head -50

# Check the work item state
curl -s -H "Authorization: Bearer $AUTH_TOKEN" "http://localhost:8000/api/v2/work-items/$WORK_ITEM_ID" | python3 -m json.tool
```

**Fix the root cause**, following the architecture:
- Domain layer bugs → fix domain models/events
- Application service bugs → fix application services
- Adapter bugs → fix the adapter, not the port
- Resilience bugs → fix infrastructure/resilience layer
- Bootstrap/wiring bugs → fix `production_bootstrap.py` or loader

After fixing, stop and restart the server, re-register the project, and retry from Step 3.

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
   AGENT_WORKSPACE_BASE=${AGENT_WORKSPACE_BASE:-/tmp/codetoreum/workspaces}
   ls $AGENT_WORKSPACE_BASE/
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

---

## Drill mode: restart

Goal: prove the system either resumes or surfaces orphan state when the server is killed mid-execution. This is the verification drill for persistence-grade in-memory replacements (lock service, run registry).

1. Complete Steps 1–6 above to trigger a work item.
2. Tail the server log and wait for the `WorkflowStartedEvent` line (Phase 5 of the run):
   ```bash
   until grep -q "WorkflowStartedEvent" /tmp/codetoreum.log; do sleep 1; done
   echo "Workflow started, killing server"
   ```
3. SIGTERM the server: `kill -15 $CODETOREUM_PID` (DO NOT use SIGKILL — we want clean teardown to be testable). Confirm the process exits.
4. Restart the server with the same command as Step 3.
5. After Phase 7 reports ready, query the work item:
   ```bash
   curl -s -H "Authorization: Bearer $AUTH_TOKEN" http://localhost:8000/api/v2/work-items/$WORK_ITEM_ID | python3 -m json.tool
   ```
6. Expected outcomes (any of these is acceptable; "no observable state at all" is not):
   - The executor detects the orphaned run (no matching `WorkflowCompletedEvent` for the existing `WorkflowStartedEvent`) and resumes or emits a `WorkflowOrphanedEvent`.
   - The lock state is rebuilt from persistence (Redis); the work item is still queued or running.
   - Auto-progression continues from the column the work item was in before restart.
7. Failure modes to report:
   - Work item silently stuck in the old column with no event trail.
   - Duplicate `WorkflowStartedEvent` for the same `work_item_id` (suggests the run registry lost state).
   - Lock service returns `ACQUIRED` for a new work item on the same board immediately (suggests the lock was lost and pipeline serialization is broken).

While `IPipelineLockService`, `IActiveWorkflowRunRegistry`, and `IWorkItemBranchTracker` are in-memory, this drill is expected to fail. The Phase B production adapters make it pass.

---

## Drill mode: concurrent

Goal: prove pipeline serialization holds when two work items are triggered on the same board before the first completes. This is the verification drill for the lock service's queueing behavior.

1. Complete Steps 1–3 to start the server.
2. Create two work items on the same board (call Step 5 twice with different `external_id`s). Record `WORK_ITEM_ID_A` and `WORK_ITEM_ID_B`.
3. Trigger both into "In Progress" back-to-back, without waiting:
   ```bash
   curl -s -X POST http://localhost:8000/api/v2/trigger/column-change \
     -H "Content-Type: application/json" -H "Authorization: Bearer $AUTH_TOKEN" \
     -d "{\"work_item_id\": \"$WORK_ITEM_ID_A\", \"to_column\": \"In Progress\", \"project_id\": \"rounds\", \"board_id\": \"rounds-board-1\"}"
   curl -s -X POST http://localhost:8000/api/v2/trigger/column-change \
     -H "Content-Type: application/json" -H "Authorization: Bearer $AUTH_TOKEN" \
     -d "{\"work_item_id\": \"$WORK_ITEM_ID_B\", \"to_column\": \"In Progress\", \"project_id\": \"rounds\", \"board_id\": \"rounds-board-1\"}"
   ```
4. Expected log patterns:
   - First trigger: `Lock acquired for $WORK_ITEM_ID_A`.
   - Second trigger: `try_acquire_lock` returns `LockStatus.QUEUED` for `$WORK_ITEM_ID_B` (NOT `ACQUIRED`).
   - When A finishes: `Lock released for $WORK_ITEM_ID_A, next work item: $WORK_ITEM_ID_B` followed by `Lock acquired for $WORK_ITEM_ID_B`.
5. Failure modes:
   - Both work items log `Lock acquired` simultaneously — pipeline serialization is broken (catastrophic).
   - B is never picked up after A completes — queue release/handoff is broken.
   - B is picked up but A's lock was force-released — stale-lock detection misfired.

After Phase B Step 2 ships `RedisPipelineLockService`, run this drill with two server instances (`docker compose up --scale codetoreum=2`) to prove multi-instance coordination.
