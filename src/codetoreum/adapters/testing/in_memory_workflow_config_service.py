"""In-memory workflow configuration service for testing and simulation."""

from codetoreum.domain.board_workflow_template import BoardWorkflowTemplate
from codetoreum.ports.exceptions import ValidationError
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService


class InMemoryWorkflowConfigService(IWorkflowConfigService):
    """In-memory implementation of IWorkflowConfigService for testing and simulation.

    Templates are stored in a plain dict keyed by board_id.  All four port
    methods are implemented so that this adapter satisfies the full contract
    and production code can be written against the interface without mocks.

    Attributes:
        _templates: board_id -> BoardWorkflowTemplate
    """

    def __init__(self) -> None:
        """Initialize the in-memory configuration service."""
        self._templates: dict[str, BoardWorkflowTemplate] = {}

    # ── Port interface ────────────────────────────────────────────────────────

    async def get_board_workflow_template(self, board_id: str) -> BoardWorkflowTemplate | None:
        """Return the template for *board_id*, or None if unconfigured."""
        return self._templates.get(board_id)

    async def save_board_workflow_template(self, template: BoardWorkflowTemplate) -> None:
        """Persist (or overwrite) the template, keyed by template.board_id.

        Args:
            template: Fully-populated BoardWorkflowTemplate with non-empty
                board_id and project_id.

        Raises:
            ValidationError: If template.board_id or template.project_id is empty.
        """
        if not template.board_id or not template.board_id.strip():
            msg = "template.board_id cannot be empty"
            raise ValidationError(msg)
        if not template.project_id or not template.project_id.strip():
            msg = "template.project_id cannot be empty"
            raise ValidationError(msg)
        self._templates[template.board_id] = template

    async def list_board_workflow_templates(self, project_id: str) -> list[BoardWorkflowTemplate]:
        """Return all templates whose project_id matches, sorted by board_id.

        Args:
            project_id: Project to filter by.

        Raises:
            ValidationError: If project_id is empty.
        """
        if not project_id or not project_id.strip():
            msg = "project_id cannot be empty"
            raise ValidationError(msg)
        return sorted(
            (t for t in self._templates.values() if t.project_id == project_id),
            key=lambda t: t.board_id,
        )

    async def delete_board_workflow_template(self, board_id: str) -> None:
        """Remove the template for *board_id*.  No-op if absent (idempotent)."""
        self._templates.pop(board_id, None)

    # ── Test / simulation helpers ─────────────────────────────────────────────

    def register_template(self, board_id: str, template: BoardWorkflowTemplate) -> None:
        """Synchronous test helper — stores template under *board_id*.

        Prefer ``save_board_workflow_template`` in application code; use this
        only in test fixtures where ``await`` is not available.

        Args:
            board_id: Key to store the template under.
            template: Workflow template to store.
        """
        self._templates[board_id] = template

    def clear(self) -> None:
        """Remove all templates.  Useful between tests to ensure isolation."""
        self._templates.clear()
