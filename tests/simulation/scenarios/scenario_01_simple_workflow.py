"""
Scenario 1: Simple Workflow

Single work item progresses through a 3-stage workflow with 3 different agents.
Tests basic workflow execution with no complications.

Expected outcome:
- Work item moves through all 3 stages
- 3 agent executions complete successfully
- Workflow completes successfully
"""

from datetime import timedelta

from codetoreum.infrastructure.simulation import (
    SimulationConfig,
    SimulationRunner,
)


def create_config() -> SimulationConfig:
    """Create configuration for simple workflow scenario."""
    config = SimulationConfig.create_fast_config(
        scenario_name="simple_workflow",
        speed_multiplier=100.0,
    )

    config.scenario_description = "Single work item through 3-stage workflow: Code Generation -> Review -> Testing"

    # Configurable test output values
    config.metadata.update(
        {
            "tests_passed": 10,
            "tests_failed": 0,
            "coverage_percent": 95,
        }
    )

    # Configure code generator agent
    config.add_agent_response_pattern(
        agent_id="code-generator",
        pattern=r".*generate.*",
        response=(
            "I've generated the following code:\n\n"
            "```python\n"
            "def authenticate_user(username: str, password: str) -> bool:\n"
            "    # OAuth2 authentication implementation\n"
            "    return True\n"
            "```"
        ),
    )

    # Configure code reviewer agent
    config.add_agent_response_pattern(
        agent_id="code-reviewer",
        pattern=r".*review.*",
        response=("Code review feedback:\n- Implementation looks good\n- OAuth2 flow is correct\n- LGTM!"),
    )

    # Configure test runner agent
    config.add_agent_response_pattern(
        agent_id="test-runner",
        pattern=r".*test.*",
        response=(
            "Test execution completed:\n"
            "- {tests_passed} tests passed\n"
            "- {tests_failed} tests failed\n"
            "- Coverage: {coverage_percent}%"
        ),
    )

    # Configure container for running tests
    config.set_container_command_result(
        command="pytest",
        exit_code=0,
        stdout=f"====== {config.metadata['tests_passed']} passed in 2.5s =======",
        stderr="",
    )

    return config


async def run_scenario(runner: SimulationRunner) -> None:
    """
    Execute the simple workflow scenario.

    Args:
        runner: Simulation runner instance
    """
    # Initial assertions
    runner.assert_equal(
        len(runner.captured_events),
        0,
        "initial_state",
        "No events at start",
    )

    # Simulate triggering a workflow
    # In a real scenario, this would call WorkflowOrchestrator
    # For now, we'll simulate by capturing events manually

    from codetoreum.domain.events import (
        AgentExecutionCompleted,
        AgentExecutionStarted,
        WorkflowCompleted,
        WorkflowStarted,
    )

    # Simulate workflow start
    workflow_started = WorkflowStarted(
        aggregate_id="ISSUE-123",
        payload={
            "workflow_id": "basic-workflow",
            "stage": "Code Generation",
        },
    )
    runner.capture_event(workflow_started)

    runner.assert_event_occurred(
        "WorkflowStarted",
        "ISSUE-123",
        "workflow_started",
    )

    # Advance time for stage 1 execution (code generation)
    await runner.advance_time(timedelta(minutes=5))

    # Simulate agent execution for code generation
    execution_started_1 = AgentExecutionStarted(
        aggregate_id="exec-1",
        payload={
            "agent_id": "code-generator",
            "work_item_id": "ISSUE-123",
        },
    )
    runner.capture_event(execution_started_1)

    await runner.advance_time(timedelta(minutes=2))

    execution_completed_1 = AgentExecutionCompleted(
        aggregate_id="exec-1",
        payload={
            "agent_id": "code-generator",
            "status": "completed",
        },
    )
    runner.capture_event(execution_completed_1)

    # Advance time for stage 2 execution (code review)
    await runner.advance_time(timedelta(minutes=1))

    execution_started_2 = AgentExecutionStarted(
        aggregate_id="exec-2",
        payload={
            "agent_id": "code-reviewer",
            "work_item_id": "ISSUE-123",
        },
    )
    runner.capture_event(execution_started_2)

    await runner.advance_time(timedelta(minutes=3))

    execution_completed_2 = AgentExecutionCompleted(
        aggregate_id="exec-2",
        payload={
            "agent_id": "code-reviewer",
            "status": "completed",
        },
    )
    runner.capture_event(execution_completed_2)

    # Advance time for stage 3 execution (testing)
    await runner.advance_time(timedelta(minutes=1))

    execution_started_3 = AgentExecutionStarted(
        aggregate_id="exec-3",
        payload={
            "agent_id": "test-runner",
            "work_item_id": "ISSUE-123",
        },
    )
    runner.capture_event(execution_started_3)

    await runner.advance_time(timedelta(minutes=4))

    execution_completed_3 = AgentExecutionCompleted(
        aggregate_id="exec-3",
        payload={
            "agent_id": "test-runner",
            "status": "completed",
        },
    )
    runner.capture_event(execution_completed_3)

    # Workflow completes
    workflow_completed = WorkflowCompleted(
        aggregate_id="ISSUE-123",
        payload={
            "workflow_id": "basic-workflow",
            "final_stage": "Testing",
        },
    )
    runner.capture_event(workflow_completed)

    # Final assertions
    runner.assert_event_count(
        "AgentExecutionStarted",
        3,
        "three_executions_started",
    )

    runner.assert_event_count(
        "AgentExecutionCompleted",
        3,
        "three_executions_completed",
    )

    runner.assert_event_occurred(
        "WorkflowCompleted",
        "ISSUE-123",
        "workflow_completed",
    )

    # Check that we have all expected events
    runner.assert_equal(
        len(runner.captured_events),
        8,  # 1 start + 3*2 executions + 1 complete
        "total_events",
        "Expected 8 total events",
    )


async def test_simple_workflow():
    """Test simple workflow scenario."""
    config = create_config()
    runner = SimulationRunner(config)

    result = await runner.run(run_scenario)

    # Print summary
    runner.print_summary()

    # Verify success
    assert result.success, f"Scenario failed: {result.errors}"
    assert result.assertions_passed == 6
    assert result.assertions_failed == 0
    assert result.events_captured == 8

    # Verify performance goal (10-100x faster)
    assert result.speed_multiplier >= 10.0, f"Speed multiplier {result.speed_multiplier:.1f}x is below 10x target"

    print(f"\n✓ Scenario completed {result.speed_multiplier:.1f}x faster than real time")


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_simple_workflow())
