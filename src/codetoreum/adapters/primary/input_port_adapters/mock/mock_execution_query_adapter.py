"""
Mock Execution Query Adapter

In-memory implementation of IExecutionQueryPort for development and testing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from threading import RLock
from typing import TYPE_CHECKING, Any

from codetoreum.domain.agent_execution import ExecutionStatus
from codetoreum.domain.exceptions import ExecutionNotFoundError
from codetoreum.ports.input.execution_query import (
    ExecutionFilters,
    ExecutionHistory,
    ExecutionHistoryEntry,
    ExecutionInfo,
    ExecutionListResult,
    ExecutionLogs,
    ExecutionPaginationParams,
    ExecutionSortField,
    IExecutionQueryPort,
    LogEntry,
    SortOrder,
)

if TYPE_CHECKING:
    from codetoreum.adapters.testing.execution_service_agent_executor import ExecutionServiceAgentExecutor


class MockExecutionQueryAdapter(IExecutionQueryPort):
    """
    Mock implementation of IExecutionQueryPort using in-memory storage.

    Can optionally be wired to an ExecutionServiceAgentExecutor to expose
    execution records as query results. This enables visibility into the
    executions endpoint (GET /api/v2/executions) during simulation testing.
    """

    def __init__(self, agent_executor: ExecutionServiceAgentExecutor | None = None):
        self._executions: dict[str, ExecutionInfo] = {}
        self._logs: dict[str, list[LogEntry]] = {}  # execution_id -> logs
        self._history: dict[str, list[ExecutionHistoryEntry]] = {}  # execution_id -> history
        self._agent_executor = agent_executor
        self._lock = RLock()

    def add_execution(self, execution_info: ExecutionInfo):
        """Helper method to add an execution to mock storage."""
        with self._lock:
            self._executions[execution_info.id] = execution_info
            if execution_info.id not in self._logs:
                self._logs[execution_info.id] = []
            if execution_info.id not in self._history:
                self._history[execution_info.id] = []

    def add_log_entry(self, execution_id: str, log_entry: LogEntry):
        """Helper method to add a log entry."""
        with self._lock:
            if execution_id not in self._logs:
                self._logs[execution_id] = []
            self._logs[execution_id].append(log_entry)

    def add_history_event(self, execution_id: str, event: ExecutionHistoryEntry):
        """Helper method to add a history event."""
        with self._lock:
            if execution_id not in self._history:
                self._history[execution_id] = []
            self._history[execution_id].append(event)

    async def get_execution(self, execution_id: str) -> ExecutionInfo:
        """Get execution by ID."""
        with self._lock:
            # Sync executions from agent executor if available
            self._sync_from_agent_executor()

            if execution_id not in self._executions:
                msg = f"Execution with ID {execution_id} not found"
                raise ExecutionNotFoundError(msg)
            return self._executions[execution_id]

    async def list_executions(
        self,
        filters: ExecutionFilters | None = None,
        pagination: ExecutionPaginationParams | None = None,
    ) -> ExecutionListResult:
        """List executions with optional filtering and pagination."""
        with self._lock:
            # Sync executions from agent executor if available
            self._sync_from_agent_executor()

            # Get all executions
            executions = list(self._executions.values())

            # Apply filters
            if filters:
                executions = self._apply_filters(executions, filters)

            # Sort executions
            if pagination:
                executions = self._sort_executions(executions, pagination)

            total_count = len(executions)

            # Apply pagination
            offset = 0
            limit = 20
            if pagination:
                offset = pagination.offset
                limit = pagination.limit

            paginated_executions = executions[offset : offset + limit]
            has_next = (offset + limit) < total_count

            return ExecutionListResult(
                executions=paginated_executions,
                total_count=total_count,
                offset=offset,
                limit=limit,
                has_next=has_next,
            )

    async def get_execution_logs(
        self,
        execution_id: str,
        stage: str | None = None,
        tail: int | None = None,
    ) -> ExecutionLogs:
        """Get execution logs."""
        with self._lock:
            if execution_id not in self._executions:
                msg = f"Execution with ID {execution_id} not found"
                raise ExecutionNotFoundError(msg)

            logs = self._logs.get(execution_id, [])

            # Filter by stage if specified
            if stage:
                logs = [log for log in logs if log.stage == stage]

            # Apply tail if specified
            if tail:
                logs = logs[-tail:]

            return ExecutionLogs(
                execution_id=execution_id,
                logs=logs,
                total_lines=len(logs),
                stage=stage,
                has_more=False,  # Mock doesn't paginate logs
            )

    async def get_execution_history(self, execution_id: str, limit: int | None = None) -> ExecutionHistory:
        """Get execution event history."""
        with self._lock:
            if execution_id not in self._executions:
                msg = f"Execution with ID {execution_id} not found"
                raise ExecutionNotFoundError(msg)

            history = self._history.get(execution_id, [])

            # Apply limit if specified
            if limit:
                history = history[-limit:]

            return ExecutionHistory(
                execution_id=execution_id,
                events=history,
                total_events=len(history),
            )

    async def count_executions(self, filters: ExecutionFilters | None = None) -> int:
        """Count executions matching filters."""
        with self._lock:
            # Sync executions from agent executor if available
            self._sync_from_agent_executor()

            executions = list(self._executions.values())

            if filters:
                executions = self._apply_filters(executions, filters)

            return len(executions)

    def _apply_filters(self, executions: list[ExecutionInfo], filters: ExecutionFilters) -> list[ExecutionInfo]:
        """Apply filters to execution list."""
        result = executions

        if filters.status is not None:
            result = [e for e in result if e.status == filters.status]

        if filters.agent_id is not None:
            result = [e for e in result if e.agent_id == filters.agent_id]

        if filters.work_item_id is not None:
            result = [e for e in result if e.work_item_id == filters.work_item_id]

        if filters.workflow_id is not None:
            result = [e for e in result if e.workflow_id == filters.workflow_id]

        if filters.stage_name is not None:
            result = [e for e in result if e.stage_name == filters.stage_name]

        if filters.start_date is not None:
            result = [e for e in result if e.started_at and e.started_at >= filters.start_date]

        if filters.end_date is not None:
            result = [e for e in result if e.started_at and e.started_at <= filters.end_date]

        return result

    def _sort_executions(
        self,
        executions: list[ExecutionInfo],
        pagination: ExecutionPaginationParams,
    ) -> list[ExecutionInfo]:
        """Sort executions based on pagination parameters."""
        reverse = pagination.sort_order == SortOrder.DESC

        if pagination.sort_by == ExecutionSortField.INITIALIZED_AT:
            executions.sort(key=lambda e: e.initialized_at, reverse=reverse)
        elif pagination.sort_by == ExecutionSortField.STARTED_AT:
            executions.sort(
                key=lambda e: e.started_at or datetime.min.replace(tzinfo=UTC),
                reverse=reverse,
            )
        elif pagination.sort_by == ExecutionSortField.COMPLETED_AT:
            executions.sort(
                key=lambda e: e.completed_at or datetime.min.replace(tzinfo=UTC),
                reverse=reverse,
            )
        elif pagination.sort_by == ExecutionSortField.DURATION:
            executions.sort(
                key=lambda e: e.duration_seconds or 0.0,
                reverse=reverse,
            )
        elif pagination.sort_by == ExecutionSortField.STATUS:
            executions.sort(key=lambda e: e.status.value, reverse=reverse)

        return executions

    def _sync_from_agent_executor(self) -> None:
        """
        Synchronize executions from the agent executor (if available).

        This enables visibility into the executions endpoint by pulling execution
        records from ExecutionServiceAgentExecutor, which tracks all agent executions
        performed during simulation. This solves issue #371 where execution data
        was not visible through the GET /api/v2/executions REST endpoint.

        The sync is:
        - On-demand: Only called when query methods are invoked
        - Idempotent: Safe to call multiple times (checks if execution already exists)
        - Lock-safe: Called within the adapter's lock to prevent race conditions
        """
        if not self._agent_executor:
            return

        # Get the execution records from the agent executor
        executor_executions = self._agent_executor.executions

        # Convert each executor record to ExecutionInfo and add to our storage
        for exec_record in executor_executions:
            # Generate unique ID per execution using work_item_id and agent_id
            # This ensures multi-stage pipelines (same work_item_id with different agents)
            # don't collide. E.g., work_item_123-architect, work_item_123-coder, work_item_123-tester
            work_item_id = exec_record.get("work_item_id", "unknown")
            agent_id = exec_record.get("agent_id", "unknown")
            execution_id = f"{work_item_id}-{agent_id}"

            # Skip if already processed
            if execution_id in self._executions:
                continue

            # Convert executor record to ExecutionInfo
            execution_info = self._convert_executor_record_to_execution_info(exec_record, execution_id)

            # Add to our storage
            self._executions[execution_id] = execution_info
            if execution_id not in self._logs:
                self._logs[execution_id] = []
            if execution_id not in self._history:
                self._history[execution_id] = []

    def _convert_executor_record_to_execution_info(self, record: dict[str, Any], execution_id: str) -> ExecutionInfo:
        """
        Convert an ExecutionServiceAgentExecutor record to ExecutionInfo.

        Args:
            record: Execution record from executor with keys:
                - work_item_id: ID of the work item being executed
                - agent_id: ID of the agent
                - board_id: ID of the board
                - started_at: ISO timestamp of execution start
                - workflow_id: ID of the workflow
                - stage_name: Name of the pipeline stage
            execution_id: Unique execution identifier (typically work_item_id-agent_id)

        Returns:
            ExecutionInfo with standard execution details
        """
        work_item_id = record.get("work_item_id", "unknown")
        agent_id = record.get("agent_id", "unknown")
        workflow_id = record.get("workflow_id", "unknown")
        stage_name = record.get("stage_name", "unknown")
        started_at_str = record.get("started_at", datetime.now(UTC).isoformat())

        # Parse started_at timestamp
        try:
            initialized_at = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            initialized_at = datetime.now(UTC)

        # Create ExecutionInfo with execution data from executor record
        # Status is COMPLETED for now (executor doesn't track detailed status yet)
        return ExecutionInfo(
            id=execution_id,
            agent_id=agent_id,
            agent_name=f"agent-{agent_id}",
            work_item_id=work_item_id,
            workflow_id=workflow_id,
            stage_name=stage_name,
            status=ExecutionStatus.COMPLETED,
            container_name=None,
            container_id=None,
            output=record.get("output"),
            error_message=None,
            error_detail=None,
            exit_code=None,
            input_tokens=0,
            output_tokens=0,
            duration_seconds=None,
            initialized_at=initialized_at,
            started_at=initialized_at,
            completed_at=datetime.now(UTC),
        )

    def clear(self):
        """Clear all data (useful for testing)."""
        with self._lock:
            self._executions.clear()
            self._logs.clear()
            self._history.clear()
