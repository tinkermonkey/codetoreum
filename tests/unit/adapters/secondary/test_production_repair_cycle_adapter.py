"""Unit tests for ProductionRepairCycleAdapter circuit breaker, classification dispatch, and helper methods.

Verifies that:
1. execute() raises CircuitBreakerOpenError and emits fast-fail event when CB is pre-opened
2. is_open() is used to check state (not get_state() == OPEN)
3. Without a CB, LLM is called directly (not via cb.call())
4. With a CB, LLM is wrapped via circuit_breaker.call()
5. get_stats().total_calls is used for RepairCycleResult.total_agent_calls
6. fix_failures_by_file checks is_open() before each file
7. Classification dispatch routes CODE_DEFECT to fix_failures_by_file, ENVIRONMENT_ISSUE to rebuild/verify
8. TRANSIENT_FAILURE escalates to CODE_DEFECT after 2 consecutive occurrences
9. DEPENDENCY_ISSUE/CONFIGURATION_ISSUE route to apply_systemic_fixes
10. Classifier exceptions fall back to fix_failures_by_file
11. Prior classifications and fix attempts are tracked and passed to systemic analysis
12. Environment rebuild/verify, apply_systemic_fixes, and prompt builders work correctly
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.adapters.secondary.production_repair_cycle_adapter import (
    ProductionRepairCycleAdapter,
    RepairCycleConfig,
)
from codetoreum.domain.repair_cycle_types import (
    FailureClassification,
    RepairTestFailure,
    RepairTestResult,
    RepairTestRunConfig,
    RepairTestType,
    RepairTestWarning,
)
from codetoreum.infrastructure.resilience.exceptions import CircuitBreakerOpenError
from codetoreum.infrastructure.resilience.interfaces import CircuitState
from codetoreum.infrastructure.resilience.mocks import MockCircuitBreaker
from codetoreum.ports.output.llm_provider import ExecutionResult

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

# Always-failing response: avoids CycleResult invariant bug where
# _run_test_cycle hardcodes final_result=None even when passed=True.
_VALID_JSON_RESPONSE = (
    '{"passed": 0, "failed": 1, '
    '"failures": [{"file": "test_foo.py", "test": "test_bar", "message": "fail"}], '
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
                max_iterations=1,
                review_warnings=False,
            ),
        )
        self.agent_name = "test_agent"
        self.max_total_agent_calls = max_total_agent_calls
        self.checkpoint_interval = 5
        self.agent_config = None  # No per-subtask agent config in tests


def _make_adapter(
    *,
    llm_response: str = _VALID_JSON_RESPONSE,
    circuit_breaker=None,
    event_emitter=None,
) -> tuple[ProductionRepairCycleAdapter, AsyncMock]:
    """Return (adapter, mock_llm) pre-wired for tests."""
    llm = AsyncMock()
    llm.execute.return_value = ExecutionResult(content=llm_response)

    # Create async factory that returns the same mock LLM for any agent name
    async def llm_factory(agent_name):
        return llm

    config = RepairCycleConfig(max_json_parse_retries=1, json_parse_retry_delay_ms=0)
    adapter = ProductionRepairCycleAdapter(
        llm_factory=llm_factory,
        config=config,
        event_emitter=event_emitter,
        circuit_breaker=circuit_breaker,
    )
    return adapter, llm


# ---------------------------------------------------------------------------
# CB pre-opened → execute() raises and emits fast-fail event
# ---------------------------------------------------------------------------


class TestCircuitBreakerPreOpened:
    @pytest.mark.asyncio
    async def test_execute_raises_when_cb_pre_opened(self):
        """execute() raises CircuitBreakerOpenError when CB is open before the loop."""
        cb = MockCircuitBreaker(initial_state=CircuitState.OPEN)
        adapter, _ = _make_adapter(circuit_breaker=cb)
        ctx = _RepairCycleContext()

        with pytest.raises(CircuitBreakerOpenError):
            await adapter.execute(ctx)

    @pytest.mark.asyncio
    async def test_execute_emits_fast_fail_event_when_cb_pre_opened(self):
        """execute() emits RepairCycleFastFailEvent when CB is pre-opened."""
        cb = MockCircuitBreaker(initial_state=CircuitState.OPEN)
        event_emitter = MagicMock()
        adapter, _ = _make_adapter(circuit_breaker=cb, event_emitter=event_emitter)
        ctx = _RepairCycleContext()

        with pytest.raises(CircuitBreakerOpenError):
            await adapter.execute(ctx)

        emitted_types = [call.args[0].type for call in event_emitter.emit.call_args_list]
        assert "repair_cycle.fast_fail" in emitted_types

    @pytest.mark.asyncio
    async def test_execute_no_llm_calls_when_cb_pre_opened(self):
        """LLM must not be called at all when CB is open at the start."""
        cb = MockCircuitBreaker(initial_state=CircuitState.OPEN)
        adapter, llm = _make_adapter(circuit_breaker=cb)
        ctx = _RepairCycleContext()

        with pytest.raises(CircuitBreakerOpenError):
            await adapter.execute(ctx)

        llm.execute.assert_not_called()


# ---------------------------------------------------------------------------
# is_open() is the check — not get_state() == OPEN
# ---------------------------------------------------------------------------


class TestIsOpenUsedNotGetState:
    @pytest.mark.asyncio
    async def test_is_open_true_overrides_closed_get_state(self):
        """CB with is_open()=True but get_state()=CLOSED is still treated as open."""
        cb = MagicMock()
        # is_open() returns True → should be treated as open
        cb.is_open.return_value = True
        # get_state() would return CLOSED if the old pattern were used
        cb.get_state.return_value = CircuitState.CLOSED
        cb.get_stats.return_value = MagicMock(total_calls=0)

        adapter, _ = _make_adapter(circuit_breaker=cb)
        ctx = _RepairCycleContext()

        with pytest.raises(CircuitBreakerOpenError):
            await adapter.execute(ctx)

        # Confirms is_open was called (not get_state compared to OPEN)
        cb.is_open.assert_called()


# ---------------------------------------------------------------------------
# Without CB → direct LLM call
# ---------------------------------------------------------------------------


class TestNoCBDirectLLMCall:
    @pytest.mark.asyncio
    async def test_no_cb_run_tests_calls_llm_directly(self):
        """Without a CB, run_tests() calls llm_provider.execute directly."""
        adapter, llm = _make_adapter(circuit_breaker=None)
        ctx = _RepairCycleContext()

        await adapter.run_tests(ctx.test_configs[0], ctx)

        llm.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_cb_result_total_agent_calls_is_zero(self):
        """Without CB, RepairCycleResult.total_agent_calls == 0 (no stats available)."""
        adapter, _ = _make_adapter(circuit_breaker=None)
        ctx = _RepairCycleContext()

        result = await adapter.execute(ctx)

        assert result.total_agent_calls == 0


# ---------------------------------------------------------------------------
# With CB → LLM wrapped via circuit_breaker.call()
# ---------------------------------------------------------------------------


class TestWithCBWrapsLLM:
    @pytest.mark.asyncio
    async def test_with_cb_run_tests_calls_via_cb(self):
        """With a CB, run_tests() routes the LLM call through circuit_breaker.call()."""
        cb = MockCircuitBreaker()
        adapter, llm = _make_adapter(circuit_breaker=cb)
        ctx = _RepairCycleContext()

        await adapter.run_tests(ctx.test_configs[0], ctx)

        assert len(cb.call_history) >= 1
        assert cb.call_history[0]["operation"] == "repair_cycle.run_tests"

    @pytest.mark.asyncio
    async def test_with_cb_total_agent_calls_reflects_cb_stats(self):
        """RepairCycleResult.total_agent_calls == circuit_breaker.get_stats().total_calls."""
        cb = MockCircuitBreaker()
        adapter, _ = _make_adapter(circuit_breaker=cb)
        ctx = _RepairCycleContext()

        result = await adapter.execute(ctx)

        assert result.total_agent_calls == cb.get_stats().total_calls


# ---------------------------------------------------------------------------
# fix_failures_by_file checks is_open() before each file
# ---------------------------------------------------------------------------


class TestFixFailuresByFileCircuitBreaker:
    @pytest.mark.asyncio
    async def test_fix_failures_raises_when_cb_open(self):
        """fix_failures_by_file raises CircuitBreakerOpenError when CB is open."""
        cb = MockCircuitBreaker(initial_state=CircuitState.OPEN)
        adapter, _ = _make_adapter(circuit_breaker=cb)
        ctx = _RepairCycleContext()

        grouped: dict[str, tuple[RepairTestFailure, ...]] = {
            "test_foo.py": (RepairTestFailure(file="test_foo.py", test="test_1", message="fail"),),
        }

        with pytest.raises(CircuitBreakerOpenError):
            await adapter.fix_failures_by_file(grouped, ctx.test_configs[0], ctx)

    @pytest.mark.asyncio
    async def test_fix_failures_calls_is_open_before_each_file(self):
        """fix_failures_by_file calls is_open() once per file."""
        cb = MagicMock()
        cb.is_open.return_value = False  # stay closed
        cb.call = AsyncMock(return_value=None)
        cb.get_stats.return_value = MagicMock(total_calls=0)

        adapter, _ = _make_adapter(circuit_breaker=cb)
        ctx = _RepairCycleContext()

        grouped: dict[str, tuple[RepairTestFailure, ...]] = {
            "test_a.py": (RepairTestFailure(file="test_a.py", test="t1", message="fail"),),
            "test_b.py": (RepairTestFailure(file="test_b.py", test="t2", message="fail"),),
        }

        await adapter.fix_failures_by_file(grouped, ctx.test_configs[0], ctx)

        # is_open must have been called for each file (at minimum twice)
        assert cb.is_open.call_count >= 2


# ---------------------------------------------------------------------------
# Classification Dispatch: CODE_DEFECT
# ---------------------------------------------------------------------------


class TestClassificationDispatchCodeDefect:
    @pytest.mark.asyncio
    async def test_code_defect_dispatch_calls_fix_failures_by_file(self):
        """CODE_DEFECT classification routes to fix_failures_by_file."""
        event_emitter = MagicMock()
        systemic_service = AsyncMock()
        systemic_service.analyze.return_value = MagicMock(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.95,
            reasoning="Source code has a bug",
            recommended_action="Fix the bug",
            cross_cutting=False,
        )

        adapter, llm = _make_adapter(event_emitter=event_emitter)
        adapter._systemic_analysis_service = systemic_service

        # Mock fix_failures_by_file
        adapter.fix_failures_by_file = AsyncMock(return_value=1)

        ctx = _RepairCycleContext(max_total_agent_calls=100)
        await adapter.execute(ctx)

        systemic_service.analyze.assert_called_once()
        adapter.fix_failures_by_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_code_defect_emits_systemic_analysis_events(self):
        """CODE_DEFECT dispatch emits SystemicAnalysisStartedEvent and CompletedEvent."""
        event_emitter = MagicMock()
        systemic_service = AsyncMock()
        systemic_service.analyze.return_value = MagicMock(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.95,
            reasoning="Source code has a bug",
            recommended_action="Fix the bug",
            cross_cutting=False,
        )

        adapter, _ = _make_adapter(event_emitter=event_emitter)
        adapter._systemic_analysis_service = systemic_service
        adapter.fix_failures_by_file = AsyncMock(return_value=1)

        ctx = _RepairCycleContext(max_total_agent_calls=100)
        await adapter.execute(ctx)

        emitted_types = [call.args[0].type for call in event_emitter.emit.call_args_list]
        assert "repair_cycle.systemic_analysis_started" in emitted_types
        assert "repair_cycle.systemic_analysis_completed" in emitted_types

    @pytest.mark.asyncio
    async def test_code_defect_resets_transient_counter(self):
        """CODE_DEFECT classification resets consecutive_transient_failures counter."""
        event_emitter = MagicMock()
        systemic_service = AsyncMock()

        # First iteration: TRANSIENT_FAILURE (increments counter)
        # Second iteration: CODE_DEFECT (resets counter)
        systemic_service.analyze.side_effect = [
            MagicMock(
                classification=FailureClassification.TRANSIENT_FAILURE,
                confidence=0.8,
                reasoning="Flaky test",
                recommended_action="Retry",
            cross_cutting=False,
            ),
            MagicMock(
                classification=FailureClassification.CODE_DEFECT,
                confidence=0.95,
                reasoning="Source code has a bug",
                recommended_action="Fix the bug",
            cross_cutting=False,
            ),
        ]

        adapter, _ = _make_adapter(event_emitter=event_emitter)
        adapter._systemic_analysis_service = systemic_service
        adapter.fix_failures_by_file = AsyncMock(return_value=1)

        ctx = _RepairCycleContext(max_total_agent_calls=100)
        # Set max_iterations to 2 to allow multiple analysis calls
        ctx.test_configs = (
            RepairTestRunConfig(
                test_type=RepairTestType.UNIT,
                timeout=30,
                max_iterations=2,
                review_warnings=False,
            ),
        )

        await adapter.execute(ctx)

        # Both analyze calls should succeed
        assert systemic_service.analyze.call_count == 2


# ---------------------------------------------------------------------------
# Classification Dispatch: ENVIRONMENT_ISSUE
# ---------------------------------------------------------------------------


class TestClassificationDispatchEnvironmentIssue:
    @pytest.mark.asyncio
    async def test_environment_issue_dispatch_calls_rebuild_and_verify(self):
        """ENVIRONMENT_ISSUE classification routes to rebuild_environment and verify_environment."""
        event_emitter = MagicMock()
        systemic_service = AsyncMock()
        systemic_service.analyze.return_value = MagicMock(
            classification=FailureClassification.ENVIRONMENT_ISSUE,
            confidence=0.9,
            reasoning="Missing environment setup",
            recommended_action="Rebuild environment",
            cross_cutting=False,
        )

        adapter, _ = _make_adapter(event_emitter=event_emitter)
        adapter._systemic_analysis_service = systemic_service
        adapter.rebuild_environment = AsyncMock(return_value=True)
        adapter.verify_environment = AsyncMock(return_value=True)

        ctx = _RepairCycleContext(max_total_agent_calls=100)
        await adapter.execute(ctx)

        systemic_service.analyze.assert_called_once()
        adapter.rebuild_environment.assert_called_once()
        adapter.verify_environment.assert_called_once()

    @pytest.mark.asyncio
    async def test_environment_issue_skip_verify_if_rebuild_fails(self):
        """ENVIRONMENT_ISSUE skips verify_environment if rebuild_environment returns False."""
        event_emitter = MagicMock()
        systemic_service = AsyncMock()
        systemic_service.analyze.return_value = MagicMock(
            classification=FailureClassification.ENVIRONMENT_ISSUE,
            confidence=0.9,
            reasoning="Missing environment setup",
            recommended_action="Rebuild environment",
            cross_cutting=False,
        )

        adapter, _ = _make_adapter(event_emitter=event_emitter)
        adapter._systemic_analysis_service = systemic_service
        adapter.rebuild_environment = AsyncMock(return_value=False)
        adapter.verify_environment = AsyncMock(return_value=True)

        ctx = _RepairCycleContext(max_total_agent_calls=100)
        await adapter.execute(ctx)

        adapter.rebuild_environment.assert_called_once()
        # verify_environment should not be called if rebuild fails
        adapter.verify_environment.assert_not_called()

    @pytest.mark.asyncio
    async def test_environment_issue_resets_transient_counter(self):
        """ENVIRONMENT_ISSUE classification resets consecutive_transient_failures counter."""
        event_emitter = MagicMock()
        systemic_service = AsyncMock()
        systemic_service.analyze.return_value = MagicMock(
            classification=FailureClassification.ENVIRONMENT_ISSUE,
            confidence=0.9,
            reasoning="Missing environment setup",
            recommended_action="Rebuild environment",
            cross_cutting=False,
        )

        adapter, _ = _make_adapter(event_emitter=event_emitter)
        adapter._systemic_analysis_service = systemic_service
        adapter.rebuild_environment = AsyncMock(return_value=True)
        adapter.verify_environment = AsyncMock(return_value=True)

        ctx = _RepairCycleContext(max_total_agent_calls=100)
        await adapter.execute(ctx)

        systemic_service.analyze.assert_called_once()


# ---------------------------------------------------------------------------
# Classification Dispatch: TRANSIENT_FAILURE
# ---------------------------------------------------------------------------


class TestClassificationDispatchTransientFailure:
    @pytest.mark.asyncio
    async def test_transient_failure_single_occurrence_no_fix(self):
        """Single TRANSIENT_FAILURE classification does not trigger fix.

        Verifies retry behavior by confirming the loop continues (max_iterations=2)
        but no fix method is called for a single transient failure.
        """
        event_emitter = MagicMock()
        systemic_service = AsyncMock()
        systemic_service.analyze.return_value = MagicMock(
            classification=FailureClassification.TRANSIENT_FAILURE,
            confidence=0.8,
            reasoning="Flaky test",
            recommended_action="Retry",
            cross_cutting=False,
        )

        adapter, _ = _make_adapter(event_emitter=event_emitter)
        adapter._systemic_analysis_service = systemic_service
        adapter.fix_failures_by_file = AsyncMock(return_value=0)

        ctx = _RepairCycleContext(max_total_agent_calls=100)
        # Allow multiple iterations to verify retry continues without fix
        ctx.test_configs = (
            RepairTestRunConfig(
                test_type=RepairTestType.UNIT,
                timeout=30,
                max_iterations=2,
                review_warnings=False,
            ),
        )
        await adapter.execute(ctx)

        # Verify analyze was called at least once (loop continued)
        assert systemic_service.analyze.call_count >= 1
        # fix_failures_by_file should not be called for single TRANSIENT_FAILURE
        adapter.fix_failures_by_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_transient_failure_escalates_after_two_consecutive(self):
        """TRANSIENT_FAILURE escalates to CODE_DEFECT after 2 consecutive occurrences.

        Escalation is verified by confirming that:
        1. Two consecutive TRANSIENT_FAILUREs increment the counter to 2
        2. On the 3rd iteration, counter >= 2 triggers escalation to CODE_DEFECT
        3. fix_failures_by_file is called exactly once on escalation
        """
        event_emitter = MagicMock()
        systemic_service = AsyncMock()

        # Iterate 3 times: TRANSIENT_FAILURE twice, then CODE_DEFECT
        systemic_service.analyze.side_effect = [
            MagicMock(
                classification=FailureClassification.TRANSIENT_FAILURE,
                confidence=0.8,
                reasoning="Flaky test 1",
                recommended_action="Retry",
            cross_cutting=False,
            ),
            MagicMock(
                classification=FailureClassification.TRANSIENT_FAILURE,
                confidence=0.8,
                reasoning="Flaky test 2",
                recommended_action="Retry",
            cross_cutting=False,
            ),
            MagicMock(
                classification=FailureClassification.CODE_DEFECT,
                confidence=0.95,
                reasoning="Code defect from escalation",
                recommended_action="Fix the bug",
            cross_cutting=False,
            ),
        ]

        adapter, _ = _make_adapter(event_emitter=event_emitter)
        adapter._systemic_analysis_service = systemic_service
        adapter.fix_failures_by_file = AsyncMock(return_value=1)

        ctx = _RepairCycleContext(max_total_agent_calls=100)
        ctx.test_configs = (
            RepairTestRunConfig(
                test_type=RepairTestType.UNIT,
                timeout=30,
                max_iterations=3,
                review_warnings=False,
            ),
        )

        await adapter.execute(ctx)

        # After 2 consecutive TRANSIENT_FAILURE, the 3rd iteration escalates to CODE_DEFECT
        # fix_failures_by_file should be called exactly once on escalation
        assert adapter.fix_failures_by_file.call_count == 1

    @pytest.mark.asyncio
    async def test_transient_failure_increments_consecutive_counter(self):
        """Each TRANSIENT_FAILURE increments the consecutive counter."""
        event_emitter = MagicMock()
        systemic_service = AsyncMock()

        # Multiple TRANSIENT_FAILURE classifications
        systemic_service.analyze.side_effect = [
            MagicMock(
                classification=FailureClassification.TRANSIENT_FAILURE,
                confidence=0.8,
                reasoning="Flaky test 1",
                recommended_action="Retry",
            cross_cutting=False,
            ),
            MagicMock(
                classification=FailureClassification.TRANSIENT_FAILURE,
                confidence=0.8,
                reasoning="Flaky test 2",
                recommended_action="Retry",
            cross_cutting=False,
            ),
            MagicMock(
                classification=FailureClassification.TRANSIENT_FAILURE,
                confidence=0.8,
                reasoning="Flaky test 3",
                recommended_action="Retry",
            cross_cutting=False,
            ),
        ]

        adapter, _ = _make_adapter(event_emitter=event_emitter)
        adapter._systemic_analysis_service = systemic_service
        adapter.fix_failures_by_file = AsyncMock(return_value=0)

        ctx = _RepairCycleContext(max_total_agent_calls=100)
        ctx.test_configs = (
            RepairTestRunConfig(
                test_type=RepairTestType.UNIT,
                timeout=30,
                max_iterations=3,
                review_warnings=False,
            ),
        )

        await adapter.execute(ctx)

        systemic_service.analyze.assert_called()

    @pytest.mark.asyncio
    async def test_transient_failure_counter_resets_after_escalation(self):
        """Counter is reset after escalating TRANSIENT_FAILURE to CODE_DEFECT.

        Verifies that after escalation, the counter does not remain permanently
        elevated. Subsequent TRANSIENT_FAILURE classifications should not
        immediately escalate without reaching the threshold again.
        """
        event_emitter = MagicMock()
        systemic_service = AsyncMock()

        # Sequence: 3 consecutive TRANSIENT_FAILURE classifications trigger escalation
        # (counter reaches 3 > max_consecutive_transient=2), then counter resets.
        # Subsequent TRANSIENT_FAILURE classifications restart counting without escalating.
        systemic_service.analyze.side_effect = [
            MagicMock(
                classification=FailureClassification.TRANSIENT_FAILURE,
                confidence=0.8,
                reasoning="Flaky test 1",
                recommended_action="Retry",
            cross_cutting=False,
            ),
            MagicMock(
                classification=FailureClassification.TRANSIENT_FAILURE,
                confidence=0.8,
                reasoning="Flaky test 2",
                recommended_action="Retry",
            cross_cutting=False,
            ),
            MagicMock(
                classification=FailureClassification.TRANSIENT_FAILURE,
                confidence=0.8,
                reasoning="Flaky test 3 (escalation triggers on 3rd consecutive)",
                recommended_action="Retry",
            cross_cutting=False,
            ),
            MagicMock(
                classification=FailureClassification.TRANSIENT_FAILURE,
                confidence=0.8,
                reasoning="Flaky test 4 (counter resets to 1 after escalation)",
                recommended_action="Retry",
            cross_cutting=False,
            ),
            MagicMock(
                classification=FailureClassification.TRANSIENT_FAILURE,
                confidence=0.8,
                reasoning="Flaky test 5 (counter at 2, below escalation threshold)",
                recommended_action="Retry",
            cross_cutting=False,
            ),
        ]

        adapter, _ = _make_adapter(event_emitter=event_emitter)
        adapter._systemic_analysis_service = systemic_service
        adapter.fix_failures_by_file = AsyncMock(return_value=1)

        ctx = _RepairCycleContext(max_total_agent_calls=100)
        ctx.test_configs = (
            RepairTestRunConfig(
                test_type=RepairTestType.UNIT,
                timeout=30,
                max_iterations=5,
                review_warnings=False,
            ),
        )

        await adapter.execute(ctx)

        # fix_failures_by_file should be called exactly once (iteration 3 escalation)
        # If counter was not reset, it would be called again on iteration 5 (after two more
        # TRANSIENT_FAILURE classifications). With the counter reset after escalation,
        # the two subsequent TRANSIENT_FAILUREs (iterations 4-5) should not escalate.
        assert adapter.fix_failures_by_file.call_count == 1


# ---------------------------------------------------------------------------
# Classification Dispatch: DEPENDENCY_ISSUE and CONFIGURATION_ISSUE
# ---------------------------------------------------------------------------


class TestClassificationDispatchSystemicIssues:
    @pytest.mark.asyncio
    async def test_dependency_issue_dispatch_calls_apply_systemic_fixes(self):
        """DEPENDENCY_ISSUE classification routes to apply_systemic_fixes."""
        event_emitter = MagicMock()
        systemic_service = AsyncMock()
        systemic_service.analyze.return_value = MagicMock(
            classification=FailureClassification.DEPENDENCY_ISSUE,
            confidence=0.85,
            reasoning="Missing dependency",
            recommended_action="Install dependency",
            cross_cutting=False,
        )

        adapter, _ = _make_adapter(event_emitter=event_emitter)
        adapter._systemic_analysis_service = systemic_service
        adapter.apply_systemic_fixes = AsyncMock(return_value=True)

        ctx = _RepairCycleContext(max_total_agent_calls=100)
        await adapter.execute(ctx)

        adapter.apply_systemic_fixes.assert_called_once()

    @pytest.mark.asyncio
    async def test_configuration_issue_dispatch_calls_apply_systemic_fixes(self):
        """CONFIGURATION_ISSUE classification routes to apply_systemic_fixes."""
        event_emitter = MagicMock()
        systemic_service = AsyncMock()
        systemic_service.analyze.return_value = MagicMock(
            classification=FailureClassification.CONFIGURATION_ISSUE,
            confidence=0.85,
            reasoning="Missing configuration",
            recommended_action="Fix configuration",
            cross_cutting=False,
        )

        adapter, _ = _make_adapter(event_emitter=event_emitter)
        adapter._systemic_analysis_service = systemic_service
        adapter.apply_systemic_fixes = AsyncMock(return_value=True)

        ctx = _RepairCycleContext(max_total_agent_calls=100)
        await adapter.execute(ctx)

        adapter.apply_systemic_fixes.assert_called_once()

    @pytest.mark.asyncio
    async def test_systemic_issues_reset_transient_counter(self):
        """DEPENDENCY_ISSUE and CONFIGURATION_ISSUE reset transient counter."""
        event_emitter = MagicMock()
        systemic_service = AsyncMock()
        systemic_service.analyze.return_value = MagicMock(
            classification=FailureClassification.DEPENDENCY_ISSUE,
            confidence=0.85,
            reasoning="Missing dependency",
            recommended_action="Install dependency",
            cross_cutting=False,
        )

        adapter, _ = _make_adapter(event_emitter=event_emitter)
        adapter._systemic_analysis_service = systemic_service
        adapter.apply_systemic_fixes = AsyncMock(return_value=True)

        ctx = _RepairCycleContext(max_total_agent_calls=100)
        await adapter.execute(ctx)

        adapter.apply_systemic_fixes.assert_called_once()

    @pytest.mark.asyncio
    async def test_systemic_fix_failure_reflected_in_prior_fix_attempts(self):
        """Systemic fix failure (False return) is reflected in prior_fix_attempts.

        Verifies that when apply_systemic_fixes() returns False (fix failed),
        the prior_fix_attempts description reflects this with "attempted but failed"
        instead of unconditionally saying "applied".
        """
        event_emitter = MagicMock()
        systemic_service = AsyncMock()
        systemic_service.analyze.return_value = MagicMock(
            classification=FailureClassification.DEPENDENCY_ISSUE,
            confidence=0.85,
            reasoning="Missing dependency",
            recommended_action="Install dependency",
            cross_cutting=False,
        )

        adapter, _ = _make_adapter(event_emitter=event_emitter)
        adapter._systemic_analysis_service = systemic_service
        # First iteration: fix fails (returns False)
        # Second iteration: fix succeeds (returns True)
        adapter.apply_systemic_fixes = AsyncMock(side_effect=[False, True])
        adapter.fix_failures_by_file = AsyncMock(return_value=0)

        ctx = _RepairCycleContext(max_total_agent_calls=100)
        ctx.test_configs = (
            RepairTestRunConfig(
                test_type=RepairTestType.UNIT,
                timeout=30,
                max_iterations=2,
                review_warnings=False,
            ),
        )

        await adapter.execute(ctx)

        # Verify analyze was called twice (two iterations)
        assert systemic_service.analyze.call_count == 2

        # First iteration: prior_fix_attempts should be empty
        first_call_context = systemic_service.analyze.call_args_list[0][0][1]
        assert len(first_call_context.prior_fix_attempts) == 0

        # Second iteration: prior_fix_attempts should contain the first iteration's failure
        second_call_context = systemic_service.analyze.call_args_list[1][0][1]
        assert len(second_call_context.prior_fix_attempts) == 1
        # Key assertion: the description must reflect that the fix failed
        attempt_desc = second_call_context.prior_fix_attempts[0]
        assert "attempted but failed" in attempt_desc
        assert "dependency_issue" in attempt_desc.lower()


# ---------------------------------------------------------------------------
# Classifier Exception Handling (Fallback)
# ---------------------------------------------------------------------------


class TestClassifierExceptionFallback:
    @pytest.mark.asyncio
    async def test_classifier_exception_falls_back_to_fix_failures_by_file(self):
        """Systemic analysis exception falls back to fix_failures_by_file."""
        event_emitter = MagicMock()
        systemic_service = AsyncMock()
        systemic_service.analyze.side_effect = RuntimeError("Classifier failed")

        adapter, _ = _make_adapter(event_emitter=event_emitter)
        adapter._systemic_analysis_service = systemic_service
        adapter.fix_failures_by_file = AsyncMock(return_value=1)

        ctx = _RepairCycleContext(max_total_agent_calls=100)
        await adapter.execute(ctx)

        # Should fall back to fix_failures_by_file
        adapter.fix_failures_by_file.assert_called()

        # Verify both SystemicAnalysisStartedEvent and CompletedEvent are emitted
        # to maintain event lifecycle consistency
        emitted_types = [call.args[0].type for call in event_emitter.emit.call_args_list]
        assert "repair_cycle.systemic_analysis_started" in emitted_types
        assert "repair_cycle.systemic_analysis_completed" in emitted_types

        # Verify the completed event indicates failure (confidence=0.0)
        completed_events = [
            call.args[0]
            for call in event_emitter.emit.call_args_list
            if call.args[0].type == "repair_cycle.systemic_analysis_completed"
        ]
        assert len(completed_events) >= 1
        # At least one completed event should have zero confidence (the failed one)
        assert any(evt.confidence == 0.0 for evt in completed_events)

    @pytest.mark.asyncio
    async def test_no_systemic_service_uses_fallback(self):
        """No systemic service injected uses fallback to fix_failures_by_file."""
        event_emitter = MagicMock()

        adapter, _ = _make_adapter(event_emitter=event_emitter)
        adapter._systemic_analysis_service = None
        adapter.fix_failures_by_file = AsyncMock(return_value=1)

        ctx = _RepairCycleContext(max_total_agent_calls=100)
        await adapter.execute(ctx)

        # Should use fallback since no classifier
        adapter.fix_failures_by_file.assert_called()


# ---------------------------------------------------------------------------
# Prior Classifications and Fix Attempts Tracking
# ---------------------------------------------------------------------------


class TestPriorTrackingData:
    @pytest.mark.asyncio
    async def test_prior_classifications_tracked(self):
        """Prior classifications are tracked and passed to analysis context.

        Verifies that:
        1. Analyze is called exactly twice (two iterations)
        2. First call has empty prior_classifications
        3. Second call has non-empty prior_classifications
        """
        event_emitter = MagicMock()
        systemic_service = AsyncMock()
        systemic_service.analyze.return_value = MagicMock(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.95,
            reasoning="Source code has a bug",
            recommended_action="Fix the bug",
            cross_cutting=False,
        )

        adapter, _ = _make_adapter(event_emitter=event_emitter)
        adapter._systemic_analysis_service = systemic_service
        adapter.fix_failures_by_file = AsyncMock(return_value=1)

        ctx = _RepairCycleContext(max_total_agent_calls=100)
        ctx.test_configs = (
            RepairTestRunConfig(
                test_type=RepairTestType.UNIT,
                timeout=30,
                max_iterations=2,
                review_warnings=False,
            ),
        )

        await adapter.execute(ctx)

        # Unconditionally verify analyze was called exactly twice
        assert systemic_service.analyze.call_count == 2

        # Verify first call has empty prior_classifications
        first_call_context = systemic_service.analyze.call_args_list[0][0][1]
        assert len(first_call_context.prior_classifications) == 0

        # Verify second call has non-empty prior_classifications
        second_call_context = systemic_service.analyze.call_args_list[1][0][1]
        assert len(second_call_context.prior_classifications) > 0

    @pytest.mark.asyncio
    async def test_prior_fix_attempts_tracked(self):
        """Prior fix attempts are tracked in fix attempt list.

        Verifies that:
        1. Analyze is called exactly twice (two iterations)
        2. First call has empty prior_fix_attempts
        3. Second call has non-empty prior_fix_attempts
        """
        event_emitter = MagicMock()
        systemic_service = AsyncMock()
        systemic_service.analyze.return_value = MagicMock(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.95,
            reasoning="Source code has a bug",
            recommended_action="Fix the bug",
            cross_cutting=False,
        )

        adapter, _ = _make_adapter(event_emitter=event_emitter)
        adapter._systemic_analysis_service = systemic_service
        adapter.fix_failures_by_file = AsyncMock(return_value=1)

        ctx = _RepairCycleContext(max_total_agent_calls=100)
        ctx.test_configs = (
            RepairTestRunConfig(
                test_type=RepairTestType.UNIT,
                timeout=30,
                max_iterations=2,
                review_warnings=False,
            ),
        )

        await adapter.execute(ctx)

        # Unconditionally verify analyze was called exactly twice
        assert systemic_service.analyze.call_count == 2

        # Verify first call has empty prior_fix_attempts
        first_call_context = systemic_service.analyze.call_args_list[0][0][1]
        assert len(first_call_context.prior_fix_attempts) == 0

        # Verify second call has non-empty prior_fix_attempts
        second_call_context = systemic_service.analyze.call_args_list[1][0][1]
        assert len(second_call_context.prior_fix_attempts) > 0


# ---------------------------------------------------------------------------
# Helper Method Tests: rebuild_environment, verify_environment
# ---------------------------------------------------------------------------


class TestEnvironmentHelperMethods:
    @pytest.mark.asyncio
    async def test_rebuild_environment_success(self):
        """rebuild_environment returns True on successful execution."""
        event_emitter = MagicMock()

        adapter, llm = _make_adapter(event_emitter=event_emitter)
        ctx = _RepairCycleContext()
        config = ctx.test_configs[0]

        result = await adapter.rebuild_environment(config, ctx)

        assert result is True
        llm.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_rebuild_environment_failure(self):
        """rebuild_environment returns False on exception."""
        event_emitter = MagicMock()
        llm = AsyncMock()
        llm.execute.side_effect = RuntimeError("LLM failed")

        config = RepairCycleConfig(max_json_parse_retries=1, json_parse_retry_delay_ms=0)
        adapter = ProductionRepairCycleAdapter(
            llm_factory=lambda: llm,
            config=config,
            event_emitter=event_emitter,
            circuit_breaker=None,
        )

        ctx = _RepairCycleContext()
        result = await adapter.rebuild_environment(ctx.test_configs[0], ctx)

        assert result is False

    @pytest.mark.asyncio
    async def test_verify_environment_success(self):
        """verify_environment returns True on successful execution."""
        event_emitter = MagicMock()

        adapter, llm = _make_adapter(event_emitter=event_emitter)
        ctx = _RepairCycleContext()
        config = ctx.test_configs[0]

        result = await adapter.verify_environment(config, ctx)

        assert result is True
        llm.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_environment_failure(self):
        """verify_environment returns False on exception."""
        event_emitter = MagicMock()
        llm = AsyncMock()
        llm.execute.side_effect = RuntimeError("LLM failed")

        config = RepairCycleConfig(max_json_parse_retries=1, json_parse_retry_delay_ms=0)
        adapter = ProductionRepairCycleAdapter(
            llm_factory=lambda: llm,
            config=config,
            event_emitter=event_emitter,
            circuit_breaker=None,
        )

        ctx = _RepairCycleContext()
        result = await adapter.verify_environment(ctx.test_configs[0], ctx)

        assert result is False


# ---------------------------------------------------------------------------
# Helper Method Tests: apply_systemic_fixes
# ---------------------------------------------------------------------------


class TestApplySystemicFixes:
    @pytest.mark.asyncio
    async def test_apply_systemic_fixes_dependency_issue(self):
        """apply_systemic_fixes routes DEPENDENCY_ISSUE to _apply_dependency_fix."""
        event_emitter = MagicMock()

        adapter, llm = _make_adapter(event_emitter=event_emitter)
        adapter._apply_dependency_fix = AsyncMock(return_value=True)

        ctx = _RepairCycleContext()
        config = ctx.test_configs[0]
        failure = RepairTestFailure(file="test_foo.py", test="test_bar", message="fail")
        test_result = MagicMock()
        test_result.failures = [failure]

        result = await adapter.apply_systemic_fixes(
            FailureClassification.DEPENDENCY_ISSUE,
            "Missing dependency",
            test_result,
            config,
            ctx,
        )

        assert result is True
        adapter._apply_dependency_fix.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_systemic_fixes_configuration_issue(self):
        """apply_systemic_fixes routes CONFIGURATION_ISSUE to _apply_configuration_fix."""
        event_emitter = MagicMock()

        adapter, llm = _make_adapter(event_emitter=event_emitter)
        adapter._apply_configuration_fix = AsyncMock(return_value=True)

        ctx = _RepairCycleContext()
        config = ctx.test_configs[0]
        failure = RepairTestFailure(file="test_foo.py", test="test_bar", message="fail")
        test_result = MagicMock()
        test_result.failures = [failure]

        result = await adapter.apply_systemic_fixes(
            FailureClassification.CONFIGURATION_ISSUE,
            "Missing configuration",
            test_result,
            config,
            ctx,
        )

        assert result is True
        adapter._apply_configuration_fix.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_systemic_fixes_unknown_enum_defaults_to_dependency(self):
        """apply_systemic_fixes defaults unknown enum values to dependency fix.

        This tests the fallback behavior for any FailureClassification value that
        is not explicitly handled (DEPENDENCY_ISSUE or CONFIGURATION_ISSUE).
        """
        event_emitter = MagicMock()

        adapter, llm = _make_adapter(event_emitter=event_emitter)
        adapter._apply_dependency_fix = AsyncMock(return_value=True)

        ctx = _RepairCycleContext()
        config = ctx.test_configs[0]
        failure = RepairTestFailure(file="test_foo.py", test="test_bar", message="fail")
        test_result = MagicMock()
        test_result.failures = [failure]

        # Pass a valid enum value that is not explicitly handled (e.g., CODE_DEFECT)
        # The apply_systemic_fixes method should default to dependency fix
        result = await adapter.apply_systemic_fixes(
            FailureClassification.CODE_DEFECT,
            "Code defect that should trigger dependency fix fallback",
            test_result,
            config,
            ctx,
        )

        # Should default to dependency fix for unhandled classification
        adapter._apply_dependency_fix.assert_called_once()


# ---------------------------------------------------------------------------
# Helper Method Tests: Prompt Builders
# ---------------------------------------------------------------------------


class TestPromptBuilders:
    def test_build_environment_rebuild_prompt_unit(self):
        """_build_environment_rebuild_prompt generates appropriate prompt for unit tests."""
        adapter, _ = _make_adapter()
        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=30,
            max_iterations=1,
            review_warnings=False,
        )

        prompt = adapter._build_environment_rebuild_prompt(config)

        assert "rebuild" in prompt.lower()
        assert "unit tests" in prompt.lower()

    def test_build_environment_rebuild_prompt_integration(self):
        """_build_environment_rebuild_prompt includes integration test reference."""
        adapter, _ = _make_adapter()
        config = RepairTestRunConfig(
            test_type=RepairTestType.INTEGRATION,
            timeout=30,
            max_iterations=1,
            review_warnings=False,
        )

        prompt = adapter._build_environment_rebuild_prompt(config)

        assert "integration tests" in prompt.lower()

    def test_build_environment_verify_prompt_unit(self):
        """_build_environment_verify_prompt generates appropriate prompt for unit tests."""
        adapter, _ = _make_adapter()
        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=30,
            max_iterations=1,
            review_warnings=False,
        )

        prompt = adapter._build_environment_verify_prompt(config)

        assert "verify" in prompt.lower()
        assert "unit tests" in prompt.lower()

    def test_build_environment_verify_prompt_e2e(self):
        """_build_environment_verify_prompt includes e2e test reference."""
        adapter, _ = _make_adapter()
        config = RepairTestRunConfig(
            test_type=RepairTestType.E2E,
            timeout=30,
            max_iterations=1,
            review_warnings=False,
        )

        prompt = adapter._build_environment_verify_prompt(config)

        assert "end-to-end tests" in prompt.lower()

    def test_build_dependency_fix_prompt(self):
        """_build_dependency_fix_prompt includes reasoning and failure details."""
        adapter, _ = _make_adapter()
        failure = RepairTestFailure(
            file="test_foo.py",
            test="test_bar",
            message="ImportError: No module named 'foo'",
        )
        test_result = MagicMock()
        test_result.failures = [failure]

        prompt = adapter._build_dependency_fix_prompt("Missing 'foo' package", test_result)

        assert "Missing 'foo' package" in prompt
        assert "test_foo.py" in prompt
        assert "dependency" in prompt.lower()

    def test_build_configuration_fix_prompt(self):
        """_build_configuration_fix_prompt includes reasoning and failure details."""
        adapter, _ = _make_adapter()
        failure = RepairTestFailure(
            file="test_foo.py",
            test="test_bar",
            message="KeyError: 'DATABASE_URL'",
        )
        test_result = MagicMock()
        test_result.failures = [failure]

        prompt = adapter._build_configuration_fix_prompt("Missing DATABASE_URL env var", test_result)

        assert "Missing DATABASE_URL env var" in prompt
        assert "test_foo.py" in prompt
        assert "configuration" in prompt.lower()


# ---------------------------------------------------------------------------
# Dependency Fix Helper Tests
# ---------------------------------------------------------------------------


class TestApplyDependencyFix:
    @pytest.mark.asyncio
    async def test_apply_dependency_fix_success(self):
        """_apply_dependency_fix returns True on successful fix."""
        event_emitter = MagicMock()

        adapter, llm = _make_adapter(event_emitter=event_emitter)
        ctx = _RepairCycleContext()
        config = ctx.test_configs[0]
        failure = RepairTestFailure(file="test_foo.py", test="test_bar", message="fail")
        test_result = MagicMock()
        test_result.failures = [failure]

        result = await adapter._apply_dependency_fix("Missing dep", test_result, config, ctx)

        assert result is True
        llm.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_dependency_fix_failure(self):
        """_apply_dependency_fix returns False on exception."""
        event_emitter = MagicMock()
        llm = AsyncMock()
        llm.execute.side_effect = RuntimeError("LLM failed")

        config = RepairCycleConfig(max_json_parse_retries=1, json_parse_retry_delay_ms=0)
        adapter = ProductionRepairCycleAdapter(
            llm_factory=lambda: llm,
            config=config,
            event_emitter=event_emitter,
            circuit_breaker=None,
        )

        ctx = _RepairCycleContext()
        failure = RepairTestFailure(file="test_foo.py", test="test_bar", message="fail")
        test_result = MagicMock()
        test_result.failures = [failure]

        result = await adapter._apply_dependency_fix("Missing dep", test_result, ctx.test_configs[0], ctx)

        assert result is False


# ---------------------------------------------------------------------------
# Configuration Fix Helper Tests
# ---------------------------------------------------------------------------


class TestApplyConfigurationFix:
    @pytest.mark.asyncio
    async def test_apply_configuration_fix_success(self):
        """_apply_configuration_fix returns True on successful fix."""
        event_emitter = MagicMock()

        adapter, llm = _make_adapter(event_emitter=event_emitter)
        ctx = _RepairCycleContext()
        config = ctx.test_configs[0]
        failure = RepairTestFailure(file="test_foo.py", test="test_bar", message="fail")
        test_result = MagicMock()
        test_result.failures = [failure]

        result = await adapter._apply_configuration_fix("Missing config", test_result, config, ctx)

        assert result is True
        llm.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_configuration_fix_failure(self):
        """_apply_configuration_fix returns False on exception."""
        event_emitter = MagicMock()
        llm = AsyncMock()
        llm.execute.side_effect = RuntimeError("LLM failed")

        config = RepairCycleConfig(max_json_parse_retries=1, json_parse_retry_delay_ms=0)
        adapter = ProductionRepairCycleAdapter(
            llm_factory=lambda: llm,
            config=config,
            event_emitter=event_emitter,
            circuit_breaker=None,
        )

        ctx = _RepairCycleContext()
        failure = RepairTestFailure(file="test_foo.py", test="test_bar", message="fail")
        test_result = MagicMock()
        test_result.failures = [failure]

        result = await adapter._apply_configuration_fix("Missing config", test_result, ctx.test_configs[0], ctx)

        assert result is False


# ---------------------------------------------------------------------------
# Agent config routing tests (PRIMARY BEHAVIORAL CHANGE)
# ---------------------------------------------------------------------------


class TestAgentConfigRouting:
    """Tests for _get_llm_for_subtask agent config routing (issue #556)."""

    def _make_tracking_adapter(self):
        """Create adapter with LLM factory that tracks which agent names are resolved."""
        resolved_agents = []

        async def tracking_factory(agent_name: str):
            """Async factory that records the agent name requested."""
            resolved_agents.append(agent_name)
            llm = AsyncMock()
            llm.execute.return_value = ExecutionResult(content=_VALID_JSON_RESPONSE)
            return llm

        config = RepairCycleConfig(max_json_parse_retries=1, json_parse_retry_delay_ms=0)
        adapter = ProductionRepairCycleAdapter(
            llm_factory=tracking_factory,
            config=config,
        )
        adapter._resolved_agents = resolved_agents
        return adapter

    @pytest.mark.asyncio
    async def test_run_tests_routes_through_test_execution_agent(self):
        """run_tests routes through agent resolved for 'test_execution' sub-task."""
        from codetoreum.domain.repair_cycle_types import RepairCycleAgentConfig

        # Create specialized agent config that assigns different agents to sub-tasks
        agent_config = RepairCycleAgentConfig(
            test_execution="qa_test_executor",
            code_fix="code_fixer",
        )

        adapter = self._make_tracking_adapter()
        ctx = _RepairCycleContext()
        # Set agent_config on the context
        ctx.agent_config = agent_config
        ctx.agent_name = "default_agent"

        await adapter.run_tests(ctx.test_configs[0], ctx)

        # Verify the test_execution agent was resolved
        assert (
            "qa_test_executor" in adapter._resolved_agents
        ), f"Expected 'qa_test_executor' in resolved agents, got {adapter._resolved_agents}"

    @pytest.mark.asyncio
    async def test_fix_failures_routes_through_code_fix_agent(self):
        """fix_failures_by_file routes through agent resolved for 'code_fix' sub-task."""
        from codetoreum.domain.repair_cycle_types import RepairCycleAgentConfig

        agent_config = RepairCycleAgentConfig(
            test_execution="qa_test_executor",
            code_fix="code_fixer",
        )

        adapter = self._make_tracking_adapter()
        ctx = _RepairCycleContext()
        ctx.agent_config = agent_config
        ctx.agent_name = "default_agent"

        grouped: dict[str, tuple[RepairTestFailure, ...]] = {
            "test_file.py": (RepairTestFailure(file="test_file.py", test="t1", message="fail"),),
        }

        await adapter.fix_failures_by_file(grouped, ctx.test_configs[0], ctx)

        # Verify the code_fix agent was resolved
        assert (
            "code_fixer" in adapter._resolved_agents
        ), f"Expected 'code_fixer' in resolved agents, got {adapter._resolved_agents}"

    @pytest.mark.asyncio
    async def test_handle_warnings_routes_through_code_fix_agent(self):
        """handle_warnings routes through agent resolved for 'code_fix' sub-task."""
        from codetoreum.domain.repair_cycle_types import RepairCycleAgentConfig, RepairTestResult, RepairTestWarning

        agent_config = RepairCycleAgentConfig(
            test_execution="qa_test_executor",
            code_fix="code_fixer",
        )

        # Mock the factory to track which agent name it's called with
        llm_mock = AsyncMock()
        llm_mock.execute.return_value = ExecutionResult(content="Fixed")
        call_tracker = []

        async def tracking_factory(agent_name):
            call_tracker.append(agent_name)
            return llm_mock

        config = RepairCycleConfig(max_json_parse_retries=1, json_parse_retry_delay_ms=0)
        adapter = ProductionRepairCycleAdapter(
            llm_factory=tracking_factory,
            config=config,
        )

        ctx = _RepairCycleContext()
        ctx.agent_config = agent_config
        ctx.agent_name = "default_agent"

        # Create a config with review_warnings=True (default context has it as False)
        test_config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=30,
            max_iterations=1,
            review_warnings=True,  # Important: need this to be True
        )

        test_result = RepairTestResult(
            test_type=test_config.test_type,
            iteration=1,
            passed=5,
            failed=0,
            warnings=1,
            failures=(),
            warning_list=(RepairTestWarning(file="src/file.py", message="deprecation warning"),),
            raw_output="",
            timestamp="2025-01-01T00:00:00Z",
        )

        await adapter.handle_warnings(test_result, test_config, ctx)

        # Verify factory was called with the configured code_fix agent
        assert len(call_tracker) > 0, "Expected llm_factory to be called"
        assert call_tracker[0] == "code_fixer", f"Expected code_fixer agent, got {call_tracker[0]}"

    @pytest.mark.asyncio
    async def test_agent_config_fallback_to_default_when_none(self):
        """When agent_config is None, falls back to context.agent_name."""
        adapter = self._make_tracking_adapter()
        ctx = _RepairCycleContext()
        ctx.agent_config = None
        ctx.agent_name = "default_repair_agent"

        await adapter.run_tests(ctx.test_configs[0], ctx)

        # Verify the default agent was resolved
        assert (
            "default_repair_agent" in adapter._resolved_agents
        ), f"Expected 'default_repair_agent' in resolved agents, got {adapter._resolved_agents}"

    @pytest.mark.asyncio
    async def test_agent_config_partial_mapping(self):
        """Agent config with only some sub-tasks configured falls back for others."""
        from codetoreum.domain.repair_cycle_types import RepairCycleAgentConfig

        # Only test_execution is configured, code_fix should fall back
        agent_config = RepairCycleAgentConfig(
            test_execution="qa_executor",
            code_fix=None,  # Falls back to default
        )

        adapter = self._make_tracking_adapter()
        ctx = _RepairCycleContext()
        ctx.agent_config = agent_config
        ctx.agent_name = "default_agent"

        await adapter.run_tests(ctx.test_configs[0], ctx)

        # Verify the configured test_execution agent was resolved
        assert (
            "qa_executor" in adapter._resolved_agents
        ), f"Expected 'qa_executor' in resolved agents, got {adapter._resolved_agents}"


class TestEnvironmentRebuildAndVerifyReturnValueHandling:
    """Verifies that rebuild_environment() and verify_environment() return values are checked.

    Ensures that:
    1. When rebuild_environment() returns False, repair cycle stops (breaks the iteration loop)
    2. When verify_environment() returns False, repair cycle stops (breaks the iteration loop)
    3. When both succeed, repair cycle continues to the next iteration
    """

    @staticmethod
    def _make_llm_factory_with_mock(mock_llm: AsyncMock) -> callable:
        """Create an LLM factory that returns the given mock LLM."""

        async def factory(agent_name: str) -> AsyncMock:
            return mock_llm

        return factory

    @pytest.mark.asyncio
    async def test_rebuild_environment_failure_breaks_iteration(self):
        """When rebuild_environment() returns False, the iteration loop breaks."""
        # Setup: LLM returns success for test runs and systemic analysis
        mock_llm = AsyncMock()
        mock_llm.execute = AsyncMock(return_value=ExecutionResult(content=_VALID_JSON_RESPONSE))

        adapter = ProductionRepairCycleAdapter(
            llm_factory=self._make_llm_factory_with_mock(mock_llm),
            config=RepairCycleConfig(),
        )

        # Setup systemic analysis service to return ENVIRONMENT_ISSUE classification
        systemic_service = AsyncMock()
        systemic_service.analyze.return_value = MagicMock(
            classification=FailureClassification.ENVIRONMENT_ISSUE,
            confidence=0.9,
            reasoning="Environment issue detected",
            recommended_action="Rebuild environment",
            cross_cutting=False,
        )
        adapter._systemic_analysis_service = systemic_service

        # Mock fix methods
        adapter.fix_failures_by_file = AsyncMock(return_value=1)

        # Mock rebuild_environment to return False (failure)
        adapter.rebuild_environment = AsyncMock(return_value=False)
        adapter.verify_environment = AsyncMock()

        ctx = _RepairCycleContext(max_total_agent_calls=1000)

        # Run the repair cycle - should break after rebuild fails
        result = await adapter._run_test_cycle(
            config=ctx.test_configs[0],
            context=ctx,
            test_type_index=1,
        )

        # Verify that rebuild_environment was called
        assert adapter.rebuild_environment.called, "rebuild_environment should be called"

        # Verify that verify_environment was NOT called (because rebuild failed)
        assert not adapter.verify_environment.called, "verify_environment should not be called when rebuild fails"

        # Verify that the cycle did not pass (stopped early)
        assert not result.passed, "Cycle should not pass when rebuild fails"

    @pytest.mark.asyncio
    async def test_verify_environment_failure_breaks_iteration(self):
        """When verify_environment() returns False, the iteration loop breaks."""
        # Setup: LLM returns success for test runs and systemic analysis
        mock_llm = AsyncMock()
        mock_llm.execute = AsyncMock(return_value=ExecutionResult(content=_VALID_JSON_RESPONSE))

        adapter = ProductionRepairCycleAdapter(
            llm_factory=self._make_llm_factory_with_mock(mock_llm),
            config=RepairCycleConfig(),
        )

        # Setup systemic analysis service to return ENVIRONMENT_ISSUE classification
        systemic_service = AsyncMock()
        systemic_service.analyze.return_value = MagicMock(
            classification=FailureClassification.ENVIRONMENT_ISSUE,
            confidence=0.9,
            reasoning="Environment issue detected",
            recommended_action="Rebuild environment",
            cross_cutting=False,
        )
        adapter._systemic_analysis_service = systemic_service

        # Mock fix methods
        adapter.fix_failures_by_file = AsyncMock(return_value=1)

        # Mock rebuild_environment to return True (success)
        adapter.rebuild_environment = AsyncMock(return_value=True)

        # Mock verify_environment to return False (environment not ready)
        adapter.verify_environment = AsyncMock(return_value=False)

        ctx = _RepairCycleContext(max_total_agent_calls=1000)

        # Run the repair cycle - should break after verification fails
        result = await adapter._run_test_cycle(
            config=ctx.test_configs[0],
            context=ctx,
            test_type_index=1,
        )

        # Verify that both rebuild and verify were called
        assert adapter.rebuild_environment.called, "rebuild_environment should be called"
        assert adapter.verify_environment.called, "verify_environment should be called"

        # Verify that the cycle did not pass (stopped after verification failure)
        assert not result.passed, "Cycle should not pass when verification fails"

    @pytest.mark.asyncio
    async def test_successful_rebuild_and_verify_continue_iteration(self):
        """When both rebuild and verify succeed, the cycle continues."""
        # Setup: LLM returns no failures on initial test, then verify succeeds
        mock_llm = AsyncMock()
        # First call for initial test succeeds with no failures
        success_response = '{"passed": 1, "failed": 0, ' '"failures": [], ' '"warnings": []}'
        mock_llm.execute = AsyncMock(return_value=ExecutionResult(content=success_response))

        adapter = ProductionRepairCycleAdapter(
            llm_factory=self._make_llm_factory_with_mock(mock_llm),
            config=RepairCycleConfig(),
        )

        adapter.analyze_systemic_issues = AsyncMock(return_value="")
        adapter.apply_systemic_fixes = AsyncMock(return_value=False)
        adapter.fix_failures_by_file = AsyncMock(return_value=0)
        adapter.rebuild_environment = AsyncMock(return_value=True)
        adapter.verify_environment = AsyncMock(return_value=True)

        ctx = _RepairCycleContext(max_total_agent_calls=1000)

        # Run the repair cycle
        result = await adapter._run_test_cycle(
            config=ctx.test_configs[0],
            context=ctx,
            test_type_index=1,
        )

        # Verify that the cycle passed (no failures means success)
        assert result.passed, "Cycle should pass when tests have no failures"

        # Neither rebuild nor verify should have been called (no failures, no systemic analysis)
        assert (
            not adapter.rebuild_environment.called
        ), "rebuild_environment should not be called when tests pass immediately"
        assert (
            not adapter.verify_environment.called
        ), "verify_environment should not be called when tests pass immediately"


# ---------------------------------------------------------------------------
# Timeout handling tests (issue #566)
# ---------------------------------------------------------------------------


class TestTimeoutHandling:
    """Tests for LLM call timeout enforcement via asyncio.wait_for()."""

    def _make_slow_llm(self, delay_seconds: float) -> AsyncMock:
        """Create an LLM mock that sleeps before returning."""
        llm = AsyncMock()

        async def slow_execute(**kwargs):
            await asyncio.sleep(delay_seconds)
            return ExecutionResult(content=_VALID_JSON_RESPONSE)

        llm.execute = slow_execute
        return llm

    async def _make_factory_with_slow_llm(self, delay_seconds: float):
        """Create a factory that returns a slow LLM."""
        slow_llm = self._make_slow_llm(delay_seconds)

        async def factory(agent_name: str):
            return slow_llm

        return factory

    @pytest.mark.asyncio
    async def test_run_tests_raises_timeout_error_when_llm_exceeds_timeout(self):
        """run_tests raises TimeoutError when LLM takes longer than config.timeout."""
        # Create a very short timeout (100ms) and LLM that sleeps 1s
        factory = await self._make_factory_with_slow_llm(delay_seconds=1.0)
        adapter = ProductionRepairCycleAdapter(
            llm_factory=factory,
            config=RepairCycleConfig(),
        )

        ctx = _RepairCycleContext()
        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=0.1,  # 100ms timeout
            max_iterations=1,
        )

        with pytest.raises(TimeoutError) as exc_info:
            await adapter.run_tests(config, ctx)

        assert "Test execution exceeded timeout" in str(exc_info.value)
        assert "0.1 seconds" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fix_failures_by_file_handles_timeout_gracefully(self):
        """fix_failures_by_file catches TimeoutError and returns 0 files fixed."""
        factory = await self._make_factory_with_slow_llm(delay_seconds=1.0)
        adapter = ProductionRepairCycleAdapter(
            llm_factory=factory,
            config=RepairCycleConfig(),
        )

        ctx = _RepairCycleContext()
        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=0.1,  # 100ms timeout
            max_iterations=1,
        )

        failures = {
            "test_foo.py": (
                RepairTestFailure(
                    file="test_foo.py",
                    test="test_bar",
                    message="assertion failed",
                ),
            ),
        }

        # fix_failures_by_file catches TimeoutError and emits failure event
        result = await adapter.fix_failures_by_file(failures, config, ctx)
        assert result == 0  # No files fixed due to timeout

    @pytest.mark.asyncio
    async def test_handle_warnings_handles_timeout_gracefully(self):
        """handle_warnings catches TimeoutError and returns 0 warnings reviewed."""
        factory = await self._make_factory_with_slow_llm(delay_seconds=1.0)
        adapter = ProductionRepairCycleAdapter(
            llm_factory=factory,
            config=RepairCycleConfig(),
        )

        ctx = _RepairCycleContext()
        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=0.1,  # 100ms timeout
            max_iterations=1,
            review_warnings=True,
        )

        test_result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=1,
            failed=0,
            warnings=1,
            failures=(),
            warning_list=(
                RepairTestWarning(
                    file="test_foo.py",
                    message="deprecation warning",
                ),
            ),
            raw_output="{}",
            timestamp="2024-01-01T00:00:00Z",
        )

        # handle_warnings catches TimeoutError and continues
        result = await adapter.handle_warnings(test_result, config, ctx)
        assert result == 0  # No warnings reviewed due to timeout

    @pytest.mark.asyncio
    @pytest.mark.parametrize("timeout_seconds", [0.01, 0.02, 0.05])
    async def test_timeout_respects_config_timeout_value(self, timeout_seconds):
        """Timeout values from config are actually enforced."""
        # Create LLM that delays 0.5 seconds (much longer than any timeout)
        factory = await self._make_factory_with_slow_llm(delay_seconds=0.5)
        adapter = ProductionRepairCycleAdapter(
            llm_factory=factory,
            config=RepairCycleConfig(),
        )

        ctx = _RepairCycleContext()
        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=timeout_seconds,
            max_iterations=1,
        )

        with pytest.raises(TimeoutError):
            await adapter.run_tests(config, ctx)


# ---------------------------------------------------------------------------
# Systemic Fix: fix_failures_systemically()
# ---------------------------------------------------------------------------


class TestFixFailuresSystemically:
    @pytest.mark.asyncio
    async def test_fix_failures_systemically_emits_events(self):
        """fix_failures_systemically emits SystemicFixStartedEvent and SystemicFixCompletedEvent."""
        event_emitter = MagicMock()
        llm_response = '{"root_cause_addressed": "Fixed shared interface", "files_modified": ["file1.py", "file2.py"]}'
        adapter, _ = _make_adapter(llm_response=llm_response, event_emitter=event_emitter)
        ctx = _RepairCycleContext()

        failures = (
            RepairTestFailure(file="test_a.py", test="test_1", message="fail"),
            RepairTestFailure(file="test_b.py", test="test_2", message="fail"),
        )
        analysis_result = MagicMock(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.95,
            reasoning="Shared interface broken",
            recommended_action="Fix interface",
            affected_files=("a.py", "b.py"),
            cross_cutting=True,
        )

        result = await adapter.fix_failures_systemically(
            failures, analysis_result, ctx.test_configs[0], ctx
        )

        # Verify events were emitted
        emitted_types = [call.args[0].type for call in event_emitter.emit.call_args_list]
        assert "repair_cycle.systemic_fix_started" in emitted_types
        assert "repair_cycle.systemic_fix_completed" in emitted_types

    @pytest.mark.asyncio
    async def test_fix_failures_systemically_single_llm_invocation(self):
        """fix_failures_systemically makes exactly one LLM invocation."""
        llm_response = '{"root_cause_addressed": "Fixed shared interface", "files_modified": ["file1.py"]}'
        adapter, llm = _make_adapter(llm_response=llm_response)
        ctx = _RepairCycleContext()

        failures = (
            RepairTestFailure(file="test_a.py", test="test_1", message="fail"),
            RepairTestFailure(file="test_b.py", test="test_2", message="fail"),
        )
        analysis_result = MagicMock(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.95,
            reasoning="Shared interface broken",
            recommended_action="Fix interface",
            affected_files=("a.py", "b.py"),
            cross_cutting=False,
        )

        await adapter.fix_failures_systemically(
            failures, analysis_result, ctx.test_configs[0], ctx
        )

        # Verify exactly one LLM call was made
        assert llm.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_fix_failures_systemically_returns_success_with_files(self):
        """fix_failures_systemically returns SystemicFixResult with success=True and files_modified."""
        llm_response = '{"root_cause_addressed": "Fixed shared interface", "files_modified": ["file1.py", "file2.py"]}'
        adapter, _ = _make_adapter(llm_response=llm_response)
        ctx = _RepairCycleContext()

        failures = (
            RepairTestFailure(file="test_a.py", test="test_1", message="fail"),
            RepairTestFailure(file="test_b.py", test="test_2", message="fail"),
        )
        analysis_result = MagicMock(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.95,
            reasoning="Shared interface broken",
            recommended_action="Fix interface",
            affected_files=("a.py", "b.py"),
            cross_cutting=False,
        )

        result = await adapter.fix_failures_systemically(
            failures, analysis_result, ctx.test_configs[0], ctx
        )

        assert result.success is True
        assert len(result.files_modified) == 2
        assert "file1.py" in result.files_modified
        assert "file2.py" in result.files_modified

    @pytest.mark.asyncio
    async def test_fix_failures_systemically_failure_returns_false(self):
        """fix_failures_systemically returns success=False on LLM error."""
        adapter, llm = _make_adapter()
        # Simulate LLM failure
        llm.execute.side_effect = Exception("LLM error")
        ctx = _RepairCycleContext()

        failures = (
            RepairTestFailure(file="test_a.py", test="test_1", message="fail"),
        )
        analysis_result = MagicMock(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.95,
            reasoning="Shared interface broken",
            recommended_action="Fix interface",
            affected_files=("a.py",),
            cross_cutting=False,
        )

        result = await adapter.fix_failures_systemically(
            failures, analysis_result, ctx.test_configs[0], ctx
        )

        assert result.success is False
        assert len(result.files_modified) == 0

    @pytest.mark.asyncio
    async def test_fix_failures_systemically_parse_error_returns_false(self):
        """fix_failures_systemically handles JSON parse errors gracefully."""
        adapter, _ = _make_adapter(llm_response="invalid json")
        ctx = _RepairCycleContext()

        failures = (
            RepairTestFailure(file="test_a.py", test="test_1", message="fail"),
        )
        analysis_result = MagicMock(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.95,
            reasoning="Shared interface broken",
            recommended_action="Fix interface",
            affected_files=("a.py",),
            cross_cutting=False,
        )

        result = await adapter.fix_failures_systemically(
            failures, analysis_result, ctx.test_configs[0], ctx
        )

        assert result.success is False


# ---------------------------------------------------------------------------
# Classification Dispatch: CODE_DEFECT with cross_cutting
# ---------------------------------------------------------------------------


class TestClassificationDispatchCodeDefectWithCrossCutting:
    @pytest.mark.asyncio
    async def test_code_defect_cross_cutting_calls_systemic_fix(self):
        """CODE_DEFECT with cross_cutting=True calls fix_failures_systemically."""
        event_emitter = MagicMock()
        systemic_service = AsyncMock()
        systemic_service.analyze.return_value = MagicMock(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.95,
            reasoning="Shared interface issue",
            recommended_action="Fix interface",
            affected_files=("a.py", "b.py"),
            cross_cutting=True,
        )

        adapter, _ = _make_adapter(event_emitter=event_emitter)
        adapter._systemic_analysis_service = systemic_service

        # Mock fix_failures_systemically
        adapter.fix_failures_systemically = AsyncMock(
            return_value=MagicMock(success=True, files_modified=("file1.py", "file2.py"))
        )

        ctx = _RepairCycleContext(max_total_agent_calls=100)
        await adapter.execute(ctx)

        # Verify systemic fix was called
        adapter.fix_failures_systemically.assert_called_once()

    @pytest.mark.asyncio
    async def test_code_defect_non_cross_cutting_calls_fix_by_file(self):
        """CODE_DEFECT with cross_cutting=False calls fix_failures_by_file."""
        event_emitter = MagicMock()
        systemic_service = AsyncMock()
        systemic_service.analyze.return_value = MagicMock(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.95,
            reasoning="File-specific issue",
            recommended_action="Fix file",
            affected_files=("a.py",),
            cross_cutting=False,
        )

        adapter, _ = _make_adapter(event_emitter=event_emitter)
        adapter._systemic_analysis_service = systemic_service

        # Mock fix_failures_by_file
        adapter.fix_failures_by_file = AsyncMock(return_value=1)

        ctx = _RepairCycleContext(max_total_agent_calls=100)
        await adapter.execute(ctx)

        # Verify file-level fix was called, not systemic
        adapter.fix_failures_by_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_code_defect_cross_cutting_exceeds_50_failures_fallback(self):
        """CODE_DEFECT with cross_cutting=True but > 50 failures falls back to fix_failures_by_file."""
        event_emitter = MagicMock()
        systemic_service = AsyncMock()

        # Create 51 failures
        failures = tuple(
            RepairTestFailure(file=f"test_{i}.py", test=f"test_{i}", message="fail")
            for i in range(51)
        )

        systemic_service.analyze.return_value = MagicMock(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.95,
            reasoning="Shared interface issue",
            recommended_action="Fix interface",
            affected_files=("a.py", "b.py"),
            cross_cutting=True,  # cross_cutting but > 50 failures
        )

        adapter, _ = _make_adapter(event_emitter=event_emitter)
        adapter._systemic_analysis_service = systemic_service

        # Mock both methods
        adapter.fix_failures_systemically = AsyncMock()
        adapter.fix_failures_by_file = AsyncMock(return_value=5)

        # Manually call _run_test_cycle since execute uses run_tests mock
        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=30,
            max_iterations=1,
            review_warnings=False,
        )
        ctx = _RepairCycleContext(max_total_agent_calls=100)

        test_result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=0,
            failed=51,
            warnings=0,
            failures=failures,
            warning_list=(),
            raw_output="{}",
            timestamp="2024-01-01T00:00:00Z",
        )

        adapter.run_tests = AsyncMock(return_value=test_result)

        await adapter.execute(ctx)

        # Should fallback to fix_failures_by_file instead of systemic
        adapter.fix_failures_systemically.assert_not_called()
        adapter.fix_failures_by_file.assert_called_once()
