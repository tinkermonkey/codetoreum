"""Integration tests for ExecutionService."""

from collections.abc import Iterator

import pytest

from codetoreum.adapters.testing.fake_container_adapter import FakeContainerAdapter
from codetoreum.adapters.testing.in_memory_event_store import InMemoryEventStore
from codetoreum.adapters.testing.in_memory_storage_adapter import InMemoryStorageAdapter
from codetoreum.adapters.testing.mock_llm_adapter import MockLLMAdapter
from codetoreum.application.execution_service import (
    ExecutionService,
    LogEntry,
)
from codetoreum.domain.agent import Agent, AgentCapability, AgentType
from codetoreum.domain.agent_execution import ExecutionStatus
from codetoreum.domain.types import ContainerId
from codetoreum.domain.value_objects import (
    ContainerConfig,
    ExecutionContext,
)
from codetoreum.domain.work_item import (
    WorkItem,
    WorkItemPriority,
)

# Fixtures


@pytest.fixture
def mock_event_store() -> Iterator[InMemoryEventStore]:
    """Create mock event store."""
    store = InMemoryEventStore()
    yield store
    store.clear()


@pytest.fixture
def mock_llm_provider() -> Iterator[MockLLMAdapter]:
    """Create mock LLM provider."""
    provider = MockLLMAdapter(default_response="Hello World!")
    yield provider
    provider.reset_stats()


@pytest.fixture
def mock_container() -> Iterator[FakeContainerAdapter]:
    """Create mock container adapter."""
    container = FakeContainerAdapter(default_exit_code=0)
    yield container
    container.clear()


@pytest.fixture
def mock_storage() -> Iterator[InMemoryStorageAdapter]:
    """Create mock storage adapter."""
    storage = InMemoryStorageAdapter()
    yield storage
    storage.clear()


@pytest.fixture
def execution_service(
    mock_llm_provider: MockLLMAdapter,
    mock_container: FakeContainerAdapter,
    mock_event_store: InMemoryEventStore,
    mock_storage: InMemoryStorageAdapter,
) -> ExecutionService:
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
def sample_agent() -> Agent:
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
def sample_work_item() -> WorkItem:
    """Create sample work item."""
    return WorkItem.create(
        title="Test Issue",
        description="Test description",
        project_id="project-123",
        priority=WorkItemPriority.MEDIUM,
    )


@pytest.fixture
def sample_execution_context() -> ExecutionContext:
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
async def test_create_execution(execution_service, sample_agent, sample_work_item, mock_event_store):
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
async def test_start_execution(execution_service, sample_agent, sample_work_item, mock_event_store):
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

    result = await execution_service.execute_with_llm(execution, sample_execution_context)

    assert result.success
    assert execution.status == ExecutionStatus.COMPLETED
    assert execution.output == "Hello World!"
    assert execution.input_tokens == 20
    assert execution.output_tokens == 10


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

    await execution_service.start_execution(execution, sample_execution_context, container_config)

    result = await execution_service.execute_with_container(execution, sample_execution_context, container_config)

    assert result.success
    assert execution.status == ExecutionStatus.COMPLETED
    assert execution.input_tokens == 20  # Extracted from logs
    assert execution.output_tokens == 10


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

    await execution_service.start_execution(execution, sample_execution_context, container_config)

    # Set container ID manually for testing
    execution.container_id = ContainerId("test-container")

    logs = await execution_service.get_execution_logs(execution)

    assert len(logs) > 0
    assert all(isinstance(entry, LogEntry) for entry in logs)
    assert all(entry.source == "container" for entry in logs)
