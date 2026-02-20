"""
Mock Workflow Run Query Adapter

In-memory implementation of IWorkflowRunQueryPort for development and testing.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from threading import RLock

from codetoreum.ports.input.workflow_run_query import (
    IWorkflowRunQueryPort,
    WorkflowRunInfo,
    WorkflowRunStatus,
    WorkflowRunStageInfo,
    WorkflowRunSummary,
    WorkflowRunListResult,
    WorkflowRunFilters,
    WorkflowRunPaginationParams,
)


class MockWorkflowRunQueryAdapter(IWorkflowRunQueryPort):
    """
    Mock implementation of IWorkflowRunQueryPort using in-memory storage.
    """

    def __init__(self):
        self._runs: Dict[str, Dict] = {}
        self._lock = RLock()

    async def get_workflow_run(self, workflow_run_id: str) -> WorkflowRunInfo:
        """Get a workflow run by ID."""
        return WorkflowRunInfo(
            id=workflow_run_id,
            work_item_id="wi-mock-123",
            workflow_id="wf-mock-123",
            project_id="proj-123",
            status=WorkflowRunStatus.RUNNING,
            current_stage_index=1,
            current_stage_name="review",
            stages=[
                WorkflowRunStageInfo(
                    name="implementation",
                    agent_name="developer_agent",
                    status="completed",
                    started_at=datetime.now(timezone.utc),
                    completed_at=datetime.now(timezone.utc),
                    execution_id="exec-111",
                ),
                WorkflowRunStageInfo(
                    name="review",
                    agent_name="reviewer_agent",
                    status="running",
                    started_at=datetime.now(timezone.utc),
                    completed_at=None,
                    execution_id="exec-222",
                ),
            ],
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            duration=None,
            issue_title="Fix authentication bug",
            issue_number=42,
            project="codetoreum",
            triggered_by="github_webhook",
            priority="high",
            metadata={},
        )

    async def list_workflow_runs(
        self,
        filters: Optional[WorkflowRunFilters] = None,
        pagination: Optional[WorkflowRunPaginationParams] = None,
    ) -> WorkflowRunListResult:
        """List workflow runs."""
        return WorkflowRunListResult(
            runs=[
                WorkflowRunSummary(
                    id="wfrun-mock-123",
                    work_item_id="wi-mock-123",
                    workflow_id="wf-mock-123",
                    project_id="proj-123",
                    status=WorkflowRunStatus.RUNNING,
                    current_stage_index=1,
                    current_stage_name="review",
                    started_at=datetime.now(timezone.utc),
                    completed_at=None,
                    duration=None,
                    issue_title="Fix authentication bug",
                    issue_number=42,
                    project="codetoreum",
                    triggered_by="github_webhook",
                    priority="high",
                )
            ],
            total_count=1,
            offset=pagination.offset if pagination else 0,
            limit=pagination.limit if pagination else 20,
            has_next=False,
        )

    async def get_workflow_run_events(
        self,
        workflow_run_id: str,
        offset: int = 0,
        limit: int = 50,
        event_types: Optional[List[str]] = None,
        since: Optional[datetime] = None,
    ) -> Dict:
        """Get events for a workflow run."""
        return {
            "events": [
                {
                    "id": "evt-mock-123",
                    "event_type": "WorkflowStarted",
                    "workflow_run_id": workflow_run_id,
                    "timestamp": datetime.now(timezone.utc),
                    "agent_name": None,
                    "stage_name": "implementation",
                    "status": None,
                    "data": {
                        "work_item_id": "wi-mock-123",
                        "triggered_by": "github_webhook",
                    },
                }
            ],
            "totalCount": 1,
            "offset": offset,
            "limit": limit,
            "hasNext": False,
        }

    async def get_workflow_run_audit(
        self,
        workflow_run_id: str,
        offset: int = 0,
        limit: int = 100,
    ) -> Dict:
        """Get comprehensive audit information for a workflow run."""
        # Mock workflow run summary
        workflow_run = WorkflowRunSummary(
            id=workflow_run_id,
            work_item_id="wi-mock-123",
            workflow_id="wf-mock-123",
            project_id="proj-123",
            status=WorkflowRunStatus.COMPLETED,
            current_stage_index=2,
            current_stage_name="merge",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            duration=300,
            issue_title="Fix authentication bug",
            issue_number=42,
            project="codetoreum",
            triggered_by="github_webhook",
            priority="high",
        )

        # Mock events
        mock_events = [
            {
                "id": "evt-1",
                "event_type": "WorkflowCreated",
                "aggregate_id": workflow_run_id,
                "aggregate_type": "Workflow",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": {"work_item_id": "wi-mock-123"},
                "correlation_id": None,
                "causation_id": None,
                "user_id": None,
                "metadata": {},
            },
            {
                "id": "evt-2",
                "event_type": "WorkflowStarted",
                "aggregate_id": workflow_run_id,
                "aggregate_type": "Workflow",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": {"first_stage": "implementation"},
                "correlation_id": None,
                "causation_id": None,
                "user_id": None,
                "metadata": {},
            },
            {
                "id": "evt-3",
                "event_type": "WorkflowCompleted",
                "aggregate_id": workflow_run_id,
                "aggregate_type": "Workflow",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": {"duration_seconds": 300},
                "correlation_id": None,
                "causation_id": None,
                "user_id": None,
                "metadata": {},
            },
        ]

        # Apply pagination
        paginated_events = mock_events[offset : offset + limit]

        # Mock stages
        stages = [
            {
                "name": "implementation",
                "status": "completed",
                "startedAt": datetime.now(timezone.utc).isoformat(),
                "completedAt": datetime.now(timezone.utc).isoformat(),
                "durationSeconds": 150.0,
                "events": [mock_events[1]],
            },
            {
                "name": "review",
                "status": "completed",
                "startedAt": datetime.now(timezone.utc).isoformat(),
                "completedAt": datetime.now(timezone.utc).isoformat(),
                "durationSeconds": 100.0,
                "events": [],
            },
        ]

        # Mock validation
        validation = {
            "sequenceValid": True,
            "expectedSequence": ["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"],
            "actualSequence": ["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"],
            "missingEvents": [],
            "unexpectedEvents": [],
            "outOfOrderEvents": [],
        }

        return {
            "workflow_run": workflow_run,
            "events": paginated_events,
            "stages": stages,
            "validation": validation,
            "total_event_count": len(mock_events),
            "offset": offset,
            "limit": limit,
            "has_next": (offset + limit) < len(mock_events),
        }

    def clear(self):
        """Clear all data (useful for testing)."""
        with self._lock:
            self._runs.clear()
