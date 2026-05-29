"""Unit tests for the ICodingAgent port and supporting value objects (D1).

Covers:

- ``InvocationMode`` string serialisation values.
- ``CodingAgentInvocationOptions`` immutability (frozen).
- ``CodingAgentResult`` immutability (frozen).
- ``ICodingAgent`` cannot be instantiated directly (abstract).
"""

from dataclasses import FrozenInstanceError
from decimal import Decimal
from types import MappingProxyType

import pytest

from codetoreum.ports.output.coding_agent import (
    CodingAgentInvocationOptions,
    CodingAgentResult,
    ICodingAgent,
    InvocationMode,
)


class TestInvocationMode:
    """InvocationMode StrEnum semantics."""

    def test_values_match_documented_strings(self) -> None:
        assert InvocationMode.CONTAINERIZED.value == "containerized"
        assert InvocationMode.HOST.value == "host"
        assert InvocationMode.API.value == "api"

    def test_is_str_subclass(self) -> None:
        # StrEnum members ARE strings — important for cross-language wire
        # serialisation (event "invocation_mode" is a plain string).
        assert isinstance(InvocationMode.CONTAINERIZED, str)
        assert isinstance(InvocationMode.HOST, str)
        assert isinstance(InvocationMode.API, str)

    def test_round_trips_through_string(self) -> None:
        for mode in InvocationMode:
            assert InvocationMode(mode.value) is mode

    def test_three_modes_only(self) -> None:
        # Guard against accidental additions without a corresponding doc update.
        assert {m.value for m in InvocationMode} == {"containerized", "host", "api"}


class TestCodingAgentInvocationOptions:
    """CodingAgentInvocationOptions is an immutable value object."""

    def _make(self, **overrides) -> CodingAgentInvocationOptions:
        defaults = {
            "invocation_mode": InvocationMode.CONTAINERIZED,
            "model": "claude-sonnet-4-6",
            "timeout_seconds": 3600,
            "cost_limit_usd": Decimal("5.00"),
            "mode_config": MappingProxyType({"image": "codetoreum-agent:latest", "cpu_limit": "2"}),
        }
        defaults.update(overrides)
        return CodingAgentInvocationOptions(**defaults)

    def test_create_valid(self) -> None:
        opts = self._make()
        assert opts.invocation_mode == InvocationMode.CONTAINERIZED
        assert opts.model == "claude-sonnet-4-6"
        assert opts.timeout_seconds == 3600
        assert opts.cost_limit_usd == Decimal("5.00")
        assert dict(opts.mode_config) == {
            "image": "codetoreum-agent:latest",
            "cpu_limit": "2",
        }

    def test_cost_limit_none_allowed(self) -> None:
        opts = self._make(cost_limit_usd=None)
        assert opts.cost_limit_usd is None

    def test_is_frozen(self) -> None:
        opts = self._make()
        with pytest.raises(FrozenInstanceError):
            opts.model = "claude-opus"  # type: ignore[misc]

    def test_supports_api_mode(self) -> None:
        opts = self._make(
            invocation_mode=InvocationMode.API,
            mode_config={"endpoint": "https://api.example.com"},
        )
        assert opts.invocation_mode == InvocationMode.API
        assert opts.mode_config["endpoint"] == "https://api.example.com"


class TestCodingAgentResult:
    """CodingAgentResult is an immutable summary."""

    def _make(self, **overrides) -> CodingAgentResult:
        defaults = {
            "success": True,
            "summary_text": "Implemented the requested feature.",
            "total_cost_usd": Decimal("0.42"),
            "total_input_tokens": 1234,
            "total_output_tokens": 567,
            "tool_call_count": 8,
            "duration_ms": 65000,
            "error_summary": None,
        }
        defaults.update(overrides)
        return CodingAgentResult(**defaults)

    def test_create_success(self) -> None:
        r = self._make()
        assert r.success is True
        assert r.summary_text == "Implemented the requested feature."
        assert r.total_cost_usd == Decimal("0.42")
        assert r.total_input_tokens == 1234
        assert r.total_output_tokens == 567
        assert r.tool_call_count == 8
        assert r.duration_ms == 65000
        assert r.error_summary is None

    def test_create_failure(self) -> None:
        r = self._make(success=False, error_summary="Container OOM-killed")
        assert r.success is False
        assert r.error_summary == "Container OOM-killed"

    def test_is_frozen(self) -> None:
        r = self._make()
        with pytest.raises(FrozenInstanceError):
            r.success = False  # type: ignore[misc]


class TestICodingAgent:
    """ICodingAgent is an abstract base class."""

    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            ICodingAgent()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_both_methods(self) -> None:
        # A subclass missing one abstract method must still fail to
        # instantiate (regression check on the abstractmethod decorators).
        class OnlySupportedModes(ICodingAgent):
            def supported_invocation_modes(self) -> frozenset[InvocationMode]:
                return frozenset({InvocationMode.HOST})

            # `execute` deliberately not implemented.

        with pytest.raises(TypeError):
            OnlySupportedModes()  # type: ignore[abstract]
