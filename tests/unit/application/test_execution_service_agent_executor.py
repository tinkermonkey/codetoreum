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
from codetoreum.domain.events import AgentExecutionCompletedEvent
from codetoreum.domain.work_item import WorkItem
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.output.active_workflow_run_registry import ActiveRunInfo


def _build_dependencies() -> dict:
    """Return the standard dependencies dict the test suite assembles inline.

    Centralized so that depth-axis A4c can add `event_bus` once instead of
    sprinkling it through every test. Each test still constructs its own
    AsyncMocks so they remain isolated.
    """
    return {
        "execution_service": AsyncMock(),
        "workspace_router": AsyncMock(),
        "config_store": AsyncMock(),
        "agent_repository": AsyncMock(),
        "work_item_service": AsyncMock(),
        "run_registry": AsyncMock(),
        "branch_tracker": AsyncMock(),
        "vcs": AsyncMock(),
        "clock": SimulationClock(),
        "event_bus": EventBus(max_retries=0, retry_delay_seconds=0.0),
    }


def _subscribe_completion_callback(event_bus: EventBus, callback: AsyncMock, board_id: str = "board-1") -> None:
    """Wire `callback` to receive completion events in the legacy
    (work_item_id, board_id, success) shape so existing assertions still work.

    The default_board_id arg is preserved for tests that previously called
    `executor.set_completion_handler(callback, board_id)` — the value is now
    set via the executor constructor's `default_board_id` parameter.
    """

    async def _bridge(event: AgentExecutionCompletedEvent) -> None:
        await callback(event.work_item_id, event.board_id, event.success)

    event_bus.subscribe("AgentExecutionCompletedEvent", _bridge)


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
        clock = SimulationClock()
        event_bus = EventBus(max_retries=0, retry_delay_seconds=0.0)

        executor = ExecutionServiceAgentExecutor(
            execution_service=execution_service,
            workspace_router=workspace_router,
            config_store=config_store,
            agent_repository=agent_repository,
            work_item_service=work_item_service,
            run_registry=run_registry,
            branch_tracker=branch_tracker,
            vcs=vcs,
            clock=clock,
            event_bus=event_bus,
        )

        assert executor is not None
        assert executor._execution_service is execution_service
        assert executor._workspace_router is workspace_router
        assert executor._config_store is config_store
        assert executor._event_bus is event_bus

    def test_executor_initializes_with_optional_recovery_service(self):
        """Test that executor accepts optional recovery service."""
        dependencies = _build_dependencies()

        recovery_service = AsyncMock()

        executor = ExecutionServiceAgentExecutor(recovery_service=recovery_service, **dependencies)

        assert executor._recovery_service is recovery_service

    def test_executor_initializes_with_execution_delay(self):
        """Test that executor accepts execution delay for testing."""
        dependencies = _build_dependencies()

        executor = ExecutionServiceAgentExecutor(execution_delay=0.5, **dependencies)

        assert executor._execution_delay == 0.5

    def test_executor_wires_event_bus_and_default_board_id(self):
        """Verify constructor accepts the event bus and default_board_id.

        Replaces the previous `test_set_completion_handler_wires_callback` test.
        The set_completion_handler callback mechanism has been removed in
        favour of event-bus publication (see commit "Add
        AgentExecutionCompletedEvent for executor → board-handler seam" and
        siblings).
        """
        dependencies = _build_dependencies()

        executor = ExecutionServiceAgentExecutor(**dependencies, default_board_id="board-xyz")

        assert executor._event_bus is dependencies["event_bus"]
        assert executor._default_board_id == "board-xyz"
        assert not hasattr(executor, "_completion_callback")
        assert not hasattr(executor, "set_completion_handler")


class TestExecutionServiceAgentExecutorExecution:
    """Test execution behavior (fire-and-forget pattern)."""

    @pytest.mark.asyncio
    async def test_execute_records_execution_and_schedules_task(self):
        """Test that execute() records execution data and schedules async task.

        The execute() method is fire-and-forget: it records the execution,
        schedules _run_execution as a background task, and returns immediately
        without waiting for completion.
        """
        dependencies = _build_dependencies()

        executor = ExecutionServiceAgentExecutor(**dependencies)

        # Record active run
        run_info = ActiveRunInfo(
            run_id="run-1",
            work_item_id="item-1",
            project_id="project-1",
            stage_name="Ready",
            board_id="board-1",
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
        dependencies = _build_dependencies()

        executor = ExecutionServiceAgentExecutor(**dependencies, default_board_id="default-board")

        executor._run_registry.get_active_run.return_value = ActiveRunInfo(
            run_id="run-1",
            work_item_id="item-1",
            project_id="project-1",
            stage_name="Ready",
            board_id="board-1",
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
        dependencies = _build_dependencies()

        executor = ExecutionServiceAgentExecutor(**dependencies)

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
        dependencies = _build_dependencies()

        executor = ExecutionServiceAgentExecutor(execution_delay=0.1, **dependencies)

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
        dependencies = _build_dependencies()

        executor = ExecutionServiceAgentExecutor(**dependencies)
        callback = AsyncMock()
        _subscribe_completion_callback(dependencies["event_bus"], callback, "board-1")

        # No active run - should complete callback with failure
        executor._run_registry.get_active_run.return_value = None

        await executor._run_execution("item-1", "architect", "board-1")

        # Verify completion callback was called with False (failure)
        callback.assert_called_once_with("item-1", "board-1", False)
        executor._run_registry.get_active_run.assert_called_once_with("item-1")

    @pytest.mark.asyncio
    async def test_run_execution_step2_agent_load_failure(self):
        """Test Step 2: Handle failure when loading agent."""
        dependencies = _build_dependencies()

        executor = ExecutionServiceAgentExecutor(**dependencies)
        callback = AsyncMock()
        _subscribe_completion_callback(dependencies["event_bus"], callback, "board-1")

        # Setup active run
        run_info = ActiveRunInfo(
            run_id="run-1",
            work_item_id="item-1",
            project_id="project-1",
            stage_name="Ready",
            board_id="board-1",
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
        dependencies = _build_dependencies()

        executor = ExecutionServiceAgentExecutor(**dependencies)
        callback = AsyncMock()
        _subscribe_completion_callback(dependencies["event_bus"], callback, "board-1")

        # Setup active run
        run_info = ActiveRunInfo(
            run_id="run-1",
            work_item_id="item-1",
            project_id="project-1",
            stage_name="Ready",
            board_id="board-1",
        )
        executor._run_registry.get_active_run.return_value = run_info

        # Agent loads successfully
        agent = MagicMock(spec=Agent)
        executor._agent_repository.get_by_id.return_value = agent

        # Work item load fails
        executor._work_item_service.get_work_item.side_effect = Exception("Work item not found")

        await executor._run_execution("item-1", "architect", "board-1")

        # Verify completion callback called with False
        callback.assert_called_once_with("item-1", "board-1", False)

    @pytest.mark.asyncio
    async def test_run_execution_step4_project_config_load_failure(self):
        """Test Step 4: Handle failure when loading project config."""
        dependencies = _build_dependencies()

        executor = ExecutionServiceAgentExecutor(**dependencies)
        callback = AsyncMock()
        _subscribe_completion_callback(dependencies["event_bus"], callback, "board-1")

        # Setup active run
        run_info = ActiveRunInfo(
            run_id="run-1",
            work_item_id="item-1",
            project_id="project-1",
            stage_name="Ready",
            board_id="board-1",
        )
        executor._run_registry.get_active_run.return_value = run_info

        # Agent and work item load successfully
        agent = MagicMock(spec=Agent)
        executor._agent_repository.get_by_id.return_value = agent

        work_item = MagicMock(spec=WorkItem)
        executor._work_item_service.get_work_item.return_value = work_item

        # Project config load fails
        executor._config_store.get_project_config.side_effect = Exception("Config not found")

        await executor._run_execution("item-1", "architect", "board-1")

        # Verify completion callback called with False
        callback.assert_called_once_with("item-1", "board-1", False)


class TestExecutionServiceAgentExecutorCompletion:
    """Test completion callback handling."""

    @pytest.mark.asyncio
    async def test_completion_publish_with_no_subscribers_does_not_crash(self):
        """Publishing AgentExecutionCompletedEvent with no subscribers is a no-op.

        The event bus is required; subscribers are not. The executor must
        not crash when nothing is listening (e.g., bootstrap order issue).
        """
        dependencies = _build_dependencies()

        executor = ExecutionServiceAgentExecutor(**dependencies)

        executor._run_registry.get_active_run.return_value = None

        # Should not raise
        await executor._run_execution("item-1", "architect", "board-1")

    @pytest.mark.asyncio
    async def test_pending_tasks_cleanup_on_completion(self):
        """Test that completed tasks are properly cleaned up from _pending_tasks."""
        dependencies = _build_dependencies()

        executor = ExecutionServiceAgentExecutor(**dependencies)

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
        dependencies = _build_dependencies()

        executor = ExecutionServiceAgentExecutor(**dependencies)

        executor._run_registry.get_active_run.return_value = ActiveRunInfo(
            run_id="run-1",
            work_item_id="item-1",
            project_id="project-1",
            stage_name="Ready",
            board_id="board-1",
        )

        # Execute multiple times — item-1/coder is deduplicated because item-1 is still in
        # _executing_work_items when the second execute() call is made
        await executor.execute("item-1", "architect")
        await executor.execute("item-1", "coder")  # deduplicated: item-1 already executing
        await executor.execute("item-2", "architect")

        # item-1/architect and item-2/architect recorded; item-1/coder is deduplicated
        assert len(executor.executions) == 2
        assert executor.executions[0]["agent_id"] == "architect"
        assert executor.executions[0]["work_item_id"] == "item-1"
        assert executor.executions[1]["work_item_id"] == "item-2"

        # Clean up
        for task in executor._pending_tasks:
            task.cancel()
        await asyncio.gather(*executor._pending_tasks, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_executions_property_returns_copy(self):
        """Test that executions property returns a copy, not mutable reference."""
        dependencies = _build_dependencies()

        executor = ExecutionServiceAgentExecutor(**dependencies)

        executor._run_registry.get_active_run.return_value = ActiveRunInfo(
            run_id="run-1",
            work_item_id="item-1",
            project_id="project-1",
            stage_name="Ready",
            board_id="board-1",
        )

        await executor.execute("item-1", "architect")

        # Get executions list
        exec_list_1 = executor.executions
        exec_count_before = len(exec_list_1)

        # Execute a different item (same item would be deduplicated)
        executor._run_registry.get_active_run.return_value = ActiveRunInfo(
            run_id="run-2",
            work_item_id="item-2",
            project_id="project-1",
            stage_name="Ready",
            board_id="board-1",
        )
        await executor.execute("item-2", "architect")

        # Previous list should not be modified (copy semantics)
        assert len(exec_list_1) == exec_count_before

        # New list should have new execution
        exec_list_2 = executor.executions
        assert len(exec_list_2) == exec_count_before + 1

        # Clean up
        for task in executor._pending_tasks:
            task.cancel()
        await asyncio.gather(*executor._pending_tasks, return_exceptions=True)
