import logging
from typing import Any

from codetoreum.application.workflow_orchestrator import (
    IDecisionEvents,
    IProjectsAPI,
    IWorkflowStateManager,
    WorkflowState,
)

logger = logging.getLogger(__name__)


class ProductionWorkflowStateManager(IWorkflowStateManager):
    """MVP in-memory workflow state manager."""

    def __init__(self):
        self._states: dict[str, WorkflowState] = {}

    async def get_workflow_state(self, issue_id: str) -> WorkflowState:
        if issue_id not in self._states:
            self._states[issue_id] = WorkflowState(in_progress_tasks={}, current_column=None, current_agent=None)
        return self._states[issue_id]

    async def update_workflow_state(self, issue_id: str, state: WorkflowState) -> None:
        self._states[issue_id] = state
        logger.debug(f"Workflow state updated for {issue_id}")

    async def get_item_position(self, work_item_id: str) -> dict[str, Any] | None:
        for issue_id, state in self._states.items():
            if issue_id == work_item_id:
                return {"column": state.current_column, "agent": state.current_agent}
        return None


class ProductionDecisionEvents(IDecisionEvents):
    """MVP decision events tracker."""

    def __init__(self):
        self.routing_decisions: list[Any] = []
        self.progression_decisions: list[Any] = []

    async def emit_routing_decision(self, decision: Any) -> None:
        self.routing_decisions.append(decision)
        logger.debug(f"Routing decision recorded: {getattr(decision, 'id', decision)}")

    async def emit_progression_decision(self, decision: Any) -> None:
        self.progression_decisions.append(decision)
        logger.debug(f"Progression decision recorded: {getattr(decision, 'id', decision)}")


class ProductionProjectsAPI(IProjectsAPI):
    """MVP GitHub Projects card operations."""

    def __init__(self):
        self.card_movements: list[dict[str, Any]] = []
        self.labels_added: list[dict[str, Any]] = []

    async def move_card_to_column(self, project: str, issue_number: int, column_name: str) -> None:
        movement = {
            "project": project,
            "issue_number": issue_number,
            "column_name": column_name,
            "timestamp": None,
        }
        self.card_movements.append(movement)
        logger.debug(f"Card movement recorded: issue #{issue_number} -> {column_name}")

    async def add_label(self, project: str, issue_number: int, label: str) -> None:
        label_op = {"project": project, "issue_number": issue_number, "label": label}
        self.labels_added.append(label_op)
        logger.debug(f"Label added: issue #{issue_number} <- {label}")
