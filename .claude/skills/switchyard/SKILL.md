# Switchyard Pipeline Run Analysis Skill

You are analyzing real pipeline run data from **Switchyard** — the production predecessor to Codetoreum — to identify patterns, failure modes, and workflow behaviors that should be reflected in Codetoreum's simulation scenarios (`scenarios/`).

## Context

Switchyard is a running AI agent orchestration system with 300+ recorded pipeline runs across multiple projects and boards. Its data is the ground truth for what real agent-driven software workflows look like. Codetoreum's simulation scenarios should model these real behaviors with fidelity.

### Elasticsearch Access

**Host**: `http://localhost:9200` (no authentication required)

### Indices

| Index | Contents | Key fields |
|-------|----------|------------|
| `pipeline-runs-*` | One doc per pipeline run | `id` (keyword), `project` (keyword), `board` (keyword), `issue_number`, `issue_title` (text), `started_at`, `ended_at`, `status` (keyword), `outcome` (keyword: `"failed"` or null), `summary` (text — rich narrative), `orchestratorRecommendations` (array), `projectRecommendations` (array), `discussion_id` |
| `decision-events-*` | Orchestrator decisions | `pipeline_run_id` (keyword), `timestamp`, `event_type`, `agent`, `decision_category`, `inputs`, `decision`, `reason`, `event_category` |
| `agent-events-*` | Agent lifecycle events | `pipeline_run_id` (keyword), `timestamp`, `event_type`, `agent`, `container_name`, `event_category` |

> **Note**: Indices are date-partitioned (e.g., `decision-events-2026-03-26`) with 7-day ILM retention. Always query with wildcards: `pipeline-runs-*`, `decision-events-*`, `agent-events-*`.

### Known Data Shape

- **Boards**: `"SDLC Execution"` (~280 runs), `"Planning & Design"` (~42 runs)
- **Projects**: `context-studio`, `context-library`, `documentation_robotics`, `codetoreum`, `agent_team_ansible`
- **Outcomes**: `"failed"` (~10 runs have explicit failure analysis); most runs have `null` outcome (completed without error)
- **Summary field**: Rich markdown narrative with timeline, root cause analysis, agent performance, and recommendations — only populated on runs that triggered post-completion analysis

---

## Codetoreum Scenarios (for comparison)

Scenarios live in `scenarios/`. Each scenario has a `scenario.md` and YAML config files under `orchestrator/` and `external/`. Current scenarios:

| Directory | What it tests |
|-----------|---------------|
| `sdlc_pipeline/` | Full 6-column SDLC: Backlog→Ready→In Progress→Code Review→Testing→Done |
| `review_cycle/` | Maker-checker with human gate, SLA escalation, `Changes Requested` column |
| `failure_recovery/` | Flaky agent (50% failure rate), `on_failure_column` routing, manual recovery |
| `repair_cycle_test/` | Test-fix-validate loops with repair agents |
| `smoke/` | Minimal sanity scenario |
| `stress_test/` | Load and concurrency |
| `dev_environment_repair/` | Container recovery and environment repair |

---

## How to Search and Fetch Runs

### List recent completed runs
```bash
curl -s "http://localhost:9200/pipeline-runs-*/_search" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": { "term": { "status": "completed" } },
    "sort": [{ "ended_at": "desc" }],
    "size": 20,
    "_source": ["id", "project", "board", "issue_number", "issue_title", "started_at", "ended_at", "outcome"]
  }'
```

### Search runs by issue title / description
```bash
curl -s "http://localhost:9200/pipeline-runs-*/_search" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "bool": {
        "must": [{ "match": { "issue_title": "SEARCH_TERM" } }]
      }
    },
    "sort": [{ "ended_at": "desc" }],
    "size": 10,
    "_source": ["id", "project", "board", "issue_number", "issue_title", "started_at", "ended_at", "outcome"]
  }'
```

### Fetch a specific pipeline run by ID
```bash
curl -s "http://localhost:9200/pipeline-runs-*/_search" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": { "term": { "id": "PIPELINE_RUN_ID" } },
    "size": 1
  }'
```

### Filter by board and/or project
```bash
curl -s "http://localhost:9200/pipeline-runs-*/_search" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "bool": {
        "filter": [
          { "term": { "status": "completed" } },
          { "term": { "board": "SDLC Execution" } },
          { "term": { "project": "context-library" } }
        ]
      }
    },
    "sort": [{ "ended_at": "desc" }],
    "size": 10,
    "_source": ["id", "project", "board", "issue_number", "issue_title", "started_at", "ended_at", "outcome"]
  }'
```

### Get failed runs
```bash
curl -s "http://localhost:9200/pipeline-runs-*/_search" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": { "term": { "outcome": "failed" } },
    "sort": [{ "ended_at": "desc" }],
    "size": 20,
    "_source": ["id", "project", "board", "issue_number", "issue_title", "outcome", "summary"]
  }'
```

### Get full timeline for a specific run (decision + agent events)
```bash
PIPELINE_RUN_ID="<uuid>"

# Decision events (routing, stage transitions, errors, branch management)
curl -s "http://localhost:9200/decision-events-*/_search" \
  -H 'Content-Type: application/json' \
  -d "{
    \"query\": { \"term\": { \"pipeline_run_id\": \"$PIPELINE_RUN_ID\" } },
    \"sort\": [{ \"timestamp\": \"asc\" }],
    \"size\": 1000
  }"

# Agent lifecycle events (container launches, tool calls, completions, failures)
curl -s "http://localhost:9200/agent-events-*/_search" \
  -H 'Content-Type: application/json' \
  -d "{
    \"query\": { \"term\": { \"pipeline_run_id\": \"$PIPELINE_RUN_ID\" } },
    \"sort\": [{ \"timestamp\": \"asc\" }],
    \"size\": 1000
  }"
```

### Search run summaries for a keyword (full-text search on rich narrative)
```bash
curl -s "http://localhost:9200/pipeline-runs-*/_search" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "match": { "summary": "KEYWORD" }
    },
    "size": 5,
    "_source": ["id", "project", "board", "issue_number", "issue_title", "outcome"]
  }'
```

---

## Analysis Framework

When analyzing pipeline runs against simulation scenarios, structure your output as follows:

### 1. Run Overview
- Project, board, issue title, outcome, duration
- Which Switchyard agents participated (maps to Codetoreum agent roles)
- Whether a `summary` exists (indicates post-run analysis was performed)

### 2. Stage / Column Mapping
Map what happened in Switchyard to Codetoreum board columns:
- Switchyard "Development" → Codetoreum "In Progress"
- Switchyard "Code Review" → Codetoreum "Code Review"
- Branch management decisions → `IVersionControlService` behaviors
- Human feedback loops → manual column patterns with `is_pipeline_trigger`

### 3. Failure Mode Analysis
If the run failed or had errors, identify:
- **Primary failure type**: git conflict, agent error, timeout, external API failure, etc.
- **Recovery behavior**: was the item moved to a failure column? Was there a human gate?
- **Which scenario covers this**: match to `failure_recovery/`, `repair_cycle_test/`, etc.
- **Gap**: what failure mode is NOT covered by any existing scenario?

### 4. Human Feedback Loop Detection
Look for `discussion_id` on pipeline run docs and `event_type: "human_feedback_*"` in decision events. These indicate:
- An agent posted output and a human replied
- The agent responded to feedback in a conversational loop
- Maps to Codetoreum's `review_cycle/` scenario and `ConversationalLoopOrchestrator`

### 5. Scenario Gap Analysis
For each run analyzed, answer:
- **Covered**: which existing scenario models this behavior?
- **Partially covered**: which scenario is close but missing key details?
- **Not covered**: what new scenario should be created to model this?
- **Depth**: does the existing scenario capture the edge cases seen in production?

### 6. Recommendations
Produce actionable suggestions in one of two forms:
- **Enrich existing scenario**: specific additions to `scenario.md` or YAML configs (new failure modes, additional work items, timing details)
- **New scenario**: a name, board flow sketch, and what it validates

---

## Common Patterns Found in Switchyard Data

Use these as a reference when categorizing runs:

| Pattern | Switchyard behavior | Codetoreum scenario |
|---------|--------------------|--------------------|
| Normal SDLC | 2-3 agents, no failures | `sdlc_pipeline/` |
| Reviewer finds issues | `code_reviewer` posts "CHANGES NEEDED" | `review_cycle/` (on_failure routing) |
| Git push conflict | Non-fast-forward on shared branch | Not fully covered — gap |
| Human feedback reply | Human comments trigger agent re-entry | Partially in `review_cycle/` |
| Agent no-op (no file changes) | Agent completes, nothing committed | Not covered — gap |
| Shared parent branch | Sub-issues share feature branch | Not covered — gap |
| Planning & Design board | Single-agent issue analysis/design | Not covered — gap |
