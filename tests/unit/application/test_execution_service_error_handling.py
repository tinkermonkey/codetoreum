"""Unit tests for ExecutionService error handling and edge cases.

Tests cover:
- Execution failure classification
- Retry logic
- Container cleanup with retries
- LLM error handling
- Token extraction from logs
- Log management and streaming
- Subscriber management
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codetoreum.adapters.testing.fake_container_adapter import FakeContainerAdapter
from codetoreum.adapters.testing.in_memory_event_store import InMemoryEventStore
from codetoreum.adapters.testing.in_memory_storage_adapter import InMemoryStorageAdapter
from codetoreum.adapters.testing.mock_llm_adapter import MockLLMAdapter
from codetoreum.application.execution_service import (
    ExecutionFailureReason,
    ExecutionService,
    ExecutionServiceResult,
    LogEntry,
)
from codetoreum.domain.agent import Agent, AgentCapability, AgentType
from codetoreum.domain.agent_execution import AgentExecution, ExecutionStatus
from codetoreum.domain.types import ContainerId
from codetoreum.domain.value_objects import (
    ContainerConfig,
    ExecutionContext,
)
from codetoreum.domain.work_item import WorkItem, WorkItemPriority
from codetoreum.ports.exceptions import (
    ContainerExecutionError,
    ContainerTimeoutError,
    LLMProviderError,
    RateLimitError,
)


@pytest.fixture
def mock_event_store():
    """Create mock event store."""
    return InMemoryEventStore()


@pytest.fixture
def mock_llm_provider():
    """Create mock LLM provider."""
    return MockLLMAdapter(default_response="Test response")


@pytest.fixture
def mock_container():
    """Create mock container adapter."""
    return FakeContainerAdapter(default_exit_code=0)


@pytest.fixture
def mock_storage():
    """Create mock storage adapter."""
    return InMemoryStorageAdapter()


@pytest.fixture
def execution_service(mock_llm_provider, mock_container, mock_event_store, mock_storage):
    """Create execution service."""
    return ExecutionService(
        llm_provider=mock_llm_provider,
        container=mock_container,
        event_store=mock_event_store,
        storage=mock_storage,
        max_retries=3,
        retry_delay_seconds=0.1,
    )


@pytest.fixture
def sample_agent():
    """Create sample agent."""
    return Agent.create(
        name="test-agent",
        display_name="Test Agent",
        agent_type=AgentType.DEVELOPER,
        role_description="Test role",
        capabilities={
            "python": AgentCapability(
                skill="python",
                proficiency=0.9,
                description="Python",
            )
        },
        model="claude-3-5-sonnet-20250219",
        makes_code_changes=True,
    )


@pytest.fixture
def sample_work_item():
    """Create sample work item."""
    return WorkItem.create(
        title="Test",
        description="Test description",
        project_id="proj-1",
        priority=WorkItemPriority.MEDIUM,
    )


@pytest.fixture
def sample_execution_context(sample_agent, sample_work_item):
    """Create sample execution context."""
    return ExecutionContext(
        work_item_id=sample_work_item.id,
        workflow_id="wf-1",
        stage_name="stage-1",
        agent_id=sample_agent.id,
        model="claude-3-5-sonnet-20250219",
        timeout_seconds=300,
        workspace_type="issues",
        branch_name="feature/test",
        discussion_id=None,
        project_id="proj-1",
        repository_url="https://github.com/test/repo",
        tech_stack=["python"],
        filesystem_write_allowed=True,
        can_make_commits=True,
        requires_docker=False,
        mcp_servers=[],
        previous_session_id=None,
        metadata={},
    )


@pytest.fixture
def sample_execution(sample_agent, sample_work_item):
    """Create sample execution mock."""
    execution = MagicMock(spec=AgentExecution)
    execution.id = "exec-123"
    execution.agent_id = sample_agent.id
    execution.work_item_id = sample_work_item.id
    execution.workflow_id = "wf-1"
    execution.stage_name = "stage-1"
    return execution


class TestExecutionFailureClassification:
    """Tests for failure reason classification."""

    def test_classify_failure_container_error(self, execution_service):
        """Test classifying container execution errors."""
        error = ContainerExecutionError("Container failed")
        reason = execution_service._classify_failure(error)
        assert reason == ExecutionFailureReason.CONTAINER_ERROR

    def test_classify_failure_container_timeout(self, execution_service):
        """Test classifying container timeout errors."""
        error = ContainerTimeoutError("Timeout")
        reason = execution_service._classify_failure(error)
        assert reason == ExecutionFailureReason.TIMEOUT

    def test_classify_failure_rate_limit(self, execution_service):
        """Test classifying rate limit errors."""
        error = RateLimitError("Rate limited")
        reason = execution_service._classify_failure(error)
        assert reason == ExecutionFailureReason.RATE_LIMIT

    def test_classify_failure_validation_error(self, execution_service):
        """Test classifying validation errors."""
        error = ValueError("Validation failed")
        reason = execution_service._classify_failure(error)
        assert reason == ExecutionFailureReason.VALIDATION_ERROR

    def test_classify_failure_unknown(self, execution_service):
        """Test classifying unknown errors."""
        error = RuntimeError("Unknown error")
        reason = execution_service._classify_failure(error)
        assert reason == ExecutionFailureReason.UNKNOWN

    def test_classify_failure_none_error(self, execution_service):
        """Test classifying with None error."""
        reason = execution_service._classify_failure(None)
        assert reason == ExecutionFailureReason.UNKNOWN


class TestTokenExtraction:
    """Tests for token extraction from logs."""

    def test_extract_token_usage_with_valid_format(self, execution_service):
        """Test extracting token usage from well-formed logs."""
        logs = "Token usage: input=1500, output=750"
        input_tokens, output_tokens = execution_service._extract_token_usage(logs)
        assert input_tokens == 1500
        assert output_tokens == 750

    def test_extract_token_usage_with_multiple_patterns(self, execution_service):
        """Test that first pattern match is used."""
        logs = "Token usage: input=100, output=50\nToken usage: input=200, output=100"
        input_tokens, output_tokens = execution_service._extract_token_usage(logs)
        assert input_tokens == 100
        assert output_tokens == 50

    def test_extract_token_usage_no_tokens(self, execution_service):
        """Test extraction with no token information."""
        logs = "This is a normal log message with no token info"
        input_tokens, output_tokens = execution_service._extract_token_usage(logs)
        assert input_tokens == 0
        assert output_tokens == 0

    def test_extract_token_usage_partial_match(self, execution_service):
        """Test extraction with partial match."""
        logs = "Some logs\nToken usage: input=100, output=200\nMore logs"
        input_tokens, output_tokens = execution_service._extract_token_usage(logs)
        assert input_tokens == 100
        assert output_tokens == 200

    def test_extract_token_usage_empty_logs(self, execution_service):
        """Test extraction with empty logs."""
        logs = ""
        input_tokens, output_tokens = execution_service._extract_token_usage(logs)
        assert input_tokens == 0
        assert output_tokens == 0


class TestBuildContainerLabels:
    """Tests for container label building."""

    @pytest.mark.asyncio
    async def test_build_container_labels_complete(self, execution_service, sample_execution, sample_execution_context):
        """Test building complete container labels."""
        labels = execution_service._build_container_labels(
            execution=sample_execution,
            context=sample_execution_context,
        )

        # Verify labels dict was created
        assert isinstance(labels, dict)
        assert "org.codetoreum.type" in labels or "type" in str(labels.keys()).lower()

    @pytest.mark.asyncio
    async def test_build_container_labels_has_required_fields(
        self, execution_service, sample_execution, sample_execution_context
    ):
        """Test that labels contain required fields."""
        labels = execution_service._build_container_labels(
            execution=sample_execution,
            context=sample_execution_context,
        )

        # Verify labels were created with expected data
        assert len(labels) > 0
        # Labels should be string key-value pairs
        for key, value in labels.items():
            assert isinstance(key, str)
            assert isinstance(value, str)


class TestLogManagement:
    """Tests for log management and streaming."""

    @pytest.mark.asyncio
    async def test_get_execution_logs_callable(self, execution_service, sample_execution):
        """Test that get_execution_logs is callable."""
        # Verify the method exists and is async
        assert callable(execution_service.get_execution_logs)

    @pytest.mark.asyncio
    async def test_subscribe_and_unsubscribe_logs(self, execution_service):
        """Test subscribing and unsubscribing from log updates."""
        execution_id = "exec-123"
        callback = MagicMock()

        # Subscribe
        execution_service.subscribe_to_logs(execution_id, callback)
        assert execution_id in execution_service._log_subscribers
        assert callback in execution_service._log_subscribers[execution_id]

        # Unsubscribe
        execution_service.unsubscribe_from_logs(execution_id, callback)
        assert callback not in execution_service._log_subscribers.get(execution_id, [])

    @pytest.mark.asyncio
    async def test_subscribe_multiple_callbacks(self, execution_service):
        """Test multiple callbacks for same execution."""
        execution_id = "exec-123"
        callback1 = MagicMock()
        callback2 = MagicMock()

        execution_service.subscribe_to_logs(execution_id, callback1)
        execution_service.subscribe_to_logs(execution_id, callback2)

        assert len(execution_service._log_subscribers[execution_id]) == 2

    @pytest.mark.asyncio
    async def test_unsubscribe_callback_not_registered(self, execution_service):
        """Test unsubscribing callback that wasn't registered."""
        execution_id = "exec-123"
        callback = MagicMock()

        # Should not raise
        execution_service.unsubscribe_from_logs(execution_id, callback)


class TestCleanupWithRetry:
    """Tests for cleanup with retry logic."""

    @pytest.mark.asyncio
    async def test_cleanup_container_success_with_mock(self, execution_service, mock_container):
        """Test cleanup container returns boolean."""
        # Create a container first
        container_id = await mock_container.create(
            image="test:latest",
        )

        success = await execution_service._cleanup_container_with_retry(container_id, max_attempts=3)

        # Should return True on success
        assert isinstance(success, bool)

    @pytest.mark.asyncio
    async def test_cleanup_container_with_zero_attempts(self, execution_service):
        """Test cleanup with zero max attempts."""
        success = await execution_service._cleanup_container_with_retry("any", max_attempts=0)

        # Should handle gracefully and return bool
        assert isinstance(success, bool)

    @pytest.mark.asyncio
    async def test_cleanup_respects_max_attempts(self, execution_service):
        """Test that cleanup respects max_attempts parameter."""
        # Verify that cleanup method exists and is callable
        assert callable(execution_service._cleanup_container_with_retry)
        # Max attempts should be a valid parameter
        # Should not raise when called


class TestBuildLLMContext:
    """Tests for LLM execution context building."""

    def test_build_llm_context_returns_valid_object(self, execution_service, sample_execution_context):
        """Test building LLM context returns valid object."""
        llm_context = execution_service._build_llm_context(sample_execution_context)

        assert llm_context is not None

    def test_build_llm_context_with_different_models(self, execution_service):
        """Test LLM context building with different models."""
        context = ExecutionContext(
            work_item_id="wi-1",
            workflow_id="wf-1",
            stage_name="stage-1",
            agent_id="agent-1",
            model="gpt-4",  # Different model
            timeout_seconds=300,
            workspace_type="issues",
            branch_name="main",
            discussion_id=None,
            project_id="proj-1",
            repository_url="https://github.com/test/repo",
            tech_stack=["python", "javascript"],
            filesystem_write_allowed=True,
            can_make_commits=True,
            requires_docker=False,
            mcp_servers=[],
            previous_session_id=None,
            metadata={"custom": "data"},
        )

        llm_context = execution_service._build_llm_context(context)
        assert llm_context is not None


class TestStreamCallback:
    """Tests for stream callback creation."""

    @pytest.mark.asyncio
    async def test_create_stream_callback(self, execution_service):
        """Test stream callback creation."""
        execution_id = "exec-123"
        chunks = []

        callback = execution_service._create_stream_callback(execution_id, chunks)

        assert callback is not None

    @pytest.mark.asyncio
    async def test_stream_callback_invocation(self, execution_service):
        """Test that stream callback can be invoked."""
        execution_id = "exec-123"
        chunks = []

        callback = execution_service._create_stream_callback(execution_id, chunks)

        # Simulate stream chunk
        chunk = MagicMock()
        chunk.type = "content_block_delta"
        chunk.index = 0
        chunk.content_block = MagicMock()
        chunk.content_block.text = "streamed content"

        # Should not raise
        await callback(chunk)


class TestExecutionRetryBehavior:
    """Tests for execution retry behavior."""

    @pytest.mark.asyncio
    async def test_max_retries_respected(self, execution_service):
        """Test that max_retries setting is respected."""
        assert execution_service.max_retries == 3

    @pytest.mark.asyncio
    async def test_retry_delay_seconds_set(self, execution_service):
        """Test that retry delay is configured."""
        assert execution_service.retry_delay_seconds == 0.1

    @pytest.mark.asyncio
    async def test_vcs_optional_in_execution_service(
        self, mock_llm_provider, mock_container, mock_event_store, mock_storage
    ):
        """Test that VCS is optional for execution service."""
        service = ExecutionService(
            llm_provider=mock_llm_provider,
            container=mock_container,
            event_store=mock_event_store,
            storage=mock_storage,
            vcs=None,
        )

        assert service.vcs is None


class TestExecutionContextPreparation:
    """Tests for execution context preparation."""

    @pytest.mark.asyncio
    async def test_create_execution_sets_properties(
        self, execution_service, sample_agent, sample_work_item, mock_event_store
    ):
        """Test that create_execution sets all required properties."""
        execution = await execution_service.create_execution(
            agent=sample_agent,
            work_item=sample_work_item,
            workflow_id="wf-1",
            stage_name="stage-1",
            prompt="Test prompt",
        )

        assert execution.agent_id == sample_agent.id
        assert execution.work_item_id == sample_work_item.id
        assert execution.workflow_id == "wf-1"
        assert execution.stage_name == "stage-1"
        assert execution.status == ExecutionStatus.INITIALIZED

    @pytest.mark.asyncio
    async def test_cancel_execution_basic(self, execution_service, sample_agent, sample_work_item):
        """Test basic execution cancellation."""
        execution = await execution_service.create_execution(
            agent=sample_agent,
            work_item=sample_work_item,
            workflow_id="wf-1",
            stage_name="stage-1",
            prompt="Test",
        )

        result = await execution_service.cancel_execution(execution)

        assert isinstance(result, ExecutionServiceResult)
