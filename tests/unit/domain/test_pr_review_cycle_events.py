"""Unit tests for PR Review Cycle domain events.

Tests cover:
- Immutability of frozen events
- Dot-notation type strings
- to_dict() / from_dict() round-trip serialization
- __post_init__ validation
- Event inheritance from CodetoreumEvent
"""

import pytest
from datetime import UTC, datetime
from uuid import uuid4

from codetoreum.domain.events.pr_review_cycle_events import (
    PRReviewCycleStartedEvent,
    PRReviewCycleCodeReviewStartedEvent,
    PRReviewCycleVerificationStartedEvent,
    PRReviewCycleCICheckCompletedEvent,
    PRReviewCycleConsolidationStartedEvent,
    PRReviewCycleApprovedEvent,
    PRReviewCycleIssuesFoundEvent,
    PRReviewCycleMaxCyclesReachedEvent,
    PRReviewCycleEscalatedEvent,
)


def get_iso_timestamp():
    """Get current timestamp in ISO format."""
    return datetime.now(UTC).isoformat()


class TestPRReviewCycleStartedEvent:
    """Tests for PRReviewCycleStartedEvent."""

    def test_create_event(self):
        """Test creating the event."""
        ts = get_iso_timestamp()
        event = PRReviewCycleStartedEvent(
            type="pr_review_cycle.started",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            cycle_number=1,
            max_outer_cycles=3,
            verifier_context_sources=("parent_issue", "ba_output"),
            phases_planned=4,
            workflow_run_id="run-456",
        )
        assert event.pr_id == "pr-123"
        assert event.cycle_number == 1
        assert event.max_outer_cycles == 3
        assert len(event.verifier_context_sources) == 2
        assert event.phases_planned == 4

    def test_event_type_correct(self):
        """Test event type is correct."""
        ts = get_iso_timestamp()
        event = PRReviewCycleStartedEvent(
            type="pr_review_cycle.started",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            cycle_number=1,
            max_outer_cycles=3,
            verifier_context_sources=("parent_issue",),
            phases_planned=4,
            workflow_run_id="run-456",
        )
        assert event.type == "pr_review_cycle.started"

    def test_event_immutable(self):
        """Test event is immutable."""
        ts = get_iso_timestamp()
        event = PRReviewCycleStartedEvent(
            type="pr_review_cycle.started",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            cycle_number=1,
            max_outer_cycles=3,
            verifier_context_sources=("parent_issue",),
            phases_planned=4,
            workflow_run_id="run-456",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            event.pr_id = "pr-999"

    def test_to_dict(self):
        """Test serialization to dict."""
        ts = get_iso_timestamp()
        event = PRReviewCycleStartedEvent(
            type="pr_review_cycle.started",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            cycle_number=1,
            max_outer_cycles=3,
            verifier_context_sources=("parent_issue", "ba_output"),
            phases_planned=4,
            workflow_run_id="run-456",
        )
        data = event.to_dict()
        assert data["type"] == "pr_review_cycle.started"
        assert data["pr_id"] == "pr-123"
        assert data["cycle_number"] == 1
        assert data["max_outer_cycles"] == 3
        assert data["verifier_context_sources"] == ["parent_issue", "ba_output"]
        assert data["phases_planned"] == 4
        assert data["workflow_run_id"] == "run-456"

    def test_from_dict_round_trip(self):
        """Test from_dict round-trip preserves all fields."""
        ts = get_iso_timestamp()
        event_id = str(uuid4())
        original = PRReviewCycleStartedEvent(
            type="pr_review_cycle.started",
            timestamp=ts,
            source="mock",
            correlation_id="corr-123",
            event_id=event_id,
            pr_id="pr-123",
            cycle_number=1,
            max_outer_cycles=3,
            verifier_context_sources=("parent_issue", "ba_output"),
            phases_planned=4,
            workflow_run_id="run-456",
        )
        data = original.to_dict()
        restored = PRReviewCycleStartedEvent.from_dict(data)

        assert restored.type == original.type
        assert restored.timestamp == original.timestamp
        assert restored.source == original.source
        assert restored.correlation_id == original.correlation_id
        assert restored.event_id == original.event_id
        assert restored.pr_id == original.pr_id
        assert restored.cycle_number == original.cycle_number
        assert restored.max_outer_cycles == original.max_outer_cycles
        assert restored.verifier_context_sources == original.verifier_context_sources
        assert restored.phases_planned == original.phases_planned
        assert restored.workflow_run_id == original.workflow_run_id

    def test_validation_empty_pr_id(self):
        """Test validation rejects empty pr_id."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="pr_id is required"):
            PRReviewCycleStartedEvent(
                type="pr_review_cycle.started",
                timestamp=ts,
                source="mock",
                pr_id="",
                cycle_number=1,
                max_outer_cycles=3,
                verifier_context_sources=("parent_issue",),
                phases_planned=4,
                workflow_run_id="run-456",
            )

    def test_validation_cycle_number_min(self):
        """Test cycle_number must be >= 1."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="cycle_number must be >= 1"):
            PRReviewCycleStartedEvent(
                type="pr_review_cycle.started",
                timestamp=ts,
                source="mock",
                pr_id="pr-123",
                cycle_number=0,
                max_outer_cycles=3,
                verifier_context_sources=("parent_issue",),
                phases_planned=4,
                workflow_run_id="run-456",
            )


class TestPRReviewCycleCodeReviewStartedEvent:
    """Tests for PRReviewCycleCodeReviewStartedEvent."""

    def test_create_event(self):
        """Test creating the event."""
        ts = get_iso_timestamp()
        event = PRReviewCycleCodeReviewStartedEvent(
            type="pr_review_cycle.code_review_started",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            workflow_run_id="run-456",
            timeout_seconds=600,
        )
        assert event.pr_id == "pr-123"
        assert event.timeout_seconds == 600

    def test_to_dict_from_dict_round_trip(self):
        """Test serialization round-trip."""
        ts = get_iso_timestamp()
        original = PRReviewCycleCodeReviewStartedEvent(
            type="pr_review_cycle.code_review_started",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            workflow_run_id="run-456",
            timeout_seconds=600,
        )
        data = original.to_dict()
        restored = PRReviewCycleCodeReviewStartedEvent.from_dict(data)
        assert restored.pr_id == original.pr_id
        assert restored.timeout_seconds == original.timeout_seconds


class TestPRReviewCycleVerificationStartedEvent:
    """Tests for PRReviewCycleVerificationStartedEvent."""

    def test_create_event(self):
        """Test creating the event."""
        ts = get_iso_timestamp()
        event = PRReviewCycleVerificationStartedEvent(
            type="pr_review_cycle.verification_started",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            context_source="parent_issue",
            source_index=1,
            total_sources=2,
            workflow_run_id="run-456",
        )
        assert event.context_source == "parent_issue"
        assert event.source_index == 1
        assert event.total_sources == 2

    def test_validation_source_index_exceeds_total(self):
        """Test source_index cannot exceed total_sources."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="source_index cannot exceed total_sources"):
            PRReviewCycleVerificationStartedEvent(
                type="pr_review_cycle.verification_started",
                timestamp=ts,
                source="mock",
                pr_id="pr-123",
                context_source="parent_issue",
                source_index=3,
                total_sources=2,
                workflow_run_id="run-456",
            )

    def test_to_dict_from_dict_round_trip(self):
        """Test serialization round-trip."""
        ts = get_iso_timestamp()
        original = PRReviewCycleVerificationStartedEvent(
            type="pr_review_cycle.verification_started",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            context_source="parent_issue",
            source_index=1,
            total_sources=2,
            workflow_run_id="run-456",
        )
        data = original.to_dict()
        restored = PRReviewCycleVerificationStartedEvent.from_dict(data)
        assert restored.context_source == original.context_source
        assert restored.source_index == original.source_index
        assert restored.total_sources == original.total_sources


class TestPRReviewCycleCICheckCompletedEvent:
    """Tests for PRReviewCycleCICheckCompletedEvent."""

    def test_create_event_passed(self):
        """Test creating event when CI passed."""
        ts = get_iso_timestamp()
        event = PRReviewCycleCICheckCompletedEvent(
            type="pr_review_cycle.ci_check_completed",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            ci_passed=True,
            duration_seconds=30.5,
            workflow_run_id="run-456",
        )
        assert event.ci_passed is True
        assert event.duration_seconds == 30.5

    def test_create_event_failed(self):
        """Test creating event when CI failed."""
        ts = get_iso_timestamp()
        event = PRReviewCycleCICheckCompletedEvent(
            type="pr_review_cycle.ci_check_completed",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            ci_passed=False,
            duration_seconds=30.5,
            workflow_run_id="run-456",
        )
        assert event.ci_passed is False

    def test_to_dict_from_dict_round_trip(self):
        """Test serialization round-trip."""
        ts = get_iso_timestamp()
        original = PRReviewCycleCICheckCompletedEvent(
            type="pr_review_cycle.ci_check_completed",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            ci_passed=False,
            duration_seconds=30.5,
            workflow_run_id="run-456",
        )
        data = original.to_dict()
        restored = PRReviewCycleCICheckCompletedEvent.from_dict(data)
        assert restored.ci_passed == original.ci_passed
        assert restored.duration_seconds == original.duration_seconds


class TestPRReviewCycleConsolidationStartedEvent:
    """Tests for PRReviewCycleConsolidationStartedEvent."""

    def test_create_event(self):
        """Test creating the event."""
        ts = get_iso_timestamp()
        event = PRReviewCycleConsolidationStartedEvent(
            type="pr_review_cycle.consolidation_started",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            finding_count=5,
            workflow_run_id="run-456",
        )
        assert event.finding_count == 5

    def test_to_dict_from_dict_round_trip(self):
        """Test serialization round-trip."""
        ts = get_iso_timestamp()
        original = PRReviewCycleConsolidationStartedEvent(
            type="pr_review_cycle.consolidation_started",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            finding_count=5,
            workflow_run_id="run-456",
        )
        data = original.to_dict()
        restored = PRReviewCycleConsolidationStartedEvent.from_dict(data)
        assert restored.finding_count == original.finding_count


class TestPRReviewCycleApprovedEvent:
    """Tests for PRReviewCycleApprovedEvent."""

    def test_create_event(self):
        """Test creating the event."""
        ts = get_iso_timestamp()
        event = PRReviewCycleApprovedEvent(
            type="pr_review_cycle.approved",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            cycle_number=1,
            cycle_duration_seconds=600.0,
            next_column="Done",
            workflow_run_id="run-456",
        )
        assert event.pr_id == "pr-123"
        assert event.next_column == "Done"

    def test_to_dict_from_dict_round_trip(self):
        """Test serialization round-trip."""
        ts = get_iso_timestamp()
        original = PRReviewCycleApprovedEvent(
            type="pr_review_cycle.approved",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            cycle_number=1,
            cycle_duration_seconds=600.0,
            next_column="Done",
            workflow_run_id="run-456",
        )
        data = original.to_dict()
        restored = PRReviewCycleApprovedEvent.from_dict(data)
        assert restored.cycle_number == original.cycle_number
        assert restored.next_column == original.next_column


class TestPRReviewCycleIssuesFoundEvent:
    """Tests for PRReviewCycleIssuesFoundEvent."""

    def test_create_event(self):
        """Test creating the event."""
        ts = get_iso_timestamp()
        event = PRReviewCycleIssuesFoundEvent(
            type="pr_review_cycle.issues_found",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            cycle_number=1,
            finding_count=3,
            sub_issue_count=3,
            cycle_duration_seconds=600.0,
            next_column="In Development",
            workflow_run_id="run-456",
        )
        assert event.finding_count == 3
        assert event.sub_issue_count == 3

    def test_validation_finding_count_min(self):
        """Test finding_count must be >= 1 for issues found."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="finding_count must be >= 1"):
            PRReviewCycleIssuesFoundEvent(
                type="pr_review_cycle.issues_found",
                timestamp=ts,
                source="mock",
                pr_id="pr-123",
                cycle_number=1,
                finding_count=0,
                sub_issue_count=0,
                cycle_duration_seconds=600.0,
                next_column="In Development",
                workflow_run_id="run-456",
            )

    def test_to_dict_from_dict_round_trip(self):
        """Test serialization round-trip."""
        ts = get_iso_timestamp()
        original = PRReviewCycleIssuesFoundEvent(
            type="pr_review_cycle.issues_found",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            cycle_number=1,
            finding_count=3,
            sub_issue_count=3,
            cycle_duration_seconds=600.0,
            next_column="In Development",
            workflow_run_id="run-456",
        )
        data = original.to_dict()
        restored = PRReviewCycleIssuesFoundEvent.from_dict(data)
        assert restored.finding_count == original.finding_count
        assert restored.sub_issue_count == original.sub_issue_count


class TestPRReviewCycleMaxCyclesReachedEvent:
    """Tests for PRReviewCycleMaxCyclesReachedEvent."""

    def test_create_event(self):
        """Test creating the event."""
        ts = get_iso_timestamp()
        event = PRReviewCycleMaxCyclesReachedEvent(
            type="pr_review_cycle.max_cycles_reached",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            cycle_number=4,
            max_outer_cycles=3,
            next_column="Escalated",
            workflow_run_id="run-456",
        )
        assert event.cycle_number == 4
        assert event.max_outer_cycles == 3

    def test_validation_cycle_number_exceeds_max(self):
        """Test cycle_number must exceed max_outer_cycles."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="cycle_number must exceed max_outer_cycles"):
            PRReviewCycleMaxCyclesReachedEvent(
                type="pr_review_cycle.max_cycles_reached",
                timestamp=ts,
                source="mock",
                pr_id="pr-123",
                cycle_number=3,
                max_outer_cycles=3,
                next_column="Escalated",
                workflow_run_id="run-456",
            )

    def test_to_dict_from_dict_round_trip(self):
        """Test serialization round-trip."""
        ts = get_iso_timestamp()
        original = PRReviewCycleMaxCyclesReachedEvent(
            type="pr_review_cycle.max_cycles_reached",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            cycle_number=4,
            max_outer_cycles=3,
            next_column="Escalated",
            workflow_run_id="run-456",
        )
        data = original.to_dict()
        restored = PRReviewCycleMaxCyclesReachedEvent.from_dict(data)
        assert restored.cycle_number == original.cycle_number
        assert restored.max_outer_cycles == original.max_outer_cycles


class TestPRReviewCycleEscalatedEvent:
    """Tests for PRReviewCycleEscalatedEvent."""

    def test_create_event(self):
        """Test creating the event."""
        ts = get_iso_timestamp()
        event = PRReviewCycleEscalatedEvent(
            type="pr_review_cycle.escalated",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            reason="max_cycles_reached",
            cycle_number=4,
            workflow_run_id="run-456",
        )
        assert event.reason == "max_cycles_reached"

    def test_to_dict_from_dict_round_trip(self):
        """Test serialization round-trip."""
        ts = get_iso_timestamp()
        original = PRReviewCycleEscalatedEvent(
            type="pr_review_cycle.escalated",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            reason="max_cycles_reached",
            cycle_number=4,
            workflow_run_id="run-456",
        )
        data = original.to_dict()
        restored = PRReviewCycleEscalatedEvent.from_dict(data)
        assert restored.reason == original.reason
        assert restored.cycle_number == original.cycle_number


# Import after class definitions to avoid circular import
from codetoreum.domain.pr_review_cycle_types import PRReviewOutcome
