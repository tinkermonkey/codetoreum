"""ExecutionServiceAgentExecutor - wires IAgentExecutor to ExecutionService chain.

This adapter drives the full LLM → Container → VCS chain in simulation by
integrating with ExecutionService, WorkspaceRouter, and supporting repositories.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from codetoreum.domain.project_context import ProjectContext
from codetoreum.domain.services.execution_context_builder import ExecutionContextBuilder
from codetoreum.domain.types import WorkItemId
from codetoreum.domain.value_objects import ContainerConfig
from codetoreum.ports.output.agent_executor import IAgentExecutor

if TYPE_CHECKING:
    from codetoreum.application.execution_service import ExecutionService
    from codetoreum.application.workspace_router import WorkspaceRouter
    from codetoreum.ports.output.active_workflow_run_registry import IActiveWorkflowRunRegistry
    from codetoreum.ports.output.agent_repository import IAgentRepository
    from codetoreum.ports.output.config_store import IConfigStore
    from codetoreum.ports.output.version_control_service import IVersionControlService
    from codetoreum.ports.output.work_item_branch_tracker import IWorkItemBranchTracker
    from codetoreum.ports.output.work_item_service import IWorkItemService

logger = logging.getLogger(__name__)


class ExecutionServiceAgentExecutor(IAgentExecutor):
    """Wires IAgentExecutor → ExecutionService → LLM/Container/VCS chain.

    This adapter replaces MockAgentExecutor for Phase 3 testing. It drives the
    full execution chain:
    1. Looks up active run from registry (set by BoardColumnEventHandler)
    2. Loads domain objects (Agent, WorkItem, ProjectConfig → ProjectContext)
    3. Clones repository and routes workspace
    4. Builds execution context
    5. Creates and starts execution via ExecutionService
    6. Executes via LLM path (default) or Container path (requires_docker=True)
    7. Finalizes workspace (commits, pushes)
    8. Clears registry entries
    9. Calls completion callback for board auto-progression
    """

    def __init__(
        self,
        execution_service: ExecutionService,
        workspace_router: WorkspaceRouter,
        config_store: IConfigStore,
        agent_repository: IAgentRepository,
        work_item_service: IWorkItemService,
        run_registry: IActiveWorkflowRunRegistry,
        branch_tracker: IWorkItemBranchTracker,
        vcs: IVersionControlService,
        execution_delay: float = 0.0,
    ) -> None:
        """Initialize ExecutionServiceAgentExecutor.

        Args:
            execution_service: Core execution engine
            workspace_router: Handles repository branch setup and cleanup
            config_store: Project and agent configuration store
            agent_repository: Repository for Agent domain objects
            work_item_service: Service for work item lookups
            run_registry: Tracks active workflow runs per work item
            branch_tracker: Tracks VCS branches per work item
            vcs: Version control service for repository operations
            execution_delay: Optional delay (seconds) before execution for testing
        """
        self._execution_service = execution_service
        self._workspace_router = workspace_router
        self._config_store = config_store
        self._agent_repository = agent_repository
        self._work_item_service = work_item_service
        self._run_registry = run_registry
        self._branch_tracker = branch_tracker
        self._vcs = vcs
        self._execution_delay = execution_delay

        self._completion_callback: Callable[[str, str, bool], Coroutine[Any, Any, None]] | None = None
        self._default_board_id = "board-1"
        self._executions: list[dict[str, Any]] = []
        self._pending_tasks: set[asyncio.Task] = set()

    def set_completion_handler(
        self,
        callback: Callable[[str, str, bool], Coroutine[Any, Any, None]],
        default_board_id: str,
    ) -> None:
        """Wire completion callback after handler creation.

        Avoids circular constructor dependencies.

        Args:
            callback: Async function(work_item_id, board_id, success)
            default_board_id: Board ID to pass to callback
        """
        self._completion_callback = callback
        self._default_board_id = default_board_id

    @property
    def executions(self) -> list[dict[str, Any]]:
        """Return recorded executions for test assertions."""
        return list(self._executions)

    async def execute(self, work_item_id: str, agent_id: str, board_id: str | None = None) -> None:
        """Execute an agent on a work item (fire-and-forget).

        Records the execution and schedules background work via
        asyncio.create_task so the caller is not blocked.

        Args:
            work_item_id: ID of the work item to process
            agent_id: ID of the agent to execute
            board_id: ID of the board containing the work item
        """
        resolved_board_id = board_id or self._default_board_id
        now = datetime.now(UTC)

        self._executions.append(
            {
                "work_item_id": work_item_id,
                "agent_id": agent_id,
                "board_id": resolved_board_id,
                "started_at": now.isoformat(),
            }
        )

        logger.info(f"ExecutionServiceAgentExecutor: scheduling agent '{agent_id}' for '{work_item_id}'")

        task = asyncio.create_task(self._run_execution(work_item_id, agent_id, resolved_board_id))
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

    async def _run_execution(self, work_item_id: str, agent_id: str, board_id: str) -> None:
        """Drive the full execution chain for a work item.

        Args:
            work_item_id: Work item to process
            agent_id: Agent identifier
            board_id: Board identifier
        """
        success = False
        try:
            if self._execution_delay > 0:
                await asyncio.sleep(self._execution_delay)

            # Step 1: Look up active run
            run_info = await self._run_registry.get_active_run(work_item_id)
            if run_info is None:
                logger.error(
                    f"No active run found for work item '{work_item_id}'. Cannot execute.",
                    extra={"error_id": "ERR_EXEC_CHAIN_NO_ACTIVE_RUN"},
                )
                await self._call_completion(work_item_id, board_id, False)
                return

            # Step 2: Load domain objects
            try:
                agent = await self._agent_repository.get_by_id(agent_id)
            except Exception as e:
                logger.error(
                    f"Failed to load agent '{agent_id}': {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_EXEC_CHAIN_AGENT_LOAD_FAILURE"},
                )
                await self._call_completion(work_item_id, board_id, False)
                return

            try:
                work_item = await self._work_item_service.get_work_item(WorkItemId(work_item_id))
            except Exception as e:
                logger.error(
                    f"Failed to load work item '{work_item_id}': {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_EXEC_CHAIN_WORK_ITEM_LOAD_FAILURE"},
                )
                await self._call_completion(work_item_id, board_id, False)
                return

            try:
                project_config = await self._config_store.get_project_config(run_info.project_id)
            except Exception as e:
                logger.error(
                    f"Failed to load project config '{run_info.project_id}': {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_EXEC_CHAIN_PROJECT_CONFIG_LOAD_FAILURE"},
                )
                await self._call_completion(work_item_id, board_id, False)
                return

            # Build ProjectContext from ProjectConfig
            # ProjectConfig has: id, name, github_org, github_repo, tech_stacks, etc.
            # ProjectContext needs: id, name, display_name, repository_url, default_branch, etc.
            repo_url = f"https://github.com/{project_config.github_org}/{project_config.github_repo}.git"
            project_context = ProjectContext(
                id=project_config.id,
                name=project_config.name,
                display_name=project_config.name,
                repository_url=repo_url,
                default_branch="main",
                branch_prefix="feature/",
                tech_stack=list(project_config.tech_stacks.keys()) if project_config.tech_stacks else [],
                primary_language="python",
                test_command=project_config.testing.get("command") if project_config.testing else None,
                test_framework=project_config.testing.get("framework") if project_config.testing else None,
                has_ci_cd=bool(project_config.testing.get("ci_cd", False)) if project_config.testing else False,
                default_workflow_template_id="default",
                custom_workflows={},
                has_dockerfile=False,
                dockerfile_path=None,
                requires_dev_container=False,
                environment_variables=dict(project_config.environment_variables or {}),
                secrets=[],
                mcp_servers=[],
                metadata={},
                created_at=project_config.created_at or datetime.now(UTC),
                updated_at=project_config.updated_at or datetime.now(UTC),
            )

            # Step 3: Clone repository (synthetic path for simulation)
            repo_path = f"/workspace/{work_item_id}"
            try:
                await self._vcs.clone_repository(repo_url, repo_path)
            except Exception as e:
                logger.warning(
                    f"VCS clone failed (non-fatal in simulation): {e}",
                    extra={"error_id": "ERR_EXEC_CHAIN_VCS_CLONE_FAILURE"},
                )
                # In simulation, continue even if clone "fails" (path may already exist)

            # Step 4: Route workspace
            try:
                workspace = await self._workspace_router.route_workspace(work_item, agent, project_context)
            except Exception as e:
                logger.error(
                    f"Workspace routing failed for '{work_item_id}': {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_EXEC_CHAIN_WORKSPACE_ROUTE_FAILURE"},
                )
                await self._call_completion(work_item_id, board_id, False)
                return

            # Step 5: Track branch
            if workspace.branch_name:
                await self._branch_tracker.set_branch(work_item_id, workspace.branch_name)

            # Step 6: Prepare workspace
            prep_result = await self._workspace_router.prepare_workspace(
                workspace, project_context, work_item, repo_path
            )
            if not prep_result.success:
                logger.error(
                    f"Workspace preparation failed for '{work_item_id}': {prep_result.reason}",
                    extra={"error_id": "ERR_EXEC_CHAIN_WORKSPACE_PREPARE_FAILURE"},
                )
                await self._call_completion(work_item_id, board_id, False)
                return

            # Step 7: Build execution context
            context = ExecutionContextBuilder.build_context(
                work_item=work_item,
                workflow_id=run_info.run_id,
                stage_name=run_info.stage_name,
                agent=agent,
                project=project_context,
                workspace=workspace,
            )

            # Step 8: Create and start execution
            prompt = (
                f"Process work item {work_item_id}: "
                f"{getattr(work_item, 'title', work_item_id)} "
                f"— stage: {run_info.stage_name}"
            )
            execution = await self._execution_service.create_execution(
                agent=agent,
                work_item=work_item,
                workflow_id=run_info.run_id,
                stage_name=run_info.stage_name,
                prompt=prompt,
            )
            start_result = await self._execution_service.start_execution(execution, context)
            if not start_result.success:
                logger.error(
                    f"Failed to start execution for '{work_item_id}': {start_result.error}",
                    extra={"error_id": "ERR_EXEC_CHAIN_EXECUTION_START_FAILURE"},
                )
                await self._workspace_router.finalize_workspace(
                    workspace, project_context, {"success": False}, repo_path
                )
                await self._call_completion(work_item_id, board_id, False)
                return

            # Step 9: Execute via LLM or Container
            if agent.requires_docker:
                container_config = ContainerConfig(
                    image="codetoreum-agent:latest",
                    working_dir="/workspace",
                )
                exec_result = await self._execution_service.execute_with_container(execution, context, container_config)
            else:
                exec_result = await self._execution_service.execute_with_llm(execution, context)

            # Step 10: Finalize workspace
            await self._workspace_router.finalize_workspace(
                workspace,
                project_context,
                {"success": exec_result.success, "output": getattr(exec_result.execution, "output", "")},
                repo_path,
            )

            # Step 11: Clear registry
            await self._run_registry.clear_run(work_item_id)
            await self._branch_tracker.clear(work_item_id)

            success = exec_result.success
            logger.info(
                f"ExecutionServiceAgentExecutor: '{agent_id}' completed for '{work_item_id}' " f"(success={success})"
            )

        except asyncio.CancelledError:
            logger.info(f"ExecutionServiceAgentExecutor: execution cancelled for '{work_item_id}'")
            raise
        except Exception as e:
            logger.error(
                f"ExecutionServiceAgentExecutor: unexpected error for '{work_item_id}': {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXEC_CHAIN_UNEXPECTED_FAILURE"},
            )
            success = False
        finally:
            if not success:
                # Clean up registry on failure
                try:
                    await self._run_registry.clear_run(work_item_id)
                    await self._branch_tracker.clear(work_item_id)
                except Exception:
                    logger.error(
                        f"Failed to clean up registry/branch-tracker for '{work_item_id}' "
                        "after execution failure — work item may be stuck",
                        exc_info=True,
                        extra={"error_id": "ERR_EXEC_CHAIN_CLEANUP_FAILURE"},
                    )

        await self._call_completion(work_item_id, board_id, success)

    async def _call_completion(self, work_item_id: str, board_id: str, success: bool) -> None:
        """Invoke completion callback with error handling.

        Args:
            work_item_id: Work item that completed
            board_id: Board identifier
            success: Whether execution succeeded
        """
        if self._completion_callback:
            try:
                await self._completion_callback(work_item_id, board_id, success)
            except Exception as e:
                logger.error(
                    f"Completion callback failed for '{work_item_id}': {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_EXEC_CHAIN_COMPLETION_CALLBACK_FAILURE"},
                )
        else:
            logger.warning(
                f"No completion callback set for ExecutionServiceAgentExecutor. "
                f"Work item '{work_item_id}' completed but auto-progression will not occur."
            )
