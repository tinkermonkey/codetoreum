"""Output port interfaces."""

from codetoreum.domain.repair_cycle_types import EnvironmentRepairConfig
from codetoreum.domain.value_objects import ProjectConfig
from codetoreum.ports.output.agent_executor import IAgentExecutor
from codetoreum.ports.output.agent_launcher import IAgentLauncher
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
from codetoreum.ports.output.llm_provider import (
    ExecutionContext,
    ExecutionResult,
    ModelInfo,
    StreamCallback,
    StreamChunk,
    ToolCall,
    ToolCallDelta,
    ToolDefinition,
    UsageStats,
)
from codetoreum.ports.output.llm_text_provider import ILLMTextProvider

# ``ILLMProvider`` is the historical name for the autonomous-agent launcher
# port. It is now an alias of ``IAgentLauncher`` (the only production
# implementation, ``ClaudeCodeAdapter``, is an agent launcher). New code
# should import ``IAgentLauncher`` or ``ILLMTextProvider`` directly; see
# ``documentation/architecture/ports/output/agent-launcher.md``.
ILLMProvider = IAgentLauncher

# ``AgentLLMFactory`` is the async factory callable used throughout the
# orchestration layer to obtain an agent launcher configured for a given
# agent (system prompt, model, etc.). Defined here (after the alias) so the
# alias is resolved.
from collections.abc import Callable, Coroutine
from typing import Any

AgentLLMFactory = Callable[[str], Coroutine[Any, Any, IAgentLauncher]]
"""Async factory callable that creates a configured IAgentLauncher for an agent.

Input:  agent_name (str) - e.g., "senior_software_engineer"
Output: Coroutine resolving to a configured IAgentLauncher with the agent's
        model, temperature, system prompt, tool config.

This factory is async-safe and can be called from both sync and async contexts
(via ``await factory(agent_name)``). Pre-populated caches in the resolver
ensure most calls complete without needing the event loop.
"""
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
from codetoreum.ports.output.pr_review_cycle_service import (
    IPRReviewCycle,
    PRReviewCycleRequest,
    PRReviewCycleStateData,
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
    # Branch Resolution Service
    "IBranchResolutionService",
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
    # LLM Provider (split into agent launcher + text provider; ILLMProvider is a deprecated alias)
    "AgentLLMFactory",
    "IAgentLauncher",
    "ILLMProvider",
    "ILLMTextProvider",
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
