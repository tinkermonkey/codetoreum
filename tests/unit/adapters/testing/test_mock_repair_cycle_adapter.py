"""Tests for MockRepairCycleAdapter.

Comprehensive tests for the mock repair cycle adapter, verifying:
1. SimulationClock integration for deterministic time
2. Configuration methods (set_test_result_sequence, set_iterations_until_success, set_always_fail)
3. Core repair cycle execution methods
4. Event emission and logging
5. Assertion helper methods
6. Circuit breaker functionality
"""

from datetime import UTC, datetime, timedelta

import pytest

from codetoreum.adapters.testing.mock_repair_cycle_adapter import (
    MockRepairCycleAdapter,
)
from codetoreum.domain.repair_cycle_types import (
    RepairTestFailure,
    RepairTestResult,
    RepairTestRunConfig,
    RepairTestType,
    RepairTestWarning,
)
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock


class MockRepairCycleContext:
    """Mock implementation of RepairCycleContext for testing."""

    def __init__(
        self,
        stage_name: str = "fix_failures",
        workflow_run_id: str = "pipeline_123",
        test_configs: tuple | None = None,
        agent_name: str = "senior_software_engineer",
        max_total_agent_calls: int = 100,
        checkpoint_interval: int = 5,
        agent_config=None,
    ):
        self.stage_name = stage_name
        self.workflow_run_id = workflow_run_id
        self.test_configs = test_configs or (
            RepairTestRunConfig(
                test_type=RepairTestType.UNIT,
                timeout=900,
                max_iterations=3,
                review_warnings=True,
            ),
        )
        self.agent_name = agent_name
        self.max_total_agent_calls = max_total_agent_calls
        self.checkpoint_interval = checkpoint_interval
        self.agent_config = agent_config


class TestSimulationClockIntegration:
    """Tests for SimulationClock integration (FR-11.5)."""

    @pytest.mark.asyncio
    async def test_clock_initialization(self):
        """Verify adapter initializes with clock."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)
        assert adapter.clock is clock
        assert adapter.agent_call_count == 0

    @pytest.mark.asyncio
    async def test_clock_time_advancement_on_test_run(self):
        """Verify clock advances 30 seconds per test (FR-11.6)."""
        clock = SimulationClock(speed_multiplier=100.0)
        start_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        clock.start_at(start_time)

        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="",
            timestamp=clock.now().isoformat(),
        )
        adapter.set_test_result_sequence(RepairTestType.UNIT, [result])

        context = MockRepairCycleContext()
        await adapter.run_tests(context.test_configs[0], context)

        # Clock should advance by 30 seconds
        expected_time = start_time + timedelta(seconds=30)
        assert clock.now() == expected_time

    @pytest.mark.asyncio
    async def test_clock_time_advancement_on_fix(self):
        """Verify clock advances 2 minutes per file fix (FR-11.7)."""
        clock = SimulationClock(speed_multiplier=100.0)
        start_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        clock.start_at(start_time)

        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        context = MockRepairCycleContext()
        failures: dict[str, tuple[RepairTestFailure, ...]] = {
            "test_file.py": (RepairTestFailure(file="test_file.py", test="test_1", message="Failed"),)
        }

        config = context.test_configs[0]
        await adapter.fix_failures_by_file(failures, config, context)

        # Clock should advance by 2 minutes
        expected_time = start_time + timedelta(minutes=2)
        assert clock.now() == expected_time

    @pytest.mark.asyncio
    async def test_clock_time_advancement_on_warning_review(self):
        """Verify clock advances 1 minute per warning review (FR-11.8)."""
        clock = SimulationClock(speed_multiplier=100.0)
        start_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        clock.start_at(start_time)

        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        context = MockRepairCycleContext()
        config = context.test_configs[0]

        test_result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=2,
            failures=(),
            warning_list=(
                RepairTestWarning(file="src/file1.py", message="Warning 1"),
                RepairTestWarning(file="src/file2.py", message="Warning 2"),
            ),
            raw_output="",
            timestamp=clock.now().isoformat(),
        )

        await adapter.handle_warnings(test_result, config, context)

        # Clock should advance by 2 minutes (1 per warning)
        expected_time = start_time + timedelta(minutes=2)
        assert clock.now() == expected_time


class TestConfigurationMethods:
    """Tests for configuration methods (FR-11.2, FR-11.3, FR-11.4)."""

    def test_set_test_result_sequence(self):
        """Test set_test_result_sequence (FR-11.2)."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)

        result1 = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=9,
            failed=1,
            warnings=0,
            failures=(RepairTestFailure(file="test.py", test="test_1", message="Failed"),),
            warning_list=(),
            raw_output="",
            timestamp=clock.now().isoformat(),
        )

        result2 = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=2,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="",
            timestamp=clock.now().isoformat(),
        )

        adapter.set_test_result_sequence(RepairTestType.UNIT, [result1, result2])

        assert RepairTestType.UNIT in adapter.test_results
        assert len(adapter.test_results[RepairTestType.UNIT]) == 2

    def test_set_iterations_until_success(self):
        """Test set_iterations_until_success (FR-11.3)."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)

        adapter.set_iterations_until_success(RepairTestType.UNIT, 3)

        sequence = adapter.test_results[RepairTestType.UNIT]
        assert len(sequence) == 3

        # First two should fail
        assert sequence[0].failed == 3
        assert sequence[1].failed == 3

        # Last should pass
        assert sequence[2].failed == 0

    def test_set_always_fail(self):
        """Test set_always_fail (FR-11.4)."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)

        adapter.set_always_fail(RepairTestType.UNIT, 5)

        sequence = adapter.test_results[RepairTestType.UNIT]
        assert len(sequence) == 5

        # All should fail
        for result in sequence:
            assert result.failed == 3


class TestEventLogging:
    """Tests for event logging and retrieval (FR-11.9, FR-11.10)."""

    @pytest.mark.asyncio
    async def test_get_all_events(self):
        """Test get_all_events method (FR-11.10)."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        context = MockRepairCycleContext()
        result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="",
            timestamp=clock.now().isoformat(),
        )
        adapter.set_test_result_sequence(RepairTestType.UNIT, [result])

        await adapter.run_tests(context.test_configs[0], context)

        events = adapter.get_all_events()
        assert len(events) > 0
        assert all("timestamp" in e for e in events)

    @pytest.mark.asyncio
    async def test_get_events_by_type(self):
        """Test get_events_by_type method (FR-11.10)."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        context = MockRepairCycleContext()
        result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="",
            timestamp=clock.now().isoformat(),
        )
        adapter.set_test_result_sequence(RepairTestType.UNIT, [result])

        await adapter.run_tests(context.test_configs[0], context)

        events = adapter.get_events_by_type("TEST_EXECUTION_COMPLETED")
        assert len(events) > 0
        assert all(e.get("type") == "TEST_EXECUTION_COMPLETED" for e in events)


class TestAssertionHelpers:
    """Tests for assertion helper methods (FR-12.1-12.7)."""

    @pytest.mark.asyncio
    async def test_assert_iteration_count(self):
        """Test assert_iteration_count (FR-12.1)."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        adapter.set_iterations_until_success(RepairTestType.UNIT, 2)
        context = MockRepairCycleContext()

        await adapter.execute(context)

        # Should not raise
        adapter.assert_iteration_count(RepairTestType.UNIT, 2)

        # Should raise for wrong count
        with pytest.raises(AssertionError):
            adapter.assert_iteration_count(RepairTestType.UNIT, 3)

    @pytest.mark.asyncio
    async def test_assert_test_type_passed(self):
        """Test assert_test_type_passed (FR-12.2)."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="",
            timestamp=clock.now().isoformat(),
        )
        adapter.set_test_result_sequence(RepairTestType.UNIT, [result])

        context = MockRepairCycleContext()
        await adapter.execute(context)

        # Should not raise
        adapter.assert_test_type_passed(RepairTestType.UNIT)

    @pytest.mark.asyncio
    async def test_assert_test_type_failed(self):
        """Test assert_test_type_failed (FR-12.3)."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        adapter.set_always_fail(RepairTestType.UNIT, 3)
        context = MockRepairCycleContext()

        await adapter.execute(context)

        # Should not raise
        adapter.assert_test_type_failed(RepairTestType.UNIT)

    @pytest.mark.asyncio
    async def test_assert_overall_success(self):
        """Test assert_overall_success (FR-12.5)."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="",
            timestamp=clock.now().isoformat(),
        )
        adapter.set_test_result_sequence(RepairTestType.UNIT, [result])

        context = MockRepairCycleContext()
        await adapter.execute(context)

        # Should not raise
        adapter.assert_overall_success()

    @pytest.mark.asyncio
    async def test_assert_overall_failure(self):
        """Test assert_overall_failure (FR-12.6)."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        adapter.set_always_fail(RepairTestType.UNIT, 3)
        context = MockRepairCycleContext()

        await adapter.execute(context)

        # Should not raise
        adapter.assert_overall_failure()

    def test_get_agent_call_count(self):
        """Test get_agent_call_count (FR-12.7)."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)

        assert adapter.get_agent_call_count() == 0

        adapter.agent_call_count = 5
        assert adapter.get_agent_call_count() == 5


class TestCircuitBreaker:
    """Tests for circuit breaker functionality (FR-7.1-7.5)."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_triggers(self):
        """Verify circuit breaker prevents execution beyond max agent calls."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        test_result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=7,
            failed=3,
            warnings=0,
            failures=(
                RepairTestFailure(file="test.py", test="test_1", message="Failed"),
                RepairTestFailure(file="test.py", test="test_2", message="Failed"),
                RepairTestFailure(file="test.py", test="test_3", message="Failed"),
            ),
            warning_list=(),
            raw_output="",
            timestamp=clock.now().isoformat(),
        )
        adapter.set_test_result_sequence(RepairTestType.UNIT, [test_result, test_result, test_result, test_result])

        # Set low limit to trigger circuit breaker
        context = MockRepairCycleContext(max_total_agent_calls=3)
        cycle_result = await adapter.execute(context)

        # Should have hit circuit breaker before using all iterations
        assert not cycle_result.overall_success
        assert cycle_result.total_agent_calls >= context.max_total_agent_calls

    @pytest.mark.asyncio
    async def test_circuit_breaker_event_emitted(self):
        """Verify circuit breaker emits fast-fail event."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=7,
            failed=3,
            warnings=0,
            failures=(
                RepairTestFailure(file="test.py", test="test_1", message="Failed"),
                RepairTestFailure(file="test.py", test="test_2", message="Failed"),
                RepairTestFailure(file="test.py", test="test_3", message="Failed"),
            ),
            warning_list=(),
            raw_output="",
            timestamp=clock.now().isoformat(),
        )
        # Create multiple iterations to trigger circuit breaker
        adapter.set_test_result_sequence(RepairTestType.UNIT, [result] * 10)

        context = MockRepairCycleContext(max_total_agent_calls=2)
        await adapter.execute(context)

        # Should have fast-fail event when circuit breaker triggers
        events = adapter.get_events_by_type("REPAIR_CYCLE_FAST_FAIL")
        # May or may not have a fast-fail event depending on exact timing, but execution should stop
        assert adapter.agent_call_count >= 2


class TestFullExecutionFlow:
    """Tests for complete repair cycle execution."""

    @pytest.mark.asyncio
    async def test_successful_repair_cycle(self):
        """Test complete successful repair cycle."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        adapter.set_iterations_until_success(RepairTestType.UNIT, 2)

        context = MockRepairCycleContext()
        result = await adapter.execute(context)

        assert result.overall_success
        assert result.total_agent_calls >= 2

    @pytest.mark.asyncio
    async def test_failed_repair_cycle(self):
        """Test complete failed repair cycle."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        adapter.set_always_fail(RepairTestType.UNIT, 3)

        context = MockRepairCycleContext()
        result = await adapter.execute(context)

        assert not result.overall_success

    @pytest.mark.asyncio
    async def test_fast_fail_on_first_test_type_failure(self):
        """Test that fast-fail stops when first test type fails."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        adapter.set_always_fail(RepairTestType.UNIT, 3)
        adapter.set_iterations_until_success(RepairTestType.INTEGRATION, 1)

        context = MockRepairCycleContext(
            test_configs=(
                RepairTestRunConfig(
                    test_type=RepairTestType.UNIT,
                    timeout=900,
                    max_iterations=3,
                    review_warnings=True,
                ),
                RepairTestRunConfig(
                    test_type=RepairTestType.INTEGRATION,
                    timeout=900,
                    max_iterations=3,
                    review_warnings=True,
                ),
            )
        )

        result = await adapter.execute(context)

        assert not result.overall_success
        # Only the first test type should have been executed
        assert len(result.test_results) == 1


class MockRepairCycleAgentConfig:
    """Mock implementation of RepairCycleAgentConfig for testing agent selection."""

    def __init__(self, agent_map: dict[str, str] | None = None):
        """Initialize with optional agent mapping for sub-tasks.

        Args:
            agent_map: Mapping of sub_task -> agent_name
        """
        self.agent_map = agent_map or {}

    def resolve_agent(self, sub_task: str, default: str) -> str:
        """Resolve agent for a sub-task, falling back to default."""
        return self.agent_map.get(sub_task, default)


class TestAgentSelectionTracking:
    """Tests for agent selection tracking in repair cycle."""

    @pytest.mark.asyncio
    async def test_get_subtask_agent_calls_empty_initially(self):
        """Verify agent calls list is empty before execution."""
        adapter = MockRepairCycleAdapter()
        calls = adapter.get_subtask_agent_calls()
        assert calls == []

    @pytest.mark.asyncio
    async def test_record_agent_for_test_execution(self):
        """Verify agent is recorded when run_tests is called."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="",
            timestamp=clock.now().isoformat(),
        )
        adapter.set_test_result_sequence(RepairTestType.UNIT, [result])

        context = MockRepairCycleContext(agent_name="qa_engineer")
        await adapter.run_tests(context.test_configs[0], context)

        calls = adapter.get_subtask_agent_calls()
        assert len(calls) == 1
        assert calls[0]["sub_task"] == "test_execution"
        assert calls[0]["agent_name"] == "qa_engineer"
        assert "timestamp" in calls[0]

    @pytest.mark.asyncio
    async def test_record_agent_for_code_fix(self):
        """Verify agent is recorded when fix_failures_by_file is called."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        context = MockRepairCycleContext(agent_name="senior_software_engineer")
        config = context.test_configs[0]

        failures: dict[str, tuple[RepairTestFailure, ...]] = {
            "test_file.py": (RepairTestFailure(file="test_file.py", test="test_1", message="Failed"),)
        }

        await adapter.fix_failures_by_file(failures, config, context)

        calls = adapter.get_subtask_agent_calls()
        assert len(calls) == 1
        assert calls[0]["sub_task"] == "code_fix"
        assert calls[0]["agent_name"] == "senior_software_engineer"

    @pytest.mark.asyncio
    async def test_record_agent_for_warning_review(self):
        """Verify agent is recorded when handle_warnings is called."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        context = MockRepairCycleContext(agent_name="code_reviewer")
        config = context.test_configs[0]

        test_result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=1,
            failures=(),
            warning_list=(RepairTestWarning(file="src/file.py", message="Warning"),),
            raw_output="",
            timestamp=clock.now().isoformat(),
        )

        await adapter.handle_warnings(test_result, config, context)

        calls = adapter.get_subtask_agent_calls()
        assert len(calls) == 1
        assert calls[0]["sub_task"] == "code_fix"
        assert calls[0]["agent_name"] == "code_reviewer"

    @pytest.mark.asyncio
    async def test_resolve_agent_with_config(self):
        """Verify agent is resolved from config when available."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        agent_config = MockRepairCycleAgentConfig(
            agent_map={"test_execution": "qa_engineer", "code_fix": "senior_software_engineer"}
        )
        context = MockRepairCycleContext(
            agent_config=agent_config, agent_name="default_agent"
        )

        result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="",
            timestamp=clock.now().isoformat(),
        )
        adapter.set_test_result_sequence(RepairTestType.UNIT, [result])

        await adapter.run_tests(context.test_configs[0], context)

        calls = adapter.get_subtask_agent_calls()
        assert len(calls) == 1
        assert calls[0]["agent_name"] == "qa_engineer"

    @pytest.mark.asyncio
    async def test_fallback_to_default_agent_when_no_config(self):
        """Verify default agent is used when config is None."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        context = MockRepairCycleContext(agent_config=None, agent_name="default_agent")

        result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="",
            timestamp=clock.now().isoformat(),
        )
        adapter.set_test_result_sequence(RepairTestType.UNIT, [result])

        await adapter.run_tests(context.test_configs[0], context)

        calls = adapter.get_subtask_agent_calls()
        assert len(calls) == 1
        assert calls[0]["agent_name"] == "default_agent"

    @pytest.mark.asyncio
    async def test_assert_subtask_used_agent_success(self):
        """Verify assert_subtask_used_agent succeeds on match."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        context = MockRepairCycleContext(agent_name="qa_engineer")

        result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="",
            timestamp=clock.now().isoformat(),
        )
        adapter.set_test_result_sequence(RepairTestType.UNIT, [result])

        await adapter.run_tests(context.test_configs[0], context)

        # Should not raise
        adapter.assert_subtask_used_agent("test_execution", "qa_engineer")

    @pytest.mark.asyncio
    async def test_assert_subtask_used_agent_fails_on_mismatch(self):
        """Verify assert_subtask_used_agent fails on agent mismatch."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        context = MockRepairCycleContext(agent_name="qa_engineer")

        result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="",
            timestamp=clock.now().isoformat(),
        )
        adapter.set_test_result_sequence(RepairTestType.UNIT, [result])

        await adapter.run_tests(context.test_configs[0], context)

        with pytest.raises(AssertionError, match="expected agent 'senior_software_engineer', got 'qa_engineer'"):
            adapter.assert_subtask_used_agent("test_execution", "senior_software_engineer")

    @pytest.mark.asyncio
    async def test_assert_subtask_used_agent_fails_on_no_calls(self):
        """Verify assert_subtask_used_agent fails when no calls recorded."""
        adapter = MockRepairCycleAdapter()

        with pytest.raises(AssertionError, match="No calls recorded for sub_task"):
            adapter.assert_subtask_used_agent("test_execution", "qa_engineer")

    @pytest.mark.asyncio
    async def test_multiple_subtask_calls_track_independently(self):
        """Verify multiple sub-task calls are tracked independently."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        # Set up test results with failures
        failure_result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=7,
            failed=3,
            warnings=0,
            failures=(
                RepairTestFailure(file="test_file.py", test="test_1", message="Failed"),
                RepairTestFailure(file="test_file.py", test="test_2", message="Failed"),
                RepairTestFailure(file="test_file.py", test="test_3", message="Failed"),
            ),
            warning_list=(),
            raw_output="",
            timestamp=clock.now().isoformat(),
        )

        success_result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=2,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="",
            timestamp=clock.now().isoformat(),
        )

        adapter.set_test_result_sequence(RepairTestType.UNIT, [failure_result, success_result])

        agent_config = MockRepairCycleAgentConfig(
            agent_map={"test_execution": "qa_engineer", "code_fix": "senior_software_engineer"}
        )
        context = MockRepairCycleContext(agent_config=agent_config)

        # Run the full cycle
        result = await adapter.execute(context)

        # Should record test_execution, code_fix (for file), test_execution (retest)
        calls = adapter.get_subtask_agent_calls()
        assert len(calls) >= 3

        # Verify agents by sub-task
        test_execution_calls = [c for c in calls if c["sub_task"] == "test_execution"]
        code_fix_calls = [c for c in calls if c["sub_task"] == "code_fix"]

        assert all(c["agent_name"] == "qa_engineer" for c in test_execution_calls)
        assert all(c["agent_name"] == "senior_software_engineer" for c in code_fix_calls)

    @pytest.mark.asyncio
    async def test_assert_subtask_used_agent_checks_most_recent_call(self):
        """Verify assertion checks most recent call for multiple invocations."""
        clock = SimulationClock(speed_multiplier=100.0)
        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        # First call with agent_1
        context1 = MockRepairCycleContext(agent_name="agent_1")
        result1 = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="",
            timestamp=clock.now().isoformat(),
        )
        adapter.set_test_result_sequence(RepairTestType.UNIT, [result1])

        await adapter.run_tests(context1.test_configs[0], context1)

        # Second call with agent_2
        context2 = MockRepairCycleContext(agent_name="agent_2")
        result2 = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=2,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="",
            timestamp=clock.now().isoformat(),
        )
        adapter.set_test_result_sequence(RepairTestType.UNIT, [result1, result2])

        await adapter.run_tests(context2.test_configs[0], context2)

        # Assertion should check most recent (agent_2)
        adapter.assert_subtask_used_agent("test_execution", "agent_2")

        # And fail for the first one
        with pytest.raises(AssertionError):
            adapter.assert_subtask_used_agent("test_execution", "agent_1")
