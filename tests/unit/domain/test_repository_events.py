"""Unit tests for repository domain events."""

from uuid import uuid4

import pytest

from codetoreum.domain.events.repository_events import (
    BranchCreatedEvent,
    CommitCreatedEvent,
    FilesStagedEvent,
)


class TestFilesStagedEvent:
    """Tests for FilesStagedEvent."""

    def test_initialization_with_all_fields(self):
        """Test event initialization with all fields."""
        event = FilesStagedEvent(
            type="repository.files_staged",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            repository_id="repo-1",
            file_paths=("src/main.py", "tests/test_main.py"),
            project_id="proj-1",
        )

        assert event.type == "repository.files_staged"
        assert event.timestamp == "2025-01-14T10:30:00+00:00"
        assert event.source == "github"
        assert event.repository_id == "repo-1"
        assert event.file_paths == ("src/main.py", "tests/test_main.py")
        assert event.project_id == "proj-1"

    def test_initialization_converts_list_to_tuple(self):
        """Test that list file_paths are converted to tuple for immutability."""
        event = FilesStagedEvent(
            type="repository.files_staged",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            repository_id="repo-1",
            file_paths=["src/file1.py", "src/file2.py"],  # Pass as list
            project_id="proj-1",
        )

        # Should be converted to tuple
        assert isinstance(event.file_paths, tuple)
        assert event.file_paths == ("src/file1.py", "src/file2.py")

    def test_missing_repository_id_raises_validation_error(self):
        """Test that missing repository_id raises ValueError."""
        with pytest.raises(ValueError, match="repository_id is required"):
            FilesStagedEvent(
                type="repository.files_staged",
                timestamp="2025-01-14T10:30:00+00:00",
                source="github",
                repository_id="",
                file_paths=("file.py",),
            )

    def test_empty_file_paths_raises_validation_error(self):
        """Test that empty file_paths raises ValueError."""
        with pytest.raises(ValueError, match="file_paths cannot be empty"):
            FilesStagedEvent(
                type="repository.files_staged",
                timestamp="2025-01-14T10:30:00+00:00",
                source="github",
                repository_id="repo-1",
                file_paths=(),
            )

    def test_to_dict_serialization(self):
        """Test serialization to dictionary converts tuple to list."""
        event = FilesStagedEvent(
            type="repository.files_staged",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            repository_id="repo-1",
            file_paths=("main.py", "utils.py", "config.py"),
            project_id="proj-1",
            event_id="event-123",
        )

        event_dict = event.to_dict()

        assert event_dict["type"] == "repository.files_staged"
        assert event_dict["repository_id"] == "repo-1"
        # Note: file_paths is converted back to list for serialization
        assert event_dict["file_paths"] == ["main.py", "utils.py", "config.py"]
        assert event_dict["project_id"] == "proj-1"

    def test_from_dict_deserialization(self):
        """Test deserialization from dictionary converts list to tuple."""
        event_dict = {
            "type": "repository.files_staged",
            "timestamp": "2025-01-14T10:30:00+00:00",
            "source": "github",
            "repository_id": "repo-2",
            "file_paths": ["file1.py", "file2.py"],  # Passed as list
            "project_id": "proj-2",
            "event_id": "event-456",
        }

        event = FilesStagedEvent.from_dict(event_dict)

        assert event.repository_id == "repo-2"
        assert isinstance(event.file_paths, tuple)
        assert event.file_paths == ("file1.py", "file2.py")
        assert event.project_id == "proj-2"

    def test_from_dict_with_empty_file_paths_defaults_to_empty_tuple(self):
        """Test that empty file_paths in dict results in validation error."""
        event_dict = {
            "type": "repository.files_staged",
            "timestamp": "2025-01-14T10:30:00+00:00",
            "source": "github",
            "repository_id": "repo-1",
            "file_paths": [],
        }

        # Should raise validation error due to empty file_paths
        with pytest.raises(ValueError, match="file_paths cannot be empty"):
            FilesStagedEvent.from_dict(event_dict)

    def test_round_trip_serialization(self):
        """Test round trip serialization."""
        original_event = FilesStagedEvent(
            type="repository.files_staged",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            repository_id="repo-1",
            file_paths=("src/a.py", "src/b.py", "tests/test_a.py"),
            project_id="proj-1",
        )

        event_dict = original_event.to_dict()
        restored_event = FilesStagedEvent.from_dict(event_dict)

        assert restored_event.repository_id == original_event.repository_id
        assert restored_event.file_paths == original_event.file_paths
        assert restored_event.project_id == original_event.project_id

    def test_event_type_property(self):
        """Test event_type property."""
        event = FilesStagedEvent(
            type="repository.files_staged",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            repository_id="repo-1",
            file_paths=("file.py",),
        )

        assert event.event_type == "FilesStagedEvent"


class TestCommitCreatedEvent:
    """Tests for CommitCreatedEvent."""

    def test_initialization_with_all_fields(self):
        """Test event initialization with all fields."""
        event = CommitCreatedEvent(
            type="repository.commit_created",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            repository_id="repo-1",
            commit_sha="abc1234",
            message="Fix bug in main",
            author="orchestrator",
            changed_files=("src/main.py",),
            project_id="proj-1",
        )

        assert event.repository_id == "repo-1"
        assert event.commit_sha == "abc1234"
        assert event.message == "Fix bug in main"
        assert event.author == "orchestrator"
        assert event.changed_files == ("src/main.py",)

    def test_initialization_converts_list_to_tuple(self):
        """Test that list changed_files are converted to tuple."""
        event = CommitCreatedEvent(
            type="repository.commit_created",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            repository_id="repo-1",
            commit_sha="def5678",
            message="Feature: add new feature",
            author="agent",
            changed_files=["file1.py", "file2.py"],
            project_id="proj-1",
        )

        assert isinstance(event.changed_files, tuple)
        assert event.changed_files == ("file1.py", "file2.py")

    def test_missing_repository_id_raises_validation_error(self):
        """Test that missing repository_id raises ValueError."""
        with pytest.raises(ValueError, match="repository_id is required"):
            CommitCreatedEvent(
                type="repository.commit_created",
                timestamp="2025-01-14T10:30:00+00:00",
                source="github",
                repository_id="",
                commit_sha="abc123",
                message="Test",
                author="test",
            )

    def test_missing_commit_sha_raises_validation_error(self):
        """Test that missing commit_sha raises ValueError."""
        with pytest.raises(ValueError, match="commit_sha is required"):
            CommitCreatedEvent(
                type="repository.commit_created",
                timestamp="2025-01-14T10:30:00+00:00",
                source="github",
                repository_id="repo-1",
                commit_sha="",
                message="Test",
                author="test",
            )

    def test_missing_message_raises_validation_error(self):
        """Test that missing message raises ValueError."""
        with pytest.raises(ValueError, match="message is required"):
            CommitCreatedEvent(
                type="repository.commit_created",
                timestamp="2025-01-14T10:30:00+00:00",
                source="github",
                repository_id="repo-1",
                commit_sha="abc123",
                message="",
                author="test",
            )

    def test_missing_author_raises_validation_error(self):
        """Test that missing author raises ValueError."""
        with pytest.raises(ValueError, match="author is required"):
            CommitCreatedEvent(
                type="repository.commit_created",
                timestamp="2025-01-14T10:30:00+00:00",
                source="github",
                repository_id="repo-1",
                commit_sha="abc123",
                message="Test",
                author="",
            )

    def test_to_dict_serialization(self):
        """Test serialization to dictionary."""
        event = CommitCreatedEvent(
            type="repository.commit_created",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            repository_id="repo-1",
            commit_sha="abc1234567890",
            message="Fix critical bug",
            author="orchestrator",
            changed_files=("src/fix.py", "tests/test_fix.py"),
            project_id="proj-1",
            event_id="event-789",
        )

        event_dict = event.to_dict()

        assert event_dict["repository_id"] == "repo-1"
        assert event_dict["commit_sha"] == "abc1234567890"
        assert event_dict["message"] == "Fix critical bug"
        assert event_dict["author"] == "orchestrator"
        assert event_dict["changed_files"] == ["src/fix.py", "tests/test_fix.py"]
        assert event_dict["project_id"] == "proj-1"

    def test_from_dict_deserialization(self):
        """Test deserialization from dictionary."""
        event_dict = {
            "type": "repository.commit_created",
            "timestamp": "2025-01-14T10:30:00+00:00",
            "source": "github",
            "repository_id": "repo-2",
            "commit_sha": "def5678",
            "message": "Add feature X",
            "author": "dev-agent",
            "changed_files": ["feature.py"],
            "project_id": "proj-2",
        }

        event = CommitCreatedEvent.from_dict(event_dict)

        assert event.repository_id == "repo-2"
        assert event.commit_sha == "def5678"
        assert event.message == "Add feature X"
        assert event.author == "dev-agent"
        assert isinstance(event.changed_files, tuple)

    def test_round_trip_serialization(self):
        """Test round trip serialization."""
        original_event = CommitCreatedEvent(
            type="repository.commit_created",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            repository_id="repo-1",
            commit_sha="1234567890abcdef",
            message="Multi-line commit\n\nWith details",
            author="system",
            changed_files=("file1.py", "file2.py", "file3.py"),
            project_id="proj-1",
        )

        event_dict = original_event.to_dict()
        restored_event = CommitCreatedEvent.from_dict(event_dict)

        assert restored_event.repository_id == original_event.repository_id
        assert restored_event.commit_sha == original_event.commit_sha
        assert restored_event.message == original_event.message
        assert restored_event.author == original_event.author
        assert restored_event.changed_files == original_event.changed_files

    def test_empty_changed_files_allowed(self):
        """Test that empty changed_files tuple is allowed."""
        event = CommitCreatedEvent(
            type="repository.commit_created",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            repository_id="repo-1",
            commit_sha="abc123",
            message="Empty commit",
            author="test",
            changed_files=(),
        )

        assert event.changed_files == ()


class TestBranchCreatedEvent:
    """Tests for BranchCreatedEvent."""

    def test_initialization_with_all_fields(self):
        """Test event initialization with all fields."""
        event = BranchCreatedEvent(
            type="repository.branch_created",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            repository_id="repo-1",
            branch_name="fix/issue-123",
            base_commit="abc1234",
            project_id="proj-1",
        )

        assert event.repository_id == "repo-1"
        assert event.branch_name == "fix/issue-123"
        assert event.base_commit == "abc1234"
        assert event.project_id == "proj-1"

    def test_missing_repository_id_raises_validation_error(self):
        """Test that missing repository_id raises ValueError."""
        with pytest.raises(ValueError, match="repository_id is required"):
            BranchCreatedEvent(
                type="repository.branch_created",
                timestamp="2025-01-14T10:30:00+00:00",
                source="github",
                repository_id="",
                branch_name="main",
                base_commit="abc123",
            )

    def test_missing_branch_name_raises_validation_error(self):
        """Test that missing branch_name raises ValueError."""
        with pytest.raises(ValueError, match="branch_name is required"):
            BranchCreatedEvent(
                type="repository.branch_created",
                timestamp="2025-01-14T10:30:00+00:00",
                source="github",
                repository_id="repo-1",
                branch_name="",
                base_commit="abc123",
            )

    def test_missing_base_commit_raises_validation_error(self):
        """Test that missing base_commit raises ValueError."""
        with pytest.raises(ValueError, match="base_commit is required"):
            BranchCreatedEvent(
                type="repository.branch_created",
                timestamp="2025-01-14T10:30:00+00:00",
                source="github",
                repository_id="repo-1",
                branch_name="feature/new",
                base_commit="",
            )

    def test_to_dict_serialization(self):
        """Test serialization to dictionary."""
        event = BranchCreatedEvent(
            type="repository.branch_created",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            repository_id="repo-1",
            branch_name="feature/user-auth",
            base_commit="main-sha",
            project_id="proj-1",
            event_id="event-999",
        )

        event_dict = event.to_dict()

        assert event_dict["type"] == "repository.branch_created"
        assert event_dict["repository_id"] == "repo-1"
        assert event_dict["branch_name"] == "feature/user-auth"
        assert event_dict["base_commit"] == "main-sha"
        assert event_dict["project_id"] == "proj-1"

    def test_from_dict_deserialization(self):
        """Test deserialization from dictionary."""
        event_dict = {
            "type": "repository.branch_created",
            "timestamp": "2025-01-14T10:30:00+00:00",
            "source": "github",
            "repository_id": "repo-2",
            "branch_name": "bugfix/issue-456",
            "base_commit": "develop",
            "project_id": "proj-2",
        }

        event = BranchCreatedEvent.from_dict(event_dict)

        assert event.repository_id == "repo-2"
        assert event.branch_name == "bugfix/issue-456"
        assert event.base_commit == "develop"

    def test_round_trip_serialization(self):
        """Test round trip serialization."""
        original_event = BranchCreatedEvent(
            type="repository.branch_created",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            repository_id="repo-1",
            branch_name="release/v1.0.0",
            base_commit="abc1234567890def",
            project_id="proj-1",
        )

        event_dict = original_event.to_dict()
        restored_event = BranchCreatedEvent.from_dict(event_dict)

        assert restored_event.repository_id == original_event.repository_id
        assert restored_event.branch_name == original_event.branch_name
        assert restored_event.base_commit == original_event.base_commit

    def test_event_type_property(self):
        """Test event_type property."""
        event = BranchCreatedEvent(
            type="repository.branch_created",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            repository_id="repo-1",
            branch_name="main",
            base_commit="abc123",
        )

        assert event.event_type == "BranchCreatedEvent"
