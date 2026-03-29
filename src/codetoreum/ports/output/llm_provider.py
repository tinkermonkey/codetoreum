"""ILLMProvider output port interface."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

from codetoreum.domain.types import ExecutionId, UserId

# ============================================================================
# Data Models
# ============================================================================


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
class ToolDefinition:
    """Definition of a tool/function the LLM can call.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation. Mutable collections are
    converted to immutable equivalents.
    """

    name: str
    description: str
    parameters: MappingProxyType
    required: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        # Coerce dict to MappingProxyType for parameters
        if isinstance(self.parameters, dict):
            object.__setattr__(self, "parameters", MappingProxyType(self.parameters))

        # Coerce list to tuple for required
        if isinstance(self.required, list):
            object.__setattr__(self, "required", tuple(self.required))

        if not isinstance(self.name, str) or not self.name:
            msg = "name must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.description, str) or not self.description:
            msg = "description must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.parameters, MappingProxyType):
            msg = "parameters must be a dict or MappingProxyType"
            raise ValueError(msg)

        if not isinstance(self.required, tuple):
            msg = "required must be a list or tuple of strings"
            raise ValueError(msg)

        if not all(isinstance(r, str) and r for r in self.required):
            msg = "all required items must be non-empty strings"
            raise ValueError(msg)


@dataclass(frozen=True)
class ToolCall:
    """Represents a tool call made by the LLM.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation. Arguments dict is
    converted to MappingProxyType for immutability.
    """

    tool_name: str
    arguments: MappingProxyType
    call_id: str

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        # Coerce dict to MappingProxyType for arguments
        if isinstance(self.arguments, dict):
            object.__setattr__(self, "arguments", MappingProxyType(self.arguments))

        if not isinstance(self.tool_name, str) or not self.tool_name:
            msg = "tool_name must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.arguments, MappingProxyType):
            msg = "arguments must be a dict or MappingProxyType"
            raise ValueError(msg)

        if not isinstance(self.call_id, str) or not self.call_id:
            msg = "call_id must be a non-empty string"
            raise ValueError(msg)


@dataclass(frozen=True)
class ToolCallDelta:
    """Incremental update to a tool call (for streaming).

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation. Delta dict is converted
    to MappingProxyType for immutability.
    """

    call_id: str
    delta: MappingProxyType

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        # Coerce dict to MappingProxyType for delta
        if isinstance(self.delta, dict):
            object.__setattr__(self, "delta", MappingProxyType(self.delta))

        if not isinstance(self.call_id, str) or not self.call_id:
            msg = "call_id must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.delta, MappingProxyType):
            msg = "delta must be a dict or MappingProxyType"
            raise ValueError(msg)


@dataclass(frozen=True)
class StreamChunk:
    """Single chunk in streaming response.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation. Metadata dict is converted
    to MappingProxyType for immutability.
    """

    content: str
    chunk_index: int
    is_final: bool = False

    # Tool calls in progress
    tool_call_delta: ToolCallDelta | None = None

    # Metadata
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        # Coerce dict to MappingProxyType for metadata
        if isinstance(self.metadata, dict):
            object.__setattr__(self, "metadata", MappingProxyType(self.metadata))

        if not isinstance(self.content, str):
            msg = "content must be a string"
            raise ValueError(msg)

        if isinstance(self.chunk_index, bool) or not isinstance(self.chunk_index, int) or self.chunk_index < 0:
            msg = "chunk_index must be a non-negative integer"
            raise ValueError(msg)

        if not isinstance(self.is_final, bool):
            msg = "is_final must be a boolean"
            raise ValueError(msg)

        if self.tool_call_delta is not None:
            if not isinstance(self.tool_call_delta, ToolCallDelta):
                msg = "tool_call_delta must be a ToolCallDelta or None"
                raise ValueError(msg)

        if not isinstance(self.timestamp, datetime):
            msg = "timestamp must be a datetime instance"
            raise ValueError(msg)

        if not isinstance(self.metadata, MappingProxyType):
            msg = "metadata must be a dict or MappingProxyType"
            raise ValueError(msg)


@dataclass(frozen=True)
class ExecutionResult:
    """Result from LLM execution.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation. Tool calls and metadata
    are converted to immutable equivalents.
    """

    # Response content
    content: str
    role: str = "assistant"

    # Tool calls (if any)
    tool_calls: tuple[ToolCall, ...] = ()

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
        # Coerce list to tuple for tool_calls
        if isinstance(self.tool_calls, list):
            object.__setattr__(self, "tool_calls", tuple(self.tool_calls))

        # Coerce dict to MappingProxyType for metadata
        if isinstance(self.metadata, dict):
            object.__setattr__(self, "metadata", MappingProxyType(self.metadata))

        if not isinstance(self.content, str) or not self.content:
            msg = "content must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.role, str) or not self.role:
            msg = "role must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.tool_calls, tuple):
            msg = "tool_calls must be a list or tuple of ToolCall instances"
            raise ValueError(msg)

        if not all(isinstance(tc, ToolCall) for tc in self.tool_calls):
            msg = "all tool_calls must be ToolCall instances"
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


@dataclass(frozen=True)
class ModelInfo:
    """Information about an LLM model.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation. Metadata dict is converted
    to MappingProxyType for immutability.
    """

    model_id: str
    provider: str
    display_name: str
    context_window: int
    max_output_tokens: int
    supports_tools: bool = False
    supports_streaming: bool = False
    cost_per_input_token: float = 0.0
    cost_per_output_token: float = 0.0
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        # Coerce dict to MappingProxyType for metadata
        if isinstance(self.metadata, dict):
            object.__setattr__(self, "metadata", MappingProxyType(self.metadata))

        if not isinstance(self.model_id, str) or not self.model_id:
            msg = "model_id must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.provider, str) or not self.provider:
            msg = "provider must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.display_name, str) or not self.display_name:
            msg = "display_name must be a non-empty string"
            raise ValueError(msg)

        if (
            isinstance(self.context_window, bool)
            or not isinstance(self.context_window, int)
            or self.context_window <= 0
        ):
            msg = "context_window must be a positive integer"
            raise ValueError(msg)

        if (
            isinstance(self.max_output_tokens, bool)
            or not isinstance(self.max_output_tokens, int)
            or self.max_output_tokens <= 0
        ):
            msg = "max_output_tokens must be a positive integer"
            raise ValueError(msg)

        if not isinstance(self.supports_tools, bool):
            msg = "supports_tools must be a boolean"
            raise ValueError(msg)

        if not isinstance(self.supports_streaming, bool):
            msg = "supports_streaming must be a boolean"
            raise ValueError(msg)

        if not isinstance(self.cost_per_input_token, (int, float)) or self.cost_per_input_token < 0:
            msg = "cost_per_input_token must be a non-negative number"
            raise ValueError(msg)

        if not isinstance(self.cost_per_output_token, (int, float)) or self.cost_per_output_token < 0:
            msg = "cost_per_output_token must be a non-negative number"
            raise ValueError(msg)

        if not isinstance(self.metadata, MappingProxyType):
            msg = "metadata must be a dict or MappingProxyType"
            raise ValueError(msg)


@dataclass(frozen=True)
class UsageStats:
    """Usage statistics for the LLM provider.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation. By-model dict is converted
    to MappingProxyType for immutability.
    """

    total_requests: int
    total_tokens: int
    input_tokens: int
    output_tokens: int
    total_cost: float
    period_start: datetime
    period_end: datetime
    by_model: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        # Coerce dict to MappingProxyType for by_model
        if isinstance(self.by_model, dict):
            object.__setattr__(self, "by_model", MappingProxyType(self.by_model))

        if isinstance(self.total_requests, bool) or not isinstance(self.total_requests, int) or self.total_requests < 0:
            msg = "total_requests must be a non-negative integer"
            raise ValueError(msg)

        if isinstance(self.total_tokens, bool) or not isinstance(self.total_tokens, int) or self.total_tokens < 0:
            msg = "total_tokens must be a non-negative integer"
            raise ValueError(msg)

        if isinstance(self.input_tokens, bool) or not isinstance(self.input_tokens, int) or self.input_tokens < 0:
            msg = "input_tokens must be a non-negative integer"
            raise ValueError(msg)

        if isinstance(self.output_tokens, bool) or not isinstance(self.output_tokens, int) or self.output_tokens < 0:
            msg = "output_tokens must be a non-negative integer"
            raise ValueError(msg)

        if not isinstance(self.total_cost, (int, float)) or self.total_cost < 0:
            msg = "total_cost must be a non-negative number"
            raise ValueError(msg)

        if not isinstance(self.period_start, datetime):
            msg = "period_start must be a datetime instance"
            raise ValueError(msg)

        if not isinstance(self.period_end, datetime):
            msg = "period_end must be a datetime instance"
            raise ValueError(msg)

        if not isinstance(self.by_model, MappingProxyType):
            msg = "by_model must be a dict or MappingProxyType"
            raise ValueError(msg)


# Type alias for stream callback
StreamCallback = Callable[[StreamChunk], Awaitable[None]]

# Type alias for LLM provider factory
# Takes an agent name and returns a configured ILLMProvider instance
AgentLLMFactory = Callable[..., "ILLMProvider"]


# ============================================================================
# Port Interface
# ============================================================================


class ILLMProvider(ABC):
    """
    Interface for Large Language Model providers.

    This port abstracts LLM operations, supporting various providers
    like Claude, GPT-4, and local models. For Codetoreum, providers
    run in containerized environments with context mounted as files.
    """

    # Core Execution

    @abstractmethod
    async def execute(
        self,
        prompt: str,
        context: ExecutionContext | None = None,
        stream_callback: StreamCallback | None = None,
    ) -> ExecutionResult:
        """
        Execute a prompt with the LLM.

        Args:
            prompt: The prompt to execute (may reference mounted context files)
            context: Execution context with parameters and mounted paths
            stream_callback: Optional callback for streaming responses

        Returns:
            ExecutionResult: Execution result with response and metadata

        Raises:
            PromptTooLongError: Prompt exceeds token limit
            RateLimitError: Provider rate limit exceeded
            AuthenticationError: Invalid credentials
            ExternalServiceError: Provider service error
        """

    @abstractmethod
    async def execute_with_tools(
        self,
        prompt: str,
        tools: list[ToolDefinition],
        context: ExecutionContext | None = None,
        stream_callback: StreamCallback | None = None,
    ) -> ExecutionResult:
        """
        Execute prompt with tool/function calling capabilities.

        Args:
            prompt: The prompt to execute
            tools: Available tools for the LLM to use
            context: Execution context
            stream_callback: Optional streaming callback

        Returns:
            ExecutionResult: Result with tool calls and responses

        Raises:
            ToolExecutionError: Tool execution failed
            UnsupportedFeatureError: Provider doesn't support tools
            PromptTooLongError: Prompt exceeds token limit
            RateLimitError: Provider rate limit exceeded
            ExternalServiceError: Provider service error
        """

    # Streaming

    @abstractmethod
    async def stream_completion(
        self,
        prompt: str,
        context: ExecutionContext | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream completion tokens as they're generated.

        Args:
            prompt: The prompt to execute
            context: Execution context

        Yields:
            StreamChunk: Streaming response chunks

        Raises:
            StreamingError: Streaming failure
            UnsupportedFeatureError: Provider doesn't support streaming
            PromptTooLongError: Prompt exceeds token limit
            RateLimitError: Provider rate limit exceeded
        """

    # Conversation Management

    @abstractmethod
    async def create_conversation(
        self,
        system_prompt: str | None = None,
        parameters: ExecutionContext | None = None,
    ) -> str:
        """
        Create a new conversation session.

        Args:
            system_prompt: System instructions
            parameters: Model parameters

        Returns:
            str: Unique conversation identifier

        Raises:
            ExternalServiceError: Provider service error
        """

    @abstractmethod
    async def continue_conversation(
        self,
        conversation_id: str,
        message: str,
        stream_callback: StreamCallback | None = None,
    ) -> ExecutionResult:
        """
        Continue an existing conversation.

        Args:
            conversation_id: Conversation to continue
            message: New message in conversation
            stream_callback: Optional streaming callback

        Returns:
            ExecutionResult: Response in conversation context

        Raises:
            ConversationNotFoundError: Conversation doesn't exist
            ConversationExpiredError: Conversation has expired
            RateLimitError: Provider rate limit exceeded
        """

    # Model Information

    @abstractmethod
    async def get_model_info(self) -> ModelInfo:
        """
        Get information about the current model.

        Returns:
            ModelInfo: Model information

        Raises:
            ExternalServiceError: Provider service error
        """

    @abstractmethod
    async def list_available_models(self) -> list[ModelInfo]:
        """
        List all available models from this provider.

        Returns:
            List[ModelInfo]: List of available models

        Raises:
            ExternalServiceError: Provider service error
        """

    # Token Management

    @abstractmethod
    async def count_tokens(
        self,
        text: str,
        model: str | None = None,
    ) -> int:
        """
        Count tokens in text.

        Args:
            text: Text to count tokens for
            model: Optional model identifier (uses default if not specified)

        Returns:
            int: Token count

        Raises:
            ExternalServiceError: Provider service error
        """

    @abstractmethod
    async def get_usage_stats(
        self,
        since: datetime | None = None,
    ) -> UsageStats:
        """
        Get usage statistics (token usage and costs).

        Args:
            since: Start time for statistics period

        Returns:
            UsageStats: Usage statistics

        Raises:
            ExternalServiceError: Provider service error
        """
