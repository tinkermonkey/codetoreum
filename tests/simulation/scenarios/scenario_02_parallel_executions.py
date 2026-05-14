"""
Scenario 2: Parallel Executions

Multiple work items progress through the workflow simultaneously.
Tests concurrent execution handling.

Expected outcome:
- 3 work items start workflows
- Agent executions run in parallel
- All workflows complete successfully
"""

from datetime import timedelta

from tests.simulation.test_event_helpers import (
    AgentExecutionCompleted,
    AgentExecutionStarted,
    WorkflowCompleted,
    WorkflowStarted,
)
from codetoreum.infrastructure.simulation import (
    SimulationConfig,
    SimulationRunner,
)


def create_config() -> SimulationConfig:
    """Create configuration for parallel execution scenario."""
    config = SimulationConfig.create_fast_config(
        scenario_name="parallel_executions",
        speed_multiplier=100.0,
    )

    config.scenario_description = "3 work items executing in parallel"

    # Configure agents
    config.add_agent_response_pattern(
        agent_id="code-generator",
        pattern=r".*",
        response="Generated code for the feature",
    )

    return config


async def run_scenario(runner: SimulationRunner) -> None:
    """Execute parallel executions scenario."""
    work_items = ["ISSUE-101", "ISSUE-102", "ISSUE-103"]

    # Start all workflows
    for work_item_id in work_items:
        event = WorkflowStarted(
            aggregate_id=work_item_id,
            payload={"workflow_id": "basic-workflow"},
        )
        runner.capture_event(event)

    runner.assert_event_count("WorkflowStarted", 3, "all_workflows_started")

    # Simulate parallel executions
    await runner.advance_time(timedelta(minutes=5))

    # All items start execution
    for i, work_item_id in enumerate(work_items):
        event = AgentExecutionStarted(
            aggregate_id=f"exec-{i + 1}",
            payload={"work_item_id": work_item_id},
        )
        runner.capture_event(event)

    runner.assert_event_count("AgentExecutionStarted", 3, "all_executions_started")

    # All complete
    await runner.advance_time(timedelta(minutes=10))

    for i in range(3):
        event = AgentExecutionCompleted(
            aggregate_id=f"exec-{i + 1}",
            payload={"status": "completed"},
        )
        runner.capture_event(event)

    runner.assert_event_count("AgentExecutionCompleted", 3, "all_executions_completed")

    # All workflows complete
    for work_item_id in work_items:
        event = WorkflowCompleted(
            aggregate_id=work_item_id,
            payload={"workflow_id": "basic-workflow"},
        )
        runner.capture_event(event)

    runner.assert_event_count("WorkflowCompleted", 3, "all_workflows_completed")


async def test_parallel_executions():
    """Test parallel executions scenario."""
    config = create_config()
    runner = SimulationRunner(config)

    result = await runner.run(run_scenario)
    runner.print_summary()

    assert result.success, f"Scenario failed: {result.errors}"
    assert result.events_captured == 12  # 3 * (start + exec_start + exec_done + complete)
    assert result.speed_multiplier >= 10.0


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_parallel_executions())
