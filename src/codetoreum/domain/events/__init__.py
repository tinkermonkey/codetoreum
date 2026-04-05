"""Vendor-agnostic events for adapter integration and domain events.

This package contains two types of events:
1. Domain Events: Internal events for workflow state management (DomainEvent)
2. Adapter Events: Vendor-agnostic events emitted by adapters to the orchestrator

Event Categories (Adapter Events):
- Board Events: Work item movement between columns
- Discussion Events: Comments and responses on work items
- Code Review Events: Code review lifecycle and feedback
- Pipeline Lock Events: Lock management for work item processing
- Work Item Events: Work item creation and updates
"""

# Adapter event infrastructure
from .adapter_events import (
    CodetoreumEvent,
    now_iso,
)

# Board events
from .board_events import (
    BoardReconciledEvent,
    ColumnSLAExceededEvent,
    WorkItemColumnChangedEvent,
    WorkItemPositionChangedEvent,
)

# Branch resolution events
from .branch_events import (
    BranchCreatedEvent as BranchResolutionCreatedEvent,
    BranchResolvedEvent,
    BranchReusedEvent,
)

# Container execution events
from .container_events import (
    ContainerExecutionCompletedEvent,
)

# Container recovery events
from .container_recovery_events import (
    ContainerKilledEvent,
    ContainerRecoveredEvent,
    ContainerRecoveryCompletedEvent,
)

# Discussion events
from .discussion_events import (
    AgentResponsePostedEvent,
    Comment,
    CommentContext,
    CommentNeedsResponseEvent,
    CommentPostedEvent,
)

# Execution events
from .execution_events import (
    ExecutionTimedOutEvent,
)

# Legacy domain events (static imports for mypy compatibility)
from .legacy_domain_events import (
    AgentAssigned,
    AgentCapabilityAdded,
    AgentCapabilityRemoved,
    AgentCapabilityUpdated,
    AgentConfigUpdated,
    AgentConstraintsUpdated,
    AgentCreated,
    AgentExecutionCompleted,
    AgentExecutionFailed,
    AgentExecutionStarted,
    AgentMaxRetriesUpdated,
    AgentMcpServerAdded,
    AgentMcpServerRemoved,
    AgentModelUpdated,
    AgentTimeoutUpdated,
    BoardReconciled,
    CommandMounted,
    CommandUnmounted,
    DomainEvent,
    EnvironmentVariableChanged,
    ExecutionCancelled,
    ExecutionCompleted,
    ExecutionFailed,
    ExecutionInitialized,
    ExecutionPaused,
    ExecutionResumed,
    ExecutionRetryScheduled,
    ExecutionStarted,
    ExecutionTimeout,
    PipelineCompleted,
    PipelineConfigUpdated,
    PipelineFailed,
    PipelineStageCompleted,
    PipelineStageFailed,
    PipelineStageStarted,
    ProjectConfigUpdated,
    ProjectContextCreated,
    ProjectDockerConfigUpdated,
    ProjectTestConfigUpdated,
    ProjectWorkflowMappingAdded,
    ReviewApproved,
    ReviewCycleApproved,
    ReviewCycleCreated,
    ReviewCycleEscalated,
    ReviewCycleRejected,
    ReviewFeedbackSubmitted,
    ReviewIterationStarted,
    ReviewRejected,
    SubAgentMounted,
    SubAgentUnmounted,
    WorkflowAttached,
    WorkflowBranchSelected,
    WorkflowCancelled,
    WorkflowCompleted,
    WorkflowCreated,
    WorkflowFailed,
    WorkflowPaused,
    WorkflowResumed,
    WorkflowStageAdvanced,
    WorkflowStageStatusUpdated,
    WorkflowStarted,
    WorkItemBlocked,
    WorkItemColumnChanged,
    WorkItemCompleted,
    WorkItemCreated,
    WorkItemFailed,
    WorkItemLabelsUpdated,
    WorkItemPriorityUpdated,
    WorkItemStageUpdated,
    WorkItemStarted,
    WorkItemUnblocked,
    WorkItemUnderReview,
)

# Pipeline lock events
from .lock_events import (
    LockAcquiredEvent,
    LockReleasedEvent,
    LockStuckEvent,
    PipelineLockAcquiredEvent,
    PipelineLockReleasedEvent,
    StaleLockDetectedEvent,
    WorkItemQueuedEvent,
)

# Project management events
from .project_events import (
    OrchestrationCycleCompletedEvent,
    ProjectClonedEvent,
    ProjectCloneFailedEvent,
    ProjectDisabledEvent,
    ProjectEnabledEvent,
)

# Queue events
from .queue_events import (
    QueueItemAddedEvent,
    QueueItemRemovedEvent,
    QueuePositionChangedEvent,
    WorkItemDeadLetterQueuedEvent,
)

# Repair cycle events
from .repair_cycle_events import (
    EnvironmentRebuildCompletedEvent,
    EnvironmentRebuildExhaustedEvent,
    EnvironmentRebuildStartedEvent,
    EnvironmentVerificationCompletedEvent,
    EnvironmentVerificationStartedEvent,
    RepairCycleCheckpointFailedEvent,
    RepairCycleCompletedEvent,
    RepairCycleFastFailEvent,
    RepairCycleFileFixCompletedEvent,
    RepairCycleFileFixStartedEvent,
    RepairCycleFixCycleStartedEvent,
    RepairCycleMetricsBackendFailedEvent,
    RepairCycleResumedEvent,
    RepairCycleStartedEvent,
    RepairCycleTestCycleCompletedEvent,
    RepairCycleTestExecutionCompletedEvent,
    RepairCycleTestExecutionStartedEvent,
    RepairCycleWarningReviewCompletedEvent,
    RepairCycleWarningReviewStartedEvent,
    SystemicAnalysisCompletedEvent,
    SystemicAnalysisStartedEvent,
    SystemicFixCompletedEvent,
    SystemicFixStartedEvent,
)

# Repository events
from .repository_events import (
    BranchCreatedEvent,
    BranchPushedEvent,
    CommitCreatedEvent,
    FilesStagedEvent,
)

# Review cycle events
from .review_cycle_events import (
    ReviewCycleApprovedEvent,
    ReviewCycleEscalatedToHumanEvent,
    ReviewCycleHumanFeedbackReceivedEvent,
    ReviewCycleIterationCompletedEvent,
    ReviewCycleMakerRevisionEvent,
    ReviewCycleMaxIterationsReachedEvent,
    ReviewCycleStartedEvent,
)

# Code review events
from .review_events import (
    CodeReviewStatus,
    ReviewCommentAddedEvent,
    ReviewStatusChangedEvent,
)

# Storage events
from .storage_events import (
    ArtifactDeletedEvent,
    ArtifactUploadedEvent,
)

# Work item events
from .work_item_events import (
    WorkItemCreatedEvent,
    WorkItemUpdatedEvent,
)

__all__ = [
    # Legacy domain events (from events.py)
    "DomainEvent",
    "WorkItemCreated",
    "AgentAssigned",
    "WorkItemStarted",
    "WorkItemUnderReview",
    "WorkItemCompleted",
    "WorkItemFailed",
    "WorkItemBlocked",
    "WorkItemUnblocked",
    "WorkflowAttached",
    "WorkItemStageUpdated",
    "WorkItemLabelsUpdated",
    "WorkItemPriorityUpdated",
    "AgentCreated",
    "AgentCapabilityAdded",
    "AgentCapabilityRemoved",
    "AgentCapabilityUpdated",
    "AgentModelUpdated",
    "AgentTimeoutUpdated",
    "AgentMaxRetriesUpdated",
    "AgentConstraintsUpdated",
    "AgentMcpServerAdded",
    "AgentMcpServerRemoved",
    "AgentExecutionStarted",
    "AgentExecutionCompleted",
    "AgentExecutionFailed",
    "ExecutionInitialized",
    "ExecutionStarted",
    "ExecutionCompleted",
    "ExecutionFailed",
    "ExecutionTimeout",
    "ExecutionCancelled",
    "ExecutionPaused",
    "ExecutionResumed",
    "ExecutionRetryScheduled",
    "WorkflowBranchSelected",
    "WorkflowCreated",
    "WorkflowStarted",
    "WorkflowStageAdvanced",
    "WorkflowStageStatusUpdated",
    "WorkflowCompleted",
    "WorkflowFailed",
    "WorkflowPaused",
    "WorkflowResumed",
    "WorkflowCancelled",
    "ReviewApproved",
    "ReviewCycleCreated",
    "ReviewIterationStarted",
    "ReviewFeedbackSubmitted",
    "ReviewCycleApproved",
    "ReviewCycleRejected",
    "ReviewCycleEscalated",
    "ReviewRejected",
    "ProjectContextCreated",
    "ProjectTestConfigUpdated",
    "ProjectDockerConfigUpdated",
    "ProjectWorkflowMappingAdded",
    "PipelineStageStarted",
    "PipelineStageCompleted",
    "PipelineStageFailed",
    "PipelineCompleted",
    "PipelineFailed",
    "ProjectConfigUpdated",
    "AgentConfigUpdated",
    "PipelineConfigUpdated",
    "EnvironmentVariableChanged",
    "CommandMounted",
    "CommandUnmounted",
    "SubAgentMounted",
    "SubAgentUnmounted",
    # Adapter event infrastructure
    "CodetoreumEvent",
    "now_iso",
    # Board events
    "WorkItemColumnChangedEvent",
    "WorkItemPositionChangedEvent",
    "BoardReconciledEvent",
    "ColumnSLAExceededEvent",
    # Branch resolution events
    "BranchResolvedEvent",
    "BranchReusedEvent",
    "BranchResolutionCreatedEvent",
    # Discussion events
    "Comment",
    "CommentContext",
    "CommentNeedsResponseEvent",
    "CommentPostedEvent",
    "AgentResponsePostedEvent",
    # Code review events
    "CodeReviewStatus",
    "ReviewStatusChangedEvent",
    "ReviewCommentAddedEvent",
    # Pipeline lock events
    "LockAcquiredEvent",
    "LockReleasedEvent",
    "StaleLockDetectedEvent",
    "LockStuckEvent",
    "PipelineLockAcquiredEvent",
    "PipelineLockReleasedEvent",
    "WorkItemQueuedEvent",
    # Work item events
    "WorkItemCreatedEvent",
    "WorkItemUpdatedEvent",
    # Repair cycle events
    "RepairCycleStartedEvent",
    "RepairCycleTestExecutionStartedEvent",
    "RepairCycleTestExecutionCompletedEvent",
    "RepairCycleFixCycleStartedEvent",
    "RepairCycleFileFixStartedEvent",
    "RepairCycleFileFixCompletedEvent",
    "RepairCycleWarningReviewStartedEvent",
    "RepairCycleWarningReviewCompletedEvent",
    "RepairCycleTestCycleCompletedEvent",
    "RepairCycleFastFailEvent",
    "RepairCycleResumedEvent",
    "RepairCycleCheckpointFailedEvent",
    "RepairCycleMetricsBackendFailedEvent",
    "RepairCycleCompletedEvent",
    "SystemicAnalysisStartedEvent",
    "SystemicAnalysisCompletedEvent",
    "SystemicFixCompletedEvent",
    "SystemicFixStartedEvent",
    "EnvironmentRebuildStartedEvent",
    "EnvironmentRebuildCompletedEvent",
    "EnvironmentRebuildExhaustedEvent",
    "EnvironmentVerificationStartedEvent",
    "EnvironmentVerificationCompletedEvent",
    # Review cycle events
    "ReviewCycleStartedEvent",
    "ReviewCycleIterationCompletedEvent",
    "ReviewCycleMakerRevisionEvent",
    "ReviewCycleEscalatedToHumanEvent",
    "ReviewCycleHumanFeedbackReceivedEvent",
    "ReviewCycleMaxIterationsReachedEvent",
    "ReviewCycleApprovedEvent",
    # Container execution events
    "ContainerExecutionCompletedEvent",
    # Execution events
    "ExecutionTimedOutEvent",
    # Container recovery events
    "ContainerRecoveredEvent",
    "ContainerKilledEvent",
    "ContainerRecoveryCompletedEvent",
    # Project management events
    "ProjectClonedEvent",
    "ProjectCloneFailedEvent",
    "ProjectEnabledEvent",
    "ProjectDisabledEvent",
    "OrchestrationCycleCompletedEvent",
    # Queue events
    "QueueItemAddedEvent",
    "QueueItemRemovedEvent",
    "QueuePositionChangedEvent",
    "WorkItemDeadLetterQueuedEvent",
    # Repository events
    "CommitCreatedEvent",
    "BranchCreatedEvent",
    "BranchPushedEvent",
    "FilesStagedEvent",
    # Storage events
    "ArtifactUploadedEvent",
    "ArtifactDeletedEvent",
]
