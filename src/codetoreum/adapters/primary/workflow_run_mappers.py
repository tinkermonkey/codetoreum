"""
Workflow Run Mappers

Maps between domain models and DTOs for workflow runs.
"""


from codetoreum.adapters.primary.audit_dtos import (
    AuditStageInfo,
    AuditValidationResult,
    WorkflowRunAuditResponse,
)
from codetoreum.adapters.primary.workflow_run_dtos import (
    WorkflowEventResponse,
    WorkflowEventsListResponse,
    WorkflowRunListResponse,
    WorkflowRunResponse,
    WorkflowRunStageResponse,
    WorkflowRunSummaryResponse,
)
from codetoreum.ports.input.workflow_run_query import (
    WorkflowRunAuditResult,
    WorkflowRunInfo,
    WorkflowRunListResult,
    WorkflowRunStageInfo,
    WorkflowRunSummary,
)


class WorkflowRunMapper:
    """Maps workflow run domain objects to DTOs"""

    @staticmethod
    def to_stage_response(stage: WorkflowRunStageInfo) -> WorkflowRunStageResponse:
        """
        Convert workflow run stage info to response DTO.

        Args:
            stage: Domain workflow run stage info

        Returns:
            WorkflowRunStageResponse DTO
        """
        return WorkflowRunStageResponse(
            name=stage.name,
            agentName=stage.agent_name,
            status=stage.status,
            startedAt=stage.started_at,
            completedAt=stage.completed_at,
            executionId=stage.execution_id,
            output=stage.output,
            errorMessage=stage.error_message,
            metadata=stage.metadata,
        )

    @staticmethod
    def to_summary_response(run: WorkflowRunSummary) -> WorkflowRunSummaryResponse:
        """
        Convert workflow run summary to response DTO.

        Args:
            run: Domain workflow run summary

        Returns:
            WorkflowRunSummaryResponse DTO
        """
        return WorkflowRunSummaryResponse(
            id=run.id,
            workItemId=run.work_item_id,
            workflowId=run.workflow_id,
            projectId=run.project_id,
            status=run.status.value if hasattr(run.status, 'value') else str(run.status),
            currentStageIndex=run.current_stage_index,
            currentStageName=run.current_stage_name,
            startedAt=run.started_at,
            completedAt=run.completed_at,
            duration=run.duration,
            issueTitle=run.issue_title,
            issueNumber=run.issue_number,
            project=run.project,
            triggeredBy=run.triggered_by,
            priority=run.priority,
        )

    @staticmethod
    def to_response(run: WorkflowRunInfo) -> WorkflowRunResponse:
        """
        Convert workflow run info to response DTO.

        Args:
            run: Domain workflow run info

        Returns:
            WorkflowRunResponse DTO
        """
        return WorkflowRunResponse(
            id=run.id,
            workItemId=run.work_item_id,
            workflowId=run.workflow_id,
            projectId=run.project_id,
            status=run.status.value if hasattr(run.status, 'value') else str(run.status),
            stages=[WorkflowRunMapper.to_stage_response(stage) for stage in run.stages],
            metadata=run.metadata,
        )

    @staticmethod
    def to_list_response(result: WorkflowRunListResult) -> WorkflowRunListResponse:
        """
        Convert workflow run list result to response DTO.

        Args:
            result: Domain workflow run list result

        Returns:
            WorkflowRunListResponse DTO
        """
        return WorkflowRunListResponse(
            runs=[WorkflowRunMapper.to_summary_response(run) for run in result.runs],
            total_count=result.total_count,
            page=(result.offset // result.limit) + 1 if result.limit > 0 else 1,
            page_size=result.limit,
            has_next=result.has_next,
        )

    @staticmethod
    def to_event_response(event: dict) -> WorkflowEventResponse:
        """
        Convert event dictionary to workflow event response DTO.

        Args:
            event: Event dictionary

        Returns:
            WorkflowEventResponse DTO
        """
        return WorkflowEventResponse(
            id=event.get("id") or event.get("event_id", ""),
            eventType=event.get("eventType") or event.get("event_type", ""),
            workflowRunId=event.get("workflowRunId") or event.get("workflow_run_id") or event.get("aggregate_id", ""),
            timestamp=event.get("timestamp") or event.get("occurred_at"),
            agentName=event.get("agentName") or event.get("agent_name"),
            stageName=event.get("stageName") or event.get("stage_name"),
            status=event.get("status"),
            data=event.get("data", {}),
        )

    @staticmethod
    def to_events_list_response(events: list[dict], total_count: int, offset: int, limit: int, has_next: bool) -> WorkflowEventsListResponse:
        """
        Convert list of events to events list response DTO.

        Args:
            events: List of event dictionaries
            total_count: Total number of events
            offset: Pagination offset
            limit: Pagination limit
            has_next: Whether there are more events

        Returns:
            WorkflowEventsListResponse DTO
        """
        return WorkflowEventsListResponse(
            events=[WorkflowRunMapper.to_event_response(event) for event in events],
            total_count=total_count,
            page=(offset // limit) + 1 if limit > 0 else 1,
            page_size=limit,
            has_next=has_next,
        )

    @staticmethod
    def to_audit_response(audit_result: WorkflowRunAuditResult) -> WorkflowRunAuditResponse:
        """
        Convert audit result to WorkflowRunAuditResponse DTO.

        Args:
            audit_result: WorkflowRunAuditResult containing:
                - workflow_run: WorkflowRunSummary
                - events: List[event_dict]
                - stages: List[stage_info_dict]
                - validation: validation_result_dict
                - total_count: int
                - offset: int
                - limit: int
                - has_next: bool

        Returns:
            WorkflowRunAuditResponse DTO
        """
        # Convert workflow run summary
        workflow_run_summary = WorkflowRunMapper.to_summary_response(
            audit_result.workflow_run
        )

        # Convert events
        events = [
            WorkflowRunMapper.to_event_response(event)
            for event in audit_result.events
        ]

        # Convert stage info (including nested events)
        stages = []
        for stage_dict in audit_result.stages:
            # Validate required fields with meaningful error messages
            if "name" not in stage_dict:
                raise KeyError(
                    f"Stage dictionary missing required 'name' field. "
                    f"Available keys: {list(stage_dict.keys())}"
                )
            if "status" not in stage_dict:
                raise KeyError(
                    f"Stage dictionary missing required 'status' field for stage '{stage_dict.get('name', 'unknown')}'. "
                    f"Available keys: {list(stage_dict.keys())}"
                )

            # Map events within each stage
            stage_events = [
                WorkflowRunMapper.to_event_response(event)
                for event in stage_dict.get("events", [])
            ]
            # Create stage with mapped events
            stages.append(AuditStageInfo(
                name=stage_dict["name"],
                status=stage_dict["status"],
                startedAt=stage_dict.get("startedAt") or stage_dict.get("started_at"),
                completedAt=stage_dict.get("completedAt") or stage_dict.get("completed_at"),
                durationSeconds=stage_dict.get("durationSeconds") or stage_dict.get("duration_seconds"),
                events=stage_events,
                output=stage_dict.get("output"),
                errorMessage=stage_dict.get("errorMessage") or stage_dict.get("error_message"),
                metadata=stage_dict.get("metadata", {}),
            ))

        # Convert validation result (if present)
        validation = None
        if audit_result.validation is not None:
            try:
                validation = AuditValidationResult(**audit_result.validation)
            except (TypeError, ValueError) as e:
                raise ValueError(
                    f"Failed to construct AuditValidationResult from validation data. "
                    f"Error: {e}. "
                    f"Validation data keys: {list(audit_result.validation.keys()) if isinstance(audit_result.validation, dict) else type(audit_result.validation).__name__}"
                ) from e

        return WorkflowRunAuditResponse(
            workflowRun=workflow_run_summary,
            events=events,
            stages=stages,
            validation=validation,
            totalEventCount=audit_result.total_count,
            offset=audit_result.offset,
            limit=audit_result.limit,
            hasNext=audit_result.has_next,
        )
