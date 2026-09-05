"""Invocation strategies for :class:`ClaudeCodeAdapter` (post-D3).

A strategy encapsulates **where the agent's execution happens** for one
:class:`~codetoreum.ports.output.coding_agent.InvocationMode`:

- :class:`ContainerizedClaudeStrategy` (mode = ``containerized``) runs the
  CLI inside a sandboxed container via
  :class:`~codetoreum.ports.output.container.IContainer`.
- :class:`HostClaudeStrategy` (mode = ``host``) runs the CLI as a host
  subprocess via :mod:`asyncio.subprocess`.

Both strategies stream the agent's ``stream-json`` output through the
shared :class:`~codetoreum.adapters.secondary.claude_code.stream_parser.ClaudeStreamJsonParser`,
publish each emitted event to the supplied
:class:`~codetoreum.infrastructure.event_bus.EventBus`, and return a final
:class:`~codetoreum.ports.output.coding_agent.CodingAgentResult`.
"""

from codetoreum.adapters.secondary.claude_code.strategies.base import (
    ClaudeInvocationStrategy,
)
from codetoreum.adapters.secondary.claude_code.strategies.containerized import (
    ContainerizedClaudeStrategy,
)
from codetoreum.adapters.secondary.claude_code.strategies.host import (
    CredentialProviderProtocol,
    HostClaudeStrategy,
)

__all__ = [
    "ClaudeInvocationStrategy",
    "ContainerizedClaudeStrategy",
    "CredentialProviderProtocol",
    "HostClaudeStrategy",
]
