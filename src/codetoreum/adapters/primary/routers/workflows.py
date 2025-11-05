"""
Workflows REST API Router

Provides RESTful CRUD endpoints for workflow definitions with versioning,
validation, and lifecycle management.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.config import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    DEFAULT_OFFSET,
    VERSIONS_DEFAULT_LIMIT,
    VERSIONS_MAX_LIMIT,
)
from codetoreum.adapters.primary.workflow_dtos import (
    CreateWorkflowRequest,
    UpdateWorkflowRequest,
    WorkflowResponse,
    WorkflowListResponse,
    WorkflowCommandResult,
    WorkflowVersionListResponse,
    WorkflowValidationResponse,
)
from codetoreum.adapters.primary.workflow_mappers import WorkflowMapper
from codetoreum.ports.input.workflow_definition_command import (
    IWorkflowDefinitionCommandPort,
    DeleteWorkflowDefinitionCommand,
)
from codetoreum.ports.input.workflow_query import (
    IWorkflowQueryPort,
    WorkflowFilters,
    WorkflowPaginationParams,
    WorkflowSortField,
    SortOrder,
)


def create_workflows_router(
    definition_command_port: IWorkflowDefinitionCommandPort,
    query_port: IWorkflowQueryPort,
    auth_deps: Optional[SimpleAuthDependencies] = None,
) -> APIRouter:
    """
    Create the workflows REST API router.

    Args:
        definition_command_port: Workflow definition command input port
        query_port: Workflow query input port
        auth_deps: Optional authentication dependencies

    Returns:
        Configured APIRouter for workflows
    """
    # Create router with authentication dependency if provided
    router_kwargs = {
        "prefix": "/api/v2/workflows",
        "tags": ["workflows"],
    }
    if auth_deps:
        router_kwargs["dependencies"] = [Depends(auth_deps.require_auth)]

    router = APIRouter(**router_kwargs)

    # ========================================================================
    # Create Workflow Definition
    # ========================================================================

    @router.post(
        "",
        response_model=WorkflowResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Create a new workflow definition",
        response_description="Created workflow definition",
    )
    async def create_workflow(request: CreateWorkflowRequest) -> WorkflowResponse:
        """
        Create a new workflow definition.

        **Request Body:**
        - name: Workflow name (required, max 200 characters)
        - description: Workflow description (required)
        - project_id: Project ID (required)
        - stages: List of workflow stages (required, at least 1)
        - transitions: Stage transitions (optional)
        - work_item_types: Applicable work item types (optional)
        - is_template: Whether this is a reusable template (default: false)
        - metadata: Additional metadata (optional)

        **Returns:**
        - 201 Created: Workflow created successfully with version 1
        - 400 Bad Request: Invalid request parameters, circular dependencies, or invalid agent references
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Project not found

        **Validation:**
        - Checks for circular dependencies in stage transitions
        - Validates that referenced agents exist
        - Ensures stage names are unique within workflow
        """
        try:
            # Convert DTO to command
            command = WorkflowMapper.to_create_command(request)

            # Execute command via port
            result = await definition_command_port.create_workflow_definition(command)

            if not result.success:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": result.message,
                        "errors": result.errors,
                    },
                )

            # Retrieve created workflow
            workflow_info = await query_port.get_workflow(result.workflow_id)

            # Convert to response DTO
            return WorkflowMapper.to_response(workflow_info)

        except ValueError as e:
            # Invalid enum values or validation errors
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request: {str(e)}",
            )
        except Exception as e:
            # Domain errors (circular dependencies, agent not found, etc.)
            error_msg = str(e).lower()
            if "not found" in error_msg:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=str(e),
                )
            elif "circular" in error_msg:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Circular dependency detected: {str(e)}",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    # ========================================================================
    # List Workflow Definitions
    # ========================================================================

    @router.get(
        "",
        response_model=WorkflowListResponse,
        summary="List workflow definitions with filtering and pagination",
        response_description="List of workflow definitions",
    )
    async def list_workflows(
        project_id: Optional[str] = Query(None, description="Filter by project ID"),
        is_template: Optional[bool] = Query(None, description="Filter by template status"),
        is_active: Optional[bool] = Query(None, description="Filter by active status"),
        work_item_type: Optional[str] = Query(None, description="Filter by applicable work item type"),
        name_contains: Optional[str] = Query(None, description="Filter by partial name match"),
        offset: int = Query(DEFAULT_OFFSET, ge=0, description="Offset for pagination"),
        limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description=f"Limit for pagination (max {MAX_PAGE_SIZE})"),
        sort_by: str = Query("updated_at", description="Sort field (name, created_at, updated_at, version)"),
        sort_order: str = Query("desc", description="Sort order (asc, desc)"),
    ) -> WorkflowListResponse:
        """
        List workflow definitions with optional filtering and pagination.

        **Query Parameters:**
        - project_id: Filter by project ID
        - is_template: Filter by template status (true/false)
        - is_active: Filter by active status (true/false)
        - work_item_type: Filter by applicable work item type
        - name_contains: Partial name match
        - offset: Pagination offset (default: 0)
        - limit: Pagination limit (default: 20, max: 100)
        - sort_by: Sort field (name, created_at, updated_at, version)
        - sort_order: Sort order (asc, desc)

        **Returns:**
        - 200 OK: List of workflows with pagination metadata
        - 400 Bad Request: Invalid filter parameters
        - 401 Unauthorized: Authentication required

        **Examples:**
        - List all workflows: `GET /api/v2/workflows`
        - Filter by project: `GET /api/v2/workflows?project_id=proj-123`
        - Filter active workflows: `GET /api/v2/workflows?is_active=true`
        - Templates only: `GET /api/v2/workflows?is_template=true`
        """
        try:
            # Parse filters
            filters = WorkflowFilters(
                project_id=project_id,
                is_template=is_template,
                is_active=is_active,
                work_item_type=work_item_type,
                name_contains=name_contains,
            )

            # Parse pagination
            try:
                sort_field = WorkflowSortField(sort_by.lower())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid sort field: {sort_by}",
                )

            try:
                sort_order_enum = SortOrder(sort_order.lower())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid sort order: {sort_order}",
                )

            pagination = WorkflowPaginationParams(
                offset=offset,
                limit=limit,
                sort_by=sort_field,
                sort_order=sort_order_enum,
            )

            # Execute query via port
            result = await query_port.list_workflows(filters, pagination)

            # Convert to response DTO
            return WorkflowMapper.to_list_response(result)

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    # ========================================================================
    # Get Workflow Definition
    # ========================================================================

    @router.get(
        "/{workflow_id}",
        response_model=WorkflowResponse,
        summary="Get workflow definition details",
        response_description="Workflow definition including stages and transitions",
    )
    async def get_workflow(
        workflow_id: str,
        version: Optional[int] = Query(None, description="Specific version to retrieve (defaults to latest)")
    ) -> WorkflowResponse:
        """
        Get detailed information about a specific workflow definition.

        **Parameters:**
        - workflow_id: Workflow ID

        **Query Parameters:**
        - version: Specific version to retrieve (optional, defaults to latest)

        **Returns:**
        - 200 OK: Workflow definition with all stages and transitions
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Workflow or version not found

        **Response includes:**
        - All workflow metadata
        - Complete stage definitions with entry conditions
        - Stage transitions
        - Version information
        """
        try:
            # Get workflow definition
            workflow_info = await query_port.get_workflow(workflow_id, version)

            # Convert to response DTO
            return WorkflowMapper.to_response(workflow_info)

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow not found: {str(e)}",
            )

    # ========================================================================
    # Update Workflow Definition
    # ========================================================================

    @router.put(
        "/{workflow_id}",
        response_model=WorkflowResponse,
        summary="Update workflow definition",
        response_description="Updated workflow definition with new version number",
    )
    async def update_workflow(
        workflow_id: str,
        request: UpdateWorkflowRequest,
    ) -> WorkflowResponse:
        """
        Update an existing workflow definition.

        This creates a new version while preserving the history.

        **Parameters:**
        - workflow_id: Workflow ID

        **Request Body:**
        - name: Updated name (optional)
        - description: Updated description (optional)
        - stages: Updated stages (optional)
        - transitions: Updated transitions (optional)
        - work_item_types: Updated work item types (optional)
        - metadata: Updated metadata (optional)

        **Returns:**
        - 200 OK: Workflow updated successfully, new version created
        - 400 Bad Request: Invalid request parameters or validation errors
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Workflow not found

        **Note:**
        - Only provided fields will be updated
        - Creates new version (increments version number)
        - Previous versions remain accessible
        - Validates for circular dependencies
        - Emits domain event for audit trail
        """
        try:
            # Convert DTO to command
            command = WorkflowMapper.to_update_command(workflow_id, request)

            # Execute command via port
            result = await definition_command_port.update_workflow_definition(command)

            if not result.success:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": result.message,
                        "errors": result.errors,
                    },
                )

            # Retrieve updated workflow
            workflow_info = await query_port.get_workflow(workflow_id)

            # Convert to response DTO
            return WorkflowMapper.to_response(workflow_info)

        except ValueError as e:
            # Invalid enum values or validation errors
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request: {str(e)}",
            )
        except Exception as e:
            # Domain errors
            error_msg = str(e).lower()
            if "not found" in error_msg:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=str(e),
                )
            elif "circular" in error_msg:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Circular dependency detected: {str(e)}",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    # ========================================================================
    # Delete Workflow Definition
    # ========================================================================

    @router.delete(
        "/{workflow_id}",
        response_model=WorkflowCommandResult,
        summary="Delete workflow definition",
        response_description="Deletion result",
    )
    async def delete_workflow(
        workflow_id: str,
        force: bool = Query(False, description="Force delete even if active executions exist")
    ) -> WorkflowCommandResult:
        """
        Delete a workflow definition (soft delete).

        **Parameters:**
        - workflow_id: Workflow ID

        **Query Parameters:**
        - force: Force deletion even if active executions exist (default: false)

        **Returns:**
        - 200 OK: Workflow deleted successfully (204 No Content)
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Workflow not found
        - 409 Conflict: Active executions exist and force=false

        **Note:**
        - This is a soft delete - workflow is marked as deleted but history preserved
        - By default, deletion fails if active executions exist
        - Use force=true to delete regardless (active executions continue with last version)
        - Deleted workflows do not appear in list queries
        """
        try:
            # Check for active executions if not forcing
            if not force:
                active_count = await query_port.count_active_executions(workflow_id)
                if active_count > 0:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Cannot delete workflow: {active_count} active execution(s) exist. Use force=true to delete anyway.",
                    )

            # Execute command via port
            command = DeleteWorkflowDefinitionCommand(
                workflow_id=workflow_id,
                force=force,
            )
            result = await definition_command_port.delete_workflow_definition(command)

            if not result.success:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": result.message,
                        "errors": result.errors,
                    },
                )

            # Convert to response DTO
            return WorkflowMapper.to_command_result(result)

        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except Exception as e:
            # Domain errors
            if "not found" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=str(e),
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    # ========================================================================
    # Get Workflow Version History
    # ========================================================================

    @router.get(
        "/{workflow_id}/versions",
        response_model=WorkflowVersionListResponse,
        summary="Get workflow version history",
        response_description="List of workflow versions",
    )
    async def get_workflow_versions(
        workflow_id: str,
        limit: int = Query(VERSIONS_DEFAULT_LIMIT, ge=1, le=VERSIONS_MAX_LIMIT, description=f"Maximum number of versions to return (max {VERSIONS_MAX_LIMIT})")
    ) -> WorkflowVersionListResponse:
        """
        Get version history for a workflow.

        **Parameters:**
        - workflow_id: Workflow ID

        **Query Parameters:**
        - limit: Maximum number of versions (default: 10, max: 100)

        **Returns:**
        - 200 OK: List of versions with metadata
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Workflow not found

        **Response includes:**
        - Version number
        - Creation timestamp
        - Creator (if available)
        - Changes summary
        """
        try:
            # Get version history
            history = await query_port.get_workflow_versions(workflow_id, limit)

            # Convert to response DTO
            return WorkflowMapper.to_version_list_response(history)

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow not found: {str(e)}",
            )

    # ========================================================================
    # Validate Workflow Definition
    # ========================================================================

    @router.get(
        "/{workflow_id}/validate",
        response_model=WorkflowValidationResponse,
        summary="Validate workflow definition",
        response_description="Validation result with errors and warnings",
    )
    async def validate_workflow(
        workflow_id: str,
        version: Optional[int] = Query(None, description="Specific version to validate (defaults to latest)")
    ) -> WorkflowValidationResponse:
        """
        Validate a workflow definition.

        Checks for:
        - Circular stage dependencies
        - Invalid agent references
        - Entry condition validity
        - Transition consistency

        **Parameters:**
        - workflow_id: Workflow ID

        **Query Parameters:**
        - version: Specific version to validate (optional, defaults to latest)

        **Returns:**
        - 200 OK: Validation result
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Workflow or version not found

        **Response includes:**
        - is_valid: Whether workflow passed validation
        - errors: List of validation errors (blocking)
        - warnings: List of warnings (non-blocking)
        """
        try:
            # Validate workflow
            validation = await query_port.validate_workflow(workflow_id, version)

            # Convert to response DTO
            return WorkflowMapper.to_validation_response(validation)

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow not found: {str(e)}",
            )

    return router
