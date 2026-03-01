"""
Tests for critical issues fixed in PR #290.

This test suite verifies:
1. Development mock get_workflow_run_events returns proper WorkflowRunEventsResult dataclass
2. Development mock get_workflow_run_audit returns proper WorkflowRunAuditResult dataclass
3. AuditStageInfo.status Literal type includes all 6 status values
4. _build_stage_info correctly maps all 6 StageStatus enum values
"""

from typing import Literal, cast
from unittest.mock import MagicMock

import pytest

from codetoreum.adapters.primary.audit_dtos import AuditStageInfo
from codetoreum.domain.pipeline_stage import StageStatus


class TestDevelopmentMockReturnTypes:
    """Test that development mocks return proper dataclass types by inspecting source code."""

    def test_get_workflow_run_events_source_code(self):
        """Verify get_workflow_run_events source code returns WorkflowRunEventsResult."""
        # Read the source code and verify it returns the correct dataclass
        import importlib.util

        spec = importlib.util.find_spec("codetoreum.adapters.primary.fastapi_app")
        fastapi_app_path = spec.origin
        with open(fastapi_app_path) as f:
            content = f.read()

        # Verify the method returns WorkflowRunEventsResult, not a dict
        assert (
            "return WorkflowRunEventsResult(" in content
        ), "get_workflow_run_events should return WorkflowRunEventsResult dataclass"
        assert "total_count=1" in content, "Should use snake_case total_count, not camelCase totalCount"
        assert "has_next=False" in content, "Should use snake_case has_next, not camelCase hasNext"

        # Verify old broken code is gone
        assert '"totalCount": 1' not in content, "Old dict with camelCase totalCount should be removed"
        assert '"hasNext": False' not in content, "Old dict with camelCase hasNext should be removed"

    def test_get_workflow_run_audit_source_code(self):
        """Verify get_workflow_run_audit source code returns WorkflowRunAuditResult."""
        # Read the source code and verify it returns the correct dataclass
        import importlib.util

        spec = importlib.util.find_spec("codetoreum.adapters.primary.fastapi_app")
        fastapi_app_path = spec.origin
        with open(fastapi_app_path) as f:
            content = f.read()

        # Verify the method returns WorkflowRunAuditResult, not a dict
        assert (
            "return WorkflowRunAuditResult(" in content
        ), "get_workflow_run_audit should return WorkflowRunAuditResult dataclass"

        # Verify validation dict uses camelCase keys (per AuditValidationResult Pydantic model)
        assert '"sequenceValid": True' in content, "Validation dict should use camelCase sequenceValid"
        assert '"expectedSequence": []' in content, "Validation dict should use camelCase expectedSequence"
        assert '"actualSequence": []' in content, "Validation dict should use camelCase actualSequence"


class TestAuditStageInfoLiteralType:
    """Test that AuditStageInfo.status Literal includes all status values."""

    def test_all_status_values_allowed(self):
        """Verify AuditStageInfo accepts all 6 status values."""
        # All 6 status values from StageStatus enum
        valid_statuses: list[Literal["pending", "ready", "running", "completed", "failed", "skipped"]] = [
            "pending",
            "ready",
            "running",
            "completed",
            "failed",
            "skipped",
        ]

        for status in valid_statuses:
            # Should not raise validation error
            stage_info = AuditStageInfo(
                name=f"test-stage-{status}",
                status=status,
                startedAt=None,
                completedAt=None,
                durationSeconds=None,
                events=[],
                output=None,
                errorMessage=None,
                metadata={},
            )
            assert stage_info.status == status, f"Status {status} should be valid"

    def test_invalid_status_rejected(self):
        """Verify AuditStageInfo rejects invalid status values."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            AuditStageInfo(
                name="test-stage",
                status=cast(
                    "Literal['pending', 'ready', 'running', 'completed', 'failed', 'skipped']",
                    "invalid_status",
                ),  # Not in Literal
                startedAt=None,
                completedAt=None,
                durationSeconds=None,
                events=[],
                output=None,
                errorMessage=None,
                metadata={},
            )

        # Pydantic should reject this
        assert "invalid_status" in str(exc_info.value).lower() or "literal" in str(exc_info.value).lower()


class TestBuildStageInfoStatusMapping:
    """Test that _build_stage_info correctly maps all StageStatus enum values."""

    def test_all_status_mappings(self):
        """Verify all 6 StageStatus enum values are correctly mapped."""
        from codetoreum.adapters.testing.in_memory_event_store import InMemoryEventStore
        from codetoreum.application.workflow_run_query_service import (
            WorkflowRunQueryService,
        )
        from codetoreum.domain.pipeline_stage import PipelineStage
        from codetoreum.domain.workflow import Workflow

        # Create a minimal mock workflow with stages in all 6 statuses
        mock_workflow = MagicMock(spec=Workflow)

        # Test each status mapping
        status_mappings = [
            (StageStatus.PENDING, "pending"),
            (StageStatus.READY, "ready"),
            (StageStatus.RUNNING, "running"),
            (StageStatus.COMPLETED, "completed"),
            (StageStatus.FAILED, "failed"),
            (StageStatus.SKIPPED, "skipped"),
        ]

        for domain_status, expected_api_status in status_mappings:
            # Create a mock stage with the specific status
            mock_stage = MagicMock(spec=PipelineStage)
            mock_stage.status = domain_status
            mock_stage.name = f"stage-{domain_status.value}"
            mock_stage.agent_name = "test-agent"
            mock_stage.started_at = None
            mock_stage.completed_at = None
            mock_stage.execution_id = None
            mock_stage.output = None
            mock_stage.error_message = None
            mock_stage.metadata = {}

            mock_workflow.stages = [mock_stage]

            # Create service with correct parameters
            service = WorkflowRunQueryService(
                event_store=InMemoryEventStore(),
            )

            # Call _build_stage_info
            stages_info = service._build_stage_info(mock_workflow, events=[])

            # Verify the status was correctly mapped
            assert len(stages_info) == 1, f"Should have 1 stage for {domain_status}"
            assert (
                stages_info[0]["status"] == expected_api_status
            ), f"StageStatus.{domain_status.name} should map to '{expected_api_status}', got '{stages_info[0]['status']}'"

    def test_skipped_maps_to_skipped_not_pending(self):
        """Critical fix: SKIPPED should map to 'skipped', not 'pending'."""
        from codetoreum.adapters.testing.in_memory_event_store import InMemoryEventStore
        from codetoreum.application.workflow_run_query_service import (
            WorkflowRunQueryService,
        )
        from codetoreum.domain.pipeline_stage import PipelineStage
        from codetoreum.domain.workflow import Workflow

        # Create a mock workflow with a SKIPPED stage
        mock_stage = MagicMock(spec=PipelineStage)
        mock_stage.status = StageStatus.SKIPPED
        mock_stage.name = "skipped-stage"
        mock_stage.agent_name = "test-agent"
        mock_stage.started_at = None
        mock_stage.completed_at = None
        mock_stage.execution_id = None
        mock_stage.output = None
        mock_stage.error_message = None
        mock_stage.metadata = {}

        mock_workflow = MagicMock(spec=Workflow)
        mock_workflow.stages = [mock_stage]

        # Create service with correct parameters
        service = WorkflowRunQueryService(
            event_store=InMemoryEventStore(),
        )

        # Call _build_stage_info
        stages_info = service._build_stage_info(mock_workflow, events=[])

        # Critical assertion: SKIPPED must map to "skipped", not "pending"
        assert (
            stages_info[0]["status"] == "skipped"
        ), "CRITICAL BUG: StageStatus.SKIPPED incorrectly maps to 'pending' instead of 'skipped'"
