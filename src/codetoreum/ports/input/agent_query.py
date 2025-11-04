"""
Agent Query Port Interface

Defines the contract for querying agent registry information.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional

from codetoreum.domain.agent import Agent, AgentType


# ============================================================================
# Filters and Pagination
# ============================================================================


@dataclass
class AgentFilters:
    """Filters for agent queries."""

    capability: Optional[str] = None
    agent_type: Optional[AgentType] = None
    requires_docker: Optional[bool] = None
    makes_code_changes: Optional[bool] = None


class AgentSortField(Enum):
    """Fields available for sorting agents."""

    NAME = "name"
    DISPLAY_NAME = "display_name"
    AGENT_TYPE = "agent_type"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


class SortOrder(Enum):
    """Sort order enumeration."""

    ASC = "asc"
    DESC = "desc"


@dataclass
class AgentPaginationParams:
    """Pagination parameters for agent list."""

    offset: int = 0
    limit: int = 20
    sort_by: AgentSortField = AgentSortField.UPDATED_AT
    sort_order: SortOrder = SortOrder.DESC


# ============================================================================
# Result Models
# ============================================================================


@dataclass
class AgentExecutionStats:
    """Execution statistics for an agent."""

    total_executions: int
    successful_executions: int
    failed_executions: int
    timeout_executions: int
    average_duration_seconds: Optional[float]
    last_execution_at: Optional[datetime]


@dataclass
class AgentInfo:
    """Agent information for query results."""

    # From Agent domain model
    id: str
    name: str
    display_name: str
    agent_type: str
    role_description: str
    model: str
    timeout_seconds: int
    max_retries: int
    requires_docker: bool
    requires_dev_container: bool
    makes_code_changes: bool
    filesystem_write_allowed: bool
    mcp_servers: List[str]
    created_at: datetime
    updated_at: datetime

    # Capabilities (skill -> proficiency mapping)
    capabilities: dict  # Dict[str, float]

    # Execution stats (optional - may not be loaded for list queries)
    execution_stats: Optional[AgentExecutionStats] = None


@dataclass
class AgentListResult:
    """Result for agent list queries."""

    agents: List[AgentInfo]
    total_count: int
    offset: int
    limit: int
    has_next: bool


# ============================================================================
# Port Interface
# ============================================================================


class IAgentQueryPort(ABC):
    """
    Agent Query Input Port.

    Provides read-only access to agent registry information.
    """

    @abstractmethod
    async def get_agent(self, agent_id: str, include_stats: bool = False) -> AgentInfo:
        """
        Get agent by ID.

        Args:
            agent_id: Agent ID
            include_stats: Whether to include execution statistics

        Returns:
            AgentInfo with agent details

        Raises:
            AgentNotFoundError: If agent doesn't exist
        """
        pass

    @abstractmethod
    async def get_agent_by_name(
        self, name: str, include_stats: bool = False
    ) -> AgentInfo:
        """
        Get agent by name.

        Args:
            name: Agent name (unique identifier)
            include_stats: Whether to include execution statistics

        Returns:
            AgentInfo with agent details

        Raises:
            AgentNotFoundError: If agent doesn't exist
        """
        pass

    @abstractmethod
    async def list_agents(
        self, filters: Optional[AgentFilters] = None, pagination: Optional[AgentPaginationParams] = None
    ) -> AgentListResult:
        """
        List agents with optional filtering and pagination.

        Args:
            filters: Optional filters for agent selection
            pagination: Optional pagination parameters

        Returns:
            AgentListResult with matching agents
        """
        pass

    @abstractmethod
    async def list_agents_by_capability(
        self,
        capability: str,
        min_proficiency: float = 0.0,
        pagination: Optional[AgentPaginationParams] = None,
    ) -> AgentListResult:
        """
        List agents that have a specific capability.

        Args:
            capability: Capability/skill name
            min_proficiency: Minimum proficiency level (0.0 to 1.0)
            pagination: Optional pagination parameters

        Returns:
            AgentListResult with matching agents sorted by proficiency (descending)
        """
        pass

    @abstractmethod
    async def count_agents(self, filters: Optional[AgentFilters] = None) -> int:
        """
        Count agents matching filters.

        Args:
            filters: Optional filters for agent selection

        Returns:
            Count of matching agents
        """
        pass
