"""Diagnostics router for system operations and maintenance."""

import logging
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.ports.exceptions import EventStoreError, ResourceNotFoundError, StreamNotFoundError
from codetoreum.ports.output.active_workflow_run_registry import IActiveWorkflowRunRegistry
from codetoreum.ports.output.board_service import BoardConfig, IBoardService, ReconciliationResult
from codetoreum.ports.output.distributed_lock import IDistributedLock
from codetoreum.ports.output.event_store import IEventStore
from codetoreum.ports.output.failed_event_store import IFailedEventStore
from codetoreum.ports.output.orphan_scan_registry import IOrphanScanRegistry
from codetoreum.ports.output.pipeline_queue import IPipelineQueue
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService

logger = logging.getLogger(__name__)


class BoardReconcileRequest(BaseModel):
    """Request to reconcile a board with its configuration."""

    auto_create_missing: bool = True


class BoardReconcileResponse(BaseModel):
    """Response with board reconciliation results."""

    board_id: str
    columns_added: list[str]
    columns_removed: list[str]
    columns_renamed: list[tuple[str, str]]
    orphaned_items: list[str]
    status: str


class ActiveRunInfo(BaseModel):
    """Information about an active workflow run."""

    work_item_id: str
    run_id: str
    stage_name: str
    project_id: str
    board_id: str
    started_at: str


class LockHolderInfo(BaseModel):
    """Information about a lock holder."""

    lock_key: str
    holder_id: str
    acquired_at: datetime
    ttl_seconds: int
    expires_at: datetime
    holder_metadata: dict[str, str] = Field(default_factory=dict)


class QueueEntryInfo(BaseModel):
    """Entry in a pipeline queue."""

    work_item_id: str
    stage_name: str
    board_position: int
    enqueued_at: datetime
    metadata: dict[str, str] = Field(default_factory=dict)


class PipelineQueueState(BaseModel):
    """State of a pipeline queue."""

    queue_key: str
    entries: list[QueueEntryInfo]
    depth: int


class FailedEventStats(BaseModel):
    """Statistics about failed events."""

    total_failed_events: int
    pending_retries: int
    exhausted_retries: int
    total_retries_attempted: int
    total_retries_succeeded: int
    total_retries_failed: int
    oldest_event: datetime | None = None
    newest_event: datetime | None = None
    failure_reasons: dict[str, int] | None = None


class OrphanScanResultInfo(BaseModel):
    """Result of an orphan scan."""

    scan_id: str
    scanned_at: datetime
    locks_scanned: int
    orphaned_locks_found: int
    orphaned_locks_released: int
    errors: list[str] = Field(default_factory=list)


class DiagnosticsStateResponse(BaseModel):
    """Complete diagnostics state snapshot."""

    active_runs: list[ActiveRunInfo] = Field(default_factory=list)
    pipeline_locks: list[LockHolderInfo] = Field(default_factory=list)
    pipeline_queues: list[PipelineQueueState] = Field(default_factory=list)
    failed_event_stats: FailedEventStats | None = None
    last_orphan_scan: OrphanScanResultInfo | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    subsystem_errors: list[str] = Field(
        default_factory=list,
        description="List of subsystems that failed to retrieve data. Presence indicates incomplete response.",
    )


class TriggerStatus(str, Enum):
    """Status of a trigger/event."""

    RECEIVED = "received"
    QUEUED = "queued"
    IN_PROGRESS = "in-progress"
    COMPLETED = "completed"
    FAILED = "failed"


class TriggerLifecycleResponse(BaseModel):
    """Trigger lifecycle information."""

    event_id: str
    received_at: datetime
    status: str = Field(default="received")
    queue_position: int | None = None
    active_run_id: str | None = None
    failure_reason: str | None = None
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))


def create_diagnostics_router(
    board_service: IBoardService | None = None,
    workflow_config: IWorkflowConfigService | None = None,
    active_run_registry: IActiveWorkflowRunRegistry | None = None,
    distributed_lock: IDistributedLock | None = None,
    pipeline_queue: IPipelineQueue | None = None,
    failed_event_store: IFailedEventStore | None = None,
    orphan_scan_registry: IOrphanScanRegistry | None = None,
    event_store: IEventStore | None = None,
    auth_deps: SimpleAuthDependencies | None = None,
) -> APIRouter:
    """Create the diagnostics router.

    Args:
        board_service: Board service for board operations.
        workflow_config: Workflow configuration service.
        active_run_registry: Registry for active workflow runs.
        distributed_lock: Distributed lock service.
        pipeline_queue: Pipeline queue service.
        failed_event_store: Store for failed events.
        orphan_scan_registry: Registry for orphan scan results.
        event_store: Event store for querying events.
        auth_deps: Optional authentication dependencies.

    Returns:
        Configured APIRouter.
    """
    router_kwargs: dict[str, Any] = {
        "prefix": "/api/v2/diagnostics",
        "tags": ["diagnostics"],
    }
    if auth_deps:
        router_kwargs["dependencies"] = [Depends(auth_deps.require_auth)]

    router = APIRouter(**router_kwargs)

    @router.post(
        "/boards/{board_id}/reconcile",
        response_model=BoardReconcileResponse,
        status_code=status.HTTP_200_OK,
        summary="Reconcile board structure with configuration",
        response_description="Results of board reconciliation",
    )
    async def reconcile_board(
        board_id: str,
        request: BoardReconcileRequest,
    ) -> BoardReconcileResponse:
        """
        Reconcile a board's structure with its expected configuration.

        Creates missing columns, reports extra columns, and validates board state.
        This is a maintenance operation that ensures boards stay in sync with
        their workflow configuration.

        **Path Parameters:**
        - board_id: ID of the board to reconcile

        **Request Body:**
        - auto_create_missing: If true, create missing columns. If false, only report. (default: true)

        **Returns:**
        - 200 OK: Reconciliation completed with results
        - 400 Bad Request: Invalid parameters
        - 404 Not Found: Board doesn't exist
        """
        if board_service is None or workflow_config is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Required services not available",
            )

        try:
            # Get the workflow template for the board to find expected columns
            board_config = await workflow_config.get_board_workflow_template(board_id)
            if not board_config:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No workflow configuration found for board {board_id}",
                )

            # Extract column names from the template
            expected_columns = [col.name for col in board_config.columns]

            # Create reconciliation config
            recon_config = BoardConfig(
                board_id=board_id,
                expected_columns=tuple(expected_columns),
                auto_create_missing=request.auto_create_missing,
            )

            # Perform reconciliation
            result: ReconciliationResult = await board_service.reconcile_board(board_id, recon_config)

            return BoardReconcileResponse(
                board_id=result.board_id,
                columns_added=list(result.columns_added),
                columns_removed=list(result.columns_removed),
                columns_renamed=list(result.columns_renamed),
                orphaned_items=list(result.orphaned_items),
                status="success",
            )
        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid parameters: {e!s}",
            ) from e
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Board reconciliation failed: {e!s}",
            ) from e

    @router.get(
        "/state",
        response_model=DiagnosticsStateResponse,
        status_code=status.HTTP_200_OK,
        summary="Get complete system diagnostics state",
        response_description="Current state of all system components",
    )
    async def get_diagnostics_state() -> DiagnosticsStateResponse:
        """
        Get a complete snapshot of the system's current state for diagnostics.

        Returns a comprehensive view of:
        - Active workflow runs (from IActiveWorkflowRunRegistry)
        - Active pipeline locks (from IDistributedLock)
        - Pipeline queue contents (from IPipelineQueue per known key)
        - Failed event statistics (from IFailedEventStore)
        - Last orphan scan results (from IOrphanScanRegistry)

        This endpoint replaces ad-hoc Redis introspection and provides a single
        observability interface for system state during debugging and analysis.

        **Returns:**
        - 200 OK: Diagnostics state snapshot (subsystem_errors field indicates incomplete data)
        """
        try:
            active_runs: list[ActiveRunInfo] = []
            pipeline_locks: list[LockHolderInfo] = []
            pipeline_queues: list[PipelineQueueState] = []
            failed_event_stats: FailedEventStats | None = None
            last_orphan_scan: OrphanScanResultInfo | None = None
            subsystem_errors: list[str] = []

            # Get active workflow runs
            if active_run_registry:
                try:
                    runs = await active_run_registry.get_all_runs()
                    active_runs = [
                        ActiveRunInfo(
                            work_item_id=work_item_id,
                            run_id=run_info.run_id,
                            stage_name=run_info.stage_name,
                            project_id=run_info.project_id,
                            board_id=run_info.board_id,
                            started_at=run_info.started_at,
                        )
                        for work_item_id, run_info in runs
                    ]
                except Exception as e:
                    logger.warning("Failed to get active runs: %s", e, exc_info=True)
                    subsystem_errors.append("active_workflow_run_registry")

            # Get pipeline locks
            if distributed_lock:
                try:
                    holders = await distributed_lock.get_all_holders()
                    pipeline_locks = [
                        LockHolderInfo(
                            lock_key=holder.lock_key,
                            holder_id=holder.holder_id,
                            acquired_at=holder.acquired_at,
                            ttl_seconds=holder.ttl_seconds,
                            expires_at=holder.expires_at,
                            holder_metadata=dict(holder.holder_metadata) if holder.holder_metadata else {},
                        )
                        for holder in holders
                    ]
                except Exception as e:
                    logger.warning("Failed to get lock holders: %s", e, exc_info=True)
                    subsystem_errors.append("distributed_lock")

            # Get pipeline queues
            if pipeline_queue:
                try:
                    # Discover queue keys from multiple sources:
                    # 1. Active runs
                    # 2. Lock holders
                    # 3. Event store (WorkItemQueuedEvent records queue_key in metadata)
                    queue_keys = set()

                    # Add queue keys from active runs
                    for run in active_runs:
                        queue_keys.add(f"{run.project_id}:{run.board_id}")

                    # Add queue keys from lock holders
                    for lock in pipeline_locks:
                        queue_keys.add(lock.lock_key)

                    # Add queue keys from event store (WorkItemQueuedEvent)
                    if event_store:
                        try:
                            # Query for WorkItemQueuedEvent to find all queue keys ever used
                            queued_events = await event_store.get_events_by_type(
                                "WorkItemQueuedEvent",
                                limit=1000,  # Get up to 1000 recent queued events
                            )
                            for event in queued_events:
                                if event.event_data and "queue_key" in event.event_data:
                                    queue_keys.add(str(event.event_data["queue_key"]))
                        except Exception as e:
                            logger.debug("Failed to query WorkItemQueuedEvent from event store: %s", e, exc_info=True)

                    for queue_key in queue_keys:
                        try:
                            entries = await pipeline_queue.list(queue_key)
                            depth = await pipeline_queue.length(queue_key)
                            pipeline_queues.append(
                                PipelineQueueState(
                                    queue_key=queue_key,
                                    entries=[
                                        QueueEntryInfo(
                                            work_item_id=entry.work_item_id,
                                            stage_name=entry.stage_name,
                                            board_position=entry.board_position,
                                            enqueued_at=entry.enqueued_at,
                                            metadata=dict(entry.metadata) if entry.metadata else {},
                                        )
                                        for entry in entries
                                    ],
                                    depth=depth,
                                )
                            )
                        except Exception as e:
                            logger.warning("Failed to read queue %s: %s", queue_key, e, exc_info=True)
                except Exception as e:
                    logger.warning("Failed to get queue states: %s", e, exc_info=True)
                    subsystem_errors.append("pipeline_queue")

            # Get failed event stats
            if failed_event_store:
                try:
                    stats = failed_event_store.get_stats()
                    failed_event_stats = FailedEventStats(
                        total_failed_events=stats.total_failed_events,
                        pending_retries=stats.pending_retries,
                        exhausted_retries=stats.exhausted_retries,
                        total_retries_attempted=stats.total_retries_attempted,
                        total_retries_succeeded=stats.total_retries_succeeded,
                        total_retries_failed=stats.total_retries_failed,
                        oldest_event=stats.oldest_event,
                        newest_event=stats.newest_event,
                        failure_reasons=stats.failure_reasons,
                    )
                except Exception as e:
                    logger.warning("Failed to get failed event stats: %s", e, exc_info=True)
                    subsystem_errors.append("failed_event_store")

            # Get last orphan scan result
            if orphan_scan_registry:
                try:
                    last_scan = await orphan_scan_registry.get_last_scan()
                    if last_scan:
                        last_orphan_scan = OrphanScanResultInfo(
                            scan_id=last_scan.scan_id,
                            scanned_at=last_scan.scanned_at,
                            locks_scanned=last_scan.locks_scanned,
                            orphaned_locks_found=last_scan.orphaned_locks_found,
                            orphaned_locks_released=last_scan.orphaned_locks_released,
                            errors=last_scan.errors or [],
                        )
                except Exception as e:
                    logger.warning("Failed to get orphan scan results: %s", e, exc_info=True)
                    subsystem_errors.append("orphan_scan_registry")

            return DiagnosticsStateResponse(
                active_runs=active_runs,
                pipeline_locks=pipeline_locks,
                pipeline_queues=pipeline_queues,
                failed_event_stats=failed_event_stats,
                last_orphan_scan=last_orphan_scan,
                subsystem_errors=subsystem_errors,
            )

        except Exception as e:
            logger.error("Diagnostics state query failed: %s", e, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve diagnostics state: {e!s}",
            ) from e

    @router.get(
        "/triggers/{event_id}",
        response_model=TriggerLifecycleResponse,
        status_code=status.HTTP_200_OK,
        summary="Get trigger/event lifecycle information",
        response_description="Status and resolution information for a trigger event",
    )
    async def get_trigger_lifecycle(event_id: str) -> TriggerLifecycleResponse:
        """
        Get the lifecycle status of a trigger event.

        Returns:
        - received_at: When the event was first received
        - status: Current status (received | queued | in-progress | completed | failed)
        - queue_position: Position in queue if queued, None otherwise
        - active_run_id: ID of active workflow run if in-progress, None otherwise
        - failure_reason: Reason for failure if failed, None otherwise

        The status is determined by querying the event store and active run registry
        to track the event through its lifecycle.

        **Path Parameters:**
        - event_id: The event/trigger ID to query

        **Returns:**
        - 200 OK: Trigger lifecycle information
        - 404 Not Found: Event not found
        """
        if not event_store:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Event store not available",
            )

        try:
            # Query event store for events matching this event_id
            # Events are stored with aggregate_id, so we look for events with this as aggregate_id
            events: list = []

            try:
                events = await event_store.get_events(
                    stream_id=event_id,
                    from_version=0,
                )
            except (StreamNotFoundError, ResourceNotFoundError):
                # Stream doesn't exist, this is a "not found" condition - allow fallback
                logger.debug("Stream %s not found, trying correlation_id lookup", event_id)
                pass
            except EventStoreError as e:
                # Infrastructure failure, propagate as 500
                logger.warning("Event store infrastructure error when querying stream_id '%s': %s", event_id, e, exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Event store temporarily unavailable",
                ) from e
            except Exception as e:
                # Unknown error, treat as infrastructure failure
                logger.warning("Unexpected error querying stream_id '%s': %s", event_id, e, exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Event store temporarily unavailable",
                ) from e

            if not events:
                # Try to find by correlation_id if available
                try:
                    events = await event_store.get_events_by_correlation_id(event_id)
                except EventStoreError as e:
                    # Infrastructure failure
                    logger.warning("Event store infrastructure error when querying correlation_id '%s': %s", event_id, e, exc_info=True)
                    # If correlation_id lookup fails with infrastructure error and no events found,
                    # we can't confirm the event doesn't exist, so return 500
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Event store temporarily unavailable",
                    ) from e
                except Exception as e:
                    # Unknown error, treat as infrastructure failure
                    logger.warning("Unexpected error querying correlation_id '%s': %s", event_id, e, exc_info=True)
                    # If correlation_id lookup fails with unknown error and no events found,
                    # we can't confirm the event doesn't exist, so return 500
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Event store temporarily unavailable",
                    ) from e

            if not events:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Event {event_id} not found",
                )

            # Get the first event's timestamp as received_at
            first_event = events[0]
            received_at = first_event.timestamp

            # Determine status based on event types and active runs
            status_value = TriggerStatus.RECEIVED
            queue_position: int | None = None
            active_run_id: str | None = None
            failure_reason: str | None = None

            # Check event types to determine status
            event_types = [e.event_type for e in events]

            if "WorkItemQueuedEvent" in event_types:
                status_value = TriggerStatus.QUEUED
                # Try to get queue position from the event data or registry
                if pipeline_queue:
                    # Query queue for position using first event's work item ID
                    # Queue key format is project_id:board_id from event metadata
                    if first_event.event_data and "project_id" in first_event.event_data and "board_id" in first_event.event_data:
                        queue_key = f"{first_event.event_data['project_id']}:{first_event.event_data['board_id']}"
                        try:
                            pos = await pipeline_queue.position_of(queue_key, first_event.aggregate_id)
                            if pos is not None:
                                queue_position = pos
                        except Exception as e:
                            logger.warning("Failed to get queue position for %s: %s", first_event.aggregate_id, e, exc_info=True)

            if "WorkflowStartedEvent" in event_types or "ExecutionStartedEvent" in event_types:
                status_value = TriggerStatus.IN_PROGRESS
                # Find the associated run_id from active runs
                if active_run_registry:
                    active_run = await active_run_registry.get_active_run(
                        first_event.aggregate_id
                    )
                    if active_run:
                        active_run_id = active_run.run_id

            if "WorkflowCompletedEvent" in event_types or "ExecutionCompletedEvent" in event_types:
                status_value = TriggerStatus.COMPLETED

            if (
                "WorkflowFailedEvent" in event_types
                or "ExecutionFailedEvent" in event_types
                or "EventDeadLetterQueuedEvent" in event_types
            ):
                status_value = TriggerStatus.FAILED
                # Extract failure reason from the event
                for event in events:
                    if "failure_reason" in event.event_data:
                        failure_reason = str(event.event_data.get("failure_reason"))
                    elif "error_message" in event.event_data:
                        failure_reason = str(event.event_data.get("error_message"))

            return TriggerLifecycleResponse(
                event_id=event_id,
                received_at=received_at,
                status=status_value,
                queue_position=queue_position,
                active_run_id=active_run_id,
                failure_reason=failure_reason,
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Trigger lifecycle query failed: %s", e, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve trigger lifecycle: {e!s}",
            ) from e

    return router
