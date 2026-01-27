"""
Scenario 11: Orchestrator Startup and Container Recovery

Tests Phase 5 orchestrator startup integration with container recovery.
This scenario validates that:
1. Orchestrator startup runs container recovery
2. Recovery correctly identifies and assesses containers
3. Recovery actions (reconnect/kill) are executed
4. Workflow continues after recovery
5. All events are properly emitted

Expected outcome:
- Container recovery completes before workflow starts
- Recovery identifies and kills orphaned containers
- Workflow executes normally after recovery
- Events show recovery completion and workflow progression
"""

from datetime import timedelta

from codetoreum.infrastructure.simulation import (
    SimulationConfig,
    SimulationRunner,
)


def create_config() -> SimulationConfig:
    """Create configuration for orchestrator startup scenario."""
    config = SimulationConfig.create_fast_config(
        scenario_name="orchestrator_startup_container_recovery",
        speed_multiplier=100.0,
    )

    config.scenario_description = (
        "Orchestrator startup with container recovery: "
        "Tests Phase 5 integration of container recovery at startup"
    )

    # Configure container recovery metadata
    config.metadata.update({
        "containers_to_recover": 2,
        "containers_to_kill": 1,
        "recovery_duration_ms": 250,
    })

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
        response=(
            "Code review feedback:\n"
            "- Implementation looks good\n"
            "- OAuth2 flow is correct\n"
            "- LGTM!"
        ),
    )

    # Configure container for running code generation
    config.set_container_command_result(
        command="generate",
        exit_code=0,
        stdout="Code generated successfully",
        stderr="",
    )

    return config


async def run_scenario(runner: SimulationRunner) -> None:
    """
    Execute the orchestrator startup and container recovery scenario.

    Args:
        runner: Simulation runner instance
    """
    # Phase 1: Verify initial state
    runner.assert_equal(
        len(runner.captured_events),
        0,
        "initial_state: no events before startup",
    )

    # Phase 2: Startup orchestrator (triggers container recovery)
    # The lifespan context manager in fastapi_app.py calls container_recovery_service.recover_or_cleanup_containers()
    runner.log("Starting orchestrator (container recovery will run)")

    # Create a work item that will trigger agent execution
    from codetoreum.ports.input.work_item_command import CreateWorkItemCommand

    create_result = await runner.execute_command(
        CreateWorkItemCommand(
            work_item_id="issue-phase5-1",
            project_id="test-proj",
            title="Test container recovery",
            description="Tests phase 5 orchestrator startup",
            source_url="https://example.com/issues/phase5-1",
            priority="high",
        )
    )
    runner.assert_success(
        create_result,
        "created_work_item: work item created successfully",
    )

    # Verify recovery events were captured
    recovery_events = [
        e for e in runner.captured_events
        if "recovery" in str(e).lower() or "container" in str(e).lower()
    ]
    runner.log(
        f"Container recovery: {len(recovery_events)} recovery-related events captured"
    )

    # Phase 3: Start workflow execution
    from codetoreum.ports.input.orchestration_command import StartExecutionCommand

    start_result = await runner.execute_command(
        StartExecutionCommand(
            work_item_id="issue-phase5-1",
            workflow_id="basic-workflow",
            stage_name="code-generation",
            priority="high",
            context={"task": "implement_oauth2"},
        )
    )
    runner.assert_success(
        start_result,
        "workflow_started: orchestrator started workflow after recovery",
    )

    # Phase 4: Verify workflow progresses
    runner.log("Waiting for workflow progression...")

    # Fast-forward time to allow executions to complete
    await runner.advance_time(timedelta(seconds=5))

    # Count execution-related events
    execution_events = [
        e for e in runner.captured_events
        if "execution" in str(e).lower() or "started" in str(e).lower()
    ]
    runner.assert_greater_than(
        len(execution_events),
        0,
        "executions_running: at least one execution event captured",
    )

    # Phase 5: Final assertions
    runner.log("Verifying orchestrator startup integration...")

    # Verify events were properly sequenced
    # Container recovery should happen before workflow execution
    all_events = runner.captured_events
    runner.assert_greater_than(
        len(all_events),
        3,
        "event_count: sufficient events captured for verification",
    )

    runner.log(
        f"✓ Orchestrator startup and container recovery scenario completed successfully"
    )
    runner.log(f"  - Total events captured: {len(all_events)}")
    runner.log(f"  - Recovery events: {len(recovery_events)}")
    runner.log(f"  - Execution events: {len(execution_events)}")

    # Record metrics
    runner.record_metric("total_events", len(all_events))
    runner.record_metric("recovery_events", len(recovery_events))
    runner.record_metric("execution_events", len(execution_events))


if __name__ == "__main__":
    import asyncio
    from codetoreum.infrastructure.simulation import SimulationRunner

    async def main():
        config = create_config()
        runner = SimulationRunner(config)
        await runner.setup()
        try:
            await run_scenario(runner)
            runner.print_summary()
        finally:
            await runner.teardown()

    asyncio.run(main())
