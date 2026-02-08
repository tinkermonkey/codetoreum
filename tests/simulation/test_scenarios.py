"""Simulation scenario tests."""

import pytest
from datetime import timedelta

from codetoreum.infrastructure.simulation import (
    SimulationConfig,
    SimulationRunner,
)

# Import scenario functions
from .scenarios.scenario_01_simple_workflow import (
    create_config as create_simple_config,
    run_scenario as run_simple_scenario,
)
from .scenarios.scenario_02_parallel_executions import (
    create_config as create_parallel_config,
    run_scenario as run_parallel_scenario,
)
from .scenarios.scenario_03_review_cycle import (
    create_config as create_review_config,
    run_scenario as run_review_scenario,
)
from .scenarios.scenario_04_execution_failure import (
    create_config as create_failure_config,
    run_scenario as run_failure_scenario,
)
from .scenarios.scenario_05_complex_workflow import (
    create_config as create_complex_config,
    run_scenario as run_complex_scenario,
)
from .scenarios.scenario_10_agent_execution import (
    create_config as create_agent_execution_config,
    run_scenario as run_agent_execution_scenario,
)

from .helpers import (
    AssertionHelpers,
    print_event_timeline,
    print_metrics_summary,
)


@pytest.mark.simulation
@pytest.mark.scenario
@pytest.mark.asyncio
async def test_scenario_01_simple_workflow():
    """Test Scenario 1: Simple Workflow."""
    config = create_simple_config()
    runner = SimulationRunner(config)

    result = await runner.run(run_simple_scenario)

    # Print diagnostics
    print_event_timeline(runner)

    # Verify success
    assert result.success, f"Scenario failed with errors: {result.errors}"
    assert result.assertions_passed >= 5, "Expected at least 5 assertions to pass"
    assert result.assertions_failed == 0, "Expected no failed assertions"

    # Verify performance goal (10-100x faster)
    assert result.speed_multiplier >= 10.0, (
        f"Speed multiplier {result.speed_multiplier:.1f}x below 10x target"
    )

    # Verify events captured
    assert result.events_captured >= 6, "Expected at least 6 events"

    # Additional assertions using helpers
    AssertionHelpers.assert_workflow_completed(runner, "ISSUE-123", expected_stages=3)


@pytest.mark.simulation
@pytest.mark.scenario
@pytest.mark.asyncio
async def test_scenario_02_parallel_executions():
    """Test Scenario 2: Parallel Executions."""
    config = create_parallel_config()
    runner = SimulationRunner(config)

    result = await runner.run(run_parallel_scenario)

    # Print diagnostics
    print_event_timeline(runner)

    # Verify success
    assert result.success, f"Scenario failed with errors: {result.errors}"
    assert result.assertions_passed >= 4, "Expected at least 4 assertions to pass"

    # Verify all work items completed
    for work_item_id in ["ISSUE-101", "ISSUE-102", "ISSUE-103"]:
        AssertionHelpers.assert_workflow_completed(runner, work_item_id)

    # Verify performance
    assert result.speed_multiplier >= 10.0


@pytest.mark.simulation
@pytest.mark.scenario
@pytest.mark.asyncio
async def test_scenario_03_review_cycle():
    """Test Scenario 3: Review Cycle with Feedback."""
    config = create_review_config()
    runner = SimulationRunner(config)

    result = await runner.run(run_review_scenario)

    # Print diagnostics
    print_event_timeline(runner)

    # Verify success
    assert result.success, f"Scenario failed with errors: {result.errors}"

    # Verify review cycle events
    rejected_events = runner.get_events_by_type("ReviewRejected")
    approved_events = runner.get_events_by_type("ReviewApproved")

    assert len(rejected_events) == 1, "Expected exactly 1 rejection"
    assert len(approved_events) == 1, "Expected exactly 1 approval"

    # Verify workflow completed after feedback loop
    AssertionHelpers.assert_workflow_completed(runner, "ISSUE-200")

    # Verify performance
    assert result.speed_multiplier >= 10.0


@pytest.mark.simulation
@pytest.mark.scenario
@pytest.mark.asyncio
async def test_scenario_04_execution_failure():
    """Test Scenario 4: Execution Failure and Retry."""
    config = create_failure_config()
    runner = SimulationRunner(config)

    result = await runner.run(run_failure_scenario)

    # Print diagnostics
    print_event_timeline(runner)

    # Verify success
    assert result.success, f"Scenario failed with errors: {result.errors}"

    # Verify failure and retry events
    failed_events = runner.get_events_by_type("AgentExecutionFailed")
    retry_events = runner.get_events_by_type("ExecutionRetryScheduled")
    completed_events = runner.get_events_by_type("AgentExecutionCompleted")

    assert len(failed_events) == 1, "Expected exactly 1 failure"
    assert len(retry_events) == 1, "Expected exactly 1 retry scheduled"
    assert len(completed_events) == 1, "Expected exactly 1 successful completion"

    # Verify workflow eventually completed
    AssertionHelpers.assert_workflow_completed(runner, "ISSUE-300")

    # Verify performance
    assert result.speed_multiplier >= 10.0


@pytest.mark.simulation
@pytest.mark.scenario
@pytest.mark.asyncio
async def test_scenario_05_complex_workflow():
    """Test Scenario 5: Complex Workflow with Branches."""
    config = create_complex_config()
    runner = SimulationRunner(config)

    result = await runner.run(run_complex_scenario)

    # Print diagnostics
    print_event_timeline(runner)

    # Verify success
    assert result.success, f"Scenario failed with errors: {result.errors}"

    # Verify branching occurred
    branch_events = runner.get_events_by_type("WorkflowBranchSelected")
    assert len(branch_events) == 1, "Expected exactly 1 branch selection"

    # Verify multiple stages completed
    completed_events = runner.get_events_by_type("AgentExecutionCompleted")
    assert len(completed_events) >= 4, "Expected at least 4 stage completions"

    # Verify workflow completed
    AssertionHelpers.assert_workflow_completed(runner, "ISSUE-400")

    # Verify simulated time was significant
    assert result.simulated_duration_seconds >= 25 * 60, (
        "Expected at least 25 minutes of simulated time"
    )

    # Verify performance
    assert result.speed_multiplier >= 10.0


@pytest.mark.simulation
@pytest.mark.scenario
@pytest.mark.asyncio
async def test_scenario_10_agent_execution():
    """Test Scenario 10: Agent Execution Lifecycle."""
    config = create_agent_execution_config()
    runner = SimulationRunner(config)

    result = await runner.run(run_agent_execution_scenario)

    # Print diagnostics
    print_event_timeline(runner)

    # Verify success
    assert result.success, f"Scenario failed with errors: {result.errors}"
    assert result.assertions_passed >= 40, (
        f"Expected at least 40 assertions to pass, got {result.assertions_passed}"
    )
    assert result.assertions_failed == 0, (
        f"Expected no failed assertions, got {result.assertions_failed}"
    )

    # Verify performance goal (10-100x faster)
    assert result.speed_multiplier >= 10.0, (
        f"Speed multiplier {result.speed_multiplier:.1f}x below 10x target"
    )


@pytest.mark.simulation
@pytest.mark.asyncio
async def test_all_scenarios_meet_performance_target():
    """
    Meta-test: Verify all scenarios meet the 10-100x performance target.

    Note: scenario_07_repair_cycle is NOT included because it tests the
    MockRepairCycleAdapter directly, not through SimulationRunner.
    It has its own test suite in scenarios/scenario_07_repair_cycle.py.
    """
    scenarios = [
        ("Simple Workflow", create_simple_config, run_simple_scenario),
        ("Parallel Executions", create_parallel_config, run_parallel_scenario),
        ("Review Cycle", create_review_config, run_review_scenario),
        ("Execution Failure", create_failure_config, run_failure_scenario),
        ("Complex Workflow", create_complex_config, run_complex_scenario),
        ("Agent Execution", create_agent_execution_config, run_agent_execution_scenario),
    ]

    results = []

    for name, create_config_func, run_func in scenarios:
        config = create_config_func()
        runner = SimulationRunner(config)
        result = await runner.run(run_func)

        results.append((name, result))

        print(f"\n{name}:")
        print(f"  Speed: {result.speed_multiplier:.1f}x")
        print(f"  Real time: {result.duration_seconds:.2f}s")
        print(f"  Simulated time: {result.simulated_duration_seconds:.1f}s")
        print(f"  Events: {result.events_captured}")
        print(f"  Assertions: {result.assertions_passed}/{result.assertions_passed + result.assertions_failed}")

    # Verify all meet performance target
    for name, result in results:
        assert result.speed_multiplier >= 10.0, (
            f"{name} failed to meet 10x performance target "
            f"(achieved {result.speed_multiplier:.1f}x)"
        )

    # Verify all succeeded
    for name, result in results:
        assert result.success, f"{name} failed: {result.errors}"

    print("\n✓ All scenarios met performance targets and passed")


@pytest.mark.simulation
@pytest.mark.asyncio
async def test_simulation_with_custom_helpers(simulation_runner):
    """Test using simulation helpers for common patterns."""
    from .helpers import ScenarioHelpers, AssertionHelpers

    runner = simulation_runner

    async def custom_scenario(sim: SimulationRunner):
        # Use helpers to simulate workflow
        await ScenarioHelpers.simulate_workflow_execution(
            sim,
            work_item_id="CUSTOM-001",
            stages=[
                {"agent_id": "agent-1", "duration_minutes": 3},
                {"agent_id": "agent-2", "duration_minutes": 5},
            ],
        )

        # Verify basic events
        sim.assert_event_occurred("WorkflowStarted", "CUSTOM-001", "workflow_started")
        sim.assert_event_occurred("WorkflowCompleted", "CUSTOM-001", "workflow_completed")
        sim.assert_event_count("AgentExecutionStarted", 2, "two_executions")

    result = await runner.run(custom_scenario)

    assert result.success
    assert result.assertions_passed == 3
    assert result.events_captured == 6  # 1 start + 2*start + 2*complete + 1 complete (excluding some)


@pytest.mark.simulation
@pytest.mark.asyncio
async def test_simulation_clock_manipulation(simulation_clock):
    """Test simulation clock time manipulation."""
    from datetime import datetime, timezone

    clock = simulation_clock

    # Verify initial time
    start_time = clock.now()
    assert start_time == datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Advance time
    await clock.advance(timedelta(hours=1))
    assert clock.now() == datetime(2025, 1, 1, 13, 0, 0, tzinfo=timezone.utc)

    # Advance to specific time
    await clock.advance_to(datetime(2025, 1, 1, 15, 30, 0, tzinfo=timezone.utc))
    assert clock.now() == datetime(2025, 1, 1, 15, 30, 0, tzinfo=timezone.utc)


@pytest.mark.simulation
@pytest.mark.asyncio
async def test_mock_adapters_integration(
    mock_llm,
    fake_container,
    in_memory_metrics,
    mock_notifier,
):
    """Test that all mock adapters work correctly."""
    # Test LLM adapter
    mock_llm.add_response_pattern(r"test", "Test response")
    result = await mock_llm.execute("test prompt")
    assert result.content == "Test response"

    # Test container adapter
    fake_container.set_command_result("test-cmd", 0, "Success")
    container_result = await fake_container.run(
        image="test-image",
        command=["test-cmd"],
        volumes={},
        environment={},
    )
    assert container_result.exit_code == 0
    assert "Success" in container_result.stdout

    # Test metrics adapter
    await in_memory_metrics.increment_counter("test.counter", 5)
    assert in_memory_metrics.get_counter_value("test.counter") == 5

    # Test notifier adapter
    from codetoreum.ports.output.notifier import (
        NotificationChannel,
        NotificationPriority,
    )

    notif_result = await mock_notifier.send(
        channel=NotificationChannel.EMAIL,
        recipient="test@example.com",
        subject="Test",
        message="Test message",
        priority=NotificationPriority.NORMAL,
    )
    assert notif_result.success
    assert mock_notifier.get_notification_count() == 1


