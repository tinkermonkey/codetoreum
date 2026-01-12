"""In-memory workflow configuration service for testing and simulation."""

from typing import Dict, Optional

from codetoreum.domain.board_workflow_template import BoardWorkflowTemplate
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService


class InMemoryWorkflowConfigService(IWorkflowConfigService):
    """In-memory implementation of workflow configuration service.

    Stores workflow templates in memory, suitable for testing and simulation
    scenarios. Provides helper methods for test setup and teardown.

    Attributes:
        _templates: Storage mapping board_id -> BoardWorkflowTemplate
    """

    def __init__(self):
        """Initialize the in-memory configuration service."""
        self._templates: Dict[str, BoardWorkflowTemplate] = {}

    async def get_board_workflow_template(
        self, board_id: str
    ) -> Optional[BoardWorkflowTemplate]:
        """Get workflow template for a board.

        Args:
            board_id: Unique identifier of the board

        Returns:
            BoardWorkflowTemplate if configured, None if board has no template
        """
        return self._templates.get(board_id)

    def register_template(
        self, board_id: str, template: BoardWorkflowTemplate
    ) -> None:
        """Register a workflow template for a board (test helper).

        Args:
            board_id: Board identifier to associate with template
            template: Workflow template configuration
        """
        self._templates[board_id] = template

    def clear(self) -> None:
        """Clear all registered templates (test helper).

        Useful for test cleanup to ensure isolation between tests.
        """
        self._templates.clear()
