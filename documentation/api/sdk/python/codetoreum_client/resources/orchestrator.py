"""
Orchestrator resource client
"""
from typing import Optional
from ..models import WorkflowRun


class OrchestratorResource:
    """Client for orchestrator endpoints."""

    def __init__(self, client):
        self.client = client

    def start_workflow(
        self,
        work_item_id: str,
        workflow_id: Optional[str] = None,
    ) -> WorkflowRun:
        """
        Start workflow execution for a work item.

        Args:
            work_item_id: Work item ID
            workflow_id: Optional specific workflow ID (auto-selected if not provided)

        Returns:
            WorkflowRun with run information

        Example:
            >>> run = client.orchestrator.start_workflow("wi_abc123")
            >>> print(f"Started workflow: {run.workflow_run_id}")
        """
        payload = {"work_item_id": work_item_id}

        if workflow_id:
            payload["workflow_id"] = workflow_id

        data = self.client.post("/api/v2/orchestrator/start", json=payload)
        return WorkflowRun.from_dict(data)

    def pause_workflow(self, workflow_run_id: str) -> WorkflowRun:
        """
        Pause a running workflow.

        Args:
            workflow_run_id: Workflow run ID

        Returns:
            Updated WorkflowRun

        Example:
            >>> run = client.orchestrator.pause_workflow("run_abc123")
        """
        data = self.client.post(f"/api/v2/orchestrator/{workflow_run_id}/pause")
        return WorkflowRun.from_dict(data)

    def resume_workflow(self, workflow_run_id: str) -> WorkflowRun:
        """
        Resume a paused workflow.

        Args:
            workflow_run_id: Workflow run ID

        Returns:
            Updated WorkflowRun

        Example:
            >>> run = client.orchestrator.resume_workflow("run_abc123")
        """
        data = self.client.post(f"/api/v2/orchestrator/{workflow_run_id}/resume")
        return WorkflowRun.from_dict(data)

    def cancel_workflow(self, workflow_run_id: str) -> WorkflowRun:
        """
        Cancel a workflow execution.

        Args:
            workflow_run_id: Workflow run ID

        Returns:
            Updated WorkflowRun

        Example:
            >>> run = client.orchestrator.cancel_workflow("run_abc123")
        """
        data = self.client.post(f"/api/v2/orchestrator/{workflow_run_id}/cancel")
        return WorkflowRun.from_dict(data)

    def check_entry_conditions(
        self,
        work_item_id: str,
        stage_name: str,
    ) -> dict:
        """
        Check if entry conditions are met for a stage.

        Args:
            work_item_id: Work item ID
            stage_name: Stage name to check

        Returns:
            Dictionary with conditions_met boolean and details

        Example:
            >>> result = client.orchestrator.check_entry_conditions(
            ...     "wi_abc123",
            ...     "development"
            ... )
            >>> if result["conditions_met"]:
            ...     print("Ready to proceed!")
        """
        payload = {
            "work_item_id": work_item_id,
            "stage_name": stage_name,
        }

        return self.client.post(
            "/api/v2/orchestrator/check-entry-conditions",
            json=payload
        )
