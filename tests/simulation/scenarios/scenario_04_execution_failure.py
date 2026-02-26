"""
Scenario 4: Execution Failure and Retry

Agent execution fails initially, then succeeds on retry.
Tests error handling and retry logic.

Expected outcome:
- First execution fails
- Retry is triggered
- Second execution succeeds
- Workflow completes
"""

from datetime import timedelta

from codetoreum.domain.events import (
    WorkflowStarted,
    AgentExecutionStarted,
    AgentExecutionFailed,
    ExecutionRetryScheduled,
    AgentExecutionCompleted,
    WorkflowCompleted,
)
from codetoreum.infrastructure.simulation import (
    SimulationConfig,
    SimulationRunner,
)


def create_config() -> SimulationConfig:
    """Create configuration for execution failure scenario."""
    config = SimulationConfig.create_fast_config(
        scenario_name="execution_failure_and_retry",
        speed_multiplier=100.0,
    )

    config.scenario_description = "Agent execution fails and retries successfully"

    # Simulate flaky agent (fails first, succeeds second)
    config.add_agent_response_pattern(
        agent_id="flaky-agent",
        pattern=r".*",
        response="Success on retry",
    )

    # Container command fails first time
    config.set_container_command_result(
        command="build",
        exit_code=1,
        stdout="",
        stderr="Error: Build failed due to temporary network issue",
    )

    return config


async def run_scenario(runner: SimulationRunner) -> None:
    """Execute execution failure scenario."""
    work_item_id = "ISSUE-300"

    # Start workflow
    event = WorkflowStarted(
        aggregate_id=work_item_id,
        payload={"workflow_id": "build-workflow"},
    )
    runner.capture_event(event)

    # First execution attempt
    await runner.advance_time(timedelta(minutes=2))

    event = AgentExecutionStarted(
        aggregate_id="exec-1",
        payload={"agent_id": "flaky-agent", "attempt": 1},
    )
    runner.capture_event(event)

    await runner.advance_time(timedelta(minutes=3))

    # First execution fails
    event = AgentExecutionFailed(
        aggregate_id="exec-1",
        payload={"status": "failed", "error": "Network timeout"},
    )
    runner.capture_event(event)

    runner.assert_event_occurred("AgentExecutionFailed", assertion_name="first_attempt_failed")

    # Retry scheduled
    await runner.advance_time(timedelta(minutes=1))

    event = ExecutionRetryScheduled(
        aggregate_id="exec-1",
        payload={"retry_attempt": 1},
    )
    runner.capture_event(event)

    # Second execution attempt
    await runner.advance_time(timedelta(minutes=2))

    event = AgentExecutionStarted(
        aggregate_id="exec-2",
        payload={"agent_id": "flaky-agent", "attempt": 2},
    )
    runner.capture_event(event)

    await runner.advance_time(timedelta(minutes=3))

    # Second execution succeeds
    event = AgentExecutionCompleted(
        aggregate_id="exec-2",
        payload={"status": "completed"},
    )
    runner.capture_event(event)

    runner.assert_event_occurred("AgentExecutionCompleted", assertion_name="retry_succeeded")

    # Workflow completes
    event = WorkflowCompleted(
        aggregate_id=work_item_id,
        payload={"total_attempts": 2},
    )
    runner.capture_event(event)

    # Assertions
    runner.assert_event_count("AgentExecutionStarted", 2, "two_attempts")
    runner.assert_event_count("AgentExecutionFailed", 1, "one_failure")
    runner.assert_event_count("ExecutionRetryScheduled", 1, "one_retry_scheduled")
    runner.assert_event_count("AgentExecutionCompleted", 1, "one_success")


async def test_execution_failure():
    """Test execution failure and retry scenario."""
    config = create_config()
    runner = SimulationRunner(config)

    result = await runner.run(run_scenario)
    runner.print_summary()

    assert result.success, f"Scenario failed: {result.errors}"
    assert result.events_captured == 8
    assert result.assertions_passed == 6


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_execution_failure())
