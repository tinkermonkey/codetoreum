"""Unit tests for container domain events."""

import pytest

from codetoreum.domain.events.container_events import ContainerExecutionCompletedEvent


class TestContainerExecutionCompletedEvent:
    """Tests for ContainerExecutionCompletedEvent."""

    def test_initialization_with_all_fields(self):
        """Test event initialization with all fields."""
        event = ContainerExecutionCompletedEvent(
            type="container.execution_completed",
            timestamp="2025-01-14T10:30:00+00:00",
            source="docker",
            container_id="container-123",
            command="pytest tests/",
            exit_code=0,
            output_files=("test_results.json", "coverage.xml"),
            project_id="proj-1",
        )

        assert event.type == "container.execution_completed"
        assert event.timestamp == "2025-01-14T10:30:00+00:00"
        assert event.source == "docker"
        assert event.container_id == "container-123"
        assert event.command == "pytest tests/"
        assert event.exit_code == 0
        assert event.output_files == ("test_results.json", "coverage.xml")
        assert event.project_id == "proj-1"

    def test_initialization_with_minimal_fields(self):
        """Test event initialization with minimal required fields."""
        event = ContainerExecutionCompletedEvent(
            type="container.execution_completed",
            timestamp="2025-01-14T10:30:00+00:00",
            source="docker",
            container_id="container-456",
            command="echo hello",
            exit_code=0,
        )

        assert event.container_id == "container-456"
        assert event.command == "echo hello"
        assert event.exit_code == 0
        assert event.output_files == ()
        assert event.project_id is None

    def test_initialization_converts_list_to_tuple(self):
        """Test that list output_files are converted to tuple."""
        event = ContainerExecutionCompletedEvent(
            type="container.execution_completed",
            timestamp="2025-01-14T10:30:00+00:00",
            source="docker",
            container_id="container-1",
            command="ls",
            exit_code=0,
            output_files=["file1.txt", "file2.txt"],
            project_id="proj-1",
        )

        assert isinstance(event.output_files, tuple)
        assert event.output_files == ("file1.txt", "file2.txt")

    def test_missing_container_id_raises_validation_error(self):
        """Test that missing container_id raises ValueError."""
        with pytest.raises(ValueError, match="container_id is required"):
            ContainerExecutionCompletedEvent(
                type="container.execution_completed",
                timestamp="2025-01-14T10:30:00+00:00",
                source="docker",
                container_id="",
                command="test",
                exit_code=0,
            )

    def test_missing_command_raises_validation_error(self):
        """Test that missing command raises ValueError."""
        with pytest.raises(ValueError, match="command is required"):
            ContainerExecutionCompletedEvent(
                type="container.execution_completed",
                timestamp="2025-01-14T10:30:00+00:00",
                source="docker",
                container_id="container-1",
                command="",
                exit_code=0,
            )

    def test_negative_exit_code_raises_validation_error(self):
        """Test that negative exit_code raises ValueError."""
        with pytest.raises(ValueError, match="exit_code must be >= 0"):
            ContainerExecutionCompletedEvent(
                type="container.execution_completed",
                timestamp="2025-01-14T10:30:00+00:00",
                source="docker",
                container_id="container-1",
                command="test",
                exit_code=-1,
            )

    def test_zero_exit_code_for_success(self):
        """Test that exit_code=0 represents success."""
        event = ContainerExecutionCompletedEvent(
            type="container.execution_completed",
            timestamp="2025-01-14T10:30:00+00:00",
            source="docker",
            container_id="container-1",
            command="pytest",
            exit_code=0,
        )

        assert event.exit_code == 0

    def test_nonzero_exit_code_for_failure(self):
        """Test that non-zero exit_code represents failure."""
        event = ContainerExecutionCompletedEvent(
            type="container.execution_completed",
            timestamp="2025-01-14T10:30:00+00:00",
            source="docker",
            container_id="container-1",
            command="failing_command",
            exit_code=127,
        )

        assert event.exit_code == 127

    def test_to_dict_serialization(self):
        """Test serialization to dictionary."""
        event = ContainerExecutionCompletedEvent(
            type="container.execution_completed",
            timestamp="2025-01-14T10:30:00+00:00",
            source="docker",
            container_id="container-abc",
            command="python -m pytest",
            exit_code=1,
            output_files=("results.json", "logs.txt", "coverage.xml"),
            project_id="proj-1",
            event_id="event-123",
        )

        event_dict = event.to_dict()

        assert event_dict["type"] == "container.execution_completed"
        assert event_dict["timestamp"] == "2025-01-14T10:30:00+00:00"
        assert event_dict["source"] == "docker"
        assert event_dict["container_id"] == "container-abc"
        assert event_dict["command"] == "python -m pytest"
        assert event_dict["exit_code"] == 1
        # Note: output_files is converted back to list for serialization
        assert event_dict["output_files"] == ["results.json", "logs.txt", "coverage.xml"]
        assert event_dict["project_id"] == "proj-1"
        assert event_dict["event_id"] == "event-123"

    def test_from_dict_deserialization(self):
        """Test deserialization from dictionary."""
        event_dict = {
            "type": "container.execution_completed",
            "timestamp": "2025-01-14T10:30:00+00:00",
            "source": "docker",
            "container_id": "container-xyz",
            "command": "npm test",
            "exit_code=": 0,
            "output_files": ["output.json"],
            "project_id": "proj-2",
            "event_id": "event-456",
            "correlation_id": "corr-123",
        }

        event = ContainerExecutionCompletedEvent.from_dict(event_dict)

        assert event.container_id == "container-xyz"
        assert event.command == "npm test"
        assert isinstance(event.output_files, tuple)
        assert event.output_files == ("output.json",)

    def test_from_dict_with_missing_optional_fields(self):
        """Test deserialization with missing optional fields."""
        event_dict = {
            "type": "container.execution_completed",
            "timestamp": "2025-01-14T10:30:00+00:00",
            "source": "docker",
            "container_id": "container-1",
            "command": "ls",
            "exit_code": 0,
        }

        event = ContainerExecutionCompletedEvent.from_dict(event_dict)

        assert event.output_files == ()
        assert event.project_id is None
        assert event.event_id is not None

    def test_from_dict_with_empty_output_files(self):
        """Test deserialization with empty output_files list."""
        event_dict = {
            "type": "container.execution_completed",
            "timestamp": "2025-01-14T10:30:00+00:00",
            "source": "docker",
            "container_id": "container-1",
            "command": "echo",
            "exit_code": 0,
            "output_files": [],
        }

        event = ContainerExecutionCompletedEvent.from_dict(event_dict)

        assert event.output_files == ()

    def test_round_trip_serialization(self):
        """Test that serialization and deserialization are reversible."""
        original_event = ContainerExecutionCompletedEvent(
            type="container.execution_completed",
            timestamp="2025-01-14T10:30:00+00:00",
            source="docker",
            container_id="container-test",
            command="python -m pytest --cov",
            exit_code=0,
            output_files=("coverage_report.html", "test_output.xml"),
            project_id="proj-1",
        )

        # Serialize and deserialize
        event_dict = original_event.to_dict()
        restored_event = ContainerExecutionCompletedEvent.from_dict(event_dict)

        # Compare key attributes
        assert restored_event.container_id == original_event.container_id
        assert restored_event.command == original_event.command
        assert restored_event.exit_code == original_event.exit_code
        assert restored_event.output_files == original_event.output_files
        assert restored_event.project_id == original_event.project_id

    def test_immutability_prevents_modification(self):
        """Test that event is frozen and cannot be modified."""
        event = ContainerExecutionCompletedEvent(
            type="container.execution_completed",
            timestamp="2025-01-14T10:30:00+00:00",
            source="docker",
            container_id="container-1",
            command="test",
            exit_code=0,
        )

        # Attempting to modify should raise FrozenInstanceError
        with pytest.raises(Exception):  # FrozenInstanceError
            event.exit_code = 1

    def test_event_type_property(self):
        """Test that event_type property returns class name."""
        event = ContainerExecutionCompletedEvent(
            type="container.execution_completed",
            timestamp="2025-01-14T10:30:00+00:00",
            source="docker",
            container_id="container-1",
            command="test",
            exit_code=0,
        )

        assert event.event_type == "ContainerExecutionCompletedEvent"

    def test_multiple_output_files(self):
        """Test event with multiple output files."""
        output_files = (
            "stdout.log",
            "stderr.log",
            "metrics.json",
            "coverage.xml",
            "report.html",
        )

        event = ContainerExecutionCompletedEvent(
            type="container.execution_completed",
            timestamp="2025-01-14T10:30:00+00:00",
            source="docker",
            container_id="container-1",
            command="complex_test_suite",
            exit_code=0,
            output_files=output_files,
        )

        assert len(event.output_files) == 5
        assert event.output_files == output_files

    def test_correlation_id_for_tracing(self):
        """Test correlation_id for event tracing."""
        correlation_id = "trace-789"

        event = ContainerExecutionCompletedEvent(
            type="container.execution_completed",
            timestamp="2025-01-14T10:30:00+00:00",
            source="docker",
            container_id="container-1",
            command="test",
            exit_code=0,
            correlation_id=correlation_id,
        )

        assert event.correlation_id == correlation_id
