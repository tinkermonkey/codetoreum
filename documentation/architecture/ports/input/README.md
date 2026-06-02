# Input Ports

Input ports define inbound contracts — commands, queries, and services that external clients (HTTP API, webhooks, CLI, internal services) invoke to interact with the system.

## Port Groups (6 files)

Input ports are grouped by functional domain:

1. **agent-management.md** — IAgentCommandPort, IAgentQueryPort
   - Create, update, delete agents
   - Query agent details and status

2. **work-item-management.md** — IWorkItemCommandPort, IWorkItemQueryPort, ITaskQueryPort
   - Create, update work items
   - Query work items and tasks
   - Manage work item status and assignments

3. **workflow-management.md** — IWorkflowCommandPort, IWorkflowQueryPort, IWorkflowDefinitionCommandPort, IWorkflowRunQueryPort
   - Define workflows and stages
   - Start workflow runs
   - Query workflow definitions and execution status

4. **execution-management.md** — IExecutionCommandPort, IExecutionQueryPort, IOrchestrationCommandPort
   - Queue agent executions
   - Query execution status
   - Orchestrate multi-step workflows

5. **configuration.md** — IConfigurationCommandPort, IConfigurationQueryPort, IMetricsQueryPort
   - Manage system configuration
   - Query configuration values
   - Query system metrics

6. **system-services.md** — IAuthenticationPort, IConversationalLoopService, IWorkspaceQueryPort, IAuditQueryPort, IIssueIntakePort, Diagnostics endpoints
   - Verify user authentication
   - Multi-turn agent conversations
   - Workspace file operations
   - Audit log queries
   - System diagnostics and observability (state snapshot, trigger lifecycle)

## Interface Definition Pattern

Each input port is defined as a Python ABC (Abstract Base Class):

```python
from abc import ABC, abstractmethod

class IWorkItemCommandPort(ABC):
    @abstractmethod
    async def create_work_item(self, title: str, ...) -> WorkItem:
        """Create a new work item."""
        pass
```

All input ports are async and use domain types for parameters and return values.

## Adapter Implementations

Input ports are primarily implemented by:
- **Mock Input Port Adapters** (`adapters/primary/input_port_adapters/mock/`) for simulation and testing
- **FastAPI route handlers** that wrap input port implementations

Input ports are primarily inbound (clients call them), so "production" adapters are less common. Instead, primary adapters (FastAPI handlers) delegate to application services that then use output ports.

## Phase Delivery

- **Phase 4**: Complete input port documentation (all 6 groups, 20 interfaces)

## See Also

- [Port Architecture Overview](../README.md)
- [Output Ports](../output/)
- [Application Services](../../application-services/)
