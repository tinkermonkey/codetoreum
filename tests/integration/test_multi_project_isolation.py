"""Integration tests for multi-project namespace isolation.

Tests verify that state is properly isolated between projects by running
actual MultiProjectOrchestrator code with mock adapters. Each project maintains
independent orchestration state without cross-project interference.
"""

from unittest.mock import AsyncMock

import pytest

from codetoreum.adapters.testing.mock_project_manager_adapter import (
    MockProjectManagerAdapter,
)
from codetoreum.application.multi_project_orchestrator import MultiProjectOrchestrator
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
def orchestrator(project_manager, workflow_orchestrator, board_service):
    """Create MultiProjectOrchestrator with mock adapters."""
    return MultiProjectOrchestrator(
        project_manager=project_manager,
        workflow_orchestrator=workflow_orchestrator,
        board_service=board_service,
        event_emitter=None,
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
    """Integration tests for project-scoped state isolation.

    These tests invoke the real MultiProjectOrchestrator with mock adapters
    to verify that state isolation is properly maintained at the orchestrator level.
    """

    @pytest.mark.asyncio
    async def test_orchestrator_processes_multiple_projects(
        self, orchestrator, project_manager, workflow_orchestrator
    ):
        """Verify orchestrator processes each project independently.

        Tests the core responsibility: when orchestrator runs a cycle,
        it should invoke per-project orchestration for each enabled project.
        """
        # Setup: Create two enabled projects
        config_proj1 = create_project_config("https://github.com/org/project1.git")
        config_proj2 = create_project_config("https://github.com/org/project2.git")

        project_manager.add_project("project1", config_proj1)
        project_manager.add_project("project2", config_proj2)

        # Mock workflow orchestrator to return specific action counts per project
        workflow_orchestrator.orchestrate_project = AsyncMock(return_value=5)

        # Execute: Run orchestration cycle through real orchestrator
        result = await orchestrator.run_orchestration_cycle()

        # Verify: Both projects were processed
        assert result.success, "Orchestration cycle should succeed"
        assert result.projects_processed == 2, "Should process 2 projects"
        assert result.total_actions == 10, "Should aggregate 5+5=10 actions"

        # Verify: Workflow orchestrator was called for each project
        assert workflow_orchestrator.orchestrate_project.call_count == 2
        calls = workflow_orchestrator.orchestrate_project.call_args_list
        project_names = [call[1]["project_name"] for call in calls]
        assert "project1" in project_names
        assert "project2" in project_names

    @pytest.mark.asyncio
    async def test_project_isolation_prevents_cross_contamination(
        self, orchestrator, project_manager, workflow_orchestrator
    ):
        """Verify project state doesn't cross-contaminate.

        When orchestrator processes two projects with the same board names,
        each project maintains its own workspace and orchestration context.
        """
        # Setup: Two projects with same board names but different repos
        config_proj1 = create_project_config("https://github.com/org/project1.git")
        config_proj2 = create_project_config("https://github.com/org/project2.git")

        project_manager.add_project("project1", config_proj1)
        project_manager.add_project("project2", config_proj2)

        # Configure workflow orchestrator to return different results per project
        async def orchestrate_project_side_effect(**kwargs):
            project_name = kwargs.get("project_name")
            # Different result for each project to verify isolation
            return 10 if project_name == "project1" else 20

        workflow_orchestrator.orchestrate_project = AsyncMock(
            side_effect=orchestrate_project_side_effect
        )

        # Execute: Run orchestration cycle
        result = await orchestrator.run_orchestration_cycle()

        # Verify: Orchestrator correctly called per-project orchestration
        assert result.success
        assert result.projects_processed == 2

        # Verify: Orchestrator passed correct workspace paths
        calls = workflow_orchestrator.orchestrate_project.call_args_list
        workspaces_passed = [call[1]["workspace_path"] for call in calls]
        # Each project should have its own workspace
        assert len(set(workspaces_passed)) == 2, "Each project should have separate workspace"

    @pytest.mark.asyncio
    async def test_project_configuration_independence(
        self, orchestrator, project_manager
    ):
        """Verify project configurations remain independent.

        When updating one project's config, it doesn't affect other projects.
        """
        # Setup: Create two projects with different branches
        config_proj1 = create_project_config(
            "https://github.com/org/project1.git", branch="main"
        )
        config_proj2 = create_project_config(
            "https://github.com/org/project2.git", branch="develop"
        )

        project_manager.add_project("project1", config_proj1)
        project_manager.add_project("project2", config_proj2)

        # Verify: Initial statuses have correct branches
        status_p1_before = await orchestrator.get_project_status("project1")
        status_p2_before = await orchestrator.get_project_status("project2")

        assert status_p1_before.branch == "main"
        assert status_p2_before.branch == "develop"

        # Execute: Update project1 configuration
        new_config_p1 = create_project_config(
            "https://github.com/org/project1.git", branch="release"
        )
        project_manager.update_project("project1", new_config_p1)

        # Verify: Project1 changed, project2 unaffected
        status_p1_after = await orchestrator.get_project_status("project1")
        status_p2_after = await orchestrator.get_project_status("project2")

        assert status_p1_after.branch == "release", "Project1 branch should update"
        assert status_p2_after.branch == "develop", "Project2 branch should remain unchanged"

    @pytest.mark.asyncio
    async def test_disabled_projects_not_orchestrated(
        self, orchestrator, project_manager, workflow_orchestrator
    ):
        """Verify disabled projects are skipped in orchestration cycles.

        When a project is disabled, the orchestrator should not call
        workflow orchestration for it.
        """
        # Setup: One enabled, one disabled project
        config_proj1 = create_project_config("https://github.com/org/project1.git")
        config_proj2_disabled = ProjectConfig(
            repo_url="https://github.com/org/project2.git",
            branch="main",
            enabled=False,
            org="test-org",
        )

        project_manager.add_project("project1", config_proj1)
        project_manager.add_project("project2", config_proj2_disabled)

        # Execute: Run orchestration cycle
        result = await orchestrator.run_orchestration_cycle()

        # Verify: Only enabled project was processed
        assert result.success
        assert result.projects_processed == 1, "Only 1 enabled project should be processed"

        # Verify: Workflow orchestrator only called for enabled project
        assert workflow_orchestrator.orchestrate_project.call_count == 1
        call_args = workflow_orchestrator.orchestrate_project.call_args[1]
        assert call_args["project_name"] == "project1"

    @pytest.mark.asyncio
    async def test_enabled_projects_list_accurate(self, project_manager, orchestrator):
        """Verify enabled_projects list is accurate.

        The orchestrator should correctly identify and process only enabled projects,
        filtering out disabled ones.
        """
        # Setup: Create enabled and disabled projects
        config_enabled = create_project_config("https://github.com/org/enabled.git")
        config_disabled = ProjectConfig(
            repo_url="https://github.com/org/disabled.git",
            branch="main",
            enabled=False,
            org="test-org",
        )

        project_manager.add_project("enabled_proj", config_enabled)
        project_manager.add_project("disabled_proj", config_disabled)

        # Execute: Get enabled projects through orchestrator
        enabled_list = await orchestrator.list_enabled_projects()

        # Verify: Only enabled project in list
        assert len(enabled_list) == 1
        assert "enabled_proj" in enabled_list
        assert "disabled_proj" not in enabled_list
