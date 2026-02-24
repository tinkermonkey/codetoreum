"""
Mock Config Command Adapter

In-memory implementation of IConfigurationCommandPort for development and testing.
"""

from threading import RLock

from codetoreum.ports.input.config_command import (
    AddEnvironmentVariableCommand,
    ConfigurationCommandResult,
    IConfigurationCommandPort,
    MountCommandCommand,
    MountSubAgentCommand,
    RemoveEnvironmentVariableCommand,
    UnmountCommandCommand,
    UnmountSubAgentCommand,
    UpdateAgentConfigCommand,
    UpdatePipelineConfigCommand,
    UpdateProjectConfigCommand,
)


class MockConfigCommandAdapter(IConfigurationCommandPort):
    """
    Mock implementation of IConfigurationCommandPort using in-memory storage.
    """

    def __init__(self, configuration_service=None):
        self._configs: dict[str, dict] = {}
        self._lock = RLock()
        self._service = configuration_service

    async def update_project_config(
        self, command: UpdateProjectConfigCommand
    ) -> ConfigurationCommandResult:
        """Update project configuration."""
        with self._lock:
            return ConfigurationCommandResult(
                success=True,
                config_version=2,
                message="Project config updated",
                changes_applied=command.updates,
            )

    async def update_agent_config(
        self, command: UpdateAgentConfigCommand
    ) -> ConfigurationCommandResult:
        """Update agent configuration."""
        with self._lock:
            return ConfigurationCommandResult(
                success=True,
                config_version=2,
                message="Agent config updated",
                changes_applied=command.updates,
            )

    async def update_pipeline_config(
        self, command: UpdatePipelineConfigCommand
    ) -> ConfigurationCommandResult:
        """Update pipeline configuration."""
        with self._lock:
            return ConfigurationCommandResult(
                success=True,
                config_version=2,
                message="Pipeline config updated",
                changes_applied=command.updates,
            )

    async def add_environment_variable(
        self, command: AddEnvironmentVariableCommand
    ) -> ConfigurationCommandResult:
        """Add an environment variable."""
        with self._lock:
            return ConfigurationCommandResult(
                success=True,
                config_version=2,
                message="Environment variable added",
                changes_applied={command.variable_name: command.variable_value},
            )

    async def remove_environment_variable(
        self, command: RemoveEnvironmentVariableCommand
    ) -> ConfigurationCommandResult:
        """Remove an environment variable."""
        with self._lock:
            return ConfigurationCommandResult(
                success=True,
                config_version=2,
                message="Environment variable removed",
                changes_applied={},
            )

    async def mount_command(
        self, command: MountCommandCommand
    ) -> ConfigurationCommandResult:
        """Mount a command."""
        with self._lock:
            return ConfigurationCommandResult(
                success=True,
                config_version=2,
                message="Command mounted",
                changes_applied={},
            )

    async def unmount_command(
        self, command: UnmountCommandCommand
    ) -> ConfigurationCommandResult:
        """Unmount a command."""
        with self._lock:
            return ConfigurationCommandResult(
                success=True,
                config_version=2,
                message="Command unmounted",
                changes_applied={},
            )

    async def mount_subagent(
        self, command: MountSubAgentCommand
    ) -> ConfigurationCommandResult:
        """Mount a sub-agent."""
        with self._lock:
            return ConfigurationCommandResult(
                success=True,
                config_version=2,
                message="Sub-agent mounted",
                changes_applied={},
            )

    async def unmount_subagent(
        self, command: UnmountSubAgentCommand
    ) -> ConfigurationCommandResult:
        """Unmount a sub-agent."""
        with self._lock:
            return ConfigurationCommandResult(
                success=True,
                config_version=2,
                message="Sub-agent unmounted",
                changes_applied={},
            )

    def clear(self):
        """Clear all data (useful for testing)."""
        with self._lock:
            self._configs.clear()
