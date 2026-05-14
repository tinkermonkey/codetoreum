"""
Expected Sequence Registry

Defines canonical event sequences for different workflow types and provides
pattern matching support for sequence validation.

Pattern Syntax:
- EventType - exact match required
- EventType* - zero or more occurrences
- EventType+ - one or more occurrences
- EventA|EventB - either event type (mutual exclusion)

Example:
    registry = ExpectedSequenceRegistry()
    sequence = registry.get_expected_sequence("standard_workflow")
    # Returns: ["WorkflowCreatedEvent", "WorkflowStartedEvent", "WorkflowStageAdvancedEvent*", ...]
"""

from dataclasses import dataclass


@dataclass
class SequencePattern:
    """Pattern for expected event sequences."""

    name: str
    pattern: list[str]

    def __post_init__(self) -> None:
        """Validate sequence pattern after initialization."""
        if not self.name or not self.name.strip():
            message = "name must be non-empty"
            raise ValueError(message)
        if not self.pattern:
            message = "pattern must be a non-empty list"
            raise ValueError(message)


class ExpectedSequenceRegistry:
    """
    Registry of expected event sequences per workflow type.

    This class defines the canonical sequences of events that should occur
    during different workflow patterns. These sequences are used for:
    - Audit trail validation
    - Anomaly detection
    - Compliance verification
    - Workflow completion verification

    Each sequence uses pattern syntax to support flexible matching:
    - * (zero or more)
    - + (one or more)
    - | (either/or)
    """

    # Base sequences for common workflow patterns
    # Names match CodetoreumEvent subclass names (event_type property = __class__.__name__)
    WORKFLOW_LIFECYCLE = [
        "WorkflowCreatedEvent",
        "WorkflowStartedEvent",
        "WorkflowStageAdvancedEvent*",  # Zero or more stage transitions
        "WorkflowCompletedEvent|WorkflowFailedEvent",  # Terminal state (either)
    ]

    STAGE_EXECUTION = [
        "ExecutionInitializedEvent",
        "ExecutionStartedEvent",
        "ExecutionCompletedEvent|ExecutionFailedEvent|ExecutionTimedOutEvent",
    ]

    REVIEW_CYCLE = [
        "ReviewCycleStartedEvent",
        "ReviewCycleIterationCompletedEvent+",  # One or more iterations
        "ReviewCycleMakerRevisionEvent*",
        "ReviewCycleApproved|ReviewCycleRejectedEvent|ReviewCycleEscalatedToHumanEvent",
    ]

    REPAIR_CYCLE = [
        "RepairCycleStartedEvent",
        "RepairCycleTestExecutionStartedEvent",
        "RepairCycleTestExecutionCompletedEvent|RepairCycleTestCycleCompletedEvent",
        "RepairCycleCompletedEvent",
    ]

    @classmethod
    def get_expected_sequence(cls, workflow_type: str = "default") -> list[str]:
        """
        Get expected sequence for workflow type.

        Combines base patterns based on workflow configuration.
        For now, returns WORKFLOW_LIFECYCLE as default.

        Future enhancement: Derive from workflow configuration dynamically
        to compose sequences from multiple base patterns (e.g., workflow +
        review cycle + repair cycle).

        Args:
            workflow_type: Type of workflow (e.g., "standard_workflow", "review_workflow")

        Returns:
            List of event type patterns in expected order
        """
        # Future: Map workflow_type to specific pattern combinations
        # For now, return base workflow lifecycle
        return cls.WORKFLOW_LIFECYCLE

    @classmethod
    def get_stage_execution_sequence(cls) -> list[str]:
        """
        Get expected sequence for stage execution.

        Returns:
            List of event type patterns for stage execution
        """
        return cls.STAGE_EXECUTION

    @classmethod
    def get_review_cycle_sequence(cls) -> list[str]:
        """
        Get expected sequence for review cycles.

        Returns:
            List of event type patterns for review cycles
        """
        return cls.REVIEW_CYCLE

    @classmethod
    def get_repair_cycle_sequence(cls) -> list[str]:
        """
        Get expected sequence for repair cycles.

        Returns:
            List of event type patterns for repair cycles
        """
        return cls.REPAIR_CYCLE

    @classmethod
    def get_all_patterns(cls) -> list[SequencePattern]:
        """
        Get all available sequence patterns.

        Returns:
            List of all defined sequence patterns
        """
        return [
            SequencePattern(name="workflow_lifecycle", pattern=cls.WORKFLOW_LIFECYCLE),
            SequencePattern(name="stage_execution", pattern=cls.STAGE_EXECUTION),
            SequencePattern(name="review_cycle", pattern=cls.REVIEW_CYCLE),
            SequencePattern(name="repair_cycle", pattern=cls.REPAIR_CYCLE),
        ]
