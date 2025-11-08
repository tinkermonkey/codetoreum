# Simulation Mode Usage Guide

## Overview

This guide shows you how to start and interact with the Codetoreum simulation server for manual testing, demos, and development. The simulation server provides a full FastAPI application with all features enabled, using in-memory mock adapters instead of external services.

**Time to get started: <5 minutes**

## Prerequisites

- Python 3.11+
- Project dependencies installed (`pip install -e .`)
- No external services required (GitHub, Docker, Redis, etc.)

## Quick Start

### Start the Server (Default Configuration)

```bash
python -m codetoreum.cli.simulation_server
```

**Output:**
```
═══════════════════════════════════════════
   Codetoreum Simulation Server
═══════════════════════════════════════════

Loading Configuration
Using built-in scenario: default
Speed multiplier: 1.0x

Bootstrapping Application
✓ Application bootstrapped successfully

Seeding Test Data
Seeding from built-in scenario: default
✓ Data seeded successfully
  Projects: 1, Workflows: 1, Agents: 3, Work Items: 2

╭─────────── Simulation Server Started ───────────╮
│  Host              localhost                     │
│  Port              8000                          │
│  Scenario          default                       │
│  Speed Multiplier  1.0x                          │
│  Debug Mode        Disabled                      │
│                                                   │
│  Seeded Projects   1                             │
│  Seeded Workflows  1                             │
│  Seeded Agents     3                             │
│  Seeded Work Items 2                             │
╰──────────────────────────────────────────────────╯

URLs:
  API Docs:      http://localhost:8000/docs
  Health Check:  http://localhost:8000/api/health
  WebSocket:     ws://localhost:8000/ws

NOTE: Server running in SIMULATION MODE
All data is in-memory and will be lost on shutdown
```

### Access the API Documentation

Open your browser to: **http://localhost:8000/docs**

You'll see the interactive OpenAPI documentation with all endpoints.

## Command-Line Options

### Server Configuration

```bash
# Custom port
python -m codetoreum.cli.simulation_server --port 8080

# Custom host (for network access)
python -m codetoreum.cli.simulation_server --host 0.0.0.0 --port 8080

# Enable debug logging
python -m codetoreum.cli.simulation_server --debug
```

### Built-in Scenarios

Choose a pre-configured scenario:

```bash
# Demo scenario (realistic project with 5 work items)
python -m codetoreum.cli.simulation_server --scenario demo

# Stress test (many projects and work items)
python -m codetoreum.cli.simulation_server --scenario stress_test

# Review cycle (demonstrates feedback loops)
python -m codetoreum.cli.simulation_server --scenario review_cycle

# Failure recovery (demonstrates retry logic)
python -m codetoreum.cli.simulation_server --scenario failure_recovery
```

**Available Scenarios:**
- `default` - Minimal scenario (1 project, 1 workflow, 2 work items)
- `demo` - Realistic demo (1 project, 1 workflow, 5 work items, 5 agents)
- `stress_test` - High load (10 projects, 5 workflows each, 50 work items)
- `review_cycle` - Review loop (1 work item with rejection/approval cycle)
- `failure_recovery` - Failure handling (1 work item with execution failure and retry)

### Custom Scenario File

```bash
# Load custom YAML scenario
python -m codetoreum.cli.simulation_server --scenario-file /path/to/custom.yaml
```

See [Scenario File Format](#scenario-file-format) section below.

### Time Acceleration

```bash
# 10x faster (30 minutes → 3 minutes)
python -m codetoreum.cli.simulation_server --speed-multiplier 10.0

# 100x faster (30 minutes → 18 seconds)
python -m codetoreum.cli.simulation_server --speed-multiplier 100.0
```

### Empty Start (No Seeding)

```bash
# Start with no pre-loaded data
python -m codetoreum.cli.simulation_server --no-seed
```

Useful when you want to create all data via API calls.

## Interacting via REST API

### Health Check

```bash
curl http://localhost:8000/api/health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "mode": "simulation",
  "timestamp": "2025-01-01T12:00:00Z"
}
```

### List Projects

```bash
curl http://localhost:8000/api/v2/projects
```

**Response:**
```json
{
  "items": [
    {
      "id": "proj-001",
      "name": "example-project",
      "description": "Example project for testing",
      "repository_url": "https://github.com/example/repo.git",
      "default_branch": "main",
      "created_at": "2025-01-01T12:00:00Z"
    }
  ],
  "total": 1,
  "limit": 100,
  "offset": 0
}
```

### Create Work Item

```bash
curl -X POST http://localhost:8000/api/v2/work-items \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "proj-001",
    "title": "Add user authentication",
    "description": "Implement OAuth2-based authentication system",
    "labels": ["feature", "authentication"],
    "priority": "HIGH"
  }'
```

**Response:**
```json
{
  "id": "work-item-abc123",
  "project_id": "proj-001",
  "title": "Add user authentication",
  "description": "Implement OAuth2-based authentication system",
  "labels": ["feature", "authentication"],
  "priority": "HIGH",
  "status": "NEW",
  "created_at": "2025-01-01T12:00:00Z",
  "updated_at": "2025-01-01T12:00:00Z"
}
```

### Get Work Item

```bash
curl http://localhost:8000/api/v2/work-items/work-item-abc123
```

### List Work Items with Filters

```bash
# Filter by project
curl "http://localhost:8000/api/v2/work-items?project_id=proj-001"

# Filter by status
curl "http://localhost:8000/api/v2/work-items?status=IN_PROGRESS"

# Combine filters
curl "http://localhost:8000/api/v2/work-items?project_id=proj-001&status=COMPLETED&limit=10"
```

### Trigger Workflow

```bash
curl -X POST http://localhost:8000/api/v2/orchestrator/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "work_item_id": "work-item-abc123",
    "workflow_id": "feature-workflow",
    "force": false
  }'
```

**Response:**
```json
{
  "status": "triggered",
  "work_item_id": "work-item-abc123",
  "workflow_id": "feature-workflow",
  "execution_id": "exec-xyz789",
  "message": "Workflow triggered successfully"
}
```

### Get Workflow Status

```bash
curl http://localhost:8000/api/v2/workflows/feature-workflow/status
```

### List Agent Executions

```bash
# All executions
curl http://localhost:8000/api/v2/executions

# Filter by work item
curl "http://localhost:8000/api/v2/executions?work_item_id=work-item-abc123"

# Filter by status
curl "http://localhost:8000/api/v2/executions?status=COMPLETED"
```

**Response:**
```json
{
  "items": [
    {
      "id": "exec-001",
      "work_item_id": "work-item-abc123",
      "agent_id": "agent-architect",
      "status": "COMPLETED",
      "started_at": "2025-01-01T12:05:00Z",
      "completed_at": "2025-01-01T12:15:00Z",
      "duration_seconds": 600,
      "output_summary": "Designed authentication system architecture"
    }
  ],
  "total": 1
}
```

### Get Execution Details

```bash
curl http://localhost:8000/api/v2/executions/exec-001
```

## WebSocket Connection

### Connect via JavaScript

```javascript
// Connect to WebSocket
const ws = new WebSocket('ws://localhost:8000/api/v2/events/stream');

// Subscribe to all events
ws.onopen = () => {
  ws.send(JSON.stringify({
    type: 'subscribe',
    subscription_type: 'all_events'
  }));
};

// Handle incoming events
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received event:', data);

  if (data.type === 'AgentExecutionCompleted') {
    console.log('Execution completed:', data.payload.execution_id);
  }
};

// Handle errors
ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

// Handle disconnection
ws.onclose = () => {
  console.log('WebSocket closed');
};
```

### Filter Events by Work Item

```javascript
ws.send(JSON.stringify({
  type: 'subscribe',
  subscription_type: 'work_item_events',
  work_item_id: 'work-item-abc123'
}));
```

### Filter Events by Workflow

```javascript
ws.send(JSON.stringify({
  type: 'subscribe',
  subscription_type: 'workflow_events',
  workflow_id: 'feature-workflow'
}));
```

### Connect via Python

```python
import asyncio
import websockets
import json

async def listen_events():
    uri = "ws://localhost:8000/api/v2/events/stream"
    async with websockets.connect(uri) as websocket:
        # Subscribe
        await websocket.send(json.dumps({
            "type": "subscribe",
            "subscription_type": "all_events"
        }))

        # Listen for events
        while True:
            message = await websocket.recv()
            event = json.loads(message)
            print(f"Event: {event['type']}")

asyncio.run(listen_events())
```

### Connect via `websocat` (CLI Tool)

```bash
# Install websocat (if not installed)
# macOS: brew install websocat
# Linux: cargo install websocat

# Connect and subscribe
echo '{"type":"subscribe","subscription_type":"all_events"}' | \
  websocat ws://localhost:8000/api/v2/events/stream
```

## Querying Observability Data

### Metrics

```bash
# Get all metrics
curl http://localhost:8000/api/v2/metrics

# Filter by metric name
curl "http://localhost:8000/api/v2/metrics?metric_name=execution_duration"

# Filter by labels
curl "http://localhost:8000/api/v2/metrics?label_agent_id=agent-architect"
```

**Response:**
```json
[
  {
    "metric_name": "execution_duration",
    "value": 600.5,
    "labels": {
      "agent_id": "agent-architect",
      "work_item_id": "work-item-abc123",
      "status": "completed"
    },
    "timestamp": "2025-01-01T12:15:00Z"
  }
]
```

### Events

```bash
# Get all events
curl http://localhost:8000/api/v2/events

# Filter by event type
curl "http://localhost:8000/api/v2/events?event_type=AgentExecutionCompleted"

# Filter by aggregate (work item)
curl "http://localhost:8000/api/v2/events?aggregate_id=work-item-abc123"

# Limit results
curl "http://localhost:8000/api/v2/events?limit=50"
```

**Response:**
```json
{
  "events": [
    {
      "id": "evt-001",
      "event_type": "WorkItemCreated",
      "aggregate_id": "work-item-abc123",
      "aggregate_type": "WorkItem",
      "payload": {
        "title": "Add user authentication",
        "description": "Implement OAuth2-based authentication system"
      },
      "timestamp": "2025-01-01T12:00:00Z",
      "correlation_id": "corr-123",
      "causation_id": null,
      "metadata": {}
    }
  ],
  "total": 1,
  "limit": 100,
  "offset": 0
}
```

### Event Timeline

Get events in chronological order:

```bash
curl "http://localhost:8000/api/v2/events?aggregate_id=work-item-abc123&order=asc"
```

## Time Manipulation

### Check Current Time

```bash
curl http://localhost:8000/api/v2/simulation/time
```

**Response:**
```json
{
  "current_time": "2025-01-01T12:00:00Z",
  "speed_multiplier": 1.0,
  "auto_advance": false
}
```

### Advance Time (If Enabled)

**Note:** This endpoint is only available if time manipulation is explicitly enabled in the configuration.

```bash
curl -X POST http://localhost:8000/api/v2/simulation/time/advance \
  -H "Content-Type: application/json" \
  -d '{
    "delta_seconds": 3600
  }'
```

## Scenario File Format

Create custom scenarios with YAML files:

```yaml
# my-scenario.yaml

name: "My Custom Scenario"
description: "Custom scenario for testing feature X"
version: "1.0"

# Time settings
speed_multiplier: 10.0
auto_advance: false

# Projects
projects:
  - name: "my-project"
    description: "My test project"
    repository_url: "https://github.com/me/repo.git"
    default_branch: "main"
    metadata:
      team: "engineering"

# Workflows
workflows:
  - name: "my-workflow"
    description: "My custom workflow"
    stages:
      - name: "design"
        agent_type: "architect"
        description: "Design architecture"
        order: 1
        max_retries: 2
        timeout_seconds: 3600

      - name: "implement"
        agent_type: "developer"
        description: "Implement feature"
        order: 2
        max_retries: 3
        timeout_seconds: 7200

# Agents
agents:
  - name: "architect"
    agent_type: "architect"
    description: "Software architect"
    capabilities: ["code_generation", "code_review"]
    llm_model: "claude-3-5-sonnet-20241022"
    temperature: 0.7
    max_tokens: 8192
    system_prompt: "You are a software architect."
    enabled: true

  - name: "developer"
    agent_type: "developer"
    description: "Senior developer"
    capabilities: ["code_generation"]
    llm_model: "claude-3-5-sonnet-20241022"
    temperature: 0.7
    max_tokens: 8192
    system_prompt: "You are a senior developer."
    enabled: true

# Work Items
work_items:
  - title: "Build feature X"
    description: "Implement feature X with tests"
    labels: ["feature", "priority-high"]
    priority: "high"
    status: "new"
    metadata:
      estimated_hours: 16

# Metadata
metadata:
  scenario_type: "custom"
  author: "your-name"
```

**Load custom scenario:**

```bash
python -m codetoreum.cli.simulation_server --scenario-file my-scenario.yaml
```

## Troubleshooting

### Server Won't Start

**Problem:** Port already in use

```
OSError: Port 8000 is already in use. Try a different port with --port
```

**Solution:** Use a different port

```bash
python -m codetoreum.cli.simulation_server --port 8080
```

---

**Problem:** Permission denied

```
OSError: Permission denied to bind to port 80
```

**Solution:** Use a port > 1024 or run with elevated privileges

```bash
python -m codetoreum.cli.simulation_server --port 8080
```

### Scenario File Errors

**Problem:** Invalid YAML syntax

```
click.FileError: Invalid YAML: ...
```

**Solution:** Validate YAML syntax using online validator or `yamllint`

```bash
yamllint my-scenario.yaml
```

---

**Problem:** File not found

```
FileNotFoundError: Scenario 'custom' not found
```

**Solution:** Use `--scenario-file` for custom scenarios, `--scenario` for built-in

```bash
# Built-in scenarios
python -m codetoreum.cli.simulation_server --scenario demo

# Custom scenarios
python -m codetoreum.cli.simulation_server --scenario-file custom.yaml
```

### API Errors

**Problem:** 404 Not Found on API calls

```json
{"detail": "Not Found"}
```

**Solution:** Check the API version in the URL path

```bash
# Correct: /api/v2/work-items
curl http://localhost:8000/api/v2/work-items

# Incorrect: /api/work-items
curl http://localhost:8000/api/work-items
```

---

**Problem:** 422 Validation Error

```json
{
  "detail": [
    {
      "loc": ["body", "project_id"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

**Solution:** Check request payload matches API schema (see `/docs` for schema)

### WebSocket Connection Issues

**Problem:** Connection refused

```
WebSocket connection to 'ws://localhost:8000/ws' failed
```

**Solution:** Use correct WebSocket path

```javascript
// Correct path
ws://localhost:8000/api/v2/events/stream

// Not: ws://localhost:8000/ws
```

---

**Problem:** No events received

**Solution:** Send subscription message after connecting

```javascript
ws.onopen = () => {
  // Required: Send subscription
  ws.send(JSON.stringify({
    type: 'subscribe',
    subscription_type: 'all_events'
  }));
};
```

### Memory Issues

**Problem:** Server runs out of memory

**Solution:** Use smaller scenarios or reduce speed multiplier

```bash
# Use default scenario instead of stress_test
python -m codetoreum.cli.simulation_server --scenario default

# Reduce speed multiplier to prevent event buildup
python -m codetoreum.cli.simulation_server --speed-multiplier 1.0
```

## Common Workflows

### Demo Workflow

1. Start server with demo scenario:
   ```bash
   python -m codetoreum.cli.simulation_server --scenario demo
   ```

2. Open API docs: http://localhost:8000/docs

3. List work items:
   ```bash
   curl http://localhost:8000/api/v2/work-items
   ```

4. Trigger workflow for first work item:
   ```bash
   curl -X POST http://localhost:8000/api/v2/orchestrator/trigger \
     -H "Content-Type: application/json" \
     -d '{"work_item_id": "WORK_ITEM_ID", "workflow_id": "feature-development-workflow"}'
   ```

5. Watch execution progress via WebSocket (see JavaScript example above)

6. Query metrics after completion:
   ```bash
   curl http://localhost:8000/api/v2/metrics
   ```

### Development Workflow

1. Start with empty state:
   ```bash
   python -m codetoreum.cli.simulation_server --no-seed --debug
   ```

2. Create project via API:
   ```bash
   curl -X POST http://localhost:8000/api/v2/projects \
     -H "Content-Type: application/json" \
     -d '{
       "name": "test-project",
       "description": "Development testing",
       "repository_url": "https://github.com/test/repo.git"
     }'
   ```

3. Create agents, workflows, work items (similar API calls)

4. Test your changes

5. Review logs and events for debugging

### Testing Workflow

1. Start with fast simulation:
   ```bash
   python -m codetoreum.cli.simulation_server --scenario default --speed-multiplier 100.0
   ```

2. Run your test script that makes API calls

3. Verify expected behavior via assertions on API responses

4. Check event store for audit trail:
   ```bash
   curl http://localhost:8000/api/v2/events
   ```

## Tips and Best Practices

### Performance

- Use higher speed multipliers (10x-100x) for faster testing
- Use `--no-seed` to reduce memory footprint for custom testing
- Monitor memory usage with `htop` or similar tools
- Restart server periodically for long-running manual tests

### Debugging

- Enable `--debug` flag for detailed logging
- Query event store to see complete audit trail
- Use WebSocket to watch events in real-time
- Check `/api/health` to verify server is running

### Development

- Use interactive API docs at `/docs` to explore endpoints
- Test API changes immediately without external dependencies
- Use custom scenario files to test specific configurations
- Combine with frontend development (no CORS restrictions in simulation)

## Next Steps

- **Testing Guide**: [testing_with_simulation_mode.md](testing_with_simulation_mode.md) - Learn how to write E2E tests
- **Architecture**: [../simulation_mode_architecture.md](../simulation_mode_architecture.md) - Understand the implementation
- **API Reference**: http://localhost:8000/docs (when server is running)

## Support

For issues or questions:
- Check [troubleshooting](#troubleshooting) section above
- Review simulation logs with `--debug` flag
- Consult architecture documentation for technical details
- File bug reports with logs and reproduction steps
