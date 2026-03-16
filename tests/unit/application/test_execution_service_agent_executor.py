"""Unit tests for ExecutionServiceAgentExecutor.

Tests the central simulation executor component that drives the full LLM → Container → VCS
execution chain. ExecutionServiceAgentExecutor is responsible for:
1. Looking up active workflow runs
2. Loading domain objects (Agent, WorkItem, ProjectConfig)
3. Building ProjectContext
4. Cloning repositories
5. Routing workspaces
6. Building execution context
7. Creating and executing via ExecutionService
8. Finalizing workspaces and calling completion callbacks
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codetoreum.adapters.testing.execution_service_agent_executor import (
    ExecutionServiceAgentExecutor,
)
from codetoreum.domain.agent import Agent
from codetoreum.domain.work_item import WorkItem
from codetoreum.ports.output.active_workflow_run_registry import ActiveRunInfo


class TestExecutionServiceAgentExecutorInitialization:
    """Test ExecutionServiceAgentExecutor initialization and configuration."""

    def test_executor_initializes_with_required_dependencies(self):
        """Test that executor initializes with all required port implementations."""
        execution_service = AsyncMock()
        workspace_router = AsyncMock()
        config_store = AsyncMock()
        agent_repository = AsyncMock()
        work_item_service = AsyncMock()
        run_registry = AsyncMock()
        branch_tracker = AsyncMock()
        vcs = AsyncMock()

        executor = ExecutionServiceAgentExecutor(
            execution_service=execution_service,
            workspace_router=workspace_router,
            config_store=config_store,
            agent_repository=agent_repository,
            work_item_service=work_item_service,
            run_registry=run_registry,
            branch_tracker=branch_tracker,
            vcs=vcs,
        )

        assert executor is not None
        assert executor._execution_service is execution_service
        assert executor._workspace_router is workspace_router
        assert executor._config_store is config_store

    def test_executor_initializes_with_optional_recovery_service(self):
        """Test that executor accepts optional recovery service."""
        dependencies = {
            "execution_service": AsyncMock(),
            "workspace_router": AsyncMock(),
            "config_store": AsyncMock(),
            "agent_repository": AsyncMock(),
            "work_item_service": AsyncMock(),
            "run_registry": AsyncMock(),
            "branch_tracker": AsyncMock(),
            "vcs": AsyncMock(),
        }

        recovery_service = AsyncMock()

        executor = ExecutionServiceAgentExecutor(
            recovery_service=recovery_service,
            **dependencies
        )

        assert executor._recovery_service is recovery_service

    def test_executor_initializes_with_execution_delay(self):
        """Test that executor accepts execution delay for testing."""
        dependencies = {
            "execution_service": AsyncMock(),
            "workspace_router": AsyncMock(),
            "config_store": AsyncMock(),
            "agent_repository": AsyncMock(),
            "work_item_service": AsyncMock(),
            "run_registry": AsyncMock(),
            "branch_tracker": AsyncMock(),
            "vcs": AsyncMock(),
        }

        executor = ExecutionServiceAgentExecutor(
            execution_delay=0.5,
            **dependencies
        )

        assert executor._execution_delay == 0.5

    def test_set_completion_handler_wires_callback(self):
        """Test that set_completion_handler correctly wires completion callback."""
        dependencies = {
            "execution_service": AsyncMock(),
            "workspace_router": AsyncMock(),
            "config_store": AsyncMock(),
            "agent_repository": AsyncMock(),
            "work_item_service": AsyncMock(),
            "run_registry": AsyncMock(),
            "branch_tracker": AsyncMock(),
            "vcs": AsyncMock(),
        }

        executor = ExecutionServiceAgentExecutor(**dependencies)

        callback = AsyncMock()
        executor.set_completion_handler(callback, "board-1")

        assert executor._completion_callback is callback
        assert executor._default_board_id == "board-1"


class TestExecutionServiceAgentExecutorExecution:
    """Test execution behavior (fire-and-forget pattern)."""

    @pytest.mark.asyncio
    async def test_execute_records_execution_and_schedules_task(self):
        """Test that execute() records execution data and schedules async task.

        The execute() method is fire-and-forget: it records the execution,
        schedules _run_execution as a background task, and returns immediately
        without waiting for completion.
        """
        dependencies = {
            "execution_service": AsyncMock(),
            "workspace_router": AsyncMock(),
            "config_store": AsyncMock(),
            "agent_repository": AsyncMock(),
            "work_item_service": AsyncMock(),
            "run_registry": AsyncMock(),
            "branch_tracker": AsyncMock(),
            "vcs": AsyncMock(),
        }

        executor = ExecutionServiceAgentExecutor(**dependencies)
        executor.set_completion_handler(AsyncMock(), "board-1")

        # Record active run
        run_info = ActiveRunInfo(
            run_id="run-1",
            work_item_id="item-1",
            project_id="project-1",
            stage_name="Ready",
        )
        executor._run_registry.get_active_run.return_value = run_info

        # Execute (should return immediately)
        await executor.execute("item-1", "architect")

        # Verify execution was recorded
        assert len(executor.executions) == 1
        execution = executor.executions[0]
        assert execution["work_item_id"] == "item-1"
        assert execution["agent_id"] == "architect"
        assert execution["board_id"] == "board-1"
        assert execution["workflow_id"] == "run-1"
        assert execution["stage_name"] == "Ready"

        # Clean up pending tasks
        for task in executor._pending_tasks:
            task.cancel()
        await asyncio.gather(*executor._pending_tasks, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_execute_uses_provided_board_id_when_given(self):
        """Test that execute() uses provided board_id instead of default."""
        dependencies = {
            "execution_service": AsyncMock(),
            "workspace_router": AsyncMock(),
            "config_store": AsyncMock(),
            "agent_repository": AsyncMock(),
            "work_item_service": AsyncMock(),
            "run_registry": AsyncMock(),
            "branch_tracker": AsyncMock(),
            "vcs": AsyncMock(),
        }

        executor = ExecutionServiceAgentExecutor(**dependencies)
        executor.set_completion_handler(AsyncMock(), "default-board")

        executor._run_registry.get_active_run.return_value = ActiveRunInfo(
            run_id="run-1",
            work_item_id="item-1",
            project_id="project-1",
            stage_name="Ready",
        )

        await executor.execute("item-1", "coder", board_id="custom-board")

        execution = executor.executions[0]
        assert execution["board_id"] == "custom-board"

        # Clean up
        for task in executor._pending_tasks:
            task.cancel()
        await asyncio.gather(*executor._pending_tasks, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_execute_handles_missing_active_run(self):
        """Test that execute() handles case where no active run exists.

        When active run is not found, it records 'unknown' for workflow/stage.
        """
        dependencies = {
            "execution_service": AsyncMock(),
            "workspace_router": AsyncMock(),
            "config_store": AsyncMock(),
            "agent_repository": AsyncMock(),
            "work_item_service": AsyncMock(),
            "run_registry": AsyncMock(),
            "branch_tracker": AsyncMock(),
            "vcs": AsyncMock(),
        }

        executor = ExecutionServiceAgentExecutor(**dependencies)
        executor.set_completion_handler(AsyncMock(), "board-1")

        # No active run
        executor._run_registry.get_active_run.return_value = None

        await executor.execute("item-1", "architect")

        execution = executor.executions[0]
        assert execution["workflow_id"] == "unknown"
        assert execution["stage_name"] == "unknown"

        # Clean up
        for task in executor._pending_tasks:
            task.cancel()
        await asyncio.gather(*executor._pending_tasks, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_execute_respects_execution_delay_for_testing(self):
        """Test that _run_execution respects execution_delay parameter.

        The delay is useful for simulation testing to allow events to settle.
        """
        dependencies = {
            "execution_service": AsyncMock(),
            "workspace_router": AsyncMock(),
            "config_store": AsyncMock(),
            "agent_repository": AsyncMock(),
            "work_item_service": AsyncMock(),
            "run_registry": AsyncMock(),
            "branch_tracker": AsyncMock(),
            "vcs": AsyncMock(),
        }

        executor = ExecutionServiceAgentExecutor(
            execution_delay=0.1,
            **dependencies
        )
        executor.set_completion_handler(AsyncMock(), "board-1")

        # Mock to fail early (no active run) to test delay is applied
        executor._run_registry.get_active_run.return_value = None

        start = datetime.now(UTC)
        await executor.execute("item-1", "architect")

        # Wait for task to complete
        pending_copy = list(executor._pending_tasks)
        for task in pending_copy:
            try:
                await task
            except Exception:
                pass

        elapsed = (datetime.now(UTC) - start).total_seconds()

        # Should have waited at least the delay time
        assert elapsed >= 0.1 - 0.05  # Allow 50ms tolerance

        # Clean up
        pending_copy = list(executor._pending_tasks)
        for task in pending_copy:
            task.cancel()
        await asyncio.gather(*executor._pending_tasks, return_exceptions=True)


class TestExecutionServiceAgentExecutorChainSteps:
    """Test individual steps in the execution chain (Step 1 - Step 11)."""

    @pytest.mark.asyncio
    async def test_run_execution_step1_active_run_lookup(self):
        """Test Step 1: Look up active run from registry."""
        dependencies = {
            "execution_service": AsyncMock(),
            "workspace_router": AsyncMock(),
            "config_store": AsyncMock(),
            "agent_repository": AsyncMock(),
            "work_item_service": AsyncMock(),
            "run_registry": AsyncMock(),
            "branch_tracker": AsyncMock(),
            "vcs": AsyncMock(),
        }

        executor = ExecutionServiceAgentExecutor(**dependencies)
        callback = AsyncMock()
        executor.set_completion_handler(callback, "board-1")

        # No active run - should complete callback with failure
        executor._run_registry.get_active_run.return_value = None

        await executor._run_execution("item-1", "architect", "board-1")

        # Verify completion callback was called with False (failure)
        callback.assert_called_once_with("item-1", "board-1", False)
        executor._run_registry.get_active_run.assert_called_once_with("item-1")

    @pytest.mark.asyncio
    async def test_run_execution_step2_agent_load_failure(self):
        """Test Step 2: Handle failure when loading agent."""
        dependencies = {
            "execution_service": AsyncMock(),
            "workspace_router": AsyncMock(),
            "config_store": AsyncMock(),
            "agent_repository": AsyncMock(),
            "work_item_service": AsyncMock(),
            "run_registry": AsyncMock(),
            "branch_tracker": AsyncMock(),
            "vcs": AsyncMock(),
        }

        executor = ExecutionServiceAgentExecutor(**dependencies)
        callback = AsyncMock()
        executor.set_completion_handler(callback, "board-1")

        # Setup active run
        run_info = ActiveRunInfo(
            run_id="run-1",
            work_item_id="item-1",
            project_id="project-1",
            stage_name="Ready",
        )
        executor._run_registry.get_active_run.return_value = run_info

        # Agent load fails
        executor._agent_repository.get_by_id.side_effect = Exception("Agent not found")

        await executor._run_execution("item-1", "architect", "board-1")

        # Verify completion callback called with False
        callback.assert_called_once_with("item-1", "board-1", False)

    @pytest.mark.asyncio
    async def test_run_execution_step3_work_item_load_failure(self):
        """Test Step 3: Handle failure when loading work item."""
        dependencies = {
            "execution_service": AsyncMock(),
            "workspace_router": AsyncMock(),
            "config_store": AsyncMock(),
            "agent_repository": AsyncMock(),
            "work_item_service": AsyncMock(),
            "run_registry": AsyncMock(),
            "branch_tracker": AsyncMock(),
            "vcs": AsyncMock(),
        }

        executor = ExecutionServiceAgentExecutor(**dependencies)
        callback = AsyncMock()
        executor.set_completion_handler(callback, "board-1")

        # Setup active run
        run_info = ActiveRunInfo(
            run_id="run-1",
            work_item_id="item-1",
            project_id="project-1",
            stage_name="Ready",
        )
        executor._run_registry.get_active_run.return_value = run_info

        # Agent loads successfully
        agent = MagicMock(spec=Agent)
        executor._agent_repository.get_by_id.return_value = agent

        # Work item load fails
        executor._work_item_service.get_work_item.side_effect = Exception(
            "Work item not found"
        )

        await executor._run_execution("item-1", "architect", "board-1")

        # Verify completion callback called with False
        callback.assert_called_once_with("item-1", "board-1", False)

    @pytest.mark.asyncio
    async def test_run_execution_step4_project_config_load_failure(self):
        """Test Step 4: Handle failure when loading project config."""
        dependencies = {
            "execution_service": AsyncMock(),
            "workspace_router": AsyncMock(),
            "config_store": AsyncMock(),
            "agent_repository": AsyncMock(),
            "work_item_service": AsyncMock(),
            "run_registry": AsyncMock(),
            "branch_tracker": AsyncMock(),
            "vcs": AsyncMock(),
        }

        executor = ExecutionServiceAgentExecutor(**dependencies)
        callback = AsyncMock()
        executor.set_completion_handler(callback, "board-1")

        # Setup active run
        run_info = ActiveRunInfo(
            run_id="run-1",
            work_item_id="item-1",
            project_id="project-1",
            stage_name="Ready",
        )
        executor._run_registry.get_active_run.return_value = run_info

        # Agent and work item load successfully
        agent = MagicMock(spec=Agent)
        executor._agent_repository.get_by_id.return_value = agent

        work_item = MagicMock(spec=WorkItem)
        executor._work_item_service.get_work_item.return_value = work_item

        # Project config load fails
        executor._config_store.get_project_config.side_effect = Exception(
            "Config not found"
        )

        await executor._run_execution("item-1", "architect", "board-1")

        # Verify completion callback called with False
        callback.assert_called_once_with("item-1", "board-1", False)


class TestExecutionServiceAgentExecutorCompletion:
    """Test completion callback handling."""

    @pytest.mark.asyncio
    async def test_completion_callback_not_called_if_not_set(self):
        """Test that missing completion callback doesn't crash executor."""
        dependencies = {
            "execution_service": AsyncMock(),
            "workspace_router": AsyncMock(),
            "config_store": AsyncMock(),
            "agent_repository": AsyncMock(),
            "work_item_service": AsyncMock(),
            "run_registry": AsyncMock(),
            "branch_tracker": AsyncMock(),
            "vcs": AsyncMock(),
        }

        executor = ExecutionServiceAgentExecutor(**dependencies)
        # Don't call set_completion_handler

        executor._run_registry.get_active_run.return_value = None

        # Should not raise
        await executor._run_execution("item-1", "architect", "board-1")

    @pytest.mark.asyncio
    async def test_pending_tasks_cleanup_on_completion(self):
        """Test that completed tasks are properly cleaned up from _pending_tasks."""
        dependencies = {
            "execution_service": AsyncMock(),
            "workspace_router": AsyncMock(),
            "config_store": AsyncMock(),
            "agent_repository": AsyncMock(),
            "work_item_service": AsyncMock(),
            "run_registry": AsyncMock(),
            "branch_tracker": AsyncMock(),
            "vcs": AsyncMock(),
        }

        executor = ExecutionServiceAgentExecutor(**dependencies)
        executor.set_completion_handler(AsyncMock(), "board-1")

        executor._run_registry.get_active_run.return_value = None

        # Execute and wait for task
        await executor.execute("item-1", "architect")

        # Task should be in pending set
        assert len(executor._pending_tasks) > 0

        # Wait for tasks to complete
        for task in executor._pending_tasks.copy():
            try:
                await task
            except Exception:
                pass

        # After a brief moment, tasks should be cleaned up (done callback)
        await asyncio.sleep(0.01)

        # All tasks should be cleaned (done callback removes them)
        pending_count = len([t for t in executor._pending_tasks if not t.done()])
        assert pending_count == 0


class TestExecutionServiceAgentExecutorMultipleExecutions:
    """Test behavior with multiple concurrent executions."""

    @pytest.mark.asyncio
    async def test_multiple_executions_recorded_separately(self):
        """Test that multiple executions are recorded as separate entries."""
        dependencies = {
            "execution_service": AsyncMock(),
            "workspace_router": AsyncMock(),
            "config_store": AsyncMock(),
            "agent_repository": AsyncMock(),
            "work_item_service": AsyncMock(),
            "run_registry": AsyncMock(),
            "branch_tracker": AsyncMock(),
            "vcs": AsyncMock(),
        }

        executor = ExecutionServiceAgentExecutor(**dependencies)
        executor.set_completion_handler(AsyncMock(), "board-1")

        executor._run_registry.get_active_run.return_value = ActiveRunInfo(
            run_id="run-1",
            work_item_id="item-1",
            project_id="project-1",
            stage_name="Ready",
        )

        # Execute multiple times
        await executor.execute("item-1", "architect")
        await executor.execute("item-1", "coder")
        await executor.execute("item-2", "architect")

        # All executions should be recorded
        assert len(executor.executions) == 3
        assert executor.executions[0]["agent_id"] == "architect"
        assert executor.executions[1]["agent_id"] == "coder"
        assert executor.executions[2]["work_item_id"] == "item-2"

        # Clean up
        for task in executor._pending_tasks:
            task.cancel()
        await asyncio.gather(*executor._pending_tasks, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_executions_property_returns_copy(self):
        """Test that executions property returns a copy, not mutable reference."""
        dependencies = {
            "execution_service": AsyncMock(),
            "workspace_router": AsyncMock(),
            "config_store": AsyncMock(),
            "agent_repository": AsyncMock(),
            "work_item_service": AsyncMock(),
            "run_registry": AsyncMock(),
            "branch_tracker": AsyncMock(),
            "vcs": AsyncMock(),
        }

        executor = ExecutionServiceAgentExecutor(**dependencies)
        executor.set_completion_handler(AsyncMock(), "board-1")

        executor._run_registry.get_active_run.return_value = ActiveRunInfo(
            run_id="run-1",
            work_item_id="item-1",
            project_id="project-1",
            stage_name="Ready",
        )

        await executor.execute("item-1", "architect")

        # Get executions list
        exec_list_1 = executor.executions
        exec_count_before = len(exec_list_1)

        # Execute again
        await executor.execute("item-1", "coder")

        # Previous list should not be modified
        assert len(exec_list_1) == exec_count_before

        # New list should have new execution
        exec_list_2 = executor.executions
        assert len(exec_list_2) == exec_count_before + 1

        # Clean up
        for task in executor._pending_tasks:
            task.cancel()
        await asyncio.gather(*executor._pending_tasks, return_exceptions=True)
