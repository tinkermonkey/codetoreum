"""Unit tests for PR Review Cycle domain types.

Tests cover:
- Immutability of frozen dataclasses
- Mutable state of PRReviewCycleState
- Default values
- __post_init__ validation
- Consistency checks
"""

from datetime import UTC, datetime
from typing import cast

import pytest

from codetoreum.domain.pr_review_cycle_types import (
    PRReviewCycleConfig,
    PRReviewCycleResult,
    PRReviewCycleState,
    PRReviewFinding,
    PRReviewOutcome,
    PRReviewPhaseOutput,
    PRReviewStatus,
)


class TestPRReviewOutcome:
    """Tests for PRReviewOutcome enum."""

    def test_enum_values(self):
        """Test enum has correct values."""
        assert PRReviewOutcome.ISSUES_FOUND.value == "issues_found"
        assert PRReviewOutcome.APPROVED.value == "approved"
        assert PRReviewOutcome.MAX_CYCLES_REACHED.value == "max_cycles"

    def test_enum_serializable(self):
        """Test enum is serializable (str, Enum)."""
        outcome = PRReviewOutcome.APPROVED
        assert isinstance(outcome, str)
        # String representation includes the enum member name
        assert str(outcome) == "PRReviewOutcome.APPROVED"
        # But the value is the lowercase snake_case
        # Cast back to Enum to access .value
        assert cast("PRReviewOutcome", outcome).value == "approved"


class TestPRReviewStatus:
    """Tests for PRReviewStatus enum."""

    def test_enum_values(self):
        """Test enum has all seven values."""
        assert PRReviewStatus.PENDING.value == "pending"
        assert PRReviewStatus.PHASE_1_CODE_REVIEW.value == "phase_1_code_review"
        assert PRReviewStatus.PHASE_2_VERIFICATION.value == "phase_2_verification"
        assert PRReviewStatus.PHASE_3_CI_CHECK.value == "phase_3_ci_check"
        assert PRReviewStatus.PHASE_4_CONSOLIDATION.value == "phase_4_consolidation"
        assert PRReviewStatus.COMPLETED.value == "completed"
        assert PRReviewStatus.ESCALATED.value == "escalated"


class TestPRReviewFinding:
    """Tests for PRReviewFinding frozen dataclass."""

    def test_create_valid_finding(self):
        """Test creating a valid finding."""
        finding = PRReviewFinding(
            title="Null pointer exception",
            description="Missing null check before accessing variable",
            severity="high",
            phase="code_review",
            context_source="pr_diff",
        )
        assert finding.title == "Null pointer exception"
        assert finding.description == "Missing null check before accessing variable"
        assert finding.severity == "high"
        assert finding.phase == "code_review"
        assert finding.context_source == "pr_diff"

    def test_finding_immutable(self):
        """Test finding is immutable (frozen)."""
        finding = PRReviewFinding(
            title="Issue",
            description="Issue description",
            severity="high",
            phase="verification",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            finding.severity = "low"

    def test_finding_without_context_source(self):
        """Test finding without context source."""
        finding = PRReviewFinding(
            title="General issue",
            description="A general finding",
            severity="low",
            phase="code_review",
            context_source=None,
        )
        assert finding.context_source is None

    def test_finding_invalid_severity(self):
        """Test finding rejects invalid severity."""
        with pytest.raises(ValueError, match="severity must be one of"):
            PRReviewFinding(
                title="Issue",
                description="Description",
                severity="invalid",
                phase="code_review",
            )

    def test_finding_empty_title(self):
        """Test finding rejects empty title."""
        with pytest.raises(ValueError, match="title is required"):
            PRReviewFinding(
                title="",
                description="Description",
                severity="high",
                phase="code_review",
            )

    def test_finding_empty_description(self):
        """Test finding rejects empty description."""
        with pytest.raises(ValueError, match="description is required"):
            PRReviewFinding(
                title="Issue",
                description="",
                severity="high",
                phase="code_review",
            )

    def test_finding_empty_severity(self):
        """Test finding rejects empty severity."""
        with pytest.raises(ValueError, match="severity is required"):
            PRReviewFinding(
                title="Issue",
                description="Description",
                severity="",
                phase="code_review",
            )

    def test_finding_empty_phase(self):
        """Test finding rejects empty phase."""
        with pytest.raises(ValueError, match="phase is required"):
            PRReviewFinding(
                title="Issue",
                description="Description",
                severity="high",
                phase="",
            )


class TestPRReviewPhaseOutput:
    """Tests for PRReviewPhaseOutput frozen dataclass."""

    def test_create_successful_phase(self):
        """Test creating output for successful phase."""
        findings = (PRReviewFinding(title="Bug", description="A bug", severity="high", phase="code_review"),)
        output = PRReviewPhaseOutput(
            phase_name="code_review",
            phase_index=1,
            success=True,
            findings=findings,
            summary="Found 1 issue",
            duration_seconds=600.5,
            context_source="pr_diff",
            comment_id="comment-123",
        )
        assert output.phase_name == "code_review"
        assert output.phase_index == 1
        assert output.success is True
        assert len(output.findings) == 1
        assert output.summary == "Found 1 issue"
        assert output.duration_seconds == 600.5
        assert output.context_source == "pr_diff"
        assert output.comment_id == "comment-123"
        assert output.error is None

    def test_create_failed_phase(self):
        """Test creating output for failed phase."""
        output = PRReviewPhaseOutput(
            phase_name="ci_check",
            phase_index=3,
            success=False,
            findings=(),
            summary="CI failed",
            duration_seconds=10.0,
            error="Connection timeout",
        )
        assert output.success is False
        assert output.error == "Connection timeout"
        assert output.phase_index == 3

    def test_phase_output_immutable(self):
        """Test phase output is immutable."""
        output = PRReviewPhaseOutput(
            phase_name="code_review",
            phase_index=1,
            success=True,
            findings=(),
            summary="OK",
            duration_seconds=0.0,
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            output.phase_name = "verification"

    def test_phase_output_empty_phase_name(self):
        """Test rejects empty phase name."""
        with pytest.raises(ValueError, match="phase_name is required"):
            PRReviewPhaseOutput(
                phase_name="",
                phase_index=1,
                success=True,
                findings=(),
                summary="OK",
                duration_seconds=0.0,
            )

    def test_phase_output_zero_phase_index(self):
        """Test accepts phase_index=0 (valid sentinel for non-Phase 2 phases)."""
        output = PRReviewPhaseOutput(
            phase_name="code_review",
            phase_index=0,
            success=True,
            findings=(),
            summary="OK",
            duration_seconds=0.0,
        )
        assert output.phase_index == 0

    def test_phase_output_invalid_negative_phase_index(self):
        """Test rejects negative phase index."""
        with pytest.raises(ValueError, match="phase_index must be >= 0"):
            PRReviewPhaseOutput(
                phase_name="code_review",
                phase_index=-1,
                success=True,
                findings=(),
                summary="OK",
                duration_seconds=0.0,
            )

    def test_phase_output_empty_summary(self):
        """Test rejects empty summary."""
        with pytest.raises(ValueError, match="summary is required"):
            PRReviewPhaseOutput(
                phase_name="code_review",
                phase_index=1,
                success=True,
                findings=(),
                summary="",
                duration_seconds=0.0,
            )

    def test_phase_output_negative_duration(self):
        """Test rejects negative duration."""
        with pytest.raises(ValueError, match="duration_seconds must be non-negative"):
            PRReviewPhaseOutput(
                phase_name="code_review",
                phase_index=1,
                success=True,
                findings=(),
                summary="OK",
                duration_seconds=-1.0,
            )

    def test_phase_output_success_without_error_consistency(self):
        """Test success=True cannot have error set."""
        with pytest.raises(ValueError, match="success=True but error is set"):
            PRReviewPhaseOutput(
                phase_name="code_review",
                phase_index=1,
                success=True,
                findings=(),
                summary="OK",
                duration_seconds=0.0,
                error="Some error",
            )

    def test_phase_output_failure_without_error_consistency(self):
        """Test success=False must have error."""
        with pytest.raises(ValueError, match="success=False but error is not set"):
            PRReviewPhaseOutput(
                phase_name="code_review",
                phase_index=1,
                success=False,
                findings=(),
                summary="Failed",
                duration_seconds=0.0,
            )


class TestPRReviewCycleConfig:
    """Tests for PRReviewCycleConfig frozen dataclass."""

    def test_create_with_defaults(self):
        """Test creating config with default values (required fields provided)."""
        config = PRReviewCycleConfig(
            code_review_agent="agent-1",
            verifier_agent="agent-2",
            consolidation_agent="agent-3",
            on_issues_found_column="Review",
            on_approved_column="Done",
        )
        assert config.max_outer_cycles == 3
        assert config.verifier_context_sources == ("parent_issue",)
        assert config.code_review_timeout_seconds == 600
        assert config.verification_timeout_seconds == 300
        assert config.ci_check_enabled is True
        assert config.ci_check_timeout_seconds == 300
        assert config.consolidation_timeout_seconds == 600
        assert config.sub_issue_creation is True
        assert config.sub_issue_labels == ()

    def test_create_with_custom_values(self):
        """Test creating config with custom values."""
        config = PRReviewCycleConfig(
            max_outer_cycles=5,
            verifier_context_sources=("parent_issue", "ba_output", "arch_spec"),
            code_review_timeout_seconds=900,
            verification_timeout_seconds=600,
            ci_check_enabled=True,
            ci_check_timeout_seconds=600,
            consolidation_timeout_seconds=1200,
            sub_issue_creation=True,
            sub_issue_labels=("bug", "enhancement"),
            sub_issue_initial_column="Backlog",
            code_review_agent="agent-1",
            verifier_agent="agent-2",
            consolidation_agent="agent-3",
            on_issues_found_column="Review",
            on_approved_column="Done",
        )
        assert config.max_outer_cycles == 5
        assert config.verifier_context_sources == ("parent_issue", "ba_output", "arch_spec")
        assert config.code_review_timeout_seconds == 900
        assert config.sub_issue_labels == ("bug", "enhancement")
        assert config.sub_issue_initial_column == "Backlog"
        assert config.code_review_agent == "agent-1"
        assert config.verifier_agent == "agent-2"
        assert config.consolidation_agent == "agent-3"

    def test_config_immutable(self):
        """Test config is immutable."""
        config = PRReviewCycleConfig(
            code_review_agent="agent-1",
            verifier_agent="agent-2",
            consolidation_agent="agent-3",
            on_issues_found_column="Review",
            on_approved_column="Done",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            config.max_outer_cycles = 2

    def test_config_max_outer_cycles_min(self):
        """Test max_outer_cycles must be >= 1."""
        with pytest.raises(ValueError, match="max_outer_cycles must be >= 1"):
            PRReviewCycleConfig(
                max_outer_cycles=0,
                code_review_agent="agent-1",
                verifier_agent="agent-2",
                consolidation_agent="agent-3",
                on_issues_found_column="Review",
                on_approved_column="Done",
            )

    def test_config_verifier_context_sources_empty(self):
        """Test verifier_context_sources must not be empty."""
        with pytest.raises(ValueError, match="verifier_context_sources must not be empty"):
            PRReviewCycleConfig(
                verifier_context_sources=(),
                code_review_agent="agent-1",
                verifier_agent="agent-2",
                consolidation_agent="agent-3",
                on_issues_found_column="Review",
                on_approved_column="Done",
            )

    def test_config_sub_issue_labels_tuple(self):
        """Test sub_issue_labels must be a tuple."""
        with pytest.raises(ValueError, match="sub_issue_labels must be a tuple"):
            PRReviewCycleConfig(
                sub_issue_labels=["bug", "enhancement"],
                code_review_agent="agent-1",
                verifier_agent="agent-2",
                consolidation_agent="agent-3",
                on_issues_found_column="Review",
                on_approved_column="Done",
            )

    def test_config_explicit_agent_fields(self):
        """Test agent fields are explicit and required."""
        # Spec requires three explicit named fields for agents
        config = PRReviewCycleConfig(
            code_review_agent="agent-1",
            verifier_agent="agent-2",
            consolidation_agent="agent-3",
            on_issues_found_column="Issues",
            on_approved_column="Done",
        )
        assert config.code_review_agent == "agent-1"
        assert config.verifier_agent == "agent-2"
        assert config.consolidation_agent == "agent-3"

    def test_config_ci_check_timeout_validation_when_enabled(self):
        """Test ci_check_timeout_seconds must be > 0 when ci_check_enabled=True."""
        with pytest.raises(ValueError, match="ci_check_timeout_seconds must be > 0"):
            PRReviewCycleConfig(
                ci_check_enabled=True,
                ci_check_timeout_seconds=0,
                code_review_agent="agent-1",
                verifier_agent="agent-2",
                consolidation_agent="agent-3",
                on_issues_found_column="Review",
                on_approved_column="Done",
            )

    def test_config_ci_check_timeout_validation_when_disabled(self):
        """Test ci_check_timeout_seconds ignored when ci_check_enabled=False."""
        # Should not raise even with ci_check_timeout_seconds=0
        config = PRReviewCycleConfig(
            ci_check_enabled=False,
            ci_check_timeout_seconds=0,
            code_review_agent="agent-1",
            verifier_agent="agent-2",
            consolidation_agent="agent-3",
            on_issues_found_column="Review",
            on_approved_column="Done",
        )
        assert config.ci_check_timeout_seconds == 0

    def test_config_code_review_timeout_positive(self):
        """Test code_review_timeout_seconds must be > 0."""
        with pytest.raises(ValueError, match="code_review_timeout_seconds must be > 0"):
            PRReviewCycleConfig(
                code_review_timeout_seconds=0,
                code_review_agent="agent-1",
                verifier_agent="agent-2",
                consolidation_agent="agent-3",
                on_issues_found_column="Review",
                on_approved_column="Done",
            )

    def test_config_verification_timeout_positive(self):
        """Test verification_timeout_seconds must be > 0."""
        with pytest.raises(ValueError, match="verification_timeout_seconds must be > 0"):
            PRReviewCycleConfig(
                verification_timeout_seconds=0,
                code_review_agent="agent-1",
                verifier_agent="agent-2",
                consolidation_agent="agent-3",
                on_issues_found_column="Review",
                on_approved_column="Done",
            )

    def test_config_consolidation_timeout_positive(self):
        """Test consolidation_timeout_seconds must be > 0."""
        with pytest.raises(ValueError, match="consolidation_timeout_seconds must be > 0"):
            PRReviewCycleConfig(
                consolidation_timeout_seconds=0,
                code_review_agent="agent-1",
                verifier_agent="agent-2",
                consolidation_agent="agent-3",
                on_issues_found_column="Review",
                on_approved_column="Done",
            )


class TestPRReviewCycleResult:
    """Tests for PRReviewCycleResult frozen dataclass."""

    def test_create_approved_result(self):
        """Test creating an approved result."""
        phase_output = PRReviewPhaseOutput(
            phase_name="code_review",
            phase_index=1,
            success=True,
            findings=(),
            summary="Approved",
            duration_seconds=600.0,
        )
        result = PRReviewCycleResult(
            cycle_number=1,
            workflow_run_id="run-123",
            outcome=PRReviewOutcome.APPROVED,
            phase_outputs=(phase_output,),
            all_findings=(),
            sub_issues_created=(),
            ci_passed=True,
            total_findings=0,
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            total_duration_seconds=600.0,
            timestamp=datetime.now(UTC).isoformat(),
            next_column="Done",
        )
        assert result.outcome == PRReviewOutcome.APPROVED
        assert result.sub_issues_created == ()
        assert result.ci_passed is True
        assert result.total_findings == 0

    def test_create_issues_found_result(self):
        """Test creating a result with issues found."""
        finding = PRReviewFinding(title="Bug", description="A bug", severity="high", phase="code_review")
        phase_output = PRReviewPhaseOutput(
            phase_name="code_review",
            phase_index=1,
            success=True,
            findings=(finding,),
            summary="Found 1 issue",
            duration_seconds=600.0,
        )
        result = PRReviewCycleResult(
            cycle_number=1,
            workflow_run_id="run-123",
            outcome=PRReviewOutcome.ISSUES_FOUND,
            phase_outputs=(phase_output,),
            all_findings=(finding,),
            sub_issues_created=("issue-1", "issue-2"),
            ci_passed=False,
            total_findings=1,
            critical_count=0,
            high_count=1,
            medium_count=0,
            low_count=0,
            total_duration_seconds=600.0,
            timestamp=datetime.now(UTC).isoformat(),
            next_column="In Development",
        )
        assert result.outcome == PRReviewOutcome.ISSUES_FOUND
        assert len(result.sub_issues_created) == 2
        assert result.high_count == 1
        assert result.total_findings == 1

    def test_result_immutable(self):
        """Test result is immutable."""
        phase_output = PRReviewPhaseOutput(
            phase_name="code_review",
            phase_index=1,
            success=True,
            findings=(),
            summary="OK",
            duration_seconds=0.0,
        )
        result = PRReviewCycleResult(
            cycle_number=1,
            workflow_run_id="run-123",
            outcome=PRReviewOutcome.APPROVED,
            phase_outputs=(phase_output,),
            all_findings=(),
            sub_issues_created=(),
            ci_passed=True,
            total_findings=0,
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            total_duration_seconds=0.0,
            timestamp=datetime.now(UTC).isoformat(),
            next_column="Done",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            result.cycle_number = 2

    def test_result_severity_counts_validation(self):
        """Test severity counts must sum to total_findings."""
        phase_output = PRReviewPhaseOutput(
            phase_name="code_review",
            phase_index=1,
            success=True,
            findings=(),
            summary="OK",
            duration_seconds=0.0,
        )
        with pytest.raises(ValueError, match="Severity counts .* must sum to total_findings"):
            PRReviewCycleResult(
                cycle_number=1,
                workflow_run_id="run-123",
                outcome=PRReviewOutcome.APPROVED,
                phase_outputs=(phase_output,),
                all_findings=(),
                sub_issues_created=(),
                ci_passed=True,
                total_findings=2,  # Mismatched with severity counts (0)
                critical_count=0,
                high_count=0,
                medium_count=0,
                low_count=0,
                total_duration_seconds=0.0,
                timestamp=datetime.now(UTC).isoformat(),
                next_column="Done",
            )

    def test_result_total_findings_matches_all_findings_length(self):
        """Test total_findings must match len(all_findings)."""
        finding = PRReviewFinding(title="Bug", description="A bug", severity="high", phase="code_review")
        phase_output = PRReviewPhaseOutput(
            phase_name="code_review",
            phase_index=1,
            success=True,
            findings=(finding,),
            summary="Found 1 issue",
            duration_seconds=600.0,
        )
        # total_findings (2) doesn't match len(all_findings) (1)
        # Severity counts must sum to total_findings, so we need to make them match
        with pytest.raises(ValueError, match="total_findings .* must match len\\(all_findings\\)"):
            PRReviewCycleResult(
                cycle_number=1,
                workflow_run_id="run-123",
                outcome=PRReviewOutcome.ISSUES_FOUND,
                phase_outputs=(phase_output,),
                all_findings=(finding,),
                sub_issues_created=("issue-1",),
                ci_passed=False,
                total_findings=2,  # Mismatched with actual findings count (1)
                critical_count=0,
                high_count=2,  # Severity counts sum to 2 (matching total_findings)
                medium_count=0,
                low_count=0,
                total_duration_seconds=600.0,
                timestamp=datetime.now(UTC).isoformat(),
                next_column="In Development",
            )

    def test_result_issues_found_allows_empty_sub_issues(self):
        """Test ISSUES_FOUND outcome allows empty sub_issue_ids when sub_issue_creation is disabled."""
        phase_output = PRReviewPhaseOutput(
            phase_name="code_review",
            phase_index=1,
            success=True,
            findings=(),
            summary="OK",
            duration_seconds=0.0,
        )
        # Should not raise - sub_issue_ids can be empty if sub-issue creation is disabled
        result = PRReviewCycleResult(
            cycle_number=1,
            workflow_run_id="run-123",
            outcome=PRReviewOutcome.ISSUES_FOUND,
            phase_outputs=(phase_output,),
            all_findings=(),
            sub_issues_created=(),
            ci_passed=False,
            total_findings=0,
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            total_duration_seconds=0.0,
            timestamp=datetime.now(UTC).isoformat(),
            next_column="In Development",
        )
        assert result.outcome == PRReviewOutcome.ISSUES_FOUND
        assert result.sub_issues_created == ()

    def test_result_approved_forbids_sub_issues(self):
        """Test APPROVED outcome forbids sub_issue_ids."""
        phase_output = PRReviewPhaseOutput(
            phase_name="code_review",
            phase_index=1,
            success=True,
            findings=(),
            summary="OK",
            duration_seconds=0.0,
        )
        with pytest.raises(ValueError, match="outcome=APPROVED but sub_issues_created is non-empty"):
            PRReviewCycleResult(
                cycle_number=1,
                workflow_run_id="run-123",
                outcome=PRReviewOutcome.APPROVED,
                phase_outputs=(phase_output,),
                all_findings=(),
                sub_issues_created=("issue-1",),
                ci_passed=True,
                total_findings=0,
                critical_count=0,
                high_count=0,
                medium_count=0,
                low_count=0,
                total_duration_seconds=0.0,
                timestamp=datetime.now(UTC).isoformat(),
                next_column="Done",
            )

    def test_result_cycle_number_min(self):
        """Test cycle_number must be >= 1."""
        phase_output = PRReviewPhaseOutput(
            phase_name="code_review",
            phase_index=1,
            success=True,
            findings=(),
            summary="OK",
            duration_seconds=0.0,
        )
        with pytest.raises(ValueError, match="cycle_number must be >= 1"):
            PRReviewCycleResult(
                cycle_number=0,
                workflow_run_id="run-123",
                outcome=PRReviewOutcome.APPROVED,
                phase_outputs=(phase_output,),
                all_findings=(),
                sub_issues_created=(),
                ci_passed=True,
                total_findings=0,
                critical_count=0,
                high_count=0,
                medium_count=0,
                low_count=0,
                total_duration_seconds=0.0,
                timestamp=datetime.now(UTC).isoformat(),
                next_column="Done",
            )


class TestPRReviewCycleState:
    """Tests for PRReviewCycleState mutable dataclass."""

    @staticmethod
    def _create_test_config() -> "PRReviewCycleConfig":
        """Create a minimal config for testing."""
        return PRReviewCycleConfig(
            code_review_agent="agent-1",
            verifier_agent="agent-2",
            consolidation_agent="agent-3",
            on_issues_found_column="Review",
            on_approved_column="Done",
        )

    def test_create_state(self):
        """Test creating mutable state."""
        now = datetime.now(UTC)
        config = self._create_test_config()
        state = PRReviewCycleState(
            id="cycle-123",
            pr_id="pr-456",
            work_item_id="item-789",
            project_id="proj-101",
            board_id="board-202",
            status=PRReviewStatus.PHASE_1_CODE_REVIEW,
            cycle_number=1,
            current_phase="code_review",
            findings=[],
            phase_outputs=[],
            config=config,
            started_at=now,
            updated_at=now,
        )
        assert state.id == "cycle-123"
        assert state.pr_id == "pr-456"
        assert state.work_item_id == "item-789"
        assert state.project_id == "proj-101"
        assert state.board_id == "board-202"
        assert state.status == PRReviewStatus.PHASE_1_CODE_REVIEW
        assert state.findings == []
        assert state.phase_outputs == []
        assert state.config == config

    def test_state_mutable(self):
        """Test state is mutable (not frozen)."""
        now = datetime.now(UTC)
        config = self._create_test_config()
        state = PRReviewCycleState(
            id="cycle-123",
            pr_id="pr-456",
            work_item_id="item-789",
            project_id="proj-101",
            board_id="board-202",
            status=PRReviewStatus.PENDING,
            cycle_number=1,
            current_phase="init",
            findings=[],
            phase_outputs=[],
            config=config,
            started_at=now,
            updated_at=now,
        )
        # Should not raise
        state.status = PRReviewStatus.PHASE_1_CODE_REVIEW
        assert state.status == PRReviewStatus.PHASE_1_CODE_REVIEW

    def test_state_findings_mutable_list(self):
        """Test findings list is mutable."""
        now = datetime.now(UTC)
        config = self._create_test_config()
        findings: list[dict[str, object]] = []
        state = PRReviewCycleState(
            id="cycle-123",
            pr_id="pr-456",
            work_item_id="item-789",
            project_id="proj-101",
            board_id="board-202",
            status=PRReviewStatus.PHASE_1_CODE_REVIEW,
            cycle_number=1,
            current_phase="code_review",
            findings=findings,
            phase_outputs=[],
            config=config,
            started_at=now,
            updated_at=now,
        )
        # Should be able to append
        new_finding = PRReviewFinding(title="Bug", description="A bug", severity="high", phase="code_review")
        state.findings.append(new_finding)
        assert len(state.findings) == 1

    def test_state_empty_cycle_id(self):
        """Test rejects empty cycle_id."""
        now = datetime.now(UTC)
        config = self._create_test_config()
        with pytest.raises(ValueError, match="cycle_id is required"):
            PRReviewCycleState(
                id="",
                pr_id="pr-456",
                work_item_id="item-789",
                project_id="proj-101",
                board_id="board-202",
                status=PRReviewStatus.PENDING,
                cycle_number=1,
                current_phase="init",
                findings=[],
                phase_outputs=[],
                config=config,
                started_at=now,
                updated_at=now,
            )

    def test_state_optional_pr_id(self):
        """Test accepts None for pr_id (work items without associated PR)."""
        now = datetime.now(UTC)
        config = self._create_test_config()
        state = PRReviewCycleState(
            id="cycle-123",
            pr_id=None,
            work_item_id="item-789",
            project_id="proj-101",
            board_id="board-202",
            status=PRReviewStatus.PENDING,
            cycle_number=1,
            current_phase="init",
            findings=[],
            phase_outputs=[],
            config=config,
            started_at=now,
            updated_at=now,
        )
        assert state.pr_id is None

    def test_state_empty_pr_id(self):
        """Test rejects empty string pr_id."""
        now = datetime.now(UTC)
        config = self._create_test_config()
        with pytest.raises(ValueError, match="pr_id must be a non-empty string or None"):
            PRReviewCycleState(
                id="cycle-123",
                pr_id="",
                work_item_id="item-789",
                project_id="proj-101",
                board_id="board-202",
                status=PRReviewStatus.PENDING,
                cycle_number=1,
                current_phase="init",
                findings=[],
                phase_outputs=[],
                config=config,
                started_at=now,
                updated_at=now,
            )

    def test_state_empty_work_item_id(self):
        """Test rejects empty work_item_id."""
        now = datetime.now(UTC)
        config = self._create_test_config()
        with pytest.raises(ValueError, match="work_item_id is required"):
            PRReviewCycleState(
                id="cycle-123",
                pr_id="pr-456",
                work_item_id="",
                project_id="proj-101",
                board_id="board-202",
                status=PRReviewStatus.PENDING,
                cycle_number=1,
                current_phase="init",
                findings=[],
                phase_outputs=[],
                config=config,
                started_at=now,
                updated_at=now,
            )

    def test_state_cycle_number_min(self):
        """Test cycle_number must be >= 1."""
        now = datetime.now(UTC)
        config = self._create_test_config()
        with pytest.raises(ValueError, match="cycle_number must be >= 1"):
            PRReviewCycleState(
                id="cycle-123",
                pr_id="pr-456",
                work_item_id="item-789",
                project_id="proj-101",
                board_id="board-202",
                status=PRReviewStatus.PENDING,
                cycle_number=0,
                current_phase="init",
                findings=[],
                phase_outputs=[],
                config=config,
                started_at=now,
                updated_at=now,
            )
