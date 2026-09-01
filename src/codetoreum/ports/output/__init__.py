"""Output port interfaces."""

from codetoreum.domain.repair_cycle_types import EnvironmentRepairConfig
from codetoreum.domain.value_objects import ProjectConfig
from codetoreum.ports.output.agent_executor import IAgentExecutor
from codetoreum.ports.output.board_service import (
    BoardColumn,
    BoardConfig,
    ColumnMovementResult,
    IBoardService,
    MovedByType,
    ProjectBoard,
    ReconciliationResult,
    WorkItemPosition,
)
from codetoreum.ports.output.branch_resolution_service import IBranchResolutionService
from codetoreum.ports.output.code_review_service import (
    Approval,
    CodeReview,
    CodeReviewStatus,
    ICodeReviewService,
    ReviewComment,
)
from codetoreum.ports.output.coding_agent import (
    CodingAgentInvocationOptions,
    CodingAgentResult,
    ICodingAgent,
    InvocationMode,
)
from codetoreum.ports.output.container import (
    ContainerHealthStatus,
    ContainerResult,
    ContainerStatus,
    IContainer,
)
from codetoreum.ports.output.container_recovery import (
    ContainerMetadata,
    IAgentContainerRecoveryService,
    RecoveryAssessment,
    RecoveryResult,
)
from codetoreum.ports.output.container_recovery_tracking_store import (
    IContainerRecoveryTrackingStore,
)
from codetoreum.ports.output.discussion_adapter import (
    DiscussionMonitoringConfig,
    DiscussionThread,
    IDiscussionAdapter,
)
from codetoreum.ports.output.distributed_lock import (
    AcquireResult,
    AcquireStatus,
    IDistributedLock,
    LockHolder,
    ReleaseReason,
    ReleaseResult,
)
from codetoreum.ports.output.encryption_service import (
    DecryptionError,
    EncryptionError,
    IEncryptionService,
)
from codetoreum.ports.output.environment_repair_service import IEnvironmentRepairService
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.event_store import IEventStore
from codetoreum.ports.output.failed_event_store import (
    FailedEventRecord,
    FailedEventStoreStats,
    FailureReason,
    IFailedEventStore,
)
from codetoreum.ports.output.identity_service import (
    BotIdentityConfig,
    IIdentityService,
)
from codetoreum.ports.output.llm_types import ExecutionContext, ExecutionResult
from codetoreum.ports.output.metrics import IMetrics, MetricData
from codetoreum.ports.output.monitoring import (
    IMonitoredService,
    MonitoringConfig,
    MonitoringState,
    MonitoringStatus,
)
from codetoreum.ports.output.notifier import (
    Action,
    Attachment,
    DeliveryStatus,
    INotifier,
    Notification,
    NotificationChannel,
    NotificationPriority,
    NotificationResult,
    RichContent,
)
from codetoreum.ports.output.pipeline_queue import (
    EnqueueResult,
    IPipelineQueue,
)
from codetoreum.ports.output.pipeline_queue import (
    QueueEntry as IPipelineQueueEntry,
)
from codetoreum.ports.output.pr_review_cycle_service import (
    IPRReviewCycle,
    PRReviewCycleRequest,
    PRReviewCycleStateData,
)
from codetoreum.ports.output.project_manager_service import IProjectManagerService
from codetoreum.ports.output.prompt_builder import (
    ExecutionOutput,
    IPromptBuilder,
    StructuredPrompt,
)
from codetoreum.ports.output.repair_cycle_checkpoint_store import (
    IRepairCycleCheckpointStore,
)
from codetoreum.ports.output.repair_cycle_service import (
    IRepairCycle,
    RepairCycleContext,
)
from codetoreum.ports.output.repository import (
    IRepository,
    MergeResult,
    RepositoryStatus,
)
from codetoreum.ports.output.systemic_analysis_service import (
    ISystemicAnalysisService,
)
from codetoreum.ports.output.ticket_system import Comment, ITicketSystem
from codetoreum.ports.output.version_control_service import (
    IVersionControlService,
    Repository,
    VCSStatus,
)
from codetoreum.ports.output.work_execution_state_tracker import (
    ExecutionState,
    IWorkExecutionStateTracker,
)
from codetoreum.ports.output.work_item_service import IWorkItemService
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService
from codetoreum.ports.output.workflow_orchestrator import (
    CardMovedRequest,
    IssueData,
    IWorkflowOrchestrator,
    ReviewCycleCompletedRequest,
    StageCompletedRequest,
    WorkflowAction,
    WorkflowResult,
)

__all__ = [
    # Agent Executor
    "IAgentExecutor",
    # Branch Resolution Service
    "IBranchResolutionService",
    # Container Recovery Service
    "IAgentContainerRecoveryService",
    "ContainerMetadata",
    "RecoveryAssessment",
    "RecoveryResult",
    # Container Recovery Tracking (dependencies for container recovery)
    "IContainerRecoveryTrackingStore",
    "ExecutionState",
    "IWorkExecutionStateTracker",
    # Board Service
    "IBoardService",
    "BoardColumn",
    "BoardConfig",
    "ColumnMovementResult",
    "MovedByType",
    "ProjectBoard",
    "ReconciliationResult",
    "WorkItemPosition",
    # Coding Agent (sole agent-execution port after Phase D5)
    "ICodingAgent",
    "InvocationMode",
    "CodingAgentInvocationOptions",
    "CodingAgentResult",
    # Code Review Service
    "ICodeReviewService",
    "Approval",
    "CodeReview",
    "CodeReviewStatus",
    "ReviewComment",
    # Container
    "IContainer",
    "ContainerHealthStatus",
    "ContainerResult",
    "ContainerStatus",
    # Discussion Adapter
    "IDiscussionAdapter",
    "DiscussionMonitoringConfig",
    "DiscussionThread",
    # Encryption Service
    "IEncryptionService",
    "EncryptionError",
    "DecryptionError",
    # Environment Repair Service
    "IEnvironmentRepairService",
    "EnvironmentRepairConfig",
    # Event Emitter
    "IEventEmitter",
    # Event Store
    "IEventStore",
    # Failed Event Store
    "IFailedEventStore",
    "FailedEventRecord",
    "FailedEventStoreStats",
    "FailureReason",
    # Identity Service
    "IIdentityService",
    "BotIdentityConfig",
    # Legacy LLM types (kept for the prompt→completion repair-cycle adapters
    # that haven't migrated to ICodingAgent yet; see ports/output/llm_types.py)
    "ExecutionContext",
    "ExecutionResult",
    # Metrics
    "IMetrics",
    "MetricData",
    # Monitoring
    "IMonitoredService",
    "MonitoringConfig",
    "MonitoringState",
    "MonitoringStatus",
    # Notifier
    "INotifier",
    "Action",
    "Attachment",
    "DeliveryStatus",
    "Notification",
    "NotificationChannel",
    "NotificationPriority",
    "NotificationResult",
    "RichContent",
    # Distributed Lock
    "IDistributedLock",
    "AcquireResult",
    "AcquireStatus",
    "LockHolder",
    "ReleaseResult",
    "ReleaseReason",
    # Pipeline Queue
    "IPipelineQueue",
    "EnqueueResult",
    "IPipelineQueueEntry",
    # Project Manager Service
    "IProjectManagerService",
    "ProjectConfig",
    # Prompt Builder (D1 — assembles vendor-agnostic StructuredPrompt)
    "IPromptBuilder",
    "StructuredPrompt",
    "ExecutionOutput",
    # Pipeline Queue Service
    "IPipelineQueueService",
    "PipelineQueueEntry",
    "QueueEntry",  # Backward compatibility alias
    # PR Review Cycle Service
    "IPRReviewCycle",
    "PRReviewCycleRequest",
    "PRReviewCycleStateData",
    # Repair Cycle Service
    "IRepairCycle",
    "RepairCycleContext",
    "IRepairCycleCheckpointStore",
    # Systemic Analysis Service
    "ISystemicAnalysisService",
    # Repository
    "IRepository",
    "MergeResult",
    "RepositoryStatus",
    # Storage
    # Ticket System
    "ITicketSystem",
    "Comment",
    # Version Control Service
    "IVersionControlService",
    "Repository",
    "VCSStatus",
    # Work Item Service
    "IWorkItemService",
    # Workflow Config Service
    "IWorkflowConfigService",
    # Workflow Orchestrator
    "IWorkflowOrchestrator",
    "CardMovedRequest",
    "IssueData",
    "ReviewCycleCompletedRequest",
    "StageCompletedRequest",
    "WorkflowAction",
    "WorkflowResult",
]
