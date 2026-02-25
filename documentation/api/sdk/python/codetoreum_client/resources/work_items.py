"""
Work items resource client
"""
from __future__ import annotations

import builtins
from typing import Any, List, Optional

from ..models import PaginatedResponse, WorkItem


class WorkItemsResource:
    """Client for work items endpoints."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def create(
        self,
        title: str,
        description: str,
        project_id: str,
        labels: Optional[List[str]] = None,
        priority: str = "medium",
        status: str = "pending",
        external_id: Optional[str] = None,
    ) -> WorkItem:
        """
        Create a new work item.

        Args:
            title: Work item title
            description: Detailed description
            project_id: Project identifier
            labels: List of labels
            priority: Priority (low, medium, high, critical)
            status: Initial status
            external_id: External ticket ID (e.g., GitHub issue number)

        Returns:
            Created WorkItem

        Example:
            >>> work_item = client.work_items.create(
            ...     title="Add authentication",
            ...     description="Implement JWT auth",
            ...     project_id="my-project",
            ...     labels=["feature", "security"]
            ... )
        """
        payload: dict[str, Any] = {
            "title": title,
            "description": description,
            "project_id": project_id,
            "labels": labels or [],
            "priority": priority,
            "status": status,
        }

        if external_id:
            payload["external_id"] = external_id

        data = self.client.post("/api/v2/work-items/", json=payload)
        return WorkItem.from_dict(data)

    def list(
        self,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        labels: Optional[List[str]] = None,
        offset: int = 0,
        limit: int = 50,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> PaginatedResponse:
        """
        List work items with filtering and pagination.

        Args:
            project_id: Filter by project
            status: Filter by status
            assignee: Filter by assignee
            labels: Filter by labels
            offset: Number of items to skip
            limit: Maximum items to return
            sort_by: Field to sort by
            sort_order: Sort order (asc or desc)

        Returns:
            PaginatedResponse with WorkItem objects

        Example:
            >>> response = client.work_items.list(
            ...     status="pending",
            ...     limit=10
            ... )
            >>> for work_item in response.items:
            ...     print(work_item.title)
        """
        params: dict[str, Any] = {
            "offset": offset,
            "limit": limit,
            "sort_by": sort_by,
            "sort_order": sort_order,
        }

        if project_id:
            params["project_id"] = project_id
        if status:
            params["status"] = status
        if assignee:
            params["assignee"] = assignee
        if labels:
            params["labels"] = ",".join(labels)

        data = self.client.get("/api/v2/work-items/", params=params)
        return PaginatedResponse.from_dict(data, WorkItem)

    def get(self, work_item_id: str) -> WorkItem:
        """
        Get a specific work item.

        Args:
            work_item_id: Work item ID

        Returns:
            WorkItem

        Example:
            >>> work_item = client.work_items.get("wi_abc123")
        """
        data = self.client.get(f"/api/v2/work-items/{work_item_id}")
        return WorkItem.from_dict(data)

    def update(
        self,
        work_item_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        labels: Optional[List[str]] = None,
        priority: Optional[str] = None,
        workflow_stage: Optional[str] = None,
    ) -> WorkItem:
        """
        Update a work item.

        Args:
            work_item_id: Work item ID
            title: New title
            description: New description
            status: New status
            assignee: New assignee
            labels: New labels
            priority: New priority
            workflow_stage: New workflow stage

        Returns:
            Updated WorkItem

        Example:
            >>> work_item = client.work_items.update(
            ...     "wi_abc123",
            ...     status="in_progress",
            ...     assignee="agent-backend-dev"
            ... )
        """
        payload: dict[str, Any] = {}

        if title is not None:
            payload["title"] = title
        if description is not None:
            payload["description"] = description
        if status is not None:
            payload["status"] = status
        if assignee is not None:
            payload["assignee"] = assignee
        if labels is not None:
            payload["labels"] = labels
        if priority is not None:
            payload["priority"] = priority
        if workflow_stage is not None:
            payload["workflow_stage"] = workflow_stage

        data = self.client.put(f"/api/v2/work-items/{work_item_id}", json=payload)
        return WorkItem.from_dict(data)

    def delete(self, work_item_id: str) -> dict[str, Any]:
        """
        Delete a work item.

        Args:
            work_item_id: Work item ID

        Returns:
            Deletion confirmation

        Example:
            >>> client.work_items.delete("wi_abc123")
        """
        result: dict[str, Any] = self.client.delete(f"/api/v2/work-items/{work_item_id}")
        return result

    def get_history(self, work_item_id: str) -> builtins.list[dict[str, Any]]:
        """
        Get change history for a work item.

        Args:
            work_item_id: Work item ID

        Returns:
            List of history entries

        Example:
            >>> history = client.work_items.get_history("wi_abc123")
        """
        data: dict[str, Any] = self.client.get(f"/api/v2/work-items/{work_item_id}/history")
        result: builtins.list[dict[str, Any]] = data.get("history", [])
        return result
