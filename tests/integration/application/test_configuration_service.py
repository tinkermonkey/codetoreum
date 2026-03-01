"""
Integration tests for Configuration Service.

Tests configuration service with in-memory adapters to verify:
- Configuration loading and caching
- Configuration validation
- Configuration updates with versioning
- Event emission
"""

from datetime import UTC, datetime

import pytest

from codetoreum.adapters.testing.in_memory_config_store import InMemoryConfigStore
from codetoreum.adapters.testing.in_memory_event_store import InMemoryEventStore
from codetoreum.application.configuration_service import ConfigurationService
from codetoreum.domain.events import (
    AgentConfigUpdated,
    CommandMounted,
    EnvironmentVariableChanged,
    PipelineConfigUpdated,
    ProjectConfigUpdated,
    SubAgentMounted,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.input.config_command import (
    AddEnvironmentVariableCommand,
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
    ConfigNotFoundError,
    ProjectConfig,
)


@pytest.fixture
async def config_store():
    """Create in-memory config store."""
    store = InMemoryConfigStore()
    yield store
    store.clear()


@pytest.fixture
async def event_store():
    """Create in-memory event store."""
    store = InMemoryEventStore()
    yield store
    store.clear()


@pytest.fixture
async def event_bus(event_store):
    """Create event bus with in-memory event store."""
    from codetoreum.infrastructure.event_bus import EventHandler

    bus = EventBus()

    # Create handler that persists events to event store
    class EventStoreHandler(EventHandler):
        def __init__(self, store):
            self.store = store

        async def handle(self, event):
            await self.store.append(event.aggregate_id, [event])

        def get_event_types(self):
            return []  # Wildcard handler - receives all events

    handler = EventStoreHandler(event_store)
    bus.register_handler(handler)
    yield bus
    # Cleanup: unregister all handlers
    bus.unregister_handler(handler)
    for handlers in list(bus._handlers.values()):
        for h in list(handlers):
            bus.unregister_handler(h)
    for h in list(bus._wildcard_handlers):
        bus.unregister_handler(h)
    bus.reset_statistics()


@pytest.fixture
async def config_service(config_store, event_bus):
    """Create configuration service with mock adapters."""
    return ConfigurationService(config_store, event_bus)


@pytest.fixture
async def sample_project(config_store):
    """Create sample project configuration."""
    project = ProjectConfig(
        id="proj-1",
        name="test-project",
        github_org="test-org",
        github_repo="test-repo",
        tech_stacks={"language": "python", "framework": "fastapi"},
        pipelines=[],
        testing={"command": "pytest", "directory": "tests"},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await config_store.save_project_config(project)
    return project


class TestProjectConfigUpdate:
    """Tests for project configuration updates."""

    @pytest.mark.asyncio
    async def test_update_project_config_success(self, config_service, sample_project, event_store):
        """Test successful project config update."""
        command = UpdateProjectConfigCommand(
            project_name="test-project",
            updates={
                "tech_stacks": {"language": "python", "framework": "django"},
                "testing": {"command": "pytest -v", "directory": "tests"},
            },
            user_id="user-1",
            reason="Update tech stack",
        )

        result = await config_service.update_project_config(command)

        assert result.success
        assert result.config_version == 2
        assert "tech_stacks" in result.changes_applied
        assert result.message.startswith("Project config updated")

        # Verify event emitted
        events = await event_store.get_events(sample_project.id)
        assert len(events) == 1
        assert isinstance(events[0], ProjectConfigUpdated)
        assert events[0].payload["version"] == 2
        assert events[0].payload["updated_by"] == "user-1"

    @pytest.mark.asyncio
    async def test_update_project_config_not_found(self, config_service):
        """Test update fails for non-existent project."""
        command = UpdateProjectConfigCommand(
            project_name="non-existent",
            updates={"tech_stacks": {"language": "python"}},
            user_id="user-1",
        )

        with pytest.raises(ConfigNotFoundError):
            await config_service.update_project_config(command)

    @pytest.mark.asyncio
    async def test_update_project_config_validation_error(self, config_service, sample_project):
        """Test update fails with invalid updates."""
        command = UpdateProjectConfigCommand(
            project_name="test-project",
            updates={"pipelines": "invalid"},  # Should be list
            user_id="user-1",
        )

        with pytest.raises(ValidationError):
            await config_service.update_project_config(command)

    @pytest.mark.asyncio
    async def test_update_project_config_versioning(self, config_service, sample_project, config_store):
        """Test version increments on each update."""
        for i in range(3):
            command = UpdateProjectConfigCommand(
                project_name="test-project",
                updates={"tech_stacks": {"version": str(i)}},
                user_id="user-1",
            )
            result = await config_service.update_project_config(command)
            assert result.config_version == i + 2  # Started at v1


class TestAgentConfigUpdate:
    """Tests for agent configuration updates."""

    @pytest.mark.asyncio
    async def test_update_agent_config_success(self, config_service, sample_project, event_store):
        """Test successful agent config update."""
        command = UpdateAgentConfigCommand(
            project_name="test-project",
            agent_name="test-agent",
            updates={
                "model": "claude-sonnet-4",
                "timeout": 7200,
                "mcp_servers": ["server1", "server2"],
            },
            user_id="user-1",
        )

        result = await config_service.update_agent_config(command)

        assert result.success
        assert result.config_version == 2
        assert "model" in result.changes_applied

        # Verify event emitted
        events = await event_store.get_events(f"{sample_project.id}:test-agent")
        assert len(events) == 1
        assert isinstance(events[0], AgentConfigUpdated)

    @pytest.mark.asyncio
    async def test_update_agent_config_creates_if_not_exists(self, config_service, sample_project, config_store):
        """Test agent config is created if doesn't exist."""
        command = UpdateAgentConfigCommand(
            project_name="test-project",
            agent_name="new-agent",
            updates={"model": "claude-sonnet-4"},
            user_id="user-1",
        )

        result = await config_service.update_agent_config(command)

        assert result.success
        # Verify agent was created
        agent = await config_store.get_agent_config(sample_project.id, "new-agent")
        assert agent.model == "claude-sonnet-4"

    @pytest.mark.asyncio
    async def test_update_agent_config_validation_error(self, config_service, sample_project):
        """Test update fails with invalid model."""
        command = UpdateAgentConfigCommand(
            project_name="test-project",
            agent_name="test-agent",
            updates={"model": "invalid-model"},
            user_id="user-1",
        )

        with pytest.raises(ValidationError):
            await config_service.update_agent_config(command)


class TestPipelineConfigUpdate:
    """Tests for pipeline configuration updates."""

    @pytest.mark.asyncio
    async def test_update_pipeline_config_success(self, config_service, sample_project, event_store):
        """Test successful pipeline config update."""
        command = UpdatePipelineConfigCommand(
            project_name="test-project",
            pipeline_name="test-pipeline",
            updates={
                "stages": [
                    {"name": "stage1", "agent": "agent1"},
                    {"name": "stage2", "agent": "agent2"},
                ],
                "triggers": ["label:feature"],
            },
            user_id="user-1",
        )

        result = await config_service.update_pipeline_config(command)

        assert result.success
        assert result.config_version == 2

        # Verify event emitted
        events = await event_store.get_events(f"{sample_project.id}:test-pipeline")
        assert len(events) == 1
        assert isinstance(events[0], PipelineConfigUpdated)


class TestEnvironmentVariables:
    """Tests for environment variable management."""

    @pytest.mark.asyncio
    async def test_add_environment_variable_success(self, config_service, sample_project, event_store, config_store):
        """Test adding environment variable."""
        command = AddEnvironmentVariableCommand(
            project_name="test-project",
            variable_name="API_KEY",
            variable_value="test-key",
            is_secret=True,
            description="Test API key",
            user_id="user-1",
        )

        result = await config_service.add_environment_variable(command)

        assert result.success
        assert result.message == "Environment variable 'API_KEY' added"

        # Verify variable was added
        project = await config_store.get_project_config(sample_project.id)
        assert "API_KEY" in project.environment_variables
        assert project.environment_variables["API_KEY"]["is_secret"] is True

        # Verify event emitted
        events = await event_store.get_events(sample_project.id)
        assert len(events) == 1
        assert isinstance(events[0], EnvironmentVariableChanged)
        assert events[0].payload["action"] == "added"

    @pytest.mark.asyncio
    async def test_update_environment_variable(self, config_service, sample_project, config_store):
        """Test updating existing environment variable."""
        # Add initial variable
        command1 = AddEnvironmentVariableCommand(
            project_name="test-project",
            variable_name="TEST_VAR",
            variable_value="value1",
            user_id="user-1",
        )
        await config_service.add_environment_variable(command1)

        # Update variable
        command2 = AddEnvironmentVariableCommand(
            project_name="test-project",
            variable_name="TEST_VAR",
            variable_value="value2",
            user_id="user-1",
        )
        result = await config_service.add_environment_variable(command2)

        assert result.success
        assert "updated" in result.message

    @pytest.mark.asyncio
    async def test_remove_environment_variable_success(self, config_service, sample_project, config_store, event_store):
        """Test removing environment variable."""
        # Add variable first
        add_command = AddEnvironmentVariableCommand(
            project_name="test-project",
            variable_name="REMOVE_ME",
            variable_value="test",
            user_id="user-1",
        )
        await config_service.add_environment_variable(add_command)

        # Remove variable
        remove_command = RemoveEnvironmentVariableCommand(
            project_name="test-project",
            variable_name="REMOVE_ME",
            user_id="user-1",
        )
        result = await config_service.remove_environment_variable(remove_command)

        assert result.success
        assert result.message == "Environment variable 'REMOVE_ME' removed"

        # Verify variable was removed
        project = await config_store.get_project_config(sample_project.id)
        assert "REMOVE_ME" not in project.environment_variables

    @pytest.mark.asyncio
    async def test_remove_nonexistent_variable_error(self, config_service, sample_project):
        """Test removing non-existent variable fails."""
        command = RemoveEnvironmentVariableCommand(
            project_name="test-project",
            variable_name="NONEXISTENT",
            user_id="user-1",
        )

        with pytest.raises(ValidationError):
            await config_service.remove_environment_variable(command)

    @pytest.mark.asyncio
    async def test_environment_variable_validation(self, config_service, sample_project):
        """Test environment variable name validation."""
        # Invalid name (lowercase)
        command = AddEnvironmentVariableCommand(
            project_name="test-project",
            variable_name="invalid_name",
            variable_value="value",
            user_id="user-1",
        )

        with pytest.raises(ValidationError):
            await config_service.add_environment_variable(command)

    @pytest.mark.asyncio
    async def test_reserved_variable_name_error(self, config_service, sample_project):
        """Test reserved variable names are rejected."""
        command = AddEnvironmentVariableCommand(
            project_name="test-project",
            variable_name="PATH",
            variable_value="/usr/bin",
            user_id="user-1",
        )

        with pytest.raises(ValidationError):
            await config_service.add_environment_variable(command)


class TestCommandMounting:
    """Tests for command mounting/unmounting."""

    @pytest.mark.asyncio
    async def test_mount_command_success(self, config_service, sample_project, event_store, config_store, tmp_path):
        """Test mounting command."""
        # Create temporary command file
        command_file = tmp_path / "test_command.md"
        command_file.write_text("# Test Command\n\nTest command content")

        command = MountCommandCommand(
            project_name="test-project",
            command_name="test-cmd",
            command_path=str(command_file),
            description="Test command",
            user_id="user-1",
        )

        result = await config_service.mount_command(command)

        assert result.success
        assert result.message == "Command 'test-cmd' mounted"

        # Verify command was mounted
        project = await config_store.get_project_config(sample_project.id)
        assert "test-cmd" in project.mounted_commands

        # Verify event emitted
        events = await event_store.get_events(sample_project.id)
        assert len(events) == 1
        assert isinstance(events[0], CommandMounted)

    @pytest.mark.asyncio
    async def test_mount_command_file_not_found(self, config_service, sample_project):
        """Test mounting non-existent command file fails."""
        command = MountCommandCommand(
            project_name="test-project",
            command_name="test-cmd",
            command_path="/nonexistent/file.md",
            user_id="user-1",
        )

        with pytest.raises(ValidationError):
            await config_service.mount_command(command)

    @pytest.mark.asyncio
    async def test_mount_command_invalid_extension(self, config_service, sample_project, tmp_path):
        """Test mounting non-.md file fails."""
        command_file = tmp_path / "test_command.txt"
        command_file.write_text("Test content")

        command = MountCommandCommand(
            project_name="test-project",
            command_name="test-cmd",
            command_path=str(command_file),
            user_id="user-1",
        )

        with pytest.raises(ValidationError):
            await config_service.mount_command(command)

    @pytest.mark.asyncio
    async def test_unmount_command_success(self, config_service, sample_project, config_store, tmp_path):
        """Test unmounting command."""
        # Mount command first
        command_file = tmp_path / "test_command.md"
        command_file.write_text("# Test Command")

        mount_cmd = MountCommandCommand(
            project_name="test-project",
            command_name="test-cmd",
            command_path=str(command_file),
            user_id="user-1",
        )
        await config_service.mount_command(mount_cmd)

        # Unmount command
        unmount_cmd = UnmountCommandCommand(
            project_name="test-project",
            command_name="test-cmd",
            user_id="user-1",
        )
        result = await config_service.unmount_command(unmount_cmd)

        assert result.success
        assert result.message == "Command 'test-cmd' unmounted"

        # Verify command was unmounted
        project = await config_store.get_project_config(sample_project.id)
        assert "test-cmd" not in project.mounted_commands

    @pytest.mark.asyncio
    async def test_unmount_nonexistent_command_error(self, config_service, sample_project):
        """Test unmounting non-existent command fails."""
        command = UnmountCommandCommand(
            project_name="test-project",
            command_name="nonexistent",
            user_id="user-1",
        )

        with pytest.raises(ValidationError):
            await config_service.unmount_command(command)


class TestSubAgentMounting:
    """Tests for sub-agent mounting/unmounting."""

    @pytest.mark.asyncio
    async def test_mount_subagent_success(self, config_service, sample_project, event_store, config_store):
        """Test mounting sub-agent."""
        command = MountSubAgentCommand(
            project_name="test-project",
            subagent_name="test-subagent",
            subagent_config={
                "name": "test-subagent",
                "type": "specialized",
                "model": "claude-sonnet-4",
            },
            description="Test sub-agent",
            user_id="user-1",
        )

        result = await config_service.mount_subagent(command)

        assert result.success
        assert result.message == "Sub-agent 'test-subagent' mounted"

        # Verify sub-agent was mounted
        project = await config_store.get_project_config(sample_project.id)
        assert "test-subagent" in project.mounted_subagents

        # Verify event emitted
        events = await event_store.get_events(sample_project.id)
        assert len(events) == 1
        assert isinstance(events[0], SubAgentMounted)

    @pytest.mark.asyncio
    async def test_mount_subagent_validation_error(self, config_service, sample_project):
        """Test mounting sub-agent with invalid config fails."""
        command = MountSubAgentCommand(
            project_name="test-project",
            subagent_name="test-subagent",
            subagent_config={"invalid": "config"},  # Missing required fields
            user_id="user-1",
        )

        with pytest.raises(ValidationError):
            await config_service.mount_subagent(command)

    @pytest.mark.asyncio
    async def test_unmount_subagent_success(self, config_service, sample_project, config_store):
        """Test unmounting sub-agent."""
        # Mount sub-agent first
        mount_cmd = MountSubAgentCommand(
            project_name="test-project",
            subagent_name="test-subagent",
            subagent_config={
                "name": "test-subagent",
                "type": "specialized",
            },
            user_id="user-1",
        )
        await config_service.mount_subagent(mount_cmd)

        # Unmount sub-agent
        unmount_cmd = UnmountSubAgentCommand(
            project_name="test-project",
            subagent_name="test-subagent",
            user_id="user-1",
        )
        result = await config_service.unmount_subagent(unmount_cmd)

        assert result.success
        assert result.message == "Sub-agent 'test-subagent' unmounted"

        # Verify sub-agent was unmounted
        project = await config_store.get_project_config(sample_project.id)
        assert "test-subagent" not in project.mounted_subagents


class TestConfigurationCaching:
    """Tests for configuration caching and versioning."""

    @pytest.mark.asyncio
    async def test_version_history_tracking(self, config_service, sample_project, config_store):
        """Test version history is tracked correctly."""
        # Make multiple updates
        for i in range(3):
            command = UpdateProjectConfigCommand(
                project_name="test-project",
                updates={"tech_stacks": {"update": str(i)}},
                user_id="user-1",
                reason=f"Update {i}",
            )
            await config_service.update_project_config(command)

        # Check history
        versions = await config_store.list_config_versions(sample_project.id)
        assert len(versions) == 3
        assert versions[0].version == 4  # Latest first
        assert versions[2].version == 2  # Oldest last

    @pytest.mark.asyncio
    async def test_concurrent_updates_version_increment(self, config_service, sample_project, config_store):
        """Test version increments correctly with multiple updates."""
        initial_version = sample_project.version

        # Simulate concurrent updates
        commands = [
            UpdateProjectConfigCommand(
                project_name="test-project",
                updates={"tech_stacks": {"concurrent": str(i)}},
                user_id=f"user-{i}",
            )
            for i in range(5)
        ]

        for cmd in commands:
            await config_service.update_project_config(cmd)

        # Verify final version
        project = await config_store.get_project_config(sample_project.id)
        assert project.version == initial_version + 5


# New tests for revision 1


@pytest.mark.asyncio
async def test_concurrent_configuration_updates(config_service, config_store, sample_project):
    """Test that concurrent updates are properly serialized with locks."""
    import asyncio

    # Create multiple concurrent update tasks
    async def update_tech_stack(stack_name: str):
        command = UpdateProjectConfigCommand(
            project_name=sample_project.name,
            updates={"tech_stacks": {stack_name: "1.0.0"}},
            user_id="test_user",
        )
        return await config_service.update_project_config(command)

    # Run 10 concurrent updates
    tasks = [update_tech_stack(f"stack_{i}") for i in range(10)]
    results = await asyncio.gather(*tasks)

    # All should succeed
    assert all(r.success for r in results)

    # Verify all tech stacks were added
    project = await config_store.get_project_config(sample_project.id)
    assert len(project.tech_stacks) >= 10  # At least the 10 we added

    # Version should be initial + 10 (one for each update)
    assert project.version == 11  # Initial version 1 + 10 updates


@pytest.mark.asyncio
async def test_large_configuration_objects(config_service, config_store, sample_project):
    """Test handling of large configuration objects."""
    # Create a large configuration with many pipelines
    large_pipelines = [
        {
            "name": f"pipeline_{i}",
            "stages": [{"name": f"stage_{j}", "agent": "test_agent"} for j in range(20)],  # 20 stages per pipeline
        }
        for i in range(50)  # 50 pipelines
    ]

    command = UpdateProjectConfigCommand(
        project_name=sample_project.name,
        updates={"pipelines": large_pipelines},
        user_id="test_user",
    )

    result = await config_service.update_project_config(command)
    assert result.success

    # Verify all pipelines were saved
    project = await config_store.get_project_config(sample_project.id)
    assert len(project.pipelines) == 50
    assert all(len(p["stages"]) == 20 for p in project.pipelines)


@pytest.mark.asyncio
async def test_malformed_json_in_configuration(config_service, sample_project):
    """Test handling of malformed/invalid JSON-like structures."""
    # Try to update with invalid pipeline structure
    command = UpdateProjectConfigCommand(
        project_name=sample_project.name,
        updates={
            "pipelines": "not_a_list",  # Should be a list
        },
        user_id="test_user",
    )

    with pytest.raises(ValidationError) as exc_info:
        await config_service.update_project_config(command)

    assert "pipelines must be a list" in str(exc_info.value)


@pytest.mark.asyncio
async def test_search_functionality(config_store, sample_project):
    """Test configuration search functionality."""
    # Save a few more projects with different names
    project1 = ProjectConfig(
        id="proj-api-gateway",
        name="api-gateway-service",
        github_org="test",
        github_repo="api-gateway",
        tech_stacks={"python": "3.11"},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    project2 = ProjectConfig(
        id="proj-user-service",
        name="user-management",
        github_org="test",
        github_repo="users",
        tech_stacks={"java": "17"},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await config_store.save_project_config(project1)
    await config_store.save_project_config(project2)

    # Test search for single term
    results = await config_store.search_configs("gateway")
    assert len(results) > 0
    assert any("gateway" in str(r).lower() for r in results)

    # Test search for multiple terms (AND search)
    results = await config_store.search_configs("api gateway")
    assert len(results) > 0
    # Should match project1 which has both "api" and "gateway"

    # Test search with no results
    results = await config_store.search_configs("nonexistent_term_xyz")
    assert len(results) == 0


@pytest.mark.asyncio
async def test_encryption_service_integration(config_store, event_bus, sample_project):
    """Test integration with encryption service for secrets."""
    from codetoreum.adapters.testing.simple_encryption_adapter import (
        SimpleEncryptionAdapter,
    )

    encryption_service = SimpleEncryptionAdapter()
    config_service = ConfigurationService(
        config_store=config_store,
        event_bus=event_bus,
        encryption_service=encryption_service,
    )

    # Add a secret environment variable
    command = AddEnvironmentVariableCommand(
        project_name=sample_project.name,
        variable_name="API_SECRET_KEY",
        variable_value="my-super-secret-key-12345",
        is_secret=True,
        user_id="test_user",
    )

    result = await config_service.add_environment_variable(command)
    assert result.success

    # Verify the secret is encrypted in storage
    project = await config_store.get_project_config(sample_project.id)
    stored_value = project.environment_variables["API_SECRET_KEY"]["value"]

    # Should not be plaintext
    assert stored_value != "my-super-secret-key-12345"

    # Should be in encrypted format (key_id:nonce:ciphertext)
    assert stored_value.count(":") == 2

    # Verify we can decrypt it
    decrypted = await encryption_service.decrypt(stored_value)
    assert decrypted == "my-super-secret-key-12345"


@pytest.mark.asyncio
async def test_pipeline_stage_uniqueness_validation(config_service, sample_project):
    """Test validation of pipeline stage name uniqueness."""
    command = UpdatePipelineConfigCommand(
        project_name=sample_project.name,
        pipeline_name="test-pipeline",
        updates={
            "stages": [
                {"name": "build", "agent": "builder"},
                {"name": "test", "agent": "tester"},
                {"name": "build", "agent": "duplicate"},  # Duplicate name
            ]
        },
        user_id="test_user",
    )

    with pytest.raises(ValidationError) as exc_info:
        await config_service.update_pipeline_config(command)

    assert "stage names must be unique" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_pipeline_circular_dependency_detection(config_service, sample_project):
    """Test detection of circular dependencies in pipeline stages."""
    command = UpdatePipelineConfigCommand(
        project_name=sample_project.name,
        pipeline_name="test-pipeline",
        updates={
            "stages": [
                {"name": "A", "agent": "agent1", "transitions": ["B"]},
                {"name": "B", "agent": "agent2", "transitions": ["C"]},
                {"name": "C", "agent": "agent3", "transitions": ["A"]},  # Circular!
            ]
        },
        user_id="test_user",
    )

    with pytest.raises(ValidationError) as exc_info:
        await config_service.update_pipeline_config(command)

    assert "circular dependency" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_reserved_environment_variable_validation(config_service, sample_project):
    """Test that reserved environment variables are rejected."""
    reserved_vars = ["PATH", "HOME", "USER", "SHELL"]

    for var_name in reserved_vars:
        command = AddEnvironmentVariableCommand(
            project_name=sample_project.name,
            variable_name=var_name,
            variable_value="some_value",
            user_id="test_user",
        )

        with pytest.raises(ValidationError) as exc_info:
            await config_service.add_environment_variable(command)

        assert "reserved" in str(exc_info.value).lower()




@pytest.mark.asyncio
async def test_concurrent_agent_config_updates(config_service, config_store, sample_project):
    """Test concurrent updates to different agent configurations."""
    import asyncio

    async def update_agent_timeout(agent_name: str, timeout: int):
        command = UpdateAgentConfigCommand(
            project_name=sample_project.name,
            agent_name=agent_name,
            updates={"timeout": timeout},
            user_id="test_user",
        )
        return await config_service.update_agent_config(command)

    # Update 5 different agents concurrently
    tasks = [update_agent_timeout(f"agent_{i}", 3600 + i * 100) for i in range(5)]
    results = await asyncio.gather(*tasks)

    # All should succeed
    assert all(r.success for r in results)

    # Verify all agents were configured
    for i in range(5):
        agent_config = await config_store.get_agent_config(sample_project.id, f"agent_{i}")
        assert agent_config.timeout == 3600 + i * 100
