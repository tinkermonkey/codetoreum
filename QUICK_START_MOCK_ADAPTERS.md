# Quick Start Guide: Using Mock Adapters

This guide shows how to use the newly implemented mock adapters in your development workflow.

## Overview

All 9 input port interfaces now have fully functional mock implementations:

| Port Interface | Mock Adapter |
|---------------|--------------|
| `IAgentQueryPort` | `MockAgentQueryAdapter` |
| `IAgentCommandPort` | `MockAgentCommandAdapter` |
| `IExecutionQueryPort` | `MockExecutionQueryAdapter` |
| `IExecutionCommandPort` | `MockExecutionCommandAdapter` |
| `IWorkItemQueryPort` | `MockWorkItemQueryAdapter` |
| `IWorkItemCommandPort` | `MockWorkItemCommandAdapter` |
| `IMetricsQueryPort` | `MockMetricsQueryAdapter` |
| `IConfigurationQueryPort` | `MockConfigQueryAdapter` |
| `IWorkspaceQueryPort` | `MockWorkspaceQueryAdapter` |

## Basic Usage

### 1. Import Mock Adapters

```python
from codetoreum.adapters.primary.input_port_adapters.mock import (
    MockAgentQueryAdapter,
    MockAgentCommandAdapter,
    MockExecutionQueryAdapter,
    MockExecutionCommandAdapter,
    MockWorkItemQueryAdapter,
    MockWorkItemCommandAdapter,
    MockMetricsQueryAdapter,
    MockConfigQueryAdapter,
    MockWorkspaceQueryAdapter,
)
```

### 2. Create Adapter Instances

```python
# Query adapters
agent_query = MockAgentQueryAdapter()
execution_query = MockExecutionQueryAdapter()
work_item_query = MockWorkItemQueryAdapter()
metrics_query = MockMetricsQueryAdapter()
config_query = MockConfigQueryAdapter()
workspace_query = MockWorkspaceQueryAdapter()

# Command adapters
agent_command = MockAgentCommandAdapter()
execution_command = MockExecutionCommandAdapter()
work_item_command = MockWorkItemCommandAdapter()
```

### 3. Seed with Test Data

```python
from datetime import datetime, timezone
from uuid import uuid4

from codetoreum.domain.agent import Agent, AgentType, AgentCapability
from codetoreum.domain.work_item import WorkItem, WorkItemStatus, WorkItemPriority

# Create test agent
test_agent = Agent(
    id=str(uuid4()),
    name="developer_agent",
    display_name="Developer Agent",
    agent_type=AgentType.DEVELOPER,
    capabilities={
        "python": AgentCapability(skill="python", proficiency=0.9),
        "testing": AgentCapability(skill="testing", proficiency=0.7),
    },
    role_description="Writes Python code and tests",
    model="claude-sonnet-4-5",
    timeout_seconds=300,
    max_retries=3,
    requires_docker=True,
    requires_dev_container=False,
    makes_code_changes=True,
    filesystem_write_allowed=True,
    mcp_servers=["artifacts", "logging"],
    metadata={},
    created_at=datetime.now(timezone.utc),
    updated_at=datetime.now(timezone.utc),
)

# Add to mock adapters
agent_query.add_agent(test_agent)
agent_command._agents[test_agent.id] = test_agent

# Create test work item
test_work_item = WorkItem(
    id=str(uuid4()),
    project_id="project-123",
    title="Implement feature X",
    description="Add new feature to the system",
    status=WorkItemStatus.OPEN,
    priority=WorkItemPriority.HIGH,
    assignee=None,
    labels=["feature", "backend"],
    workflow_id=None,
    workflow_stage=None,
    external_id="ISSUE-123",
    external_url="https://github.com/org/repo/issues/123",
    metadata={},
    created_at=datetime.now(timezone.utc),
    updated_at=datetime.now(timezone.utc),
)

# Add to mock adapters
work_item_query.add_work_item(test_work_item)
work_item_command._work_items[test_work_item.id] = test_work_item
```

### 4. Use in API Endpoints

```python
from fastapi import FastAPI, Depends

app = FastAPI()

# Dependency injection
def get_agent_query_port():
    return agent_query

def get_agent_command_port():
    return agent_command

# API endpoint
@app.get("/api/v1/agents/{agent_id}")
async def get_agent(
    agent_id: str,
    port: IAgentQueryPort = Depends(get_agent_query_port)
):
    agent_info = await port.get_agent(agent_id, include_stats=False)
    return agent_info

@app.post("/api/v1/agents")
async def create_agent(
    command: CreateAgentCommand,
    port: IAgentCommandPort = Depends(get_agent_command_port)
):
    agent = await port.create_agent(command)
    return agent
```

## Common Patterns

### Pattern 1: Query with Filters

```python
from codetoreum.ports.input.agent_query import AgentFilters, AgentPaginationParams, AgentSortField, SortOrder

# Filter agents
filters = AgentFilters(
    agent_type=AgentType.DEVELOPER,
    requires_docker=True,
    makes_code_changes=True,
)

# Pagination
pagination = AgentPaginationParams(
    offset=0,
    limit=20,
    sort_by=AgentSortField.UPDATED_AT,
    sort_order=SortOrder.DESC,
)

# Execute query
result = await agent_query.list_agents(filters, pagination)

print(f"Total agents: {result.total_count}")
print(f"Page size: {len(result.agents)}")
print(f"Has more: {result.has_next}")

for agent in result.agents:
    print(f"- {agent.display_name} ({agent.name})")
```

### Pattern 2: Create and Update

```python
from codetoreum.ports.input.work_item_command import CreateWorkItemCommand, UpdateWorkItemCommand

# Create work item
create_cmd = CreateWorkItemCommand(
    project_id="project-123",
    title="New task",
    description="Task description",
    labels=["bug", "urgent"],
    priority=WorkItemPriority.CRITICAL,
)

work_item = await work_item_command.create_work_item(create_cmd)
print(f"Created work item: {work_item.id}")

# Update work item
update_cmd = UpdateWorkItemCommand(
    work_item_id=work_item.id,
    title="Updated title",
    labels=["bug", "urgent", "backend"],
)

updated_work_item = await work_item_command.update_work_item(update_cmd)
print(f"Updated work item: {updated_work_item.title}")
```

### Pattern 3: Search

```python
from codetoreum.ports.input.work_item_query import WorkItemSearchParams, PaginationParams

# Search work items
search_params = WorkItemSearchParams(
    query="authentication",  # Search in title and description
    filters=WorkItemFilters(
        status=WorkItemStatus.OPEN,
        priority=WorkItemPriority.HIGH,
    ),
    pagination=PaginationParams(
        offset=0,
        limit=10,
        sort_by=SortField.UPDATED_AT,
        sort_order=SortOrder.DESC,
    ),
)

result = await work_item_query.search_work_items(search_params)

for item in result.work_items:
    print(f"- {item.title} (Priority: {item.priority.value})")
```

### Pattern 4: Get Metrics

```python
from datetime import timedelta

# Get system health
health = await metrics_query.get_system_health()
print(f"Overall status: {health.status.value}")
print(f"Uptime: {health.uptime_seconds}s")

for component in health.components:
    print(f"- {component.component_name}: {component.status.value}")

# Get performance metrics
now = datetime.now(timezone.utc)
start_time = now - timedelta(hours=1)
end_time = now

perf = await metrics_query.get_performance_metrics(
    start_time=start_time,
    end_time=end_time,
    aggregation_window_seconds=60,
)

print(f"API requests: {perf.api_request_count}")
print(f"API errors: {perf.api_error_count}")
print(f"P95 latency: {perf.api_latency_p95_ms}ms")
print(f"Active executions: {perf.active_executions}")
```

### Pattern 5: Thread-Safe Concurrent Access

```python
import asyncio

async def concurrent_queries():
    tasks = [
        agent_query.get_agent("agent-1"),
        agent_query.get_agent("agent-2"),
        agent_query.list_agents(),
        work_item_query.list_work_items(),
        execution_query.list_executions(),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"Task {i} failed: {result}")
        else:
            print(f"Task {i} succeeded")

# All mock adapters are thread-safe
await concurrent_queries()
```

## Testing with Mock Adapters

### Unit Test Example

```python
import pytest
from codetoreum.adapters.primary.input_port_adapters.mock import MockAgentQueryAdapter
from codetoreum.domain.agent import Agent, AgentType, AgentCapability
from codetoreum.domain.exceptions import AgentNotFoundError

@pytest.fixture
def agent_query():
    adapter = MockAgentQueryAdapter()
    # Seed with test data
    test_agent = Agent(...)
    adapter.add_agent(test_agent)
    yield adapter
    # Cleanup
    adapter.clear()

@pytest.mark.asyncio
async def test_get_agent(agent_query):
    # Test successful retrieval
    agent = await agent_query.get_agent("test-agent-id")
    assert agent.name == "developer_agent"
    assert agent.agent_type == "developer"

@pytest.mark.asyncio
async def test_get_agent_not_found(agent_query):
    # Test not found error
    with pytest.raises(AgentNotFoundError):
        await agent_query.get_agent("nonexistent-id")

@pytest.mark.asyncio
async def test_list_agents_with_filters(agent_query):
    filters = AgentFilters(agent_type=AgentType.DEVELOPER)
    result = await agent_query.list_agents(filters)

    assert result.total_count > 0
    assert all(a.agent_type == "developer" for a in result.agents)
```

### Integration Test Example

```python
import pytest
from codetoreum.adapters.primary.input_port_adapters.mock import (
    MockAgentCommandAdapter,
    MockAgentQueryAdapter,
)
from codetoreum.ports.input.agent_command import CreateAgentCommand

@pytest.fixture
def agent_adapters():
    query_adapter = MockAgentQueryAdapter()
    command_adapter = MockAgentCommandAdapter()
    yield query_adapter, command_adapter
    query_adapter.clear()
    command_adapter.clear()

@pytest.mark.asyncio
async def test_create_and_query_agent(agent_adapters):
    query_adapter, command_adapter = agent_adapters

    # Create agent via command port
    create_cmd = CreateAgentCommand(
        name="test_agent",
        display_name="Test Agent",
        agent_type=AgentType.DEVELOPER,
        role_description="Test role",
        model="claude-sonnet-4-5",
        capabilities={
            "python": AgentCapability(skill="python", proficiency=0.8)
        },
    )

    created_agent = await command_adapter.create_agent(create_cmd)

    # Sync to query adapter (in real system, this happens via event projection)
    query_adapter.add_agent(created_agent)

    # Query via query port
    queried_agent = await query_adapter.get_agent_by_name("test_agent")

    assert queried_agent.id == created_agent.id
    assert queried_agent.name == "test_agent"
    assert "python" in queried_agent.capabilities
```

## Helper Methods Reference

### Agent Adapters

```python
# MockAgentQueryAdapter
agent_query.add_agent(agent, execution_stats=None)
agent_query.clear()

# MockAgentCommandAdapter
agent_command.get_agent(agent_id)  # Returns Agent domain model
agent_command.clear()
```

### Execution Adapters

```python
# MockExecutionQueryAdapter
execution_query.add_execution(execution_info)
execution_query.add_log_entry(execution_id, log_entry)
execution_query.add_history_event(execution_id, event)
execution_query.clear()

# MockExecutionCommandAdapter
execution_command.add_execution(execution)
execution_command.get_execution(execution_id)
execution_command.clear()
```

### Work Item Adapters

```python
# MockWorkItemQueryAdapter
work_item_query.add_work_item(work_item)
work_item_query.add_event(work_item_id, event)
work_item_query.clear()

# MockWorkItemCommandAdapter
work_item_command.get_work_item(work_item_id)
work_item_command.clear()
```

### Metrics Adapter

```python
# MockMetricsQueryAdapter
metrics_query.set_component_health(component_name, health_info)
metrics_query.record_metric(metric_name, value, timestamp, labels)
metrics_query.set_integration_status(status)
metrics_query.set_simulation_mode(mode_info)
metrics_query.clear()
```

### Config Adapter

```python
# MockConfigQueryAdapter
config_query.add_project_config(config)
config_query.add_agent_config(config)
config_query.add_pipeline_config(config)
config_query.clear()
```

### Workspace Adapter

```python
# MockWorkspaceQueryAdapter
workspace_query.add_workspace(workspace_info)
workspace_query.update_resource_usage(workspace_id, usage)
workspace_query.add_log_line(workspace_id, log_line)
workspace_query.clear()
```

## Best Practices

1. **Always Clear in Tests**: Use `adapter.clear()` in test teardown to prevent state leakage
2. **Use Fixtures**: Create pytest fixtures for adapters to ensure proper setup/teardown
3. **Seed Realistic Data**: Add test data that reflects production scenarios
4. **Test Error Cases**: Verify not found errors, validation errors, etc.
5. **Thread Safety**: All adapters use RLock - safe for concurrent access
6. **Sync Query/Command**: Remember to sync data between query and command adapters in tests
   (in production, this happens automatically via event projections)

## Limitations of Mock Adapters

Mock adapters are great for development and testing, but have limitations:

1. **No Persistence**: Data is lost when adapter is destroyed
2. **No Transactions**: Changes are immediate, no rollback
3. **Simple Search**: Substring matching only (no fuzzy search, relevance ranking)
4. **No Aggregations**: Limited analytics capabilities
5. **In-Memory Only**: Not suitable for large datasets (> 10k records)

For production use, PostgreSQL-backed adapters will be implemented to address these limitations.

## Next Steps

- See `/workspace/IMPLEMENTATION_PLAN_MISSING_PORTS.md` for the full implementation plan
- See `/workspace/IMPLEMENTATION_STATUS_SUMMARY.md` for current status and progress
- PostgreSQL adapters will be implemented next, following the same patterns as mock adapters
