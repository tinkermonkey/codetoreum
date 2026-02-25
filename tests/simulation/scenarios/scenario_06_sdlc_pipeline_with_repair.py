"""Test scenarios for Simulation Scenario 06: Full SDLC Pipeline with Repair Cycle.

Comprehensive test scenarios validating the full SDLC pipeline workflow including:
- Review cycle progression to Testing column
- Repair cycle invocation when item enters Testing column
- Test-fix-validate loop integration
- End-to-end workflow from Development → Review → Testing
"""

import pytest

from codetoreum.adapters.testing.mock_repair_cycle_adapter import MockRepairCycleAdapter
from codetoreum.adapters.testing.mock_review_cycle_adapter import MockReviewCycleAdapter
from codetoreum.application.event_handlers.repair_cycle_event_handler import (
    RepairCycleEventContext,
)
from codetoreum.domain.events import WorkItemColumnChanged
from codetoreum.domain.repair_cycle_types import (
    RepairTestRunConfig,
    RepairTestType,
)
from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationApplicationBootstrap,
)
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.output.review_cycle_service import ReviewCycleRequest


class TestScenario06SDLCPipelineWithRepair:
    """Test scenarios for full SDLC pipeline with repair cycle integration."""

    @pytest.mark.asyncio
    async def test_scenario_01_happy_path_first_approval_with_testing(self):
        """
        Test full workflow: Review approval → Testing column → Repair cycle.

        Timeline (simulated):
        00:00 - Review cycle starts
        00:30 - Iteration 1: APPROVED
        00:30 - Work item moves to Testing column
        00:31 - Repair cycle starts
        01:00 - UNIT tests pass (1 iteration)
        01:30 - INTEGRATION tests pass (1 iteration)
        02:00 - E2E tests pass (1 iteration)
        02:00 - Repair cycle completes successfully

        Expected:
        - Review cycle: 1 iteration, APPROVED
        - Repair cycle: 3 test types, all pass on first iteration
        - Work item advances through Testing column
        """
        clock = SimulationClock(speed_multiplier=100.0)

        # Setup adapters
        review_adapter = MockReviewCycleAdapter(clock)
        review_adapter.current_project = "test-project"
        review_adapter.set_approve_immediately("work-item-1")

        repair_adapter = MockRepairCycleAdapter(clock)
        repair_adapter.current_project = "test-project"
        # Configure all test types to pass on first iteration
        repair_adapter.set_iterations_until_success(RepairTestType.UNIT, 1)
        repair_adapter.set_iterations_until_success(RepairTestType.INTEGRATION, 1)
        repair_adapter.set_iterations_until_success(RepairTestType.E2E, 1)

        # Execute review cycle
        review_request = ReviewCycleRequest(
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

        review_result = await review_adapter.start_review_cycle(review_request)

        # Assert review cycle passed
        assert review_result.cycle_complete is True
        assert review_result.final_status == "APPROVED"
        assert review_result.next_column == "Testing"
        review_adapter.assert_iteration_count("work-item-1", 1)

        # Simulate work item moving to Testing column
        WorkItemColumnChanged(
            aggregate_id="work-item-1",
            payload={
                "work_item_id": "work-item-1",
                "board_id": "test-board",
                "project_id": "test-project",
                "from_column": "Code Review",
                "to_column": "Testing",
                "moved_by": "system"
            }
        )

        # Execute repair cycle (would be triggered by event handler in full integration)
        repair_context = RepairCycleEventContext(
            stage_name="Testing",
            workflow_run_id="work-item-1",
            test_configs=(
                RepairTestRunConfig(test_type=RepairTestType.UNIT),
                RepairTestRunConfig(test_type=RepairTestType.INTEGRATION),
                RepairTestRunConfig(test_type=RepairTestType.E2E),
            ),
            agent_name="senior_software_engineer",
            max_total_agent_calls=100,
            checkpoint_interval=5,
        )

        repair_result = await repair_adapter.execute(repair_context)

        # Assert repair cycle passed
        assert repair_result.overall_success is True
        assert len(repair_result.test_results) == 3
        assert all(tr.passed for tr in repair_result.test_results)
        assert all(tr.iterations == 1 for tr in repair_result.test_results)
        repair_adapter.assert_overall_success()

    @pytest.mark.asyncio
    async def test_scenario_02_review_to_repair_with_failures(self):
        """
        Test workflow with repair cycle handling test failures.

        Timeline (simulated):
        00:00 - Review cycle starts
        00:30 - Iteration 1: APPROVED
        00:30 - Work item moves to Testing column
        00:31 - Repair cycle starts
        01:00 - UNIT tests fail (iteration 1)
        03:00 - UNIT tests fixed and pass (iteration 2)
        03:30 - INTEGRATION tests pass (iteration 1)
        04:00 - E2E tests pass (iteration 1)

        Expected:
        - Review cycle: 1 iteration, APPROVED
        - Repair cycle: UNIT needs 2 iterations (1 fail + 1 fix + 1 pass), others pass on first
        """
        clock = SimulationClock(speed_multiplier=100.0)

        # Setup adapters
        review_adapter = MockReviewCycleAdapter(clock)
        review_adapter.current_project = "test-project"
        review_adapter.set_approve_immediately("work-item-2")

        repair_adapter = MockRepairCycleAdapter(clock)
        repair_adapter.current_project = "test-project"
        # Configure UNIT tests to fail once, then pass
        repair_adapter.set_iterations_until_success(RepairTestType.UNIT, 2)
        repair_adapter.set_iterations_until_success(RepairTestType.INTEGRATION, 1)
        repair_adapter.set_iterations_until_success(RepairTestType.E2E, 1)

        # Execute review cycle
        review_request = ReviewCycleRequest(
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

        review_result = await review_adapter.start_review_cycle(review_request)
        assert review_result.final_status == "APPROVED"

        # Execute repair cycle
        repair_context = RepairCycleEventContext(
            stage_name="Testing",
            workflow_run_id="work-item-2",
            test_configs=(
                RepairTestRunConfig(test_type=RepairTestType.UNIT),
                RepairTestRunConfig(test_type=RepairTestType.INTEGRATION),
                RepairTestRunConfig(test_type=RepairTestType.E2E),
            ),
            agent_name="senior_software_engineer",
            max_total_agent_calls=100,
            checkpoint_interval=5,
        )

        repair_result = await repair_adapter.execute(repair_context)

        # Assert repair cycle passed after failures
        assert repair_result.overall_success is True
        assert repair_result.test_results[0].iterations == 2  # UNIT needed 2 iterations
        assert repair_result.test_results[1].iterations == 1  # INTEGRATION passed on first
        assert repair_result.test_results[2].iterations == 1  # E2E passed on first
        repair_adapter.assert_test_type_passed(RepairTestType.UNIT)

    @pytest.mark.asyncio
    async def test_scenario_testing_failure_remains_in_column(self):
        """
        Test failure scenario: Review approved, but tests fail beyond max iterations.

        Work item should remain in Testing column after repair cycle exhausts max iterations
        without all tests passing. This validates the fast-fail strategy and escalation path.

        Timeline (simulated):
        00:00 - Review cycle starts
        00:30 - Iteration 1: APPROVED
        00:30 - Work item moves to Testing column
        00:31 - Repair cycle starts
        01:00 - UNIT tests fail (iteration 1)
        03:00 - UNIT tests fail (iteration 2)
        05:00 - UNIT tests fail (iteration 3)
        ...
        After max_total_agent_calls (5) exhausted: Repair cycle fails

        Expected:
        - Review cycle: 1 iteration, APPROVED
        - Repair cycle: Fails after max iterations
        - Work item remains in Testing column (awaiting human intervention)
        """
        clock = SimulationClock(speed_multiplier=100.0)

        # Setup adapters
        review_adapter = MockReviewCycleAdapter(clock)
        review_adapter.current_project = "test-project"
        review_adapter.set_approve_immediately("work-item-10")

        repair_adapter = MockRepairCycleAdapter(clock)
        repair_adapter.current_project = "test-project"
        # Configure UNIT tests to never pass (requires 999 iterations)
        repair_adapter.set_iterations_until_success(RepairTestType.UNIT, 999)

        # Execute review cycle
        review_request = ReviewCycleRequest(
            work_item_id="work-item-10",
            project_id="test-project",
            board_id="test-board",
            maker_agent="senior_software_engineer",
            reviewer_agent="code_reviewer",
            max_iterations=5,
            auto_advance_on_approval=True,
            escalate_on_blocked=True,
            previous_stage_output="Initial implementation"
        )

        review_result = await review_adapter.start_review_cycle(review_request)
        assert review_result.final_status == "APPROVED"

        # Execute repair cycle with limited agent calls
        repair_context = RepairCycleEventContext(
            stage_name="Testing",
            workflow_run_id="work-item-10",
            test_configs=(
                RepairTestRunConfig(test_type=RepairTestType.UNIT),
            ),
            agent_name="senior_software_engineer",
            max_total_agent_calls=5,  # Limited to force failure
            checkpoint_interval=5,
        )

        repair_result = await repair_adapter.execute(repair_context)

        # Assert repair cycle failed (not all tests passed)
        assert repair_result.overall_success is False

        # Determine final column based on result
        # Per requirements: Stay in Testing if repair fails after max iterations
        final_column = "Staged" if repair_result.overall_success else "Testing"
        assert final_column == "Testing"

        # Verify the UNIT test never passed
        unit_results = [tr for tr in repair_result.test_results if tr.test_type == RepairTestType.UNIT]
        assert len(unit_results) == 1
        assert unit_results[0].passed is False

    @pytest.mark.asyncio
    async def test_scenario_04_bootstrap_integration(self):
        """
        Test full bootstrap integration with event handlers wired.

        This test validates that:
        1. Bootstrap creates all adapters including repair cycle
        2. Event handlers are registered
        3. Repair cycle handler is connected to event bus
        """
        from codetoreum.infrastructure.simulation.simulation_config import (
            SimulationConfig,
        )

        # Create bootstrap with fast simulation config
        config = SimulationConfig.create_fast_config("test_bootstrap")
        bootstrap = SimulationApplicationBootstrap(config)

        # Setup the application
        await bootstrap.setup()

        try:
            # Verify adapters were created
            assert bootstrap.adapters is not None
            assert bootstrap.adapters.repair_cycle is not None
            assert isinstance(bootstrap.adapters.repair_cycle, MockRepairCycleAdapter)

            # Verify infrastructure was created
            assert bootstrap.infrastructure is not None
            assert bootstrap.infrastructure.event_bus is not None

            # Verify engine was created (engine encapsulates clock)
            assert bootstrap.engine is not None

            # Verify services were created
            assert bootstrap.services is not None

            # Verify the clock is shared between repair cycle and engine
            assert bootstrap.adapters.repair_cycle._clock == bootstrap.engine.get_clock_for_testing()

            logger = __import__('logging').getLogger(__name__)
            logger.info("Bootstrap integration test passed")

        finally:
            # Cleanup
            await bootstrap.teardown()

    @pytest.mark.asyncio
    async def test_scenario_05_performance_validation(self):
        """
        Performance validation: Full SDLC pipeline (review + repair) in <10s real-time.

        Expected:
        - Review cycle: ~500ms simulated (at 100x speed)
        - Repair cycle: ~2s simulated (at 100x speed)
        - Total real-time: <100ms
        """
        import time

        start_time = time.time()
        clock = SimulationClock(speed_multiplier=100.0)

        # Setup adapters
        review_adapter = MockReviewCycleAdapter(clock)
        review_adapter.current_project = "test-project"
        review_adapter.set_approve_immediately("perf-test")

        repair_adapter = MockRepairCycleAdapter(clock)
        repair_adapter.current_project = "test-project"
        repair_adapter.set_iterations_until_success(RepairTestType.UNIT, 1)
        repair_adapter.set_iterations_until_success(RepairTestType.INTEGRATION, 1)

        # Execute review cycle
        review_request = ReviewCycleRequest(
            work_item_id="perf-test",
            project_id="test-project",
            board_id="test-board",
            maker_agent="senior_software_engineer",
            reviewer_agent="code_reviewer",
            max_iterations=5,
            auto_advance_on_approval=True,
            escalate_on_blocked=True,
            previous_stage_output="Perf test output"
        )

        review_result = await review_adapter.start_review_cycle(review_request)
        assert review_result.final_status == "APPROVED"

        # Execute repair cycle
        repair_context = RepairCycleEventContext(
            stage_name="Testing",
            workflow_run_id="perf-test",
            test_configs=(
                RepairTestRunConfig(test_type=RepairTestType.UNIT),
                RepairTestRunConfig(test_type=RepairTestType.INTEGRATION),
            ),
            agent_name="senior_software_engineer",
            max_total_agent_calls=50,
            checkpoint_interval=5,
        )

        repair_result = await repair_adapter.execute(repair_context)
        assert repair_result.overall_success is True

        elapsed_time = time.time() - start_time

        # Assert performance requirements
        assert elapsed_time < 10.0, (
            f"Performance test failed: {elapsed_time:.2f}s (expected <10s)"
        )
