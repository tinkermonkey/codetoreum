"""Domain layer - Pure business logic with no external dependencies."""

from codetoreum.domain.agent import Agent, AgentCapability, AgentType
from codetoreum.domain.agent_execution import AgentExecution, ExecutionStatus
from codetoreum.domain.events import (
    AgentAssigned,
    AgentCapabilityAdded,
    AgentCapabilityRemoved,
    AgentCapabilityUpdated,
    AgentConstraintsUpdated,
    AgentCreated,
    AgentMaxRetriesUpdated,
    AgentMcpServerAdded,
    AgentMcpServerRemoved,
    AgentModelUpdated,
    AgentTimeoutUpdated,
    DomainEvent,
    ExecutionCompleted,
    ExecutionFailed,
    ExecutionInitialized,
    ExecutionStarted,
    ExecutionTimeout,
    WorkflowAttached,
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
from codetoreum.domain.exceptions import DomainError
from codetoreum.domain.pipeline_stage import PipelineStage, StageStatus, StageType
from codetoreum.domain.project_context import (
    ProjectContext,
    ProjectContextCreated,
    ProjectDockerConfigUpdated,
    ProjectTestConfigUpdated,
    ProjectWorkflowMappingAdded,
)
from codetoreum.domain.review_cycle import (
    ReviewCycle,
    ReviewCycleApproved,
    ReviewCycleCreated,
    ReviewCycleEscalated,
    ReviewDecision,
    ReviewFeedback,
    ReviewFeedbackSubmitted,
    ReviewIteration,
    ReviewIterationStarted,
    ReviewStatus,
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
    "DomainEvent",
    "DomainError",
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
    # Project Context
    "ProjectContext",
    "ProjectContextCreated",
    "ProjectDockerConfigUpdated",
    "ProjectTestConfigUpdated",
    "ProjectWorkflowMappingAdded",
    # Workspace Context
    "WorkspaceContext",
    "WorkspaceType",
    # Review Cycle
    "ReviewCycle",
    "ReviewStatus",
    "ReviewDecision",
    "ReviewFeedback",
    "ReviewIteration",
    "ReviewCycleCreated",
    "ReviewIterationStarted",
    "ReviewFeedbackSubmitted",
    "ReviewCycleApproved",
    "ReviewCycleEscalated",
    # Work Item Events
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
    # Agent Events
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
    # Execution Events
    "ExecutionInitialized",
    "ExecutionStarted",
    "ExecutionCompleted",
    "ExecutionFailed",
    "ExecutionTimeout",
    # Workflow Events
    "WorkflowCreated",
    "WorkflowStarted",
    "WorkflowStageAdvanced",
    "WorkflowStageStatusUpdated",
    "WorkflowCompleted",
    "WorkflowFailed",
    "WorkflowPaused",
    "WorkflowResumed",
    "WorkflowCancelled",
]
