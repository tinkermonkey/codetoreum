"""
Configuration Command Input Port

This module defines the input port interface for configuration management operations,
including project, agent, pipeline, environment variable, and command mounting configuration.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class UpdateProjectConfigCommand:
    """Command to update project configuration"""

    project_name: str
    updates: dict[str, Any]  # Partial updates
    user_id: str
    reason: str | None = None


@dataclass
class UpdateAgentConfigCommand:
    """Command to update agent configuration"""

    project_name: str
    agent_name: str
    updates: dict[str, Any]
    user_id: str
    reason: str | None = None


@dataclass
class UpdatePipelineConfigCommand:
    """Command to update pipeline configuration"""

    project_name: str
    pipeline_name: str
    updates: dict[str, Any]
    user_id: str
    reason: str | None = None


@dataclass
class AddEnvironmentVariableCommand:
    """Command to add/update project environment variable"""

    project_name: str
    variable_name: str
    variable_value: str
    user_id: str
    is_secret: bool = False  # If true, encrypt storage
    description: str | None = None


@dataclass
class RemoveEnvironmentVariableCommand:
    """Command to remove project environment variable"""

    project_name: str
    variable_name: str
    user_id: str


@dataclass
class MountCommandCommand:
    """Command to mount a command into project agent"""

    project_name: str
    command_name: str
    command_path: str  # Path to command file
    user_id: str
    description: str | None = None


@dataclass
class UnmountCommandCommand:
    """Command to unmount a command from project agent"""

    project_name: str
    command_name: str
    user_id: str


@dataclass
class MountSubAgentCommand:
    """Command to mount a sub-agent into project agent"""

    project_name: str
    subagent_name: str
    subagent_config: dict[str, Any]
    user_id: str
    description: str | None = None


@dataclass
class UnmountSubAgentCommand:
    """Command to unmount a sub-agent from project agent"""

    project_name: str
    subagent_name: str
    user_id: str


@dataclass
class ConfigurationCommandResult:
    """Result of configuration command"""

    success: bool
    config_version: int  # New version number after update
    message: str
    changes_applied: dict[str, Any]  # What actually changed
    errors: list[str] | None = field(default=None)


class IConfigurationCommandPort(ABC):
    """
    Input port for configuration commands.

    This port enables dynamic management of system configuration through
    a web UI or API, replacing static YAML files with database-backed
    configuration.

    Implementations of this port should:
    - Validate configuration updates
    - Delegate to configuration service for persistence
    - Emit appropriate domain events
    - Track configuration versions
    - Handle encryption for secret values
    """

    @abstractmethod
    async def update_project_config(self, command: UpdateProjectConfigCommand) -> ConfigurationCommandResult:
        """
        Updates project configuration.

        Args:
            command: Update command with changes

        Returns:
            Result with new config version

        Raises:
            ProjectNotFoundError: If project doesn't exist
            ValidationError: If updates invalid
            PermissionError: If user lacks permission
        """

    @abstractmethod
    async def update_agent_config(self, command: UpdateAgentConfigCommand) -> ConfigurationCommandResult:
        """
        Updates agent configuration for a project.

        Args:
            command: Update command with agent changes

        Returns:
            Result with new config version

        Raises:
            ProjectNotFoundError: If project doesn't exist
            AgentNotFoundError: If agent doesn't exist
            ValidationError: If updates invalid
            PermissionError: If user lacks permission
        """

    @abstractmethod
    async def update_pipeline_config(self, command: UpdatePipelineConfigCommand) -> ConfigurationCommandResult:
        """
        Updates pipeline configuration for a project.

        Args:
            command: Update command with pipeline changes

        Returns:
            Result with new config version

        Raises:
            ProjectNotFoundError: If project doesn't exist
            PipelineNotFoundError: If pipeline doesn't exist
            ValidationError: If updates invalid
            PermissionError: If user lacks permission
        """

    @abstractmethod
    async def add_environment_variable(self, command: AddEnvironmentVariableCommand) -> ConfigurationCommandResult:
        """
        Adds or updates environment variable for project.

        This supports project-level environment variables that are
        passed to agent containers during execution.

        Args:
            command: Command with environment variable details

        Returns:
            Result with new config version

        Raises:
            ProjectNotFoundError: If project doesn't exist
            ValidationError: If variable name/value invalid
            PermissionError: If user lacks permission
        """

    @abstractmethod
    async def remove_environment_variable(
        self, command: RemoveEnvironmentVariableCommand
    ) -> ConfigurationCommandResult:
        """
        Removes environment variable from project.

        Args:
            command: Command specifying variable to remove

        Returns:
            Result with new config version

        Raises:
            ProjectNotFoundError: If project doesn't exist
            VariableNotFoundError: If variable doesn't exist
            PermissionError: If user lacks permission
        """

    @abstractmethod
    async def mount_command(self, command: MountCommandCommand) -> ConfigurationCommandResult:
        """
        Mounts a command into project agent.

        This enables dynamic command mounting, allowing commands to be
        available to agents during execution.

        Args:
            command: Command with command file details

        Returns:
            Result with new config version

        Raises:
            ProjectNotFoundError: If project doesn't exist
            CommandFileNotFoundError: If command file doesn't exist
            ValidationError: If command file invalid
            PermissionError: If user lacks permission
        """

    @abstractmethod
    async def unmount_command(self, command: UnmountCommandCommand) -> ConfigurationCommandResult:
        """
        Unmounts a command from project agent.

        Args:
            command: Command specifying command to unmount

        Returns:
            Result with new config version

        Raises:
            ProjectNotFoundError: If project doesn't exist
            CommandNotFoundError: If command not mounted
            PermissionError: If user lacks permission
        """

    @abstractmethod
    async def mount_subagent(self, command: MountSubAgentCommand) -> ConfigurationCommandResult:
        """
        Mounts a sub-agent into project agent.

        This enables dynamic sub-agent mounting, allowing specialized
        agents to be available during execution.

        Args:
            command: Command with sub-agent configuration

        Returns:
            Result with new config version

        Raises:
            ProjectNotFoundError: If project doesn't exist
            ValidationError: If sub-agent config invalid
            PermissionError: If user lacks permission
        """

    @abstractmethod
    async def unmount_subagent(self, command: UnmountSubAgentCommand) -> ConfigurationCommandResult:
        """
        Unmounts a sub-agent from project agent.

        Args:
            command: Command specifying sub-agent to unmount

        Returns:
            Result with new config version

        Raises:
            ProjectNotFoundError: If project doesn't exist
            SubAgentNotFoundError: If sub-agent not mounted
            PermissionError: If user lacks permission
        """
