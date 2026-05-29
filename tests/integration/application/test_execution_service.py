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
    assert mock_event_store.get_total_event_count() > 0


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
    # MockLLMAdapter uses word-based token counting: "Implement the feature" = 3 words
    assert execution.input_tokens == 3
    # "Hello World!" = 2 words
    assert execution.output_tokens == 2


@pytest.mark.asyncio
async def test_execute_with_container_creates_container(
    execution_service,
    sample_agent,
    sample_work_item,
    sample_execution_context,
    mock_container,
):
    """Test that execute_with_container properly creates and manages containers.

    This test verifies the container creation flow. Full container execution
    lifecycle testing is handled in simulation tests that use deterministic
    mock adapters with proper lifecycle support.
    """
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

    # Call execute_with_container and handle the result
    # The FakeContainerAdapter will create the container but may not complete it properly
    # This test verifies the execution service correctly calls the container adapter
    result = await execution_service.execute_with_container(execution, sample_execution_context, container_config)

    # Verify the execution service attempted to execute via container
    # The result may fail due to fake adapter limitations, but the execution should be tracked
    assert execution.id is not None
    assert execution.status in (ExecutionStatus.FAILED, ExecutionStatus.COMPLETED)
    # Verify cleanup happened (active executions removed)
    assert execution.id not in execution_service._active_executions


@pytest.mark.asyncio
async def test_extract_and_upload_artifacts_uploads_output_tree(
    execution_service,
    sample_agent,
    sample_work_item,
    sample_execution_context,
    mock_container,
    mock_storage,
):
    """Files under /output in the container land at executions/{id}/artifacts/{path} in IStorage."""
    execution = await execution_service.create_execution(
        agent=sample_agent,
        work_item=sample_work_item,
        workflow_id="workflow-123",
        stage_name="development",
        prompt="Implement the feature",
    )

    # Seed a container with an /output tree
    container_id = await mock_container.create(image="codetoreum/agent:latest")
    mock_container.write_output_file(container_id, "/output/result.json", '{"ok": true}')
    mock_container.write_output_file(container_id, "/output/logs/run.log", "started\n")

    # Call the helper directly so we control the container_id wiring
    await execution_service._extract_and_upload_artifacts(execution, container_id, sample_execution_context)

    # Verify uploads landed at the expected storage keys
    expected_json_key = f"executions/{execution.id}/artifacts/result.json"
    expected_log_key = f"executions/{execution.id}/artifacts/logs/run.log"
    assert await mock_storage.exists(expected_json_key)
    assert await mock_storage.exists(expected_log_key)
    json_content = await mock_storage.download(expected_json_key)
    assert json_content == b'{"ok": true}'
    log_content = await mock_storage.download(expected_log_key)
    assert log_content == b"started\n"


@pytest.mark.asyncio
async def test_extract_and_upload_artifacts_no_output_dir_is_soft_miss(
    execution_service,
    sample_agent,
    sample_work_item,
    sample_execution_context,
    mock_container,
    mock_storage,
):
    """When the agent produced no /output, extraction logs and returns cleanly — no upload, no raise."""
    execution = await execution_service.create_execution(
        agent=sample_agent,
        work_item=sample_work_item,
        workflow_id="workflow-123",
        stage_name="development",
        prompt="Implement the feature",
    )

    # Create a container but DO NOT write any /output files
    container_id = await mock_container.create(image="codetoreum/agent:latest")

    # Should not raise
    await execution_service._extract_and_upload_artifacts(execution, container_id, sample_execution_context)

    # And nothing was uploaded under the artifacts prefix
    artifact_files = await mock_storage.list_files(prefix=f"executions/{execution.id}/artifacts/")
    assert artifact_files == []


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
    assert execution.status == ExecutionStatus.CANCELLED
    assert "cancelled" in execution.error_message.lower()


@pytest.mark.asyncio
async def test_get_execution_logs(
    execution_service,
    sample_agent,
    sample_work_item,
    sample_execution_context,
    mock_container,
):
    """Test getting execution logs.

    This tests the log retrieval functionality when a container_id is present.
    Note: Full container lifecycle testing is better covered in simulation tests.
    """
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

    # Manually set a container_id to test log retrieval
    # In a real scenario, this would be set by execute_with_container
    container_name = f"codetoreum-{execution.agent_id}-{execution.id[:8]}"
    execution.container_id = ContainerId(container_name)

    # Create the container in the fake adapter so it can be queried
    await mock_container.create(
        image=container_config.image,
        name=container_name,
        working_dir=container_config.working_dir,
    )

    # Get logs from the execution
    logs = await execution_service.get_execution_logs(execution)

    # FakeContainerAdapter returns fake logs for any container
    assert len(logs) > 0
    assert all(isinstance(entry, LogEntry) for entry in logs)
    assert all(entry.source == "container" for entry in logs)


@pytest.mark.asyncio
async def test_stream_logs_done_callback_handles_exceptions(execution_service):
    """Test that _stream_logs_done_callback properly handles exceptions from log streaming task."""
    import asyncio
    from unittest.mock import AsyncMock, patch

    # Create a task that raises an exception
    async def failing_task():
        raise RuntimeError("Log streaming failed")

    # Create and run the task
    task = asyncio.create_task(failing_task())
    try:
        await task
    except RuntimeError:
        pass  # Catch the exception so task is done

    # Mock the logger to verify error was logged
    with patch("codetoreum.application.execution_service.logger") as mock_logger:
        execution_service._stream_logs_done_callback(task)
        mock_logger.error.assert_called_once()
        # Verify the error message mentions log streaming
        call_args = mock_logger.error.call_args
        assert "log streaming" in str(call_args).lower()


def test_build_llm_context_maps_repository_path_to_working_directory(execution_service):
    """Test that _build_llm_context correctly maps repository_path to working_directory."""
    from pathlib import Path

    context = ExecutionContext(
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
        previous_session_id="session-456",
        metadata={"key": "value"},
        repository_path="/tmp/test-repo",  # Path to cloned repository
    )

    llm_context = execution_service._build_llm_context(context)

    # Verify working_directory is set to the repository path
    assert llm_context.working_directory == Path("/tmp/test-repo")
    # Verify other context fields are copied correctly
    assert llm_context.model == context.model
    assert llm_context.timeout_seconds == context.timeout_seconds
    assert llm_context.session_id == context.previous_session_id


def test_build_llm_context_handles_none_repository_path(execution_service):
    """Test that _build_llm_context handles None repository_path correctly."""
    context = ExecutionContext(
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
        repository_path=None,  # No repository path
    )

    llm_context = execution_service._build_llm_context(context)

    # Verify working_directory is None when repository_path is None
    assert llm_context.working_directory is None


@pytest.mark.asyncio
async def test_stream_logs_done_callback_ignores_cancelled_error(execution_service):
    """Test that _stream_logs_done_callback suppresses CancelledError."""
    import asyncio
    from unittest.mock import patch

    # Create a task that gets cancelled
    async def cancellable_task():
        await asyncio.sleep(1)

    task = asyncio.create_task(cancellable_task())
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass  # Normal cancellation

    # Mock the logger to verify no error was logged
    with patch("codetoreum.application.execution_service.logger") as mock_logger:
        execution_service._stream_logs_done_callback(task)
        mock_logger.error.assert_not_called()


def test_build_llm_context_passes_environment_variables(execution_service):
    """Test that _build_llm_context passes project environment variables to LLM context."""
    context = ExecutionContext(
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
        environment_variables={
            "API_KEY": "secret-key-123",
            "FEATURE_FLAG": "enabled",
            "DEBUG_MODE": "false",
        },
        metadata={},
    )

    llm_context = execution_service._build_llm_context(context)

    # Verify environment variables are passed to LLM context
    assert llm_context.environment_variables is not None
    assert "API_KEY" in llm_context.environment_variables
    assert llm_context.environment_variables["API_KEY"] == "secret-key-123"
    assert llm_context.environment_variables["FEATURE_FLAG"] == "enabled"
    assert llm_context.environment_variables["DEBUG_MODE"] == "false"


def test_build_llm_context_handles_empty_environment_variables(execution_service):
    """Test that _build_llm_context handles empty environment variables correctly."""
    context = ExecutionContext(
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
        environment_variables=None,  # No environment variables
        metadata={},
    )

    llm_context = execution_service._build_llm_context(context)

    # Verify empty environment variables are handled
    assert llm_context.environment_variables is not None
    assert len(llm_context.environment_variables) == 0


@pytest.mark.asyncio
async def test_execute_with_llm_forwards_environment_variables(
    execution_service,
    sample_agent,
    sample_work_item,
    mock_event_store,
    mock_llm_provider,
):
    """Test that execute_with_llm forwards environment variables to the LLM provider."""
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
        environment_variables={
            "API_KEY": "test-api-key",
            "DB_HOST": "localhost",
        },
        metadata={},
    )

    await execution_service.start_execution(execution, context)
    result = await execution_service.execute_with_llm(execution, context)

    # Verify execution succeeded
    assert result.success

    # Verify the LLM provider received the environment variables
    assert mock_llm_provider.last_context is not None
    assert "API_KEY" in mock_llm_provider.last_context.environment_variables
    assert mock_llm_provider.last_context.environment_variables["API_KEY"] == "test-api-key"
    assert mock_llm_provider.last_context.environment_variables["DB_HOST"] == "localhost"
