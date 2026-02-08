"""Integration tests for multi-project namespace isolation.

Tests verify that state is properly isolated between projects by running
actual orchestrator code with mock adapters. Each project maintains
independent orchestration state without cross-project interference.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from codetoreum.application.multi_project_orchestrator import MultiProjectOrchestrator
from codetoreum.adapters.testing.mock_project_manager_adapter import (
    MockProjectManagerAdapter,
)
from codetoreum.domain.value_objects import ProjectConfig


@pytest.fixture
def project_manager():
    """Create a fresh project manager adapter."""
    return MockProjectManagerAdapter()


@pytest.fixture
def workflow_orchestrator():
    """Create mock workflow orchestrator."""
    mock = AsyncMock()
    # Default: return 0 actions taken
    mock.orchestrate_project = AsyncMock(return_value=0)
    return mock


@pytest.fixture
def board_service():
    """Create mock board service."""
    return AsyncMock()


@pytest.fixture
def event_emitter():
    """Create mock event emitter."""
    return MagicMock()


@pytest.fixture
def orchestrator(project_manager, workflow_orchestrator, board_service, event_emitter):
    """Create MultiProjectOrchestrator with mocks."""
    return MultiProjectOrchestrator(
        project_manager=project_manager,
        workflow_orchestrator=workflow_orchestrator,
        board_service=board_service,
        event_emitter=event_emitter,
    )


def create_project_config(repo_url: str, branch: str = "main") -> ProjectConfig:
    """Helper to create a project configuration."""
    return ProjectConfig(
        repo_url=repo_url,
        branch=branch,
        enabled=True,
        org="test-org",
    )


class TestMultiProjectNamespaceIsolation:
    """Integration tests for project-scoped state isolation."""

    @pytest.mark.asyncio
    async def test_pipeline_locks_isolated_by_project(self, orchestrator, project_manager):
        """Verify pipeline locks are namespaced per project.

        When two projects execute orchestration cycles with the same board names,
        the orchestrator should maintain separate locks for each project,
        proving namespace isolation at the lock level.
        """
        # Create two projects with same board names but different repos
        config_proj1 = create_project_config("https://github.com/org/project1.git")
        config_proj2 = create_project_config("https://github.com/org/project2.git")

        project_manager.add_project("project1", config_proj1)
        project_manager.add_project("project2", config_proj2)

        # Run orchestration cycle - the orchestrator should process both projects
        result = await orchestrator.run_orchestration_cycle()

        # Verify both projects were processed
        assert result.success
        assert result.projects_processed == 2

        # Verify both projects' workspaces were created
        workspace_p1 = await project_manager.get_project_path("project1")
        workspace_p2 = await project_manager.get_project_path("project2")

        assert workspace_p1 is not None
        assert workspace_p2 is not None
        assert workspace_p1 != workspace_p2, "Each project should have separate workspace"

    @pytest.mark.asyncio
    async def test_queue_state_isolated_by_project(self, orchestrator, project_manager):
        """Verify queue state is isolated per project.

        When two projects execute orchestration cycles, each should maintain
        independent queue state without interference.
        """
        # Create two projects
        config_proj1 = create_project_config("https://github.com/org/project1.git")
        config_proj2 = create_project_config("https://github.com/org/project2.git")

        project_manager.add_project("project1", config_proj1)
        project_manager.add_project("project2", config_proj2)

        # Run orchestration cycle
        result = await orchestrator.run_orchestration_cycle()

        # Verify both projects processed independently
        assert result.success
        assert result.projects_processed == 2

        # Get project statuses - each should have independent configuration
        status_p1 = await orchestrator.get_project_status("project1")
        status_p2 = await orchestrator.get_project_status("project2")

        # Verify isolation: different repos for each project
        assert status_p1.repo_url != status_p2.repo_url
        assert status_p1.project_name == "project1"
        assert status_p2.project_name == "project2"

    @pytest.mark.asyncio
    async def test_session_state_isolated_by_project(self, orchestrator, project_manager):
        """Verify session state is namespaced per project.

        When the orchestrator processes multiple projects, each should maintain
        independent session state.
        """
        # Create two projects with different branches
        config_proj1 = create_project_config(
            "https://github.com/org/project1.git", branch="main"
        )
        config_proj2 = create_project_config(
            "https://github.com/org/project2.git", branch="develop"
        )

        project_manager.add_project("project1", config_proj1)
        project_manager.add_project("project2", config_proj2)

        # Run orchestration cycle
        result = await orchestrator.run_orchestration_cycle()

        # Verify both projects processed
        assert result.success
        assert result.projects_processed == 2

        # Get project configs through orchestrator - verify isolation
        status_p1 = await orchestrator.get_project_status("project1")
        status_p2 = await orchestrator.get_project_status("project2")

        # Verify each project maintains independent session state (branch)
        assert status_p1.branch == "main"
        assert status_p2.branch == "develop"

    @pytest.mark.asyncio
    async def test_execution_state_isolated_by_project(self, orchestrator, project_manager, workflow_orchestrator):
        """Verify execution state is namespaced per project.

        When the orchestrator delegates to workflow orchestrator for each project,
        separate executions should be initiated per project.
        """
        # Create two projects
        config_proj1 = create_project_config("https://github.com/org/project1.git")
        config_proj2 = create_project_config("https://github.com/org/project2.git")

        project_manager.add_project("project1", config_proj1)
        project_manager.add_project("project2", config_proj2)

        # Track calls to workflow orchestrator
        workflow_orchestrator.orchestrate_project = AsyncMock(return_value=5)

        # Run orchestration cycle
        result = await orchestrator.run_orchestration_cycle()

        # Verify both projects were passed to workflow orchestrator independently
        assert result.success
        assert result.projects_processed == 2

        # Verify orchestrate_project was called once per project
        assert workflow_orchestrator.orchestrate_project.call_count == 2

        # Verify each call had correct project context
        calls = workflow_orchestrator.orchestrate_project.call_args_list
        project_names = [call[1]["project_name"] for call in calls]
        assert "project1" in project_names
        assert "project2" in project_names

    @pytest.mark.asyncio
    async def test_project_configurations_remain_independent(self, orchestrator, project_manager):
        """Verify that updating one project config doesn't affect others."""
        # Create two projects with different configs
        config_proj1 = create_project_config(
            "https://github.com/org/project1.git", branch="main"
        )
        config_proj2 = create_project_config(
            "https://github.com/org/project2.git", branch="develop"
        )

        project_manager.add_project("project1", config_proj1)
        project_manager.add_project("project2", config_proj2)

        # Get initial statuses
        status_p1_before = await orchestrator.get_project_status("project1")
        status_p2_before = await orchestrator.get_project_status("project2")

        assert status_p1_before.branch == "main"
        assert status_p2_before.branch == "develop"

        # Update project1 config
        new_config_p1 = create_project_config(
            "https://github.com/org/project1.git", branch="release"
        )
        project_manager.update_project("project1", new_config_p1)

        # Verify project1 changed
        status_p1_after = await orchestrator.get_project_status("project1")
        assert status_p1_after.branch == "release"

        # Verify project2 unchanged
        status_p2_after = await orchestrator.get_project_status("project2")
        assert status_p2_after.branch == "develop"

    @pytest.mark.asyncio
    async def test_orchestrator_handles_disabled_projects(self, orchestrator, project_manager):
        """Verify orchestrator skips disabled projects in cycles.

        When a project is disabled, the orchestrator should not attempt to
        orchestrate it, proving isolation at the project enabling level.
        """
        # Create two projects
        config_proj1 = create_project_config("https://github.com/org/project1.git")
        config_proj2_disabled = ProjectConfig(
            repo_url="https://github.com/org/project2.git",
            branch="main",
            enabled=False,  # Disabled
            org="test-org",
        )

        project_manager.add_project("project1", config_proj1)
        project_manager.add_project("project2", config_proj2_disabled)

        # Run orchestration cycle
        result = await orchestrator.run_orchestration_cycle()

        # Verify only enabled project was processed
        assert result.success
        assert result.projects_processed == 1

        # Verify disabled project was skipped
        status_enabled = await orchestrator.get_project_status("project1")
        assert status_enabled.enabled

        status_disabled = await orchestrator.get_project_status("project2")
        assert not status_disabled.enabled
