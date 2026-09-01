"""Execution Service application service."""

import logging
from dataclasses import dataclass
from enum import Enum

from codetoreum.domain.agent import Agent, CommitPolicy
from codetoreum.domain.agent_execution import AgentExecution, ExecutionStatus
from codetoreum.domain.exceptions import DomainError
from codetoreum.domain.value_objects import (
    ExecutionContext,
)
from codetoreum.domain.work_item import WorkItem

# WorkspaceContext is referenced via typing only — keep it lazy to avoid
# tightening the domain import surface for callers that already pass it.
from codetoreum.domain.workspace_context import WorkspaceContext
from codetoreum.infrastructure.observability.instrumentation import (
    instrument_async_function,
)
from codetoreum.ports.exceptions import (
    ContainerExecutionError,
    ContainerTimeoutError,
    EventStoreError,
    ExternalServiceError,
    RateLimitError,
)
from codetoreum.ports.output import IEventStore
from codetoreum.ports.output.coding_agent import (
    CodingAgentInvocationOptions,
    CodingAgentResult,
    ICodingAgent,
)
from codetoreum.ports.output.version_control_service import IVersionControlService
from codetoreum.ports.output.work_execution_state_tracker import (
    IWorkExecutionStateTracker,
)

logger = logging.getLogger(__name__)


class ExecutionFailureReason(Enum):
    """Reasons for execution failure."""

    CONTAINER_ERROR = "container_error"
    LLM_ERROR = "llm_error"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    VALIDATION_ERROR = "validation_error"
    # D-J: agent produced output, but the post-execution VCS commit/push step
    # failed (e.g. branch refspec mismatch, remote rejected push). The agent
    # work is on the local workspace and may already be in a local commit; the
    # branch did NOT make it to the remote. Surfacing this as a distinct
    # failure_reason lets downstream handlers route to the on_failure_column
    # and avoid auto-progressing as if the work shipped successfully.
    WORKSPACE_COMMIT_ERROR = "workspace_commit_error"
    UNKNOWN = "unknown"


class WorkspaceCommitError(Exception):
    """Raised by :meth:`ExecutionService._commit_workspace` when commit/push fails.

    Carries the partial-progress signals (``commit_sha`` may be set when the
    local commit succeeded but the subsequent push to the remote failed) so
    the caller can include them on the failed ``ExecutionServiceResult`` —
    a human investigating the failure can find the local commit even though
    the branch never reached the remote. D-J.
    """

    def __init__(self, message: str, commit_sha: str | None = None, branch: str | None = None) -> None:
        super().__init__(message)
        self.commit_sha = commit_sha
        self.branch = branch


@dataclass
class ExecutionServiceResult:
    """Result from execution service operations."""

    success: bool
    execution: AgentExecution
    reason: str | None = None
    error: str | None = None
    failure_reason: ExecutionFailureReason | None = None
    commit_sha: str | None = None  # Git commit SHA produced; None if no file changes
    branch: str | None = None  # Branch pushed; None if no commit was made


class ExecutionService:
    """
    Application service for managing agent execution lifecycle.

    Responsibilities:
    - Create and initialize agent executions
    - Delegate execution to the injected ``ICodingAgent`` adapter
    - Commit workspace changes after a successful agent run
    - Persist lifecycle events (Initialized, Started, Completed, Failed,
      Cancelled) to the event store

    Container orchestration, log streaming, artifact upload, and token
    parsing all retired in Phase D5 — those concerns now live inside the
    coding-agent adapter (e.g. ``ClaudeCodeAdapter``'s containerized
    strategy and stream parser).
    """

    def __init__(
        self,
        coding_agent: ICodingAgent,
        event_store: IEventStore,
        execution_tracker: IWorkExecutionStateTracker,
        max_retries: int = 1,
        retry_delay_seconds: float = 5,
        vcs: IVersionControlService | None = None,
    ):
        """
        Initialize ExecutionService.

        Args:
            coding_agent: The :class:`ICodingAgent` adapter (Phase D3 port).
                Owns invocation-mode selection, prompt rendering, and the
                emission of granular ``CodingAgent*`` events.
            event_store: Event store for domain events
            execution_tracker: Execution state tracker for recovery hints
            max_retries: Maximum number of retry attempts (reserved — the
                new execute() path does not yet implement retries).
            retry_delay_seconds: Delay between retry attempts (reserved —
                see ``max_retries``).
            vcs: Version control service for post-execution commit+push.
                 When None the commit step is skipped (e.g. simulation
                 without VCS).
        """
        self.coding_agent: ICodingAgent = coding_agent
        self.event_store = event_store
        self.execution_tracker = execution_tracker
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self.vcs = vcs

        # Track active executions for cancel_execution lookups.
        self._active_executions: dict[str, AgentExecution] = {}

    @instrument_async_function(
        name="execution.create_execution",
        attributes={"service": "execution_service", "operation": "create"},
    )
    async def create_execution(
        self,
        agent: Agent,
        work_item: WorkItem,
        workflow_id: str,
        stage_name: str,
        prompt: str,
        previous_session_id: str | None = None,
    ) -> AgentExecution:
        """
        Create new agent execution.

        Args:
            agent: Agent to execute
            work_item: Work item being processed
            workflow_id: Workflow instance ID
            stage_name: Current pipeline stage
            prompt: Prompt for the agent
            previous_session_id: Optional session ID for continuity

        Returns:
            Created AgentExecution entity

        Raises:
            DomainError: If validation fails
        """
        try:
            execution = AgentExecution.create(
                agent_id=agent.id,
                work_item_id=work_item.id,
                workflow_id=workflow_id,
                stage_name=stage_name,
                prompt=prompt,
                model=agent.invocation.model,
                session_id=previous_session_id,
            )

            # Persist events
            events = execution.get_pending_events()
            for event in events:
                await self.event_store.append(execution.id, [event])
            execution.clear_events()

            logger.info(f"Created execution {execution.id} for agent {agent.name} on work item {work_item.id}")

            return execution

        except EventStoreError as e:
            logger.error(
                f"Failed to persist execution creation events: {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_CREATE_EVENT_STORE_FAILURE"},
            )
            raise
        except DomainError as e:
            logger.error(
                f"Failed to create execution (validation error): {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_CREATE_VALIDATION_FAILURE"},
            )
            raise

    @instrument_async_function(
        name="execution.start_execution",
        attributes={"service": "execution_service", "operation": "start"},
    )
    async def start_execution(
        self,
        execution: AgentExecution,
        context: ExecutionContext,
    ) -> ExecutionServiceResult:
        """
        Start agent execution.

        Args:
            execution: AgentExecution to start
            context: Execution context

        Returns:
            ExecutionServiceResult with outcome

        Raises:
            DomainError: If execution cannot be started
        """
        try:
            # Validate execution state
            if execution.status != ExecutionStatus.INITIALIZED:
                message = f"Execution {execution.id} is not in INITIALIZED state"
                raise DomainError(message)

            # Track as active
            self._active_executions[execution.id] = execution

            # Start execution. Container naming retired in D5 — the coding
            # agent adapter owns the invocation runtime (container, host,
            # API) and no longer surfaces a container name to lifecycle
            # callers. The legacy container_name argument to
            # AgentExecution.start is preserved as Optional and left None.
            execution.start(container_name=None)

            # Persist events
            events = execution.get_pending_events()
            for event in events:
                await self.event_store.append(execution.id, [event])
            execution.clear_events()

            # Write execution state for recovery fast-path lookups.
            # The recovery adapter uses this hint store to assess containers
            # at startup without replaying the full event stream.
            try:
                await self.execution_tracker.mark_execution_started(
                    project=context.project_id,
                    work_item_id=context.work_item_id,
                    agent=context.agent_id,
                )
            except Exception as e:
                logger.error(
                    f"Failed to update execution state tracker for execution {execution.id}: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_EXECUTION_TRACKER_UPDATE_FAILURE"},
                )
                # Don't fail the execution if tracking fails — it's only a hint.
                # Recovery will safely default to kill if no hint is found.

            logger.info(f"Started execution {execution.id}")

            return ExecutionServiceResult(
                success=True,
                execution=execution,
                reason="Execution started successfully",
            )

        except EventStoreError as e:
            logger.error(
                f"Failed to persist start event for execution {execution.id}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_START_EVENT_STORE_FAILURE"},
            )
            return ExecutionServiceResult(
                success=False,
                execution=execution,
                error=str(e),
                failure_reason=ExecutionFailureReason.UNKNOWN,
            )
        except DomainError as e:
            logger.error(
                f"Failed to start execution {execution.id} (validation error): {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_START_VALIDATION_FAILURE"},
            )
            return ExecutionServiceResult(
                success=False,
                execution=execution,
                error=str(e),
                failure_reason=ExecutionFailureReason.VALIDATION_ERROR,
            )

    @instrument_async_function(
        name="execution.execute",
        attributes={"service": "execution_service", "operation": "execute"},
    )
    async def execute(
        self,
        execution: AgentExecution,
        context: ExecutionContext,
        workspace_context: WorkspaceContext,
        options: CodingAgentInvocationOptions,
    ) -> ExecutionServiceResult:
        """Unified execution entry point (Phase D4).

        Delegates to the injected :class:`ICodingAgent`, captures the
        :class:`CodingAgentResult`, commits the workspace on success, and
        emits the appropriate ``ExecutionCompletedEvent`` /
        ``ExecutionFailedEvent`` via the domain object's lifecycle
        methods (``execution.complete()`` / ``execution.fail()``). Those
        domain methods own event construction so the audit trail stays
        in lockstep with state transitions (per INV-10).

        Replaces both :meth:`execute_with_llm` and
        :meth:`execute_with_container`. The coding-agent adapter owns the
        invocation-mode decision (container vs. host vs. API); this
        service no longer branches on ``Agent.requires_docker``.

        Args:
            execution: AgentExecution to run; must be in RUNNING state.
            context: Service-side execution context (carries repository
                path, commit policy, etc. — used for workspace commit and
                lifecycle, not passed to the coding agent).
            workspace_context: Logical workspace description from
                ``WorkspaceRouter``; forwarded to
                :meth:`ICodingAgent.execute` so the adapter can render
                prompts and place files.
            options: Per-execution :class:`CodingAgentInvocationOptions`
                (mode, model, timeout, cost limit, mode-specific config).

        Returns:
            ExecutionServiceResult summarising the outcome.
        """
        # Track as active so cancel_execution can find this run.
        self._active_executions[execution.id] = execution

        try:
            result: CodingAgentResult = await self.coding_agent.execute(
                execution,
                workspace_context,
                options,
            )

            if result.success:
                # Commit before completing so ExecutionCompletedEvent carries the
                # commit SHA — downstream handlers (workflow progression, PR
                # creation) rely on this ordering.
                commit_sha: str | None = None
                commit_branch: str | None = None
                commit_error: WorkspaceCommitError | None = None
                try:
                    commit_sha, commit_branch = await self._commit_workspace(context, execution)
                except WorkspaceCommitError as wce:
                    # D-J: agent ran successfully but commit/push failed. The
                    # agent's work didn't reach the remote, so we MUST mark
                    # the execution failed — otherwise downstream handlers
                    # (BoardColumnEventHandler.handle_agent_completion) would
                    # auto-progress the work item to "In Review" even though
                    # nothing was published. Capture partial-progress info
                    # so the failed result still reports any local commit.
                    commit_sha = wce.commit_sha
                    commit_branch = wce.branch
                    commit_error = wce

                if commit_error is not None:
                    # Failure path: record execution.fail(), emit
                    # ExecutionFailedEvent, return success=False.
                    error_message = (
                        f"Workspace commit/push failed: {commit_error}"
                        if str(commit_error)
                        else "Workspace commit/push failed"
                    )
                    execution.fail(error_message=error_message)

                    events = execution.get_pending_events()
                    for event in events:
                        await self.event_store.append(execution.id, [event])
                    execution.clear_events()

                    self._active_executions.pop(execution.id, None)

                    logger.error(
                        f"ExecutionService.execute: execution {execution.id} marked failed "
                        f"after workspace commit/push failure "
                        f"(commit_sha={commit_sha}, branch={commit_branch})",
                        extra={
                            "error_id": "ERR_EXECUTION_WORKSPACE_COMMIT_FAILURE",
                            "work_item_id": context.work_item_id,
                            "commit_sha": commit_sha,
                            "branch": commit_branch,
                        },
                    )

                    return ExecutionServiceResult(
                        success=False,
                        execution=execution,
                        error=error_message,
                        failure_reason=ExecutionFailureReason.WORKSPACE_COMMIT_ERROR,
                        commit_sha=commit_sha,
                        branch=commit_branch,
                    )

                execution.complete(
                    output=result.summary_text,
                    input_tokens=result.total_input_tokens,
                    output_tokens=result.total_output_tokens,
                    commit_sha=commit_sha,
                    branch=commit_branch,
                )

                events = execution.get_pending_events()
                for event in events:
                    await self.event_store.append(execution.id, [event])
                execution.clear_events()

                self._active_executions.pop(execution.id, None)

                logger.info(
                    f"ExecutionService.execute: completed execution {execution.id} "
                    f"(mode={options.invocation_mode.value}, model={options.model}, "
                    f"tokens_in={result.total_input_tokens}, tokens_out={result.total_output_tokens}, "
                    f"tool_calls={result.tool_call_count}, duration_ms={result.duration_ms})"
                )

                return ExecutionServiceResult(
                    success=True,
                    execution=execution,
                    reason="Execution completed via coding agent",
                    commit_sha=commit_sha,
                    branch=commit_branch,
                )

            # Failure path — optionally capture partial progress for ALWAYS-commit agents
            failure_commit_sha: str | None = None
            failure_branch: str | None = None
            if context.commit_policy == CommitPolicy.ALWAYS:
                try:
                    failure_commit_sha, failure_branch = await self._commit_workspace(context, execution)
                except WorkspaceCommitError as wce:
                    # Preserve whatever partial progress made it through (local
                    # commit may have succeeded even if push failed).
                    failure_commit_sha = wce.commit_sha
                    failure_branch = wce.branch
                    logger.warning(
                        f"Partial commit failed for execution {execution.id} (ALWAYS policy), "
                        f"proceeding with failure result (commit_sha={failure_commit_sha}, "
                        f"branch={failure_branch})",
                        exc_info=True,
                        extra={
                            "error_id": "ERR_EXECUTION_COMMIT_PARTIAL_FAILURE",
                            "work_item_id": context.work_item_id,
                        },
                    )

            error_message = result.error_summary or "Coding agent reported failure"
            execution.fail(error_message=error_message)

            events = execution.get_pending_events()
            for event in events:
                await self.event_store.append(execution.id, [event])
            execution.clear_events()

            self._active_executions.pop(execution.id, None)

            logger.error(
                f"ExecutionService.execute: execution {execution.id} failed: {error_message}",
                extra={"error_id": "ERR_EXECUTION_CODING_AGENT_FAILURE"},
            )

            return ExecutionServiceResult(
                success=False,
                execution=execution,
                error=error_message,
                failure_reason=self._classify_coding_agent_failure(result),
                commit_sha=failure_commit_sha,
                branch=failure_branch,
            )

        except Exception as exc:
            # Adapter raised — translate into a failed execution so the
            # workflow doesn't strand in RUNNING state. We don't try to
            # commit anything here; the run path is undefined.
            error_message = f"Coding agent raised exception: {exc}"
            try:
                execution.fail(error_message=error_message)
                events = execution.get_pending_events()
                for event in events:
                    await self.event_store.append(execution.id, [event])
                execution.clear_events()
            except Exception:
                logger.error(
                    f"Failed to record fail() for execution {execution.id} " "after coding agent exception",
                    exc_info=True,
                    extra={"error_id": "ERR_EXECUTION_FAIL_RECORD_FAILURE"},
                )
            self._active_executions.pop(execution.id, None)

            logger.error(
                f"ExecutionService.execute: coding agent raised for execution {execution.id}: {exc}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_CODING_AGENT_EXCEPTION"},
            )

            return ExecutionServiceResult(
                success=False,
                execution=execution,
                error=error_message,
                failure_reason=self._classify_failure(exc),
            )

    @staticmethod
    def _classify_coding_agent_failure(result: CodingAgentResult) -> ExecutionFailureReason:
        """Derive a coarse :class:`ExecutionFailureReason` from a failed result.

        The :class:`CodingAgentResult` schema is intentionally narrow
        (success / summary / error_summary). For the bridge state we
        return ``UNKNOWN`` unless the error summary hints at a
        well-known category. D5+ can broaden this when the coding-agent
        error model grows.
        """
        if not result.error_summary:
            return ExecutionFailureReason.UNKNOWN
        lowered = result.error_summary.lower()
        if "timeout" in lowered:
            return ExecutionFailureReason.TIMEOUT
        if "rate limit" in lowered or "ratelimit" in lowered:
            return ExecutionFailureReason.RATE_LIMIT
        return ExecutionFailureReason.UNKNOWN

    async def _commit_workspace(
        self,
        context: ExecutionContext,
        execution: AgentExecution,
    ) -> tuple[str | None, str | None]:
        """Commit and push workspace changes after execution completes.

        Called before execution.complete() so that the ExecutionCompleted event
        carries the commit SHA and downstream handlers (workflow progression,
        PR creation) see committed code.

        Returns:
            (commit_sha, branch) — both None when no commit is needed.

        Raises:
            RuntimeError: If vcs adapter is missing, repository_path is unset,
                or branch_name is unset when a commit is expected.
        """
        if context.commit_policy == CommitPolicy.NONE:
            return None, None
        if not context.can_make_commits:
            return None, None
        if self.vcs is None:
            raise RuntimeError(f"VCS adapter not configured — cannot commit workspace for execution {execution.id}")
        if not context.repository_path:
            raise RuntimeError(f"repository_path not set on ExecutionContext for execution {execution.id}")

        branch = context.branch_name
        if not branch:
            raise RuntimeError(f"branch_name not set on ExecutionContext for execution {execution.id}")

        commit_sha: str | None = None
        try:
            vcs_status = await self.vcs.status(context.repository_path)
            has_staged = bool(vcs_status.staged_files)
            # Claude Code edits existing files (unstaged) AND creates new files
            # (untracked) but does not run `git commit`. New files are the common
            # case, so both sets must be staged or the commit captures nothing.
            files_to_stage = list(vcs_status.unstaged_files) + list(vcs_status.untracked_files)
            commit_message = (
                f"[{context.work_item_id}] {context.stage_name}: agent {context.agent_id}\n\n"
                f"Co-Authored-By: Codetoreum <noreply@codetoreum.ai>"
            )

            if files_to_stage:
                # Stage all unstaged + untracked files so the pushed branch captures
                # the agent's actual output. Anything already staged is committed too
                # (the commit carries no pathspec).
                commit_sha = await self.vcs.commit(
                    context.repository_path,
                    message=commit_message,
                    author_name="Codetoreum",
                    author_email="noreply@codetoreum.ai",
                    files=files_to_stage,
                )
                logger.info(
                    f"Committed {len(files_to_stage)} file(s) for execution {execution.id}: "
                    f"{commit_sha} → {branch}",
                    extra={"work_item_id": context.work_item_id, "commit_sha": commit_sha, "branch": branch},
                )
            elif has_staged:
                # Only pre-staged content (agent staged before container exit), nothing
                # else dirty. Commit whatever is in the index.
                commit_sha = await self.vcs.commit(
                    context.repository_path,
                    message=commit_message,
                    author_name="Codetoreum",
                    author_email="noreply@codetoreum.ai",
                )
                logger.info(
                    f"Committed workspace for execution {execution.id}: {commit_sha} → {branch}",
                    extra={"work_item_id": context.work_item_id, "commit_sha": commit_sha, "branch": branch},
                )
            else:
                # No staged or unstaged files. The agent may have committed and cleaned
                # up inside the container. Always push so those commits are captured.
                # If there is truly nothing to push, git is a no-op.
                logger.warning(
                    f"No staged or unstaged changes for execution {execution.id} — "
                    "pushing branch to capture any commits made inside the container",
                    extra={"work_item_id": context.work_item_id, "agent_id": context.agent_id},
                )

            # Always push: picks up commits the agent made inside the Docker container.
            try:
                await self.vcs.push(context.repository_path, branch)
            except Exception as push_exc:
                # D-J: the commit may have succeeded locally but the push to
                # the remote failed. Wrap in WorkspaceCommitError so the
                # caller in execute() can preserve commit_sha/branch on the
                # failed ExecutionServiceResult (a human can find the local
                # commit; the remote branch was NOT updated).
                logger.error(
                    f"Failed to push branch {branch} for execution {execution.id}: {push_exc}",
                    exc_info=True,
                    extra={
                        "error_id": "ERR_EXECUTION_PUSH_FAILURE",
                        "work_item_id": context.work_item_id,
                        "branch": branch,
                        "commit_sha": commit_sha,
                    },
                )
                raise WorkspaceCommitError(
                    f"Push of branch {branch} failed for execution {execution.id}: {push_exc}",
                    commit_sha=commit_sha,
                    branch=branch,
                ) from push_exc
            logger.info(
                f"Pushed branch {branch} for execution {execution.id}",
                extra={"work_item_id": context.work_item_id, "branch": branch},
            )

            # Open a PR for the pushed branch when the project allows it.
            # Failures are logged but do not abort the execution — the
            # branch is already on the remote, so the work isn't lost; a
            # PR can be opened by hand or by re-running.
            if context.auto_create_pull_requests:
                await self._open_pull_request(context, branch, commit_sha, execution)

            return commit_sha, branch
        except WorkspaceCommitError:
            # Already logged at the push site; rethrow as-is so the caller in
            # execute() can read commit_sha/branch off the exception.
            raise
        except Exception as exc:
            logger.error(
                f"Failed to commit workspace for execution {execution.id}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_COMMIT_FAILURE", "work_item_id": context.work_item_id},
            )
            # Wrap so the caller has a single exception type to dispatch on.
            raise WorkspaceCommitError(
                f"Commit failed for execution {execution.id}: {exc}",
                commit_sha=commit_sha,
                branch=branch,
            ) from exc

    async def _open_pull_request(
        self,
        context: ExecutionContext,
        branch: str,
        commit_sha: str | None,
        execution: AgentExecution,
    ) -> None:
        """Open a PR for the pushed branch and refresh title on commit. Best-effort: logs and swallows."""
        if self.vcs is None or not context.repository_path:
            return
        repo_path: str = context.repository_path
        # Default base is "main" — the project default branch is not on
        # ExecutionContext today (would require plumbing through builder
        # + executor). "main" is correct for the GitHub-based projects
        # we target and matches the existing pull-from-main behaviour
        # in WorkspaceRouter.
        base = "main"
        title = f"[{context.work_item_id}] {context.stage_name}: {context.agent_id}"
        body_lines = [
            f"Automated PR opened by Codetoreum for work item `{context.work_item_id}`.",
            "",
            f"- Stage: `{context.stage_name}`",
            f"- Agent: `{context.agent_id}`",
            f"- Branch: `{branch}`",
        ]
        if commit_sha:
            body_lines.append(f"- Commit: `{commit_sha}`")
        body = "\n".join(body_lines)

        try:
            pr_url = await self.vcs.create_pull_request(
                repo_path=repo_path,
                head=branch,
                base=base,
                title=title,
                body=body,
            )
            logger.info(
                f"Opened pull request for execution {execution.id}: {pr_url}",
                extra={
                    "work_item_id": context.work_item_id,
                    "branch": branch,
                    "pr_url": pr_url,
                },
            )

            # Branch reuse across work items can leave a stale title on the existing PR.
            title_updated = await self.vcs.update_pull_request_title(
                repo_path=repo_path,
                head=branch,
                base=base,
                new_title=title,
            )
            if title_updated:
                logger.info(
                    f"Refreshed PR title for execution {execution.id}",
                    extra={
                        "work_item_id": context.work_item_id,
                        "branch": branch,
                        "new_title": title,
                    },
                )
        except Exception:
            logger.error(
                f"Failed to open/update pull request for execution {execution.id} "
                f"(branch={branch}); the push succeeded so the work is on "
                "the remote — open the PR manually or re-run the stage",
                exc_info=True,
                extra={
                    "error_id": "ERR_EXECUTION_PR_CREATE_FAILURE",
                    "work_item_id": context.work_item_id,
                    "branch": branch,
                },
            )

    @instrument_async_function(
        name="execution.cancel_execution",
        attributes={"service": "execution_service", "operation": "cancel"},
    )
    async def cancel_execution(self, execution: AgentExecution) -> ExecutionServiceResult:
        """
        Cancel running execution.

        Args:
            execution: AgentExecution to cancel

        Returns:
            ExecutionServiceResult with outcome
        """
        try:
            if not execution.is_terminal():
                # D5: container teardown moved into the coding-agent
                # adapter; cancel_execution only records the lifecycle
                # transition. The adapter's own timeout / cleanup paths
                # are responsible for releasing any subprocess or
                # container backing the run.

                # Mark as cancelled
                execution.cancel(reason="Execution cancelled by user")

                # Persist events
                events = execution.get_pending_events()
                for event in events:
                    await self.event_store.append(execution.id, [event])
                execution.clear_events()

                # Clean up tracking
                self._active_executions.pop(execution.id, None)

                logger.info(f"Cancelled execution {execution.id}")

                return ExecutionServiceResult(success=True, execution=execution, reason="Execution cancelled")
            return ExecutionServiceResult(
                success=False,
                execution=execution,
                error="Execution already in terminal state",
            )

        except EventStoreError as e:
            logger.error(
                f"Failed to persist cancellation for execution {execution.id}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_CANCEL_EVENTSTORE_FAILURE"},
            )
            return ExecutionServiceResult(success=False, execution=execution, error=str(e))
        except DomainError as e:
            logger.error(
                f"Domain error during cancellation of execution {execution.id}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_CANCEL_DOMAIN_FAILURE"},
            )
            return ExecutionServiceResult(success=False, execution=execution, error=str(e))

    def _classify_failure(self, error: Exception | None) -> ExecutionFailureReason:
        """
        Classify failure reason from exception.

        Args:
            error: Exception that caused failure

        Returns:
            ExecutionFailureReason
        """
        if error is None:
            return ExecutionFailureReason.UNKNOWN

        if isinstance(error, RateLimitError):
            return ExecutionFailureReason.RATE_LIMIT
        if isinstance(error, ContainerTimeoutError):
            return ExecutionFailureReason.TIMEOUT
        if isinstance(error, ContainerExecutionError):
            return ExecutionFailureReason.CONTAINER_ERROR
        if isinstance(error, ExternalServiceError):
            return ExecutionFailureReason.LLM_ERROR
        if isinstance(error, (ValueError, DomainError)):
            return ExecutionFailureReason.VALIDATION_ERROR
        return ExecutionFailureReason.UNKNOWN
