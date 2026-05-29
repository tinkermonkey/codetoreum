"""Claude Code adapter package (post-D3 redesign).

Implements the :class:`~codetoreum.ports.output.coding_agent.ICodingAgent`
port via :class:`ClaudeCodeAdapter`, with internal strategy pattern
(:mod:`.strategies`), Claude-specific stream parser
(:mod:`.stream_parser`), and a vendor-specific prompt renderer
(:mod:`.prompt_renderer`).

The old :mod:`codetoreum.adapters.secondary.claude_code_adapter` (which
implements the deprecated ``IAgentLauncher`` port) coexists during D3/D4
and is removed in Phase D5.
"""

from codetoreum.adapters.secondary.claude_code.adapter import (
    ClaudeCodeAdapter,
    ClaudeCodeAdapterConfig,
    UnsupportedInvocationModeError,
)
from codetoreum.adapters.secondary.claude_code.credentials import (
    EnvironmentCredentialProvider,
    StaticCredentialProvider,
)

__all__ = [
    "ClaudeCodeAdapter",
    "ClaudeCodeAdapterConfig",
    "EnvironmentCredentialProvider",
    "StaticCredentialProvider",
    "UnsupportedInvocationModeError",
]
