"""Integration tests for project enable/disable behavior.

Tests verify that disabling a project stops processing through the orchestrator,
and re-enabling a project resumes orchestration.
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
    mock.orchestrate_project = AsyncMock(return_value=5)
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


def create_project_config(repo_url: str, branch: str = "main", enabled: bool = True) -> ProjectConfig:
    """Helper to create a project configuration."""
    return ProjectConfig(
        repo_url=repo_url,
        branch=branch,
        enabled=enabled,
        org="test-org",
    )


class TestProjectEnableDisable:
    """Integration tests for project enable/disable behavior.

    These tests verify that the orchestrator correctly handles disabled projects
    and that disabling/re-enabling doesn't affect orchestration of other projects.
    """

    @pytest.mark.asyncio
    async def test_disabled_project_excluded_from_orchestration(
        self, orchestrator, project_manager, workflow_orchestrator
    ):
        """Verify disabled project is excluded from orchestration cycle.

        When a project is disabled, the orchestrator should not invoke
        workflow orchestration for it.
        """
        # Setup: Create enabled and disabled project
        enabled_config = create_project_config("https://github.com/org/enabled.git", enabled=True)
        disabled_config = create_project_config("https://github.com/org/disabled.git", enabled=False)

        project_manager.add_project("enabled-proj", enabled_config)
        project_manager.add_project("disabled-proj", disabled_config)

        # Execute: Run orchestration cycle
        result = await orchestrator.run_orchestration_cycle()

        # Verify: Only enabled project was orchestrated
        assert result.success
        assert result.projects_processed == 1
        assert workflow_orchestrator.orchestrate_project.call_count == 1

        call_args = workflow_orchestrator.orchestrate_project.call_args[1]
        assert call_args["project_name"] == "enabled-proj"

    @pytest.mark.asyncio
    async def test_disabling_project_stops_orchestration(self, orchestrator, project_manager, workflow_orchestrator):
        """Verify disabling a project stops its orchestration on next cycle.

        When a project transitions from enabled to disabled, subsequent
        orchestration cycles should exclude it.
        """
        # Setup: Create initially enabled project
        config = create_project_config("https://github.com/org/test.git", enabled=True)
        project_manager.add_project("test-proj", config)

        # Execute: First cycle - project enabled
        result1 = await orchestrator.run_orchestration_cycle()
        assert result1.projects_processed == 1
        assert workflow_orchestrator.orchestrate_project.call_count == 1

        # Execute: Disable project
        disabled_config = create_project_config("https://github.com/org/test.git", enabled=False)
        project_manager.update_project("test-proj", disabled_config)

        # Reset mock call count
        workflow_orchestrator.reset_mock()

        # Execute: Second cycle - project now disabled
        result2 = await orchestrator.run_orchestration_cycle()

        # Verify: Project not orchestrated in second cycle
        assert result2.projects_processed == 0
        assert workflow_orchestrator.orchestrate_project.call_count == 0

    @pytest.mark.asyncio
    async def test_re_enabling_project_resumes_orchestration(
        self, orchestrator, project_manager, workflow_orchestrator
    ):
        """Verify re-enabling a project resumes its orchestration.

        When a project is disabled then re-enabled, orchestration should
        resume on the next cycle.
        """
        # Setup: Create project
        config = create_project_config("https://github.com/org/test.git", enabled=True)
        project_manager.add_project("test-proj", config)

        # Execute: Disable project
        disabled_config = create_project_config("https://github.com/org/test.git", enabled=False)
        project_manager.update_project("test-proj", disabled_config)

        # Reset mock
        workflow_orchestrator.reset_mock()

        # Verify: Disabled project not orchestrated
        result_disabled = await orchestrator.run_orchestration_cycle()
        assert result_disabled.projects_processed == 0

        # Execute: Re-enable project
        enabled_config = create_project_config("https://github.com/org/test.git", enabled=True)
        project_manager.update_project("test-proj", enabled_config)

        # Reset mock
        workflow_orchestrator.reset_mock()

        # Execute: Next cycle
        result_enabled = await orchestrator.run_orchestration_cycle()

        # Verify: Project orchestrated again
        assert result_enabled.projects_processed == 1
        assert workflow_orchestrator.orchestrate_project.call_count == 1

    @pytest.mark.asyncio
    async def test_disable_one_project_does_not_affect_others(
        self, orchestrator, project_manager, workflow_orchestrator
    ):
        """Verify disabling one project doesn't affect others.

        When multiple projects exist and one is disabled, other enabled
        projects should continue to be orchestrated normally.
        """
        # Setup: Create three projects, all enabled
        config_a = create_project_config("https://github.com/org/project-a.git")
        config_b = create_project_config("https://github.com/org/project-b.git")
        config_c = create_project_config("https://github.com/org/project-c.git")

        project_manager.add_project("project-a", config_a)
        project_manager.add_project("project-b", config_b)
        project_manager.add_project("project-c", config_c)

        # Execute: First cycle - all enabled
        result1 = await orchestrator.run_orchestration_cycle()
        assert result1.projects_processed == 3

        # Execute: Disable only project-b
        disabled_config_b = create_project_config("https://github.com/org/project-b.git", enabled=False)
        project_manager.update_project("project-b", disabled_config_b)

        # Reset mock
        workflow_orchestrator.reset_mock()

        # Execute: Second cycle with project-b disabled
        result2 = await orchestrator.run_orchestration_cycle()

        # Verify: Only 2 projects orchestrated (a and c)
        assert result2.projects_processed == 2
        assert workflow_orchestrator.orchestrate_project.call_count == 2

        # Verify: Correct projects were orchestrated
        calls = workflow_orchestrator.orchestrate_project.call_args_list
        project_names = [call[1]["project_name"] for call in calls]
        assert "project-a" in project_names
        assert "project-c" in project_names
        assert "project-b" not in project_names

    @pytest.mark.asyncio
    async def test_multiple_disable_enable_cycles(self, orchestrator, project_manager, workflow_orchestrator):
        """Verify multiple disable/enable cycles work correctly.

        Tests that a project can be cycled between enabled and disabled
        multiple times without issues.
        """
        # Setup: Create project
        config = create_project_config("https://github.com/org/test.git", enabled=True)
        project_manager.add_project("test-proj", config)

        # Cycle 1: Enabled
        result = await orchestrator.run_orchestration_cycle()
        assert result.projects_processed == 1

        # Disable
        project_manager.update_project(
            "test-proj",
            create_project_config("https://github.com/org/test.git", enabled=False),
        )
        workflow_orchestrator.reset_mock()

        # Cycle 2: Disabled
        result = await orchestrator.run_orchestration_cycle()
        assert result.projects_processed == 0

        # Re-enable
        project_manager.update_project(
            "test-proj",
            create_project_config("https://github.com/org/test.git", enabled=True),
        )
        workflow_orchestrator.reset_mock()

        # Cycle 3: Enabled again
        result = await orchestrator.run_orchestration_cycle()
        assert result.projects_processed == 1

        # Disable again
        project_manager.update_project(
            "test-proj",
            create_project_config("https://github.com/org/test.git", enabled=False),
        )
        workflow_orchestrator.reset_mock()

        # Cycle 4: Disabled again
        result = await orchestrator.run_orchestration_cycle()
        assert result.projects_processed == 0
