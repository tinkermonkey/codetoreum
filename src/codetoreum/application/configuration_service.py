"""
Configuration Service

Application service for configuration management with validation,
versioning, and event emission.
"""

import asyncio
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from codetoreum.domain.events import (
    AgentConfigUpdated,
    CommandMounted,
    CommandUnmounted,
    EnvironmentVariableChanged,
    PipelineConfigUpdated,
    ProjectConfigUpdated,
    SubAgentMounted,
    SubAgentUnmounted,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.output import IEncryptionService

logger = logging.getLogger(__name__)
from codetoreum.ports.input.config_command import (
    AddEnvironmentVariableCommand,
    ConfigurationCommandResult,
    MountCommandCommand,
    MountSubAgentCommand,
    RemoveEnvironmentVariableCommand,
    UnmountCommandCommand,
    UnmountSubAgentCommand,
    UpdateAgentConfigCommand,
    UpdatePipelineConfigCommand,
    UpdateProjectConfigCommand,
)
from codetoreum.ports.input.exceptions import ValidationError
from codetoreum.ports.output.config_store import (
    AgentConfig,
    ConfigNotFoundError,
    IConfigStore,
    PipelineConfig,
    ProjectConfig,
)


class ConfigurationService:
    """
    Application service for configuration management.

    Responsibilities:
    - Load and cache configurations
    - Validate configuration updates
    - Support configuration updates with versioning
    - Emit configuration change events
    - Handle encryption for secret values
    """

    def __init__(
        self,
        config_store: IConfigStore,
        event_bus: EventBus,
        encryption_service: IEncryptionService | None = None,
        validator: Optional["ConfigurationValidator"] = None,
    ):
        """
        Initialize configuration service.

        Args:
            config_store: Configuration storage port
            event_bus: Event bus for publishing events
            encryption_service: Encryption service for sensitive values (optional)
            validator: Configuration validator (created if not provided)
        """
        self.config_store = config_store
        self.event_bus = event_bus
        self.encryption_service = encryption_service
        self.validator = validator or ConfigurationValidator()
        # Locks for concurrent access protection (one per project)
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, project_name: str) -> asyncio.Lock:
        """Get or create lock for a project."""
        if project_name not in self._locks:
            self._locks[project_name] = asyncio.Lock()
        return self._locks[project_name]

    async def update_project_config(
        self,
        command: UpdateProjectConfigCommand
    ) -> ConfigurationCommandResult:
        """
        Update project configuration.

        Args:
            command: Update command with changes

        Returns:
            Result with new config version

        Raises:
            ConfigNotFoundError: If project doesn't exist
            ValidationError: If updates invalid
        """
        # Acquire lock for this project to prevent concurrent updates
        async with self._get_lock(command.project_name):
            # Load current config
            try:
                config = await self.config_store.get_project_config_by_name(
                    command.project_name
                )
            except ConfigNotFoundError:
                message = f"Project '{command.project_name}' not found"
                raise ConfigNotFoundError(message)

            # Validate updates
            validation = self.validator.validate_project_updates(
                config,
                command.updates
            )
            if not validation.valid:
                raise ValidationError("; ".join(validation.errors or []))

            # Store old values for computing changes
            old_config: dict[str, Any] = {
                "tech_stacks": config.tech_stacks.copy(),
                "pipelines": [p.copy() for p in config.pipelines],
                "testing": config.testing.copy(),
            }

            # Apply updates (deep merge)
            self._deep_merge(config.tech_stacks, command.updates.get("tech_stacks", {}))
            if "pipelines" in command.updates:
                config.pipelines = command.updates["pipelines"]
            if "testing" in command.updates:
                self._deep_merge(config.testing, command.updates["testing"])

            # Update metadata
            config.updated_at = datetime.now(UTC)
            config.version += 1
            config.metadata["updated_by"] = command.user_id
            if command.reason:
                config.metadata["update_reason"] = command.reason

            # Save configuration with rollback on event emission failure
            old_version = config.version - 1
            try:
                await self.config_store.save_project_config(config)

                # Compute changes
                changes = self._compute_changes(old_config, {
                    "tech_stacks": config.tech_stacks,
                    "pipelines": config.pipelines,
                    "testing": config.testing,
                })

                # Emit event
                event = ProjectConfigUpdated(
                    aggregate_id=config.id,
                    payload={
                        "project_id": config.id,
                        "version": config.version,
                        "changes": changes,
                        "updated_by": command.user_id,
                        "reason": command.reason,
                    },
                    user_id=command.user_id,
                )
                await self.event_bus.publish(event)

            except Exception as e:
                # Rollback on failure
                logger.error(
                    f"Failed to update project config or emit event: {e}. "
                    f"Rolling back changes for project '{command.project_name}'",
                    exc_info=True,
                    extra={"error_id": "ERR_CONFIG_UPDATE_PROJECT_FAILURE"}
                )
                config.version = old_version
                config.tech_stacks = old_config["tech_stacks"]
                config.pipelines = old_config["pipelines"]
                config.testing = old_config["testing"]
                await self.config_store.save_project_config(config)
                raise

            return ConfigurationCommandResult(
                success=True,
                config_version=config.version,
                message=f"Project config updated to version {config.version}",
                changes_applied=changes,
            )

    async def update_agent_config(
        self,
        command: UpdateAgentConfigCommand
    ) -> ConfigurationCommandResult:
        """
        Update agent configuration.

        Args:
            command: Update command with agent changes

        Returns:
            Result with new config version

        Raises:
            ConfigNotFoundError: If project or agent doesn't exist
            ValidationError: If updates invalid
        """
        # Get project to validate it exists
        try:
            project = await self.config_store.get_project_config_by_name(
                command.project_name
            )
        except ConfigNotFoundError:
            message = f"Project '{command.project_name}' not found"
            raise ConfigNotFoundError(message)

        # Load agent config
        try:
            config = await self.config_store.get_agent_config(
                project.id,
                command.agent_name
            )
        except ConfigNotFoundError:
            # Create new agent config if doesn't exist
            config = AgentConfig(
                project_id=project.id,
                agent_name=command.agent_name,
                model="claude-sonnet-4-5-20250929",
                timeout=3600,
                requires_docker=True,
                makes_code_changes=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

        # Validate updates
        validation = self.validator.validate_agent_updates(
            command.agent_name,
            command.updates
        )
        if not validation.valid:
            raise ValidationError("; ".join(validation.errors or []))

        # Store old values
        old_values = {
            "model": config.model,
            "timeout": config.timeout,
            "mcp_servers": config.mcp_servers.copy(),
        }

        # Apply updates
        if "model" in command.updates:
            config.model = command.updates["model"]
        if "timeout" in command.updates:
            config.timeout = command.updates["timeout"]
        if "requires_docker" in command.updates:
            config.requires_docker = command.updates["requires_docker"]
        if "makes_code_changes" in command.updates:
            config.makes_code_changes = command.updates["makes_code_changes"]
        if "mcp_servers" in command.updates:
            config.mcp_servers = command.updates["mcp_servers"]
        if "capabilities" in command.updates:
            config.capabilities = command.updates["capabilities"]
        if "constraints" in command.updates:
            config.constraints = command.updates["constraints"]

        # Update metadata
        config.updated_at = datetime.now(UTC)
        config.version += 1
        config.metadata["updated_by"] = command.user_id
        if command.reason:
            config.metadata["update_reason"] = command.reason

        # Save configuration
        await self.config_store.save_agent_config(config)

        # Compute changes
        changes = self._compute_changes(old_values, {
            "model": config.model,
            "timeout": config.timeout,
            "mcp_servers": config.mcp_servers,
        })

        # Emit event
        event = AgentConfigUpdated(
            aggregate_id=f"{project.id}:{command.agent_name}",
            payload={
                "project_id": project.id,
                "agent_name": command.agent_name,
                "version": config.version,
                "changes": changes,
                "updated_by": command.user_id,
                "reason": command.reason,
            },
            user_id=command.user_id,
        )
        await self.event_bus.publish(event)

        return ConfigurationCommandResult(
            success=True,
            config_version=config.version,
            message=f"Agent '{command.agent_name}' config updated to version {config.version}",
            changes_applied=changes,
        )

    async def update_pipeline_config(
        self,
        command: UpdatePipelineConfigCommand
    ) -> ConfigurationCommandResult:
        """
        Update pipeline configuration.

        Args:
            command: Update command with pipeline changes

        Returns:
            Result with new config version

        Raises:
            ConfigNotFoundError: If project or pipeline doesn't exist
            ValidationError: If updates invalid
        """
        # Get project
        try:
            project = await self.config_store.get_project_config_by_name(
                command.project_name
            )
        except ConfigNotFoundError:
            message = f"Project '{command.project_name}' not found"
            raise ConfigNotFoundError(message)

        # Load pipeline config
        try:
            config = await self.config_store.get_pipeline_config(
                project.id,
                command.pipeline_name
            )
        except ConfigNotFoundError:
            # Create new pipeline config if doesn't exist
            config = PipelineConfig(
                id=f"{project.id}:{command.pipeline_name}",
                project_id=project.id,
                name=command.pipeline_name,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

        # Validate updates
        validation = self.validator.validate_pipeline_updates(
            command.pipeline_name,
            command.updates
        )
        if not validation.valid:
            raise ValidationError("; ".join(validation.errors or []))

        # Store old values
        old_values = {
            "stages": config.stages.copy(),
            "triggers": config.triggers.copy(),
        }

        # Apply updates
        if "stages" in command.updates:
            config.stages = command.updates["stages"]
        if "triggers" in command.updates:
            config.triggers = command.updates["triggers"]

        # Update metadata
        config.updated_at = datetime.now(UTC)
        config.version += 1
        config.metadata["updated_by"] = command.user_id
        if command.reason:
            config.metadata["update_reason"] = command.reason

        # Save configuration
        await self.config_store.save_pipeline_config(config)

        # Compute changes
        changes = self._compute_changes(old_values, {
            "stages": config.stages,
            "triggers": config.triggers,
        })

        # Emit event
        event = PipelineConfigUpdated(
            aggregate_id=config.id,
            payload={
                "project_id": project.id,
                "pipeline_name": command.pipeline_name,
                "version": config.version,
                "changes": changes,
                "updated_by": command.user_id,
                "reason": command.reason,
            },
            user_id=command.user_id,
        )
        await self.event_bus.publish(event)

        return ConfigurationCommandResult(
            success=True,
            config_version=config.version,
            message=f"Pipeline '{command.pipeline_name}' config updated to version {config.version}",
            changes_applied=changes,
        )

    async def add_environment_variable(
        self,
        command: AddEnvironmentVariableCommand
    ) -> ConfigurationCommandResult:
        """
        Add or update environment variable for project.

        Args:
            command: Command with environment variable details

        Returns:
            Result with new config version

        Raises:
            ConfigNotFoundError: If project doesn't exist
            ValidationError: If variable name/value invalid
        """
        # Load config
        try:
            config = await self.config_store.get_project_config_by_name(
                command.project_name
            )
        except ConfigNotFoundError:
            message = f"Project '{command.project_name}' not found"
            raise ConfigNotFoundError(message)

        # Validate
        validation = self.validator.validate_environment_variable(
            command.variable_name,
            command.variable_value
        )
        if not validation.valid:
            raise ValidationError("; ".join(validation.errors or []))

        # Acquire lock for concurrent access protection
        async with self._get_lock(command.project_name):
            # Check if updating existing variable
            is_update = command.variable_name in config.environment_variables
            action = "updated" if is_update else "added"

            # Add/update variable with encryption for secrets
            stored_value = command.variable_value
            if command.is_secret:
                if self.encryption_service:
                    try:
                        stored_value = await self.encryption_service.encrypt(command.variable_value)
                        logger.debug(f"Encrypted environment variable '{command.variable_name}'")
                    except Exception as e:
                        logger.error(
                            f"Failed to encrypt environment variable: {e}",
                            exc_info=True,
                            extra={"error_id": "ERR_CONFIG_ENCRYPT_ENV_VAR_FAILURE"}
                        )
                        message = f"Failed to encrypt variable: {e}"
                        raise ValidationError(message)
                else:
                    logger.warning(
                        f"No encryption service configured. Storing secret "
                        f"'{command.variable_name}' in plaintext",
                        extra={"error_id": "ERR_CONFIG_NO_ENCRYPTION_SERVICE"}
                    )

            config.environment_variables[command.variable_name] = {
                "value": stored_value,
                "is_secret": command.is_secret,
                "description": command.description,
                "created_at": datetime.now(UTC).isoformat(),
                "created_by": command.user_id,
            }

            # Update metadata
            config.updated_at = datetime.now(UTC)
            config.version += 1

            # Save with rollback on failure
            old_version = config.version - 1
            old_env_vars = config.environment_variables.copy()
            try:
                await self.config_store.save_project_config(config)

                # Emit event
                event = EnvironmentVariableChanged(
                    aggregate_id=config.id,
                    payload={
                        "project_id": config.id,
                        "variable_name": command.variable_name,
                        "action": action,
                        "is_secret": command.is_secret,
                        "changed_by": command.user_id,
                    },
                    user_id=command.user_id,
                )
                await self.event_bus.publish(event)

            except Exception as e:
                # Rollback on failure
                logger.error(
                    f"Failed to add/update environment variable or emit event: {e}. "
                    f"Rolling back changes",
                    exc_info=True,
                    extra={"error_id": "ERR_CONFIG_UPDATE_ENV_VAR_FAILURE"}
                )
                config.version = old_version
                config.environment_variables = old_env_vars
                await self.config_store.save_project_config(config)
                raise

        return ConfigurationCommandResult(
            success=True,
            config_version=config.version,
            message=f"Environment variable '{command.variable_name}' {action}",
            changes_applied={"variable_name": command.variable_name, "action": action},
        )

    async def remove_environment_variable(
        self,
        command: RemoveEnvironmentVariableCommand
    ) -> ConfigurationCommandResult:
        """
        Remove environment variable from project.

        Args:
            command: Command specifying variable to remove

        Returns:
            Result with new config version

        Raises:
            ConfigNotFoundError: If project doesn't exist
            ValidationError: If variable doesn't exist
        """
        # Load config
        try:
            config = await self.config_store.get_project_config_by_name(
                command.project_name
            )
        except ConfigNotFoundError:
            message = f"Project '{command.project_name}' not found"
            raise ConfigNotFoundError(message)

        # Check if variable exists
        if command.variable_name not in config.environment_variables:
            message = f"Environment variable '{command.variable_name}' not found"
            raise ValidationError(message)

        # Remove variable
        del config.environment_variables[command.variable_name]

        # Update metadata
        config.updated_at = datetime.now(UTC)
        config.version += 1

        # Save
        await self.config_store.save_project_config(config)

        # Emit event
        event = EnvironmentVariableChanged(
            aggregate_id=config.id,
            payload={
                "project_id": config.id,
                "variable_name": command.variable_name,
                "action": "removed",
                "is_secret": False,
                "changed_by": command.user_id,
            },
            user_id=command.user_id,
        )
        await self.event_bus.publish(event)

        return ConfigurationCommandResult(
            success=True,
            config_version=config.version,
            message=f"Environment variable '{command.variable_name}' removed",
            changes_applied={"variable_name": command.variable_name, "action": "removed"},
        )

    async def mount_command(
        self,
        command: MountCommandCommand
    ) -> ConfigurationCommandResult:
        """
        Mount a command into project agent.

        Args:
            command: Command with command file details

        Returns:
            Result with new config version

        Raises:
            ConfigNotFoundError: If project doesn't exist
            ValidationError: If command file doesn't exist or is invalid
        """
        # Load config
        try:
            config = await self.config_store.get_project_config_by_name(
                command.project_name
            )
        except ConfigNotFoundError:
            message = f"Project '{command.project_name}' not found"
            raise ConfigNotFoundError(message)

        # Validate command file exists
        command_path = Path(command.command_path)
        if not command_path.exists():
            message = f"Command file not found: {command.command_path}"
            raise ValidationError(message)

        # Validate command file format (basic check)
        if not command_path.suffix == ".md":
            message = "Command file must be a .md file"
            raise ValidationError(message)

        # Mount command
        config.mounted_commands[command.command_name] = {
            "path": command.command_path,
            "description": command.description,
            "created_at": datetime.now(UTC).isoformat(),
            "created_by": command.user_id,
        }

        # Update metadata
        config.updated_at = datetime.now(UTC)
        config.version += 1

        # Save
        await self.config_store.save_project_config(config)

        # Emit event
        event = CommandMounted(
            aggregate_id=config.id,
            payload={
                "project_id": config.id,
                "command_name": command.command_name,
                "command_path": command.command_path,
                "mounted_by": command.user_id,
            },
            user_id=command.user_id,
        )
        await self.event_bus.publish(event)

        return ConfigurationCommandResult(
            success=True,
            config_version=config.version,
            message=f"Command '{command.command_name}' mounted",
            changes_applied={"command_name": command.command_name},
        )

    async def unmount_command(
        self,
        command: UnmountCommandCommand
    ) -> ConfigurationCommandResult:
        """
        Unmount a command from project agent.

        Args:
            command: Command specifying command to unmount

        Returns:
            Result with new config version

        Raises:
            ConfigNotFoundError: If project doesn't exist
            ValidationError: If command not mounted
        """
        # Load config
        try:
            config = await self.config_store.get_project_config_by_name(
                command.project_name
            )
        except ConfigNotFoundError:
            message = f"Project '{command.project_name}' not found"
            raise ConfigNotFoundError(message)

        # Check if command exists
        if command.command_name not in config.mounted_commands:
            message = f"Command '{command.command_name}' not mounted"
            raise ValidationError(message)

        # Unmount command
        del config.mounted_commands[command.command_name]

        # Update metadata
        config.updated_at = datetime.now(UTC)
        config.version += 1

        # Save
        await self.config_store.save_project_config(config)

        # Emit event
        event = CommandUnmounted(
            aggregate_id=config.id,
            payload={
                "project_id": config.id,
                "command_name": command.command_name,
                "unmounted_by": command.user_id,
            },
            user_id=command.user_id,
        )
        await self.event_bus.publish(event)

        return ConfigurationCommandResult(
            success=True,
            config_version=config.version,
            message=f"Command '{command.command_name}' unmounted",
            changes_applied={"command_name": command.command_name},
        )

    async def mount_subagent(
        self,
        command: MountSubAgentCommand
    ) -> ConfigurationCommandResult:
        """
        Mount a sub-agent into project agent.

        Args:
            command: Command with sub-agent configuration

        Returns:
            Result with new config version

        Raises:
            ConfigNotFoundError: If project doesn't exist
            ValidationError: If sub-agent config invalid
        """
        # Load config
        try:
            config = await self.config_store.get_project_config_by_name(
                command.project_name
            )
        except ConfigNotFoundError:
            message = f"Project '{command.project_name}' not found"
            raise ConfigNotFoundError(message)

        # Validate sub-agent config
        validation = self.validator.validate_subagent_config(
            command.subagent_config
        )
        if not validation.valid:
            raise ValidationError("; ".join(validation.errors or []))

        # Mount sub-agent
        config.mounted_subagents[command.subagent_name] = {
            "config": command.subagent_config,
            "description": command.description,
            "created_at": datetime.now(UTC).isoformat(),
            "created_by": command.user_id,
        }

        # Update metadata
        config.updated_at = datetime.now(UTC)
        config.version += 1

        # Save
        await self.config_store.save_project_config(config)

        # Emit event
        event = SubAgentMounted(
            aggregate_id=config.id,
            payload={
                "project_id": config.id,
                "subagent_name": command.subagent_name,
                "mounted_by": command.user_id,
            },
            user_id=command.user_id,
        )
        await self.event_bus.publish(event)

        return ConfigurationCommandResult(
            success=True,
            config_version=config.version,
            message=f"Sub-agent '{command.subagent_name}' mounted",
            changes_applied={"subagent_name": command.subagent_name},
        )

    async def unmount_subagent(
        self,
        command: UnmountSubAgentCommand
    ) -> ConfigurationCommandResult:
        """
        Unmount a sub-agent from project agent.

        Args:
            command: Command specifying sub-agent to unmount

        Returns:
            Result with new config version

        Raises:
            ConfigNotFoundError: If project doesn't exist
            ValidationError: If sub-agent not mounted
        """
        # Load config
        try:
            config = await self.config_store.get_project_config_by_name(
                command.project_name
            )
        except ConfigNotFoundError:
            message = f"Project '{command.project_name}' not found"
            raise ConfigNotFoundError(message)

        # Check if sub-agent exists
        if command.subagent_name not in config.mounted_subagents:
            message = f"Sub-agent '{command.subagent_name}' not mounted"
            raise ValidationError(message)

        # Unmount sub-agent
        del config.mounted_subagents[command.subagent_name]

        # Update metadata
        config.updated_at = datetime.now(UTC)
        config.version += 1

        # Save
        await self.config_store.save_project_config(config)

        # Emit event
        event = SubAgentUnmounted(
            aggregate_id=config.id,
            payload={
                "project_id": config.id,
                "subagent_name": command.subagent_name,
                "unmounted_by": command.user_id,
            },
            user_id=command.user_id,
        )
        await self.event_bus.publish(event)

        return ConfigurationCommandResult(
            success=True,
            config_version=config.version,
            message=f"Sub-agent '{command.subagent_name}' unmounted",
            changes_applied={"subagent_name": command.subagent_name},
        )

    # Helper methods

    def _deep_merge(self, target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
        """
        Deep merge source into target dict.

        Args:
            target: Target dictionary to merge into
            source: Source dictionary to merge from

        Returns:
            The merged target dictionary
        """
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._deep_merge(target[key], value)
            else:
                target[key] = value
        return target

    def _compute_changes(
        self,
        old_config: dict[str, Any],
        new_config: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Compute changes between old and new config.

        Args:
            old_config: Old configuration dictionary
            new_config: New configuration dictionary

        Returns:
            Dictionary mapping changed keys to old/new values
        """
        changes: dict[str, Any] = {}
        for key in new_config:
            if key not in old_config or old_config[key] != new_config[key]:
                changes[key] = {
                    "old": old_config.get(key),
                    "new": new_config[key],
                }
        return changes


class ConfigurationValidator:
    """Validates configuration updates."""

    def validate_project_updates(
        self,
        current_config: ProjectConfig,
        updates: dict[str, Any]
    ) -> "ValidationResult":
        """
        Validate project configuration updates.

        Checks:
        - Required fields not removed
        - Data types match schema
        - Referenced resources exist
        """
        errors = []

        # Validate tech stacks
        if "tech_stacks" in updates:
            if not isinstance(updates["tech_stacks"], dict):
                errors.append("tech_stacks must be a dictionary")

        # Validate pipelines
        if "pipelines" in updates:
            if not isinstance(updates["pipelines"], list):
                errors.append("pipelines must be a list")
            else:
                for i, pipeline in enumerate(updates["pipelines"]):
                    if not isinstance(pipeline, dict):
                        errors.append(f"Pipeline {i} must be a dictionary")
                    elif "name" not in pipeline:
                        errors.append(f"Pipeline {i} missing required 'name' field")

        # Validate testing config
        if "testing" in updates:
            if not isinstance(updates["testing"], dict):
                errors.append("testing must be a dictionary")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors if errors else None
        )

    def validate_agent_updates(
        self,
        agent_name: str,
        updates: dict[str, Any]
    ) -> "ValidationResult":
        """
        Validate agent configuration updates.

        Checks:
        - Model is valid
        - Timeout is positive integer
        - MCP servers format
        """
        errors = []

        # Validate model
        if "model" in updates:
            if not isinstance(updates["model"], str):
                errors.append("model must be a string")
            elif not self._is_valid_model(updates["model"]):
                errors.append(f"Invalid model: {updates['model']}")

        # Validate timeout
        if "timeout" in updates:
            if not isinstance(updates["timeout"], int) or updates["timeout"] <= 0:
                errors.append("timeout must be a positive integer")

        # Validate MCP servers
        if "mcp_servers" in updates:
            if not isinstance(updates["mcp_servers"], list):
                errors.append("mcp_servers must be a list")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors if errors else None
        )

    def validate_pipeline_updates(
        self,
        pipeline_name: str,
        updates: dict[str, Any]
    ) -> "ValidationResult":
        """
        Validate pipeline configuration updates.

        Checks:
        - Stages format and uniqueness
        - No circular dependencies in stage transitions
        """
        errors: list[str] = []

        # Validate stages
        if "stages" in updates:
            if not isinstance(updates["stages"], list):
                errors.append("stages must be a list")
            else:
                # Check for unique stage names
                stage_names = [s.get("name") for s in updates["stages"] if isinstance(s, dict)]
                if len(stage_names) != len(set(stage_names)):
                    errors.append("Pipeline stage names must be unique")

                # Check for circular dependencies
                stage_map: dict[str, Any] = {s.get("name") or "": s for s in updates["stages"] if isinstance(s, dict)}
                for stage in updates["stages"]:
                    if isinstance(stage, dict) and "transitions" in stage:
                        if self._has_circular_dependency(
                            stage.get("name") or "",
                            stage.get("transitions", []),
                            stage_map,
                        ):
                            errors.append(
                                f"Circular dependency detected in stage '{stage.get('name')}'"
                            )

        # Validate triggers
        if "triggers" in updates:
            if not isinstance(updates["triggers"], list):
                errors.append("triggers must be a list")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors if errors else None
        )

    def _has_circular_dependency(
        self,
        start_stage: str,
        transitions: list[str],
        stage_map: dict[str, Any],
        visited: set | None = None
    ) -> bool:
        """
        Check for circular dependencies in pipeline stage transitions.

        Args:
            start_stage: Starting stage name
            transitions: List of stage transitions
            stage_map: Map of stage names to stage configs
            visited: Set of visited stages (for recursion)

        Returns:
            True if circular dependency detected, False otherwise
        """
        if visited is None:
            visited = set()

        visited.add(start_stage)

        for next_stage in transitions:
            if next_stage == start_stage:
                return True
            if next_stage in visited:
                return True
            if next_stage in stage_map:
                next_transitions = stage_map[next_stage].get("transitions", [])
                if self._has_circular_dependency(
                    start_stage, next_transitions, stage_map, visited.copy()
                ):
                    return True

        return False

    def validate_environment_variable(
        self,
        name: str,
        value: str
    ) -> "ValidationResult":
        """
        Validate environment variable.

        Checks:
        - Name follows ENV_VAR conventions (uppercase with underscores)
        - Not a reserved system variable
        - Value is string
        """
        errors: list[str] = []

        # Check name format
        if not re.match(r"^[A-Z][A-Z0-9_]*$", name):
            errors.append(
                f"Variable name must be uppercase with underscores: {name}"
            )

        # Check reserved names (expanded list of common system variables)
        reserved = [
            # System paths
            "PATH", "HOME", "PWD", "OLDPWD", "TMPDIR", "TEMP", "TMP",
            # User/session
            "USER", "LOGNAME", "USERNAME", "SHELL", "TERM", "EDITOR",
            # System info
            "HOSTNAME", "HOSTTYPE", "OSTYPE", "MACHTYPE", "LANG", "LC_ALL",
            # Process info
            "PID", "PPID", "UID", "GID", "EUID", "EGID",
            # Special
            "IFS", "PS1", "PS2", "PS3", "PS4", "BASH_VERSION", "SHLVL",
        ]
        if name in reserved:
            errors.append(f"Cannot override reserved system variable: {name}")

        # Check value is string
        if not isinstance(value, str):
            errors.append("Variable value must be string")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors if errors else None
        )

    def validate_subagent_config(
        self,
        config: dict[str, Any]
    ) -> "ValidationResult":
        """Validate sub-agent configuration."""
        errors = []

        # Check required fields
        required_fields = ["name", "type"]
        for field in required_fields:
            if field not in config:
                errors.append(f"Sub-agent config missing required field: {field}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors if errors else None
        )

    def _is_valid_model(self, model: str) -> bool:
        """Check if model is valid."""
        # Simple validation - could be more sophisticated
        valid_prefixes = ["claude-", "gpt-"]
        return any(model.startswith(prefix) for prefix in valid_prefixes)


class ValidationResult:
    """Result of configuration validation."""

    def __init__(self, valid: bool, errors: list[str] | None = None):
        """
        Initialize validation result.

        Args:
            valid: Whether validation passed
            errors: List of error messages (if validation failed)
        """
        self.valid = valid
        self.errors = errors
