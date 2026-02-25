"""Agents resource client"""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Any

from ..models import Agent, PaginatedResponse

if TYPE_CHECKING:
    from ..client import CodetoreumClient


class AgentsResource:
    """Client for agents endpoints."""

    def __init__(self, client: CodetoreumClient) -> None:
        self.client = client

    def _validate_agent_params(self, name: str, description: str, agent_type: str) -> None:
        """Validate agent creation/update parameters."""
        if not name or not isinstance(name, str) or not name.strip():
            raise ValueError("name must be a non-empty string")

        if not description or not isinstance(description, str) or not description.strip():
            raise ValueError("description must be a non-empty string")

        if not agent_type or not isinstance(agent_type, str) or not agent_type.strip():
            raise ValueError("agent_type must be a non-empty string")

        # Validate agent_type against known types
        valid_types = [
            "senior_software_engineer",
            "code_reviewer",
            "test_engineer",
            "documentation_specialist",
            "devops_engineer",
            "custom"
        ]
        if agent_type not in valid_types:
            raise ValueError(
                f"agent_type must be one of {valid_types}, got '{agent_type}'"
            )

    def create(
        self,
        name: str,
        description: str,
        agent_type: str,
        capabilities: builtins.list[str] | None = None,
        config: dict[str, Any] | None = None,
        **kwargs: Any
    ) -> Agent:
        """
        Create a new agent.

        Args:
            name: Agent name (required, non-empty)
            description: Agent description (required, non-empty)
            agent_type: Agent type - one of: senior_software_engineer, code_reviewer,
                       test_engineer, documentation_specialist, devops_engineer, custom
            capabilities: List of agent capabilities (optional)
            config: Agent configuration dict (optional)
            **kwargs: Additional agent properties

        Returns:
            Created Agent object

        Raises:
            ValueError: If required parameters are missing or invalid
            CodetoreumError: If API request fails

        Example:
            >>> agent = client.agents.create(
            ...     name="Python Expert",
            ...     description="Specializes in Python backend development",
            ...     agent_type="senior_software_engineer",
            ...     capabilities=["python", "fastapi", "sqlalchemy"]
            ... )
        """
        self._validate_agent_params(name, description, agent_type)

        payload: dict[str, Any] = {
            "name": name.strip(),
            "description": description.strip(),
            "agent_type": agent_type,
        }

        if capabilities is not None:
            if not isinstance(capabilities, list):
                raise ValueError("capabilities must be a list")
            payload["capabilities"] = capabilities

        if config is not None:
            if not isinstance(config, dict):
                raise ValueError("config must be a dictionary")
            payload["config"] = config

        payload.update(kwargs)

        data: dict[str, Any] = self.client.post("/api/v2/agents/", json=payload)
        return Agent.from_dict(data)

    def list(
        self,
        agent_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
        **filters: Any
    ) -> PaginatedResponse:
        """
        List agents with optional filtering.

        Args:
            agent_type: Filter by agent type
            status: Filter by status (active, inactive)
            limit: Maximum number of results (default: 100)
            offset: Number of results to skip (default: 0)
            **filters: Additional filter parameters

        Returns:
            PaginatedResponse containing Agent objects

        Example:
            >>> agents = client.agents.list(
            ...     agent_type="senior_software_engineer",
            ...     status="active",
            ...     limit=50
            ... )
            >>> for agent in agents.items:
            ...     print(f"{agent.name}: {agent.description}")
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}

        if agent_type:
            params["agent_type"] = agent_type
        if status:
            params["status"] = status

        params.update(filters)

        data: dict[str, Any] = self.client.get("/api/v2/agents/", params=params)
        return PaginatedResponse.from_dict(data, Agent)

    def get(self, agent_id: str) -> Agent:
        """
        Get agent details by ID.

        Args:
            agent_id: Agent ID

        Returns:
            Agent object

        Raises:
            ValueError: If agent_id is empty
            CodetoreumError: If agent not found or request fails

        Example:
            >>> agent = client.agents.get("agent_123")
            >>> print(f"{agent.name}: {agent.agent_type}")
        """
        if not agent_id or not isinstance(agent_id, str) or not agent_id.strip():
            raise ValueError("agent_id must be a non-empty string")

        data = self.client.get(f"/api/v2/agents/{agent_id}")
        return Agent.from_dict(data)

    def update(
        self,
        agent_id: str,
        name: str | None = None,
        description: str | None = None,
        capabilities: builtins.list[str] | None = None,
        config: dict[str, Any] | None = None,
        status: str | None = None,
        **updates: Any
    ) -> Agent:
        """
        Update an agent.

        Args:
            agent_id: Agent ID
            name: New name (optional)
            description: New description (optional)
            capabilities: Updated capabilities list (optional)
            config: Updated configuration (optional)
            status: New status (active, inactive) (optional)
            **updates: Additional fields to update

        Returns:
            Updated Agent object

        Raises:
            ValueError: If agent_id is empty or parameters are invalid
            CodetoreumError: If agent not found or request fails

        Example:
            >>> agent = client.agents.update(
            ...     "agent_123",
            ...     description="Updated description",
            ...     capabilities=["python", "fastapi", "sqlalchemy", "postgresql"]
            ... )
        """
        if not agent_id or not isinstance(agent_id, str) or not agent_id.strip():
            raise ValueError("agent_id must be a non-empty string")

        payload: dict[str, Any] = {}

        if name is not None:
            if not isinstance(name, str) or not name.strip():
                raise ValueError("name must be a non-empty string")
            payload["name"] = name.strip()

        if description is not None:
            if not isinstance(description, str) or not description.strip():
                raise ValueError("description must be a non-empty string")
            payload["description"] = description.strip()

        if capabilities is not None:
            if not isinstance(capabilities, list):
                raise ValueError("capabilities must be a list")
            payload["capabilities"] = capabilities

        if config is not None:
            if not isinstance(config, dict):
                raise ValueError("config must be a dictionary")
            payload["config"] = config

        if status is not None:
            if status not in ["active", "inactive"]:
                raise ValueError("status must be 'active' or 'inactive'")
            payload["status"] = status

        payload.update(updates)

        if not payload:
            raise ValueError("At least one field must be provided for update")

        data: dict[str, Any] = self.client.put(f"/api/v2/agents/{agent_id}", json=payload)
        return Agent.from_dict(data)

    def delete(self, agent_id: str) -> dict[str, Any]:
        """
        Delete an agent.

        Args:
            agent_id: Agent ID

        Returns:
            Deletion confirmation

        Raises:
            ValueError: If agent_id is empty
            CodetoreumError: If agent not found or request fails

        Example:
            >>> result = client.agents.delete("agent_123")
            >>> print(result["message"])
        """
        if not agent_id or not isinstance(agent_id, str) or not agent_id.strip():
            raise ValueError("agent_id must be a non-empty string")

        result: dict[str, Any] = self.client.delete(f"/api/v2/agents/{agent_id}")
        return result

    def get_executions(
        self,
        agent_id: str,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> PaginatedResponse:
        """
        Get execution history for an agent.

        Args:
            agent_id: Agent ID
            status: Filter by execution status (optional)
            limit: Maximum number of results (default: 100)
            offset: Number of results to skip (default: 0)

        Returns:
            PaginatedResponse containing execution objects

        Raises:
            ValueError: If agent_id is empty
            CodetoreumError: If agent not found or request fails

        Example:
            >>> executions = client.agents.get_executions(
            ...     "agent_123",
            ...     status="completed",
            ...     limit=20
            ... )
        """
        if not agent_id or not isinstance(agent_id, str) or not agent_id.strip():
            raise ValueError("agent_id must be a non-empty string")

        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status

        from ..models import Execution

        data: dict[str, Any] = self.client.get(
            f"/api/v2/agents/{agent_id}/executions", params=params
        )
        return PaginatedResponse.from_dict(data, Execution)
