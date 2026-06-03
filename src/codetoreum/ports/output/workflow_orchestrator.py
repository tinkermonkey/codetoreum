"""Workflow orchestrator port interface.

This interface defines contracts for orchestrating workflows within
a single project, handling card movements, stage transitions, and
agent execution.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codetoreum.application.workflow_orchestrator import (
        CardMovedEvent,
        ReviewCycleCompletedEvent,
        StageCompletedEvent,
        WorkflowResult,
    )


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
    async def handle_card_movement(self, event: "CardMovedEvent") -> "WorkflowResult":
        """Handle card movement from GitHub Projects board.

        Args:
            event: Card movement event with source and target column information.

        Returns:
            WorkflowResult indicating the orchestration action taken.
        """

    @abstractmethod
    async def handle_stage_completion(self, event: "StageCompletedEvent") -> "WorkflowResult":
        """Handle completion of a pipeline stage.

        Args:
            event: Stage completion event with results and context.

        Returns:
            WorkflowResult indicating the next orchestration action.
        """

    @abstractmethod
    async def handle_review_cycle_completion(self, event: "ReviewCycleCompletedEvent") -> "WorkflowResult":
        """Handle review cycle completion.

        Args:
            event: Review cycle completion event with approval status.

        Returns:
            WorkflowResult indicating whether to progress the workflow.
        """

