"""ILLMTextProvider output port interface.

Models prompt-to-text LLM APIs — Anthropic API, OpenAI API, AWS Bedrock,
GCP Vertex AI, and similar. Sibling port to ``IAgentLauncher``.

There is no production adapter for ``ILLMTextProvider`` yet — this port
establishes the contract so an Anthropic API adapter, OpenAI API adapter, or
similar can be added cleanly in a later cycle (see Phase G of
``.claude/plans/bootstrap-breadth-axis-implementation.md``).

Key semantic differences from ``IAgentLauncher``:

- ``execute`` corresponds to a single prompt-to-completion HTTP request. There
  is no agentic loop, no working directory, no file editing inside the call.
- Errors are HTTP-shaped: rate limits, authentication, model-not-found,
  content filter, context-length-exceeded.
- ``count_tokens`` is exact (provider-side endpoint), not approximate.
- ``list_available_models`` reflects what the API actually returns at runtime.
- ``create_conversation`` / ``continue_conversation`` map onto provider-managed
  conversation state (where supported) or to a stateless message-history
  replay.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime

from codetoreum.ports.output.llm_provider import (
    ExecutionContext,
    ExecutionResult,
    ModelInfo,
    StreamCallback,
    StreamChunk,
    ToolDefinition,
    UsageStats,
)


class ILLMTextProvider(ABC):
    """
    Interface for prompt-to-text LLM API providers.

    Implementations call a remote API endpoint (Anthropic, OpenAI, Bedrock,
    Vertex) for each ``execute`` call. Unlike ``IAgentLauncher``, there is no
    subprocess and no agentic loop — the model returns a completion for the
    prompt and that is the result.
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
        Send a prompt to the LLM API and return the completion.

        Args:
            prompt: Prompt to send to the model
            context: Execution context (model selection, sampling parameters,
                conversation history)
            stream_callback: Optional callback for streaming token chunks

        Returns:
            ExecutionResult: Completion with text, token usage, and metadata

        Raises:
            PromptTooLongError: Prompt exceeds the model\'s context window
            RateLimitError: API rate limit exceeded
            AuthenticationError: Invalid API credentials
            ExternalServiceError: API error response
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
        Send a prompt with tool-use definitions and return the completion.

        Tool definitions are passed directly to the API (Anthropic
        ``tools=...``, OpenAI ``tools=...``). The model decides whether to
        invoke tools; tool execution itself is the caller\'s responsibility.

        Args:
            prompt: Prompt to send
            tools: Tool definitions to expose to the model
            context: Execution context
            stream_callback: Optional streaming callback

        Returns:
            ExecutionResult: Completion with ``tool_calls`` populated when the
                model elected to invoke tools

        Raises:
            ToolExecutionError: Tool result handling failed
            UnsupportedFeatureError: API doesn\'t support tool use for the model
        """

    # Streaming

    @abstractmethod
    async def stream_completion(
        self,
        prompt: str,
        context: ExecutionContext | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream completion tokens as the API generates them.

        Args:
            prompt: Prompt to send
            context: Execution context

        Yields:
            StreamChunk: Token chunks from the API stream

        Raises:
            StreamingError: Streaming failed mid-response
        """

    # Conversation Management

    @abstractmethod
    async def create_conversation(
        self,
        system_prompt: str | None = None,
        parameters: ExecutionContext | None = None,
    ) -> str:
        """
        Create a new conversation context.

        For APIs that maintain server-side conversation state (e.g. OpenAI
        Assistants), this returns the server-issued identifier. For stateless
        APIs (Anthropic Messages), this returns a locally-generated identifier
        and the adapter replays history on each call.

        Args:
            system_prompt: System instructions for the conversation
            parameters: Default model parameters

        Returns:
            str: Conversation identifier
        """

    @abstractmethod
    async def continue_conversation(
        self,
        conversation_id: str,
        message: str,
        stream_callback: StreamCallback | None = None,
    ) -> ExecutionResult:
        """
        Send a new message in an existing conversation.

        Args:
            conversation_id: Identifier from ``create_conversation``
            message: New user message
            stream_callback: Optional streaming callback

        Returns:
            ExecutionResult: Model\'s response in the conversation context

        Raises:
            ConversationNotFoundError: Conversation doesn\'t exist
            ConversationExpiredError: Conversation has expired (provider-dependent)
        """

    # Model Information

    @abstractmethod
    async def get_model_info(self) -> ModelInfo:
        """
        Get information about the configured default model.

        Returns:
            ModelInfo: Model specs (context window, max output, costs)
        """

    @abstractmethod
    async def list_available_models(self) -> list[ModelInfo]:
        """
        List all models available through this API.

        Implementations should query the provider\'s model-listing endpoint
        (e.g. ``models.list()``) rather than returning a hard-coded list.

        Returns:
            List[ModelInfo]: Available models
        """

    # Token Management

    @abstractmethod
    async def count_tokens(
        self,
        text: str,
        model: str | None = None,
    ) -> int:
        """
        Count tokens exactly using the provider\'s tokenizer.

        For APIs that expose a counting endpoint (Anthropic
        ``messages.count_tokens``, OpenAI tiktoken), implementations should
        use it for exact counts rather than approximations.

        Args:
            text: Text to count tokens for
            model: Optional model identifier (uses default if not specified)

        Returns:
            int: Exact token count
        """

    @abstractmethod
    async def get_usage_stats(
        self,
        since: datetime | None = None,
    ) -> UsageStats:
        """
        Get usage statistics, ideally from the provider\'s billing API.

        Args:
            since: Start time for statistics period

        Returns:
            UsageStats: Usage statistics (requests, tokens, cost)
        """
