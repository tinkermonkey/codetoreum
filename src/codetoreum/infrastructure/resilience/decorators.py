"""Resilient adapter decorators.

Provides decorators that wrap port interfaces with resilience patterns.
"""

from collections.abc import AsyncIterator, Callable
from datetime import datetime
from typing import Any, TypeVar

from codetoreum.domain.comment import Comment
from codetoreum.domain.types import ProjectId, UserId, WorkItemId
from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus
from codetoreum.ports.output.board_service import (
    BoardColumn,
    BoardConfig,
    ColumnMovementResult,
    IBoardService,
    MovedByType,
    ProjectBoard,
    ReconciliationResult,
    WorkItemPosition,
)
from codetoreum.ports.output.discussion_adapter import IDiscussionAdapter
from codetoreum.ports.output.llm_provider import (
    ExecutionContext,
    ExecutionResult,
    ILLMProvider,
    ModelInfo,
    StreamCallback,
    StreamChunk,
    ToolDefinition,
    UsageStats,
)
from codetoreum.ports.output.monitoring import MonitoringConfig, MonitoringStatus
from codetoreum.ports.output.ticket_system import ITicketSystem

from .interfaces import ICircuitBreaker, IRateLimiter, IRetryPolicy, ITimeout

T = TypeVar("T")


# ============================================================================
# Resilient Ticket System Decorator
# ============================================================================


class ResilientTicketSystemDecorator(ITicketSystem):
    """
    Wraps ITicketSystem with resilience patterns.

    Applies rate limiting, circuit breaking, retries, and timeouts
    to all ticket system operations.
    """

    def __init__(
        self,
        wrapped: ITicketSystem,
        rate_limiter: IRateLimiter | None = None,
        circuit_breaker: ICircuitBreaker | None = None,
        retry_policy: IRetryPolicy | None = None,
        timeout: ITimeout | None = None,
        default_timeout_seconds: float = 30.0,
    ):
        """
        Initialize resilient decorator.

        Args:
            wrapped: Underlying ticket system adapter
            rate_limiter: Optional rate limiter
            circuit_breaker: Optional circuit breaker
            retry_policy: Optional retry policy
            timeout: Optional timeout handler
            default_timeout_seconds: Default operation timeout
        """
        self._wrapped = wrapped
        self._rate_limiter = rate_limiter
        self._circuit_breaker = circuit_breaker
        self._retry_policy = retry_policy
        self._timeout = timeout
        self._default_timeout = default_timeout_seconds

    async def get_work_item(self, item_id: WorkItemId) -> WorkItem:
        """Get work item with full resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.get_work_item(item_id),
            operation_name="get_work_item",
            rate_limit_cost=1,
        )

    async def create_work_item(
        self,
        title: str,
        description: str,
        project_id: ProjectId,
        labels: list[str] | None = None,
        assignee: UserId | None = None,
        priority: WorkItemPriority | None = None,
        metadata: dict[str, Any] | None = None,
        parent_issue_id: str | None = None,
    ) -> WorkItem:
        """Create work item with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.create_work_item(
                title, description, project_id, labels, assignee, priority, metadata, parent_issue_id
            ),
            operation_name="create_work_item",
            rate_limit_cost=2,  # Writes cost more
        )

    async def get_child_issues(self, parent_id: WorkItemId) -> list[WorkItem]:
        """Get child issues with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.get_child_issues(parent_id),
            operation_name="get_child_issues",
            rate_limit_cost=1,
        )

    async def update_work_item(self, item_id: WorkItemId, updates: dict[str, Any]) -> WorkItem:
        """Update work item with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.update_work_item(item_id, updates),
            operation_name="update_work_item",
            rate_limit_cost=2,
        )

    async def delete_work_item(self, item_id: WorkItemId) -> None:
        """Delete work item with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.delete_work_item(item_id),
            operation_name="delete_work_item",
            rate_limit_cost=2,
        )

    async def update_status(
        self,
        item_id: WorkItemId,
        status: WorkItemStatus,
        reason: str | None = None,
    ) -> WorkItem:
        """Update status with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.update_status(item_id, status, reason),
            operation_name="update_status",
            rate_limit_cost=2,
        )

    async def list_work_items(
        self,
        project_id: ProjectId | None = None,
        status: WorkItemStatus | None = None,
        assignee: UserId | None = None,
        labels: list[str] | None = None,
        created_after: datetime | None = None,
        updated_after: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[WorkItem]:
        """List work items with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.list_work_items(
                project_id, status, assignee, labels, created_after, updated_after, limit, offset
            ),
            operation_name="list_work_items",
            rate_limit_cost=1,
        )

    async def search_work_items(
        self,
        query: str,
        project_id: ProjectId | None = None,
        limit: int = 100,
    ) -> list[WorkItem]:
        """Search work items with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.search_work_items(query, project_id, limit),
            operation_name="search_work_items",
            rate_limit_cost=1,
        )

    async def get_work_item_stream(
        self,
        project_id: ProjectId | None = None,
        since: datetime | None = None,
    ) -> AsyncIterator[WorkItem]:
        """Stream work items (streaming doesn't work well with retries)."""
        # Streaming operations don't benefit from retries
        # Apply rate limiting and circuit breaker only
        if self._rate_limiter:
            await self._rate_limiter.acquire("get_work_item_stream", 1)

        if self._circuit_breaker:

            async def stream_operation():
                return self._wrapped.get_work_item_stream(project_id, since)

            return await self._circuit_breaker.call(stream_operation, "get_work_item_stream")
        return self._wrapped.get_work_item_stream(project_id, since)

    async def add_comment(
        self,
        item_id: WorkItemId,
        body: str,
        author: UserId | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Comment:
        """Add comment with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.add_comment(item_id, body, author, metadata),
            operation_name="add_comment",
            rate_limit_cost=1,
        )

    async def get_comments(
        self,
        item_id: WorkItemId,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[Comment]:
        """Get comments with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.get_comments(item_id, since, limit),
            operation_name="get_comments",
            rate_limit_cost=1,
        )

    async def link_work_items(
        self,
        source_id: WorkItemId,
        target_id: WorkItemId,
        relationship: str,
    ) -> None:
        """Link work items with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.link_work_items(source_id, target_id, relationship),
            operation_name="link_work_items",
            rate_limit_cost=2,
        )

    async def get_related_items(
        self,
        item_id: WorkItemId,
        relationship: str | None = None,
    ) -> list[WorkItem]:
        """Get related items with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.get_related_items(item_id, relationship),
            operation_name="get_related_items",
            rate_limit_cost=1,
        )

    async def register_webhook(
        self,
        url: str,
        events: list[str],
        project_id: ProjectId | None = None,
    ) -> str:
        """Register webhook with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.register_webhook(url, events, project_id),
            operation_name="register_webhook",
            rate_limit_cost=2,
        )

    async def unregister_webhook(self, webhook_id: str) -> None:
        """Unregister webhook with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.unregister_webhook(webhook_id),
            operation_name="unregister_webhook",
            rate_limit_cost=2,
        )

    async def _execute_resilient(
        self,
        operation: Callable[[], T],
        operation_name: str,
        rate_limit_cost: int = 1,
        timeout_seconds: float | None = None,
    ) -> T:
        """
        Execute operation with all resilience patterns.

        Order of application:
        1. Rate limiting (prevent overload)
        2. Circuit breaker (fail fast if unhealthy)
        3. Timeout (prevent hanging)
        4. Retry (handle transient errors)
        """
        # 1. Rate limiting
        if self._rate_limiter:
            await self._rate_limiter.acquire(operation_name, rate_limit_cost)

        # 2. Circuit breaker wraps the rest
        if self._circuit_breaker:
            return await self._circuit_breaker.call(
                self._execute_with_timeout_and_retry,
                operation_name,
                operation,
                operation_name,
                timeout_seconds or self._default_timeout,
            )
        return await self._execute_with_timeout_and_retry(
            operation, operation_name, timeout_seconds or self._default_timeout
        )

    async def _execute_with_timeout_and_retry(
        self, operation: Callable[[], T], operation_name: str, timeout_seconds: float
    ) -> T:
        """Apply timeout and retry."""

        # 3. Timeout wraps operation
        async def timed_operation():
            if self._timeout:
                return await self._timeout.execute(operation, timeout_seconds, operation_name)
            return await operation()

        # 4. Retry wraps timeout
        if self._retry_policy:
            return await self._retry_policy.execute(timed_operation, operation_name)
        return await timed_operation()


# ============================================================================
# Resilient LLM Provider Decorator
# ============================================================================


class ResilientLLMProviderDecorator(ILLMProvider):
    """
    Wraps ILLMProvider with resilience patterns.

    Special considerations for LLMs:
    - Token-based rate limiting (not just request count)
    - Longer timeouts (LLM calls can take minutes)
    - Less aggressive retries (LLM calls are expensive)
    """

    def __init__(
        self,
        wrapped: ILLMProvider,
        rate_limiter: IRateLimiter | None = None,
        circuit_breaker: ICircuitBreaker | None = None,
        retry_policy: IRetryPolicy | None = None,
        timeout: ITimeout | None = None,
        default_timeout_seconds: float = 300.0,  # 5 minutes for LLM
    ):
        self._wrapped = wrapped
        self._rate_limiter = rate_limiter
        self._circuit_breaker = circuit_breaker
        self._retry_policy = retry_policy
        self._timeout = timeout
        self._default_timeout = default_timeout_seconds

    async def execute(
        self,
        prompt: str,
        context: ExecutionContext | None = None,
        stream_callback: StreamCallback | None = None,
    ) -> ExecutionResult:
        """Execute with resilience."""
        # Estimate token cost for rate limiting
        estimated_tokens = self._estimate_tokens(prompt)

        return await self._execute_resilient(
            operation=lambda: self._wrapped.execute(prompt, context, stream_callback),
            operation_name="llm_execute",
            rate_limit_cost=estimated_tokens,
        )

    async def execute_with_tools(
        self,
        prompt: str,
        tools: list[ToolDefinition],
        context: ExecutionContext | None = None,
        stream_callback: StreamCallback | None = None,
    ) -> ExecutionResult:
        """Execute with tools and resilience."""
        estimated_tokens = self._estimate_tokens(prompt)

        return await self._execute_resilient(
            operation=lambda: self._wrapped.execute_with_tools(prompt, tools, context, stream_callback),
            operation_name="llm_execute_with_tools",
            rate_limit_cost=estimated_tokens,
        )

    async def stream_completion(
        self,
        prompt: str,
        context: ExecutionContext | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream completion (less resilience for streaming)."""
        # Streaming doesn't work well with retries
        if self._rate_limiter:
            estimated_tokens = self._estimate_tokens(prompt)
            await self._rate_limiter.acquire("stream_completion", estimated_tokens)

        if self._circuit_breaker:

            async def stream_operation():
                return self._wrapped.stream_completion(prompt, context)

            return await self._circuit_breaker.call(stream_operation, "stream_completion")
        return self._wrapped.stream_completion(prompt, context)

    async def create_conversation(
        self,
        system_prompt: str | None = None,
        parameters: ExecutionContext | None = None,
    ) -> str:
        """Create conversation with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.create_conversation(system_prompt, parameters),
            operation_name="create_conversation",
            rate_limit_cost=1,
        )

    async def continue_conversation(
        self,
        conversation_id: str,
        message: str,
        stream_callback: StreamCallback | None = None,
    ) -> ExecutionResult:
        """Continue conversation with resilience."""
        estimated_tokens = self._estimate_tokens(message)

        return await self._execute_resilient(
            operation=lambda: self._wrapped.continue_conversation(conversation_id, message, stream_callback),
            operation_name="continue_conversation",
            rate_limit_cost=estimated_tokens,
        )

    async def get_model_info(self) -> ModelInfo:
        """Get model info with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.get_model_info(),
            operation_name="get_model_info",
            rate_limit_cost=1,
        )

    async def list_available_models(self) -> list[ModelInfo]:
        """List models with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.list_available_models(),
            operation_name="list_available_models",
            rate_limit_cost=1,
        )

    async def count_tokens(
        self,
        text: str,
        model: str | None = None,
    ) -> int:
        """Count tokens with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.count_tokens(text, model),
            operation_name="count_tokens",
            rate_limit_cost=1,
        )

    async def get_usage_stats(
        self,
        since: datetime | None = None,
    ) -> UsageStats:
        """Get usage stats with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.get_usage_stats(since),
            operation_name="get_usage_stats",
            rate_limit_cost=1,
        )

    async def _execute_resilient(self, operation: Callable[[], T], operation_name: str, rate_limit_cost: int) -> T:
        """Execute with resilience patterns."""
        # Rate limiting with token cost
        if self._rate_limiter:
            await self._rate_limiter.acquire(operation_name, rate_limit_cost)

        # Circuit breaker
        if self._circuit_breaker:
            return await self._circuit_breaker.call(
                self._execute_with_timeout_and_retry, operation_name, operation, operation_name
            )
        return await self._execute_with_timeout_and_retry(operation, operation_name)

    async def _execute_with_timeout_and_retry(self, operation: Callable[[], T], operation_name: str) -> T:
        """Apply timeout and retry."""

        async def timed_operation():
            if self._timeout:
                return await self._timeout.execute(operation, self._default_timeout, operation_name)
            return await operation()

        if self._retry_policy:
            return await self._retry_policy.execute(timed_operation, operation_name)
        return await timed_operation()

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (4 chars per token)."""
        return max(1, len(text) // 4)


# ============================================================================
# Resilient Board Service Decorator
# ============================================================================


class ResilientBoardServiceDecorator(IBoardService):
    """
    Wraps IBoardService with resilience patterns.

    Applies rate limiting, circuit breaking, retries, and timeouts
    to all board service operations.
    """

    def __init__(
        self,
        wrapped: IBoardService,
        rate_limiter: IRateLimiter | None = None,
        circuit_breaker: ICircuitBreaker | None = None,
        retry_policy: IRetryPolicy | None = None,
        timeout: ITimeout | None = None,
        default_timeout_seconds: float = 30.0,
    ):
        """
        Initialize resilient board service decorator.

        Args:
            wrapped: Underlying board service adapter
            rate_limiter: Optional rate limiter (respects GitHub 5000 req/hr limit)
            circuit_breaker: Optional circuit breaker
            retry_policy: Optional retry policy
            timeout: Optional timeout handler
            default_timeout_seconds: Default operation timeout
        """
        self._wrapped = wrapped
        self._rate_limiter = rate_limiter
        self._circuit_breaker = circuit_breaker
        self._retry_policy = retry_policy
        self._timeout = timeout
        self._default_timeout = default_timeout_seconds

    # IEventEmitter implementation (pass through)

    def on(self, event_type: str, handler: Callable) -> None:
        """Register event handler."""
        self._wrapped.on(event_type, handler)

    def off(self, event_type: str, handler: Callable) -> None:
        """Unregister event handler."""
        self._wrapped.off(event_type, handler)

    def emit(self, event: Any) -> None:
        """Emit event."""
        self._wrapped.emit(event)

    # IMonitoredService implementation

    async def start_monitoring(self, project_id: str, config: MonitoringConfig) -> None:
        """Start monitoring with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.start_monitoring(project_id, config),
            operation_name="start_monitoring",
            rate_limit_cost=1,
        )

    async def stop_monitoring(self, project_id: str) -> None:
        """Stop monitoring with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.stop_monitoring(project_id),
            operation_name="stop_monitoring",
            rate_limit_cost=1,
        )

    async def get_monitoring_status(self, project_id: str) -> MonitoringStatus:
        """Get monitoring status."""
        return await self._wrapped.get_monitoring_status(project_id)

    # Query Operations

    async def get_board(self, project_id: str, board_id: str) -> ProjectBoard:
        """Get board with resilience (1 GraphQL credit)."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.get_board(project_id, board_id),
            operation_name="get_board",
            rate_limit_cost=1,
        )

    async def get_columns(self, board_id: str) -> list[BoardColumn]:
        """Get columns with resilience (1 GraphQL credit)."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.get_columns(board_id),
            operation_name="get_columns",
            rate_limit_cost=1,
        )

    async def get_items_in_column(self, board_id: str, column_name: str):
        """Get items in column with resilience (1 GraphQL credit)."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.get_items_in_column(board_id, column_name),
            operation_name="get_items_in_column",
            rate_limit_cost=1,
        )

    async def get_item_position(self, work_item_id: str) -> WorkItemPosition:
        """Get item position with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.get_item_position(work_item_id),
            operation_name="get_item_position",
            rate_limit_cost=1,
        )

    async def get_all_boards(self) -> list[ProjectBoard]:
        """Get all boards with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.get_all_boards(),
            operation_name="get_all_boards",
            rate_limit_cost=1,
        )

    async def get_board_items(self, project_id: str, board_id: str) -> list[WorkItemPosition]:
        """Get board items with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.get_board_items(project_id, board_id),
            operation_name="get_board_items",
            rate_limit_cost=1,
        )

    # Command Operations

    async def move_item_to_column(self, work_item_id: str, target_column: str, moved_by: MovedByType):
        """Move item with resilience (1 GraphQL mutation)."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.move_item_to_column(work_item_id, target_column, moved_by),
            operation_name="move_item_to_column",
            rate_limit_cost=1,
        )

    async def add_item_to_column(self, work_item_id: str, target_column: str, moved_by: MovedByType) -> ColumnMovementResult:
        """Add item to initial column with resilience (1 GraphQL mutation)."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.add_item_to_column(work_item_id, target_column, moved_by),
            operation_name="add_item_to_column",
            rate_limit_cost=1,
        )

    async def reconcile_board(self, board_id: str, config: BoardConfig) -> ReconciliationResult:
        """Reconcile board with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.reconcile_board(board_id, config),
            operation_name="reconcile_board",
            rate_limit_cost=5,  # May create multiple columns
        )

    # Webhook Handler

    async def handle_webhook(self, payload: dict) -> None:
        """Handle webhook (no rate limiting, no retries)."""
        # Webhooks should fail fast, no retries
        return await self._wrapped.handle_webhook(payload)

    # Resilience execution

    async def _execute_resilient(
        self,
        operation: Callable[[], T],
        operation_name: str,
        rate_limit_cost: int = 1,
        timeout_seconds: float | None = None,
    ) -> T:
        """
        Execute operation with all resilience patterns.

        Order of application:
        1. Rate limiting (respect GitHub 5000 req/hr limit)
        2. Circuit breaker (fail fast if unhealthy)
        3. Timeout (prevent hanging)
        4. Retry (handle transient errors)
        """
        # 1. Rate limiting
        if self._rate_limiter:
            await self._rate_limiter.acquire(operation_name, rate_limit_cost)

        # 2. Circuit breaker wraps the rest
        if self._circuit_breaker:
            return await self._circuit_breaker.call(
                self._execute_with_timeout_and_retry,
                operation_name,
                operation,
                operation_name,
                timeout_seconds or self._default_timeout,
            )
        return await self._execute_with_timeout_and_retry(
            operation, operation_name, timeout_seconds or self._default_timeout
        )

    async def _execute_with_timeout_and_retry(
        self, operation: Callable[[], T], operation_name: str, timeout_seconds: float
    ) -> T:
        """Apply timeout and retry."""

        # 3. Timeout wraps operation
        async def timed_operation():
            if self._timeout:
                return await self._timeout.execute(operation, timeout_seconds, operation_name)
            return await operation()

        # 4. Retry wraps timeout
        if self._retry_policy:
            return await self._retry_policy.execute(timed_operation, operation_name)
        return await timed_operation()


# ============================================================================
# Resilient Discussion Adapter Decorator
# ============================================================================


class ResilientDiscussionAdapterDecorator(IDiscussionAdapter):
    """
    Wraps IDiscussionAdapter with resilience patterns.

    Applies rate limiting, circuit breaking, retries, and timeouts
    to all discussion adapter operations.
    """

    def __init__(
        self,
        wrapped,
        rate_limiter: IRateLimiter | None = None,
        circuit_breaker: ICircuitBreaker | None = None,
        retry_policy: IRetryPolicy | None = None,
        timeout: ITimeout | None = None,
        default_timeout_seconds: float = 30.0,
    ):
        """
        Initialize resilient decorator.

        Args:
            wrapped: Underlying discussion adapter
            rate_limiter: Optional rate limiter
            circuit_breaker: Optional circuit breaker
            retry_policy: Optional retry policy
            timeout: Optional timeout handler
            default_timeout_seconds: Default operation timeout
        """
        self._wrapped = wrapped
        self._rate_limiter = rate_limiter
        self._circuit_breaker = circuit_breaker
        self._retry_policy = retry_policy
        self._timeout = timeout
        self._default_timeout = default_timeout_seconds

    async def get_thread(self, work_item_id: str):
        """Retrieve thread with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.get_thread(work_item_id),
            operation_name="discussion_get_thread",
            rate_limit_cost=1,
        )

    async def add_comment(
        self,
        work_item_id: str,
        content: str,
        parent_id: str | None = None,
    ):
        """Add comment with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.add_comment(work_item_id, content, parent_id),
            operation_name="discussion_add_comment",
            rate_limit_cost=2,  # Writes cost more
        )

    def start_monitoring(self, work_item_id: str, config) -> None:
        """Start monitoring (synchronous, no resilience wrapper)."""
        return self._wrapped.start_monitoring(work_item_id, config)

    def stop_monitoring(self, work_item_id: str) -> None:
        """Stop monitoring (synchronous, no resilience wrapper)."""
        return self._wrapped.stop_monitoring(work_item_id)

    async def handle_webhook(self, payload: dict) -> None:
        """Handle webhook with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.handle_webhook(payload),
            operation_name="discussion_handle_webhook",
            rate_limit_cost=1,
        )

    def on(self, event_type: str, handler) -> None:
        """Register event handler (pass through)."""
        return self._wrapped.on(event_type, handler)

    def off(self, event_type: str, handler) -> None:
        """Unregister event handler (pass through)."""
        return self._wrapped.off(event_type, handler)

    def emit(self, event) -> None:
        """Emit event (pass through)."""
        return self._wrapped.emit(event)

    async def close(self) -> None:
        """Close underlying adapter (pass through)."""
        return await self._wrapped.close()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
        return False

    async def _execute_resilient(
        self,
        operation: Callable[[], T],
        operation_name: str,
        rate_limit_cost: int = 1,
        timeout_seconds: float | None = None,
    ) -> T:
        """
        Execute operation with all resilience patterns.

        Order of application:
        1. Rate limiting (prevent overload)
        2. Circuit breaker (fail fast if unhealthy)
        3. Timeout (prevent hanging)
        4. Retry (handle transient errors)
        """
        # 1. Rate limiting
        if self._rate_limiter:
            await self._rate_limiter.acquire(operation_name, rate_limit_cost)

        # 2. Circuit breaker wraps the rest
        if self._circuit_breaker:
            return await self._circuit_breaker.call(
                self._execute_with_timeout_and_retry,
                operation_name,
                operation,
                operation_name,
                timeout_seconds or self._default_timeout,
            )
        return await self._execute_with_timeout_and_retry(
            operation, operation_name, timeout_seconds or self._default_timeout
        )

    async def _execute_with_timeout_and_retry(
        self, operation: Callable[[], T], operation_name: str, timeout_seconds: float
    ) -> T:
        """Apply timeout and retry."""

        # 3. Timeout wraps operation
        async def timed_operation():
            if self._timeout:
                return await self._timeout.execute(operation, timeout_seconds, operation_name)
            return await operation()

        # 4. Retry wraps timeout
        if self._retry_policy:
            return await self._retry_policy.execute(timed_operation, operation_name)
        return await timed_operation()
