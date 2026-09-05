"""Domain value objects for coding-agent configuration (D6).

These types live in the domain layer so both the :class:`Agent`
aggregate and the :class:`AgentConfig` port DTO can reference the same
shape without one importing from the other.

The port :mod:`codetoreum.ports.output.coding_agent` re-exports
:class:`InvocationMode` for callers that already import from there;
domain code should import from this module directly to keep the layering
clean.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any


class InvocationMode(StrEnum):
    """Where the coding agent's execution happens.

    Orthogonal to *how* the agent communicates (subprocess
    ``stream-json``, HTTP streaming response, etc.) — that's an
    adapter-internal implementation choice.

    Members:
        CONTAINERIZED: adapter uses ``IContainer`` to run the agent
            inside a sandboxed container.
        HOST: adapter runs the agent process directly on the host.
        API: adapter makes HTTP calls (Copilot, future direct APIs).
    """

    CONTAINERIZED = "containerized"
    HOST = "host"
    API = "api"


@dataclass(frozen=True)
class AgentInvocationConfig:
    """Per-execution invocation configuration for an agent (D6, proposal §3h).

    Immutable value object describing how a coding-agent adapter should
    invoke a model for a given agent. Coupled with
    :class:`~codetoreum.ports.output.coding_agent.CodingAgentInvocationOptions`
    at execute time: the executor lifts ``invocation.mode``,
    ``invocation.model``, ``invocation.timeout_seconds``,
    ``invocation.mode_config`` and ``invocation.cost_limit_usd`` straight
    into the options the adapter receives.

    Attributes:
        mode: Where execution happens (CONTAINERIZED / HOST / API).
            Validated by the loader against the adapter's
            ``supported_invocation_modes()`` at config load time, not at
            first execution.
        model: Model name (e.g. ``"claude-sonnet-4-6"``).
        timeout_seconds: Hard timeout for the execution.
        mode_config: Mode-specific configuration — e.g. for
            ``CONTAINERIZED``: ``{"image": ..., "cpu_limit": ...,
            "memory_limit": ...}``; for ``API``: ``{"endpoint": ...}``.
            Carried as a generic ``Mapping`` so each mode's strategy can
            interpret it.
        cost_limit_usd: Optional per-execution USD cost ceiling. ``None``
            means no enforced limit.
    """

    mode: InvocationMode
    model: str
    timeout_seconds: int
    mode_config: Mapping[str, Any] = field(default_factory=dict)
    cost_limit_usd: Decimal | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, InvocationMode):
            msg = f"mode must be InvocationMode, got {type(self.mode).__name__}"
            raise ValueError(msg)
        if not isinstance(self.model, str) or not self.model:
            msg = "model must be a non-empty string"
            raise ValueError(msg)
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, int)
            or self.timeout_seconds <= 0
        ):
            msg = "timeout_seconds must be a positive integer"
            raise ValueError(msg)
        # mode_config: accept any Mapping; freeze dicts.
        if isinstance(self.mode_config, dict):
            object.__setattr__(self, "mode_config", MappingProxyType(dict(self.mode_config)))
        elif not isinstance(self.mode_config, Mapping):
            msg = "mode_config must be a Mapping"
            raise ValueError(msg)
        if self.cost_limit_usd is not None and not isinstance(self.cost_limit_usd, Decimal):
            msg = "cost_limit_usd must be None or Decimal"
            raise ValueError(msg)


__all__ = ["AgentInvocationConfig", "InvocationMode"]
