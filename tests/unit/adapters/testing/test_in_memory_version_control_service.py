"""Tests for InMemoryVersionControlService.

This test class verifies that InMemoryVersionControlService correctly implements
IVersionControlService semantics and handles exceptions correctly.

Note: InMemoryVersionControlService is a pure in-memory implementation that does
not create actual files or directories. Tests verify the semantic contracts
(correct exception types, state transitions, etc.) rather than filesystem effects.
"""

import pytest

from codetoreum.adapters.testing.in_memory_version_control_service import (
    InMemoryVersionControlService,
)
from codetoreum.ports.exceptions import (
    RepositoryError,
    ResourceNotFoundError,
    ValidationError,
)
from codetoreum.ports.output.version_control_service import Repository


class TestInMemoryVersionControlServiceExceptions:
    """Test exception handling for InMemoryVersionControlService."""

    @pytest.mark.asyncio
    async def test_clone_repository_with_empty_url_raises_validation_error(self):
        """Cloning with empty URL should raise ValidationError."""
        service = InMemoryVersionControlService()

        with pytest.raises(ValidationError):
            await service.clone_repository("", "/workspace/repo")

    @pytest.mark.asyncio
    async def test_clone_repository_with_empty_path_raises_validation_error(self):
        """Cloning with empty target path should raise ValidationError."""
        service = InMemoryVersionControlService()

        with pytest.raises(ValidationError):
            await service.clone_repository("https://github.com/test/repo.git", "")

    @pytest.mark.asyncio
    async def test_checkout_nonexistent_repo_raises_repository_error(self):
        """Checking out in nonexistent repository should raise RepositoryError."""
        service = InMemoryVersionControlService()

        with pytest.raises(RepositoryError):
            await service.checkout("/nonexistent/repo/path", "main")

    @pytest.mark.asyncio
    async def test_commit_nonexistent_repo_raises_repository_error(self):
        """Committing in nonexistent repository should raise RepositoryError."""
        service = InMemoryVersionControlService()

        with pytest.raises(RepositoryError):
            await service.commit("/nonexistent/repo/path", "Test commit")

    @pytest.mark.asyncio
    async def test_commit_empty_message_raises_validation_error(self):
        """Committing with empty message should raise ValidationError."""
        service = InMemoryVersionControlService()
        # First clone to create the repository
        await service.clone_repository("https://github.com/test/repo.git", "/workspace/test-repo")

        with pytest.raises(ValidationError):
            await service.commit("/workspace/test-repo", "")

    @pytest.mark.asyncio
    async def test_push_nonexistent_repo_raises_repository_error(self):
        """Pushing nonexistent repository should raise RepositoryError."""
        service = InMemoryVersionControlService()

        with pytest.raises(RepositoryError):
            await service.push("/nonexistent/repo/path", "main")

    @pytest.mark.asyncio
    async def test_push_nonexistent_branch_raises_repository_error(self):
        """Pushing nonexistent branch should raise RepositoryError."""
        service = InMemoryVersionControlService()
        # First clone to create the repository
        await service.clone_repository("https://github.com/test/repo.git", "/workspace/test-repo")

        with pytest.raises(RepositoryError):
            await service.push("/workspace/test-repo", "nonexistent-branch")

    @pytest.mark.asyncio
    async def test_get_repository_nonexistent_raises_resource_not_found_error(self):
        """Getting nonexistent repository should raise ResourceNotFoundError."""
        service = InMemoryVersionControlService()

        with pytest.raises(ResourceNotFoundError) as exc_info:
            await service.get_repository("nonexistent-repo-id")

        exc = exc_info.value
        assert exc.resource_type == "Repository"
        assert "nonexistent-repo-id" in exc.resource_id


class TestInMemoryVersionControlServiceBehavior:
    """Test core behavior and state management."""

    @pytest.mark.asyncio
    async def test_clone_repository_makes_repository_findable(self):
        """After cloning, repository should be findable by URL or path."""
        service = InMemoryVersionControlService()
        url = "https://github.com/test/repo.git"
        path = "/workspace/test-repo"

        await service.clone_repository(url, path)

        # Should be findable by URL
        repo_by_url = await service.get_repository(url)
        assert repo_by_url.url == url

        # Should be findable by path
        repo_by_path = await service.get_repository(path)
        assert repo_by_path.url == url

    @pytest.mark.asyncio
    async def test_clone_extracts_repo_name_from_url(self):
        """Clone should extract repository name from URL."""
        service = InMemoryVersionControlService()
        url = "https://github.com/myorg/my-awesome-repo.git"

        await service.clone_repository(url, "/workspace/repo")

        repo = await service.get_repository(url)
        assert repo.name == "my-awesome-repo"

    @pytest.mark.asyncio
    async def test_clone_with_branch_parameter(self):
        """Clone should accept optional branch parameter."""
        service = InMemoryVersionControlService()

        # Should not raise
        await service.clone_repository(
            "https://github.com/test/repo.git",
            "/workspace/test-repo",
            branch="develop",
        )

        repo = await service.get_repository("/workspace/test-repo")
        assert repo is not None

    @pytest.mark.asyncio
    async def test_checkout_existing_branch(self):
        """Checkout should switch to existing branch."""
        service = InMemoryVersionControlService()
        path = "/workspace/test-repo"

        await service.clone_repository("https://github.com/test/repo.git", path)
        # Initial clone creates 'main' branch
        # Checkout to same branch should work
        await service.checkout(path, "main")

        # Should not raise

    @pytest.mark.asyncio
    async def test_checkout_creates_new_branch(self):
        """Checkout should create new branch if it doesn't exist."""
        service = InMemoryVersionControlService()
        path = "/workspace/test-repo"

        await service.clone_repository("https://github.com/test/repo.git", path)
        # Create a new branch via checkout
        await service.checkout(path, "feature/new-feature")

        # Should not raise

    @pytest.mark.asyncio
    async def test_commit_generates_unique_shas(self):
        """Commit should generate unique SHAs for different messages."""
        service = InMemoryVersionControlService()
        path = "/workspace/test-repo"

        await service.clone_repository("https://github.com/test/repo.git", path)

        sha1 = await service.commit(path, "First commit")
        sha2 = await service.commit(path, "Second commit")

        assert sha1 != sha2
        assert len(sha1) >= 40
        assert len(sha2) >= 40

    @pytest.mark.asyncio
    async def test_commit_returns_hex_string(self):
        """Commit should return valid hex string SHA."""
        service = InMemoryVersionControlService()
        path = "/workspace/test-repo"

        await service.clone_repository("https://github.com/test/repo.git", path)
        sha = await service.commit(path, "Test commit")

        # Should be a valid hex string
        assert isinstance(sha, str)
        try:
            int(sha, 16)  # Should be valid hex
        except ValueError:
            pytest.fail(f"Commit SHA is not valid hex: {sha}")

    @pytest.mark.asyncio
    async def test_push_existing_branch_succeeds(self):
        """Push should succeed for existing branch."""
        service = InMemoryVersionControlService()
        path = "/workspace/test-repo"

        await service.clone_repository("https://github.com/test/repo.git", path)
        # Should not raise
        await service.push(path, "main")

    @pytest.mark.asyncio
    async def test_multiple_repositories_independent_state(self):
        """Multiple repositories should maintain independent state."""
        service = InMemoryVersionControlService()

        # Clone two repositories
        await service.clone_repository("https://github.com/test/repo1.git", "/workspace/repo1")
        await service.clone_repository("https://github.com/test/repo2.git", "/workspace/repo2")

        # Commit to first repo
        sha1 = await service.commit("/workspace/repo1", "Repo 1 commit")

        # Commit to second repo with same message (should get same SHA)
        sha2 = await service.commit("/workspace/repo2", "Repo 1 commit")

        assert sha1 != sha2  # Different commits should have different SHAs even with same message

        # Operations on one shouldn't affect the other
        await service.checkout("/workspace/repo1", "feature/test")

        # Commit to feature branch in repo1
        repo1_feature_sha = await service.commit("/workspace/repo1", "Feature commit")

        # Repo2 should still be on main with no feature commits
        repo2_main_shas = await service.commit("/workspace/repo2", "Feature commit")

        # Same message but different repo states
        assert repo1_feature_sha != repo2_main_shas  # Different branches/repos

    @pytest.mark.asyncio
    async def test_repository_default_branch_is_main(self):
        """Repository default branch should be 'main'."""
        service = InMemoryVersionControlService()

        await service.clone_repository("https://github.com/test/repo.git", "/workspace/test-repo")

        repo = await service.get_repository("/workspace/test-repo")
        assert repo.default_branch == "main"

    @pytest.mark.asyncio
    async def test_repository_metadata_complete(self):
        """Repository metadata should contain all required fields."""
        service = InMemoryVersionControlService()
        url = "https://github.com/test/repo.git"

        await service.clone_repository(url, "/workspace/test-repo")

        repo = await service.get_repository(url)

        assert isinstance(repo, Repository)
        assert hasattr(repo, "id")
        assert hasattr(repo, "name")
        assert hasattr(repo, "url")
        assert hasattr(repo, "default_branch")
        assert repo.url == url
        assert repo.id == "repo"
        assert repo.default_branch == "main"


class TestVersionControlServiceStatus:
    """Test status() method with derived state from actual repository tracking."""

    @pytest.mark.asyncio
    async def test_status_freshly_cloned_repo_returns_clean(self):
        """Fresh clone should return clean status with no staged or unstaged files."""
        service = InMemoryVersionControlService()
        path = "/workspace/test-repo"

        await service.clone_repository("https://github.com/test/repo.git", path)

        status = await service.status(path)

        assert status.is_dirty is False
        assert status.staged_files == ()
        assert status.unstaged_files == ()

    @pytest.mark.asyncio
    async def test_status_with_unstaged_file(self):
        """After seeding a working-tree file, status should show it as unstaged."""
        service = InMemoryVersionControlService()
        path = "/workspace/test-repo"

        await service.clone_repository("https://github.com/test/repo.git", path)
        service.seed_working_tree_file(path, "src/main.py", "print('hello')")

        status = await service.status(path)

        assert status.is_dirty is True
        assert status.staged_files == ()
        assert "src/main.py" in status.unstaged_files

    @pytest.mark.asyncio
    async def test_status_with_staged_files(self):
        """After staging files, status should show them as staged."""
        service = InMemoryVersionControlService()
        path = "/workspace/test-repo"

        await service.clone_repository("https://github.com/test/repo.git", path)
        service.stage_files(path, ["src/main.py", "README.md"])

        status = await service.status(path)

        assert status.is_dirty is True
        assert "src/main.py" in status.staged_files
        assert "README.md" in status.staged_files
        assert status.unstaged_files == ()

    @pytest.mark.asyncio
    async def test_status_with_both_staged_and_unstaged_files(self):
        """Status should properly distinguish between staged and unstaged files."""
        service = InMemoryVersionControlService()
        path = "/workspace/test-repo"

        await service.clone_repository("https://github.com/test/repo.git", path)
        service.seed_working_tree_file(path, "src/main.py", "print('hello')")
        service.seed_working_tree_file(path, "src/helper.py", "def help(): pass")
        service.stage_files(path, ["src/main.py"])

        status = await service.status(path)

        assert status.is_dirty is True
        assert "src/main.py" in status.staged_files
        assert "src/helper.py" in status.unstaged_files
        assert "src/helper.py" not in status.staged_files
        assert "src/main.py" not in status.unstaged_files

    @pytest.mark.asyncio
    async def test_status_no_wildcard_in_staged_files(self):
        """Staged files should contain actual filenames, never wildcards."""
        service = InMemoryVersionControlService()
        path = "/workspace/test-repo"

        await service.clone_repository("https://github.com/test/repo.git", path)
        service.stage_files(path, ["file1.txt", "file2.txt"])

        status = await service.status(path)

        # Should never contain the wildcard
        assert "*" not in status.staged_files
        assert "file1.txt" in status.staged_files
        assert "file2.txt" in status.staged_files

    @pytest.mark.asyncio
    async def test_status_after_commit_clears_staged_files(self):
        """After commit, staged files should be cleared and status should reflect clean state."""
        service = InMemoryVersionControlService()
        path = "/workspace/test-repo"

        await service.clone_repository("https://github.com/test/repo.git", path)
        service.stage_files(path, ["src/main.py"])

        # Verify staged before commit
        status_before = await service.status(path)
        assert status_before.is_dirty is True
        assert "src/main.py" in status_before.staged_files

        # Commit
        await service.commit(path, "Add main.py")

        # After commit, staged files should be cleared
        status_after = await service.status(path)
        assert status_after.is_dirty is False
        assert status_after.staged_files == ()
        assert status_after.unstaged_files == ()

    @pytest.mark.asyncio
    async def test_status_after_commit_with_unstaged_files(self):
        """After commit, unstaged files should remain if not staged."""
        service = InMemoryVersionControlService()
        path = "/workspace/test-repo"

        await service.clone_repository("https://github.com/test/repo.git", path)
        service.seed_working_tree_file(path, "src/main.py", "print('hello')")
        service.seed_working_tree_file(path, "src/helper.py", "def help(): pass")
        service.stage_files(path, ["src/main.py"])

        # Commit staged file
        await service.commit(path, "Add main.py")

        # Check status after commit
        status = await service.status(path)

        # Staged files should be cleared, but unstaged should remain
        assert status.is_dirty is True
        assert status.staged_files == ()
        assert "src/helper.py" in status.unstaged_files

    @pytest.mark.asyncio
    async def test_status_clone_seed_stage_commit_sequence(self):
        """Full sequence: clone -> seed file -> stage -> commit -> status clean."""
        service = InMemoryVersionControlService()
        path = "/workspace/test-repo"

        # Clone
        await service.clone_repository("https://github.com/test/repo.git", path)
        status = await service.status(path)
        assert status.is_dirty is False

        # Seed a file
        service.seed_working_tree_file(path, "src/main.py", "print('hello')")
        status = await service.status(path)
        assert status.is_dirty is True
        assert "src/main.py" in status.unstaged_files

        # Stage the file
        service.stage_files(path, ["src/main.py"])
        status = await service.status(path)
        assert status.is_dirty is True
        assert "src/main.py" in status.staged_files
        assert "src/main.py" not in status.unstaged_files

        # Commit
        await service.commit(path, "Add main.py")
        status = await service.status(path)
        assert status.is_dirty is False
        assert status.staged_files == ()
        assert status.unstaged_files == ()

    @pytest.mark.asyncio
    async def test_status_multiple_repos_independent(self):
        """Status for multiple repos should be independent."""
        service = InMemoryVersionControlService()
        path1 = "/workspace/repo1"
        path2 = "/workspace/repo2"

        await service.clone_repository("https://github.com/test/repo1.git", path1)
        await service.clone_repository("https://github.com/test/repo2.git", path2)

        # Seed file in repo1 only
        service.seed_working_tree_file(path1, "file.txt", "content")

        # Repo1 should be dirty
        status1 = await service.status(path1)
        assert status1.is_dirty is True

        # Repo2 should be clean
        status2 = await service.status(path2)
        assert status2.is_dirty is False

    @pytest.mark.asyncio
    async def test_status_nonexistent_repo_raises_error(self):
        """Status on nonexistent repo should raise RepositoryError."""
        service = InMemoryVersionControlService()

        with pytest.raises(RepositoryError):
            await service.status("/nonexistent/repo")
