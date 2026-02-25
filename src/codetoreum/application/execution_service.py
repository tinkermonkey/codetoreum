"""Execution Service application service."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    cast,
)

from codetoreum.domain.agent import Agent
from codetoreum.domain.agent_execution import AgentExecution, ExecutionStatus
from codetoreum.domain.exceptions import DomainError
from codetoreum.domain.project_context import ProjectContext
from codetoreum.domain.types import (
    CONTAINER_LABEL_AGENT,
    CONTAINER_LABEL_EXECUTION_ID,
    CONTAINER_LABEL_PROJECT,
    CONTAINER_LABEL_TASK_ID,
    CONTAINER_LABEL_TYPE,
    CONTAINER_LABEL_WORK_ITEM_ID,
    CONTAINER_LABEL_WORKFLOW_RUN_ID,
)
from codetoreum.domain.value_objects import (
    ContainerConfig,
    ExecutionContext,
)
from codetoreum.domain.value_objects import ExecutionResult as DomainExecutionResult
from codetoreum.domain.work_item import WorkItem
from codetoreum.domain.workspace_context import WorkspaceContext
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
    StorageError,
)
from codetoreum.ports.output import IContainer, IEventStore, ILLMProvider, IStorage
from codetoreum.ports.output.llm_provider import ExecutionContext as LLMExecutionContext

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
    reason: Optional[str] = None
    error: Optional[str] = None
    failure_reason: Optional[ExecutionFailureReason] = None


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
        max_retries: int = 3,
        retry_delay_seconds: int = 5,
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
        """
        self.llm_provider = llm_provider
        self.container = container
        self.event_store = event_store
        self.storage = storage
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

        # Track active executions for streaming
        self._active_executions: Dict[str, AgentExecution] = {}
        self._log_subscribers: Dict[str, List[Callable[[LogEntry], None]]] = {}

    @instrument_async_function(
        name="execution.create_execution",
        attributes={"service": "execution_service", "operation": "create"}
    )
    async def create_execution(
        self,
        agent: Agent,
        work_item: WorkItem,
        workflow_id: str,
        stage_name: str,
        prompt: str,
        previous_session_id: Optional[str] = None,
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
                await self.event_store.append(event.aggregate_id, [event])
            execution.clear_events()

            logger.info(
                f"Created execution {execution.id} for agent {agent.name} "
                f"on work item {work_item.id}"
            )

            return execution

        except EventStoreError as e:
            logger.error(
                f"Failed to persist execution creation events: {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_CREATE_EVENT_STORE_FAILURE"}
            )
            raise
        except DomainError as e:
            logger.error(
                f"Failed to create execution (validation error): {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_CREATE_VALIDATION_FAILURE"}
            )
            raise

    @instrument_async_function(
        name="execution.start_execution",
        attributes={"service": "execution_service", "operation": "start"}
    )
    async def start_execution(
        self,
        execution: AgentExecution,
        context: ExecutionContext,
        container_config: Optional[ContainerConfig] = None,
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
                raise DomainError(
                    f"Execution {execution.id} is not in INITIALIZED state"
                )

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
                await self.event_store.append(event.aggregate_id, [event])
            execution.clear_events()

            logger.info(
                f"Started execution {execution.id} "
                f"(container: {container_name or 'none'})"
            )

            return ExecutionServiceResult(
                success=True,
                execution=execution,
                reason="Execution started successfully",
            )

        except EventStoreError as e:
            logger.error(
                f"Failed to persist start event for execution {execution.id}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_START_EVENT_STORE_FAILURE"}
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
                extra={"error_id": "ERR_EXECUTION_START_VALIDATION_FAILURE"}
            )
            return ExecutionServiceResult(
                success=False,
                execution=execution,
                error=str(e),
                failure_reason=ExecutionFailureReason.VALIDATION_ERROR,
            )

    @instrument_async_function(
        name="execution.execute_with_llm",
        attributes={"service": "execution_service", "operation": "execute_llm"}
    )
    async def execute_with_llm(
        self,
        execution: AgentExecution,
        context: ExecutionContext,
        stream_callback: Optional[Callable[[str], None]] = None,
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
        last_error: Optional[Exception] = None

        while retry_count <= self.max_retries:
            try:
                # Build LLM execution context
                llm_context = self._build_llm_context(context)

                # Execute with LLM
                result = await self.llm_provider.execute(
                    prompt=execution.prompt,
                    context=llm_context,
                    stream_callback=self._create_stream_callback(
                        execution.id, stream_callback
                    )
                    if stream_callback
                    else None,
                )

                # Complete execution successfully
                execution.complete(
                    output=result.content,
                    input_tokens=result.prompt_tokens,
                    output_tokens=result.completion_tokens,
                    session_id=result.metadata.get("session_id"),
                )

                # Persist events
                events = execution.get_pending_events()
                for event in events:
                    await self.event_store.append(event.aggregate_id, [event])
                execution.clear_events()

                # Clean up tracking
                self._active_executions.pop(execution.id, None)

                logger.info(
                    f"Completed execution {execution.id} successfully "
                    f"(tokens: {result.total_tokens})"
                )

                return ExecutionServiceResult(
                    success=True, execution=execution, reason="Execution completed"
                )

            except RateLimitError as e:
                logger.warning(
                    f"Rate limit hit for execution {execution.id}, "
                    f"retry {retry_count + 1}/{self.max_retries}",
                    extra={"error_id": "ERR_EXECUTION_LLM_RATE_LIMIT"}
                )
                last_error = e
                retry_count += 1
                if retry_count <= self.max_retries:
                    await asyncio.sleep(self.retry_delay_seconds * retry_count)
                continue

            except (ExternalServiceError, LLMProviderError) as e:
                logger.error(
                    f"LLM service error for execution {execution.id}: {e}, "
                    f"retry {retry_count + 1}/{self.max_retries}",
                    exc_info=True,
                    extra={"error_id": "ERR_EXECUTION_LLM_SERVICE_ERROR"}
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
                    extra={"error_id": "ERR_EXECUTION_EVENTSTORE_FAILURE"}
                )
                last_error = e
                break

            except DomainError as e:
                logger.error(
                    f"Domain validation error during execution {execution.id}: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_EXECUTION_DOMAIN_VALIDATION_FAILURE"}
                )
                last_error = e
                break

        # All retries exhausted, fail execution
        error_message = f"Execution failed after {retry_count} retries: {last_error}"
        execution.fail(error_message=error_message)

        # Persist failure events
        events = execution.get_pending_events()
        for event in events:
            await self.event_store.append(event.aggregate_id, [event])
        execution.clear_events()

        # Clean up tracking
        self._active_executions.pop(execution.id, None)

        logger.error(
            f"Failed execution {execution.id}: {error_message}",
            exc_info=True,
            extra={"error_id": "ERR_EXECUTION_RETRIES_EXHAUSTED"}
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
    ) -> Dict[str, str]:
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

    @instrument_async_function(
        name="execution.execute_with_container",
        attributes={"service": "execution_service", "operation": "execute_container"}
    )
    async def execute_with_container(
        self,
        execution: AgentExecution,
        context: ExecutionContext,
        container_config: ContainerConfig,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> ExecutionServiceResult:
        """
        Execute agent in Docker container.

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

            # Create container
            container_id = await self.container.create(
                image=container_config.image,
                name=execution.container_name,
                command=container_config.command,
                volumes=cast(Optional[Dict[str, str]], container_config.volumes),
                environment=container_config.environment or {},
                working_dir=container_config.working_dir,
                user=container_config.user,
                network=container_config.network,
                labels=labels,
            )

            logger.info(
                f"Created container {container_id} for execution {execution.id}"
            )

            # Start container
            await self.container.start(container_id)

            # Stream logs if callback provided
            if stream_callback:
                asyncio.create_task(
                    self._stream_container_logs(
                        container_id, execution.id, stream_callback
                    )
                )

            # Wait for container to complete
            exit_code = await self.container.wait(
                container_id, timeout=context.timeout_seconds
            )

            # Get output
            logs = await self.container.logs(container_id)

            # Extract token usage from logs (if available)
            input_tokens, output_tokens = self._extract_token_usage(logs)

            if exit_code == 0:
                # Complete execution successfully
                execution.complete(
                    output=logs,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )

                # Persist events
                events = execution.get_pending_events()
                for event in events:
                    await self.event_store.append(event.aggregate_id, [event])
                execution.clear_events()

                logger.info(f"Container execution {execution.id} completed successfully")

                return ExecutionServiceResult(
                    success=True,
                    execution=execution,
                    reason="Container execution completed",
                )
            else:
                # Execution failed
                error_message = f"Container exited with code {exit_code}"
                execution.fail(error_message=error_message, exit_code=exit_code)

                # Persist events
                events = execution.get_pending_events()
                for event in events:
                    await self.event_store.append(event.aggregate_id, [event])
                execution.clear_events()

                logger.error(
                    f"Container execution {execution.id} failed: {error_message}",
                    extra={"error_id": "ERR_EXECUTION_CONTAINER_EXIT_FAILURE"}
                )

                return ExecutionServiceResult(
                    success=False,
                    execution=execution,
                    error=error_message,
                    failure_reason=ExecutionFailureReason.CONTAINER_ERROR,
                )

        except ContainerTimeoutError as e:
            logger.error(
                f"Container execution {execution.id} timed out: {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_CONTAINER_TIMEOUT"}
            )
            execution.timeout()

            # Persist events
            events = execution.get_pending_events()
            for event in events:
                await self.event_store.append(event.aggregate_id, [event])
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
                extra={"error_id": "ERR_EXECUTION_CONTAINER_ERROR"}
            )

            error_message = f"Container execution error: {e}"
            execution.fail(error_message=error_message)

            # Persist events
            events = execution.get_pending_events()
            for event in events:
                await self.event_store.append(event.aggregate_id, [event])
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
                extra={"error_id": "ERR_EXECUTION_CONTAINER_EVENTSTORE_FAILURE"}
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
                cleanup_success = await self._cleanup_container_with_retry(
                    container_id, max_attempts=3
                )
                if not cleanup_success:
                    logger.error(
                        f"CRITICAL: Failed to cleanup container {container_id} after retries. "
                        f"Manual intervention may be required.",
                        extra={"error_id": "ERR_EXECUTION_CONTAINER_CLEANUP_CRITICAL"}
                    )

            # Clean up tracking
            self._active_executions.pop(execution.id, None)

    @instrument_async_function(
        name="execution.cancel_execution",
        attributes={"service": "execution_service", "operation": "cancel"}
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
                    cleanup_success = await self._cleanup_container_with_retry(
                        execution.container_id, max_attempts=3
                    )
                    if not cleanup_success:
                        logger.error(
                            f"Failed to stop container {execution.container_id} during cancellation",
                            extra={"error_id": "ERR_EXECUTION_CANCEL_CONTAINER_STOP_FAILURE"}
                        )

                # Mark as failed
                execution.fail(error_message="Execution cancelled by user")

                # Persist events
                events = execution.get_pending_events()
                for event in events:
                    await self.event_store.append(event.aggregate_id, [event])
                execution.clear_events()

                # Clean up tracking
                self._active_executions.pop(execution.id, None)

                logger.info(f"Cancelled execution {execution.id}")

                return ExecutionServiceResult(
                    success=True, execution=execution, reason="Execution cancelled"
                )
            else:
                return ExecutionServiceResult(
                    success=False,
                    execution=execution,
                    error="Execution already in terminal state",
                )

        except EventStoreError as e:
            logger.error(
                f"Failed to persist cancellation for execution {execution.id}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_CANCEL_EVENTSTORE_FAILURE"}
            )
            return ExecutionServiceResult(
                success=False, execution=execution, error=str(e)
            )
        except DomainError as e:
            logger.error(
                f"Domain error during cancellation of execution {execution.id}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_CANCEL_DOMAIN_FAILURE"}
            )
            return ExecutionServiceResult(
                success=False, execution=execution, error=str(e)
            )

    async def get_execution_logs(
        self, execution: AgentExecution, tail: Optional[int] = None
    ) -> List[LogEntry]:
        """
        Get execution logs.

        Args:
            execution: AgentExecution to get logs for
            tail: Optional number of lines from end

        Returns:
            List of log entries
        """
        logs: List[LogEntry] = []

        try:
            if execution.container_id:
                # Get container logs
                container_logs = await self.container.logs(
                    execution.container_id, stream=False, tail=tail
                )

                # Parse logs into entries
                for line in container_logs.split("\n"):
                    if line.strip():
                        logs.append(
                            LogEntry(
                                timestamp=datetime.now(timezone.utc),
                                level="INFO",
                                message=line,
                                source="container",
                            )
                        )

        except ContainerExecutionError as e:
            logger.error(
                f"Container error getting logs for execution {execution.id}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_GET_LOGS_CONTAINER_ERROR"}
            )
            # Return empty list on container errors
        except PortError as e:
            logger.error(
                f"Unexpected error getting logs for execution {execution.id}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_GET_LOGS_UNEXPECTED_ERROR"}
            )
            # Return empty list on unexpected errors

        return logs

    async def stream_execution_logs(
        self, execution: AgentExecution
    ) -> AsyncIterator[LogEntry]:
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
            log_stream = await self.container.logs(
                execution.container_id, stream=True, follow=True
            )

            async for log_line in log_stream:
                if log_line.strip():
                    yield LogEntry(
                        timestamp=datetime.now(timezone.utc),
                        level="INFO",
                        message=log_line,
                        source="container",
                    )

        except PortError as e:
            logger.error(
                f"Error streaming logs for execution {execution.id}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_STREAM_LOGS_ERROR"}
            )
            yield LogEntry(
                timestamp=datetime.now(timezone.utc),
                level="ERROR",
                message=f"Log streaming error: {e}",
                source="service",
            )

    def subscribe_to_logs(
        self, execution_id: str, callback: Callable[[LogEntry], None]
    ) -> None:
        """
        Subscribe to log updates for an execution.

        Args:
            execution_id: Execution to subscribe to
            callback: Callback function for log entries
        """
        if execution_id not in self._log_subscribers:
            self._log_subscribers[execution_id] = []
        self._log_subscribers[execution_id].append(callback)

    def unsubscribe_from_logs(
        self, execution_id: str, callback: Callable[[LogEntry], None]
    ) -> None:
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
        self, context: ExecutionContext
    ) -> LLMExecutionContext:
        """
        Build LLM execution context from domain context.

        Args:
            context: Domain execution context

        Returns:
            LLM provider execution context
        """
        return LLMExecutionContext(
            model=context.model,
            timeout_seconds=context.timeout_seconds,
            environment_variables=context.metadata,
            session_id=context.previous_session_id,
            execution_id=None,  # Will be set by provider
            metadata=context.metadata,
        )

    def _create_stream_callback(
        self, execution_id: str, user_callback: Optional[Callable[[str], None]]
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
                    timestamp=datetime.now(timezone.utc),
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
                            extra={"error_id": "ERR_EXECUTION_LOG_SUBSCRIBER_ERROR"}
                        )

            # Call user callback
            if user_callback:
                try:
                    user_callback(content)
                except Exception as e:
                    logger.error(
                        f"Error in user stream callback: {e}",
                        exc_info=True,
                        extra={"error_id": "ERR_EXECUTION_USER_CALLBACK_ERROR"}
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
            log_stream = await self.container.logs(
                container_id, stream=True, follow=True
            )

            async for log_line in log_stream:
                if log_line.strip():
                    callback(log_line)

        except PortError as e:
            logger.error(
                f"Error streaming container logs: {e}",
                exc_info=True,
                extra={"error_id": "ERR_EXECUTION_STREAM_CONTAINER_LOGS_ERROR"}
            )

    def _extract_token_usage(self, logs: str) -> Tuple[int, int]:
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
        import re

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

    async def _cleanup_container_with_retry(
        self, container_id: str, max_attempts: int = 3
    ) -> bool:
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
                    f"Cleanup attempt {attempt + 1}/{max_attempts} failed for "
                    f"container {container_id}: {e}",
                    extra={"error_id": "ERR_EXECUTION_CLEANUP_ATTEMPT_FAILURE"}
                )
                if attempt < max_attempts - 1:
                    # Exponential backoff: 1s, 2s, 4s
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.error(
                        f"Failed to cleanup container {container_id} after {max_attempts} attempts",
                        extra={"error_id": "ERR_EXECUTION_CLEANUP_FINAL_FAILURE"}
                    )
                    return False

        return False

    def _classify_failure(
        self, error: Optional[Exception]
    ) -> ExecutionFailureReason:
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
        elif isinstance(error, ContainerTimeoutError):
            return ExecutionFailureReason.TIMEOUT
        elif isinstance(error, ContainerExecutionError):
            return ExecutionFailureReason.CONTAINER_ERROR
        elif isinstance(error, ExternalServiceError):
            return ExecutionFailureReason.LLM_ERROR
        elif isinstance(error, (ValueError, DomainError)):
            return ExecutionFailureReason.VALIDATION_ERROR
        else:
            return ExecutionFailureReason.UNKNOWN
