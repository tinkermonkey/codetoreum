"""Board workflow template REST API endpoints.

Provides CRUD endpoints for managing BoardWorkflowTemplate configurations,
supporting the production pipeline configuration workflow.

Endpoints:
- GET /api/v2/projects/{project_id}/board-workflows - List templates
- GET /api/v2/projects/{project_id}/board-workflows/{board_id} - Get template
- POST /api/v2/projects/{project_id}/board-workflows - Create template
- PUT /api/v2/projects/{project_id}/board-workflows/{board_id} - Update template
- DELETE /api/v2/projects/{project_id}/board-workflows/{board_id} - Delete template
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.domain.board_workflow_template import (
    BoardWorkflowTemplate,
    ColumnTemplate,
    ColumnType,
)
from codetoreum.ports.exceptions import ValidationError
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService

logger = logging.getLogger(__name__)


# ── DTOs ───────────────────────────────────────────────────────────────────


class ColumnTemplateRequest(BaseModel):
    """Request DTO for column template."""

    name: str = Field(..., description="Display name of the column")
    type: str = Field(..., description="Column type: 'manual' or 'automated'")
    agent_id: str | None = Field(None, description="Agent ID to trigger (required for automated)")
    is_pipeline_trigger: bool = Field(False, description="If True, acquiring lock when item enters")
    is_exit_column: bool = Field(False, description="If True, releasing lock when item enters")
    position: int = Field(..., description="Column order (0 = leftmost/first)")
    auto_progress_on_completion: bool = Field(False, description="Auto-move to next column on completion")
    sla_seconds: int | None = Field(None, description="Optional SLA threshold in seconds")
    on_failure_column: str | None = Field(None, description="Column to move item to on failure")
    sla_escalation_column: str | None = Field(None, description="Column to move item to on SLA expiry")
    execution_type: str = Field("task_queue", description="Execution mode: 'task_queue' or 'conversational'")


class BoardWorkflowTemplateRequest(BaseModel):
    """Request DTO for creating/updating a board workflow template."""

    name: str = Field(..., description="Display name for the workflow template")
    columns: list[ColumnTemplateRequest] = Field(..., description="Column configurations")


class ColumnTemplateResponse(BaseModel):
    """Response DTO for column template."""

    name: str
    type: str
    agent_id: str | None
    is_pipeline_trigger: bool
    is_exit_column: bool
    position: int
    auto_progress_on_completion: bool
    sla_seconds: int | None
    on_failure_column: str | None
    sla_escalation_column: str | None
    execution_type: str


class BoardWorkflowTemplateResponse(BaseModel):
    """Response DTO for board workflow template."""

    id: str
    name: str
    board_id: str
    project_id: str
    columns: list[ColumnTemplateResponse]
    created_at: datetime | None
    updated_at: datetime | None


class BoardWorkflowTemplateListResponse(BaseModel):
    """Response DTO for list of board workflow templates."""

    templates: list[BoardWorkflowTemplateResponse]
    total_count: int


def create_board_workflow_router(
    workflow_config_service: IWorkflowConfigService,
    auth_deps: SimpleAuthDependencies | None = None,
) -> APIRouter:
    """Create the board workflow template REST API router.

    Args:
        workflow_config_service: IWorkflowConfigService implementation
        auth_deps: Optional authentication dependencies

    Returns:
        Configured APIRouter for board workflow management
    """
    router = APIRouter(
        prefix="/api/v2/projects",
        tags=["board-workflows"],
    )

    @router.get(
        "/{project_id}/board-workflows",
        response_model=BoardWorkflowTemplateListResponse,
        summary="List board workflow templates for a project",
        response_description="List of board workflow templates",
    )
    async def list_templates(
        project_id: str, _: str = Depends(auth_deps) if auth_deps else None
    ) -> BoardWorkflowTemplateListResponse:
        """List all workflow templates for a project.

        Args:
            project_id: Project identifier

        Returns:
            List of board workflow templates for the project

        Raises:
            400: If project_id is invalid
            500: On internal error
        """
        try:
            templates = await workflow_config_service.list_board_workflow_templates(project_id)

            responses = [
                BoardWorkflowTemplateResponse(
                    id=t.id,
                    name=t.name,
                    board_id=t.board_id,
                    project_id=t.project_id,
                    columns=[
                        ColumnTemplateResponse(
                            name=c.name,
                            type=c.type.value,
                            agent_id=c.agent_id,
                            is_pipeline_trigger=c.is_pipeline_trigger,
                            is_exit_column=c.is_exit_column,
                            position=c.position,
                            auto_progress_on_completion=c.auto_progress_on_completion,
                            sla_seconds=c.sla_seconds,
                            on_failure_column=c.on_failure_column,
                            sla_escalation_column=c.sla_escalation_column,
                            execution_type=c.execution_type,
                        )
                        for c in t.columns
                    ],
                    created_at=t.created_at,
                    updated_at=t.updated_at,
                )
                for t in templates
            ]

            return BoardWorkflowTemplateListResponse(templates=responses, total_count=len(responses))

        except ValidationError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except Exception as e:
            logger.error(f"Failed to list templates for project {project_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list templates: {e!s}",
            )

    @router.get(
        "/{project_id}/board-workflows/{board_id}",
        response_model=BoardWorkflowTemplateResponse,
        summary="Get a board workflow template",
        response_description="Board workflow template",
    )
    async def get_template(
        project_id: str, board_id: str, _: str = Depends(auth_deps) if auth_deps else None
    ) -> BoardWorkflowTemplateResponse:
        """Get a specific board workflow template.

        Args:
            project_id: Project identifier
            board_id: Board identifier

        Returns:
            The board workflow template

        Raises:
            404: If template not found
            500: On internal error
        """
        try:
            template = await workflow_config_service.get_board_workflow_template(board_id)

            if not template:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Template not found for board {board_id}",
                )

            # Verify template belongs to project
            if template.project_id != project_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Template not found for board {board_id}",
                )

            return BoardWorkflowTemplateResponse(
                id=template.id,
                name=template.name,
                board_id=template.board_id,
                project_id=template.project_id,
                columns=[
                    ColumnTemplateResponse(
                        name=c.name,
                        type=c.type.value,
                        agent_id=c.agent_id,
                        is_pipeline_trigger=c.is_pipeline_trigger,
                        is_exit_column=c.is_exit_column,
                        position=c.position,
                        auto_progress_on_completion=c.auto_progress_on_completion,
                        sla_seconds=c.sla_seconds,
                        on_failure_column=c.on_failure_column,
                        sla_escalation_column=c.sla_escalation_column,
                        execution_type=c.execution_type,
                    )
                    for c in template.columns
                ],
                created_at=template.created_at,
                updated_at=template.updated_at,
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get template for board {board_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get template: {e!s}",
            )

    @router.post(
        "/{project_id}/board-workflows",
        response_model=BoardWorkflowTemplateResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Create a new board workflow template",
        response_description="Created board workflow template",
    )
    async def create_template(
        project_id: str,
        request: BoardWorkflowTemplateRequest,
        _: str = Depends(auth_deps) if auth_deps else None,
    ) -> BoardWorkflowTemplateResponse:
        """Create a new board workflow template.

        Args:
            project_id: Project identifier
            request: Template creation request with columns

        Returns:
            The created board workflow template

        Raises:
            400: If request is invalid
            500: On internal error
        """
        try:
            # Convert request columns to domain objects
            columns = []
            for col_req in request.columns:
                col = ColumnTemplate(
                    name=col_req.name,
                    type=ColumnType(col_req.type),
                    agent_id=col_req.agent_id,
                    is_pipeline_trigger=col_req.is_pipeline_trigger,
                    is_exit_column=col_req.is_exit_column,
                    position=col_req.position,
                    auto_progress_on_completion=col_req.auto_progress_on_completion,
                    sla_seconds=col_req.sla_seconds,
                    on_failure_column=col_req.on_failure_column,
                    sla_escalation_column=col_req.sla_escalation_column,
                    execution_type=col_req.execution_type,
                )
                columns.append(col)

            # Use board_id as template ID for now (simplifies keying)
            # In a real system, you might generate a UUID and allow custom board_id mapping
            template_id = f"template-{project_id}-{len(columns)}-cols"

            template = BoardWorkflowTemplate(
                id=template_id,
                name=request.name,
                board_id=project_id,  # For now, use project_id as board_id
                project_id=project_id,
                columns=tuple(columns),
            )

            await workflow_config_service.save_board_workflow_template(template)

            return BoardWorkflowTemplateResponse(
                id=template.id,
                name=template.name,
                board_id=template.board_id,
                project_id=template.project_id,
                columns=[
                    ColumnTemplateResponse(
                        name=c.name,
                        type=c.type.value,
                        agent_id=c.agent_id,
                        is_pipeline_trigger=c.is_pipeline_trigger,
                        is_exit_column=c.is_exit_column,
                        position=c.position,
                        auto_progress_on_completion=c.auto_progress_on_completion,
                        sla_seconds=c.sla_seconds,
                        on_failure_column=c.on_failure_column,
                        sla_escalation_column=c.sla_escalation_column,
                        execution_type=c.execution_type,
                    )
                    for c in template.columns
                ],
                created_at=template.created_at,
                updated_at=template.updated_at,
            )

        except ValidationError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except Exception as e:
            logger.error(f"Failed to create template for project {project_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create template: {e!s}",
            )

    @router.put(
        "/{project_id}/board-workflows/{board_id}",
        response_model=BoardWorkflowTemplateResponse,
        summary="Update a board workflow template",
        response_description="Updated board workflow template",
    )
    async def update_template(
        project_id: str,
        board_id: str,
        request: BoardWorkflowTemplateRequest,
        _: str = Depends(auth_deps) if auth_deps else None,
    ) -> BoardWorkflowTemplateResponse:
        """Update an existing board workflow template.

        Args:
            project_id: Project identifier
            board_id: Board identifier
            request: Template update request with columns

        Returns:
            The updated board workflow template

        Raises:
            404: If template not found
            400: If request is invalid
            500: On internal error
        """
        try:
            # Get existing template
            existing = await workflow_config_service.get_board_workflow_template(board_id)
            if not existing:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Template not found for board {board_id}",
                )

            # Verify template belongs to project
            if existing.project_id != project_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Template not found for board {board_id}",
                )

            # Convert request columns to domain objects
            columns = []
            for col_req in request.columns:
                col = ColumnTemplate(
                    name=col_req.name,
                    type=ColumnType(col_req.type),
                    agent_id=col_req.agent_id,
                    is_pipeline_trigger=col_req.is_pipeline_trigger,
                    is_exit_column=col_req.is_exit_column,
                    position=col_req.position,
                    auto_progress_on_completion=col_req.auto_progress_on_completion,
                    sla_seconds=col_req.sla_seconds,
                    on_failure_column=col_req.on_failure_column,
                    sla_escalation_column=col_req.sla_escalation_column,
                    execution_type=col_req.execution_type,
                )
                columns.append(col)

            # Create updated template
            updated_template = BoardWorkflowTemplate(
                id=existing.id,
                name=request.name,
                board_id=board_id,
                project_id=project_id,
                columns=tuple(columns),
                created_at=existing.created_at,
                updated_at=datetime.now(UTC),
            )

            await workflow_config_service.save_board_workflow_template(updated_template)

            return BoardWorkflowTemplateResponse(
                id=updated_template.id,
                name=updated_template.name,
                board_id=updated_template.board_id,
                project_id=updated_template.project_id,
                columns=[
                    ColumnTemplateResponse(
                        name=c.name,
                        type=c.type.value,
                        agent_id=c.agent_id,
                        is_pipeline_trigger=c.is_pipeline_trigger,
                        is_exit_column=c.is_exit_column,
                        position=c.position,
                        auto_progress_on_completion=c.auto_progress_on_completion,
                        sla_seconds=c.sla_seconds,
                        on_failure_column=c.on_failure_column,
                        sla_escalation_column=c.sla_escalation_column,
                        execution_type=c.execution_type,
                    )
                    for c in updated_template.columns
                ],
                created_at=updated_template.created_at,
                updated_at=updated_template.updated_at,
            )

        except HTTPException:
            raise
        except ValidationError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except Exception as e:
            logger.error(f"Failed to update template for board {board_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update template: {e!s}",
            )

    @router.delete(
        "/{project_id}/board-workflows/{board_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Delete a board workflow template",
    )
    async def delete_template(
        project_id: str, board_id: str, _: str = Depends(auth_deps) if auth_deps else None
    ) -> None:
        """Delete a board workflow template.

        Args:
            project_id: Project identifier
            board_id: Board identifier

        Raises:
            404: If template not found
            500: On internal error
        """
        try:
            # Verify template exists and belongs to project
            existing = await workflow_config_service.get_board_workflow_template(board_id)
            if not existing or existing.project_id != project_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Template not found for board {board_id}",
                )

            await workflow_config_service.delete_board_workflow_template(board_id)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to delete template for board {board_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete template: {e!s}",
            )

    return router
