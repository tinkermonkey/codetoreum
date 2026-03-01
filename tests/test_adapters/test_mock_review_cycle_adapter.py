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

from codetoreum.adapters.testing.mock_llm_adapter import MockLLMAdapter
from codetoreum.adapters.testing.mock_review_cycle_adapter import (
    MockReviewCycleAdapter,
    ReviewSequenceItem,
)
from codetoreum.domain.review_cycle import ReviewDecision
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.output.review_cycle_service import ReviewCycleRequest


@pytest.fixture
def clock():
    """Create a SimulationClock for testing with fast speed."""
    return SimulationClock(speed_multiplier=100.0)


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
            ReviewSequenceItem(decision=ReviewDecision.REQUEST_CHANGES, summary="First pass"),
            ReviewSequenceItem(decision=ReviewDecision.APPROVE, summary="Second pass looks good"),
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

        assert any(hasattr(e, "type") and e.type == "review_cycle.approved" for e in events_received)

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
    async def test_assert_escalation_occurred(self, adapter, base_request):
        """Test escalation occurred assertion."""
        adapter.set_always_escalate("item-1")

        await adapter.start_review_cycle(base_request)

        adapter.assert_escalation_occurred("item-1")

    @pytest.mark.asyncio
    async def test_assert_no_escalation(self, adapter, base_request):
        """Test no escalation assertion."""
        adapter.set_approve_immediately("item-1")

        await adapter.start_review_cycle(base_request)

        adapter.assert_no_escalation("item-1")

    @pytest.mark.asyncio
    async def test_assert_no_escalation_failure(self, adapter, base_request):
        """Test no escalation assertion fails on escalation."""
        adapter.set_always_escalate("item-1")

        await adapter.start_review_cycle(base_request)

        with pytest.raises(AssertionError, match="Unexpected escalation"):
            adapter.assert_no_escalation("item-1")


class TestSimulationClockIntegration:
    """Test SimulationClock integration."""

    @pytest.mark.asyncio
    async def test_clock_advancement(self, adapter, base_request):
        """Test that clock advances during execution."""
        initial_time = adapter.clock.now()
        adapter.set_approve_immediately("item-1")

        await adapter.start_review_cycle(base_request)

        final_time = adapter.clock.now()
        # Clock should advance (even by small amount for fast simulation)
        assert final_time > initial_time

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

        # Clock should advance for each cycle
        assert time_after_second > time_after_first
        assert time_after_first > initial_time


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

    def test_invalid_work_item_id(self, adapter):
        """Test validation of missing work item ID."""
        with pytest.raises(ValueError, match="work_item_id must be a non-empty string"):
            ReviewCycleRequest(
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

    @pytest.mark.asyncio
    async def test_invalid_max_iterations(self, adapter):
        """Test validation of invalid max iterations."""
        with pytest.raises(ValueError, match="max_iterations must be positive"):
            ReviewCycleRequest(
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

    def test_assert_no_handler_errors(self, adapter):
        """Test assertion for handler errors."""
        adapter.assert_no_handler_errors()


class TestHumanFeedbackQueue:
    """Test human feedback queue functionality."""

    def test_queue_human_feedback(self, adapter):
        """Test queueing human feedback."""
        adapter.queue_human_feedback("item-1", "Please fix the security issue")

        queue = adapter._human_feedback_queue.get("item-1", [])
        assert len(queue) == 1
        assert queue[0] == "Please fix the security issue"

    def test_queue_multiple_feedback(self, adapter):
        """Test queueing multiple feedback items."""
        adapter.queue_human_feedback("item-1", "First feedback")
        adapter.queue_human_feedback("item-1", "Second feedback")

        queue = adapter._human_feedback_queue.get("item-1", [])
        assert len(queue) == 2
        assert queue[0] == "First feedback"
        assert queue[1] == "Second feedback"

    def test_queue_human_feedback_empty_raises_error(self, adapter):
        """Test that empty feedback raises error."""
        with pytest.raises(ValueError, match="cannot be empty"):
            adapter.queue_human_feedback("item-1", "")

        with pytest.raises(ValueError, match="cannot be empty"):
            adapter.queue_human_feedback("item-1", "   ")

    def test_queue_human_feedback_separate_work_items(self, adapter):
        """Test queuing feedback for different work items."""
        adapter.queue_human_feedback("item-1", "Feedback for item-1")
        adapter.queue_human_feedback("item-2", "Feedback for item-2")

        queue1 = adapter._human_feedback_queue.get("item-1", [])
        queue2 = adapter._human_feedback_queue.get("item-2", [])

        assert queue1[0] == "Feedback for item-1"
        assert queue2[0] == "Feedback for item-2"


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


class TestCausalLinkingWithLLMOutput:
    """Test causal linking - evaluating actual prior LLM output (FR-2/US-2.2)."""

    @pytest.mark.asyncio
    async def test_evaluates_actual_prior_llm_output(self, clock):
        """Test that review cycle evaluates actual prior LLM output, not generated LLM calls.

        This test verifies US-2.2: "feedback references actual generated code content".
        The review adapter should analyze the prior_stage_output (actual maker output)
        rather than generating a new LLM call.
        """
        # Setup: Create adapter with LLM support
        llm_adapter = MockLLMAdapter()
        adapter = MockReviewCycleAdapter(clock=clock, llm_adapter=llm_adapter)
        adapter.current_project = "test-project"

        # Create request with actual prior LLM output (from maker agent)
        # This simulates code that was actually generated by the maker agent
        prior_output = (
            "def fix_bug():\n"
            "    '''Fixed the critical bug that was causing failures.'''\n"
            "    # Implementation improved\n"
            "    return 'fixed'\n"
            "\n"
            "def test_fix_bug():\n"
            "    '''Test to verify the fix works.'''\n"
            "    assert fix_bug() == 'fixed'\n"
        )

        request = ReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            maker_agent="code_generator",
            reviewer_agent="code_reviewer",
            max_iterations=3,
            auto_advance_on_approval=True,
            escalate_on_blocked=True,
            previous_stage_output=prior_output,  # Actual maker output
        )

        # Execute: Start review cycle without pre-configured sequence
        # This forces it to use causal linking and evaluate actual prior output
        result = await adapter.start_review_cycle(request)

        # Verify: Review should evaluate the prior output and approve (has fixes, tests, explanation)
        assert result.cycle_complete
        # The prior output has quality patterns (fixed) + test patterns + explanation
        # so it should be approved
        assert result.final_status == "APPROVED"
        assert result.total_iterations == 1

    @pytest.mark.asyncio
    async def test_evaluates_output_with_errors(self, clock):
        """Test evaluation of prior output containing errors - should request changes."""
        llm_adapter = MockLLMAdapter()
        adapter = MockReviewCycleAdapter(clock=clock, llm_adapter=llm_adapter)
        adapter.current_project = "test-project"

        # Prior output with errors but no fixes
        prior_output = (
            "def process_data():\n"
            "    failed to parse JSON\n"
            "    # Error: exception thrown in validator\n"
            "    traceback shown in output\n"
        )

        request = ReviewCycleRequest(
            work_item_id="item-2",
            project_id="proj-1",
            board_id="board-1",
            maker_agent="code_generator",
            reviewer_agent="code_reviewer",
            max_iterations=1,  # Set to 1 so first REQUEST_CHANGES escalates
            auto_advance_on_approval=True,
            escalate_on_blocked=True,
            previous_stage_output=prior_output,
        )

        result = await adapter.start_review_cycle(request)

        # Should be BLOCKED (errors without fixes, max iterations reached on iteration 1)
        assert result.cycle_complete
        assert result.final_status == "BLOCKED"
        assert result.total_iterations == 1

    @pytest.mark.asyncio
    async def test_evaluates_incomplete_output(self, clock):
        """Test evaluation of incomplete prior output - should request changes."""
        llm_adapter = MockLLMAdapter()
        adapter = MockReviewCycleAdapter(clock=clock, llm_adapter=llm_adapter)
        adapter.current_project = "test-project"

        # Prior output without tests
        prior_output = (
            "def refactored_function():\n"
            "    '''Refactored for better performance.'''\n"
            "    return optimized_value\n"
        )

        request = ReviewCycleRequest(
            work_item_id="item-3",
            project_id="proj-1",
            board_id="board-1",
            maker_agent="code_generator",
            reviewer_agent="code_reviewer",
            max_iterations=1,  # Set to 1 so REQUEST_CHANGES escalates
            auto_advance_on_approval=True,
            escalate_on_blocked=True,
            previous_stage_output=prior_output,
        )

        result = await adapter.start_review_cycle(request)

        # Should be BLOCKED (improvements but no test coverage, max iterations reached)
        assert result.cycle_complete
        assert result.final_status == "BLOCKED"
        assert result.total_iterations == 1

    @pytest.mark.asyncio
    async def test_prior_output_used_not_new_llm_call(self, clock):
        """Test that prior_stage_output is used, not a newly generated LLM response.

        This directly validates the fix for the issue: MockReviewCycleAdapter should
        evaluate the actual prior_stage_output from the request, not construct a new
        LLM call to generate review content.
        """
        llm_adapter = MockLLMAdapter()
        adapter = MockReviewCycleAdapter(clock=clock, llm_adapter=llm_adapter)
        adapter.current_project = "test-project"

        # Unique prior output with enough characteristics to be approved
        # (quality patterns + test patterns + explanation)
        unique_prior_output = (
            "UNIQUE_MARKER_xyz: improved refactored validated\n"
            "def test_something():\n"
            "    assert True\n"
            "    verify output is correct\n"
        )

        request = ReviewCycleRequest(
            work_item_id="item-4",
            project_id="proj-1",
            board_id="board-1",
            maker_agent="code_generator",
            reviewer_agent="code_reviewer",
            max_iterations=1,
            auto_advance_on_approval=True,
            escalate_on_blocked=True,
            previous_stage_output=unique_prior_output,
        )

        result = await adapter.start_review_cycle(request)

        # Verify the LLM adapter was never called (critical to the fix)
        # The review decision was derived from analyzing prior_stage_output, not from an LLM call
        assert llm_adapter.get_request_count() == 0, (
            "LLM adapter should NOT be invoked during causal linking; "
            "review decisions are derived from prior_stage_output deterministically"
        )

        # Retrieve the cycle state to verify the prior output was evaluated
        cycle_state = await adapter.get_cycle_state("item-4")
        assert cycle_state is not None

        # The fact that result.final_status is APPROVED confirms that the adapter
        # evaluated the prior_output (which contains "improved", "refactored", "test", "assert", "verify")
        # The prior_output has all characteristics needed for approval:
        # - quality patterns (improved, refactored)
        # - test patterns (test, assert, verify)
        # - sufficient length for explanation (>100 chars)
        assert result.final_status == "APPROVED"
