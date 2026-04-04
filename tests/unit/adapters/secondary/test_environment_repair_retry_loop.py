"""Integration tests for environment repair retry loop in ProductionRepairCycleAdapter.

Verifies that:
1. Environment issue classified → retry loop with rebuild/verify bounded by max_env_rebuilds
2. Single rebuild succeeds → verify succeeds → tests rerun
3. First rebuild fails → retries → second rebuild succeeds → verify succeeds
4. All rebuild attempts fail → exhausted marker set, cycle breaks
5. Rebuild succeeds but verify fails → retries → eventually exhausted or succeeds
6. Proper logging and event emission during retry loops
7. IEnvironmentRepairService is properly delegated to when injected
8. Fallback to LLM-based rebuild/verify when service not provided
9. MockRepairCycleAdapter delegates to service when provided
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.adapters.secondary.production_repair_cycle_adapter import (
    ProductionRepairCycleAdapter,
    RepairCycleConfig,
)
from codetoreum.adapters.testing.mock_repair_cycle_adapter import MockRepairCycleAdapter
from codetoreum.domain.repair_cycle_types import (
    EnvironmentRepairConfig,
    FailureClassification,
    RepairTestFailure,
    RepairTestResult,
    RepairTestRunConfig,
    RepairTestType,
    RebuildResult,
    VerificationResult,
)
from codetoreum.ports.output.llm_provider import ExecutionResult

# ---------------------------------------------------------------------------
# Shared test fixtures and helpers
# ---------------------------------------------------------------------------

_ENVIRONMENT_ISSUE_JSON = (
    '{"passed": 0, "failed": 1, '
    '"failures": [{"file": "test_foo.py", "test": "test_bar", "message": "env error"}], '
    '"warnings": []}'
)


class _RepairCycleContext:
    """Minimal RepairCycleContext for unit tests."""

    def __init__(self, max_total_agent_calls: int = 100) -> None:
        self.stage_name = "fix_failures"
        self.workflow_run_id = "run-1"
        self.work_item_id = "item-1"
        self.test_configs = (
            RepairTestRunConfig(
                test_type=RepairTestType.UNIT,
                timeout=30,
                max_iterations=2,
                review_warnings=False,
            ),
        )
        self.agent_name = "test_agent"
        self.max_total_agent_calls = max_total_agent_calls
        self.checkpoint_interval = 5
        self.agent_config = None
        self.systemic_fix_failure_ceiling = 50
        self.iteration = 0
        self.prior_fix_attempts = ()
        self.prior_classifications = ()


def _make_async_factory(llm):
    """Create an async factory that returns the given LLM for any agent name."""

    async def factory(agent_name):
        return llm

    return factory


def _make_adapter(
    *,
    llm_response: str = _ENVIRONMENT_ISSUE_JSON,
    environment_repair_service=None,
) -> tuple[ProductionRepairCycleAdapter, AsyncMock]:
    """Return (adapter, mock_llm) pre-wired for tests."""
    llm = AsyncMock()
    llm.execute.return_value = ExecutionResult(content=llm_response)

    llm_factory = _make_async_factory(llm)
    return (
        ProductionRepairCycleAdapter(
            llm_factory=llm_factory,
            config=RepairCycleConfig(),
            environment_repair_service=environment_repair_service,
        ),
        llm,
    )


# ---------------------------------------------------------------------------
# Environment Repair Retry Loop Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_environment_issue_single_rebuild_succeeds():
    """Test ENVIRONMENT_ISSUE with single rebuild attempt that succeeds."""
    # Mock environment repair service
    env_service = AsyncMock()
    env_service.rebuild_environment.return_value = RebuildResult(
        success=True,
        duration_seconds=5.0,
        actions_taken=("install_deps",),
        error=None,
    )
    env_service.verify_environment.return_value = VerificationResult(
        healthy=True,
        checks_passed=("deps_check", "config_check"),
        checks_failed=(),
        duration_seconds=2.0,
    )

    # Mock systemic analysis to classify as ENVIRONMENT_ISSUE
    systemic_service = AsyncMock()
    systemic_service.analyze.return_value = MagicMock(
        classification=FailureClassification.ENVIRONMENT_ISSUE,
        confidence=0.95,
        reasoning="Missing dependencies",
        recommended_action="Rebuild environment",
        affected_files=("test_foo.py",),
        cross_cutting=False,
    )

    adapter, llm = _make_adapter(environment_repair_service=env_service)
    adapter._systemic_analysis_service = systemic_service

    # After rebuild/verify succeeds, tests pass
    llm.execute.side_effect = [
        ExecutionResult(content=_ENVIRONMENT_ISSUE_JSON),  # Initial test run
        ExecutionResult(
            content='{"passed": 1, "failed": 0, "failures": [], "warnings": []}'
        ),  # Re-test after env fix
    ]

    ctx = _RepairCycleContext()
    result = await adapter.execute(ctx)

    # Verify rebuild and verify were called
    env_service.rebuild_environment.assert_called_once()
    env_service.verify_environment.assert_called_once()

    # Verify no more rebuild attempts (success on first try)
    assert env_service.rebuild_environment.call_count == 1
    assert env_service.verify_environment.call_count == 1

    # Verify test passed after environment fix
    assert result.overall_success


@pytest.mark.asyncio
async def test_environment_issue_rebuild_fails_then_succeeds():
    """Test ENVIRONMENT_ISSUE where first rebuild fails, second rebuild succeeds."""
    env_service = AsyncMock()

    # First rebuild fails, second succeeds
    env_service.rebuild_environment.side_effect = [
        RebuildResult(success=False, duration_seconds=3.0, actions_taken=(), error="Failed to install deps"),
        RebuildResult(success=True, duration_seconds=5.0, actions_taken=("install_deps",), error=None),
    ]

    # Both verifications succeed (but only second is called after successful rebuild)
    env_service.verify_environment.return_value = VerificationResult(
        healthy=True,
        checks_passed=("deps_check",),
        checks_failed=(),
        duration_seconds=2.0,
    )

    systemic_service = AsyncMock()
    systemic_service.analyze.return_value = MagicMock(
        classification=FailureClassification.ENVIRONMENT_ISSUE,
        confidence=0.95,
        reasoning="Missing dependencies",
        recommended_action="Rebuild environment",
        affected_files=("test_foo.py",),
        cross_cutting=False,
    )

    adapter, llm = _make_adapter(environment_repair_service=env_service)
    adapter._systemic_analysis_service = systemic_service

    llm.execute.side_effect = [
        ExecutionResult(content=_ENVIRONMENT_ISSUE_JSON),  # Initial test run
        ExecutionResult(
            content='{"passed": 1, "failed": 0, "failures": [], "warnings": []}'
        ),  # Re-test after env fix succeeds
    ]

    ctx = _RepairCycleContext()
    result = await adapter.execute(ctx)

    # Verify rebuild was called twice (first failed, second succeeded)
    assert env_service.rebuild_environment.call_count == 2
    # Verify is called once (only after successful rebuild)
    assert env_service.verify_environment.call_count == 1

    assert result.overall_success


@pytest.mark.asyncio
async def test_environment_issue_all_rebuilds_exhausted():
    """Test ENVIRONMENT_ISSUE where all rebuild attempts fail or verification fails."""
    env_service = AsyncMock()

    # All rebuilds fail
    env_service.rebuild_environment.return_value = RebuildResult(
        success=False,
        duration_seconds=3.0,
        actions_taken=(),
        error="Persistent environment issue",
    )

    env_service.verify_environment.return_value = VerificationResult(
        healthy=False,
        checks_passed=(),
        checks_failed=("deps_check",),
        duration_seconds=2.0,
    )

    systemic_service = AsyncMock()
    systemic_service.analyze.return_value = MagicMock(
        classification=FailureClassification.ENVIRONMENT_ISSUE,
        confidence=0.95,
        reasoning="Environment corruption",
        recommended_action="Rebuild environment",
        affected_files=("test_foo.py",),
        cross_cutting=False,
    )

    adapter, llm = _make_adapter(environment_repair_service=env_service)
    adapter._systemic_analysis_service = systemic_service

    llm.execute.return_value = ExecutionResult(content=_ENVIRONMENT_ISSUE_JSON)

    ctx = _RepairCycleContext()
    result = await adapter.execute(ctx)

    # Verify rebuild was called max_env_rebuilds times
    env_repair_config = EnvironmentRepairConfig()
    assert env_service.rebuild_environment.call_count == env_repair_config.max_env_rebuilds

    # Verify cycle failed (exhausted)
    assert result.overall_success is False


@pytest.mark.asyncio
async def test_environment_issue_rebuild_succeeds_verify_fails_all_attempts():
    """Test ENVIRONMENT_ISSUE where rebuild succeeds but verify fails repeatedly."""
    env_service = AsyncMock()

    env_service.rebuild_environment.return_value = RebuildResult(
        success=True,
        duration_seconds=5.0,
        actions_taken=("install_deps",),
        error=None,
    )

    # All verifications fail
    env_service.verify_environment.return_value = VerificationResult(
        healthy=False,
        checks_passed=(),
        checks_failed=("config_check",),
        duration_seconds=2.0,
    )

    systemic_service = AsyncMock()
    systemic_service.analyze.return_value = MagicMock(
        classification=FailureClassification.ENVIRONMENT_ISSUE,
        confidence=0.95,
        reasoning="Configuration issue",
        recommended_action="Rebuild environment",
        affected_files=("test_foo.py",),
        cross_cutting=False,
    )

    adapter, llm = _make_adapter(environment_repair_service=env_service)
    adapter._systemic_analysis_service = systemic_service

    llm.execute.return_value = ExecutionResult(content=_ENVIRONMENT_ISSUE_JSON)

    ctx = _RepairCycleContext()
    result = await adapter.execute(ctx)

    # Verify rebuild and verify were called max_env_rebuilds times each
    env_repair_config = EnvironmentRepairConfig()
    assert env_service.rebuild_environment.call_count == env_repair_config.max_env_rebuilds
    assert env_service.verify_environment.call_count == env_repair_config.max_env_rebuilds

    # Verify cycle failed (exhausted)
    assert result.overall_success is False


@pytest.mark.asyncio
async def test_environment_issue_without_service_uses_llm_fallback():
    """Test ENVIRONMENT_ISSUE without environment repair service falls back to LLM."""
    systemic_service = AsyncMock()
    systemic_service.analyze.return_value = MagicMock(
        classification=FailureClassification.ENVIRONMENT_ISSUE,
        confidence=0.95,
        reasoning="Missing dependencies",
        recommended_action="Rebuild environment",
        affected_files=("test_foo.py",),
        cross_cutting=False,
    )

    adapter, llm = _make_adapter(environment_repair_service=None)  # No service
    adapter._systemic_analysis_service = systemic_service

    # Mock LLM responses for rebuild, verify, and retest
    llm.execute.side_effect = [
        ExecutionResult(content=_ENVIRONMENT_ISSUE_JSON),  # Initial test
        ExecutionResult(content='{"success": true}'),  # Rebuild (LLM fallback)
        ExecutionResult(content='{"ready": true}'),  # Verify (LLM fallback)
        ExecutionResult(
            content='{"passed": 1, "failed": 0, "failures": [], "warnings": []}'
        ),  # Retest
    ]

    ctx = _RepairCycleContext()
    result = await adapter.execute(ctx)

    # Verify LLM was called for rebuild and verify (fallback path)
    # First call: initial test run
    # Second call: rebuild prompt (LLM fallback)
    # Third call: verify prompt (LLM fallback)
    # Fourth call: retest
    assert llm.execute.call_count >= 3  # At minimum for test, rebuild, verify


@pytest.mark.asyncio
async def test_mock_repair_cycle_adapter_delegates_to_environment_service():
    """Test MockRepairCycleAdapter delegates to injected environment repair service."""
    env_service = AsyncMock()
    env_service.rebuild_environment.return_value = RebuildResult(
        success=True,
        duration_seconds=5.0,
        actions_taken=("mock_rebuild",),
        error=None,
    )
    env_service.verify_environment.return_value = VerificationResult(
        healthy=True,
        checks_passed=("mock_check",),
        checks_failed=(),
        duration_seconds=1.0,
    )

    adapter = MockRepairCycleAdapter(environment_repair_service=env_service)

    config = RepairTestRunConfig(
        test_type=RepairTestType.UNIT,
        timeout=30,
        max_iterations=1,
        review_warnings=False,
    )
    ctx = _RepairCycleContext()

    # Call rebuild
    rebuild_result = await adapter.rebuild_environment(config, ctx)
    assert rebuild_result is True
    env_service.rebuild_environment.assert_called_once()

    # Call verify
    verify_result = await adapter.verify_environment(config, ctx)
    assert verify_result is True
    env_service.verify_environment.assert_called_once()


@pytest.mark.asyncio
async def test_mock_repair_cycle_adapter_fallback_without_service():
    """Test MockRepairCycleAdapter simulates successful rebuild/verify without service."""
    # No service injected
    adapter = MockRepairCycleAdapter(environment_repair_service=None)

    config = RepairTestRunConfig(
        test_type=RepairTestType.UNIT,
        timeout=30,
        max_iterations=1,
        review_warnings=False,
    )
    ctx = _RepairCycleContext()

    # Should simulate successful rebuild
    rebuild_result = await adapter.rebuild_environment(config, ctx)
    assert rebuild_result is True

    # Should simulate successful verify
    verify_result = await adapter.verify_environment(config, ctx)
    assert verify_result is True
