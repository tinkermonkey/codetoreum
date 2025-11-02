"""Resilient adapter decorators.

Provides decorators that wrap port interfaces with resilience patterns.
"""

import time
from datetime import datetime
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, TypeVar

from codetoreum.domain.comment import Comment
from codetoreum.domain.types import ExecutionId, ProjectId, UserId, WorkItemId
from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus
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
from codetoreum.ports.output.ticket_system import ITicketSystem

from .interfaces import ICircuitBreaker, IRateLimiter, IRetryPolicy, ITimeout


T = TypeVar('T')


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
        rate_limiter: Optional[IRateLimiter] = None,
        circuit_breaker: Optional[ICircuitBreaker] = None,
        retry_policy: Optional[IRetryPolicy] = None,
        timeout: Optional[ITimeout] = None,
        default_timeout_seconds: float = 30.0
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
            rate_limit_cost=1
        )

    async def create_work_item(
        self,
        title: str,
        description: str,
        project_id: ProjectId,
        labels: Optional[List[str]] = None,
        assignee: Optional[UserId] = None,
        priority: Optional[WorkItemPriority] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> WorkItem:
        """Create work item with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.create_work_item(
                title, description, project_id, labels, assignee, priority, metadata
            ),
            operation_name="create_work_item",
            rate_limit_cost=2  # Writes cost more
        )

    async def update_work_item(
        self, item_id: WorkItemId, updates: Dict[str, Any]
    ) -> WorkItem:
        """Update work item with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.update_work_item(item_id, updates),
            operation_name="update_work_item",
            rate_limit_cost=2
        )

    async def delete_work_item(self, item_id: WorkItemId) -> None:
        """Delete work item with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.delete_work_item(item_id),
            operation_name="delete_work_item",
            rate_limit_cost=2
        )

    async def update_status(
        self,
        item_id: WorkItemId,
        status: WorkItemStatus,
        reason: Optional[str] = None,
    ) -> WorkItem:
        """Update status with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.update_status(item_id, status, reason),
            operation_name="update_status",
            rate_limit_cost=2
        )

    async def list_work_items(
        self,
        project_id: Optional[ProjectId] = None,
        status: Optional[WorkItemStatus] = None,
        assignee: Optional[UserId] = None,
        labels: Optional[List[str]] = None,
        created_after: Optional[datetime] = None,
        updated_after: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[WorkItem]:
        """List work items with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.list_work_items(
                project_id, status, assignee, labels, created_after, updated_after, limit, offset
            ),
            operation_name="list_work_items",
            rate_limit_cost=1
        )

    async def search_work_items(
        self,
        query: str,
        project_id: Optional[ProjectId] = None,
        limit: int = 100,
    ) -> List[WorkItem]:
        """Search work items with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.search_work_items(query, project_id, limit),
            operation_name="search_work_items",
            rate_limit_cost=1
        )

    async def get_work_item_stream(
        self,
        project_id: Optional[ProjectId] = None,
        since: Optional[datetime] = None,
    ) -> AsyncIterator[WorkItem]:
        """Stream work items (streaming doesn't work well with retries)."""
        # Streaming operations don't benefit from retries
        # Apply rate limiting and circuit breaker only
        if self._rate_limiter:
            await self._rate_limiter.acquire("get_work_item_stream", 1)

        if self._circuit_breaker:
            async def stream_operation():
                return self._wrapped.get_work_item_stream(project_id, since)
            return await self._circuit_breaker.call(
                stream_operation,
                "get_work_item_stream"
            )
        else:
            return self._wrapped.get_work_item_stream(project_id, since)

    async def add_comment(
        self,
        item_id: WorkItemId,
        body: str,
        author: Optional[UserId] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Comment:
        """Add comment with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.add_comment(item_id, body, author, metadata),
            operation_name="add_comment",
            rate_limit_cost=1
        )

    async def get_comments(
        self,
        item_id: WorkItemId,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Comment]:
        """Get comments with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.get_comments(item_id, since, limit),
            operation_name="get_comments",
            rate_limit_cost=1
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
            rate_limit_cost=2
        )

    async def get_related_items(
        self,
        item_id: WorkItemId,
        relationship: Optional[str] = None,
    ) -> List[WorkItem]:
        """Get related items with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.get_related_items(item_id, relationship),
            operation_name="get_related_items",
            rate_limit_cost=1
        )

    async def register_webhook(
        self,
        url: str,
        events: List[str],
        project_id: Optional[ProjectId] = None,
    ) -> str:
        """Register webhook with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.register_webhook(url, events, project_id),
            operation_name="register_webhook",
            rate_limit_cost=2
        )

    async def unregister_webhook(self, webhook_id: str) -> None:
        """Unregister webhook with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.unregister_webhook(webhook_id),
            operation_name="unregister_webhook",
            rate_limit_cost=2
        )

    async def _execute_resilient(
        self,
        operation: Callable[[], T],
        operation_name: str,
        rate_limit_cost: int = 1,
        timeout_seconds: Optional[float] = None
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
                timeout_seconds or self._default_timeout
            )
        else:
            return await self._execute_with_timeout_and_retry(
                operation,
                operation_name,
                timeout_seconds or self._default_timeout
            )

    async def _execute_with_timeout_and_retry(
        self,
        operation: Callable[[], T],
        operation_name: str,
        timeout_seconds: float
    ) -> T:
        """Apply timeout and retry."""
        # 3. Timeout wraps operation
        async def timed_operation():
            if self._timeout:
                return await self._timeout.execute(
                    operation,
                    timeout_seconds,
                    operation_name
                )
            else:
                return await operation()

        # 4. Retry wraps timeout
        if self._retry_policy:
            return await self._retry_policy.execute(
                timed_operation,
                operation_name
            )
        else:
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
        rate_limiter: Optional[IRateLimiter] = None,
        circuit_breaker: Optional[ICircuitBreaker] = None,
        retry_policy: Optional[IRetryPolicy] = None,
        timeout: Optional[ITimeout] = None,
        default_timeout_seconds: float = 300.0  # 5 minutes for LLM
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
        context: Optional[ExecutionContext] = None,
        stream_callback: Optional[StreamCallback] = None,
    ) -> ExecutionResult:
        """Execute with resilience."""
        # Estimate token cost for rate limiting
        estimated_tokens = self._estimate_tokens(prompt)

        return await self._execute_resilient(
            operation=lambda: self._wrapped.execute(prompt, context, stream_callback),
            operation_name="llm_execute",
            rate_limit_cost=estimated_tokens
        )

    async def execute_with_tools(
        self,
        prompt: str,
        tools: List[ToolDefinition],
        context: Optional[ExecutionContext] = None,
        stream_callback: Optional[StreamCallback] = None,
    ) -> ExecutionResult:
        """Execute with tools and resilience."""
        estimated_tokens = self._estimate_tokens(prompt)

        return await self._execute_resilient(
            operation=lambda: self._wrapped.execute_with_tools(prompt, tools, context, stream_callback),
            operation_name="llm_execute_with_tools",
            rate_limit_cost=estimated_tokens
        )

    async def stream_completion(
        self,
        prompt: str,
        context: Optional[ExecutionContext] = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream completion (less resilience for streaming)."""
        # Streaming doesn't work well with retries
        if self._rate_limiter:
            estimated_tokens = self._estimate_tokens(prompt)
            await self._rate_limiter.acquire("stream_completion", estimated_tokens)

        if self._circuit_breaker:
            async def stream_operation():
                return self._wrapped.stream_completion(prompt, context)
            return await self._circuit_breaker.call(
                stream_operation,
                "stream_completion"
            )
        else:
            return self._wrapped.stream_completion(prompt, context)

    async def create_conversation(
        self,
        system_prompt: Optional[str] = None,
        parameters: Optional[ExecutionContext] = None,
    ) -> str:
        """Create conversation with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.create_conversation(system_prompt, parameters),
            operation_name="create_conversation",
            rate_limit_cost=1
        )

    async def continue_conversation(
        self,
        conversation_id: str,
        message: str,
        stream_callback: Optional[StreamCallback] = None,
    ) -> ExecutionResult:
        """Continue conversation with resilience."""
        estimated_tokens = self._estimate_tokens(message)

        return await self._execute_resilient(
            operation=lambda: self._wrapped.continue_conversation(conversation_id, message, stream_callback),
            operation_name="continue_conversation",
            rate_limit_cost=estimated_tokens
        )

    async def get_model_info(self) -> ModelInfo:
        """Get model info with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.get_model_info(),
            operation_name="get_model_info",
            rate_limit_cost=1
        )

    async def list_available_models(self) -> List[ModelInfo]:
        """List models with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.list_available_models(),
            operation_name="list_available_models",
            rate_limit_cost=1
        )

    async def count_tokens(
        self,
        text: str,
        model: Optional[str] = None,
    ) -> int:
        """Count tokens with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.count_tokens(text, model),
            operation_name="count_tokens",
            rate_limit_cost=1
        )

    async def get_usage_stats(
        self,
        since: Optional[datetime] = None,
    ) -> UsageStats:
        """Get usage stats with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.get_usage_stats(since),
            operation_name="get_usage_stats",
            rate_limit_cost=1
        )

    async def _execute_resilient(
        self,
        operation: Callable[[], T],
        operation_name: str,
        rate_limit_cost: int
    ) -> T:
        """Execute with resilience patterns."""
        # Rate limiting with token cost
        if self._rate_limiter:
            await self._rate_limiter.acquire(operation_name, rate_limit_cost)

        # Circuit breaker
        if self._circuit_breaker:
            return await self._circuit_breaker.call(
                self._execute_with_timeout_and_retry,
                operation_name,
                operation,
                operation_name
            )
        else:
            return await self._execute_with_timeout_and_retry(
                operation,
                operation_name
            )

    async def _execute_with_timeout_and_retry(
        self,
        operation: Callable[[], T],
        operation_name: str
    ) -> T:
        """Apply timeout and retry."""
        async def timed_operation():
            if self._timeout:
                return await self._timeout.execute(
                    operation,
                    self._default_timeout,
                    operation_name
                )
            else:
                return await operation()

        if self._retry_policy:
            return await self._retry_policy.execute(timed_operation, operation_name)
        else:
            return await timed_operation()

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (4 chars per token)."""
        return max(1, len(text) // 4)
