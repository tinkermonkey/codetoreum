"""
Tests for Event Sequence Validator
"""

import pytest
from codetoreum.application.event_sequence_validator import (
    EventSequenceValidator,
    PatternElement,
    PatternOperator,
    ValidationResult,
)


class TestPatternParsing:
    """Tests for pattern parsing."""

    def test_parse_exact_match_pattern(self):
        """Test parsing exact match pattern."""
        validator = EventSequenceValidator()
        elem = validator._parse_pattern("WorkflowCreated")

        assert elem.event_types == ("WorkflowCreated",)
        assert elem.operator == PatternOperator.EXACT
        assert elem.min_occurrences == 1
        assert elem.max_occurrences == 1

    def test_parse_zero_or_more_pattern(self):
        """Test parsing zero or more pattern."""
        validator = EventSequenceValidator()
        elem = validator._parse_pattern("WorkflowStageAdvanced*")

        assert elem.event_types == ("WorkflowStageAdvanced",)
        assert elem.operator == PatternOperator.ZERO_OR_MORE
        assert elem.min_occurrences == 0
        assert elem.max_occurrences is None  # Unlimited

    def test_parse_one_or_more_pattern(self):
        """Test parsing one or more pattern."""
        validator = EventSequenceValidator()
        elem = validator._parse_pattern("ReviewIterationStarted+")

        assert elem.event_types == ("ReviewIterationStarted",)
        assert elem.operator == PatternOperator.ONE_OR_MORE
        assert elem.min_occurrences == 1
        assert elem.max_occurrences is None  # Unlimited

    def test_parse_either_or_pattern(self):
        """Test parsing either/or pattern."""
        validator = EventSequenceValidator()
        elem = validator._parse_pattern("WorkflowCompleted|WorkflowFailed")

        assert "WorkflowCompleted" in elem.event_types
        assert "WorkflowFailed" in elem.event_types
        assert len(elem.event_types) == 2
        assert elem.operator == PatternOperator.EITHER_OR
        assert elem.min_occurrences == 1
        assert elem.max_occurrences == 1

    def test_parse_either_or_with_zero_or_more(self):
        """Test parsing either/or with zero or more."""
        validator = EventSequenceValidator()
        elem = validator._parse_pattern("EventA|EventB*")

        assert "EventA" in elem.event_types
        assert "EventB" in elem.event_types
        assert elem.operator == PatternOperator.ZERO_OR_MORE
        assert elem.min_occurrences == 0
        assert elem.max_occurrences is None

    def test_parse_either_or_with_one_or_more(self):
        """Test parsing either/or with one or more."""
        validator = EventSequenceValidator()
        elem = validator._parse_pattern("EventA|EventB+")

        assert "EventA" in elem.event_types
        assert "EventB" in elem.event_types
        assert elem.operator == PatternOperator.ONE_OR_MORE
        assert elem.min_occurrences == 1
        assert elem.max_occurrences is None

    def test_pattern_cache(self):
        """Test that parsed patterns are cached."""
        validator = EventSequenceValidator()

        # Parse same pattern twice
        elem1 = validator._parse_pattern("WorkflowCreated")
        elem2 = validator._parse_pattern("WorkflowCreated")

        # Should be same object (cached)
        assert elem1 is elem2

    def test_clear_cache(self):
        """Test clearing pattern cache."""
        validator = EventSequenceValidator()

        # Parse and cache pattern
        validator._parse_pattern("WorkflowCreated")
        assert len(validator._pattern_cache) == 1

        # Clear cache
        validator.clear_cache()
        assert len(validator._pattern_cache) == 0


class TestSequenceValidation:
    """Tests for sequence validation."""

    def test_validate_simple_exact_match_sequence(self):
        """Test validating simple exact match sequence."""
        validator = EventSequenceValidator()
        pattern = ["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"]
        actual = ["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"]

        result = validator.validate(pattern, actual)

        assert result.is_valid
        assert len(result.missing_events) == 0
        assert len(result.unexpected_events) == 0
        assert len(result.out_of_order_events) == 0
        assert result.error_message is None

    def test_validate_sequence_with_missing_event(self):
        """Test validation detects missing events."""
        validator = EventSequenceValidator()
        pattern = ["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"]
        actual = ["WorkflowCreated", "WorkflowCompleted"]  # Missing WorkflowStarted

        result = validator.validate(pattern, actual)

        assert not result.is_valid
        assert "WorkflowStarted" in result.missing_events
        assert len(result.unexpected_events) == 0

    def test_validate_sequence_with_unexpected_event(self):
        """Test validation detects unexpected events."""
        validator = EventSequenceValidator()
        pattern = ["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"]
        actual = ["WorkflowCreated", "WorkflowStarted", "UnexpectedEvent", "WorkflowCompleted"]

        result = validator.validate(pattern, actual)

        assert not result.is_valid
        assert "UnexpectedEvent" in result.unexpected_events
        # Note: WorkflowCompleted appears in both missing and unexpected because
        # the unexpected event broke the sequence - we found WorkflowCompleted
        # but not in the right position (after UnexpectedEvent broke the pattern)

    def test_validate_zero_or_more_with_zero_occurrences(self):
        """Test zero or more pattern with zero occurrences."""
        validator = EventSequenceValidator()
        pattern = ["WorkflowCreated", "WorkflowStageAdvanced*", "WorkflowCompleted"]
        actual = ["WorkflowCreated", "WorkflowCompleted"]  # Zero stage advances

        result = validator.validate(pattern, actual)

        assert result.is_valid
        assert len(result.missing_events) == 0
        assert len(result.unexpected_events) == 0

    def test_validate_zero_or_more_with_one_occurrence(self):
        """Test zero or more pattern with one occurrence."""
        validator = EventSequenceValidator()
        pattern = ["WorkflowCreated", "WorkflowStageAdvanced*", "WorkflowCompleted"]
        actual = ["WorkflowCreated", "WorkflowStageAdvanced", "WorkflowCompleted"]

        result = validator.validate(pattern, actual)

        assert result.is_valid
        assert len(result.missing_events) == 0
        assert len(result.unexpected_events) == 0

    def test_validate_zero_or_more_with_multiple_occurrences(self):
        """Test zero or more pattern with multiple occurrences."""
        validator = EventSequenceValidator()
        pattern = ["WorkflowCreated", "WorkflowStageAdvanced*", "WorkflowCompleted"]
        actual = [
            "WorkflowCreated",
            "WorkflowStageAdvanced",
            "WorkflowStageAdvanced",
            "WorkflowStageAdvanced",
            "WorkflowCompleted"
        ]

        result = validator.validate(pattern, actual)

        assert result.is_valid
        assert len(result.missing_events) == 0
        assert len(result.unexpected_events) == 0

    def test_validate_one_or_more_with_zero_occurrences(self):
        """Test one or more pattern with zero occurrences (should fail)."""
        validator = EventSequenceValidator()
        pattern = ["ReviewCycleCreated", "ReviewIterationStarted+", "ReviewCycleApproved"]
        actual = ["ReviewCycleCreated", "ReviewCycleApproved"]  # Missing required iteration

        result = validator.validate(pattern, actual)

        assert not result.is_valid
        assert any("ReviewIterationStarted" in event for event in result.missing_events)

    def test_validate_one_or_more_with_one_occurrence(self):
        """Test one or more pattern with one occurrence."""
        validator = EventSequenceValidator()
        pattern = ["ReviewCycleCreated", "ReviewIterationStarted+", "ReviewCycleApproved"]
        actual = ["ReviewCycleCreated", "ReviewIterationStarted", "ReviewCycleApproved"]

        result = validator.validate(pattern, actual)

        assert result.is_valid
        assert len(result.missing_events) == 0
        assert len(result.unexpected_events) == 0

    def test_validate_one_or_more_with_multiple_occurrences(self):
        """Test one or more pattern with multiple occurrences."""
        validator = EventSequenceValidator()
        pattern = ["ReviewCycleCreated", "ReviewIterationStarted+", "ReviewCycleApproved"]
        actual = [
            "ReviewCycleCreated",
            "ReviewIterationStarted",
            "ReviewIterationStarted",
            "ReviewIterationStarted",
            "ReviewCycleApproved"
        ]

        result = validator.validate(pattern, actual)

        assert result.is_valid
        assert len(result.missing_events) == 0
        assert len(result.unexpected_events) == 0

    def test_validate_either_or_with_first_option(self):
        """Test either/or pattern with first option."""
        validator = EventSequenceValidator()
        pattern = ["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted|WorkflowFailed"]
        actual = ["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"]

        result = validator.validate(pattern, actual)

        assert result.is_valid
        assert len(result.missing_events) == 0
        assert len(result.unexpected_events) == 0

    def test_validate_either_or_with_second_option(self):
        """Test either/or pattern with second option."""
        validator = EventSequenceValidator()
        pattern = ["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted|WorkflowFailed"]
        actual = ["WorkflowCreated", "WorkflowStarted", "WorkflowFailed"]

        result = validator.validate(pattern, actual)

        assert result.is_valid
        assert len(result.missing_events) == 0
        assert len(result.unexpected_events) == 0

    def test_validate_either_or_with_neither_option(self):
        """Test either/or pattern with neither option (should fail)."""
        validator = EventSequenceValidator()
        pattern = ["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted|WorkflowFailed"]
        actual = ["WorkflowCreated", "WorkflowStarted", "WorkflowCancelled"]

        result = validator.validate(pattern, actual)

        assert not result.is_valid
        # Should have missing event (one of the required options)
        assert len(result.missing_events) > 0 or len(result.unexpected_events) > 0


class TestComplexPatterns:
    """Tests for complex pattern combinations."""

    def test_workflow_lifecycle_pattern(self):
        """Test complete workflow lifecycle pattern from registry."""
        validator = EventSequenceValidator()
        pattern = [
            "WorkflowCreated",
            "WorkflowStarted",
            "WorkflowStageAdvanced*",
            "WorkflowCompleted|WorkflowFailed"
        ]

        # Valid sequence with multiple stage advances
        actual = [
            "WorkflowCreated",
            "WorkflowStarted",
            "WorkflowStageAdvanced",
            "WorkflowStageAdvanced",
            "WorkflowCompleted"
        ]

        result = validator.validate(pattern, actual)
        assert result.is_valid

    def test_stage_execution_pattern(self):
        """Test stage execution pattern."""
        validator = EventSequenceValidator()
        pattern = [
            "ExecutionInitialized",
            "ExecutionStarted",
            "ExecutionCompleted|ExecutionFailed|ExecutionTimeout"
        ]

        # Test with completion
        actual_completed = ["ExecutionInitialized", "ExecutionStarted", "ExecutionCompleted"]
        result = validator.validate(pattern, actual_completed)
        assert result.is_valid

        # Test with failure
        actual_failed = ["ExecutionInitialized", "ExecutionStarted", "ExecutionFailed"]
        result = validator.validate(pattern, actual_failed)
        assert result.is_valid

        # Test with timeout
        actual_timeout = ["ExecutionInitialized", "ExecutionStarted", "ExecutionTimeout"]
        result = validator.validate(pattern, actual_timeout)
        assert result.is_valid

    def test_review_cycle_pattern(self):
        """Test review cycle pattern."""
        validator = EventSequenceValidator()
        pattern = [
            "ReviewCycleCreated",
            "ReviewIterationStarted+",
            "ReviewFeedbackSubmitted*",
            "ReviewCycleApproved|ReviewCycleRejected|ReviewCycleEscalated"
        ]

        # Valid with one iteration, no feedback
        actual = [
            "ReviewCycleCreated",
            "ReviewIterationStarted",
            "ReviewCycleApproved"
        ]
        result = validator.validate(pattern, actual)
        assert result.is_valid

        # Valid with multiple iterations and feedback (sequential, not interleaved)
        # Note: The greedy algorithm matches all ReviewIterationStarted+ first,
        # then all ReviewFeedbackSubmitted*, so they must be grouped
        actual_complex = [
            "ReviewCycleCreated",
            "ReviewIterationStarted",
            "ReviewIterationStarted",
            "ReviewFeedbackSubmitted",
            "ReviewFeedbackSubmitted",
            "ReviewFeedbackSubmitted",
            "ReviewCycleApproved"
        ]
        result = validator.validate(pattern, actual_complex)
        assert result.is_valid

    def test_repair_cycle_pattern(self):
        """Test repair cycle pattern."""
        validator = EventSequenceValidator()
        pattern = [
            "RepairCycleCreated",
            "TestExecutionStarted",
            "TestExecutionCompleted|TestExecutionFailed",
            "RepairCycleCompleted|RepairCycleExhausted"
        ]

        # Valid with test completion
        actual = [
            "RepairCycleCreated",
            "TestExecutionStarted",
            "TestExecutionCompleted",
            "RepairCycleCompleted"
        ]
        result = validator.validate(pattern, actual)
        assert result.is_valid

        # Valid with test failure and exhaustion
        actual_exhausted = [
            "RepairCycleCreated",
            "TestExecutionStarted",
            "TestExecutionFailed",
            "RepairCycleExhausted"
        ]
        result = validator.validate(pattern, actual_exhausted)
        assert result.is_valid

    def test_empty_sequence(self):
        """Test validation with empty sequences."""
        validator = EventSequenceValidator()

        # Empty pattern and empty actual
        result = validator.validate([], [])
        assert result.is_valid

        # Empty pattern with events (unexpected events)
        result = validator.validate([], ["Event1", "Event2"])
        assert not result.is_valid
        assert len(result.unexpected_events) > 0

    def test_complex_interleaved_pattern(self):
        """Test complex pattern with interleaved optional events."""
        validator = EventSequenceValidator()
        pattern = [
            "Start",
            "OptionalA*",
            "Middle",
            "OptionalB*",
            "End"
        ]

        # All optional events present
        actual = ["Start", "OptionalA", "OptionalA", "Middle", "OptionalB", "End"]
        result = validator.validate(pattern, actual)
        assert result.is_valid

        # No optional events
        actual_minimal = ["Start", "Middle", "End"]
        result = validator.validate(pattern, actual_minimal)
        assert result.is_valid


class TestValidationResultBooleanContext:
    """Test ValidationResult boolean context."""

    def test_valid_result_is_truthy(self):
        """Test that valid result is truthy."""
        result = ValidationResult(
            is_valid=True,
            missing_events=(),
            unexpected_events=(),
            out_of_order_events=()
        )
        assert result
        assert bool(result) is True

    def test_invalid_result_is_falsy(self):
        """Test that invalid result is falsy."""
        result = ValidationResult(
            is_valid=False,
            missing_events=("Event1",),
            unexpected_events=(),
            out_of_order_events=()
        )
        assert not result
        assert bool(result) is False


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_multiple_alternatives_in_either_or(self):
        """Test either/or with 3+ alternatives."""
        validator = EventSequenceValidator()
        pattern = ["Start", "EventA|EventB|EventC", "End"]

        # Each alternative should work
        for event in ["EventA", "EventB", "EventC"]:
            actual = ["Start", event, "End"]
            result = validator.validate(pattern, actual)
            assert result.is_valid

    def test_pattern_with_whitespace(self):
        """Test pattern parsing with whitespace."""
        validator = EventSequenceValidator()
        elem = validator._parse_pattern("EventA | EventB *")

        # Should strip whitespace from event types
        assert "EventA" in elem.event_types
        assert "EventB" in elem.event_types

    def test_consecutive_optional_patterns(self):
        """Test multiple consecutive optional patterns."""
        validator = EventSequenceValidator()
        pattern = ["Start", "OptA*", "OptB*", "OptC*", "End"]

        # All present
        actual_all = ["Start", "OptA", "OptB", "OptC", "End"]
        result = validator.validate(pattern, actual_all)
        assert result.is_valid

        # None present
        actual_none = ["Start", "End"]
        result = validator.validate(pattern, actual_none)
        assert result.is_valid

        # Some present
        actual_some = ["Start", "OptA", "OptC", "End"]
        result = validator.validate(pattern, actual_some)
        assert result.is_valid


class TestAuditIntegration:
    """Tests for audit DTO integration."""

    def test_create_audit_validation_result_valid(self):
        """Test creating audit validation result for valid sequence."""
        validator = EventSequenceValidator()
        pattern = ["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"]
        actual = ["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"]

        audit_result = validator.create_audit_validation_result(pattern, actual)

        assert audit_result["sequenceValid"] is True
        assert audit_result["expectedSequence"] == pattern
        assert audit_result["actualSequence"] == actual
        assert len(audit_result["missingEvents"]) == 0
        assert len(audit_result["unexpectedEvents"]) == 0
        assert len(audit_result["outOfOrderEvents"]) == 0

    def test_create_audit_validation_result_invalid(self):
        """Test creating audit validation result for invalid sequence."""
        validator = EventSequenceValidator()
        pattern = ["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"]
        actual = ["WorkflowCreated", "WorkflowCompleted"]  # Missing WorkflowStarted

        audit_result = validator.create_audit_validation_result(pattern, actual)

        assert audit_result["sequenceValid"] is False
        assert audit_result["expectedSequence"] == pattern
        assert audit_result["actualSequence"] == actual
        assert "WorkflowStarted" in audit_result["missingEvents"]
        assert len(audit_result["unexpectedEvents"]) == 0

    def test_create_audit_validation_result_with_unexpected(self):
        """Test creating audit validation result with unexpected events."""
        validator = EventSequenceValidator()
        pattern = ["Event1", "Event2"]
        actual = ["Event1", "Event2", "Event3", "Event4"]

        audit_result = validator.create_audit_validation_result(pattern, actual)

        assert audit_result["sequenceValid"] is False
        assert "Event3" in audit_result["unexpectedEvents"]
        assert "Event4" in audit_result["unexpectedEvents"]

    def test_audit_result_structure(self):
        """Test that audit result has correct structure for DTO compatibility."""
        validator = EventSequenceValidator()
        pattern = ["Event1"]
        actual = ["Event1"]

        audit_result = validator.create_audit_validation_result(pattern, actual)

        # Verify all required keys are present
        required_keys = {
            "sequenceValid",
            "expectedSequence",
            "actualSequence",
            "missingEvents",
            "unexpectedEvents",
            "outOfOrderEvents"
        }
        assert set(audit_result.keys()) == required_keys

        # Verify types
        assert isinstance(audit_result["sequenceValid"], bool)
        assert isinstance(audit_result["expectedSequence"], list)
        assert isinstance(audit_result["actualSequence"], list)
        assert isinstance(audit_result["missingEvents"], list)
        assert isinstance(audit_result["unexpectedEvents"], list)
        assert isinstance(audit_result["outOfOrderEvents"], list)


class TestPatternElementValidation:
    """Tests for PatternElement.__post_init__ validation."""

    def test_pattern_element_with_empty_event_types(self):
        """Test that PatternElement rejects empty event_types."""
        with pytest.raises(ValueError, match="event_types must be a non-empty tuple"):
            PatternElement(
                event_types=(),
                operator=PatternOperator.EXACT,
                min_occurrences=1,
                max_occurrences=1
            )

    def test_pattern_element_with_negative_min_occurrences(self):
        """Test that PatternElement rejects negative min_occurrences."""
        with pytest.raises(ValueError, match="min_occurrences must be >= 0"):
            PatternElement(
                event_types=("Event1",),
                operator=PatternOperator.EXACT,
                min_occurrences=-1,
                max_occurrences=1
            )

    def test_pattern_element_with_max_less_than_min(self):
        """Test that PatternElement rejects max_occurrences < min_occurrences."""
        with pytest.raises(ValueError, match="max_occurrences must be >= min_occurrences"):
            PatternElement(
                event_types=("Event1",),
                operator=PatternOperator.EXACT,
                min_occurrences=5,
                max_occurrences=2
            )

    def test_pattern_element_valid_with_none_max(self):
        """Test that PatternElement accepts None for max_occurrences (unlimited)."""
        elem = PatternElement(
            event_types=("Event1",),
            operator=PatternOperator.ZERO_OR_MORE,
            min_occurrences=0,
            max_occurrences=None
        )
        assert elem.max_occurrences is None

    def test_pattern_element_is_frozen(self):
        """Test that PatternElement is immutable (frozen)."""
        elem = PatternElement(
            event_types=("Event1",),
            operator=PatternOperator.EXACT,
            min_occurrences=1,
            max_occurrences=1
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            elem.min_occurrences = 5


class TestValidationResultValidation:
    """Tests for ValidationResult.__post_init__ validation."""

    def test_validation_result_inconsistency_is_valid_true_with_errors(self):
        """Test that ValidationResult rejects is_valid=True with errors present."""
        with pytest.raises(ValueError, match="ValidationResult inconsistency: is_valid=True but errors present"):
            ValidationResult(
                is_valid=True,
                missing_events=("Event1",),  # Error present
                unexpected_events=(),
                out_of_order_events=()
            )

    def test_validation_result_inconsistency_is_valid_false_no_errors(self):
        """Test that ValidationResult rejects is_valid=False with no errors."""
        with pytest.raises(ValueError, match="ValidationResult inconsistency: is_valid=False but no errors present"):
            ValidationResult(
                is_valid=False,
                missing_events=(),
                unexpected_events=(),
                out_of_order_events=(),
                error_message=None
            )

    def test_validation_result_is_valid_false_with_error_message_only(self):
        """Test that ValidationResult accepts is_valid=False with only error_message."""
        result = ValidationResult(
            is_valid=False,
            missing_events=(),
            unexpected_events=(),
            out_of_order_events=(),
            error_message="Custom error message"
        )
        assert not result.is_valid
        assert result.error_message == "Custom error message"

    def test_validation_result_is_frozen(self):
        """Test that ValidationResult is immutable (frozen)."""
        result = ValidationResult(
            is_valid=True,
            missing_events=(),
            unexpected_events=(),
            out_of_order_events=()
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            result.is_valid = False
