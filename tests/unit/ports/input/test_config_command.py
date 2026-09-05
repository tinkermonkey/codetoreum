"""
Unit tests for Configuration Command Input Port

Tests the data structures and behavior of the IConfigurationCommandPort
command objects and implementations.
"""

import pytest

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
from codetoreum.ports.input.exceptions import (
    AgentNotFoundError,
    CommandFileNotFoundError,
    CommandNotFoundError,
    PermissionError,
    PipelineNotFoundError,
    ProjectNotFoundError,
    SubAgentNotFoundError,
    ValidationError,
    VariableNotFoundError,
)


class TestUpdateProjectConfigCommand:
    """Tests for UpdateProjectConfigCommand dataclass"""

    def test_minimal_command_creation(self):
        """Test creating command with minimal fields"""
        updates = {"github": {"repo": "owner/repo"}}
        cmd = UpdateProjectConfigCommand(project_name="test-project", updates=updates, user_id="user-123")

        assert cmd.project_name == "test-project"
        assert cmd.updates == updates
        assert cmd.user_id == "user-123"
        assert cmd.reason is None

    def test_command_with_reason(self):
        """Test creating command with reason"""
        updates = {"tech_stack": ["python", "react"]}
        cmd = UpdateProjectConfigCommand(
            project_name="test-project",
            updates=updates,
            user_id="user-123",
            reason="Updating tech stack for new requirements",
        )

        assert cmd.project_name == "test-project"
        assert cmd.updates == updates
        assert cmd.user_id == "user-123"
        assert cmd.reason == "Updating tech stack for new requirements"


class TestUpdateAgentConfigCommand:
    """Tests for UpdateAgentConfigCommand dataclass"""

    def test_agent_config_command(self):
        """Test creating agent config command"""
        updates = {"model": "claude-3-opus", "timeout": 600}
        cmd = UpdateAgentConfigCommand(
            project_name="test-project",
            agent_name="builder-agent",
            updates=updates,
            user_id="user-123",
        )

        assert cmd.project_name == "test-project"
        assert cmd.agent_name == "builder-agent"
        assert cmd.updates == updates
        assert cmd.user_id == "user-123"


class TestUpdatePipelineConfigCommand:
    """Tests for UpdatePipelineConfigCommand dataclass"""

    def test_pipeline_config_command(self):
        """Test creating pipeline config command"""
        updates = {"stages": ["build", "test", "deploy"]}
        cmd = UpdatePipelineConfigCommand(
            project_name="test-project",
            pipeline_name="ci-pipeline",
            updates=updates,
            user_id="user-123",
            reason="Adding deploy stage",
        )

        assert cmd.project_name == "test-project"
        assert cmd.pipeline_name == "ci-pipeline"
        assert cmd.updates == updates
        assert cmd.user_id == "user-123"
        assert cmd.reason == "Adding deploy stage"


class TestAddEnvironmentVariableCommand:
    """Tests for AddEnvironmentVariableCommand dataclass"""

    def test_non_secret_variable(self):
        """Test creating command for non-secret variable"""
        cmd = AddEnvironmentVariableCommand(
            project_name="test-project",
            variable_name="BUILD_ENV",
            variable_value="production",
            user_id="user-123",
        )

        assert cmd.project_name == "test-project"
        assert cmd.variable_name == "BUILD_ENV"
        assert cmd.variable_value == "production"
        assert cmd.is_secret is False
        assert cmd.description is None
        assert cmd.user_id == "user-123"

    def test_secret_variable_with_description(self):
        """Test creating command for secret variable with description"""
        cmd = AddEnvironmentVariableCommand(
            project_name="test-project",
            variable_name="API_KEY",
            variable_value="secret-key-value",
            is_secret=True,
            description="API key for external service",
            user_id="user-123",
        )

        assert cmd.project_name == "test-project"
        assert cmd.variable_name == "API_KEY"
        assert cmd.variable_value == "secret-key-value"
        assert cmd.is_secret is True
        assert cmd.description == "API key for external service"
        assert cmd.user_id == "user-123"


class TestRemoveEnvironmentVariableCommand:
    """Tests for RemoveEnvironmentVariableCommand dataclass"""

    def test_remove_variable_command(self):
        """Test creating command to remove variable"""
        cmd = RemoveEnvironmentVariableCommand(project_name="test-project", variable_name="OLD_VAR", user_id="user-123")

        assert cmd.project_name == "test-project"
        assert cmd.variable_name == "OLD_VAR"
        assert cmd.user_id == "user-123"


class TestMountCommandCommand:
    """Tests for MountCommandCommand dataclass"""

    def test_mount_command(self):
        """Test creating command to mount a command"""
        cmd = MountCommandCommand(
            project_name="test-project",
            command_name="custom-build",
            command_path="/commands/custom-build.sh",
            description="Custom build script",
            user_id="user-123",
        )

        assert cmd.project_name == "test-project"
        assert cmd.command_name == "custom-build"
        assert cmd.command_path == "/commands/custom-build.sh"
        assert cmd.description == "Custom build script"
        assert cmd.user_id == "user-123"


class TestUnmountCommandCommand:
    """Tests for UnmountCommandCommand dataclass"""

    def test_unmount_command(self):
        """Test creating command to unmount a command"""
        cmd = UnmountCommandCommand(project_name="test-project", command_name="old-command", user_id="user-123")

        assert cmd.project_name == "test-project"
        assert cmd.command_name == "old-command"
        assert cmd.user_id == "user-123"


class TestMountSubAgentCommand:
    """Tests for MountSubAgentCommand dataclass"""

    def test_mount_subagent(self):
        """Test creating command to mount a sub-agent"""
        config = {"model": "claude-3-sonnet", "capabilities": ["code-review", "testing"]}
        cmd = MountSubAgentCommand(
            project_name="test-project",
            subagent_name="reviewer-agent",
            subagent_config=config,
            description="Code review sub-agent",
            user_id="user-123",
        )

        assert cmd.project_name == "test-project"
        assert cmd.subagent_name == "reviewer-agent"
        assert cmd.subagent_config == config
        assert cmd.description == "Code review sub-agent"
        assert cmd.user_id == "user-123"


class TestUnmountSubAgentCommand:
    """Tests for UnmountSubAgentCommand dataclass"""

    def test_unmount_subagent(self):
        """Test creating command to unmount a sub-agent"""
        cmd = UnmountSubAgentCommand(project_name="test-project", subagent_name="old-agent", user_id="user-123")

        assert cmd.project_name == "test-project"
        assert cmd.subagent_name == "old-agent"
        assert cmd.user_id == "user-123"


class TestConfigurationCommandResult:
    """Tests for ConfigurationCommandResult dataclass"""

    def test_successful_result(self):
        """Test creating successful result"""
        changes = {"github.repo": "new-owner/new-repo"}
        result = ConfigurationCommandResult(
            success=True,
            config_version=5,
            message="Configuration updated successfully",
            changes_applied=changes,
        )

        assert result.success is True
        assert result.config_version == 5
        assert result.message == "Configuration updated successfully"
        assert result.changes_applied == changes
        assert result.errors is None

    def test_failed_result_with_errors(self):
        """Test creating failed result with errors"""
        errors = ["Invalid repository format", "Missing required field"]
        result = ConfigurationCommandResult(
            success=False,
            config_version=4,
            message="Configuration update failed",
            changes_applied={},
            errors=errors,
        )

        assert result.success is False
        assert result.config_version == 4
        assert result.message == "Configuration update failed"
        assert result.changes_applied == {}
        assert result.errors == errors


@pytest.mark.asyncio
class TestConfigCommandPortBehavior:
    """Tests for expected behavior of implementations"""

    async def test_update_project_config_returns_result(self):
        """Test that update_project_config returns ConfigurationCommandResult"""

        class MockPort(IConfigurationCommandPort):
            async def update_project_config(self, command):
                return ConfigurationCommandResult(
                    success=True,
                    config_version=2,
                    message="Project config updated",
                    changes_applied=command.updates,
                )

            async def update_agent_config(self, command):
                pass

            async def update_pipeline_config(self, command):
                pass

            async def add_environment_variable(self, command):
                pass

            async def remove_environment_variable(self, command):
                pass

            async def mount_command(self, command):
                pass

            async def unmount_command(self, command):
                pass

            async def mount_subagent(self, command):
                pass

            async def unmount_subagent(self, command):
                pass

        port = MockPort()
        cmd = UpdateProjectConfigCommand(project_name="test", updates={"key": "value"}, user_id="user-123")

        result = await port.update_project_config(cmd)

        assert isinstance(result, ConfigurationCommandResult)
        assert result.success is True
        assert result.config_version == 2
        assert result.changes_applied == {"key": "value"}

    async def test_add_environment_variable_handles_secrets(self):
        """Test that add_environment_variable can handle secret variables"""

        class MockPort(IConfigurationCommandPort):
            async def update_project_config(self, command):
                pass

            async def update_agent_config(self, command):
                pass

            async def update_pipeline_config(self, command):
                pass

            async def add_environment_variable(self, command):
                # Implementation should handle encryption for secrets
                return ConfigurationCommandResult(
                    success=True,
                    config_version=3,
                    message=f"Variable '{command.variable_name}' added",
                    changes_applied={"variable_name": command.variable_name},
                )

            async def remove_environment_variable(self, command):
                pass

            async def mount_command(self, command):
                pass

            async def unmount_command(self, command):
                pass

            async def mount_subagent(self, command):
                pass

            async def unmount_subagent(self, command):
                pass

        port = MockPort()
        cmd = AddEnvironmentVariableCommand(
            project_name="test",
            variable_name="SECRET_KEY",
            variable_value="secret-value",
            is_secret=True,
            user_id="user-123",
        )

        result = await port.add_environment_variable(cmd)

        assert isinstance(result, ConfigurationCommandResult)
        assert result.success is True
        assert result.config_version == 3


@pytest.mark.asyncio
class TestConfigCommandPortErrorHandling:
    """Tests for error handling in configuration command implementations"""

    async def test_update_project_config_raises_project_not_found(self):
        """Test that update_project_config raises ProjectNotFoundError for non-existent project"""

        class MockPort(IConfigurationCommandPort):
            async def update_project_config(self, command):
                raise ProjectNotFoundError(f"Project '{command.project_name}' not found")

            async def update_agent_config(self, command):
                pass

            async def update_pipeline_config(self, command):
                pass

            async def add_environment_variable(self, command):
                pass

            async def remove_environment_variable(self, command):
                pass

            async def mount_command(self, command):
                pass

            async def unmount_command(self, command):
                pass

            async def mount_subagent(self, command):
                pass

            async def unmount_subagent(self, command):
                pass

        port = MockPort()
        cmd = UpdateProjectConfigCommand(project_name="non-existent", updates={"key": "value"}, user_id="user-123")

        with pytest.raises(ProjectNotFoundError, match="Project 'non-existent' not found"):
            await port.update_project_config(cmd)

    async def test_update_project_config_raises_validation_error(self):
        """Test that update_project_config raises ValidationError for invalid updates"""

        class MockPort(IConfigurationCommandPort):
            async def update_project_config(self, command):
                raise ValidationError("Invalid configuration format")

            async def update_agent_config(self, command):
                pass

            async def update_pipeline_config(self, command):
                pass

            async def add_environment_variable(self, command):
                pass

            async def remove_environment_variable(self, command):
                pass

            async def mount_command(self, command):
                pass

            async def unmount_command(self, command):
                pass

            async def mount_subagent(self, command):
                pass

            async def unmount_subagent(self, command):
                pass

        port = MockPort()
        cmd = UpdateProjectConfigCommand(project_name="test-project", updates={"invalid": "format"}, user_id="user-123")

        with pytest.raises(ValidationError, match="Invalid configuration format"):
            await port.update_project_config(cmd)

    async def test_update_agent_config_raises_agent_not_found(self):
        """Test that update_agent_config raises AgentNotFoundError"""

        class MockPort(IConfigurationCommandPort):
            async def update_project_config(self, command):
                pass

            async def update_agent_config(self, command):
                raise AgentNotFoundError(f"Agent '{command.agent_name}' not found")

            async def update_pipeline_config(self, command):
                pass

            async def add_environment_variable(self, command):
                pass

            async def remove_environment_variable(self, command):
                pass

            async def mount_command(self, command):
                pass

            async def unmount_command(self, command):
                pass

            async def mount_subagent(self, command):
                pass

            async def unmount_subagent(self, command):
                pass

        port = MockPort()
        cmd = UpdateAgentConfigCommand(
            project_name="test-project",
            agent_name="non-existent-agent",
            updates={"model": "claude-3-opus"},
            user_id="user-123",
        )

        with pytest.raises(AgentNotFoundError, match="Agent 'non-existent-agent' not found"):
            await port.update_agent_config(cmd)

    async def test_update_pipeline_config_raises_pipeline_not_found(self):
        """Test that update_pipeline_config raises PipelineNotFoundError"""

        class MockPort(IConfigurationCommandPort):
            async def update_project_config(self, command):
                pass

            async def update_agent_config(self, command):
                pass

            async def update_pipeline_config(self, command):
                raise PipelineNotFoundError(f"Pipeline '{command.pipeline_name}' not found")

            async def add_environment_variable(self, command):
                pass

            async def remove_environment_variable(self, command):
                pass

            async def mount_command(self, command):
                pass

            async def unmount_command(self, command):
                pass

            async def mount_subagent(self, command):
                pass

            async def unmount_subagent(self, command):
                pass

        port = MockPort()
        cmd = UpdatePipelineConfigCommand(
            project_name="test-project",
            pipeline_name="non-existent-pipeline",
            updates={"stages": ["build"]},
            user_id="user-123",
        )

        with pytest.raises(PipelineNotFoundError, match="Pipeline 'non-existent-pipeline' not found"):
            await port.update_pipeline_config(cmd)

    async def test_remove_environment_variable_raises_variable_not_found(self):
        """Test that remove_environment_variable raises VariableNotFoundError"""

        class MockPort(IConfigurationCommandPort):
            async def update_project_config(self, command):
                pass

            async def update_agent_config(self, command):
                pass

            async def update_pipeline_config(self, command):
                pass

            async def add_environment_variable(self, command):
                pass

            async def remove_environment_variable(self, command):
                raise VariableNotFoundError(f"Variable '{command.variable_name}' not found")

            async def mount_command(self, command):
                pass

            async def unmount_command(self, command):
                pass

            async def mount_subagent(self, command):
                pass

            async def unmount_subagent(self, command):
                pass

        port = MockPort()
        cmd = RemoveEnvironmentVariableCommand(
            project_name="test-project", variable_name="NON_EXISTENT_VAR", user_id="user-123"
        )

        with pytest.raises(VariableNotFoundError, match="Variable 'NON_EXISTENT_VAR' not found"):
            await port.remove_environment_variable(cmd)

    async def test_mount_command_raises_command_file_not_found(self):
        """Test that mount_command raises CommandFileNotFoundError"""

        class MockPort(IConfigurationCommandPort):
            async def update_project_config(self, command):
                pass

            async def update_agent_config(self, command):
                pass

            async def update_pipeline_config(self, command):
                pass

            async def add_environment_variable(self, command):
                pass

            async def remove_environment_variable(self, command):
                pass

            async def mount_command(self, command):
                raise CommandFileNotFoundError(f"Command file '{command.command_path}' not found")

            async def unmount_command(self, command):
                pass

            async def mount_subagent(self, command):
                pass

            async def unmount_subagent(self, command):
                pass

        port = MockPort()
        cmd = MountCommandCommand(
            project_name="test-project",
            command_name="custom-build",
            command_path="/nonexistent/command.sh",
            user_id="user-123",
        )

        with pytest.raises(CommandFileNotFoundError, match="Command file '/nonexistent/command.sh' not found"):
            await port.mount_command(cmd)

    async def test_unmount_command_raises_command_not_found(self):
        """Test that unmount_command raises CommandNotFoundError"""

        class MockPort(IConfigurationCommandPort):
            async def update_project_config(self, command):
                pass

            async def update_agent_config(self, command):
                pass

            async def update_pipeline_config(self, command):
                pass

            async def add_environment_variable(self, command):
                pass

            async def remove_environment_variable(self, command):
                pass

            async def mount_command(self, command):
                pass

            async def unmount_command(self, command):
                raise CommandNotFoundError(f"Command '{command.command_name}' not mounted")

            async def mount_subagent(self, command):
                pass

            async def unmount_subagent(self, command):
                pass

        port = MockPort()
        cmd = UnmountCommandCommand(
            project_name="test-project", command_name="non-existent-command", user_id="user-123"
        )

        with pytest.raises(CommandNotFoundError, match="Command 'non-existent-command' not mounted"):
            await port.unmount_command(cmd)

    async def test_unmount_subagent_raises_subagent_not_found(self):
        """Test that unmount_subagent raises SubAgentNotFoundError"""

        class MockPort(IConfigurationCommandPort):
            async def update_project_config(self, command):
                pass

            async def update_agent_config(self, command):
                pass

            async def update_pipeline_config(self, command):
                pass

            async def add_environment_variable(self, command):
                pass

            async def remove_environment_variable(self, command):
                pass

            async def mount_command(self, command):
                pass

            async def unmount_command(self, command):
                pass

            async def mount_subagent(self, command):
                pass

            async def unmount_subagent(self, command):
                raise SubAgentNotFoundError(f"Sub-agent '{command.subagent_name}' not mounted")

        port = MockPort()
        cmd = UnmountSubAgentCommand(
            project_name="test-project", subagent_name="non-existent-agent", user_id="user-123"
        )

        with pytest.raises(SubAgentNotFoundError, match="Sub-agent 'non-existent-agent' not mounted"):
            await port.unmount_subagent(cmd)

    async def test_operation_raises_permission_error(self):
        """Test that operations raise PermissionError when user lacks permission"""

        class MockPort(IConfigurationCommandPort):
            async def update_project_config(self, command):
                raise PermissionError(f"User '{command.user_id}' lacks permission")

            async def update_agent_config(self, command):
                pass

            async def update_pipeline_config(self, command):
                pass

            async def add_environment_variable(self, command):
                pass

            async def remove_environment_variable(self, command):
                pass

            async def mount_command(self, command):
                pass

            async def unmount_command(self, command):
                pass

            async def mount_subagent(self, command):
                pass

            async def unmount_subagent(self, command):
                pass

        port = MockPort()
        cmd = UpdateProjectConfigCommand(
            project_name="test-project", updates={"key": "value"}, user_id="unauthorized-user"
        )

        with pytest.raises(PermissionError, match="User 'unauthorized-user' lacks permission"):
            await port.update_project_config(cmd)
