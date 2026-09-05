"""Unit tests for container execution domain events."""

import pytest

from codetoreum.domain.events import ContainerExecutionCompletedEvent, now_iso

# For immutability tests (container events are frozen dataclasses)
try:
    from dataclasses import FrozenInstanceError
except ImportError:
    # Fallback for older Python versions
    FrozenInstanceError = AttributeError  # type: ignore


class TestContainerExecutionCompletedEvent:
    """Test ContainerExecutionCompletedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid container execution completed event."""
        event = ContainerExecutionCompletedEvent(
            type="container.execution_completed",
            timestamp=now_iso(),
            source="fake_container",
            container_id="container-123",
            command="pytest tests/",
            exit_code=0,
            output_files=("test_results.json", "coverage.xml"),
            project_id="proj-1",
        )

        assert event.container_id == "container-123"
        assert event.command == "pytest tests/"
        assert event.exit_code == 0
        assert event.output_files == ("test_results.json", "coverage.xml")
        assert event.project_id == "proj-1"

    def test_output_files_converted_to_tuple(self):
        """Test that list output_files are converted to tuples for immutability."""
        event = ContainerExecutionCompletedEvent(
            type="container.execution_completed",
            timestamp=now_iso(),
            source="fake_container",
            container_id="container-456",
            command="npm test",
            exit_code=0,
            output_files=["output.txt", "logs.txt"],  # Pass list
            project_id="proj-1",
        )

        # Verify it's now a tuple
        assert isinstance(event.output_files, tuple)
        assert event.output_files == ("output.txt", "logs.txt")

    def test_event_is_frozen(self):
        """Test that event is immutable after creation."""
        event = ContainerExecutionCompletedEvent(
            type="container.execution_completed",
            timestamp=now_iso(),
            source="fake_container",
            container_id="container-789",
            command="make build",
            exit_code=0,
            output_files=("artifact.zip",),
            project_id="proj-1",
        )

        # Attempt to modify should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            event.container_id = "new-container-id"

    def test_missing_container_id_raises_error(self):
        """Test that missing container_id raises ValueError."""
        with pytest.raises(ValueError, match="container_id is required"):
            ContainerExecutionCompletedEvent(
                type="container.execution_completed",
                timestamp=now_iso(),
                source="fake_container",
                container_id="",  # Empty
                command="pytest",
                exit_code=0,
                output_files=(),
                project_id="proj-1",
            )

    def test_missing_command_raises_error(self):
        """Test that missing command raises ValueError."""
        with pytest.raises(ValueError, match="command is required"):
            ContainerExecutionCompletedEvent(
                type="container.execution_completed",
                timestamp=now_iso(),
                source="fake_container",
                container_id="container-123",
                command="",  # Empty
                exit_code=0,
                output_files=(),
                project_id="proj-1",
            )

    def test_negative_exit_code_raises_error(self):
        """Test that negative exit code raises ValueError."""
        with pytest.raises(ValueError, match="exit_code must be >= 0"):
            ContainerExecutionCompletedEvent(
                type="container.execution_completed",
                timestamp=now_iso(),
                source="fake_container",
                container_id="container-123",
                command="pytest",
                exit_code=-1,  # Negative
                output_files=(),
                project_id="proj-1",
            )

    def test_empty_output_files_is_valid(self):
        """Test that empty output_files is valid."""
        event = ContainerExecutionCompletedEvent(
            type="container.execution_completed",
            timestamp=now_iso(),
            source="fake_container",
            container_id="container-123",
            command="echo 'done'",
            exit_code=0,
            output_files=(),
            project_id="proj-1",
        )

        assert event.output_files == ()

    def test_to_dict_conversion(self):
        """Test serialization to dictionary."""
        event = ContainerExecutionCompletedEvent(
            type="container.execution_completed",
            timestamp=now_iso(),
            source="fake_container",
            container_id="container-123",
            command="pytest tests/",
            exit_code=0,
            output_files=("results.json",),
            project_id="proj-1",
        )

        data = event.to_dict()

        assert data["container_id"] == "container-123"
        assert data["command"] == "pytest tests/"
        assert data["exit_code"] == 0
        assert data["output_files"] == ["results.json"]  # Converted to list
        assert data["project_id"] == "proj-1"
        assert data["type"] == "container.execution_completed"
        assert data["source"] == "fake_container"

    def test_from_dict_conversion(self):
        """Test deserialization from dictionary."""
        data = {
            "type": "container.execution_completed",
            "timestamp": now_iso(),
            "source": "fake_container",
            "container_id": "container-123",
            "command": "docker build",
            "exit_code": 0,
            "output_files": ["Dockerfile", "image.tar"],
            "project_id": "proj-1",
        }

        event = ContainerExecutionCompletedEvent.from_dict(data)

        assert event.container_id == "container-123"
        assert event.command == "docker build"
        assert event.exit_code == 0
        assert isinstance(event.output_files, tuple)
        assert event.output_files == ("Dockerfile", "image.tar")

    def test_nonzero_exit_code_is_valid(self):
        """Test that non-zero exit codes are valid (for failed commands)."""
        event = ContainerExecutionCompletedEvent(
            type="container.execution_completed",
            timestamp=now_iso(),
            source="fake_container",
            container_id="container-fail",
            command="failing_command",
            exit_code=1,
            output_files=("error.log",),
            project_id="proj-1",
        )

        assert event.exit_code == 1
        assert event.output_files == ("error.log",)

    def test_correlation_id_preservation(self):
        """Test that correlation_id is preserved in event."""
        import uuid

        correlation_id = str(uuid.uuid4())
        event = ContainerExecutionCompletedEvent(
            type="container.execution_completed",
            timestamp=now_iso(),
            source="fake_container",
            correlation_id=correlation_id,
            container_id="container-123",
            command="test",
            exit_code=0,
            output_files=(),
            project_id="proj-1",
        )

        assert event.correlation_id == correlation_id

    def test_output_files_immutability_in_place(self):
        """Test that output_files tuple cannot be modified in place."""
        event = ContainerExecutionCompletedEvent(
            type="container.execution_completed",
            timestamp=now_iso(),
            source="fake_container",
            container_id="container-123",
            command="test",
            exit_code=0,
            output_files=("file1.txt",),
            project_id="proj-1",
        )

        # Tuples don't have append(), so this would raise AttributeError
        with pytest.raises(AttributeError):
            event.output_files.append("file2.txt")

    def test_multiple_output_files(self):
        """Test handling of multiple output files."""
        files = ("results.json", "logs.txt", "artifacts.zip", "report.html")
        event = ContainerExecutionCompletedEvent(
            type="container.execution_completed",
            timestamp=now_iso(),
            source="fake_container",
            container_id="container-123",
            command="build_all",
            exit_code=0,
            output_files=files,
            project_id="proj-1",
        )

        assert len(event.output_files) == 4
        assert event.output_files == files
