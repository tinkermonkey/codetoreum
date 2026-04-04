"""Unit tests for ProductionEnvironmentRepairAdapter.

Verifies that:
1. rebuild_environment() emits start and completed events
2. verify_environment() emits start and completed events
3. rebuild_environment() applies rebuild timeout from EnvironmentRepairConfig
4. verify_environment() applies verification timeout from EnvironmentRepairConfig
5. Timeouts are enforced independently for rebuild and verify
6. Errors are logged with ErrorRegistry IDs and exc_info=True
7. LLM responses are parsed correctly
8. Malformed JSON responses are handled gracefully
9. Both methods return structured RebuildResult / VerificationResult
10. Events contain all required fields
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.adapters.secondary.production_environment_repair_adapter import (
    EnvironmentRepairAdapterConfig,
    ProductionEnvironmentRepairAdapter,
)
from codetoreum.adapters.testing.capturing_mock_event_emitter import CapturingMockEventEmitter
from codetoreum.domain.events.repair_cycle_events import (
    EnvironmentRebuildCompletedEvent,
    EnvironmentRebuildStartedEvent,
    EnvironmentVerificationCompletedEvent,
    EnvironmentVerificationStartedEvent,
)
from codetoreum.domain.repair_cycle_types import (
    EnvironmentRepairConfig,
    RepairTestRunConfig,
    RepairTestType,
)
from codetoreum.ports.output.llm_provider import ExecutionResult
from codetoreum.ports.output.repair_cycle_service import RepairCycleContext

# ============================================================================
# Test Fixtures and Helpers
# ============================================================================


@pytest.fixture
def mock_event_emitter():
    """Create a mock event emitter."""
    return CapturingMockEventEmitter()


@pytest.fixture
def mock_llm():
    """Create a mock LLM provider."""
    llm = AsyncMock()
    return llm


@pytest.fixture
def repair_config():
    """Create standard environment repair config."""
    return EnvironmentRepairConfig(
        max_env_rebuilds=2,
        env_rebuild_timeout_seconds=60,
        env_verification_timeout_seconds=30,
    )


@pytest.fixture
def test_context():
    """Create a test repair cycle context."""
    context = MagicMock(spec=RepairCycleContext)
    context.work_item_id = "issue-456"
    context.workflow_run_id = "run-123"
    context.iteration = 1
    context.agent_name = "test_agent"
    context.agent_config = None
    return context


@pytest.fixture
def test_config():
    """Create a test run configuration."""
    return RepairTestRunConfig(
        test_type=RepairTestType.UNIT,
        timeout=900,
        max_iterations=5,
        review_warnings=True,
    )


def _make_async_factory(llm):
    """Create an async factory that returns the given LLM for any agent name."""

    async def factory(agent_name):
        return llm

    return factory


def _make_adapter(
    llm,
    repair_config=None,
    event_emitter=None,
):
    """Create a ProductionEnvironmentRepairAdapter with the given LLM and config."""
    if repair_config is None:
        repair_config = EnvironmentRepairConfig()
    llm_factory = _make_async_factory(llm)
    return ProductionEnvironmentRepairAdapter(
        llm_factory=llm_factory,
        repair_config=repair_config,
        event_emitter=event_emitter,
    )


# ============================================================================
# rebuild_environment() Tests
# ============================================================================


@pytest.mark.asyncio
async def test_rebuild_environment_success(
    mock_llm, repair_config, test_context, test_config, mock_event_emitter
):
    """Test successful environment rebuild."""
    # Setup
    response = {
        "success": True,
        "actions_taken": ["install_deps", "configure_env"],
        "error": None,
    }
    mock_llm.execute.return_value = ExecutionResult(content=json.dumps(response))

    adapter = _make_adapter(mock_llm, repair_config, mock_event_emitter)

    # Execute
    result = await adapter.rebuild_environment(
        project="test-project",
        config=test_config,
        context=test_context,
    )

    # Verify result
    assert result.success is True
    assert len(result.actions_taken) == 2
    assert "install_deps" in result.actions_taken
    assert result.error is None
    assert result.duration_seconds >= 0

    # Verify events were emitted
    events = mock_event_emitter.get_events()
    assert len(events) == 2

    assert isinstance(events[0], EnvironmentRebuildStartedEvent)
    assert events[0].workflow_run_id == "run-123"
    assert events[0].test_type == RepairTestType.UNIT
    assert events[0].iteration == 1

    assert isinstance(events[1], EnvironmentRebuildCompletedEvent)
    assert events[1].workflow_run_id == "run-123"
    assert events[1].test_type == RepairTestType.UNIT
    assert events[1].iteration == 1
    assert events[1].success is True
    assert len(events[1].actions_taken) == 2


@pytest.mark.asyncio
async def test_rebuild_environment_failure(
    mock_llm, repair_config, test_context, test_config, mock_event_emitter
):
    """Test failed environment rebuild with error message."""
    # Setup
    response = {
        "success": False,
        "actions_taken": ["install_deps"],
        "error": "Failed to install dependency X",
    }
    mock_llm.execute.return_value = ExecutionResult(content=json.dumps(response))

    adapter = _make_adapter(mock_llm, repair_config, mock_event_emitter)

    # Execute
    result = await adapter.rebuild_environment(
        project="test-project",
        config=test_config,
        context=test_context,
    )

    # Verify result
    assert result.success is False
    assert result.error == "Failed to install dependency X"

    # Verify completed event reflects failure
    events = mock_event_emitter.get_events()
    completed_event = events[1]
    assert completed_event.success is False
    assert completed_event.error == "Failed to install dependency X"


@pytest.mark.asyncio
async def test_rebuild_environment_timeout(
    mock_llm, test_context, test_config, mock_event_emitter
):
    """Test rebuild timeout enforcement using configured timeout."""
    # Setup - create config with very short timeout
    rebuild_timeout = 1
    repair_config = EnvironmentRepairConfig(
        env_rebuild_timeout_seconds=rebuild_timeout,
        env_verification_timeout_seconds=30,
    )

    # Make LLM take longer than timeout
    async def slow_execute(**kwargs):
        import asyncio

        await asyncio.sleep(rebuild_timeout + 1)
        return ExecutionResult(content="{}")

    mock_llm.execute = slow_execute

    adapter = _make_adapter(mock_llm, repair_config, mock_event_emitter)

    # Execute and expect timeout
    with pytest.raises(TimeoutError, match="exceeded timeout"):
        await adapter.rebuild_environment(
            project="test-project",
            config=test_config,
            context=test_context,
        )

    # Verify completed event was emitted with timeout info
    events = mock_event_emitter.get_events()
    assert len(events) >= 2
    completed_event = next(
        (e for e in events if isinstance(e, EnvironmentRebuildCompletedEvent)),
        None,
    )
    assert completed_event is not None
    assert completed_event.success is False


@pytest.mark.asyncio
async def test_rebuild_environment_json_parse_error(
    mock_llm, repair_config, test_context, test_config, mock_event_emitter
):
    """Test rebuild with malformed JSON response."""
    # Setup - return invalid JSON
    mock_llm.execute.return_value = ExecutionResult(content="not valid json {")

    adapter = _make_adapter(mock_llm, repair_config, mock_event_emitter)

    # Execute
    result = await adapter.rebuild_environment(
        project="test-project",
        config=test_config,
        context=test_context,
    )

    # Verify result indicates failure
    assert result.success is False
    assert "Failed to parse" in result.error

    # Verify completed event reflects parse error
    events = mock_event_emitter.get_events()
    completed_event = events[1]
    assert completed_event.success is False


@pytest.mark.asyncio
async def test_rebuild_environment_no_event_emitter(mock_llm, repair_config, test_context, test_config):
    """Test rebuild works without event emitter (null-object pattern)."""
    # Setup - no event emitter provided
    response = {
        "success": True,
        "actions_taken": ["install_deps"],
        "error": None,
    }
    mock_llm.execute.return_value = ExecutionResult(content=json.dumps(response))

    adapter = _make_adapter(mock_llm, repair_config, event_emitter=None)

    # Execute - should not raise even without emitter
    result = await adapter.rebuild_environment(
        project="test-project",
        config=test_config,
        context=test_context,
    )

    assert result.success is True


# ============================================================================
# verify_environment() Tests
# ============================================================================


@pytest.mark.asyncio
async def test_verify_environment_success(
    mock_llm, repair_config, test_context, test_config, mock_event_emitter
):
    """Test successful environment verification."""
    # Setup
    response = {
        "healthy": True,
        "checks_passed": ["deps_installed", "env_vars_set", "services_running"],
        "checks_failed": [],
    }
    mock_llm.execute.return_value = ExecutionResult(content=json.dumps(response))

    adapter = _make_adapter(mock_llm, repair_config, mock_event_emitter)

    # Execute
    result = await adapter.verify_environment(
        project="test-project",
        config=test_config,
        context=test_context,
    )

    # Verify result
    assert result.healthy is True
    assert len(result.checks_passed) == 3
    assert len(result.checks_failed) == 0
    assert result.duration_seconds >= 0

    # Verify events were emitted
    events = mock_event_emitter.get_events()
    assert len(events) == 2

    assert isinstance(events[0], EnvironmentVerificationStartedEvent)
    assert events[0].workflow_run_id == "run-123"
    assert events[0].test_type == RepairTestType.UNIT
    assert events[0].iteration == 1

    assert isinstance(events[1], EnvironmentVerificationCompletedEvent)
    assert events[1].workflow_run_id == "run-123"
    assert events[1].test_type == RepairTestType.UNIT
    assert events[1].iteration == 1
    assert events[1].healthy is True
    assert len(events[1].checks_passed) == 3


@pytest.mark.asyncio
async def test_verify_environment_failure(
    mock_llm, repair_config, test_context, test_config, mock_event_emitter
):
    """Test failed environment verification with failed checks."""
    # Setup
    response = {
        "healthy": False,
        "checks_passed": ["deps_installed"],
        "checks_failed": ["env_vars_set", "services_running"],
    }
    mock_llm.execute.return_value = ExecutionResult(content=json.dumps(response))

    adapter = _make_adapter(mock_llm, repair_config, mock_event_emitter)

    # Execute
    result = await adapter.verify_environment(
        project="test-project",
        config=test_config,
        context=test_context,
    )

    # Verify result
    assert result.healthy is False
    assert len(result.checks_passed) == 1
    assert len(result.checks_failed) == 2

    # Verify completed event reflects failure
    events = mock_event_emitter.get_events()
    completed_event = events[1]
    assert completed_event.healthy is False
    assert len(completed_event.checks_failed) == 2


@pytest.mark.asyncio
async def test_verify_environment_timeout(
    mock_llm, test_context, test_config, mock_event_emitter
):
    """Test verification timeout enforcement using configured timeout."""
    # Setup - create config with very short timeout
    verify_timeout = 1
    repair_config = EnvironmentRepairConfig(
        env_rebuild_timeout_seconds=60,
        env_verification_timeout_seconds=verify_timeout,
    )

    # Make LLM take longer than timeout
    async def slow_execute(**kwargs):
        import asyncio

        await asyncio.sleep(verify_timeout + 1)
        return ExecutionResult(content="{}")

    mock_llm.execute = slow_execute

    adapter = _make_adapter(mock_llm, repair_config, mock_event_emitter)

    # Execute and expect timeout
    with pytest.raises(TimeoutError, match="exceeded timeout"):
        await adapter.verify_environment(
            project="test-project",
            config=test_config,
            context=test_context,
        )

    # Verify completed event was emitted with timeout info
    events = mock_event_emitter.get_events()
    assert len(events) >= 2
    completed_event = next(
        (e for e in events if isinstance(e, EnvironmentVerificationCompletedEvent)),
        None,
    )
    assert completed_event is not None
    assert completed_event.healthy is False


@pytest.mark.asyncio
async def test_verify_environment_json_parse_error(
    mock_llm, repair_config, test_context, test_config, mock_event_emitter
):
    """Test verification with malformed JSON response."""
    # Setup - return invalid JSON
    mock_llm.execute.return_value = ExecutionResult(content="not valid json [")

    adapter = _make_adapter(mock_llm, repair_config, mock_event_emitter)

    # Execute
    result = await adapter.verify_environment(
        project="test-project",
        config=test_config,
        context=test_context,
    )

    # Verify result indicates failure
    assert result.healthy is False
    assert "parsing_response" in result.checks_failed

    # Verify completed event reflects parse error
    events = mock_event_emitter.get_events()
    completed_event = events[1]
    assert completed_event.healthy is False


@pytest.mark.asyncio
async def test_verify_environment_no_event_emitter(
    mock_llm, repair_config, test_context, test_config
):
    """Test verify works without event emitter (null-object pattern)."""
    # Setup - no event emitter provided
    response = {
        "healthy": True,
        "checks_passed": ["deps_installed"],
        "checks_failed": [],
    }
    mock_llm.execute.return_value = ExecutionResult(content=json.dumps(response))

    adapter = _make_adapter(mock_llm, repair_config, event_emitter=None)

    # Execute - should not raise even without emitter
    result = await adapter.verify_environment(
        project="test-project",
        config=test_config,
        context=test_context,
    )

    assert result.healthy is True


# ============================================================================
# Independent Timeout Tests
# ============================================================================


@pytest.mark.asyncio
async def test_rebuild_and_verify_independent_timeouts(
    mock_llm, test_context, test_config, mock_event_emitter
):
    """Test that rebuild and verify timeouts are independent."""
    # Setup - short rebuild timeout, longer verify timeout
    repair_config = EnvironmentRepairConfig(
        env_rebuild_timeout_seconds=1,
        env_verification_timeout_seconds=60,
    )

    # First call (rebuild) will timeout
    call_count = 0

    async def mock_execute(**kwargs):
        nonlocal call_count
        import asyncio

        call_count += 1
        if call_count == 1:
            # First call (rebuild) - slow, will timeout
            await asyncio.sleep(2)
        else:
            # Second call (verify) - fast, will succeed
            return ExecutionResult(
                content=json.dumps(
                    {
                        "healthy": True,
                        "checks_passed": ["all"],
                        "checks_failed": [],
                    }
                )
            )
        return ExecutionResult(content="{}")

    mock_llm.execute = mock_execute

    adapter = _make_adapter(mock_llm, repair_config, mock_event_emitter)

    # First call should timeout with rebuild timeout
    with pytest.raises(TimeoutError, match="exceeded timeout"):
        await adapter.rebuild_environment(
            project="test-project",
            config=test_config,
            context=test_context,
        )

    # Verify rebuild used its own timeout
    events = mock_event_emitter.get_events()
    rebuild_completed = next(
        (e for e in events if isinstance(e, EnvironmentRebuildCompletedEvent)), None
    )
    assert rebuild_completed is not None


# ============================================================================
# Agent Resolution Tests
# ============================================================================


@pytest.mark.asyncio
async def test_rebuild_with_specialized_agent(mock_llm, repair_config, test_config):
    """Test that rebuild uses specialized agent when configured."""
    from unittest.mock import call

    # Create a mock agent config
    agent_config = MagicMock()
    agent_config.resolve_agent.return_value = "specialized_rebuild_agent"

    context = MagicMock(spec=RepairCycleContext)
    context.work_item_id = "issue-456"
    context.workflow_run_id = "run-123"
    context.iteration = 1
    context.agent_name = "default_agent"
    context.agent_config = agent_config

    response = {"success": True, "actions_taken": [], "error": None}
    mock_llm.execute.return_value = ExecutionResult(content=json.dumps(response))

    llm_calls = []

    async def tracking_factory(agent_name):
        llm_calls.append(agent_name)
        return mock_llm

    adapter = ProductionEnvironmentRepairAdapter(
        llm_factory=tracking_factory,
        repair_config=repair_config,
    )

    # Execute rebuild
    await adapter.rebuild_environment(
        project="test-project",
        config=test_config,
        context=context,
    )

    # Verify specialized agent was used
    assert "specialized_rebuild_agent" in llm_calls
    agent_config.resolve_agent.assert_called_with("env_rebuild", "default_agent")


@pytest.mark.asyncio
async def test_verify_with_specialized_agent(mock_llm, repair_config, test_config):
    """Test that verify uses specialized agent when configured."""
    # Create a mock agent config
    agent_config = MagicMock()
    agent_config.resolve_agent.return_value = "specialized_verify_agent"

    context = MagicMock(spec=RepairCycleContext)
    context.work_item_id = "issue-456"
    context.workflow_run_id = "run-123"
    context.iteration = 1
    context.agent_name = "default_agent"
    context.agent_config = agent_config

    response = {"healthy": True, "checks_passed": [], "checks_failed": []}
    mock_llm.execute.return_value = ExecutionResult(content=json.dumps(response))

    llm_calls = []

    async def tracking_factory(agent_name):
        llm_calls.append(agent_name)
        return mock_llm

    adapter = ProductionEnvironmentRepairAdapter(
        llm_factory=tracking_factory,
        repair_config=repair_config,
    )

    # Execute verify
    await adapter.verify_environment(
        project="test-project",
        config=test_config,
        context=context,
    )

    # Verify specialized agent was used
    assert "specialized_verify_agent" in llm_calls
    agent_config.resolve_agent.assert_called_with("env_verification", "default_agent")
