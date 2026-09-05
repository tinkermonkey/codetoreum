"""Domain layer - Pure business logic with no external dependencies."""

from codetoreum.domain.agent import Agent, AgentCapability, AgentType
from codetoreum.domain.agent_execution import AgentExecution, ExecutionStatus
from codetoreum.domain.board_workflow_template import (
    BoardReconciliationConfig,
    BoardWorkflowTemplate,
    ColumnTemplate,
    ColumnType,
)
from codetoreum.domain.conversational_session import ConversationalSessionState
from codetoreum.domain.events import (
    AgentAssignedEvent,
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
    BoardReconciledEvent,
    ProjectContextCreatedEvent,
    ProjectDockerConfigUpdatedEvent,
    ProjectTestConfigUpdatedEvent,
    ProjectWorkflowMappingAddedEvent,
    WorkflowAttachedEvent,
    WorkflowCancelledEvent,
    WorkflowCompletedEvent,
    WorkflowCreatedEvent,
    WorkflowFailedEvent,
    WorkflowPausedEvent,
    WorkflowResumedEvent,
    WorkflowStageAdvancedEvent,
    WorkflowStageStatusUpdatedEvent,
    WorkflowStartedEvent,
    WorkItemBlockedEvent,
    WorkItemColumnChangedEvent,
    WorkItemCompletedEvent,
    WorkItemCreatedEvent,
    WorkItemFailedEvent,
    WorkItemLabelsUpdatedEvent,
    WorkItemPriorityUpdatedEvent,
    WorkItemStageUpdatedEvent,
    WorkItemStartedEvent,
    WorkItemUnblockedEvent,
    WorkItemUnderReviewEvent,
)
from codetoreum.domain.exceptions import DomainError
from codetoreum.domain.pipeline_stage import PipelineStage, StageStatus, StageType
from codetoreum.domain.project_context import ProjectContext
from codetoreum.domain.repair_cycle_types import (
    CycleResult,
    EnvironmentRepairConfig,
    RebuildResult,
    RepairCycleAgentConfig,
    RepairCycleResult,
    RepairCycleStageConfig,
    RepairTestFailure,
    RepairTestResult,
    RepairTestRunConfig,
    RepairTestType,
    RepairTestWarning,
    VerificationResult,
)
from codetoreum.domain.review_cycle import (
    ReviewCycle,
    ReviewDecision,
    ReviewFeedback,
    ReviewIteration,
    ReviewStatus,
)
from codetoreum.domain.services import (
    AgentMatchingService,
    AssignmentResult,
    ExecutionContextBuilder,
    WorkAssignmentService,
    WorkflowValidationService,
)
from codetoreum.domain.user import (
    ROLE_PERMISSIONS,
    APIKey,
    AuthContext,
    Permission,
    User,
    UserRole,
)
from codetoreum.domain.value_objects import (
    AgentId,
    ContainerConfig,
    ExecutionContext,
    ExecutionId,
    ExecutionResult,
    Requirement,
    TimeRange,
    TokenUsage,
    WorkflowId,
    WorkItemId,
)
from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus
from codetoreum.domain.workflow import Workflow, WorkflowStatus
from codetoreum.domain.workflow_template import StageTemplate, WorkflowTemplate
from codetoreum.domain.workspace_context import (
    WorkspaceContext,
    WorkspaceType,
)

__all__ = [
    # Base classes
    "DomainError",
    # Value Objects
    "WorkItemId",
    "WorkflowId",
    "AgentId",
    "ExecutionId",
    "Requirement",
    "ExecutionResult",
    "ContainerConfig",
    "ExecutionContext",
    "TimeRange",
    "TokenUsage",
    # Work Item
    "WorkItem",
    "WorkItemStatus",
    "WorkItemPriority",
    # Agent
    "Agent",
    "AgentType",
    "AgentCapability",
    # Agent Execution
    "AgentExecution",
    "ExecutionStatus",
    # Pipeline Stage
    "PipelineStage",
    "StageStatus",
    "StageType",
    # Workflow
    "Workflow",
    "WorkflowStatus",
    # Workflow Template
    "WorkflowTemplate",
    "StageTemplate",
    # Board Workflow Template
    "BoardWorkflowTemplate",
    "ColumnTemplate",
    "ColumnType",
    "BoardReconciliationConfig",
    # Project Context
    "ProjectContext",
    # Workspace Context
    "WorkspaceContext",
    "WorkspaceType",
    # Review Cycle
    "ReviewCycle",
    "ReviewStatus",
    "ReviewDecision",
    "ReviewFeedback",
    "ReviewIteration",
    "ReviewCycleCreatedEvent",
    "ReviewCycleIterationStartedEvent",
    "ReviewCycleFeedbackSubmittedEvent",
    "ReviewCycleApprovedEvent",
    "ReviewCycleRejectedEvent",
    "ReviewCycleEscalatedToHumanEvent",
    # Work Item Events
    "AgentAssignedEvent",
    "WorkflowAttachedEvent",
    # Board Events
    "WorkItemColumnChangedEvent",
    "BoardReconciledEvent",
    # Agent Events
    # Execution Events
    "ExecutionInitializedEvent",
    "ExecutionStartedEvent",
    "ExecutionCompletedEvent",
    "ExecutionFailedEvent",
    # Workflow Events
    "WorkflowCreatedEvent",
    "WorkflowStartedEvent",
    "WorkflowStageAdvancedEvent",
    "WorkflowStageStatusUpdatedEvent",
    "WorkflowCompletedEvent",
    "WorkflowFailedEvent",
    "WorkflowPausedEvent",
    "WorkflowResumedEvent",
    "WorkflowCancelledEvent",
    # Domain Services
    "AgentMatchingService",
    "WorkAssignmentService",
    "AssignmentResult",
    "WorkflowValidationService",
    "ExecutionContextBuilder",
    # User & Authentication
    "User",
    "UserRole",
    "Permission",
    "ROLE_PERMISSIONS",
    "APIKey",
    "AuthContext",
    # Repair Cycle Types
    "RepairTestType",
    "RepairTestRunConfig",
    "RepairTestFailure",
    "RepairTestWarning",
    "RepairTestResult",
    "CycleResult",
    "RepairCycleResult",
    "RepairCycleAgentConfig",
    "EnvironmentRepairConfig",
    "RepairCycleStageConfig",
    "RebuildResult",
    "VerificationResult",
    # Conversational Session
    "ConversationalSessionState",
]
