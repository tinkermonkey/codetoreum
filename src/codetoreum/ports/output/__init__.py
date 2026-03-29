"""Output port interfaces."""

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
from codetoreum.ports.output.code_review_service import (
    Approval,
    CodeReview,
    CodeReviewStatus,
    ICodeReviewService,
    ReviewComment,
)
from codetoreum.ports.output.container import (
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
from codetoreum.ports.output.discussion_adapter import (
    DiscussionMonitoringConfig,
    DiscussionThread,
    IDiscussionAdapter,
)
from codetoreum.ports.output.encryption_service import (
    DecryptionError,
    EncryptionError,
    IEncryptionService,
)
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
from codetoreum.ports.output.llm_provider import (
    ExecutionContext,
    ExecutionResult,
    ILLMProvider,
    ModelInfo,
    StreamCallback,
    StreamChunk,
    ToolCall,
    ToolCallDelta,
    ToolDefinition,
    UsageStats,
)
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
from codetoreum.ports.output.pipeline_lock_service import (
    IPipelineLockService,
    PipelineLock,
)
from codetoreum.ports.output.pipeline_queue_service import (
    IPipelineQueueService,
    PipelineQueueEntry,
    QueueEntry,  # Backward compatibility alias
)
from codetoreum.ports.output.project_manager_service import IProjectManagerService
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
from codetoreum.ports.output.storage import IStorage, StorageObject
from codetoreum.ports.output.systemic_analysis_service import (
    ISystemicAnalysisService,
)
from codetoreum.ports.output.ticket_system import Comment, ITicketSystem
from codetoreum.ports.output.version_control_service import (
    IVersionControlService,
    Repository,
    VCSStatus,
)
from codetoreum.ports.output.work_item_service import IWorkItemService
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService

__all__ = [
    # Agent Executor
    "IAgentExecutor",
    # Container Recovery Service
    "IAgentContainerRecoveryService",
    "ContainerMetadata",
    "RecoveryAssessment",
    "RecoveryResult",
    # Board Service
    "IBoardService",
    "BoardColumn",
    "BoardConfig",
    "ColumnMovementResult",
    "MovedByType",
    "ProjectBoard",
    "ReconciliationResult",
    "WorkItemPosition",
    # Code Review Service
    "ICodeReviewService",
    "Approval",
    "CodeReview",
    "CodeReviewStatus",
    "ReviewComment",
    # Container
    "IContainer",
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
    # LLM Provider
    "ILLMProvider",
    "ExecutionContext",
    "ExecutionResult",
    "ModelInfo",
    "StreamCallback",
    "StreamChunk",
    "ToolCall",
    "ToolCallDelta",
    "ToolDefinition",
    "UsageStats",
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
    # Pipeline Lock Service
    "IPipelineLockService",
    "PipelineLock",
    # Project Manager Service
    "IProjectManagerService",
    "ProjectConfig",
    # Pipeline Queue Service
    "IPipelineQueueService",
    "PipelineQueueEntry",
    "QueueEntry",  # Backward compatibility alias
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
    "IStorage",
    "StorageObject",
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
]
