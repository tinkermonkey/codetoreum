"""Workflow configuration service port interface.

This interface defines the contract for storing and retrieving workflow
configuration — specifically the BoardWorkflowTemplate that maps board columns
to workflow semantics (agent assignments, pipeline-lock triggers, SLA thresholds,
auto-progression, etc.).

Implementations:
    - InMemoryWorkflowConfigService (adapters/testing/) — simulation & tests
    - Future: DatabaseWorkflowConfigService (adapters/secondary/) — production

Data format:
    The unit of configuration is BoardWorkflowTemplate, which is keyed by
    board_id at rest.  Each template carries its own board_id and project_id so
    that it is self-describing when serialised and so that project-scoped listing
    is possible without a separate join.

    See domain/board_workflow_template.py for the full ColumnTemplate schema
    (type, agent_id, is_pipeline_trigger, is_exit_column, sla_seconds, etc.).
"""

from abc import ABC, abstractmethod

from codetoreum.domain.board_workflow_template import BoardWorkflowTemplate


class IWorkflowConfigService(ABC):
    """Port for storing and retrieving board workflow templates.

    Provides the read path used at runtime by BoardColumnEventHandler and the
    write path used by configuration tooling (CLI, admin API, seeder).

    Example — runtime read:
        template = await service.get_board_workflow_template("board-123")
        if template:
            col = template.get_column_config("In Progress")
            if col and col.agent_id:
                # trigger agent execution

    Example — configuration write (seeder or admin API):
        await service.save_board_workflow_template(template)

    Example — project-scoped listing (admin UI):
        templates = await service.list_board_workflow_templates("proj-abc")
    """

    @abstractmethod
    async def get_board_workflow_template(self, board_id: str) -> BoardWorkflowTemplate | None:
        """Get the workflow template for a specific board.

        Args:
            board_id: Board identifier (matches template.board_id)

        Returns:
            BoardWorkflowTemplate if a template has been configured for this
            board, None if the board has no template.

        Raises:
            ExternalServiceError: On backing-store communication failure.
        """

    @abstractmethod
    async def save_board_workflow_template(self, template: BoardWorkflowTemplate) -> None:
        """Persist or overwrite the workflow template for a board.

        Uses template.board_id as the storage key.  If a template already
        exists for that board it is replaced in full — there is no partial
        update; callers must supply the complete template.

        Args:
            template: Fully-populated BoardWorkflowTemplate.  Both
                template.board_id and template.project_id must be non-empty.

        Raises:
            ValidationError: If template.board_id or template.project_id is empty.
            ExternalServiceError: On backing-store communication failure.
        """

    @abstractmethod
    async def list_board_workflow_templates(self, project_id: str) -> list[BoardWorkflowTemplate]:
        """List all workflow templates that belong to a project.

        Args:
            project_id: Project identifier (matches template.project_id)

        Returns:
            List of BoardWorkflowTemplate instances for the project, ordered
            by board_id.  Empty list if the project has no configured boards.

        Raises:
            ValidationError: If project_id is empty.
            ExternalServiceError: On backing-store communication failure.
        """

    @abstractmethod
    async def delete_board_workflow_template(self, board_id: str) -> None:
        """Remove the workflow template for a board.

        No-op if no template exists for board_id (idempotent).

        Args:
            board_id: Board identifier whose template should be deleted.

        Raises:
            ExternalServiceError: On backing-store communication failure.
        """
