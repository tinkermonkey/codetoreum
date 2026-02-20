"""Unit tests for WorkflowRunMapper.to_audit_response.

These tests verify that the WorkflowRunMapper.to_audit_response method correctly
converts audit data dictionaries to WorkflowRunAuditResponse DTOs.
"""

from datetime import datetime, timezone

import pytest

from codetoreum.adapters.primary.workflow_run_mappers import WorkflowRunMapper
from codetoreum.ports.input.workflow_run_query import WorkflowRunSummary, WorkflowRunStatus


class TestWorkflowRunMapperAuditResponse:
    """Test suite for WorkflowRunMapper.to_audit_response."""

    def _create_workflow_run_summary(self, **kwargs):
        """Helper to create WorkflowRunSummary with defaults."""
        defaults = {
            "id": "wfrun-123",
            "workflow_id": "wf-456",
            "project_id": "proj-789",
            "work_item_id": "wi-101",
            "status": WorkflowRunStatus.COMPLETED,
            "current_stage_index": 2,
            "current_stage_name": "Review",
            "started_at": datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            "completed_at": datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            "duration": 7200,
            "issue_title": "Test Issue",
            "issue_number": 42,
            "project": "test-project",
            "triggered_by": "user-123",
            "priority": "HIGH",
        }
        defaults.update(kwargs)
        return WorkflowRunSummary(**defaults)

    def test_to_audit_response_with_full_data(self):
        """Test converting complete audit data to WorkflowRunAuditResponse."""
        # Arrange
        audit_data = {
            "workflow_run": self._create_workflow_run_summary(),
            "events": [
                {
                    "event_id": "evt-1",
                    "event_type": "WorkflowRunStarted",
                    "timestamp": datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
                    "sequence_number": 1,
                    "data": {},
                },
            ],
            "stages": [
                {
                    "name": "Build",
                    "status": "completed",
                    "startedAt": datetime(2025, 1, 15, 10, 5, 0, tzinfo=timezone.utc),
                    "completedAt": datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
                    "durationSeconds": 1500,
                    "events": [],
                }
            ],
            "validation": None,  # Validation details tested in integration tests
            "total_event_count": 42,
            "offset": 0,
            "limit": 100,
            "has_next": False,
        }

        # Act
        response = WorkflowRunMapper.to_audit_response(audit_data)

        # Assert
        assert response.workflowRun.id == "wfrun-123"
        assert len(response.events) == 1
        assert len(response.stages) == 1
        assert response.validation is None  # Not testing validation structure (integration tests cover this)
        assert response.totalEventCount == 42
        assert response.offset == 0
        assert response.limit == 100
        assert response.hasNext is False

    def test_to_audit_response_with_snake_case_stage_fields(self):
        """Test that mapper handles both camelCase and snake_case stage fields."""
        # Arrange
        audit_data = {
            "workflow_run": self._create_workflow_run_summary(status=WorkflowRunStatus.RUNNING),
            "events": [],
            "stages": [
                {
                    "name": "Test",
                    "status": "running",
                    "started_at": datetime(2025, 1, 15, 11, 0, 0, tzinfo=timezone.utc),
                    "completed_at": None,
                    "duration_seconds": None,
                    "events": [],
                }
            ],
            "validation": None,
            "total_event_count": 10,
            "offset": 0,
            "limit": 100,
            "has_next": False,
        }

        # Act
        response = WorkflowRunMapper.to_audit_response(audit_data)

        # Assert - Stage fields mapped correctly from snake_case
        assert len(response.stages) == 1
        assert response.stages[0].name == "Test"
        assert response.stages[0].status == "running"
        assert response.stages[0].startedAt == datetime(2025, 1, 15, 11, 0, 0, tzinfo=timezone.utc)
        assert response.stages[0].completedAt is None
        assert response.stages[0].durationSeconds is None

    def test_to_audit_response_with_none_validation(self):
        """Test that mapper handles None validation when include_validation=False."""
        # Arrange
        audit_data = {
            "workflow_run": self._create_workflow_run_summary(),
            "events": [],
            "stages": [],
            "validation": None,  # Validation disabled
            "total_event_count": 5,
            "offset": 0,
            "limit": 100,
            "has_next": False,
        }

        # Act
        response = WorkflowRunMapper.to_audit_response(audit_data)

        # Assert - Validation should be None
        assert response.validation is None
        assert response.totalEventCount == 5

    def test_to_audit_response_with_pagination(self):
        """Test pagination fields are correctly mapped."""
        # Arrange
        audit_data = {
            "workflow_run": self._create_workflow_run_summary(status=WorkflowRunStatus.RUNNING),
            "events": [],
            "stages": [],
            "validation": None,
            "total_event_count": 500,
            "offset": 100,
            "limit": 200,
            "has_next": True,
        }

        # Act
        response = WorkflowRunMapper.to_audit_response(audit_data)

        # Assert - Pagination
        assert response.totalEventCount == 500
        assert response.offset == 100
        assert response.limit == 200
        assert response.hasNext is True
