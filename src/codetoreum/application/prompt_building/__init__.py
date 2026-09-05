"""Application-layer prompt-building strategies.

This package holds concrete :class:`~codetoreum.ports.output.prompt_builder.IPromptBuilder`
implementations. The default is :class:`DefaultPromptBuilder`. Future
strategy variants (custom per-project prompt assemblers, A/B test variants,
etc.) can live alongside it.

Per INV-18 (see ``bootstrap/ARCHITECTURE.md`` §6), prompt-building business
logic lives here, not inside coding agent adapters. Adapters render the
resulting :class:`~codetoreum.ports.output.prompt_builder.StructuredPrompt`
to their vendor's expected format but do not own *what context to include*.
"""

from codetoreum.application.prompt_building.default_prompt_builder import (
    DefaultPromptBuilder,
)

__all__ = ["DefaultPromptBuilder"]
