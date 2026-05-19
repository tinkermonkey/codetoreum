"""Production path tests for ExecutionServiceAgentExecutor.

Covers Steps 5-11 of the execution chain:
- Step 5: Track branch in IWorkItemBranchTracker
- Step 6: Prepare workspace (write context files, etc.)
- Step 7: Build execution context via ExecutionContextBuilder
- Step 8: Create execution via ExecutionService
- Step 9: Start execution and validate result
- Step 10: Execute via LLM or Container path
- Step 11: Finalize workspace (always runs, even on execution failure)

Also covers recovery logic:
- Completion callback failure handling
- Recovery service invocation on callback failure
- Recovery service failure handling (don't let it crash fire-and-forget task)
"""

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from codetoreum.adapters.secondary.execution_service_agent_executor import (
    ExecutionServiceAgentExecutor,
)
from codetoreum.domain.agent import AgentType
from codetoreum.domain.project_context import ProjectContext
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.output.active_workflow_run_registry import ActiveRunInfo

_UNSET = object()


class ProductionPathFixture:
    """Fixture with all dependencies pre-configured for production path testing."""

    WORK_ITEM_ID = "wi-production-test"
    AGENT_ID = "agent-coder"
    BOARD_ID = "board-1"

    def __init__(self) -> None:
        # Core dependencies
        self.run_registry = AsyncMock()
        self.agent_repository = AsyncMock()
        self.work_item_service = AsyncMock()
        self.config_store = AsyncMock()
        self.vcs = AsyncMock()
        self.workspace_router = AsyncMock()
        self.branch_tracker = AsyncMock()
        self.execution_service = AsyncMock()
        self.completion_callback = AsyncMock()
        self.clock = SimulationClock()
        self.recovery_service = AsyncMock()

        # Step 1: Active run
        self.run_info = ActiveRunInfo(
            work_item_id=self.WORK_ITEM_ID,
            run_id="run-prod-1",
            stage_name="implementation",
            project_id="proj-1",
            board_id="board-1",
        )
        self.run_registry.get_active_run.return_value = self.run_info

        # Step 2a: Agent
        self.agent = MagicMock()
        self.agent.id = self.AGENT_ID
        self.agent.name = "coder-agent"
        self.agent.display_name = "Coder Agent"
        self.agent.agent_type = AgentType.DEVELOPER
        self.agent.role_description = "A coding agent for implementation"
        self.agent.system_prompt = "You are an expert coder"
        self.agent.model = "claude-opus-4-7"
        self.agent.requires_docker = False
        self.agent.requires_dev_container = False
        self.agent.timeout_seconds = 3600
        self.agent.max_retries = 3
        self.agent.makes_code_changes = True
        self.agent.filesystem_write_allowed = True
        self.agent.mcp_servers = []
        self.agent.capabilities = {}
        self.agent_repository.get_by_id.return_value = self.agent

        # Step 2b: WorkItem
        self.work_item = MagicMock()
        self.work_item.id = self.WORK_ITEM_ID
        self.work_item.title = "Implement feature X"
        self.work_item.description = "Implement a new feature"
        self.work_item.status = MagicMock(value="in_progress")
        self.work_item.priority = MagicMock(value=3)
        self.work_item.labels = []
        self.work_item.external_url = None
        self.work_item.assigned_agent_id = None
        self.work_item_service.get_work_item.return_value = self.work_item

        # Step 2c: ProjectConfig
        self.project_config = MagicMock()
        self.project_config.id = "proj-1"
        self.project_config.name = "test-project"
        self.project_config.github_org = "test-org"
        self.project_config.github_repo = "test-repo"
        self.project_config.tech_stacks = {"python": "3.11"}
        self.project_config.testing = {"command": "pytest", "framework": "pytest"}
        self.project_config.environment_variables = {"ENV": "test"}
        self.project_config.created_at = None
        self.project_config.updated_at = None
        self.config_store.get_project_config.return_value = self.project_config

        # Step 3: VCS clone (no-op for simulation)
        self.vcs.clone_repository.return_value = None

        # Step 4: Route workspace
        self.workspace = MagicMock()
        self.workspace.work_item_id = self.WORK_ITEM_ID
        self.workspace.project_id = "proj-1"
        self.workspace.branch_name = "feature/issue-1-implementation"
        self.workspace_router.route_workspace.return_value = self.workspace

        # Step 5: Branch tracker
        self.branch_tracker.set_branch.return_value = None

        # Step 6: Prepare workspace
        self.prep_result = MagicMock()
        self.prep_result.success = True
        self.workspace_router.prepare_workspace.return_value = self.prep_result

        # Step 8: Create execution
        self.execution = MagicMock()
        self.execution.id = "exec-prod-1"
        self.execution_service.create_execution.return_value = self.execution

        # Step 9: Start execution
        self.start_result = MagicMock()
        self.start_result.success = True
        self.execution_service.start_execution.return_value = self.start_result

        # Step 10: Execute with LLM (default path)
        self.exec_result = MagicMock()
        self.exec_result.success = True
        self.exec_result.execution = MagicMock(output="Completed successfully")
        self.execution_service.execute_with_llm.return_value = self.exec_result

        # Step 11: Finalize workspace
        self.finalize_result = MagicMock()
        self.finalize_result.success = True
        self.workspace_router.finalize_workspace.return_value = self.finalize_result

    def make_executor(self, recovery_service=_UNSET, workflow_config_service=_UNSET) -> ExecutionServiceAgentExecutor:
        executor = ExecutionServiceAgentExecutor(
            execution_service=self.execution_service,
            workspace_router=self.workspace_router,
            config_store=self.config_store,
            agent_repository=self.agent_repository,
            work_item_service=self.work_item_service,
            run_registry=self.run_registry,
            branch_tracker=self.branch_tracker,
            vcs=self.vcs,
            clock=self.clock,
            recovery_service=self.recovery_service if recovery_service is _UNSET else recovery_service,
            workflow_config_service=None if workflow_config_service is _UNSET else workflow_config_service,
        )
        executor.set_completion_handler(self.completion_callback, self.BOARD_ID)
        return executor


class TestProductionExecutionPath:
    """Test the full production execution path (Steps 5-11)."""

    @pytest.mark.asyncio
    async def test_full_llm_execution_path_success(self):
        """Full chain: load objects → route → prepare → create → start → execute → finalize → complete."""
        fx = ProductionPathFixture()
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        # Verify all steps executed in order
        fx.run_registry.get_active_run.assert_called_once_with(fx.WORK_ITEM_ID)
        fx.agent_repository.get_by_id.assert_called_once_with(fx.AGENT_ID)
        fx.work_item_service.get_work_item.assert_called_once()
        fx.config_store.get_project_config.assert_called_once_with("proj-1")

        # Step 3: VCS clone
        fx.vcs.clone_repository.assert_called_once()

        # Step 4: Route workspace
        fx.workspace_router.route_workspace.assert_called_once()

        # Step 5: Track branch
        fx.branch_tracker.set_branch.assert_called_once_with(fx.WORK_ITEM_ID, fx.workspace.branch_name)

        # Step 6: Prepare workspace
        fx.workspace_router.prepare_workspace.assert_called_once()

        # Step 8: Create execution
        fx.execution_service.create_execution.assert_called_once()

        # Step 9: Start execution
        fx.execution_service.start_execution.assert_called_once_with(fx.execution, ANY)

        # Step 10: Execute (LLM path)
        fx.execution_service.execute_with_llm.assert_called_once()
        fx.execution_service.execute_with_container.assert_not_called()

        # Step 11: Finalize workspace
        fx.workspace_router.finalize_workspace.assert_called_once()

        # Cleanup
        fx.run_registry.clear_run.assert_called_once_with(fx.WORK_ITEM_ID)
        fx.branch_tracker.clear.assert_called_once_with(fx.WORK_ITEM_ID)

        # Completion callback called with success=True
        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, True)

    @pytest.mark.asyncio
    async def test_full_container_execution_path_success(self):
        """Full chain with requires_docker=True routes to execute_with_container."""
        fx = ProductionPathFixture()
        fx.agent.requires_docker = True

        container_result = MagicMock()
        container_result.success = True
        container_result.execution = MagicMock(output="Container completed")
        fx.execution_service.execute_with_container.return_value = container_result

        executor = fx.make_executor()
        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        # Verify container path taken
        fx.execution_service.execute_with_container.assert_called_once()
        fx.execution_service.execute_with_llm.assert_not_called()

        # Completion should be called with success=True
        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, True)


class TestProductionPathStep5BranchTracking:
    """Test Step 5: Branch tracking in IWorkItemBranchTracker."""

    @pytest.mark.asyncio
    async def test_branch_tracked_when_workspace_has_branch_name(self):
        """Step 5: set_branch called when workspace.branch_name is provided."""
        fx = ProductionPathFixture()
        fx.workspace.branch_name = "feature/issue-123-tracking"
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        fx.branch_tracker.set_branch.assert_called_once_with(fx.WORK_ITEM_ID, "feature/issue-123-tracking")
        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, True)

    @pytest.mark.asyncio
    async def test_branch_not_tracked_when_workspace_branch_is_none(self):
        """Step 5: set_branch not called when workspace.branch_name is None."""
        fx = ProductionPathFixture()
        fx.workspace.branch_name = None  # No branch
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        # set_branch should not be called for falsy branch names
        fx.branch_tracker.set_branch.assert_not_called()
        # But execution should still complete successfully
        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, True)

    @pytest.mark.asyncio
    async def test_branch_tracker_failure_stops_execution(self):
        """Step 5: branch_tracker.set_branch raises → execution fails."""
        fx = ProductionPathFixture()
        fx.branch_tracker.set_branch.side_effect = RuntimeError("Branch tracker unavailable")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)
        # Downstream steps should not execute
        fx.workspace_router.prepare_workspace.assert_not_called()
        fx.execution_service.create_execution.assert_not_called()


class TestProductionPathStep6WorkspacePreparation:
    """Test Step 6: Workspace preparation."""

    @pytest.mark.asyncio
    async def test_workspace_prepared_with_correct_arguments(self):
        """Step 6: prepare_workspace called with workspace, project context, work item, repo path."""
        fx = ProductionPathFixture()
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        # Verify prepare_workspace was called
        assert fx.workspace_router.prepare_workspace.call_count == 1
        call_args = fx.workspace_router.prepare_workspace.call_args
        prepared_workspace = call_args.args[0]
        project_context = call_args.args[1]
        prepared_work_item = call_args.args[2]
        repo_path = call_args.args[3]

        assert prepared_workspace == fx.workspace
        assert isinstance(project_context, ProjectContext)
        assert prepared_work_item == fx.work_item
        assert fx.WORK_ITEM_ID in repo_path  # Repo path should include work item ID

    @pytest.mark.asyncio
    async def test_workspace_preparation_failure_stops_execution(self):
        """Step 6: prepare_workspace.success=False → execution fails."""
        fx = ProductionPathFixture()
        fx.prep_result.success = False
        fx.prep_result.reason = "Disk full"
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)
        fx.execution_service.create_execution.assert_not_called()

    @pytest.mark.asyncio
    async def test_workspace_preparation_exception_stops_execution(self):
        """Step 6: prepare_workspace raises exception → execution fails."""
        fx = ProductionPathFixture()
        fx.workspace_router.prepare_workspace.side_effect = RuntimeError("Prep crashed")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)
        fx.execution_service.create_execution.assert_not_called()


class TestProductionPathStep7ExecutionContextBuilding:
    """Test Step 7: Execution context building via ExecutionContextBuilder."""

    @pytest.mark.asyncio
    async def test_execution_context_built_from_domain_objects(self):
        """Step 7: ExecutionContextBuilder.build_context called with correct objects."""
        fx = ProductionPathFixture()

        # Mock ExecutionContextBuilder to capture the call
        with patch(
            "codetoreum.adapters.secondary.execution_service_agent_executor.ExecutionContextBuilder"
        ) as mock_builder:
            mock_context = MagicMock()
            mock_builder.build_context.return_value = mock_context

            executor = fx.make_executor()
            await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

            # Verify build_context was called with the right arguments
            assert mock_builder.build_context.called
            call_kwargs = mock_builder.build_context.call_args.kwargs
            assert call_kwargs["work_item"] == fx.work_item
            assert call_kwargs["agent"] == fx.agent
            assert isinstance(call_kwargs["project"], ProjectContext)
            assert call_kwargs["workspace"] == fx.workspace


class TestProductionPathStep8CreateExecution:
    """Test Step 8: Create execution via ExecutionService."""

    @pytest.mark.asyncio
    async def test_execution_created_with_correct_arguments(self):
        """Step 8: create_execution called with agent, work item, workflow info."""
        fx = ProductionPathFixture()
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        assert fx.execution_service.create_execution.call_count == 1
        call_kwargs = fx.execution_service.create_execution.call_args.kwargs
        assert call_kwargs["agent"] == fx.agent
        assert call_kwargs["work_item"] == fx.work_item
        assert call_kwargs["workflow_id"] == "run-prod-1"
        assert call_kwargs["stage_name"] == "implementation"

    @pytest.mark.asyncio
    async def test_create_execution_failure_finalizes_and_fails(self):
        """Step 8: create_execution raises → finalize_workspace called, completion=False."""
        fx = ProductionPathFixture()
        fx.execution_service.create_execution.side_effect = RuntimeError("Execution DB error")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        # Finalize should be called even on create_execution failure
        fx.workspace_router.finalize_workspace.assert_called_once()
        finalize_args = fx.workspace_router.finalize_workspace.call_args
        assert finalize_args.args[2]["success"] is False

        # Completion called with failure
        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)

    @pytest.mark.asyncio
    async def test_prompt_build_failure_finalizes_and_fails(self):
        """Step 8: PromptBuilder.build_prompt raises → finalize_workspace, completion=False."""
        fx = ProductionPathFixture()
        executor = fx.make_executor()

        with patch(
            "codetoreum.adapters.secondary.execution_service_agent_executor.PromptBuilder"
        ) as mock_prompt_builder:
            mock_prompt_builder.build_prompt.side_effect = AttributeError("None agent field")

            await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

            # Finalize should be called on prompt build failure
            fx.workspace_router.finalize_workspace.assert_called_once()
            finalize_args = fx.workspace_router.finalize_workspace.call_args
            assert finalize_args.args[2]["success"] is False

            # Completion called with failure
            fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)

            # create_execution should never be called
            fx.execution_service.create_execution.assert_not_called()


class TestProductionPathStep9StartExecution:
    """Test Step 9: Start execution and validate result."""

    @pytest.mark.asyncio
    async def test_execution_started_with_correct_arguments(self):
        """Step 9: start_execution called with execution and context."""
        fx = ProductionPathFixture()

        with patch(
            "codetoreum.adapters.secondary.execution_service_agent_executor.ExecutionContextBuilder"
        ) as mock_builder:
            mock_context = MagicMock()
            mock_builder.build_context.return_value = mock_context

            executor = fx.make_executor()
            await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

            assert fx.execution_service.start_execution.call_count == 1
            call_args = fx.execution_service.start_execution.call_args
            assert call_args.args[0] == fx.execution
            assert call_args.args[1] == mock_context

    @pytest.mark.asyncio
    async def test_start_execution_failure_finalizes_and_fails(self):
        """Step 9: start_execution.success=False → finalize_workspace, completion=False."""
        fx = ProductionPathFixture()
        fx.start_result.success = False
        fx.start_result.error = "Container startup timeout"
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        # Finalize should be called on startup failure
        fx.workspace_router.finalize_workspace.assert_called_once()
        finalize_args = fx.workspace_router.finalize_workspace.call_args
        assert finalize_args.args[2]["success"] is False

        # Completion called with failure
        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)

        # Execution should not proceed
        fx.execution_service.execute_with_llm.assert_not_called()


class TestProductionPathStep10Execution:
    """Test Step 10: Execute via LLM or Container path."""

    @pytest.mark.asyncio
    async def test_llm_execution_called_when_requires_docker_false(self):
        """Step 10: agent.requires_docker=False → execute_with_llm called."""
        fx = ProductionPathFixture()
        fx.agent.requires_docker = False
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        fx.execution_service.execute_with_llm.assert_called_once()
        fx.execution_service.execute_with_container.assert_not_called()

    @pytest.mark.asyncio
    async def test_container_execution_called_when_requires_docker_true(self):
        """Step 10: agent.requires_docker=True → execute_with_container called."""
        fx = ProductionPathFixture()
        fx.agent.requires_docker = True

        container_result = MagicMock()
        container_result.success = True
        container_result.execution = MagicMock(output="Container output")
        fx.execution_service.execute_with_container.return_value = container_result

        executor = fx.make_executor()
        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        fx.execution_service.execute_with_container.assert_called_once()
        fx.execution_service.execute_with_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_execution_failure_is_soft_failure(self):
        """Step 10: execute_with_llm.success=False → finalize and completion=False."""
        fx = ProductionPathFixture()
        fx.exec_result.success = False
        fx.exec_result.execution = MagicMock(output="LLM error output")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        # Finalize should still be called
        fx.workspace_router.finalize_workspace.assert_called_once()
        finalize_args = fx.workspace_router.finalize_workspace.call_args
        assert finalize_args.args[2]["success"] is False

        # Completion called with failure
        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)

    @pytest.mark.asyncio
    async def test_execution_exception_is_caught_and_finalized(self):
        """Step 10: execute_with_llm raises exception → finalize and completion=False."""
        fx = ProductionPathFixture()
        fx.execution_service.execute_with_llm.side_effect = RuntimeError("LLM call failed")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        # Finalize should still be called (in try/finally pattern)
        fx.workspace_router.finalize_workspace.assert_called_once()
        finalize_args = fx.workspace_router.finalize_workspace.call_args
        assert finalize_args.args[2]["success"] is False

        # Completion called with failure
        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, False)


class TestProductionPathStep11Finalization:
    """Test Step 11: Finalize workspace (always runs)."""

    @pytest.mark.asyncio
    async def test_workspace_finalization_on_success(self):
        """Step 11: finalize_workspace called with success=True on successful execution."""
        fx = ProductionPathFixture()
        fx.exec_result.success = True
        fx.exec_result.execution = MagicMock(output="Success output")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        fx.workspace_router.finalize_workspace.assert_called_once()
        finalize_call = fx.workspace_router.finalize_workspace.call_args
        finalize_data = finalize_call.args[2]
        assert finalize_data["success"] is True
        assert "Success output" in finalize_data.get("output", "")

    @pytest.mark.asyncio
    async def test_workspace_finalization_on_soft_failure(self):
        """Step 11: finalize_workspace called with success=False on soft execution failure."""
        fx = ProductionPathFixture()
        fx.exec_result.success = False
        fx.exec_result.execution = MagicMock(output="Failure details")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        fx.workspace_router.finalize_workspace.assert_called_once()
        finalize_call = fx.workspace_router.finalize_workspace.call_args
        finalize_data = finalize_call.args[2]
        assert finalize_data["success"] is False

    @pytest.mark.asyncio
    async def test_workspace_finalization_on_execution_exception(self):
        """Step 11: finalize_workspace called even if execute raises exception."""
        fx = ProductionPathFixture()
        fx.execution_service.execute_with_llm.side_effect = RuntimeError("Execution crashed")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        # Finalize should still be called (finally block)
        fx.workspace_router.finalize_workspace.assert_called_once()
        finalize_call = fx.workspace_router.finalize_workspace.call_args
        finalize_data = finalize_call.args[2]
        assert finalize_data["success"] is False

    @pytest.mark.asyncio
    async def test_workspace_finalization_failure_does_not_prevent_completion(self):
        """Step 11: finalize_workspace failure logged but doesn't prevent completion."""
        fx = ProductionPathFixture()
        fx.workspace_router.finalize_workspace.side_effect = RuntimeError("Finalize crashed")
        executor = fx.make_executor()

        # Should not raise
        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        # Completion still called (success=True because exec succeeded before finalize crashed)
        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, True)

    @pytest.mark.asyncio
    async def test_finalization_receives_execution_output(self):
        """Step 11: finalize_workspace receives execution output in data dict."""
        fx = ProductionPathFixture()
        fx.exec_result.success = True
        fx.exec_result.execution = MagicMock(output="Generated code:\nclass Foo:\n  pass")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        finalize_call = fx.workspace_router.finalize_workspace.call_args
        finalize_data = finalize_call.args[2]
        assert "Generated code:" in finalize_data.get("output", "")


class TestProductionPathCleanupAndCompletion:
    """Test cleanup and completion callback behavior."""

    @pytest.mark.asyncio
    async def test_registry_and_branch_tracker_cleared_on_success(self):
        """Registry and branch-tracker cleared after successful execution."""
        fx = ProductionPathFixture()
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        fx.run_registry.clear_run.assert_called_once_with(fx.WORK_ITEM_ID)
        fx.branch_tracker.clear.assert_called_once_with(fx.WORK_ITEM_ID)

    @pytest.mark.asyncio
    async def test_registry_and_branch_tracker_cleared_on_failure(self):
        """Registry and branch-tracker cleared even on execution failure."""
        fx = ProductionPathFixture()
        fx.execution_service.execute_with_llm.side_effect = RuntimeError("Execution failed")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        # Cleanup still happens (finally block)
        fx.run_registry.clear_run.assert_called_once_with(fx.WORK_ITEM_ID)
        fx.branch_tracker.clear.assert_called_once_with(fx.WORK_ITEM_ID)

    @pytest.mark.asyncio
    async def test_registry_and_branch_tracker_cleared_on_prep_failure(self):
        """Registry and branch-tracker cleared even if prep fails."""
        fx = ProductionPathFixture()
        fx.workspace_router.prepare_workspace.return_value = MagicMock(success=False, reason="Error")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        # Cleanup still happens
        fx.run_registry.clear_run.assert_called_once_with(fx.WORK_ITEM_ID)
        fx.branch_tracker.clear.assert_called_once_with(fx.WORK_ITEM_ID)

    @pytest.mark.asyncio
    async def test_cleanup_failure_does_not_prevent_completion(self):
        """Cleanup failure logged but doesn't prevent completion callback."""
        fx = ProductionPathFixture()
        fx.run_registry.clear_run.side_effect = RuntimeError("Registry unavailable")
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        # Completion still called despite cleanup failure
        fx.completion_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_completion_callback_called_exactly_once(self):
        """Completion callback called exactly once, with correct success value."""
        fx = ProductionPathFixture()
        executor = fx.make_executor()

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        # Exactly one call
        assert fx.completion_callback.call_count == 1
        # With success=True
        fx.completion_callback.assert_called_once_with(fx.WORK_ITEM_ID, fx.BOARD_ID, True)


class TestCompletionCallbackFailureRecovery:
    """Test recovery logic in _call_completion (lines 515-566)."""

    @pytest.mark.asyncio
    async def test_completion_callback_failure_invokes_recovery_service(self):
        """Completion callback raises → recovery service.handle_completion_callback_failure called."""
        fx = ProductionPathFixture()
        fx.completion_callback.side_effect = RuntimeError("Auto-progression failed")
        executor = fx.make_executor(recovery_service=fx.recovery_service)

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        # Recovery service should be invoked
        assert fx.recovery_service.handle_completion_callback_failure.called
        call_kwargs = fx.recovery_service.handle_completion_callback_failure.call_args.kwargs
        assert call_kwargs["work_item_id"] == fx.WORK_ITEM_ID
        assert call_kwargs["board_id"] == fx.BOARD_ID
        assert call_kwargs["success"] is True

    @pytest.mark.asyncio
    async def test_completion_callback_failure_with_recovery_service_receives_error(self):
        """Recovery service receives the exception that caused callback failure."""
        fx = ProductionPathFixture()
        callback_error = RuntimeError("Board update failed")
        fx.completion_callback.side_effect = callback_error
        executor = fx.make_executor(recovery_service=fx.recovery_service)

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        # Recovery service should receive the exception
        call_kwargs = fx.recovery_service.handle_completion_callback_failure.call_args.kwargs
        assert call_kwargs["error"] == callback_error

    @pytest.mark.asyncio
    async def test_completion_callback_failure_without_recovery_service(self):
        """Completion callback failure without recovery service is just logged."""
        fx = ProductionPathFixture()
        fx.completion_callback.side_effect = RuntimeError("Auto-progression failed")
        executor = fx.make_executor(recovery_service=None)

        # Should not raise
        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        # Cleanup still happens
        fx.run_registry.clear_run.assert_called_once_with(fx.WORK_ITEM_ID)
        fx.branch_tracker.clear.assert_called_once_with(fx.WORK_ITEM_ID)

    @pytest.mark.asyncio
    async def test_recovery_service_failure_does_not_crash_task(self):
        """Recovery service failure logged but doesn't propagate in fire-and-forget task."""
        fx = ProductionPathFixture()
        fx.completion_callback.side_effect = RuntimeError("Callback failed")
        fx.recovery_service.handle_completion_callback_failure.side_effect = RuntimeError("Recovery service crashed")
        executor = fx.make_executor(recovery_service=fx.recovery_service)

        # Should not raise even though recovery service failed
        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

    @pytest.mark.asyncio
    async def test_completion_callback_success_does_not_invoke_recovery(self):
        """When completion callback succeeds, recovery service not invoked."""
        fx = ProductionPathFixture()
        executor = fx.make_executor(recovery_service=fx.recovery_service)

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        # Recovery service should not be called
        fx.recovery_service.handle_completion_callback_failure.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_completion_callback_handler_error_logged(self):
        """When no completion callback set, error logged with helpful message."""
        fx = ProductionPathFixture()
        executor = ExecutionServiceAgentExecutor(
            execution_service=fx.execution_service,
            workspace_router=fx.workspace_router,
            config_store=fx.config_store,
            agent_repository=fx.agent_repository,
            work_item_service=fx.work_item_service,
            run_registry=fx.run_registry,
            branch_tracker=fx.branch_tracker,
            vcs=fx.vcs,
            clock=fx.clock,
            recovery_service=fx.recovery_service,
        )
        # Don't call set_completion_handler

        # Execution should complete without crashing
        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        # No exception should be raised


class TestProductionPathProjectContextBuilding:
    """Test ProjectContext construction from ProjectConfig."""

    @pytest.mark.asyncio
    async def test_project_context_built_from_config(self):
        """ProjectContext correctly constructed from ProjectConfig during execution."""
        fx = ProductionPathFixture()

        with patch(
            "codetoreum.adapters.secondary.execution_service_agent_executor.ProjectContext"
        ) as mock_context_class:
            executor = fx.make_executor()
            await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

            # ProjectContext should be instantiated
            assert mock_context_class.called

    @pytest.mark.asyncio
    async def test_repository_url_constructed_from_github_org_and_repo(self):
        """ProjectContext receives correct repository URL from org/repo."""
        fx = ProductionPathFixture()
        fx.project_config.github_org = "my-org"
        fx.project_config.github_repo = "my-repo"

        # Capture the ProjectContext that gets built
        with patch(
            "codetoreum.adapters.secondary.execution_service_agent_executor.ProjectContext"
        ) as mock_context_class:
            executor = fx.make_executor()
            await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

            # Check the call
            call_kwargs = mock_context_class.call_args.kwargs
            assert call_kwargs["repository_url"] == "https://github.com/my-org/my-repo.git"


class TestPromptBuilderIntegration:
    """Test PromptBuilder integration with workflow_config_service in execution chain."""

    @pytest.mark.asyncio
    async def test_workflow_template_fetched_when_config_service_provided(self):
        """Step 8: workflow_config_service.get_board_workflow_template called when service injected."""
        fx = ProductionPathFixture()
        workflow_config_service = AsyncMock()
        mock_template = MagicMock()
        mock_template.stages = {"implementation": "Implement the feature"}
        workflow_config_service.get_board_workflow_template.return_value = mock_template

        executor = fx.make_executor(workflow_config_service=workflow_config_service)

        await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

        # Verify workflow template was fetched
        workflow_config_service.get_board_workflow_template.assert_called_once_with(fx.BOARD_ID)

    @pytest.mark.asyncio
    async def test_prompt_built_with_workflow_template_when_service_provided(self):
        """Step 8: PromptBuilder.build_prompt called with workflow_template parameter."""
        fx = ProductionPathFixture()
        workflow_config_service = AsyncMock()
        mock_template = MagicMock()
        mock_template.stages = {"implementation": "Implement the feature"}
        workflow_config_service.get_board_workflow_template.return_value = mock_template

        with patch(
            "codetoreum.adapters.secondary.execution_service_agent_executor.PromptBuilder"
        ) as mock_prompt_builder:
            mock_prompt = "Test prompt"
            mock_prompt_builder.build_prompt.return_value = mock_prompt

            executor = fx.make_executor(workflow_config_service=workflow_config_service)

            await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

            # Verify PromptBuilder.build_prompt was called with workflow_template
            assert mock_prompt_builder.build_prompt.called
            call_kwargs = mock_prompt_builder.build_prompt.call_args.kwargs
            assert call_kwargs["workflow_template"] == mock_template

    @pytest.mark.asyncio
    async def test_prompt_built_without_template_when_service_not_provided(self):
        """Step 8: PromptBuilder.build_prompt called with workflow_template=None when service not provided."""
        fx = ProductionPathFixture()

        with patch(
            "codetoreum.adapters.secondary.execution_service_agent_executor.PromptBuilder"
        ) as mock_prompt_builder:
            mock_prompt = "Test prompt"
            mock_prompt_builder.build_prompt.return_value = mock_prompt

            executor = fx.make_executor()

            await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

            # Verify PromptBuilder.build_prompt was called with workflow_template=None
            assert mock_prompt_builder.build_prompt.called
            call_kwargs = mock_prompt_builder.build_prompt.call_args.kwargs
            assert call_kwargs["workflow_template"] is None

    @pytest.mark.asyncio
    async def test_workflow_template_fetch_failure_logged_but_prompt_built(self):
        """Step 8: workflow_template fetch failure logged as warning, prompt still built with None."""
        fx = ProductionPathFixture()
        workflow_config_service = AsyncMock()
        workflow_config_service.get_board_workflow_template.side_effect = RuntimeError("Service unavailable")

        with patch(
            "codetoreum.adapters.secondary.execution_service_agent_executor.PromptBuilder"
        ) as mock_prompt_builder:
            with patch("codetoreum.adapters.secondary.execution_service_agent_executor.logger") as mock_logger:
                mock_prompt = "Test prompt"
                mock_prompt_builder.build_prompt.return_value = mock_prompt

                executor = fx.make_executor(workflow_config_service=workflow_config_service)

                await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

                # Verify warning was logged
                assert mock_logger.warning.called
                warning_call = mock_logger.warning.call_args
                assert "Failed to fetch workflow template" in warning_call.args[0]

                # Verify PromptBuilder still called with workflow_template=None
                assert mock_prompt_builder.build_prompt.called
                call_kwargs = mock_prompt_builder.build_prompt.call_args.kwargs
                assert call_kwargs["workflow_template"] is None

    @pytest.mark.asyncio
    async def test_prompt_building_handles_missing_previous_stage_output(self):
        """Step 8: PromptBuilder.build_prompt called even when previous_stage.txt missing."""
        fx = ProductionPathFixture()

        with patch(
            "codetoreum.adapters.secondary.execution_service_agent_executor.PromptBuilder"
        ) as mock_prompt_builder:
            with patch(
                "codetoreum.adapters.secondary.execution_service_agent_executor.Path.exists",
                return_value=False,
            ):
                mock_prompt = "Test prompt"
                mock_prompt_builder.build_prompt.return_value = mock_prompt

                executor = fx.make_executor()

                await executor._run_execution(fx.WORK_ITEM_ID, fx.AGENT_ID, fx.BOARD_ID)

                # Verify PromptBuilder still called with previous_output=None
                assert mock_prompt_builder.build_prompt.called
                call_kwargs = mock_prompt_builder.build_prompt.call_args.kwargs
                assert call_kwargs["previous_output"] is None
