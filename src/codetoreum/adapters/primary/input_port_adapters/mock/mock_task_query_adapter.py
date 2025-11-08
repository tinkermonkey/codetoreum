"""
Mock Task Query Adapter

In-memory implementation of ITaskQueryPort for development and testing.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from threading import RLock

from codetoreum.ports.input.task_query import (
    ITaskQueryPort,
    ExecutionStatusInfo,
    ExecutionStatus,
    ExecutionListResult,
    ExecutionListItem,
    ArtifactListResult,
    ArtifactInfo,
    ExecutionHistory,
    ExecutionHistoryEntry,
)


class MockTaskQueryAdapter(ITaskQueryPort):
    """
    Mock implementation of ITaskQueryPort using in-memory storage.
    """

    def __init__(self):
        self._executions: Dict[str, Dict] = {}
        self._lock = RLock()

    async def get_execution_status(
        self, execution_id: str
    ) -> ExecutionStatusInfo:
        """Get execution status."""
        return ExecutionStatusInfo(
            execution_id=execution_id,
            workflow_run_id="mock-workflow-123",
            work_item_id="123",
            project_name="test-project",
            pipeline_name="test-pipeline",
            stage_name="test-stage",
            agent_name="test-agent",
            status=ExecutionStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            duration_seconds=10.5,
        )

    async def list_executions(
        self,
        workflow_run_id: Optional[str] = None,
        work_item_id: Optional[str] = None,
        project_name: Optional[str] = None,
        status: Optional[ExecutionStatus] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> ExecutionListResult:
        """List executions."""
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
        artifact_type: Optional[str] = None,
    ) -> ArtifactListResult:
        """Get execution artifacts."""
        return ArtifactListResult(artifacts=[], total_count=0)

    async def get_execution_history(
        self,
        execution_id: str,
        limit: Optional[int] = None,
    ) -> ExecutionHistory:
        """Get execution history."""
        return ExecutionHistory(
            execution_id=execution_id,
            entries=[],
            total_entries=0,
        )

    async def get_workflow_executions(
        self, workflow_run_id: str
    ) -> ExecutionListResult:
        """Get all executions for a workflow run."""
        return ExecutionListResult(
            executions=[],
            total_count=0,
            page=1,
            page_size=50,
            has_next=False,
        )

    def clear(self):
        """Clear all data (useful for testing)."""
        with self._lock:
            self._executions.clear()
