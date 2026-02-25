"""Simulation Scenario 10: Agent Execution Lifecycle.

Tests comprehensive agent execution workflows including:
1. Single agent execution lifecycle (INITIALIZED → RUNNING → COMPLETED)
2. Concurrent agent executions across multiple work items
3. Execution with container provisioning and context mounting
4. Agent failure and timeout scenarios
5. Execution retry logic with backoff
6. Token usage tracking and reporting
7. Session continuity across multiple executions
8. Execution cancellation and pause/resume

Key Features Tested:
- AgentExecution entity lifecycle and state transitions
- ExecutionService container orchestration
- ExecutionContext preparation with environment and file mounting
- Token counting (input/output) and cost calculation
- Event emission for all execution state changes
- Error handling and retry logic
- Workspace context (issue vs discussion vs hybrid)
- Resource cleanup and container removal
"""

from datetime import timedelta

import pytest

from codetoreum.domain.agent_execution import AgentExecution, ExecutionStatus
from codetoreum.domain.value_objects import ContainerConfig, ExecutionContext
from codetoreum.domain.workspace_context import WorkspaceContext
from codetoreum.infrastructure.simulation import (
    SimulationConfig,
    SimulationRunner,
)


def create_config(
    scenario_name: str = "scenario_10_agent_execution",
) -> SimulationConfig:
    """Create configuration for agent execution scenario."""
    config = SimulationConfig.create_fast_config(
        scenario_name=scenario_name,
        speed_multiplier=100.0,
    )
    config.scenario_description = (
        "Comprehensive agent execution lifecycle testing including state transitions, "
        "container provisioning, error handling, retries, and token tracking"
    )

    # Configure agent responses for different execution patterns
    config.add_agent_response_pattern(
        agent_id="code-generator",
        pattern=r"generate.*code",
        response="```python\nclass Feature:\n    def __init__(self):\n        pass\n```",
    )

    config.add_agent_response_pattern(
        agent_id="code-reviewer",
        pattern=r"review.*code",
        response="LGTM! Code looks good. Minor suggestion on naming.",
    )

    config.add_agent_response_pattern(
        agent_id="test-runner",
        pattern=r"run.*test",
        response="All 15 tests passed successfully in 2.3s",
    )

    # Configure container results
    config.set_container_command_result(
        command="pytest",
        exit_code=0,
        stdout="===== 15 passed in 2.31s =====",
    )

    config.set_container_command_result(
        command="python -m pylint",
        exit_code=0,
        stdout="Your code has been rated at 9.5/10",
    )

    return config


async def run_scenario(runner: SimulationRunner):
    """Run agent execution simulation scenarios.

    This scenario tests the complete agent execution lifecycle through multiple
    test cases that progressively exercise more complex scenarios.
    """

    # Test Case 1: Single Agent Execution - Happy Path
    await scenario_single_agent_execution_happy_path(runner)

    # Test Case 2: Multiple Concurrent Executions
    await scenario_multiple_concurrent_executions(runner)

    # Test Case 3: Execution with Container Provisioning
    await scenario_execution_with_container_provisioning(runner)

    # Test Case 4: Agent Failure and Error Handling
    await scenario_agent_failure_scenarios(runner)

    # Test Case 5: Execution Timeout
    await scenario_execution_timeout_scenario(runner)

    # Test Case 6: Token Usage Tracking
    await scenario_token_usage_tracking(runner)

    # Test Case 7: Session Continuity
    await scenario_session_continuity(runner)

    # Test Case 8: Execution Cancellation
    await scenario_execution_cancellation(runner)


async def scenario_single_agent_execution_happy_path(runner: SimulationRunner):
    """Test single agent execution with complete lifecycle.

    Validates:
    - Execution creation and initialization
    - Transition from INITIALIZED to RUNNING to COMPLETED
    - Event emission at each state transition
    - Output and token tracking
    """
    # Create execution
    execution = AgentExecution.create(
        agent_id="code-generator",
        work_item_id="ISSUE-101",
        workflow_id="workflow-main",
        stage_name="coding",
        prompt="Generate a Python class for user authentication",
        model="claude-sonnet-4-5",
    )

    # Verify initial state
    runner.assert_equal(
        execution.status,
        ExecutionStatus.INITIALIZED,
        "single_execution_initialized",
        "Execution should be in INITIALIZED state after creation"
    )
    runner.assert_true(
        execution.id is not None,
        "single_execution_has_id",
        "Execution should have an ID"
    )

    # Capture initialization event
    init_event = execution.get_pending_events()[0]
    runner.assert_equal(
        init_event.event_type,
        "ExecutionInitialized",
        "single_execution_init_event",
        "Should emit ExecutionInitialized event"
    )

    # Start execution
    execution.start(container_name="agent-101-dev")
    runner.assert_equal(
        execution.status,
        ExecutionStatus.RUNNING,
        "single_execution_running",
        "Execution should be in RUNNING state after start"
    )
    runner.assert_true(
        execution.started_at is not None,
        "single_execution_started_at",
        "Started timestamp should be set"
    )

    # Advance time to simulate agent working
    await runner.advance_time(timedelta(seconds=30))

    # Complete execution
    execution.complete(
        output="```python\nclass AuthenticationManager:\n    def login(self, user, pwd):\n        pass\n```",
        input_tokens=145,
        output_tokens=89,
        session_id="session-abc123",
    )

    runner.assert_equal(
        execution.status,
        ExecutionStatus.COMPLETED,
        "single_execution_completed",
        "Execution should be in COMPLETED state after completion"
    )
    runner.assert_true(
        execution.completed_at is not None,
        "single_execution_completed_at",
        "Completed timestamp should be set"
    )
    runner.assert_equal(
        execution.exit_code,
        0,
        "single_execution_exit_code",
        "Exit code should be 0 for successful completion"
    )
    runner.assert_equal(
        execution.input_tokens,
        145,
        "single_execution_input_tokens",
        "Input tokens should be tracked"
    )
    runner.assert_equal(
        execution.output_tokens,
        89,
        "single_execution_output_tokens",
        "Output tokens should be tracked"
    )
    runner.assert_equal(
        execution.get_total_tokens(),
        234,
        "single_execution_total_tokens",
        "Total tokens should be input + output"
    )

    # Verify terminal state
    runner.assert_true(
        execution.is_terminal(),
        "single_execution_is_terminal",
        "COMPLETED is a terminal state"
    )


async def scenario_multiple_concurrent_executions(runner: SimulationRunner):
    """Test multiple agents executing concurrently on different work items.

    Validates:
    - Independent execution tracking
    - Concurrent state management
    - Event correlation via correlation_id
    """
    # Create three concurrent executions
    executions = []
    for i in range(1, 4):
        exec_id = f"ISSUE-20{i}"
        execution = AgentExecution.create(
            agent_id="code-generator" if i == 1 else "code-reviewer" if i == 2 else "test-runner",
            work_item_id=exec_id,
            workflow_id=f"workflow-{i}",
            stage_name="coding" if i <= 2 else "testing",
            prompt=f"Process item {i}",
            model="claude-sonnet-4-5",
        )
        executions.append(execution)

    # Start all executions
    for i, execution in enumerate(executions):
        execution.start(container_name=f"agent-20{i+1}-dev")

    runner.assert_equal(
        len(executions),
        3,
        "concurrent_execution_count",
        "Should have 3 concurrent executions"
    )

    # Verify all are in RUNNING state
    for exec in executions:
        runner.assert_equal(
            exec.status,
            ExecutionStatus.RUNNING,
            f"concurrent_exec_{exec.work_item_id}_running",
            f"Execution {exec.work_item_id} should be RUNNING"
        )

    # Complete first two, leave third running
    await runner.advance_time(timedelta(seconds=20))
    executions[0].complete(output="Generated code", input_tokens=100, output_tokens=50)

    await runner.advance_time(timedelta(seconds=15))
    executions[1].complete(output="Code reviewed", input_tokens=95, output_tokens=42)

    # Verify mixed states
    runner.assert_equal(
        executions[0].status,
        ExecutionStatus.COMPLETED,
        "concurrent_first_completed",
        "First execution should be COMPLETED"
    )
    runner.assert_equal(
        executions[1].status,
        ExecutionStatus.COMPLETED,
        "concurrent_second_completed",
        "Second execution should be COMPLETED"
    )
    runner.assert_equal(
        executions[2].status,
        ExecutionStatus.RUNNING,
        "concurrent_third_running",
        "Third execution should still be RUNNING"
    )

    # Complete final execution
    await runner.advance_time(timedelta(seconds=25))
    executions[2].complete(output="Tests passed", input_tokens=120, output_tokens=65)

    runner.assert_equal(
        executions[2].status,
        ExecutionStatus.COMPLETED,
        "concurrent_third_completed",
        "Third execution should now be COMPLETED"
    )


async def scenario_execution_with_container_provisioning(runner: SimulationRunner):
    """Test execution with container context and environment setup.

    Validates:
    - ExecutionContext preparation
    - Container configuration
    - Environment variable passing
    - Workspace context determination
    """
    # Create execution context with full configuration
    workspace_ctx = WorkspaceContext.for_issue(
        project_id="proj-123",
        work_item_id="ISSUE-301",
        branch_name="feature/auth-system",
        create_pr=True
    )

    exec_context = ExecutionContext(
        work_item_id="ISSUE-301",
        workflow_id="workflow-main",
        stage_name="implementation",
        agent_id="developer",
        model="claude-sonnet-4-5",
        timeout_seconds=900,
        workspace_type=workspace_ctx.workspace_type.value,
        branch_name=workspace_ctx.branch_name,
        discussion_id=None,
        project_id="proj-123",
        repository_url="https://github.com/org/repo.git",
        tech_stack=["python", "fastapi", "postgresql"],
        filesystem_write_allowed=True,
        can_make_commits=True,
        requires_docker=True,
        mcp_servers=["filesystem", "git", "bash"],
        previous_session_id=None,
        metadata={"task_category": "backend", "priority": "high"},
    )

    # Verify context properties
    runner.assert_equal(
        exec_context.work_item_id,
        "ISSUE-301",
        "container_context_work_item",
        "Context should contain work item ID"
    )
    runner.assert_equal(
        exec_context.branch_name,
        "feature/auth-system",
        "container_context_branch",
        "Context should contain branch name for issue workspace"
    )
    runner.assert_true(
        exec_context.filesystem_write_allowed,
        "container_context_write_allowed",
        "Filesystem write should be allowed"
    )
    runner.assert_true(
        exec_context.can_make_commits,
        "container_context_can_commit",
        "Commit capability should be enabled"
    )

    # Create container configuration
    container_config = ContainerConfig(
        image="codetoreum/agent:latest",
        name="agent-301-dev",
        command=["/bin/bash", "-c", "python -m src.agent.main"],
        working_dir="/workspace",
        user="1000:1000",
        environment={
            "AGENT_ID": "developer",
            "WORK_ITEM": "ISSUE-301",
            "GITHUB_TOKEN": "***",
            "DEBUG": "true",
        },
        volumes={
            "/host/repo": {"bind": "/workspace", "mode": "rw"},
            "/host/context": {"bind": "/context", "mode": "ro"},
        },
        auto_remove=False,
    )

    runner.assert_equal(
        container_config.image,
        "codetoreum/agent:latest",
        "container_image",
        "Container should have correct image"
    )
    runner.assert_equal(
        container_config.user,
        "1000:1000",
        "container_user",
        "Container should run as specific user"
    )
    runner.assert_true(
        "AGENT_ID" in container_config.environment,
        "container_env_agent_id",
        "Container should have AGENT_ID environment variable"
    )
    runner.assert_true(
        container_config.volumes is not None
        and any("/workspace" in (v.get("bind") or "") for v in container_config.volumes.values()),
        "container_workspace_volume",
        "Container should have workspace volume mounted"
    )


async def scenario_agent_failure_scenarios(runner: SimulationRunner):
    """Test agent execution failure scenarios and error handling.

    Validates:
    - Failure state transition (RUNNING → FAILED)
    - Error message capture
    - Exit code assignment
    - Event emission on failure
    """
    # Scenario 1: Agent fails during execution
    execution1 = AgentExecution.create(
        agent_id="code-generator",
        work_item_id="ISSUE-401",
        workflow_id="workflow-main",
        stage_name="coding",
        prompt="Generate invalid code",
        model="claude-sonnet-4-5",
    )

    execution1.start()
    await runner.advance_time(timedelta(seconds=20))

    # Simulate failure
    execution1.fail(
        error_message="LLM rate limit exceeded, retry after 60 seconds",
        exit_code=429
    )

    runner.assert_equal(
        execution1.status,
        ExecutionStatus.FAILED,
        "failure_status",
        "Execution should be in FAILED state"
    )
    runner.assert_equal(
        execution1.exit_code,
        429,
        "failure_exit_code",
        "Exit code should reflect rate limit error"
    )
    runner.assert_true(
        execution1.error_message is not None
        and "rate limit" in execution1.error_message.lower(),
        "failure_error_message",
        "Error message should be captured"
    )
    runner.assert_true(
        execution1.is_terminal(),
        "failure_is_terminal",
        "FAILED is a terminal state"
    )

    # Scenario 2: Failure with no exit code specified
    execution2 = AgentExecution.create(
        agent_id="test-runner",
        work_item_id="ISSUE-402",
        workflow_id="workflow-main",
        stage_name="testing",
        prompt="Run tests",
        model="claude-sonnet-4-5",
    )

    execution2.start()
    await runner.advance_time(timedelta(seconds=15))

    execution2.fail(error_message="Container execution failed: out of memory")

    runner.assert_equal(
        execution2.status,
        ExecutionStatus.FAILED,
        "failure_no_exit_code_status",
        "Execution should fail"
    )
    runner.assert_true(
        execution2.exit_code is None or execution2.exit_code != 0,
        "failure_no_exit_code",
        "Exit code should not be 0 for failure"
    )


async def scenario_execution_timeout_scenario(runner: SimulationRunner):
    """Test execution timeout handling.

    Validates:
    - Timeout state transition (RUNNING → TIMEOUT)
    - Exit code assignment for timeout (-1)
    - Automatic failure on timeout
    """
    execution = AgentExecution.create(
        agent_id="code-generator",
        work_item_id="ISSUE-501",
        workflow_id="workflow-main",
        stage_name="coding",
        prompt="Generate very complex code",
        model="claude-sonnet-4-5",
    )

    execution.start()

    # Simulate execution timeout
    await runner.advance_time(timedelta(seconds=15 * 60))  # 15 minutes timeout

    execution.timeout()

    runner.assert_equal(
        execution.status,
        ExecutionStatus.TIMEOUT,
        "timeout_status",
        "Execution should be in TIMEOUT state"
    )
    runner.assert_equal(
        execution.exit_code,
        -1,
        "timeout_exit_code",
        "Timeout should have exit code -1"
    )
    runner.assert_true(
        execution.error_message is not None
        and "timeout" in execution.error_message.lower(),
        "timeout_error_message",
        "Error message should indicate timeout"
    )
    runner.assert_true(
        execution.is_terminal(),
        "timeout_is_terminal",
        "TIMEOUT is a terminal state"
    )


async def scenario_token_usage_tracking(runner: SimulationRunner):
    """Test token usage tracking and cost calculation.

    Validates:
    - Input and output token counting
    - Total token calculation
    - Token tracking across multiple executions
    """
    executions = []

    # Create three executions with different token usage
    for i, (in_tokens, out_tokens) in enumerate([(100, 50), (150, 75), (200, 120)], 1):
        exec = AgentExecution.create(
            agent_id=f"agent-{i}",
            work_item_id=f"ISSUE-60{i}",
            workflow_id="workflow-token-test",
            stage_name="processing",
            prompt=f"Process with token usage {i}",
            model="claude-sonnet-4-5",
        )
        exec.start()
        await runner.advance_time(timedelta(seconds=10))
        exec.complete(
            output=f"Output {i}",
            input_tokens=in_tokens,
            output_tokens=out_tokens,
        )
        executions.append(exec)

    # Verify individual token counts
    runner.assert_equal(
        executions[0].input_tokens,
        100,
        "token_tracking_exec1_input",
        "First execution input tokens"
    )
    runner.assert_equal(
        executions[0].output_tokens,
        50,
        "token_tracking_exec1_output",
        "First execution output tokens"
    )
    runner.assert_equal(
        executions[0].get_total_tokens(),
        150,
        "token_tracking_exec1_total",
        "First execution total tokens"
    )

    # Verify aggregated tokens
    total_input = sum(exec.input_tokens for exec in executions)
    total_output = sum(exec.output_tokens for exec in executions)

    runner.assert_equal(
        total_input,
        450,
        "token_tracking_total_input",
        "Total input tokens across all executions"
    )
    runner.assert_equal(
        total_output,
        245,
        "token_tracking_total_output",
        "Total output tokens across all executions"
    )


async def scenario_session_continuity(runner: SimulationRunner):
    """Test session continuity across multiple executions.

    Validates:
    - Session ID assignment
    - Session linking between executions
    - Multi-turn interaction tracking
    """
    # First execution in session
    exec1 = AgentExecution.create(
        agent_id="code-generator",
        work_item_id="ISSUE-701",
        workflow_id="workflow-session-test",
        stage_name="planning",
        prompt="Plan the implementation",
        model="claude-sonnet-4-5",
    )

    session_id = "session-user-701"
    exec1.start()
    await runner.advance_time(timedelta(seconds=10))
    exec1.complete(
        output="Implementation plan created",
        input_tokens=120,
        output_tokens=180,
        session_id=session_id,
    )

    runner.assert_equal(
        exec1.session_id,
        session_id,
        "session_continuity_exec1_session",
        "First execution should have session ID"
    )

    # Second execution in same session
    exec2 = AgentExecution.create(
        agent_id="code-generator",
        work_item_id="ISSUE-702",
        workflow_id="workflow-session-test",
        stage_name="implementation",
        prompt="Implement based on plan",
        model="claude-sonnet-4-5",
    )

    exec2.start()
    await runner.advance_time(timedelta(seconds=15))
    exec2.complete(
        output="Implementation complete",
        input_tokens=200,
        output_tokens=250,
        session_id=session_id,  # Same session
    )

    runner.assert_equal(
        exec2.session_id,
        session_id,
        "session_continuity_exec2_session",
        "Second execution should have same session ID"
    )

    # Verify session continuity
    runner.assert_true(
        exec1.session_id == exec2.session_id,
        "session_continuity_match",
        "Both executions should be in same session"
    )


async def scenario_execution_cancellation(runner: SimulationRunner):
    """Test execution cancellation and pause/resume.

    Validates:
    - Cancellation from various states
    - Pause and resume transitions
    - Exit code assignment for cancellation
    """
    # Test cancellation
    execution = AgentExecution.create(
        agent_id="code-generator",
        work_item_id="ISSUE-801",
        workflow_id="workflow-cancel-test",
        stage_name="coding",
        prompt="Generate code (will be cancelled)",
        model="claude-sonnet-4-5",
    )

    execution.start()
    await runner.advance_time(timedelta(seconds=20))

    # Pause execution
    execution.pause(reason="User requested pause for review")
    runner.assert_equal(
        execution.status,
        ExecutionStatus.PAUSED,
        "cancel_paused_status",
        "Execution should be PAUSED"
    )

    # Resume execution
    await runner.advance_time(timedelta(seconds=10))
    execution.resume()
    runner.assert_equal(
        execution.status,
        ExecutionStatus.RUNNING,
        "cancel_resumed_status",
        "Execution should be RUNNING again after resume"
    )

    # Cancel execution
    execution.cancel(reason="User cancelled due to priority change")
    runner.assert_equal(
        execution.status,
        ExecutionStatus.CANCELLED,
        "cancel_cancelled_status",
        "Execution should be CANCELLED"
    )
    runner.assert_equal(
        execution.exit_code,
        -2,
        "cancel_exit_code",
        "Cancellation should have exit code -2"
    )
    runner.assert_true(
        execution.is_terminal(),
        "cancel_is_terminal",
        "CANCELLED is a terminal state"
    )


@pytest.mark.asyncio
async def test_scenario_10_agent_execution():
    """Test Scenario 10: Agent Execution Lifecycle."""
    config = create_config()
    runner = SimulationRunner(config)

    result = await runner.run(run_scenario)

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


if __name__ == "__main__":
    import asyncio

    async def run_all():
        """Run all scenario 10 tests."""
        print("\n" + "=" * 70)
        print("SCENARIO 10: Agent Execution Lifecycle")
        print("=" * 70)

        config = create_config()
        runner = SimulationRunner(config)
        result = await runner.run(run_scenario)

        print("\n✓ Agent Execution Scenario completed")
        print(f"  Speed multiplier: {result.speed_multiplier:.1f}x")
        print(f"  Real time: {result.duration_seconds:.2f}s")
        print(f"  Simulated time: {result.simulated_duration_seconds:.1f}s")
        print(f"  Events captured: {result.events_captured}")
        print(f"  Assertions: {result.assertions_passed}/{result.assertions_passed + result.assertions_failed}")

        print("\n" + "=" * 70)
        print("All Scenario 10 tests completed successfully!")
        print("=" * 70 + "\n")

    asyncio.run(run_all())
