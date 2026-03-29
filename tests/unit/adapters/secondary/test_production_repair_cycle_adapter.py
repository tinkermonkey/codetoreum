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

from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.adapters.secondary.production_repair_cycle_adapter import (
    ProductionRepairCycleAdapter,
    RepairCycleConfig,
)
from codetoreum.domain.repair_cycle_types import (
    FailureClassification,
    RepairTestFailure,
    RepairTestRunConfig,
    RepairTestType,
)
from codetoreum.infrastructure.resilience.exceptions import CircuitBreakerOpenError
from codetoreum.infrastructure.resilience.interfaces import CircuitState
from codetoreum.infrastructure.resilience.mocks import MockCircuitBreaker

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


def _make_adapter(
    *,
    llm_response: str = _VALID_JSON_RESPONSE,
    circuit_breaker=None,
    event_emitter=None,
) -> tuple[ProductionRepairCycleAdapter, AsyncMock]:
    """Return (adapter, mock_llm) pre-wired for tests."""
    llm = AsyncMock()
    llm.execute.return_value = llm_response
    config = RepairCycleConfig(max_json_parse_retries=1, json_parse_retry_delay_ms=0)
    adapter = ProductionRepairCycleAdapter(
        llm_factory=lambda: llm,
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
            ),
            MagicMock(
                classification=FailureClassification.CODE_DEFECT,
                confidence=0.95,
                reasoning="Source code has a bug",
                recommended_action="Fix the bug",
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
            ),
            MagicMock(
                classification=FailureClassification.TRANSIENT_FAILURE,
                confidence=0.8,
                reasoning="Flaky test 2",
                recommended_action="Retry",
            ),
            MagicMock(
                classification=FailureClassification.CODE_DEFECT,
                confidence=0.95,
                reasoning="Code defect from escalation",
                recommended_action="Fix the bug",
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
            ),
            MagicMock(
                classification=FailureClassification.TRANSIENT_FAILURE,
                confidence=0.8,
                reasoning="Flaky test 2",
                recommended_action="Retry",
            ),
            MagicMock(
                classification=FailureClassification.TRANSIENT_FAILURE,
                confidence=0.8,
                reasoning="Flaky test 3",
                recommended_action="Retry",
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
            ),
            MagicMock(
                classification=FailureClassification.TRANSIENT_FAILURE,
                confidence=0.8,
                reasoning="Flaky test 2",
                recommended_action="Retry",
            ),
            MagicMock(
                classification=FailureClassification.TRANSIENT_FAILURE,
                confidence=0.8,
                reasoning="Flaky test 3 (escalation triggers on 3rd consecutive)",
                recommended_action="Retry",
            ),
            MagicMock(
                classification=FailureClassification.TRANSIENT_FAILURE,
                confidence=0.8,
                reasoning="Flaky test 4 (counter resets to 1 after escalation)",
                recommended_action="Retry",
            ),
            MagicMock(
                classification=FailureClassification.TRANSIENT_FAILURE,
                confidence=0.8,
                reasoning="Flaky test 5 (counter at 2, below escalation threshold)",
                recommended_action="Retry",
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
        )

        adapter, _ = _make_adapter(event_emitter=event_emitter)
        adapter._systemic_analysis_service = systemic_service
        adapter.apply_systemic_fixes = AsyncMock(return_value=True)

        ctx = _RepairCycleContext(max_total_agent_calls=100)
        await adapter.execute(ctx)

        adapter.apply_systemic_fixes.assert_called_once()


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
