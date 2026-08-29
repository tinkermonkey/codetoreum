"""Unit tests for CI pipeline events."""

import uuid

import pytest

from codetoreum.domain.events import (
    CIPipelineStatusCheckedEvent,
    CIRunCompletedEvent,
    CIRunStartedEvent,
    now_iso,
)

# For immutability tests (when events become frozen dataclasses)
try:
    from dataclasses import FrozenInstanceError
except ImportError:
    # Fallback for older Python versions or non-frozen dataclasses
    FrozenInstanceError = AttributeError  # type: ignore


class TestCIPipelineStatusCheckedEvent:
    """Test CIPipelineStatusCheckedEvent."""

    def test_immutability_frozen_instance_error(self):
        """Test that attempting to modify event fields raises FrozenInstanceError."""
        event = CIPipelineStatusCheckedEvent(
            type="ci.pipeline_status_checked",
            timestamp=now_iso(),
            source="github",
            pr_id="456",
            project_id="proj-1",
            status="passed",
        )

        with pytest.raises(FrozenInstanceError):
            event.pr_id = "789"

        with pytest.raises(FrozenInstanceError):
            event.status = "failed"

        with pytest.raises(FrozenInstanceError):
            event.check_count = 10

    def test_create_valid_event(self):
        """Test creating a valid CI pipeline status checked event."""
        timestamp = now_iso()
        event = CIPipelineStatusCheckedEvent(
            type="ci.pipeline_status_checked",
            timestamp=timestamp,
            source="github",
            pr_id="456",
            project_id="proj-1",
            status="passed",
            check_count=5,
            passed_count=5,
            failed_count=0,
            pending_count=0,
        )

        assert event.pr_id == "456"
        assert event.project_id == "proj-1"
        assert event.status == "passed"
        assert event.check_count == 5
        assert event.passed_count == 5
        assert event.failed_count == 0
        assert event.pending_count == 0

    def test_status_pending(self):
        """Test CI status checked with pending status."""
        event = CIPipelineStatusCheckedEvent(
            type="ci.pipeline_status_checked",
            timestamp=now_iso(),
            source="github",
            pr_id="456",
            project_id="proj-1",
            status="pending",
            check_count=3,
            passed_count=0,
            failed_count=0,
            pending_count=3,
        )

        assert event.status == "pending"
        assert event.pending_count == 3

    def test_status_failed(self):
        """Test CI status checked with failed status."""
        event = CIPipelineStatusCheckedEvent(
            type="ci.pipeline_status_checked",
            timestamp=now_iso(),
            source="github",
            pr_id="456",
            project_id="proj-1",
            status="failed",
            check_count=5,
            passed_count=2,
            failed_count=3,
            pending_count=0,
        )

        assert event.status == "failed"
        assert event.failed_count == 3
        assert event.pending_count == 0

    def test_missing_pr_id(self):
        """Test that pr_id is required."""
        with pytest.raises(ValueError, match="pr_id"):
            CIPipelineStatusCheckedEvent(
                type="ci.pipeline_status_checked",
                timestamp=now_iso(),
                source="github",
                pr_id="",  # Empty
                project_id="proj-1",
                status="passed",
            )

    def test_missing_project_id(self):
        """Test that project_id is required."""
        with pytest.raises(ValueError, match="project_id"):
            CIPipelineStatusCheckedEvent(
                type="ci.pipeline_status_checked",
                timestamp=now_iso(),
                source="github",
                pr_id="456",
                project_id="",  # Empty
                status="passed",
            )

    def test_missing_status(self):
        """Test that status is required."""
        with pytest.raises(ValueError, match="status"):
            CIPipelineStatusCheckedEvent(
                type="ci.pipeline_status_checked",
                timestamp=now_iso(),
                source="github",
                pr_id="456",
                project_id="proj-1",
                status="",  # Empty
            )

    def test_invalid_status(self):
        """Test that invalid status values are rejected."""
        with pytest.raises(ValueError, match="Invalid status"):
            CIPipelineStatusCheckedEvent(
                type="ci.pipeline_status_checked",
                timestamp=now_iso(),
                source="github",
                pr_id="456",
                project_id="proj-1",
                status="passsed",  # Typo - not a valid status
            )

    def test_all_valid_statuses(self):
        """Test all valid status values are accepted."""
        valid_statuses = ["pending", "running", "passed", "failed", "skipped"]
        for status in valid_statuses:
            event = CIPipelineStatusCheckedEvent(
                type="ci.pipeline_status_checked",
                timestamp=now_iso(),
                source="github",
                pr_id="456",
                project_id="proj-1",
                status=status,
            )
            assert event.status == status

    def test_negative_check_count(self):
        """Test that check_count must be non-negative."""
        with pytest.raises(ValueError, match="check_count"):
            CIPipelineStatusCheckedEvent(
                type="ci.pipeline_status_checked",
                timestamp=now_iso(),
                source="github",
                pr_id="456",
                project_id="proj-1",
                status="passed",
                check_count=-1,  # Invalid
            )

    def test_negative_passed_count(self):
        """Test that passed_count must be non-negative."""
        with pytest.raises(ValueError, match="passed_count"):
            CIPipelineStatusCheckedEvent(
                type="ci.pipeline_status_checked",
                timestamp=now_iso(),
                source="github",
                pr_id="456",
                project_id="proj-1",
                status="passed",
                passed_count=-1,  # Invalid
            )

    def test_negative_failed_count(self):
        """Test that failed_count must be non-negative."""
        with pytest.raises(ValueError, match="failed_count"):
            CIPipelineStatusCheckedEvent(
                type="ci.pipeline_status_checked",
                timestamp=now_iso(),
                source="github",
                pr_id="456",
                project_id="proj-1",
                status="failed",
                failed_count=-1,  # Invalid
            )

    def test_negative_pending_count(self):
        """Test that pending_count must be non-negative."""
        with pytest.raises(ValueError, match="pending_count"):
            CIPipelineStatusCheckedEvent(
                type="ci.pipeline_status_checked",
                timestamp=now_iso(),
                source="github",
                pr_id="456",
                project_id="proj-1",
                status="pending",
                pending_count=-1,  # Invalid
            )

    def test_count_consistency_exceeded(self):
        """Test that sum of counts cannot exceed check_count."""
        with pytest.raises(ValueError, match="exceeds check_count"):
            CIPipelineStatusCheckedEvent(
                type="ci.pipeline_status_checked",
                timestamp=now_iso(),
                source="github",
                pr_id="456",
                project_id="proj-1",
                status="pending",
                check_count=1,
                passed_count=999,  # Impossible: exceeds check_count
                failed_count=0,
                pending_count=0,
            )

    def test_count_consistency_valid(self):
        """Test that valid count combinations are accepted."""
        # Sum equals check_count
        event = CIPipelineStatusCheckedEvent(
            type="ci.pipeline_status_checked",
            timestamp=now_iso(),
            source="github",
            pr_id="456",
            project_id="proj-1",
            status="pending",
            check_count=5,
            passed_count=2,
            failed_count=1,
            pending_count=2,
        )
        assert event.check_count == 5
        assert event.passed_count + event.failed_count + event.pending_count == 5

        # Sum is less than check_count (skipped checks)
        event2 = CIPipelineStatusCheckedEvent(
            type="ci.pipeline_status_checked",
            timestamp=now_iso(),
            source="github",
            pr_id="456",
            project_id="proj-1",
            status="pending",
            check_count=5,
            passed_count=2,
            failed_count=1,
            pending_count=1,  # Sum is 4, less than 5
        )
        assert event2.check_count == 5
        assert event2.passed_count + event2.failed_count + event2.pending_count == 4

    def test_status_checked_serialization(self):
        """Test CI status checked event serialization."""
        timestamp = now_iso()
        event = CIPipelineStatusCheckedEvent(
            type="ci.pipeline_status_checked",
            timestamp=timestamp,
            source="github",
            correlation_id="corr-456",
            pr_id="456",
            project_id="proj-1",
            status="passed",
            check_count=5,
            passed_count=5,
            failed_count=0,
            pending_count=0,
        )

        d = event.to_dict()

        assert d["type"] == "ci.pipeline_status_checked"
        assert d["pr_id"] == "456"
        assert d["project_id"] == "proj-1"
        assert d["status"] == "passed"
        assert d["check_count"] == 5
        assert d["passed_count"] == 5
        assert d["failed_count"] == 0
        assert d["pending_count"] == 0

    def test_status_checked_deserialization(self):
        """Test CI status checked event deserialization."""
        timestamp = now_iso()
        d = {
            "type": "ci.pipeline_status_checked",
            "timestamp": timestamp,
            "source": "github",
            "correlation_id": "corr-456",
            "pr_id": "456",
            "project_id": "proj-1",
            "status": "passed",
            "check_count": 5,
            "passed_count": 5,
            "failed_count": 0,
            "pending_count": 0,
        }

        event = CIPipelineStatusCheckedEvent.from_dict(d)

        assert event.type == "ci.pipeline_status_checked"
        assert event.pr_id == "456"
        assert event.project_id == "proj-1"
        assert event.status == "passed"
        assert event.check_count == 5
        assert event.passed_count == 5
        assert event.failed_count == 0
        assert event.pending_count == 0

    def test_status_checked_roundtrip(self):
        """Test CI status checked event roundtrip serialization."""
        timestamp = now_iso()
        original = CIPipelineStatusCheckedEvent(
            type="ci.pipeline_status_checked",
            timestamp=timestamp,
            source="github",
            correlation_id="corr-456",
            pr_id="456",
            project_id="proj-1",
            status="passed",
            check_count=5,
            passed_count=5,
            failed_count=0,
            pending_count=0,
        )

        d = original.to_dict()
        restored = CIPipelineStatusCheckedEvent.from_dict(d)

        assert restored.pr_id == original.pr_id
        assert restored.project_id == original.project_id
        assert restored.status == original.status
        assert restored.check_count == original.check_count
        assert restored.passed_count == original.passed_count
        assert restored.failed_count == original.failed_count
        assert restored.pending_count == original.pending_count

    def test_status_checked_missing_pr_id_from_dict(self):
        """Test that from_dict raises KeyError when pr_id is missing."""
        d = {
            "type": "ci.pipeline_status_checked",
            "timestamp": now_iso(),
            "source": "github",
            "project_id": "proj-1",
            "status": "passed",
        }

        with pytest.raises(KeyError):
            CIPipelineStatusCheckedEvent.from_dict(d)

    def test_status_checked_missing_project_id_from_dict(self):
        """Test that from_dict raises KeyError when project_id is missing."""
        d = {
            "type": "ci.pipeline_status_checked",
            "timestamp": now_iso(),
            "source": "github",
            "pr_id": "456",
            "status": "passed",
        }

        with pytest.raises(KeyError):
            CIPipelineStatusCheckedEvent.from_dict(d)

    def test_status_checked_missing_status_from_dict(self):
        """Test that from_dict raises KeyError when status is missing."""
        d = {
            "type": "ci.pipeline_status_checked",
            "timestamp": now_iso(),
            "source": "github",
            "pr_id": "456",
            "project_id": "proj-1",
        }

        with pytest.raises(KeyError):
            CIPipelineStatusCheckedEvent.from_dict(d)

    def test_status_checked_invalid_status_from_dict(self):
        """Test that from_dict raises ValueError for invalid status."""
        d = {
            "type": "ci.pipeline_status_checked",
            "timestamp": now_iso(),
            "source": "github",
            "pr_id": "456",
            "project_id": "proj-1",
            "status": "invalid_status",
        }

        with pytest.raises(ValueError, match="Invalid status"):
            CIPipelineStatusCheckedEvent.from_dict(d)

    def test_status_checked_empty_timestamp_from_dict(self):
        """Test that from_dict raises ValueError when timestamp is empty."""
        d = {
            "type": "ci.pipeline_status_checked",
            "timestamp": "",  # Empty timestamp
            "source": "github",
            "pr_id": "456",
            "project_id": "proj-1",
            "status": "passed",
        }

        with pytest.raises(ValueError):
            CIPipelineStatusCheckedEvent.from_dict(d)

    def test_status_checked_empty_source_from_dict(self):
        """Test that from_dict raises ValueError when source is empty."""
        d = {
            "type": "ci.pipeline_status_checked",
            "timestamp": now_iso(),
            "source": "",  # Empty source
            "pr_id": "456",
            "project_id": "proj-1",
            "status": "passed",
        }

        with pytest.raises(ValueError):
            CIPipelineStatusCheckedEvent.from_dict(d)

    def test_status_checked_count_consistency_from_dict(self):
        """Test that from_dict raises ValueError for inconsistent counts."""
        d = {
            "type": "ci.pipeline_status_checked",
            "timestamp": now_iso(),
            "source": "github",
            "pr_id": "456",
            "project_id": "proj-1",
            "status": "pending",
            "check_count": 1,
            "passed_count": 999,  # Impossible
            "failed_count": 0,
            "pending_count": 0,
        }

        with pytest.raises(ValueError, match="exceeds check_count"):
            CIPipelineStatusCheckedEvent.from_dict(d)


class TestCIRunStartedEvent:
    """Test CIRunStartedEvent."""

    def test_immutability_frozen_instance_error(self):
        """Test that attempting to modify event fields raises FrozenInstanceError."""
        event = CIRunStartedEvent(
            type="ci.run_started",
            timestamp=now_iso(),
            source="orchestrator",
            project_id="proj-1",
            workflow_run_id="wf-123",
            working_directory="/workspace",
            timeout_seconds=600,
        )

        with pytest.raises(FrozenInstanceError):
            event.project_id = "proj-2"

        with pytest.raises(FrozenInstanceError):
            event.timeout_seconds = 300

        with pytest.raises(FrozenInstanceError):
            event.workflow_run_id = "wf-456"

    def test_create_valid_event(self):
        """Test creating a valid CI run started event."""
        timestamp = now_iso()
        event = CIRunStartedEvent(
            type="ci.run_started",
            timestamp=timestamp,
            source="orchestrator",
            project_id="proj-1",
            workflow_run_id="wf-123",
            working_directory="/workspace",
            timeout_seconds=600,
            checks_planned=3,
        )

        assert event.project_id == "proj-1"
        assert event.workflow_run_id == "wf-123"
        assert event.working_directory == "/workspace"
        assert event.timeout_seconds == 600
        assert event.checks_planned == 3

    def test_different_timeout(self):
        """Test CI run started with different timeout."""
        event = CIRunStartedEvent(
            type="ci.run_started",
            timestamp=now_iso(),
            source="orchestrator",
            project_id="proj-1",
            workflow_run_id="wf-123",
            working_directory="/workspace",
            timeout_seconds=300,
            checks_planned=5,
        )

        assert event.timeout_seconds == 300
        assert event.checks_planned == 5

    def test_missing_project_id(self):
        """Test that project_id is required."""
        with pytest.raises(ValueError, match="project_id"):
            CIRunStartedEvent(
                type="ci.run_started",
                timestamp=now_iso(),
                source="orchestrator",
                project_id="",  # Empty
                workflow_run_id="wf-123",
                working_directory="/workspace",
                timeout_seconds=600,
            )

    def test_missing_workflow_run_id(self):
        """Test that workflow_run_id is required."""
        with pytest.raises(ValueError, match="workflow_run_id"):
            CIRunStartedEvent(
                type="ci.run_started",
                timestamp=now_iso(),
                source="orchestrator",
                project_id="proj-1",
                workflow_run_id="",  # Empty
                working_directory="/workspace",
                timeout_seconds=600,
            )

    def test_missing_working_directory(self):
        """Test that working_directory is required."""
        with pytest.raises(ValueError, match="working_directory"):
            CIRunStartedEvent(
                type="ci.run_started",
                timestamp=now_iso(),
                source="orchestrator",
                project_id="proj-1",
                workflow_run_id="wf-123",
                working_directory="",  # Empty
                timeout_seconds=600,
            )

    def test_invalid_timeout_zero(self):
        """Test that timeout_seconds must be positive."""
        with pytest.raises(ValueError, match="timeout_seconds"):
            CIRunStartedEvent(
                type="ci.run_started",
                timestamp=now_iso(),
                source="orchestrator",
                project_id="proj-1",
                workflow_run_id="wf-123",
                working_directory="/workspace",
                timeout_seconds=0,  # Invalid
            )

    def test_invalid_timeout_negative(self):
        """Test that timeout_seconds must be positive."""
        with pytest.raises(ValueError, match="timeout_seconds"):
            CIRunStartedEvent(
                type="ci.run_started",
                timestamp=now_iso(),
                source="orchestrator",
                project_id="proj-1",
                workflow_run_id="wf-123",
                working_directory="/workspace",
                timeout_seconds=-1,  # Invalid
            )

    def test_negative_checks_planned(self):
        """Test that checks_planned must be non-negative."""
        with pytest.raises(ValueError, match="checks_planned"):
            CIRunStartedEvent(
                type="ci.run_started",
                timestamp=now_iso(),
                source="orchestrator",
                project_id="proj-1",
                workflow_run_id="wf-123",
                working_directory="/workspace",
                timeout_seconds=600,
                checks_planned=-1,  # Invalid
            )

    def test_run_started_serialization(self):
        """Test CI run started event serialization."""
        timestamp = now_iso()
        event = CIRunStartedEvent(
            type="ci.run_started",
            timestamp=timestamp,
            source="orchestrator",
            correlation_id="corr-123",
            project_id="proj-1",
            workflow_run_id="wf-123",
            working_directory="/workspace",
            timeout_seconds=600,
            checks_planned=3,
        )

        d = event.to_dict()

        assert d["type"] == "ci.run_started"
        assert d["project_id"] == "proj-1"
        assert d["workflow_run_id"] == "wf-123"
        assert d["working_directory"] == "/workspace"
        assert d["timeout_seconds"] == 600
        assert d["checks_planned"] == 3

    def test_run_started_deserialization(self):
        """Test CI run started event deserialization."""
        timestamp = now_iso()
        d = {
            "type": "ci.run_started",
            "timestamp": timestamp,
            "source": "orchestrator",
            "correlation_id": "corr-123",
            "project_id": "proj-1",
            "workflow_run_id": "wf-123",
            "working_directory": "/workspace",
            "timeout_seconds": 600,
            "checks_planned": 3,
        }

        event = CIRunStartedEvent.from_dict(d)

        assert event.type == "ci.run_started"
        assert event.project_id == "proj-1"
        assert event.workflow_run_id == "wf-123"
        assert event.working_directory == "/workspace"
        assert event.timeout_seconds == 600
        assert event.checks_planned == 3

    def test_run_started_roundtrip(self):
        """Test CI run started event roundtrip serialization."""
        timestamp = now_iso()
        original = CIRunStartedEvent(
            type="ci.run_started",
            timestamp=timestamp,
            source="orchestrator",
            correlation_id="corr-123",
            project_id="proj-1",
            workflow_run_id="wf-123",
            working_directory="/workspace",
            timeout_seconds=600,
            checks_planned=3,
        )

        d = original.to_dict()
        restored = CIRunStartedEvent.from_dict(d)

        assert restored.project_id == original.project_id
        assert restored.workflow_run_id == original.workflow_run_id
        assert restored.working_directory == original.working_directory
        assert restored.timeout_seconds == original.timeout_seconds
        assert restored.checks_planned == original.checks_planned

    def test_run_started_missing_project_id_from_dict(self):
        """Test that from_dict raises KeyError when project_id is missing."""
        d = {
            "type": "ci.run_started",
            "timestamp": now_iso(),
            "source": "orchestrator",
            "workflow_run_id": "wf-123",
            "working_directory": "/workspace",
            "timeout_seconds": 600,
        }

        with pytest.raises(KeyError):
            CIRunStartedEvent.from_dict(d)

    def test_run_started_missing_timeout_from_dict(self):
        """Test that from_dict raises KeyError when timeout_seconds is missing."""
        d = {
            "type": "ci.run_started",
            "timestamp": now_iso(),
            "source": "orchestrator",
            "project_id": "proj-1",
            "workflow_run_id": "wf-123",
            "working_directory": "/workspace",
        }

        with pytest.raises(KeyError):
            CIRunStartedEvent.from_dict(d)


class TestCIRunCompletedEvent:
    """Test CIRunCompletedEvent."""

    def test_immutability_frozen_instance_error(self):
        """Test that attempting to modify event fields raises FrozenInstanceError."""
        event = CIRunCompletedEvent(
            type="ci.run_completed",
            timestamp=now_iso(),
            source="orchestrator",
            project_id="proj-1",
            workflow_run_id="wf-123",
            check_count=5,
            passed_count=5,
            failure_count=0,
            pending_count=0,
        )

        with pytest.raises(FrozenInstanceError):
            event.project_id = "proj-2"

        with pytest.raises(FrozenInstanceError):
            event.passed_count = 3

        with pytest.raises(FrozenInstanceError):
            event.failure_count = 2

    def test_create_valid_event(self):
        """Test creating a valid CI run completed event."""
        timestamp = now_iso()
        event = CIRunCompletedEvent(
            type="ci.run_completed",
            timestamp=timestamp,
            source="orchestrator",
            project_id="proj-1",
            workflow_run_id="wf-123",
            check_count=5,
            passed_count=5,
            failure_count=0,
            pending_count=0,
            warning_count=0,
            output="All tests passed!",
        )

        assert event.project_id == "proj-1"
        assert event.workflow_run_id == "wf-123"
        assert event.check_count == 5
        assert event.passed_count == 5
        assert event.failure_count == 0
        assert event.pending_count == 0
        assert event.warning_count == 0
        assert event.output == "All tests passed!"

    def test_run_completed_with_failures(self):
        """Test CI run completed with failed checks."""
        event = CIRunCompletedEvent(
            type="ci.run_completed",
            timestamp=now_iso(),
            source="orchestrator",
            project_id="proj-1",
            workflow_run_id="wf-123",
            check_count=5,
            passed_count=3,
            failure_count=2,
            pending_count=0,
            warning_count=1,
            output="Some tests failed",
        )

        assert event.check_count == 5
        assert event.passed_count == 3
        assert event.failure_count == 2
        assert event.pending_count == 0
        assert event.warning_count == 1

    def test_run_completed_empty_output(self):
        """Test CI run completed with empty output."""
        event = CIRunCompletedEvent(
            type="ci.run_completed",
            timestamp=now_iso(),
            source="orchestrator",
            project_id="proj-1",
            workflow_run_id="wf-123",
            check_count=0,
            passed_count=0,
            failure_count=0,
            pending_count=0,
            warning_count=0,
            output="",
        )

        assert event.output == ""

    def test_missing_project_id(self):
        """Test that project_id is required."""
        with pytest.raises(ValueError, match="project_id"):
            CIRunCompletedEvent(
                type="ci.run_completed",
                timestamp=now_iso(),
                source="orchestrator",
                project_id="",  # Empty
                workflow_run_id="wf-123",
                check_count=5,
                passed_count=5,
                failure_count=0,
                pending_count=0,
            )

    def test_missing_workflow_run_id(self):
        """Test that workflow_run_id is required."""
        with pytest.raises(ValueError, match="workflow_run_id"):
            CIRunCompletedEvent(
                type="ci.run_completed",
                timestamp=now_iso(),
                source="orchestrator",
                project_id="proj-1",
                workflow_run_id="",  # Empty
                check_count=5,
                passed_count=5,
                failure_count=0,
                pending_count=0,
            )

    def test_negative_passed(self):
        """Test that passed_count must be non-negative."""
        with pytest.raises(ValueError, match="passed_count"):
            CIRunCompletedEvent(
                type="ci.run_completed",
                timestamp=now_iso(),
                source="orchestrator",
                project_id="proj-1",
                workflow_run_id="wf-123",
                check_count=1,
                passed_count=-1,  # Invalid
                failure_count=0,
                pending_count=0,
            )

    def test_negative_failed(self):
        """Test that failure_count must be non-negative."""
        with pytest.raises(ValueError, match="failure_count"):
            CIRunCompletedEvent(
                type="ci.run_completed",
                timestamp=now_iso(),
                source="orchestrator",
                project_id="proj-1",
                workflow_run_id="wf-123",
                check_count=5,
                passed_count=5,
                failure_count=-1,  # Invalid
                pending_count=0,
            )

    def test_negative_warning_count(self):
        """Test that warning_count must be non-negative."""
        with pytest.raises(ValueError, match="warning_count"):
            CIRunCompletedEvent(
                type="ci.run_completed",
                timestamp=now_iso(),
                source="orchestrator",
                project_id="proj-1",
                workflow_run_id="wf-123",
                check_count=5,
                passed_count=5,
                failure_count=0,
                pending_count=0,
                warning_count=-1,  # Invalid
            )

    def test_run_completed_serialization(self):
        """Test CI run completed event serialization."""
        timestamp = now_iso()
        event = CIRunCompletedEvent(
            type="ci.run_completed",
            timestamp=timestamp,
            source="orchestrator",
            correlation_id="corr-123",
            project_id="proj-1",
            workflow_run_id="wf-123",
            check_count=5,
            passed_count=5,
            failure_count=0,
            pending_count=0,
            warning_count=0,
            output="All tests passed!",
        )

        d = event.to_dict()

        assert d["type"] == "ci.run_completed"
        assert d["project_id"] == "proj-1"
        assert d["workflow_run_id"] == "wf-123"
        assert d["check_count"] == 5
        assert d["passed_count"] == 5
        assert d["failure_count"] == 0
        assert d["pending_count"] == 0
        assert d["warning_count"] == 0
        assert d["output"] == "All tests passed!"

    def test_run_completed_deserialization(self):
        """Test CI run completed event deserialization."""
        timestamp = now_iso()
        d = {
            "type": "ci.run_completed",
            "timestamp": timestamp,
            "source": "orchestrator",
            "correlation_id": "corr-123",
            "project_id": "proj-1",
            "workflow_run_id": "wf-123",
            "check_count": 5,
            "passed_count": 5,
            "failure_count": 0,
            "pending_count": 0,
            "warning_count": 0,
            "output": "All tests passed!",
        }

        event = CIRunCompletedEvent.from_dict(d)

        assert event.type == "ci.run_completed"
        assert event.project_id == "proj-1"
        assert event.workflow_run_id == "wf-123"
        assert event.check_count == 5
        assert event.passed_count == 5
        assert event.failure_count == 0
        assert event.pending_count == 0
        assert event.warning_count == 0
        assert event.output == "All tests passed!"

    def test_run_completed_roundtrip(self):
        """Test CI run completed event roundtrip serialization."""
        timestamp = now_iso()
        original = CIRunCompletedEvent(
            type="ci.run_completed",
            timestamp=timestamp,
            source="orchestrator",
            correlation_id="corr-123",
            project_id="proj-1",
            workflow_run_id="wf-123",
            check_count=5,
            passed_count=5,
            failure_count=0,
            pending_count=0,
            warning_count=0,
            output="All tests passed!",
        )

        d = original.to_dict()
        restored = CIRunCompletedEvent.from_dict(d)

        assert restored.project_id == original.project_id
        assert restored.workflow_run_id == original.workflow_run_id
        assert restored.check_count == original.check_count
        assert restored.passed_count == original.passed_count
        assert restored.failure_count == original.failure_count
        assert restored.pending_count == original.pending_count
        assert restored.warning_count == original.warning_count
        assert restored.output == original.output

    def test_run_completed_missing_project_id_from_dict(self):
        """Test that from_dict raises KeyError when project_id is missing."""
        d = {
            "type": "ci.run_completed",
            "timestamp": now_iso(),
            "source": "orchestrator",
            "workflow_run_id": "wf-123",
            "passed_count": 5,
            "failure_count": 0,
        }

        with pytest.raises(KeyError):
            CIRunCompletedEvent.from_dict(d)

    def test_run_completed_missing_passed_from_dict(self):
        """Test that from_dict raises KeyError when passed_count is missing."""
        d = {
            "type": "ci.run_completed",
            "timestamp": now_iso(),
            "source": "orchestrator",
            "project_id": "proj-1",
            "workflow_run_id": "wf-123",
            "failure_count": 0,
        }

        with pytest.raises(KeyError):
            CIRunCompletedEvent.from_dict(d)

    def test_run_completed_missing_failed_from_dict(self):
        """Test that from_dict raises KeyError when failure_count is missing."""
        d = {
            "type": "ci.run_completed",
            "timestamp": now_iso(),
            "source": "orchestrator",
            "project_id": "proj-1",
            "workflow_run_id": "wf-123",
            "passed_count": 5,
        }

        with pytest.raises(KeyError):
            CIRunCompletedEvent.from_dict(d)

    def test_negative_check_count(self):
        """Test that check_count must be non-negative."""
        with pytest.raises(ValueError, match="check_count"):
            CIRunCompletedEvent(
                type="ci.run_completed",
                timestamp=now_iso(),
                source="orchestrator",
                project_id="proj-1",
                workflow_run_id="wf-123",
                check_count=-1,  # Invalid
                passed_count=0,
                failure_count=0,
                pending_count=0,
            )

    def test_negative_pending_count(self):
        """Test that pending_count must be non-negative."""
        with pytest.raises(ValueError, match="pending_count"):
            CIRunCompletedEvent(
                type="ci.run_completed",
                timestamp=now_iso(),
                source="orchestrator",
                project_id="proj-1",
                workflow_run_id="wf-123",
                check_count=3,
                passed_count=0,
                failure_count=0,
                pending_count=-1,  # Invalid
            )

    def test_count_consistency_exceeded(self):
        """Test that sum of counts cannot exceed check_count."""
        with pytest.raises(ValueError, match="exceeds check_count"):
            CIRunCompletedEvent(
                type="ci.run_completed",
                timestamp=now_iso(),
                source="orchestrator",
                project_id="proj-1",
                workflow_run_id="wf-123",
                check_count=2,
                passed_count=3,  # Impossible: exceeds check_count
                failure_count=0,
                pending_count=0,
            )

    def test_count_consistency_valid(self):
        """Test that valid count combinations are accepted."""
        # Sum equals check_count
        event = CIRunCompletedEvent(
            type="ci.run_completed",
            timestamp=now_iso(),
            source="orchestrator",
            project_id="proj-1",
            workflow_run_id="wf-123",
            check_count=5,
            passed_count=2,
            failure_count=1,
            pending_count=2,
        )
        assert event.check_count == 5
        assert event.passed_count + event.failure_count + event.pending_count == 5

        # Sum is less than check_count (skipped checks)
        event2 = CIRunCompletedEvent(
            type="ci.run_completed",
            timestamp=now_iso(),
            source="orchestrator",
            project_id="proj-1",
            workflow_run_id="wf-123",
            check_count=5,
            passed_count=2,
            failure_count=1,
            pending_count=1,  # Sum is 4, less than 5
        )
        assert event2.check_count == 5
        assert event2.passed_count + event2.failure_count + event2.pending_count == 4

    def test_run_completed_with_pending_checks(self):
        """Test CI run completed with pending checks."""
        event = CIRunCompletedEvent(
            type="ci.run_completed",
            timestamp=now_iso(),
            source="orchestrator",
            project_id="proj-1",
            workflow_run_id="wf-123",
            check_count=5,
            passed_count=2,
            failure_count=1,
            pending_count=2,
            warning_count=0,
            output="Some checks still running",
        )

        assert event.check_count == 5
        assert event.passed_count == 2
        assert event.failure_count == 1
        assert event.pending_count == 2
