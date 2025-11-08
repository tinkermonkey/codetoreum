"""
Mock Workflow Query Adapter

In-memory implementation of IWorkflowQueryPort for development and testing.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from threading import RLock

from codetoreum.ports.input.workflow_query import (
    IWorkflowQueryPort,
    WorkflowDefinitionInfo,
    WorkflowSummaryInfo,
    WorkflowListResult,
    WorkflowVersionHistoryResult,
    WorkflowVersionInfo,
    WorkflowValidationResult,
    StageInfo,
    StageTransitionInfo,
)


class MockWorkflowQueryAdapter(IWorkflowQueryPort):
    """
    Mock implementation of IWorkflowQueryPort using in-memory storage.
    """

    def __init__(self):
        self._workflows: Dict[str, Dict] = {}
        self._lock = RLock()

    async def get_workflow(
        self, workflow_id: str, version: Optional[int] = None
    ) -> WorkflowDefinitionInfo:
        """Get a workflow definition."""
        return WorkflowDefinitionInfo(
            id=workflow_id,
            name="mock-workflow",
            description="Mock workflow for testing",
            project_id="proj-123",
            version=version or 1,
            stages=[
                StageInfo(
                    name="development",
                    agent_name="software_engineer",
                    timeout_seconds=1800,
                    retry_count=2,
                    entry_conditions=[],
                    metadata={},
                )
            ],
            transitions=[],
            work_item_types=["issue"],
            is_template=False,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            metadata={},
        )

    async def list_workflows(
        self, filters=None, pagination=None
    ) -> WorkflowListResult:
        """List workflows."""
        summary = WorkflowSummaryInfo(
            id="wf-mock-123",
            name="mock-workflow",
            description="Mock workflow",
            project_id="proj-123",
            version=1,
            stage_count=1,
            work_item_types=["issue"],
            is_template=False,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        return WorkflowListResult(
            workflows=[summary],
            total_count=1,
            offset=0,
            limit=20,
            has_next=False,
        )

    async def get_workflow_versions(
        self, workflow_id: str, limit: int = 10
    ) -> WorkflowVersionHistoryResult:
        """Get workflow version history."""
        return WorkflowVersionHistoryResult(
            workflow_id=workflow_id,
            versions=[
                WorkflowVersionInfo(
                    version=1,
                    created_at=datetime.now(timezone.utc),
                    created_by=None,
                    changes_summary="Initial version",
                )
            ],
            total_count=1,
        )

    async def validate_workflow(
        self, workflow_id: str, version: Optional[int] = None
    ) -> WorkflowValidationResult:
        """Validate a workflow."""
        return WorkflowValidationResult(
            is_valid=True,
            errors=[],
            warnings=[],
        )

    async def get_workflows_for_work_item_type(
        self, work_item_type: str, project_id: Optional[str] = None
    ) -> List[WorkflowSummaryInfo]:
        """Get workflows for a work item type."""
        return []

    async def count_active_executions(self, workflow_id: str) -> int:
        """Count active executions for a workflow."""
        return 0

    def clear(self):
        """Clear all data (useful for testing)."""
        with self._lock:
            self._workflows.clear()
