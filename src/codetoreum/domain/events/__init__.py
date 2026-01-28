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

# Import old domain events (backward compatibility)
# These are imported from the base events.py module
import sys
from pathlib import Path

# Add the parent events.py to the namespace for backward compatibility
_events_py = Path(__file__).parent.parent / "events.py"
if _events_py.exists():
    import importlib.util
    spec = importlib.util.spec_from_file_location("_old_events", str(_events_py))
    _old_events = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_old_events)

    # Export all old event classes
    for name in dir(_old_events):
        if not name.startswith("_") and name[0].isupper():
            globals()[name] = getattr(_old_events, name)

# Adapter event infrastructure
from .adapter_events import (
    CodetoreumEvent,
    now_iso,
)

# Board events
from .board_events import (
    BoardReconciledEvent,
    WorkItemColumnChangedEvent,
)

# Discussion events
from .discussion_events import (
    Comment,
    CommentContext,
    CommentNeedsResponseEvent,
    CommentPostedEvent,
    AgentResponsePostedEvent,
)

# Code review events
from .review_events import (
    CodeReviewStatus,
    ReviewCommentAddedEvent,
    ReviewStatusChangedEvent,
)

# Pipeline lock events
from .lock_events import (
    LockAcquiredEvent,
    LockReleasedEvent,
    LockStaleDetectedEvent,
    PipelineLockAcquiredEvent,
    PipelineLockReleasedEvent,
    WorkItemQueuedEvent,
)

# Work item events
from .work_item_events import (
    WorkItemCreatedEvent,
    WorkItemUpdatedEvent,
)

# Repair cycle events
from .repair_cycle_events import (
    RepairCycleStartedEvent,
    RepairCycleTestExecutionStartedEvent,
    RepairCycleTestExecutionCompletedEvent,
    RepairCycleFixCycleStartedEvent,
    RepairCycleFileFixStartedEvent,
    RepairCycleFileFixCompletedEvent,
    RepairCycleWarningReviewStartedEvent,
    RepairCycleWarningReviewCompletedEvent,
    RepairCycleTestCycleCompletedEvent,
    RepairCycleFastFailEvent,
    RepairCycleResumedEvent,
    RepairCycleCheckpointFailedEvent,
    RepairCycleMetricsBackendFailedEvent,
    RepairCycleCompletedEvent,
)

# Container recovery events
from .container_recovery_events import (
    ContainerRecoveredEvent,
    ContainerKilledEvent,
    ContainerRecoveryCompletedEvent,
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
    "ExecutionInitialized",
    "ExecutionStarted",
    "ExecutionCompleted",
    "ExecutionFailed",
    "ExecutionTimeout",
    "ExecutionCancelled",
    "ExecutionPaused",
    "ExecutionResumed",
    "WorkflowCreated",
    "WorkflowStarted",
    "WorkflowStageAdvanced",
    "WorkflowStageStatusUpdated",
    "WorkflowCompleted",
    "WorkflowFailed",
    "WorkflowPaused",
    "WorkflowResumed",
    "WorkflowCancelled",
    "ReviewCycleCreated",
    "ReviewIterationStarted",
    "ReviewFeedbackSubmitted",
    "ReviewCycleApproved",
    "ReviewCycleRejected",
    "ReviewCycleEscalated",
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
    "BoardReconciledEvent",
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
    "LockStaleDetectedEvent",
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
    # Container recovery events
    "ContainerRecoveredEvent",
    "ContainerKilledEvent",
    "ContainerRecoveryCompletedEvent",
]
