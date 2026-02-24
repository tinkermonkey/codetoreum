"""Workflows resource client"""
from typing import Any, Optional
from ..models import Workflow, PaginatedResponse
from ..exceptions import CodetoreumError


# Type aliases to avoid shadowing the list() method defined in this class
DictAny = dict[str, Any]
ListDictAny = list[dict[str, Any]]


class WorkflowsResource:
    """Client for workflows endpoints."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def _validate_workflow_params(self, name: str, description: str, stages: ListDictAny) -> None:
        """Validate workflow creation parameters."""
        if not name or not isinstance(name, str) or not name.strip():
            raise ValueError("name must be a non-empty string")

        if not description or not isinstance(description, str) or not description.strip():
            raise ValueError("description must be a non-empty string")

        if not isinstance(stages, list) or len(stages) == 0:
            raise ValueError("stages must be a non-empty list")

        # Validate each stage
        for i, stage in enumerate(stages):
            if not isinstance(stage, dict):
                raise ValueError(f"stage {i} must be a dictionary")
            if "name" not in stage or not stage["name"]:
                raise ValueError(f"stage {i} must have a non-empty 'name' field")
            if "agent_id" not in stage or not stage["agent_id"]:
                raise ValueError(f"stage {i} must have a non-empty 'agent_id' field")

    def create(
        self,
        name: str,
        description: str,
        stages: ListDictAny,
        enabled: bool = True,
        **kwargs: Any
    ) -> Workflow:
        """
        Create a workflow definition.

        Args:
            name: Workflow name (required, non-empty)
            description: Workflow description (required, non-empty)
            stages: List of workflow stages (required, non-empty)
                Each stage must have: name, agent_id
                Optional fields: entry_conditions, exit_conditions, timeout_minutes
            enabled: Whether workflow is enabled (default: True)
            **kwargs: Additional workflow properties

        Returns:
            Created Workflow object

        Raises:
            ValueError: If required parameters are missing or invalid
            CodetoreumError: If API request fails

        Example:
            >>> workflow = client.workflows.create(
            ...     name="Standard Development Workflow",
            ...     description="Development, review, and testing stages",
            ...     stages=[
            ...         {
            ...             "name": "development",
            ...             "agent_id": "agent_dev",
            ...             "entry_conditions": {"status": "ready"},
            ...             "timeout_minutes": 120
            ...         },
            ...         {
            ...             "name": "code_review",
            ...             "agent_id": "agent_reviewer",
            ...             "timeout_minutes": 60
            ...         }
            ...     ]
            ... )
        """
        self._validate_workflow_params(name, description, stages)

        payload = {
            "name": name.strip(),
            "description": description.strip(),
            "stages": stages,
            "enabled": enabled,
        }
        payload.update(kwargs)

        data = self.client.post("/api/v2/workflows/", json=payload)
        return Workflow.from_dict(data)

    def list(
        self,
        enabled: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
        **filters: Any
    ) -> PaginatedResponse:
        """
        List workflows.

        Args:
            enabled: Filter by enabled status (optional)
            limit: Maximum number of results (default: 100)
            offset: Number of results to skip (default: 0)
            **filters: Additional filter parameters

        Returns:
            PaginatedResponse containing Workflow objects

        Example:
            >>> workflows = client.workflows.list(enabled=True, limit=50)
            >>> for workflow in workflows.items:
            ...     print(f"{workflow.name}: {len(workflow.stages)} stages")
        """
        params: DictAny = {"limit": limit, "offset": offset}

        if enabled is not None:
            params["enabled"] = enabled

        params.update(filters)

        data = self.client.get("/api/v2/workflows/", params=params)
        return PaginatedResponse.from_dict(data, Workflow)

    def get(self, workflow_id: str) -> Workflow:
        """
        Get workflow definition by ID.

        Args:
            workflow_id: Workflow ID

        Returns:
            Workflow object

        Raises:
            ValueError: If workflow_id is empty
            CodetoreumError: If workflow not found or request fails

        Example:
            >>> workflow = client.workflows.get("workflow_123")
            >>> print(f"{workflow.name}: {workflow.description}")
            >>> for stage in workflow.stages:
            ...     print(f"  - {stage['name']}")
        """
        if not workflow_id or not isinstance(workflow_id, str) or not workflow_id.strip():
            raise ValueError("workflow_id must be a non-empty string")

        data = self.client.get(f"/api/v2/workflows/{workflow_id}")
        return Workflow.from_dict(data)

    def update(
        self,
        workflow_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        stages: Optional[ListDictAny] = None,
        enabled: Optional[bool] = None,
        **updates: Any
    ) -> Workflow:
        """
        Update workflow definition.

        Args:
            workflow_id: Workflow ID
            name: New name (optional)
            description: New description (optional)
            stages: Updated stages list (optional)
            enabled: New enabled status (optional)
            **updates: Additional fields to update

        Returns:
            Updated Workflow object

        Raises:
            ValueError: If workflow_id is empty or parameters are invalid
            CodetoreumError: If workflow not found or request fails

        Example:
            >>> workflow = client.workflows.update(
            ...     "workflow_123",
            ...     description="Updated description",
            ...     enabled=True
            ... )
        """
        if not workflow_id or not isinstance(workflow_id, str) or not workflow_id.strip():
            raise ValueError("workflow_id must be a non-empty string")

        payload: DictAny = {}

        if name is not None:
            if not isinstance(name, str) or not name.strip():
                raise ValueError("name must be a non-empty string")
            payload["name"] = name.strip()

        if description is not None:
            if not isinstance(description, str) or not description.strip():
                raise ValueError("description must be a non-empty string")
            payload["description"] = description.strip()

        if stages is not None:
            if not isinstance(stages, list) or len(stages) == 0:
                raise ValueError("stages must be a non-empty list")
            payload["stages"] = stages

        if enabled is not None:
            if not isinstance(enabled, bool):
                raise ValueError("enabled must be a boolean")
            payload["enabled"] = enabled

        payload.update(updates)

        if not payload:
            raise ValueError("At least one field must be provided for update")

        data = self.client.put(f"/api/v2/workflows/{workflow_id}", json=payload)
        return Workflow.from_dict(data)

    def delete(self, workflow_id: str) -> DictAny:
        """
        Delete workflow definition.

        Args:
            workflow_id: Workflow ID

        Returns:
            Deletion confirmation

        Raises:
            ValueError: If workflow_id is empty
            CodetoreumError: If workflow not found or request fails

        Example:
            >>> result = client.workflows.delete("workflow_123")
            >>> print(result["message"])
        """
        if not workflow_id or not isinstance(workflow_id, str) or not workflow_id.strip():
            raise ValueError("workflow_id must be a non-empty string")

        result = self.client.delete(f"/api/v2/workflows/{workflow_id}")
        return result if isinstance(result, dict) else {}

    def get_runs(
        self,
        workflow_id: str,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> PaginatedResponse:
        """
        Get workflow execution runs for a specific workflow.

        Args:
            workflow_id: Workflow ID
            status: Filter by run status (optional)
            limit: Maximum number of results (default: 100)
            offset: Number of results to skip (default: 0)

        Returns:
            PaginatedResponse containing workflow run objects

        Raises:
            ValueError: If workflow_id is empty
            CodetoreumError: If workflow not found or request fails

        Example:
            >>> runs = client.workflows.get_runs(
            ...     "workflow_123",
            ...     status="running",
            ...     limit=20
            ... )
        """
        if not workflow_id or not isinstance(workflow_id, str) or not workflow_id.strip():
            raise ValueError("workflow_id must be a non-empty string")

        params: DictAny = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status

        from ..models import WorkflowRun
        data = self.client.get(f"/api/v2/workflows/{workflow_id}/runs", params=params)
        return PaginatedResponse.from_dict(data, WorkflowRun)
