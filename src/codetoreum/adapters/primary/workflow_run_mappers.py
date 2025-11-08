"""
Workflow Run Mappers

Maps between domain models and DTOs for workflow runs.
"""

from typing import List

from codetoreum.adapters.primary.workflow_run_dtos import (
    WorkflowRunSummaryResponse,
    WorkflowRunResponse,
    WorkflowRunListResponse,
    WorkflowRunStageResponse,
    WorkflowEventResponse,
    WorkflowEventsListResponse,
)
from codetoreum.ports.input.workflow_run_query import (
    WorkflowRunInfo,
    WorkflowRunSummary,
    WorkflowRunListResult,
    WorkflowRunStageInfo,
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
            totalCount=result.total_count,
            offset=result.offset,
            limit=result.limit,
            hasNext=result.has_next,
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
            workflowRunId=event.get("workflowRunId") or event.get("workflow_run_id", ""),
            timestamp=event.get("timestamp") or event.get("occurred_at"),
            agentName=event.get("agentName") or event.get("agent_name"),
            stageName=event.get("stageName") or event.get("stage_name"),
            status=event.get("status"),
            data=event.get("data", {}),
        )

    @staticmethod
    def to_events_list_response(events: List[dict], total_count: int, offset: int, limit: int, has_next: bool) -> WorkflowEventsListResponse:
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
            totalCount=total_count,
            offset=offset,
            limit=limit,
            hasNext=has_next,
        )
