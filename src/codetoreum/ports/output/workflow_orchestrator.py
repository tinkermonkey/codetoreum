"""Workflow orchestrator port interface.

This interface defines contracts for orchestrating workflows within
a single project, handling card movements, stage transitions, and
agent execution.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class WorkflowAction(Enum):
    """Possible workflow actions."""

    TASK_QUEUED = "task_queued"
    AUTO_ADVANCE = "auto_advance"
    ESCALATE = "escalate"
    COMPLETE = "complete"
    NO_ACTION = "no_action"


@dataclass
class WorkflowResult:
    """Result of workflow orchestration action."""

    success: bool
    task_id: str | None
    agent_name: str | None
    action: WorkflowAction
    next_column: str | None
    reason: str
    error: str | None = None


@dataclass
class IssueData:
    """Issue information from GitHub."""

    number: int
    title: str
    body: str
    labels: list[str]
    state: str
    created_at: datetime
    updated_at: datetime


@dataclass
class CardMovedRequest:
    """Data passed to the orchestrator when a card moves on GitHub Projects board."""

    project: str
    board: str
    issue_number: int
    from_column: str | None
    to_column: str
    issue_data: IssueData
    timestamp: datetime


@dataclass
class StageCompletedRequest:
    """Data passed to the orchestrator when a pipeline stage completes."""

    project: str
    issue_number: int
    stage_name: str
    agent_name: str
    success: bool
    output: str
    context: dict[str, Any]
    timestamp: datetime


@dataclass
class ReviewCycleCompletedRequest:
    """Data passed to the orchestrator when review cycle completes."""

    project: str
    issue_number: int
    approved: bool
    iteration: int
    maker_agent: str
    reviewer_agent: str
    feedback: str | None
    timestamp: datetime
    context: dict[str, Any]


class IWorkflowOrchestrator(ABC):
    """Output port for orchestrating workflows within a project.

    Coordinates workflow execution for a single project, handling:
    - Card movements on project boards
    - Workflow stage transitions
    - Agent task queuing and execution
    - Review cycles and feedback loops

    Workflow orchestration is triggered by WorkItemColumnChangedEvent and other
    domain events emitted by adapters. The application is fully event-driven;
    polling is handled internally by adapters as a private concern.
    """

    @abstractmethod
    async def handle_card_movement(self, event: CardMovedRequest) -> WorkflowResult:
        """Handle card movement from GitHub Projects board.

        Args:
            event: Card movement request with source and target column information.

        Returns:
            WorkflowResult indicating the orchestration action taken.
        """

    @abstractmethod
    async def handle_stage_completion(self, event: StageCompletedRequest) -> WorkflowResult:
        """Handle completion of a pipeline stage.

        Args:
            event: Stage completion request with results and context.

        Returns:
            WorkflowResult indicating the next orchestration action.
        """

    @abstractmethod
    async def handle_review_cycle_completion(self, event: ReviewCycleCompletedRequest) -> WorkflowResult:
        """Handle review cycle completion.

        Args:
            event: Review cycle completion request with approval status.

        Returns:
            WorkflowResult indicating whether to progress the workflow.
        """

