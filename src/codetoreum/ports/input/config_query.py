"""
Configuration Query Input Port

This module defines the input port interface for read-only configuration queries,
including fetching project config, search, audit trail, and version history.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class ProjectConfigInfo:
    """Project configuration information"""
    id: str
    name: str
    description: str | None
    github_org: str | None
    github_repo: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    environment_variables: dict[str, str]  # Without sensitive values
    mounted_commands: list[dict[str, Any]]
    mounted_subagents: list[dict[str, Any]]
    metadata: dict[str, Any]


@dataclass
class AgentConfigInfo:
    """Agent configuration information"""
    project_id: str
    agent_name: str
    display_name: str | None
    model: str
    timeout_seconds: int
    max_retries: int
    requires_docker: bool
    requires_dev_container: bool
    makes_code_changes: bool
    filesystem_write_allowed: bool
    version: int
    created_at: datetime
    updated_at: datetime
    mcp_servers: list[dict[str, Any]]
    capabilities: dict[str, Any]
    metadata: dict[str, Any]


@dataclass
class PipelineConfigInfo:
    """Pipeline configuration information"""
    id: str
    project_id: str
    name: str
    description: str | None
    version: int
    stages: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any]


@dataclass
class ConfigVersionInfo:
    """Configuration version history entry"""
    version: int
    created_at: datetime
    created_by: str | None
    changes: dict[str, Any]
    reason: str | None


@dataclass
class ConfigSearchResult:
    """Configuration search result"""
    config_id: str
    config_type: str  # "project", "agent", "pipeline"
    name: str
    description: str | None
    matched_fields: list[str]
    score: float  # Relevance score


@dataclass
class ConfigSearchResults:
    """List of configuration search results"""
    results: list[ConfigSearchResult]
    total_count: int
    query: str
    filters: dict[str, Any]


@dataclass
class PaginationParams:
    """Pagination parameters"""
    offset: int = 0
    limit: int = 20


class IConfigurationQueryPort(ABC):
    """
    Input port for configuration queries.

    This port provides read-only access to system configuration,
    supporting the configuration management UI and API endpoints.
    """

    @abstractmethod
    async def get_project_config(
        self,
        project_id: str,
        include_secrets: bool = False
    ) -> ProjectConfigInfo:
        """
        Get project configuration by ID.

        Args:
            project_id: Project ID
            include_secrets: Whether to include secret values (default: False)

        Returns:
            Project configuration information

        Raises:
            ProjectNotFoundError: If project doesn't exist
        """

    @abstractmethod
    async def get_project_config_by_name(
        self,
        project_name: str,
        include_secrets: bool = False
    ) -> ProjectConfigInfo:
        """
        Get project configuration by name.

        Args:
            project_name: Project name
            include_secrets: Whether to include secret values (default: False)

        Returns:
            Project configuration information

        Raises:
            ProjectNotFoundError: If project doesn't exist
        """

    @abstractmethod
    async def get_agent_config(
        self,
        project_id: str,
        agent_name: str
    ) -> AgentConfigInfo:
        """
        Get agent configuration.

        Args:
            project_id: Project ID
            agent_name: Agent name

        Returns:
            Agent configuration information

        Raises:
            ProjectNotFoundError: If project doesn't exist
            AgentNotFoundError: If agent doesn't exist
        """

    @abstractmethod
    async def get_pipeline_config(
        self,
        project_id: str,
        pipeline_name: str
    ) -> PipelineConfigInfo:
        """
        Get pipeline configuration.

        Args:
            project_id: Project ID
            pipeline_name: Pipeline name

        Returns:
            Pipeline configuration information

        Raises:
            ProjectNotFoundError: If project doesn't exist
            PipelineNotFoundError: If pipeline doesn't exist
        """

    @abstractmethod
    async def list_projects(
        self,
        pagination: PaginationParams | None = None
    ) -> list[ProjectConfigInfo]:
        """
        List all projects.

        Args:
            pagination: Optional pagination parameters

        Returns:
            List of project configurations
        """

    @abstractmethod
    async def list_agents(
        self,
        project_id: str | None = None,
        pagination: PaginationParams | None = None
    ) -> list[AgentConfigInfo]:
        """
        List agents. When project_id is None, returns agents across all projects.

        Args:
            project_id: Project ID (None for all projects)
            pagination: Optional pagination parameters

        Returns:
            List of agent configurations

        Raises:
            ProjectNotFoundError: If project_id is specified and doesn't exist
        """

    @abstractmethod
    async def list_pipelines(
        self,
        project_id: str | None = None,
        pagination: PaginationParams | None = None
    ) -> list[PipelineConfigInfo]:
        """
        List pipelines. When project_id is None, returns pipelines across all projects.

        Args:
            project_id: Project ID (None for all projects)
            pagination: Optional pagination parameters

        Returns:
            List of pipeline configurations

        Raises:
            ProjectNotFoundError: If project_id is specified and doesn't exist
        """

    @abstractmethod
    async def search_configs(
        self,
        query: str,
        config_type: str | None = None,
        project_id: str | None = None,
        pagination: PaginationParams | None = None
    ) -> ConfigSearchResults:
        """
        Search across all configurations using full-text search.

        Args:
            query: Search query string
            config_type: Optional filter by type ("project", "agent", "pipeline")
            project_id: Optional filter by project
            pagination: Optional pagination parameters

        Returns:
            Search results with relevance scores

        Examples:
            - search_configs("authentication") - find all configs mentioning auth
            - search_configs("bug", config_type="workflow") - find workflows for bugs
        """

    @abstractmethod
    async def get_config_version_history(
        self,
        config_id: str,
        config_type: str,
        limit: int = 10
    ) -> list[ConfigVersionInfo]:
        """
        Get version history for a configuration.

        Args:
            config_id: Configuration ID
            config_type: Type of configuration ("project", "agent", "pipeline")
            limit: Maximum number of versions to return (default: 10)

        Returns:
            List of version history entries, newest first

        Raises:
            ConfigNotFoundError: If configuration doesn't exist
        """

    @abstractmethod
    async def get_config_version(
        self,
        config_id: str,
        config_type: str,
        version: int
    ) -> dict[str, Any]:
        """
        Get a specific version of a configuration.

        Args:
            config_id: Configuration ID
            config_type: Type of configuration
            version: Version number to retrieve

        Returns:
            Configuration at specified version

        Raises:
            ConfigNotFoundError: If configuration or version doesn't exist
        """

    @abstractmethod
    async def count_configs(
        self,
        config_type: str | None = None,
        project_id: str | None = None
    ) -> int:
        """
        Count configurations.

        Args:
            config_type: Optional filter by type
            project_id: Optional filter by project

        Returns:
            Count of matching configurations
        """
