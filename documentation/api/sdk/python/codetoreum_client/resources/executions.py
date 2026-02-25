"""
Executions resource client
"""
from typing import TYPE_CHECKING, Any, Callable, List, Optional, cast

from ..models import Execution, PaginatedResponse

if TYPE_CHECKING:
    from ..client import CodetoreumClient


class ExecutionsResource:
    """Client for executions endpoints."""

    def __init__(self, client: "CodetoreumClient") -> None:
        self.client = client

    def list(  # noqa: A003
        self,
        status: Optional[str] = None,
        work_item_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        workflow_run_id: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
        sort_by: str = "started_at",
        sort_order: str = "desc",
    ) -> PaginatedResponse:
        """
        List agent executions with filtering and pagination.

        Args:
            status: Filter by status (pending, running, completed, failed, cancelled)
            work_item_id: Filter by work item
            agent_id: Filter by agent
            workflow_run_id: Filter by workflow run
            offset: Number of items to skip
            limit: Maximum items to return
            sort_by: Field to sort by
            sort_order: Sort order (asc or desc)

        Returns:
            PaginatedResponse with Execution objects

        Example:
            >>> response = client.executions.list(status="running")
            >>> for execution in response.items:
            ...     print(f"{execution.id}: {execution.status}")
        """
        params = {
            "offset": offset,
            "limit": limit,
            "sort_by": sort_by,
            "sort_order": sort_order,
        }

        if status:
            params["status"] = status
        if work_item_id:
            params["work_item_id"] = work_item_id
        if agent_id:
            params["agent_id"] = agent_id
        if workflow_run_id:
            params["workflow_run_id"] = workflow_run_id

        data: dict[str, Any] = self.client.get("/api/v2/executions/", params=params)
        return PaginatedResponse.from_dict(data, Execution)

    def get(self, execution_id: str) -> Execution:
        """
        Get detailed information about a specific execution.

        Args:
            execution_id: Execution ID

        Returns:
            Execution with current status and progress

        Example:
            >>> execution = client.executions.get("exec_abc123")
            >>> print(f"Status: {execution.status}")
        """
        data: dict[str, Any] = self.client.get(f"/api/v2/executions/{execution_id}")
        return Execution.from_dict(data)

    def get_logs(
        self,
        execution_id: str,
        tail: Optional[int] = None,
    ) -> List[str]:
        """
        Get execution logs.

        Args:
            execution_id: Execution ID
            tail: Return only last N lines

        Returns:
            List of log lines

        Example:
            >>> logs = client.executions.get_logs("exec_abc123", tail=50)
            >>> for log in logs:
            ...     print(log)
        """
        params: dict[str, int] = {}
        if tail is not None:
            params["tail"] = tail

        data: dict[str, Any] = self.client.get(f"/api/v2/executions/{execution_id}/logs", params=params)
        return cast(List[str], data.get("logs", []))

    def get_history(self, execution_id: str) -> List[dict[str, Any]]:
        """
        Get execution event history.

        Args:
            execution_id: Execution ID

        Returns:
            List of execution events

        Example:
            >>> history = client.executions.get_history("exec_abc123")
        """
        data: dict[str, Any] = self.client.get(f"/api/v2/executions/{execution_id}/history")
        return cast(List[dict[str, Any]], data.get("events", []))

    def terminate(self, execution_id: str) -> Execution:
        """
        Terminate a running execution.

        Args:
            execution_id: Execution ID

        Returns:
            Updated Execution

        Example:
            >>> execution = client.executions.terminate("exec_abc123")
        """
        data: dict[str, Any] = self.client.post(f"/api/v2/executions/{execution_id}/terminate")
        return Execution.from_dict(data)

    def pause(self, execution_id: str) -> Execution:
        """
        Pause a running execution.

        Args:
            execution_id: Execution ID

        Returns:
            Updated Execution

        Example:
            >>> execution = client.executions.pause("exec_abc123")
        """
        data: dict[str, Any] = self.client.post(f"/api/v2/executions/{execution_id}/pause")
        return Execution.from_dict(data)

    def resume(self, execution_id: str) -> Execution:
        """
        Resume a paused execution.

        Args:
            execution_id: Execution ID

        Returns:
            Updated Execution

        Example:
            >>> execution = client.executions.resume("exec_abc123")
        """
        data: dict[str, Any] = self.client.post(f"/api/v2/executions/{execution_id}/resume")
        return Execution.from_dict(data)

    def wait_for_completion(
        self,
        execution_id: str,
        check_interval: int = 5,
        timeout: int = 3600,
        callback: Optional[Callable[[Execution], None]] = None,
    ) -> Execution:
        """
        Wait for an execution to complete.

        Args:
            execution_id: Execution ID
            check_interval: Seconds between status checks
            timeout: Maximum seconds to wait
            callback: Optional callback function called on each check with Execution

        Returns:
            Final Execution status

        Raises:
            TimeoutError: If execution doesn't complete within timeout

        Example:
            >>> def on_progress(execution):
            ...     if execution.progress:
            ...         print(f"Progress: {execution.progress['percentage']}%")
            >>>
            >>> execution = client.executions.wait_for_completion(
            ...     "exec_abc123",
            ...     callback=on_progress
            ... )
        """
        import time

        start_time: float = time.time()

        while True:
            if time.time() - start_time > timeout:
                raise TimeoutError(
                    f"Execution {execution_id} did not complete within {timeout}s"
                )

            execution: Execution = self.get(execution_id)

            if callback:
                callback(execution)

            if execution.status in ["completed", "failed", "cancelled"]:
                return execution

            time.sleep(check_interval)
