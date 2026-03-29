"""Unit tests for repair cycle domain types.

Tests verify immutability, validation, and behavior of all repair cycle
domain types following the event sourcing pattern.
"""

import pytest

try:
    from dataclasses import FrozenInstanceError
except ImportError:
    FrozenInstanceError = AttributeError  # type: ignore

from codetoreum.domain.repair_cycle_types import (
    AnalysisContext,
    CycleResult,
    FailureClassification,
    RepairCycleResult,
    RepairCycleStageConfig,
    RepairTestFailure,
    RepairTestResult,
    RepairTestRunConfig,
    RepairTestType,
    RepairTestWarning,
    SystemicAnalysisResult,
)

# ============================================================================
# RepairTestType Enum Tests
# ============================================================================


class TestRepairTestType:
    """Test RepairTestType enum."""

    def test_enum_values(self):
        """Test that all required test types exist."""
        assert RepairTestType.UNIT.value == "UNIT"
        assert RepairTestType.INTEGRATION.value == "INTEGRATION"
        assert RepairTestType.E2E.value == "E2E"

    def test_enum_ordering(self):
        """Test execution order is UNIT → INTEGRATION → E2E."""
        types = list(RepairTestType)
        assert len(types) == 3
        assert types[0] == RepairTestType.UNIT
        assert types[1] == RepairTestType.INTEGRATION
        assert types[2] == RepairTestType.E2E

    def test_enum_comparison(self):
        """Test enum equality."""
        unit1 = RepairTestType.UNIT
        unit2 = RepairTestType.UNIT
        assert unit1 == unit2
        assert unit1 != RepairTestType.INTEGRATION


# ============================================================================
# RepairTestFailure Immutability Tests
# ============================================================================


class TestRepairTestFailure:
    """Test RepairTestFailure value object."""

    def test_create_failure(self):
        """Test creating a test failure."""
        failure = RepairTestFailure(
            file="test_auth.py",
            test="test_login_success",
            message="Expected True, got False",
        )
        assert failure.file == "test_auth.py"
        assert failure.test == "test_login_success"
        assert failure.message == "Expected True, got False"

    def test_immutability_raises_frozen_error(self):
        """Test that frozen dataclass prevents modification."""
        failure = RepairTestFailure(
            file="test_auth.py",
            test="test_login",
            message="Failed",
        )
        with pytest.raises(FrozenInstanceError):
            failure.file = "test_other.py"  # type: ignore[misc]

        with pytest.raises(FrozenInstanceError):
            failure.test = "test_other"  # type: ignore[misc]

        with pytest.raises(FrozenInstanceError):
            failure.message = "Different message"  # type: ignore[misc]

    def test_empty_file_raises_error(self):
        """Test that empty file raises ValueError."""
        with pytest.raises(ValueError, match="file is required"):
            RepairTestFailure(
                file="",
                test="test_login",
                message="Failed",
            )

    def test_empty_test_raises_error(self):
        """Test that empty test raises ValueError."""
        with pytest.raises(ValueError, match="test is required"):
            RepairTestFailure(
                file="test_auth.py",
                test="",
                message="Failed",
            )

    def test_empty_message_raises_error(self):
        """Test that empty message raises ValueError."""
        with pytest.raises(ValueError, match="message is required"):
            RepairTestFailure(
                file="test_auth.py",
                test="test_login",
                message="",
            )

    def test_equality(self):
        """Test value object equality."""
        failure1 = RepairTestFailure(
            file="test_auth.py",
            test="test_login",
            message="Failed",
        )
        failure2 = RepairTestFailure(
            file="test_auth.py",
            test="test_login",
            message="Failed",
        )
        assert failure1 == failure2

    def test_inequality(self):
        """Test value object inequality."""
        failure1 = RepairTestFailure(
            file="test_auth.py",
            test="test_login",
            message="Failed",
        )
        failure2 = RepairTestFailure(
            file="test_auth.py",
            test="test_logout",
            message="Failed",
        )
        assert failure1 != failure2


# ============================================================================
# RepairTestWarning Immutability Tests
# ============================================================================


class TestRepairTestWarning:
    """Test RepairTestWarning value object."""

    def test_create_warning(self):
        """Test creating a test warning."""
        warning = RepairTestWarning(
            file="auth.py",
            message="DeprecationWarning: use_new_api() is deprecated",
        )
        assert warning.file == "auth.py"
        assert warning.message == "DeprecationWarning: use_new_api() is deprecated"

    def test_immutability_raises_frozen_error(self):
        """Test that frozen dataclass prevents modification."""
        warning = RepairTestWarning(
            file="auth.py",
            message="DeprecationWarning",
        )
        with pytest.raises(FrozenInstanceError):
            warning.file = "other.py"  # type: ignore[misc]

        with pytest.raises(FrozenInstanceError):
            warning.message = "Different warning"  # type: ignore[misc]

    def test_empty_file_raises_error(self):
        """Test that empty file raises ValueError."""
        with pytest.raises(ValueError, match="file is required"):
            RepairTestWarning(
                file="",
                message="Warning",
            )

    def test_empty_message_raises_error(self):
        """Test that empty message raises ValueError."""
        with pytest.raises(ValueError, match="message is required"):
            RepairTestWarning(
                file="auth.py",
                message="",
            )

    def test_equality(self):
        """Test value object equality."""
        warning1 = RepairTestWarning(
            file="auth.py",
            message="DeprecationWarning",
        )
        warning2 = RepairTestWarning(
            file="auth.py",
            message="DeprecationWarning",
        )
        assert warning1 == warning2


# ============================================================================
# RepairTestResult Immutability Tests
# ============================================================================


class TestRepairTestResult:
    """Test RepairTestResult value object."""

    def test_create_test_result_no_failures(self):
        """Test creating a test result with no failures."""
        result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="All tests passed",
            timestamp="2025-01-22T10:00:00Z",
        )
        assert result.test_type == RepairTestType.UNIT
        assert result.iteration == 1
        assert result.passed == 10
        assert result.failed == 0
        assert result.warnings == 0
        assert result.failures == ()
        assert result.warning_list == ()

    def test_create_test_result_with_failures(self):
        """Test creating a test result with failures."""
        failure = RepairTestFailure(
            file="test_auth.py",
            test="test_login",
            message="Failed",
        )
        result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=2,
            passed=9,
            failed=1,
            warnings=0,
            failures=(failure,),
            warning_list=(),
            raw_output="1 test failed",
            timestamp="2025-01-22T10:05:00Z",
        )
        assert result.failed == 1
        assert len(result.failures) == 1
        assert result.failures[0] == failure

    def test_failures_tuple_immutable(self):
        """Test that failures tuple is immutable."""
        result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="OK",
            timestamp="2025-01-22T10:00:00Z",
        )
        with pytest.raises((TypeError, AttributeError)):
            result.failures.append(None)  # type: ignore[attr-defined]

    def test_result_immutability_raises_frozen_error(self):
        """Test that frozen dataclass prevents modification."""
        result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="OK",
            timestamp="2025-01-22T10:00:00Z",
        )
        with pytest.raises(FrozenInstanceError):
            result.passed = 11  # type: ignore[misc]

        with pytest.raises(FrozenInstanceError):
            result.iteration = 2  # type: ignore[misc]

    def test_invalid_iteration_raises_error(self):
        """Test that iteration < 1 raises ValueError."""
        with pytest.raises(ValueError, match="iteration must be >= 1"):
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=0,
                passed=10,
                failed=0,
                warnings=0,
                failures=(),
                warning_list=(),
                raw_output="OK",
                timestamp="2025-01-22T10:00:00Z",
            )

    def test_negative_passed_raises_error(self):
        """Test that negative passed count raises ValueError."""
        with pytest.raises(ValueError, match="passed must be >= 0"):
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=-1,
                failed=0,
                warnings=0,
                failures=(),
                warning_list=(),
                raw_output="OK",
                timestamp="2025-01-22T10:00:00Z",
            )

    def test_negative_failed_raises_error(self):
        """Test that negative failed count raises ValueError."""
        with pytest.raises(ValueError, match="failed must be >= 0"):
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=10,
                failed=-1,
                warnings=0,
                failures=(),
                warning_list=(),
                raw_output="OK",
                timestamp="2025-01-22T10:00:00Z",
            )

    def test_negative_warnings_raises_error(self):
        """Test that negative warnings count raises ValueError."""
        with pytest.raises(ValueError, match="warnings must be >= 0"):
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=10,
                failed=0,
                warnings=-1,
                failures=(),
                warning_list=(),
                raw_output="OK",
                timestamp="2025-01-22T10:00:00Z",
            )

    def test_empty_timestamp_raises_error(self):
        """Test that empty timestamp raises ValueError."""
        with pytest.raises(ValueError, match="timestamp is required"):
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=10,
                failed=0,
                warnings=0,
                failures=(),
                warning_list=(),
                raw_output="OK",
                timestamp="",
            )

    def test_failed_count_mismatch_raises_error(self):
        """Test that failed count mismatch with failures list raises ValueError."""
        failure = RepairTestFailure(
            file="test_auth.py",
            test="test_login",
            message="Failed",
        )
        with pytest.raises(ValueError, match="failed count mismatch"):
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=10,
                failed=2,  # Mismatch: says 2 but only 1 in list
                warnings=0,
                failures=(failure,),  # Only 1 failure
                warning_list=(),
                raw_output="OK",
                timestamp="2025-01-22T10:00:00Z",
            )

    def test_warnings_count_mismatch_raises_error(self):
        """Test that warnings count mismatch with warning_list raises ValueError."""
        warning = RepairTestWarning(
            file="auth.py",
            message="DeprecationWarning",
        )
        with pytest.raises(ValueError, match="warnings count mismatch"):
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=10,
                failed=0,
                warnings=2,  # Mismatch: says 2 but only 1 in list
                failures=(),
                warning_list=(warning,),  # Only 1 warning
                raw_output="OK",
                timestamp="2025-01-22T10:00:00Z",
            )


# ============================================================================
# CycleResult Immutability Tests
# ============================================================================


class TestCycleResult:
    """Test CycleResult value object."""

    def test_create_successful_cycle(self):
        """Test creating a successful cycle result."""
        test_result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="OK",
            timestamp="2025-01-22T10:00:00Z",
        )
        cycle = CycleResult(
            test_type=RepairTestType.UNIT,
            passed=True,
            iterations=1,
            final_result=test_result,
            error=None,
            files_fixed=0,
            warnings_reviewed=0,
            duration_seconds=5.5,
        )
        assert cycle.passed is True
        assert cycle.test_type == RepairTestType.UNIT
        assert cycle.iterations == 1
        assert cycle.final_result == test_result
        assert cycle.error is None
        assert cycle.files_fixed == 0
        assert cycle.warnings_reviewed == 0
        assert cycle.duration_seconds == 5.5

    def test_create_failed_cycle(self):
        """Test creating a failed cycle result."""
        cycle = CycleResult(
            test_type=RepairTestType.INTEGRATION,
            passed=False,
            iterations=3,
            final_result=None,
            error="Test execution timeout",
            files_fixed=0,
            warnings_reviewed=0,
            duration_seconds=900.0,
        )
        assert cycle.passed is False
        assert cycle.error == "Test execution timeout"
        assert cycle.final_result is None

    def test_cycle_immutability_raises_frozen_error(self):
        """Test that frozen dataclass prevents modification."""
        test_result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="OK",
            timestamp="2025-01-22T10:00:00Z",
        )
        cycle = CycleResult(
            test_type=RepairTestType.UNIT,
            passed=True,
            iterations=1,
            final_result=test_result,
            error=None,
            files_fixed=0,
            warnings_reviewed=0,
            duration_seconds=5.5,
        )
        with pytest.raises(FrozenInstanceError):
            cycle.passed = False  # type: ignore[misc]

        with pytest.raises(FrozenInstanceError):
            cycle.iterations = 2  # type: ignore[misc]

    def test_negative_iterations_raises_error(self):
        """Test that negative iterations raises ValueError."""
        with pytest.raises(ValueError, match="iterations must be >= 0"):
            CycleResult(
                test_type=RepairTestType.UNIT,
                passed=False,
                iterations=-1,
                final_result=None,
                error="Failed",
                files_fixed=0,
                warnings_reviewed=0,
                duration_seconds=10.0,
            )

    def test_negative_files_fixed_raises_error(self):
        """Test that negative files_fixed raises ValueError."""
        with pytest.raises(ValueError, match="files_fixed must be >= 0"):
            CycleResult(
                test_type=RepairTestType.UNIT,
                passed=False,
                iterations=1,
                final_result=None,
                error="Failed",
                files_fixed=-1,
                warnings_reviewed=0,
                duration_seconds=10.0,
            )

    def test_negative_warnings_reviewed_raises_error(self):
        """Test that negative warnings_reviewed raises ValueError."""
        with pytest.raises(ValueError, match="warnings_reviewed must be >= 0"):
            CycleResult(
                test_type=RepairTestType.UNIT,
                passed=False,
                iterations=1,
                final_result=None,
                error="Failed",
                files_fixed=0,
                warnings_reviewed=-1,
                duration_seconds=10.0,
            )

    def test_negative_duration_raises_error(self):
        """Test that negative duration raises ValueError."""
        with pytest.raises(ValueError, match="duration_seconds must be >= 0"):
            CycleResult(
                test_type=RepairTestType.UNIT,
                passed=False,
                iterations=1,
                final_result=None,
                error="Failed",
                files_fixed=0,
                warnings_reviewed=0,
                duration_seconds=-1.0,
            )

    def test_passed_true_with_no_final_result_raises_error(self):
        """Test that passed=True without final_result raises ValueError."""
        with pytest.raises(ValueError, match="passed=True but final_result is None"):
            CycleResult(
                test_type=RepairTestType.UNIT,
                passed=True,
                iterations=1,
                final_result=None,  # Inconsistency: passed but no result
                error=None,
                files_fixed=0,
                warnings_reviewed=0,
                duration_seconds=5.0,
            )

    def test_passed_true_with_error_raises_error(self):
        """Test that passed=True with error set raises ValueError."""
        test_result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="OK",
            timestamp="2025-01-22T10:00:00Z",
        )
        with pytest.raises(ValueError, match="passed=True but error is set"):
            CycleResult(
                test_type=RepairTestType.UNIT,
                passed=True,
                iterations=1,
                final_result=test_result,
                error="Test execution timeout",  # Inconsistency: passed but has error
                files_fixed=0,
                warnings_reviewed=0,
                duration_seconds=5.0,
            )


# ============================================================================
# RepairCycleResult Immutability Tests
# ============================================================================


class TestRepairCycleResult:
    """Test RepairCycleResult value object."""

    def test_create_cycle_result(self):
        """Test creating a repair cycle result."""
        test_result1 = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="OK",
            timestamp="2025-01-22T10:00:00Z",
        )
        cycle1 = CycleResult(
            test_type=RepairTestType.UNIT,
            passed=True,
            iterations=1,
            final_result=test_result1,
            error=None,
            files_fixed=0,
            warnings_reviewed=0,
            duration_seconds=5.0,
        )
        test_result2 = RepairTestResult(
            test_type=RepairTestType.INTEGRATION,
            iteration=2,
            passed=8,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="OK",
            timestamp="2025-01-22T10:15:00Z",
        )
        cycle2 = CycleResult(
            test_type=RepairTestType.INTEGRATION,
            passed=True,
            iterations=2,
            final_result=test_result2,
            error=None,
            files_fixed=2,
            warnings_reviewed=1,
            duration_seconds=15.0,
        )
        result = RepairCycleResult(
            stage="fix_failures",
            test_results=(cycle1, cycle2),
            overall_success=True,
            total_agent_calls=5,
            duration_seconds=20.0,
            timestamp="2025-01-22T10:30:00Z",
        )
        assert result.stage == "fix_failures"
        assert len(result.test_results) == 2
        assert result.overall_success is True
        assert result.total_agent_calls == 5
        assert result.duration_seconds == 20.0

    def test_test_results_tuple_immutable(self):
        """Test that test_results tuple is immutable."""
        result = RepairCycleResult(
            stage="fix_failures",
            test_results=(),
            overall_success=False,
            total_agent_calls=0,
            duration_seconds=0.0,
            timestamp="2025-01-22T10:00:00Z",
        )
        with pytest.raises((TypeError, AttributeError)):
            result.test_results.append(None)  # type: ignore[attr-defined]

    def test_cycle_result_immutability_raises_frozen_error(self):
        """Test that frozen dataclass prevents modification."""
        result = RepairCycleResult(
            stage="fix_failures",
            test_results=(),
            overall_success=True,
            total_agent_calls=5,
            duration_seconds=20.0,
            timestamp="2025-01-22T10:00:00Z",
        )
        with pytest.raises(FrozenInstanceError):
            result.overall_success = False  # type: ignore[misc]

        with pytest.raises(FrozenInstanceError):
            result.total_agent_calls = 10  # type: ignore[misc]

    def test_empty_stage_raises_error(self):
        """Test that empty stage raises ValueError."""
        with pytest.raises(ValueError, match="stage is required"):
            RepairCycleResult(
                stage="",
                test_results=(),
                overall_success=False,
                total_agent_calls=0,
                duration_seconds=0.0,
                timestamp="2025-01-22T10:00:00Z",
            )

    def test_negative_total_agent_calls_raises_error(self):
        """Test that negative total_agent_calls raises ValueError."""
        with pytest.raises(ValueError, match="total_agent_calls must be >= 0"):
            RepairCycleResult(
                stage="fix_failures",
                test_results=(),
                overall_success=False,
                total_agent_calls=-1,
                duration_seconds=0.0,
                timestamp="2025-01-22T10:00:00Z",
            )

    def test_negative_duration_raises_error(self):
        """Test that negative duration raises ValueError."""
        with pytest.raises(ValueError, match="duration_seconds must be >= 0"):
            RepairCycleResult(
                stage="fix_failures",
                test_results=(),
                overall_success=False,
                total_agent_calls=0,
                duration_seconds=-1.0,
                timestamp="2025-01-22T10:00:00Z",
            )

    def test_empty_timestamp_raises_error(self):
        """Test that empty timestamp raises ValueError."""
        with pytest.raises(ValueError, match="timestamp is required"):
            RepairCycleResult(
                stage="fix_failures",
                test_results=(),
                overall_success=False,
                total_agent_calls=0,
                duration_seconds=0.0,
                timestamp="",
            )

    def test_overall_success_true_with_failed_tests_raises_error(self):
        """Test that overall_success=True with failed test results raises ValueError."""
        test_result1 = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="OK",
            timestamp="2025-01-22T10:00:00Z",
        )
        cycle1 = CycleResult(
            test_type=RepairTestType.UNIT,
            passed=True,
            iterations=1,
            final_result=test_result1,
            error=None,
            files_fixed=0,
            warnings_reviewed=0,
            duration_seconds=5.0,
        )
        cycle2 = CycleResult(
            test_type=RepairTestType.INTEGRATION,
            passed=False,  # This one failed
            iterations=3,
            final_result=None,
            error="Test execution timeout",
            files_fixed=0,
            warnings_reviewed=0,
            duration_seconds=900.0,
        )
        with pytest.raises(ValueError, match="overall_success=True but some test types failed"):
            RepairCycleResult(
                stage="fix_failures",
                test_results=(cycle1, cycle2),
                overall_success=True,  # Inconsistency: says success but cycle2 failed
                total_agent_calls=5,
                duration_seconds=905.0,
                timestamp="2025-01-22T10:30:00Z",
            )

    def test_overall_success_false_with_all_passed_raises_error(self):
        """Test that overall_success=False with all passed test results raises ValueError."""
        test_result1 = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="OK",
            timestamp="2025-01-22T10:00:00Z",
        )
        cycle1 = CycleResult(
            test_type=RepairTestType.UNIT,
            passed=True,
            iterations=1,
            final_result=test_result1,
            error=None,
            files_fixed=0,
            warnings_reviewed=0,
            duration_seconds=5.0,
        )
        test_result2 = RepairTestResult(
            test_type=RepairTestType.INTEGRATION,
            iteration=2,
            passed=8,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="OK",
            timestamp="2025-01-22T10:15:00Z",
        )
        cycle2 = CycleResult(
            test_type=RepairTestType.INTEGRATION,
            passed=True,
            iterations=2,
            final_result=test_result2,
            error=None,
            files_fixed=2,
            warnings_reviewed=1,
            duration_seconds=15.0,
        )
        with pytest.raises(ValueError, match="overall_success=False but all test results passed"):
            RepairCycleResult(
                stage="fix_failures",
                test_results=(cycle1, cycle2),
                overall_success=False,  # Inconsistency: says failed but all passed
                total_agent_calls=5,
                duration_seconds=20.0,
                timestamp="2025-01-22T10:30:00Z",
            )


# ============================================================================
# RepairTestRunConfig Tests
# ============================================================================


class TestRepairTestRunConfig:
    """Test RepairTestRunConfig value object."""

    def test_create_config_with_defaults(self):
        """Test creating config with default values."""
        config = RepairTestRunConfig(test_type=RepairTestType.UNIT)
        assert config.test_type == RepairTestType.UNIT
        assert config.timeout == 900
        assert config.max_iterations == 5
        assert config.review_warnings is True
        assert config.max_file_iterations == 3

    def test_create_config_with_custom_values(self):
        """Test creating config with custom values."""
        config = RepairTestRunConfig(
            test_type=RepairTestType.E2E,
            timeout=1800,
            max_iterations=10,
            review_warnings=False,
            max_file_iterations=5,
        )
        assert config.test_type == RepairTestType.E2E
        assert config.timeout == 1800
        assert config.max_iterations == 10
        assert config.review_warnings is False
        assert config.max_file_iterations == 5

    def test_config_immutability_raises_frozen_error(self):
        """Test that frozen dataclass prevents modification."""
        config = RepairTestRunConfig(test_type=RepairTestType.UNIT)
        with pytest.raises(FrozenInstanceError):
            config.timeout = 1800  # type: ignore[misc]

        with pytest.raises(FrozenInstanceError):
            config.max_iterations = 10  # type: ignore[misc]

    def test_invalid_timeout_raises_error(self):
        """Test that invalid timeout raises ValueError."""
        with pytest.raises(ValueError, match="timeout must be > 0"):
            RepairTestRunConfig(
                test_type=RepairTestType.UNIT,
                timeout=0,
            )

        with pytest.raises(ValueError, match="timeout must be > 0"):
            RepairTestRunConfig(
                test_type=RepairTestType.UNIT,
                timeout=-1,
            )

    def test_invalid_max_iterations_raises_error(self):
        """Test that invalid max_iterations raises ValueError."""
        with pytest.raises(ValueError, match="max_iterations must be > 0"):
            RepairTestRunConfig(
                test_type=RepairTestType.UNIT,
                max_iterations=0,
            )

        with pytest.raises(ValueError, match="max_iterations must be > 0"):
            RepairTestRunConfig(
                test_type=RepairTestType.UNIT,
                max_iterations=-1,
            )

    def test_invalid_max_file_iterations_raises_error(self):
        """Test that invalid max_file_iterations raises ValueError."""
        with pytest.raises(ValueError, match="max_file_iterations must be > 0"):
            RepairTestRunConfig(
                test_type=RepairTestType.UNIT,
                max_file_iterations=0,
            )

        with pytest.raises(ValueError, match="max_file_iterations must be > 0"):
            RepairTestRunConfig(
                test_type=RepairTestType.UNIT,
                max_file_iterations=-1,
            )


# ============================================================================
# RepairCycleStageConfig Tests
# ============================================================================


class TestRepairCycleStageConfig:
    """Test RepairCycleStageConfig value object."""

    def test_create_config_with_defaults(self):
        """Test creating stage config with default values."""
        test_config = RepairTestRunConfig(test_type=RepairTestType.UNIT)
        config = RepairCycleStageConfig(
            name="fix_failures",
            test_configs=(test_config,),
        )
        assert config.name == "fix_failures"
        assert len(config.test_configs) == 1
        assert config.agent_name == "senior_software_engineer"
        assert config.max_total_agent_calls == 100
        assert config.checkpoint_interval == 5

    def test_create_config_with_all_test_types(self):
        """Test creating config with all test types."""
        configs = (
            RepairTestRunConfig(test_type=RepairTestType.UNIT),
            RepairTestRunConfig(test_type=RepairTestType.INTEGRATION),
            RepairTestRunConfig(test_type=RepairTestType.E2E),
        )
        config = RepairCycleStageConfig(
            name="full_cycle",
            test_configs=configs,
        )
        assert len(config.test_configs) == 3
        assert config.test_configs[0].test_type == RepairTestType.UNIT
        assert config.test_configs[1].test_type == RepairTestType.INTEGRATION
        assert config.test_configs[2].test_type == RepairTestType.E2E

    def test_create_config_with_custom_values(self):
        """Test creating config with custom values."""
        test_config = RepairTestRunConfig(test_type=RepairTestType.UNIT)
        config = RepairCycleStageConfig(
            name="fix_warnings",
            test_configs=(test_config,),
            agent_name="code_reviewer",
            max_total_agent_calls=200,
            checkpoint_interval=10,
        )
        assert config.agent_name == "code_reviewer"
        assert config.max_total_agent_calls == 200
        assert config.checkpoint_interval == 10

    def test_test_configs_tuple_immutable(self):
        """Test that test_configs tuple is immutable."""
        config = RepairCycleStageConfig(
            name="fix_failures",
            test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
        )
        with pytest.raises((TypeError, AttributeError)):
            config.test_configs.append(None)  # type: ignore[attr-defined]

    def test_config_immutability_raises_frozen_error(self):
        """Test that frozen dataclass prevents modification."""
        config = RepairCycleStageConfig(
            name="fix_failures",
            test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
        )
        with pytest.raises(FrozenInstanceError):
            config.name = "fix_warnings"  # type: ignore[misc]

        with pytest.raises(FrozenInstanceError):
            config.max_total_agent_calls = 50  # type: ignore[misc]

    def test_empty_name_raises_error(self):
        """Test that empty name raises ValueError."""
        with pytest.raises(ValueError, match="name is required"):
            RepairCycleStageConfig(
                name="",
                test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
            )

    def test_empty_test_configs_raises_error(self):
        """Test that empty test_configs raises ValueError."""
        with pytest.raises(ValueError, match="test_configs must not be empty"):
            RepairCycleStageConfig(
                name="fix_failures",
                test_configs=(),
            )

    def test_invalid_max_total_agent_calls_raises_error(self):
        """Test that invalid max_total_agent_calls raises ValueError."""
        with pytest.raises(ValueError, match="max_total_agent_calls must be > 0"):
            RepairCycleStageConfig(
                name="fix_failures",
                test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
                max_total_agent_calls=0,
            )

    def test_invalid_checkpoint_interval_raises_error(self):
        """Test that invalid checkpoint_interval raises ValueError."""
        with pytest.raises(ValueError, match="checkpoint_interval must be > 0"):
            RepairCycleStageConfig(
                name="fix_failures",
                test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
                checkpoint_interval=0,
            )


# ============================================================================
# FailureClassification Enum Tests
# ============================================================================


class TestFailureClassification:
    """Test FailureClassification enum."""

    def test_all_five_values_exist(self):
        """Test that all five required classification values exist."""
        assert FailureClassification.CODE_DEFECT.value == "code_defect"
        assert FailureClassification.ENVIRONMENT_ISSUE.value == "environment_issue"
        assert FailureClassification.TRANSIENT_FAILURE.value == "transient_failure"
        assert FailureClassification.DEPENDENCY_ISSUE.value == "dependency_issue"
        assert FailureClassification.CONFIGURATION_ISSUE.value == "configuration_issue"

    def test_enum_count(self):
        """Test that exactly five enum values exist."""
        values = list(FailureClassification)
        assert len(values) == 5

    def test_enum_is_str(self):
        """Test that enum values are strings (inherits from str)."""
        assert isinstance(FailureClassification.CODE_DEFECT, str)
        assert isinstance(FailureClassification.ENVIRONMENT_ISSUE, str)
        assert FailureClassification.CODE_DEFECT == "code_defect"

    def test_enum_equality(self):
        """Test enum equality."""
        assert FailureClassification.CODE_DEFECT == FailureClassification.CODE_DEFECT
        assert FailureClassification.CODE_DEFECT != FailureClassification.ENVIRONMENT_ISSUE


# ============================================================================
# SystemicAnalysisResult Immutability Tests
# ============================================================================


class TestSystemicAnalysisResult:
    """Test SystemicAnalysisResult value object."""

    def test_create_result_with_valid_data(self):
        """Test creating a systemic analysis result with valid data."""
        result = SystemicAnalysisResult(
            classification=FailureClassification.ENVIRONMENT_ISSUE,
            confidence=0.75,
            reasoning="Environment setup misconfiguration detected",
            affected_files=("setup.sh", "docker-compose.yml"),
            recommended_action="Rebuild environment",
        )
        assert result.classification == FailureClassification.ENVIRONMENT_ISSUE
        assert result.confidence == 0.75
        assert result.reasoning == "Environment setup misconfiguration detected"
        assert result.affected_files == ("setup.sh", "docker-compose.yml")
        assert result.recommended_action == "Rebuild environment"

    def test_create_result_with_empty_affected_files(self):
        """Test creating a result with empty affected_files tuple."""
        result = SystemicAnalysisResult(
            classification=FailureClassification.TRANSIENT_FAILURE,
            confidence=0.5,
            reasoning="Likely transient network issue",
            affected_files=(),
            recommended_action="Retry without fix",
        )
        assert result.affected_files == ()

    def test_result_immutability_raises_frozen_error(self):
        """Test that frozen dataclass prevents modification."""
        result = SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.9,
            reasoning="Code defect found",
            affected_files=("main.py",),
            recommended_action="Fix code",
        )
        with pytest.raises(FrozenInstanceError):
            result.classification = FailureClassification.ENVIRONMENT_ISSUE  # type: ignore[misc]

        with pytest.raises(FrozenInstanceError):
            result.confidence = 0.95  # type: ignore[misc]

        with pytest.raises(FrozenInstanceError):
            result.reasoning = "Different reasoning"  # type: ignore[misc]

        with pytest.raises(FrozenInstanceError):
            result.recommended_action = "Different action"  # type: ignore[misc]

    def test_confidence_boundary_0_0_passes(self):
        """Test that confidence=0.0 is valid."""
        result = SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.0,
            reasoning="Unknown classification",
            affected_files=(),
            recommended_action="Default action",
        )
        assert result.confidence == 0.0

    def test_confidence_boundary_1_0_passes(self):
        """Test that confidence=1.0 is valid."""
        result = SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=1.0,
            reasoning="Definite classification",
            affected_files=(),
            recommended_action="Action",
        )
        assert result.confidence == 1.0

    def test_confidence_boundary_0_5_passes(self):
        """Test that confidence=0.5 is valid."""
        result = SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.5,
            reasoning="Moderate confidence",
            affected_files=(),
            recommended_action="Action",
        )
        assert result.confidence == 0.5

    def test_confidence_below_0_raises_error(self):
        """Test that confidence < 0.0 raises ValueError."""
        with pytest.raises(ValueError, match="confidence must be between 0.0 and 1.0"):
            SystemicAnalysisResult(
                classification=FailureClassification.CODE_DEFECT,
                confidence=-0.1,
                reasoning="Valid reasoning",
                affected_files=(),
                recommended_action="Action",
            )

    def test_confidence_above_1_raises_error(self):
        """Test that confidence > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="confidence must be between 0.0 and 1.0"):
            SystemicAnalysisResult(
                classification=FailureClassification.CODE_DEFECT,
                confidence=1.1,
                reasoning="Valid reasoning",
                affected_files=(),
                recommended_action="Action",
            )

    def test_invalid_classification_raises_error(self):
        """Test that non-FailureClassification value raises ValueError."""
        with pytest.raises(ValueError, match="classification must be a FailureClassification"):
            SystemicAnalysisResult(
                classification="invalid",  # type: ignore[arg-type]
                confidence=0.5,
                reasoning="Valid reasoning",
                affected_files=(),
                recommended_action="Action",
            )

    def test_empty_reasoning_raises_error(self):
        """Test that empty reasoning raises ValueError."""
        with pytest.raises(ValueError, match="reasoning is required"):
            SystemicAnalysisResult(
                classification=FailureClassification.CODE_DEFECT,
                confidence=0.5,
                reasoning="",
                affected_files=(),
                recommended_action="Action",
            )

    def test_empty_recommended_action_raises_error(self):
        """Test that empty recommended_action raises ValueError."""
        with pytest.raises(ValueError, match="recommended_action is required"):
            SystemicAnalysisResult(
                classification=FailureClassification.CODE_DEFECT,
                confidence=0.5,
                reasoning="Valid reasoning",
                affected_files=(),
                recommended_action="",
            )

    def test_affected_files_tuple_immutable(self):
        """Test that affected_files tuple is immutable."""
        result = SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.9,
            reasoning="Code defect",
            affected_files=("file1.py", "file2.py"),
            recommended_action="Fix code",
        )
        with pytest.raises((TypeError, AttributeError)):
            result.affected_files.append("file3.py")  # type: ignore[attr-defined]

    def test_equality(self):
        """Test value object equality."""
        result1 = SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.9,
            reasoning="Code defect",
            affected_files=("file.py",),
            recommended_action="Fix code",
        )
        result2 = SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.9,
            reasoning="Code defect",
            affected_files=("file.py",),
            recommended_action="Fix code",
        )
        assert result1 == result2

    def test_inequality_different_classification(self):
        """Test value object inequality with different classification."""
        result1 = SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.9,
            reasoning="Code defect",
            affected_files=("file.py",),
            recommended_action="Fix code",
        )
        result2 = SystemicAnalysisResult(
            classification=FailureClassification.ENVIRONMENT_ISSUE,
            confidence=0.9,
            reasoning="Code defect",
            affected_files=("file.py",),
            recommended_action="Fix code",
        )
        assert result1 != result2


# ============================================================================
# AnalysisContext Immutability Tests
# ============================================================================


class TestAnalysisContext:
    """Test AnalysisContext value object."""

    def test_create_context_with_required_fields_only(self):
        """Test creating analysis context with only required fields."""
        context = AnalysisContext(
            work_item_id="WI-123",
            iteration=2,
            workflow_run_id="WR-456",
        )
        assert context.work_item_id == "WI-123"
        assert context.iteration == 2
        assert context.workflow_run_id == "WR-456"
        assert context.prior_fix_attempts == ()
        assert context.prior_classifications == ()

    def test_create_context_with_all_fields(self):
        """Test creating analysis context with all fields."""
        result1 = SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.9,
            reasoning="Previous classification",
            affected_files=(),
            recommended_action="Previous action",
        )
        context = AnalysisContext(
            work_item_id="WI-123",
            iteration=3,
            workflow_run_id="WR-456",
            prior_fix_attempts=("Applied file fix", "Rebuilt environment"),
            prior_classifications=(result1,),
        )
        assert context.work_item_id == "WI-123"
        assert context.iteration == 3
        assert context.workflow_run_id == "WR-456"
        assert len(context.prior_fix_attempts) == 2
        assert len(context.prior_classifications) == 1
        assert context.prior_classifications[0] == result1

    def test_context_immutability_raises_frozen_error(self):
        """Test that frozen dataclass prevents modification."""
        context = AnalysisContext(
            work_item_id="WI-123",
            iteration=1,
            workflow_run_id="WR-456",
        )
        with pytest.raises(FrozenInstanceError):
            context.work_item_id = "WI-999"  # type: ignore[misc]

        with pytest.raises(FrozenInstanceError):
            context.iteration = 5  # type: ignore[misc]

        with pytest.raises(FrozenInstanceError):
            context.workflow_run_id = "WR-999"  # type: ignore[misc]

    def test_empty_work_item_id_raises_error(self):
        """Test that empty work_item_id raises ValueError."""
        with pytest.raises(ValueError, match="work_item_id is required"):
            AnalysisContext(
                work_item_id="",
                iteration=1,
                workflow_run_id="WR-456",
            )

    def test_empty_workflow_run_id_raises_error(self):
        """Test that empty workflow_run_id raises ValueError."""
        with pytest.raises(ValueError, match="workflow_run_id is required"):
            AnalysisContext(
                work_item_id="WI-123",
                iteration=1,
                workflow_run_id="",
            )

    def test_negative_iteration_raises_error(self):
        """Test that negative iteration raises ValueError."""
        with pytest.raises(ValueError, match="iteration must be non-negative"):
            AnalysisContext(
                work_item_id="WI-123",
                iteration=-1,
                workflow_run_id="WR-456",
            )

    def test_zero_iteration_passes(self):
        """Test that iteration=0 is valid."""
        context = AnalysisContext(
            work_item_id="WI-123",
            iteration=0,
            workflow_run_id="WR-456",
        )
        assert context.iteration == 0

    def test_prior_fix_attempts_tuple_immutable(self):
        """Test that prior_fix_attempts tuple is immutable."""
        context = AnalysisContext(
            work_item_id="WI-123",
            iteration=1,
            workflow_run_id="WR-456",
            prior_fix_attempts=("Attempt 1", "Attempt 2"),
        )
        with pytest.raises((TypeError, AttributeError)):
            context.prior_fix_attempts.append("Attempt 3")  # type: ignore[attr-defined]

    def test_prior_classifications_tuple_immutable(self):
        """Test that prior_classifications tuple is immutable."""
        result = SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.9,
            reasoning="Previous",
            affected_files=(),
            recommended_action="Action",
        )
        context = AnalysisContext(
            work_item_id="WI-123",
            iteration=1,
            workflow_run_id="WR-456",
            prior_classifications=(result,),
        )
        with pytest.raises((TypeError, AttributeError)):
            context.prior_classifications.append(result)  # type: ignore[attr-defined]

    def test_equality(self):
        """Test value object equality."""
        context1 = AnalysisContext(
            work_item_id="WI-123",
            iteration=2,
            workflow_run_id="WR-456",
        )
        context2 = AnalysisContext(
            work_item_id="WI-123",
            iteration=2,
            workflow_run_id="WR-456",
        )
        assert context1 == context2

    def test_inequality_different_iteration(self):
        """Test value object inequality with different iteration."""
        context1 = AnalysisContext(
            work_item_id="WI-123",
            iteration=1,
            workflow_run_id="WR-456",
        )
        context2 = AnalysisContext(
            work_item_id="WI-123",
            iteration=2,
            workflow_run_id="WR-456",
        )
        assert context1 != context2

    def test_escalation_support_with_multiple_classifications(self):
        """Test that prior_classifications supports escalation scenarios."""
        # Simulate escalation: first classification, then second based on failed attempt
        result1 = SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.6,
            reasoning="Initial guess: code defect",
            affected_files=("main.py",),
            recommended_action="Fix code",
        )
        result2 = SystemicAnalysisResult(
            classification=FailureClassification.ENVIRONMENT_ISSUE,
            confidence=0.95,
            reasoning="Escalated: environment issue after code fix failed",
            affected_files=(),
            recommended_action="Rebuild environment",
        )
        context = AnalysisContext(
            work_item_id="WI-123",
            iteration=2,
            workflow_run_id="WR-456",
            prior_fix_attempts=("Applied file fix to main.py",),
            prior_classifications=(result1, result2),
        )
        assert len(context.prior_classifications) == 2
        assert context.prior_classifications[0].confidence == 0.6
        assert context.prior_classifications[1].confidence == 0.95
        assert context.prior_classifications[1].classification == FailureClassification.ENVIRONMENT_ISSUE
