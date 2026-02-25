"""
Configuration Store Output Port

Provides interface for configuration storage and retrieval with versioning,
caching, and search capabilities. Replaces YAML-based configuration with
database-backed configuration.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ProjectConfig:
    """Project configuration aggregate."""

    id: str
    name: str
    github_org: str
    github_repo: str
    tech_stacks: dict[str, str] = field(default_factory=dict)
    pipelines: list[dict[str, Any]] = field(default_factory=list)
    testing: dict[str, Any] = field(default_factory=dict)
    environment_variables: dict[str, Any] = field(default_factory=dict)
    mounted_commands: dict[str, Any] = field(default_factory=dict)
    mounted_subagents: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentConfig:
    """Agent configuration."""

    project_id: str
    agent_name: str
    model: str
    timeout: int
    requires_docker: bool
    makes_code_changes: bool
    mcp_servers: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineConfig:
    """Pipeline configuration."""

    id: str
    project_id: str
    name: str
    stages: list[dict[str, Any]] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowTemplate:
    """Workflow template configuration."""

    id: str
    name: str
    description: str
    stages: list[dict[str, Any]] = field(default_factory=list)
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EnvironmentVariable:
    """Environment variable configuration."""

    name: str
    value: str  # Encrypted if is_secret=True
    is_secret: bool = False
    description: str | None = None
    created_at: datetime | None = None
    created_by: str | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None


@dataclass
class MountedCommand:
    """Mounted command configuration."""

    name: str
    path: str
    description: str | None = None
    created_at: datetime | None = None
    created_by: str | None = None


@dataclass
class MountedSubAgent:
    """Mounted sub-agent configuration."""

    name: str
    config: dict[str, Any]
    description: str | None = None
    created_at: datetime | None = None
    created_by: str | None = None


@dataclass
class ConfigVersion:
    """Configuration version metadata."""

    version: int
    changed_at: datetime
    changed_by: str
    change_type: str
    changes: dict[str, Any]
    reason: str | None = None


class ConfigNotFoundError(Exception):
    """Raised when configuration is not found."""


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""


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

    @abstractmethod
    async def save_project_config(self, config: ProjectConfig) -> None:
        """
        Save project configuration.

        Creates a new version if config already exists.

        Args:
            config: ProjectConfig to save
        """

    @abstractmethod
    async def get_agent_config(self, project_id: str, agent_name: str) -> AgentConfig:
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

    @abstractmethod
    async def save_agent_config(self, config: AgentConfig) -> None:
        """
        Save agent configuration.

        Args:
            config: AgentConfig to save
        """

    @abstractmethod
    async def get_pipeline_config(self, project_id: str, pipeline_name: str) -> PipelineConfig:
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

    @abstractmethod
    async def save_pipeline_config(self, config: PipelineConfig) -> None:
        """
        Save pipeline configuration.

        Args:
            config: PipelineConfig to save
        """

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

    @abstractmethod
    async def save_workflow_template(self, template: WorkflowTemplate) -> None:
        """
        Save workflow template.

        Args:
            template: WorkflowTemplate to save
        """

    @abstractmethod
    async def list_projects(self) -> list[ProjectConfig]:
        """
        List all projects.

        Returns:
            List of ProjectConfig instances
        """

    @abstractmethod
    async def list_agents(self, project_id: str) -> list[AgentConfig]:
        """
        List all agents for a project.

        Args:
            project_id: Project identifier

        Returns:
            List of AgentConfig instances
        """

    @abstractmethod
    async def list_pipelines(self, project_id: str) -> list[PipelineConfig]:
        """
        List all pipelines for a project.

        Args:
            project_id: Project identifier

        Returns:
            List of PipelineConfig instances
        """

    @abstractmethod
    async def search_configs(self, query: str, config_type: str | None = None) -> list[dict[str, Any]]:
        """
        Search configurations using full-text search.

        Search Behavior:
        - Case-insensitive matching
        - Partial substring matches supported
        - Multiple space-separated terms are treated as AND search
          (all terms must be present)
        - Searches across all text fields (name, description, metadata, etc.)
        - Results sorted by relevance (most relevant first)

        Example queries:
        - "api gateway" -> matches configs containing both "api" AND "gateway"
        - "claude-sonnet" -> matches configs with "claude-sonnet" in any field
        - "production" -> matches all configs with "production" in any field

        Args:
            query: Search query string (space-separated terms for AND search)
            config_type: Optional filter by config type (project, agent, pipeline)

        Returns:
            List of matching configurations (dictionaries with config data)
        """

    @abstractmethod
    async def get_config_version(self, config_id: str, version: int) -> dict[str, Any]:
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

    @abstractmethod
    async def list_config_versions(self, config_id: str, limit: int = 10) -> list[ConfigVersion]:
        """
        List configuration version history.

        Args:
            config_id: Configuration identifier
            limit: Maximum number of versions to return

        Returns:
            List of ConfigVersion instances, newest first
        """

    @abstractmethod
    async def delete_project_config(self, project_id: str) -> None:
        """
        Delete project configuration.

        Args:
            project_id: Project identifier

        Raises:
            ConfigNotFoundError: If project doesn't exist
        """

    @abstractmethod
    async def delete_agent_config(self, project_id: str, agent_name: str) -> None:
        """
        Delete agent configuration.

        Args:
            project_id: Project identifier
            agent_name: Agent name

        Raises:
            ConfigNotFoundError: If agent config doesn't exist
        """

    @abstractmethod
    async def exists(self, project_id: str) -> bool:
        """
        Check if project configuration exists.

        Args:
            project_id: Project identifier

        Returns:
            True if project exists, False otherwise
        """
