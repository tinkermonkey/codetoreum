"""Integration tests for resilient decorators.

Tests the full integration of resilience patterns with adapters.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

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
from codetoreum.ports.output.llm_provider import (
    ExecutionContext,
    ExecutionResult,
    ILLMProvider,
)
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
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            completed_at=None
        )

    # Stub implementations for other required methods
    async def create_work_item(self, title: str, description: str, project_id: ProjectId,
                                labels: list[str] | None = None, assignee: UserId | None = None,
                                priority: WorkItemPriority | None = None,
                                metadata: dict[str, Any] | None = None) -> WorkItem:
        raise NotImplementedError

    async def update_work_item(self, item_id: WorkItemId, updates: dict[str, Any]) -> WorkItem:
        raise NotImplementedError

    async def delete_work_item(self, item_id: WorkItemId) -> None:
        raise NotImplementedError

    async def update_status(self, item_id: WorkItemId, status: WorkItemStatus,
                           reason: str | None = None) -> WorkItem:
        raise NotImplementedError

    async def list_work_items(self, project_id: ProjectId | None = None,
                             status: WorkItemStatus | None = None, assignee: UserId | None = None,
                             labels: list[str] | None = None, created_after: datetime | None = None,
                             updated_after: datetime | None = None, limit: int = 100,
                             offset: int = 0) -> list[WorkItem]:
        raise NotImplementedError

    async def search_work_items(self, query: str, project_id: ProjectId | None = None,
                                limit: int = 100) -> list[WorkItem]:
        raise NotImplementedError

    async def get_work_item_stream(self, project_id: ProjectId | None = None,
                                   since: datetime | None = None) -> AsyncIterator[WorkItem]:
        raise NotImplementedError

    async def add_comment(self, item_id: WorkItemId, body: str, author: UserId | None = None,
                         metadata: dict[str, Any] | None = None) -> Comment:
        raise NotImplementedError

    async def get_comments(self, item_id: WorkItemId, since: datetime | None = None,
                          limit: int = 100) -> list[Comment]:
        raise NotImplementedError

    async def link_work_items(self, source_id: WorkItemId, target_id: WorkItemId,
                             relationship: str) -> None:
        raise NotImplementedError

    async def get_related_items(self, item_id: WorkItemId,
                               relationship: str | None = None) -> list[WorkItem]:
        raise NotImplementedError

    async def register_webhook(self, url: str, events: list[str],
                              project_id: ProjectId | None = None) -> str:
        raise NotImplementedError

    async def unregister_webhook(self, webhook_id: str) -> None:
        raise NotImplementedError


class FlakyLLMProvider(ILLMProvider):
    """Mock LLM provider that fails intermittently."""

    def __init__(self, fail_count: int = 0):
        self.fail_count = fail_count
        self.call_count = 0

    async def execute(self, prompt: str, context: ExecutionContext | None = None,
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
        raise NotImplementedError

    async def stream_completion(self, prompt: str, context=None):
        raise NotImplementedError

    async def create_conversation(self, system_prompt=None, parameters=None) -> str:
        raise NotImplementedError

    async def continue_conversation(self, conversation_id: str, message: str, stream_callback=None):
        raise NotImplementedError

    async def get_model_info(self):
        raise NotImplementedError

    async def list_available_models(self):
        raise NotImplementedError

    async def count_tokens(self, text: str, model=None) -> int:
        raise NotImplementedError

    async def get_usage_stats(self, since=None):
        raise NotImplementedError


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
        # Verify resilience components handled the transient failure
        assert flaky_adapter.call_count > 1  # Should have retried after first failure

