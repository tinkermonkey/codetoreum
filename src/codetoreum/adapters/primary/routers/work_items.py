"""
Work Items REST API Router

Provides RESTful CRUD endpoints for work items (issues, tasks) with
filtering, pagination, and search capabilities.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.adapters.primary.work_item_dtos import (
    CreateWorkItemRequest,
    UpdateWorkItemRequest,
    WorkItemCommandResult,
    WorkItemDetailResponse,
    WorkItemListResponse,
    WorkItemResponse,
)
from codetoreum.adapters.primary.work_item_mappers import WorkItemMapper
from codetoreum.config import DEFAULT_OFFSET, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from codetoreum.domain.work_item import WorkItemPriority, WorkItemStatus
from codetoreum.infrastructure.security import InvalidInputError, sanitize_search_query
from codetoreum.ports.input.work_item_command import IWorkItemCommandPort
from codetoreum.ports.input.work_item_query import (
    IWorkItemQueryPort,
    SortField,
    SortOrder,
    WorkItemFilters,
    WorkItemSearchParams,
)
from codetoreum.ports.input.work_item_query import (
    PaginationParams as DomainPaginationParams,
)


def create_work_items_router(
    command_port: IWorkItemCommandPort,
    query_port: IWorkItemQueryPort,
    auth_deps: SimpleAuthDependencies | None = None,
) -> APIRouter:
    """
    Create the work items REST API router.

    Args:
        command_port: Work item command input port
        query_port: Work item query input port
        auth_deps: Optional authentication dependencies

    Returns:
        Configured APIRouter for work items
    """
    # Create router with authentication dependency if provided
    router_kwargs = {
        "prefix": "/api/v2/work-items",
        "tags": ["work-items"],
    }
    if auth_deps:
        router_kwargs["dependencies"] = [Depends(auth_deps.require_auth)]

    router = APIRouter(**router_kwargs)

    # ========================================================================
    # Create Work Item
    # ========================================================================

    @router.post(
        "",
        response_model=WorkItemResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Create a new work item",
        response_description="Created work item",
    )
    async def create_work_item(request: CreateWorkItemRequest) -> WorkItemResponse:
        """
        Create a new work item.

        **Request Body:**
        - project_id: Project ID (required)
        - title: Work item title (required, max 500 characters)
        - description: Work item description (required)
        - labels: List of labels/tags (optional)
        - priority: Priority level - LOW, MEDIUM, HIGH, CRITICAL (default: MEDIUM)
        - external_id: External system ID (optional)
        - external_url: External system URL (optional)

        **Returns:**
        - 201 Created: Work item created successfully
        - 400 Bad Request: Invalid request parameters
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Project not found

        **Example:**
        ```json
        {
          "project_id": "proj-123",
          "title": "Implement user authentication",
          "description": "Add JWT-based authentication to the API",
          "labels": ["feature", "security"],
          "priority": "HIGH",
          "external_id": "42",
          "external_url": "https://github.com/org/repo/issues/42"
        }
        ```
        """
        try:
            # Convert DTO to command
            command = WorkItemMapper.to_create_command(request)

            # Execute command via port
            work_item = await command_port.create_work_item(command)

            # Convert domain model to response DTO
            return WorkItemMapper.to_response(work_item)

        except ValueError as e:
            # Invalid enum values or validation errors
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request: {e!s}",
            )
        except Exception as e:
            # Domain errors (project not found, etc.)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    # ========================================================================
    # List Work Items
    # ========================================================================

    @router.get(
        "",
        response_model=WorkItemListResponse,
        summary="List work items with filtering and pagination",
        response_description="List of work items",
    )
    async def list_work_items(
        project_id: str | None = Query(None, description="Filter by project ID"),
        status: str | None = Query(None, description="Filter by status (NEW, ASSIGNED, IN_PROGRESS, etc.)"),
        assignee: str | None = Query(None, description="Filter by assigned agent ID"),
        labels: str | None = Query(None, description="Filter by labels (comma-separated, AND logic)"),
        workflow_stage: str | None = Query(None, description="Filter by workflow stage"),
        priority: str | None = Query(None, description="Filter by priority (LOW, MEDIUM, HIGH, CRITICAL)"),
        search: str | None = Query(None, description="Search in title and description"),
        offset: int = Query(DEFAULT_OFFSET, ge=0, description="Offset for pagination"),
        limit: int = Query(
            DEFAULT_PAGE_SIZE,
            ge=1,
            le=MAX_PAGE_SIZE,
            description=f"Limit for pagination (max {MAX_PAGE_SIZE})",
        ),
        sort_by: str = Query("updated_at", description="Sort field (created_at, updated_at, priority, title, status)"),
        sort_order: str = Query("desc", description="Sort order (asc, desc)"),
    ) -> WorkItemListResponse:
        """
        List work items with optional filtering and pagination.

        **Query Parameters:**
        - project_id: Filter by project ID
        - status: Filter by status (NEW, ASSIGNED, IN_PROGRESS, UNDER_REVIEW, COMPLETED, FAILED, BLOCKED)
        - assignee: Filter by assigned agent ID
        - labels: Comma-separated labels (applies AND logic)
        - workflow_stage: Filter by current workflow stage
        - priority: Filter by priority (LOW, MEDIUM, HIGH, CRITICAL)
        - search: Full-text search in title and description
        - offset: Pagination offset (default: 0)
        - limit: Pagination limit (default: 20, max: 100)
        - sort_by: Sort field (created_at, updated_at, priority, title, status)
        - sort_order: Sort order (asc, desc)

        **Returns:**
        - 200 OK: List of work items with pagination metadata
        - 400 Bad Request: Invalid filter parameters
        - 401 Unauthorized: Authentication required

        **Examples:**
        - List all work items: `GET /api/v2/work-items`
        - Filter by status: `GET /api/v2/work-items?status=in_progress`
        - Filter by multiple criteria: `GET /api/v2/work-items?status=in_progress&priority=HIGH&labels=bug,critical`
        - Search: `GET /api/v2/work-items?search=authentication`
        - Paginate: `GET /api/v2/work-items?offset=20&limit=50`
        """
        try:
            # Sanitize search query to prevent injection attacks
            sanitized_search = None
            if search:
                try:
                    sanitized_search = sanitize_search_query(search, max_length=500)
                except InvalidInputError as e:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid search query: {e!s}",
                    )

            # Validate sort_by field to prevent injection
            valid_sort_fields = ["created_at", "updated_at", "priority", "title", "status"]
            if sort_by.lower() not in valid_sort_fields:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid sort field. Must be one of: {', '.join(valid_sort_fields)}",
                )

            # Validate sort_order to prevent injection
            if sort_order.lower() not in ["asc", "desc"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid sort order. Must be 'asc' or 'desc'",
                )

            # Parse filters
            filters = WorkItemFilters(
                project_id=project_id,
                status=WorkItemStatus(status) if status else None,
                assignee=assignee,
                labels=labels.split(",") if labels else None,
                workflow_stage=workflow_stage,
                priority=WorkItemPriority[priority.upper()] if priority else None,
            )

            # Parse pagination
            pagination = DomainPaginationParams(
                offset=offset,
                limit=limit,
                sort_by=SortField(sort_by.lower()),
                sort_order=SortOrder(sort_order.lower()),
            )

            # Execute query via port
            if sanitized_search:
                # Use search endpoint with sanitized query
                search_params = WorkItemSearchParams(
                    query=sanitized_search,
                    filters=filters,
                    pagination=pagination,
                )
                result = await query_port.search_work_items(search_params)
            else:
                # Use list endpoint
                result = await query_port.list_work_items(filters, pagination)

            # Convert to response DTO
            response = WorkItemMapper.to_list_response(result)

            # Calculate page number from offset/limit
            response.page = (offset // limit) + 1 if limit > 0 else 1

            return response

        except ValueError as e:
            # Invalid enum values
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid filter parameter: {e!s}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    # ========================================================================
    # Get Work Item Details
    # ========================================================================

    @router.get(
        "/{work_item_id}",
        response_model=WorkItemDetailResponse,
        summary="Get work item details",
        response_description="Work item details including history",
    )
    async def get_work_item(work_item_id: str) -> WorkItemDetailResponse:
        """
        Get detailed information about a specific work item.

        **Parameters:**
        - work_item_id: Work item ID

        **Returns:**
        - 200 OK: Work item details with history
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Work item not found

        **Response includes:**
        - All work item fields
        - Current status and stage
        - Assigned agent information
        - Event history count
        - Recent domain events
        """
        try:
            # Get work item
            work_item = await query_port.get_work_item(work_item_id)

            # Get history
            history = await query_port.get_work_item_history(work_item_id, limit=10)

            # Convert to response DTO
            return WorkItemMapper.to_detail_response(work_item, history)

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Work item not found: {e!s}",
            )

    # ========================================================================
    # Update Work Item
    # ========================================================================

    @router.put(
        "/{work_item_id}",
        response_model=WorkItemResponse,
        summary="Update work item",
        response_description="Updated work item",
    )
    async def update_work_item(
        work_item_id: str,
        request: UpdateWorkItemRequest,
    ) -> WorkItemResponse:
        """
        Update an existing work item.

        **Parameters:**
        - work_item_id: Work item ID

        **Request Body:**
        - title: Updated title (optional)
        - description: Updated description (optional)
        - labels: Updated labels (optional)
        - priority: Updated priority - LOW, MEDIUM, HIGH, CRITICAL (optional)

        **Returns:**
        - 200 OK: Work item updated successfully
        - 400 Bad Request: Invalid request parameters
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Work item not found

        **Note:**
        - Only provided fields will be updated
        - Emits domain event for audit trail
        """
        try:
            # Convert DTO to command
            command = WorkItemMapper.to_update_command(work_item_id, request)

            # Execute command via port
            work_item = await command_port.update_work_item(command)

            # Convert domain model to response DTO
            return WorkItemMapper.to_response(work_item)

        except ValueError as e:
            # Invalid enum values or validation errors
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request: {e!s}",
            )
        except Exception as e:
            # Domain errors (work item not found, etc.)
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
    # Delete Work Item
    # ========================================================================

    @router.delete(
        "/{work_item_id}",
        response_model=WorkItemCommandResult,
        summary="Delete work item (soft delete)",
        response_description="Deletion result",
    )
    async def delete_work_item(work_item_id: str) -> WorkItemCommandResult:
        """
        Soft delete a work item.

        **Parameters:**
        - work_item_id: Work item ID

        **Returns:**
        - 200 OK: Work item deleted successfully
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Work item not found

        **Note:**
        - This is a soft delete - the work item is marked as deleted but remains in the event store
        - Work item will not appear in list queries after deletion
        - Event history is preserved for audit trail
        """
        try:
            # Execute command via port
            result = await command_port.delete_work_item(work_item_id)

            # Convert to response DTO
            return WorkItemMapper.to_command_result(result)

        except Exception as e:
            # Domain errors (work item not found, etc.)
            if "not found" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=str(e),
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    return router
