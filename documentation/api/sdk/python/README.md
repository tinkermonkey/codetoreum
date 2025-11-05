# Codetoreum Python SDK

Official Python client library for the Codetoreum AI Agent Orchestration Platform.

## Installation

```bash
pip install codetoreum-client
```

For WebSocket support:
```bash
pip install codetoreum-client[websocket]
```

## Quick Start

```python
from codetoreum_client import CodetoreumClient

# Initialize client
client = CodetoreumClient(
    base_url="http://localhost:8000",
    api_token="your_token_here"  # Get from server startup logs
)

# Create a work item
work_item = client.work_items.create(
    title="Implement user authentication",
    description="Add JWT-based authentication to the API",
    project_id="my-project",
    labels=["feature", "security"],
    priority="high"
)

print(f"Created work item: {work_item.id}")

# Start a workflow
workflow_run = client.orchestrator.start_workflow(work_item.id)
print(f"Started workflow: {workflow_run.workflow_run_id}")

# Monitor execution
execution_response = client.executions.list(
    workflow_run_id=workflow_run.workflow_run_id,
    status="running"
)

for execution in execution_response.items:
    print(f"Execution {execution.id}: {execution.status}")
    logs = client.executions.get_logs(execution.id, tail=10)
    for log in logs:
        print(f"  {log}")
```

## Features

- **Work Items**: Create, list, update, and delete work items
- **Agents**: Manage AI agents and their capabilities
- **Workflows**: Define and manage multi-stage workflows
- **Orchestrator**: Start, pause, resume, and cancel workflow executions
- **Executions**: Monitor agent executions and retrieve logs
- **Real-time Events**: Stream events via WebSocket
- **Configuration**: Manage project and agent configurations
- **Metrics**: Access performance and health metrics

## Usage Examples

### Work Items

```python
# List pending work items
response = client.work_items.list(status="pending", limit=10)
for item in response.items:
    print(f"{item.title} - {item.priority}")

# Get specific work item
work_item = client.work_items.get("wi_abc123")

# Update work item
client.work_items.update(
    "wi_abc123",
    status="in_progress",
    assignee="agent-backend-dev"
)

# Get change history
history = client.work_items.get_history("wi_abc123")
```

### Agents

```python
# Create an agent
agent = client.agents.create(
    name="backend-specialist",
    description="Python backend development specialist",
    agent_type="claude_code",
    capabilities=["python", "fastapi", "postgresql"],
    configuration={
        "model": "claude-sonnet-4",
        "temperature": 0.7,
        "max_tokens": 8000
    }
)

# List active agents
response = client.agents.list(active=True)
for agent in response.items:
    print(f"{agent.name}: {', '.join(agent.capabilities)}")
```

### Executions

```python
# List running executions
response = client.executions.list(status="running")

# Get execution details
execution = client.executions.get("exec_abc123")
print(f"Status: {execution.status}")
if execution.progress:
    print(f"Progress: {execution.progress['percentage']}%")

# Get logs
logs = client.executions.get_logs("exec_abc123", tail=50)
for log in logs:
    print(log)

# Wait for completion
def on_progress(execution):
    if execution.progress:
        print(f"Progress: {execution.progress['percentage']}%")

final = client.executions.wait_for_completion(
    "exec_abc123",
    callback=on_progress,
    timeout=600
)
print(f"Final status: {final.status}")
```

### Real-time Events

```python
# Stream real-time events
for event in client.events.stream():
    event_type = event["type"]
    data = event["data"]

    if event_type == "execution.completed":
        print(f"Execution {data['execution_id']} completed")
    elif event_type == "workflow.started":
        print(f"Workflow {data['workflow_run_id']} started")
```

### Workflows

```python
# Create workflow definition
workflow = client.workflows.create(
    name="feature-development",
    description="Standard feature development workflow",
    version="1.0.0",
    stages=[
        {
            "name": "analysis",
            "agent_id": "agent-analyzer",
            "entry_conditions": ["work_item.labels contains 'feature'"],
            "timeout_minutes": 30
        },
        {
            "name": "development",
            "agent_id": "agent-backend-dev",
            "entry_conditions": ["previous_stage.status == 'completed'"],
            "timeout_minutes": 120
        }
    ]
)

# Start workflow
run = client.orchestrator.start_workflow(
    work_item_id="wi_abc123",
    workflow_id=workflow.id
)

# Control workflow
client.orchestrator.pause_workflow(run.workflow_run_id)
client.orchestrator.resume_workflow(run.workflow_run_id)
client.orchestrator.cancel_workflow(run.workflow_run_id)
```

### Context Manager

```python
# Use as context manager for automatic cleanup
with CodetoreumClient(api_token="your_token") as client:
    work_items = client.work_items.list()
    # ... use client ...
# Session automatically closed
```

## Error Handling

```python
from codetoreum_client import (
    CodetoreumError,
    AuthenticationError,
    NotFoundError,
    RateLimitError
)

try:
    work_item = client.work_items.get("invalid_id")
except NotFoundError:
    print("Work item not found")
except AuthenticationError:
    print("Invalid authentication token")
except RateLimitError:
    print("Rate limit exceeded, please wait")
except CodetoreumError as e:
    print(f"API error: {e}")
```

## Configuration

### Environment Variables

```bash
export CODETOREUM_API_TOKEN="your_token_here"
export CODETOREUM_BASE_URL="http://localhost:8000"
```

```python
import os
from codetoreum_client import CodetoreumClient

client = CodetoreumClient(
    base_url=os.getenv("CODETOREUM_BASE_URL"),
    api_token=os.getenv("CODETOREUM_API_TOKEN")
)
```

### Custom Timeout

```python
client = CodetoreumClient(
    api_token="your_token",
    timeout=60  # 60 seconds
)
```

### SSL Verification

```python
# Disable SSL verification (not recommended for production)
client = CodetoreumClient(
    api_token="your_token",
    verify_ssl=False
)
```

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black codetoreum_client/

# Type checking
mypy codetoreum_client/

# Linting
flake8 codetoreum_client/
```

## API Documentation

Full API documentation is available at:
- Swagger UI: `http://localhost:8000/api/docs`
- ReDoc: `http://localhost:8000/api/redoc`
- OpenAPI JSON: `http://localhost:8000/api/openapi.json`

## Support

- Documentation: https://docs.codetoreum.com
- Issues: https://github.com/codetoreum/codetoreum/issues
- Source: https://github.com/codetoreum/codetoreum

## License

MIT License - see LICENSE file for details
