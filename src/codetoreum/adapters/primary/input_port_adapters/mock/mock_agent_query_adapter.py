"""
Mock Agent Query Adapter

In-memory implementation of IAgentQueryPort for development and testing.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from threading import RLock

from codetoreum.ports.input.agent_query import (
    AgentExecutionStats,
    AgentFilters,
    AgentInfo,
    AgentListResult,
    AgentPaginationParams,
    IAgentQueryPort,
)
from codetoreum.domain.agent import Agent
from codetoreum.domain.exceptions import AgentNotFoundError


class MockAgentQueryAdapter(IAgentQueryPort):
    """
    Mock implementation of IAgentQueryPort using in-memory storage.

    This adapter stores agents in a dictionary and provides full query capabilities
    without requiring a database. It's thread-safe and suitable for testing and
    development environments.
    """

    def __init__(self):
        self._agents: Dict[str, AgentInfo] = {}
        self._agents_by_name: Dict[str, str] = {}  # name -> agent_id
        self._execution_stats: Dict[str, AgentExecutionStats] = {}
        self._lock = RLock()

    def add_agent(self, agent: Agent, execution_stats: Optional[AgentExecutionStats] = None):
        """
        Helper method to add an agent to the mock storage.

        Args:
            agent: Agent domain model
            execution_stats: Optional execution statistics
        """
        with self._lock:
            agent_info = self._convert_agent_to_info(agent, execution_stats)
            self._agents[agent.id] = agent_info
            self._agents_by_name[agent.name] = agent.id
            if execution_stats:
                self._execution_stats[agent.id] = execution_stats

    def _convert_agent_to_info(
        self,
        agent: Agent,
        execution_stats: Optional[AgentExecutionStats] = None
    ) -> AgentInfo:
        """Convert Agent domain model to AgentInfo."""
        return AgentInfo(
            id=agent.id,
            name=agent.name,
            display_name=agent.display_name,
            agent_type=agent.agent_type.value,
            role_description=agent.role_description,
            model=agent.model,
            timeout_seconds=agent.timeout_seconds,
            max_retries=agent.max_retries,
            requires_docker=agent.requires_docker,
            requires_dev_container=agent.requires_dev_container,
            makes_code_changes=agent.makes_code_changes,
            filesystem_write_allowed=agent.filesystem_write_allowed,
            mcp_servers=agent.mcp_servers.copy(),
            created_at=agent.created_at,
            updated_at=agent.updated_at,
            capabilities={
                skill: cap.proficiency
                for skill, cap in agent.capabilities.items()
            },
            environment_variables=agent.metadata.get("environment_variables", {}),
            execution_stats=execution_stats,
        )

    async def get_agent(self, agent_id: str, include_stats: bool = False) -> AgentInfo:
        """Get agent by ID."""
        with self._lock:
            if agent_id not in self._agents:
                raise AgentNotFoundError(f"Agent with ID {agent_id} not found")

            agent_info = self._agents[agent_id]

            if include_stats and agent_id in self._execution_stats:
                # Create a copy with stats
                return AgentInfo(
                    id=agent_info.id,
                    name=agent_info.name,
                    display_name=agent_info.display_name,
                    agent_type=agent_info.agent_type,
                    role_description=agent_info.role_description,
                    model=agent_info.model,
                    timeout_seconds=agent_info.timeout_seconds,
                    max_retries=agent_info.max_retries,
                    requires_docker=agent_info.requires_docker,
                    requires_dev_container=agent_info.requires_dev_container,
                    makes_code_changes=agent_info.makes_code_changes,
                    filesystem_write_allowed=agent_info.filesystem_write_allowed,
                    mcp_servers=agent_info.mcp_servers,
                    created_at=agent_info.created_at,
                    updated_at=agent_info.updated_at,
                    capabilities=agent_info.capabilities,
                    environment_variables=agent_info.environment_variables,
                    execution_stats=self._execution_stats.get(agent_id),
                )

            return agent_info

    async def get_agent_by_name(self, name: str, include_stats: bool = False) -> AgentInfo:
        """Get agent by name."""
        with self._lock:
            if name not in self._agents_by_name:
                raise AgentNotFoundError(f"Agent with name '{name}' not found")

            agent_id = self._agents_by_name[name]
            return await self.get_agent(agent_id, include_stats)

    async def list_agents(
        self,
        filters: Optional[AgentFilters] = None,
        pagination: Optional[AgentPaginationParams] = None,
    ) -> AgentListResult:
        """List agents with optional filtering and pagination."""
        with self._lock:
            # Get all agents
            agents = list(self._agents.values())

            # Apply filters
            if filters:
                agents = self._apply_filters(agents, filters)

            # Sort agents
            if pagination:
                agents = self._sort_agents(agents, pagination)

            total_count = len(agents)

            # Apply pagination
            offset = 0
            limit = 20
            if pagination:
                offset = pagination.offset
                limit = pagination.limit

            paginated_agents = agents[offset : offset + limit]
            has_next = (offset + limit) < total_count

            return AgentListResult(
                agents=paginated_agents,
                total_count=total_count,
                offset=offset,
                limit=limit,
                has_next=has_next,
            )

    async def list_agents_by_capability(
        self,
        capability: str,
        min_proficiency: float = 0.0,
        pagination: Optional[AgentPaginationParams] = None,
    ) -> AgentListResult:
        """List agents that have a specific capability."""
        with self._lock:
            # Filter agents by capability
            matching_agents = []
            for agent in self._agents.values():
                if capability in agent.capabilities:
                    proficiency = agent.capabilities[capability]
                    if proficiency >= min_proficiency:
                        matching_agents.append(agent)

            # Sort by proficiency (descending)
            matching_agents.sort(
                key=lambda a: a.capabilities[capability],
                reverse=True,
            )

            total_count = len(matching_agents)

            # Apply pagination
            offset = 0
            limit = 20
            if pagination:
                offset = pagination.offset
                limit = pagination.limit

            paginated_agents = matching_agents[offset : offset + limit]
            has_next = (offset + limit) < total_count

            return AgentListResult(
                agents=paginated_agents,
                total_count=total_count,
                offset=offset,
                limit=limit,
                has_next=has_next,
            )

    async def count_agents(self, filters: Optional[AgentFilters] = None) -> int:
        """Count agents matching filters."""
        with self._lock:
            agents = list(self._agents.values())

            if filters:
                agents = self._apply_filters(agents, filters)

            return len(agents)

    def _apply_filters(self, agents: List[AgentInfo], filters: AgentFilters) -> List[AgentInfo]:
        """Apply filters to agent list."""
        result = agents

        if filters.capability is not None:
            result = [a for a in result if filters.capability in a.capabilities]

        if filters.agent_type is not None:
            result = [a for a in result if a.agent_type == filters.agent_type.value]

        if filters.requires_docker is not None:
            result = [a for a in result if a.requires_docker == filters.requires_docker]

        if filters.makes_code_changes is not None:
            result = [a for a in result if a.makes_code_changes == filters.makes_code_changes]

        return result

    def _sort_agents(
        self,
        agents: List[AgentInfo],
        pagination: AgentPaginationParams,
    ) -> List[AgentInfo]:
        """Sort agents based on pagination parameters."""
        from codetoreum.ports.input.agent_query import AgentSortField, SortOrder

        reverse = pagination.sort_order == SortOrder.DESC

        if pagination.sort_by == AgentSortField.NAME:
            agents.sort(key=lambda a: a.name, reverse=reverse)
        elif pagination.sort_by == AgentSortField.DISPLAY_NAME:
            agents.sort(key=lambda a: a.display_name, reverse=reverse)
        elif pagination.sort_by == AgentSortField.AGENT_TYPE:
            agents.sort(key=lambda a: a.agent_type, reverse=reverse)
        elif pagination.sort_by == AgentSortField.CREATED_AT:
            agents.sort(key=lambda a: a.created_at, reverse=reverse)
        elif pagination.sort_by == AgentSortField.UPDATED_AT:
            agents.sort(key=lambda a: a.updated_at, reverse=reverse)

        return agents

    def clear(self):
        """Clear all agents (useful for testing)."""
        with self._lock:
            self._agents.clear()
            self._agents_by_name.clear()
            self._execution_stats.clear()
