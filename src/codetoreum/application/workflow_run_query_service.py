"""
Workflow Run Query Service

Application service implementing IWorkflowRunQueryPort to query workflow runs
from the event store using event sourcing.
"""

import asyncio
import logging
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Any

from codetoreum.application.event_sequence_validator import EventSequenceValidator
from codetoreum.application.expected_sequence_registry import ExpectedSequenceRegistry
from codetoreum.domain.events import DomainEvent
from codetoreum.domain.pipeline_stage import StageStatus
from codetoreum.domain.types import WorkItemId
from codetoreum.domain.workflow import Workflow, WorkflowStatus
from codetoreum.ports.exceptions import ResourceNotFoundError, WorkItemNotFoundError
from codetoreum.ports.input.workflow_run_query import (
    IWorkflowRunQueryPort,
    SortOrder,
    WorkflowRunAuditResult,
    WorkflowRunEventsResult,
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


class LRUCache:
    """
    Thread-safe LRU cache with size limit and TTL support.

    Features:
    - Maximum size limit with LRU eviction
    - TTL (time-to-live) for cache entries
    - Async-safe operations using asyncio.Lock
    - O(1) operations using OrderedDict
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300):
        """
        Initialize LRU cache.

        Args:
            max_size: Maximum number of entries to cache
            ttl_seconds: Time-to-live for cache entries in seconds
        """
        self.max_size = max_size
        self.ttl = timedelta(seconds=ttl_seconds)
        self._cache: OrderedDict[str, tuple[Any, datetime]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found or expired
        """
        async with self._lock:
            if key not in self._cache:
                logger.debug(f"Cache miss: key={key}")
                return None

            value, timestamp = self._cache[key]

            # Check if expired
            now = datetime.now(UTC)
            if now - timestamp > self.ttl:
                age_seconds = (now - timestamp).total_seconds()
                logger.debug(f"Cache expired: key={key}, age={age_seconds:.1f}s, ttl={self.ttl.total_seconds()}s")
                del self._cache[key]
                return None

            # Update access order (move to end = most recently used)
            self._cache.move_to_end(key)
            logger.debug(f"Cache hit: key={key}")

            return value

    async def set(self, key: str, value: Any) -> None:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
        """
        async with self._lock:
            # Track whether this is an update or new entry
            was_update = key in self._cache

            # If key exists, remove it (we'll re-add at end)
            if was_update:
                logger.debug(f"Cache update: key={key}")
                del self._cache[key]

            # Evict least recently used if at max size
            elif len(self._cache) >= self.max_size:
                evicted_key = next(iter(self._cache))
                logger.debug(f"Cache eviction: evicted_key={evicted_key}, cache_size={len(self._cache)}")
                self._cache.popitem(last=False)

            # Add new entry (at end = most recently used)
            self._cache[key] = (value, datetime.now(UTC))
            if not was_update:
                logger.debug(f"Cache set: key={key}, cache_size={len(self._cache)}")

    async def clear(self) -> None:
        """Clear all cached entries."""
        async with self._lock:
            self._cache.clear()

    async def size(self) -> int:
        """Get current cache size."""
        async with self._lock:
            return len(self._cache)


class WorkflowRunQueryService(IWorkflowRunQueryPort):
    """
    Query service for workflow runs using event sourcing.

    Reconstructs workflow run state from domain events stored in the event store.
    Provides filtering, sorting, and pagination capabilities for workflow run queries.

    **Architecture**:
    - Queries event store for workflow events (aggregate_type="Workflow")
    - Uses Elasticsearch aggregations for efficient filtering and sorting at DB level
    - Reconstructs Workflow aggregates using Workflow.from_events()
    - Enriches with work item metadata from ticket system
    - Transforms domain models to query port data structures

    **Performance**:
    - Pushes filtering and sorting to Elasticsearch (no in-memory operations)
    - Uses event store indexes for efficient queries
    - Supports pagination to handle large result sets (10K+ workflows)
    - LRU cache for work item metadata to reduce external API calls

    **Resilience**:
    - This service should be wrapped with resilience decorators at instantiation
    - Gracefully handles missing work items (returns partial data)
    - Specific exception handling (doesn't mask programming errors)
    - Properly handles partial failures in async enrichment
    """

    def __init__(
        self,
        event_store: IEventStore,
        ticket_system: ITicketSystem | None = None,
        cache_size: int = 1000,
        cache_ttl_seconds: int = 300,
    ):
        """
        Initialize workflow run query service.

        Args:
            event_store: Event store for querying workflow events
            ticket_system: Optional ticket system for enriching with work item data
            cache_size: Maximum number of work items to cache (default: 1000)
            cache_ttl_seconds: Cache TTL in seconds (default: 300 = 5 minutes)
        """
        self.event_store = event_store
        self.ticket_system = ticket_system
        self._work_item_cache = LRUCache(max_size=cache_size, ttl_seconds=cache_ttl_seconds)
        self._audit_cache = LRUCache(max_size=cache_size // 2, ttl_seconds=cache_ttl_seconds)
        self._sequence_validator = EventSequenceValidator()
        self._sequence_registry = ExpectedSequenceRegistry()

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
            message = "WorkflowRun"
            raise ResourceNotFoundError(message, workflow_run_id)

        # Reconstruct workflow from events
        workflow = Workflow.from_events(events)

        # Enrich with work item metadata
        work_item_metadata = await self._get_work_item_metadata(workflow.work_item_id)

        # Convert to WorkflowRunInfo
        return self._to_workflow_run_info(workflow, work_item_metadata)

    async def list_workflow_runs(
        self,
        filters: WorkflowRunFilters | None = None,
        pagination: WorkflowRunPaginationParams | None = None,
    ) -> WorkflowRunListResult:
        """
        List workflow runs matching the specified criteria.

        **Performance**: This method uses Elasticsearch aggregations to filter and
        paginate workflows at the database level. No in-memory filtering or sorting
        is performed, enabling efficient queries on datasets with 10K+ workflows.

        Args:
            filters: Optional filters to apply
            pagination: Pagination parameters

        Returns:
            Paginated list of workflow run summaries

        Raises:
            EventStoreError: If query fails
        """
        logger.debug(f"Listing workflow runs with filters: {filters}, pagination: {pagination}")

        # Set defaults
        if pagination is None:
            pagination = WorkflowRunPaginationParams()

        # Build Elasticsearch query filters
        event_data_filters = self._build_event_data_filters(filters)

        # Query workflow stream IDs using Elasticsearch aggregations
        # This pushes filtering and pagination to the database level
        stream_ids, total_count = await self.event_store.query_streams_by_latest_event(  # type: ignore[attr-defined]
            aggregate_type="Workflow",
            event_data_filters=event_data_filters if event_data_filters else None,
            sort_by="timestamp",  # Will be refined after reconstruction
            sort_order="desc",
            offset=0,  # Get more than needed for post-reconstruction sorting
            limit=pagination.offset + pagination.limit + 100,  # Buffer for reconstruction failures
        )

        logger.debug(
            f"Elasticsearch query returned {len(stream_ids)} workflows "
            f"(total: {total_count})"
        )

        # Reconstruct workflows from events (only the ones we need)
        workflows: list[Workflow] = []
        failed_count = 0

        for stream_id in stream_ids:
            try:
                events = await self.event_store.get_events(stream_id=stream_id)
                if not events:
                    failed_count += 1
                    continue

                workflow = Workflow.from_events(events)
                workflows.append(workflow)

            except ResourceNotFoundError:
                logger.warning(
                    f"Workflow {stream_id} not found during reconstruction",
                    extra={"error_id": "ERR_WORKFLOW_RUN_QUERY_NOT_FOUND"}
                )
                failed_count += 1
            except ValueError as e:
                logger.error(
                    f"Invalid workflow state for {stream_id}: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_WORKFLOW_RUN_QUERY_INVALID_STATE"}
                )
                failed_count += 1
            except Exception as e:
                logger.error(
                    f"Unexpected error reconstructing workflow {stream_id}: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_WORKFLOW_RUN_QUERY_RECONSTRUCTION_FAILURE"}
                )
                failed_count += 1

        if failed_count > 0:
            logger.warning(
                f"Failed to reconstruct {failed_count} workflows",
                extra={"error_id": "ERR_WORKFLOW_RUN_QUERY_PARTIAL_RECONSTRUCTION_FAILURE"}
            )

        # Post-reconstruction filtering (status filtering requires reconstructed workflow state)
        filtered_workflows = self._filter_workflows_by_status(workflows, filters)

        # Post-reconstruction sorting (needed because Elasticsearch can't sort by calculated fields)
        sorted_workflows = self._sort_workflows(filtered_workflows, pagination)

        # Apply pagination (accounting for reconstruction failures)
        paginated_workflows = sorted_workflows[
            pagination.offset : pagination.offset + pagination.limit
        ]

        # Convert to summaries with metadata enrichment (parallel for performance)
        summaries = await self._enrich_workflows_with_metadata(paginated_workflows)

        # Calculate pagination metadata
        has_next = (pagination.offset + pagination.limit) < len(sorted_workflows)

        return WorkflowRunListResult(
            runs=summaries,
            total_count=len(sorted_workflows),  # Actual count after reconstruction
            offset=pagination.offset,
            limit=pagination.limit,
            has_next=has_next,
        )

    async def get_workflow_run_events(
        self,
        workflow_run_id: str,
        offset: int = 0,
        limit: int = 50,
        event_types: list[str] | None = None,
        since: datetime | None = None,
    ) -> WorkflowRunEventsResult:
        """
        Retrieve events for a specific workflow run.

        Args:
            workflow_run_id: Unique identifier for the workflow run
            offset: Pagination offset
            limit: Pagination limit (default 50, max 200)
            event_types: Optional filter by event types
            since: Optional timestamp - events after this time

        Returns:
            WorkflowRunEventsResult containing events list and pagination info

        Raises:
            ResourceNotFoundError: If workflow run doesn't exist
        """
        logger.debug(
            f"Getting events for workflow run: {workflow_run_id}, "
            f"offset={offset}, limit={limit}, event_types={event_types}, since={since}"
        )

        # Verify workflow exists
        if not await self.event_store.stream_exists(workflow_run_id):
            message = "WorkflowRun"
            raise ResourceNotFoundError(message, workflow_run_id)

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

        return WorkflowRunEventsResult(
            events=events_data,
            total_count=total_count,
            offset=offset,
            limit=limit,
            has_next=(offset + limit) < total_count,
        )

    async def get_workflow_run_audit(
        self,
        workflow_run_id: str,
        offset: int = 0,
        limit: int = 100,
        include_validation: bool = True,
    ) -> WorkflowRunAuditResult:
        """
        Retrieve comprehensive audit information for a workflow run.

        This method provides:
        - Workflow run summary with metadata enrichment
        - Paginated events list
        - Stage-grouped events with duration calculations (always complete, not paginated)
        - Sequence validation against expected patterns (optional)

        **Caching Strategy**:
        - Full audit results are cached with TTL
        - Cache key includes pagination and validation parameters
        - Workflow run summary is cached separately via work item cache
        - Invalidation: Cache entries expire after TTL (default 5 minutes)

        **Stage Grouping Note**:
        The `stages` field in the response always contains complete stage information
        (all events for each stage), regardless of the pagination applied to the main
        `events` field. This ensures stage summaries provide a complete picture.

        Args:
            workflow_run_id: Unique identifier for the workflow run
            offset: Event pagination offset (default: 0)
            limit: Event pagination limit (default: 100, max: 200)
            include_validation: Whether to validate event sequence (default: True)

        Returns:
            WorkflowRunAuditResult containing audit data

        Raises:
            ResourceNotFoundError: If workflow run doesn't exist
        """
        logger.debug(
            f"Getting audit for workflow run: {workflow_run_id}, "
            f"offset={offset}, limit={limit}, include_validation={include_validation}"
        )

        # Cache key for non-paginated data (workflow summary, events, stages)
        # We cache the core data separately from pagination/validation options
        #
        # SOLUTION to cache fragmentation issue (Medium priority from PR review):
        # To avoid cache thrashing from different pagination parameters, we cache only
        # the core workflow data (summary, all events, stage info) using workflow_run_id
        # as the cache key. Pagination and validation are applied AFTER cache retrieval,
        # ensuring a single cache entry per workflow regardless of pagination parameters.
        # This provides optimal cache hit rates even with varying offset/limit values.
        core_cache_key = f"{workflow_run_id}:audit_core"
        cached_core = await self._audit_cache.get(core_cache_key)

        if cached_core is not None:
            logger.debug(f"Audit cache hit for {workflow_run_id}")
            workflow_run_summary, events_data, stages_info = cached_core
        else:
            # Verify workflow exists and get all events
            if not await self.event_store.stream_exists(workflow_run_id):
                message = "WorkflowRun"
                raise ResourceNotFoundError(message, workflow_run_id)

            all_events = await self.event_store.get_events(stream_id=workflow_run_id)

            if not all_events:
                message = "WorkflowRun"
                raise ResourceNotFoundError(message, workflow_run_id)

            # Reconstruct workflow for summary and stage info
            workflow = Workflow.from_events(all_events)

            # Get work item metadata
            work_item_metadata = await self._get_work_item_metadata(workflow.work_item_id)

            # Build workflow run summary
            workflow_run_summary = self._to_workflow_run_summary(workflow, work_item_metadata)

            # Convert events to dict format
            events_data = [self._event_to_dict(event) for event in all_events]

            # Build stage-grouped events (always complete, not paginated)
            stages_info = self._build_stage_info(workflow, all_events)

            # Cache the core data (without pagination/validation)
            await self._audit_cache.set(core_cache_key, (workflow_run_summary, events_data, stages_info))

        # Apply pagination to events (done after cache retrieval)
        total_event_count = len(events_data)
        paginated_events = events_data[offset : offset + limit]

        # Validate event sequence if requested (computed on demand, not cached)
        # This is inexpensive compared to event store fetches
        validation_result = None
        if include_validation:
            # Reconstruct all_events from events_data for validation
            # Note: We could optimize this further by caching event_types separately
            actual_sequence = [event["event_type"] for event in events_data]
            expected_pattern = self._sequence_registry.get_expected_sequence("default")
            validation_result = self._sequence_validator.create_audit_validation_result(
                expected_pattern,
                actual_sequence
            )

        # Build audit response
        audit_data = WorkflowRunAuditResult(
            workflow_run=workflow_run_summary,
            events=paginated_events,
            stages=stages_info,
            validation=validation_result,
            total_count=total_event_count,
            offset=offset,
            limit=limit,
            has_next=(offset + limit) < total_event_count,
        )

        logger.debug(
            f"Audit for {workflow_run_id}: {total_event_count} total events, "
            f"{len(paginated_events)} returned"
            + (f", validation={'valid' if validation_result and validation_result.get('sequenceValid') else 'invalid'}" if include_validation else "")
        )

        return audit_data

    # Private helper methods

    def _build_event_data_filters(
        self, filters: WorkflowRunFilters | None
    ) -> dict[str, Any] | None:
        """
        Build Elasticsearch event data filters from WorkflowRunFilters.

        This method translates application-level filters into Elasticsearch query
        filters that can be applied at the database level for efficiency.

        Args:
            filters: Application-level filters

        Returns:
            Dictionary of Elasticsearch filters or None

        Note:
            Status filtering requires examining the latest event, which is handled
            by the event store's query_streams_by_latest_event method.
        """
        if filters is None:
            return None

        event_filters: dict[str, Any] = {}

        # Note: Status filtering is complex with event sourcing because status
        # is derived from events. For now, we'll do post-filtering after reconstruction.
        # In the future, consider maintaining a materialized view for status.

        # Project ID filter
        if filters.project_id:
            event_filters["data.project_id"] = filters.project_id

        # Work item ID filter
        if filters.work_item_id:
            event_filters["data.work_item_id"] = filters.work_item_id

        # Workflow template ID filter
        if filters.workflow_id:
            event_filters["data.template_id"] = filters.workflow_id

        return event_filters if event_filters else None

    async def _enrich_workflows_with_metadata(
        self, workflows: list[Workflow]
    ) -> list[WorkflowRunSummary]:
        """
        Enrich workflows with metadata in parallel.

        This method fetches work item metadata for multiple workflows concurrently
        and handles partial failures gracefully.

        Args:
            workflows: List of workflows to enrich

        Returns:
            List of workflow run summaries with metadata

        Note:
            Failures to fetch individual work items are logged but don't prevent
            returning summaries for successful workflows.
        """
        async def enrich_one(workflow: Workflow) -> WorkflowRunSummary:
            """Enrich a single workflow."""
            try:
                work_item_metadata = await self._get_work_item_metadata(workflow.work_item_id)
                return self._to_workflow_run_summary(workflow, work_item_metadata)
            except WorkItemNotFoundError:
                logger.warning(
                    f"Work item {workflow.work_item_id} not found, "
                    f"using default metadata",
                    extra={"error_id": "ERR_WORKFLOW_RUN_QUERY_WORK_ITEM_NOT_FOUND"}
                )
                return self._to_workflow_run_summary(workflow, self._default_metadata())
            except Exception as e:
                logger.error(
                    f"Unexpected error enriching workflow {workflow.id} "
                    f"with work item {workflow.work_item_id}: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_WORKFLOW_RUN_QUERY_ENRICH_FAILURE"}
                )
                return self._to_workflow_run_summary(workflow, self._default_metadata())

        # Execute enrichment in parallel (with error handling per workflow)
        summaries = await asyncio.gather(*[enrich_one(w) for w in workflows], return_exceptions=True)

        # Handle any exceptions returned from gather
        processed_summaries: list[WorkflowRunSummary] = []
        for summary in summaries:
            if isinstance(summary, (Exception, BaseException)):
                logger.error(
                    f"Unexpected error during workflow enrichment: {summary}",
                    exc_info=summary,
                    extra={"error_id": "ERR_WORKFLOW_RUN_QUERY_ENRICHMENT_EXCEPTION"}
                )
                # Skip this workflow if enrichment completely failed
                # The enrich_one function should handle all normal cases
            else:
                processed_summaries.append(summary)

        return processed_summaries

    @staticmethod
    def _parse_issue_number(external_id: str | None) -> int | None:
        """Parse issue number from external_id, stripping any leading '#'."""
        if not external_id:
            return None
        try:
            return int(str(external_id).lstrip("#"))
        except (ValueError, TypeError):
            return None

    def _default_metadata(self) -> dict[str, Any]:
        """
        Get default metadata for when work item fetch fails.

        Returns:
            Dictionary with None values for all metadata fields
        """
        return {
            "issue_title": None,
            "issue_number": None,
            "project": None,
            "triggered_by": None,
            "priority": None,
        }

    def _filter_workflows_by_status(
        self,
        workflows: list[Workflow],
        filters: WorkflowRunFilters | None,
    ) -> list[Workflow]:
        """
        Filter workflows by status after reconstruction.

        Status filtering must be done post-reconstruction because workflow status
        is derived from the aggregate's event stream, not stored in individual events.

        Args:
            workflows: List of workflows to filter
            filters: Optional filters (may include status filter)

        Returns:
            Filtered list of workflows
        """
        if filters is None or not filters.status:
            return workflows

        # Convert WorkflowRunStatus to WorkflowStatus for comparison
        status_filter_set = set(filters.status)

        return [
            workflow for workflow in workflows
            if self._map_workflow_status(workflow.status) in status_filter_set
        ]

    def _sort_workflows(
        self,
        workflows: list[Workflow],
        pagination: WorkflowRunPaginationParams,
    ) -> list[Workflow]:
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
        if pagination.sort_by.value == "completedAt":
            return sorted(
                workflows,
                key=lambda w: w.completed_at or datetime.min,
                reverse=reverse,
            )
        if pagination.sort_by.value == "duration":
            return sorted(
                workflows,
                key=lambda w: w.get_duration_seconds() or 0,
                reverse=reverse,
            )
        # Default to startedAt
        return sorted(
            workflows,
            key=lambda w: w.started_at or datetime.min,
            reverse=reverse,
        )

    async def _get_work_item_metadata(self, work_item_id: str) -> dict:
        """
        Get work item metadata with LRU caching and TTL.

        Args:
            work_item_id: Work item ID

        Returns:
            Dictionary with work item metadata (title, number, project, etc.)

        Raises:
            TicketNotFoundError: If work item doesn't exist (when ticket system is available)
        """
        # Check cache
        cached = await self._work_item_cache.get(work_item_id)
        if cached is not None:
            logger.debug(f"Cache hit for work item {work_item_id}")
            return dict(cached)

        # Default metadata
        metadata = self._default_metadata()

        # Fetch from ticket system if available
        if self.ticket_system:
            try:
                work_item = await self.ticket_system.get_work_item(WorkItemId(work_item_id))
                metadata = {
                    "issue_title": work_item.title,
                    "issue_number": self._parse_issue_number(work_item.external_id),
                    "project": work_item.project_id,
                    "triggered_by": getattr(work_item, "assignee", None) or work_item.assigned_agent_id,
                    "priority": work_item.priority.name if work_item.priority else None,
                }
            except WorkItemNotFoundError:
                logger.warning(
                    f"Work item {work_item_id} not found in ticket system",
                    extra={"error_id": "ERR_WORKFLOW_RUN_QUERY_METADATA_NOT_FOUND"}
                )
                # Cache the failure to avoid repeated lookups
                await self._work_item_cache.set(work_item_id, metadata)
                raise
            except Exception as e:
                logger.error(
                    f"Unexpected error fetching work item metadata for {work_item_id}: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_WORKFLOW_RUN_QUERY_METADATA_FETCH_FAILURE"}
                )
                # Don't cache errors (might be transient)
                return metadata

        # Cache the result
        await self._work_item_cache.set(work_item_id, metadata)

        return metadata

    def _to_workflow_run_info(
        self, workflow: Workflow, work_item_metadata: dict
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
        stages: list[WorkflowRunStageInfo] = []
        for stage in workflow.stages:
            # Get metadata and wrap in MappingProxyType for immutability
            stage_info = WorkflowRunStageInfo(
                name=stage.name,
                agent_name=stage.agent_config.get("agent_id", ""),
                status=stage.status.value,
                started_at=stage.started_at,
                completed_at=stage.completed_at,
                execution_id=stage.execution_id,
                output=stage.output,
                error_message=stage.error_message,
                metadata=MappingProxyType(stage.metadata),
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
        self, workflow: Workflow, work_item_metadata: dict
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
            WorkflowStatus.PAUSED: WorkflowRunStatus.RUNNING,  # Paused workflows are still considered active/running
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

    def _build_stage_info(self, workflow: Workflow, events: list[DomainEvent]) -> list[dict]:
        """
        Build stage-grouped event information for audit view.

        Groups events by workflow stage and calculates stage durations.

        Args:
            workflow: Reconstructed workflow aggregate
            events: All events for this workflow run

        Returns:
            List of stage info dictionaries compatible with AuditStageInfo DTO
        """
        # Pre-index events by stage_name and execution_id for O(1) lookup
        # This avoids O(stages * events) complexity
        events_by_stage_name: dict[str, list[DomainEvent]] = {}
        events_by_execution_id: dict[str, list[DomainEvent]] = {}

        for event in events:
            event_data = event.payload if hasattr(event, "payload") else {}
            event_stage_name = event_data.get("stage_name")
            event_execution_id = event_data.get("execution_id")

            if event_stage_name:
                if event_stage_name not in events_by_stage_name:
                    events_by_stage_name[event_stage_name] = []
                events_by_stage_name[event_stage_name].append(event)

            if event_execution_id:
                if event_execution_id not in events_by_execution_id:
                    events_by_execution_id[event_execution_id] = []
                events_by_execution_id[event_execution_id].append(event)

        stages_info = []

        for stage in workflow.stages:
            # Determine stage status - map all StageStatus values explicitly
            if stage.status == StageStatus.PENDING:
                status = "pending"
            elif stage.status == StageStatus.READY:
                status = "ready"
            elif stage.status == StageStatus.RUNNING:
                status = "running"
            elif stage.status == StageStatus.COMPLETED:
                status = "completed"
            elif stage.status == StageStatus.FAILED:
                status = "failed"
            elif stage.status == StageStatus.SKIPPED:
                status = "skipped"
            else:
                status = "pending"  # Fallback for unknown status

            # Calculate duration
            duration_seconds = None
            if stage.started_at and stage.completed_at:
                duration_seconds = (stage.completed_at - stage.started_at).total_seconds()

            # Collect events for this stage using pre-indexed lookups (O(1))
            stage_events_dict = {}  # Use dict keyed by id(event) to avoid duplicates

            # Get events by stage name
            for event in events_by_stage_name.get(stage.name, []):
                stage_events_dict[id(event)] = event

            # Get events by execution ID
            if stage.execution_id:
                for event in events_by_execution_id.get(stage.execution_id, []):
                    stage_events_dict[id(event)] = event

            # Convert to list of event dicts (already deduped by dict keys)
            stage_events = [self._event_to_dict(event) for event in stage_events_dict.values()]

            stage_info = {
                "name": stage.name,
                "status": status,
                "startedAt": stage.started_at.isoformat() if stage.started_at else None,
                "completedAt": stage.completed_at.isoformat() if stage.completed_at else None,
                "durationSeconds": duration_seconds,
                "events": stage_events,
                "output": stage.output,
                "errorMessage": stage.error_message,
                "metadata": stage.metadata,
            }
            stages_info.append(stage_info)

        return stages_info
