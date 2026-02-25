"""
Agent List Endpoints

Provides endpoints for listing and filtering agents.
"""


from fastapi import APIRouter, HTTPException, Query, status

from codetoreum.adapters.primary.agent_dtos import AgentListResponse
from codetoreum.adapters.primary.agent_mappers import AgentMapper
from codetoreum.config import DEFAULT_OFFSET, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from codetoreum.domain.agent import AgentType
from codetoreum.ports.input.agent_query import (
    AgentFilters,
    AgentPaginationParams,
    AgentSortField,
    IAgentQueryPort,
    SortOrder,
)


def register_list_endpoints(router: APIRouter, query_port: IAgentQueryPort) -> None:
    """
    Register agent list endpoints on the given router.

    Args:
        router: APIRouter to register endpoints on
        query_port: Agent query port for data access
    """

    @router.get(
        "",
        response_model=AgentListResponse,
        summary="List agents with filtering and pagination",
        response_description="List of agents in registry",
        responses={
            200: {"description": "List of agents with pagination metadata"},
            400: {"description": "Bad Request - Invalid filter parameters", "content": {"application/json": {"example": {"detail": "Invalid agent type: invalid_type"}}}},
            401: {"description": "Unauthorized - Authentication required", "content": {"application/json": {"example": {"detail": "Not authenticated"}}}},
        },
    )
    async def list_agents(
        capability: str | None = Query(None, description="Filter by capability/skill"),
        agent_type: str | None = Query(None, description="Filter by agent type (maker, reviewer, etc.)"),
        requires_docker: bool | None = Query(None, description="Filter by Docker requirement"),
        makes_code_changes: bool | None = Query(None, description="Filter by code modification capability"),
        offset: int = Query(DEFAULT_OFFSET, ge=0, description="Offset for pagination"),
        limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description=f"Limit for pagination (max {MAX_PAGE_SIZE})"),
        sort_by: str = Query("updated_at", description="Sort field (name, display_name, agent_type, created_at, updated_at)"),
        sort_order: str = Query("desc", description="Sort order (asc, desc)"),
    ) -> AgentListResponse:
        """
        List agents with optional filtering and pagination.

        **Query Parameters:**
        - capability: Filter by capability/skill name
        - agent_type: Filter by agent type (maker, reviewer, specialized, etc.)
        - requires_docker: Filter by Docker requirement
        - makes_code_changes: Filter by code modification capability
        - offset: Pagination offset (default: 0)
        - limit: Pagination limit (default: 20, max: 100)
        - sort_by: Sort field (name, display_name, agent_type, created_at, updated_at)
        - sort_order: Sort order (asc, desc)

        **Returns:**
        - 200 OK: List of agents with pagination metadata
        - 400 Bad Request: Invalid filter parameters
        - 401 Unauthorized: Authentication required

        **Examples:**
        - List all agents: `GET /api/v2/agents`
        - Filter by capability: `GET /api/v2/agents?capability=code_review`
        - Filter by type: `GET /api/v2/agents?agent_type=maker`
        - Combined filters: `GET /api/v2/agents?makes_code_changes=true&requires_docker=true`
        """
        try:
            # Parse filters
            agent_type_enum = None
            if agent_type:
                try:
                    agent_type_enum = AgentType(agent_type.lower())
                except ValueError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid agent type: {agent_type}",
                    )

            filters = AgentFilters(
                capability=capability,
                agent_type=agent_type_enum,
                requires_docker=requires_docker,
                makes_code_changes=makes_code_changes,
            )

            # Parse pagination
            try:
                sort_field = AgentSortField(sort_by.lower())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid sort field: {sort_by}. Must be one of: name, display_name, agent_type, created_at, updated_at",
                )

            try:
                sort_order_enum = SortOrder(sort_order.lower())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid sort order: {sort_order}. Must be asc or desc",
                )

            pagination = AgentPaginationParams(
                offset=offset,
                limit=limit,
                sort_by=sort_field,
                sort_order=sort_order_enum,
            )

            # Execute query via port
            result = await query_port.list_agents(filters, pagination)

            # Convert to response DTO
            response = AgentMapper.to_list_response(result)

            # Calculate page number from offset/limit
            response.page = (offset // limit) + 1 if limit > 0 else 1

            return response

        except HTTPException:
            raise
        except (ValueError, KeyError, AttributeError) as e:
            # Known validation or attribute errors
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to list agents: {e!s}",
            )

    @router.get(
        "/{agent_id}",
        response_model=AgentMapper.to_response.__annotations__["return"],
        summary="Get agent details",
        response_description="Agent details including capabilities and execution statistics",
        responses={
            200: {"description": "Agent details with capabilities and optional stats"},
            401: {"description": "Unauthorized - Authentication required", "content": {"application/json": {"example": {"detail": "Not authenticated"}}}},
            404: {"description": "Not Found - Agent not found", "content": {"application/json": {"example": {"detail": "Agent not found: agent with ID 'agent-123' not found"}}}},
        },
    )
    async def get_agent(
        agent_id: str,
        include_stats: bool = Query(True, description="Include execution statistics"),
    ):
        """
        Get detailed information about a specific agent.

        **Parameters:**
        - agent_id: Agent ID

        **Query Parameters:**
        - include_stats: Include execution statistics (default: true)

        **Returns:**
        - 200 OK: Agent details with capabilities and optional stats
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Agent not found

        **Response includes:**
        - All agent configuration
        - Capabilities with proficiency levels
        - Container configuration
        - Execution statistics (if include_stats=true)
        - Sensitive environment variable values are masked (e.g., `API_KEY: "***"`)

        **Note:** Sensitive fields like API keys or tokens in metadata are automatically masked.
        """
        try:
            # Get agent info
            agent_info = await query_port.get_agent(agent_id, include_stats=include_stats)

            # Convert to response DTO (mapper handles sensitive field masking)
            response = AgentMapper.to_response(agent_info)

            return response

        except (ValueError, KeyError, AttributeError) as e:
            if "not found" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Agent not found: {e!s}",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to get agent: {e!s}",
            )
