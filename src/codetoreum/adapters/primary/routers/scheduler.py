"""
Scheduler REST API Router

Provides RESTful endpoints for viewing and managing the execution queue and
scheduler status.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.adapters.primary.orchestration_dtos import ExecutionQueueResponse
from codetoreum.adapters.primary.workflow_mappers import OrchestrationMapper
from codetoreum.ports.input.task_query import ITaskQueryPort, ExecutionStatus


def create_scheduler_router(
    task_query_port: ITaskQueryPort,
    auth_deps: Optional[SimpleAuthDependencies] = None,
) -> APIRouter:
    """
    Create the scheduler REST API router.

    Args:
        task_query_port: Task query input port
        auth_deps: Optional authentication dependencies

    Returns:
        Configured APIRouter for scheduler
    """
    # Create router with authentication dependency if provided
    router_kwargs = {
        "prefix": "/api/v2/scheduler",
        "tags": ["scheduler"],
    }
    if auth_deps:
        router_kwargs["dependencies"] = [Depends(auth_deps.require_auth)]

    router = APIRouter(**router_kwargs)

    # ========================================================================
    # Get Execution Queue
    # ========================================================================

    @router.get(
        "/queue",
        response_model=ExecutionQueueResponse,
        summary="Get execution queue and scheduling status",
        response_description="List of queued and running executions",
    )
    async def get_execution_queue(
        status_filter: Optional[str] = Query(
            None,
            alias="status",
            description="Filter by status (queued, running, pending)"
        ),
        workflow_run_id: Optional[str] = Query(None, description="Filter by workflow run ID"),
        work_item_id: Optional[str] = Query(None, description="Filter by work item ID"),
        project_name: Optional[str] = Query(None, description="Filter by project name"),
        page: int = Query(1, ge=1, description="Page number (1-indexed)"),
        page_size: int = Query(50, ge=1, le=100, description="Items per page (max 100)"),
    ) -> ExecutionQueueResponse:
        """
        Get the current execution queue and scheduling status.

        Returns list of queued and running agent executions with work item details,
        plus queue statistics.

        **Query Parameters:**
        - status: Filter by execution status (queued, running, pending)
        - workflow_run_id: Filter by workflow run ID
        - work_item_id: Filter by work item ID
        - project_name: Filter by project name
        - page: Page number (default: 1)
        - page_size: Items per page (default: 50, max: 100)

        **Returns:**
        - 200 OK: List of executions with queue statistics
        - 400 Bad Request: Invalid filter parameters
        - 401 Unauthorized: Authentication required

        **Response includes:**
        - executions: List of queued/running executions
        - queue_stats: Statistics about queue (total_queued, total_running, by_priority)
        - pagination: Page metadata

        **Queue Statistics:**
        - total_queued: Number of executions waiting to run
        - total_running: Number of currently running executions
        - critical_priority: Count of critical priority items
        - high_priority: Count of high priority items
        - medium_priority: Count of medium priority items
        - low_priority: Count of low priority items

        **Examples:**
        - All queued/running: `GET /api/v2/scheduler/queue`
        - Only queued: `GET /api/v2/scheduler/queue?status=pending`
        - Only running: `GET /api/v2/scheduler/queue?status=running`
        - By workflow: `GET /api/v2/scheduler/queue?workflow_run_id=wr-123`
        - By work item: `GET /api/v2/scheduler/queue?work_item_id=wi-456`
        """
        try:
            # Parse status filter
            status_enum = None
            if status_filter:
                try:
                    status_enum = ExecutionStatus(status_filter.lower())
                except ValueError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid status filter: {status_filter}. Must be one of: queued, running, pending, completed, failed, cancelled, paused",
                    )

            # Query executions via port
            execution_list = await task_query_port.list_executions(
                workflow_run_id=workflow_run_id,
                work_item_id=work_item_id,
                project_name=project_name,
                status=status_enum,
                page=page,
                page_size=page_size,
            )

            # Calculate queue statistics
            # In a real implementation, this would be a separate query or cached metric
            # For now, we'll derive it from the execution list
            queue_stats = {
                "total_queued": sum(
                    1 for exec in execution_list.executions
                    if exec.status == ExecutionStatus.PENDING
                ),
                "total_running": sum(
                    1 for exec in execution_list.executions
                    if exec.status == ExecutionStatus.RUNNING
                ),
                # Priority counts would need to be added to execution data
                "critical_priority": 0,
                "high_priority": 0,
                "medium_priority": 0,
                "low_priority": 0,
            }

            # Convert to response DTO
            return OrchestrationMapper.to_queue_response(execution_list, queue_stats)

        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    # ========================================================================
    # Get Queue Statistics
    # ========================================================================

    @router.get(
        "/queue/stats",
        summary="Get detailed queue statistics",
        response_description="Queue statistics",
    )
    async def get_queue_statistics():
        """
        Get detailed statistics about the execution queue.

        Returns aggregate metrics about queue depth, processing times,
        and priority distribution.

        **Returns:**
        - 200 OK: Queue statistics
        - 401 Unauthorized: Authentication required

        **Response includes:**
        - total_queued: Number of executions waiting
        - total_running: Number of currently running executions
        - by_priority: Breakdown by priority level
        - by_project: Breakdown by project
        - average_wait_time_seconds: Average time in queue
        - oldest_queued_at: Timestamp of oldest queued item

        **Example Response:**
        ```json
        {
          "total_queued": 15,
          "total_running": 3,
          "by_priority": {
            "CRITICAL": 2,
            "HIGH": 5,
            "MEDIUM": 7,
            "LOW": 1
          },
          "by_project": {
            "proj-123": 8,
            "proj-456": 7
          },
          "average_wait_time_seconds": 45,
          "oldest_queued_at": "2025-11-03T10:00:00Z"
        }
        ```
        """
        try:
            # In a real implementation, this would query a metrics service
            # or cached aggregates. For now, return a placeholder.

            # Query all pending and running executions
            pending_list = await task_query_port.list_executions(
                status=ExecutionStatus.PENDING,
                page=1,
                page_size=1000,  # Get all pending
            )

            running_list = await task_query_port.list_executions(
                status=ExecutionStatus.RUNNING,
                page=1,
                page_size=1000,  # Get all running
            )

            stats = {
                "total_queued": pending_list.total_count,
                "total_running": running_list.total_count,
                "by_priority": {
                    "CRITICAL": 0,
                    "HIGH": 0,
                    "MEDIUM": 0,
                    "LOW": 0,
                },
                "by_project": {},
                "average_wait_time_seconds": 0,
                "oldest_queued_at": None,
            }

            # Find oldest queued item
            if pending_list.executions:
                oldest = min(
                    pending_list.executions,
                    key=lambda e: e.started_at if e.started_at else "9999-12-31"
                )
                stats["oldest_queued_at"] = oldest.started_at.isoformat() if oldest.started_at else None

            return stats

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    return router
