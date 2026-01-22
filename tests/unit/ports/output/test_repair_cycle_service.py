"""Unit tests for IRepairCycleService port interface and data classes.

Tests validate:
1. Data class immutability (frozen dataclasses)
2. Data class validation (constraints in __post_init__)
3. Interface contract (abstract methods exist)
4. Event emission capability (inherited from IEventEmitter)
5. Monitoring capability (inherited from IMonitoredService)
"""

import pytest
from dataclasses import FrozenInstanceError
from unittest.mock import MagicMock

from codetoreum.domain.repair_cycle_types import (
    RepairTestFailure,
    RepairTestType,
    RepairTestWarning,
)
from codetoreum import ports as output_ports


# =============================================================================
# RepairCycleStatus Tests
# =============================================================================


class TestRepairCycleStatusDC:
    """Tests for RepairCycleStatus data class."""

    def test_create_valid_status(self) -> None:
        """Test creating a valid RepairCycleStatus."""
        status = output_ports.output.RepairCycleStatus(
            cycle_id="cycle-123",
            project_id="proj-456",
            stage_name="fix_failures",
            state="IN_PROGRESS",
            test_type_index=0,
            test_type_count=3,
            current_iteration=2,
            max_iterations=5,
            agent_call_count=10,
            max_agent_calls=100,
            started_at="2025-10-26T10:00:00Z",
            completed_at=None,
            checkpoint_iteration=1,
        )

        assert status.cycle_id == "cycle-123"
        assert status.project_id == "proj-456"
        assert status.state == "IN_PROGRESS"

    def test_repair_cycle_status_is_immutable(self) -> None:
        """Test that RepairCycleStatus is frozen (immutable)."""
        status = output_ports.output.RepairCycleStatus(
            cycle_id="cycle-123",
            project_id="proj-456",
            stage_name="fix_failures",
            state="IN_PROGRESS",
            test_type_index=0,
            test_type_count=3,
            current_iteration=2,
            max_iterations=5,
            agent_call_count=10,
            max_agent_calls=100,
            started_at="2025-10-26T10:00:00Z",
        )

        with pytest.raises(FrozenInstanceError):
            status.state = "COMPLETED"  # type: ignore

    def test_repair_cycle_status_missing_cycle_id(self) -> None:
        """Test that missing cycle_id raises ValueError."""
        with pytest.raises(ValueError, match="cycle_id is required"):
            output_ports.output.RepairCycleStatus(
                cycle_id="",
                project_id="proj-456",
                stage_name="fix_failures",
                state="IN_PROGRESS",
                test_type_index=0,
                test_type_count=3,
                current_iteration=2,
                max_iterations=5,
                agent_call_count=10,
                max_agent_calls=100,
                started_at="2025-10-26T10:00:00Z",
            )

    def test_repair_cycle_status_negative_test_type_index(self) -> None:
        """Test that negative test_type_index raises ValueError."""
        with pytest.raises(ValueError, match="test_type_index must be >= 0"):
            output_ports.output.RepairCycleStatus(
                cycle_id="cycle-123",
                project_id="proj-456",
                stage_name="fix_failures",
                state="IN_PROGRESS",
                test_type_index=-1,
                test_type_count=3,
                current_iteration=2,
                max_iterations=5,
                agent_call_count=10,
                max_agent_calls=100,
                started_at="2025-10-26T10:00:00Z",
            )


# =============================================================================
# TestExecutionRequest Tests
# =============================================================================


class TestExecutionRequestDCTests:
    """Tests for TestExecutionRequest data class."""

    def test_create_valid_test_execution_request(self) -> None:
        """Test creating a valid TestExecutionRequest."""
        request = output_ports.output.TestExecutionRequest(
            cycle_id="cycle-123",
            test_type=RepairTestType.UNIT,
            iteration=1,
            timeout=900,
            container_id="container-456",
        )

        assert request.cycle_id == "cycle-123"
        assert request.test_type == RepairTestType.UNIT
        assert request.iteration == 1

    def test_test_execution_request_is_immutable(self) -> None:
        """Test that TestExecutionRequest is frozen."""
        request = output_ports.output.TestExecutionRequest(
            cycle_id="cycle-123",
            test_type=RepairTestType.UNIT,
            iteration=1,
            timeout=900,
            container_id="container-456",
        )

        with pytest.raises(FrozenInstanceError):
            request.iteration = 2  # type: ignore

    def test_test_execution_request_missing_cycle_id(self) -> None:
        """Test that missing cycle_id raises ValueError."""
        with pytest.raises(ValueError, match="cycle_id is required"):
            output_ports.output.TestExecutionRequest(
                cycle_id="",
                test_type=RepairTestType.UNIT,
                iteration=1,
                timeout=900,
                container_id="container-456",
            )

    def test_test_execution_request_iteration_zero(self) -> None:
        """Test that iteration < 1 raises ValueError."""
        with pytest.raises(ValueError, match="iteration must be >= 1"):
            output_ports.output.TestExecutionRequest(
                cycle_id="cycle-123",
                test_type=RepairTestType.UNIT,
                iteration=0,
                timeout=900,
                container_id="container-456",
            )

    def test_test_execution_request_negative_timeout(self) -> None:
        """Test that timeout <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="timeout must be > 0"):
            output_ports.output.TestExecutionRequest(
                cycle_id="cycle-123",
                test_type=RepairTestType.UNIT,
                iteration=1,
                timeout=0,
                container_id="container-456",
            )


# =============================================================================
# FixRequest Tests
# =============================================================================


class TestFixRequestDCTests:
    """Tests for FixRequest data class."""

    def test_create_valid_fix_request(self) -> None:
        """Test creating a valid FixRequest."""
        failures = (
            RepairTestFailure(
                file="test_auth.py", test="test_login", message="Expected True but got False"
            ),
        )
        request = output_ports.output.FixRequest(
            cycle_id="cycle-123",
            test_file="test_auth.py",
            test_type=RepairTestType.UNIT,
            failures=failures,
            iteration=1,
            container_id="container-456",
        )

        assert request.cycle_id == "cycle-123"
        assert request.test_file == "test_auth.py"

    def test_fix_request_is_immutable(self) -> None:
        """Test that FixRequest is frozen."""
        failures = (
            RepairTestFailure(
                file="test_auth.py", test="test_login", message="Expected True but got False"
            ),
        )
        request = output_ports.output.FixRequest(
            cycle_id="cycle-123",
            test_file="test_auth.py",
            test_type=RepairTestType.UNIT,
            failures=failures,
            iteration=1,
            container_id="container-456",
        )

        with pytest.raises(FrozenInstanceError):
            request.iteration = 2  # type: ignore

    def test_fix_request_empty_failures(self) -> None:
        """Test that empty failures tuple raises ValueError."""
        with pytest.raises(ValueError, match="failures must not be empty"):
            output_ports.output.FixRequest(
                cycle_id="cycle-123",
                test_file="test_auth.py",
                test_type=RepairTestType.UNIT,
                failures=(),
                iteration=1,
                container_id="container-456",
            )

    def test_fix_request_multiple_failures(self) -> None:
        """Test FixRequest with multiple failures."""
        failures = (
            RepairTestFailure(
                file="test_auth.py", test="test_login", message="Expected True but got False"
            ),
            RepairTestFailure(
                file="test_auth.py",
                test="test_logout",
                message="AssertionError: User not logged out",
            ),
        )
        request = output_ports.output.FixRequest(
            cycle_id="cycle-123",
            test_file="test_auth.py",
            test_type=RepairTestType.UNIT,
            failures=failures,
            iteration=1,
            container_id="container-456",
        )

        assert len(request.failures) == 2


# =============================================================================
# WarningReviewRequest Tests
# =============================================================================


class TestWarningReviewRequestDCTests:
    """Tests for WarningReviewRequest data class."""

    def test_create_valid_warning_review_request(self) -> None:
        """Test creating a valid WarningReviewRequest."""
        warnings = (
            RepairTestWarning(file="auth.py", message="DeprecationWarning: use_new_api() is deprecated"),
        )
        request = output_ports.output.WarningReviewRequest(
            cycle_id="cycle-123",
            source_file="auth.py",
            test_type=RepairTestType.UNIT,
            warnings=warnings,
            iteration=1,
            container_id="container-456",
        )

        assert request.cycle_id == "cycle-123"
        assert request.source_file == "auth.py"

    def test_warning_review_request_is_immutable(self) -> None:
        """Test that WarningReviewRequest is frozen."""
        warnings = (
            RepairTestWarning(file="auth.py", message="DeprecationWarning: use_new_api() is deprecated"),
        )
        request = output_ports.output.WarningReviewRequest(
            cycle_id="cycle-123",
            source_file="auth.py",
            test_type=RepairTestType.UNIT,
            warnings=warnings,
            iteration=1,
            container_id="container-456",
        )

        with pytest.raises(FrozenInstanceError):
            request.iteration = 2  # type: ignore

    def test_warning_review_request_empty_warnings(self) -> None:
        """Test that empty warnings tuple raises ValueError."""
        with pytest.raises(ValueError, match="warnings must not be empty"):
            output_ports.output.WarningReviewRequest(
                cycle_id="cycle-123",
                source_file="auth.py",
                test_type=RepairTestType.UNIT,
                warnings=(),
                iteration=1,
                container_id="container-456",
            )


# =============================================================================
# IRepairCycleService Interface Tests
# =============================================================================


class TestIRepairCycleServiceInterface:
    """Tests for IRepairCycleService interface."""

    def test_interface_has_query_methods(self) -> None:
        """Test that interface defines query methods."""
        service_class = output_ports.output.IRepairCycleService
        assert hasattr(service_class, "get_repair_cycle_status")
        assert hasattr(service_class, "get_test_results")
        assert hasattr(service_class, "get_cycle_result")
        assert hasattr(service_class, "get_checkpoint")

    def test_interface_has_command_methods(self) -> None:
        """Test that interface defines command methods."""
        service_class = output_ports.output.IRepairCycleService
        assert hasattr(service_class, "start_repair_cycle")
        assert hasattr(service_class, "execute_test")
        assert hasattr(service_class, "coordinate_fix")
        assert hasattr(service_class, "coordinate_warning_review")
        assert hasattr(service_class, "record_test_cycle_result")
        assert hasattr(service_class, "abort_cycle")
        assert hasattr(service_class, "complete_cycle")
        assert hasattr(service_class, "save_checkpoint")

    def test_interface_extends_event_emitter_and_monitored_service(self) -> None:
        """Test that IRepairCycleService extends correct interfaces."""
        from codetoreum.ports.output import IEventEmitter, IMonitoredService

        # IRepairCycleService should be a subclass of both
        assert issubclass(output_ports.output.IRepairCycleService, IEventEmitter)
        assert issubclass(output_ports.output.IRepairCycleService, IMonitoredService)
