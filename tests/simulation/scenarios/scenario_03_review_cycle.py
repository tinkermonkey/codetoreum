"""
Scenario 3: Review Cycle with Feedback Loop

Work item goes through maker-checker review with feedback loop.
Tests review rejection and resubmission.

Expected outcome:
- Initial code generation
- Review rejects (needs changes)
- Code regeneration with feedback
- Review approves
- Workflow completes
"""

from datetime import timedelta

from codetoreum.domain.events import DomainEvent
from codetoreum.infrastructure.simulation import (
    SimulationConfig,
    SimulationRunner,
)


def create_config() -> SimulationConfig:
    """Create configuration for review cycle scenario."""
    config = SimulationConfig.create_fast_config(
        scenario_name="review_cycle_with_feedback",
        speed_multiplier=100.0,
    )

    config.scenario_description = "Review cycle with rejection and resubmission"

    config.add_agent_response_pattern(
        agent_id="code-generator",
        pattern=r".*first.*",
        response="First version of code (needs improvement)",
    )

    config.add_agent_response_pattern(
        agent_id="code-generator",
        pattern=r".*revised.*",
        response="Revised version of code (improved based on feedback)",
    )

    config.add_agent_response_pattern(
        agent_id="reviewer",
        pattern=r".*first.*",
        response="NEEDS_CHANGES: Please add error handling",
    )

    config.add_agent_response_pattern(
        agent_id="reviewer",
        pattern=r".*revised.*",
        response="APPROVED: Looks good now!",
    )

    return config


async def run_scenario(runner: SimulationRunner) -> None:
    """Execute review cycle scenario."""
    work_item_id = "ISSUE-200"

    # Start workflow
    event = DomainEvent(
        aggregate_id=work_item_id,
        aggregate_type="WorkItem",
        payload={"workflow_id": "review-workflow"},
    )
    event.event_type = "WorkflowStarted"
    runner.capture_event(event)

    # First code generation
    await runner.advance_time(timedelta(minutes=5))

    event = DomainEvent(
        aggregate_id="exec-1",
        aggregate_type="AgentExecution",
        payload={"agent_id": "code-generator", "iteration": 1},
    )
    event.event_type = "AgentExecutionCompleted"
    runner.capture_event(event)

    # Review rejects
    await runner.advance_time(timedelta(minutes=3))

    event = DomainEvent(
        aggregate_id="review-1",
        aggregate_type="ReviewCycle",
        payload={"decision": "rejected", "feedback": "Add error handling"},
    )
    event.event_type = "ReviewRejected"
    runner.capture_event(event)

    runner.assert_event_occurred("ReviewRejected", assertion_name="first_review_rejected")

    # Code regeneration with feedback
    await runner.advance_time(timedelta(minutes=5))

    event = DomainEvent(
        aggregate_id="exec-2",
        aggregate_type="AgentExecution",
        payload={"agent_id": "code-generator", "iteration": 2, "with_feedback": True},
    )
    event.event_type = "AgentExecutionCompleted"
    runner.capture_event(event)

    # Review approves
    await runner.advance_time(timedelta(minutes=3))

    event = DomainEvent(
        aggregate_id="review-2",
        aggregate_type="ReviewCycle",
        payload={"decision": "approved"},
    )
    event.event_type = "ReviewApproved"
    runner.capture_event(event)

    runner.assert_event_occurred("ReviewApproved", assertion_name="second_review_approved")

    # Workflow completes
    event = DomainEvent(
        aggregate_id=work_item_id,
        aggregate_type="WorkItem",
        payload={"iterations": 2},
    )
    event.event_type = "WorkflowCompleted"
    runner.capture_event(event)

    # Assertions
    runner.assert_event_count("ReviewRejected", 1, "one_rejection")
    runner.assert_event_count("ReviewApproved", 1, "one_approval")
    runner.assert_event_count("AgentExecutionCompleted", 2, "two_executions")


async def test_review_cycle():
    """Test review cycle scenario."""
    config = create_config()
    runner = SimulationRunner(config)

    result = await runner.run(run_scenario)
    runner.print_summary()

    assert result.success, f"Scenario failed: {result.errors}"
    assert result.events_captured == 6
    assert result.assertions_passed == 5


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_review_cycle())
