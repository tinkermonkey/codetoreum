"""Comprehensive tests for MockReviewCycleAdapter.

Tests cover:
1. Basic configuration and shorthand methods
2. Review cycle execution with different sequences
3. Iteration counting and state tracking
4. Event emission and handling
5. Human escalation scenarios
6. SimulationClock integration
7. Error handling and assertions
"""

import pytest
from datetime import datetime, timezone

from codetoreum.adapters.testing.mock_review_cycle_adapter import (
    MockReviewCycleAdapter,
    ReviewSequenceItem,
)
from codetoreum.domain.review_cycle import ReviewDecision
from codetoreum.ports.output.review_cycle_service import (
    ReviewCycleRequest,
    ReviewFinding,
)
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock


@pytest.fixture
def clock():
    """Create a SimulationClock for testing."""
    return SimulationClock()


@pytest.fixture
def adapter(clock):
    """Create a MockReviewCycleAdapter with test project."""
    adapter = MockReviewCycleAdapter(clock=clock)
    adapter.current_project = "test-project"
    return adapter


@pytest.fixture
def base_request():
    """Create a base review cycle request."""
    return ReviewCycleRequest(
        work_item_id="item-1",
        project_id="proj-1",
        board_id="board-1",
        maker_agent="junior_dev",
        reviewer_agent="senior_dev",
        max_iterations=3,
        auto_advance_on_approval=True,
        escalate_on_blocked=True,
        previous_stage_output="Initial implementation",
    )


class TestBasicConfiguration:
    """Test basic adapter configuration."""

    def test_create_adapter(self, clock):
        """Test creating adapter with clock."""
        adapter = MockReviewCycleAdapter(clock=clock)
        assert adapter.clock is clock
        assert adapter.current_project is None

    def test_set_current_project(self, adapter):
        """Test setting current project."""
        adapter.current_project = "test-proj"
        assert adapter.current_project == "test-proj"

    def test_clear_state(self, adapter, base_request):
        """Test clearing adapter state."""
        adapter.set_approve_immediately("item-1")
        adapter.clear()
        assert len(adapter._review_sequences) == 0
        assert len(adapter._events) == 0


class TestReviewSequenceConfiguration:
    """Test review sequence configuration methods."""

    def test_set_review_sequence(self, adapter):
        """Test setting custom review sequence."""
        sequence = [
            ReviewSequenceItem(
                decision=ReviewDecision.REQUEST_CHANGES,
                summary="First pass"
            ),
            ReviewSequenceItem(
                decision=ReviewDecision.APPROVE,
                summary="Second pass looks good"
            ),
        ]
        adapter.set_review_sequence("item-1", sequence)
        assert adapter._review_sequences["item-1"] == sequence

    def test_set_review_sequence_empty_raises_error(self, adapter):
        """Test that empty sequence raises error."""
        with pytest.raises(ValueError, match="cannot be empty"):
            adapter.set_review_sequence("item-1", [])

    def test_set_approve_immediately(self, adapter):
        """Test shorthand for immediate approval."""
        adapter.set_approve_immediately("item-1")
        sequence = adapter._review_sequences["item-1"]
        assert len(sequence) == 1
        assert sequence[0].decision == ReviewDecision.APPROVE

    def test_set_request_changes_then_approve(self, adapter):
        """Test shorthand for changes then approve."""
        adapter.set_request_changes_then_approve("item-1", iterations=2)
        sequence = adapter._review_sequences["item-1"]
        assert len(sequence) == 2
        assert sequence[0].decision == ReviewDecision.REQUEST_CHANGES
        assert sequence[1].decision == ReviewDecision.APPROVE

    def test_set_always_escalate(self, adapter):
        """Test shorthand for escalation."""
        adapter.set_always_escalate("item-1")
        sequence = adapter._review_sequences["item-1"]
        assert len(sequence) == 1
        assert sequence[0].decision == ReviewDecision.ESCALATE
        assert sequence[0].findings  # Should have blocking finding

    def test_set_max_iterations_escalation(self, adapter):
        """Test shorthand for escalation after max iterations."""
        adapter.set_max_iterations_escalation("item-1", max_iterations=3)
        sequence = adapter._review_sequences["item-1"]
        assert len(sequence) == 3
        for item in sequence:
            assert item.decision == ReviewDecision.REQUEST_CHANGES


class TestReviewCycleExecution:
    """Test review cycle execution."""

    @pytest.mark.asyncio
    async def test_approve_immediately(self, adapter, base_request):
        """Test immediate approval flow."""
        adapter.set_approve_immediately("item-1")

        result = await adapter.start_review_cycle(base_request)

        assert result.cycle_complete
        assert result.final_status == "APPROVED"
        assert result.total_iterations == 1
        assert not result.human_escalation_occurred

    @pytest.mark.asyncio
    async def test_request_changes_then_approve(self, adapter, base_request):
        """Test request changes followed by approval."""
        adapter.set_request_changes_then_approve("item-1", iterations=2)

        result = await adapter.start_review_cycle(base_request)

        assert result.cycle_complete
        assert result.final_status == "APPROVED"
        assert result.total_iterations == 2
        assert not result.human_escalation_occurred

    @pytest.mark.asyncio
    async def test_escalate_to_human(self, adapter, base_request):
        """Test escalation to human."""
        adapter.set_always_escalate("item-1")

        result = await adapter.start_review_cycle(base_request)

        assert result.cycle_complete
        assert result.final_status == "BLOCKED"
        assert result.total_iterations == 1
        assert result.human_escalation_occurred

    @pytest.mark.asyncio
    async def test_max_iterations_escalation(self, adapter, base_request):
        """Test escalation after max iterations."""
        request = ReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            maker_agent="junior_dev",
            reviewer_agent="senior_dev",
            max_iterations=2,
            auto_advance_on_approval=True,
            escalate_on_blocked=True,
            previous_stage_output="Initial implementation",
        )
        adapter.set_max_iterations_escalation("item-1", max_iterations=2)

        result = await adapter.start_review_cycle(request)

        assert result.cycle_complete
        assert result.total_iterations == 2
        # After 2 iterations of changes requested, should escalate
        assert result.final_status in ["BLOCKED", "CHANGES_REQUESTED"]

    @pytest.mark.asyncio
    async def test_default_sequence_approve_if_none_configured(self, adapter, base_request):
        """Test default sequence is approve if none configured."""
        # Don't configure any sequence
        result = await adapter.start_review_cycle(base_request)

        assert result.cycle_complete
        assert result.final_status == "APPROVED"
        assert result.total_iterations == 1


class TestIterationAndStateTracking:
    """Test iteration counting and state tracking."""

    @pytest.mark.asyncio
    async def test_cycle_state_stored(self, adapter, base_request):
        """Test that cycle state is stored."""
        adapter.set_approve_immediately("item-1")

        await adapter.start_review_cycle(base_request)

        state = await adapter.get_cycle_state("item-1")
        assert state is not None
        assert state.work_item_id == "item-1"
        assert state.current_iteration == 1

    @pytest.mark.asyncio
    async def test_iteration_count_matches_sequence(self, adapter, base_request):
        """Test iteration count matches sequence length."""
        adapter.set_request_changes_then_approve("item-1", iterations=3)

        await adapter.start_review_cycle(base_request)

        state = await adapter.get_cycle_state("item-1")
        assert state.current_iteration == 3

    @pytest.mark.asyncio
    async def test_save_and_retrieve_cycle_state(self, adapter, base_request):
        """Test saving and retrieving cycle state."""
        adapter.set_approve_immediately("item-1")

        await adapter.start_review_cycle(base_request)
        state = await adapter.get_cycle_state("item-1")

        # Save state (explicitly)
        await adapter.save_cycle_state(state)

        # Retrieve state
        retrieved_state = await adapter.get_cycle_state("item-1")
        assert retrieved_state.work_item_id == state.work_item_id
        assert retrieved_state.current_iteration == state.current_iteration

    @pytest.mark.asyncio
    async def test_remove_cycle_state(self, adapter, base_request):
        """Test removing cycle state."""
        adapter.set_approve_immediately("item-1")

        await adapter.start_review_cycle(base_request)
        state = await adapter.get_cycle_state("item-1")

        await adapter.remove_cycle_state(state)

        removed_state = await adapter.get_cycle_state("item-1")
        assert removed_state is None


class TestEventEmission:
    """Test event emission and handling."""

    @pytest.mark.asyncio
    async def test_review_cycle_started_event(self, adapter, base_request):
        """Test review cycle started event is emitted."""
        events_received = []

        def handler(event):
            events_received.append(event)

        adapter.on("review_cycle.started", handler)
        adapter.set_approve_immediately("item-1")

        await adapter.start_review_cycle(base_request)

        assert len(events_received) > 0
        assert hasattr(events_received[0], "type")

    @pytest.mark.asyncio
    async def test_review_cycle_approved_event(self, adapter, base_request):
        """Test review cycle approved event is emitted."""
        events_received = []

        def handler(event):
            events_received.append(event)

        adapter.on("review_cycle.approved", handler)
        adapter.set_approve_immediately("item-1")

        await adapter.start_review_cycle(base_request)

        assert any(
            hasattr(e, "type") and e.type == "review_cycle.approved"
            for e in events_received
        )

    @pytest.mark.asyncio
    async def test_review_cycle_escalated_event(self, adapter, base_request):
        """Test review cycle escalated event is emitted."""
        events_received = []

        def handler(event):
            events_received.append(event)

        adapter.on("review_cycle.escalated_to_human", handler)
        adapter.set_always_escalate("item-1")

        await adapter.start_review_cycle(base_request)

        # Should have escalation event
        assert len(events_received) > 0

    @pytest.mark.asyncio
    async def test_get_all_events(self, adapter, base_request):
        """Test retrieving all events."""
        adapter.set_approve_immediately("item-1")

        await adapter.start_review_cycle(base_request)

        events = adapter.get_all_events()
        assert len(events) > 0
        assert all("type" in e for e in events)

    @pytest.mark.asyncio
    async def test_get_events_by_type(self, adapter, base_request):
        """Test filtering events by type."""
        adapter.set_approve_immediately("item-1")

        await adapter.start_review_cycle(base_request)

        started_events = adapter.get_events_by_type("review_cycle.started")
        assert len(started_events) > 0


class TestAssertionHelpers:
    """Test assertion helper methods."""

    @pytest.mark.asyncio
    async def test_assert_iteration_count(self, adapter, base_request):
        """Test iteration count assertion."""
        adapter.set_request_changes_then_approve("item-1", iterations=2)

        await adapter.start_review_cycle(base_request)

        adapter.assert_iteration_count("item-1", 2)

    @pytest.mark.asyncio
    async def test_assert_iteration_count_failure(self, adapter, base_request):
        """Test iteration count assertion fails on mismatch."""
        adapter.set_request_changes_then_approve("item-1", iterations=2)

        await adapter.start_review_cycle(base_request)

        with pytest.raises(AssertionError, match="Expected 3 iterations"):
            adapter.assert_iteration_count("item-1", 3)

    @pytest.mark.asyncio
    async def test_assert_final_status(self, adapter, base_request):
        """Test final status assertion."""
        adapter.set_approve_immediately("item-1")

        await adapter.start_review_cycle(base_request)

        adapter.assert_final_status("item-1", "APPROVED")

    @pytest.mark.asyncio
    async def test_assert_final_status_failure(self, adapter, base_request):
        """Test final status assertion fails on mismatch."""
        adapter.set_approve_immediately("item-1")

        await adapter.start_review_cycle(base_request)

        with pytest.raises(AssertionError, match="Expected status"):
            adapter.assert_final_status("item-1", "BLOCKED")

    @pytest.mark.asyncio
    async def test_assert_human_escalation(self, adapter, base_request):
        """Test human escalation assertion."""
        adapter.set_always_escalate("item-1")

        await adapter.start_review_cycle(base_request)

        adapter.assert_human_escalation("item-1")

    @pytest.mark.asyncio
    async def test_assert_no_human_escalation(self, adapter, base_request):
        """Test no human escalation assertion."""
        adapter.set_approve_immediately("item-1")

        await adapter.start_review_cycle(base_request)

        adapter.assert_no_human_escalation("item-1")

    @pytest.mark.asyncio
    async def test_assert_no_human_escalation_failure(self, adapter, base_request):
        """Test no human escalation assertion fails on escalation."""
        adapter.set_always_escalate("item-1")

        await adapter.start_review_cycle(base_request)

        with pytest.raises(AssertionError, match="Unexpected human escalation"):
            adapter.assert_no_human_escalation("item-1")


class TestSimulationClockIntegration:
    """Test SimulationClock integration."""

    @pytest.mark.asyncio
    async def test_clock_advancement(self, adapter, base_request):
        """Test that clock advances during execution."""
        initial_time = adapter.clock.now()
        adapter.set_approve_immediately("item-1")

        await adapter.start_review_cycle(base_request)

        final_time = adapter.clock.now()
        # Clock should advance by at least 30 seconds
        assert (final_time - initial_time).total_seconds() >= 30

    @pytest.mark.asyncio
    async def test_multiple_cycles_clock_advances(self, adapter):
        """Test that clock advances for multiple cycles."""
        initial_time = adapter.clock.now()

        request1 = ReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            maker_agent="junior_dev",
            reviewer_agent="senior_dev",
            max_iterations=3,
            auto_advance_on_approval=True,
            escalate_on_blocked=True,
            previous_stage_output="Initial implementation",
        )

        adapter.set_approve_immediately("item-1")
        await adapter.start_review_cycle(request1)

        time_after_first = adapter.clock.now()

        request2 = ReviewCycleRequest(
            work_item_id="item-2",
            project_id="proj-1",
            board_id="board-1",
            maker_agent="junior_dev",
            reviewer_agent="senior_dev",
            max_iterations=3,
            auto_advance_on_approval=True,
            escalate_on_blocked=True,
            previous_stage_output="Second implementation",
        )

        adapter.set_approve_immediately("item-2")
        await adapter.start_review_cycle(request2)

        time_after_second = adapter.clock.now()

        # Clock should advance more for second cycle
        assert (time_after_second - time_after_first).total_seconds() >= 30


class TestReviewResultParsing:
    """Test review output parsing."""

    def test_parse_review_approve(self, adapter):
        """Test parsing approve decision."""
        result = adapter.parse_review("This looks good, I approve")
        assert result.status == "APPROVED"

    def test_parse_review_changes_requested(self, adapter):
        """Test parsing changes requested."""
        result = adapter.parse_review("Please fix the issues")
        assert result.status == "CHANGES_REQUESTED"

    def test_parse_review_escalate(self, adapter):
        """Test parsing escalation."""
        result = adapter.parse_review("This has blocking issues")
        assert result.status == "BLOCKED"
        assert len(result.findings) > 0

    def test_parse_review_with_blocking_findings(self, adapter):
        """Test parsing with blocking findings."""
        result = adapter.parse_review("blocking: security issue found")
        assert len(result.findings) > 0
        assert result.blocking_count > 0


class TestErrorHandling:
    """Test error handling and validation."""

    @pytest.mark.asyncio
    async def test_invalid_work_item_id(self, adapter):
        """Test validation of missing work item ID."""
        request = ReviewCycleRequest(
            work_item_id="",
            project_id="proj-1",
            board_id="board-1",
            maker_agent="junior_dev",
            reviewer_agent="senior_dev",
            max_iterations=3,
            auto_advance_on_approval=True,
            escalate_on_blocked=True,
            previous_stage_output="Initial implementation",
        )

        with pytest.raises(ValueError, match="work_item_id is required"):
            await adapter.start_review_cycle(request)

    @pytest.mark.asyncio
    async def test_invalid_max_iterations(self, adapter):
        """Test validation of invalid max iterations."""
        request = ReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            maker_agent="junior_dev",
            reviewer_agent="senior_dev",
            max_iterations=0,
            auto_advance_on_approval=True,
            escalate_on_blocked=True,
            previous_stage_output="Initial implementation",
        )

        with pytest.raises(ValueError, match="max_iterations must be positive"):
            await adapter.start_review_cycle(request)

    def test_assert_no_handler_errors(self, adapter):
        """Test assertion for handler errors."""
        adapter.assert_no_handler_errors()


class TestMultipleCycles:
    """Test handling multiple concurrent cycles."""

    @pytest.mark.asyncio
    async def test_multiple_work_items_independent_sequences(self, adapter):
        """Test that multiple work items can have independent sequences."""
        adapter.set_approve_immediately("item-1")
        adapter.set_request_changes_then_approve("item-2", iterations=2)

        request1 = ReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            maker_agent="junior_dev",
            reviewer_agent="senior_dev",
            max_iterations=3,
            auto_advance_on_approval=True,
            escalate_on_blocked=True,
            previous_stage_output="Initial implementation",
        )

        request2 = ReviewCycleRequest(
            work_item_id="item-2",
            project_id="proj-1",
            board_id="board-1",
            maker_agent="junior_dev",
            reviewer_agent="senior_dev",
            max_iterations=3,
            auto_advance_on_approval=True,
            escalate_on_blocked=True,
            previous_stage_output="Second implementation",
        )

        result1 = await adapter.start_review_cycle(request1)
        result2 = await adapter.start_review_cycle(request2)

        assert result1.total_iterations == 1
        assert result2.total_iterations == 2

    @pytest.mark.asyncio
    async def test_load_active_cycles(self, adapter):
        """Test loading active cycles for a project."""
        adapter.set_approve_immediately("item-1")

        request = ReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            maker_agent="junior_dev",
            reviewer_agent="senior_dev",
            max_iterations=3,
            auto_advance_on_approval=True,
            escalate_on_blocked=True,
            previous_stage_output="Initial implementation",
        )

        await adapter.start_review_cycle(request)

        # Note: In mock, completed cycles have status="completed"
        # This test verifies the interface works
        active = await adapter.load_active_cycles("proj-1")
        # Completed cycles won't show up in active list
        assert isinstance(active, list)
