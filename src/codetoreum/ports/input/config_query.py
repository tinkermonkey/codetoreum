"""
Configuration Query Input Port

This module defines the input port interface for read-only configuration queries,
including fetching project config, search, audit trail, and version history.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ProjectConfigInfo:
    """Project configuration information"""
    id: str
    name: str
    description: Optional[str]
    github_org: Optional[str]
    github_repo: Optional[str]
    version: int
    created_at: datetime
    updated_at: datetime
    environment_variables: Dict[str, str]  # Without sensitive values
    mounted_commands: List[Dict[str, Any]]
    mounted_subagents: List[Dict[str, Any]]
    metadata: Dict[str, Any]


@dataclass
class AgentConfigInfo:
    """Agent configuration information"""
    project_id: str
    agent_name: str
    display_name: Optional[str]
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
    mcp_servers: List[Dict[str, Any]]
    capabilities: Dict[str, Any]
    metadata: Dict[str, Any]


@dataclass
class PipelineConfigInfo:
    """Pipeline configuration information"""
    id: str
    project_id: str
    name: str
    description: Optional[str]
    version: int
    stages: List[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any]


@dataclass
class ConfigVersionInfo:
    """Configuration version history entry"""
    version: int
    created_at: datetime
    created_by: Optional[str]
    changes: Dict[str, Any]
    reason: Optional[str]


@dataclass
class ConfigSearchResult:
    """Configuration search result"""
    config_id: str
    config_type: str  # "project", "agent", "pipeline"
    name: str
    description: Optional[str]
    matched_fields: List[str]
    score: float  # Relevance score


@dataclass
class ConfigSearchResults:
    """List of configuration search results"""
    results: List[ConfigSearchResult]
    total_count: int
    query: str
    filters: Dict[str, Any]


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
        pass

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
        pass

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
        pass

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
        pass

    @abstractmethod
    async def list_projects(
        self,
        pagination: Optional[PaginationParams] = None
    ) -> List[ProjectConfigInfo]:
        """
        List all projects.

        Args:
            pagination: Optional pagination parameters

        Returns:
            List of project configurations
        """
        pass

    @abstractmethod
    async def list_agents(
        self,
        project_id: Optional[str] = None,
        pagination: Optional[PaginationParams] = None
    ) -> List[AgentConfigInfo]:
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
        pass

    @abstractmethod
    async def list_pipelines(
        self,
        project_id: Optional[str] = None,
        pagination: Optional[PaginationParams] = None
    ) -> List[PipelineConfigInfo]:
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
        pass

    @abstractmethod
    async def search_configs(
        self,
        query: str,
        config_type: Optional[str] = None,
        project_id: Optional[str] = None,
        pagination: Optional[PaginationParams] = None
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
        pass

    @abstractmethod
    async def get_config_version_history(
        self,
        config_id: str,
        config_type: str,
        limit: int = 10
    ) -> List[ConfigVersionInfo]:
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
        pass

    @abstractmethod
    async def get_config_version(
        self,
        config_id: str,
        config_type: str,
        version: int
    ) -> Dict[str, Any]:
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
        pass

    @abstractmethod
    async def count_configs(
        self,
        config_type: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> int:
        """
        Count configurations.

        Args:
            config_type: Optional filter by type
            project_id: Optional filter by project

        Returns:
            Count of matching configurations
        """
        pass
