"""Unit tests for repair cycle logging infrastructure."""

import logging
from datetime import UTC, datetime
from unittest.mock import MagicMock, call, patch

import pytest

from codetoreum.infrastructure.repair_cycle_logging import (
    RepairCycleErrorLogger,
    RepairCycleLogContext,
    RepairCycleLogger,
    RepairCycleLoggingContext,
    RepairCycleLogLevel,
    RepairCyclePerformanceLogger,
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


class TestRepairCycleLoggerBehavior:
    """Test actual logging behavior of RepairCycleLogger."""

    def test_debug_logging(self) -> None:
        """Test debug method logs at debug level."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        logger = RepairCycleLogger(context)

        with patch.object(logger.logger, "debug") as mock_debug:
            logger.debug("Debug message", {"key": "value"})
            mock_debug.assert_called_once()
            call_args = mock_debug.call_args[0][0]
            assert "Debug message" in call_args
            assert "workflow_run_id=run-123" in call_args
            assert "key=value" in call_args

    def test_info_logging(self) -> None:
        """Test info method logs at info level."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        logger = RepairCycleLogger(context)

        with patch.object(logger.logger, "info") as mock_info:
            logger.info("Info message")
            mock_info.assert_called_once()
            call_args = mock_info.call_args[0][0]
            assert "Info message" in call_args
            assert "workflow_run_id=run-123" in call_args

    def test_warning_logging(self) -> None:
        """Test warning method logs at warning level."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        logger = RepairCycleLogger(context)

        with patch.object(logger.logger, "warning") as mock_warning:
            logger.warning("Warning message")
            mock_warning.assert_called_once()

    def test_error_logging(self) -> None:
        """Test error method logs with exc_info."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        logger = RepairCycleLogger(context)

        with patch.object(logger.logger, "error") as mock_error:
            logger.error("Error message")
            mock_error.assert_called_once()
            assert mock_error.call_args[1]["exc_info"] is True

    def test_critical_logging(self) -> None:
        """Test critical method logs critical messages."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        logger = RepairCycleLogger(context)

        with patch.object(logger.logger, "critical") as mock_critical:
            logger.critical("Critical message")
            mock_critical.assert_called_once()

    def test_log_duration_context_manager_success(self) -> None:
        """Test log_duration context manager on successful operation."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        logger = RepairCycleLogger(context)

        with patch.object(logger.logger, "info") as mock_info:
            with logger.log_duration("test_operation", {"iteration": 1}):
                pass

            # Should have 2 calls: started and completed
            assert mock_info.call_count == 2
            calls = mock_info.call_args_list
            assert "test_operation started" in calls[0][0][0]
            assert "test_operation completed" in calls[1][0][0]
            assert "success" in calls[1][0][0]

    def test_log_duration_context_manager_failure(self) -> None:
        """Test log_duration context manager on failed operation."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        logger = RepairCycleLogger(context)

        with patch.object(logger.logger, "info") as mock_info:
            with patch.object(logger.logger, "error") as mock_error:
                try:
                    with logger.log_duration("test_operation"):
                        raise ValueError("Test error")
                except ValueError:
                    pass

                # Info should be called once (started)
                assert mock_info.call_count == 1
                assert "test_operation started" in mock_info.call_args[0][0]

                # Error should be called once (failed)
                assert mock_error.call_count == 1
                assert "test_operation failed" in mock_error.call_args[0][0]
                assert mock_error.call_args[1]["exc_info"] is True

    def test_log_stage_context_manager(self) -> None:
        """Test log_stage context manager."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        logger = RepairCycleLogger(context)

        with patch.object(logger.logger, "info") as mock_info:
            with logger.log_stage("fix_failures", {"file_count": 3}):
                pass

            assert mock_info.call_count == 2
            calls = mock_info.call_args_list
            assert "stage:fix_failures started" in calls[0][0][0]


class TestRepairCyclePerformanceLoggerBehavior:
    """Test actual behavior of RepairCyclePerformanceLogger."""

    def test_record_timing_logs_operation(self) -> None:
        """Test record_timing logs performance metrics."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        perf_logger = RepairCyclePerformanceLogger(context)

        with patch.object(perf_logger.logger, "info") as mock_info:
            perf_logger.record_timing("test_execution", 1.5)
            mock_info.assert_called_once()
            call_args = mock_info.call_args[0][0]
            assert "operation=test_execution" in call_args
            assert "duration=1.5s" in call_args

    def test_record_timing_tracks_multiple_timings(self) -> None:
        """Test record_timing accumulates multiple timing measurements."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        perf_logger = RepairCyclePerformanceLogger(context)

        perf_logger.record_timing("op1", 1.0)
        perf_logger.record_timing("op1", 2.0)
        perf_logger.record_timing("op1", 3.0)

        stats = perf_logger.get_statistics()
        assert stats["op1"]["count"] == 3
        assert stats["op1"]["avg"] == 2.0

    def test_log_slow_operation_when_threshold_exceeded(self) -> None:
        """Test log_slow_operation logs when threshold is exceeded."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        perf_logger = RepairCyclePerformanceLogger(context)

        with patch.object(perf_logger.logger, "warning") as mock_warning:
            perf_logger.log_slow_operation("test", 5.0, 2.0, {"context": "data"})
            mock_warning.assert_called_once()
            call_args = mock_warning.call_args[0][0]
            assert "slow_operation_detected" in call_args
            assert "duration=5.0s" in call_args
            assert "threshold=2.0s" in call_args

    def test_log_slow_operation_silent_when_under_threshold(self) -> None:
        """Test log_slow_operation doesn't log when under threshold."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        perf_logger = RepairCyclePerformanceLogger(context)

        with patch.object(perf_logger.logger, "warning") as mock_warning:
            perf_logger.log_slow_operation("test", 1.0, 2.0)
            mock_warning.assert_not_called()

    def test_log_resource_usage(self) -> None:
        """Test log_resource_usage logs resource metrics."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        perf_logger = RepairCyclePerformanceLogger(context)

        with patch.object(perf_logger.logger, "debug") as mock_debug:
            perf_logger.log_resource_usage({"cpu_percent": 45.2, "memory_mb": 512})
            mock_debug.assert_called_once()
            call_args = mock_debug.call_args[0][0]
            assert "cpu_percent=45.2" in call_args
            assert "memory_mb=512" in call_args

    def test_get_statistics(self) -> None:
        """Test get_statistics returns correct statistics."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        perf_logger = RepairCyclePerformanceLogger(context)

        perf_logger.record_timing("op1", 1.0)
        perf_logger.record_timing("op1", 3.0)
        perf_logger.record_timing("op2", 5.0)

        stats = perf_logger.get_statistics()
        assert len(stats) == 2
        assert stats["op1"]["min"] == 1.0
        assert stats["op1"]["max"] == 3.0
        assert stats["op1"]["avg"] == 2.0
        assert stats["op2"]["total"] == 5.0


class TestRepairCycleErrorLoggerBehavior:
    """Test actual behavior of RepairCycleErrorLogger."""

    def test_log_test_failure(self) -> None:
        """Test log_test_failure logs failure details."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        error_logger = RepairCycleErrorLogger(context)

        with patch.object(error_logger.logger, "error") as mock_error:
            error_logger.log_test_failure(
                "unit",
                "test_file.py",
                "AssertionError: Expected True",
                {"line": 42},
            )
            mock_error.assert_called_once()
            call_args = mock_error.call_args[0][0]
            assert "test_failure" in call_args
            assert "test_type=unit" in call_args
            assert "test_file=test_file.py" in call_args

    def test_log_test_failure_increments_count(self) -> None:
        """Test log_test_failure increments error count."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        error_logger = RepairCycleErrorLogger(context)

        error_logger.log_test_failure("unit", "test.py", "Failed")
        error_logger.log_test_failure("unit", "test.py", "Failed")

        summary = error_logger.get_error_summary()
        assert summary["test_failure"] == 2

    def test_log_fix_attempt_success(self) -> None:
        """Test log_fix_attempt logs successful fix."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        error_logger = RepairCycleErrorLogger(context)

        with patch.object(error_logger.logger, "info") as mock_info:
            error_logger.log_fix_attempt(
                "/path/to/file.py",
                1,
                True,
                agent_response="Fixed the issue",
            )
            mock_info.assert_called_once()
            call_args = mock_info.call_args[0][0]
            assert "fix_attempt" in call_args
            assert "status=success" in call_args

    def test_log_fix_attempt_failure(self) -> None:
        """Test log_fix_attempt logs failed fix."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        error_logger = RepairCycleErrorLogger(context)

        with patch.object(error_logger.logger, "warning") as mock_warning:
            error_logger.log_fix_attempt(
                "/path/to/file.py",
                1,
                False,
                error="Syntax error",
            )
            mock_warning.assert_called_once()
            call_args = mock_warning.call_args[0][0]
            assert "fix_attempt" in call_args
            assert "status=failed" in call_args

    def test_log_circuit_breaker_triggered(self) -> None:
        """Test log_circuit_breaker_triggered logs breaker activation."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        error_logger = RepairCycleErrorLogger(context)

        with patch.object(error_logger.logger, "critical") as mock_critical:
            error_logger.log_circuit_breaker_triggered(
                "Too many failures",
                {"failures": 5, "threshold": 3},
            )
            mock_critical.assert_called_once()
            call_args = mock_critical.call_args[0][0]
            assert "circuit_breaker_triggered" in call_args
            assert "reason=Too many failures" in call_args

    def test_log_checkpoint_created(self) -> None:
        """Test log_checkpoint_created logs checkpoint."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        error_logger = RepairCycleErrorLogger(context)

        with patch.object(error_logger.logger, "info") as mock_info:
            error_logger.log_checkpoint_created(
                "cp-001",
                {"files": 5, "timestamp": "2024-01-01T00:00:00"},
            )
            mock_info.assert_called_once()
            call_args = mock_info.call_args[0][0]
            assert "checkpoint_created" in call_args
            assert "checkpoint_id=cp-001" in call_args

    def test_log_checkpoint_restored(self) -> None:
        """Test log_checkpoint_restored logs restoration."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        error_logger = RepairCycleErrorLogger(context)

        with patch.object(error_logger.logger, "info") as mock_info:
            error_logger.log_checkpoint_restored(
                "cp-001",
                {"files_restored": 5},
            )
            mock_info.assert_called_once()
            call_args = mock_info.call_args[0][0]
            assert "checkpoint_restored" in call_args

    def test_get_error_summary(self) -> None:
        """Test get_error_summary returns error counts."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        error_logger = RepairCycleErrorLogger(context)

        error_logger.log_test_failure("unit", "test.py", "Failed")
        error_logger.log_fix_attempt("/file.py", 1, False, error="Error")
        error_logger.log_circuit_breaker_triggered("Reason")

        summary = error_logger.get_error_summary()
        assert summary["test_failure"] == 1
        assert summary["fix_attempt_failed"] == 1
        assert summary["circuit_breaker"] == 1


class TestRepairCycleLoggingContextBehavior:
    """Test context manager behavior."""

    def test_logging_context_enter_exit_success(self) -> None:
        """Test context manager enters and exits successfully."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        logging_context = RepairCycleLoggingContext(context)

        with patch.object(logging_context.logger.logger, "info") as mock_info:
            with logging_context:
                pass

            assert mock_info.call_count == 2
            calls = mock_info.call_args_list
            assert "repair_cycle_context_started" in calls[0][0][0]
            assert "repair_cycle_context_completed" in calls[1][0][0]

    def test_logging_context_handles_exception(self) -> None:
        """Test context manager handles exceptions."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        logging_context = RepairCycleLoggingContext(context)

        with patch.object(logging_context.error_logger.logger, "error") as mock_error:
            try:
                with logging_context:
                    raise ValueError("Test error")
            except ValueError:
                pass

            mock_error.assert_called_once()
            call_args = mock_error.call_args[0][0]
            assert "repair_cycle_context_failed" in call_args
            assert "ValueError" in call_args

    def test_logging_context_log_operation(self) -> None:
        """Test log_operation context manager."""
        context = RepairCycleLogContext(
            workflow_run_id="run-123",
            stage_name="test_execution",
            agent_name="TestAgent",
        )
        logging_context = RepairCycleLoggingContext(context)

        with patch.object(logging_context.logger.logger, "info") as mock_info:
            with logging_context.log_operation("test_op", {"iteration": 1}):
                pass

            # Should log start and completion
            assert mock_info.call_count >= 2
