"""Unit tests for PR Review Cycle domain events.

Tests cover:
- Immutability of frozen events
- Dot-notation type strings
- to_dict() / from_dict() round-trip serialization
- __post_init__ validation
- Event inheritance from CodetoreumEvent
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from codetoreum.domain.events.pr_review_cycle_events import (
    PRReviewCycleApprovedEvent,
    PRReviewCycleCICheckCompletedEvent,
    PRReviewCycleCodeReviewStartedEvent,
    PRReviewCycleConsolidationCompletedEvent,
    PRReviewCycleConsolidationStartedEvent,
    PRReviewCycleEscalatedEvent,
    PRReviewCycleIssuesFoundEvent,
    PRReviewCycleMaxCyclesReachedEvent,
    PRReviewCyclePhaseCompletedEvent,
    PRReviewCyclePhaseStartedEvent,
    PRReviewCycleStartedEvent,
    PRReviewCycleVerificationStartedEvent,
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
            work_item_id="work-123",
            cycle_number=1,
            max_outer_cycles=3,
            verifier_context_sources=("parent_issue", "ba_output"),
            phases_planned=4,
            workflow_run_id="run-456",
        )
        assert event.pr_id == "pr-123"
        assert event.work_item_id == "work-123"
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
            work_item_id="work-123",
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
            work_item_id="work-123",
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
            work_item_id="work-123",
            cycle_number=1,
            max_outer_cycles=3,
            verifier_context_sources=("parent_issue", "ba_output"),
            phases_planned=4,
            workflow_run_id="run-456",
        )
        data = event.to_dict()
        assert data["type"] == "pr_review_cycle.started"
        assert data["pr_id"] == "pr-123"
        assert data["work_item_id"] == "work-123"
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
            work_item_id="work-123",
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
        assert restored.work_item_id == original.work_item_id
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
                work_item_id="work-123",
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
                work_item_id="work-123",
                cycle_number=0,
                max_outer_cycles=3,
                verifier_context_sources=("parent_issue",),
                phases_planned=4,
                workflow_run_id="run-456",
            )


class TestPRReviewCyclePhaseStartedEvent:
    """Tests for PRReviewCyclePhaseStartedEvent."""

    def test_create_event(self):
        """Test creating the event."""
        ts = get_iso_timestamp()
        event = PRReviewCyclePhaseStartedEvent(
            type="pr_review_cycle.phase_started",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            phase_name="code_review",
            phase_index=1,
            agent_id="agent-456",
            context_source="pr_diff",
            workflow_run_id="run-789",
        )
        assert event.pr_id == "pr-123"
        assert event.phase_name == "code_review"
        assert event.phase_index == 1
        assert event.agent_id == "agent-456"
        assert event.context_source == "pr_diff"
        assert event.workflow_run_id == "run-789"

    def test_event_immutable(self):
        """Test event is immutable."""
        ts = get_iso_timestamp()
        event = PRReviewCyclePhaseStartedEvent(
            type="pr_review_cycle.phase_started",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            phase_name="code_review",
            phase_index=1,
            agent_id="agent-456",
            context_source="pr_diff",
            workflow_run_id="run-789",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            event.phase_name = "verification"

    def test_to_dict_from_dict_round_trip(self):
        """Test serialization round-trip."""
        ts = get_iso_timestamp()
        event_id = str(uuid4())
        original = PRReviewCyclePhaseStartedEvent(
            type="pr_review_cycle.phase_started",
            timestamp=ts,
            source="mock",
            correlation_id="corr-123",
            event_id=event_id,
            pr_id="pr-123",
            phase_name="verification",
            phase_index=2,
            agent_id="agent-789",
            context_source="parent_issue",
            workflow_run_id="run-456",
        )
        data = original.to_dict()
        restored = PRReviewCyclePhaseStartedEvent.from_dict(data)

        assert restored.type == original.type
        assert restored.timestamp == original.timestamp
        assert restored.source == original.source
        assert restored.correlation_id == original.correlation_id
        assert restored.event_id == original.event_id
        assert restored.pr_id == original.pr_id
        assert restored.phase_name == original.phase_name
        assert restored.phase_index == original.phase_index
        assert restored.agent_id == original.agent_id
        assert restored.context_source == original.context_source
        assert restored.workflow_run_id == original.workflow_run_id

    def test_validation_empty_pr_id(self):
        """Test validation rejects empty pr_id."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="pr_id is required"):
            PRReviewCyclePhaseStartedEvent(
                type="pr_review_cycle.phase_started",
                timestamp=ts,
                source="mock",
                pr_id="",
                phase_name="code_review",
                phase_index=1,
                agent_id="agent-456",
                context_source="pr_diff",
                workflow_run_id="run-789",
            )

    def test_validation_empty_phase_name(self):
        """Test validation rejects empty phase_name."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="phase_name is required"):
            PRReviewCyclePhaseStartedEvent(
                type="pr_review_cycle.phase_started",
                timestamp=ts,
                source="mock",
                pr_id="pr-123",
                phase_name="",
                phase_index=1,
                agent_id="agent-456",
                context_source="pr_diff",
                workflow_run_id="run-789",
            )

    def test_validation_phase_index_min(self):
        """Test validation requires phase_index >= 1."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="phase_index must be >= 1"):
            PRReviewCyclePhaseStartedEvent(
                type="pr_review_cycle.phase_started",
                timestamp=ts,
                source="mock",
                pr_id="pr-123",
                phase_name="code_review",
                phase_index=0,
                agent_id="agent-456",
                context_source="pr_diff",
                workflow_run_id="run-789",
            )

    def test_validation_empty_agent_id(self):
        """Test validation rejects empty agent_id."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="agent_id is required"):
            PRReviewCyclePhaseStartedEvent(
                type="pr_review_cycle.phase_started",
                timestamp=ts,
                source="mock",
                pr_id="pr-123",
                phase_name="code_review",
                phase_index=1,
                agent_id="",
                context_source="pr_diff",
                workflow_run_id="run-789",
            )

    def test_validation_context_source_must_be_string(self):
        """Test validation requires context_source to be a string."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="context_source must be a string"):
            PRReviewCyclePhaseStartedEvent(
                type="pr_review_cycle.phase_started",
                timestamp=ts,
                source="mock",
                pr_id="pr-123",
                phase_name="code_review",
                phase_index=1,
                agent_id="agent-456",
                context_source=None,  # type: ignore
                workflow_run_id="run-789",
            )

    def test_validation_empty_workflow_run_id(self):
        """Test validation rejects empty workflow_run_id."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="workflow_run_id is required"):
            PRReviewCyclePhaseStartedEvent(
                type="pr_review_cycle.phase_started",
                timestamp=ts,
                source="mock",
                pr_id="pr-123",
                phase_name="code_review",
                phase_index=1,
                agent_id="agent-456",
                context_source="pr_diff",
                workflow_run_id="",
            )

    def test_context_source_can_be_empty_string(self):
        """Test context_source can be empty string for CI/consolidation phases."""
        ts = get_iso_timestamp()
        event = PRReviewCyclePhaseStartedEvent(
            type="pr_review_cycle.phase_started",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            phase_name="ci_check",
            phase_index=3,
            agent_id="agent-456",
            context_source="",  # Empty string for CI/consolidation
            workflow_run_id="run-789",
        )
        assert event.context_source == ""


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
            failures_count=0,
            pending_count=0,
            duration_seconds=30.5,
            workflow_run_id="run-456",
        )
        assert event.ci_passed is True
        assert event.failures_count == 0
        assert event.pending_count == 0
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
            failures_count=2,
            pending_count=1,
            duration_seconds=30.5,
            workflow_run_id="run-456",
        )
        assert event.ci_passed is False
        assert event.failures_count == 2
        assert event.pending_count == 1

    def test_to_dict_from_dict_round_trip(self):
        """Test serialization round-trip."""
        ts = get_iso_timestamp()
        original = PRReviewCycleCICheckCompletedEvent(
            type="pr_review_cycle.ci_check_completed",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            ci_passed=False,
            failures_count=2,
            pending_count=1,
            duration_seconds=30.5,
            workflow_run_id="run-456",
        )
        data = original.to_dict()
        restored = PRReviewCycleCICheckCompletedEvent.from_dict(data)
        assert restored.ci_passed == original.ci_passed
        assert restored.failures_count == original.failures_count
        assert restored.pending_count == original.pending_count
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
            total=3,
            critical_count=1,
            high_count=1,
            medium_count=1,
            low_count=0,
            sub_issue_count=3,
            cycle_duration_seconds=600.0,
            next_column="In Development",
            workflow_run_id="run-456",
        )
        assert event.total == 3
        assert event.critical_count == 1
        assert event.high_count == 1
        assert event.medium_count == 1
        assert event.low_count == 0
        assert event.sub_issue_count == 3

    def test_validation_finding_count_min(self):
        """Test finding_count must be >= 1 for issues found."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="total must be >= 1 when issues found"):
            PRReviewCycleIssuesFoundEvent(
                type="pr_review_cycle.issues_found",
                timestamp=ts,
                source="mock",
                pr_id="pr-123",
                cycle_number=1,
                total=0,
                critical_count=0,
                high_count=0,
                medium_count=0,
                low_count=0,
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
            total=3,
            critical_count=1,
            high_count=1,
            medium_count=1,
            low_count=0,
            sub_issue_count=3,
            cycle_duration_seconds=600.0,
            next_column="In Development",
            workflow_run_id="run-456",
        )
        data = original.to_dict()
        restored = PRReviewCycleIssuesFoundEvent.from_dict(data)
        assert restored.total == original.total
        assert restored.critical_count == original.critical_count
        assert restored.high_count == original.high_count
        assert restored.medium_count == original.medium_count
        assert restored.low_count == original.low_count
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
            max_cycles=3,
            next_column="Escalated",
            workflow_run_id="run-456",
        )
        assert event.cycle_number == 4
        assert event.max_cycles == 3

    def test_validation_cycle_number_exceeds_max(self):
        """Test cycle_number must exceed max_cycles."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="cycle_number must exceed max_cycles"):
            PRReviewCycleMaxCyclesReachedEvent(
                type="pr_review_cycle.max_cycles_reached",
                timestamp=ts,
                source="mock",
                pr_id="pr-123",
                cycle_number=3,
                max_cycles=3,
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
            max_cycles=3,
            next_column="Escalated",
            workflow_run_id="run-456",
        )
        data = original.to_dict()
        restored = PRReviewCycleMaxCyclesReachedEvent.from_dict(data)
        assert restored.cycle_number == original.cycle_number
        assert restored.max_cycles == original.max_cycles


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


class TestPRReviewCyclePhaseCompletedEvent:
    """Tests for PRReviewCyclePhaseCompletedEvent."""

    def test_create_event(self):
        """Test creating the event."""
        ts = get_iso_timestamp()
        event = PRReviewCyclePhaseCompletedEvent(
            type="pr_review_cycle.phase_completed",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            phase_name="code_review",
            phase_index=1,
            findings_count=3,
            comment_id="comment-456",
            workflow_run_id="run-456",
        )
        assert event.phase_name == "code_review"
        assert event.phase_index == 1
        assert event.findings_count == 3
        assert event.comment_id == "comment-456"

    def test_event_type_correct(self):
        """Test event type is correct."""
        ts = get_iso_timestamp()
        event = PRReviewCyclePhaseCompletedEvent(
            type="pr_review_cycle.phase_completed",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            phase_name="verification",
            phase_index=2,
            findings_count=1,
            comment_id="",
            workflow_run_id="run-456",
        )
        assert event.type == "pr_review_cycle.phase_completed"

    def test_event_immutable(self):
        """Test event is immutable."""
        ts = get_iso_timestamp()
        event = PRReviewCyclePhaseCompletedEvent(
            type="pr_review_cycle.phase_completed",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            phase_name="code_review",
            phase_index=1,
            findings_count=3,
            comment_id="comment-456",
            workflow_run_id="run-456",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            event.phase_name = "verification"

    def test_validation_phase_index_must_be_positive(self):
        """Test phase_index must be >= 1."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="phase_index must be >= 1"):
            PRReviewCyclePhaseCompletedEvent(
                type="pr_review_cycle.phase_completed",
                timestamp=ts,
                source="mock",
                pr_id="pr-123",
                phase_name="code_review",
                phase_index=0,
                findings_count=3,
                comment_id="comment-456",
                workflow_run_id="run-456",
            )

    def test_to_dict_from_dict_round_trip(self):
        """Test serialization round-trip."""
        ts = get_iso_timestamp()
        original = PRReviewCyclePhaseCompletedEvent(
            type="pr_review_cycle.phase_completed",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            phase_name="verification",
            phase_index=2,
            findings_count=2,
            comment_id="comment-789",
            workflow_run_id="run-456",
        )
        data = original.to_dict()
        restored = PRReviewCyclePhaseCompletedEvent.from_dict(data)
        assert restored.phase_name == original.phase_name
        assert restored.phase_index == original.phase_index
        assert restored.findings_count == original.findings_count
        assert restored.comment_id == original.comment_id


class TestPRReviewCycleConsolidationCompletedEvent:
    """Tests for PRReviewCycleConsolidationCompletedEvent."""

    def test_create_event(self):
        """Test creating the event."""
        ts = get_iso_timestamp()
        event = PRReviewCycleConsolidationCompletedEvent(
            type="pr_review_cycle.consolidation_completed",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            total_findings=5,
            critical_count=2,
            high_count=2,
            medium_count=1,
            low_count=0,
            consolidation_duration_seconds=300.0,
            workflow_run_id="run-456",
        )
        assert event.total_findings == 5
        assert event.critical_count == 2
        assert event.high_count == 2
        assert event.medium_count == 1
        assert event.low_count == 0

    def test_event_type_correct(self):
        """Test event type is correct."""
        ts = get_iso_timestamp()
        event = PRReviewCycleConsolidationCompletedEvent(
            type="pr_review_cycle.consolidation_completed",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            total_findings=0,
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            consolidation_duration_seconds=100.0,
            workflow_run_id="run-456",
        )
        assert event.type == "pr_review_cycle.consolidation_completed"

    def test_event_immutable(self):
        """Test event is immutable."""
        ts = get_iso_timestamp()
        event = PRReviewCycleConsolidationCompletedEvent(
            type="pr_review_cycle.consolidation_completed",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            total_findings=5,
            critical_count=2,
            high_count=2,
            medium_count=1,
            low_count=0,
            consolidation_duration_seconds=300.0,
            workflow_run_id="run-456",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            event.total_findings = 10

    def test_validation_severity_counts_must_sum_to_total(self):
        """Test severity counts must sum to total_findings."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="Severity counts .* must sum to total_findings"):
            PRReviewCycleConsolidationCompletedEvent(
                type="pr_review_cycle.consolidation_completed",
                timestamp=ts,
                source="mock",
                pr_id="pr-123",
                total_findings=5,
                critical_count=2,
                high_count=2,
                medium_count=0,
                low_count=0,  # Sum is 4, not 5
                consolidation_duration_seconds=300.0,
                workflow_run_id="run-456",
            )

    def test_validation_zero_findings_allowed(self):
        """Test zero findings is allowed (when no issues found)."""
        ts = get_iso_timestamp()
        event = PRReviewCycleConsolidationCompletedEvent(
            type="pr_review_cycle.consolidation_completed",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            total_findings=0,
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            consolidation_duration_seconds=100.0,
            workflow_run_id="run-456",
        )
        assert event.total_findings == 0

    def test_to_dict_from_dict_round_trip(self):
        """Test serialization round-trip."""
        ts = get_iso_timestamp()
        original = PRReviewCycleConsolidationCompletedEvent(
            type="pr_review_cycle.consolidation_completed",
            timestamp=ts,
            source="mock",
            pr_id="pr-123",
            total_findings=5,
            critical_count=1,
            high_count=2,
            medium_count=2,
            low_count=0,
            consolidation_duration_seconds=450.0,
            workflow_run_id="run-456",
        )
        data = original.to_dict()
        restored = PRReviewCycleConsolidationCompletedEvent.from_dict(data)
        assert restored.total_findings == original.total_findings
        assert restored.critical_count == original.critical_count
        assert restored.high_count == original.high_count
        assert restored.medium_count == original.medium_count
        assert restored.low_count == original.low_count
        assert restored.consolidation_duration_seconds == original.consolidation_duration_seconds
