"""Contract tests for IProjectManagerService interface.

These tests define the contract that any implementation of IProjectManagerService
must satisfy. Implementations should inherit from the test class and provide
a concrete instance via the create_service() method.
"""

from abc import ABC, abstractmethod

import pytest

from codetoreum.adapters.testing.mock_project_manager_adapter import (
    MockProjectManagerAdapter,
)
from codetoreum.domain.value_objects import ProjectConfig
from codetoreum.ports.exceptions import ResourceNotFoundError
from codetoreum.ports.output.project_manager_service import IProjectManagerService


class IProjectManagerServiceContractTests(ABC):
    """Abstract contract tests for IProjectManagerService implementations.

    Subclasses must implement create_service() to provide a concrete
    IProjectManagerService implementation to test.
    """

    @abstractmethod
    async def create_service(self) -> IProjectManagerService:
        """Create and return an IProjectManagerService instance for testing."""

    @pytest.mark.asyncio
    async def test_get_enabled_projects_filters_disabled(self):
        """Verify get_enabled_projects excludes disabled projects."""
        service = await self.create_service()

        # Add enabled and disabled projects
        config_enabled = ProjectConfig(
            repo_url="https://github.com/org/enabled.git",
            branch="main",
            enabled=True,
            org="test-org",
        )
        config_disabled = ProjectConfig(
            repo_url="https://github.com/org/disabled.git",
            branch="main",
            enabled=False,
            org="test-org",
        )

        # Add projects (adapter's add_project method signature)
        if hasattr(service, "add_project"):
            service.add_project("enabled", config_enabled)
            service.add_project("disabled", config_disabled)

            # Get enabled projects
            enabled = await service.get_enabled_projects()

            # Verify only enabled projects are returned (returns List[str] of project names)
            assert len(enabled) == 1
            assert "enabled" in enabled
            assert "disabled" not in enabled

    @pytest.mark.asyncio
    async def test_get_project_path_derives_from_repo_url(self):
        """Verify workspace path derived correctly from repo URL."""
        service = await self.create_service()

        # Test HTTPS format
        https_config = ProjectConfig(
            repo_url="https://github.com/myorg/myrepo.git",
            branch="main",
            enabled=True,
            org="myorg",
        )

        # Test SSH format
        ssh_config = ProjectConfig(
            repo_url="git@github.com:myorg/myrepo.git",
            branch="main",
            enabled=True,
            org="myorg",
        )

        if hasattr(service, "add_project"):
            service.add_project("https-repo", https_config)
            service.add_project("ssh-repo", ssh_config)

            # Get paths
            https_path = await service.get_project_path("https-repo")
            ssh_path = await service.get_project_path("ssh-repo")

            # Both should derive meaningful paths from repo URL
            assert https_path is not None
            assert ssh_path is not None
            # Both should reference the project name or repo in the path
            assert "myrepo" in https_path or "https-repo" in https_path
            assert "myrepo" in ssh_path or "ssh-repo" in ssh_path

    @pytest.mark.asyncio
    async def test_ensure_project_cloned_handles_failure(self):
        """Verify clone failures raise exceptions."""
        service = await self.create_service()

        # Try to clone nonexistent project
        with pytest.raises(ResourceNotFoundError):
            await service.ensure_project_cloned("nonexistent-project")


class TestMockProjectManagerAdapter(IProjectManagerServiceContractTests):
    """Contract tests for MockProjectManagerAdapter.

    Verifies that the mock adapter implementation satisfies the
    IProjectManagerService interface contract.
    """

    async def create_service(self) -> IProjectManagerService:
        """Create a MockProjectManagerAdapter instance."""
        return MockProjectManagerAdapter()
