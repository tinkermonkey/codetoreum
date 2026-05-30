"""ExecutionServiceAgentExecutor - wires IAgentExecutor to ExecutionService chain.

This adapter drives the full LLM → Container → VCS chain in both simulation and
production by integrating with ExecutionService, WorkspaceRouter, and supporting repositories.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from codetoreum.domain.events import AgentExecutionCompletedEvent, now_iso
from codetoreum.domain.project_context import ProjectContext
from codetoreum.domain.services.execution_context_builder import ExecutionContextBuilder
from codetoreum.domain.types import WorkItemId
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.ports.output.agent_executor import IAgentExecutor
from codetoreum.ports.output.coding_agent import CodingAgentInvocationOptions

if TYPE_CHECKING:
    from codetoreum.application.agent_execution_recovery_service import (
        AgentExecutionRecoveryService,
    )
    from codetoreum.application.execution_service import ExecutionService
    from codetoreum.application.workspace_router import WorkspaceRouter
    from codetoreum.infrastructure.event_bus import EventBus
    from codetoreum.infrastructure.simulation.simulation_clock import ClockProtocol
    from codetoreum.ports.output.active_workflow_run_registry import IActiveWorkflowRunRegistry
    from codetoreum.ports.output.agent_repository import IAgentRepository
    from codetoreum.ports.output.config_store import IConfigStore
    from codetoreum.ports.output.version_control_service import IVersionControlService
    from codetoreum.ports.output.work_item_branch_tracker import IWorkItemBranchTracker
    from codetoreum.ports.output.work_item_service import IWorkItemService
    from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService

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
    10. Executes via ExecutionService.execute() (the unified D4 path that
        delegates to ICodingAgent — adapter owns the invocation-mode decision)
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
        clock: ClockProtocol,
        event_bus: EventBus,
        recovery_service: AgentExecutionRecoveryService | None = None,
        execution_delay: float = 0.0,
        workflow_config_service: IWorkflowConfigService | None = None,
        workspace_base_dir: str = "/workspace",
        default_board_id: str = "board-1",
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
            clock: Clock implementation (IClock protocol) for time tracking
            event_bus: Event bus used to publish AgentExecutionCompletedEvent
                when the executor finishes processing a work item. The previous
                set_completion_handler callback mechanism has been replaced; the
                event bus is now the sole channel for executor → BEH
                auto-progression signalling.
            recovery_service: Service for handling completion publish failures
            execution_delay: Optional delay (seconds) before execution for testing
            workflow_config_service: Optional service for fetching workflow templates
            workspace_base_dir: Base directory for cloned repositories. Defaults to
                /workspace (the Docker container mount point). Override in simulation
                with a tempfile path so tests don't require root access.
            default_board_id: Board id published with the completion event when
                the active run registry has no board context (defensive fallback).
        """
        self._execution_service = execution_service
        self._workspace_router = workspace_router
        self._config_store = config_store
        self._agent_repository = agent_repository
        self._work_item_service = work_item_service
        self._run_registry = run_registry
        self._branch_tracker = branch_tracker
        self._vcs = vcs
        self._clock = clock
        self._event_bus = event_bus
        self._recovery_service = recovery_service
        self._execution_delay = execution_delay
        self._workflow_config_service = workflow_config_service
        self._workspace_base_dir = workspace_base_dir

        self._default_board_id = default_board_id
        self._executions: list[dict[str, Any]] = []
        self._pending_tasks: set[asyncio.Task] = set()
        # Track active executions: task -> ActiveExecutionInfo mapping
        self._active_executions: dict[asyncio.Task, ActiveExecutionInfo] = {}
        # Guard against double-dispatch: set of work_item_ids currently being executed
        self._executing_work_items: set[str] = set()

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
        info = self._active_executions.pop(task, None)  # Clean up execution tracking
        if info:
            self._executing_work_items.discard(info.work_item_id)
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

        if work_item_id in self._executing_work_items:
            logger.warning(
                f"ExecutionServiceAgentExecutor: work item '{work_item_id}' already executing, "
                "ignoring duplicate execute() call",
                extra={"error_id": "ERR_EXEC_DUPLICATE_EXECUTION", "work_item_id": work_item_id},
            )
            return

        # Use clock.now() for consistent time tracking with watchdog timeout checks
        now = self._clock.now()

        # Get active run to obtain workflow_id and stage_name
        run_info = await self._run_registry.get_active_run(work_item_id)
        workflow_id = run_info.run_id if run_info else "unknown"
        stage_name = run_info.stage_name if run_info else "unknown"

        # Load agent to get its configured timeout
        # This ensures the watchdog respects the agent's timeout instead of using a default.
        timeout_seconds = 3600  # Fallback default (1 hour) if agent load fails
        try:
            agent = await self._agent_repository.get_by_id(agent_id)
            timeout_seconds = agent.invocation.timeout_seconds
        except Exception as e:
            logger.warning(
                f"Failed to load agent '{agent_id}' for timeout in execute(): {e}, "
                f"falling back to {timeout_seconds}s default",
                exc_info=True,
            )

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

        self._executing_work_items.add(work_item_id)
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
            board_id: Board identifier (used as fallback if run_info is not available)
        """
        success = False
        resolved_board_id = board_id  # fallback; overridden by run_info below
        run_info = None
        try:
            if self._execution_delay > 0:
                await asyncio.sleep(self._execution_delay)

            # Step 1: Look up active run
            run_info = await self._run_registry.get_active_run(work_item_id)
            if run_info is None:
                logger.error(
                    f"No active run found for work item '{work_item_id}'. Cannot execute.",
                    extra={"error_id": ErrorRegistry.ERR_EXEC_CHAIN_NO_ACTIVE_RUN},
                )
                await self._call_completion(work_item_id, board_id, False)
                return

            # Resolve board_id dynamically from run_info instead of using static default
            resolved_board_id = run_info.board_id

            # Step 2: Load domain objects
            try:
                agent = await self._agent_repository.get_by_id(agent_id)
            except Exception as e:
                logger.error(
                    f"Failed to load agent '{agent_id}': {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_EXEC_CHAIN_AGENT_LOAD_FAILURE},
                )
                await self._call_completion(work_item_id, resolved_board_id, False)
                return

            try:
                work_item = await self._work_item_service.get_work_item(WorkItemId(work_item_id))
            except Exception as e:
                logger.error(
                    f"Failed to load work item '{work_item_id}': {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_EXEC_CHAIN_WORK_ITEM_LOAD_FAILURE},
                )
                await self._call_completion(work_item_id, resolved_board_id, False)
                return

            # Advance work item lifecycle to IN_PROGRESS before execution starts.
            # assign_agent() transitions NEW → ASSIGNED, start() transitions ASSIGNED → IN_PROGRESS.
            try:
                await self._work_item_service.transition_to_in_progress(work_item_id, agent.id)
                # Reload so downstream logic sees the updated status.
                work_item = await self._work_item_service.get_work_item(WorkItemId(work_item_id))
            except Exception as e:
                logger.warning(
                    f"Could not advance lifecycle for '{work_item_id}' to IN_PROGRESS: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_EXEC_CHAIN_LIFECYCLE_ADVANCE_FAILURE"},
                )

            try:
                project_config = await self._config_store.get_project_config(run_info.project_id)
            except Exception as e:
                logger.error(
                    f"Failed to load project config '{run_info.project_id}': {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_EXEC_CHAIN_PROJECT_CONFIG_LOAD_FAILURE},
                )
                await self._call_completion(work_item_id, resolved_board_id, False)
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

            # Step 3: Clone repository
            repo_path = f"{self._workspace_base_dir}/{work_item_id}"
            try:
                await self._vcs.clone_repository(repo_url, repo_path)
            except Exception as e:
                logger.error(
                    f"VCS clone failed for '{work_item_id}': {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_EXEC_CHAIN_VCS_CLONE_FAILURE},
                )
                await self._call_completion(work_item_id, resolved_board_id, False)
                return

            # Step 4: Route workspace
            try:
                workspace = await self._workspace_router.route_workspace(work_item, agent, project_context)
            except Exception as e:
                logger.error(
                    f"Workspace routing failed for '{work_item_id}': {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_EXEC_CHAIN_WORKSPACE_ROUTE_FAILURE},
                )
                await self._call_completion(work_item_id, resolved_board_id, False)
                return

            # Step 5: Track branch
            if workspace.branch_name:
                try:
                    await self._branch_tracker.set_branch(work_item_id, workspace.branch_name)
                except Exception as e:
                    logger.error(
                        f"Branch tracker set_branch failed for '{work_item_id}': {e}",
                        exc_info=True,
                        extra={"error_id": ErrorRegistry.ERR_EXEC_CHAIN_BRANCH_TRACKER_FAILURE},
                    )
                    await self._call_completion(work_item_id, resolved_board_id, False)
                    return

            # Step 6: Prepare workspace
            prep_result = await self._workspace_router.prepare_workspace(
                workspace, project_context, work_item, repo_path
            )
            if not prep_result.success:
                logger.error(
                    f"Workspace preparation failed for '{work_item_id}': {prep_result.reason}",
                    extra={"error_id": ErrorRegistry.ERR_EXEC_CHAIN_WORKSPACE_PREPARE_FAILURE},
                )
                await self._call_completion(work_item_id, resolved_board_id, False)
                return

            # Step 7: Build execution context — pass repo_path so ExecutionService
            # can commit the workspace without re-querying WorkspaceRouter.
            context = ExecutionContextBuilder.build_context(
                work_item=work_item,
                workflow_id=run_info.run_id,
                stage_name=run_info.stage_name,
                agent=agent,
                project=project_context,
                workspace=workspace,
                repository_path=repo_path,
            )

            # Step 8: Build comprehensive prompt and create execution
            try:
                # workflow_template fetching retired in Phase D5 — the
                # legacy PromptBuilder.build_prompt consumed it. The new
                # IPromptBuilder receives stage info through WorkspaceContext,
                # so the workflow_config_service lookup is now moot here.

                # Try to load previous stage output from context directory
                # (forwarded to the coding-agent adapter via WorkspaceContext).
                previous_output = None
                try:
                    context_file = Path(repo_path) / "context" / "previous_stage.txt"
                    exists = await asyncio.to_thread(context_file.exists)
                    if exists:
                        previous_output = await asyncio.to_thread(context_file.read_text, encoding="utf-8")
                except OSError as e:
                    logger.warning(f"Failed to read previous stage output: {e}", exc_info=True)

                # Phase D5: legacy PromptBuilder.build_prompt retired. The
                # coding-agent adapter now invokes IPromptBuilder.build()
                # internally with the WorkspaceContext + execution metadata,
                # so this seam only needs a placeholder value for the
                # AgentExecution.prompt field (kept for audit-trail
                # serialization).
                _ = previous_output  # consumed by the coding-agent adapter via WorkspaceContext
                prompt = f"[stage:{run_info.stage_name}] agent={agent.name} work_item={work_item_id}"

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
                    extra={"error_id": ErrorRegistry.ERR_EXEC_CHAIN_CREATE_EXECUTION_FAILURE},
                )
                await self._workspace_router.finalize_workspace(
                    workspace, project_context, {"success": False}, repo_path
                )
                await self._call_completion(work_item_id, resolved_board_id, False)
                return

            # Step 9: Start execution
            start_result = await self._execution_service.start_execution(execution, context)
            if not start_result.success:
                logger.error(
                    f"Failed to start execution for '{work_item_id}': {start_result.error}",
                    extra={"error_id": ErrorRegistry.ERR_EXEC_CHAIN_EXECUTION_START_FAILURE},
                )
                await self._workspace_router.finalize_workspace(
                    workspace, project_context, {"success": False}, repo_path
                )
                await self._call_completion(work_item_id, resolved_board_id, False)
                return

            # Step 10: Dispatch via the unified ExecutionService.execute() path
            # (Phase D4). The coding-agent adapter owns the invocation-mode
            # decision. D6: invocation options are now sourced directly from
            # `agent.invocation` (populated by the bootstrap loader from the
            # new schema) — no more requires_docker bridge.
            invocation_options = self._build_invocation_options(agent, context)
            # D6: populate WorkspaceContext.workspace_path so the coding-agent
            # adapter / strategies can resolve the cloned repo location
            # (mount target for containerised mode, cwd for host mode).
            workspace = workspace.with_workspace_path(Path(repo_path))
            exec_result = None
            try:
                exec_result = await self._execution_service.execute(
                    execution,
                    context,
                    workspace,
                    invocation_options,
                )
            except Exception as exec_err:
                logger.error(
                    f"ExecutionServiceAgentExecutor: execution call failed for '{work_item_id}': {exec_err}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_EXEC_CHAIN_EXECUTION_FAILURE},
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
                    extra={"error_id": ErrorRegistry.ERR_EXEC_CHAIN_FINALIZE_FAILURE},
                )

            success = exec_succeeded
            logger.info(
                f"ExecutionServiceAgentExecutor: '{agent_id}' completed for '{work_item_id}' (success={success})"
            )

        except asyncio.CancelledError:
            logger.info(f"ExecutionServiceAgentExecutor: execution cancelled for '{work_item_id}'")
            await self._call_completion(work_item_id, resolved_board_id, False)
            raise
        except Exception as e:
            logger.error(
                f"ExecutionServiceAgentExecutor: unexpected error for '{work_item_id}': {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_EXEC_CHAIN_UNEXPECTED_FAILURE},
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
                    extra={"error_id": ErrorRegistry.ERR_EXEC_CHAIN_CLEANUP_FAILURE},
                )

        await self._call_completion(
            work_item_id, resolved_board_id, success, project_id=run_info.project_id if run_info else None
        )

    @staticmethod
    def _build_invocation_options(
        agent: Any,
        context: Any,
    ) -> CodingAgentInvocationOptions:
        """Translate the agent + context into a :class:`CodingAgentInvocationOptions`.

        D6: reads ``agent.invocation`` (populated by the bootstrap loader
        from the new schema — proposal §3h) directly. The mode, model,
        timeout, and mode_config flow straight through to the
        coding-agent adapter. ``cost_limit_usd`` flows through too when
        the agent config supplied one.

        Raises:
            ValueError: When the agent has no ``invocation`` block. The
                bootstrap loader rejects this shape at load time, so the
                only way to reach this branch is via an agent persisted
                under the legacy schema that hasn't been re-registered;
                surface a clear error rather than silently choosing a
                mode.
        """
        invocation = getattr(agent, "invocation", None)
        if invocation is None:
            agent_id = getattr(agent, "id", None) or getattr(agent, "name", "<unknown>")
            msg = (
                f"Agent '{agent_id}' has no `invocation` config (D6). "
                "Re-register the agent through bootstrap/register_project.py "
                "with the new schema (coding_agent + invocation block)."
            )
            raise ValueError(msg)

        return CodingAgentInvocationOptions(
            invocation_mode=invocation.mode,
            model=invocation.model,
            timeout_seconds=invocation.timeout_seconds,
            cost_limit_usd=invocation.cost_limit_usd,
            mode_config=dict(invocation.mode_config),
        )

    async def _call_completion(
        self,
        work_item_id: str,
        board_id: str,
        success: bool,
        project_id: str | None = None,
        error_summary: str | None = None,
    ) -> None:
        """Publish AgentExecutionCompletedEvent so BoardColumnEventHandler can auto-progress.

        Previously this method invoked a `set_completion_handler` callback. The
        event bus replaces that callback: `BoardColumnEventHandler` subscribes to
        `AgentExecutionCompletedEvent` and runs the same auto-progression logic.

        **Scheduling**: The publish is dispatched via `asyncio.create_task` and
        NOT awaited here. Awaiting would keep `_run_execution` (and therefore the
        outer `_executing_work_items` membership) alive across the BEH handler
        chain — which calls `board.move_item_to_column`, schedules a deferred
        bridge task, and yields control. Any deferred bridge task from an earlier
        move can then run before the executor's task completes, hit
        `LockStatus.ALREADY_HELD`, and re-trigger the agent — turning a single
        auto-progression into a loop. Detaching the publish lets the executor's
        task complete (and clear its `_executing_work_items` entry) before the
        BEH handler runs, matching the timing of the original
        `set_completion_handler` callback path.

        **Failure handling**: A done-callback inspects the publish task's result.
        If it failed, the recovery service is invoked from within the callback —
        this preserves the recovery semantics the old callback path had, even
        though the publish is no longer awaited inline.

        Args:
            work_item_id: Work item that completed
            board_id: Board identifier
            success: Whether execution succeeded
            project_id: Optional project id for recovery service context
            error_summary: Optional short error description (None on success)
        """
        event = AgentExecutionCompletedEvent(
            type="agent_execution.completed",
            timestamp=now_iso(),
            source="execution_service_agent_executor",
            work_item_id=work_item_id,
            board_id=board_id,
            success=success,
            error_summary=error_summary,
        )

        publish_task = asyncio.create_task(self._event_bus.publish(event))
        # Track the task so it isn't garbage-collected mid-flight; the done-callback
        # discards it from the set once it finishes.
        self._pending_tasks.add(publish_task)

        def _on_publish_done(t: asyncio.Task[None]) -> None:
            self._pending_tasks.discard(t)
            try:
                exc = t.exception()
            except asyncio.CancelledError:
                return
            if exc is None:
                return
            logger.error(
                f"Publishing AgentExecutionCompletedEvent failed for '{work_item_id}': {exc}",
                exc_info=exc,
                extra={"error_id": ErrorRegistry.ERR_EXEC_CHAIN_COMPLETION_CALLBACK_FAILURE},
            )
            if not self._recovery_service:
                return
            # Recovery is async; schedule it as its own task. We can't await here
            # because we're inside a sync done-callback.
            recovery_coro = self._recovery_service.handle_completion_callback_failure(
                work_item_id=work_item_id,
                board_id=board_id,
                success=success,
                error=exc,
                project_id=project_id,
            )
            recovery_task = asyncio.create_task(recovery_coro)
            self._pending_tasks.add(recovery_task)

            def _on_recovery_done(rt: asyncio.Task[None]) -> None:
                self._pending_tasks.discard(rt)
                try:
                    rexc = rt.exception()
                except asyncio.CancelledError:
                    return
                if rexc is not None:
                    logger.error(
                        f"Recovery service failed for '{work_item_id}' after completion publish failure: {rexc}",
                        exc_info=rexc,
                        extra={"error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR},
                    )

            recovery_task.add_done_callback(_on_recovery_done)

        publish_task.add_done_callback(_on_publish_done)
