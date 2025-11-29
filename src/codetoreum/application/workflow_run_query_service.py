"""
Workflow Run Query Service

Application service implementing IWorkflowRunQueryPort to query workflow runs
from the event store using event sourcing.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from codetoreum.domain.events import DomainEvent, WorkflowCreated
from codetoreum.domain.workflow import Workflow, WorkflowStatus
from codetoreum.ports.exceptions import ResourceNotFoundError
from codetoreum.ports.input.workflow_run_query import (
    IWorkflowRunQueryPort,
    SortOrder,
    WorkflowRunFilters,
    WorkflowRunInfo,
    WorkflowRunListResult,
    WorkflowRunPaginationParams,
    WorkflowRunStageInfo,
    WorkflowRunStatus,
    WorkflowRunSummary,
)
from codetoreum.ports.output.event_store import IEventStore
from codetoreum.ports.output.ticket_system import ITicketSystem

logger = logging.getLogger(__name__)


class WorkflowRunQueryService(IWorkflowRunQueryPort):
    """
    Query service for workflow runs using event sourcing.

    Reconstructs workflow run state from domain events stored in the event store.
    Provides filtering, sorting, and pagination capabilities for workflow run queries.

    **Architecture**:
    - Queries event store for workflow events (aggregate_type="Workflow")
    - Reconstructs Workflow aggregates using Workflow.from_events()
    - Enriches with work item metadata from ticket system
    - Transforms domain models to query port data structures

    **Performance**:
    - Uses event store indexes for efficient queries
    - Supports pagination to handle large result sets
    - Caches work item metadata to reduce external API calls

    **Resilience**:
    - This service should be wrapped with resilience decorators at instantiation
    - Gracefully handles missing work items (returns partial data)
    - Logs errors and continues processing other results
    """

    def __init__(
        self,
        event_store: IEventStore,
        ticket_system: Optional[ITicketSystem] = None,
    ):
        """
        Initialize workflow run query service.

        Args:
            event_store: Event store for querying workflow events
            ticket_system: Optional ticket system for enriching with work item data
        """
        self.event_store = event_store
        self.ticket_system = ticket_system
        self._work_item_cache: Dict[str, Dict] = {}  # Simple in-memory cache

    async def get_workflow_run(self, workflow_run_id: str) -> WorkflowRunInfo:
        """
        Retrieve a specific workflow run by ID.

        Args:
            workflow_run_id: Unique identifier for the workflow run

        Returns:
            Complete workflow run information

        Raises:
            ResourceNotFoundError: If workflow run doesn't exist
        """
        logger.debug(f"Getting workflow run: {workflow_run_id}")

        # Get all events for this workflow run
        events = await self.event_store.get_events(stream_id=workflow_run_id)

        if not events:
            raise ResourceNotFoundError("WorkflowRun", workflow_run_id)

        # Reconstruct workflow from events
        workflow = Workflow.from_events(events)

        # Enrich with work item metadata
        work_item_metadata = await self._get_work_item_metadata(workflow.work_item_id)

        # Convert to WorkflowRunInfo
        return self._to_workflow_run_info(workflow, work_item_metadata)

    async def list_workflow_runs(
        self,
        filters: Optional[WorkflowRunFilters] = None,
        pagination: Optional[WorkflowRunPaginationParams] = None,
    ) -> WorkflowRunListResult:
        """
        List workflow runs matching the specified criteria.

        Args:
            filters: Optional filters to apply
            pagination: Pagination parameters

        Returns:
            Paginated list of workflow run summaries
        """
        logger.debug(f"Listing workflow runs with filters: {filters}, pagination: {pagination}")

        # Set defaults
        if pagination is None:
            pagination = WorkflowRunPaginationParams()

        # Get all workflow stream IDs
        stream_ids = await self.event_store.get_all_stream_ids(aggregate_type="Workflow")

        logger.debug(f"Found {len(stream_ids)} workflow streams")

        # Reconstruct workflows and apply filters
        matching_workflows: List[Workflow] = []

        for stream_id in stream_ids:
            try:
                events = await self.event_store.get_events(stream_id=stream_id)
                if not events:
                    continue

                workflow = Workflow.from_events(events)

                # Apply filters
                if self._matches_filters(workflow, filters):
                    matching_workflows.append(workflow)

            except Exception as e:
                logger.warning(f"Error reconstructing workflow {stream_id}: {e}")
                continue

        logger.debug(f"Found {len(matching_workflows)} matching workflows after filtering")

        # Sort workflows
        sorted_workflows = self._sort_workflows(matching_workflows, pagination)

        # Apply pagination
        total_count = len(sorted_workflows)
        paginated_workflows = sorted_workflows[
            pagination.offset : pagination.offset + pagination.limit
        ]

        # Convert to summaries with metadata enrichment
        summaries: List[WorkflowRunSummary] = []
        for workflow in paginated_workflows:
            work_item_metadata = await self._get_work_item_metadata(workflow.work_item_id)
            summary = self._to_workflow_run_summary(workflow, work_item_metadata)
            summaries.append(summary)

        # Calculate pagination metadata
        has_next = (pagination.offset + pagination.limit) < total_count

        return WorkflowRunListResult(
            runs=summaries,
            total_count=total_count,
            offset=pagination.offset,
            limit=pagination.limit,
            has_next=has_next,
        )

    async def get_workflow_run_events(
        self,
        workflow_run_id: str,
        offset: int = 0,
        limit: int = 50,
        event_types: Optional[List[str]] = None,
        since: Optional[datetime] = None,
    ) -> dict:
        """
        Retrieve events for a specific workflow run.

        Args:
            workflow_run_id: Unique identifier for the workflow run
            offset: Pagination offset
            limit: Pagination limit (default 50, max 200)
            event_types: Optional filter by event types
            since: Optional timestamp - events after this time

        Returns:
            Dictionary containing events list and pagination info

        Raises:
            ResourceNotFoundError: If workflow run doesn't exist
        """
        logger.debug(
            f"Getting events for workflow run: {workflow_run_id}, "
            f"offset={offset}, limit={limit}, event_types={event_types}, since={since}"
        )

        # Verify workflow exists
        if not await self.event_store.stream_exists(workflow_run_id):
            raise ResourceNotFoundError("WorkflowRun", workflow_run_id)

        # Get events from event store
        if since:
            all_events = await self.event_store.get_events_since(
                since=since,
                stream_id=workflow_run_id,
            )
        else:
            all_events = await self.event_store.get_events(stream_id=workflow_run_id)

        # Filter by event types if specified
        if event_types:
            filtered_events = [
                event for event in all_events if event.event_type in event_types
            ]
        else:
            filtered_events = all_events

        # Apply pagination
        total_count = len(filtered_events)
        paginated_events = filtered_events[offset : offset + limit]

        # Convert events to dict format
        events_data = [self._event_to_dict(event) for event in paginated_events]

        return {
            "events": events_data,
            "total_count": total_count,
            "offset": offset,
            "limit": limit,
            "has_next": (offset + limit) < total_count,
        }

    # Private helper methods

    def _matches_filters(
        self, workflow: Workflow, filters: Optional[WorkflowRunFilters]
    ) -> bool:
        """
        Check if workflow matches the specified filters.

        Args:
            workflow: Workflow to check
            filters: Filters to apply

        Returns:
            True if workflow matches all filters
        """
        if filters is None:
            return True

        # Status filter
        if filters.status:
            workflow_status = self._map_workflow_status(workflow.status)
            if workflow_status not in filters.status:
                return False

        # Project filter
        if filters.project_id and workflow.project_id != filters.project_id:
            return False

        # Work item filter
        if filters.work_item_id and workflow.work_item_id != filters.work_item_id:
            return False

        # Workflow template filter
        if filters.workflow_id and workflow.template_id != filters.workflow_id:
            return False

        return True

    def _sort_workflows(
        self,
        workflows: List[Workflow],
        pagination: WorkflowRunPaginationParams,
    ) -> List[Workflow]:
        """
        Sort workflows according to pagination parameters.

        Args:
            workflows: List of workflows to sort
            pagination: Pagination parameters with sort criteria

        Returns:
            Sorted list of workflows
        """
        reverse = pagination.sort_order == SortOrder.DESC

        if pagination.sort_by.value == "startedAt":
            return sorted(
                workflows,
                key=lambda w: w.started_at or datetime.min,
                reverse=reverse,
            )
        elif pagination.sort_by.value == "completedAt":
            return sorted(
                workflows,
                key=lambda w: w.completed_at or datetime.min,
                reverse=reverse,
            )
        elif pagination.sort_by.value == "duration":
            return sorted(
                workflows,
                key=lambda w: w.get_duration_seconds() or 0,
                reverse=reverse,
            )
        else:
            # Default to startedAt
            return sorted(
                workflows,
                key=lambda w: w.started_at or datetime.min,
                reverse=reverse,
            )

    async def _get_work_item_metadata(self, work_item_id: str) -> Dict:
        """
        Get work item metadata with caching.

        Args:
            work_item_id: Work item ID

        Returns:
            Dictionary with work item metadata (title, number, project, etc.)
        """
        # Check cache
        if work_item_id in self._work_item_cache:
            return self._work_item_cache[work_item_id]

        # Default metadata
        metadata = {
            "issue_title": None,
            "issue_number": None,
            "project": None,
            "triggered_by": None,
            "priority": None,
        }

        # Fetch from ticket system if available
        if self.ticket_system:
            try:
                work_item = await self.ticket_system.get_work_item(work_item_id)
                metadata = {
                    "issue_title": work_item.title,
                    "issue_number": work_item.external_id,
                    "project": work_item.project_id,
                    "triggered_by": getattr(work_item, 'assignee', None) or work_item.assigned_agent_id,
                    "priority": work_item.priority.name if work_item.priority else None,
                }
            except Exception as e:
                logger.warning(
                    f"Failed to fetch work item metadata for {work_item_id}: {e}"
                )

        # Cache the result
        self._work_item_cache[work_item_id] = metadata

        return metadata

    def _to_workflow_run_info(
        self, workflow: Workflow, work_item_metadata: Dict
    ) -> WorkflowRunInfo:
        """
        Convert Workflow domain model to WorkflowRunInfo.

        Args:
            workflow: Workflow domain model
            work_item_metadata: Work item metadata dict

        Returns:
            WorkflowRunInfo data structure
        """
        # Extract stage information
        stages: List[WorkflowRunStageInfo] = []
        for stage in workflow.stages:
            stage_info = WorkflowRunStageInfo(
                name=stage.name,
                agent_name=stage.agent_name,
                status=stage.status.value,
                started_at=stage.started_at,
                completed_at=stage.completed_at,
                execution_id=stage.execution_id,
            )
            stages.append(stage_info)

        # Get current stage name
        current_stage_name = None
        if workflow.current_stage_index < len(workflow.stages):
            current_stage_name = workflow.stages[workflow.current_stage_index].name

        return WorkflowRunInfo(
            id=workflow.id,
            work_item_id=workflow.work_item_id,
            workflow_id=workflow.template_id,
            project_id=workflow.project_id,
            status=self._map_workflow_status(workflow.status),
            current_stage_index=workflow.current_stage_index,
            current_stage_name=current_stage_name,
            stages=stages,
            started_at=workflow.started_at,
            completed_at=workflow.completed_at,
            duration=workflow.get_duration_seconds(),
            issue_title=work_item_metadata.get("issue_title"),
            issue_number=work_item_metadata.get("issue_number"),
            project=work_item_metadata.get("project") or workflow.project_id,
            triggered_by=work_item_metadata.get("triggered_by"),
            priority=work_item_metadata.get("priority"),
            metadata=workflow.metadata,
        )

    def _to_workflow_run_summary(
        self, workflow: Workflow, work_item_metadata: Dict
    ) -> WorkflowRunSummary:
        """
        Convert Workflow domain model to WorkflowRunSummary.

        Args:
            workflow: Workflow domain model
            work_item_metadata: Work item metadata dict

        Returns:
            WorkflowRunSummary data structure
        """
        # Get current stage name
        current_stage_name = None
        if workflow.current_stage_index < len(workflow.stages):
            current_stage_name = workflow.stages[workflow.current_stage_index].name

        return WorkflowRunSummary(
            id=workflow.id,
            work_item_id=workflow.work_item_id,
            workflow_id=workflow.template_id,
            project_id=workflow.project_id,
            status=self._map_workflow_status(workflow.status),
            current_stage_index=workflow.current_stage_index,
            current_stage_name=current_stage_name,
            started_at=workflow.started_at,
            completed_at=workflow.completed_at,
            duration=workflow.get_duration_seconds(),
            issue_title=work_item_metadata.get("issue_title"),
            issue_number=work_item_metadata.get("issue_number"),
            project=work_item_metadata.get("project") or workflow.project_id,
            triggered_by=work_item_metadata.get("triggered_by"),
            priority=work_item_metadata.get("priority"),
        )

    def _map_workflow_status(self, status: WorkflowStatus) -> WorkflowRunStatus:
        """
        Map domain WorkflowStatus to query port WorkflowRunStatus.

        Args:
            status: Domain workflow status

        Returns:
            Query port workflow run status
        """
        mapping = {
            WorkflowStatus.PENDING: WorkflowRunStatus.PENDING,
            WorkflowStatus.RUNNING: WorkflowRunStatus.RUNNING,
            WorkflowStatus.COMPLETED: WorkflowRunStatus.COMPLETED,
            WorkflowStatus.FAILED: WorkflowRunStatus.FAILED,
            WorkflowStatus.CANCELLED: WorkflowRunStatus.CANCELLED,
        }
        return mapping[status]

    def _event_to_dict(self, event: DomainEvent) -> dict:
        """
        Convert domain event to dictionary format for API response.

        Args:
            event: Domain event

        Returns:
            Dictionary with event data
        """
        return {
            "id": str(event.event_id),
            "event_type": event.event_type,
            "aggregate_id": event.aggregate_id,
            "aggregate_type": event.aggregate_type,
            "timestamp": event.occurred_at.isoformat(),
            "data": event.payload,
            "correlation_id": event.correlation_id,
            "causation_id": event.causation_id,
            "user_id": event.user_id,
            "metadata": event.metadata,
        }
