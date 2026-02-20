"""
Tests for Expected Sequence Registry
"""

import pytest
from codetoreum.application.expected_sequence_registry import (
    ExpectedSequenceRegistry,
    SequencePattern,
)


class TestExpectedSequenceRegistry:
    """Tests for ExpectedSequenceRegistry."""

    def test_get_expected_sequence_default(self):
        """Test getting default workflow sequence."""
        sequence = ExpectedSequenceRegistry.get_expected_sequence()

        assert sequence == ExpectedSequenceRegistry.WORKFLOW_LIFECYCLE
        assert "WorkflowCreated" in sequence
        assert "WorkflowStarted" in sequence
        assert "WorkflowStageAdvanced*" in sequence
        assert "WorkflowCompleted|WorkflowFailed" in sequence

    def test_get_expected_sequence_with_type(self):
        """Test getting sequence for specific workflow type."""
        # For now, all types return WORKFLOW_LIFECYCLE
        sequence = ExpectedSequenceRegistry.get_expected_sequence("standard_workflow")
        assert sequence == ExpectedSequenceRegistry.WORKFLOW_LIFECYCLE

    def test_workflow_lifecycle_pattern(self):
        """Test workflow lifecycle pattern structure."""
        pattern = ExpectedSequenceRegistry.WORKFLOW_LIFECYCLE

        assert len(pattern) == 4
        assert pattern[0] == "WorkflowCreated"
        assert pattern[1] == "WorkflowStarted"
        assert pattern[2] == "WorkflowStageAdvanced*"  # Zero or more
        assert pattern[3] == "WorkflowCompleted|WorkflowFailed"  # Either/or

    def test_stage_execution_pattern(self):
        """Test stage execution pattern structure."""
        pattern = ExpectedSequenceRegistry.get_stage_execution_sequence()

        assert len(pattern) == 3
        assert pattern[0] == "ExecutionInitialized"
        assert pattern[1] == "ExecutionStarted"
        assert "ExecutionCompleted" in pattern[2]
        assert "ExecutionFailed" in pattern[2]
        assert "ExecutionTimeout" in pattern[2]

    def test_review_cycle_pattern(self):
        """Test review cycle pattern structure."""
        pattern = ExpectedSequenceRegistry.get_review_cycle_sequence()

        assert len(pattern) == 4
        assert pattern[0] == "ReviewCycleCreated"
        assert pattern[1] == "ReviewIterationStarted+"  # One or more
        assert pattern[2] == "ReviewFeedbackSubmitted*"  # Zero or more
        assert "ReviewCycleApproved" in pattern[3]
        assert "ReviewCycleRejected" in pattern[3]
        assert "ReviewCycleEscalated" in pattern[3]

    def test_repair_cycle_pattern(self):
        """Test repair cycle pattern structure."""
        pattern = ExpectedSequenceRegistry.get_repair_cycle_sequence()

        assert len(pattern) == 4
        assert pattern[0] == "RepairCycleCreated"
        assert pattern[1] == "TestExecutionStarted"
        assert "TestExecutionCompleted" in pattern[2]
        assert "TestExecutionFailed" in pattern[2]
        assert "RepairCycleCompleted" in pattern[3]
        assert "RepairCycleExhausted" in pattern[3]

    def test_get_all_patterns(self):
        """Test getting all available patterns."""
        patterns = ExpectedSequenceRegistry.get_all_patterns()

        assert len(patterns) == 4
        assert all(isinstance(p, SequencePattern) for p in patterns)

        pattern_names = [p.name for p in patterns]
        assert "workflow_lifecycle" in pattern_names
        assert "stage_execution" in pattern_names
        assert "review_cycle" in pattern_names
        assert "repair_cycle" in pattern_names

    def test_pattern_contains_zero_or_more_operator(self):
        """Test that patterns correctly use * (zero or more) operator."""
        workflow = ExpectedSequenceRegistry.WORKFLOW_LIFECYCLE
        review = ExpectedSequenceRegistry.REVIEW_CYCLE

        # Workflow has optional stage advances
        assert any("*" in p for p in workflow)
        # Review has optional feedback
        assert any("*" in p for p in review)

    def test_pattern_contains_one_or_more_operator(self):
        """Test that patterns correctly use + (one or more) operator."""
        review = ExpectedSequenceRegistry.REVIEW_CYCLE

        # Review requires at least one iteration
        assert any("+" in p for p in review)

    def test_pattern_contains_either_or_operator(self):
        """Test that patterns correctly use | (either/or) operator."""
        workflow = ExpectedSequenceRegistry.WORKFLOW_LIFECYCLE
        stage = ExpectedSequenceRegistry.STAGE_EXECUTION
        review = ExpectedSequenceRegistry.REVIEW_CYCLE
        repair = ExpectedSequenceRegistry.REPAIR_CYCLE

        # All patterns should have mutually exclusive terminal states
        assert any("|" in p for p in workflow)
        assert any("|" in p for p in stage)
        assert any("|" in p for p in review)
        assert any("|" in p for p in repair)

    def test_sequence_pattern_dataclass(self):
        """Test SequencePattern dataclass."""
        pattern = SequencePattern(
            name="test_pattern",
            pattern=["Event1", "Event2", "Event3"]
        )

        assert pattern.name == "test_pattern"
        assert len(pattern.pattern) == 3
        assert pattern.pattern[0] == "Event1"
