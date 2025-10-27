"""Unit tests for PipelineStage entity."""

import pytest
from datetime import datetime, timezone

from codetoreum.domain.pipeline_stage import (
    PipelineStage,
    StageStatus,
    StageType,
)
from codetoreum.domain.exceptions import DomainError


class TestPipelineStageCreation:
    """Test PipelineStage creation."""

    def test_create_minimal_stage(self):
        """Test creating a stage with minimal parameters."""
        stage = PipelineStage.create(
            name="test-stage",
            workflow_id="wf-123",
            agent_id="agent-1",
        )

        assert stage.name == "test-stage"
        assert stage.workflow_id == "wf-123"
        assert stage.agent_id == "agent-1"
        assert stage.stage_type == StageType.SEQUENTIAL
        assert stage.status == StageStatus.PENDING
        assert stage.dependencies == []
        assert stage.is_parallel is False
        assert stage.requires_review is False
        assert stage.execution_id is None
        assert stage.started_at is None
        assert stage.completed_at is None
        assert stage.output is None
        assert stage.error_message is None
        assert stage.metadata == {}

    def test_create_stage_with_all_parameters(self):
        """Test creating a stage with all parameters."""
        stage = PipelineStage.create(
            name="review-stage",
            workflow_id="wf-123",
            agent_id="agent-1",
            stage_type=StageType.REVIEW,
            description="Review stage description",
            dependencies=["stage-1", "stage-2"],
            is_parallel=True,
            requires_review=True,
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
            max_review_iterations=5,
        )

        assert stage.name == "review-stage"
        assert stage.workflow_id == "wf-123"
        assert stage.agent_id == "agent-1"
        assert stage.stage_type == StageType.REVIEW
        assert stage.description == "Review stage description"
        assert stage.dependencies == ["stage-1", "stage-2"]
        assert stage.is_parallel is True
        assert stage.requires_review is True
        assert stage.maker_agent_id == "maker-1"
        assert stage.reviewer_agent_id == "reviewer-1"
        assert stage.max_review_iterations == 5
        assert stage.status == StageStatus.PENDING


class TestStageLifecycle:
    """Test PipelineStage lifecycle methods."""

    def test_mark_ready(self):
        """Test marking a stage as ready."""
        stage = PipelineStage.create("test", "wf-1", "agent-1")
        assert stage.status == StageStatus.PENDING

        stage.mark_ready()
        assert stage.status == StageStatus.READY

    def test_mark_ready_fails_if_not_pending(self):
        """Test that mark_ready fails if stage is not pending."""
        stage = PipelineStage.create("test", "wf-1", "agent-1")
        stage.mark_ready()

        with pytest.raises(DomainError, match="Cannot mark ready"):
            stage.mark_ready()

    def test_start_stage(self):
        """Test starting a stage."""
        stage = PipelineStage.create("test", "wf-1", "agent-1")
        stage.mark_ready()

        stage.start("exec-123")
        assert stage.status == StageStatus.RUNNING
        assert stage.execution_id == "exec-123"
        assert stage.started_at is not None
        assert isinstance(stage.started_at, datetime)

    def test_start_fails_if_not_ready(self):
        """Test that start fails if stage is not ready."""
        stage = PipelineStage.create("test", "wf-1", "agent-1")

        with pytest.raises(DomainError, match="Cannot start: stage not ready"):
            stage.start("exec-123")

    def test_complete_stage(self):
        """Test completing a stage."""
        stage = PipelineStage.create("test", "wf-1", "agent-1")
        stage.mark_ready()
        stage.start("exec-123")

        stage.complete("output data")
        assert stage.status == StageStatus.COMPLETED
        assert stage.output == "output data"
        assert stage.completed_at is not None
        assert isinstance(stage.completed_at, datetime)

    def test_complete_fails_if_not_running(self):
        """Test that complete fails if stage is not running."""
        stage = PipelineStage.create("test", "wf-1", "agent-1")

        with pytest.raises(DomainError, match="Cannot complete: stage not running"):
            stage.complete("output")

    def test_fail_stage(self):
        """Test failing a stage."""
        stage = PipelineStage.create("test", "wf-1", "agent-1")
        stage.mark_ready()
        stage.start("exec-123")

        stage.fail("Something went wrong")
        assert stage.status == StageStatus.FAILED
        assert stage.error_message == "Something went wrong"
        assert stage.completed_at is not None

    def test_fail_stage_from_ready(self):
        """Test failing a stage from ready status."""
        stage = PipelineStage.create("test", "wf-1", "agent-1")
        stage.mark_ready()

        stage.fail("Failed before starting")
        assert stage.status == StageStatus.FAILED
        assert stage.error_message == "Failed before starting"

    def test_fail_fails_from_invalid_status(self):
        """Test that fail fails from invalid status."""
        stage = PipelineStage.create("test", "wf-1", "agent-1")

        with pytest.raises(DomainError, match="Cannot fail: invalid status"):
            stage.fail("error")

    def test_skip_stage(self):
        """Test skipping a stage."""
        stage = PipelineStage.create("test", "wf-1", "agent-1")

        stage.skip("Not needed")
        assert stage.status == StageStatus.SKIPPED
        assert stage.metadata["skip_reason"] == "Not needed"
        assert stage.completed_at is not None

    def test_skip_fails_if_not_pending(self):
        """Test that skip fails if stage is not pending."""
        stage = PipelineStage.create("test", "wf-1", "agent-1")
        stage.mark_ready()

        with pytest.raises(DomainError, match="Cannot skip: stage in status"):
            stage.skip("reason")


class TestStageDependencies:
    """Test stage dependency logic."""

    def test_can_start_with_no_dependencies(self):
        """Test that stage with no dependencies can start."""
        stage = PipelineStage.create("test", "wf-1", "agent-1")
        stage.mark_ready()

        assert stage.can_start([])
        assert stage.can_start(["other-stage"])

    def test_can_start_with_satisfied_dependencies(self):
        """Test that stage can start when dependencies are satisfied."""
        stage = PipelineStage.create(
            "test", "wf-1", "agent-1", dependencies=["stage-1", "stage-2"]
        )
        stage.mark_ready()

        assert not stage.can_start([])
        assert not stage.can_start(["stage-1"])
        assert stage.can_start(["stage-1", "stage-2"])
        assert stage.can_start(["stage-1", "stage-2", "stage-3"])

    def test_can_start_fails_if_not_pending_or_ready(self):
        """Test that can_start returns False if stage is not pending or ready."""
        stage = PipelineStage.create("test", "wf-1", "agent-1")
        stage.mark_ready()
        stage.start("exec-1")

        assert not stage.can_start([])


class TestStageQueries:
    """Test stage query methods."""

    def test_is_completed(self):
        """Test is_completed method."""
        stage = PipelineStage.create("test", "wf-1", "agent-1")
        assert not stage.is_completed()

        stage.mark_ready()
        stage.start("exec-1")
        stage.complete("output")
        assert stage.is_completed()

    def test_is_failed(self):
        """Test is_failed method."""
        stage = PipelineStage.create("test", "wf-1", "agent-1")
        assert not stage.is_failed()

        stage.mark_ready()
        stage.start("exec-1")
        stage.fail("error")
        assert stage.is_failed()

    def test_is_terminal(self):
        """Test is_terminal method."""
        stage = PipelineStage.create("test", "wf-1", "agent-1")
        assert not stage.is_terminal()

        # Completed is terminal
        stage_completed = PipelineStage.create("test1", "wf-1", "agent-1")
        stage_completed.mark_ready()
        stage_completed.start("exec-1")
        stage_completed.complete("output")
        assert stage_completed.is_terminal()

        # Failed is terminal
        stage_failed = PipelineStage.create("test2", "wf-1", "agent-1")
        stage_failed.mark_ready()
        stage_failed.start("exec-2")
        stage_failed.fail("error")
        assert stage_failed.is_terminal()

        # Skipped is terminal
        stage_skipped = PipelineStage.create("test3", "wf-1", "agent-1")
        stage_skipped.skip("not needed")
        assert stage_skipped.is_terminal()

    def test_get_duration_seconds(self):
        """Test get_duration_seconds method."""
        stage = PipelineStage.create("test", "wf-1", "agent-1")
        assert stage.get_duration_seconds() is None

        stage.mark_ready()
        stage.start("exec-1")
        assert stage.get_duration_seconds() is None

        stage.complete("output")
        duration = stage.get_duration_seconds()
        assert duration is not None
        assert duration >= 0
        assert isinstance(duration, float)

    def test_update_status(self):
        """Test update_status method."""
        stage = PipelineStage.create("test", "wf-1", "agent-1")
        assert stage.status == StageStatus.PENDING

        stage.update_status("ready")
        assert stage.status == StageStatus.READY

        stage.update_status("running")
        assert stage.status == StageStatus.RUNNING

    def test_update_status_invalid_value(self):
        """Test update_status with invalid value."""
        stage = PipelineStage.create("test", "wf-1", "agent-1")

        with pytest.raises(ValueError):
            stage.update_status("invalid")


class TestStageTypes:
    """Test different stage types."""

    def test_sequential_stage(self):
        """Test sequential stage type."""
        stage = PipelineStage.create(
            "test", "wf-1", "agent-1", stage_type=StageType.SEQUENTIAL
        )
        assert stage.stage_type == StageType.SEQUENTIAL
        assert not stage.is_parallel

    def test_parallel_stage(self):
        """Test parallel stage type."""
        stage = PipelineStage.create(
            "test",
            "wf-1",
            "agent-1",
            stage_type=StageType.PARALLEL,
            is_parallel=True,
        )
        assert stage.stage_type == StageType.PARALLEL
        assert stage.is_parallel

    def test_review_stage(self):
        """Test review stage type."""
        stage = PipelineStage.create(
            "test",
            "wf-1",
            "agent-1",
            stage_type=StageType.REVIEW,
            requires_review=True,
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )
        assert stage.stage_type == StageType.REVIEW
        assert stage.requires_review
        assert stage.maker_agent_id == "maker-1"
        assert stage.reviewer_agent_id == "reviewer-1"


class TestStageMetadata:
    """Test stage metadata handling."""

    def test_metadata_initialization(self):
        """Test that metadata is initialized as empty dict."""
        stage = PipelineStage.create("test", "wf-1", "agent-1")
        assert stage.metadata == {}
        assert isinstance(stage.metadata, dict)

    def test_metadata_modification(self):
        """Test modifying stage metadata."""
        stage = PipelineStage.create("test", "wf-1", "agent-1")
        stage.metadata["custom_key"] = "custom_value"
        assert stage.metadata["custom_key"] == "custom_value"

    def test_skip_reason_in_metadata(self):
        """Test that skip reason is stored in metadata."""
        stage = PipelineStage.create("test", "wf-1", "agent-1")
        stage.skip("Not applicable")
        assert "skip_reason" in stage.metadata
        assert stage.metadata["skip_reason"] == "Not applicable"
