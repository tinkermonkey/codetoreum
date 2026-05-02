"""Unit tests for repair cycle logging infrastructure."""

import pytest
from datetime import datetime, UTC
from codetoreum.infrastructure.repair_cycle_logging import (
    RepairCycleLogContext,
    RepairCycleLogLevel,
    RepairCycleLogger,
)


class TestRepairCycleLogLevel:
    """Test RepairCycleLogLevel enum."""

    def test_debug_level(self) -> None:
        """Test DEBUG log level."""
        assert RepairCycleLogLevel.DEBUG.value == "DEBUG"

    def test_info_level(self) -> None:
        """Test INFO log level."""
        assert RepairCycleLogLevel.INFO.value == "INFO"

    def test_warning_level(self) -> None:
        """Test WARNING log level."""
        assert RepairCycleLogLevel.WARNING.value == "WARNING"

    def test_error_level(self) -> None:
        """Test ERROR log level."""
        assert RepairCycleLogLevel.ERROR.value == "ERROR"

    def test_critical_level(self) -> None:
        """Test CRITICAL log level."""
        assert RepairCycleLogLevel.CRITICAL.value == "CRITICAL"

    def test_all_levels(self) -> None:
        """Test that all expected levels exist."""
        levels = {l.value for l in RepairCycleLogLevel}
        assert levels == {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class TestRepairCycleLogContext:
    """Test RepairCycleLogContext."""

    def test_create_valid_context(self) -> None:
        """Test creating a valid log context."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
            test_type="UNIT",
            iteration=1,
        )

        assert context.workflow_run_id == "run-123"
        assert context.stage_name == "test_execution"
        assert context.agent_name == "TestAgent"
        assert context.test_type == "UNIT"
        assert context.iteration == 1

    def test_context_with_optional_fields(self) -> None:
        """Test context with all optional fields."""
        now = datetime.now(UTC)
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
            test_type="INTEGRATION",
            iteration=2,
            file_path="/path/to/file.py",
            correlation_id="corr-456",
            user_id="user-789",
            project_id="proj-000",
            timestamp=now,
        )

        assert context.file_path == "/path/to/file.py"
        assert context.correlation_id == "corr-456"
        assert context.user_id == "user-789"
        assert context.project_id == "proj-000"
        assert context.timestamp == now

    def test_context_timestamp_default(self) -> None:
        """Test that timestamp is set automatically if not provided."""
        before = datetime.now(UTC)
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test",
            agent_name="Agent",
        )
        after = datetime.now(UTC)

        assert context.timestamp is not None
        assert before <= context.timestamp <= after

    def test_context_to_dict(self) -> None:
        """Test converting context to dictionary."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
            test_type="UNIT",
        )

        context_dict = context.to_dict()

        assert context_dict["workflow_run_id"] == "run-123"
        assert context_dict["stage_name"] == "test_execution"
        assert context_dict["agent_name"] == "TestAgent"
        assert context_dict["test_type"] == "UNIT"
        assert "timestamp" in context_dict

    def test_context_to_dict_excludes_none(self) -> None:
        """Test that to_dict excludes None values."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test",
            agent_name="Agent",
            test_type=None,  # None value
            file_path=None,  # None value
        )

        context_dict = context.to_dict()

        assert "test_type" not in context_dict
        assert "file_path" not in context_dict
        assert context_dict["workflow_run_id"] == "run-123"

    def test_context_to_dict_timestamp_iso_format(self) -> None:
        """Test that timestamp is converted to ISO format in dict."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test",
            agent_name="Agent",
        )

        context_dict = context.to_dict()
        timestamp_str = context_dict["timestamp"]

        # Verify it's a valid ISO format string
        assert isinstance(timestamp_str, str)
        assert "T" in timestamp_str  # ISO format includes T


class TestRepairCycleLogger:
    """Test RepairCycleLogger."""

    def test_init_with_context(self) -> None:
        """Test initializing logger with context."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )

        logger = RepairCycleLogger(context)

        assert logger.context == context

    def test_logger_has_context_workflow_run_id(self) -> None:
        """Test that logger has access to workflow_run_id."""
        context = RepairCycleLogContext(
            workflow_run_id="run-456",
            stage_name="test",
            agent_name="Agent",
        )

        logger = RepairCycleLogger(context)

        assert logger.context.workflow_run_id == "run-456"

    def test_logger_has_context_stage_name(self) -> None:
        """Test that logger has access to stage_name."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="fix_cycle",
            agent_name="Agent",
        )

        logger = RepairCycleLogger(context)

        assert logger.context.stage_name == "fix_cycle"

    def test_logger_with_test_type(self) -> None:
        """Test logger with test type specified."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
            test_type="E2E",
        )

        logger = RepairCycleLogger(context)

        assert logger.context.test_type == "E2E"

    def test_logger_iteration_tracking(self) -> None:
        """Test logger tracks iteration number."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
            iteration=5,
        )

        logger = RepairCycleLogger(context)

        assert logger.context.iteration == 5

    def test_multiple_loggers_independent_contexts(self) -> None:
        """Test that multiple loggers can have independent contexts."""
        context1 = RepairCycleLogContext(
            workflow_run_id="run-1",
            stage_name="test1",
            agent_name="Agent1",
        )

        context2 = RepairCycleLogContext(
            workflow_run_id="run-2",
            stage_name="test2",
            agent_name="Agent2",
        )

        logger1 = RepairCycleLogger(context1)
        logger2 = RepairCycleLogger(context2)

        assert logger1.context.workflow_run_id == "run-1"
        assert logger2.context.workflow_run_id == "run-2"
        assert logger1.context != logger2.context


class TestRepairCycleLoggingIntegration:
    """Integration tests for repair cycle logging."""

    def test_create_context_and_log(self) -> None:
        """Test creating context and initializing logger."""
        context = RepairCycleLogContext(
            workflow_run_id="run-integration-test",
            stage_name="test_execution",
            agent_name="TestAgent",
            test_type="UNIT",
            iteration=1,
            project_id="proj-123",
            user_id="user-456",
        )

        logger = RepairCycleLogger(context)

        # Verify all context is accessible through logger
        assert logger.context.workflow_run_id == "run-integration-test"
        assert logger.context.stage_name == "test_execution"
        assert logger.context.agent_name == "TestAgent"
        assert logger.context.test_type == "UNIT"
        assert logger.context.iteration == 1
        assert logger.context.project_id == "proj-123"
        assert logger.context.user_id == "user-456"

    def test_context_dict_for_structured_logging(self) -> None:
        """Test that context dict is suitable for structured logging."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
            test_type="INTEGRATION",
            iteration=2,
        )

        context_dict = context.to_dict()

        # Verify all required fields are present
        assert "workflow_run_id" in context_dict
        assert "stage_name" in context_dict
        assert "agent_name" in context_dict
        assert "test_type" in context_dict
        assert "iteration" in context_dict
        assert "timestamp" in context_dict

        # Verify types
        assert isinstance(context_dict["workflow_run_id"], str)
        assert isinstance(context_dict["stage_name"], str)
        assert isinstance(context_dict["timestamp"], str)
        assert isinstance(context_dict["iteration"], int)
