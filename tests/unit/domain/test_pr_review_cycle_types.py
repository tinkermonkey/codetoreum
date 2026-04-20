"""Unit tests for PR Review Cycle domain types.

Tests cover:
- Immutability of frozen dataclasses
- Mutable state of PRReviewCycleState
- Default values
- __post_init__ validation
- Consistency checks
"""

import pytest
from datetime import UTC, datetime

from codetoreum.domain.pr_review_cycle_types import (
    PRReviewOutcome,
    PRReviewStatus,
    PRReviewFinding,
    PRReviewPhaseOutput,
    PRReviewCycleConfig,
    PRReviewCycleResult,
    PRReviewCycleState,
)


class TestPRReviewOutcome:
    """Tests for PRReviewOutcome enum."""

    def test_enum_values(self):
        """Test enum has correct values."""
        assert PRReviewOutcome.ISSUES_FOUND.value == "issues_found"
        assert PRReviewOutcome.APPROVED.value == "approved"
        assert PRReviewOutcome.MAX_CYCLES_REACHED.value == "max_cycles_reached"

    def test_enum_serializable(self):
        """Test enum is serializable (str, Enum)."""
        outcome = PRReviewOutcome.APPROVED
        assert isinstance(outcome, str)
        # String representation includes the enum member name
        assert str(outcome) == "PRReviewOutcome.APPROVED"
        # But the value is the lowercase snake_case
        assert outcome.value == "approved"


class TestPRReviewStatus:
    """Tests for PRReviewStatus enum."""

    def test_enum_values(self):
        """Test enum has all seven values."""
        assert PRReviewStatus.PENDING.value == "pending"
        assert PRReviewStatus.IN_CODE_REVIEW.value == "in_code_review"
        assert PRReviewStatus.IN_VERIFICATION.value == "in_verification"
        assert PRReviewStatus.IN_CI_CHECK.value == "in_ci_check"
        assert PRReviewStatus.IN_CONSOLIDATION.value == "in_consolidation"
        assert PRReviewStatus.COMPLETED.value == "completed"
        assert PRReviewStatus.ESCALATED.value == "escalated"


class TestPRReviewFinding:
    """Tests for PRReviewFinding frozen dataclass."""

    def test_create_valid_finding(self):
        """Test creating a valid finding."""
        finding = PRReviewFinding(
            type="bug",
            severity="high",
            file="app.py",
            line_number=42,
            message="Null pointer exception",
            suggestion="Add null check before accessing",
        )
        assert finding.type == "bug"
        assert finding.severity == "high"
        assert finding.file == "app.py"
        assert finding.line_number == 42
        assert finding.message == "Null pointer exception"
        assert finding.suggestion == "Add null check before accessing"

    def test_finding_immutable(self):
        """Test finding is immutable (frozen)."""
        finding = PRReviewFinding(
            type="bug",
            severity="high",
            file="app.py",
            line_number=42,
            message="Issue",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            finding.severity = "low"

    def test_finding_without_line_number(self):
        """Test finding without line number (file-level)."""
        finding = PRReviewFinding(
            type="style",
            severity="low",
            file="app.py",
            line_number=None,
            message="File is too long",
        )
        assert finding.line_number is None

    def test_finding_without_suggestion(self):
        """Test finding without suggestion."""
        finding = PRReviewFinding(
            type="info",
            severity="low",
            file="app.py",
            line_number=10,
            message="Info message",
        )
        assert finding.suggestion is None

    def test_finding_invalid_severity(self):
        """Test finding rejects invalid severity."""
        with pytest.raises(ValueError, match="severity must be one of"):
            PRReviewFinding(
                type="bug",
                severity="invalid",
                file="app.py",
                line_number=42,
                message="Issue",
            )

    def test_finding_empty_type(self):
        """Test finding rejects empty type."""
        with pytest.raises(ValueError, match="type is required"):
            PRReviewFinding(
                type="",
                severity="high",
                file="app.py",
                line_number=42,
                message="Issue",
            )

    def test_finding_empty_severity(self):
        """Test finding rejects empty severity."""
        with pytest.raises(ValueError, match="severity is required"):
            PRReviewFinding(
                type="bug",
                severity="",
                file="app.py",
                line_number=42,
                message="Issue",
            )

    def test_finding_empty_file(self):
        """Test finding rejects empty file."""
        with pytest.raises(ValueError, match="file is required"):
            PRReviewFinding(
                type="bug",
                severity="high",
                file="",
                line_number=42,
                message="Issue",
            )

    def test_finding_empty_message(self):
        """Test finding rejects empty message."""
        with pytest.raises(ValueError, match="message is required"):
            PRReviewFinding(
                type="bug",
                severity="high",
                file="app.py",
                line_number=42,
                message="",
            )

    def test_finding_negative_line_number(self):
        """Test finding rejects negative line number."""
        with pytest.raises(ValueError, match="line_number must be non-negative"):
            PRReviewFinding(
                type="bug",
                severity="high",
                file="app.py",
                line_number=-1,
                message="Issue",
            )


class TestPRReviewPhaseOutput:
    """Tests for PRReviewPhaseOutput frozen dataclass."""

    def test_create_successful_phase(self):
        """Test creating output for successful phase."""
        findings = (
            PRReviewFinding(
                type="bug", severity="high", file="app.py", line_number=10, message="Issue"
            ),
        )
        output = PRReviewPhaseOutput(
            phase_name="code_review",
            success=True,
            findings=findings,
            summary="Found 1 issue",
            duration_seconds=600.5,
        )
        assert output.phase_name == "code_review"
        assert output.success is True
        assert len(output.findings) == 1
        assert output.summary == "Found 1 issue"
        assert output.duration_seconds == 600.5
        assert output.error is None

    def test_create_failed_phase(self):
        """Test creating output for failed phase."""
        output = PRReviewPhaseOutput(
            phase_name="ci_check",
            success=False,
            findings=(),
            summary="CI failed",
            duration_seconds=10.0,
            error="Connection timeout",
        )
        assert output.success is False
        assert output.error == "Connection timeout"

    def test_phase_output_immutable(self):
        """Test phase output is immutable."""
        output = PRReviewPhaseOutput(
            phase_name="code_review",
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
                success=False,
                findings=(),
                summary="Failed",
                duration_seconds=0.0,
            )


class TestPRReviewCycleConfig:
    """Tests for PRReviewCycleConfig frozen dataclass."""

    def test_create_with_defaults(self):
        """Test creating config with default values."""
        config = PRReviewCycleConfig()
        assert config.max_outer_cycles == 1
        assert config.verifier_context_sources == ("parent_issue",)
        assert config.code_review_timeout_seconds == 600
        assert config.verification_timeout_seconds == 300
        assert config.ci_check_enabled is True
        assert config.ci_check_timeout_seconds == 300
        assert config.consolidation_timeout_seconds == 600

    def test_create_with_custom_values(self):
        """Test creating config with custom values."""
        config = PRReviewCycleConfig(
            max_outer_cycles=3,
            verifier_context_sources=("parent_issue", "ba_output", "arch_spec"),
            code_review_timeout_seconds=900,
            verification_timeout_seconds=600,
            ci_check_enabled=True,
            ci_check_timeout_seconds=600,
            consolidation_timeout_seconds=1200,
        )
        assert config.max_outer_cycles == 3
        assert config.verifier_context_sources == ("parent_issue", "ba_output", "arch_spec")
        assert config.code_review_timeout_seconds == 900

    def test_config_immutable(self):
        """Test config is immutable."""
        config = PRReviewCycleConfig()
        with pytest.raises(Exception):  # FrozenInstanceError
            config.max_outer_cycles = 2

    def test_config_max_outer_cycles_min(self):
        """Test max_outer_cycles must be >= 1."""
        with pytest.raises(ValueError, match="max_outer_cycles must be >= 1"):
            PRReviewCycleConfig(max_outer_cycles=0)

    def test_config_verifier_context_sources_empty(self):
        """Test verifier_context_sources must not be empty."""
        with pytest.raises(ValueError, match="verifier_context_sources must not be empty"):
            PRReviewCycleConfig(verifier_context_sources=())

    def test_config_ci_check_timeout_validation_when_enabled(self):
        """Test ci_check_timeout_seconds must be > 0 when ci_check_enabled=True."""
        with pytest.raises(ValueError, match="ci_check_timeout_seconds must be > 0"):
            PRReviewCycleConfig(ci_check_enabled=True, ci_check_timeout_seconds=0)

    def test_config_ci_check_timeout_validation_when_disabled(self):
        """Test ci_check_timeout_seconds ignored when ci_check_enabled=False."""
        # Should not raise even with ci_check_timeout_seconds=0
        config = PRReviewCycleConfig(ci_check_enabled=False, ci_check_timeout_seconds=0)
        assert config.ci_check_timeout_seconds == 0

    def test_config_code_review_timeout_positive(self):
        """Test code_review_timeout_seconds must be > 0."""
        with pytest.raises(ValueError, match="code_review_timeout_seconds must be > 0"):
            PRReviewCycleConfig(code_review_timeout_seconds=0)

    def test_config_verification_timeout_positive(self):
        """Test verification_timeout_seconds must be > 0."""
        with pytest.raises(ValueError, match="verification_timeout_seconds must be > 0"):
            PRReviewCycleConfig(verification_timeout_seconds=0)

    def test_config_consolidation_timeout_positive(self):
        """Test consolidation_timeout_seconds must be > 0."""
        with pytest.raises(ValueError, match="consolidation_timeout_seconds must be > 0"):
            PRReviewCycleConfig(consolidation_timeout_seconds=0)


class TestPRReviewCycleResult:
    """Tests for PRReviewCycleResult frozen dataclass."""

    def test_create_approved_result(self):
        """Test creating an approved result."""
        phase_output = PRReviewPhaseOutput(
            phase_name="code_review",
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
            sub_issue_ids=(),
            ci_passed=True,
            total_duration_seconds=600.0,
            timestamp=datetime.now(UTC).isoformat(),
            next_column="Done",
        )
        assert result.outcome == PRReviewOutcome.APPROVED
        assert result.sub_issue_ids == ()
        assert result.ci_passed is True

    def test_create_issues_found_result(self):
        """Test creating a result with issues found."""
        finding = PRReviewFinding(
            type="bug", severity="high", file="app.py", line_number=10, message="Issue"
        )
        phase_output = PRReviewPhaseOutput(
            phase_name="code_review",
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
            sub_issue_ids=("issue-1", "issue-2"),
            ci_passed=False,
            total_duration_seconds=600.0,
            timestamp=datetime.now(UTC).isoformat(),
            next_column="In Development",
        )
        assert result.outcome == PRReviewOutcome.ISSUES_FOUND
        assert len(result.sub_issue_ids) == 2

    def test_result_immutable(self):
        """Test result is immutable."""
        phase_output = PRReviewPhaseOutput(
            phase_name="code_review",
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
            sub_issue_ids=(),
            ci_passed=True,
            total_duration_seconds=0.0,
            timestamp=datetime.now(UTC).isoformat(),
            next_column="Done",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            result.cycle_number = 2

    def test_result_issues_found_requires_sub_issues(self):
        """Test ISSUES_FOUND outcome requires sub_issue_ids."""
        phase_output = PRReviewPhaseOutput(
            phase_name="code_review",
            success=True,
            findings=(),
            summary="OK",
            duration_seconds=0.0,
        )
        with pytest.raises(ValueError, match="outcome=ISSUES_FOUND but sub_issue_ids is empty"):
            PRReviewCycleResult(
                cycle_number=1,
                workflow_run_id="run-123",
                outcome=PRReviewOutcome.ISSUES_FOUND,
                phase_outputs=(phase_output,),
                all_findings=(),
                sub_issue_ids=(),
                ci_passed=False,
                total_duration_seconds=0.0,
                timestamp=datetime.now(UTC).isoformat(),
                next_column="In Development",
            )

    def test_result_approved_forbids_sub_issues(self):
        """Test APPROVED outcome forbids sub_issue_ids."""
        phase_output = PRReviewPhaseOutput(
            phase_name="code_review",
            success=True,
            findings=(),
            summary="OK",
            duration_seconds=0.0,
        )
        with pytest.raises(ValueError, match="outcome=APPROVED but sub_issue_ids is non-empty"):
            PRReviewCycleResult(
                cycle_number=1,
                workflow_run_id="run-123",
                outcome=PRReviewOutcome.APPROVED,
                phase_outputs=(phase_output,),
                all_findings=(),
                sub_issue_ids=("issue-1",),
                ci_passed=True,
                total_duration_seconds=0.0,
                timestamp=datetime.now(UTC).isoformat(),
                next_column="Done",
            )

    def test_result_cycle_number_min(self):
        """Test cycle_number must be >= 1."""
        phase_output = PRReviewPhaseOutput(
            phase_name="code_review",
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
                sub_issue_ids=(),
                ci_passed=True,
                total_duration_seconds=0.0,
                timestamp=datetime.now(UTC).isoformat(),
                next_column="Done",
            )


class TestPRReviewCycleState:
    """Tests for PRReviewCycleState mutable dataclass."""

    def test_create_state(self):
        """Test creating mutable state."""
        now = datetime.now(UTC).isoformat()
        state = PRReviewCycleState(
            cycle_id="cycle-123",
            pr_id="pr-456",
            status=PRReviewStatus.IN_CODE_REVIEW,
            cycle_number=1,
            current_phase="code_review",
            findings=[],
            phase_outputs=[],
            started_at=now,
            updated_at=now,
        )
        assert state.cycle_id == "cycle-123"
        assert state.pr_id == "pr-456"
        assert state.status == PRReviewStatus.IN_CODE_REVIEW
        assert state.findings == []
        assert state.phase_outputs == []

    def test_state_mutable(self):
        """Test state is mutable (not frozen)."""
        now = datetime.now(UTC).isoformat()
        state = PRReviewCycleState(
            cycle_id="cycle-123",
            pr_id="pr-456",
            status=PRReviewStatus.PENDING,
            cycle_number=1,
            current_phase="init",
            findings=[],
            phase_outputs=[],
            started_at=now,
            updated_at=now,
        )
        # Should not raise
        state.status = PRReviewStatus.IN_CODE_REVIEW
        assert state.status == PRReviewStatus.IN_CODE_REVIEW

    def test_state_findings_mutable_list(self):
        """Test findings list is mutable."""
        now = datetime.now(UTC).isoformat()
        findings = []
        state = PRReviewCycleState(
            cycle_id="cycle-123",
            pr_id="pr-456",
            status=PRReviewStatus.IN_CODE_REVIEW,
            cycle_number=1,
            current_phase="code_review",
            findings=findings,
            phase_outputs=[],
            started_at=now,
            updated_at=now,
        )
        # Should be able to append
        new_finding = PRReviewFinding(
            type="bug", severity="high", file="app.py", line_number=10, message="Issue"
        )
        state.findings.append(new_finding)
        assert len(state.findings) == 1

    def test_state_empty_cycle_id(self):
        """Test rejects empty cycle_id."""
        now = datetime.now(UTC).isoformat()
        with pytest.raises(ValueError, match="cycle_id is required"):
            PRReviewCycleState(
                cycle_id="",
                pr_id="pr-456",
                status=PRReviewStatus.PENDING,
                cycle_number=1,
                current_phase="init",
                findings=[],
                phase_outputs=[],
                started_at=now,
                updated_at=now,
            )

    def test_state_empty_pr_id(self):
        """Test rejects empty pr_id."""
        now = datetime.now(UTC).isoformat()
        with pytest.raises(ValueError, match="pr_id is required"):
            PRReviewCycleState(
                cycle_id="cycle-123",
                pr_id="",
                status=PRReviewStatus.PENDING,
                cycle_number=1,
                current_phase="init",
                findings=[],
                phase_outputs=[],
                started_at=now,
                updated_at=now,
            )

    def test_state_cycle_number_min(self):
        """Test cycle_number must be >= 1."""
        now = datetime.now(UTC).isoformat()
        with pytest.raises(ValueError, match="cycle_number must be >= 1"):
            PRReviewCycleState(
                cycle_id="cycle-123",
                pr_id="pr-456",
                status=PRReviewStatus.PENDING,
                cycle_number=0,
                current_phase="init",
                findings=[],
                phase_outputs=[],
                started_at=now,
                updated_at=now,
            )
