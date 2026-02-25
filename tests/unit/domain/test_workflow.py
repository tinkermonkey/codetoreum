"""Unit tests for Workflow aggregate root."""

from datetime import datetime

import pytest

from codetoreum.domain.events import (
    WorkflowCancelled,
    WorkflowCompleted,
    WorkflowCreated,
    WorkflowFailed,
    WorkflowPaused,
    WorkflowResumed,
    WorkflowStageAdvanced,
    WorkflowStageStatusUpdated,
    WorkflowStarted,
)
from codetoreum.domain.exceptions import DomainError
from codetoreum.domain.pipeline_stage import StageStatus
from codetoreum.domain.workflow import Workflow, WorkflowStatus
from codetoreum.domain.workflow_template import WorkflowTemplate


class TestWorkflowCreation:
    """Test Workflow creation."""

    def test_create_workflow_from_template(self):
        """Test creating a workflow from a template."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")
        template.add_stage("stage2", "agent-2", dependencies=["stage1"])

        workflow = Workflow.create("work-item-1", template, "project-1")

        assert workflow.id is not None
        assert workflow.work_item_id == "work-item-1"
        assert workflow.template_id == template.id
        assert workflow.project_id == "project-1"
        assert workflow.status == WorkflowStatus.PENDING
        assert len(workflow.stages) == 2
        assert workflow.current_stage_index == 0
        assert workflow.completed_stages == []
        assert workflow.started_at is None
        assert workflow.completed_at is None
        assert workflow.paused_at is None
        assert workflow.created_at is not None
        assert workflow.updated_at is not None

    def test_create_workflow_emits_event(self):
        """Test that creating a workflow emits WorkflowCreated event."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")

        events = workflow.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkflowCreated)
        assert events[0].aggregate_id == workflow.id
        assert events[0].payload["work_item_id"] == "work-item-1"
        assert events[0].payload["template_id"] == template.id
        assert events[0].payload["project_id"] == "project-1"
        assert events[0].payload["stage_count"] == 1

    def test_create_workflow_sets_workflow_id_on_stages(self):
        """Test that creating workflow sets workflow_id on all stages."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")
        template.add_stage("stage2", "agent-2")

        workflow = Workflow.create("work-item-1", template, "project-1")

        for stage in workflow.stages:
            assert stage.workflow_id == workflow.id


class TestWorkflowInvariants:
    """Test workflow invariant validation."""

    def test_workflow_must_have_at_least_one_stage(self):
        """Test that workflow must have at least one stage."""
        template = WorkflowTemplate.create("test", "Test Template")

        with pytest.raises(DomainError, match="at least one stage"):
            Workflow.create("work-item-1", template, "project-1")

    def test_workflow_cannot_exceed_max_parallel_stages(self):
        """Test that workflow cannot have more than 10 parallel stages."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")
        for i in range(11):
            template.add_stage(
                f"parallel-{i}",
                f"agent-{i}",
                dependencies=["stage1"],
                is_parallel=True,
            )

        with pytest.raises(DomainError, match="Cannot exceed 10 parallel stages"):
            Workflow.create("work-item-1", template, "project-1")

    def test_workflow_detects_circular_dependencies(self):
        """Test that workflow detects circular dependencies."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1", dependencies=["stage2"])
        template.add_stage("stage2", "agent-2", dependencies=["stage1"])

        with pytest.raises(DomainError, match="circular stage dependencies"):
            Workflow.create("work-item-1", template, "project-1")

    def test_workflow_validates_dependencies(self):
        """Test that workflow validates all dependencies are satisfied."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1", dependencies=["nonexistent"])

        with pytest.raises(DomainError, match="dependencies are satisfied"):
            Workflow.create("work-item-1", template, "project-1")


class TestWorkflowLifecycle:
    """Test workflow lifecycle methods."""

    def test_start_workflow(self):
        """Test starting a workflow."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")
        workflow.clear_events()

        workflow.start()

        assert workflow.status == WorkflowStatus.RUNNING
        assert workflow.started_at is not None
        assert isinstance(workflow.started_at, datetime)

        events = workflow.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkflowStarted)

    def test_start_workflow_fails_if_not_pending(self):
        """Test that start fails if workflow is not pending."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")
        workflow.start()

        with pytest.raises(DomainError, match="Cannot start workflow in status"):
            workflow.start()

    def test_advance_to_next_stage(self):
        """Test advancing to next stage."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")
        template.add_stage("stage2", "agent-2")

        workflow = Workflow.create("work-item-1", template, "project-1")
        workflow.start()
        workflow.clear_events()

        # Complete current stage
        current_stage = workflow.get_current_stage()
        current_stage.mark_ready()
        current_stage.start("exec-1")
        current_stage.complete("output")

        workflow.advance_to_next_stage()

        assert workflow.current_stage_index == 1
        assert "stage1" in workflow.completed_stages
        assert workflow.status == WorkflowStatus.RUNNING

        events = workflow.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkflowStageAdvanced)

    def test_advance_completes_workflow_on_last_stage(self):
        """Test that advancing on last stage completes workflow."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")
        workflow.start()
        workflow.clear_events()

        # Complete the only stage
        current_stage = workflow.get_current_stage()
        current_stage.mark_ready()
        current_stage.start("exec-1")
        current_stage.complete("output")

        workflow.advance_to_next_stage()

        assert workflow.status == WorkflowStatus.COMPLETED
        assert workflow.completed_at is not None

        events = workflow.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkflowCompleted)

    def test_advance_fails_if_not_running(self):
        """Test that advance fails if workflow is not running."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")

        with pytest.raises(DomainError, match="Cannot advance non-running workflow"):
            workflow.advance_to_next_stage()

    def test_advance_fails_if_current_stage_not_completed(self):
        """Test that advance fails if current stage is not completed."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")
        template.add_stage("stage2", "agent-2")

        workflow = Workflow.create("work-item-1", template, "project-1")
        workflow.start()

        with pytest.raises(DomainError, match="current stage not completed"):
            workflow.advance_to_next_stage()

    def test_complete_workflow(self):
        """Test completing a workflow."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")
        workflow.start()

        # Complete all stages
        for stage in workflow.stages:
            stage.mark_ready()
            stage.start("exec-1")
            stage.complete("output")

        workflow.clear_events()
        workflow.complete()

        assert workflow.status == WorkflowStatus.COMPLETED
        assert workflow.completed_at is not None

        events = workflow.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkflowCompleted)

    def test_complete_fails_if_not_running(self):
        """Test that complete fails if workflow is not running."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")

        with pytest.raises(DomainError, match="Cannot complete workflow in status"):
            workflow.complete()

    def test_complete_fails_if_stages_not_completed(self):
        """Test that complete fails if not all stages are completed."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")
        template.add_stage("stage2", "agent-2")

        workflow = Workflow.create("work-item-1", template, "project-1")
        workflow.start()

        with pytest.raises(DomainError, match="not completed"):
            workflow.complete()

    def test_fail_workflow(self):
        """Test failing a workflow."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")
        workflow.start()
        workflow.clear_events()

        workflow.fail("Something went wrong")

        assert workflow.status == WorkflowStatus.FAILED

        events = workflow.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkflowFailed)
        assert events[0].payload["reason"] == "Something went wrong"

    def test_fail_workflow_with_failed_stage(self):
        """Test failing workflow with specific failed stage."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")
        workflow.start()
        workflow.clear_events()

        workflow.fail("Error in stage", failed_stage="stage1")

        events = workflow.get_pending_events()
        assert events[0].payload["failed_stage"] == "stage1"

    def test_fail_fails_if_completed(self):
        """Test that fail fails if workflow is completed."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")
        workflow.start()

        # Complete workflow
        stage = workflow.get_current_stage()
        stage.mark_ready()
        stage.start("exec-1")
        stage.complete("output")
        workflow.advance_to_next_stage()

        with pytest.raises(DomainError, match="Cannot fail workflow in terminal"):
            workflow.fail("reason")

    def test_pause_workflow(self):
        """Test pausing a workflow."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")
        workflow.start()
        workflow.clear_events()

        workflow.pause("User requested pause")

        assert workflow.status == WorkflowStatus.PAUSED
        assert workflow.paused_at is not None

        events = workflow.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkflowPaused)

    def test_pause_fails_if_not_running(self):
        """Test that pause fails if workflow is not running."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")

        with pytest.raises(DomainError, match="Can only pause running workflows"):
            workflow.pause("reason")

    def test_resume_workflow(self):
        """Test resuming a paused workflow."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")
        workflow.start()
        workflow.pause("Paused")
        workflow.clear_events()

        workflow.resume()

        assert workflow.status == WorkflowStatus.RUNNING

        events = workflow.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkflowResumed)

    def test_resume_fails_if_not_paused(self):
        """Test that resume fails if workflow is not paused."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")

        with pytest.raises(DomainError, match="Can only resume paused workflows"):
            workflow.resume()

    def test_cancel_workflow(self):
        """Test cancelling a workflow."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")
        workflow.start()
        workflow.clear_events()

        workflow.cancel("User cancelled")

        assert workflow.status == WorkflowStatus.CANCELLED

        events = workflow.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkflowCancelled)

    def test_cancel_fails_if_completed(self):
        """Test that cancel fails if workflow is completed."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")
        workflow.start()

        # Complete workflow
        stage = workflow.get_current_stage()
        stage.mark_ready()
        stage.start("exec-1")
        stage.complete("output")
        workflow.advance_to_next_stage()

        with pytest.raises(DomainError, match="Cannot cancel workflow in terminal"):
            workflow.cancel("reason")


class TestStageManagement:
    """Test workflow stage management methods."""

    def test_get_current_stage(self):
        """Test getting current stage."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")
        template.add_stage("stage2", "agent-2")

        workflow = Workflow.create("work-item-1", template, "project-1")

        current_stage = workflow.get_current_stage()
        assert current_stage.name == "stage1"

    def test_get_stage_by_name(self):
        """Test getting stage by name."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")
        template.add_stage("stage2", "agent-2")

        workflow = Workflow.create("work-item-1", template, "project-1")

        stage = workflow.get_stage_by_name("stage2")
        assert stage is not None
        assert stage.name == "stage2"

    def test_get_stage_by_name_not_found(self):
        """Test getting stage by name that doesn't exist."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")

        stage = workflow.get_stage_by_name("nonexistent")
        assert stage is None

    def test_update_stage_status(self):
        """Test updating stage status."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")
        workflow.clear_events()

        workflow.update_stage_status("stage1", "ready")

        stage = workflow.get_stage_by_name("stage1")
        assert stage is not None
        assert stage.status == StageStatus.READY

        events = workflow.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkflowStageStatusUpdated)

    def test_update_stage_status_not_found(self):
        """Test updating status of non-existent stage."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")

        with pytest.raises(DomainError, match="not found"):
            workflow.update_stage_status("nonexistent", "ready")


class TestWorkflowQueries:
    """Test workflow query methods."""

    def test_is_completed(self):
        """Test is_completed method."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")
        assert not workflow.is_completed()

        workflow.start()
        stage = workflow.get_current_stage()
        stage.mark_ready()
        stage.start("exec-1")
        stage.complete("output")
        workflow.advance_to_next_stage()

        assert workflow.is_completed()

    def test_is_failed(self):
        """Test is_failed method."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")
        assert not workflow.is_failed()

        workflow.start()
        workflow.fail("error")

        assert workflow.is_failed()

    def test_is_running(self):
        """Test is_running method."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")
        assert not workflow.is_running()

        workflow.start()
        assert workflow.is_running()

    def test_get_progress_percentage(self):
        """Test get_progress_percentage method."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")
        template.add_stage("stage2", "agent-2")
        template.add_stage("stage3", "agent-3")

        workflow = Workflow.create("work-item-1", template, "project-1")
        assert workflow.get_progress_percentage() == 0.0

        workflow.completed_stages = ["stage1"]
        assert workflow.get_progress_percentage() == pytest.approx(33.33, rel=0.01)

        workflow.completed_stages = ["stage1", "stage2"]
        assert workflow.get_progress_percentage() == pytest.approx(66.66, rel=0.01)

        workflow.completed_stages = ["stage1", "stage2", "stage3"]
        assert workflow.get_progress_percentage() == 100.0

    def test_get_duration_seconds(self):
        """Test get_duration_seconds method."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")
        assert workflow.get_duration_seconds() is None

        workflow.start()
        duration = workflow.get_duration_seconds()
        assert duration is not None
        assert duration >= 0
        assert isinstance(duration, int)


class TestEventManagement:
    """Test workflow event management."""

    def test_get_pending_events(self):
        """Test getting pending events."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")

        events = workflow.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkflowCreated)

    def test_clear_events(self):
        """Test clearing pending events."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")
        assert len(workflow.get_pending_events()) == 1

        workflow.clear_events()
        assert len(workflow.get_pending_events()) == 0

    def test_version_increments(self):
        """Test that version increments on state changes."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        workflow = Workflow.create("work-item-1", template, "project-1")
        initial_version = workflow._version

        workflow.start()
        assert workflow._version == initial_version + 1

        workflow.pause("reason")
        assert workflow._version == initial_version + 2


class TestEventSourcing:
    """Test event sourcing support."""

    def test_from_events_empty_list(self):
        """Test reconstruction from empty event list fails."""
        with pytest.raises(DomainError, match="empty event stream"):
            Workflow.from_events([])

    def test_from_events_wrong_first_event(self):
        """Test reconstruction with wrong first event fails."""
        from codetoreum.domain.events import WorkflowStarted

        event = WorkflowStarted("wf-1", {"started_at": "2024-01-01T00:00:00"})

        with pytest.raises(DomainError, match="First event must be WorkflowCreated"):
            Workflow.from_events([event])

    def test_from_events_basic(self):
        """Test basic event reconstruction."""
        created_event = WorkflowCreated(
            "wf-1",
            {
                "work_item_id": "work-1",
                "template_id": "template-1",
                "project_id": "project-1",
                "stage_count": 1,
            },
        )

        workflow = Workflow.from_events([created_event])

        assert workflow.id == "wf-1"
        assert workflow.work_item_id == "work-1"
        assert workflow.template_id == "template-1"
        assert workflow.project_id == "project-1"
        assert workflow.status == WorkflowStatus.PENDING

    def test_apply_workflow_started_event(self):
        """Test applying WorkflowStarted event."""
        created_event = WorkflowCreated(
            "wf-1",
            {
                "work_item_id": "work-1",
                "template_id": "template-1",
                "project_id": "project-1",
                "stage_count": 1,
            },
        )
        started_event = WorkflowStarted(
            "wf-1",
            {
                "started_at": "2024-01-01T00:00:00",
                "work_item_id": "work-1",
                "first_stage": "stage1",
            },
        )

        workflow = Workflow.from_events([created_event, started_event])

        assert workflow.status == WorkflowStatus.RUNNING
        assert workflow.started_at is not None

    def test_apply_workflow_completed_event(self):
        """Test applying WorkflowCompleted event."""
        created_event = WorkflowCreated(
            "wf-1",
            {
                "work_item_id": "work-1",
                "template_id": "template-1",
                "project_id": "project-1",
                "stage_count": 1,
            },
        )
        completed_event = WorkflowCompleted(
            "wf-1",
            {
                "completed_at": "2024-01-01T00:00:00",
                "work_item_id": "work-1",
                "duration_seconds": 100.0,
            },
        )

        workflow = Workflow.from_events([created_event, completed_event])

        assert workflow.status == WorkflowStatus.COMPLETED
        assert workflow.completed_at is not None
