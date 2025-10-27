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
from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus

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
]
