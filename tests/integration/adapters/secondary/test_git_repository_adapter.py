"""Integration tests for Git Repository Adapter.

These tests interact with actual git repositories and require:
- Git installed and available in PATH
- Filesystem access for temporary repositories
"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from codetoreum.adapters.secondary import GitConfig, GitRepositoryAdapter
from codetoreum.domain.types import BranchName
from codetoreum.ports.exceptions import (
    ValidationError,
)


@pytest.fixture
def git_config():
    """Create Git configuration."""
    return GitConfig(
        git_path="git",
        default_author_name="Test User",
        default_author_email="test@example.com",
        timeout_seconds=30,
    )


@pytest.fixture
def git_adapter(git_config):
    """Create Git adapter instance."""
    return GitRepositoryAdapter(git_config)


@pytest.fixture
def temp_repo():
    """Create a temporary directory for test repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_clone_repository(git_adapter, temp_repo):
    """Test cloning a repository."""
    # Clone a small public repository
    repo_path = temp_repo / "test-repo"

    repo_id = await git_adapter.clone(
        url="https://github.com/octocat/Hello-World.git",
        destination=repo_path,
    )

    assert repo_id is not None
    assert repo_path.exists()
    assert (repo_path / ".git").exists()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_and_checkout_branch(git_adapter, temp_repo):
    """Test creating and checking out branches."""
    # Initialize repository
    repo_path = temp_repo / "test-repo"
    repo_path.mkdir()

    await git_adapter._run_git_command(["init"], cwd=repo_path)
    await git_adapter._run_git_command(
        ["config", "user.name", "Test User"],
        cwd=repo_path,
    )
    await git_adapter._run_git_command(
        ["config", "user.email", "test@example.com"],
        cwd=repo_path,
    )

    # Create initial commit
    test_file = repo_path / "test.txt"
    test_file.write_text("Hello")

    await git_adapter._run_git_command(["add", "."], cwd=repo_path)
    await git_adapter._run_git_command(
        ["commit", "-m", "Initial commit"],
        cwd=repo_path,
    )

    # Create new branch
    await git_adapter.create_branch(repo_path, BranchName("feature-branch"))

    # List branches
    branches = await git_adapter.list_branches(repo_path)
    assert "feature-branch" in branches

    # Checkout branch
    await git_adapter.checkout(repo_path, BranchName("feature-branch"))

    # Get status
    status = await git_adapter.status(repo_path)
    assert status.current_branch == BranchName("feature-branch")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_commit_workflow(git_adapter, temp_repo):
    """Test committing changes."""
    # Initialize repository
    repo_path = temp_repo / "test-repo"
    repo_path.mkdir()

    await git_adapter._run_git_command(["init"], cwd=repo_path)
    await git_adapter._run_git_command(
        ["config", "user.name", "Test User"],
        cwd=repo_path,
    )
    await git_adapter._run_git_command(
        ["config", "user.email", "test@example.com"],
        cwd=repo_path,
    )

    # Create file
    test_file = repo_path / "test.txt"
    test_file.write_text("Hello, World!")

    # Get status before commit
    status = await git_adapter.status(repo_path)
    assert status.is_dirty is True
    assert "test.txt" in status.untracked_files

    # Stage the file
    await git_adapter.stage_files(repo_path, ["test.txt"])

    # Commit
    commit_sha = await git_adapter.commit(
        repo_path,
        message="Add test file",
        author_name="Test User",
        author_email="test@example.com",
    )

    assert commit_sha is not None
    assert len(commit_sha) == 40  # Git SHA is 40 characters

    # Get status after commit
    status = await git_adapter.status(repo_path)
    assert status.is_dirty is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_commit_info(git_adapter, temp_repo):
    """Test getting commit information."""
    # Initialize repository and create commit
    repo_path = temp_repo / "test-repo"
    repo_path.mkdir()

    await git_adapter._run_git_command(["init"], cwd=repo_path)
    await git_adapter._run_git_command(
        ["config", "user.name", "Test User"],
        cwd=repo_path,
    )
    await git_adapter._run_git_command(
        ["config", "user.email", "test@example.com"],
        cwd=repo_path,
    )

    test_file = repo_path / "test.txt"
    test_file.write_text("Test content")

    # Stage and commit
    await git_adapter.stage_files(repo_path, ["test.txt"])
    commit_sha = await git_adapter.commit(
        repo_path,
        message="Test commit",
        author_name="Test User",
        author_email="test@example.com",
    )

    # Get commit info
    commit_info = await git_adapter.get_commit_info(repo_path, commit_sha)

    assert commit_info.sha == commit_sha
    assert commit_info.author.name == "Test User"
    assert commit_info.author.email == "test@example.com"
    assert commit_info.message == "Test commit"
    assert isinstance(commit_info.timestamp, datetime)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_commit_history(git_adapter, temp_repo):
    """Test getting commit history."""
    # Initialize repository and create multiple commits
    repo_path = temp_repo / "test-repo"
    repo_path.mkdir()

    await git_adapter._run_git_command(["init"], cwd=repo_path)
    await git_adapter._run_git_command(
        ["config", "user.name", "Test User"],
        cwd=repo_path,
    )
    await git_adapter._run_git_command(
        ["config", "user.email", "test@example.com"],
        cwd=repo_path,
    )

    # Create multiple commits
    for i in range(3):
        test_file = repo_path / f"file{i}.txt"
        test_file.write_text(f"Content {i}")

        # Stage and commit
        await git_adapter.stage_files(repo_path, [f"file{i}.txt"])
        await git_adapter.commit(
            repo_path,
            message=f"Commit {i}",
            author_name="Test User",
            author_email="test@example.com",
        )

    # Get history
    history = await git_adapter.get_commit_history(repo_path, limit=10)

    assert len(history) == 3
    assert history[0].message == "Commit 2"  # Most recent first
    assert history[2].message == "Commit 0"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_merge_branches(git_adapter, temp_repo):
    """Test merging branches."""
    # Initialize repository
    repo_path = temp_repo / "test-repo"
    repo_path.mkdir()

    await git_adapter._run_git_command(["init"], cwd=repo_path)
    await git_adapter._run_git_command(
        ["config", "user.name", "Test User"],
        cwd=repo_path,
    )
    await git_adapter._run_git_command(
        ["config", "user.email", "test@example.com"],
        cwd=repo_path,
    )

    # Create initial commit on main
    (repo_path / "main.txt").write_text("Main")
    await git_adapter.stage_files(repo_path, ["main.txt"])
    await git_adapter.commit(
        repo_path,
        message="Main commit",
        author_name="Test User",
        author_email="test@example.com",
    )

    # Create feature branch
    await git_adapter.create_branch(repo_path, BranchName("feature"))
    await git_adapter.checkout(repo_path, BranchName("feature"))

    # Create commit on feature branch
    (repo_path / "feature.txt").write_text("Feature")
    await git_adapter.stage_files(repo_path, ["feature.txt"])
    await git_adapter.commit(
        repo_path,
        message="Feature commit",
        author_name="Test User",
        author_email="test@example.com",
    )

    # Switch back to main
    await git_adapter.checkout(repo_path, BranchName("master"))

    # Merge feature into main
    result = await git_adapter.merge(repo_path, "feature")

    assert result.success is True
    assert len(result.conflicts) == 0
    assert result.merge_commit is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_diff(git_adapter, temp_repo):
    """Test getting diff between refs."""
    # Initialize repository
    repo_path = temp_repo / "test-repo"
    repo_path.mkdir()

    await git_adapter._run_git_command(["init"], cwd=repo_path)
    await git_adapter._run_git_command(
        ["config", "user.name", "Test User"],
        cwd=repo_path,
    )
    await git_adapter._run_git_command(
        ["config", "user.email", "test@example.com"],
        cwd=repo_path,
    )

    # Create first commit
    (repo_path / "file.txt").write_text("Version 1")
    await git_adapter.stage_files(repo_path, ["file.txt"])
    commit1 = await git_adapter.commit(
        repo_path,
        message="First",
        author_name="Test User",
        author_email="test@example.com",
    )

    # Create second commit
    (repo_path / "file.txt").write_text("Version 2")
    await git_adapter.stage_files(repo_path, ["file.txt"])
    commit2 = await git_adapter.commit(
        repo_path,
        message="Second",
        author_name="Test User",
        author_email="test@example.com",
    )

    # Get diff
    diff = await git_adapter.diff(repo_path, commit1, commit2)

    assert diff is not None
    assert "Version 1" in diff or "Version 2" in diff


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_file_content(git_adapter, temp_repo):
    """Test getting file content."""
    # Initialize repository
    repo_path = temp_repo / "test-repo"
    repo_path.mkdir()

    await git_adapter._run_git_command(["init"], cwd=repo_path)
    await git_adapter._run_git_command(
        ["config", "user.name", "Test User"],
        cwd=repo_path,
    )
    await git_adapter._run_git_command(
        ["config", "user.email", "test@example.com"],
        cwd=repo_path,
    )

    # Create and commit file
    (repo_path / "test.txt").write_text("Test content")
    await git_adapter.stage_files(repo_path, ["test.txt"])
    commit_sha = await git_adapter.commit(
        repo_path,
        message="Add file",
        author_name="Test User",
        author_email="test@example.com",
    )

    # Get file content from working tree
    content = await git_adapter.get_file_content(repo_path, "test.txt")
    assert content == "Test content"

    # Get file content from specific commit
    content = await git_adapter.get_file_content(repo_path, "test.txt", ref=commit_sha)
    assert content == "Test content"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_add_remove_remote(git_adapter, temp_repo):
    """Test adding and removing remotes."""
    # Initialize repository
    repo_path = temp_repo / "test-repo"
    repo_path.mkdir()

    await git_adapter._run_git_command(["init"], cwd=repo_path)

    # Add remote
    await git_adapter.add_remote(
        repo_path,
        "origin",
        "https://github.com/test/test.git",
    )

    # Verify remote was added
    result = await git_adapter._run_git_command(["remote", "-v"], cwd=repo_path)
    assert "origin" in result.stdout

    # Remove remote
    await git_adapter.remove_remote(repo_path, "origin")

    # Verify remote was removed
    result = await git_adapter._run_git_command(["remote", "-v"], cwd=repo_path)
    assert "origin" not in result.stdout


@pytest.mark.integration
@pytest.mark.asyncio
async def test_invalid_repository_path(git_adapter):
    """Test operations on invalid repository path."""
    invalid_path = Path("/nonexistent/path")

    with pytest.raises(ValidationError):
        await git_adapter.checkout(invalid_path, BranchName("main"))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_context_manager(git_config):
    """Test using adapter as async context manager."""
    async with GitRepositoryAdapter(git_config) as adapter:
        # Adapter should be usable
        config = adapter.config
        assert config is not None
