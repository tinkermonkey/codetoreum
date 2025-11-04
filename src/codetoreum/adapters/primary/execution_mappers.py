"""
Execution Mappers

Converts between domain models and API DTOs for executions.
"""

from codetoreum.adapters.primary.execution_dtos import (
    ContainerStatusDTO,
    ExecutionCommandResult,
    ExecutionErrorDetailDTO,
    ExecutionHistoryEntryDTO,
    ExecutionHistoryResponse,
    ExecutionListResponse,
    ExecutionLogsResponse,
    ExecutionResponse,
    ExecutionSummaryResponse,
    LogEntryDTO,
)
from codetoreum.ports.input.execution_command import (
    ExecutionCommandResult as PortExecutionCommandResult,
)
from codetoreum.ports.input.execution_query import (
    ExecutionHistory,
    ExecutionInfo,
    ExecutionListResult,
    ExecutionLogs,
)


class ExecutionMapper:
    """Maps between Execution domain models and API DTOs."""

    @staticmethod
    def to_response(execution_info: ExecutionInfo) -> ExecutionResponse:
        """
        Convert ExecutionInfo (from port) to ExecutionResponse DTO.

        Args:
            execution_info: ExecutionInfo from query port

        Returns:
            ExecutionResponse DTO
        """
        # Convert error detail if present
        error_detail = None
        if execution_info.error_detail:
            container_status = None
            if execution_info.error_detail.container_status:
                container_status = ContainerStatusDTO(
                    container_id=execution_info.error_detail.container_status.container_id,
                    container_name=execution_info.error_detail.container_status.container_name,
                    last_known_status=execution_info.error_detail.container_status.last_known_status,
                    exit_code=execution_info.error_detail.container_status.exit_code,
                )

            error_detail = ExecutionErrorDetailDTO(
                error_type=execution_info.error_detail.error_type.value,
                message=execution_info.error_detail.message,
                container_status=container_status,
                partial_logs_available=execution_info.error_detail.partial_logs_available,
            )

        return ExecutionResponse(
            id=execution_info.id,
            agent_id=execution_info.agent_id,
            agent_name=execution_info.agent_name,
            work_item_id=execution_info.work_item_id,
            workflow_id=execution_info.workflow_id,
            stage_name=execution_info.stage_name,
            status=execution_info.status.value,
            container_name=execution_info.container_name,
            container_id=execution_info.container_id,
            output=execution_info.output,
            error_message=execution_info.error_message,
            error_detail=error_detail,
            exit_code=execution_info.exit_code,
            input_tokens=execution_info.input_tokens,
            output_tokens=execution_info.output_tokens,
            duration_seconds=execution_info.duration_seconds,
            initialized_at=execution_info.initialized_at,
            started_at=execution_info.started_at,
            completed_at=execution_info.completed_at,
            elapsed_time_seconds=execution_info.elapsed_time_seconds,
            current_stage=execution_info.current_stage,
        )

    @staticmethod
    def to_summary_response(execution_info: ExecutionInfo) -> ExecutionSummaryResponse:
        """
        Convert ExecutionInfo to ExecutionSummaryResponse (for list views).

        Args:
            execution_info: ExecutionInfo from query port

        Returns:
            ExecutionSummaryResponse DTO
        """
        error_type = None
        if execution_info.error_detail:
            error_type = execution_info.error_detail.error_type.value

        return ExecutionSummaryResponse(
            id=execution_info.id,
            agent_name=execution_info.agent_name,
            work_item_id=execution_info.work_item_id,
            workflow_id=execution_info.workflow_id,
            stage_name=execution_info.stage_name,
            status=execution_info.status.value,
            initialized_at=execution_info.initialized_at,
            started_at=execution_info.started_at,
            completed_at=execution_info.completed_at,
            duration_seconds=execution_info.duration_seconds,
            error_type=error_type,
        )

    @staticmethod
    def to_list_response(result: ExecutionListResult) -> ExecutionListResponse:
        """
        Convert ExecutionListResult to ExecutionListResponse DTO.

        Args:
            result: ExecutionListResult from query port

        Returns:
            ExecutionListResponse DTO
        """
        executions = [
            ExecutionMapper.to_summary_response(execution)
            for execution in result.executions
        ]

        return ExecutionListResponse(
            executions=executions,
            total_count=result.total_count,
            offset=result.offset,
            limit=result.limit,
            has_next=result.has_next,
        )

    @staticmethod
    def to_logs_response(logs: ExecutionLogs) -> ExecutionLogsResponse:
        """
        Convert ExecutionLogs to ExecutionLogsResponse DTO.

        Args:
            logs: ExecutionLogs from query port

        Returns:
            ExecutionLogsResponse DTO
        """
        log_entries = [
            LogEntryDTO(
                timestamp=entry.timestamp,
                level=entry.level,
                message=entry.message,
                stage=entry.stage,
            )
            for entry in logs.logs
        ]

        return ExecutionLogsResponse(
            execution_id=logs.execution_id,
            logs=log_entries,
            total_lines=logs.total_lines,
            stage=logs.stage,
            has_more=logs.has_more,
        )

    @staticmethod
    def to_history_response(history: ExecutionHistory) -> ExecutionHistoryResponse:
        """
        Convert ExecutionHistory to ExecutionHistoryResponse DTO.

        Args:
            history: ExecutionHistory from query port

        Returns:
            ExecutionHistoryResponse DTO
        """
        events = [
            ExecutionHistoryEntryDTO(
                event_type=entry.event_type,
                occurred_at=entry.occurred_at,
                payload=entry.payload,
            )
            for entry in history.events
        ]

        return ExecutionHistoryResponse(
            execution_id=history.execution_id,
            events=events,
            total_events=history.total_events,
        )

    @staticmethod
    def to_command_result(
        result: PortExecutionCommandResult,
    ) -> ExecutionCommandResult:
        """
        Convert port ExecutionCommandResult to API ExecutionCommandResult DTO.

        Args:
            result: ExecutionCommandResult from port

        Returns:
            ExecutionCommandResult DTO
        """
        return ExecutionCommandResult(
            success=result.success,
            execution_id=result.execution_id,
            message=result.message,
            new_status=result.new_status,
            errors=result.errors,
        )
