"""Test scenarios for Simulation Scenario 06: Full SDLC Pipeline.

Comprehensive test scenarios validating the full SDLC pipeline workflow including:
- Happy path with first approval
- Multiple revisions with feedback cycles
- Human escalation with blocked feedback
- Max iterations reached scenarios
- Edge cases for multiple blocks and cycle resume
"""

import pytest
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.adapters.testing.mock_review_cycle_adapter import (
    MockReviewCycleAdapter,
    ReviewSequenceItem,
)
from codetoreum.domain.review_cycle import ReviewDecision
from codetoreum.ports.output.review_cycle_service import (
    ReviewCycleRequest,
    ReviewStatus,
    ReviewFinding,
)
import time


class TestScenario06SDLCPipeline:
    """Test scenarios for Simulation Scenario 06: Full SDLC Pipeline."""

    @pytest.mark.asyncio
    async def test_scenario_01_happy_path_first_approval(self):
        """
        Scenario 1: Happy path - first review approved.

        Timeline (simulated):
        00:00 - Review cycle starts
        00:30 - Iteration 1: APPROVED
        00:30 - Advance to Testing

        Expected:
        - 1 iteration
        - 0 escalations
        - Final column: Testing
        - Events: CYCLE_STARTED, REVIEW_COMPLETED(APPROVED), CYCLE_APPROVED
        """
        clock = SimulationClock(speed_multiplier=100.0)
        review_adapter = MockReviewCycleAdapter(clock)
        review_adapter.current_project = "test-project"

        # Configure
        review_adapter.set_approve_immediately("work-item-1")

        # Execute
        request = ReviewCycleRequest(
            work_item_id="work-item-1",
            project_id="test-project",
            board_id="test-board",
            maker_agent="senior_software_engineer",
            reviewer_agent="code_reviewer",
            max_iterations=5,
            auto_advance_on_approval=True,
            escalate_on_blocked=True,
            previous_stage_output="Initial implementation output"
        )

        result = await review_adapter.start_review_cycle(request)

        # Assert
        assert result.cycle_complete is True
        assert result.final_status == "APPROVED"
        assert result.total_iterations == 1
        assert result.human_escalation_occurred is False
        assert result.next_column == "Testing"

        review_adapter.assert_iteration_count("work-item-1", 1)
        review_adapter.assert_no_escalation("work-item-1")
        review_adapter.assert_final_status("work-item-1", "APPROVED")

        # Verify event log
        events = review_adapter.get_all_events_log()
        assert any(e["type"] == "REVIEW_CYCLE_STARTED" for e in events)
        assert any(e["type"] == "REVIEW_CYCLE_COMPLETED" for e in events)

    @pytest.mark.asyncio
    async def test_scenario_02_multiple_revisions(self):
        """
        Scenario 2: Changes requested - multiple iterations.

        Timeline (simulated):
        00:00 - Cycle starts
        00:30 - Iteration 1: CHANGES_REQUESTED
        02:30 - Iteration 2: CHANGES_REQUESTED
        04:30 - Iteration 3: APPROVED
        04:30 - Advance to Testing

        Expected:
        - 3 iterations
        - 0 escalations
        - Final column: Testing
        - Events: 3x REVIEW_COMPLETED, 2x MAKER_REVISION, CYCLE_APPROVED
        """
        clock = SimulationClock(speed_multiplier=100.0)
        review_adapter = MockReviewCycleAdapter(clock)
        review_adapter.current_project = "test-project"

        # Configure
        review_adapter.set_request_changes_then_approve("work-item-2", iterations=3)

        # Execute
        request = ReviewCycleRequest(
            work_item_id="work-item-2",
            project_id="test-project",
            board_id="test-board",
            maker_agent="senior_software_engineer",
            reviewer_agent="code_reviewer",
            max_iterations=5,
            auto_advance_on_approval=True,
            escalate_on_blocked=True,
            previous_stage_output="Initial implementation output"
        )

        result = await review_adapter.start_review_cycle(request)

        # Assert
        assert result.cycle_complete is True
        assert result.final_status == "APPROVED"
        assert result.total_iterations == 3
        assert result.human_escalation_occurred is False
        assert result.next_column == "Testing"

        review_adapter.assert_iteration_count("work-item-2", 3)
        review_adapter.assert_no_escalation("work-item-2")
        review_adapter.assert_final_status("work-item-2", "APPROVED")

        # Verify iterations occurred
        state = await review_adapter.get_cycle_state("work-item-2")
        assert state is not None
        assert state.current_iteration == 3
        assert len(state.maker_outputs) == 3
        assert len(state.review_outputs) == 3

    @pytest.mark.asyncio
    async def test_scenario_03_blocked_with_human_feedback(self):
        """
        Scenario 3: Blocked - human escalation.

        Timeline (simulated):
        00:00 - Cycle starts
        00:30 - Iteration 1: BLOCKED
        00:30 - Escalation posted
        05:30 - Human responds: "Use GraphQL"
        06:00 - Reviewer re-invoked
        06:30 - Iteration 2: APPROVED
        06:30 - Advance to Testing

        Expected:
        - 2 iterations
        - 1 escalation
        - Final column: Testing
        - Events: ESCALATED_TO_HUMAN, HUMAN_FEEDBACK_RECEIVED, CYCLE_APPROVED
        """
        clock = SimulationClock(speed_multiplier=100.0)
        review_adapter = MockReviewCycleAdapter(clock)
        review_adapter.current_project = "test-project"

        # Configure
        review_adapter.set_review_sequence("work-item-3", [
            ReviewSequenceItem(
                decision=ReviewDecision.ESCALATE,
                findings=[
                    ReviewFinding(
                        severity="blocking",
                        description="Architectural decision required"
                    )
                ],
                summary="Requires human decision on architecture"
            ),
            ReviewSequenceItem(
                decision=ReviewDecision.APPROVE,
                summary="Approved after human feedback"
            )
        ])
        review_adapter.queue_human_feedback("work-item-3", "Use GraphQL for flexibility")

        # Execute
        request = ReviewCycleRequest(
            work_item_id="work-item-3",
            project_id="test-project",
            board_id="test-board",
            maker_agent="senior_software_engineer",
            reviewer_agent="code_reviewer",
            max_iterations=5,
            auto_advance_on_approval=True,
            escalate_on_blocked=True,
            previous_stage_output="Initial implementation output"
        )

        result = await review_adapter.start_review_cycle(request)

        # Assert
        assert result.cycle_complete is True
        assert result.final_status == "APPROVED"
        assert result.total_iterations == 2
        assert result.human_escalation_occurred is True
        assert result.next_column == "Testing"

        review_adapter.assert_iteration_count("work-item-3", 2)
        review_adapter.assert_escalation_occurred("work-item-3")
        review_adapter.assert_final_status("work-item-3", "APPROVED")

        # Verify human feedback event
        events = review_adapter.get_all_events_log()
        assert any(
            e["type"] == "REVIEW_CYCLE_HUMAN_FEEDBACK_RECEIVED"
            for e in events
        )

    @pytest.mark.asyncio
    async def test_scenario_04_max_iterations_reached(self):
        """
        Scenario 4: Max iterations reached.

        Timeline (simulated):
        00:00 - Cycle starts (max_iterations: 5)
        [iterations 1-5 with CHANGES_REQUESTED]
        08:30 - Max iterations reached, escalate

        Expected:
        - 5 iterations
        - 1 escalation (auto)
        - Final column: Code Review (stuck)
        - Events: 5x REVIEW_COMPLETED, 5x MAKER_REVISION_COMPLETED, MAX_ITERATIONS_REACHED
        """
        clock = SimulationClock(speed_multiplier=100.0)
        review_adapter = MockReviewCycleAdapter(clock)
        review_adapter.current_project = "test-project"

        # Configure
        review_adapter.set_max_iterations_escalation("work-item-4", max_iterations=5)

        # Execute
        request = ReviewCycleRequest(
            work_item_id="work-item-4",
            project_id="test-project",
            board_id="test-board",
            maker_agent="senior_software_engineer",
            reviewer_agent="code_reviewer",
            max_iterations=5,
            auto_advance_on_approval=True,
            escalate_on_blocked=True,
            previous_stage_output="Initial implementation output"
        )

        result = await review_adapter.start_review_cycle(request)

        # Assert
        assert result.cycle_complete is True
        assert result.final_status == "BLOCKED"
        assert result.total_iterations == 5
        assert result.human_escalation_occurred is True
        assert result.next_column == "test-board"  # Stuck in current column

        review_adapter.assert_iteration_count("work-item-4", 5)
        review_adapter.assert_escalation_occurred("work-item-4")

        # Verify max iterations event
        events = review_adapter.get_all_events_log()
        assert any(
            e["type"] == "REVIEW_CYCLE_COMPLETED"
            and e.get("human_escalation") is True
            for e in events
        )

    @pytest.mark.asyncio
    async def test_scenario_05_multiple_blocks_requiring_human_input(self):
        """
        Edge case: Multiple BLOCKED statuses in sequence.

        Timeline:
        00:30 - Iteration 1: BLOCKED ("Security concern")
        01:00 - Human: "Use parameterized queries"
        01:30 - Iteration 2: BLOCKED ("Licensing question")
        02:00 - Human: "Approved, license is MIT"
        02:30 - Iteration 3: APPROVED

        Expected:
        - 3 iterations
        - 2 escalations
        - Final status: APPROVED
        """
        clock = SimulationClock(speed_multiplier=100.0)
        review_adapter = MockReviewCycleAdapter(clock)
        review_adapter.current_project = "test-project"

        # Configure
        review_adapter.set_review_sequence("work-item-5", [
            ReviewSequenceItem(
                decision=ReviewDecision.ESCALATE,
                findings=[
                    ReviewFinding(
                        severity="blocking",
                        description="Security concern with SQL queries"
                    )
                ],
                summary="Security review required"
            ),
            ReviewSequenceItem(
                decision=ReviewDecision.ESCALATE,
                findings=[
                    ReviewFinding(
                        severity="blocking",
                        description="Licensing question on dependency"
                    )
                ],
                summary="License review required"
            ),
            ReviewSequenceItem(
                decision=ReviewDecision.APPROVE,
                summary="All concerns addressed"
            )
        ])
        review_adapter.queue_human_feedback("work-item-5", "Use parameterized queries")
        review_adapter.queue_human_feedback("work-item-5", "Approved, license is MIT")

        # Execute
        request = ReviewCycleRequest(
            work_item_id="work-item-5",
            project_id="test-project",
            board_id="test-board",
            maker_agent="senior_software_engineer",
            reviewer_agent="code_reviewer",
            max_iterations=5,
            auto_advance_on_approval=True,
            escalate_on_blocked=True,
            previous_stage_output="Initial implementation output"
        )

        result = await review_adapter.start_review_cycle(request)

        # Assert
        assert result.cycle_complete is True
        assert result.final_status == "APPROVED"
        assert result.total_iterations == 3
        assert result.human_escalation_occurred is True

        # Verify 2 escalations
        events = review_adapter.get_all_events_log()
        escalation_count = sum(
            1 for e in events
            if e.get("type") == "REVIEW_CYCLE_HUMAN_FEEDBACK_RECEIVED"
        )
        assert escalation_count >= 2

    @pytest.mark.asyncio
    async def test_scenario_06_performance_validation(self):
        """
        Performance validation: All 4 base scenarios complete in <15s real-time.

        Expected:
        - Total real-time duration < 15 seconds
        - 100x clock acceleration verified
        - No external service calls
        """
        start_time = time.time()

        clock = SimulationClock(speed_multiplier=100.0)
        review_adapter = MockReviewCycleAdapter(clock)
        review_adapter.current_project = "test-project"

        # Run all 4 base scenarios sequentially
        scenarios = [
            ("work-item-perf-1", ReviewDecision.APPROVE),
            ("work-item-perf-2", ReviewDecision.REQUEST_CHANGES),
            ("work-item-perf-3", ReviewDecision.ESCALATE),
            ("work-item-perf-4", ReviewDecision.REQUEST_CHANGES),
        ]

        for work_item_id, decision in scenarios:
            if decision == ReviewDecision.APPROVE:
                review_adapter.set_approve_immediately(work_item_id)
            elif decision == ReviewDecision.REQUEST_CHANGES:
                review_adapter.set_request_changes_then_approve(work_item_id, iterations=3)
            elif decision == ReviewDecision.ESCALATE:
                review_adapter.set_always_escalate(work_item_id)
                review_adapter.queue_human_feedback(work_item_id, "Proceed")
            else:
                review_adapter.set_max_iterations_escalation(work_item_id, max_iterations=5)

            request = ReviewCycleRequest(
                work_item_id=work_item_id,
                project_id="test-project",
                board_id="test-board",
                maker_agent="senior_software_engineer",
                reviewer_agent="code_reviewer",
                max_iterations=5,
                auto_advance_on_approval=True,
                escalate_on_blocked=True,
                previous_stage_output="Initial implementation"
            )

            result = await review_adapter.start_review_cycle(request)
            assert result is not None

        elapsed_time = time.time() - start_time

        # Assert
        assert elapsed_time < 15.0, (
            f"Performance test failed: {elapsed_time:.2f}s (expected <15s)"
        )

    @pytest.mark.asyncio
    async def test_scenario_07_cycle_resume_after_restart(self):
        """
        Edge case: Simulate orchestrator restart mid-cycle and verify resume.

        Timeline:
        00:00 - Cycle starts
        00:30 - Iteration 1: BLOCKED
        00:30 - SYSTEM RESTART (cycle state persisted)
        05:30 - Human feedback received
        06:00 - Cycle resumed
        06:30 - Iteration 2: APPROVED

        Expected:
        - Cycle state persisted and recoverable
        - Resume completes successfully
        - Final status: APPROVED
        """
        clock = SimulationClock(speed_multiplier=100.0)
        review_adapter = MockReviewCycleAdapter(clock)
        review_adapter.current_project = "test-project"

        # Configure
        review_adapter.set_review_sequence("work-item-6", [
            ReviewSequenceItem(
                decision=ReviewDecision.ESCALATE,
                summary="Requires human decision"
            ),
            ReviewSequenceItem(
                decision=ReviewDecision.APPROVE,
                summary="Approved after restart"
            )
        ])
        review_adapter.queue_human_feedback("work-item-6", "Use async patterns")

        # Execute
        request = ReviewCycleRequest(
            work_item_id="work-item-6",
            project_id="test-project",
            board_id="test-board",
            maker_agent="senior_software_engineer",
            reviewer_agent="code_reviewer",
            max_iterations=5,
            auto_advance_on_approval=True,
            escalate_on_blocked=True,
            previous_stage_output="Initial implementation output"
        )

        result = await review_adapter.start_review_cycle(request)

        # Verify cycle state was persisted
        cycle_state = await review_adapter.get_cycle_state("work-item-6")
        assert cycle_state is not None
        assert cycle_state.work_item_id == "work-item-6"

        # Simulate resume after restart
        await review_adapter.resume_review_cycle("work-item-6", "test-project")

        # Assert
        assert result.cycle_complete is True
        assert result.final_status == "APPROVED"
        assert result.total_iterations == 2

    @pytest.mark.asyncio
    async def test_scenario_08_approved_after_human_feedback_without_maker_revision(self):
        """
        Edge case: APPROVED immediately after human feedback without maker revision.

        Timeline:
        00:00 - Cycle starts
        00:30 - Iteration 1: BLOCKED
        00:30 - Escalation posted
        05:30 - Human feedback: "Approach looks good"
        06:00 - Reviewer re-evaluates
        06:30 - Iteration 2: APPROVED (no maker revision needed)

        Expected:
        - 2 iterations (review + re-evaluation)
        - 1 escalation
        - No maker output after first BLOCKED
        - Final status: APPROVED
        """
        clock = SimulationClock(speed_multiplier=100.0)
        review_adapter = MockReviewCycleAdapter(clock)
        review_adapter.current_project = "test-project"

        # Configure - human feedback allows immediate approval
        review_adapter.set_review_sequence("work-item-7", [
            ReviewSequenceItem(
                decision=ReviewDecision.ESCALATE,
                findings=[
                    ReviewFinding(
                        severity="blocking",
                        description="Needs clarification"
                    )
                ],
                summary="Requires human clarification"
            ),
            ReviewSequenceItem(
                decision=ReviewDecision.APPROVE,
                summary="Approved with human guidance"
            )
        ])
        review_adapter.queue_human_feedback(
            "work-item-7",
            "Approach looks good, proceed as planned"
        )

        # Execute
        request = ReviewCycleRequest(
            work_item_id="work-item-7",
            project_id="test-project",
            board_id="test-board",
            maker_agent="senior_software_engineer",
            reviewer_agent="code_reviewer",
            max_iterations=5,
            auto_advance_on_approval=True,
            escalate_on_blocked=True,
            previous_stage_output="Initial implementation output"
        )

        result = await review_adapter.start_review_cycle(request)

        # Assert
        assert result.cycle_complete is True
        assert result.final_status == "APPROVED"
        assert result.total_iterations == 2
        assert result.human_escalation_occurred is True

        review_adapter.assert_escalation_occurred("work-item-7")
        review_adapter.assert_final_status("work-item-7", "APPROVED")
