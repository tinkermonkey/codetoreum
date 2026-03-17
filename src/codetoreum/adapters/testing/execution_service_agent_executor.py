"""ExecutionServiceAgentExecutor - wires IAgentExecutor to ExecutionService chain.

This adapter drives the full LLM → Container → VCS chain in simulation by
integrating with ExecutionService, WorkspaceRouter, and supporting repositories.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from codetoreum.domain.project_context import ProjectContext
from codetoreum.domain.services.execution_context_builder import ExecutionContextBuilder
from codetoreum.domain.types import WorkItemId
from codetoreum.domain.value_objects import ContainerConfig
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.output.agent_executor import IAgentExecutor

if TYPE_CHECKING:
    from codetoreum.application.agent_execution_recovery_service import (
        AgentExecutionRecoveryService,
    )
    from codetoreum.application.execution_service import ExecutionService
    from codetoreum.application.workspace_router import WorkspaceRouter
    from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
    from codetoreum.ports.output.active_workflow_run_registry import IActiveWorkflowRunRegistry
    from codetoreum.ports.output.agent_repository import IAgentRepository
    from codetoreum.ports.output.config_store import IConfigStore
    from codetoreum.ports.output.version_control_service import IVersionControlService
    from codetoreum.ports.output.work_item_branch_tracker import IWorkItemBranchTracker
    from codetoreum.ports.output.work_item_service import IWorkItemService

logger = logging.getLogger(__name__)


@dataclass
class ActiveExecutionInfo:
    """Metadata about an in-progress agent execution.

    Exposed by ExecutionServiceAgentExecutor.get_active_executions() for use by
    the ExecutionTimeoutWatchdog to detect and cancel timed-out executions.

    Attributes:
        execution_id: Unique ID for this execution
        work_item_id: Work item being processed
        started_at: When execution started (UTC)
        timeout_seconds: Timeout threshold (from Agent.timeout_seconds)
        task: The running asyncio.Task for cancellation
    """

    execution_id: str
    work_item_id: str
    started_at: datetime
    timeout_seconds: int
    task: asyncio.Task


class ExecutionServiceAgentExecutor(IAgentExecutor):
    """Wires IAgentExecutor → ExecutionService → LLM/Container/VCS chain.

    This adapter drives the full execution chain when ExecutionServiceAgentExecutor
    is active. It replaces MockAgentExecutor for end-to-end testing. The chain:
    1.  Looks up active run from registry (set by BoardColumnEventHandler)
    2.  Loads domain objects (Agent, WorkItem, ProjectConfig → ProjectContext)
    3.  Clones repository (synthetic path in simulation)
    4.  Routes workspace
    5.  Tracks branch in IWorkItemBranchTracker
    6.  Prepares workspace (writes context files, etc.)
    7.  Builds execution context via ExecutionContextBuilder
    8.  Creates execution via ExecutionService
    9.  Starts execution and validates start result
    10. Executes via LLM path (default) or Container path (requires_docker=True)
    11. Finalizes workspace, clears registry/branch-tracker, calls completion callback
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
        clock: SimulationClock | None = None,
        recovery_service: AgentExecutionRecoveryService | None = None,
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
            clock: SimulationClock for consistent time tracking in simulation
                (if None, creates a default SimulationClock instance)
            recovery_service: Service for handling completion callback failures
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
        # Create default clock if not provided (for backward compatibility with tests)
        if clock is None:
            clock = SimulationClock()
        self._clock = clock
        self._recovery_service = recovery_service
        self._execution_delay = execution_delay

        self._completion_callback: Callable[[str, str, bool], Coroutine[Any, Any, None]] | None = None
        self._default_board_id = "board-1"
        self._executions: list[dict[str, Any]] = []
        self._pending_tasks: set[asyncio.Task] = set()
        # Track active executions: task -> ActiveExecutionInfo mapping
        self._active_executions: dict[asyncio.Task, ActiveExecutionInfo] = {}

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

    def _task_done_callback(self, task: asyncio.Task[None]) -> None:
        """Handle completion of fire-and-forget execution task.

        Called when asyncio.create_task() completes. Surfaces any unhandled
        exceptions that occurred during _run_execution so they are not
        silently lost. This follows the bootstrap pattern used in
        bootstrap.py:1309-1329 for board event bridge tasks.

        Also cleans up execution tracking to avoid memory leaks.

        Args:
            task: The completed asyncio.Task
        """
        self._pending_tasks.discard(task)
        self._active_executions.pop(task, None)  # Clean up execution tracking
        try:
            task.result()
        except asyncio.CancelledError:
            # Task was cancelled — normal during shutdown or by watchdog
            pass
        except Exception as task_exception:
            # Unhandled exception in _run_execution (e.g., recovery service failure)
            # This logs the failure so it's not silently swallowed
            logger.error(
                f"Unhandled exception in ExecutionServiceAgentExecutor background task: {task_exception}",
                exc_info=True,
                extra={
                    "error_type": type(task_exception).__name__,
                    "error_id": ErrorRegistry.ERR_AGENT_EXECUTION_ERROR,
                },
            )

    @property
    def executions(self) -> list[dict[str, Any]]:
        """Return recorded executions for test assertions."""
        return list(self._executions)

    def get_active_executions(self) -> list[ActiveExecutionInfo]:
        """Return snapshot of all in-progress executions for watchdog use.

        This provides read-only access to active execution metadata without exposing
        the internal task tracking dict. Used by ExecutionTimeoutWatchdog to detect
        and cancel timed-out executions.

        Returns:
            List of ActiveExecutionInfo objects for each in-progress execution
        """
        return list(self._active_executions.values())

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
        # Use clock.now() for consistent time tracking with watchdog timeout checks
        now = self._clock.now()

        # Get active run to obtain workflow_id and stage_name
        run_info = await self._run_registry.get_active_run(work_item_id)
        workflow_id = run_info.run_id if run_info else "unknown"
        stage_name = run_info.stage_name if run_info else "unknown"

        # Use a default timeout for the watchdog; _run_execution() will load the actual agent
        # with its configured timeout. This avoids duplicate agent loads on every execution.
        timeout_seconds = 3600  # Default 1 hour

        # Generate execution ID for tracking
        execution_id = f"{work_item_id}-{agent_id}-{now.timestamp()}"

        self._executions.append(
            {
                "work_item_id": work_item_id,
                "agent_id": agent_id,
                "board_id": resolved_board_id,
                "started_at": now.isoformat(),
                "workflow_id": workflow_id,
                "stage_name": stage_name,
            }
        )

        logger.info(f"ExecutionServiceAgentExecutor: scheduling agent '{agent_id}' for '{work_item_id}'")

        task = asyncio.create_task(self._run_execution(work_item_id, agent_id, resolved_board_id))
        self._pending_tasks.add(task)

        # Track active execution for timeout watchdog
        self._active_executions[task] = ActiveExecutionInfo(
            execution_id=execution_id,
            work_item_id=work_item_id,
            started_at=now,
            timeout_seconds=timeout_seconds,
            task=task,
        )

        task.add_done_callback(self._task_done_callback)

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
            repo_url = f"https://github.com/{project_config.github_org}/" f"{project_config.github_repo}.git"
            project_context = ProjectContext(
                id=project_config.id,
                name=project_config.name,
                display_name=project_config.name,
                repository_url=repo_url,
                default_branch="main",
                branch_prefix="feature/",
                tech_stack=(list(project_config.tech_stacks.keys()) if project_config.tech_stacks else []),
                primary_language="python",
                test_command=(project_config.testing.get("command") if project_config.testing else None),
                test_framework=(project_config.testing.get("framework") if project_config.testing else None),
                has_ci_cd=(bool(project_config.testing.get("ci_cd", False)) if project_config.testing else False),
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
                    exc_info=True,
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
                try:
                    await self._branch_tracker.set_branch(work_item_id, workspace.branch_name)
                except Exception as e:
                    logger.error(
                        f"Branch tracker set_branch failed for '{work_item_id}': {e}",
                        exc_info=True,
                        extra={"error_id": "ERR_EXEC_CHAIN_BRANCH_TRACKER_FAILURE"},
                    )
                    await self._call_completion(work_item_id, board_id, False)
                    return

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

            # Step 8: Create execution
            prompt = (
                f"Process work item {work_item_id}: "
                f"{getattr(work_item, 'title', work_item_id)} "
                f"— stage: {run_info.stage_name}"
            )
            try:
                execution = await self._execution_service.create_execution(
                    agent=agent,
                    work_item=work_item,
                    workflow_id=run_info.run_id,
                    stage_name=run_info.stage_name,
                    prompt=prompt,
                )
            except Exception as e:
                logger.error(
                    f"create_execution failed for '{work_item_id}': {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_EXEC_CHAIN_CREATE_EXECUTION_FAILURE"},
                )
                await self._workspace_router.finalize_workspace(
                    workspace, project_context, {"success": False}, repo_path
                )
                await self._call_completion(work_item_id, board_id, False)
                return

            # Step 9: Start execution
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

            # Step 10: Execute via LLM or Container
            exec_result = None
            try:
                if agent.requires_docker:
                    container_config = ContainerConfig(
                        image="codetoreum-agent:latest",
                        working_dir="/workspace",
                    )
                    exec_result = await self._execution_service.execute_with_container(
                        execution, context, container_config
                    )
                else:
                    exec_result = await self._execution_service.execute_with_llm(execution, context)
            except Exception as exec_err:
                logger.error(
                    f"ExecutionServiceAgentExecutor: execution call failed for '{work_item_id}': {exec_err}",
                    exc_info=True,
                    extra={"error_id": "ERR_EXEC_CHAIN_EXECUTION_FAILURE"},
                )

            # Step 11: Finalize workspace (always runs, even on execution failure,
            # to avoid stuck workspace)
            exec_succeeded = exec_result is not None and exec_result.success
            try:
                await self._workspace_router.finalize_workspace(
                    workspace,
                    project_context,
                    {
                        "success": exec_succeeded,
                        "output": (getattr(exec_result.execution, "output", "") if exec_result else ""),
                    },
                    repo_path,
                )
            except Exception as finalize_err:
                logger.error(
                    f"ExecutionServiceAgentExecutor: finalize_workspace failed for '{work_item_id}': {finalize_err}",
                    exc_info=True,
                    extra={"error_id": "ERR_EXEC_CHAIN_FINALIZE_FAILURE"},
                )

            success = exec_succeeded
            logger.info(
                f"ExecutionServiceAgentExecutor: '{agent_id}' completed for '{work_item_id}' (success={success})"
            )

        except asyncio.CancelledError:
            logger.info(f"ExecutionServiceAgentExecutor: execution cancelled for '{work_item_id}'")
            await self._call_completion(work_item_id, board_id, False)
            raise
        except Exception as e:
            logger.error(
                f"ExecutionServiceAgentExecutor: unexpected error for '{work_item_id}': {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXEC_CHAIN_UNEXPECTED_FAILURE"},
            )
            success = False
        finally:
            # Always clean up registry and branch tracker (avoids double-clear and
            # stuck state)
            try:
                await self._run_registry.clear_run(work_item_id)
                await self._branch_tracker.clear(work_item_id)
            except Exception:
                logger.error(
                    f"Failed to clean up registry/branch-tracker for '{work_item_id}' "
                    "after execution — work item may be stuck",
                    exc_info=True,
                    extra={"error_id": "ERR_EXEC_CHAIN_CLEANUP_FAILURE"},
                )

        await self._call_completion(work_item_id, board_id, success)

    async def _call_completion(self, work_item_id: str, board_id: str, success: bool) -> None:
        """Invoke completion callback with error handling and recovery.

        If the completion callback (auto-progression) fails, the work item is stuck
        in its current column. This method handles recovery via:
        1. Logging the failure with full context
        2. Using AgentExecutionRecoveryService to queue for manual recovery
        3. Failing the workflow run to signal pipeline blockage

        If the recovery service itself fails, the exception is caught and logged
        to prevent it from propagating unhandled through the fire-and-forget task.

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
                # Use recovery service to handle the failure (queue for manual recovery,
                # fail workflow)
                if self._recovery_service:
                    try:
                        await self._recovery_service.handle_completion_callback_failure(
                            work_item_id=work_item_id,
                            board_id=board_id,
                            success=success,
                            error=e,
                        )
                    except Exception as recovery_error:
                        # Recovery service itself failed (e.g., DLQ add failure,
                        # fail_workflow failure)
                        # Log this failure to prevent silent loss in fire-and-forget task
                        logger.error(
                            f"Recovery service failed for '{work_item_id}' after completion callback failure: {recovery_error}",
                            exc_info=True,
                            extra={"error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR},
                        )
        else:
            logger.error(
                f"No completion callback set for ExecutionServiceAgentExecutor. "
                f"Work item '{work_item_id}' completed with success={success} but auto-progression will not occur. "
                f"Call set_completion_handler() to wire the callback before executing.",
                extra={"error_id": "ERR_EXEC_CHAIN_NO_COMPLETION_CALLBACK"},
            )
