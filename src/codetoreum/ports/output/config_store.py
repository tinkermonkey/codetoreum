"""
Configuration Store Output Port

Provides interface for configuration storage and retrieval with versioning,
caching, and search capabilities. Replaces YAML-based configuration with
database-backed configuration.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class ProjectConfig:
    """Project configuration aggregate.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation. Dict fields are converted
    to MappingProxyType and list fields to tuples for immutability.
    """

    id: str
    name: str
    github_org: str
    github_repo: str
    tech_stacks: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    pipelines: tuple[dict[str, Any], ...] = ()
    testing: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    environment_variables: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    mounted_commands: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    mounted_subagents: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    created_at: datetime | None = None
    updated_at: datetime | None = None
    version: int = 1
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not isinstance(self.id, str) or not self.id:
            msg = "id must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.name, str) or not self.name:
            msg = "name must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.github_org, str) or not self.github_org:
            msg = "github_org must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.github_repo, str) or not self.github_repo:
            msg = "github_repo must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.tech_stacks, MappingProxyType):
            msg = "tech_stacks must be a MappingProxyType"
            raise ValueError(msg)

        if not isinstance(self.pipelines, tuple):
            msg = "pipelines must be a tuple of dicts"
            raise ValueError(msg)

        if not isinstance(self.testing, MappingProxyType):
            msg = "testing must be a MappingProxyType"
            raise ValueError(msg)

        if not isinstance(self.environment_variables, MappingProxyType):
            msg = "environment_variables must be a MappingProxyType"
            raise ValueError(msg)

        if not isinstance(self.mounted_commands, MappingProxyType):
            msg = "mounted_commands must be a MappingProxyType"
            raise ValueError(msg)

        if not isinstance(self.mounted_subagents, MappingProxyType):
            msg = "mounted_subagents must be a MappingProxyType"
            raise ValueError(msg)

        if self.created_at is not None:
            if not isinstance(self.created_at, datetime):
                msg = "created_at must be a datetime instance or None"
                raise ValueError(msg)

        if self.updated_at is not None:
            if not isinstance(self.updated_at, datetime):
                msg = "updated_at must be a datetime instance or None"
                raise ValueError(msg)

        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            msg = "version must be a positive integer"
            raise ValueError(msg)

        if not isinstance(self.metadata, MappingProxyType):
            msg = "metadata must be a MappingProxyType"
            raise ValueError(msg)


@dataclass(frozen=True)
class AgentConfig:
    """Agent configuration.

    All fields validated at construction. Frozen for immutability.
    Lists converted to tuples, dicts to MappingProxyType.
    """

    project_id: str
    agent_name: str
    model: str
    timeout: int
    requires_docker: bool
    makes_code_changes: bool
    mcp_servers: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    constraints: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        for field_name in ("project_id", "agent_name", "model"):
            val = getattr(self, field_name)
            if not isinstance(val, str) or not val:
                msg = f"{field_name} must be a non-empty string"
                raise ValueError(msg)

        if isinstance(self.timeout, bool) or not isinstance(self.timeout, int) or self.timeout <= 0:
            msg = "timeout must be a positive integer"
            raise ValueError(msg)

        if not isinstance(self.requires_docker, bool) or not isinstance(self.makes_code_changes, bool):
            msg = "requires_docker and makes_code_changes must be booleans"
            raise ValueError(msg)

        if not isinstance(self.mcp_servers, tuple) or not all(isinstance(s, str) for s in self.mcp_servers):
            msg = "mcp_servers must be a tuple of strings"
            raise ValueError(msg)

        if not isinstance(self.capabilities, tuple) or not all(isinstance(c, str) for c in self.capabilities):
            msg = "capabilities must be a tuple of strings"
            raise ValueError(msg)

        if not isinstance(self.constraints, MappingProxyType):
            msg = "constraints must be a MappingProxyType"
            raise ValueError(msg)

        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            msg = "version must be a positive integer"
            raise ValueError(msg)

        if self.metadata is not None and not isinstance(self.metadata, MappingProxyType):
            msg = "metadata must be a MappingProxyType"
            raise ValueError(msg)


@dataclass(frozen=True)
class PipelineConfig:
    """Pipeline configuration.

    All fields validated at construction. Frozen for immutability.
    Lists converted to tuples, dicts to MappingProxyType.
    """

    id: str
    project_id: str
    name: str
    stages: tuple[dict[str, Any], ...] = ()
    triggers: tuple[str, ...] = ()
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        for field_name in ("id", "project_id", "name"):
            val = getattr(self, field_name)
            if not isinstance(val, str) or not val:
                msg = f"{field_name} must be a non-empty string"
                raise ValueError(msg)

        if not isinstance(self.stages, tuple) or not all(isinstance(s, dict) for s in self.stages):
            msg = "stages must be a tuple of dicts"
            raise ValueError(msg)

        if not isinstance(self.triggers, tuple) or not all(isinstance(t, str) for t in self.triggers):
            msg = "triggers must be a tuple of strings"
            raise ValueError(msg)

        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            msg = "version must be a positive integer"
            raise ValueError(msg)

        if not isinstance(self.metadata, MappingProxyType):
            msg = "metadata must be a MappingProxyType"
            raise ValueError(msg)


@dataclass(frozen=True)
class WorkflowTemplate:
    """Workflow template configuration.

    All fields validated at construction. Frozen for immutability.
    Lists converted to tuples, dicts to MappingProxyType.
    """

    id: str
    name: str
    description: str
    stages: tuple[dict[str, Any], ...] = ()
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        for field_name in ("id", "name", "description"):
            val = getattr(self, field_name)
            if not isinstance(val, str) or not val:
                msg = f"{field_name} must be a non-empty string"
                raise ValueError(msg)

        if not isinstance(self.stages, tuple) or not all(isinstance(s, dict) for s in self.stages):
            msg = "stages must be a tuple of dicts"
            raise ValueError(msg)

        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            msg = "version must be a positive integer"
            raise ValueError(msg)

        if not isinstance(self.metadata, MappingProxyType):
            msg = "metadata must be a MappingProxyType"
            raise ValueError(msg)


@dataclass(frozen=True)
class EnvironmentVariable:
    """Environment variable configuration.

    All fields validated at construction. Frozen for immutability.
    """

    name: str
    value: str  # Encrypted if is_secret=True
    is_secret: bool = False
    description: str | None = None
    created_at: datetime | None = None
    created_by: str | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not isinstance(self.name, str) or not self.name:
            msg = "name must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.value, str) or not self.value:
            msg = "value must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.is_secret, bool):
            msg = "is_secret must be a boolean"
            raise ValueError(msg)

        if self.description is not None:
            if not isinstance(self.description, str) or not self.description:
                msg = "description must be a non-empty string or None"
                raise ValueError(msg)

        if self.created_by is not None:
            if not isinstance(self.created_by, str) or not self.created_by:
                msg = "created_by must be a non-empty string or None"
                raise ValueError(msg)

        if self.updated_by is not None:
            if not isinstance(self.updated_by, str) or not self.updated_by:
                msg = "updated_by must be a non-empty string or None"
                raise ValueError(msg)


@dataclass(frozen=True)
class MountedCommand:
    """Mounted command configuration.

    All fields validated at construction. Frozen for immutability.
    """

    name: str
    path: str
    description: str | None = None
    created_at: datetime | None = None
    created_by: str | None = None

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not isinstance(self.name, str) or not self.name:
            msg = "name must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.path, str) or not self.path:
            msg = "path must be a non-empty string"
            raise ValueError(msg)

        if self.description is not None:
            if not isinstance(self.description, str) or not self.description:
                msg = "description must be a non-empty string or None"
                raise ValueError(msg)

        if self.created_by is not None:
            if not isinstance(self.created_by, str) or not self.created_by:
                msg = "created_by must be a non-empty string or None"
                raise ValueError(msg)


@dataclass(frozen=True)
class MountedSubAgent:
    """Mounted sub-agent configuration.

    All fields validated at construction. Frozen for immutability.
    Config dict converted to MappingProxyType for immutability.
    """

    name: str
    config: MappingProxyType
    description: str | None = None
    created_at: datetime | None = None
    created_by: str | None = None

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not isinstance(self.name, str) or not self.name:
            msg = "name must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.config, MappingProxyType):
            msg = "config must be a MappingProxyType"
            raise ValueError(msg)

        if self.description is not None:
            if not isinstance(self.description, str) or not self.description:
                msg = "description must be a non-empty string or None"
                raise ValueError(msg)

        if self.created_by is not None:
            if not isinstance(self.created_by, str) or not self.created_by:
                msg = "created_by must be a non-empty string or None"
                raise ValueError(msg)


@dataclass(frozen=True)
class ConfigVersion:
    """Configuration version metadata.

    All fields validated at construction. Frozen for immutability.
    Changes dict converted to MappingProxyType for immutability.
    """

    version: int
    changed_at: datetime
    changed_by: str
    change_type: str
    changes: MappingProxyType
    reason: str | None = None

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            msg = "version must be a positive integer"
            raise ValueError(msg)

        if not isinstance(self.changed_at, datetime):
            msg = "changed_at must be a datetime instance"
            raise ValueError(msg)

        for field_name in ("changed_by", "change_type"):
            val = getattr(self, field_name)
            if not isinstance(val, str) or not val:
                msg = f"{field_name} must be a non-empty string"
                raise ValueError(msg)

        if not isinstance(self.changes, MappingProxyType):
            msg = "changes must be a MappingProxyType"
            raise ValueError(msg)

        if self.reason is not None:
            if not isinstance(self.reason, str) or not self.reason:
                msg = "reason must be a non-empty string or None"
                raise ValueError(msg)


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
