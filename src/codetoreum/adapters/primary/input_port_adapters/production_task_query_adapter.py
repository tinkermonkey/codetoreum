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
            # Query event store for execution events
            events = await self.event_store.query_events(
                event_types=["ExecutionInitialized", "ExecutionStarted", "ExecutionCompleted", "ExecutionFailed"],
                filters={"execution_id": execution_id},
            )

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

            # Build filters for event store query
            filters: dict[str, Any] = {}
            if workflow_run_id:
                filters["workflow_run_id"] = workflow_run_id
            if work_item_id:
                filters["work_item_id"] = work_item_id
            if project_name:
                filters["project_name"] = project_name

            # Query for execution events
            events = await self.event_store.query_events(
                event_types=["ExecutionInitialized", "ExecutionCompleted", "ExecutionFailed"],
                filters=filters,
            )

            # Reconstruct executions from events
            executions_by_id: dict[str, dict[str, Any]] = {}
            for event in events:
                exec_id = event.get("execution_id", "")
                if exec_id not in executions_by_id:
                    executions_by_id[exec_id] = self._reconstruct_execution_state([event], exec_id)

            # Filter by status if provided
            execution_list = []
            for exec_id, exec_data in executions_by_id.items():
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
            # Query for artifact events
            events = await self.event_store.query_events(
                event_types=["ArtifactCreated", "ExecutionCompleted"],
                filters={"execution_id": execution_id},
            )

            if not events:
                raise ResourceNotFoundError(f"Execution {execution_id} not found")

            # Extract artifacts from events
            artifacts: list[ArtifactInfo] = []
            for event in events:
                if event.get("event_type") == "ArtifactCreated":
                    artifact_data = event.get("data", {})
                    artifacts.append(
                        ArtifactInfo(
                            artifact_id=artifact_data.get("artifact_id", ""),
                            execution_id=execution_id,
                            artifact_type=artifact_type or artifact_data.get("type", ""),
                            name=artifact_data.get("name", ""),
                            path=artifact_data.get("path", ""),
                            size_bytes=artifact_data.get("size_bytes", 0),
                            created_at=datetime.fromisoformat(artifact_data.get("created_at", "")),
                            mime_type=artifact_data.get("mime_type"),
                            metadata=artifact_data.get("metadata", {}),
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
            # Query all events for execution
            events = await self.event_store.query_events(
                filters={"execution_id": execution_id},
            )

            if not events:
                raise ResourceNotFoundError(f"Execution {execution_id} not found")

            # Convert events to history entries
            entries: list[ExecutionHistoryEntry] = []
            for event in events:
                entries.append(
                    ExecutionHistoryEntry(
                        timestamp=datetime.fromisoformat(event.get("timestamp", "")),
                        event_type=event.get("event_type", ""),
                        message=event.get("message", ""),
                        details=event.get("data", {}),
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

    def _reconstruct_execution_state(self, events: list[dict[str, Any]], execution_id: str) -> dict[str, Any]:
        """
        Reconstruct execution state from event stream.

        Args:
            events: List of events for the execution
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
            event_type = event.get("event_type", "")
            data = event.get("data", {})
            timestamp = event.get("timestamp", "")

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
                state.update({"status": "running", "started_at": datetime.fromisoformat(timestamp)})
            elif event_type == "ExecutionCompleted":
                state.update(
                    {
                        "status": "completed",
                        "completed_at": datetime.fromisoformat(timestamp),
                    }
                )
                if state.get("started_at"):
                    duration = (state["completed_at"] - state["started_at"]).total_seconds()
                    state["duration_seconds"] = duration
            elif event_type == "ExecutionFailed":
                state.update(
                    {
                        "status": "failed",
                        "completed_at": datetime.fromisoformat(timestamp),
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
