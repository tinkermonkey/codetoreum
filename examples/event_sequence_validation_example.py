"""
Event Sequence Validation Example

This example demonstrates how to use the EventSequenceValidator to validate
event sequences against expected patterns with pattern matching operators.

Pattern Operators:
- EventType: Exact match (must occur exactly once)
- EventType*: Zero or more occurrences
- EventType+: One or more occurrences
- EventA|EventB: Either event type (mutual exclusion)
"""

from codetoreum.application.event_sequence_validator import EventSequenceValidator
from codetoreum.application.expected_sequence_registry import ExpectedSequenceRegistry


def example_basic_validation():
    """Example: Basic sequence validation."""
    print("=" * 80)
    print("Example 1: Basic Sequence Validation")
    print("=" * 80)

    validator = EventSequenceValidator()

    # Define expected pattern
    pattern = ["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"]

    # Valid sequence
    actual_valid = ["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"]
    result = validator.validate(pattern, actual_valid)

    print(f"Pattern: {pattern}")
    print(f"Actual:  {actual_valid}")
    print(f"Valid:   {result.is_valid}")
    print()

    # Invalid sequence (missing event)
    actual_invalid = ["WorkflowCreated", "WorkflowCompleted"]
    result = validator.validate(pattern, actual_invalid)

    print(f"Pattern: {pattern}")
    print(f"Actual:  {actual_invalid}")
    print(f"Valid:   {result.is_valid}")
    print(f"Missing: {result.missing_events}")
    print()


def example_zero_or_more_operator():
    """Example: Zero or more (*) operator."""
    print("=" * 80)
    print("Example 2: Zero or More (*) Operator")
    print("=" * 80)

    validator = EventSequenceValidator()

    # Pattern with optional events
    pattern = ["WorkflowCreated", "WorkflowStageAdvanced*", "WorkflowCompleted"]

    # Valid with zero occurrences
    actual_zero = ["WorkflowCreated", "WorkflowCompleted"]
    result = validator.validate(pattern, actual_zero)
    print(f"Pattern: {pattern}")
    print(f"Actual:  {actual_zero}")
    print(f"Valid:   {result.is_valid}")
    print()

    # Valid with multiple occurrences
    actual_multiple = [
        "WorkflowCreated",
        "WorkflowStageAdvanced",
        "WorkflowStageAdvanced",
        "WorkflowStageAdvanced",
        "WorkflowCompleted"
    ]
    result = validator.validate(pattern, actual_multiple)
    print(f"Pattern: {pattern}")
    print(f"Actual:  {actual_multiple}")
    print(f"Valid:   {result.is_valid}")
    print()


def example_one_or_more_operator():
    """Example: One or more (+) operator."""
    print("=" * 80)
    print("Example 3: One or More (+) Operator")
    print("=" * 80)

    validator = EventSequenceValidator()

    # Pattern requiring at least one occurrence
    pattern = ["ReviewCycleCreated", "ReviewIterationStarted+", "ReviewCycleApproved"]

    # Invalid with zero occurrences
    actual_zero = ["ReviewCycleCreated", "ReviewCycleApproved"]
    result = validator.validate(pattern, actual_zero)
    print(f"Pattern: {pattern}")
    print(f"Actual:  {actual_zero}")
    print(f"Valid:   {result.is_valid}")
    print(f"Missing: {result.missing_events}")
    print()

    # Valid with one occurrence
    actual_one = ["ReviewCycleCreated", "ReviewIterationStarted", "ReviewCycleApproved"]
    result = validator.validate(pattern, actual_one)
    print(f"Pattern: {pattern}")
    print(f"Actual:  {actual_one}")
    print(f"Valid:   {result.is_valid}")
    print()

    # Valid with multiple occurrences
    actual_multiple = [
        "ReviewCycleCreated",
        "ReviewIterationStarted",
        "ReviewIterationStarted",
        "ReviewIterationStarted",
        "ReviewCycleApproved"
    ]
    result = validator.validate(pattern, actual_multiple)
    print(f"Pattern: {pattern}")
    print(f"Actual:  {actual_multiple}")
    print(f"Valid:   {result.is_valid}")
    print()


def example_either_or_operator():
    """Example: Either/or (|) operator."""
    print("=" * 80)
    print("Example 4: Either/Or (|) Operator")
    print("=" * 80)

    validator = EventSequenceValidator()

    # Pattern with mutually exclusive options
    pattern = ["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted|WorkflowFailed"]

    # Valid with first option
    actual_completed = ["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"]
    result = validator.validate(pattern, actual_completed)
    print(f"Pattern: {pattern}")
    print(f"Actual:  {actual_completed}")
    print(f"Valid:   {result.is_valid}")
    print()

    # Valid with second option
    actual_failed = ["WorkflowCreated", "WorkflowStarted", "WorkflowFailed"]
    result = validator.validate(pattern, actual_failed)
    print(f"Pattern: {pattern}")
    print(f"Actual:  {actual_failed}")
    print(f"Valid:   {result.is_valid}")
    print()

    # Invalid with neither option
    actual_neither = ["WorkflowCreated", "WorkflowStarted", "WorkflowCancelled"]
    result = validator.validate(pattern, actual_neither)
    print(f"Pattern: {pattern}")
    print(f"Actual:  {actual_neither}")
    print(f"Valid:   {result.is_valid}")
    print(f"Missing: {result.missing_events}")
    print(f"Unexpected: {result.unexpected_events}")
    print()


def example_combined_operators():
    """Example: Combining operators."""
    print("=" * 80)
    print("Example 5: Combined Operators")
    print("=" * 80)

    validator = EventSequenceValidator()

    # Complex pattern combining all operators
    pattern = [
        "ReviewCycleCreated",
        "ReviewIterationStarted+",  # One or more required
        "ReviewFeedbackSubmitted*",  # Zero or more optional
        "ReviewCycleApproved|ReviewCycleRejected|ReviewCycleEscalated"  # One of three
    ]

    # Valid sequence
    actual = [
        "ReviewCycleCreated",
        "ReviewIterationStarted",
        "ReviewIterationStarted",
        "ReviewFeedbackSubmitted",
        "ReviewFeedbackSubmitted",
        "ReviewCycleApproved"
    ]
    result = validator.validate(pattern, actual)
    print(f"Pattern: {pattern}")
    print(f"Actual:  {actual}")
    print(f"Valid:   {result.is_valid}")
    print()


def example_using_registry():
    """Example: Using ExpectedSequenceRegistry."""
    print("=" * 80)
    print("Example 6: Using Expected Sequence Registry")
    print("=" * 80)

    validator = EventSequenceValidator()
    registry = ExpectedSequenceRegistry()

    # Get predefined workflow pattern
    pattern = registry.get_expected_sequence("default")
    print(f"Workflow Lifecycle Pattern: {pattern}")
    print()

    # Valid workflow sequence
    actual = [
        "WorkflowCreated",
        "WorkflowStarted",
        "WorkflowStageAdvanced",
        "WorkflowStageAdvanced",
        "WorkflowCompleted"
    ]
    result = validator.validate(pattern, actual)
    print(f"Actual:  {actual}")
    print(f"Valid:   {result.is_valid}")
    print()

    # Get stage execution pattern
    stage_pattern = registry.get_stage_execution_sequence()
    print(f"Stage Execution Pattern: {stage_pattern}")

    stage_actual = ["ExecutionInitialized", "ExecutionStarted", "ExecutionCompleted"]
    result = validator.validate(stage_pattern, stage_actual)
    print(f"Actual:  {stage_actual}")
    print(f"Valid:   {result.is_valid}")
    print()


def example_audit_integration():
    """Example: Creating audit validation results."""
    print("=" * 80)
    print("Example 7: Audit DTO Integration")
    print("=" * 80)

    validator = EventSequenceValidator()

    pattern = ["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"]
    actual = ["WorkflowCreated", "WorkflowCompleted"]  # Missing WorkflowStarted

    # Create audit-compatible validation result
    audit_result = validator.create_audit_validation_result(pattern, actual)

    print("Audit Validation Result:")
    print(f"  sequenceValid: {audit_result['sequenceValid']}")
    print(f"  expectedSequence: {audit_result['expectedSequence']}")
    print(f"  actualSequence: {audit_result['actualSequence']}")
    print(f"  missingEvents: {audit_result['missingEvents']}")
    print(f"  unexpectedEvents: {audit_result['unexpectedEvents']}")
    print(f"  outOfOrderEvents: {audit_result['outOfOrderEvents']}")
    print()


def main():
    """Run all examples."""
    example_basic_validation()
    example_zero_or_more_operator()
    example_one_or_more_operator()
    example_either_or_operator()
    example_combined_operators()
    example_using_registry()
    example_audit_integration()


if __name__ == "__main__":
    main()
