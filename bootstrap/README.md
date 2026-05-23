# Codetoreum Bootstrap

Step-by-step guide to running Codetoreum against a real GitHub repository.

---

## Overview

Codetoreum executes Claude Code agents against a target codebase in response to a work item (task description). The minimal flow is:

```
register project → start server → create work item → trigger execution → Claude works on the repo
```

---

## Prerequisites

- Docker and Docker Compose
- A GitHub token with repo read/write access (already in `.env` as `GITHUB_TOKEN`)
- A Claude OAuth token (already in `.env` as `CLAUDE_CODE_OAUTH_TOKEN`)
- Elasticsearch running (included in `docker-compose.yml`)

---

## Step 1 — Register a project

A project tells Codetoreum which GitHub repository to clone and which agents handle which board columns.

Edit `bootstrap/project.json` for your target repository:

```json
{
  "project": {
    "id": "my-project",
    "name": "my-project",
    "github_org": "tinkermonkey",
    "github_repo": "my-repo",
    "description": "...",
    "default_branch": "main"
  },
  "agents": [
    {
      "name": "senior_software_engineer",
      "description": "Implements features and fixes bugs",
      "model": "claude-sonnet-4-6",
      "timeout": 3600,
      "requires_docker": true,
      "makes_code_changes": true,
      "capabilities": ["code_generation", "debugging", "refactoring", "testing"],
      "commit_policy": "on_success"
    }
  ],
  "board": {
    "id": "board-1",
    "name": "Development Pipeline",
    "columns": [
      { "name": "Backlog",     "type": "manual",    "agent_id": null,                        "is_pipeline_trigger": false, "is_exit_column": false, "auto_progress_on_completion": false },
      { "name": "Ready",       "type": "manual",    "agent_id": null,                        "is_pipeline_trigger": true,  "is_exit_column": false, "auto_progress_on_completion": false },
      { "name": "In Progress", "type": "automated", "agent_id": "senior_software_engineer",  "is_pipeline_trigger": false, "is_exit_column": false, "auto_progress_on_completion": true, "sla_seconds": 3600, "on_failure_column": "Backlog" },
      { "name": "In Review",   "type": "manual",    "agent_id": null,                        "is_pipeline_trigger": false, "is_exit_column": false, "auto_progress_on_completion": false },
      { "name": "Done",        "type": "manual",    "agent_id": null,                        "is_pipeline_trigger": false, "is_exit_column": true,  "auto_progress_on_completion": false }
    ]
  }
}
```

**Key fields:**
- `project.id` — used as the project key everywhere; no spaces
- `project.github_org` / `github_repo` — the repository Claude will clone and work in
- `agents[].name` — must match the `agent_id` in the automated board column
- `board.columns` — only the `automated` column triggers Claude; all others are manual gates

You can have multiple project JSON files. The server loads all `*.json` files in this directory on startup.

**Persist the config to Elasticsearch:**

```bash
# Start Elasticsearch first if not running
docker compose up elasticsearch -d

# Register the project
ELASTICSEARCH_URL=http://localhost:9200 .venv/bin/python bootstrap/register_project.py

# For a different project file:
ELASTICSEARCH_URL=http://localhost:9200 .venv/bin/python bootstrap/register_project.py bootstrap/other-project.json
```

This saves the project and agent configs to Elasticsearch so they survive restarts.

---

## Step 2 — Start the server

```bash
docker compose up
```

During startup, Phase 5c loads every `*.json` file in this directory into the server's in-memory agent registry and board workflow service. You will see log lines like:

```
Phase 5c: Loading project bootstrap configurations...
Loaded agent 'senior_software_engineer' for project 'my-project'
Loaded board template 'board-1' for project 'my-project' (5 columns)
Loaded 1 project bootstrap configuration(s)
```

> **Important**: Re-run `register_project.py` + restart the server any time you change `project.json`.

### Extract the authentication token

All REST API endpoints require a bearer token. The server generates one on startup and prints it to the log:

```
Authentication token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

Extract it into a shell variable for use in the steps below:

```bash
export CODETOREUM_TOKEN=$(docker compose logs codetoreum 2>&1 | grep "Authentication token:" | tail -1 | awk '{print $NF}')
echo "Token: $CODETOREUM_TOKEN"
```

If `CODETOREUM_TOKEN` is empty, wait a moment for startup to complete and re-run the export. The token is valid for 365 days and remains stable across restarts as long as `CODETOREUM_SECRET_KEY` is set in your `.env`.

---

## Step 3 — Create a work item

A work item is the task Claude will execute. You can create one manually via the API, with or without linking it to a GitHub issue.

### Option A — Plain task (no GitHub issue)

```bash
curl -s -X POST http://localhost:8000/api/v2/work-items \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $CODETOREUM_TOKEN" \
  -d '{
    "project_id": "my-project",
    "title": "Add input validation to the login endpoint",
    "description": "The /api/login endpoint does not validate the email format. Add email format validation that returns HTTP 422 with a descriptive error when the format is invalid. Write a unit test for the new validation.",
    "priority": "HIGH"
  }'
```

### Option B — Linked to a GitHub issue

If the task already exists as a GitHub issue, link it using `external_id` (the issue number) and `external_url`:

```bash
curl -s -X POST http://localhost:8000/api/v2/work-items \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $CODETOREUM_TOKEN" \
  -d '{
    "project_id": "my-project",
    "title": "Add input validation to login endpoint",
    "description": "The /api/login endpoint does not validate the email format. Add email format validation that returns HTTP 422 with a descriptive error when the format is invalid. Write a unit test for the new validation.",
    "external_id": "42",
    "external_url": "https://github.com/tinkermonkey/my-repo/issues/42",
    "priority": "HIGH"
  }'
```

> **Note on `description`**: This is the primary input to Claude's prompt. Write it the way you would write a ticket for a senior engineer — include the problem, the expected behaviour, and any constraints. The more specific the description, the better the output.

The response includes the work item `id` you need for the next step:

```json
{
  "id": "wi-abc123",
  "project_id": "my-project",
  "title": "Add input validation to the login endpoint",
  ...
}
```

---

## Step 4 — Trigger execution

Move the work item to `"In Progress"` to start the agent pipeline:

```bash
curl -s -X POST http://localhost:8000/api/v2/trigger/column-change \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $CODETOREUM_TOKEN" \
  -d '{
    "work_item_id": "wi-abc123",
    "to_column": "In Progress",
    "project_id": "my-project",
    "board_id": "board-1"
  }'
```

The server responds with `202 Accepted` immediately. Execution runs in the background.

---

## What happens next

Once triggered, Codetoreum runs the following chain automatically:

1. **Acquire pipeline lock** — prevents another work item from running concurrently on the same board
2. **Clone the repository** — clones `github.com/<org>/<repo>` into a workspace directory
3. **Build a prompt** — combines the work item title + description + agent role + stage instructions
4. **Run Claude Code** — starts a Docker container (`codetoreum-agent:latest`) with the cloned repo mounted; Claude Code runs inside the container, reads files, edits code, runs tests, and writes changes to the mounted workspace
5. **Finalize workspace** — commits and pushes the branch if execution succeeded
6. **Auto-advance** — moves the work item to `"In Review"` (because `auto_progress_on_completion: true`)
7. **Release lock** — unblocks the next queued work item

If execution fails, the work item is moved to `"Backlog"` (the `on_failure_column`).

---

## Monitoring

**Server logs** are the primary observability tool. Look for:

```
ExecutionServiceAgentExecutor: scheduling agent 'senior_software_engineer' for 'wi-abc123'
ExecutionServiceAgentExecutor: 'senior_software_engineer' completed for 'wi-abc123' (success=True)
```

**Check work item status:**

```bash
curl -s -H "Authorization: Bearer $CODETOREUM_TOKEN" \
  http://localhost:8000/api/v2/work-items/wi-abc123 | python3 -m json.tool
```

**List all work items for a project:**

```bash
curl -s -H "Authorization: Bearer $CODETOREUM_TOKEN" \
  "http://localhost:8000/api/v2/work-items?project_id=my-project" | python3 -m json.tool
```

**API docs** (when server is running):

```
http://localhost:8000/docs
```

---

## Current limitations

| Limitation | Detail |
|---|---|
| No GitHub webhook | Work items must be created manually via the API. Webhook-driven automation requires the server to be publicly reachable (ngrok or similar). |
| Docker required | Agents run in `codetoreum-agent:latest` containers. The Docker socket must be available and the image must be built before the first run. |
| Single-agent pipeline | The default board has one automated stage. Multi-stage pipelines (design → implement → test) require additional columns and agent definitions. |
| In-memory agent/board state | Board templates and agent domain objects are held in memory. A server restart re-loads them from `bootstrap/*.json`. |

---

## Adding a second project

Create a new JSON file alongside `project.json`:

```bash
cp bootstrap/project.json bootstrap/my-other-project.json
# edit my-other-project.json — change project.id, github_org, github_repo
ELASTICSEARCH_URL=http://localhost:9200 .venv/bin/python bootstrap/register_project.py bootstrap/my-other-project.json
docker compose restart codetoreum
```

Each project gets its own board (by `board.id`), its own agents, and its own pipeline lock. Work items from different projects can run concurrently.
