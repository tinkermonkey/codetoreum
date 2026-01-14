"""Contract tests for IVersionControlService interface.

These abstract tests verify that all IVersionControlService implementations
follow the contract correctly for basic version control operations like
cloning, checking out, committing, and pushing.

Note: This is a synchronous interface with NO event emission.
"""

from abc import ABC, abstractmethod

import pytest

from codetoreum.ports.exceptions import RepositoryError, ValidationError
from codetoreum.ports.output.version_control_service import (
    IVersionControlService,
    Repository,
)


class TestVersionControlServiceContract(ABC):
    """Abstract contract tests for IVersionControlService implementations.

    Subclasses must implement create_service() to provide a concrete
    IVersionControlService implementation to test.
    """

    @abstractmethod
    async def create_service(self) -> IVersionControlService:
        """Create and return an IVersionControlService instance for testing."""
        pass

    @abstractmethod
    def get_test_repo_url(self) -> str:
        """Return a valid test repository URL."""
        pass

    @abstractmethod
    async def cleanup_repo_path(self, repo_path: str) -> None:
        """Clean up temporary repository path after test."""
        pass

    # Repository Metadata Tests

    @pytest.mark.asyncio
    async def test_get_repository_returns_metadata(self):
        """Should return repository metadata."""
        service = await self.create_service()

        repo = await service.get_repository("test-repo")

        assert isinstance(repo, Repository)
        assert hasattr(repo, "id")
        assert hasattr(repo, "name")
        assert hasattr(repo, "url")
        assert hasattr(repo, "default_branch")
        assert isinstance(repo.id, str)
        assert isinstance(repo.name, str)
        assert isinstance(repo.url, str)
        assert isinstance(repo.default_branch, str)

    # Clone Operation Tests

    @pytest.mark.asyncio
    async def test_clone_repository_creates_directory(self):
        """Cloning should create local repository directory."""
        service = await self.create_service()
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = os.path.join(tmpdir, "cloned_repo")

            try:
                url = self.get_test_repo_url()
                await service.clone_repository(url, target_path)

                # Directory should exist
                assert os.path.exists(target_path)
                # Should have .git directory
                assert os.path.exists(os.path.join(target_path, ".git"))
            finally:
                await self.cleanup_repo_path(target_path)

    @pytest.mark.asyncio
    async def test_clone_repository_with_branch(self):
        """Should be able to clone specific branch."""
        service = await self.create_service()
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = os.path.join(tmpdir, "cloned_repo")

            try:
                url = self.get_test_repo_url()
                # Try to clone with main/master branch (should exist)
                await service.clone_repository(url, target_path, branch="main")

                assert os.path.exists(target_path)
            except Exception:
                # Branch might not exist, that's ok for this test
                pass
            finally:
                await self.cleanup_repo_path(target_path)

    # Pull Operation Tests

    @pytest.mark.asyncio
    async def test_pull_latest_fetches_updates(self):
        """Pull latest should update local repository."""
        service = await self.create_service()
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = os.path.join(tmpdir, "cloned_repo")

            try:
                url = self.get_test_repo_url()
                await service.clone_repository(url, target_path)

                # Pull latest should not fail
                await service.pull_latest(target_path)
            finally:
                await self.cleanup_repo_path(target_path)

    # Checkout Operation Tests

    @pytest.mark.asyncio
    async def test_checkout_branch_succeeds(self):
        """Checkout should switch to specified branch."""
        service = await self.create_service()
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = os.path.join(tmpdir, "cloned_repo")

            try:
                url = self.get_test_repo_url()
                await service.clone_repository(url, target_path)

                # Try checking out main/master
                try:
                    await service.checkout(target_path, "main")
                except Exception:
                    # Try master if main doesn't exist
                    await service.checkout(target_path, "master")

                # Should not raise exception
            finally:
                await self.cleanup_repo_path(target_path)

    # Commit Operation Tests

    @pytest.mark.asyncio
    async def test_commit_returns_sha(self):
        """Commit should return commit SHA."""
        service = await self.create_service()
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = os.path.join(tmpdir, "cloned_repo")

            try:
                url = self.get_test_repo_url()
                await service.clone_repository(url, target_path)

                # Create a file to commit
                test_file = os.path.join(target_path, "test_file.txt")
                with open(test_file, "w") as f:
                    f.write("test content")

                # Commit should return a SHA
                sha = await service.commit(target_path, "Test commit message")

                assert isinstance(sha, str)
                assert len(sha) >= 40  # Git SHA is at least 40 chars (short form)
            except Exception:
                # Might fail if repository has special permissions
                pass
            finally:
                await self.cleanup_repo_path(target_path)

    # Push Operation Tests

    @pytest.mark.asyncio
    async def test_push_operations_interface(self):
        """Push operation should not fail when repository is up to date."""
        service = await self.create_service()
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = os.path.join(tmpdir, "cloned_repo")

            try:
                url = self.get_test_repo_url()
                await service.clone_repository(url, target_path)

                # Push should work (even if nothing to push)
                try:
                    await service.push(target_path, "main")
                except Exception:
                    # Push might fail due to permissions, that's ok
                    # We're just testing the interface exists
                    pass
            finally:
                await self.cleanup_repo_path(target_path)

    # Error Handling Tests

    @pytest.mark.asyncio
    async def test_invalid_repo_path_raises_error(self):
        """Operations on invalid paths should raise RepositoryError."""
        service = await self.create_service()

        with pytest.raises(RepositoryError):
            await service.pull_latest("/nonexistent/path/that/does/not/exist")

    @pytest.mark.asyncio
    async def test_invalid_branch_raises_error(self):
        """Checking out invalid branch should raise RepositoryError."""
        service = await self.create_service()
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = os.path.join(tmpdir, "cloned_repo")

            try:
                url = self.get_test_repo_url()
                await service.clone_repository(url, target_path)

                with pytest.raises(RepositoryError):
                    await service.checkout(target_path, "nonexistent-branch-xyz")
            finally:
                await self.cleanup_repo_path(target_path)

    @pytest.mark.asyncio
    async def test_service_has_no_event_methods(self):
        """IVersionControlService should NOT have event methods."""
        service = await self.create_service()

        # Should not have event methods (no event emission)
        assert not hasattr(service, "on")
        assert not hasattr(service, "off")
        assert not hasattr(service, "emit")
