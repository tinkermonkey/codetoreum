"""
Workflow DTO Mappers

Maps between domain models/port objects and API DTOs for workflows and orchestration.
This keeps the domain layer independent of API concerns.
"""

from datetime import UTC, datetime

from codetoreum.adapters.primary.orchestration_dtos import (
    ConditionValidationResult,
    EntryConditionValidationResponse,
    ExecutionQueueResponse,
    QueuedExecutionInfo,
    StartWorkflowExecutionRequest,
    StartWorkflowExecutionResponse,
    WorkflowExecutionResponse,
)
from codetoreum.adapters.primary.workflow_dtos import (
    CreateWorkflowRequest,
    StageEntryCondition,
    StageTransition,
    UpdateWorkflowRequest,
    WorkflowCommandResult,
    WorkflowListResponse,
    WorkflowResponse,
    WorkflowStageResponse,
    WorkflowSummaryResponse,
    WorkflowValidationError,
    WorkflowValidationResponse,
    WorkflowVersionListResponse,
    WorkflowVersionResponse,
)
from codetoreum.ports.input.orchestration_command import (
    EntryConditionCheckResult,
    ExecutionPriority,
    OrchestrationCommandResult,
    StartExecutionCommand,
)
from codetoreum.ports.input.task_query import ExecutionListResult
from codetoreum.ports.input.workflow_definition_command import (
    CreateWorkflowDefinitionCommand,
    StageDefinition,
    StageTransitionDefinition,
    UpdateWorkflowDefinitionCommand,
    WorkflowDefinitionCommandResult,
)
from codetoreum.ports.input.workflow_query import (
    WorkflowDefinitionInfo,
    WorkflowListResult,
    WorkflowSummaryInfo,
    WorkflowValidationResult,
    WorkflowVersionHistoryResult,
)


class WorkflowMapper:
    """Maps between Workflow domain models and API DTOs"""

    @staticmethod
    def to_create_command(dto: CreateWorkflowRequest) -> CreateWorkflowDefinitionCommand:
        """
        Convert CreateWorkflowRequest DTO to CreateWorkflowDefinitionCommand.

        Args:
            dto: Request DTO from API

        Returns:
            Domain command object
        """
        # Convert stage DTOs to domain objects
        stages = [
            StageDefinition(
                name=stage.name,
                agent_name=stage.agent_name,
                timeout_seconds=stage.timeout_seconds,
                retry_count=stage.retry_count,
                entry_conditions=[
                    {"condition_type": cond.condition_type, "parameters": cond.parameters}
                    for cond in stage.entry_conditions
                ],
                metadata=stage.metadata,
            )
            for stage in dto.stages
        ]

        # Convert transition DTOs to domain objects
        transitions = [
            StageTransitionDefinition(
                from_stage=trans.from_stage,
                to_stage=trans.to_stage,
                condition=trans.condition,
            )
            for trans in dto.transitions
        ]

        return CreateWorkflowDefinitionCommand(
            name=dto.name,
            description=dto.description,
            project_id=dto.project_id,
            stages=stages,
            transitions=transitions,
            work_item_types=dto.work_item_types or [],
            is_template=dto.is_template,
            metadata=dto.metadata,
        )

    @staticmethod
    def to_update_command(workflow_id: str, dto: UpdateWorkflowRequest) -> UpdateWorkflowDefinitionCommand:
        """
        Convert UpdateWorkflowRequest DTO to UpdateWorkflowDefinitionCommand.

        Args:
            workflow_id: Workflow ID
            dto: Request DTO from API

        Returns:
            Domain command object
        """
        # Convert stages if provided
        stages = None
        if dto.stages:
            stages = [
                StageDefinition(
                    name=stage.name,
                    agent_name=stage.agent_name,
                    timeout_seconds=stage.timeout_seconds,
                    retry_count=stage.retry_count,
                    entry_conditions=[
                        {"condition_type": cond.condition_type, "parameters": cond.parameters}
                        for cond in stage.entry_conditions
                    ],
                    metadata=stage.metadata,
                )
                for stage in dto.stages
            ]

        # Convert transitions if provided
        transitions = None
        if dto.transitions:
            transitions = [
                StageTransitionDefinition(
                    from_stage=trans.from_stage,
                    to_stage=trans.to_stage,
                    condition=trans.condition,
                )
                for trans in dto.transitions
            ]

        return UpdateWorkflowDefinitionCommand(
            workflow_id=workflow_id,
            name=dto.name,
            description=dto.description,
            stages=stages,
            transitions=transitions,
            work_item_types=dto.work_item_types,
            metadata=dto.metadata,
        )

    @staticmethod
    def to_response(workflow_info: WorkflowDefinitionInfo) -> WorkflowResponse:
        """
        Convert WorkflowDefinitionInfo to WorkflowResponse DTO.

        Args:
            workflow_info: Port-level workflow information

        Returns:
            Response DTO for API
        """
        # Convert stages
        stages = [
            WorkflowStageResponse(
                name=stage.name,
                agent_name=stage.agent_name,
                timeout_seconds=stage.timeout_seconds,
                retry_count=stage.retry_count,
                entry_conditions=[
                    StageEntryCondition(
                        condition_type=cond.get("condition_type", "unknown"),
                        parameters=cond.get("parameters", {}),
                    )
                    for cond in stage.entry_conditions
                ],
                metadata=stage.metadata,
            )
            for stage in workflow_info.stages
        ]

        # Convert transitions
        transitions = [
            StageTransition(
                from_stage=trans.from_stage,
                to_stage=trans.to_stage,
                condition=trans.condition,
            )
            for trans in workflow_info.transitions
        ]

        return WorkflowResponse(
            id=workflow_info.id,
            name=workflow_info.name,
            description=workflow_info.description,
            project_id=workflow_info.project_id,
            version=workflow_info.version,
            stages=stages,
            transitions=transitions,
            work_item_types=workflow_info.work_item_types,
            is_template=workflow_info.is_template,
            is_active=workflow_info.is_active,
            created_at=workflow_info.created_at,
            updated_at=workflow_info.updated_at,
            metadata=workflow_info.metadata,
        )

    @staticmethod
    def to_summary_response(workflow_summary: WorkflowSummaryInfo) -> WorkflowSummaryResponse:
        """
        Convert WorkflowSummaryInfo to WorkflowSummaryResponse DTO.

        Args:
            workflow_summary: Port-level workflow summary

        Returns:
            Summary response DTO for API
        """
        return WorkflowSummaryResponse(
            id=workflow_summary.id,
            name=workflow_summary.name,
            description=workflow_summary.description,
            project_id=workflow_summary.project_id,
            version=workflow_summary.version,
            stage_count=workflow_summary.stage_count,
            work_item_types=workflow_summary.work_item_types,
            is_template=workflow_summary.is_template,
            is_active=workflow_summary.is_active,
            created_at=workflow_summary.created_at,
            updated_at=workflow_summary.updated_at,
        )

    @staticmethod
    def to_list_response(workflow_list: WorkflowListResult) -> WorkflowListResponse:
        """
        Convert WorkflowListResult to WorkflowListResponse DTO.

        Args:
            workflow_list: Port-level workflow list result

        Returns:
            List response DTO for API
        """
        workflows = [WorkflowMapper.to_summary_response(wf) for wf in workflow_list.workflows]

        return WorkflowListResponse(
            workflows=workflows,
            total_count=workflow_list.total_count,
            page=(workflow_list.offset // workflow_list.limit) + 1 if workflow_list.limit > 0 else 1,
            page_size=workflow_list.limit,
            has_next=workflow_list.has_next,
        )

    @staticmethod
    def to_command_result(result: WorkflowDefinitionCommandResult) -> WorkflowCommandResult:
        """
        Convert WorkflowDefinitionCommandResult to WorkflowCommandResult DTO.

        Args:
            result: Domain command result

        Returns:
            Command result DTO for API
        """
        return WorkflowCommandResult(
            success=result.success,
            workflow_id=result.workflow_id,
            version=result.version,
            message=result.message,
            errors=result.errors,
        )

    @staticmethod
    def to_version_list_response(
        history: WorkflowVersionHistoryResult,
    ) -> WorkflowVersionListResponse:
        """
        Convert WorkflowVersionHistoryResult to WorkflowVersionListResponse DTO.

        Args:
            history: Port-level version history result

        Returns:
            Version list response DTO for API
        """
        versions = [
            WorkflowVersionResponse(
                version=v.version,
                created_at=v.created_at,
                created_by=v.created_by,
                changes_summary=v.changes_summary,
            )
            for v in history.versions
        ]

        return WorkflowVersionListResponse(
            workflow_id=history.workflow_id,
            versions=versions,
            total_count=history.total_count,
        )

    @staticmethod
    def to_validation_response(validation: WorkflowValidationResult) -> WorkflowValidationResponse:
        """
        Convert WorkflowValidationResult to WorkflowValidationResponse DTO.

        Args:
            validation: Port-level validation result

        Returns:
            Validation response DTO for API
        """
        errors = [
            WorkflowValidationError(
                error_type=err.error_type,
                message=err.message,
                stage_name=err.stage_name,
                details=err.details,
            )
            for err in validation.errors
        ]

        return WorkflowValidationResponse(
            is_valid=validation.is_valid,
            errors=errors,
            warnings=validation.warnings,
        )


class OrchestrationMapper:
    """Maps between Orchestration commands/queries and API DTOs"""

    @staticmethod
    def to_start_execution_command(dto: StartWorkflowExecutionRequest) -> StartExecutionCommand:
        """
        Convert StartWorkflowExecutionRequest DTO to StartExecutionCommand.

        Args:
            dto: Request DTO from API

        Returns:
            Domain command object
        """
        # Parse priority
        priority = ExecutionPriority[dto.priority.upper()]

        return StartExecutionCommand(
            work_item_id=dto.work_item_id,
            workflow_id=dto.workflow_id,
            stage_name=dto.stage_name,
            priority=priority,
            context=dto.context,
        )

    @staticmethod
    def to_start_execution_response(
        result: OrchestrationCommandResult,
    ) -> StartWorkflowExecutionResponse:
        """
        Convert OrchestrationCommandResult to StartWorkflowExecutionResponse DTO.

        Args:
            result: Domain command result

        Returns:
            Start execution response DTO for API
        """
        return StartWorkflowExecutionResponse(
            execution_id=result.execution_id,
            workflow_run_id=result.workflow_run_id,
            status=result.status,
            message=result.message,
            started_at=result.started_at or datetime.now(UTC),
        )

    @staticmethod
    def to_execution_response(result: OrchestrationCommandResult) -> WorkflowExecutionResponse:
        """
        Convert OrchestrationCommandResult to WorkflowExecutionResponse DTO.

        Args:
            result: Domain command result

        Returns:
            Execution response DTO for API
        """
        return WorkflowExecutionResponse(
            execution_id=result.execution_id,
            workflow_run_id=result.workflow_run_id,
            work_item_id="",  # Not included in result, would need to query
            workflow_id="",  # Not included in result, would need to query
            status=result.status,
            current_stage=None,  # Not included in result, would need to query
            started_at=result.started_at,
            message=result.message,
        )

    @staticmethod
    def to_entry_condition_validation_response(
        check_result: EntryConditionCheckResult,
    ) -> EntryConditionValidationResponse:
        """
        Convert EntryConditionCheckResult to EntryConditionValidationResponse DTO.

        Args:
            check_result: Port-level condition check result

        Returns:
            Validation response DTO for API
        """
        condition_results = [
            ConditionValidationResult(
                condition_type=detail.get("condition_type", "unknown"),
                is_met=detail.get("is_met", False),
                message=detail.get("message", ""),
                details=detail.get("details", {}),
            )
            for detail in check_result.condition_details
        ]

        return EntryConditionValidationResponse(
            can_start=check_result.can_start,
            stage_name=check_result.stage_name,
            condition_results=condition_results,
            blocking_conditions=check_result.blocking_conditions,
        )

    @staticmethod
    def to_queue_response(execution_list: ExecutionListResult, queue_stats: dict) -> ExecutionQueueResponse:
        """
        Convert ExecutionListResult to ExecutionQueueResponse DTO.

        Args:
            execution_list: Port-level execution list
            queue_stats: Queue statistics

        Returns:
            Queue response DTO for API
        """
        executions = [
            QueuedExecutionInfo(
                execution_id=exec.execution_id,
                workflow_run_id=exec.workflow_run_id,
                work_item_id=exec.work_item_id,
                work_item_title="",  # Would need to be looked up
                workflow_name="",  # Would need to be looked up
                stage_name=exec.stage_name,
                agent_name=exec.agent_name,
                status=exec.status.value,
                priority="MEDIUM",  # Would need to be in the execution data
                queued_at=exec.started_at or datetime.now(UTC),
                started_at=exec.started_at,
                estimated_duration_seconds=int(exec.duration_seconds) if exec.duration_seconds else None,
            )
            for exec in execution_list.executions
        ]

        return ExecutionQueueResponse(
            executions=executions,
            total_count=execution_list.total_count,
            page=execution_list.page,
            page_size=execution_list.page_size,
            has_next=execution_list.has_next,
            queue_stats=queue_stats,
        )
