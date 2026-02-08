"""Unit tests for MockProjectManagerAdapter.

Tests cover:
- Project configuration management (add, update, remove)
- Enabled project filtering
- Configuration retrieval
- Workspace path derivation
- Clone operations and event emission
- Configuration reloading
- Thread safety
- Helper methods for testing
"""

import pytest
from datetime import datetime

from codetoreum.adapters.testing.mock_project_manager_adapter import (
    MockProjectManagerAdapter,
    MockProjectState,
)
from codetoreum.adapters.testing.mock_event_emitter import MockEventEmitter
from codetoreum.domain.value_objects import ProjectConfig
from codetoreum.domain.events.project_events import (
    ProjectClonedEvent,
    ProjectCloneFailedEvent,
    ProjectEnabledEvent,
    ProjectDisabledEvent,
)
from codetoreum.ports.exceptions import (
    ExternalServiceError,
    ResourceNotFoundError,
)


@pytest.fixture
def adapter():
    """Create a fresh mock project manager adapter."""
    return MockProjectManagerAdapter()


@pytest.fixture
def config_1():
    """Sample project configuration 1."""
    return ProjectConfig(
        repo_url="https://github.com/acme/api-service.git",
        branch="main",
        enabled=True,
        org="acme",
    )


@pytest.fixture
def config_2():
    """Sample project configuration 2."""
    return ProjectConfig(
        repo_url="git@github.com:acme/web-app.git",
        branch="develop",
        enabled=False,
        org="acme",
    )


@pytest.fixture
def config_3():
    """Sample project configuration 3."""
    return ProjectConfig(
        repo_url="https://github.com/other/service",
        branch="main",
        enabled=True,
        org="other",
    )


class TestProjectConfiguration:
    """Tests for project configuration management."""

    def test_add_project(self, adapter, config_1):
        """Test adding a project configuration."""
        adapter.add_project("api-service", config_1)
        state = adapter.get_project_state("api-service")

        assert state is not None
        assert state.config == config_1
        assert state.cloned is False

    def test_add_duplicate_project_fails(self, adapter, config_1):
        """Test that adding a duplicate project raises error."""
        adapter.add_project("api-service", config_1)

        with pytest.raises(ValueError, match="already exists"):
            adapter.add_project("api-service", config_1)

    def test_update_project(self, adapter, config_1, config_2):
        """Test updating a project configuration."""
        adapter.add_project("api-service", config_1)
        adapter.update_project("api-service", config_2)

        state = adapter.get_project_state("api-service")
        assert state.config == config_2

    def test_update_nonexistent_project_fails(self, adapter, config_1):
        """Test that updating a nonexistent project raises error."""
        with pytest.raises(ResourceNotFoundError):
            adapter.update_project("nonexistent", config_1)

    def test_remove_project(self, adapter, config_1):
        """Test removing a project configuration."""
        adapter.add_project("api-service", config_1)
        adapter.remove_project("api-service")

        with pytest.raises(ResourceNotFoundError):
            adapter.remove_project("api-service")

    def test_remove_nonexistent_project_fails(self, adapter):
        """Test that removing a nonexistent project raises error."""
        with pytest.raises(ResourceNotFoundError):
            adapter.remove_project("nonexistent")

    @pytest.mark.asyncio
    async def test_clear_all_projects(self, adapter, config_1, config_2):
        """Test clearing all project configurations."""
        adapter.add_project("api-service", config_1)
        adapter.add_project("web-app", config_2)

        adapter.clear()

        with pytest.raises(ResourceNotFoundError):
            await adapter.get_project_config("api-service")


class TestGetEnabledProjects:
    """Tests for retrieving enabled projects."""

    @pytest.mark.asyncio
    async def test_get_enabled_projects_empty(self, adapter):
        """Test getting enabled projects when none exist."""
        projects = await adapter.get_enabled_projects()
        assert projects == []

    @pytest.mark.asyncio
    async def test_get_enabled_projects_single(self, adapter, config_1):
        """Test getting single enabled project."""
        adapter.add_project("api-service", config_1)

        projects = await adapter.get_enabled_projects()

        assert projects == ["api-service"]

    @pytest.mark.asyncio
    async def test_get_enabled_projects_filters_disabled(
        self, adapter, config_1, config_2
    ):
        """Test that disabled projects are filtered out."""
        adapter.add_project("api-service", config_1)
        adapter.add_project("web-app", config_2)

        projects = await adapter.get_enabled_projects()

        assert projects == ["api-service"]
        assert "web-app" not in projects

    @pytest.mark.asyncio
    async def test_get_enabled_projects_sorted(
        self, adapter, config_1, config_2, config_3
    ):
        """Test that enabled projects are returned in sorted order."""
        adapter.add_project("zebra-service", config_1)
        adapter.add_project("alpha-service", config_3)
        adapter.add_project("middle-service", config_2)

        projects = await adapter.get_enabled_projects()

        # Only zebra-service and alpha-service are enabled
        assert projects == ["alpha-service", "zebra-service"]


class TestGetProjectConfig:
    """Tests for retrieving project configurations."""

    @pytest.mark.asyncio
    async def test_get_project_config(self, adapter, config_1):
        """Test getting project configuration."""
        adapter.add_project("api-service", config_1)

        config = await adapter.get_project_config("api-service")

        assert config == config_1
        assert config.repo_url == "https://github.com/acme/api-service.git"
        assert config.branch == "main"
        assert config.enabled is True
        assert config.org == "acme"

    @pytest.mark.asyncio
    async def test_get_nonexistent_project_config_fails(self, adapter):
        """Test that getting nonexistent project config raises error."""
        with pytest.raises(
            ResourceNotFoundError, match="not found"
        ):
            await adapter.get_project_config("nonexistent")


class TestGetProjectPath:
    """Tests for workspace path derivation."""

    @pytest.mark.asyncio
    async def test_get_project_path_https_git(self, adapter, config_1):
        """Test path derivation from HTTPS .git URL."""
        adapter.add_project("api-service", config_1)

        path = await adapter.get_project_path("api-service")

        assert path == "/workspace/api-service"

    @pytest.mark.asyncio
    async def test_get_project_path_ssh_git(self, adapter, config_2):
        """Test path derivation from SSH .git URL."""
        adapter.add_project("web-app", config_2)

        path = await adapter.get_project_path("web-app")

        assert path == "/workspace/web-app"

    @pytest.mark.asyncio
    async def test_get_project_path_https_no_git(self, adapter, config_3):
        """Test path derivation from HTTPS URL without .git."""
        adapter.add_project("service", config_3)

        path = await adapter.get_project_path("service")

        assert path == "/workspace/service"

    @pytest.mark.asyncio
    async def test_get_project_path_custom_workspace(self, config_1):
        """Test path derivation with custom base workspace."""
        adapter = MockProjectManagerAdapter(base_workspace="/custom/workspace")
        adapter.add_project("api-service", config_1)

        path = await adapter.get_project_path("api-service")

        assert path == "/custom/workspace/api-service"

    @pytest.mark.asyncio
    async def test_get_nonexistent_project_path_fails(self, adapter):
        """Test that getting path for nonexistent project raises error."""
        with pytest.raises(ResourceNotFoundError, match="not found"):
            await adapter.get_project_path("nonexistent")


class TestEnsureProjectCloned:
    """Tests for clone operations and event emission."""

    @pytest.mark.asyncio
    async def test_ensure_project_cloned(self, adapter, config_1):
        """Test basic clone operation."""
        adapter.add_project("api-service", config_1)

        path = await adapter.ensure_project_cloned("api-service")

        assert path == "/workspace/api-service"

        state = adapter.get_project_state("api-service")
        assert state.cloned is True
        assert state.clone_path == "/workspace/api-service"
        assert state.clone_failures == 0

    @pytest.mark.asyncio
    async def test_clone_emits_event(self, config_1):
        """Test that successful clone emits ProjectClonedEvent."""
        emitter = MockEventEmitter()
        adapter = MockProjectManagerAdapter(event_emitter=emitter)
        adapter.add_project("api-service", config_1)

        await adapter.ensure_project_cloned("api-service")

        # Check that event was emitted
        events = emitter.get_events()
        assert any(
            isinstance(e, ProjectClonedEvent) and e.project_name == "api-service"
            for e in events
        )

    @pytest.mark.asyncio
    async def test_clone_event_contains_details(self, config_1):
        """Test that ProjectClonedEvent has correct details."""
        emitter = MockEventEmitter()
        adapter = MockProjectManagerAdapter(event_emitter=emitter)
        adapter.add_project("api-service", config_1)

        await adapter.ensure_project_cloned("api-service")

        events = [e for e in emitter.get_events() if isinstance(e, ProjectClonedEvent)]
        assert len(events) == 1

        event = events[0]
        assert event.project_name == "api-service"
        assert event.repo_url == "https://github.com/acme/api-service.git"
        assert event.workspace_path == "/workspace/api-service"
        assert event.branch == "main"

    @pytest.mark.asyncio
    async def test_clone_nonexistent_project_fails(self, adapter):
        """Test that cloning nonexistent project raises error."""
        with pytest.raises(ResourceNotFoundError):
            await adapter.ensure_project_cloned("nonexistent")

    @pytest.mark.asyncio
    async def test_clone_failure_mode(self, adapter, config_1):
        """Test clone failure simulation."""
        adapter.add_project("api-service", config_1)
        adapter.set_clone_failure_mode(True)

        with pytest.raises(ExternalServiceError, match="simulated"):
            await adapter.ensure_project_cloned("api-service")

    @pytest.mark.asyncio
    async def test_clone_failure_emits_event(self, config_1):
        """Test that clone failure emits ProjectCloneFailedEvent."""
        emitter = MockEventEmitter()
        adapter = MockProjectManagerAdapter(event_emitter=emitter)
        adapter.add_project("api-service", config_1)
        adapter.set_clone_failure_mode(True)

        with pytest.raises(ExternalServiceError):
            await adapter.ensure_project_cloned("api-service")

        events = [
            e for e in emitter.get_events() if isinstance(e, ProjectCloneFailedEvent)
        ]
        assert len(events) == 1
        assert events[0].project_name == "api-service"
        assert events[0].will_retry is True

    @pytest.mark.asyncio
    async def test_clone_failure_increments_count(self, adapter, config_1):
        """Test that clone failures increment failure count."""
        adapter.add_project("api-service", config_1)
        adapter.set_clone_failure_mode(True)

        # First failure
        with pytest.raises(ExternalServiceError):
            await adapter.ensure_project_cloned("api-service")
        assert adapter.get_clone_failure_count("api-service") == 1

        # Second failure
        with pytest.raises(ExternalServiceError):
            await adapter.ensure_project_cloned("api-service")
        assert adapter.get_clone_failure_count("api-service") == 2

    @pytest.mark.asyncio
    async def test_successful_clone_resets_failure_count(self, adapter, config_1):
        """Test that successful clone resets failure count."""
        adapter.add_project("api-service", config_1)
        adapter.set_clone_failure_mode(True)

        # Failure
        with pytest.raises(ExternalServiceError):
            await adapter.ensure_project_cloned("api-service")
        assert adapter.get_clone_failure_count("api-service") == 1

        # Disable failure mode and try again
        adapter.set_clone_failure_mode(False)
        await adapter.ensure_project_cloned("api-service")
        assert adapter.get_clone_failure_count("api-service") == 0

    @pytest.mark.asyncio
    async def test_clone_updates_timestamp(self, adapter, config_1):
        """Test that clone updates last_clone_attempt timestamp."""
        adapter.add_project("api-service", config_1)

        state = adapter.get_project_state("api-service")
        assert state.last_clone_attempt is None

        await adapter.ensure_project_cloned("api-service")

        state = adapter.get_project_state("api-service")
        assert state.last_clone_attempt is not None
        assert isinstance(state.last_clone_attempt, datetime)


class TestReloadConfig:
    """Tests for configuration reloading."""

    @pytest.mark.asyncio
    async def test_reload_config_is_noop(self, adapter, config_1):
        """Test that reload_config is a no-op in mock implementation."""
        adapter.add_project("api-service", config_1)

        # Should not raise or modify state
        await adapter.reload_config()

        # Verify state unchanged
        config = await adapter.get_project_config("api-service")
        assert config == config_1


class TestEventEmitterIntegration:
    """Tests for event emitter integration."""

    @pytest.mark.asyncio
    async def test_no_emitter_by_default(self, adapter, config_1):
        """Test that clone succeeds even without emitter."""
        adapter.add_project("api-service", config_1)

        # Should not raise
        path = await adapter.ensure_project_cloned("api-service")
        assert path == "/workspace/api-service"

    @pytest.mark.asyncio
    async def test_set_event_emitter(self, adapter, config_1):
        """Test setting event emitter after construction."""
        adapter.add_project("api-service", config_1)
        emitter = MockEventEmitter()
        adapter.set_event_emitter(emitter)

        await adapter.ensure_project_cloned("api-service")

        events = [
            e for e in emitter.get_events() if isinstance(e, ProjectClonedEvent)
        ]
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_emitter_in_constructor(self, config_1):
        """Test providing emitter in constructor."""
        emitter = MockEventEmitter()
        adapter = MockProjectManagerAdapter(event_emitter=emitter)
        adapter.add_project("api-service", config_1)

        await adapter.ensure_project_cloned("api-service")

        events = [
            e for e in emitter.get_events() if isinstance(e, ProjectClonedEvent)
        ]
        assert len(events) == 1


class TestHelperMethods:
    """Tests for testing helper methods."""

    def test_get_clone_failure_count_nonexistent_project(self, adapter):
        """Test getting failure count for nonexistent project raises error."""
        with pytest.raises(ResourceNotFoundError):
            adapter.get_clone_failure_count("nonexistent")

    def test_set_clone_failure_mode(self, adapter, config_1):
        """Test toggling clone failure mode."""
        adapter.add_project("api-service", config_1)

        adapter.set_clone_failure_mode(True)
        assert adapter._clone_failure_mode is True

        adapter.set_clone_failure_mode(False)
        assert adapter._clone_failure_mode is False

    @pytest.mark.asyncio
    async def test_multiple_projects_independent_clones(self, adapter, config_1, config_2):
        """Test that projects can be cloned independently."""
        adapter.add_project("api-service", config_1)
        adapter.add_project("web-app", config_2)

        # Clone only api-service
        await adapter.ensure_project_cloned("api-service")

        api_state = adapter.get_project_state("api-service")
        web_state = adapter.get_project_state("web-app")

        assert api_state.cloned is True
        assert web_state.cloned is False


class TestMockProjectState:
    """Tests for MockProjectState dataclass."""

    def test_project_state_creation(self, config_1):
        """Test creating a project state."""
        state = MockProjectState(config=config_1)

        assert state.config == config_1
        assert state.cloned is False
        assert state.clone_path == ""
        assert state.last_clone_attempt is None
        assert state.clone_failures == 0

    def test_project_state_with_cloned(self, config_1):
        """Test project state with cloned=True."""
        state = MockProjectState(
            config=config_1,
            cloned=True,
            clone_path="/workspace/api-service",
        )

        assert state.cloned is True
        assert state.clone_path == "/workspace/api-service"


class TestConcurrency:
    """Tests for thread safety."""

    def test_concurrent_add_projects(self, adapter, config_1, config_2):
        """Test that adding projects is thread-safe."""
        import threading

        def add_project(name, config):
            adapter.add_project(name, config)

        threads = [
            threading.Thread(target=add_project, args=("api-service", config_1)),
            threading.Thread(target=add_project, args=("web-app", config_2)),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Both projects should be added
        assert adapter.get_project_state("api-service") is not None
        assert adapter.get_project_state("web-app") is not None
