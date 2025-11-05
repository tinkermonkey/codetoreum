"""Agents resource client"""
from ..models import Agent, PaginatedResponse


class AgentsResource:
    """Client for agents endpoints."""

    def __init__(self, client):
        self.client = client

    def create(self, name: str, description: str, agent_type: str, **kwargs) -> Agent:
        """Create a new agent."""
        payload = {"name": name, "description": description, "agent_type": agent_type, **kwargs}
        data = self.client.post("/api/v2/agents/", json=payload)
        return Agent.from_dict(data)

    def list(self, **filters) -> PaginatedResponse:
        """List agents with optional filtering."""
        data = self.client.get("/api/v2/agents/", params=filters)
        return PaginatedResponse.from_dict(data, Agent)

    def get(self, agent_id: str) -> Agent:
        """Get agent details."""
        data = self.client.get(f"/api/v2/agents/{agent_id}")
        return Agent.from_dict(data)

    def update(self, agent_id: str, **updates) -> Agent:
        """Update agent."""
        data = self.client.put(f"/api/v2/agents/{agent_id}", json=updates)
        return Agent.from_dict(data)

    def delete(self, agent_id: str) -> dict:
        """Delete agent."""
        return self.client.delete(f"/api/v2/agents/{agent_id}")
