"""Unit tests for PRReviewCycleDispatchHandler."""

from unittest.mock import AsyncMock, Mock

import pytest

from codetoreum.application.event_handlers.pr_review_cycle_dispatch_handler import (
    PRReviewCycleDispatchHandler,
)
from codetoreum.domain.board_workflow_template import BoardWorkflowTemplate, ColumnTemplate
from codetoreum.domain.events.board_events import WorkItemColumnChangedEvent
from codetoreum.domain.pr_review_cycle_types import (
    PRReviewCycleResult,
    PRReviewCycleState,
    PRReviewOutcome,
)
from codetoreum.domain.work_item import WorkItem
from codetoreum.ports.exceptions import ExternalServiceError, ResourceNotFoundError
from codetoreum.ports.output.active_workflow_run_registry import (
    ActiveRunInfo,
    IActiveWorkflowRunRegistry,
)
from codetoreum.ports.output.pr_review_cycle_service import (
    IPRReviewCycle,
    PRReviewCycleRequest,
)
from codetoreum.ports.output.work_item_service import IWorkItemService
from codetoreum.ports.output.workflow_config_service import (
    IWorkflowConfigService,
)


def create_pr_review_config():
    """Create a real PR review cycle config with minimal fields."""
    from dataclasses import replace

    from codetoreum.domain.pr_review_cycle_types import PRReviewCycleConfig

    # Create a config with default values
    return PRReviewCycleConfig(
        max_outer_cycles=3,
        verifier_context_sources=("parent_issue",),
        code_review_timeout_seconds=600,
        verification_timeout_seconds=300,
        ci_check_enabled=True,
        ci_check_timeout_seconds=300,
        consolidation_timeout_seconds=600,
        on_issues_found_column="In Development",
        on_approved_column="Done",
    )


def create_mock_config(has_pr_review_cycle: bool = True):
    """Create a mock column config with pr_review_cycle_config."""
    column_config = Mock(spec=ColumnTemplate)
    column_config.name = "PR Review"
    if has_pr_review_cycle:
        column_config.pr_review_cycle_config = create_pr_review_config()
    else:
        column_config.pr_review_cycle_config = None
    return column_config


def create_mock_template(has_pr_review_cycle: bool = True):
    """Create a mock workflow template."""
    template = Mock(spec=BoardWorkflowTemplate)
    template.get_column_config = Mock(return_value=create_mock_config(has_pr_review_cycle))
    return template


def create_mock_work_item(pr_id: str = "PR-123"):
    """Create a mock work item."""
    work_item = Mock(spec=WorkItem)
    work_item.pr_id = pr_id
    work_item.external_url = f"https://github.com/org/repo/pull/{pr_id}"
    work_item.discussion_id = "disc-1"
    return work_item


class TestPRReviewCycleDispatchHandlerInitialization:
    """Test PRReviewCycleDispatchHandler initialization."""

    def test_handler_initialization(self):
        """Test handler initializes with all dependencies."""
        mock_cycle = AsyncMock(spec=IPRReviewCycle)
        mock_config = AsyncMock(spec=IWorkflowConfigService)
        mock_work_item = AsyncMock(spec=IWorkItemService)
        mock_registry = AsyncMock(spec=IActiveWorkflowRunRegistry)

        handler = PRReviewCycleDispatchHandler(
            pr_review_cycle=mock_cycle,
            workflow_config=mock_config,
            work_item_service=mock_work_item,
            active_workflow_run_registry=mock_registry,
        )

        assert handler.pr_review_cycle is mock_cycle
        assert handler.workflow_config is mock_config
        assert handler.work_item_service is mock_work_item
        assert handler.active_workflow_run_registry is mock_registry

    def test_handler_has_event_types(self):
        """Test handler reports correct event types."""
        mock_cycle = AsyncMock(spec=IPRReviewCycle)
        mock_config = AsyncMock(spec=IWorkflowConfigService)
        mock_work_item = AsyncMock(spec=IWorkItemService)
        mock_registry = AsyncMock(spec=IActiveWorkflowRunRegistry)

        handler = PRReviewCycleDispatchHandler(
            pr_review_cycle=mock_cycle,
            workflow_config=mock_config,
            work_item_service=mock_work_item,
            active_workflow_run_registry=mock_registry,
        )

        event_types = handler.get_event_types()
        assert event_types == ["WorkItemColumnChangedEvent", "WorkItemColumnChanged"]


@pytest.mark.asyncio
class TestPRReviewCycleDispatchHandlerColumnChangeWithConfig:
    """Test PRReviewCycleDispatchHandler when column has pr_review_cycle_config."""

    async def test_column_change_with_config_triggers_dispatch(self):
        """Test column change with pr_review_cycle_config triggers dispatch."""
        mock_cycle = AsyncMock(spec=IPRReviewCycle)
        mock_config = AsyncMock(spec=IWorkflowConfigService)
        mock_work_item = AsyncMock(spec=IWorkItemService)
        mock_registry = AsyncMock(spec=IActiveWorkflowRunRegistry)

        # Setup mocks
        template = create_mock_template(has_pr_review_cycle=True)
        mock_config.get_board_workflow_template = AsyncMock(return_value=template)

        mock_cycle.get_cycle_state = AsyncMock(return_value=None)

        work_item = create_mock_work_item()
        mock_work_item.get_work_item = AsyncMock(return_value=work_item)

        active_run = ActiveRunInfo(
            work_item_id="item-1",
            run_id="run-1",
            stage_name="review",
            project_id="proj-1",
        )
        mock_registry.get_active_run = AsyncMock(return_value=active_run)

        cycle_result = Mock(spec=PRReviewCycleResult)
        cycle_result.outcome = PRReviewOutcome.APPROVED
        cycle_result.next_column = "Done"
        mock_cycle.start_pr_review_cycle = AsyncMock(return_value=cycle_result)

        handler = PRReviewCycleDispatchHandler(
            pr_review_cycle=mock_cycle,
            workflow_config=mock_config,
            work_item_service=mock_work_item,
            active_workflow_run_registry=mock_registry,
        )

        event = WorkItemColumnChangedEvent(
            type="board.workitem_column_changed",
            timestamp="2026-04-21T12:00:00+00:00",
            source="test",
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="In Development",
            to_column="PR Review",
            moved_by="human",
        )

        await handler.handle(event)

        # Verify start_pr_review_cycle was called with correct arguments
        mock_cycle.start_pr_review_cycle.assert_called_once()
        call_args = mock_cycle.start_pr_review_cycle.call_args[0][0]
        assert call_args.work_item_id == "item-1"
        assert call_args.project_id == "proj-1"
        assert call_args.board_id == "board-1"
        assert call_args.pr_id == "PR-123"
        assert call_args.cycle_number == 1
        assert call_args.workflow_run_id == "run-1"

    async def test_cycle_number_first_cycle_is_one(self):
        """Test cycle number derivation: first cycle = 1."""
        mock_cycle = AsyncMock(spec=IPRReviewCycle)
        mock_config = AsyncMock(spec=IWorkflowConfigService)
        mock_work_item = AsyncMock(spec=IWorkItemService)
        mock_registry = AsyncMock(spec=IActiveWorkflowRunRegistry)

        template = create_mock_template(has_pr_review_cycle=True)
        mock_config.get_board_workflow_template = AsyncMock(return_value=template)

        # No existing cycle
        mock_cycle.get_cycle_state = AsyncMock(return_value=None)

        work_item = create_mock_work_item("PR-1")
        mock_work_item.get_work_item = AsyncMock(return_value=work_item)

        active_run = ActiveRunInfo(
            work_item_id="item-1",
            run_id="run-1",
            stage_name="review",
            project_id="proj-1",
        )
        mock_registry.get_active_run = AsyncMock(return_value=active_run)

        cycle_result = Mock(spec=PRReviewCycleResult)
        cycle_result.outcome = PRReviewOutcome.APPROVED
        cycle_result.next_column = "Done"
        mock_cycle.start_pr_review_cycle = AsyncMock(return_value=cycle_result)

        handler = PRReviewCycleDispatchHandler(
            pr_review_cycle=mock_cycle,
            workflow_config=mock_config,
            work_item_service=mock_work_item,
            active_workflow_run_registry=mock_registry,
        )

        event = WorkItemColumnChangedEvent(
            type="board.workitem_column_changed",
            timestamp="2026-04-21T12:00:00+00:00",
            source="test",
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="In Development",
            to_column="PR Review",
            moved_by="human",
        )

        await handler.handle(event)

        # Verify cycle_number is 1
        call_args = mock_cycle.start_pr_review_cycle.call_args[0][0]
        assert call_args.cycle_number == 1

    async def test_cycle_number_subsequent_increments(self):
        """Test cycle number derivation: subsequent cycles increment."""
        mock_cycle = AsyncMock(spec=IPRReviewCycle)
        mock_config = AsyncMock(spec=IWorkflowConfigService)
        mock_work_item = AsyncMock(spec=IWorkItemService)
        mock_registry = AsyncMock(spec=IActiveWorkflowRunRegistry)

        template = create_mock_template(has_pr_review_cycle=True)
        mock_config.get_board_workflow_template = AsyncMock(return_value=template)

        # Existing cycle state with cycle_number = 2
        existing_state = Mock()
        existing_state.cycle_number = 2
        mock_cycle.get_cycle_state = AsyncMock(return_value=existing_state)

        work_item = create_mock_work_item("PR-2")
        mock_work_item.get_work_item = AsyncMock(return_value=work_item)

        active_run = ActiveRunInfo(
            work_item_id="item-1",
            run_id="run-1",
            stage_name="review",
            project_id="proj-1",
        )
        mock_registry.get_active_run = AsyncMock(return_value=active_run)

        cycle_result = Mock(spec=PRReviewCycleResult)
        cycle_result.outcome = PRReviewOutcome.APPROVED
        cycle_result.next_column = "Done"
        mock_cycle.start_pr_review_cycle = AsyncMock(return_value=cycle_result)

        handler = PRReviewCycleDispatchHandler(
            pr_review_cycle=mock_cycle,
            workflow_config=mock_config,
            work_item_service=mock_work_item,
            active_workflow_run_registry=mock_registry,
        )

        event = WorkItemColumnChangedEvent(
            type="board.workitem_column_changed",
            timestamp="2026-04-21T12:00:00+00:00",
            source="test",
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="In Development",
            to_column="PR Review",
            moved_by="human",
        )

        await handler.handle(event)

        # Verify cycle_number is 3 (previous 2 + 1)
        call_args = mock_cycle.start_pr_review_cycle.call_args[0][0]
        assert call_args.cycle_number == 3


@pytest.mark.asyncio
class TestPRReviewCycleDispatchHandlerColumnChangeWithoutConfig:
    """Test PRReviewCycleDispatchHandler when column has no pr_review_cycle_config."""

    async def test_column_change_without_config_is_skipped(self):
        """Test column change without pr_review_cycle_config is skipped."""
        mock_cycle = AsyncMock(spec=IPRReviewCycle)
        mock_config = AsyncMock(spec=IWorkflowConfigService)
        mock_work_item = AsyncMock(spec=IWorkItemService)
        mock_registry = AsyncMock(spec=IActiveWorkflowRunRegistry)

        # Template without PR review cycle config
        template = create_mock_template(has_pr_review_cycle=False)
        mock_config.get_board_workflow_template = AsyncMock(return_value=template)

        handler = PRReviewCycleDispatchHandler(
            pr_review_cycle=mock_cycle,
            workflow_config=mock_config,
            work_item_service=mock_work_item,
            active_workflow_run_registry=mock_registry,
        )

        event = WorkItemColumnChangedEvent(
            type="board.workitem_column_changed",
            timestamp="2026-04-21T12:00:00+00:00",
            source="test",
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="Backlog",
            to_column="In Development",
            moved_by="human",
        )

        await handler.handle(event)

        # Verify cycle was not initiated
        mock_cycle.start_pr_review_cycle.assert_not_called()

    async def test_no_workflow_config_is_skipped(self):
        """Test column change when no workflow config is skipped."""
        mock_cycle = AsyncMock(spec=IPRReviewCycle)
        mock_config = AsyncMock(spec=IWorkflowConfigService)
        mock_work_item = AsyncMock(spec=IWorkItemService)
        mock_registry = AsyncMock(spec=IActiveWorkflowRunRegistry)

        # No template found
        mock_config.get_board_workflow_template = AsyncMock(return_value=None)

        handler = PRReviewCycleDispatchHandler(
            pr_review_cycle=mock_cycle,
            workflow_config=mock_config,
            work_item_service=mock_work_item,
            active_workflow_run_registry=mock_registry,
        )

        event = WorkItemColumnChangedEvent(
            type="board.workitem_column_changed",
            timestamp="2026-04-21T12:00:00+00:00",
            source="test",
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="Backlog",
            to_column="PR Review",
            moved_by="human",
        )

        await handler.handle(event)

        # Verify cycle was not initiated
        mock_cycle.start_pr_review_cycle.assert_not_called()


@pytest.mark.asyncio
class TestPRReviewCycleDispatchHandlerErrorHandling:
    """Test PRReviewCycleDispatchHandler error handling."""

    async def test_work_item_retrieval_failure_raises(self):
        """Test work item retrieval failure raises exception."""
        mock_cycle = AsyncMock(spec=IPRReviewCycle)
        mock_config = AsyncMock(spec=IWorkflowConfigService)
        mock_work_item = AsyncMock(spec=IWorkItemService)
        mock_registry = AsyncMock(spec=IActiveWorkflowRunRegistry)

        template = create_mock_template(has_pr_review_cycle=True)
        mock_config.get_board_workflow_template = AsyncMock(return_value=template)

        mock_cycle.get_cycle_state = AsyncMock(return_value=None)

        # Work item retrieval fails
        mock_work_item.get_work_item = AsyncMock(side_effect=ResourceNotFoundError("item-1", "Work item not found"))

        active_run = ActiveRunInfo(
            work_item_id="item-1",
            run_id="run-1",
            stage_name="review",
            project_id="proj-1",
        )
        mock_registry.get_active_run = AsyncMock(return_value=active_run)

        handler = PRReviewCycleDispatchHandler(
            pr_review_cycle=mock_cycle,
            workflow_config=mock_config,
            work_item_service=mock_work_item,
            active_workflow_run_registry=mock_registry,
        )

        event = WorkItemColumnChangedEvent(
            type="board.workitem_column_changed",
            timestamp="2026-04-21T12:00:00+00:00",
            source="test",
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="In Development",
            to_column="PR Review",
            moved_by="human",
        )

        with pytest.raises(ResourceNotFoundError):
            await handler.handle(event)

    async def test_active_run_not_found_raises(self):
        """Test missing active workflow run raises exception."""
        mock_cycle = AsyncMock(spec=IPRReviewCycle)
        mock_config = AsyncMock(spec=IWorkflowConfigService)
        mock_work_item = AsyncMock(spec=IWorkItemService)
        mock_registry = AsyncMock(spec=IActiveWorkflowRunRegistry)

        template = create_mock_template(has_pr_review_cycle=True)
        mock_config.get_board_workflow_template = AsyncMock(return_value=template)

        mock_cycle.get_cycle_state = AsyncMock(return_value=None)

        work_item = create_mock_work_item()
        mock_work_item.get_work_item = AsyncMock(return_value=work_item)

        # No active run found
        mock_registry.get_active_run = AsyncMock(return_value=None)

        handler = PRReviewCycleDispatchHandler(
            pr_review_cycle=mock_cycle,
            workflow_config=mock_config,
            work_item_service=mock_work_item,
            active_workflow_run_registry=mock_registry,
        )

        event = WorkItemColumnChangedEvent(
            type="board.workitem_column_changed",
            timestamp="2026-04-21T12:00:00+00:00",
            source="test",
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="In Development",
            to_column="PR Review",
            moved_by="human",
        )

        with pytest.raises(RuntimeError, match="No active workflow run"):
            await handler.handle(event)

    async def test_workflow_run_id_used_not_work_item_id(self):
        """Test that workflow_run_id is from active run, not work_item_id."""
        mock_cycle = AsyncMock(spec=IPRReviewCycle)
        mock_config = AsyncMock(spec=IWorkflowConfigService)
        mock_work_item = AsyncMock(spec=IWorkItemService)
        mock_registry = AsyncMock(spec=IActiveWorkflowRunRegistry)

        template = create_mock_template(has_pr_review_cycle=True)
        mock_config.get_board_workflow_template = AsyncMock(return_value=template)

        mock_cycle.get_cycle_state = AsyncMock(return_value=None)

        work_item = create_mock_work_item()
        mock_work_item.get_work_item = AsyncMock(return_value=work_item)

        # Active run with different run_id from work_item_id
        active_run = ActiveRunInfo(
            work_item_id="item-1",
            run_id="different-run-id-not-item-id",
            stage_name="review",
            project_id="proj-1",
        )
        mock_registry.get_active_run = AsyncMock(return_value=active_run)

        cycle_result = Mock(spec=PRReviewCycleResult)
        cycle_result.outcome = PRReviewOutcome.APPROVED
        cycle_result.next_column = "Done"
        mock_cycle.start_pr_review_cycle = AsyncMock(return_value=cycle_result)

        handler = PRReviewCycleDispatchHandler(
            pr_review_cycle=mock_cycle,
            workflow_config=mock_config,
            work_item_service=mock_work_item,
            active_workflow_run_registry=mock_registry,
        )

        event = WorkItemColumnChangedEvent(
            type="board.workitem_column_changed",
            timestamp="2026-04-21T12:00:00+00:00",
            source="test",
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="In Development",
            to_column="PR Review",
            moved_by="human",
        )

        await handler.handle(event)

        # Verify workflow_run_id is from active run, NOT from work_item_id
        call_args = mock_cycle.start_pr_review_cycle.call_args[0][0]
        assert call_args.workflow_run_id == "different-run-id-not-item-id"
        assert call_args.workflow_run_id != call_args.work_item_id
