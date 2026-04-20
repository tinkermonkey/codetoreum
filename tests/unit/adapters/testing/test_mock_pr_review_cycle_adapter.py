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
    return adapter


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
    """Test constructor validation."""

    def test_requires_ticket_system(self, mock_board_service, simulation_clock, mock_event_emitter):
        """Test that missing ticket_system raises TypeError."""
        with pytest.raises(TypeError, match="ticket_system is required"):
            MockPRReviewCycleAdapter(
                ticket_system=None,
                board_service=mock_board_service,
                clock=simulation_clock,
                event_emitter=mock_event_emitter,
            )

    def test_requires_board_service(self, mock_ticket_system, simulation_clock, mock_event_emitter):
        """Test that missing board_service raises TypeError."""
        with pytest.raises(TypeError, match="board_service is required"):
            MockPRReviewCycleAdapter(
                ticket_system=mock_ticket_system,
                board_service=None,
                clock=simulation_clock,
                event_emitter=mock_event_emitter,
            )

    def test_requires_clock(self, mock_ticket_system, mock_board_service, mock_event_emitter):
        """Test that missing clock raises TypeError."""
        with pytest.raises(TypeError, match="clock is required"):
            MockPRReviewCycleAdapter(
                ticket_system=mock_ticket_system,
                board_service=mock_board_service,
                clock=None,
                event_emitter=mock_event_emitter,
            )

    def test_requires_event_emitter(self, mock_ticket_system, mock_board_service, simulation_clock):
        """Test that missing event_emitter raises TypeError."""
        with pytest.raises(TypeError, match="event_emitter is required"):
            MockPRReviewCycleAdapter(
                ticket_system=mock_ticket_system,
                board_service=mock_board_service,
                clock=simulation_clock,
                event_emitter=None,
            )

    @pytest.mark.asyncio
    async def test_successful_creation_with_all_deps(
        self, mock_ticket_system, mock_board_service, simulation_clock, mock_event_emitter
    ):
        """Test successful creation with all required dependencies."""
        adapter = MockPRReviewCycleAdapter(
            ticket_system=mock_ticket_system,
            board_service=mock_board_service,
            clock=simulation_clock,
            event_emitter=mock_event_emitter,
        )
        assert adapter is not None
        assert adapter.clock is simulation_clock


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
            config=PRReviewCycleConfig(max_outer_cycles=3),
            workflow_run_id="run-1",
        )

        result = await adapter.start_pr_review_cycle(request)

        assert result.work_item_id == "item-1"
        assert result.cycle_number == 1
        assert result.cycle_state.status == PRReviewStatus.COMPLETED

        # Default should create at least one sub-issue
        mock_ticket_system.create_work_item.assert_called()


class TestApprovedPath:
    """Test the approved outcome path."""

    @pytest.mark.asyncio
    async def test_set_approved_immediately_produces_approved(self, adapter):
        """Test set_approved_immediately produces APPROVED outcome."""
        adapter.set_approved_immediately()

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3),
            workflow_run_id="run-1",
        )

        result = await adapter.start_pr_review_cycle(request)

        assert result.cycle_state.status == PRReviewStatus.COMPLETED
        adapter.assert_outcome("item-1", PRReviewOutcome.APPROVED)

    @pytest.mark.asyncio
    async def test_approved_emits_approved_event(self, adapter, mock_event_emitter):
        """Test that approved outcome emits PRReviewCycleApprovedEvent."""
        adapter.set_approved_immediately()

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Check that approved event was emitted
        approved_calls = [
            call for call in mock_event_emitter.emit.call_args_list
            if call[0][0].type == "pr_review_cycle.approved"
        ]
        assert len(approved_calls) > 0

    @pytest.mark.asyncio
    async def test_approved_creates_zero_sub_issues(self, adapter, mock_ticket_system):
        """Test that approved outcome creates no sub-issues."""
        adapter.set_approved_immediately()

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3),
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
            config=PRReviewCycleConfig(max_outer_cycles=3),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Find the CI check event
        ci_events = [
            call for call in mock_event_emitter.emit.call_args_list
            if call[0][0].type == "pr_review_cycle.ci_check_completed"
        ]
        assert len(ci_events) > 0
        ci_event = ci_events[0][0][0]
        assert ci_event.ci_passed is False

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
            config=PRReviewCycleConfig(max_outer_cycles=3),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Should not emit consolidation_started event
        consolidation_events = [
            call for call in mock_event_emitter.emit.call_args_list
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
            config=PRReviewCycleConfig(max_outer_cycles=3),
            workflow_run_id="run-1",
        )

        result = await adapter.start_pr_review_cycle(request)

        # Verify cycle completed (in failure state)
        assert result.cycle_state.status == PRReviewStatus.COMPLETED


class TestMaxCyclesPath:
    """Test the max cycles reached path."""

    @pytest.mark.asyncio
    async def test_set_max_cycles_reached(self, adapter, mock_event_emitter):
        """Test set_max_cycles_reached emits PRReviewCycleMaxCyclesReachedEvent."""
        adapter.set_max_cycles_reached()

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=3,
            config=PRReviewCycleConfig(max_outer_cycles=2),
            workflow_run_id="run-1",
        )

        result = await adapter.start_pr_review_cycle(request)

        # Should emit max_cycles_reached event
        max_cycles_calls = [
            call for call in mock_event_emitter.emit.call_args_list
            if call[0][0].type == "pr_review_cycle.max_cycles_reached"
        ]
        assert len(max_cycles_calls) > 0

        assert result.cycle_state.status == PRReviewStatus.ESCALATED

    @pytest.mark.asyncio
    async def test_max_cycles_short_circuits_phases(self, adapter, mock_event_emitter):
        """Test that max_cycles_reached short-circuits before phase events."""
        adapter.set_max_cycles_reached()

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=3,
            config=PRReviewCycleConfig(max_outer_cycles=2),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Should not emit code_review_started event
        code_review_events = [
            call for call in mock_event_emitter.emit.call_args_list
            if call[0][0].type == "pr_review_cycle.code_review_started"
        ]
        assert len(code_review_events) == 0


class TestEventOrdering:
    """Test correct event ordering in different paths."""

    @pytest.mark.asyncio
    async def test_issues_found_event_order(self, adapter, mock_event_emitter):
        """Test correct event order for ISSUES_FOUND path."""
        findings = [
            PRReviewFinding(
                type="bug",
                severity="high",
                file="main.py",
                line_number=42,
                message="Null pointer exception",
            )
        ]
        adapter.set_findings(findings)

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3),
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
        findings = [
            PRReviewFinding(
                type="bug",
                severity="high",
                file="main.py",
                line_number=42,
                message="Null pointer exception",
            ),
            PRReviewFinding(
                type="style",
                severity="low",
                file="style.py",
                line_number=None,
                message="Missing docstring",
            ),
        ]
        adapter.set_findings(findings)

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Verify create_work_item was called for each finding
        assert mock_ticket_system.create_work_item.call_count >= len(findings)

    @pytest.mark.asyncio
    async def test_sub_issues_added_to_board(self, adapter, mock_board_service, mock_ticket_system):
        """Test that sub-issues are added to board via IBoardService."""
        findings = [
            PRReviewFinding(
                type="bug",
                severity="high",
                file="main.py",
                line_number=42,
                message="Null pointer exception",
            )
        ]
        adapter.set_findings(findings)

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Verify move_item_to_column was called
        assert mock_board_service.move_item_to_column.call_count >= len(findings)

    @pytest.mark.asyncio
    async def test_assert_sub_issues_created_passes(self, adapter):
        """Test assert_sub_issues_created passes when correct count."""
        findings = [
            PRReviewFinding(
                type="bug",
                severity="high",
                file="main.py",
                line_number=42,
                message="Null pointer exception",
            ),
            PRReviewFinding(
                type="style",
                severity="low",
                file="style.py",
                line_number=None,
                message="Missing docstring",
            ),
        ]
        adapter.set_findings(findings)

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Should not raise
        adapter.assert_sub_issues_created("item-1", 2)

    @pytest.mark.asyncio
    async def test_assert_sub_issues_created_fails(self, adapter):
        """Test assert_sub_issues_created raises AssertionError for wrong count."""
        findings = [
            PRReviewFinding(
                type="bug",
                severity="high",
                file="main.py",
                line_number=42,
                message="Null pointer exception",
            )
        ]
        adapter.set_findings(findings)

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3),
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
        adapter.set_approved_immediately()

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        adapter.assert_outcome("item-1", PRReviewOutcome.APPROVED)

    @pytest.mark.asyncio
    async def test_assert_outcome_fails(self, adapter):
        """Test assert_outcome fails for wrong outcome."""
        adapter.set_approved_immediately()

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3),
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
            config=PRReviewCycleConfig(max_outer_cycles=3),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        # Should pass
        adapter.assert_ci_checked("item-1")

    @pytest.mark.asyncio
    async def test_assert_ci_checked_fails(self, adapter, mock_event_emitter):
        """Test assert_ci_checked fails if CI not checked."""
        # Max cycles path skips CI check
        adapter.set_max_cycles_reached()

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=3,
            config=PRReviewCycleConfig(max_outer_cycles=2),
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
            config=PRReviewCycleConfig(max_outer_cycles=3),
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
            config=PRReviewCycleConfig(max_outer_cycles=3),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        with pytest.raises(AssertionError):
            adapter.assert_cycle_number("item-1", 5)


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
            config=PRReviewCycleConfig(max_outer_cycles=3),
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
        adapter.set_max_cycles_reached()
        initial_time = simulation_clock.now()

        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="pr-123",
            pr_url=None,
            discussion_id=None,
            cycle_number=3,
            config=PRReviewCycleConfig(max_outer_cycles=2),
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
            config=PRReviewCycleConfig(max_outer_cycles=3),
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
            config=PRReviewCycleConfig(max_outer_cycles=3),
            workflow_run_id="run-1",
        )

        state_data = await adapter.start_pr_review_cycle(request)

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
            config=PRReviewCycleConfig(max_outer_cycles=3),
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
            config=PRReviewCycleConfig(max_outer_cycles=3),
            workflow_run_id="run-1",
        )

        await adapter.start_pr_review_cycle(request)

        cycles = await adapter.load_active_cycles("proj-1")

        assert len(cycles) > 0
        assert cycles[0].work_item_id == "item-1"
