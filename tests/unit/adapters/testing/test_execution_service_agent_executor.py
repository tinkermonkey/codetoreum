"""Unit tests for ExecutionServiceAgentExecutor failure paths.

Verifies that every failure mode in _run_execution:
1. Calls the completion callback exactly once with success=False
2. Does NOT call the completion callback with success=True
3. Cleans up registry/branch-tracker on failure (via the finally block)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.adapters.testing.execution_service_agent_executor import (
    ExecutionServiceAgentExecutor,
)
from codetoreum.ports.output.active_workflow_run_registry import ActiveRunInfo

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


class ExecutorFixture:
    """All I/O deps pre-wired to a passing happy path; override per test."""

    WORK_ITEM_ID = "wi-1"
    AGENT_ID = "agent-1"
    BOARD_ID = "board-1"

    def __init__(self) -> None:
        self.run_registry = AsyncMock()
        self.agent_repository = AsyncMock()
        self.work_item_service = AsyncMock()
        self.config_store = AsyncMock()
        self.vcs = AsyncMock()
        self.workspace_router = AsyncMock()
        self.branch_tracker = AsyncMock()
        self.execution_service = AsyncMock()
        self.completion_callback = AsyncMock()

        # Happy-path defaults ---
        self.run_info = ActiveRunInfo(
            work_item_id=self.WORK_ITEM_ID,
            run_id="run-1",
            stage_name="coding",
            project_id="proj-1",
        )
        self.run_registry.get_active_run.return_value = self.run_info

        agent = MagicMock()
        agent.id = "agent-1"
        agent.requires_docker = False
        agent.requires_dev_container = False
        agent.timeout_seconds = 60
        agent.mcp_servers = []
        self.agent_repository.get_by_id.return_value = agent

        work_item = MagicMock()
        work_item.id = "wi-1"
        work_item.title = "Test work item"
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
        self.workspace_router.prepare_workspace.return_value = prep_result

        execution = MagicMock()
        self.execution_service.create_execution.return_value = execution

        start_result = MagicMock()
        start_result.success = True
        self.execution_service.start_execution.return_value = start_result

        exec_result = MagicMock()
        exec_result.success = True
        exec_result.execution = MagicMock(output="done")
        self.execution_service.execute_with_llm.return_value = exec_result

    def make_executor(self) -> ExecutionServiceAgentExecutor:
        executor = ExecutionServiceAgentExecutor(
            execution_service=self.execution_service,
            workspace_router=self.workspace_router,
            config_store=self.config_store,
            agent_repository=self.agent_repository,
            work_item_service=self.work_item_service,
            run_registry=self.run_registry,
            branch_tracker=self.branch_tracker,
            vcs=self.vcs,
        )
        executor.set_completion_handler(self.completion_callback, self.BOARD_ID)
        return executor


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

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)
        fx.execution_service.create_execution.assert_not_called()

    @pytest.mark.asyncio
    async def test_agent_load_failure_calls_completion_with_failure(self):
        """Step 2: agent_repository.get_by_id raises → completion called with False."""
        fx = ExecutorFixture()
        fx.agent_repository.get_by_id.side_effect = RuntimeError("agent not found")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)
        fx.work_item_service.get_work_item.assert_not_called()

    @pytest.mark.asyncio
    async def test_work_item_load_failure_calls_completion_with_failure(self):
        """Step 2: work_item_service.get_work_item raises → completion called with False."""
        fx = ExecutorFixture()
        fx.work_item_service.get_work_item.side_effect = RuntimeError("work item not found")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)
        fx.config_store.get_project_config.assert_not_called()

    @pytest.mark.asyncio
    async def test_project_config_load_failure_calls_completion_with_failure(self):
        """Step 2: config_store.get_project_config raises → completion called with False."""
        fx = ExecutorFixture()
        fx.config_store.get_project_config.side_effect = RuntimeError("config not found")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)
        fx.workspace_router.route_workspace.assert_not_called()

    @pytest.mark.asyncio
    async def test_workspace_route_failure_calls_completion_with_failure(self):
        """Step 4: workspace_router.route_workspace raises → completion called with False."""
        fx = ExecutorFixture()
        fx.workspace_router.route_workspace.side_effect = RuntimeError("routing failed")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)
        fx.branch_tracker.set_branch.assert_not_called()

    @pytest.mark.asyncio
    async def test_branch_tracker_failure_calls_completion_with_failure(self):
        """Step 5: branch_tracker.set_branch raises → completion called with False."""
        fx = ExecutorFixture()
        fx.branch_tracker.set_branch.side_effect = RuntimeError("tracker failed")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

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

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)
        fx.execution_service.create_execution.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_execution_failure_finalizes_workspace_then_calls_completion(self):
        """Step 8: create_execution raises → finalize_workspace called, completion=False."""
        fx = ExecutorFixture()
        fx.execution_service.create_execution.side_effect = RuntimeError("db error")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)
        # finalize_workspace must have been called with success=False
        fx.workspace_router.finalize_workspace.assert_called_once()
        call_args = fx.workspace_router.finalize_workspace.call_args
        assert call_args.args[2] == {"success": False}

    @pytest.mark.asyncio
    async def test_start_execution_failure_calls_completion_with_failure(self):
        """Step 9: start_execution returns success=False → completion called with False."""
        fx = ExecutorFixture()
        start_result = MagicMock()
        start_result.success = False
        start_result.error = "startup error"
        fx.execution_service.start_execution.return_value = start_result
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)
        fx.execution_service.execute_with_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_unexpected_exception_calls_completion_with_failure(self):
        """Outer try/except: unexpected exception → completion called with False."""
        fx = ExecutorFixture()
        fx.execution_service.execute_with_llm.side_effect = RuntimeError("unexpected crash")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)


# ---------------------------------------------------------------------------
# Completion callback guard — exactly one call per execution
# ---------------------------------------------------------------------------


class TestCompletionCallbackCalledExactlyOnce:
    @pytest.mark.asyncio
    async def test_happy_path_exactly_one_call(self):
        fx = ExecutorFixture()
        executor = fx.make_executor()
        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)
        assert fx.completion_callback.call_count == 1

    @pytest.mark.asyncio
    async def test_early_failure_exactly_one_call(self):
        fx = ExecutorFixture()
        fx.run_registry.get_active_run.return_value = None
        executor = fx.make_executor()
        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)
        assert fx.completion_callback.call_count == 1

    @pytest.mark.asyncio
    async def test_mid_chain_failure_exactly_one_call(self):
        fx = ExecutorFixture()
        fx.execution_service.create_execution.side_effect = RuntimeError("fail")
        executor = fx.make_executor()
        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)
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
    async def test_docker_path_uses_execute_with_container(self):
        """Agent with requires_docker=True routes to execute_with_container."""
        fx = ExecutorFixture()
        agent = MagicMock()
        agent.id = "agent-1"
        agent.requires_docker = True
        agent.requires_dev_container = False
        agent.timeout_seconds = 60
        agent.mcp_servers = []
        fx.agent_repository.get_by_id.return_value = agent

        container_result = MagicMock()
        container_result.success = True
        container_result.execution = MagicMock(output="done")
        fx.execution_service.execute_with_container.return_value = container_result

        executor = fx.make_executor()
        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        fx.execution_service.execute_with_container.assert_called_once()
        fx.execution_service.execute_with_llm.assert_not_called()
        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, True)
