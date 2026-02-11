"""Integration tests for resilient decorators.

Tests the full integration of resilience patterns with adapters.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

import pytest

from codetoreum.domain.comment import Comment
from codetoreum.domain.types import ProjectId, UserId, WorkItemId
from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus
from codetoreum.infrastructure.resilience import (
    CircuitBreakerOpenError,
    MaxRetriesExceededError,
    OperationMode,
    ResilienceFactory,
)
from codetoreum.ports.output.llm_provider import ExecutionContext, ExecutionResult, ILLMProvider
from codetoreum.ports.output.ticket_system import ITicketSystem


# ============================================================================
# Mock Adapters for Testing
# ============================================================================

class FlakyTicketSystem(ITicketSystem):
    """Mock ticket system that fails intermittently."""

    def __init__(self, fail_count: int = 0):
        self.fail_count = fail_count
        self.call_count = 0

    async def get_work_item(self, item_id: WorkItemId) -> WorkItem:
        self.call_count += 1
        if self.call_count <= self.fail_count:
            raise Exception("Simulated transient failure")

        return WorkItem(
            id=item_id,
            project_id=ProjectId("test-project"),
            title="Test Item",
            description="Test description",
            status=WorkItemStatus.NEW,
            priority=WorkItemPriority.MEDIUM,
            labels=[],
            external_id=None,
            external_url=None,
            assigned_agent_id=None,
            assigned_at=None,
            current_workflow_id=None,
            current_stage=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            completed_at=None
        )

    # Stub implementations for other required methods
    async def create_work_item(self, title: str, description: str, project_id: ProjectId,
                                labels: Optional[List[str]] = None, assignee: Optional[UserId] = None,
                                priority: Optional[WorkItemPriority] = None,
                                metadata: Optional[Dict[str, Any]] = None) -> WorkItem:
        raise NotImplementedError()

    async def update_work_item(self, item_id: WorkItemId, updates: Dict[str, Any]) -> WorkItem:
        raise NotImplementedError()

    async def delete_work_item(self, item_id: WorkItemId) -> None:
        raise NotImplementedError()

    async def update_status(self, item_id: WorkItemId, status: WorkItemStatus,
                           reason: Optional[str] = None) -> WorkItem:
        raise NotImplementedError()

    async def list_work_items(self, project_id: Optional[ProjectId] = None,
                             status: Optional[WorkItemStatus] = None, assignee: Optional[UserId] = None,
                             labels: Optional[List[str]] = None, created_after: Optional[datetime] = None,
                             updated_after: Optional[datetime] = None, limit: int = 100,
                             offset: int = 0) -> List[WorkItem]:
        raise NotImplementedError()

    async def search_work_items(self, query: str, project_id: Optional[ProjectId] = None,
                                limit: int = 100) -> List[WorkItem]:
        raise NotImplementedError()

    async def get_work_item_stream(self, project_id: Optional[ProjectId] = None,
                                   since: Optional[datetime] = None) -> AsyncIterator[WorkItem]:
        raise NotImplementedError()

    async def add_comment(self, item_id: WorkItemId, body: str, author: Optional[UserId] = None,
                         metadata: Optional[Dict[str, Any]] = None) -> Comment:
        raise NotImplementedError()

    async def get_comments(self, item_id: WorkItemId, since: Optional[datetime] = None,
                          limit: int = 100) -> List[Comment]:
        raise NotImplementedError()

    async def link_work_items(self, source_id: WorkItemId, target_id: WorkItemId,
                             relationship: str) -> None:
        raise NotImplementedError()

    async def get_related_items(self, item_id: WorkItemId,
                               relationship: Optional[str] = None) -> List[WorkItem]:
        raise NotImplementedError()

    async def register_webhook(self, url: str, events: List[str],
                              project_id: Optional[ProjectId] = None) -> str:
        raise NotImplementedError()

    async def unregister_webhook(self, webhook_id: str) -> None:
        raise NotImplementedError()


class FlakyLLMProvider(ILLMProvider):
    """Mock LLM provider that fails intermittently."""

    def __init__(self, fail_count: int = 0):
        self.fail_count = fail_count
        self.call_count = 0

    async def execute(self, prompt: str, context: Optional[ExecutionContext] = None,
                     stream_callback=None) -> ExecutionResult:
        self.call_count += 1
        if self.call_count <= self.fail_count:
            raise Exception("Simulated transient LLM failure")

        return ExecutionResult(
            content="Test response",
            model="test-model",
            completion_tokens=10,
            prompt_tokens=5,
            total_tokens=15
        )

    # Stub implementations
    async def execute_with_tools(self, prompt: str, tools, context=None, stream_callback=None):
        raise NotImplementedError()

    async def stream_completion(self, prompt: str, context=None):
        raise NotImplementedError()

    async def create_conversation(self, system_prompt=None, parameters=None) -> str:
        raise NotImplementedError()

    async def continue_conversation(self, conversation_id: str, message: str, stream_callback=None):
        raise NotImplementedError()

    async def get_model_info(self):
        raise NotImplementedError()

    async def list_available_models(self):
        raise NotImplementedError()

    async def count_tokens(self, text: str, model=None) -> int:
        raise NotImplementedError()

    async def get_usage_stats(self, since=None):
        raise NotImplementedError()


# ============================================================================
# Integration Tests
# ============================================================================

class TestResilientTicketSystemIntegration:
    """Integration tests for resilient ticket system decorator."""

    @pytest.mark.asyncio
    async def test_retries_on_transient_failure(self):
        """Test that resilient decorator retries transient failures."""
        # Create adapter that fails twice then succeeds
        flaky_adapter = FlakyTicketSystem(fail_count=2)

        factory = ResilienceFactory(mode=OperationMode.INTEGRATION_TEST)
        resilient = factory.create_resilient_ticket_system(flaky_adapter)

        # Should succeed after retries
        result = await resilient.get_work_item(WorkItemId("123"))

        assert result.id == WorkItemId("123")
        assert flaky_adapter.call_count == 3  # Initial attempt + 2 retries

    @pytest.mark.asyncio
    async def test_fails_after_max_retries(self):
        """Test that operation fails after exhausting retries."""
        # Create adapter that always fails
        flaky_adapter = FlakyTicketSystem(fail_count=10)

        factory = ResilienceFactory(mode=OperationMode.INTEGRATION_TEST)
        resilient = factory.create_resilient_ticket_system(flaky_adapter)

        # Should fail after exhausting retries
        with pytest.raises(MaxRetriesExceededError):
            await resilient.get_work_item(WorkItemId("123"))

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(self):
        """Test that circuit breaker opens after repeated failures."""
        # Create adapter that always fails
        flaky_adapter = FlakyTicketSystem(fail_count=100)

        factory = ResilienceFactory(mode=OperationMode.INTEGRATION_TEST)
        resilient = factory.create_resilient_ticket_system(flaky_adapter)

        # INTEGRATION_TEST mode uses failure_threshold=3 (hardcoded in factory)
        # First 3 calls should fail with MaxRetriesExceededError
        for i in range(3):
            with pytest.raises(MaxRetriesExceededError, match="Max retries .* exceeded for get_work_item"):
                await resilient.get_work_item(WorkItemId("123"))

        # Circuit should now be open after 3 failures
        with pytest.raises(CircuitBreakerOpenError):
            await resilient.get_work_item(WorkItemId("123"))

    @pytest.mark.asyncio
    async def test_rate_limiting_applied(self):
        """Test that rate limiting is applied."""
        flaky_adapter = FlakyTicketSystem(fail_count=0)

        factory = ResilienceFactory(mode=OperationMode.SIMULATION)
        resilient = factory.create_resilient_ticket_system(flaky_adapter)

        # Make several calls
        for i in range(5):
            await resilient.get_work_item(WorkItemId(f"{i}"))

        # Verify rate limiter recorded the calls
        assert len(resilient._rate_limiter.acquire_calls) >= 5


class TestResilientLLMProviderIntegration:
    """Integration tests for resilient LLM provider decorator."""

    @pytest.mark.asyncio
    async def test_retries_llm_failures(self):
        """Test that LLM failures are retried."""
        # Create LLM that fails once then succeeds
        flaky_llm = FlakyLLMProvider(fail_count=1)

        factory = ResilienceFactory(mode=OperationMode.INTEGRATION_TEST)
        resilient = factory.create_resilient_llm_provider(flaky_llm)

        # Should succeed after retry
        result = await resilient.execute("test prompt")

        assert result.content == "Test response"
        assert flaky_llm.call_count == 2  # Initial + 1 retry

    @pytest.mark.asyncio
    async def test_token_based_rate_limiting(self):
        """Test that token-based rate limiting works for LLM."""
        flaky_llm = FlakyLLMProvider(fail_count=0)

        factory = ResilienceFactory(mode=OperationMode.SIMULATION)
        resilient = factory.create_resilient_llm_provider(flaky_llm)

        # Make a call with a long prompt
        long_prompt = "test " * 1000  # Should estimate ~1000 tokens
        await resilient.execute(long_prompt)

        # Verify rate limiter was called with estimated token cost
        assert len(resilient._rate_limiter.acquire_calls) > 0
        # Token cost should be significant (not just 1)
        token_cost = resilient._rate_limiter.acquire_calls[0][1]
        assert token_cost > 100  # Should estimate hundreds of tokens

    @pytest.mark.asyncio
    async def test_llm_has_longer_timeout(self):
        """Test that LLM operations have longer timeout."""
        flaky_llm = FlakyLLMProvider(fail_count=0)

        factory = ResilienceFactory(mode=OperationMode.INTEGRATION_TEST)
        resilient = factory.create_resilient_llm_provider(flaky_llm)

        # LLM should have 300s timeout (vs 30s for ticket system)
        assert resilient._default_timeout == 300.0


class TestEndToEndResilience:
    """End-to-end tests combining multiple resilience patterns."""

    @pytest.mark.asyncio
    async def test_full_resilience_stack(self):
        """Test all resilience patterns working together."""
        # Create flaky adapter
        flaky_adapter = FlakyTicketSystem(fail_count=1)

        factory = ResilienceFactory(mode=OperationMode.INTEGRATION_TEST)
        resilient = factory.create_resilient_ticket_system(flaky_adapter)

        # Should succeed with:
        # 1. Rate limiting applied
        # 2. Circuit breaker monitoring
        # 3. Retry on first failure
        # 4. Timeout protection
        result = await resilient.get_work_item(WorkItemId("123"))

        assert result.id == WorkItemId("123")

        # Verify resilience components were involved
        # Note: CircuitBreaker (production) doesn't have call_history, only stats
        assert len(resilient._rate_limiter.acquire_calls) > 0
        assert resilient._circuit_breaker.get_stats().total_calls > 0
        assert len(resilient._retry_policy.execution_history) > 0

    @pytest.mark.asyncio
    async def test_simulation_mode_is_fast(self):
        """Test that simulation mode runs without delays."""
        # No failures - testing speed not retry behavior
        flaky_adapter = FlakyTicketSystem(fail_count=0)

        factory = ResilienceFactory(mode=OperationMode.SIMULATION)
        resilient = factory.create_resilient_ticket_system(flaky_adapter)

        # Make many calls
        import time
        start = time.time()

        for i in range(10):
            # Should be fast in simulation mode (no rate limit delays)
            await resilient.get_work_item(WorkItemId(f"{i}"))

        elapsed = time.time() - start

        # Should complete very quickly (no delays in simulation)
        assert elapsed < 1.0  # All 10 calls in under 1 second
