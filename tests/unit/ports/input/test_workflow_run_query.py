"""
Unit tests for workflow run query input port types.
"""

import pytest

from codetoreum.ports.input.workflow_run_query import (
    WorkflowRunFilters,
    WorkflowRunPaginationParams,
    WorkflowRunStatus,
)


class TestWorkflowRunFilters:
    """Tests for WorkflowRunFilters validation."""

    def test_valid_filters(self):
        """Test creating valid filters."""
        filters = WorkflowRunFilters(
            status=(WorkflowRunStatus.RUNNING,),
            project_id="project-123",
            work_item_id="work-456",
            workflow_id="workflow-789",
        )
        assert filters.project_id == "project-123"
        assert filters.work_item_id == "work-456"
        assert filters.workflow_id == "workflow-789"
        assert filters.status == (WorkflowRunStatus.RUNNING,)

    def test_empty_project_id_raises_error(self):
        """Test that empty project_id raises ValueError."""
        with pytest.raises(ValueError, match="project_id must be non-empty if provided"):
            WorkflowRunFilters(project_id="")

    def test_whitespace_project_id_raises_error(self):
        """Test that whitespace-only project_id raises ValueError."""
        with pytest.raises(ValueError, match="project_id must be non-empty if provided"):
            WorkflowRunFilters(project_id="   ")

    def test_empty_work_item_id_raises_error(self):
        """Test that empty work_item_id raises ValueError."""
        with pytest.raises(ValueError, match="work_item_id must be non-empty if provided"):
            WorkflowRunFilters(work_item_id="")

    def test_whitespace_work_item_id_raises_error(self):
        """Test that whitespace-only work_item_id raises ValueError."""
        with pytest.raises(ValueError, match="work_item_id must be non-empty if provided"):
            WorkflowRunFilters(work_item_id="   ")

    def test_empty_workflow_id_raises_error(self):
        """Test that empty workflow_id raises ValueError."""
        with pytest.raises(ValueError, match="workflow_id must be non-empty if provided"):
            WorkflowRunFilters(workflow_id="")

    def test_whitespace_workflow_id_raises_error(self):
        """Test that whitespace-only workflow_id raises ValueError."""
        with pytest.raises(ValueError, match="workflow_id must be non-empty if provided"):
            WorkflowRunFilters(workflow_id="   ")

    def test_filters_are_immutable(self):
        """Test that WorkflowRunFilters is immutable (frozen)."""
        from dataclasses import FrozenInstanceError

        filters = WorkflowRunFilters(project_id="project-123")

        # Attempt to modify should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            filters.project_id = "new-value"  # type: ignore


class TestWorkflowRunPaginationParams:
    """Tests for WorkflowRunPaginationParams validation."""

    def test_valid_pagination(self):
        """Test creating valid pagination params."""
        params = WorkflowRunPaginationParams(offset=10, limit=50)
        assert params.offset == 10
        assert params.limit == 50

    def test_negative_offset_raises_error(self):
        """Test that negative offset raises ValueError."""
        with pytest.raises(ValueError, match="offset must be >= 0"):
            WorkflowRunPaginationParams(offset=-1)

    def test_zero_limit_raises_error(self):
        """Test that zero limit raises ValueError."""
        with pytest.raises(ValueError, match="limit must be > 0"):
            WorkflowRunPaginationParams(limit=0)

    def test_negative_limit_raises_error(self):
        """Test that negative limit raises ValueError."""
        with pytest.raises(ValueError, match="limit must be > 0"):
            WorkflowRunPaginationParams(limit=-1)

    def test_limit_exceeds_maximum(self):
        """Test that limit > 1000 raises ValueError to prevent DoS."""
        with pytest.raises(ValueError, match="limit must be <= 1000"):
            WorkflowRunPaginationParams(limit=1001)

    def test_limit_at_maximum(self):
        """Test that limit=1000 is allowed (at maximum)."""
        params = WorkflowRunPaginationParams(limit=1000)
        assert params.limit == 1000
