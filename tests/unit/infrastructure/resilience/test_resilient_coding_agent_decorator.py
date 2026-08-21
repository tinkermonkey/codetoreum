"""Unit tests for :class:`ResilientCodingAgentDecorator`."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.infrastructure.resilience.decorators import (
    ResilientCodingAgentDecorator,
)
from codetoreum.ports.output.coding_agent import (
    CodingAgentInvocationOptions,
    CodingAgentResult,
    InvocationMode,
)


def _result() -> CodingAgentResult:
    return CodingAgentResult(
        success=True,
        summary_text="ok",
        total_cost_usd=Decimal("0"),
        total_input_tokens=0,
        total_output_tokens=0,
        tool_call_count=0,
        duration_ms=1,
        error_summary=None,
    )


def _options() -> CodingAgentInvocationOptions:
    return CodingAgentInvocationOptions(
        invocation_mode=InvocationMode.HOST,
        model="m",
        timeout_seconds=30,
        cost_limit_usd=None,
        mode_config={},
    )


@pytest.mark.asyncio
async def test_passthrough_when_no_resilience_components():
    wrapped = MagicMock()
    wrapped.execute = AsyncMock(return_value=_result())
    wrapped.supported_invocation_modes = MagicMock(return_value=frozenset({InvocationMode.HOST}))
    deco = ResilientCodingAgentDecorator(wrapped=wrapped)

    assert deco.supported_invocation_modes() == frozenset({InvocationMode.HOST})

    result = await deco.execute("exec", "ctx", _options())
    assert result.success is True
    wrapped.execute.assert_awaited_once_with("exec", "ctx", _options())


@pytest.mark.asyncio
async def test_rate_limiter_invoked_with_one_unit():
    rate_limiter = AsyncMock()
    wrapped = AsyncMock()
    wrapped.execute.return_value = _result()
    deco = ResilientCodingAgentDecorator(wrapped=wrapped, rate_limiter=rate_limiter)

    await deco.execute("exec", "ctx", _options())
    rate_limiter.acquire.assert_awaited_once_with("coding_agent.execute", 1)


@pytest.mark.asyncio
async def test_circuit_breaker_calls_into_inner_pipeline():
    """A passing CB delegates to the inner pipeline and returns its result."""
    wrapped = AsyncMock()
    wrapped.execute.return_value = _result()

    class _PassThroughCB:
        async def call(self, fn, name, *args, **kwargs):
            return await fn(*args, **kwargs)

    deco = ResilientCodingAgentDecorator(
        wrapped=wrapped,
        circuit_breaker=_PassThroughCB(),
    )
    result = await deco.execute("exec", "ctx", _options())
    assert result.success is True
    wrapped.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_circuit_breaker_short_circuits_when_open():
    wrapped = AsyncMock()

    class _OpenCB:
        async def call(self, *args, **kwargs):
            raise RuntimeError("circuit open")

    deco = ResilientCodingAgentDecorator(wrapped=wrapped, circuit_breaker=_OpenCB())
    with pytest.raises(RuntimeError, match="circuit open"):
        await deco.execute("exec", "ctx", _options())
    wrapped.execute.assert_not_called()


@pytest.mark.asyncio
async def test_retry_policy_wraps_inner_pipeline():
    wrapped = AsyncMock()
    wrapped.execute.return_value = _result()

    class _CountingRetry:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, fn, name):
            self.calls += 1
            return await fn()

    retry = _CountingRetry()
    deco = ResilientCodingAgentDecorator(wrapped=wrapped, retry_policy=retry)
    await deco.execute("exec", "ctx", _options())
    assert retry.calls == 1


@pytest.mark.asyncio
async def test_timeout_invoked_with_per_call_buffer():
    wrapped = AsyncMock()
    wrapped.execute.return_value = _result()

    captured_timeouts: list[float] = []

    class _CapturingTimeout:
        async def execute(self, fn, timeout, name):
            captured_timeouts.append(timeout)
            return await fn()

    deco = ResilientCodingAgentDecorator(
        wrapped=wrapped,
        timeout=_CapturingTimeout(),
    )
    opts = CodingAgentInvocationOptions(
        invocation_mode=InvocationMode.HOST,
        model="m",
        timeout_seconds=600,
        cost_limit_usd=None,
        mode_config={},
    )
    await deco.execute("exec", "ctx", opts)
    # 600 + 300 buffer
    assert captured_timeouts == [900.0]


@pytest.mark.asyncio
async def test_supported_modes_passthrough():
    wrapped = MagicMock()
    wrapped.supported_invocation_modes = MagicMock(
        return_value=frozenset({InvocationMode.HOST, InvocationMode.CONTAINERIZED}),
    )
    deco = ResilientCodingAgentDecorator(wrapped=wrapped)
    assert deco.supported_invocation_modes() == frozenset(
        {InvocationMode.HOST, InvocationMode.CONTAINERIZED},
    )


# Silence the unused-import lint in case of future refactors.
_unused: Any = None
