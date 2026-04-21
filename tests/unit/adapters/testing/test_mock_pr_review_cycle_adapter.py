"""Unit tests for MockPRReviewCycleAdapter."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.adapters.testing.mock_pr_review_cycle_adapter import MockPRReviewCycleAdapter
from codetoreum.domain.pr_review_cycle_types import (
    PRReviewCycleConfig,
    PRReviewFinding,
    PRReviewOutcome,
    PRReviewStatus,
)
from codetoreum.domain.types import WorkItemId
from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.output.board_service import MovedByType
from codetoreum.ports.output.pr_review_cycle_service import PRReviewCycleRequest


@pytest.fixture
def mock_ticket_system():
    """Create a mock ticket system."""
    adapter = AsyncMock()
    now = datetime.now(UTC)
    adapter.create_work_item = AsyncMock(
        return_value=WorkItem(
            id="sub-issue-1",
            title="Test Sub-issue",
            description="Test Description",
            project_id="proj-1",
            status=WorkItemStatus.NEW,
            priority=WorkItemPriority.MEDIUM,
            labels=[],
            external_id=None,
            external_url=None,
            assigned_agent_id=None,
            assigned_at=None,
            current_workflow_id=None,
            current_stage=None,
            current_column=None,
            entered_column_at=None,
            created_at=now,
            updated_at=now,
        )
    )
    return adapter


@pytest.fixture
def mock_board_service():
    """Create a mock board service."""
    adapter = AsyncMock()
    adapter.move_item_to_column = AsyncMock()
    adapter.add_item_to_column = AsyncMock()
    return adapter


@pytest.fixture
def test_config():
    """Create a test PR review cycle config with required fields."""
    return PRReviewCycleConfig(
        max_outer_cycles=3,
        code_review_agent="agent-1",
        verifier_agent="agent-2",
        consolidation_agent="agent-3",
        on_issues_found_column="Review",
        on_approved_column="Done",
    )


@pytest.fixture
def mock_event_emitter():
    """Create a mock event emitter."""
    emitter = MagicMock()
    emitter.emit = MagicMock()
    return emitter


@pytest.fixture
def simulation_clock():
    """Create a simulation clock."""
    return SimulationClock(speed_multiplier=100.0)


@pytest.fixture
def adapter(mock_ticket_system, mock_board_service, simulation_clock, mock_event_emitter):
    """Create a MockPRReviewCycleAdapter instance."""
    return MockPRReviewCycleAdapter(
        ticket_system=mock_ticket_system,
        board_service=mock_board_service,
        clock=simulation_clock,
        event_emitter=mock_event_emitter,
    )


class TestConstructor:
    """Test constructor creation."""

    @pytest.mark.asyncio
    async def test_successful_creation_with_all_deps(
        self, mock_ticket_system, mock_board_service, simulation_clock, mock_event_emitter
    ):
        """Test successful creation with all dependencies."""
        adapter = MockPRReviewCycleAdapter(
            ticket_system=mock_ticket_system,
            board_service=mock_board_service,
            clock=simulation_clock,
            event_emitter=mock_event_emitter,
        )
        assert adapter is not None
        assert adapter.clock is simulation_clock

    @pytest.mark.asyncio
    async def test_creation_with_minimal_deps(self, simulation_clock):
        """Test creation with only required clock dependency."""
        adapter = MockPRReviewCycleAdapter(clock=simulation_clock)
        assert adapter is not None
        assert adapter.clock is simulation_clock
        assert adapter.ticket_system is None
        assert adapter.board_service is None
        assert adapter.event_emitter is None

    @pytest.mark.asyncio
    async def test_creation_with_no_deps(self):
        """Test creation with no dependencies (all None)."""
        adapter = MockPRReviewCycleAdapter()
        assert adapter is not None
        assert adapter.ticket_system is None
        assert adapter.board_service is None
        assert adapter.clock is None
        assert adapter.event_emitter is None

    @pytest.mark.asyncio
    async def test_property_injection_after_construction(
        self, mock_ticket_system, mock_board_service, simulation_clock, mock_event_emitter
    ):
        """Test that dependencies can be injected via properties after construction."""
        adapter = MockPRReviewCycleAdapter()

        # Inject dependencies via properties
        adapter.ticket_system = mock_ticket_system
        adapter.board_service = mock_board_service
        adapter.clock = simulation_clock
        adapter.event_emitter = mock_event_emitter

        # Verify they were set
        assert adapter.ticket_system is mock_ticket_system
        assert adapter.board_service is mock_board_service
        assert adapter.clock is simulation_clock
        assert adapter.event_emitter is mock_event_emitter


class TestDefaultBehavior:
    """Test default behavior without configuration."""

    @pytest.mark.asyncio
    async def test_default_run_produces_issues_found(self, adapter, mock_ticket_system):
        """Test that default configuration produces ISSUES_FOUND with generic findings."""
        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url="https://github.com/owner/repo/pull/123",
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        result = await adapter.start_pr_review_cycle(request)

        assert result.cycle_number == 1
        assert result.outcome == PRReviewOutcome.ISSUES_FOUND
        assert result.total_findings > 0

        # Default should create at least one sub-issue
        mock_ticket_system.create_work_item.assert_called()


class TestApprovedPath:
    """Test the approved outcome path."""

    @pytest.mark.asyncio
    async def test_set_approved_immediately_produces_approved(self, adapter):
        """Test set_approved_immediately produces APPROVED outcome."""
        adapter.set_approved_immediately("item-1")

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        result = await adapter.start_pr_review_cycle(request)

        assert result.outcome == PRReviewOutcome.APPROVED
        adapter.assert_outcome("item-1", PRReviewOutcome.APPROVED)

    @pytest.mark.asyncio
    async def test_approved_emits_approved_event(self, adapter, mock_event_emitter):
        """Test that approved outcome emits PRReviewCycleApprovedEvent."""
        adapter.set_approved_immediately("item-1")

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Check that approved event was emitted
        approved_calls = [
            call for call in mock_event_emitter.emit.call_args_list if call[0][0].type == "pr_review_cycle.approved"
        ]
        assert len(approved_calls) > 0

    @pytest.mark.asyncio
    async def test_approved_creates_zero_sub_issues(self, adapter, mock_ticket_system):
        """Test that approved outcome creates no sub-issues."""
        adapter.set_approved_immediately("item-1")

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Should not create any sub-issues
        mock_ticket_system.create_work_item.assert_not_called()


class TestCIFailingPath:
    """Test the CI failing outcome path."""

    @pytest.mark.asyncio
    async def test_set_ci_failing_emits_ci_check_event(self, adapter, mock_event_emitter):
        """Test that CI failing emits PRReviewCycleCICheckCompletedEvent with passed=False."""
        adapter.set_ci_failing("item-1", failure_count=2)

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Find the CI check event
        ci_events = [
            call
            for call in mock_event_emitter.emit.call_args_list
            if call[0][0].type == "pr_review_cycle.ci_check_completed"
        ]
        assert len(ci_events) > 0
        ci_event = ci_events[0][0][0]
        assert ci_event.passed is False

    @pytest.mark.asyncio
    async def test_ci_failing_blocks_phase_4(self, adapter, mock_event_emitter):
        """Test that CI failure prevents Phase 4 consolidation."""
        adapter.set_ci_failing("item-1", failure_count=2)

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Should not emit consolidation_started event
        consolidation_events = [
            call
            for call in mock_event_emitter.emit.call_args_list
            if call[0][0].type == "pr_review_cycle.consolidation_started"
        ]
        assert len(consolidation_events) == 0

    @pytest.mark.asyncio
    async def test_ci_failing_routes_to_failure_column(self, adapter):
        """Test that CI failure routes to on_failure_column."""
        adapter.set_ci_failing("item-1", failure_count=2)

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        result = await adapter.start_pr_review_cycle(request)

        # Verify CI failed outcome
        assert result.outcome == PRReviewOutcome.ISSUES_FOUND
        assert result.ci_passed is False


class TestMaxCyclesPath:
    """Test the max cycles reached path."""

    @pytest.mark.asyncio
    async def test_set_max_cycles_reached(self, adapter, mock_event_emitter):
        """Test set_max_cycles_reached emits PRReviewCycleMaxCyclesReachedEvent."""
        adapter.set_max_cycles_reached("item-1")

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=3,
            config=PRReviewCycleConfig(max_outer_cycles=2, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        result = await adapter.start_pr_review_cycle(request)

        # Should emit max_cycles_reached event
        max_cycles_calls = [
            call
            for call in mock_event_emitter.emit.call_args_list
            if call[0][0].type == "pr_review_cycle.max_cycles_reached"
        ]
        assert len(max_cycles_calls) > 0

        assert result.outcome == PRReviewOutcome.MAX_CYCLES_REACHED

    @pytest.mark.asyncio
    async def test_max_cycles_short_circuits_phases(self, adapter, mock_event_emitter):
        """Test that max_cycles_reached short-circuits before phase events."""
        adapter.set_max_cycles_reached("item-1")

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=3,
            config=PRReviewCycleConfig(max_outer_cycles=2, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Should not emit code_review_started event
        code_review_events = [
            call
            for call in mock_event_emitter.emit.call_args_list
            if call[0][0].type == "pr_review_cycle.code_review_started"
        ]
        assert len(code_review_events) == 0


class TestEventOrdering:
    """Test correct event ordering in different paths."""

    @pytest.mark.asyncio
    async def test_issues_found_event_order(self, adapter, mock_event_emitter):
        """Test correct event order for ISSUES_FOUND path."""
        adapter.set_findings("item-1", critical=0, high=1, medium=0, low=0)

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Get all events in order
        events = [call[0][0].type for call in mock_event_emitter.emit.call_args_list]

        # Verify order
        started_idx = events.index("pr_review_cycle.started")
        code_review_idx = events.index("pr_review_cycle.code_review_started")
        verification_idx = events.index("pr_review_cycle.verification_started")
        ci_check_idx = events.index("pr_review_cycle.ci_check_completed")
        consolidation_idx = events.index("pr_review_cycle.consolidation_started")
        issues_found_idx = events.index("pr_review_cycle.issues_found")

        assert started_idx < code_review_idx < verification_idx < ci_check_idx < consolidation_idx < issues_found_idx


class TestSubIssueCreation:
    """Test sub-issue creation and delegation."""

    @pytest.mark.asyncio
    async def test_sub_issues_created_calls_ticket_system(self, adapter, mock_ticket_system):
        """Test that sub-issues call ITicketSystem.create_work_item()."""
        adapter.set_findings("item-1", critical=0, high=1, medium=0, low=1)

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Verify create_work_item was called for each finding (2 findings: 1 high + 1 low)
        assert mock_ticket_system.create_work_item.call_count >= 2

    @pytest.mark.asyncio
    async def test_sub_issues_added_to_board(self, adapter, mock_board_service, mock_ticket_system):
        """Test that sub-issues are added to board via IBoardService."""
        adapter.set_findings("item-1", critical=0, high=1, medium=0, low=0)

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Verify add_item_to_column was called for sub-issues (1 finding: 1 high)
        assert mock_board_service.add_item_to_column.call_count >= 1

    @pytest.mark.asyncio
    async def test_assert_sub_issues_created_passes(self, adapter):
        """Test assert_sub_issues_created passes when correct count."""
        adapter.set_findings("item-1", critical=0, high=1, medium=0, low=1)

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Should not raise
        adapter.assert_sub_issues_created("item-1", 2)

    @pytest.mark.asyncio
    async def test_assert_sub_issues_created_fails(self, adapter):
        """Test assert_sub_issues_created raises AssertionError for wrong count."""
        adapter.set_findings("item-1", critical=0, high=1, medium=0, low=0)

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Should raise
        with pytest.raises(AssertionError):
            adapter.assert_sub_issues_created("item-1", 5)


class TestAssertionHelpers:
    """Test assertion helper methods."""

    @pytest.mark.asyncio
    async def test_assert_outcome(self, adapter):
        """Test assert_outcome helper."""
        adapter.set_approved_immediately("item-1")

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        adapter.assert_outcome("item-1", PRReviewOutcome.APPROVED)

    @pytest.mark.asyncio
    async def test_assert_outcome_fails(self, adapter):
        """Test assert_outcome fails for wrong outcome."""
        adapter.set_approved_immediately("item-1")

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        with pytest.raises(AssertionError):
            adapter.assert_outcome("item-1", PRReviewOutcome.ISSUES_FOUND)

    @pytest.mark.asyncio
    async def test_assert_ci_checked(self, adapter):
        """Test assert_ci_checked helper."""
        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Should pass
        adapter.assert_ci_checked("item-1")

    @pytest.mark.asyncio
    async def test_assert_ci_checked_fails(self, adapter, mock_event_emitter):
        """Test assert_ci_checked fails if CI not checked."""
        # Max cycles path skips CI check
        adapter.set_max_cycles_reached("item-1")

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=3,
            config=PRReviewCycleConfig(max_outer_cycles=2, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        with pytest.raises(AssertionError):
            adapter.assert_ci_checked("item-1")

    @pytest.mark.asyncio
    async def test_assert_cycle_number(self, adapter):
        """Test assert_cycle_number helper."""
        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=2,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        adapter.assert_cycle_number("item-1", 2)

    @pytest.mark.asyncio
    async def test_assert_cycle_number_fails(self, adapter):
        """Test assert_cycle_number fails for wrong number."""
        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=2,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        with pytest.raises(AssertionError):
            adapter.assert_cycle_number("item-1", 5)


class TestCICheckDisabledPath:
    """Test behavior when CI check is disabled via ci_check_enabled=False."""

    @pytest.mark.asyncio
    async def test_ci_disabled_skips_ci_check_event(self, adapter, mock_event_emitter):
        """Test that CI check is skipped when ci_check_enabled=False."""
        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, ci_check_enabled=False, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Verify NO CI check event was emitted
        ci_events = [
            call
            for call in mock_event_emitter.emit.call_args_list
            if call[0][0].type == "pr_review_cycle.ci_check_completed"
        ]
        assert len(ci_events) == 0, "Expected no CI check event when ci_check_enabled=False"

    @pytest.mark.asyncio
    async def test_ci_disabled_skips_ci_check_phase_output(self, adapter):
        """Test that CI check phase is not in phase_outputs when disabled."""
        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, ci_check_enabled=False, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        result = await adapter.start_pr_review_cycle(request)

        # Verify no CI check phase in outputs
        ci_phases = [p for p in result.phase_outputs if p.phase_name == "ci_check"]
        assert len(ci_phases) == 0, "Expected no CI check phase output when ci_check_enabled=False"

    @pytest.mark.asyncio
    async def test_ci_disabled_produces_correct_phase_count(self, adapter):
        """Test that phase count is correct when CI is disabled (one fewer phase)."""
        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(
                max_outer_cycles=3,
                ci_check_enabled=False,
                verifier_context_sources=("static_analysis",),
                code_review_agent="agent-1",
                verifier_agent="agent-2",
                consolidation_agent="agent-3",
                on_issues_found_column="Review",
                on_approved_column="Done",
            ),
            workflow_run_id="run-1",
        )

        result = await adapter.start_pr_review_cycle(request)

        # With verifier_context_sources=["static_analysis"] and ci_check_enabled=False:
        # Phase 1: code_review
        # Phase 2: verification_static_analysis
        # Phase 3: consolidation (no CI check phase)
        # Total: 3 phases
        assert len(result.phase_outputs) == 3, f"Expected 3 phases when CI disabled, got {len(result.phase_outputs)}"

    @pytest.mark.asyncio
    async def test_ci_disabled_produces_issues_found(self, adapter):
        """Test that default outcome is still ISSUES_FOUND when CI is disabled."""
        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, ci_check_enabled=False, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        result = await adapter.start_pr_review_cycle(request)

        # Should still produce ISSUES_FOUND with default findings
        assert result.outcome == PRReviewOutcome.ISSUES_FOUND
        assert result.total_findings > 0

    @pytest.mark.asyncio
    async def test_ci_disabled_proceeds_to_consolidation(self, adapter, mock_event_emitter):
        """Test that consolidation phase runs when CI is disabled."""
        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, ci_check_enabled=False, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Verify consolidation started event exists
        consolidation_events = [
            call
            for call in mock_event_emitter.emit.call_args_list
            if call[0][0].type == "pr_review_cycle.consolidation_started"
        ]
        assert len(consolidation_events) > 0, "Expected consolidation phase to run when CI disabled"

    @pytest.mark.asyncio
    async def test_ci_disabled_assert_ci_not_checked(self, adapter):
        """Test assert_ci_not_checked passes when CI is disabled."""
        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, ci_check_enabled=False, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Should not raise
        adapter.assert_ci_not_checked("item-1")

    @pytest.mark.asyncio
    async def test_ci_disabled_assert_ci_checked_fails(self, adapter):
        """Test assert_ci_checked fails when CI is disabled."""
        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, ci_check_enabled=False, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Should raise with helpful error message
        with pytest.raises(AssertionError) as exc_info:
            adapter.assert_ci_checked("item-1")
        assert "ci_check_enabled=False" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_ci_disabled_with_approved_outcome(self, adapter):
        """Test CI disabled path with approved outcome."""
        adapter.set_approved_immediately("item-1")

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, ci_check_enabled=False, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        result = await adapter.start_pr_review_cycle(request)

        assert result.outcome == PRReviewOutcome.APPROVED
        adapter.assert_ci_not_checked("item-1")
        adapter.assert_outcome("item-1", PRReviewOutcome.APPROVED)


class TestClockAdvancement:
    """Test that clock advances by correct durations."""

    @pytest.mark.asyncio
    async def test_phase_1_clock_advancement(self, adapter, simulation_clock):
        """Test Phase 1 advances clock by ~10 minutes."""
        initial_time = simulation_clock.now()

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        final_time = simulation_clock.now()
        elapsed = (final_time - initial_time).total_seconds()

        # Should be at least 10 minutes worth of time advanced (in simulation)
        assert elapsed > 600  # 10 minutes in real seconds (scaled)

    @pytest.mark.asyncio
    async def test_max_cycles_does_not_advance_many_phases(self, adapter, simulation_clock):
        """Test max_cycles path doesn't advance time through all phases."""
        adapter.set_max_cycles_reached("item-1")
        initial_time = simulation_clock.now()

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=3,
            config=PRReviewCycleConfig(max_outer_cycles=2, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        final_time = simulation_clock.now()
        elapsed = (final_time - initial_time).total_seconds()

        # Should have advanced minimal time since it short-circuits
        assert elapsed < 60  # Less than 1 minute


class TestStateManagement:
    """Test state management methods."""

    @pytest.mark.asyncio
    async def test_get_cycle_state(self, adapter):
        """Test get_cycle_state returns cycle."""
        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        state = await adapter.get_cycle_state("item-1", "proj-1")

        assert state is not None
        assert state.work_item_id == "item-1"
        assert state.cycle_number == 1

    @pytest.mark.asyncio
    async def test_get_cycle_state_returns_none_for_missing(self, adapter):
        """Test get_cycle_state returns None for non-existent cycle."""
        state = await adapter.get_cycle_state("missing-item", "proj-1")
        assert state is None

    @pytest.mark.asyncio
    async def test_save_cycle_state(self, adapter):
        """Test save_cycle_state persists state."""
        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Get the state that was created
        state_data = await adapter.get_cycle_state("item-1", "proj-1")
        assert state_data is not None

        # Modify and save
        await adapter.save_cycle_state(state_data)

        # Retrieve
        retrieved = await adapter.get_cycle_state("item-1", "proj-1")
        assert retrieved is not None
        assert retrieved.cycle_number == state_data.cycle_number

    @pytest.mark.asyncio
    async def test_remove_cycle_state(self, adapter):
        """Test remove_cycle_state deletes state."""
        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Remove
        await adapter.remove_cycle_state("item-1", "proj-1")

        # Verify gone
        state = await adapter.get_cycle_state("item-1", "proj-1")
        assert state is None

    @pytest.mark.asyncio
    async def test_load_active_cycles(self, adapter):
        """Test load_active_cycles returns project cycles."""
        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        cycles = await adapter.load_active_cycles("proj-1")

        assert len(cycles) > 0
        assert cycles[0].work_item_id == "item-1"

    @pytest.mark.asyncio
    async def test_remove_cycle_state_and_load_active_cycles_interaction(self, adapter):
        """Test that remove_cycle_state removes cycle from load_active_cycles.

        This test verifies the port contract semantics: a removed cycle should no longer
        appear as active. The bug this tests for was that remove_cycle_state only removed
        from _cycles but not from _project_cycles, causing load_active_cycles to return
        stale data after removal.
        """
        # Start first cycle
        request1 = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )
        await adapter.start_pr_review_cycle(request1)

        # Start a second item's cycle
        request2 = PRReviewCycleRequest(
            work_item_id="item-2",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-456",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-2",
        )
        await adapter.start_pr_review_cycle(request2)

        # Verify both cycles are in load_active_cycles
        cycles = await adapter.load_active_cycles("proj-1")
        assert len(cycles) == 2
        work_item_ids = {c.work_item_id for c in cycles}
        assert "item-1" in work_item_ids
        assert "item-2" in work_item_ids

        # Remove item-1's cycle
        await adapter.remove_cycle_state("item-1", "proj-1")

        # Verify item-1 is no longer in load_active_cycles, but item-2 still is
        cycles_after_removal = await adapter.load_active_cycles("proj-1")
        assert len(cycles_after_removal) == 1
        assert cycles_after_removal[0].work_item_id == "item-2"

        # Verify get_cycle_state also returns None for removed item
        state = await adapter.get_cycle_state("item-1", "proj-1")
        assert state is None

    @pytest.mark.asyncio
    async def test_multiple_cycles_same_work_item_no_duplicates(self, adapter):
        """Test that re-triggering cycles for same work item doesn't create duplicates.

        This test verifies that when the same work item goes through multiple cycles
        (the core re-trigger use case), load_active_cycles doesn't accumulate duplicates
        in the _project_cycles list. Only the latest cycle should be returned for each
        work item.
        """
        # Start first cycle for item-1
        request1 = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-1",
        )
        await adapter.start_pr_review_cycle(request1)

        # Verify one cycle
        cycles = await adapter.load_active_cycles("proj-1")
        assert len(cycles) == 1
        assert cycles[0].work_item_id == "item-1"
        assert cycles[0].cycle_number == 1

        # Start second cycle for same item (re-trigger)
        request2 = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=2,
            config=PRReviewCycleConfig(max_outer_cycles=3, code_review_agent="agent-1", verifier_agent="agent-2", consolidation_agent="agent-3", on_issues_found_column="Review", on_approved_column="Done"),
            workflow_run_id="run-2",
        )
        await adapter.start_pr_review_cycle(request2)

        # Verify still only one entry in load_active_cycles (not duplicated), but with cycle 2
        cycles_after_retrigger = await adapter.load_active_cycles("proj-1")
        assert len(cycles_after_retrigger) == 1, "Should have exactly one cycle, not duplicates"
        assert cycles_after_retrigger[0].work_item_id == "item-1"
        assert cycles_after_retrigger[0].cycle_number == 2, "Should contain the latest cycle (cycle 2)"

        # Verify get_cycle_state returns the latest state
        state = await adapter.get_cycle_state("item-1", "proj-1")
        assert state is not None
        assert state.cycle_number == 2
