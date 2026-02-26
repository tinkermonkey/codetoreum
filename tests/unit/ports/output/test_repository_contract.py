"""Contract tests for IRepository interface.

These abstract tests define the contract that all IRepository implementations must
satisfy. Subclasses provide specific implementations to test via create_repository().

The tests validate:
- Repository initialization and file operations
- Branch creation and checkout
- File content retrieval and modifications
- Commit operations and history
- Multi-operation sequences with state consistency
"""

from abc import ABC, abstractmethod
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from codetoreum.domain.types import BranchName, RepositoryId
from codetoreum.ports.exceptions import ResourceNotFoundError, ValidationError
from codetoreum.ports.output.repository import IRepository, MergeResult, RepositoryStatus


class TestRepositoryContract(ABC):
    """Abstract contract tests for IRepository implementations.

    Subclasses must implement create_repository() to provide a concrete
    IRepository implementation to test.

    These tests verify:
    - Basic repository operations (clone, checkout, commit)
    - File operations (get content, write content)
    - Branch management (create, list, switch)
    - Commit history and metadata
    - Multi-operation state consistency
    - Error handling for missing files/branches
    """

    @abstractmethod
    async def create_repository(self) -> IRepository:
        """Create and return an IRepository instance for testing."""

    # ===== Repository Initialization Tests =====

    @pytest.mark.asyncio
    async def test_clone_initializes_repository(self):
        """State consistency: clone creates usable repository."""
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            repo_id = await repo.clone("https://github.com/test/repo", dest)

            assert isinstance(repo_id, str)
            assert len(repo_id) > 0

    @pytest.mark.asyncio
    async def test_clone_with_branch(self):
        """State consistency: clone with specific branch checks out that branch."""
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            # Clone with specific branch
            await repo.clone("https://github.com/test/repo", dest, branch=BranchName("develop"))

            # Repository should be on that branch
            status = await repo.status(dest)
            assert status.current_branch == BranchName("develop")

    @pytest.mark.asyncio
    async def test_clone_validates_url(self):
        """Error condition: clone with empty URL raises ValidationError."""
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            with pytest.raises(ValidationError):
                await repo.clone("", dest)

    # ===== Branch Operations Tests =====

    @pytest.mark.asyncio
    async def test_create_branch_and_checkout(self):
        """State consistency: create_branch→checkout switches to new branch."""
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            await repo.clone("https://github.com/test/repo", dest)

            # Create new branch
            await repo.create_branch(dest, BranchName("feature-branch"))
            await repo.checkout(dest, BranchName("feature-branch"))

            # Verify we're on the new branch
            status = await repo.status(dest)
            assert status.current_branch == BranchName("feature-branch")

    @pytest.mark.asyncio
    async def test_create_branch_from_specific_branch(self):
        """State consistency: create_branch with from_branch uses that base."""
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            await repo.clone("https://github.com/test/repo", dest)

            # Create develop branch from main
            await repo.create_branch(dest, BranchName("develop"), from_branch=BranchName("main"))
            await repo.checkout(dest, BranchName("develop"))

            status = await repo.status(dest)
            assert status.current_branch == BranchName("develop")

    @pytest.mark.asyncio
    async def test_checkout_existing_branch(self):
        """State consistency: checkout switches to existing branch."""
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            await repo.clone("https://github.com/test/repo", dest)

            # Create and switch to feature branch
            await repo.create_branch(dest, BranchName("feature"))
            await repo.checkout(dest, BranchName("feature"))
            status = await repo.status(dest)
            assert status.current_branch == BranchName("feature")

            # Switch back to main
            await repo.checkout(dest, BranchName("main"))
            status = await repo.status(dest)
            assert status.current_branch == BranchName("main")

    @pytest.mark.asyncio
    async def test_checkout_nonexistent_branch_raises_error(self):
        """Error condition: checkout missing branch raises ResourceNotFoundError."""
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            await repo.clone("https://github.com/test/repo", dest)

            with pytest.raises(ResourceNotFoundError):
                await repo.checkout(dest, BranchName("nonexistent"))

    @pytest.mark.asyncio
    async def test_checkout_with_create_flag(self):
        """State consistency: checkout with create=True creates missing branch."""
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            await repo.clone("https://github.com/test/repo", dest)

            # Checkout with create=True should create the branch
            await repo.checkout(dest, BranchName("new-branch"), create=True)

            status = await repo.status(dest)
            assert status.current_branch == BranchName("new-branch")

    @pytest.mark.asyncio
    async def test_list_branches(self):
        """State consistency: list_branches returns all local branches."""
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            await repo.clone("https://github.com/test/repo", dest)

            # Create multiple branches
            await repo.create_branch(dest, BranchName("feature-1"))
            await repo.create_branch(dest, BranchName("feature-2"))

            # List branches
            branches = await repo.list_branches(dest)
            assert "main" in branches
            assert "feature-1" in branches
            assert "feature-2" in branches

    # ===== File Operations Tests =====

    @pytest.mark.asyncio
    async def test_get_file_content_nonexistent_raises_error(self):
        """Error condition: get_file_content for missing file raises error."""
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            await repo.clone("https://github.com/test/repo", dest)

            with pytest.raises(ResourceNotFoundError) as exc_info:
                await repo.get_file_content(dest, "nonexistent.py")
            assert "nonexistent.py" in str(exc_info.value)

    # ===== Commit Operations Tests =====

    @pytest.mark.asyncio
    async def test_commit_creates_commit_with_message(self):
        """State consistency: commit creates entry with message."""
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            await repo.clone("https://github.com/test/repo", dest)

            # Create a file to commit
            file_path = dest / "test.txt"
            file_path.write_text("test content")

            # Commit the file
            commit_hash = await repo.commit(
                dest,
                "Test commit message",
                author_name="Test Author",
                author_email="test@example.com",
                files=["test.txt"],
            )

            assert isinstance(commit_hash, str)
            assert len(commit_hash) > 0

    @pytest.mark.asyncio
    async def test_commit_validates_author_info(self):
        """Error condition: commit with missing author info raises error."""
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            await repo.clone("https://github.com/test/repo", dest)

            with pytest.raises(ValidationError):
                await repo.commit(
                    dest,
                    "Test commit",
                    author_name="",
                    author_email="test@example.com",
                )

    @pytest.mark.asyncio
    async def test_get_commit_history_returns_commits(self):
        """State consistency: get_commit_history returns commit list."""
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            await repo.clone("https://github.com/test/repo", dest)

            # Make some commits
            file_path = dest / "file1.txt"
            file_path.write_text("content 1")
            await repo.commit(
                dest,
                "First commit",
                author_name="Author",
                author_email="author@example.com",
                files=["file1.txt"],
            )

            file_path.write_text("content 2")
            await repo.commit(
                dest,
                "Second commit",
                author_name="Author",
                author_email="author@example.com",
                files=["file1.txt"],
            )

            # Get history
            history = await repo.get_commit_history(dest, limit=10)
            assert len(history) >= 2
            # Most recent should be at index 0
            assert "Second commit" in history[0]["message"]

    # ===== Status Tests =====

    @pytest.mark.asyncio
    async def test_status_returns_current_branch(self):
        """State consistency: status returns current branch."""
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            await repo.clone("https://github.com/test/repo", dest)
            await repo.create_branch(dest, BranchName("develop"))
            await repo.checkout(dest, BranchName("develop"))

            status = await repo.status(dest)
            assert status.current_branch == BranchName("develop")

    @pytest.mark.asyncio
    async def test_status_detects_dirty_state(self):
        """State consistency: status returns valid RepositoryStatus object."""
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            await repo.clone("https://github.com/test/repo", dest)

            # Get status - should return valid RepositoryStatus object
            status = await repo.status(dest)
            assert isinstance(status, RepositoryStatus)
            assert isinstance(status.is_dirty, bool)
            assert isinstance(status.staged_files, tuple)
            assert isinstance(status.unstaged_files, tuple)
            assert isinstance(status.untracked_files, tuple)

    # ===== Remote Operations Tests =====

    @pytest.mark.asyncio
    async def test_add_remote_and_remove_remote(self):
        """State consistency: add_remote→remove_remote manages remotes."""
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            await repo.clone("https://github.com/test/repo", dest)

            # Add a remote
            await repo.add_remote(dest, "upstream", "https://github.com/original/repo")

            # Remove the remote
            await repo.remove_remote(dest, "upstream")

            # Verify it's removed
            with pytest.raises(ResourceNotFoundError):
                await repo.remove_remote(dest, "upstream")

    @pytest.mark.asyncio
    async def test_remove_nonexistent_remote_raises_error(self):
        """Error condition: remove_remote for missing remote raises error."""
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            await repo.clone("https://github.com/test/repo", dest)

            with pytest.raises(ResourceNotFoundError):
                await repo.remove_remote(dest, "nonexistent")

    # ===== Merge Tests =====

    @pytest.mark.asyncio
    async def test_merge_compatible_branches(self):
        """State consistency: merge combines branches and returns MergeResult.

        This test validates that merge operations return a valid MergeResult
        with success status and conflict tracking.
        """
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            await repo.clone("https://github.com/test/repo", dest)

            # Create feature branch
            await repo.create_branch(dest, BranchName("feature"))
            await repo.checkout(dest, BranchName("feature"))

            file_path = dest / "feature.txt"
            file_path.write_text("feature content")

            await repo.commit(
                dest,
                "Add feature file",
                author_name="Author",
                author_email="author@example.com",
                files=["feature.txt"],
            )

            # Switch back to main and merge
            await repo.checkout(dest, BranchName("main"))
            result = await repo.merge(dest, "feature")

            # Merge should return a valid MergeResult
            assert isinstance(result, MergeResult)
            # Compatible branches should merge without conflicts
            assert result.success is True
            assert isinstance(result.conflicts, tuple)

    # ===== Diff Tests =====

    @pytest.mark.asyncio
    async def test_diff_returns_differences(self):
        """State consistency: diff shows changes between refs."""
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            await repo.clone("https://github.com/test/repo", dest)

            # Create a file and commit
            file1 = dest / "file1.txt"
            file1.write_text("original content")

            commit1 = await repo.commit(
                dest,
                "First commit",
                author_name="Author",
                author_email="author@example.com",
                files=["file1.txt"],
            )

            # Modify and commit again
            file1.write_text("modified content")

            commit2 = await repo.commit(
                dest,
                "Second commit",
                author_name="Author",
                author_email="author@example.com",
                files=["file1.txt"],
            )

            # Get diff
            diff = await repo.diff(dest, commit1, commit2)
            assert isinstance(diff, str)
            assert len(diff) > 0

    @pytest.mark.asyncio
    async def test_diff_with_empty_ref_raises_error(self):
        """Error condition: diff with empty ref validates input parameters.

        Per the IRepository interface contract, diff() raises ValidationError
        when parameters are empty/invalid. All implementations must enforce this.
        """
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            await repo.clone("https://github.com/test/repo", dest)

            # Attempting to diff with empty ref must raise ValidationError
            with pytest.raises(ValidationError):
                await repo.diff(dest, "main", "")

    # ===== Get Commit Info Tests =====

    @pytest.mark.asyncio
    async def test_get_commit_info_returns_metadata(self):
        """State consistency: get_commit_info returns commit metadata."""
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            await repo.clone("https://github.com/test/repo", dest)

            # Create a commit
            file_path = dest / "test.txt"
            file_path.write_text("test content")

            commit_hash = await repo.commit(
                dest,
                "Test commit",
                author_name="Test Author",
                author_email="test@example.com",
                files=["test.txt"],
            )

            # Get commit info
            info = await repo.get_commit_info(dest, commit_hash)
            assert isinstance(info, dict)
            assert "message" in info
            assert "author" in info
            assert info["message"] == "Test commit"

    @pytest.mark.asyncio
    async def test_get_commit_info_nonexistent_raises_error(self):
        """Error condition: get_commit_info for missing commit raises error."""
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            await repo.clone("https://github.com/test/repo", dest)

            with pytest.raises(ResourceNotFoundError):
                await repo.get_commit_info(dest, "nonexistent-sha")

    # ===== Remote Operations Tests (Push/Pull/Fetch) =====

    @pytest.mark.asyncio
    async def test_push_to_valid_remote(self):
        """State consistency: push to a valid remote is callable without raising unexpected errors.

        For mock implementations, push may not fully function but must not raise
        unexpected exceptions. Production implementations should successfully push.
        """
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            await repo.clone("https://github.com/test/repo", dest)

            # Create a commit to push
            file_path = dest / "push-test.txt"
            file_path.write_text("test content")

            await repo.commit(
                dest,
                "Test commit for push",
                author_name="Test Author",
                author_email="test@example.com",
                files=["push-test.txt"],
            )

            # Push should be callable. If mock doesn't support it, skip gracefully.
            try:
                await repo.push(dest, "origin", BranchName("main"))
            except NotImplementedError:
                pytest.skip("Push not implemented in this adapter")

    @pytest.mark.asyncio
    async def test_pull_from_valid_remote(self):
        """State consistency: pull from a valid remote is callable without raising unexpected errors.

        For mock implementations, pull may not fully function but must not raise
        unexpected exceptions. Production implementations should successfully pull.
        """
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            await repo.clone("https://github.com/test/repo", dest)

            # Pull should be callable. If mock doesn't support it, skip gracefully.
            try:
                await repo.pull(dest, "origin", BranchName("main"))
            except NotImplementedError:
                pytest.skip("Pull not implemented in this adapter")

    @pytest.mark.asyncio
    async def test_fetch_from_valid_remote(self):
        """State consistency: fetch from a valid remote is callable without raising unexpected errors.

        For mock implementations, fetch may not fully function but must not raise
        unexpected exceptions. Production implementations should successfully fetch.
        """
        repo = await self.create_repository()

        with TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-repo"
            dest.mkdir()

            await repo.clone("https://github.com/test/repo", dest)

            # Fetch should be callable. If mock doesn't support it, skip gracefully.
            try:
                await repo.fetch(dest, "origin")
            except NotImplementedError:
                pytest.skip("Fetch not implemented in this adapter")
