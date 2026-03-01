"""Unit tests for InMemoryRepositoryAdapter."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from codetoreum.adapters.testing import InMemoryRepositoryAdapter
from codetoreum.domain.types import BranchName
from codetoreum.ports.exceptions import ResourceNotFoundError, ValidationError


@pytest.mark.asyncio
class TestInMemoryRepositoryAdapter:
    """Tests for InMemoryRepositoryAdapter."""

    @pytest.fixture
    def adapter(self):
        """Create adapter instance."""
        return InMemoryRepositoryAdapter()

    async def test_clone_repository(self, adapter):
        """Test cloning a repository."""
        repo_id = await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        assert repo_id is not None
        assert adapter.get_repository_count() == 1

    async def test_clone_with_branch(self, adapter):
        """Test cloning with specific branch."""
        repo_id = await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
            branch=BranchName("develop"),
        )

        status = await adapter.status(Path("/tmp/test-repo"))
        assert status.current_branch == "develop"

    async def test_clone_validation(self, adapter):
        """Test clone parameter validation."""
        with pytest.raises(ValidationError, match="Repository URL is required"):
            await adapter.clone(
                url="",
                destination=Path("/tmp/test"),
            )

        with pytest.raises(ValidationError, match="Destination path is required"):
            await adapter.clone(
                url="https://github.com/test/repo.git",
                destination=None,
            )

    async def test_checkout_existing_branch(self, adapter):
        """Test checking out an existing branch."""
        repo_id = await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
            branch=BranchName("main"),
        )

        # Create another branch
        await adapter.create_branch(
            repo_path=Path("/tmp/test-repo"),
            branch_name=BranchName("feature-branch"),
        )

        # Checkout the new branch
        await adapter.checkout(
            repo_path=Path("/tmp/test-repo"),
            branch=BranchName("feature-branch"),
        )

        status = await adapter.status(Path("/tmp/test-repo"))
        assert status.current_branch == "feature-branch"

    async def test_checkout_create_new_branch(self, adapter):
        """Test checking out and creating a new branch."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        await adapter.checkout(
            repo_path=Path("/tmp/test-repo"),
            branch=BranchName("new-branch"),
            create=True,
        )

        status = await adapter.status(Path("/tmp/test-repo"))
        assert status.current_branch == "new-branch"

    async def test_checkout_nonexistent_branch_fails(self, adapter):
        """Test checking out non-existent branch fails."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        with pytest.raises(ResourceNotFoundError, match="Branch"):
            await adapter.checkout(
                repo_path=Path("/tmp/test-repo"),
                branch=BranchName("nonexistent"),
                create=False,
            )

    async def test_create_branch(self, adapter):
        """Test creating a new branch."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        await adapter.create_branch(
            repo_path=Path("/tmp/test-repo"),
            branch_name=BranchName("feature-123"),
        )

        branches = await adapter.list_branches(Path("/tmp/test-repo"))
        assert "feature-123" in branches

    async def test_create_branch_from_source(self, adapter):
        """Test creating branch from specific source branch."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        await adapter.create_branch(
            repo_path=Path("/tmp/test-repo"),
            branch_name=BranchName("develop"),
        )

        await adapter.create_branch(
            repo_path=Path("/tmp/test-repo"),
            branch_name=BranchName("feature-from-develop"),
            from_branch=BranchName("develop"),
        )

        branches = await adapter.list_branches(Path("/tmp/test-repo"))
        assert "feature-from-develop" in branches

    async def test_create_branch_validation(self, adapter):
        """Test create branch validation."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        with pytest.raises(ValidationError, match="Branch name is required"):
            await adapter.create_branch(
                repo_path=Path("/tmp/test-repo"),
                branch_name=BranchName(""),
            )

    async def test_stage_files(self, adapter):
        """Test staging files for commit."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        # Stage files
        await adapter.stage_files(
            repo_path=Path("/tmp/test-repo"),
            files=["src/main.py", "tests/test_main.py"],
        )

        # Verify status shows staged files
        status = await adapter.status(Path("/tmp/test-repo"))
        assert status.staged_files == ("src/main.py", "tests/test_main.py")
        assert status.is_dirty

    async def test_stage_files_multiple_calls(self, adapter):
        """Test staging files across multiple calls."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        # Stage first batch
        await adapter.stage_files(
            repo_path=Path("/tmp/test-repo"),
            files=["src/main.py"],
        )

        # Stage second batch
        await adapter.stage_files(
            repo_path=Path("/tmp/test-repo"),
            files=["tests/test_main.py"],
        )

        # Verify all files are staged
        status = await adapter.status(Path("/tmp/test-repo"))
        assert set(status.staged_files) == {"src/main.py", "tests/test_main.py"}

    async def test_stage_files_validation(self, adapter):
        """Test stage_files parameter validation."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        with pytest.raises(ValidationError, match="Repository path is required"):
            await adapter.stage_files(
                repo_path=None,
                files=["src/main.py"],
            )

        with pytest.raises(ValidationError, match="Files list is required and cannot be empty"):
            await adapter.stage_files(
                repo_path=Path("/tmp/test-repo"),
                files=[],
            )

    async def test_stage_files_cleared_on_commit(self, adapter):
        """Test that staged files are cleared after commit."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        # Stage files
        await adapter.stage_files(
            repo_path=Path("/tmp/test-repo"),
            files=["src/main.py", "tests/test_main.py"],
        )

        # Verify files are staged
        status = await adapter.status(Path("/tmp/test-repo"))
        assert len(status.staged_files) > 0

        # Commit
        await adapter.commit(
            repo_path=Path("/tmp/test-repo"),
            message="Test commit",
            author_name="Test",
            author_email="test@example.com",
        )

        # Verify staging area is cleared
        status = await adapter.status(Path("/tmp/test-repo"))
        assert status.staged_files == ()
        assert not status.is_dirty

    async def test_commit(self, adapter):
        """Test creating a commit."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        commit_sha = await adapter.commit(
            repo_path=Path("/tmp/test-repo"),
            message="Add new feature",
            author_name="Test Author",
            author_email="test@example.com",
            files=["src/main.py", "tests/test_main.py"],
        )

        assert commit_sha is not None
        assert isinstance(commit_sha, str)

        # Verify commit was created
        commit_info = await adapter.get_commit_info(
            repo_path=Path("/tmp/test-repo"),
            commit_sha=commit_sha,
        )
        assert commit_info.message == "Add new feature"
        assert commit_info.author.name == "Test Author"

    async def test_commit_validation(self, adapter):
        """Test commit validation."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        with pytest.raises(ValidationError, match="Commit message is required"):
            await adapter.commit(
                repo_path=Path("/tmp/test-repo"),
                message="",
                author_name="Test",
                author_email="test@example.com",
            )

        with pytest.raises(ValidationError, match="Author name and email are required"):
            await adapter.commit(
                repo_path=Path("/tmp/test-repo"),
                message="Test commit",
                author_name="",
                author_email="test@example.com",
            )

    async def test_push(self, adapter):
        """Test pushing to remote."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        await adapter.commit(
            repo_path=Path("/tmp/test-repo"),
            message="Test commit",
            author_name="Test",
            author_email="test@example.com",
        )

        # Should complete without error
        await adapter.push(
            repo_path=Path("/tmp/test-repo"),
            remote="origin",
        )

    async def test_push_missing_remote_fails(self, adapter):
        """Test push to non-existent remote fails."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        with pytest.raises(ResourceNotFoundError, match="Remote"):
            await adapter.push(
                repo_path=Path("/tmp/test-repo"),
                remote="nonexistent",
            )

    async def test_pull(self, adapter):
        """Test pulling from remote."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        # Should complete without error
        await adapter.pull(
            repo_path=Path("/tmp/test-repo"),
            remote="origin",
        )

    async def test_fetch(self, adapter):
        """Test fetching from remote."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        # Should complete without error
        await adapter.fetch(
            repo_path=Path("/tmp/test-repo"),
            remote="origin",
            prune=True,
        )

    async def test_diff(self, adapter):
        """Test getting diff between refs."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        diff = await adapter.diff(
            repo_path=Path("/tmp/test-repo"),
            base="main",
            target="HEAD",
        )

        assert isinstance(diff, str)
        assert "diff --git" in diff

    async def test_status(self, adapter):
        """Test getting repository status."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        status = await adapter.status(Path("/tmp/test-repo"))

        assert status.current_branch == "main"
        assert not status.is_dirty
        assert status.ahead_count == 0
        assert status.behind_count == 0

    async def test_list_branches(self, adapter):
        """Test listing branches."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        await adapter.create_branch(
            repo_path=Path("/tmp/test-repo"),
            branch_name=BranchName("feature-1"),
        )

        await adapter.create_branch(
            repo_path=Path("/tmp/test-repo"),
            branch_name=BranchName("feature-2"),
        )

        branches = await adapter.list_branches(Path("/tmp/test-repo"))
        assert "main" in branches
        assert "feature-1" in branches
        assert "feature-2" in branches

    async def test_merge(self, adapter):
        """Test merging branches."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        # Create and switch to feature branch
        await adapter.create_branch(
            repo_path=Path("/tmp/test-repo"),
            branch_name=BranchName("feature"),
        )
        await adapter.checkout(
            repo_path=Path("/tmp/test-repo"),
            branch=BranchName("feature"),
        )

        # Make a commit on feature branch
        await adapter.commit(
            repo_path=Path("/tmp/test-repo"),
            message="Feature commit",
            author_name="Test",
            author_email="test@example.com",
        )

        # Switch back to main and merge
        await adapter.checkout(
            repo_path=Path("/tmp/test-repo"),
            branch=BranchName("main"),
        )

        result = await adapter.merge(
            repo_path=Path("/tmp/test-repo"),
            branch="feature",
        )

        assert result.success
        assert len(result.conflicts) == 0
        assert result.merge_commit is not None

    async def test_merge_nonexistent_branch_fails(self, adapter):
        """Test merge of non-existent branch fails."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        with pytest.raises(ResourceNotFoundError, match="Branch"):
            await adapter.merge(
                repo_path=Path("/tmp/test-repo"),
                branch="nonexistent",
            )

    async def test_get_file_content(self, adapter):
        """Test getting file content."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        # Set file content
        adapter.set_file_content(
            repo_path=Path("/tmp/test-repo"),
            file_path="README.md",
            content="# Test Repository",
        )

        content = await adapter.get_file_content(
            repo_path=Path("/tmp/test-repo"),
            file_path="README.md",
        )

        assert content == "# Test Repository"

    async def test_get_file_content_nonexistent_raises_error(self, adapter):
        """Test getting non-existent file raises ResourceNotFoundError."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        with pytest.raises(ResourceNotFoundError) as exc_info:
            await adapter.get_file_content(
                repo_path=Path("/tmp/test-repo"),
                file_path="nonexistent.txt",
            )

        assert "nonexistent.txt" in str(exc_info.value)
        assert exc_info.value.resource_id is not None

    async def test_get_commit_info(self, adapter):
        """Test getting commit information."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        commit_sha = await adapter.commit(
            repo_path=Path("/tmp/test-repo"),
            message="Test commit",
            author_name="John Doe",
            author_email="john@example.com",
        )

        commit_info = await adapter.get_commit_info(
            repo_path=Path("/tmp/test-repo"),
            commit_sha=commit_sha,
        )

        assert commit_info.sha == commit_sha
        assert commit_info.message == "Test commit"
        assert commit_info.author.name == "John Doe"
        assert commit_info.author.email == "john@example.com"
        assert commit_info.timestamp is not None

    async def test_get_commit_info_nonexistent_fails(self, adapter):
        """Test getting non-existent commit fails."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        with pytest.raises(ResourceNotFoundError, match="Commit"):
            await adapter.get_commit_info(
                repo_path=Path("/tmp/test-repo"),
                commit_sha="nonexistent-sha",
            )

    async def test_get_commit_history(self, adapter):
        """Test getting commit history."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        # Create multiple commits
        for i in range(3):
            await adapter.commit(
                repo_path=Path("/tmp/test-repo"),
                message=f"Commit {i}",
                author_name="Test",
                author_email="test@example.com",
            )

        history = await adapter.get_commit_history(
            repo_path=Path("/tmp/test-repo"),
        )

        # Should have initial commit + 3 new commits
        assert len(history) == 4
        assert history[0].message == "Commit 2"
        assert history[1].message == "Commit 1"
        assert history[2].message == "Commit 0"

    async def test_get_commit_history_with_limit(self, adapter):
        """Test getting commit history with limit."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        # Create multiple commits
        for i in range(5):
            await adapter.commit(
                repo_path=Path("/tmp/test-repo"),
                message=f"Commit {i}",
                author_name="Test",
                author_email="test@example.com",
            )

        history = await adapter.get_commit_history(
            repo_path=Path("/tmp/test-repo"),
            limit=3,
        )

        assert len(history) == 3

    async def test_get_commit_history_with_since(self, adapter):
        """Test getting commit history with since filter."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        # Create a commit
        await adapter.commit(
            repo_path=Path("/tmp/test-repo"),
            message="Old commit",
            author_name="Test",
            author_email="test@example.com",
        )

        # Mark the time
        cutoff_time = datetime.now(UTC)
        await asyncio.sleep(0.01)

        # Create newer commits
        for i in range(2):
            await adapter.commit(
                repo_path=Path("/tmp/test-repo"),
                message=f"New commit {i}",
                author_name="Test",
                author_email="test@example.com",
            )

        history = await adapter.get_commit_history(
            repo_path=Path("/tmp/test-repo"),
            since=cutoff_time,
        )

        assert len(history) == 2
        assert all("New commit" in commit.message for commit in history)

    async def test_get_commit_history_nonexistent_branch_fails(self, adapter):
        """Test getting history for non-existent branch fails."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        with pytest.raises(ResourceNotFoundError, match="Branch"):
            await adapter.get_commit_history(
                repo_path=Path("/tmp/test-repo"),
                branch="nonexistent",
            )

    async def test_add_remote(self, adapter):
        """Test adding a remote."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        await adapter.add_remote(
            repo_path=Path("/tmp/test-repo"),
            name="upstream",
            url="https://github.com/upstream/repo.git",
        )

        # Should be able to fetch from new remote
        await adapter.fetch(
            repo_path=Path("/tmp/test-repo"),
            remote="upstream",
        )

    async def test_add_remote_validation(self, adapter):
        """Test add remote validation."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        with pytest.raises(ValidationError, match="Remote name is required"):
            await adapter.add_remote(
                repo_path=Path("/tmp/test-repo"),
                name="",
                url="https://github.com/test/repo.git",
            )

        with pytest.raises(ValidationError, match="Remote URL is required"):
            await adapter.add_remote(
                repo_path=Path("/tmp/test-repo"),
                name="upstream",
                url="",
            )

    async def test_remove_remote(self, adapter):
        """Test removing a remote."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        await adapter.add_remote(
            repo_path=Path("/tmp/test-repo"),
            name="backup",
            url="https://github.com/backup/repo.git",
        )

        await adapter.remove_remote(
            repo_path=Path("/tmp/test-repo"),
            name="backup",
        )

        # Should fail to fetch from removed remote
        with pytest.raises(ResourceNotFoundError, match="Remote"):
            await adapter.fetch(
                repo_path=Path("/tmp/test-repo"),
                remote="backup",
            )

    async def test_remove_remote_nonexistent_fails(self, adapter):
        """Test removing non-existent remote fails."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        with pytest.raises(ResourceNotFoundError, match="Remote"):
            await adapter.remove_remote(
                repo_path=Path("/tmp/test-repo"),
                name="nonexistent",
            )

    async def test_repository_not_found_error(self, adapter):
        """Test operations on non-existent repository fail."""
        with pytest.raises(ResourceNotFoundError, match="Repository"):
            await adapter.status(Path("/tmp/nonexistent"))

        with pytest.raises(ResourceNotFoundError, match="Repository"):
            await adapter.checkout(
                repo_path=Path("/tmp/nonexistent"),
                branch=BranchName("main"),
            )

    async def test_clear(self, adapter):
        """Test clearing all repositories."""
        await adapter.clone(
            url="https://github.com/test/repo1.git",
            destination=Path("/tmp/repo1"),
        )

        await adapter.clone(
            url="https://github.com/test/repo2.git",
            destination=Path("/tmp/repo2"),
        )

        assert adapter.get_repository_count() == 2

        adapter.clear()

        assert adapter.get_repository_count() == 0

    async def test_multiple_repositories(self, adapter):
        """Test managing multiple repositories simultaneously."""
        repo1_id = await adapter.clone(
            url="https://github.com/test/repo1.git",
            destination=Path("/tmp/repo1"),
        )

        repo2_id = await adapter.clone(
            url="https://github.com/test/repo2.git",
            destination=Path("/tmp/repo2"),
        )

        assert repo1_id != repo2_id

        # Both should be accessible
        status1 = await adapter.status(Path("/tmp/repo1"))
        status2 = await adapter.status(Path("/tmp/repo2"))

        assert status1.current_branch == "main"
        assert status2.current_branch == "main"

    async def test_thread_safety_simulation(self, adapter):
        """Test concurrent operations (simulated thread safety)."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        # Simulate concurrent commits
        tasks = []
        for i in range(5):
            task = adapter.commit(
                repo_path=Path("/tmp/test-repo"),
                message=f"Concurrent commit {i}",
                author_name="Test",
                author_email="test@example.com",
            )
            tasks.append(task)

        commit_shas = await asyncio.gather(*tasks)

        # All commits should succeed with unique SHAs
        assert len(commit_shas) == 5
        assert len(set(commit_shas)) == 5

        # History should contain all commits
        history = await adapter.get_commit_history(
            repo_path=Path("/tmp/test-repo"),
        )
        assert len(history) >= 5
