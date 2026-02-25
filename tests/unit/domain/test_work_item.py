"""Unit tests for WorkItem aggregate root."""

from datetime import datetime

import pytest

from codetoreum.domain import (
    AgentAssigned,
    DomainError,
    WorkflowAttached,
    WorkItem,
    WorkItemBlocked,
    WorkItemCompleted,
    WorkItemCreated,
    WorkItemFailed,
    WorkItemLabelsUpdated,
    WorkItemPriority,
    WorkItemPriorityUpdated,
    WorkItemStageUpdated,
    WorkItemStarted,
    WorkItemStatus,
    WorkItemUnblocked,
    WorkItemUnderReview,
)


class TestWorkItemCreation:
    """Test work item creation and validation."""

    def test_create_work_item(self):
        """Test work item creation with valid data."""
        work_item = WorkItem.create(
            title="Test Feature",
            description="Test description",
            project_id="proj-1",
        )

        assert work_item.id is not None
        assert work_item.title == "Test Feature"
        assert work_item.description == "Test description"
        assert work_item.project_id == "proj-1"
        assert work_item.status == WorkItemStatus.NEW
        assert work_item.priority == WorkItemPriority.MEDIUM
        assert work_item.labels == []
        assert work_item.assigned_agent_id is None
        assert work_item.created_at is not None
        assert work_item.updated_at is not None

    def test_create_work_item_with_all_fields(self):
        """Test work item creation with all optional fields."""
        work_item = WorkItem.create(
            title="Test Feature",
            description="Test description",
            project_id="proj-1",
            labels=["bug", "high-priority"],
            priority=WorkItemPriority.HIGH,
            external_id="123",
            external_url="https://github.com/org/repo/issues/123",
        )

        assert work_item.labels == ["bug", "high-priority"]
        assert work_item.priority == WorkItemPriority.HIGH
        assert work_item.external_id == "123"
        assert work_item.external_url == "https://github.com/org/repo/issues/123"

    def test_create_emits_event(self):
        """Test that creation emits WorkItemCreated event."""
        work_item = WorkItem.create(
            title="Test Feature",
            description="Test description",
            project_id="proj-1",
        )

        events = work_item.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkItemCreated)
        assert events[0].aggregate_id == work_item.id
        assert events[0].payload["title"] == "Test Feature"

    def test_create_with_empty_title_raises_error(self):
        """Test that empty title raises DomainError."""
        with pytest.raises(DomainError) as exc:
            WorkItem.create(
                title="",
                description="Test description",
                project_id="proj-1",
            )
        assert "non-empty title" in str(exc.value)

    def test_create_with_whitespace_title_raises_error(self):
        """Test that whitespace-only title raises DomainError."""
        with pytest.raises(DomainError) as exc:
            WorkItem.create(
                title="   ",
                description="Test description",
                project_id="proj-1",
            )
        assert "non-empty title" in str(exc.value)


class TestWorkItemAssignment:
    """Test agent assignment."""

    def test_assign_agent(self):
        """Test assigning agent to work item."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.clear_events()

        work_item.assign_agent("agent-1", "Best match for this task")

        assert work_item.assigned_agent_id == "agent-1"
        assert work_item.assigned_at is not None
        assert work_item.status == WorkItemStatus.ASSIGNED
        assert work_item._version == 1

        events = work_item.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], AgentAssigned)
        assert events[0].payload["agent_id"] == "agent-1"
        assert events[0].payload["reason"] == "Best match for this task"

    def test_assign_agent_to_already_assigned_item(self):
        """Test reassigning different agent to assigned item."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.assign_agent("agent-1", "First assignment")
        work_item.clear_events()

        work_item.assign_agent("agent-2", "Reassignment")

        assert work_item.assigned_agent_id == "agent-2"

    def test_assign_same_agent_twice_raises_error(self):
        """Test that assigning same agent twice raises error."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.assign_agent("agent-1", "First assignment")

        with pytest.raises(DomainError) as exc:
            work_item.assign_agent("agent-1", "Second assignment")
        assert "already assigned" in str(exc.value)

    def test_assign_agent_to_in_progress_item_raises_error(self):
        """Test that assigning agent to in-progress item raises error."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.assign_agent("agent-1", "Assignment")
        work_item.start()

        with pytest.raises(DomainError) as exc:
            work_item.assign_agent("agent-2", "Reassignment")
        assert "in_progress" in str(exc.value)


class TestWorkItemLifecycle:
    """Test work item lifecycle transitions."""

    def test_start_work_item(self):
        """Test starting work on assigned item."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.assign_agent("agent-1", "Assignment")
        work_item.clear_events()

        work_item.start()

        assert work_item.status == WorkItemStatus.IN_PROGRESS
        events = work_item.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkItemStarted)

    def test_start_unassigned_work_item_raises_error(self):
        """Test that starting unassigned item raises error."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")

        with pytest.raises(DomainError) as exc:
            work_item.start()
        assert "unassigned" in str(exc.value)

    def test_start_new_work_item_raises_error(self):
        """Test that starting new item without assignment raises error."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.status = WorkItemStatus.NEW  # Force status

        with pytest.raises(DomainError):
            work_item.start()

    def test_mark_under_review(self):
        """Test marking in-progress item as under review."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.assign_agent("agent-1", "Assignment")
        work_item.start()
        work_item.clear_events()

        work_item.mark_under_review()

        assert work_item.status == WorkItemStatus.UNDER_REVIEW
        events = work_item.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkItemUnderReview)

    def test_mark_under_review_when_not_in_progress_raises_error(self):
        """Test that marking non-in-progress item under review raises error."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")

        with pytest.raises(DomainError):
            work_item.mark_under_review()

    def test_complete_from_in_progress(self):
        """Test completing work item from in-progress status."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.assign_agent("agent-1", "Assignment")
        work_item.start()
        work_item.clear_events()

        work_item.complete()

        assert work_item.status == WorkItemStatus.COMPLETED
        assert work_item.completed_at is not None
        events = work_item.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkItemCompleted)

    def test_complete_from_under_review(self):
        """Test completing work item from under-review status."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.assign_agent("agent-1", "Assignment")
        work_item.start()
        work_item.mark_under_review()
        work_item.clear_events()

        work_item.complete()

        assert work_item.status == WorkItemStatus.COMPLETED

    def test_complete_unstarted_work_item_raises_error(self):
        """Test that completing unstarted item raises error."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")

        with pytest.raises(DomainError):
            work_item.complete()

    def test_fail_work_item(self):
        """Test failing work item."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.assign_agent("agent-1", "Assignment")
        work_item.start()
        work_item.clear_events()

        error_details = {"error_code": "TIMEOUT", "message": "Agent timed out"}
        work_item.fail("Execution timeout", error_details)

        assert work_item.status == WorkItemStatus.FAILED
        events = work_item.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkItemFailed)
        assert events[0].payload["reason"] == "Execution timeout"
        assert events[0].payload["error_details"] == error_details

    def test_fail_completed_work_item_raises_error(self):
        """Test that failing completed item raises error."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.assign_agent("agent-1", "Assignment")
        work_item.start()
        work_item.complete()

        with pytest.raises(DomainError) as exc:
            work_item.fail("Some reason")
        assert "terminal status" in str(exc.value)


class TestWorkItemBlocking:
    """Test work item blocking/unblocking."""

    def test_block_work_item(self):
        """Test blocking work item."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.assign_agent("agent-1", "Assignment")
        work_item.clear_events()

        work_item.block("Waiting for dependency", "issue-456")

        assert work_item.status == WorkItemStatus.BLOCKED
        events = work_item.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkItemBlocked)
        assert events[0].payload["reason"] == "Waiting for dependency"
        assert events[0].payload["blocking_issue_id"] == "issue-456"

    def test_block_completed_work_item_raises_error(self):
        """Test that blocking completed item raises error."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.assign_agent("agent-1", "Assignment")
        work_item.start()
        work_item.complete()

        with pytest.raises(DomainError):
            work_item.block("Some reason")

    def test_unblock_work_item_with_agent(self):
        """Test unblocking work item that has agent assigned."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.assign_agent("agent-1", "Assignment")
        work_item.block("Blocked")
        work_item.clear_events()

        work_item.unblock()

        assert work_item.status == WorkItemStatus.ASSIGNED
        events = work_item.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkItemUnblocked)
        assert events[0].payload["new_status"] == "assigned"

    def test_unblock_work_item_without_agent(self):
        """Test unblocking work item without agent returns to NEW."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.block("Blocked")
        work_item.clear_events()

        work_item.unblock()

        assert work_item.status == WorkItemStatus.NEW

    def test_unblock_non_blocked_work_item_raises_error(self):
        """Test that unblocking non-blocked item raises error."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")

        with pytest.raises(DomainError) as exc:
            work_item.unblock()
        assert "non-blocked" in str(exc.value)


class TestWorkItemWorkflow:
    """Test workflow-related operations."""

    def test_attach_workflow(self):
        """Test attaching workflow to work item."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.clear_events()

        work_item.attach_workflow("workflow-1")

        assert work_item.current_workflow_id == "workflow-1"
        events = work_item.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkflowAttached)

    def test_attach_workflow_when_already_attached_raises_error(self):
        """Test that attaching workflow to item with workflow raises error."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.attach_workflow("workflow-1")

        with pytest.raises(DomainError) as exc:
            work_item.attach_workflow("workflow-2")
        assert "already has workflow" in str(exc.value)

    def test_update_stage(self):
        """Test updating workflow stage."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.attach_workflow("workflow-1")
        work_item.clear_events()

        work_item.update_stage("coding")

        assert work_item.current_stage == "coding"
        events = work_item.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkItemStageUpdated)
        assert events[0].payload["new_stage"] == "coding"
        assert events[0].payload["old_stage"] is None

    def test_update_stage_without_workflow_raises_error(self):
        """Test that updating stage without workflow raises error."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")

        with pytest.raises(DomainError) as exc:
            work_item.update_stage("coding")
        assert "without workflow" in str(exc.value)


class TestWorkItemMetadata:
    """Test metadata updates."""

    def test_update_labels(self):
        """Test updating work item labels."""
        work_item = WorkItem.create("Test", "Desc", "proj-1", labels=["bug"])
        work_item.clear_events()

        work_item.update_labels(["bug", "critical", "security"])

        assert work_item.labels == ["bug", "critical", "security"]
        events = work_item.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkItemLabelsUpdated)
        assert events[0].payload["old_labels"] == ["bug"]
        assert events[0].payload["new_labels"] == ["bug", "critical", "security"]

    def test_update_priority(self):
        """Test updating work item priority."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.clear_events()

        work_item.update_priority(WorkItemPriority.CRITICAL)

        assert work_item.priority == WorkItemPriority.CRITICAL
        events = work_item.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkItemPriorityUpdated)
        assert events[0].payload["old_priority"] == WorkItemPriority.MEDIUM.value
        assert events[0].payload["new_priority"] == WorkItemPriority.CRITICAL.value


class TestWorkItemQueryMethods:
    """Test query methods."""

    def test_can_start_when_assigned(self):
        """Test can_start returns True when assigned."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.assign_agent("agent-1", "Assignment")

        assert work_item.can_start() is True

    def test_can_start_when_not_assigned(self):
        """Test can_start returns False when not assigned."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")

        assert work_item.can_start() is False

    def test_can_start_when_in_progress(self):
        """Test can_start returns False when in progress."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.assign_agent("agent-1", "Assignment")
        work_item.start()

        assert work_item.can_start() is False

    def test_is_terminal_when_completed(self):
        """Test is_terminal returns True when completed."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.assign_agent("agent-1", "Assignment")
        work_item.start()
        work_item.complete()

        assert work_item.is_terminal() is True

    def test_is_terminal_when_failed(self):
        """Test is_terminal returns True when failed."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.assign_agent("agent-1", "Assignment")
        work_item.start()
        work_item.fail("Failure")

        assert work_item.is_terminal() is True

    def test_is_terminal_when_in_progress(self):
        """Test is_terminal returns False when in progress."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.assign_agent("agent-1", "Assignment")
        work_item.start()

        assert work_item.is_terminal() is False

    def test_is_active_when_in_progress(self):
        """Test is_active returns True when in progress."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.assign_agent("agent-1", "Assignment")
        work_item.start()

        assert work_item.is_active() is True

    def test_is_active_when_under_review(self):
        """Test is_active returns True when under review."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.assign_agent("agent-1", "Assignment")
        work_item.start()
        work_item.mark_under_review()

        assert work_item.is_active() is True

    def test_is_active_when_new(self):
        """Test is_active returns False when new."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")

        assert work_item.is_active() is False


class TestWorkItemEventManagement:
    """Test event management."""

    def test_get_pending_events(self):
        """Test getting pending events."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.assign_agent("agent-1", "Assignment")

        events = work_item.get_pending_events()

        assert len(events) == 2
        assert isinstance(events[0], WorkItemCreated)
        assert isinstance(events[1], AgentAssigned)

    def test_clear_events(self):
        """Test clearing pending events."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        assert len(work_item.get_pending_events()) == 1

        work_item.clear_events()

        assert len(work_item.get_pending_events()) == 0

    def test_get_pending_events_returns_copy(self):
        """Test that get_pending_events returns a copy."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        events = work_item.get_pending_events()
        events.clear()

        # Original events should still be there
        assert len(work_item.get_pending_events()) == 1


class TestWorkItemEventSourcing:
    """Test event sourcing reconstruction."""

    def test_from_events_simple(self):
        """Test reconstructing work item from simple event stream."""
        original = WorkItem.create("Test", "Desc", "proj-1")
        events = original.get_pending_events()

        reconstructed = WorkItem.from_events(events)

        assert reconstructed.id == original.id
        assert reconstructed.title == original.title
        assert reconstructed.description == original.description
        assert reconstructed.status == WorkItemStatus.NEW

    def test_from_events_complex(self):
        """Test reconstructing work item from complex event stream."""
        original = WorkItem.create(
            "Test", "Desc", "proj-1", labels=["bug"], priority=WorkItemPriority.HIGH
        )
        original.assign_agent("agent-1", "Assignment")
        original.start()
        original.mark_under_review()
        original.complete()

        events = original.get_pending_events()
        reconstructed = WorkItem.from_events(events)

        assert reconstructed.id == original.id
        assert reconstructed.status == WorkItemStatus.COMPLETED
        assert reconstructed.assigned_agent_id == "agent-1"
        assert reconstructed.priority == WorkItemPriority.HIGH
        assert reconstructed.labels == ["bug"]
        assert reconstructed.completed_at is not None

    def test_from_events_empty_raises_error(self):
        """Test that reconstructing from empty events raises error."""
        with pytest.raises(DomainError) as exc:
            WorkItem.from_events([])
        assert "empty event stream" in str(exc.value)

    def test_from_events_wrong_first_event_raises_error(self):
        """Test that wrong first event raises error."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        work_item.assign_agent("agent-1", "Assignment")
        events = work_item.get_pending_events()

        # Start from second event (not WorkItemCreated)
        with pytest.raises(DomainError) as exc:
            WorkItem.from_events(events[1:])
        assert "First event must be WorkItemCreated" in str(exc.value)

    def test_from_events_with_workflow(self):
        """Test reconstructing work item with workflow events."""
        original = WorkItem.create("Test", "Desc", "proj-1")
        original.attach_workflow("workflow-1")
        original.update_stage("coding")

        events = original.get_pending_events()
        reconstructed = WorkItem.from_events(events)

        assert reconstructed.current_workflow_id == "workflow-1"
        assert reconstructed.current_stage == "coding"

    def test_from_events_with_blocking(self):
        """Test reconstructing work item with blocking events."""
        original = WorkItem.create("Test", "Desc", "proj-1")
        original.assign_agent("agent-1", "Assignment")
        original.block("Blocked", "issue-123")
        original.unblock()

        events = original.get_pending_events()
        reconstructed = WorkItem.from_events(events)

        assert reconstructed.status == WorkItemStatus.ASSIGNED

    def test_version_tracking(self):
        """Test that version is tracked correctly."""
        work_item = WorkItem.create("Test", "Desc", "proj-1")
        assert work_item._version == 0

        work_item.assign_agent("agent-1", "Assignment")
        assert work_item._version == 1

        work_item.start()
        assert work_item._version == 2

        work_item.complete()
        assert work_item._version == 3
