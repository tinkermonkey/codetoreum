"""Unit tests for ProductionRepairCycleAdapter circuit breaker behavior.

Verifies that:
1. execute() raises CircuitBreakerOpenError and emits fast-fail event when CB is pre-opened
2. is_open() is used to check state (not get_state() == OPEN)
3. Without a CB, LLM is called directly (not via cb.call())
4. With a CB, LLM is wrapped via circuit_breaker.call()
5. get_stats().total_calls is used for RepairCycleResult.total_agent_calls
6. fix_failures_by_file checks is_open() before each file
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.adapters.secondary.production_repair_cycle_adapter import (
    ProductionRepairCycleAdapter,
    RepairCycleConfig,
)
from codetoreum.domain.repair_cycle_types import (
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
        llm_provider=llm,
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
