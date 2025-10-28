"""
Configuration Store Output Port

Provides interface for configuration storage and retrieval with versioning,
caching, and search capabilities. Replaces YAML-based configuration with
database-backed configuration.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ProjectConfig:
    """Project configuration aggregate."""
    id: str
    name: str
    github_org: str
    github_repo: str
    tech_stacks: Dict[str, str] = field(default_factory=dict)
    pipelines: List[Dict[str, Any]] = field(default_factory=list)
    testing: Dict[str, Any] = field(default_factory=dict)
    environment_variables: Dict[str, Any] = field(default_factory=dict)
    mounted_commands: Dict[str, Any] = field(default_factory=dict)
    mounted_subagents: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    version: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentConfig:
    """Agent configuration."""
    project_id: str
    agent_name: str
    model: str
    timeout: int
    requires_docker: bool
    makes_code_changes: bool
    mcp_servers: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    constraints: Dict[str, bool] = field(default_factory=dict)
    version: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineConfig:
    """Pipeline configuration."""
    id: str
    project_id: str
    name: str
    stages: List[Dict[str, Any]] = field(default_factory=list)
    triggers: List[str] = field(default_factory=list)
    version: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowTemplate:
    """Workflow template configuration."""
    id: str
    name: str
    description: str
    stages: List[Dict[str, Any]] = field(default_factory=list)
    version: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EnvironmentVariable:
    """Environment variable configuration."""
    name: str
    value: str  # Encrypted if is_secret=True
    is_secret: bool = False
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None


@dataclass
class MountedCommand:
    """Mounted command configuration."""
    name: str
    path: str
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None


@dataclass
class MountedSubAgent:
    """Mounted sub-agent configuration."""
    name: str
    config: Dict[str, Any]
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None


@dataclass
class ConfigVersion:
    """Configuration version metadata."""
    version: int
    changed_at: datetime
    changed_by: str
    change_type: str
    changes: Dict[str, Any]
    reason: Optional[str] = None


class ConfigNotFoundError(Exception):
    """Raised when configuration is not found."""
    pass


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""
    pass


class IConfigStore(ABC):
    """
    Output port interface for configuration storage.

    This port abstracts configuration storage and retrieval with support
    for versioning, caching, search, and history tracking. Production
    implementation uses database storage (e.g., Elasticsearch + Redis),
    while test implementation uses in-memory storage.
    """

    @abstractmethod
    async def get_project_config(self, project_id: str) -> ProjectConfig:
        """
        Get project configuration by ID.

        Args:
            project_id: Project identifier

        Returns:
            ProjectConfig instance

        Raises:
            ConfigNotFoundError: If project doesn't exist
        """
        pass

    @abstractmethod
    async def get_project_config_by_name(self, project_name: str) -> ProjectConfig:
        """
        Get project configuration by name.

        Args:
            project_name: Project name

        Returns:
            ProjectConfig instance

        Raises:
            ConfigNotFoundError: If project doesn't exist
        """
        pass

    @abstractmethod
    async def save_project_config(self, config: ProjectConfig) -> None:
        """
        Save project configuration.

        Creates a new version if config already exists.

        Args:
            config: ProjectConfig to save
        """
        pass

    @abstractmethod
    async def get_agent_config(
        self,
        project_id: str,
        agent_name: str
    ) -> AgentConfig:
        """
        Get agent configuration for a project.

        Args:
            project_id: Project identifier
            agent_name: Agent name

        Returns:
            AgentConfig instance

        Raises:
            ConfigNotFoundError: If agent config doesn't exist
        """
        pass

    @abstractmethod
    async def save_agent_config(self, config: AgentConfig) -> None:
        """
        Save agent configuration.

        Args:
            config: AgentConfig to save
        """
        pass

    @abstractmethod
    async def get_pipeline_config(
        self,
        project_id: str,
        pipeline_name: str
    ) -> PipelineConfig:
        """
        Get pipeline configuration.

        Args:
            project_id: Project identifier
            pipeline_name: Pipeline name

        Returns:
            PipelineConfig instance

        Raises:
            ConfigNotFoundError: If pipeline doesn't exist
        """
        pass

    @abstractmethod
    async def save_pipeline_config(self, config: PipelineConfig) -> None:
        """
        Save pipeline configuration.

        Args:
            config: PipelineConfig to save
        """
        pass

    @abstractmethod
    async def get_workflow_template(self, template_name: str) -> WorkflowTemplate:
        """
        Get workflow template by name.

        Args:
            template_name: Template name

        Returns:
            WorkflowTemplate instance

        Raises:
            ConfigNotFoundError: If template doesn't exist
        """
        pass

    @abstractmethod
    async def save_workflow_template(self, template: WorkflowTemplate) -> None:
        """
        Save workflow template.

        Args:
            template: WorkflowTemplate to save
        """
        pass

    @abstractmethod
    async def list_projects(self) -> List[ProjectConfig]:
        """
        List all projects.

        Returns:
            List of ProjectConfig instances
        """
        pass

    @abstractmethod
    async def list_agents(self, project_id: str) -> List[AgentConfig]:
        """
        List all agents for a project.

        Args:
            project_id: Project identifier

        Returns:
            List of AgentConfig instances
        """
        pass

    @abstractmethod
    async def list_pipelines(self, project_id: str) -> List[PipelineConfig]:
        """
        List all pipelines for a project.

        Args:
            project_id: Project identifier

        Returns:
            List of PipelineConfig instances
        """
        pass

    @abstractmethod
    async def search_configs(
        self,
        query: str,
        config_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search configurations using full-text search.

        Args:
            query: Search query string
            config_type: Optional filter by config type (project, agent, pipeline)

        Returns:
            List of matching configurations
        """
        pass

    @abstractmethod
    async def get_config_version(
        self,
        config_id: str,
        version: int
    ) -> Dict[str, Any]:
        """
        Get specific version of a configuration.

        Args:
            config_id: Configuration identifier
            version: Version number

        Returns:
            Configuration data for specified version

        Raises:
            ConfigNotFoundError: If version doesn't exist
        """
        pass

    @abstractmethod
    async def list_config_versions(
        self,
        config_id: str,
        limit: int = 10
    ) -> List[ConfigVersion]:
        """
        List configuration version history.

        Args:
            config_id: Configuration identifier
            limit: Maximum number of versions to return

        Returns:
            List of ConfigVersion instances, newest first
        """
        pass

    @abstractmethod
    async def delete_project_config(self, project_id: str) -> None:
        """
        Delete project configuration.

        Args:
            project_id: Project identifier

        Raises:
            ConfigNotFoundError: If project doesn't exist
        """
        pass

    @abstractmethod
    async def delete_agent_config(
        self,
        project_id: str,
        agent_name: str
    ) -> None:
        """
        Delete agent configuration.

        Args:
            project_id: Project identifier
            agent_name: Agent name

        Raises:
            ConfigNotFoundError: If agent config doesn't exist
        """
        pass

    @abstractmethod
    async def exists(self, project_id: str) -> bool:
        """
        Check if project configuration exists.

        Args:
            project_id: Project identifier

        Returns:
            True if project exists, False otherwise
        """
        pass
