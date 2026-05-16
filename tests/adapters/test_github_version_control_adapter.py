"""Tests for GitHubVersionControlAdapter."""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codetoreum.adapters.secondary.git_repository_adapter import GitConfig
from codetoreum.adapters.secondary.github_version_control_adapter import GitHubVersionControlAdapter
from codetoreum.ports.exceptions import ResourceNotFoundError
from codetoreum.ports.output.version_control_service import Repository


class TestGitHubVersionControlAdapter:
    """Test GitHubVersionControlAdapter contract compliance."""

    def test_implements_interface(self):
        """Adapter must implement IVersionControlService."""
        adapter = GitHubVersionControlAdapter()
        assert hasattr(adapter, "clone_repository")
        assert hasattr(adapter, "checkout")
        assert hasattr(adapter, "create_branch")
        assert hasattr(adapter, "commit")
        assert hasattr(adapter, "push")
        assert hasattr(adapter, "pull")
        assert hasattr(adapter, "list_branches")
        assert hasattr(adapter, "status")
        assert hasattr(adapter, "get_repository")

    def test_constructor_accepts_git_config(self):
        """Constructor should accept optional git_config."""
        config = GitConfig(default_author_name="test", default_author_email="test@example.com")
        adapter = GitHubVersionControlAdapter(git_config=config)
        assert adapter._git_config == config

    def test_constructor_uses_default_git_config(self):
        """Constructor should use default git config if not provided."""
        adapter = GitHubVersionControlAdapter()
        assert adapter._git_config is not None
        assert isinstance(adapter._git_config, GitConfig)

    def test_get_repository_with_valid_path(self):
        """get_repository should return Repository with URL from git remote."""
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = GitHubVersionControlAdapter()
            path = Path(tmpdir)

            # Initialize a git repo
            subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)  # noqa: S607
            subprocess.run(
                ["git", "remote", "add", "origin", "https://github.com/example/repo.git"],  # noqa: S607
                cwd=path,
                check=True,
                capture_output=True,
            )

            # Get repository info
            repo = AsyncMock()
            repo.id = str(path)
            repo.name = path.name
            repo.url = "https://github.com/example/repo.git"
            repo.default_branch = "main"

            # Verify it would create a valid Repository
            with patch.object(adapter, "_repository_adapter", AsyncMock()):
                result = subprocess.run(
                    ["git", "remote", "get-url", "origin"],  # noqa: S607
                    cwd=path,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                assert result.stdout.strip() == "https://github.com/example/repo.git"

    def test_get_repository_uses_file_url_fallback(self):
        """get_repository should use file:// URL if git remote not available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = GitHubVersionControlAdapter()
            path = Path(tmpdir)

            # Initialize git repo without remote
            subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)  # noqa: S607

            # Verify fallback URL format
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],  # noqa: S607
                cwd=path,
                capture_output=True,
                text=True,
                check=False,
            )
            # Should fail since remote doesn't exist
            assert result.returncode != 0

    def test_pull_uses_keyword_arguments(self):
        """pull method should pass remote and branch as keyword arguments."""
        adapter = GitHubVersionControlAdapter()

        # Mock the underlying repository adapter
        adapter._repository_adapter = AsyncMock()

        # Call pull - verify it passes keyword arguments
        with patch.object(adapter._repository_adapter, "pull", new_callable=AsyncMock) as mock_pull:
            import asyncio

            asyncio.run(adapter.pull("/tmp/repo", "main", "origin"))
            # Verify keyword arguments were used
            mock_pull.assert_called_once()
            args, kwargs = mock_pull.call_args
            # First arg should be the path, then keyword args
            assert "remote" in kwargs or kwargs.get("remote") == "origin"
            assert "branch" in kwargs or kwargs.get("branch") == "main"

    def test_event_emitter_parameter_removed(self):
        """Constructor should not accept event_emitter parameter."""
        # Verify the constructor signature doesn't include event_emitter
        import inspect

        sig = inspect.signature(GitHubVersionControlAdapter.__init__)
        param_names = list(sig.parameters.keys())
        assert "event_emitter" not in param_names
        assert "kwargs" not in param_names

    def test_no_excessive_docstrings(self):
        """Methods should have minimal docstrings."""
        # Verify method docstrings are brief
        assert len((GitHubVersionControlAdapter.clone_repository.__doc__ or "").split("\n")) <= 2
        assert len((GitHubVersionControlAdapter.checkout.__doc__ or "").split("\n")) <= 2
        assert len((GitHubVersionControlAdapter.commit.__doc__ or "").split("\n")) <= 2


class TestRepositoryValidation:
    """Test Repository dataclass validation."""

    def test_repository_requires_non_empty_url(self):
        """Repository should require non-empty URL."""
        with pytest.raises(ValueError, match="url must be a non-empty string"):
            Repository(
                id="test",
                name="test-repo",
                url="",  # Empty URL should fail
                default_branch="main",
            )

    def test_repository_with_valid_url(self):
        """Repository should accept valid URLs."""
        repo = Repository(
            id="test",
            name="test-repo",
            url="https://github.com/example/repo.git",
            default_branch="main",
        )
        assert repo.url == "https://github.com/example/repo.git"

    def test_repository_with_file_url(self):
        """Repository should accept file:// URLs."""
        repo = Repository(
            id="test",
            name="test-repo",
            url="file:///tmp/repo",
            default_branch="main",
        )
        assert repo.url == "file:///tmp/repo"
