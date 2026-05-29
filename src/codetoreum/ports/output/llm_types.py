"""Shared LLM execution value objects.

This module owns the request/response value objects used by the legacy
prompt→completion call sites (the production repair-cycle adapters,
environment-repair adapter, and LLM-backed systemic-analysis adapter).

History: these types previously lived in
``codetoreum.ports.output.llm_provider`` alongside ``ILLMProvider`` /
``IAgentLauncher``. Phase D5 of the coding-agent port redesign deleted
those ports and their implementations; this module preserves the shared
data shapes so the prompt→completion adapters can keep operating until
they are migrated to ``ICodingAgent`` in a future cycle.

New code should prefer ``ICodingAgent`` (and the ``CodingAgentResult`` /
``CodingAgentInvocationOptions`` value objects in ``coding_agent.py``).
This module is retained for the surviving prompt→completion call sites.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

from codetoreum.domain.types import ExecutionId, UserId


@dataclass(frozen=True)
class ExecutionContext:
    """Context for LLM execution.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation. Mutable collections are
    converted to immutable equivalents.
    """

    # Model configuration
    model: str | None = None
    temperature: float = 0.7
    max_tokens: int | None = None
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0

    # Conversation context
    conversation_id: str | None = None
    message_history: tuple[dict[str, Any], ...] = ()
    system_prompt: str | None = None

    # Execution options
    timeout_seconds: int = 300
    retry_on_error: bool = True
    cache_response: bool = False

    # Workspace context (for containerized execution)
    working_directory: Path | None = None
    mounted_context_files: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    available_files: tuple[str, ...] = ()
    environment_variables: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    # MCP Server configuration
    mcp_servers: tuple[dict[str, Any], ...] = ()

    # Metadata
    user_id: UserId | None = None
    session_id: str | None = None
    execution_id: ExecutionId | None = None
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        # Coerce list to tuple for message_history
        if isinstance(self.message_history, list):
            object.__setattr__(self, "message_history", tuple(self.message_history))

        # Coerce list to tuple for available_files
        if isinstance(self.available_files, list):
            object.__setattr__(self, "available_files", tuple(self.available_files))

        # Coerce list to tuple for mcp_servers
        if isinstance(self.mcp_servers, list):
            object.__setattr__(self, "mcp_servers", tuple(self.mcp_servers))

        # Coerce dict to MappingProxyType for mounted_context_files
        if (
            isinstance(self.mounted_context_files, dict)
            and not isinstance(self.mounted_context_files, MappingProxyType)
        ) or (
            isinstance(self.mounted_context_files, Mapping)
            and not isinstance(self.mounted_context_files, MappingProxyType)
        ):
            object.__setattr__(self, "mounted_context_files", MappingProxyType(self.mounted_context_files))

        # Coerce dict to MappingProxyType for environment_variables
        if (
            isinstance(self.environment_variables, dict)
            and not isinstance(self.environment_variables, MappingProxyType)
        ) or (
            isinstance(self.environment_variables, Mapping)
            and not isinstance(self.environment_variables, MappingProxyType)
        ):
            object.__setattr__(self, "environment_variables", MappingProxyType(self.environment_variables))

        # Coerce dict to MappingProxyType for metadata
        if (isinstance(self.metadata, dict) and not isinstance(self.metadata, MappingProxyType)) or (
            isinstance(self.metadata, Mapping) and not isinstance(self.metadata, MappingProxyType)
        ):
            object.__setattr__(self, "metadata", MappingProxyType(self.metadata))

        if self.model is not None:
            if not isinstance(self.model, str) or not self.model:
                msg = "model must be a non-empty string or None"
                raise ValueError(msg)

        if not isinstance(self.temperature, (int, float)) or not (0.0 <= self.temperature <= 2.0):
            msg = "temperature must be a number between 0.0 and 2.0"
            raise ValueError(msg)

        if self.max_tokens is not None:
            if isinstance(self.max_tokens, bool) or not isinstance(self.max_tokens, int) or self.max_tokens <= 0:
                msg = "max_tokens must be a positive integer or None"
                raise ValueError(msg)

        if not isinstance(self.top_p, (int, float)) or not (0.0 <= self.top_p <= 1.0):
            msg = "top_p must be a number between 0.0 and 1.0"
            raise ValueError(msg)

        if not isinstance(self.frequency_penalty, (int, float)) or not (-2.0 <= self.frequency_penalty <= 2.0):
            msg = "frequency_penalty must be a number between -2.0 and 2.0"
            raise ValueError(msg)

        if not isinstance(self.presence_penalty, (int, float)) or not (-2.0 <= self.presence_penalty <= 2.0):
            msg = "presence_penalty must be a number between -2.0 and 2.0"
            raise ValueError(msg)

        if self.conversation_id is not None:
            if not isinstance(self.conversation_id, str) or not self.conversation_id:
                msg = "conversation_id must be a non-empty string or None"
                raise ValueError(msg)

        if not isinstance(self.message_history, tuple):
            msg = "message_history must be a list or tuple of dicts"
            raise ValueError(msg)

        if self.system_prompt is not None:
            if not isinstance(self.system_prompt, str) or not self.system_prompt:
                msg = "system_prompt must be a non-empty string or None"
                raise ValueError(msg)

        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, int)
            or self.timeout_seconds <= 0
        ):
            msg = "timeout_seconds must be a positive integer"
            raise ValueError(msg)

        if not isinstance(self.retry_on_error, bool):
            msg = "retry_on_error must be a boolean"
            raise ValueError(msg)

        if not isinstance(self.cache_response, bool):
            msg = "cache_response must be a boolean"
            raise ValueError(msg)

        if self.working_directory is not None:
            if not isinstance(self.working_directory, Path):
                msg = "working_directory must be a Path or None"
                raise ValueError(msg)

        if not isinstance(self.mounted_context_files, MappingProxyType):
            msg = "mounted_context_files must be a dict or MappingProxyType"
            raise ValueError(msg)

        if not isinstance(self.available_files, tuple):
            msg = "available_files must be a list or tuple of strings"
            raise ValueError(msg)

        if not isinstance(self.environment_variables, MappingProxyType):
            msg = "environment_variables must be a dict or MappingProxyType"
            raise ValueError(msg)

        if not isinstance(self.mcp_servers, tuple):
            msg = "mcp_servers must be a list or tuple of dicts"
            raise ValueError(msg)

        if self.user_id is not None:
            if not isinstance(self.user_id, str):
                msg = "user_id must be a string or None"
                raise ValueError(msg)

        if self.session_id is not None:
            if not isinstance(self.session_id, str) or not self.session_id:
                msg = "session_id must be a non-empty string or None"
                raise ValueError(msg)

        if self.execution_id is not None:
            if not isinstance(self.execution_id, str):
                msg = "execution_id must be a string or None"
                raise ValueError(msg)

        if not isinstance(self.metadata, MappingProxyType):
            msg = "metadata must be a dict or MappingProxyType"
            raise ValueError(msg)


@dataclass(frozen=True)
class ExecutionResult:
    """Result from a prompt→completion LLM call.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation. Metadata is converted to
    an immutable equivalent.

    Note: tool-call payloads are not modelled here — the surviving consumers
    (repair-cycle and systemic-analysis adapters) only inspect ``content``. The
    earlier ``ToolCall`` field was removed when ``IAgentLauncher`` retired in
    Phase D5.
    """

    # Response content
    content: str
    role: str = "assistant"

    # Metadata
    model: str | None = None
    completion_tokens: int = 0
    prompt_tokens: int = 0
    total_tokens: int = 0

    # Timing
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    duration_ms: int = 0

    # Additional data
    finish_reason: str = "stop"
    conversation_id: str | None = None
    cached: bool = False
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        # Coerce dict to MappingProxyType for metadata
        if isinstance(self.metadata, dict):
            object.__setattr__(self, "metadata", MappingProxyType(self.metadata))

        if not isinstance(self.content, str) or not self.content:
            msg = "content must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.role, str) or not self.role:
            msg = "role must be a non-empty string"
            raise ValueError(msg)

        if self.model is not None:
            if not isinstance(self.model, str) or not self.model:
                msg = "model must be a non-empty string or None"
                raise ValueError(msg)

        if (
            isinstance(self.completion_tokens, bool)
            or not isinstance(self.completion_tokens, int)
            or self.completion_tokens < 0
        ):
            msg = "completion_tokens must be a non-negative integer"
            raise ValueError(msg)

        if isinstance(self.prompt_tokens, bool) or not isinstance(self.prompt_tokens, int) or self.prompt_tokens < 0:
            msg = "prompt_tokens must be a non-negative integer"
            raise ValueError(msg)

        if isinstance(self.total_tokens, bool) or not isinstance(self.total_tokens, int) or self.total_tokens < 0:
            msg = "total_tokens must be a non-negative integer"
            raise ValueError(msg)

        if not isinstance(self.started_at, datetime):
            msg = "started_at must be a datetime instance"
            raise ValueError(msg)

        if not isinstance(self.completed_at, datetime):
            msg = "completed_at must be a datetime instance"
            raise ValueError(msg)

        if isinstance(self.duration_ms, bool) or not isinstance(self.duration_ms, int) or self.duration_ms < 0:
            msg = "duration_ms must be a non-negative integer"
            raise ValueError(msg)

        if not isinstance(self.finish_reason, str) or not self.finish_reason:
            msg = "finish_reason must be a non-empty string"
            raise ValueError(msg)

        if self.conversation_id is not None:
            if not isinstance(self.conversation_id, str) or not self.conversation_id:
                msg = "conversation_id must be a non-empty string or None"
                raise ValueError(msg)

        if not isinstance(self.cached, bool):
            msg = "cached must be a boolean"
            raise ValueError(msg)

        if not isinstance(self.metadata, MappingProxyType):
            msg = "metadata must be a dict or MappingProxyType"
            raise ValueError(msg)

    @property
    def total_cost(self) -> float:
        """Calculate cost based on token usage (provider-specific)."""
        return 0.0
