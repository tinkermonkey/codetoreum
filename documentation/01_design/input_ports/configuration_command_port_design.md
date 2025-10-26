# Configuration Command Input Port Design

## Purpose

The Configuration Command Port enables dynamic management of system configuration through a web UI or API, replacing static YAML files with database-backed configuration as specified in the design changes.

## Port Interface

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

@dataclass
class UpdateProjectConfigCommand:
    """Command to update project configuration"""
    project_name: str
    updates: Dict[str, Any]  # Partial updates
    user_id: str
    reason: Optional[str] = None

@dataclass
class UpdateAgentConfigCommand:
    """Command to update agent configuration"""
    project_name: str
    agent_name: str
    updates: Dict[str, Any]
    user_id: str
    reason: Optional[str] = None

@dataclass
class UpdatePipelineConfigCommand:
    """Command to update pipeline configuration"""
    project_name: str
    pipeline_name: str
    updates: Dict[str, Any]
    user_id: str
    reason: Optional[str] = None

@dataclass
class AddEnvironmentVariableCommand:
    """Command to add/update project environment variable (NEW)"""
    project_name: str
    variable_name: str
    variable_value: str
    is_secret: bool = False  # If true, encrypt storage
    description: Optional[str] = None
    user_id: str

@dataclass
class RemoveEnvironmentVariableCommand:
    """Command to remove project environment variable (NEW)"""
    project_name: str
    variable_name: str
    user_id: str

@dataclass
class MountCommandCommand:
    """Command to mount a command into project agent (NEW)"""
    project_name: str
    command_name: str
    command_path: str  # Path to command file
    description: Optional[str] = None
    user_id: str

@dataclass
class UnmountCommandCommand:
    """Command to unmount a command from project agent (NEW)"""
    project_name: str
    command_name: str
    user_id: str

@dataclass
class MountSubAgentCommand:
    """Command to mount a sub-agent into project agent (NEW)"""
    project_name: str
    subagent_name: str
    subagent_config: Dict[str, Any]
    description: Optional[str] = None
    user_id: str

@dataclass
class UnmountSubAgentCommand:
    """Command to unmount a sub-agent from project agent (NEW)"""
    project_name: str
    subagent_name: str
    user_id: str

@dataclass
class ConfigurationCommandResult:
    """Result of configuration command"""
    success: bool
    config_version: int  # New version number after update
    message: str
    changes_applied: Dict[str, Any]  # What actually changed
    errors: Optional[List[str]] = None

class IConfigurationCommandPort(ABC):
    """Input port for configuration commands"""

    @abstractmethod
    async def update_project_config(
        self,
        command: UpdateProjectConfigCommand
    ) -> ConfigurationCommandResult:
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
        pass

    @abstractmethod
    async def update_agent_config(
        self,
        command: UpdateAgentConfigCommand
    ) -> ConfigurationCommandResult:
        """Updates agent configuration for a project"""
        pass

    @abstractmethod
    async def update_pipeline_config(
        self,
        command: UpdatePipelineConfigCommand
    ) -> ConfigurationCommandResult:
        """Updates pipeline configuration for a project"""
        pass

    @abstractmethod
    async def add_environment_variable(
        self,
        command: AddEnvironmentVariableCommand
    ) -> ConfigurationCommandResult:
        """
        Adds or updates environment variable for project.

        NEW in redesign - supports project-level environment variables.
        """
        pass

    @abstractmethod
    async def remove_environment_variable(
        self,
        command: RemoveEnvironmentVariableCommand
    ) -> ConfigurationCommandResult:
        """Removes environment variable from project"""
        pass

    @abstractmethod
    async def mount_command(
        self,
        command: MountCommandCommand
    ) -> ConfigurationCommandResult:
        """
        Mounts a command into project agent.

        NEW in redesign - enables dynamic command mounting.
        """
        pass

    @abstractmethod
    async def unmount_command(
        self,
        command: UnmountCommandCommand
    ) -> ConfigurationCommandResult:
        """Unmounts a command from project agent"""
        pass

    @abstractmethod
    async def mount_subagent(
        self,
        command: MountSubAgentCommand
    ) -> ConfigurationCommandResult:
        """
        Mounts a sub-agent into project agent.

        NEW in redesign - enables dynamic sub-agent mounting.
        """
        pass

    @abstractmethod
    async def unmount_subagent(
        self,
        command: UnmountSubAgentCommand
    ) -> ConfigurationCommandResult:
        """Unmounts a sub-agent from project agent"""
        pass
```

## Configuration Storage Model

### Database Schema

```sql
-- Projects table
CREATE TABLE projects (
    id UUID PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    config_version INT NOT NULL DEFAULT 1,
    config JSONB NOT NULL  -- Full project configuration
);

-- Environment variables table (NEW)
CREATE TABLE project_environment_variables (
    id UUID PRIMARY KEY,
    project_id UUID REFERENCES projects(id),
    variable_name VARCHAR(255) NOT NULL,
    variable_value TEXT NOT NULL,  -- Encrypted if is_secret=true
    is_secret BOOLEAN NOT NULL DEFAULT FALSE,
    description TEXT,
    created_at TIMESTAMP NOT NULL,
    created_by VARCHAR(255),
    updated_at TIMESTAMP NOT NULL,
    updated_by VARCHAR(255),
    UNIQUE(project_id, variable_name)
);

-- Mounted commands table (NEW)
CREATE TABLE project_mounted_commands (
    id UUID PRIMARY KEY,
    project_id UUID REFERENCES projects(id),
    command_name VARCHAR(255) NOT NULL,
    command_path TEXT NOT NULL,  -- Path to command file
    description TEXT,
    created_at TIMESTAMP NOT NULL,
    created_by VARCHAR(255),
    UNIQUE(project_id, command_name)
);

-- Mounted sub-agents table (NEW)
CREATE TABLE project_mounted_subagents (
    id UUID PRIMARY KEY,
    project_id UUID REFERENCES projects(id),
    subagent_name VARCHAR(255) NOT NULL,
    subagent_config JSONB NOT NULL,
    description TEXT,
    created_at TIMESTAMP NOT NULL,
    created_by VARCHAR(255),
    UNIQUE(project_id, subagent_name)
);

-- Configuration history table
CREATE TABLE configuration_history (
    id UUID PRIMARY KEY,
    project_id UUID REFERENCES projects(id),
    config_version INT NOT NULL,
    change_type VARCHAR(50) NOT NULL,  -- update_project, add_env_var, etc.
    changes JSONB NOT NULL,  -- What changed
    changed_by VARCHAR(255),
    changed_at TIMESTAMP NOT NULL,
    reason TEXT
);
```

### Configuration Aggregate

```python
@dataclass
class ProjectConfiguration:
    """Domain aggregate for project configuration"""
    id: str
    name: str
    version: int
    config: Dict[str, Any]
    environment_variables: Dict[str, EnvironmentVariable]
    mounted_commands: Dict[str, MountedCommand]
    mounted_subagents: Dict[str, MountedSubAgent]
    created_at: datetime
    updated_at: datetime

    def update_config(
        self,
        updates: Dict[str, Any],
        user_id: str,
        reason: Optional[str] = None
    ) -> List[DomainEvent]:
        """
        Updates configuration with validation.

        Returns list of events to emit.
        """
        # Validate updates
        self._validate_updates(updates)

        # Apply updates
        old_config = self.config.copy()
        self.config = deep_merge(self.config, updates)

        # Increment version
        self.version += 1
        self.updated_at = utc_now()

        # Return events
        return [
            ProjectConfigUpdatedEvent(
                project_id=self.id,
                version=self.version,
                changes=self._compute_changes(old_config, self.config),
                updated_by=user_id,
                reason=reason
            )
        ]

    def add_environment_variable(
        self,
        name: str,
        value: str,
        is_secret: bool,
        description: Optional[str],
        user_id: str
    ) -> List[DomainEvent]:
        """Adds or updates environment variable"""

        # Validate name
        if not self._is_valid_env_var_name(name):
            raise ValidationError(f"Invalid variable name: {name}")

        # Encrypt if secret
        stored_value = value
        if is_secret:
            stored_value = self._encrypt(value)

        # Add/update variable
        var = EnvironmentVariable(
            name=name,
            value=stored_value,
            is_secret=is_secret,
            description=description,
            created_at=utc_now(),
            created_by=user_id
        )

        old_var = self.environment_variables.get(name)
        self.environment_variables[name] = var

        # Increment version
        self.version += 1
        self.updated_at = utc_now()

        # Return event
        action = "updated" if old_var else "added"
        return [
            EnvironmentVariableChangedEvent(
                project_id=self.id,
                variable_name=name,
                action=action,
                is_secret=is_secret,
                changed_by=user_id
            )
        ]

    def mount_command(
        self,
        name: str,
        path: str,
        description: Optional[str],
        user_id: str
    ) -> List[DomainEvent]:
        """Mounts a command"""

        # Validate command file exists
        if not Path(path).exists():
            raise ValidationError(f"Command file not found: {path}")

        # Validate command format
        self._validate_command_file(path)

        # Mount command
        cmd = MountedCommand(
            name=name,
            path=path,
            description=description,
            created_at=utc_now(),
            created_by=user_id
        )

        self.mounted_commands[name] = cmd

        # Increment version
        self.version += 1
        self.updated_at = utc_now()

        return [
            CommandMountedEvent(
                project_id=self.id,
                command_name=name,
                command_path=path,
                mounted_by=user_id
            )
        ]

    def mount_subagent(
        self,
        name: str,
        config: Dict[str, Any],
        description: Optional[str],
        user_id: str
    ) -> List[DomainEvent]:
        """Mounts a sub-agent"""

        # Validate sub-agent config
        self._validate_subagent_config(config)

        # Mount sub-agent
        subagent = MountedSubAgent(
            name=name,
            config=config,
            description=description,
            created_at=utc_now(),
            created_by=user_id
        )

        self.mounted_subagents[name] = subagent

        # Increment version
        self.version += 1
        self.updated_at = utc_now()

        return [
            SubAgentMountedEvent(
                project_id=self.id,
                subagent_name=name,
                mounted_by=user_id
            )
        ]
```

## Configuration Validation

### Update Validation
```python
class ConfigurationValidator:
    """Validates configuration updates"""

    def validate_project_updates(
        self,
        current_config: Dict[str, Any],
        updates: Dict[str, Any]
    ) -> ValidationResult:
        """
        Validates project configuration updates.

        Checks:
        - Required fields not removed
        - Data types match schema
        - Referenced resources exist
        - No circular dependencies
        """
        errors = []

        # Validate GitHub config
        if 'github' in updates:
            github_errors = self._validate_github_config(updates['github'])
            errors.extend(github_errors)

        # Validate pipelines
        if 'pipelines' in updates:
            pipeline_errors = self._validate_pipelines(updates['pipelines'])
            errors.extend(pipeline_errors)

        # Validate tech stack
        if 'tech_stack' in updates:
            tech_errors = self._validate_tech_stack(updates['tech_stack'])
            errors.extend(tech_errors)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors if errors else None
        )

    def validate_agent_updates(
        self,
        agent_name: str,
        updates: Dict[str, Any]
    ) -> ValidationResult:
        """
        Validates agent configuration updates.

        Checks:
        - Model is valid Claude model ID
        - Timeout is positive integer
        - MCP servers exist
        - Permissions are valid
        """
        errors = []

        # Validate model
        if 'model' in updates:
            if not self._is_valid_claude_model(updates['model']):
                errors.append(f"Invalid model: {updates['model']}")

        # Validate timeout
        if 'timeout' in updates:
            if not isinstance(updates['timeout'], int) or updates['timeout'] <= 0:
                errors.append("Timeout must be positive integer")

        # Validate MCP servers
        if 'mcp_servers' in updates:
            for server in updates['mcp_servers']:
                if not self._validate_mcp_server(server):
                    errors.append(f"Invalid MCP server config: {server}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors if errors else None
        )

    def validate_environment_variable(
        self,
        name: str,
        value: str
    ) -> ValidationResult:
        """
        Validates environment variable.

        Checks:
        - Name follows ENV_VAR conventions
        - No dangerous names (PATH, HOME, etc.)
        - Value is string
        """
        errors = []

        # Check name format
        if not re.match(r'^[A-Z][A-Z0-9_]*$', name):
            errors.append(
                f"Variable name must be uppercase with underscores: {name}"
            )

        # Check reserved names
        reserved = ['PATH', 'HOME', 'USER', 'SHELL', 'PWD']
        if name in reserved:
            errors.append(f"Cannot override reserved variable: {name}")

        # Check value is string
        if not isinstance(value, str):
            errors.append("Variable value must be string")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors if errors else None
        )
```

## Configuration Service

```python
class ConfigurationService:
    """Application service for configuration management"""

    def __init__(
        self,
        config_repository: IConfigurationRepository,
        event_bus: IEventBus,
        validator: ConfigurationValidator,
        encryptor: IEncryptor
    ):
        self.config_repository = config_repository
        self.event_bus = event_bus
        self.validator = validator
        self.encryptor = encryptor

    async def update_project_config(
        self,
        command: UpdateProjectConfigCommand
    ) -> ConfigurationCommandResult:
        """Updates project configuration"""

        # Load current config
        config = await self.config_repository.get_by_name(
            command.project_name
        )
        if not config:
            raise ProjectNotFoundError(command.project_name)

        # Validate updates
        validation = self.validator.validate_project_updates(
            config.config,
            command.updates
        )
        if not validation.valid:
            raise ValidationError(validation.errors)

        # Apply updates (generates events)
        events = config.update_config(
            command.updates,
            command.user_id,
            command.reason
        )

        # Save configuration
        await self.config_repository.save(config)

        # Publish events
        for event in events:
            await self.event_bus.publish(event)

        return ConfigurationCommandResult(
            success=True,
            config_version=config.version,
            message=f"Project config updated to version {config.version}",
            changes_applied=events[0].changes
        )

    async def add_environment_variable(
        self,
        command: AddEnvironmentVariableCommand
    ) -> ConfigurationCommandResult:
        """Adds environment variable to project"""

        # Load config
        config = await self.config_repository.get_by_name(
            command.project_name
        )

        # Validate
        validation = self.validator.validate_environment_variable(
            command.variable_name,
            command.variable_value
        )
        if not validation.valid:
            raise ValidationError(validation.errors)

        # Add variable (generates events)
        events = config.add_environment_variable(
            command.variable_name,
            command.variable_value,
            command.is_secret,
            command.description,
            command.user_id
        )

        # Save
        await self.config_repository.save(config)

        # Publish events
        for event in events:
            await self.event_bus.publish(event)

        return ConfigurationCommandResult(
            success=True,
            config_version=config.version,
            message=f"Environment variable '{command.variable_name}' added",
            changes_applied={'variable_name': command.variable_name}
        )
```

## Web UI Integration

### REST API Endpoints

```python
# FastAPI router for configuration
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/api/config")

@router.put("/projects/{project_name}")
async def update_project_config(
    project_name: str,
    updates: Dict[str, Any],
    user: User = Depends(get_current_user),
    config_port: IConfigurationCommandPort = Depends(get_config_port)
):
    """Updates project configuration"""
    command = UpdateProjectConfigCommand(
        project_name=project_name,
        updates=updates,
        user_id=user.id
    )

    result = await config_port.update_project_config(command)

    return {
        "success": result.success,
        "version": result.config_version,
        "message": result.message,
        "changes": result.changes_applied
    }

@router.post("/projects/{project_name}/env")
async def add_environment_variable(
    project_name: str,
    var_name: str,
    var_value: str,
    is_secret: bool = False,
    description: str = None,
    user: User = Depends(get_current_user),
    config_port: IConfigurationCommandPort = Depends(get_config_port)
):
    """Adds environment variable to project"""
    command = AddEnvironmentVariableCommand(
        project_name=project_name,
        variable_name=var_name,
        variable_value=var_value,
        is_secret=is_secret,
        description=description,
        user_id=user.id
    )

    result = await config_port.add_environment_variable(command)

    return {
        "success": result.success,
        "version": result.config_version,
        "message": result.message
    }

@router.post("/projects/{project_name}/commands")
async def mount_command(
    project_name: str,
    command_name: str,
    command_path: str,
    description: str = None,
    user: User = Depends(get_current_user),
    config_port: IConfigurationCommandPort = Depends(get_config_port)
):
    """Mounts command into project agent"""
    command = MountCommandCommand(
        project_name=project_name,
        command_name=command_name,
        command_path=command_path,
        description=description,
        user_id=user.id
    )

    result = await config_port.mount_command(command)

    return {
        "success": result.success,
        "version": result.config_version,
        "message": result.message
    }
```

## Observability

### Events Emitted
```python
@dataclass
class ProjectConfigUpdatedEvent(DomainEvent):
    """Project configuration updated"""
    project_id: str
    version: int
    changes: Dict[str, Any]
    updated_by: str
    reason: Optional[str]

@dataclass
class EnvironmentVariableChangedEvent(DomainEvent):
    """Environment variable added/updated/removed"""
    project_id: str
    variable_name: str
    action: str  # added, updated, removed
    is_secret: bool
    changed_by: str

@dataclass
class CommandMountedEvent(DomainEvent):
    """Command mounted to project agent"""
    project_id: str
    command_name: str
    command_path: str
    mounted_by: str

@dataclass
class SubAgentMountedEvent(DomainEvent):
    """Sub-agent mounted to project agent"""
    project_id: str
    subagent_name: str
    mounted_by: str
```

## Security

### Encryption
```python
class ConfigurationEncryptor:
    """Encrypts sensitive configuration"""

    def __init__(self, encryption_key: bytes):
        self.fernet = Fernet(encryption_key)

    def encrypt(self, value: str) -> str:
        """Encrypts a value"""
        return self.fernet.encrypt(value.encode()).decode()

    def decrypt(self, encrypted: str) -> str:
        """Decrypts a value"""
        return self.fernet.decrypt(encrypted.encode()).decode()
```

### Authorization
```python
class ConfigurationAuthorizer:
    """Authorizes configuration changes"""

    def can_update_project_config(
        self,
        user: User,
        project: str
    ) -> bool:
        """Check if user can update project config"""
        return user.has_permission(f"config:update:{project}")

    def can_manage_environment_variables(
        self,
        user: User,
        project: str
    ) -> bool:
        """Check if user can manage env vars"""
        return user.has_permission(f"config:env:{project}")
```

## Migration from YAML

### Migration Strategy
1. Load existing YAML configurations
2. Insert into database tables
3. Set initial version to 1
4. Mark as migrated
5. Keep YAML as read-only backup

### Migration Script
```python
async def migrate_yaml_to_database():
    """Migrates YAML configs to database"""

    # Load all YAML project configs
    yaml_configs = load_yaml_configs("config/projects/")

    for yaml_config in yaml_configs:
        # Create database record
        project = ProjectConfiguration(
            id=generate_id(),
            name=yaml_config['name'],
            version=1,
            config=yaml_config,
            environment_variables={},
            mounted_commands={},
            mounted_subagents={},
            created_at=utc_now(),
            updated_at=utc_now()
        )

        # Save to database
        await config_repository.save(project)

        print(f"✅ Migrated {project.name}")
```

## Testing

### Unit Tests
- Validation logic
- Encryption/decryption
- Configuration merging
- Version incrementing

### Integration Tests
- Full update workflow
- Database persistence
- Event emission

### Simulation Tests
- Mock configuration changes
- Test rollback scenarios
