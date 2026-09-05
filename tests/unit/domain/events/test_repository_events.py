"""Unit tests for repository-related domain events."""

import pytest

from codetoreum.domain.events import (
    BranchCreatedEvent,
    CommitCreatedEvent,
    FilesStagedEvent,
    now_iso,
)

# For immutability tests (repository events are frozen dataclasses)
try:
    from dataclasses import FrozenInstanceError
except ImportError:
    # Fallback for older Python versions
    FrozenInstanceError = AttributeError  # type: ignore


class TestFilesStagedEvent:
    """Test FilesStagedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid files staged event."""
        event = FilesStagedEvent(
            type="repository.files_staged",
            timestamp=now_iso(),
            source="mock",
            repository_id="repo-1",
            file_paths=("src/main.py", "tests/test_main.py"),
            project_id="proj-1",
        )

        assert event.repository_id == "repo-1"
        assert event.file_paths == ("src/main.py", "tests/test_main.py")
        assert event.project_id == "proj-1"

    def test_file_paths_converted_to_tuple(self):
        """Test that list file_paths are converted to tuples for immutability."""
        event = FilesStagedEvent(
            type="repository.files_staged",
            timestamp=now_iso(),
            source="mock",
            repository_id="repo-1",
            file_paths=["file1.py", "file2.py"],  # Pass list
            project_id="proj-1",
        )

        # Verify it's now a tuple
        assert isinstance(event.file_paths, tuple)
        assert event.file_paths == ("file1.py", "file2.py")

    def test_event_is_frozen(self):
        """Test that event is immutable after creation."""
        event = FilesStagedEvent(
            type="repository.files_staged",
            timestamp=now_iso(),
            source="mock",
            repository_id="repo-1",
            file_paths=("file.py",),
            project_id="proj-1",
        )

        with pytest.raises(FrozenInstanceError):
            event.repository_id = "repo-2"

    def test_missing_repository_id_raises_error(self):
        """Test that missing repository_id raises ValueError."""
        with pytest.raises(ValueError, match="repository_id is required"):
            FilesStagedEvent(
                type="repository.files_staged",
                timestamp=now_iso(),
                source="mock",
                repository_id="",
                file_paths=("file.py",),
                project_id="proj-1",
            )

    def test_empty_file_paths_raises_error(self):
        """Test that empty file_paths raises ValueError."""
        with pytest.raises(ValueError, match="file_paths cannot be empty"):
            FilesStagedEvent(
                type="repository.files_staged",
                timestamp=now_iso(),
                source="mock",
                repository_id="repo-1",
                file_paths=(),
                project_id="proj-1",
            )

    def test_single_file_staged(self):
        """Test staging a single file."""
        event = FilesStagedEvent(
            type="repository.files_staged",
            timestamp=now_iso(),
            source="mock",
            repository_id="repo-1",
            file_paths=("README.md",),
            project_id="proj-1",
        )

        assert len(event.file_paths) == 1
        assert event.file_paths[0] == "README.md"

    def test_multiple_files_staged(self):
        """Test staging multiple files."""
        files = ("src/main.py", "src/utils.py", "tests/test_main.py", "README.md")
        event = FilesStagedEvent(
            type="repository.files_staged",
            timestamp=now_iso(),
            source="mock",
            repository_id="repo-1",
            file_paths=files,
            project_id="proj-1",
        )

        assert len(event.file_paths) == 4
        assert event.file_paths == files

    def test_to_dict_conversion(self):
        """Test serialization to dictionary."""
        event = FilesStagedEvent(
            type="repository.files_staged",
            timestamp=now_iso(),
            source="mock",
            repository_id="repo-1",
            file_paths=("file1.py", "file2.py"),
            project_id="proj-1",
        )

        data = event.to_dict()

        assert data["repository_id"] == "repo-1"
        assert data["file_paths"] == ["file1.py", "file2.py"]  # Converted to list
        assert data["project_id"] == "proj-1"

    def test_from_dict_conversion(self):
        """Test deserialization from dictionary."""
        data = {
            "type": "repository.files_staged",
            "timestamp": now_iso(),
            "source": "mock",
            "repository_id": "repo-2",
            "file_paths": ["src/app.py", "src/config.py"],
            "project_id": "proj-2",
        }

        event = FilesStagedEvent.from_dict(data)

        assert event.repository_id == "repo-2"
        assert isinstance(event.file_paths, tuple)
        assert event.file_paths == ("src/app.py", "src/config.py")


class TestCommitCreatedEvent:
    """Test CommitCreatedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid commit created event."""
        event = CommitCreatedEvent(
            type="repository.commit_created",
            timestamp=now_iso(),
            source="mock",
            repository_id="repo-1",
            commit_sha="abc1234def5678",
            message="Fix critical bug in main",
            author="orchestrator",
            changed_files=("src/main.py",),
            project_id="proj-1",
        )

        assert event.repository_id == "repo-1"
        assert event.commit_sha == "abc1234def5678"
        assert event.message == "Fix critical bug in main"
        assert event.author == "orchestrator"
        assert event.changed_files == ("src/main.py",)

    def test_changed_files_converted_to_tuple(self):
        """Test that list changed_files are converted to tuples for immutability."""
        event = CommitCreatedEvent(
            type="repository.commit_created",
            timestamp=now_iso(),
            source="mock",
            repository_id="repo-1",
            commit_sha="abc1234",
            message="Update tests",
            author="orchestrator",
            changed_files=["test1.py", "test2.py"],  # Pass list
            project_id="proj-1",
        )

        # Verify it's now a tuple
        assert isinstance(event.changed_files, tuple)
        assert event.changed_files == ("test1.py", "test2.py")

    def test_event_is_frozen(self):
        """Test that event is immutable after creation."""
        event = CommitCreatedEvent(
            type="repository.commit_created",
            timestamp=now_iso(),
            source="mock",
            repository_id="repo-1",
            commit_sha="abc1234",
            message="Test message",
            author="orchestrator",
            changed_files=("file.py",),
            project_id="proj-1",
        )

        with pytest.raises(FrozenInstanceError):
            event.commit_sha = "def5678"

    def test_missing_repository_id_raises_error(self):
        """Test that missing repository_id raises ValueError."""
        with pytest.raises(ValueError, match="repository_id is required"):
            CommitCreatedEvent(
                type="repository.commit_created",
                timestamp=now_iso(),
                source="mock",
                repository_id="",
                commit_sha="abc1234",
                message="Test",
                author="orchestrator",
                changed_files=("file.py",),
                project_id="proj-1",
            )

    def test_missing_commit_sha_raises_error(self):
        """Test that missing commit_sha raises ValueError."""
        with pytest.raises(ValueError, match="commit_sha is required"):
            CommitCreatedEvent(
                type="repository.commit_created",
                timestamp=now_iso(),
                source="mock",
                repository_id="repo-1",
                commit_sha="",
                message="Test",
                author="orchestrator",
                changed_files=("file.py",),
                project_id="proj-1",
            )

    def test_missing_message_raises_error(self):
        """Test that missing message raises ValueError."""
        with pytest.raises(ValueError, match="message is required"):
            CommitCreatedEvent(
                type="repository.commit_created",
                timestamp=now_iso(),
                source="mock",
                repository_id="repo-1",
                commit_sha="abc1234",
                message="",
                author="orchestrator",
                changed_files=("file.py",),
                project_id="proj-1",
            )

    def test_missing_author_raises_error(self):
        """Test that missing author raises ValueError."""
        with pytest.raises(ValueError, match="author is required"):
            CommitCreatedEvent(
                type="repository.commit_created",
                timestamp=now_iso(),
                source="mock",
                repository_id="repo-1",
                commit_sha="abc1234",
                message="Test message",
                author="",
                changed_files=("file.py",),
                project_id="proj-1",
            )

    def test_commit_with_no_changed_files(self):
        """Test commit with empty changed_files."""
        event = CommitCreatedEvent(
            type="repository.commit_created",
            timestamp=now_iso(),
            source="mock",
            repository_id="repo-1",
            commit_sha="abc1234",
            message="Empty commit",
            author="orchestrator",
            changed_files=(),
            project_id="proj-1",
        )

        assert event.changed_files == ()

    def test_commit_with_multiple_changed_files(self):
        """Test commit with multiple changed files."""
        files = ("src/main.py", "src/utils.py", "tests/test_main.py", "README.md")
        event = CommitCreatedEvent(
            type="repository.commit_created",
            timestamp=now_iso(),
            source="mock",
            repository_id="repo-1",
            commit_sha="abc1234",
            message="Major refactoring",
            author="orchestrator",
            changed_files=files,
            project_id="proj-1",
        )

        assert len(event.changed_files) == 4
        assert event.changed_files == files

    def test_to_dict_conversion(self):
        """Test serialization to dictionary."""
        event = CommitCreatedEvent(
            type="repository.commit_created",
            timestamp=now_iso(),
            source="mock",
            repository_id="repo-1",
            commit_sha="abc1234",
            message="Fix bug",
            author="orchestrator",
            changed_files=("main.py",),
            project_id="proj-1",
        )

        data = event.to_dict()

        assert data["repository_id"] == "repo-1"
        assert data["commit_sha"] == "abc1234"
        assert data["message"] == "Fix bug"
        assert data["author"] == "orchestrator"
        assert data["changed_files"] == ["main.py"]  # Converted to list

    def test_from_dict_conversion(self):
        """Test deserialization from dictionary."""
        data = {
            "type": "repository.commit_created",
            "timestamp": now_iso(),
            "source": "mock",
            "repository_id": "repo-2",
            "commit_sha": "def5678",
            "message": "Update documentation",
            "author": "orchestrator",
            "changed_files": ["docs/README.md", "docs/API.md"],
            "project_id": "proj-2",
        }

        event = CommitCreatedEvent.from_dict(data)

        assert event.commit_sha == "def5678"
        assert event.message == "Update documentation"
        assert isinstance(event.changed_files, tuple)
        assert event.changed_files == ("docs/README.md", "docs/API.md")


class TestBranchCreatedEvent:
    """Test BranchCreatedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid branch created event."""
        event = BranchCreatedEvent(
            type="repository.branch_created",
            timestamp=now_iso(),
            source="mock",
            repository_id="repo-1",
            branch_name="feature/new-auth",
            base_commit="abc1234",
            project_id="proj-1",
        )

        assert event.repository_id == "repo-1"
        assert event.branch_name == "feature/new-auth"
        assert event.base_commit == "abc1234"
        assert event.project_id == "proj-1"

    def test_event_is_frozen(self):
        """Test that event is immutable after creation."""
        event = BranchCreatedEvent(
            type="repository.branch_created",
            timestamp=now_iso(),
            source="mock",
            repository_id="repo-1",
            branch_name="feature/test",
            base_commit="abc1234",
            project_id="proj-1",
        )

        with pytest.raises(FrozenInstanceError):
            event.branch_name = "feature/other"

    def test_missing_repository_id_raises_error(self):
        """Test that missing repository_id raises ValueError."""
        with pytest.raises(ValueError, match="repository_id is required"):
            BranchCreatedEvent(
                type="repository.branch_created",
                timestamp=now_iso(),
                source="mock",
                repository_id="",
                branch_name="feature/test",
                base_commit="abc1234",
                project_id="proj-1",
            )

    def test_missing_branch_name_raises_error(self):
        """Test that missing branch_name raises ValueError."""
        with pytest.raises(ValueError, match="branch_name is required"):
            BranchCreatedEvent(
                type="repository.branch_created",
                timestamp=now_iso(),
                source="mock",
                repository_id="repo-1",
                branch_name="",
                base_commit="abc1234",
                project_id="proj-1",
            )

    def test_missing_base_commit_raises_error(self):
        """Test that missing base_commit raises ValueError."""
        with pytest.raises(ValueError, match="base_commit is required"):
            BranchCreatedEvent(
                type="repository.branch_created",
                timestamp=now_iso(),
                source="mock",
                repository_id="repo-1",
                branch_name="feature/test",
                base_commit="",
                project_id="proj-1",
            )

    def test_feature_branch(self):
        """Test creating a feature branch."""
        event = BranchCreatedEvent(
            type="repository.branch_created",
            timestamp=now_iso(),
            source="mock",
            repository_id="repo-1",
            branch_name="feature/user-auth",
            base_commit="main-commit-hash",
            project_id="proj-1",
        )

        assert "feature/" in event.branch_name

    def test_bugfix_branch(self):
        """Test creating a bugfix branch."""
        event = BranchCreatedEvent(
            type="repository.branch_created",
            timestamp=now_iso(),
            source="mock",
            repository_id="repo-1",
            branch_name="bugfix/critical-issue",
            base_commit="main-commit-hash",
            project_id="proj-1",
        )

        assert "bugfix/" in event.branch_name

    def test_to_dict_conversion(self):
        """Test serialization to dictionary."""
        event = BranchCreatedEvent(
            type="repository.branch_created",
            timestamp=now_iso(),
            source="mock",
            repository_id="repo-1",
            branch_name="feature/test",
            base_commit="abc1234",
            project_id="proj-1",
        )

        data = event.to_dict()

        assert data["repository_id"] == "repo-1"
        assert data["branch_name"] == "feature/test"
        assert data["base_commit"] == "abc1234"
        assert data["project_id"] == "proj-1"

    def test_from_dict_conversion(self):
        """Test deserialization from dictionary."""
        data = {
            "type": "repository.branch_created",
            "timestamp": now_iso(),
            "source": "mock",
            "repository_id": "repo-2",
            "branch_name": "release/v2.0",
            "base_commit": "def5678",
            "project_id": "proj-2",
        }

        event = BranchCreatedEvent.from_dict(data)

        assert event.repository_id == "repo-2"
        assert event.branch_name == "release/v2.0"
        assert event.base_commit == "def5678"
