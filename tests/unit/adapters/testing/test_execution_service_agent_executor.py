"""Unit tests for ExecutionServiceAgentExecutor failure paths.

Verifies that every failure mode in _run_execution:
1. Calls the completion callback exactly once with success=False
2. Does NOT call the completion callback with success=True
3. Cleans up registry/branch-tracker on failure (via the finally block)
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.adapters.testing.execution_service_agent_executor import (
    ExecutionServiceAgentExecutor,
)
from codetoreum.domain.agent import AgentType
from codetoreum.domain.events import AgentExecutionCompletedEvent
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.output.active_workflow_run_registry import ActiveRunInfo

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


class ExecutorFixture:
    """All I/O deps pre-wired to a passing happy path; override per test."""

    WORK_ITEM_ID = "wi-1"
    AGENT_ID = "agent-1"
    BOARD_ID = "board-1"

    @staticmethod
    def make_agent_mock(requires_docker=False, **overrides):
        """Create a properly configured agent mock for testing.

        D6: also populates ``agent.invocation`` (an AgentInvocationConfig)
        derived from ``requires_docker`` so the executor's
        ``_build_invocation_options`` reads the new schema directly.
        """
        from codetoreum.domain.coding_agent_types import (
            AgentInvocationConfig,
            InvocationMode,
        )

        agent = MagicMock()
        agent.id = "agent-1"
        agent.name = "test-agent"
        agent.display_name = "Test Agent"
        agent.agent_type = AgentType.DEVELOPER
        agent.role_description = "A test agent for testing"
        agent.system_prompt = "You are a test agent"
        agent.max_retries = 3
        agent.requires_dev_container = False
        agent.makes_code_changes = False
        agent.filesystem_write_allowed = False
        agent.mcp_servers = []
        agent.capabilities = {}
        agent.coding_agent = "claude-code"
        # DEF-020: invocation block is the sole source of truth for
        # mode / model / timeout (flat fields removed).
        agent.invocation = AgentInvocationConfig(
            mode=(InvocationMode.CONTAINERIZED if requires_docker else InvocationMode.HOST),
            model="claude-opus-4-7",
            timeout_seconds=60,
            mode_config=({"image": "codetoreum-agent:latest"} if requires_docker else {}),
        )
        # Apply any overrides
        for key, value in overrides.items():
            setattr(agent, key, value)
        return agent

    def __init__(self) -> None:
        self.run_registry = AsyncMock()
        self.agent_repository = AsyncMock()
        self.work_item_service = AsyncMock()
        self.config_store = AsyncMock()
        self.vcs = AsyncMock()
        self.workspace_router = AsyncMock()
        self.branch_tracker = AsyncMock()
        self.execution_service = AsyncMock()
        # The executor publishes AgentExecutionCompletedEvent on the event bus
        # when it finishes processing a work item. To preserve existing
        # assertion shape (`completion_callback.assert_called_once_with(...)`),
        # we subscribe a small bridge that translates the event back into the
        # legacy (work_item_id, board_id, success) triple.
        self.event_bus = EventBus(max_retries=0, retry_delay_seconds=0.0)
        self.completion_callback = AsyncMock()

        async def _bridge(event: AgentExecutionCompletedEvent) -> None:
            await self.completion_callback(event.work_item_id, event.board_id, event.success)

        self.event_bus.subscribe("AgentExecutionCompletedEvent", _bridge)
        self.clock = SimulationClock()

        # Happy-path defaults ---
        self.run_info = ActiveRunInfo(
            work_item_id=self.WORK_ITEM_ID,
            run_id="run-1",
            stage_name="coding",
            project_id="proj-1",
            board_id=self.BOARD_ID,
            started_at=datetime.now(UTC).isoformat(),
        )
        self.run_registry.get_active_run.return_value = self.run_info

        agent = ExecutorFixture.make_agent_mock()
        self.agent_repository.get_by_id.return_value = agent

        work_item = MagicMock()
        work_item.id = "wi-1"
        work_item.title = "Test work item"
        work_item.description = "A test work item"
        work_item.status = MagicMock(value="new")
        work_item.priority = MagicMock(value=2)
        work_item.labels = []
        work_item.external_url = None
        work_item.assigned_agent_id = None
        self.work_item_service.get_work_item.return_value = work_item

        project_config = MagicMock()
        project_config.id = "proj-1"
        project_config.name = "test-project"
        project_config.github_org = "test-org"
        project_config.github_repo = "test-repo"
        project_config.tech_stacks = {}
        project_config.testing = {}
        project_config.environment_variables = {}
        project_config.created_at = None
        project_config.updated_at = None
        self.config_store.get_project_config.return_value = project_config

        workspace = MagicMock()
        workspace.work_item_id = "wi-1"
        workspace.project_id = "proj-1"
        workspace.branch_name = "feature/issue-1-test"
        self.workspace_router.route_workspace.return_value = workspace

        prep_result = MagicMock()
        prep_result.success = True
        # D-I: prepare_workspace now publishes the resolved branch back on
        # workspace_context. Reuse the routed workspace so downstream
        # ExecutionContextBuilder sees consistent IDs and the branch_name
        # that was actually checked out.
        prep_result.workspace_context = workspace
        self.workspace_router.prepare_workspace.return_value = prep_result

        execution = MagicMock()
        self.execution_service.create_execution.return_value = execution

        start_result = MagicMock()
        start_result.success = True
        self.execution_service.start_execution.return_value = start_result

        exec_result = MagicMock()
        exec_result.success = True
        exec_result.execution = MagicMock(output="done")
        # D4: executor dispatches via ExecutionService.execute() — the new
        # unified entry point that internally delegates to ICodingAgent.
        self.execution_service.execute.return_value = exec_result

    def make_executor(self, recovery_service=None) -> ExecutionServiceAgentExecutor:
        return ExecutionServiceAgentExecutor(
            execution_service=self.execution_service,
            workspace_router=self.workspace_router,
            config_store=self.config_store,
            agent_repository=self.agent_repository,
            work_item_service=self.work_item_service,
            run_registry=self.run_registry,
            branch_tracker=self.branch_tracker,
            vcs=self.vcs,
            clock=self.clock,
            event_bus=self.event_bus,
            recovery_service=recovery_service,
            default_board_id=self.BOARD_ID,
        )

    async def drain_pending(self, executor: ExecutionServiceAgentExecutor, deadline_s: float = 1.0) -> None:
        """Await every task the executor scheduled in `_pending_tasks`.

        `_call_completion` now schedules the AgentExecutionCompletedEvent publish as
        a fire-and-forget task so the executor's outer task can complete (and clear
        its `_executing_work_items` membership) before the BEH handler runs. Tests
        that assert against the completion bridge need to wait until that task has
        finished. We snapshot the set, await each task with a deadline, and repeat
        until no new tasks appear (recovery cascades).
        """
        loop_count = 0
        while executor._pending_tasks and loop_count < 20:
            snapshot = list(executor._pending_tasks)
            for t in snapshot:
                try:
                    await asyncio.wait_for(asyncio.shield(t), timeout=deadline_s)
                except (TimeoutError, asyncio.CancelledError):
                    pass
                except Exception:
                    # Exceptions are surfaced via done-callbacks; tests assert on side effects.
                    pass
            loop_count += 1


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestExecutionServiceAgentExecutorHappyPath:
    @pytest.mark.asyncio
    async def test_happy_path_calls_completion_with_success(self):
        """Full chain completes; callback called once with success=True."""
        fx = ExecutorFixture()
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        await fx.drain_pending(executor)

        await fx.drain_pending(executor)

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, True)
        fx.run_registry.clear_run.assert_called_once_with(fx.WORK_ITEM_ID)
        fx.branch_tracker.clear.assert_called_once_with(fx.WORK_ITEM_ID)


# ---------------------------------------------------------------------------
# Failure paths — one test per error site
# ---------------------------------------------------------------------------


class TestExecutionServiceAgentExecutorFailurePaths:
    @pytest.mark.asyncio
    async def test_no_active_run_calls_completion_with_failure(self):
        """Step 1: get_active_run returns None → completion called with False."""
        fx = ExecutorFixture()
        fx.run_registry.get_active_run.return_value = None
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        await fx.drain_pending(executor)

        await fx.drain_pending(executor)

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)
        fx.execution_service.create_execution.assert_not_called()

    @pytest.mark.asyncio
    async def test_agent_load_failure_calls_completion_with_failure(self):
        """Step 2: agent_repository.get_by_id raises → completion called with False."""
        fx = ExecutorFixture()
        fx.agent_repository.get_by_id.side_effect = RuntimeError("agent not found")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        await fx.drain_pending(executor)

        await fx.drain_pending(executor)

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)
        fx.work_item_service.get_work_item.assert_not_called()

    @pytest.mark.asyncio
    async def test_work_item_load_failure_calls_completion_with_failure(self):
        """Step 2: work_item_service.get_work_item raises → completion called with False."""
        fx = ExecutorFixture()
        fx.work_item_service.get_work_item.side_effect = RuntimeError("work item not found")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        await fx.drain_pending(executor)

        await fx.drain_pending(executor)

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)
        fx.config_store.get_project_config.assert_not_called()

    @pytest.mark.asyncio
    async def test_project_config_load_failure_calls_completion_with_failure(self):
        """Step 2: config_store.get_project_config raises → completion called with False."""
        fx = ExecutorFixture()
        fx.config_store.get_project_config.side_effect = RuntimeError("config not found")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        await fx.drain_pending(executor)

        await fx.drain_pending(executor)

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)
        fx.workspace_router.route_workspace.assert_not_called()

    @pytest.mark.asyncio
    async def test_vcs_clone_failure_calls_completion_with_failure(self):
        """Step 3: vcs.clone_repository raises → completion called with False."""
        fx = ExecutorFixture()
        fx.vcs.clone_repository.side_effect = RuntimeError("clone failed")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        await fx.drain_pending(executor)

        await fx.drain_pending(executor)

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)
        fx.workspace_router.route_workspace.assert_not_called()

    @pytest.mark.asyncio
    async def test_workspace_route_failure_calls_completion_with_failure(self):
        """Step 4: workspace_router.route_workspace raises → completion called with False."""
        fx = ExecutorFixture()
        fx.workspace_router.route_workspace.side_effect = RuntimeError("routing failed")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        await fx.drain_pending(executor)

        await fx.drain_pending(executor)

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)
        fx.branch_tracker.set_branch.assert_not_called()

    @pytest.mark.asyncio
    async def test_branch_tracker_failure_calls_completion_with_failure(self):
        """Step 5: branch_tracker.set_branch raises → completion called with False."""
        fx = ExecutorFixture()
        fx.branch_tracker.set_branch.side_effect = RuntimeError("tracker failed")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        await fx.drain_pending(executor)

        await fx.drain_pending(executor)

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)
        fx.workspace_router.prepare_workspace.assert_not_called()

    @pytest.mark.asyncio
    async def test_workspace_prepare_failure_calls_completion_with_failure(self):
        """Step 6: prepare_workspace returns success=False → completion called with False."""
        fx = ExecutorFixture()
        prep_result = MagicMock()
        prep_result.success = False
        prep_result.reason = "disk full"
        fx.workspace_router.prepare_workspace.return_value = prep_result
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        await fx.drain_pending(executor)

        await fx.drain_pending(executor)

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)
        fx.execution_service.create_execution.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_execution_failure_finalizes_workspace_then_calls_completion(self):
        """Step 8: create_execution raises → finalize_workspace called, completion=False."""
        fx = ExecutorFixture()
        fx.execution_service.create_execution.side_effect = RuntimeError("db error")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        await fx.drain_pending(executor)

        await fx.drain_pending(executor)

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)
        # finalize_workspace must have been called with success=False
        fx.workspace_router.finalize_workspace.assert_called_once()
        call_args = fx.workspace_router.finalize_workspace.call_args
        assert call_args.args[2] == {"success": False}

    @pytest.mark.asyncio
    async def test_start_execution_failure_calls_completion_with_failure(self):
        """Step 9: start_execution returns success=False → finalize_workspace called, completion=False."""
        fx = ExecutorFixture()
        start_result = MagicMock()
        start_result.success = False
        start_result.error = "startup error"
        fx.execution_service.start_execution.return_value = start_result
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        await fx.drain_pending(executor)

        await fx.drain_pending(executor)

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)
        fx.execution_service.execute.assert_not_called()
        # finalize_workspace must also be called with success=False (mirrors create_execution failure path)
        fx.workspace_router.finalize_workspace.assert_called_once()
        call_args = fx.workspace_router.finalize_workspace.call_args
        assert call_args.args[2] == {"success": False}

    @pytest.mark.asyncio
    async def test_unexpected_exception_calls_completion_with_failure(self):
        """Outer try/except: unexpected exception → completion called with False."""
        fx = ExecutorFixture()
        fx.execution_service.execute.side_effect = RuntimeError("unexpected crash")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        await fx.drain_pending(executor)

        await fx.drain_pending(executor)

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)

    @pytest.mark.asyncio
    async def test_execute_soft_failure_calls_completion_with_false(self):
        """Step 10: ExecutionService.execute() returns success=False → callback called with False."""
        fx = ExecutorFixture()
        exec_result = MagicMock()
        exec_result.success = False
        exec_result.execution = MagicMock(output="")
        fx.execution_service.execute.return_value = exec_result
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        await fx.drain_pending(executor)

        await fx.drain_pending(executor)

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)

    @pytest.mark.asyncio
    async def test_execute_soft_failure_finalizes_workspace_with_false(self):
        """Step 10: ExecutionService.execute() returns success=False → finalize_workspace called with success=False."""
        fx = ExecutorFixture()
        exec_result = MagicMock()
        exec_result.success = False
        exec_result.execution = MagicMock(output="")
        fx.execution_service.execute.return_value = exec_result
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        await fx.drain_pending(executor)

        await fx.drain_pending(executor)

        fx.workspace_router.finalize_workspace.assert_called_once()
        call_args = fx.workspace_router.finalize_workspace.call_args
        assert call_args.args[2]["success"] is False

    @pytest.mark.asyncio
    async def test_execute_soft_failure_no_double_clear(self):
        """Step 10: soft failure cleans up registry/branch-tracker exactly once (via finally)."""
        fx = ExecutorFixture()
        exec_result = MagicMock()
        exec_result.success = False
        exec_result.execution = MagicMock(output="")
        fx.execution_service.execute.return_value = exec_result
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        await fx.drain_pending(executor)

        await fx.drain_pending(executor)

        fx.run_registry.clear_run.assert_called_once_with(fx.WORK_ITEM_ID)
        fx.branch_tracker.clear.assert_called_once_with(fx.WORK_ITEM_ID)


# ---------------------------------------------------------------------------
# Completion callback guard — exactly one call per execution
# ---------------------------------------------------------------------------


class TestCompletionCallbackCalledExactlyOnce:
    @pytest.mark.asyncio
    async def test_happy_path_exactly_one_call(self):
        fx = ExecutorFixture()
        executor = fx.make_executor()
        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)
        await fx.drain_pending(executor)
        await fx.drain_pending(executor)
        assert fx.completion_callback.call_count == 1

    @pytest.mark.asyncio
    async def test_early_failure_exactly_one_call(self):
        fx = ExecutorFixture()
        fx.run_registry.get_active_run.return_value = None
        executor = fx.make_executor()
        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)
        await fx.drain_pending(executor)
        await fx.drain_pending(executor)
        assert fx.completion_callback.call_count == 1

    @pytest.mark.asyncio
    async def test_mid_chain_failure_exactly_one_call(self):
        fx = ExecutorFixture()
        fx.execution_service.create_execution.side_effect = RuntimeError("fail")
        executor = fx.make_executor()
        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)
        await fx.drain_pending(executor)
        await fx.drain_pending(executor)
        assert fx.completion_callback.call_count == 1


# ---------------------------------------------------------------------------
# execute() public method
# ---------------------------------------------------------------------------


class TestExecutePublicMethod:
    @pytest.mark.asyncio
    async def test_execute_records_execution_metadata(self):
        """execute() records metadata before scheduling the background task."""
        fx = ExecutorFixture()
        executor = fx.make_executor()

        await executor.execute(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        assert len(executor.executions) == 1
        rec = executor.executions[0]
        assert rec["work_item_id"] == fx.WORK_ITEM_ID
        assert rec["agent_id"] == fx.AGENT_ID
        assert rec["board_id"] == fx.BOARD_ID
        assert "started_at" in rec


# ---------------------------------------------------------------------------
# Docker path
# ---------------------------------------------------------------------------


class TestDockerExecutionPath:
    @pytest.mark.asyncio
    async def test_docker_agent_dispatches_with_containerized_invocation_mode(self):
        """Agent with requires_docker=True dispatches via ExecutionService.execute()
        with InvocationMode.CONTAINERIZED options.

        Per Phase D4, the executor no longer branches on `requires_docker` to
        choose between container and LLM call sites. It always calls
        ExecutionService.execute() and uses `_build_invocation_options` to
        derive the InvocationMode from the agent — the coding-agent adapter
        then owns the dispatch decision inside execute().
        """
        from codetoreum.ports.output.coding_agent import (
            CodingAgentInvocationOptions,
            InvocationMode,
        )

        fx = ExecutorFixture()
        agent = ExecutorFixture.make_agent_mock(requires_docker=True)
        fx.agent_repository.get_by_id.return_value = agent

        container_result = MagicMock()
        container_result.success = True
        container_result.execution = MagicMock(output="done")
        fx.execution_service.execute.return_value = container_result

        executor = fx.make_executor()
        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)
        await fx.drain_pending(executor)
        await fx.drain_pending(executor)

        fx.execution_service.execute.assert_called_once()
        call_args = fx.execution_service.execute.call_args
        # ExecutionService.execute(execution, context, workspace, options)
        options = call_args.args[3]
        assert isinstance(options, CodingAgentInvocationOptions)
        assert options.invocation_mode == InvocationMode.CONTAINERIZED
        assert options.mode_config.get("image") == "codetoreum-agent:latest"
        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, True)


# ---------------------------------------------------------------------------
# Completion callback failure recovery
# ---------------------------------------------------------------------------


class TestCompletionCallbackFailureRecovery:
    @pytest.mark.asyncio
    async def test_completion_callback_failure_invokes_recovery_service(self):
        """When event_bus.publish itself raises, recovery service is invoked.

        Under the event-bus mechanism, individual subscriber failures are
        caught by the bus dispatch loop and logged; they do not propagate
        to publish(). The executor's recovery_service hook now fires only
        when the publish call itself fails (e.g., Redis persistence error
        or EventBusError during dispatch setup). Handler-level recovery is
        BoardColumnEventHandler's responsibility, not the executor's.
        """
        from codetoreum.application.agent_execution_recovery_service import (
            AgentExecutionRecoveryService,
        )

        fx = ExecutorFixture()
        recovery_service = AsyncMock(spec=AgentExecutionRecoveryService)

        # Replace event_bus.publish to simulate a transport-level publish failure
        fx.event_bus.publish = AsyncMock(side_effect=RuntimeError("Publish failed"))

        executor = fx.make_executor(recovery_service=recovery_service)

        # Act
        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)
        await fx.drain_pending(executor)
        await fx.drain_pending(executor)

        # Assert: Recovery service invoked to handle the publish failure
        assert recovery_service.handle_completion_callback_failure.called
        call_args = recovery_service.handle_completion_callback_failure.call_args
        assert call_args.kwargs["work_item_id"] == fx.WORK_ITEM_ID
        assert call_args.kwargs["board_id"] == fx.BOARD_ID
        assert call_args.kwargs["success"] is True

    @pytest.mark.asyncio
    async def test_completion_callback_failure_without_recovery_service(self):
        """When no recovery service, a publish failure is just logged."""
        fx = ExecutorFixture()
        fx.event_bus.publish = AsyncMock(side_effect=RuntimeError("Publish failed"))

        executor = fx.make_executor(recovery_service=None)

        # Act (should not raise)
        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)
        await fx.drain_pending(executor)
        await fx.drain_pending(executor)

        # Assert: Just logged, cleanup still happens
        assert fx.run_registry.clear_run.called
        assert fx.branch_tracker.clear.called


# ---------------------------------------------------------------------------
# CancelledError handling — critical async task cancellation path
# ---------------------------------------------------------------------------


class TestCancelledErrorHandling:
    @pytest.mark.asyncio
    async def test_cancelled_error_calls_completion_with_failure_and_reraises(self):
        """When asyncio.CancelledError is raised during execution, it should:
        1. Call completion callback with success=False
        2. Re-raise the CancelledError (so asyncio task machinery works correctly)

        This is a critical path: if the re-raise is accidentally removed,
        async task cancellation silently breaks and tasks don't clean up properly.
        """
        fx = ExecutorFixture()
        # Simulate a point where CancelledError is raised
        # For example, during asyncio.sleep in execution delay or during execution
        fx.execution_service.execute.side_effect = asyncio.CancelledError()
        executor = fx.make_executor()

        # Act & Assert: CancelledError should be re-raised after cleanup
        with pytest.raises(asyncio.CancelledError):
            await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)
            await fx.drain_pending(executor)

        # Drain after the raise so the publish task fires before assertions
        await fx.drain_pending(executor)

        # Assert: Completion callback was called with success=False
        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)

        # Assert: Cleanup still happens despite re-raise (via finally)
        fx.run_registry.clear_run.assert_called_once_with(fx.WORK_ITEM_ID)
        fx.branch_tracker.clear.assert_called_once_with(fx.WORK_ITEM_ID)

    @pytest.mark.asyncio
    async def test_task_done_callback_suppresses_cancelled_error(self):
        """The _task_done_callback suppresses CancelledError and cleans up _pending_tasks.

        This tests the actual task callback mechanism (lines 115-132 in source) used by
        execute() for fire-and-forget tasks. CancelledError should be suppressed during
        shutdown, and _pending_tasks must be cleaned up even on cancellation.
        """
        fx = ExecutorFixture()
        executor = fx.make_executor()

        # Create a task that will be cancelled
        task = asyncio.create_task(executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID))
        # Add task to _pending_tasks as execute() does (line 183 in source)
        executor._pending_tasks.add(task)

        await asyncio.sleep(0.01)  # Let it start
        task.cancel()
        await asyncio.sleep(0.01)  # Let cancellation propagate

        # Act: Invoke _task_done_callback directly (as task.add_done_callback does)
        # This should NOT raise an exception even though task.result() will raise CancelledError
        exception_raised = False
        try:
            executor._task_done_callback(task)
        except Exception:
            exception_raised = True

        # Assert: No exception should propagate from the callback
        assert not exception_raised, "_task_done_callback should suppress CancelledError"

        # Assert: Task was removed from pending set despite cancellation
        assert task not in executor._pending_tasks, "Cancelled task should be removed from _pending_tasks"
