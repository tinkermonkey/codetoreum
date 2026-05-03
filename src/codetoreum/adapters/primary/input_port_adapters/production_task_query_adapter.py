"""Production Task Query Adapter

Real implementation of ITaskQueryPort that queries the event store for
execution status, history, and artifact information.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from codetoreum.ports.exceptions import ResourceNotFoundError, ValidationError
from codetoreum.ports.input.task_query import (
    ArtifactInfo,
    ArtifactListResult,
    ExecutionHistory,
    ExecutionHistoryEntry,
    ExecutionListItem,
    ExecutionListResult,
    ExecutionStatus,
    ExecutionStatusInfo,
    ITaskQueryPort,
)
from codetoreum.ports.output.event_store import IEventStore

logger = logging.getLogger(__name__)


class ProductionTaskQueryAdapter(ITaskQueryPort):
    """
    Production implementation of ITaskQueryPort.

    Queries the event store for execution information and reconstructs execution
    status, history, and artifact metadata from domain events.
    """

    def __init__(self, event_store: IEventStore):
        """
        Initialize production task query adapter.

        Args:
            event_store: Event store for querying execution events
        """
        self.event_store = event_store

    async def get_execution_status(self, execution_id: str) -> ExecutionStatusInfo:
        """
        Retrieves detailed status information for a specific execution.

        Queries the event store for execution events and reconstructs the
        current status and timing information.

        Args:
            execution_id: Unique identifier for the execution

        Returns:
            Detailed status information

        Raises:
            ResourceNotFoundError: If execution doesn't exist
        """
        try:
            # Query event store for all execution events using the execution_id as stream_id
            # (aggregate_id is the stream identifier in event sourcing)
            events = await self.event_store.get_events(stream_id=execution_id)

            if not events:
                raise ResourceNotFoundError(f"Execution {execution_id} not found")

            # Reconstruct execution state from events
            execution_data = self._reconstruct_execution_state(events, execution_id)

            return ExecutionStatusInfo(
                execution_id=execution_id,
                workflow_run_id=execution_data.get("workflow_run_id", "unknown"),
                work_item_id=execution_data.get("work_item_id", "unknown"),
                project_name=execution_data.get("project_name", "unknown"),
                pipeline_name=execution_data.get("pipeline_name", "unknown"),
                stage_name=execution_data.get("stage_name", "unknown"),
                agent_name=execution_data.get("agent_name", "unknown"),
                status=self._map_event_status(execution_data.get("status", "pending")),
                started_at=execution_data.get("started_at"),
                completed_at=execution_data.get("completed_at"),
                duration_seconds=execution_data.get("duration_seconds"),
                error_message=execution_data.get("error_message"),
                retry_count=execution_data.get("retry_count", 0),
                metadata=execution_data.get("metadata", {}),
            )
        except ResourceNotFoundError:
            raise
        except Exception as e:
            logger.error(
                f"Error retrieving execution status for {execution_id}: {e}",
                exc_info=True,
            )
            raise ResourceNotFoundError(f"Error retrieving execution {execution_id}")

    async def list_executions(
        self,
        workflow_run_id: str | None = None,
        work_item_id: str | None = None,
        project_name: str | None = None,
        status: ExecutionStatus | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> ExecutionListResult:
        """
        Lists executions matching the specified criteria.

        Queries the event store for execution events matching the given filters
        and returns paginated results.

        Args:
            workflow_run_id: Filter by workflow run
            work_item_id: Filter by work item
            project_name: Filter by project
            status: Filter by execution status
            page: Page number (1-indexed)
            page_size: Number of items per page

        Returns:
            Paginated list of executions

        Raises:
            ValidationError: If parameters are invalid
        """
        try:
            # Validate pagination parameters
            if page < 1 or page_size < 1:
                raise ValidationError("Page and page_size must be >= 1")

            # Get all execution stream IDs by querying for ExecutionInitialized events
            # (the first event in each execution stream)
            init_events = await self.event_store.get_events_by_type(
                event_type="ExecutionInitialized",
                limit=10000,  # Reasonable limit for queries
            )

            # Collect execution IDs from initialization events
            execution_ids = set()
            for event in init_events:
                # aggregate_id is the stream_id, which should be the execution ID
                if hasattr(event, "aggregate_id"):
                    execution_ids.add(event.aggregate_id)

            # Reconstruct each execution from its complete event stream
            executions_by_id: dict[str, dict[str, Any]] = {}
            for exec_id in execution_ids:
                try:
                    # Get all events for this execution stream
                    all_events = await self.event_store.get_events(stream_id=exec_id)
                    if all_events:
                        # Reconstruct execution state from ALL events, not just the first one
                        exec_data = self._reconstruct_execution_state(all_events, exec_id)
                        executions_by_id[exec_id] = exec_data
                except Exception as e:
                    logger.warning(
                        f"Failed to reconstruct execution {exec_id}: {e}",
                        exc_info=True,
                    )
                    continue

            # Filter by criteria
            execution_list = []
            for exec_id, exec_data in executions_by_id.items():
                # Apply workflow_run_id filter
                if workflow_run_id and exec_data.get("workflow_run_id") != workflow_run_id:
                    continue

                # Apply work_item_id filter
                if work_item_id and exec_data.get("work_item_id") != work_item_id:
                    continue

                # Apply project_name filter
                if project_name and exec_data.get("project_name") != project_name:
                    continue

                # Apply status filter
                if status and self._map_event_status(exec_data.get("status")) != status:
                    continue

                execution_list.append(
                    ExecutionListItem(
                        execution_id=exec_id,
                        workflow_run_id=exec_data.get("workflow_run_id", "unknown"),
                        work_item_id=exec_data.get("work_item_id", "unknown"),
                        stage_name=exec_data.get("stage_name", "unknown"),
                        agent_name=exec_data.get("agent_name", "unknown"),
                        status=self._map_event_status(exec_data.get("status", "pending")),
                        started_at=exec_data.get("started_at"),
                        duration_seconds=exec_data.get("duration_seconds"),
                    )
                )

            # Sort by started time (newest first)
            execution_list.sort(
                key=lambda x: x.started_at or datetime.fromtimestamp(0, UTC),
                reverse=True,
            )

            # Apply pagination
            total_count = len(execution_list)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            paginated_executions = execution_list[start_idx:end_idx]

            return ExecutionListResult(
                executions=paginated_executions,
                total_count=total_count,
                page=page,
                page_size=page_size,
                has_next=end_idx < total_count,
            )
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error listing executions: {e}", exc_info=True)
            return ExecutionListResult(
                executions=[],
                total_count=0,
                page=page,
                page_size=page_size,
                has_next=False,
            )

    async def get_artifacts(
        self,
        execution_id: str,
        artifact_type: str | None = None,
    ) -> ArtifactListResult:
        """
        Retrieves artifacts produced by an execution.

        Queries for artifact metadata stored in execution events or storage
        system and returns artifact information.

        Args:
            execution_id: Unique identifier for the execution
            artifact_type: Optional filter by artifact type

        Returns:
            List of artifact information

        Raises:
            ResourceNotFoundError: If execution doesn't exist
        """
        try:
            # Get all events for this execution
            events = await self.event_store.get_events(stream_id=execution_id)

            if not events:
                raise ResourceNotFoundError(f"Execution {execution_id} not found")

            # Extract artifacts from events
            artifacts: list[ArtifactInfo] = []
            for event in events:
                # Check event type using both attribute access and dict access patterns
                event_type = getattr(event, "event_type", None) or (event.get("event_type") if isinstance(event, dict) else None)

                if event_type == "ArtifactCreated":
                    # Handle both object and dict event formats
                    if isinstance(event, dict):
                        artifact_data = event.get("data", {})
                    else:
                        artifact_data = getattr(event, "payload", {}) or getattr(event, "data", {})

                    artifacts.append(
                        ArtifactInfo(
                            artifact_id=artifact_data.get("artifact_id", "") if isinstance(artifact_data, dict) else getattr(artifact_data, "artifact_id", ""),
                            execution_id=execution_id,
                            artifact_type=artifact_type or (artifact_data.get("type", "") if isinstance(artifact_data, dict) else getattr(artifact_data, "type", "")),
                            name=artifact_data.get("name", "") if isinstance(artifact_data, dict) else getattr(artifact_data, "name", ""),
                            path=artifact_data.get("path", "") if isinstance(artifact_data, dict) else getattr(artifact_data, "path", ""),
                            size_bytes=artifact_data.get("size_bytes", 0) if isinstance(artifact_data, dict) else getattr(artifact_data, "size_bytes", 0),
                            created_at=datetime.fromisoformat(artifact_data.get("created_at", "") if isinstance(artifact_data, dict) else getattr(artifact_data, "created_at", "")),
                            mime_type=artifact_data.get("mime_type") if isinstance(artifact_data, dict) else getattr(artifact_data, "mime_type", None),
                            metadata=artifact_data.get("metadata", {}) if isinstance(artifact_data, dict) else getattr(artifact_data, "metadata", {}),
                        )
                    )

            return ArtifactListResult(artifacts=artifacts, total_count=len(artifacts))
        except ResourceNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error retrieving artifacts for {execution_id}: {e}", exc_info=True)
            return ArtifactListResult(artifacts=[], total_count=0)

    async def get_execution_history(
        self,
        execution_id: str,
        limit: int | None = None,
    ) -> ExecutionHistory:
        """
        Retrieves the event history for an execution.

        Queries the event store for all events related to the execution and
        returns them as a chronologically ordered history.

        Args:
            execution_id: Unique identifier for the execution
            limit: Optional limit on number of entries to return

        Returns:
            Execution history with all events

        Raises:
            ResourceNotFoundError: If execution doesn't exist
        """
        try:
            # Get all events for this execution stream
            events = await self.event_store.get_events(stream_id=execution_id)

            if not events:
                raise ResourceNotFoundError(f"Execution {execution_id} not found")

            # Convert events to history entries
            entries: list[ExecutionHistoryEntry] = []
            for event in events:
                # Handle both object and dict event formats
                if isinstance(event, dict):
                    event_type = event.get("event_type", "")
                    timestamp_str = event.get("timestamp", "")
                    message = event.get("message", "")
                    details = event.get("data", {})
                else:
                    event_type = getattr(event, "event_type", "")
                    timestamp_str = getattr(event, "occurred_at", "")
                    if hasattr(timestamp_str, "isoformat"):
                        timestamp_str = timestamp_str.isoformat()
                    message = getattr(event, "message", "")
                    details = getattr(event, "payload", {})

                # Parse timestamp safely
                try:
                    if timestamp_str:
                        timestamp = datetime.fromisoformat(timestamp_str)
                    else:
                        timestamp = datetime.now(UTC)
                except (ValueError, TypeError):
                    timestamp = datetime.now(UTC)

                entries.append(
                    ExecutionHistoryEntry(
                        timestamp=timestamp,
                        event_type=event_type,
                        message=message,
                        details=details if isinstance(details, dict) else {},
                    )
                )

            # Sort by timestamp and apply limit
            entries.sort(key=lambda x: x.timestamp)
            if limit:
                entries = entries[-limit:]

            return ExecutionHistory(
                execution_id=execution_id,
                entries=entries,
                total_entries=len(entries),
            )
        except ResourceNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error retrieving execution history for {execution_id}: {e}", exc_info=True)
            raise ResourceNotFoundError(f"Error retrieving history for execution {execution_id}")

    async def get_workflow_executions(self, workflow_run_id: str) -> ExecutionListResult:
        """
        Retrieves all executions for a specific workflow run.

        Queries the event store for all executions within the given workflow
        run and returns them in chronological order.

        Args:
            workflow_run_id: Unique identifier for the workflow run

        Returns:
            List of all executions in the workflow

        Raises:
            ResourceNotFoundError: If workflow run doesn't exist
        """
        return await self.list_executions(workflow_run_id=workflow_run_id, page_size=1000)

    def _reconstruct_execution_state(self, events: list[Any], execution_id: str) -> dict[str, Any]:
        """
        Reconstruct execution state from event stream.

        Handles both object and dict event formats.

        Args:
            events: List of events for the execution (objects or dicts)
            execution_id: Execution ID

        Returns:
            Dict with execution state
        """
        state: dict[str, Any] = {
            "execution_id": execution_id,
            "status": "pending",
            "retry_count": 0,
            "metadata": {},
        }

        for event in events:
            # Handle both object and dict event formats
            if isinstance(event, dict):
                event_type = event.get("event_type", "")
                data = event.get("data", {}) or event.get("payload", {})
                timestamp = event.get("timestamp", "") or event.get("occurred_at", "")
            else:
                event_type = getattr(event, "event_type", "")
                data = getattr(event, "payload", {}) or getattr(event, "data", {})
                timestamp = getattr(event, "occurred_at", "")
                if hasattr(timestamp, "isoformat"):
                    timestamp = timestamp.isoformat()

            # Convert data to dict if it's an object
            if data and not isinstance(data, dict):
                if hasattr(data, "__dict__"):
                    data = data.__dict__
                else:
                    data = {}

            if event_type == "ExecutionInitialized":
                state.update(
                    {
                        "workflow_run_id": data.get("workflow_run_id"),
                        "work_item_id": data.get("work_item_id"),
                        "project_name": data.get("project_name"),
                        "pipeline_name": data.get("pipeline_name"),
                        "stage_name": data.get("stage_name"),
                        "agent_name": data.get("agent_name"),
                        "status": "initialized",
                    }
                )
            elif event_type == "ExecutionStarted":
                try:
                    if timestamp:
                        start_time = datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else timestamp
                    else:
                        start_time = datetime.now(UTC)
                except (ValueError, TypeError):
                    start_time = datetime.now(UTC)
                state.update({"status": "running", "started_at": start_time})
            elif event_type == "ExecutionCompleted":
                try:
                    if timestamp:
                        comp_time = datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else timestamp
                    else:
                        comp_time = datetime.now(UTC)
                except (ValueError, TypeError):
                    comp_time = datetime.now(UTC)
                state.update(
                    {
                        "status": "completed",
                        "completed_at": comp_time,
                    }
                )
                if state.get("started_at"):
                    duration = (state["completed_at"] - state["started_at"]).total_seconds()
                    state["duration_seconds"] = duration
            elif event_type == "ExecutionFailed":
                try:
                    if timestamp:
                        fail_time = datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else timestamp
                    else:
                        fail_time = datetime.now(UTC)
                except (ValueError, TypeError):
                    fail_time = datetime.now(UTC)
                state.update(
                    {
                        "status": "failed",
                        "completed_at": fail_time,
                        "error_message": data.get("error"),
                    }
                )
                if state.get("started_at"):
                    duration = (state["completed_at"] - state["started_at"]).total_seconds()
                    state["duration_seconds"] = duration

        return state

    def _map_event_status(self, event_status: str) -> ExecutionStatus:
        """
        Map internal event status to ExecutionStatus enum.

        Args:
            event_status: Status string from events

        Returns:
            ExecutionStatus enum value
        """
        status_map = {
            "initialized": ExecutionStatus.PENDING,
            "running": ExecutionStatus.RUNNING,
            "completed": ExecutionStatus.COMPLETED,
            "failed": ExecutionStatus.FAILED,
            "cancelled": ExecutionStatus.CANCELLED,
            "paused": ExecutionStatus.PAUSED,
            "pending": ExecutionStatus.PENDING,
        }
        return status_map.get(event_status.lower(), ExecutionStatus.PENDING)
