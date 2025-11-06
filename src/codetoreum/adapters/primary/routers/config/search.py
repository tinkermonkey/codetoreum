"""
Configuration Search Endpoints

Handles full-text search across all configuration types.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from codetoreum.config import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from codetoreum.adapters.primary.config_dtos import ConfigSearchResponse
from codetoreum.ports.input.config_query import (
    IConfigurationQueryPort,
    PaginationParams,
)


def register_search_endpoints(
    router: APIRouter,
    query_port: IConfigurationQueryPort,
) -> None:
    """Register configuration search endpoints on the router."""

    @router.get(
        "/search",
        response_model=ConfigSearchResponse,
        summary="Search configurations",
        response_description="Configuration search results",
    )
    async def search_configs(
        query: str = Query(..., min_length=1, description="Search query string"),
        config_type: Optional[str] = Query(None, description="Filter by type (project, agent, pipeline)"),
        project_id: Optional[str] = Query(None, description="Filter by project"),
        limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description=f"Maximum results (max {MAX_PAGE_SIZE})"),
    ) -> ConfigSearchResponse:
        """
        Search across all configurations using full-text search.

        Searches across project descriptions, agent names, pipeline definitions, etc.
        Results are ranked by relevance.

        **Query Parameters:**
        - query: Search query string (required)
        - config_type: Optional filter by type (project, agent, pipeline)
        - project_id: Optional filter by project
        - limit: Maximum results to return (default: 20, max: 100)

        **Returns:**
        - 200 OK: Search results with relevance scores
        - 400 Bad Request: Invalid query parameters
        - 401 Unauthorized: Authentication required

        **Examples:**
        - `GET /api/v2/config/search?query=authentication` - Find all configs mentioning auth
        - `GET /api/v2/config/search?query=bug&config_type=workflow` - Find workflows for bugs
        - `GET /api/v2/config/search?query=docker&project_id=proj-123` - Search within project
        """
        try:
            pagination = PaginationParams(offset=0, limit=limit)

            results = await query_port.search_configs(
                query=query,
                config_type=config_type,
                project_id=project_id,
                pagination=pagination,
            )

            return ConfigSearchResponse(
                results=[
                    {
                        "config_id": r.config_id,
                        "config_type": r.config_type,
                        "name": r.name,
                        "description": r.description,
                        "matched_fields": r.matched_fields,
                        "score": r.score,
                    }
                    for r in results.results
                ],
                total_count=results.total_count,
                query=results.query,
                filters=results.filters,
            )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Search failed: {str(e)}",
            )
