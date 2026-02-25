"""Workflow configuration service port interface.

This interface defines the contract for retrieving workflow configuration
including board workflow templates that define column-based orchestration logic.
"""

from abc import ABC, abstractmethod

from codetoreum.domain.board_workflow_template import BoardWorkflowTemplate


class IWorkflowConfigService(ABC):
    """Port for retrieving workflow configuration.

    Provides access to board workflow templates that define:
    - Column definitions and ordering
    - Pipeline lock trigger points
    - Exit columns for lock release
    - Agent assignments per column
    - Auto-progression behavior

    Example:
        async with service as svc:
            template = await svc.get_board_workflow_template("board-123")
            if template:
                column = template.get_column_config("In Progress")
                if column and column.agent_id:
                    # Trigger agent execution
                    pass
    """

    @abstractmethod
    async def get_board_workflow_template(
        self, board_id: str
    ) -> BoardWorkflowTemplate | None:
        """Get workflow template for a board.

        Args:
            board_id: Board identifier

        Returns:
            BoardWorkflowTemplate if found, None if board has no configured template

        Raises:
            ExternalServiceError: Service communication failure
        """
