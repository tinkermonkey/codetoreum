# Output Ports

Output ports define outbound contracts — dependencies on external systems that the application requires to fulfill its responsibilities. All external system interactions happen through output ports.

## Port Groups (7 files)

Output ports are organized by functional domain and responsibility:

1. **core-system.md** — ITicketSystem, IVersionControlService, IContainer, ILLMProvider, IRepository
   - Fundamental external dependencies
   - Ticket/issue management (GitHub, Jira, Linear, etc.)
   - Version control operations (Git)
   - Container runtime (Docker)
   - Language model providers (Claude Code, GPT-4, etc.)
   - Generic repository operations

2. **board-management.md** — IBoardService, IPipelineLockService, IPipelineQueueService
   - Project board column operations
   - Distributed pipeline locking
   - Work queue management

3. **code-review.md** — ICodeReviewService, IDiscussionAdapter, IPRReviewCycle, IReviewCycle
   - Pull request lifecycle (open, review, approve, merge)
   - Discussion/comment threads
   - Review cycle state management

4. **work-coordination.md** — IWorkItemService, IBranchResolutionService, IWorkItemBranchTracker, IWorkflowConfigService, IWorkflowOrchestrator
   - Work item CRUD and status synchronization
   - Branch naming and resolution
   - Workflow configuration persistence
   - Workflow execution orchestration

5. **infrastructure-services.md** — IEventEmitter, IEventStore, IFailedEventStore, IStorage, IMetrics, ITracer, IMonitoredService, IMessageBroker
   - Event publication and persistence
   - Failed event handling
   - Artifact storage (logs, reports, outputs)
   - Metrics collection
   - Distributed tracing (OpenTelemetry)
   - Service monitoring lifecycle
   - Asynchronous messaging

6. **domain-services.md** — IAgentExecutor, IAgentRepository, IConfigStore, IEncryptionService, IIdentityService, INotifier
   - Agent execution context and I/O
   - Agent metadata persistence
   - System configuration storage
   - Data encryption/decryption
   - Bot/human identity verification
   - Notification delivery (webhooks, email, Slack, etc.)

7. **lifecycle-services.md** — IRepairCycle, IRepairCycleCheckpointStore, IContainerRecoveryService, IEnvironmentRepairService, ICIPipelineService, ISystemicAnalysisService, IMultiProjectOrchestrator, IProjectManagerService, IActiveWorkflowRunRegistry
   - Repair cycle orchestration and state
   - Container failure recovery
   - Environment variable repair
   - CI pipeline integration
   - Systemic analysis and reporting
   - Multi-project coordination
   - Project management operations
   - Active workflow run tracking

## Interface Definition Pattern

Each output port is defined as a Python ABC (Abstract Base Class):

```python
from abc import ABC, abstractmethod

class ITicketSystem(ABC):
    @abstractmethod
    async def get_issue(self, issue_id: str) -> Issue:
        """Retrieve issue details."""
        pass
```

All output ports are async and use domain types for parameters and return values.

## Adapter Implementations

Each output port lists all known implementations:

- **Production Adapters**: Connect to real external systems (GitHubBoardAdapter, DockerContainerAdapter, etc.)
- **Secondary Adapters**: Alternative implementations (JiraTicketAdapter, etc.)
- **Testing/Mock Adapters**: In-memory or mock implementations for simulation (MockBoardAdapter, FakeContainerAdapter, etc.)

The adapter implementations section includes:
- Adapter class name
- Implementation type (production, secondary, testing)
- Source file path
- Brief description of implementation strategy

## Error Contracts

Each output port documents expected exceptions:
- `PortError` — Generic port error
- Specific exceptions for different failure modes (NotFound, AlreadyExists, etc.)

Application services should handle these errors and emit domain events to communicate failure states to the broader system.

## See Also

- [Port Architecture Overview](../README.md)
- [Input Ports](../input/)
- [Application Services](../../application-services/)
