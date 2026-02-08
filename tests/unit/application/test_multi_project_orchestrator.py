"""Tests for MultiProjectOrchestrator application service.

Comprehensive unit tests covering:
- Multi-project orchestration cycles
- Per-project orchestration
- Error handling and resilience
- Event emission
- Project status tracking
- Enable/disable operations
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from codetoreum.application.multi_project_orchestrator import MultiProjectOrchestrator
from codetoreum.domain.value_objects import ProjectConfig
from codetoreum.domain.events.project_events import OrchestrationCycleCompletedEvent
from codetoreum.ports.exceptions import ResourceNotFoundError, ExternalServiceError
from codetoreum.ports.output.multi_project_orchestrator import (
    OrchestrationCycleResult,
    ProjectOrchestrationResult,
)


@pytest.fixture
def project_manager():
    """Create mock project manager."""
    return AsyncMock()


@pytest.fixture
def workflow_orchestrator():
    """Create mock workflow orchestrator."""
    return AsyncMock()


@pytest.fixture
def board_service():
    """Create mock board service."""
    return AsyncMock()


@pytest.fixture
def event_emitter():
    """Create mock event emitter."""
    return MagicMock()


@pytest.fixture
def multi_orchestrator(project_manager, workflow_orchestrator, board_service, event_emitter):
    """Create MultiProjectOrchestrator with mocks."""
    return MultiProjectOrchestrator(
        project_manager=project_manager,
        workflow_orchestrator=workflow_orchestrator,
        board_service=board_service,
        event_emitter=event_emitter,
    )


class TestOrchestrationCycle:
    """Tests for orchestration cycle execution."""

    @pytest.mark.asyncio
    async def test_run_orchestration_cycle_success(
        self, multi_orchestrator, project_manager, workflow_orchestrator, board_service, event_emitter
    ):
        """Test successful orchestration cycle with multiple projects."""
        # Setup
        project_manager.reload_config = AsyncMock()
        project_manager.get_enabled_projects = AsyncMock(
            return_value=["api-service", "web-app"]
        )
        project_manager.get_project_config = AsyncMock(
            side_effect=lambda p: ProjectConfig(
                repo_url=f"https://github.com/acme/{p}.git",
                branch="main",
                enabled=True,
                org="acme",
            )
        )
        project_manager.ensure_project_cloned = AsyncMock(
            return_value="/workspace/project"
        )
        board_service.reconcile_board = AsyncMock()
        workflow_orchestrator.orchestrate_project = AsyncMock(
            side_effect=[5, 3]  # 5 actions for api-service, 3 for web-app
        )

        # Execute
        result = await multi_orchestrator.run_orchestration_cycle()

        # Assert
        assert result.success
        assert result.projects_processed == 2
        assert result.total_actions == 8
        assert result.total_errors == 0
        assert result.cycle_duration_ms > 0
        assert result.error_message is None

        # Verify calls
        project_manager.reload_config.assert_called_once()
        assert project_manager.get_enabled_projects.call_count == 1
        assert project_manager.get_project_config.call_count == 2
        assert project_manager.ensure_project_cloned.call_count == 2
        assert workflow_orchestrator.orchestrate_project.call_count == 2

        # Verify event emissions (ProjectCloned x2 + OrchestrationCycleCompleted)
        assert event_emitter.emit.call_count == 3
        # Last emit call should be the cycle completed event
        cycle_event = event_emitter.emit.call_args_list[-1][0][0]
        assert isinstance(cycle_event, OrchestrationCycleCompletedEvent)
        assert cycle_event.projects_processed == 2
        assert cycle_event.work_items_found == 8

    @pytest.mark.asyncio
    async def test_run_orchestration_cycle_no_enabled_projects(
        self, multi_orchestrator, project_manager, event_emitter
    ):
        """Test orchestration cycle with no enabled projects."""
        # Setup
        project_manager.reload_config = AsyncMock()
        project_manager.get_enabled_projects = AsyncMock(return_value=[])

        # Execute
        result = await multi_orchestrator.run_orchestration_cycle()

        # Assert
        assert result.success
        assert result.projects_processed == 0
        assert result.total_actions == 0
        assert result.total_errors == 0

        # Verify reload was called even with no projects
        project_manager.reload_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_orchestration_cycle_project_error_doesnt_block_others(
        self,
        multi_orchestrator,
        project_manager,
        workflow_orchestrator,
        board_service,
        event_emitter,
    ):
        """Test that error in one project doesn't block others."""
        # Setup
        project_manager.reload_config = AsyncMock()
        project_manager.get_enabled_projects = AsyncMock(
            return_value=["api-service", "web-app"]
        )
        project_manager.get_project_config = AsyncMock(
            side_effect=lambda p: ProjectConfig(
                repo_url=f"https://github.com/acme/{p}.git",
                branch="main",
                enabled=True,
                org="acme",
            )
        )
        project_manager.ensure_project_cloned = AsyncMock(
            side_effect=[
                ExternalServiceError("git", "Clone failed"),
                "/workspace/web-app",
            ]
        )
        board_service.reconcile_board = AsyncMock()
        workflow_orchestrator.orchestrate_project = AsyncMock(return_value=5)

        # Execute
        result = await multi_orchestrator.run_orchestration_cycle()

        # Assert - second project should still be processed
        assert result.success is False  # Had errors
        assert result.projects_processed == 2
        assert result.total_actions == 5  # Only from web-app
        assert result.total_errors == 1

        # Verify both projects were attempted
        assert project_manager.get_project_config.call_count == 2
        assert project_manager.ensure_project_cloned.call_count == 2

    @pytest.mark.asyncio
    async def test_run_orchestration_cycle_get_enabled_projects_fails(
        self, multi_orchestrator, project_manager, board_service, event_emitter
    ):
        """Test orchestration cycle when getting enabled projects fails."""
        # Setup
        project_manager.reload_config = AsyncMock()
        project_manager.get_enabled_projects = AsyncMock(
            side_effect=ExternalServiceError("config_service", "Service unavailable")
        )

        # Execute
        result = await multi_orchestrator.run_orchestration_cycle()

        # Assert
        assert result.success is False
        assert result.projects_processed == 0
        assert result.total_errors == 1
        assert "Failed to get enabled projects" in result.error_message

    @pytest.mark.asyncio
    async def test_run_orchestration_cycle_reload_config_fails(
        self, multi_orchestrator, project_manager, workflow_orchestrator, board_service
    ):
        """Test that reload_config failure doesn't block the cycle."""
        # Setup
        project_manager.reload_config = AsyncMock(
            side_effect=ExternalServiceError("config_service", "Read failed")
        )
        project_manager.get_enabled_projects = AsyncMock(
            return_value=["api-service"]
        )
        project_manager.get_project_config = AsyncMock(
            return_value=ProjectConfig(
                repo_url="https://github.com/acme/api-service.git",
                branch="main",
                enabled=True,
                org="acme",
            )
        )
        project_manager.ensure_project_cloned = AsyncMock(
            return_value="/workspace/api-service"
        )
        board_service.reconcile_board = AsyncMock()
        workflow_orchestrator.orchestrate_project = AsyncMock(return_value=3)

        # Execute
        result = await multi_orchestrator.run_orchestration_cycle()

        # Assert - cycle completes despite reload failure
        assert result.success is True
        assert result.projects_processed == 1
        assert result.total_actions == 3


class TestPerProjectOrchestration:
    """Tests for per-project orchestration."""

    @pytest.mark.asyncio
    async def test_orchestrate_project_success(
        self, multi_orchestrator, project_manager, workflow_orchestrator, event_emitter
    ):
        """Test successful orchestration of a single project."""
        # Setup
        config = ProjectConfig(
            repo_url="https://github.com/acme/api-service.git",
            branch="main",
            enabled=True,
            org="acme",
        )
        project_manager.get_project_config = AsyncMock(return_value=config)
        project_manager.ensure_project_cloned = AsyncMock(
            return_value="/workspace/api-service"
        )
        workflow_orchestrator.orchestrate_project = AsyncMock(return_value=5)

        # Execute
        result = await multi_orchestrator.orchestrate_project("api-service")

        # Assert
        assert result.success
        assert result.project_name == "api-service"
        assert result.actions_taken == 5
        assert result.errors == []
        assert result.workspace_path == "/workspace/api-service"

        # Verify calls
        project_manager.get_project_config.assert_called_with("api-service")
        project_manager.ensure_project_cloned.assert_called_with("api-service")
        workflow_orchestrator.orchestrate_project.assert_called_with(
            project_name="api-service",
            workspace_path="/workspace/api-service",
            config=config,
        )

    @pytest.mark.asyncio
    async def test_orchestrate_project_not_found(
        self, multi_orchestrator, project_manager
    ):
        """Test orchestration when project is not found."""
        # Setup
        project_manager.get_project_config = AsyncMock(
            side_effect=ResourceNotFoundError("Project", "nonexistent")
        )

        # Execute
        result = await multi_orchestrator.orchestrate_project("nonexistent")

        # Assert
        assert result.success is False
        assert result.project_name == "nonexistent"
        assert result.actions_taken == 0
        assert len(result.errors) == 1
        assert "Project not found" in result.errors[0]

    @pytest.mark.asyncio
    async def test_orchestrate_project_clone_fails(
        self, multi_orchestrator, project_manager, event_emitter
    ):
        """Test orchestration when project clone fails."""
        # Setup
        config = ProjectConfig(
            repo_url="https://github.com/acme/api-service.git",
            branch="main",
            enabled=True,
            org="acme",
        )
        project_manager.get_project_config = AsyncMock(return_value=config)
        project_manager.ensure_project_cloned = AsyncMock(
            side_effect=ExternalServiceError("git", "Network timeout")
        )
        event_emitter.emit = MagicMock()

        # Execute
        result = await multi_orchestrator.orchestrate_project("api-service")

        # Assert
        assert result.success is False
        assert result.actions_taken == 0
        assert len(result.errors) == 1
        assert "Clone failed" in result.errors[0]

        # Verify ProjectCloneFailedEvent emitted
        event_emitter.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_orchestrate_project_workflow_orchestrator_error(
        self, multi_orchestrator, project_manager, workflow_orchestrator, event_emitter
    ):
        """Test orchestration when workflow orchestrator raises unexpected error."""
        # Setup
        config = ProjectConfig(
            repo_url="https://github.com/acme/api-service.git",
            branch="main",
            enabled=True,
            org="acme",
        )
        project_manager.get_project_config = AsyncMock(return_value=config)
        project_manager.ensure_project_cloned = AsyncMock(
            return_value="/workspace/api-service"
        )
        event_emitter.emit = MagicMock()
        workflow_orchestrator.orchestrate_project = AsyncMock(
            side_effect=RuntimeError("Unexpected error")
        )

        # Execute
        result = await multi_orchestrator.orchestrate_project("api-service")

        # Assert
        assert result.success is False
        assert result.actions_taken == 0
        assert len(result.errors) == 1
        assert "Unexpected error" in result.errors[0]


class TestProjectStatus:
    """Tests for project status retrieval."""

    @pytest.mark.asyncio
    async def test_get_project_status_success(
        self, multi_orchestrator, project_manager
    ):
        """Test retrieving project status."""
        # Setup
        config = ProjectConfig(
            repo_url="https://github.com/acme/api-service.git",
            branch="develop",
            enabled=True,
            org="acme",
        )
        project_manager.get_project_config = AsyncMock(return_value=config)
        project_manager.get_project_path = AsyncMock(
            return_value="/workspace/api-service"
        )

        # Execute
        status = await multi_orchestrator.get_project_status("api-service")

        # Assert
        assert status["project_name"] == "api-service"
        assert status["enabled"] is True
        assert status["repo_url"] == "https://github.com/acme/api-service.git"
        assert status["branch"] == "develop"
        assert status["organization"] == "acme"
        assert status["workspace_path"] == "/workspace/api-service"

    @pytest.mark.asyncio
    async def test_get_project_status_not_found(self, multi_orchestrator, project_manager):
        """Test getting status for non-existent project."""
        # Setup
        project_manager.get_project_config = AsyncMock(
            side_effect=ResourceNotFoundError("Project", "nonexistent")
        )

        # Execute & Assert
        with pytest.raises(ResourceNotFoundError):
            await multi_orchestrator.get_project_status("nonexistent")


class TestProjectStatus:
    """Tests for project status and listing."""

    @pytest.mark.asyncio
    async def test_list_enabled_projects(self, multi_orchestrator, project_manager):
        """Test listing enabled projects."""
        # Setup
        project_manager.get_enabled_projects = AsyncMock(
            return_value=["api-service", "web-app"]
        )

        # Execute
        projects = await multi_orchestrator.list_enabled_projects()

        # Assert
        assert projects == ["api-service", "web-app"]
        project_manager.get_enabled_projects.assert_called_once()


class TestCycleMetrics:
    """Tests for cycle metrics and tracking."""

    @pytest.mark.asyncio
    async def test_cycle_count_increments(
        self, multi_orchestrator, project_manager, workflow_orchestrator, board_service
    ):
        """Test that cycle counter increments with each run."""
        # Setup
        project_manager.reload_config = AsyncMock()
        project_manager.get_enabled_projects = AsyncMock(return_value=[])
        board_service.reconcile_board = AsyncMock()

        # Execute - run cycle twice
        await multi_orchestrator.run_orchestration_cycle()
        await multi_orchestrator.run_orchestration_cycle()

        # Assert - internal state should show 2 cycles
        # (Can't directly access _cycle_count, but we can verify behavior)
        assert project_manager.reload_config.call_count == 2

    @pytest.mark.asyncio
    async def test_cycle_duration_measured(
        self, multi_orchestrator, project_manager, workflow_orchestrator, board_service
    ):
        """Test that cycle duration is accurately measured."""
        # Setup
        project_manager.reload_config = AsyncMock()
        project_manager.get_enabled_projects = AsyncMock(return_value=[])
        board_service.reconcile_board = AsyncMock()

        # Execute
        result = await multi_orchestrator.run_orchestration_cycle()

        # Assert
        assert result.cycle_duration_ms >= 0
        assert isinstance(result.cycle_duration_ms, float)

    @pytest.mark.asyncio
    async def test_event_emitted_with_correct_metrics(
        self, multi_orchestrator, project_manager, workflow_orchestrator, board_service, event_emitter
    ):
        """Test that emitted event contains correct metrics."""
        # Setup
        project_manager.reload_config = AsyncMock()
        project_manager.get_enabled_projects = AsyncMock(
            return_value=["api-service", "web-app"]
        )
        project_manager.get_project_config = AsyncMock(
            side_effect=lambda p: ProjectConfig(
                repo_url=f"https://github.com/acme/{p}.git",
                branch="main",
                enabled=True,
                org="acme",
            )
        )
        project_manager.ensure_project_cloned = AsyncMock(
            return_value="/workspace/project"
        )
        board_service.reconcile_board = AsyncMock()
        workflow_orchestrator.orchestrate_project = AsyncMock(
            side_effect=[7, 3]  # Total 10 actions
        )

        # Execute
        result = await multi_orchestrator.run_orchestration_cycle()

        # Assert
        assert event_emitter.emit.called
        event = event_emitter.emit.call_args[0][0]
        assert event.projects_processed == 2
        assert event.work_items_found == 10
        assert event.type == "orchestration.cycle_completed"
        assert event.source == "multi_project_orchestrator"


class TestErrorHandling:
    """Tests for error handling and resilience."""

    @pytest.mark.asyncio
    async def test_unexpected_error_caught_and_reported(
        self, multi_orchestrator, project_manager
    ):
        """Test that unexpected errors don't crash the orchestrator."""
        # Setup
        project_manager.reload_config = AsyncMock(side_effect=RuntimeError("Boom!"))

        # Execute
        result = await multi_orchestrator.run_orchestration_cycle()

        # Assert
        assert result.success is False
        assert result.total_errors >= 1
        assert "Boom!" in result.error_message

    @pytest.mark.asyncio
    async def test_no_event_emission_without_emitter(
        self, project_manager, workflow_orchestrator, board_service
    ):
        """Test orchestration works without event emitter."""
        # Setup
        orchestrator = MultiProjectOrchestrator(
            project_manager=project_manager,
            workflow_orchestrator=workflow_orchestrator,
            board_service=board_service,
            event_emitter=None,  # No emitter
        )
        project_manager.reload_config = AsyncMock()
        project_manager.get_enabled_projects = AsyncMock(return_value=[])

        # Execute
        result = await orchestrator.run_orchestration_cycle()

        # Assert
        assert result.success
