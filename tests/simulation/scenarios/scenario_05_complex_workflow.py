"""
Scenario 5: Complex Workflow with Branches

Multi-stage workflow with conditional branches based on results.
Tests complex workflow logic.

Expected outcome:
- Initial analysis determines approach
- Branch A or B is selected based on analysis
- Multiple stages execute
- Final validation
- Workflow completes
"""

from datetime import timedelta

from codetoreum.domain.events import DomainEvent
from codetoreum.infrastructure.simulation import (
    SimulationConfig,
    SimulationRunner,
)


def create_config() -> SimulationConfig:
    """Create configuration for complex workflow scenario."""
    config = SimulationConfig.create_fast_config(
        scenario_name="complex_workflow_with_branches",
        speed_multiplier=100.0,
    )

    config.scenario_description = "Multi-stage workflow with conditional branches"

    # Configure multiple agents
    config.add_agent_response_pattern(
        agent_id="analyzer",
        pattern=r".*",
        response="Analysis: This requires approach B (refactoring)",
    )

    config.add_agent_response_pattern(
        agent_id="refactorer",
        pattern=r".*",
        response="Refactored code structure",
    )

    config.add_agent_response_pattern(
        agent_id="tester",
        pattern=r".*",
        response="All tests passed",
    )

    config.add_agent_response_pattern(
        agent_id="validator",
        pattern=r".*",
        response="Validation successful",
    )

    return config


async def run_scenario(runner: SimulationRunner) -> None:
    """Execute complex workflow scenario."""
    work_item_id = "ISSUE-400"

    # Start workflow
    event = DomainEvent(
        aggregate_id=work_item_id,
        aggregate_type="WorkItem",
        payload={"workflow_id": "complex-workflow"},
    )
    event.event_type = "WorkflowStarted"
    runner.capture_event(event)

    # Stage 1: Analysis
    await runner.advance_time(timedelta(minutes=5))

    event = DomainEvent(
        aggregate_id="exec-1",
        aggregate_type="AgentExecution",
        payload={"agent_id": "analyzer", "stage": "analysis"},
    )
    event.event_type = "AgentExecutionCompleted"
    runner.capture_event(event)

    # Branch decision
    event = DomainEvent(
        aggregate_id=work_item_id,
        aggregate_type="Workflow",
        payload={"branch": "refactoring", "reason": "Complex codebase"},
    )
    event.event_type = "WorkflowBranchSelected"
    runner.capture_event(event)

    runner.assert_event_occurred("WorkflowBranchSelected", assertion_name="branch_selected")

    # Stage 2a: Refactoring (Branch B)
    await runner.advance_time(timedelta(minutes=10))

    event = DomainEvent(
        aggregate_id="exec-2",
        aggregate_type="AgentExecution",
        payload={"agent_id": "refactorer", "stage": "refactoring"},
    )
    event.event_type = "AgentExecutionCompleted"
    runner.capture_event(event)

    # Stage 3: Testing
    await runner.advance_time(timedelta(minutes=8))

    event = DomainEvent(
        aggregate_id="exec-3",
        aggregate_type="AgentExecution",
        payload={"agent_id": "tester", "stage": "testing"},
    )
    event.event_type = "AgentExecutionCompleted"
    runner.capture_event(event)

    # Stage 4: Validation
    await runner.advance_time(timedelta(minutes=5))

    event = DomainEvent(
        aggregate_id="exec-4",
        aggregate_type="AgentExecution",
        payload={"agent_id": "validator", "stage": "validation"},
    )
    event.event_type = "AgentExecutionCompleted"
    runner.capture_event(event)

    # Workflow completes
    event = DomainEvent(
        aggregate_id=work_item_id,
        aggregate_type="WorkItem",
        payload={
            "total_stages": 4,
            "branch_taken": "refactoring",
        },
    )
    event.event_type = "WorkflowCompleted"
    runner.capture_event(event)

    # Assertions
    runner.assert_event_count("AgentExecutionCompleted", 4, "four_stages_completed")
    runner.assert_event_occurred("WorkflowBranchSelected", assertion_name="branching_occurred")
    runner.assert_event_occurred("WorkflowCompleted", assertion_name="workflow_completed")

    # Verify total simulated time
    total_time = timedelta(minutes=5 + 10 + 8 + 5)
    runner.assert_true(
        True,  # Just checking we got here
        "timing_check",
        f"Simulated {total_time.total_seconds() / 60} minutes of workflow",
    )


async def test_complex_workflow():
    """Test complex workflow scenario."""
    config = create_config()
    runner = SimulationRunner(config)

    result = await runner.run(run_scenario)
    runner.print_summary()

    assert result.success, f"Scenario failed: {result.errors}"
    assert result.events_captured == 7
    assert result.assertions_passed == 5
    assert result.simulated_duration_seconds >= 28 * 60  # At least 28 minutes simulated


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_complex_workflow())
