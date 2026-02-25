"""ILLMProvider output port interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional

from codetoreum.domain.types import ExecutionId, UserId

# ============================================================================
# Data Models
# ============================================================================


@dataclass
class ExecutionContext:
    """Context for LLM execution."""

    # Model configuration
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0

    # Conversation context
    conversation_id: Optional[str] = None
    message_history: List[Dict[str, Any]] = field(default_factory=list)
    system_prompt: Optional[str] = None

    # Execution options
    timeout_seconds: int = 300
    retry_on_error: bool = True
    cache_response: bool = False

    # Workspace context (for containerized execution)
    working_directory: Optional[Path] = None
    mounted_context_files: Dict[str, Path] = field(default_factory=dict)
    available_files: List[str] = field(default_factory=list)
    environment_variables: Dict[str, str] = field(default_factory=dict)

    # MCP Server configuration
    mcp_servers: List[Dict[str, Any]] = field(default_factory=list)

    # Metadata
    user_id: Optional[UserId] = None
    session_id: Optional[str] = None
    execution_id: Optional[ExecutionId] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolDefinition:
    """Definition of a tool/function the LLM can call."""

    name: str
    description: str
    parameters: Dict[str, Any]
    required: List[str] = field(default_factory=list)


@dataclass
class ToolCall:
    """Represents a tool call made by the LLM."""

    tool_name: str
    arguments: Dict[str, Any]
    call_id: str


@dataclass
class ToolCallDelta:
    """Incremental update to a tool call (for streaming)."""

    call_id: str
    delta: Dict[str, Any]


@dataclass
class StreamChunk:
    """Single chunk in streaming response."""

    content: str
    chunk_index: int
    is_final: bool = False

    # Tool calls in progress
    tool_call_delta: Optional[ToolCallDelta] = None

    # Metadata
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """Result from LLM execution."""

    # Response content
    content: str
    role: str = "assistant"

    # Tool calls (if any)
    tool_calls: List[ToolCall] = field(default_factory=list)

    # Metadata
    model: Optional[str] = None
    completion_tokens: int = 0
    prompt_tokens: int = 0
    total_tokens: int = 0

    # Timing
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime = field(default_factory=datetime.utcnow)
    duration_ms: int = 0

    # Additional data
    finish_reason: str = "stop"
    conversation_id: Optional[str] = None
    cached: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_cost(self) -> float:
        """Calculate cost based on token usage (provider-specific)."""
        return 0.0


@dataclass
class ModelInfo:
    """Information about an LLM model."""

    model_id: str
    provider: str
    display_name: str
    context_window: int
    max_output_tokens: int
    supports_tools: bool = False
    supports_streaming: bool = False
    cost_per_input_token: float = 0.0
    cost_per_output_token: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UsageStats:
    """Usage statistics for the LLM provider."""

    total_requests: int
    total_tokens: int
    input_tokens: int
    output_tokens: int
    total_cost: float
    period_start: datetime
    period_end: datetime
    by_model: Dict[str, Dict[str, Any]] = field(default_factory=dict)


# Type alias for stream callback
StreamCallback = Callable[[StreamChunk], Awaitable[None]]


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
        context: Optional[ExecutionContext] = None,
        stream_callback: Optional[StreamCallback] = None,
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
        pass

    @abstractmethod
    async def execute_with_tools(
        self,
        prompt: str,
        tools: List[ToolDefinition],
        context: Optional[ExecutionContext] = None,
        stream_callback: Optional[StreamCallback] = None,
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
        pass

    # Streaming

    @abstractmethod
    async def stream_completion(
        self,
        prompt: str,
        context: Optional[ExecutionContext] = None,
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
        pass

    # Conversation Management

    @abstractmethod
    async def create_conversation(
        self,
        system_prompt: Optional[str] = None,
        parameters: Optional[ExecutionContext] = None,
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
        pass

    @abstractmethod
    async def continue_conversation(
        self,
        conversation_id: str,
        message: str,
        stream_callback: Optional[StreamCallback] = None,
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
        pass

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
        pass

    @abstractmethod
    async def list_available_models(self) -> List[ModelInfo]:
        """
        List all available models from this provider.

        Returns:
            List[ModelInfo]: List of available models

        Raises:
            ExternalServiceError: Provider service error
        """
        pass

    # Token Management

    @abstractmethod
    async def count_tokens(
        self,
        text: str,
        model: Optional[str] = None,
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
        pass

    @abstractmethod
    async def get_usage_stats(
        self,
        since: Optional[datetime] = None,
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
        pass
