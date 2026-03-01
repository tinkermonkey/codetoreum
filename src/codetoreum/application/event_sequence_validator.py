"""
Event Sequence Validator

Validates event sequences against expected patterns with support for:
- Exact matching (EventType)
- Zero or more repetitions (EventType*)
- One or more repetitions (EventType+)
- Mutual exclusion (EventA|EventB)

Example:
    validator = EventSequenceValidator()
    pattern = ["WorkflowCreated", "WorkflowStarted", "WorkflowStageAdvanced*", "WorkflowCompleted|WorkflowFailed"]
    actual = ["WorkflowCreated", "WorkflowStarted", "WorkflowStageAdvanced", "WorkflowStageAdvanced", "WorkflowCompleted"]
    result = validator.validate(pattern, actual)
    assert result.is_valid
"""

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class PatternOperator(Enum):
    """Pattern matching operators."""

    EXACT = "exact"  # Exact match
    ZERO_OR_MORE = "*"  # Zero or more occurrences
    ONE_OR_MORE = "+"  # One or more occurrences
    EITHER_OR = "|"  # Mutual exclusion (either/or)


@dataclass(frozen=True)
class PatternElement:
    """Parsed pattern element."""

    event_types: tuple[str, ...]  # Event types (multiple if using |)
    operator: PatternOperator
    min_occurrences: int  # Minimum required occurrences
    max_occurrences: int | None  # Maximum allowed occurrences (None = unlimited)

    def __post_init__(self) -> None:
        """Validate pattern element after initialization."""
        if not self.event_types:
            message = "event_types must be a non-empty tuple"
            raise ValueError(message)
        if self.min_occurrences < 0:
            message = "min_occurrences must be >= 0"
            raise ValueError(message)
        if self.max_occurrences is not None and self.max_occurrences < self.min_occurrences:
            message = "max_occurrences must be >= min_occurrences"
            raise ValueError(message)


@dataclass(frozen=True)
class ValidationResult:
    """Result of sequence validation."""

    is_valid: bool
    missing_events: tuple[str, ...]  # Expected events that didn't occur
    unexpected_events: tuple[str, ...]  # Events that shouldn't have occurred
    out_of_order_events: tuple[tuple[str, int, int], ...]  # NOT IMPLEMENTED - always empty tuple
    error_message: str | None = None

    def __post_init__(self) -> None:
        """Validate consistency of is_valid flag with error lists."""
        # If is_valid is True, all error lists should be empty
        if self.is_valid:
            if self.missing_events or self.unexpected_events or self.out_of_order_events:
                message = (
                    f"ValidationResult inconsistency: is_valid=True but errors present "
                    f"(missing={len(self.missing_events)}, unexpected={len(self.unexpected_events)}, "
                    f"out_of_order={len(self.out_of_order_events)})"
                )
                raise ValueError(message)
        # If is_valid is False, at least one error list or error_message should be present
        elif not (self.missing_events or self.unexpected_events or self.out_of_order_events or self.error_message):
            message = "ValidationResult inconsistency: is_valid=False but no errors present"
            raise ValueError(message)

    def __bool__(self) -> bool:
        """Allow using result in boolean context."""
        return self.is_valid


class EventSequenceValidator:
    """
    Validates event sequences against expected patterns.

    Supports flexible pattern matching with operators:
    - EventType: Exact match (must occur exactly once)
    - EventType*: Zero or more occurrences
    - EventType+: One or more occurrences
    - EventA|EventB: Either event type (mutual exclusion)

    Patterns can be combined:
    - "EventA|EventB*" means zero or more of either EventA or EventB
    - "EventA|EventB+" means one or more of either EventA or EventB
    """

    def __init__(self) -> None:
        """Initialize validator."""
        self._pattern_cache: dict[str, PatternElement] = {}

    def validate(self, expected_pattern: list[str], actual_events: list[str]) -> ValidationResult:
        """
        Validate actual event sequence against expected pattern.

        Uses a greedy matching algorithm that processes events sequentially:
        1. For each pattern element, try to match as many consecutive events as allowed
        2. For * and + operators, consume all matching events before moving to next pattern
        3. For exact matches and |, consume exactly one matching event
        4. Skip optional patterns (*) if no match found
        5. Report error for required patterns (exact, +) if no match found

        Args:
            expected_pattern: List of pattern strings (e.g., ["Event1", "Event2*", "Event3|Event4"])
            actual_events: List of actual event type names in order

        Returns:
            ValidationResult with validation status and details
        """
        # Parse pattern elements
        parsed_pattern = [self._parse_pattern(p) for p in expected_pattern]

        # Track validation state
        pattern_idx = 0
        event_idx = 0
        missing_events_list: list[str] = []
        unexpected_events_list: list[str] = []
        out_of_order_list: list[tuple[str, int, int]] = []

        while pattern_idx < len(parsed_pattern) and event_idx <= len(actual_events):
            pattern_elem = parsed_pattern[pattern_idx]
            matches_found = 0

            # Try to match events against current pattern element
            # Continue matching while events match the pattern
            while event_idx < len(actual_events):
                event_type = actual_events[event_idx]

                # Check if event matches pattern element
                if self._matches_pattern_element(event_type, pattern_elem):
                    matches_found += 1
                    event_idx += 1

                    # For exact match and EITHER_OR, stop after one match
                    if pattern_elem.operator in (PatternOperator.EXACT, PatternOperator.EITHER_OR):
                        break
                    # For + and *, continue consuming matches
                else:
                    # Event doesn't match - stop matching this pattern element
                    break

            # Check if we got minimum required matches
            if matches_found < pattern_elem.min_occurrences:
                # Missing required events
                if pattern_elem.operator == PatternOperator.EITHER_OR:
                    # For either/or, report all alternatives
                    missing_events_list.extend(pattern_elem.event_types)
                else:
                    for event_type in pattern_elem.event_types:
                        if pattern_elem.operator == PatternOperator.ONE_OR_MORE:
                            missing_events_list.append(f"{event_type}+")
                        else:
                            missing_events_list.append(event_type)

            # Check if we exceeded maximum allowed matches
            if pattern_elem.max_occurrences is not None and matches_found > pattern_elem.max_occurrences:
                for event_type in pattern_elem.event_types:
                    unexpected_events_list.append(
                        f"{event_type} (too many occurrences: {matches_found} > {pattern_elem.max_occurrences})"
                    )

            # Move to next pattern element
            pattern_idx += 1

        # Check for unconsumed events (unexpected events remaining)
        while event_idx < len(actual_events):
            unexpected_events_list.append(actual_events[event_idx])
            event_idx += 1

        # Check if we have unprocessed patterns that are required
        while pattern_idx < len(parsed_pattern):
            pattern_elem = parsed_pattern[pattern_idx]
            if pattern_elem.min_occurrences > 0:
                # Missing required pattern
                for event_type in pattern_elem.event_types:
                    if pattern_elem.operator == PatternOperator.ONE_OR_MORE:
                        missing_events_list.append(f"{event_type}+")
                    else:
                        missing_events_list.append(event_type)
            pattern_idx += 1

        is_valid = len(missing_events_list) == 0 and len(unexpected_events_list) == 0 and len(out_of_order_list) == 0

        # Log validation failures for operational monitoring
        if not is_valid:
            logger.warning(
                "Event sequence validation failed",
                extra={
                    "expected_pattern": expected_pattern,
                    "actual_events": actual_events,
                    "missing_events": missing_events_list,
                    "unexpected_events": unexpected_events_list,
                    "out_of_order_events": out_of_order_list,
                },
            )

        return ValidationResult(
            is_valid=is_valid,
            missing_events=tuple(missing_events_list),
            unexpected_events=tuple(unexpected_events_list),
            out_of_order_events=tuple(out_of_order_list),
            error_message=None if is_valid else "Sequence validation failed",
        )

    def _parse_pattern(self, pattern_str: str) -> PatternElement:
        """
        Parse a pattern string into a PatternElement.

        Supports:
        - "EventType" -> exact match
        - "EventType*" -> zero or more
        - "EventType+" -> one or more
        - "EventA|EventB" -> either/or (can combine with * or +)

        Args:
            pattern_str: Pattern string to parse

        Returns:
            Parsed PatternElement
        """
        # Check cache
        if pattern_str in self._pattern_cache:
            return self._pattern_cache[pattern_str]

        # Extract operator suffix (*, +, or none)
        operator = PatternOperator.EXACT
        base_pattern = pattern_str

        if pattern_str.endswith("*"):
            operator = PatternOperator.ZERO_OR_MORE
            base_pattern = pattern_str[:-1]
        elif pattern_str.endswith("+"):
            operator = PatternOperator.ONE_OR_MORE
            base_pattern = pattern_str[:-1]

        # Parse either/or alternatives
        event_types = tuple(et.strip() for et in base_pattern.split("|"))

        # Check if pattern uses either/or (mutual exclusion)
        if len(event_types) > 1:
            # Override operator to EITHER_OR if not already set
            if operator == PatternOperator.EXACT:
                operator = PatternOperator.EITHER_OR

        # Determine min/max occurrences based on operator
        if operator == PatternOperator.EXACT or operator == PatternOperator.EITHER_OR:
            min_occ = 1
            max_occ = 1
        elif operator == PatternOperator.ZERO_OR_MORE:
            min_occ = 0
            max_occ = None  # Unlimited
        elif operator == PatternOperator.ONE_OR_MORE:
            min_occ = 1
            max_occ = None  # Unlimited
        else:
            min_occ = 1
            max_occ = 1

        elem = PatternElement(
            event_types=event_types,
            operator=operator,
            min_occurrences=min_occ,
            max_occurrences=max_occ,
        )

        # Cache for future use
        self._pattern_cache[pattern_str] = elem

        return elem

    def _matches_pattern_element(self, event_type: str, pattern_elem: PatternElement) -> bool:
        """
        Check if an event type matches a pattern element.

        Args:
            event_type: Event type to check
            pattern_elem: Pattern element to match against

        Returns:
            True if event matches pattern element
        """
        return event_type in pattern_elem.event_types

    def clear_cache(self) -> None:
        """Clear the pattern parsing cache."""
        self._pattern_cache.clear()

    def create_audit_validation_result(self, expected_pattern: list[str], actual_events: list[str]) -> dict:
        """
        Create an AuditValidationResult-compatible dictionary.

        This is a convenience method for creating validation results that match
        the AuditValidationResult DTO structure from audit_dtos.py.

        LIMITATION: Out-of-order event detection is NOT IMPLEMENTED in the current
        validator implementation. The outOfOrderEvents field will ALWAYS be an empty
        list, regardless of whether events are actually out of order. The validator
        currently only detects:
        - Missing events (expected but not present)
        - Unexpected events (present but not expected)

        It does NOT detect events that are present but in the wrong sequence position.

        When out-of-order detection is implemented, the timestamp field will need to
        be populated based on actual event timestamps (not currently available to
        this method).

        Args:
            expected_pattern: List of pattern strings
            actual_events: List of actual event type names

        Returns:
            Dictionary with keys: sequenceValid, expectedSequence, actualSequence,
            missingEvents, unexpectedEvents, outOfOrderEvents (always empty)
        """
        result = self.validate(expected_pattern, actual_events)

        # Note: Out-of-order detection currently returns empty list
        # When implemented, each tuple will need to include timestamp
        return {
            "sequenceValid": result.is_valid,
            "expectedSequence": expected_pattern,
            "actualSequence": actual_events,
            "missingEvents": list(result.missing_events),
            "unexpectedEvents": list(result.unexpected_events),
            "outOfOrderEvents": [
                {
                    "eventType": event_type,
                    "expectedPosition": expected_pos,
                    "actualPosition": actual_pos,
                }
                for event_type, expected_pos, actual_pos in result.out_of_order_events
            ],
        }
