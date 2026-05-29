"""Placeholder for the ClaudeCodeAdapter implementation (filled in later in D3).

This file currently exists to satisfy the package's ``__init__`` import.
The real adapter (with strategies, parser, renderer wiring) lands in a
later commit of Phase D3.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClaudeCodeAdapterConfig:
    """Placeholder config (real shape lands with the adapter)."""


class ClaudeCodeAdapter:  # pragma: no cover - placeholder
    """Placeholder. See module docstring."""


__all__ = ["ClaudeCodeAdapter", "ClaudeCodeAdapterConfig"]
