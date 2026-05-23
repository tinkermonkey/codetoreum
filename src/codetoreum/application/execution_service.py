"""Execution Service application service."""

import asyncio
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from codetoreum.domain.agent import Agent, CommitPolicy
from codetoreum.domain.agent_execution import AgentExecution, ExecutionStatus
from codetoreum.domain.exceptions import DomainError
from codetoreum.domain.types import (
    CONTAINER_LABEL_AGENT,
    CONTAINER_LABEL_EXECUTION_ID,
    CONTAINER_LABEL_PROJECT,
    CONTAINER_LABEL_TASK_ID,
    CONTAINER_LABEL_TYPE,
    CONTAINER_LABEL_WORK_ITEM_ID,
    CONTAINER_LABEL_WORKFLOW_RUN_ID,
    ExecutionId,
)
from codetoreum.domain.value_objects import (
    ContainerConfig,
    ExecutionContext,
)
from codetoreum.domain.work_item import WorkItem
from codetoreum.infrastructure.observability.instrumentation import (
    instrument_async_function,
)
from codetoreum.ports.exceptions import (
    ContainerExecutionError,
    ContainerTimeoutError,
    EventStoreError,
    ExternalServiceError,
    LLMProviderError,
    PortError,
    RateLimitError,
)
from codetoreum.ports.output import IContainer, IEventStore, ILLMProvider, IStorage
from codetoreum.ports.output.llm_provider import ExecutionContext as LLMExecutionContext
from codetoreum.ports.output.version_control_service import IVersionControlService

logger = logging.getLogger(__name__)


class ExecutionFailureReason(Enum):
    """Reasons for execution failure."""

    CONTAINER_ERROR = "container_error"
    LLM_ERROR = "llm_error"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    VALIDATION_ERROR = "validation_error"
    UNKNOWN = "unknown"


@dataclass
class LogEntry:
    """Log entry from execution."""

    timestamp: datetime
    level: str
    message: str
    source: str  # 'container', 'llm', 'service'


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


@dataclass
class StreamUpdate:
    """Update from streaming execution."""

    execution_id: str
    content: str
    timestamp: datetime
    is_complete: bool = False


class ExecutionService:
    """
    Application service for managing agent execution lifecycle.

    Responsibilities:
    - Create and initialize agent executions
    - Coordinate with container and LLM adapters
    - Manage execution lifecycle (start, monitor, complete)
    - Handle execution failures and retries
    - Stream execution logs to subscribers
    """

    def __init__(
        self,
        llm_provider: ILLMProvider,
        container: IContainer,
        event_store: IEventStore,
        storage: IStorage,
        max_retries: int = 1,
        retry_delay_seconds: float = 5,
        vcs: IVersionControlService | None = None,
        system_credentials: dict[str, str] | None = None,
    ):
        """
        Initialize ExecutionService.

        Args:
            llm_provider: LLM provider adapter
            container: Container orchestration adapter
            event_store: Event store for domain events
            storage: Storage adapter for artifacts
            max_retries: Maximum number of retry attempts
            retry_delay_seconds: Delay between retry attempts
            vcs: Version control service for post-execution commit+push.
                 When None the commit step is skipped (e.g. simulation without VCS).
            system_credentials: Credentials injected at bootstrap time
                (ANTHROPIC_API_KEY, CLAUDE_CODE_OAUTH_TOKEN, GITHUB_TOKEN).
                Passed to container executions via environment variables so adapters
                never need to read os.environ directly.
        """
        self.llm_provider = llm_provider
        self.container = container
        self.event_store = event_store
        self.storage = storage
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self.vcs = vcs
        self._system_credentials: dict[str, str] = system_credentials or {}

        # Track active executions for streaming
        self._active_executions: dict[str, AgentExecution] = {}
        self._log_subscribers: dict[str, list[Callable[[LogEntry], None]]] = {}

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
                model=agent.model,
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
        container_config: ContainerConfig | None = None,
    ) -> ExecutionServiceResult:
        """
        Start agent execution.

        Args:
            execution: AgentExecution to start
            context: Execution context
            container_config: Optional container configuration for Docker execution

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

            # Determine container name if using Docker
            container_name = None
            if container_config:
                container_name = f"codetoreum-{execution.agent_id}-{execution.id[:8]}"

            # Start execution
            execution.start(container_name=container_name)

            # Persist events
            events = execution.get_pending_events()
            for event in events:
                await self.event_store.append(execution.id, [event])
            execution.clear_events()

            logger.info(f"Started execution {execution.id} (container: {container_name or 'none'})")

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
        name="execution.execute_with_llm",
        attributes={"service": "execution_service", "operation": "execute_llm"},
    )
    async def execute_with_llm(
        self,
        execution: AgentExecution,
        context: ExecutionContext,
        stream_callback: Callable[[str], None] | None = None,
    ) -> ExecutionServiceResult:
        """
        Execute agent with LLM provider.

        Args:
            execution: AgentExecution to run
            context: Execution context
            stream_callback: Optional callback for streaming output

        Returns:
            ExecutionServiceResult with outcome
        """
        retry_count = 0
        last_error: Exception | None = None

        while retry_count <= self.max_retries:
            try:
                # Build LLM execution context
                llm_context = self._build_llm_context(context, execution_id=ExecutionId(execution.id))

                # Execute with LLM
                result = await self.llm_provider.execute(
                    prompt=execution.prompt,
                    context=llm_context,
                    stream_callback=(
                        self._create_stream_callback(execution.id, stream_callback) if stream_callback else None
                    ),
                )

                # Commit workspace before completing so ExecutionCompleted carries the
                # commit SHA and downstream handlers see committed code.
                commit_sha, commit_branch = None, None
                try:
                    commit_sha, commit_branch = await self._commit_workspace(context, execution)
                except Exception:
                    logger.error(
                        f"Commit failed for execution {execution.id}, completing without commit SHA",
                        exc_info=True,
                        extra={"error_id": "ERR_EXECUTION_COMMIT_FAILURE", "work_item_id": context.work_item_id},
                    )

                # Complete execution successfully
                execution.complete(
                    output=result.content,
                    input_tokens=result.prompt_tokens,
                    output_tokens=result.completion_tokens,
                    session_id=result.metadata.get("session_id"),
                    commit_sha=commit_sha,
                    branch=commit_branch,
                )

                # Persist events
                events = execution.get_pending_events()
                for event in events:
                    await self.event_store.append(execution.id, [event])
                execution.clear_events()

                # Clean up tracking
                self._active_executions.pop(execution.id, None)

                logger.info(f"Completed execution {execution.id} successfully (tokens: {result.total_tokens})")

                return ExecutionServiceResult(success=True, execution=execution, reason="Execution completed")

            except RateLimitError as e:
                logger.warning(
                    f"Rate limit hit for execution {execution.id}, retry {retry_count + 1}/{self.max_retries}",
                    extra={"error_id": "ERR_EXECUTION_LLM_RATE_LIMIT"},
                )
                last_error = e
                retry_count += 1
                if retry_count <= self.max_retries:
                    await asyncio.sleep(self.retry_delay_seconds * retry_count)
                continue

            except (ExternalServiceError, LLMProviderError) as e:
                logger.error(
                    f"LLM service error for execution {execution.id}: {e}, retry {retry_count + 1}/{self.max_retries}",
                    exc_info=True,
                    extra={"error_id": "ERR_EXECUTION_LLM_SERVICE_ERROR"},
                )
                last_error = e
                retry_count += 1
                if retry_count <= self.max_retries:
                    await asyncio.sleep(self.retry_delay_seconds)
                continue

            except EventStoreError as e:
                logger.error(
                    f"Event store error during execution {execution.id}: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_EXECUTION_EVENTSTORE_FAILURE"},
                )
                last_error = e
                break

            except DomainError as e:
                logger.error(
                    f"Domain validation error during execution {execution.id}: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_EXECUTION_DOMAIN_VALIDATION_FAILURE"},
                )
                last_error = e
                break

        # All retries exhausted, fail execution
        error_message = f"Execution failed after {retry_count} retries: {last_error}"
        execution.fail(error_message=error_message)

        # Persist failure events
        events = execution.get_pending_events()
        for event in events:
            await self.event_store.append(execution.id, [event])
        execution.clear_events()

        # Clean up tracking
        self._active_executions.pop(execution.id, None)

        logger.error(
            f"Failed execution {execution.id}: {error_message}",
            exc_info=True,
            extra={"error_id": "ERR_EXECUTION_RETRIES_EXHAUSTED"},
        )

        return ExecutionServiceResult(
            success=False,
            execution=execution,
            error=error_message,
            failure_reason=self._classify_failure(last_error),
        )

    def _build_container_labels(
        self,
        execution: AgentExecution,
        context: ExecutionContext,
    ) -> dict[str, str]:
        """
        Build Docker labels for container.

        Labels are used by the container recovery service to identify and manage
        containers at orchestrator startup. All labels are immutable metadata
        extracted from domain objects.

        Args:
            execution: Agent execution instance
            context: Execution context with project and task information

        Returns:
            Dict[str, str]: Container labels following org.codetoreum.* namespace
        """
        labels = {
            CONTAINER_LABEL_TYPE: "agent",
            CONTAINER_LABEL_PROJECT: context.project_id,
            CONTAINER_LABEL_AGENT: execution.agent_id,
            CONTAINER_LABEL_WORK_ITEM_ID: execution.work_item_id,
            # In the current phase, execution.id serves as both task_id and execution_id.
            # Phase 2 recovery service uses these for container identification and tracking.
            # Future phases may introduce separate task IDs from an external scheduler.
            CONTAINER_LABEL_TASK_ID: execution.id,
            CONTAINER_LABEL_WORKFLOW_RUN_ID: execution.workflow_id,
            CONTAINER_LABEL_EXECUTION_ID: execution.id,
        }
        return labels

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
            has_unstaged = vcs_status.is_dirty or bool(vcs_status.unstaged_files)

            if has_staged:
                # Commit whatever is staged (agent may have staged files before container exit)
                commit_message = (
                    f"[{context.work_item_id}] {context.stage_name}: agent {context.agent_id}\n\n"
                    f"Co-Authored-By: Codetoreum <noreply@codetoreum.ai>"
                )
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
            elif has_unstaged:
                # Agent committed inside the container; unstaged remnants are exploration.
                # Push the agent's commits without adding more.
                logger.info(
                    f"No staged changes for execution {execution.id} "
                    f"({len(vcs_status.unstaged_files)} unstaged file(s) left as-is). "
                    "Pushing branch to capture agent commits.",
                    extra={"work_item_id": context.work_item_id, "agent_id": context.agent_id},
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
            await self.vcs.push(context.repository_path, branch)
            logger.info(
                f"Pushed branch {branch} for execution {execution.id}",
                extra={"work_item_id": context.work_item_id, "branch": branch},
            )
            return commit_sha, branch
        except Exception:
            logger.error(
                f"Failed to commit workspace for execution {execution.id}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_COMMIT_FAILURE", "work_item_id": context.work_item_id},
            )
            raise

    @instrument_async_function(
        name="execution.execute_with_container",
        attributes={"service": "execution_service", "operation": "execute_container"},
    )
    def _build_agent_container_config(
        self,
        execution: AgentExecution,
        context: "ExecutionContext",
        agent: Agent,
    ) -> ContainerConfig:
        """Build ContainerConfig for an agent container execution.

        Encapsulates all knowledge about the codetoreum-agent image contract:
        command format, workspace mount point, required environment variables,
        and git identity defaults. Credentials come from the system_credentials
        dict injected at bootstrap — no direct os.environ reads here.

        Args:
            execution: The execution whose prompt drives the agent
            context: Execution context (repository path, env overrides, model)
            agent: Agent domain object supplying the model name

        Returns:
            Fully configured ContainerConfig ready for execute_with_container
        """
        model = context.model or getattr(agent, "model", None)
        if not model:
            raise ValueError(
                f"Agent '{getattr(agent, 'id', agent)}' has no model configured " "— cannot build container config"
            )

        claude_cmd = (
            "claude",
            "--print",
            "--output-format",
            "stream-json",
            "--permission-mode",
            "bypassPermissions",
            "--model",
            model,
            "--verbose",
            execution.prompt,
        )

        volumes: dict[str, dict[str, str]] = {}
        if context.repository_path:
            volumes[context.repository_path] = {"bind": "/workspace", "mode": "rw"}

        # Credentials injected at bootstrap take precedence; context env vars can
        # override on a per-execution basis (e.g. project-specific tokens).
        env: dict[str, str] = {**self._system_credentials}
        env.setdefault("GIT_AUTHOR_NAME", "Codetoreum Agent")
        env.setdefault("GIT_AUTHOR_EMAIL", "agent@codetoreum.ai")
        env.setdefault("GIT_COMMITTER_NAME", "Codetoreum Agent")
        env.setdefault("GIT_COMMITTER_EMAIL", "agent@codetoreum.ai")
        if context.environment_variables:
            env.update(context.environment_variables)

        return ContainerConfig(
            image="codetoreum-agent:latest",
            command=claude_cmd,
            working_dir="/workspace",
            volumes=volumes if volumes else None,
            environment=env if env else None,
        )

    async def execute_agent_with_container(
        self,
        execution: AgentExecution,
        context: "ExecutionContext",
        agent: Agent,
        stream_callback: Callable[[str], None] | None = None,
    ) -> "ExecutionServiceResult":
        """Build ContainerConfig and execute agent in Docker container.

        Convenience wrapper over execute_with_container that builds the
        ContainerConfig from the agent + context so adapters do not need to
        know about image names, command formats, or credential layout.

        Args:
            execution: AgentExecution to run
            context: Execution context
            agent: Agent domain object (supplies model name)
            stream_callback: Optional callback for streaming logs

        Returns:
            ExecutionServiceResult with outcome
        """
        container_config = self._build_agent_container_config(execution, context, agent)
        return await self.execute_with_container(execution, context, container_config, stream_callback)

    async def execute_with_container(
        self,
        execution: AgentExecution,
        context: ExecutionContext,
        container_config: ContainerConfig,
        stream_callback: Callable[[str], None] | None = None,
    ) -> ExecutionServiceResult:
        """
        Execute agent in Docker container.

        Containers start detached with a bounded wait timeout. Log streaming runs
        as a background task. DockerContainerRecoveryAdapter handles reconnection
        if the orchestrator restarts mid-execution.

        Args:
            execution: AgentExecution to run
            context: Execution context
            container_config: Container configuration
            stream_callback: Optional callback for streaming logs

        Returns:
            ExecutionServiceResult with outcome
        """
        container_id = None

        try:
            # Build container labels for recovery tracking
            labels = self._build_container_labels(execution, context)

            # Create container (detached, non-blocking)
            # Use helper methods to convert immutable types (tuple, Mapping) to mutable types
            # (list, dict) for adapter compatibility, while maintaining domain layer immutability
            container_id = await self.container.create(
                image=container_config.image,
                name=execution.container_name,
                command=container_config.get_command_as_list(),
                volumes=container_config.get_volumes_as_dict(),
                environment=container_config.get_environment_as_dict(),
                working_dir=container_config.working_dir,
                user=container_config.user,
                network=container_config.network,
                labels=labels,
            )

            logger.info(f"Created container {container_id} for execution {execution.id}")

            # Start container (detached, non-blocking)
            await self.container.start(container_id)

            logger.info(f"Started container {container_id} for execution {execution.id}")

            # Stream logs in background if callback provided
            # This does not block execution
            if stream_callback:
                task = asyncio.create_task(self._stream_container_logs(container_id, execution.id, stream_callback))
                task.add_done_callback(self._stream_logs_done_callback)

            # Wait for container to complete with bounded timeout
            # Orchestrator restart drops this task, and DockerContainerRecoveryAdapter
            # picks up the container on next start
            exit_code = await self.container.wait(container_id, timeout=context.timeout_seconds)

            # Get output
            logs = await self.container.logs(container_id)

            # Extract token usage from logs (if available)
            input_tokens, output_tokens = self._extract_token_usage(logs)

            if exit_code == 0:
                # Commit workspace changes before firing ExecutionCompleted so that
                # the event carries the commit SHA and downstream handlers (workflow
                # progression, PR creation) see committed code.  A transient VCS
                # failure must not orphan the execution in RUNNING state — degrade
                # gracefully with commit_sha=None so the execution still completes.
                commit_sha, branch = None, None
                try:
                    commit_sha, branch = await self._commit_workspace(context, execution)
                except Exception:
                    logger.error(
                        f"Commit failed for execution {execution.id}, completing without commit SHA",
                        exc_info=True,
                        extra={"error_id": "ERR_EXECUTION_COMMIT_FAILURE", "work_item_id": context.work_item_id},
                    )

                execution.complete(
                    output=logs,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    commit_sha=commit_sha,
                    branch=branch,
                )

                # Persist events
                events = execution.get_pending_events()
                for event in events:
                    await self.event_store.append(execution.id, [event])
                execution.clear_events()

                logger.info(f"Container execution {execution.id} completed successfully")

                return ExecutionServiceResult(
                    success=True,
                    execution=execution,
                    reason="Container execution completed",
                    commit_sha=commit_sha,
                    branch=branch,
                )
            # Execution failed — commit partial progress for ALWAYS policy agents
            # so that incremental work is not lost even when the container exits non-zero.
            failure_commit_sha, failure_branch = None, None
            if context.commit_policy == CommitPolicy.ALWAYS:
                try:
                    failure_commit_sha, failure_branch = await self._commit_workspace(context, execution)
                except Exception:
                    logger.warning(
                        f"Partial commit failed for execution {execution.id} (ALWAYS policy), "
                        "proceeding with failure result",
                        exc_info=True,
                        extra={
                            "error_id": "ERR_EXECUTION_COMMIT_PARTIAL_FAILURE",
                            "work_item_id": context.work_item_id,
                        },
                    )

            error_message = f"Container exited with code {exit_code}"
            execution.fail(error_message=error_message, exit_code=exit_code)

            # Persist events
            events = execution.get_pending_events()
            for event in events:
                await self.event_store.append(execution.id, [event])
            execution.clear_events()

            logger.error(
                f"Container execution {execution.id} failed: {error_message}",
                extra={"error_id": "ERR_EXECUTION_CONTAINER_EXIT_FAILURE"},
            )

            return ExecutionServiceResult(
                success=False,
                execution=execution,
                error=error_message,
                failure_reason=ExecutionFailureReason.CONTAINER_ERROR,
                commit_sha=failure_commit_sha,
                branch=failure_branch,
            )

        except ContainerTimeoutError as e:
            logger.error(
                f"Container execution {execution.id} timed out: {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_CONTAINER_TIMEOUT"},
            )
            execution.timeout()

            # Persist events
            events = execution.get_pending_events()
            for event in events:
                await self.event_store.append(execution.id, [event])
            execution.clear_events()

            return ExecutionServiceResult(
                success=False,
                execution=execution,
                error=str(e),
                failure_reason=ExecutionFailureReason.TIMEOUT,
            )

        except ContainerExecutionError as e:
            logger.error(
                f"Container execution error for {execution.id}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_CONTAINER_ERROR"},
            )

            error_message = f"Container execution error: {e}"
            execution.fail(error_message=error_message)

            # Persist events
            events = execution.get_pending_events()
            for event in events:
                await self.event_store.append(execution.id, [event])
            execution.clear_events()

            return ExecutionServiceResult(
                success=False,
                execution=execution,
                error=error_message,
                failure_reason=ExecutionFailureReason.CONTAINER_ERROR,
            )

        except EventStoreError as e:
            logger.error(
                f"Event store error during container execution {execution.id}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_CONTAINER_EVENTSTORE_FAILURE"},
            )

            error_message = f"Event store error: {e}"
            execution.fail(error_message=error_message)

            return ExecutionServiceResult(
                success=False,
                execution=execution,
                error=error_message,
                failure_reason=ExecutionFailureReason.UNKNOWN,
            )

        finally:
            # Clean up container with retry
            if container_id:
                cleanup_success = await self._cleanup_container_with_retry(container_id, max_attempts=3)
                if not cleanup_success:
                    logger.error(
                        f"CRITICAL: Failed to cleanup container {container_id} after retries. "
                        f"Manual intervention may be required.",
                        extra={"error_id": "ERR_EXECUTION_CONTAINER_CLEANUP_CRITICAL"},
                    )

            # Clean up tracking
            self._active_executions.pop(execution.id, None)

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
                # Stop container if running in Docker
                if execution.container_id:
                    cleanup_success = await self._cleanup_container_with_retry(execution.container_id, max_attempts=3)
                    if not cleanup_success:
                        logger.error(
                            f"Failed to stop container {execution.container_id} during cancellation",
                            extra={"error_id": "ERR_EXECUTION_CANCEL_CONTAINER_STOP_FAILURE"},
                        )

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

    async def get_execution_logs(self, execution: AgentExecution, tail: int | None = None) -> list[LogEntry]:
        """
        Get execution logs.

        Args:
            execution: AgentExecution to get logs for
            tail: Optional number of lines from end

        Returns:
            List of log entries
        """
        logs: list[LogEntry] = []

        try:
            if execution.container_id:
                # Get container logs
                container_logs = await self.container.logs(execution.container_id, stream=False, tail=tail)

                # Parse logs into entries
                for line in container_logs.split("\n"):
                    if line.strip():
                        logs.append(
                            LogEntry(
                                timestamp=datetime.now(UTC),
                                level="INFO",
                                message=line,
                                source="container",
                            )
                        )

        except ContainerExecutionError as e:
            logger.error(
                f"Container error getting logs for execution {execution.id}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_GET_LOGS_CONTAINER_ERROR"},
            )
            # Return empty list on container errors
        except PortError as e:
            logger.error(
                f"Unexpected error getting logs for execution {execution.id}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_GET_LOGS_UNEXPECTED_ERROR"},
            )
            # Return empty list on unexpected errors

        return logs

    async def stream_execution_logs(self, execution: AgentExecution) -> AsyncIterator[LogEntry]:
        """
        Stream execution logs in real-time.

        Args:
            execution: AgentExecution to stream logs for

        Yields:
            LogEntry: Log entries as they arrive
        """
        if not execution.container_id:
            return

        try:
            log_stream = await self.container.logs(execution.container_id, stream=True, follow=True)

            async for log_line in log_stream:
                if log_line.strip():
                    yield LogEntry(
                        timestamp=datetime.now(UTC),
                        level="INFO",
                        message=log_line,
                        source="container",
                    )

        except PortError as e:
            logger.error(
                f"Error streaming logs for execution {execution.id}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_STREAM_LOGS_ERROR"},
            )
            yield LogEntry(
                timestamp=datetime.now(UTC),
                level="ERROR",
                message=f"Log streaming error: {e}",
                source="service",
            )

    def subscribe_to_logs(self, execution_id: str, callback: Callable[[LogEntry], None]) -> None:
        """
        Subscribe to log updates for an execution.

        Args:
            execution_id: Execution to subscribe to
            callback: Callback function for log entries
        """
        if execution_id not in self._log_subscribers:
            self._log_subscribers[execution_id] = []
        self._log_subscribers[execution_id].append(callback)

    def unsubscribe_from_logs(self, execution_id: str, callback: Callable[[LogEntry], None]) -> None:
        """
        Unsubscribe from log updates.

        Args:
            execution_id: Execution to unsubscribe from
            callback: Callback to remove
        """
        if execution_id in self._log_subscribers:
            self._log_subscribers[execution_id].remove(callback)
            if not self._log_subscribers[execution_id]:
                del self._log_subscribers[execution_id]

    # Helper methods

    def _build_llm_context(
        self, context: ExecutionContext, execution_id: ExecutionId | None = None
    ) -> LLMExecutionContext:
        """
        Build LLM execution context from domain context.

        Args:
            context: Domain execution context
            execution_id: AgentExecution.id to include in the LLM context

        Returns:
            LLM provider execution context
        """
        # Cast metadata to MappingProxyType for type safety.
        # LLMExecutionContext.__post_init__ will validate it at runtime.
        return LLMExecutionContext(
            model=context.model,
            timeout_seconds=context.timeout_seconds,
            environment_variables=MappingProxyType(context.environment_variables or {}),
            session_id=context.previous_session_id,
            execution_id=execution_id,
            metadata=cast("MappingProxyType", context.metadata),
            working_directory=Path(context.repository_path) if context.repository_path else None,
        )

    def _create_stream_callback(
        self, execution_id: str, user_callback: Callable[[str], None] | None
    ) -> Callable[[Any], Awaitable[None]]:
        """
        Create streaming callback that notifies subscribers and user callback.

        Args:
            execution_id: Execution ID
            user_callback: Optional user-provided callback

        Returns:
            Async callback function that accepts stream chunks
        """

        async def callback(chunk: Any) -> None:
            content = chunk.content if hasattr(chunk, "content") else str(chunk)

            # Notify log subscribers
            if execution_id in self._log_subscribers:
                log_entry = LogEntry(
                    timestamp=datetime.now(UTC),
                    level="INFO",
                    message=content,
                    source="llm",
                )
                for subscriber in self._log_subscribers[execution_id]:
                    try:
                        subscriber(log_entry)
                    except Exception as e:
                        logger.error(
                            f"Error in log subscriber: {e}",
                            exc_info=True,
                            extra={"error_id": "ERR_EXECUTION_LOG_SUBSCRIBER_ERROR"},
                        )

            # Call user callback
            if user_callback:
                try:
                    user_callback(content)
                except Exception as e:
                    logger.error(
                        f"Error in user stream callback: {e}",
                        exc_info=True,
                        extra={"error_id": "ERR_EXECUTION_USER_CALLBACK_ERROR"},
                    )

        return callback

    async def _stream_container_logs(
        self,
        container_id: str,
        execution_id: str,
        callback: Callable[[str], None],
    ) -> None:
        """
        Stream container logs to callback.

        Args:
            container_id: Container to stream from
            execution_id: Execution ID
            callback: Callback for log lines
        """
        try:
            log_stream = await self.container.logs(container_id, stream=True, follow=True)

            async for log_line in log_stream:
                if log_line.strip():
                    callback(log_line)

        except PortError as e:
            logger.error(
                f"Error streaming container logs: {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_STREAM_CONTAINER_LOGS_ERROR"},
            )

    def _stream_logs_done_callback(self, task: asyncio.Task[None]) -> None:
        """Handle completion of background log streaming task.

        Surfaces any unhandled exceptions from _stream_container_logs so they
        are not silently swallowed by asyncio's default task exception handler.

        Args:
            task: The completed asyncio.Task
        """
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(
                f"Unhandled exception in container log streaming: {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_LOG_STREAMING_EXCEPTION"},
            )

    def _extract_token_usage(self, logs: str) -> tuple[int, int]:
        """
        Extract token usage from logs.

        This method attempts to parse token usage from structured log output.
        If token information is not found, returns (0, 0).

        Expected log format: "Token usage: input=<N>, output=<M>"
        This format should be emitted by LLM provider adapters.

        Args:
            logs: Container logs

        Returns:
            Tuple of (input_tokens, output_tokens), or (0, 0) if not found
        """
        input_tokens = 0
        output_tokens = 0

        # Look for standardized token usage pattern
        # LLM provider adapters should emit this format
        pattern = r"Token usage: input=(\d+), output=(\d+)"
        match = re.search(pattern, logs)
        if match:
            input_tokens = int(match.group(1))
            output_tokens = int(match.group(2))
        else:
            # Token information not found in logs
            # This is expected if the LLM provider doesn't emit token usage
            logger.debug("Token usage information not found in logs")

        return input_tokens, output_tokens

    async def _cleanup_container_with_retry(self, container_id: str, max_attempts: int = 3) -> bool:
        """
        Clean up container with exponential backoff retry.

        Args:
            container_id: Container ID to clean up
            max_attempts: Maximum cleanup attempts

        Returns:
            True if cleanup succeeded, False otherwise
        """
        for attempt in range(max_attempts):
            try:
                # Stop container first
                await self.container.stop(container_id, timeout=5)

                # Then remove it
                await self.container.remove(container_id, force=True)

                logger.info(f"Successfully cleaned up container {container_id}")
                return True

            except ContainerExecutionError as e:
                logger.warning(
                    f"Cleanup attempt {attempt + 1}/{max_attempts} failed for container {container_id}: {e}",
                    extra={"error_id": "ERR_EXECUTION_CLEANUP_ATTEMPT_FAILURE"},
                )
                if attempt < max_attempts - 1:
                    # Exponential backoff: 1s, 2s, 4s
                    await asyncio.sleep(2**attempt)
                else:
                    logger.error(
                        f"Failed to cleanup container {container_id} after {max_attempts} attempts",
                        exc_info=True,
                        extra={"error_id": "ERR_EXECUTION_CLEANUP_FINAL_FAILURE"},
                    )
                    return False

        return False

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
