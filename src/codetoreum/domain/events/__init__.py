"""Vendor-agnostic events for adapter integration and domain events.

This package contains two types of events:
1. Domain Events: Internal events for workflow state management (CodetoreumEvent)
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

# Agent domain events (frozen dataclasses)
from .agent_events import (
    AgentCapabilityAddedEvent,
    AgentCapabilityRemovedEvent,
    AgentCapabilityUpdatedEvent,
    AgentConstraintsUpdatedEvent,
    AgentCreatedEvent,
    AgentMaxRetriesUpdatedEvent,
    AgentMcpServerAddedEvent,
    AgentMcpServerRemovedEvent,
    AgentModelUpdatedEvent,
    AgentTimeoutUpdatedEvent,
)

# Board events
from .board_events import (
    BoardReconciledEvent,
    BoardSyncFailedEvent,
    ColumnSLAExceededEvent,
    WorkItemColumnChangedEvent,
    WorkItemPositionChangedEvent,
)

# Branch resolution events
from .branch_events import (
    BranchResolutionCreatedEvent,
    BranchResolvedEvent,
    BranchReusedEvent,
)

# CI pipeline events
from .ci_pipeline_events import (
    CIPipelineStatusCheckedEvent,
    CIPipelineStatusValue,
    CIRunCompletedEvent,
    CIRunStartedEvent,
)

# Coding agent events (granular per-execution telemetry, 11 events)
from .coding_agent_events import (
    CodingAgentApiRetryEvent,
    CodingAgentCompletedEvent,
    CodingAgentInvokedEvent,
    CodingAgentOtlpSpanEvent,
    CodingAgentRateLimitEvent,
    CodingAgentReadyEvent,
    CodingAgentTextOutputEvent,
    CodingAgentThinkingEvent,
    CodingAgentTokensUsedEvent,
    CodingAgentToolCallEvent,
    CodingAgentToolResultEvent,
)

# Configuration domain events (frozen dataclasses)
from .configuration_events import (
    AgentConfigUpdatedEvent,
    CommandMountedEvent,
    CommandUnmountedEvent,
    EnvironmentVariableChangedEvent,
    PipelineConfigUpdatedEvent,
    ProjectConfigUpdatedEvent,
    SubAgentMountedEvent,
    SubAgentUnmountedEvent,
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
    ConversationalLoopStartedEvent,
    FeedbackListeningStartedEvent,
    FeedbackListeningStoppedEvent,
)

# Execution events
from .execution_events import (
    AgentExecutionCompletedEvent,
    ExecutionCancelledEvent,
    ExecutionCompletedEvent,
    ExecutionFailedEvent,
    ExecutionInitializedEvent,
    ExecutionPausedEvent,
    ExecutionResumedEvent,
    ExecutionRetryScheduledEvent,
    ExecutionStartedEvent,
    ExecutionTimedOutEvent,
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

# PR Review Cycle events
from .pr_review_cycle_events import (
    PRReviewCycleApprovedEvent,
    PRReviewCycleCICheckCompletedEvent,
    PRReviewCycleCodeReviewStartedEvent,
    PRReviewCycleConsolidationCompletedEvent,
    PRReviewCycleConsolidationStartedEvent,
    PRReviewCycleEscalatedEvent,
    PRReviewCycleIssuesFoundEvent,
    PRReviewCycleMaxCyclesReachedEvent,
    PRReviewCyclePhaseCompletedEvent,
    PRReviewCyclePhaseStartedEvent,
    PRReviewCycleStartedEvent,
    PRReviewCycleSubIssuesCreatedEvent,
    PRReviewCycleVerificationStartedEvent,
)

# Project context domain events (frozen dataclasses)
from .project_context_events import (
    ProjectContextCreatedEvent,
    ProjectDockerConfigUpdatedEvent,
    ProjectTestConfigUpdatedEvent,
    ProjectWorkflowMappingAddedEvent,
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
    TaskDispatchFailedEvent,
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
    ReviewCycleCreatedEvent,
    ReviewCycleEscalatedToHumanEvent,
    ReviewCycleFeedbackSubmittedEvent,
    ReviewCycleHumanFeedbackReceivedEvent,
    ReviewCycleIterationCompletedEvent,
    ReviewCycleIterationStartedEvent,
    ReviewCycleMakerRevisionEvent,
    ReviewCycleMaxIterationsReachedEvent,
    ReviewCycleRejectedEvent,
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

# Work item lifecycle domain events (frozen dataclasses)
from .work_item_events import (
    AgentAssignedEvent,
    WorkItemBlockedEvent,
    WorkItemColumnUpdatedEvent,
    WorkItemCompletedEvent,
    WorkItemCreatedEvent,
    WorkItemFailedEvent,
    WorkItemLabelsUpdatedEvent,
    WorkItemPriorityUpdatedEvent,
    WorkItemStageUpdatedEvent,
    WorkItemStartedEvent,
    WorkItemUnblockedEvent,
    WorkItemUnderReviewEvent,
    WorkItemUpdatedEvent,
)

# Pipeline domain events (frozen dataclasses)
# Workflow events
from .workflow_events import (
    PipelineCompletedEvent,
    PipelineFailedEvent,
    PipelineStageCompletedEvent,
    PipelineStageFailedEvent,
    PipelineStageStartedEvent,
    WorkflowAttachedEvent,
    WorkflowBranchSelectedEvent,
    WorkflowCancelledEvent,
    WorkflowCompletedEvent,
    WorkflowCreatedEvent,
    WorkflowFailedEvent,
    WorkflowOrphanedEvent,
    WorkflowPausedEvent,
    WorkflowResumedEvent,
    WorkflowStageAdvancedEvent,
    WorkflowStageStatusUpdatedEvent,
    WorkflowStartedEvent,
)

# Work item events

__all__ = [
    "CodetoreumEvent",
    # Adapter event infrastructure
    "now_iso",
    # Board events
    "WorkItemColumnChangedEvent",
    "WorkItemPositionChangedEvent",
    "BoardReconciledEvent",
    "BoardSyncFailedEvent",
    "ColumnSLAExceededEvent",
    # Branch resolution events
    "BranchResolvedEvent",
    "BranchReusedEvent",
    "BranchResolutionCreatedEvent",
    # CI pipeline events
    "CIPipelineStatusValue",
    "CIPipelineStatusCheckedEvent",
    "CIRunStartedEvent",
    "CIRunCompletedEvent",
    # Discussion events
    "Comment",
    "CommentContext",
    "CommentNeedsResponseEvent",
    "CommentPostedEvent",
    "AgentResponsePostedEvent",
    "ConversationalLoopStartedEvent",
    "FeedbackListeningStartedEvent",
    "FeedbackListeningStoppedEvent",
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
    "ReviewCycleCreatedEvent",
    "ReviewCycleIterationStartedEvent",
    "ReviewCycleFeedbackSubmittedEvent",
    "ReviewCycleRejectedEvent",
    "ReviewCycleStartedEvent",
    "ReviewCycleIterationCompletedEvent",
    "ReviewCycleMakerRevisionEvent",
    "ReviewCycleEscalatedToHumanEvent",
    "ReviewCycleHumanFeedbackReceivedEvent",
    "ReviewCycleMaxIterationsReachedEvent",
    "ReviewCycleApprovedEvent",
    # PR Review Cycle events
    "PRReviewCycleStartedEvent",
    "PRReviewCyclePhaseStartedEvent",
    "PRReviewCycleCodeReviewStartedEvent",
    "PRReviewCycleVerificationStartedEvent",
    "PRReviewCycleCICheckCompletedEvent",
    "PRReviewCycleConsolidationStartedEvent",
    "PRReviewCycleConsolidationCompletedEvent",
    "PRReviewCycleApprovedEvent",
    "PRReviewCycleIssuesFoundEvent",
    "PRReviewCycleMaxCyclesReachedEvent",
    "PRReviewCycleEscalatedEvent",
    "PRReviewCycleSubIssuesCreatedEvent",
    "PRReviewCyclePhaseCompletedEvent",
    # Container execution events
    "ContainerExecutionCompletedEvent",
    # Execution events
    "AgentExecutionCompletedEvent",
    "ExecutionCancelledEvent",
    "ExecutionInitializedEvent",
    "ExecutionPausedEvent",
    "ExecutionResumedEvent",
    "ExecutionRetryScheduledEvent",
    "ExecutionStartedEvent",
    "ExecutionCompletedEvent",
    "ExecutionFailedEvent",
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
    "TaskDispatchFailedEvent",
    "WorkItemDeadLetterQueuedEvent",
    # Repository events
    "CommitCreatedEvent",
    "BranchCreatedEvent",
    "BranchPushedEvent",
    "FilesStagedEvent",
    # Storage events
    "ArtifactUploadedEvent",
    "ArtifactDeletedEvent",
    # Workflow events
    "WorkflowAttachedEvent",
    "WorkflowBranchSelectedEvent",
    "WorkflowCancelledEvent",
    "WorkflowCompletedEvent",
    "WorkflowCreatedEvent",
    "WorkflowFailedEvent",
    "WorkflowOrphanedEvent",
    "WorkflowPausedEvent",
    "WorkflowResumedEvent",
    "WorkflowStageAdvancedEvent",
    "WorkflowStageStatusUpdatedEvent",
    "WorkflowStartedEvent",
    # Modern domain events
    "AgentCreatedEvent",
    "AgentCapabilityAddedEvent",
    "AgentCapabilityRemovedEvent",
    "AgentCapabilityUpdatedEvent",
    "AgentModelUpdatedEvent",
    "AgentTimeoutUpdatedEvent",
    "AgentMaxRetriesUpdatedEvent",
    "AgentConstraintsUpdatedEvent",
    "AgentMcpServerAddedEvent",
    "AgentMcpServerRemovedEvent",
    "ProjectContextCreatedEvent",
    "ProjectTestConfigUpdatedEvent",
    "ProjectDockerConfigUpdatedEvent",
    "ProjectWorkflowMappingAddedEvent",
    "ProjectConfigUpdatedEvent",
    "AgentConfigUpdatedEvent",
    "PipelineConfigUpdatedEvent",
    "EnvironmentVariableChangedEvent",
    "CommandMountedEvent",
    "CommandUnmountedEvent",
    "SubAgentMountedEvent",
    "SubAgentUnmountedEvent",
    "AgentAssignedEvent",
    "WorkItemStartedEvent",
    "WorkItemUnderReviewEvent",
    "WorkItemCompletedEvent",
    "WorkItemFailedEvent",
    "WorkItemBlockedEvent",
    "WorkItemUnblockedEvent",
    "WorkItemColumnUpdatedEvent",
    "WorkItemStageUpdatedEvent",
    "WorkItemLabelsUpdatedEvent",
    "WorkItemPriorityUpdatedEvent",
    "PipelineStageStartedEvent",
    "PipelineStageCompletedEvent",
    "PipelineStageFailedEvent",
    "PipelineCompletedEvent",
    "PipelineFailedEvent",
    # Coding agent events (granular per-execution telemetry, 11 events)
    "CodingAgentInvokedEvent",
    "CodingAgentReadyEvent",
    "CodingAgentToolCallEvent",
    "CodingAgentToolResultEvent",
    "CodingAgentTextOutputEvent",
    "CodingAgentThinkingEvent",
    "CodingAgentRateLimitEvent",
    "CodingAgentApiRetryEvent",
    "CodingAgentOtlpSpanEvent",
    "CodingAgentTokensUsedEvent",
    "CodingAgentCompletedEvent",
]
