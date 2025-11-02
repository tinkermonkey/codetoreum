"""Integration tests for ExecutionService."""

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.application.execution_service import (
    ExecutionFailureReason,
    ExecutionService,
    LogEntry,
)
from codetoreum.domain.agent import Agent, AgentCapability, AgentType
from codetoreum.domain.agent_execution import AgentExecution, ExecutionStatus
from codetoreum.domain.events import DomainEvent
from codetoreum.domain.exceptions import DomainError
from codetoreum.domain.value_objects import (
    ContainerConfig,
    ExecutionContext,
)
from codetoreum.domain.work_item import (
    WorkItem,
    WorkItemPriority,
    WorkItemStatus,
)
from codetoreum.ports.exceptions import (
    ContainerExecutionError,
    ContainerTimeoutError,
    ExternalServiceError,
    RateLimitError,
)
from codetoreum.ports.output import IContainer, IEventStore, ILLMProvider, IStorage
from codetoreum.ports.output.container import ContainerResult, ContainerStatus
from codetoreum.ports.output.llm_provider import (
    ExecutionContext as LLMExecutionContext,
    ExecutionResult as LLMExecutionResult,
    StreamChunk,
)


# Mock Adapters


class MockEventStore:
    """Mock event store for testing."""

    def __init__(self):
        self.events: List[DomainEvent] = []

    async def append(self, event: DomainEvent) -> None:
        """Append event to store."""
        self.events.append(event)

    async def get_events(
        self, aggregate_id: str, from_version: int = 0
    ) -> List[DomainEvent]:
        """Get events for aggregate."""
        return [e for e in self.events if e.aggregate_id == aggregate_id]


class MockLLMProvider:
    """Mock LLM provider for testing."""

    def __init__(self):
        self.execution_count = 0
        self.should_fail = False
        self.should_rate_limit = False
        self.failure_count = 0
        self.stream_enabled = False

    async def execute(
        self,
        prompt: str,
        context: Optional[LLMExecutionContext] = None,
        stream_callback=None,
    ) -> LLMExecutionResult:
        """Execute prompt."""
        self.execution_count += 1

        # Simulate rate limiting
        if self.should_rate_limit:
            self.failure_count += 1
            if self.failure_count < 3:
                raise RateLimitError(retry_after=60)

        # Simulate failure
        if self.should_fail:
            raise ExternalServiceError("llm", "LLM service error")

        # Simulate streaming
        if stream_callback and self.stream_enabled:
            for i, chunk in enumerate(["Hello", " ", "World", "!"]):
                await stream_callback(
                    StreamChunk(content=chunk, chunk_index=i, is_final=(i == 3))
                )

        return LLMExecutionResult(
            content="Hello World!",
            role="assistant",
            model="claude-3-5-sonnet-20250219",
            completion_tokens=10,
            prompt_tokens=20,
            total_tokens=30,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            duration_ms=100,
            metadata={"session_id": "test-session-123"},
        )

    async def execute_with_tools(self, prompt, tools, context=None, stream_callback=None):
        """Execute with tools."""
        return await self.execute(prompt, context, stream_callback)

    async def stream_completion(
        self, prompt: str, context: Optional[LLMExecutionContext] = None
    ) -> AsyncIterator[StreamChunk]:
        """Stream completion."""
        for i, chunk in enumerate(["Hello", " ", "World", "!"]):
            yield StreamChunk(content=chunk, chunk_index=i, is_final=(i == 3))

    async def create_conversation(self, system_prompt=None, parameters=None):
        """Create conversation."""
        return "conv-123"

    async def continue_conversation(
        self, conversation_id: str, message: str, stream_callback=None
    ):
        """Continue conversation."""
        return await self.execute(message, stream_callback=stream_callback)

    async def get_model_info(self):
        """Get model info."""
        from codetoreum.ports.output.llm_provider import ModelInfo

        return ModelInfo(
            model_id="claude-3-5-sonnet-20250219",
            provider="anthropic",
            display_name="Claude 3.5 Sonnet",
            context_window=200000,
            max_output_tokens=8192,
            supports_tools=True,
            supports_streaming=True,
        )

    async def list_available_models(self):
        """List available models."""
        return [await self.get_model_info()]

    async def count_tokens(self, text: str, model: Optional[str] = None):
        """Count tokens."""
        return len(text.split())

    async def get_usage_stats(self, since: Optional[datetime] = None):
        """Get usage stats."""
        from codetoreum.ports.output.llm_provider import UsageStats

        return UsageStats(
            total_requests=self.execution_count,
            total_tokens=30 * self.execution_count,
            input_tokens=20 * self.execution_count,
            output_tokens=10 * self.execution_count,
            total_cost=0.01 * self.execution_count,
            period_start=datetime.now(timezone.utc),
            period_end=datetime.now(timezone.utc),
        )


class MockContainer:
    """Mock container adapter for testing."""

    def __init__(self):
        self.containers: Dict[str, Dict[str, Any]] = {}
        self.should_fail = False
        self.should_timeout = False
        self.exit_code = 0
        self.log_output = "Container execution logs\nToken usage: input=20, output=10"

    async def create(
        self,
        image: str,
        name: Optional[str] = None,
        command: Optional[List[str]] = None,
        volumes: Optional[Dict[str, str]] = None,
        environment: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None,
        user: Optional[str] = None,
        network: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None,
    ) -> str:
        """Create container."""
        container_id = f"container-{len(self.containers)}"
        self.containers[container_id] = {
            "image": image,
            "name": name,
            "status": "created",
            "exit_code": None,
        }
        return container_id

    async def start(self, container_id: str) -> None:
        """Start container."""
        if container_id in self.containers:
            self.containers[container_id]["status"] = "running"

    async def stop(self, container_id: str, timeout: int = 10) -> None:
        """Stop container."""
        if container_id in self.containers:
            self.containers[container_id]["status"] = "stopped"

    async def remove(self, container_id: str, force: bool = False) -> None:
        """Remove container."""
        self.containers.pop(container_id, None)

    async def wait(self, container_id: str, timeout: Optional[int] = None) -> int:
        """Wait for container."""
        if self.should_timeout:
            raise ContainerTimeoutError("Container timed out")

        if self.should_fail:
            raise ContainerExecutionError("Container execution failed")

        if container_id in self.containers:
            self.containers[container_id]["status"] = "exited"
            self.containers[container_id]["exit_code"] = self.exit_code

        return self.exit_code

    async def logs(
        self,
        container_id: str,
        stream: bool = False,
        follow: bool = False,
        tail: Optional[int] = None,
        since: Optional[datetime] = None,
    ) -> Any:
        """Get container logs."""
        if stream:

            async def log_generator():
                for line in self.log_output.split("\n"):
                    yield line

            return log_generator()
        return self.log_output

    async def status(self, container_id: str) -> ContainerStatus:
        """Get container status."""
        container = self.containers.get(container_id, {})
        return ContainerStatus(
            id=container_id,
            status=container.get("status", "unknown"),
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            exit_code=container.get("exit_code"),
        )

    async def exec(
        self,
        container_id: str,
        command: List[str],
        user: Optional[str] = None,
        working_dir: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
    ) -> ContainerResult:
        """Execute command in container."""
        return ContainerResult(
            exit_code=0,
            stdout="Command output",
            stderr="",
            duration_ms=100,
            container_id=container_id,
        )

    async def list_containers(self, all: bool = False, filters: Optional[Dict] = None):
        """List containers."""
        return []

    async def pull_image(self, image: str, tag: str = "latest", stream_callback=None):
        """Pull image."""
        pass

    async def image_exists(self, image: str, tag: str = "latest") -> bool:
        """Check if image exists."""
        return True

    async def inspect(self, container_id: str) -> Dict[str, Any]:
        """Inspect container."""
        return self.containers.get(container_id, {})

    async def copy_to_container(
        self, container_id: str, source: str, destination: str
    ):
        """Copy to container."""
        pass

    async def copy_from_container(
        self, container_id: str, source: str, destination: str
    ):
        """Copy from container."""
        pass

    async def kill(self, container_id: str, signal: str = "SIGKILL"):
        """Kill container."""
        if container_id in self.containers:
            self.containers[container_id]["status"] = "killed"

    async def run(
        self,
        image: str,
        command: List[str],
        volumes: Dict[str, str],
        environment: Dict[str, str],
        timeout: int = 300,
        stream_callback=None,
    ) -> ContainerResult:
        """Run container."""
        return ContainerResult(
            exit_code=self.exit_code,
            stdout=self.log_output,
            stderr="",
            duration_ms=100,
            container_id="test-container",
        )


class MockStorage:
    """Mock storage adapter for testing."""

    def __init__(self):
        self.artifacts: Dict[str, bytes] = {}

    async def store_artifact(
        self, artifact_id: str, data: bytes, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Store artifact."""
        self.artifacts[artifact_id] = data
        return artifact_id

    async def retrieve_artifact(self, artifact_id: str) -> Optional[bytes]:
        """Retrieve artifact."""
        return self.artifacts.get(artifact_id)

    async def list_artifacts(self, prefix: Optional[str] = None) -> List[str]:
        """List artifacts."""
        if prefix:
            return [k for k in self.artifacts.keys() if k.startswith(prefix)]
        return list(self.artifacts.keys())

    async def delete_artifact(self, artifact_id: str) -> bool:
        """Delete artifact."""
        if artifact_id in self.artifacts:
            del self.artifacts[artifact_id]
            return True
        return False


# Fixtures


@pytest.fixture
def mock_event_store():
    """Create mock event store."""
    return MockEventStore()


@pytest.fixture
def mock_llm_provider():
    """Create mock LLM provider."""
    return MockLLMProvider()


@pytest.fixture
def mock_container():
    """Create mock container adapter."""
    return MockContainer()


@pytest.fixture
def mock_storage():
    """Create mock storage adapter."""
    return MockStorage()


@pytest.fixture
def execution_service(
    mock_llm_provider, mock_container, mock_event_store, mock_storage
):
    """Create execution service with mock adapters."""
    return ExecutionService(
        llm_provider=mock_llm_provider,
        container=mock_container,
        event_store=mock_event_store,
        storage=mock_storage,
        max_retries=3,
        retry_delay_seconds=1,
    )


@pytest.fixture
def sample_agent():
    """Create sample agent."""
    return Agent.create(
        name="test-agent",
        display_name="Test Agent",
        agent_type=AgentType.DEVELOPER,
        role_description="Develops and tests Python code",
        capabilities={
            "python": AgentCapability(
                skill="python",
                proficiency=0.9,
                description="Python development",
            )
        },
        model="claude-3-5-sonnet-20250219",
        makes_code_changes=True,
    )


@pytest.fixture
def sample_work_item():
    """Create sample work item."""
    return WorkItem.create(
        title="Test Issue",
        description="Test description",
        project_id="project-123",
        priority=WorkItemPriority.MEDIUM,
    )


@pytest.fixture
def sample_execution_context():
    """Create sample execution context."""
    return ExecutionContext(
        work_item_id="issue-123",
        workflow_id="workflow-123",
        stage_name="development",
        agent_id="agent-123",
        model="claude-3-5-sonnet-20250219",
        timeout_seconds=300,
        workspace_type="issues",
        branch_name="feature/test",
        discussion_id=None,
        project_id="project-123",
        repository_url="https://github.com/test/repo",
        tech_stack=["python"],
        filesystem_write_allowed=True,
        can_make_commits=True,
        requires_docker=False,
        mcp_servers=[],
        previous_session_id=None,
        metadata={},
    )


# Tests


@pytest.mark.asyncio
async def test_create_execution(
    execution_service, sample_agent, sample_work_item, mock_event_store
):
    """Test creating agent execution."""
    execution = await execution_service.create_execution(
        agent=sample_agent,
        work_item=sample_work_item,
        workflow_id="workflow-123",
        stage_name="development",
        prompt="Implement the feature",
    )

    assert execution.id is not None
    assert execution.agent_id == sample_agent.id
    assert execution.work_item_id == sample_work_item.id
    assert execution.status == ExecutionStatus.INITIALIZED
    assert len(mock_event_store.events) > 0


@pytest.mark.asyncio
async def test_start_execution(
    execution_service, sample_agent, sample_work_item, mock_event_store
):
    """Test starting execution."""
    execution = await execution_service.create_execution(
        agent=sample_agent,
        work_item=sample_work_item,
        workflow_id="workflow-123",
        stage_name="development",
        prompt="Implement the feature",
    )

    context = ExecutionContext(
        work_item_id=sample_work_item.id,
        workflow_id="workflow-123",
        stage_name="development",
        agent_id=sample_agent.id,
        model=sample_agent.model,
        timeout_seconds=300,
        workspace_type="issues",
        branch_name="feature/test",
        discussion_id=None,
        project_id="project-123",
        repository_url="https://github.com/test/repo",
        tech_stack=["python"],
        filesystem_write_allowed=True,
        can_make_commits=True,
        requires_docker=False,
        mcp_servers=[],
        previous_session_id=None,
        metadata={},
    )

    result = await execution_service.start_execution(execution, context)

    assert result.success
    assert execution.status == ExecutionStatus.RUNNING
    assert execution.started_at is not None


@pytest.mark.asyncio
async def test_execute_with_llm_success(
    execution_service,
    sample_agent,
    sample_work_item,
    sample_execution_context,
    mock_event_store,
):
    """Test successful LLM execution."""
    execution = await execution_service.create_execution(
        agent=sample_agent,
        work_item=sample_work_item,
        workflow_id="workflow-123",
        stage_name="development",
        prompt="Implement the feature",
    )

    await execution_service.start_execution(execution, sample_execution_context)

    result = await execution_service.execute_with_llm(
        execution, sample_execution_context
    )

    assert result.success
    assert execution.status == ExecutionStatus.COMPLETED
    assert execution.output == "Hello World!"
    assert execution.input_tokens == 20
    assert execution.output_tokens == 10


@pytest.mark.asyncio
async def test_execute_with_llm_rate_limit_retry(
    execution_service,
    sample_agent,
    sample_work_item,
    sample_execution_context,
    mock_llm_provider,
):
    """Test LLM execution with rate limiting and retry."""
    mock_llm_provider.should_rate_limit = True

    execution = await execution_service.create_execution(
        agent=sample_agent,
        work_item=sample_work_item,
        workflow_id="workflow-123",
        stage_name="development",
        prompt="Implement the feature",
    )

    await execution_service.start_execution(execution, sample_execution_context)

    result = await execution_service.execute_with_llm(
        execution, sample_execution_context
    )

    assert result.success
    assert execution.status == ExecutionStatus.COMPLETED
    # Should have retried and succeeded
    assert mock_llm_provider.execution_count >= 3


@pytest.mark.asyncio
async def test_execute_with_llm_failure(
    execution_service,
    sample_agent,
    sample_work_item,
    sample_execution_context,
    mock_llm_provider,
):
    """Test LLM execution failure."""
    mock_llm_provider.should_fail = True

    execution = await execution_service.create_execution(
        agent=sample_agent,
        work_item=sample_work_item,
        workflow_id="workflow-123",
        stage_name="development",
        prompt="Implement the feature",
    )

    await execution_service.start_execution(execution, sample_execution_context)

    result = await execution_service.execute_with_llm(
        execution, sample_execution_context
    )

    assert not result.success
    assert execution.status == ExecutionStatus.FAILED
    assert result.failure_reason == ExecutionFailureReason.LLM_ERROR


@pytest.mark.asyncio
async def test_execute_with_container_success(
    execution_service,
    sample_agent,
    sample_work_item,
    sample_execution_context,
    mock_container,
):
    """Test successful container execution."""
    execution = await execution_service.create_execution(
        agent=sample_agent,
        work_item=sample_work_item,
        workflow_id="workflow-123",
        stage_name="development",
        prompt="Implement the feature",
    )

    container_config = ContainerConfig(
        image="codetoreum/agent:latest",
        name="test-agent-container",
        working_dir="/workspace",
        user="1000:1000",
    )

    await execution_service.start_execution(
        execution, sample_execution_context, container_config
    )

    result = await execution_service.execute_with_container(
        execution, sample_execution_context, container_config
    )

    assert result.success
    assert execution.status == ExecutionStatus.COMPLETED
    assert execution.input_tokens == 20  # Extracted from logs
    assert execution.output_tokens == 10


@pytest.mark.asyncio
async def test_execute_with_container_failure(
    execution_service,
    sample_agent,
    sample_work_item,
    sample_execution_context,
    mock_container,
):
    """Test container execution failure."""
    mock_container.exit_code = 1

    execution = await execution_service.create_execution(
        agent=sample_agent,
        work_item=sample_work_item,
        workflow_id="workflow-123",
        stage_name="development",
        prompt="Implement the feature",
    )

    container_config = ContainerConfig(
        image="codetoreum/agent:latest",
        working_dir="/workspace",
    )

    await execution_service.start_execution(
        execution, sample_execution_context, container_config
    )

    result = await execution_service.execute_with_container(
        execution, sample_execution_context, container_config
    )

    assert not result.success
    assert execution.status == ExecutionStatus.FAILED
    assert result.failure_reason == ExecutionFailureReason.CONTAINER_ERROR


@pytest.mark.asyncio
async def test_execute_with_container_timeout(
    execution_service,
    sample_agent,
    sample_work_item,
    sample_execution_context,
    mock_container,
):
    """Test container execution timeout."""
    mock_container.should_timeout = True

    execution = await execution_service.create_execution(
        agent=sample_agent,
        work_item=sample_work_item,
        workflow_id="workflow-123",
        stage_name="development",
        prompt="Implement the feature",
    )

    container_config = ContainerConfig(
        image="codetoreum/agent:latest",
        working_dir="/workspace",
    )

    await execution_service.start_execution(
        execution, sample_execution_context, container_config
    )

    result = await execution_service.execute_with_container(
        execution, sample_execution_context, container_config
    )

    assert not result.success
    assert execution.status == ExecutionStatus.TIMEOUT
    assert result.failure_reason == ExecutionFailureReason.TIMEOUT


@pytest.mark.asyncio
async def test_cancel_execution(
    execution_service,
    sample_agent,
    sample_work_item,
    sample_execution_context,
):
    """Test cancelling execution."""
    execution = await execution_service.create_execution(
        agent=sample_agent,
        work_item=sample_work_item,
        workflow_id="workflow-123",
        stage_name="development",
        prompt="Implement the feature",
    )

    await execution_service.start_execution(execution, sample_execution_context)

    result = await execution_service.cancel_execution(execution)

    assert result.success
    assert execution.status == ExecutionStatus.FAILED
    assert "cancelled" in execution.error_message.lower()


@pytest.mark.asyncio
async def test_log_subscription(
    execution_service,
    sample_agent,
    sample_work_item,
    sample_execution_context,
    mock_llm_provider,
):
    """Test log subscription and streaming."""
    mock_llm_provider.stream_enabled = True
    received_logs: List[LogEntry] = []

    def log_callback(entry: LogEntry):
        received_logs.append(entry)

    execution = await execution_service.create_execution(
        agent=sample_agent,
        work_item=sample_work_item,
        workflow_id="workflow-123",
        stage_name="development",
        prompt="Implement the feature",
    )

    # Subscribe to logs
    execution_service.subscribe_to_logs(execution.id, log_callback)

    await execution_service.start_execution(execution, sample_execution_context)

    # Execute with streaming
    result = await execution_service.execute_with_llm(
        execution,
        sample_execution_context,
        stream_callback=lambda content: None,
    )

    assert result.success
    assert len(received_logs) > 0
    assert all(isinstance(entry, LogEntry) for entry in received_logs)

    # Unsubscribe
    execution_service.unsubscribe_from_logs(execution.id, log_callback)


@pytest.mark.asyncio
async def test_get_execution_logs(
    execution_service,
    sample_agent,
    sample_work_item,
    sample_execution_context,
    mock_container,
):
    """Test getting execution logs."""
    execution = await execution_service.create_execution(
        agent=sample_agent,
        work_item=sample_work_item,
        workflow_id="workflow-123",
        stage_name="development",
        prompt="Implement the feature",
    )

    container_config = ContainerConfig(
        image="codetoreum/agent:latest",
        working_dir="/workspace",
    )

    await execution_service.start_execution(
        execution, sample_execution_context, container_config
    )

    # Set container ID manually for testing
    execution.container_id = "test-container"

    logs = await execution_service.get_execution_logs(execution)

    assert len(logs) > 0
    assert all(isinstance(entry, LogEntry) for entry in logs)
    assert all(entry.source == "container" for entry in logs)
