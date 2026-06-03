"""Integration tests for ProjectLifecycleService.

Tests verify:
- Project initialization for all enabled projects
- Board reconciliation success and error handling
- Graceful handling of configuration load failures
- Logging of errors without silent swallowing
- Continuation on per-project failures
"""

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codetoreum.application.project_lifecycle_service import ProjectLifecycleService
from codetoreum.domain.value_objects import ProjectConfig
from codetoreum.ports.exceptions import ExternalServiceError, ResourceNotFoundError
from codetoreum.ports.output.board_service import BoardConfig, IBoardService
from codetoreum.ports.output.project_manager_service import IProjectManagerService


class MockProjectManagerService(IProjectManagerService):
    """Mock project manager for testing."""

    def __init__(
        self,
        enabled_projects: list[str] | None = None,
        configs: dict[str, ProjectConfig] | None = None,
        get_config_error: Exception | None = None,
        get_enabled_error: Exception | None = None,
    ):
        self.enabled_projects = enabled_projects or []
        self.configs = configs or {}
        self.get_config_error = get_config_error
        self.get_enabled_error = get_enabled_error

    async def get_enabled_projects(self) -> list[str]:
        if self.get_enabled_error:
            raise self.get_enabled_error
        return self.enabled_projects

    async def get_project_config(self, project_name: str) -> ProjectConfig:
        if self.get_config_error:
            raise self.get_config_error
        if project_name not in self.configs:
            raise ResourceNotFoundError("project", project_name)
        return self.configs[project_name]

    async def get_project_path(self, project_name: str) -> str:
        return f"/workspace/{project_name}"

    async def ensure_project_cloned(self, project_name: str) -> str:
        return f"/workspace/{project_name}"

    async def reload_config(self) -> None:
        pass


class MockBoardService(IBoardService):
    """Mock board service for testing."""

    def __init__(self, reconcile_error: Exception | None = None):
        self.reconcile_error = reconcile_error
        self.reconcile_calls: list[tuple[str, BoardConfig]] = []
        self._handlers: dict[str, list[Any]] = {}

    async def reconcile_board(self, board_id: str, config: BoardConfig) -> None:
        self.reconcile_calls.append((board_id, config))
        if self.reconcile_error:
            raise self.reconcile_error

    async def get_board(self, project_id: str, board_id: str) -> Any:
        pass

    async def get_columns(self, board_id: str) -> list[Any]:
        return []

    async def get_items_in_column(self, board_id: str, column_name: str) -> list[Any]:
        return []

    async def get_item_position(self, work_item_id: str) -> Any:
        pass

    async def move_item_to_column(self, work_item_id: str, target_column: str, moved_by: Any) -> Any:
        pass

    async def add_item_to_column(self, work_item_id: str, target_column: str, moved_by: Any) -> Any:
        pass

    async def get_board_items(self, project_id: str, board_id: str) -> list[Any]:
        return []

    async def get_all_boards(self) -> list[Any]:
        return []

    async def start_monitoring(self, project_id: str, config: Any) -> None:
        pass

    async def stop_monitoring(self, project_id: str) -> None:
        pass

    def get_monitoring_status(self, project_id: str) -> dict[str, Any]:
        return {}

    def on(self, event_type: str, handler: Any) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def off(self, event_type: str, handler: Any) -> None:
        if event_type in self._handlers:
            self._handlers[event_type] = [h for h in self._handlers[event_type] if h != handler]

    def emit(self, event: Any) -> None:
        pass

    def once(self, event_type: str, handler: Any) -> None:
        pass


@pytest.mark.asyncio
async def test_initialize_all_projects_with_no_projects():
    """Test initialization with no enabled projects."""
    project_manager = MockProjectManagerService(enabled_projects=[])
    service = ProjectLifecycleService(project_manager)

    await service.initialize_all_projects()
    # Should complete without error


@pytest.mark.asyncio
async def test_initialize_all_projects_with_single_project(caplog):
    """Test initialization with a single project."""
    config = ProjectConfig(
        repo_url="https://github.com/acme/api-service.git",
        branch="main",
        enabled=True,
        org="acme",
        github_project_id="PVT_kwDOANYYRs4AbZKf",
    )
    project_manager = MockProjectManagerService(
        enabled_projects=["api-service"],
        configs={"api-service": config},
    )
    board_service = MockBoardService()
    service = ProjectLifecycleService(project_manager, board_service)

    with caplog.at_level(logging.INFO):
        await service.initialize_all_projects()

    assert "Initializing 1 projects" in caplog.text
    assert len(board_service.reconcile_calls) == 1
    assert board_service.reconcile_calls[0][0] == "PVT_kwDOANYYRs4AbZKf"


@pytest.mark.asyncio
async def test_initialize_all_projects_with_multiple_projects(caplog):
    """Test initialization with multiple projects."""
    config1 = ProjectConfig(
        repo_url="https://github.com/acme/api-service.git",
        branch="main",
        enabled=True,
        org="acme",
        github_project_id="PVT_kwDOANYYRs4AbZKf",
    )
    config2 = ProjectConfig(
        repo_url="https://github.com/acme/web-app.git",
        branch="main",
        enabled=True,
        org="acme",
        github_project_id="PVT_kwDOANYYRs4AbZKg",
    )
    project_manager = MockProjectManagerService(
        enabled_projects=["api-service", "web-app"],
        configs={"api-service": config1, "web-app": config2},
    )
    board_service = MockBoardService()
    service = ProjectLifecycleService(project_manager, board_service)

    with caplog.at_level(logging.INFO):
        await service.initialize_all_projects()

    assert "Initializing 2 projects" in caplog.text
    assert len(board_service.reconcile_calls) == 2


@pytest.mark.asyncio
async def test_initialize_all_projects_without_board_service(caplog):
    """Test initialization when board service is not provided."""
    config = ProjectConfig(
        repo_url="https://github.com/acme/api-service.git",
        branch="main",
        enabled=True,
        org="acme",
        github_project_id="PVT_kwDOANYYRs4AbZKf",
    )
    project_manager = MockProjectManagerService(
        enabled_projects=["api-service"],
        configs={"api-service": config},
    )
    service = ProjectLifecycleService(project_manager, board_service=None)

    with caplog.at_level(logging.DEBUG):
        await service.initialize_all_projects()

    assert "Skipping board reconciliation for api-service" in caplog.text


@pytest.mark.asyncio
async def test_reconcile_project_boards_success(caplog):
    """Test successful board reconciliation."""
    config = ProjectConfig(
        repo_url="https://github.com/acme/api-service.git",
        branch="main",
        enabled=True,
        org="acme",
        github_project_id="PVT_kwDOANYYRs4AbZKf",
    )
    project_manager = MockProjectManagerService(configs={"api-service": config})
    board_service = MockBoardService()
    service = ProjectLifecycleService(project_manager, board_service)

    with caplog.at_level(logging.DEBUG):
        await service._reconcile_project_boards("api-service")

    assert "Reconciling boards for project api-service" in caplog.text
    assert len(board_service.reconcile_calls) == 1
    board_id, board_config = board_service.reconcile_calls[0]
    assert board_id == "PVT_kwDOANYYRs4AbZKf"
    assert board_config.board_id == "PVT_kwDOANYYRs4AbZKf"


@pytest.mark.asyncio
async def test_reconcile_project_boards_config_not_found(caplog):
    """Test board reconciliation when project config not found."""
    project_manager = MockProjectManagerService(configs={})
    board_service = MockBoardService()
    service = ProjectLifecycleService(project_manager, board_service)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(ResourceNotFoundError):
            await service._reconcile_project_boards("missing-project")

    assert "project configuration not found" in caplog.text
    assert len(board_service.reconcile_calls) == 0


@pytest.mark.asyncio
async def test_reconcile_project_boards_no_github_project_id(caplog):
    """Test board reconciliation skipped when github_project_id is missing."""
    config = ProjectConfig(
        repo_url="https://github.com/acme/api-service.git",
        branch="main",
        enabled=True,
        org="acme",
        github_project_id=None,
    )
    project_manager = MockProjectManagerService(configs={"api-service": config})
    board_service = MockBoardService()
    service = ProjectLifecycleService(project_manager, board_service)

    with caplog.at_level(logging.DEBUG):
        await service._reconcile_project_boards("api-service")

    assert "no github_project_id in project configuration" in caplog.text
    assert len(board_service.reconcile_calls) == 0


@pytest.mark.asyncio
async def test_reconcile_project_boards_service_error(caplog):
    """Test board reconciliation when project manager service fails."""
    service_error = ExternalServiceError(service="config_store", message="Database connection failed")
    project_manager = MockProjectManagerService(get_config_error=service_error)
    board_service = MockBoardService()
    service = ProjectLifecycleService(project_manager, board_service)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(ExternalServiceError):
            await service._reconcile_project_boards("api-service")

    assert "failed to load project configuration" in caplog.text
    assert "Database connection failed" in caplog.text
    assert len(board_service.reconcile_calls) == 0


@pytest.mark.asyncio
async def test_initialize_all_projects_continues_on_per_project_error(caplog):
    """Test that initialization continues after a per-project error."""
    config1 = ProjectConfig(
        repo_url="https://github.com/acme/api-service.git",
        branch="main",
        enabled=True,
        org="acme",
        github_project_id="PVT_kwDOANYYRs4AbZKf",
    )
    config2 = ProjectConfig(
        repo_url="https://github.com/acme/web-app.git",
        branch="main",
        enabled=True,
        org="acme",
        github_project_id="PVT_kwDOANYYRs4AbZKg",
    )

    def get_config_side_effect(project_name: str) -> ProjectConfig:
        if project_name == "api-service":
            raise ExternalServiceError(service="config_store", message="Temporary error")
        return config2

    project_manager = AsyncMock(spec=IProjectManagerService)
    project_manager.get_enabled_projects.return_value = ["api-service", "web-app"]
    project_manager.get_project_config.side_effect = get_config_side_effect

    board_service = MockBoardService()
    service = ProjectLifecycleService(project_manager, board_service)

    with caplog.at_level(logging.DEBUG):
        await service.initialize_all_projects()

    # Should log warning for api-service failure
    assert "Board reconciliation failed for api-service" in caplog.text
    # Should still reconcile web-app
    assert len(board_service.reconcile_calls) == 1
    assert board_service.reconcile_calls[0][0] == "PVT_kwDOANYYRs4AbZKg"


@pytest.mark.asyncio
async def test_initialize_all_projects_error_logged_no_silent_exceptions(caplog):
    """Test that all exceptions are logged (not silently swallowed)."""
    error = ExternalServiceError(service="config_store", message="Database connection failed")
    project_manager = MockProjectManagerService(
        enabled_projects=["api-service"],
        get_config_error=error,
    )
    board_service = MockBoardService()
    service = ProjectLifecycleService(project_manager, board_service)

    with caplog.at_level(logging.WARNING):
        await service.initialize_all_projects()

    # Should log the error, not silently swallow it
    assert "Board reconciliation failed for api-service" in caplog.text
    assert "Database connection failed" in caplog.text
    assert len(board_service.reconcile_calls) == 0


@pytest.mark.asyncio
async def test_reconcile_board_service_error_during_reconciliation(caplog):
    """Test that board service errors propagate and are logged by caller."""
    config = ProjectConfig(
        repo_url="https://github.com/acme/api-service.git",
        branch="main",
        enabled=True,
        org="acme",
        github_project_id="PVT_kwDOANYYRs4AbZKf",
    )
    project_manager = MockProjectManagerService(configs={"api-service": config})
    board_error = ExternalServiceError(service="board_service", message="Failed to reconcile board")
    board_service = MockBoardService(reconcile_error=board_error)
    service = ProjectLifecycleService(project_manager, board_service)

    # Direct call to _reconcile_project_boards should propagate the error
    with pytest.raises(ExternalServiceError):
        await service._reconcile_project_boards("api-service")

    # Error logging happens in initialize_all_projects (the caller)
    # Test that through initialize_all_projects
    project_manager2 = MockProjectManagerService(
        enabled_projects=["api-service"],
        configs={"api-service": config},
    )
    service2 = ProjectLifecycleService(project_manager2, board_service)

    with caplog.at_level(logging.WARNING):
        await service2.initialize_all_projects()

    assert "Board reconciliation failed for api-service" in caplog.text


@pytest.mark.asyncio
async def test_initialize_all_projects_with_no_config_error(caplog):
    """Test that initialization continues when get_enabled_projects fails."""
    error = ExternalServiceError(service="config_store", message="Config service unavailable")
    project_manager = MockProjectManagerService(get_enabled_error=error)
    service = ProjectLifecycleService(project_manager)

    with caplog.at_level(logging.WARNING):
        await service.initialize_all_projects()

    # Should log the error and continue
    assert "Project initialization failed" in caplog.text


@pytest.mark.asyncio
async def test_initialize_all_projects_catches_unexpected_exceptions_per_project(caplog):
    """Test that unexpected exceptions (TypeError, KeyError, etc.) are caught and logged.

    Verifies the fix for issue #931: initialize_all_projects() should continue
    processing remaining projects even when encountering unexpected exceptions,
    not just ExternalServiceError and ResourceNotFoundError.
    """
    config1 = ProjectConfig(
        repo_url="https://github.com/acme/api-service.git",
        branch="main",
        enabled=True,
        org="acme",
        github_project_id="PVT_kwDOANYYRs4AbZKf",
    )
    config2 = ProjectConfig(
        repo_url="https://github.com/acme/web-app.git",
        branch="main",
        enabled=True,
        org="acme",
        github_project_id="PVT_kwDOANYYRs4AbZKg",
    )

    # Mock board service that raises TypeError for first project, succeeds for second
    board_service = MagicMock(spec=IBoardService)
    board_service.reconcile_board = AsyncMock(side_effect=[TypeError("Unexpected type error"), None])

    project_manager = MockProjectManagerService(
        enabled_projects=["api-service", "web-app"],
        configs={"api-service": config1, "web-app": config2},
    )
    service = ProjectLifecycleService(project_manager, board_service)

    with caplog.at_level(logging.WARNING):
        # Should not raise - catches all exceptions
        await service.initialize_all_projects()

    # Verify that the error was logged
    assert "Board reconciliation failed for api-service" in caplog.text
    assert "Unexpected type error" in caplog.text

    # Verify that processing continued to the second project
    assert board_service.reconcile_board.call_count == 2


@pytest.mark.asyncio
async def test_initialize_all_projects_catches_unexpected_exceptions_during_get_enabled(caplog):
    """Test that unexpected exceptions during get_enabled_projects are caught.

    Verifies that exceptions other than ExternalServiceError/ResourceNotFoundError
    are properly handled at the outer level as well.
    """
    # Simulate an unexpected exception during get_enabled_projects
    project_manager = MockProjectManagerService(get_enabled_error=RuntimeError("Unexpected runtime error"))
    service = ProjectLifecycleService(project_manager)

    with caplog.at_level(logging.WARNING):
        # Should not raise - catches all exceptions
        await service.initialize_all_projects()

    # Verify that the error was logged
    assert "Project initialization failed" in caplog.text
    assert "Unexpected runtime error" in caplog.text
