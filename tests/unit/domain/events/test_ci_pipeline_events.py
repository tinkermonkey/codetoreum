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
        )

        assert event.pr_id == "456"
        assert event.project_id == "proj-1"
        assert event.status == "passed"
        assert event.check_count == 5
        assert event.passed_count == 5
        assert event.failed_count == 0

    def test_status_pending(self):
        """Test CI status checked with pending status."""
        event = CIPipelineStatusCheckedEvent(
            type="ci.pipeline_status_checked",
            timestamp=now_iso(),
            source="github",
            pr_id="456",
            project_id="proj-1",
            status="pending",
            check_count=0,
            passed_count=0,
            failed_count=0,
        )

        assert event.status == "pending"

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
        )

        assert event.status == "failed"
        assert event.failed_count == 3

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
        )

        d = event.to_dict()

        assert d["type"] == "ci.pipeline_status_checked"
        assert d["pr_id"] == "456"
        assert d["project_id"] == "proj-1"
        assert d["status"] == "passed"
        assert d["check_count"] == 5
        assert d["passed_count"] == 5
        assert d["failed_count"] == 0

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
        }

        event = CIPipelineStatusCheckedEvent.from_dict(d)

        assert event.type == "ci.pipeline_status_checked"
        assert event.pr_id == "456"
        assert event.project_id == "proj-1"
        assert event.status == "passed"
        assert event.check_count == 5
        assert event.passed_count == 5
        assert event.failed_count == 0

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
        )

        d = original.to_dict()
        restored = CIPipelineStatusCheckedEvent.from_dict(d)

        assert restored.pr_id == original.pr_id
        assert restored.project_id == original.project_id
        assert restored.status == original.status
        assert restored.check_count == original.check_count
        assert restored.passed_count == original.passed_count
        assert restored.failed_count == original.failed_count

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


class TestCIRunStartedEvent:
    """Test CIRunStartedEvent."""

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
        )

        assert event.project_id == "proj-1"
        assert event.workflow_run_id == "wf-123"
        assert event.working_directory == "/workspace"
        assert event.timeout_seconds == 600

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
        )

        assert event.timeout_seconds == 300

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
        )

        d = event.to_dict()

        assert d["type"] == "ci.run_started"
        assert d["project_id"] == "proj-1"
        assert d["workflow_run_id"] == "wf-123"
        assert d["working_directory"] == "/workspace"
        assert d["timeout_seconds"] == 600

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
        }

        event = CIRunStartedEvent.from_dict(d)

        assert event.type == "ci.run_started"
        assert event.project_id == "proj-1"
        assert event.workflow_run_id == "wf-123"
        assert event.working_directory == "/workspace"
        assert event.timeout_seconds == 600

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
        )

        d = original.to_dict()
        restored = CIRunStartedEvent.from_dict(d)

        assert restored.project_id == original.project_id
        assert restored.workflow_run_id == original.workflow_run_id
        assert restored.working_directory == original.working_directory
        assert restored.timeout_seconds == original.timeout_seconds

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

    def test_create_valid_event(self):
        """Test creating a valid CI run completed event."""
        timestamp = now_iso()
        event = CIRunCompletedEvent(
            type="ci.run_completed",
            timestamp=timestamp,
            source="orchestrator",
            project_id="proj-1",
            workflow_run_id="wf-123",
            passed=5,
            failed=0,
            output="All tests passed!",
        )

        assert event.project_id == "proj-1"
        assert event.workflow_run_id == "wf-123"
        assert event.passed == 5
        assert event.failed == 0
        assert event.output == "All tests passed!"

    def test_run_completed_with_failures(self):
        """Test CI run completed with failed checks."""
        event = CIRunCompletedEvent(
            type="ci.run_completed",
            timestamp=now_iso(),
            source="orchestrator",
            project_id="proj-1",
            workflow_run_id="wf-123",
            passed=3,
            failed=2,
            output="Some tests failed",
        )

        assert event.passed == 3
        assert event.failed == 2

    def test_run_completed_empty_output(self):
        """Test CI run completed with empty output."""
        event = CIRunCompletedEvent(
            type="ci.run_completed",
            timestamp=now_iso(),
            source="orchestrator",
            project_id="proj-1",
            workflow_run_id="wf-123",
            passed=0,
            failed=0,
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
                passed=5,
                failed=0,
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
                passed=5,
                failed=0,
            )

    def test_negative_passed(self):
        """Test that passed must be non-negative."""
        with pytest.raises(ValueError, match="passed"):
            CIRunCompletedEvent(
                type="ci.run_completed",
                timestamp=now_iso(),
                source="orchestrator",
                project_id="proj-1",
                workflow_run_id="wf-123",
                passed=-1,  # Invalid
                failed=0,
            )

    def test_negative_failed(self):
        """Test that failed must be non-negative."""
        with pytest.raises(ValueError, match="failed"):
            CIRunCompletedEvent(
                type="ci.run_completed",
                timestamp=now_iso(),
                source="orchestrator",
                project_id="proj-1",
                workflow_run_id="wf-123",
                passed=5,
                failed=-1,  # Invalid
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
            passed=5,
            failed=0,
            output="All tests passed!",
        )

        d = event.to_dict()

        assert d["type"] == "ci.run_completed"
        assert d["project_id"] == "proj-1"
        assert d["workflow_run_id"] == "wf-123"
        assert d["passed"] == 5
        assert d["failed"] == 0
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
            "passed": 5,
            "failed": 0,
            "output": "All tests passed!",
        }

        event = CIRunCompletedEvent.from_dict(d)

        assert event.type == "ci.run_completed"
        assert event.project_id == "proj-1"
        assert event.workflow_run_id == "wf-123"
        assert event.passed == 5
        assert event.failed == 0
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
            passed=5,
            failed=0,
            output="All tests passed!",
        )

        d = original.to_dict()
        restored = CIRunCompletedEvent.from_dict(d)

        assert restored.project_id == original.project_id
        assert restored.workflow_run_id == original.workflow_run_id
        assert restored.passed == original.passed
        assert restored.failed == original.failed
        assert restored.output == original.output

    def test_run_completed_missing_project_id_from_dict(self):
        """Test that from_dict raises KeyError when project_id is missing."""
        d = {
            "type": "ci.run_completed",
            "timestamp": now_iso(),
            "source": "orchestrator",
            "workflow_run_id": "wf-123",
            "passed": 5,
            "failed": 0,
        }

        with pytest.raises(KeyError):
            CIRunCompletedEvent.from_dict(d)

    def test_run_completed_missing_passed_from_dict(self):
        """Test that from_dict raises KeyError when passed is missing."""
        d = {
            "type": "ci.run_completed",
            "timestamp": now_iso(),
            "source": "orchestrator",
            "project_id": "proj-1",
            "workflow_run_id": "wf-123",
            "failed": 0,
        }

        with pytest.raises(KeyError):
            CIRunCompletedEvent.from_dict(d)

    def test_run_completed_missing_failed_from_dict(self):
        """Test that from_dict raises KeyError when failed is missing."""
        d = {
            "type": "ci.run_completed",
            "timestamp": now_iso(),
            "source": "orchestrator",
            "project_id": "proj-1",
            "workflow_run_id": "wf-123",
            "passed": 5,
        }

        with pytest.raises(KeyError):
            CIRunCompletedEvent.from_dict(d)
