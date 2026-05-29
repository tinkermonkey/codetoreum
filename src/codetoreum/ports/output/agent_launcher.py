"""IAgentLauncher output port interface.

Models autonomous-agent launchers — subprocess-based agentic CLIs that run
their own internal agentic loop inside a workspace. Examples: Claude Code
(``claude --print``), Aider, Cursor CLI, OpenAI Codex CLI.

Sibling port to ``ILLMTextProvider``. See
``documentation/architecture/ports/output/agent-launcher.md`` for rationale.

Key semantic differences from ``ILLMTextProvider``:

- ``execute`` runs an autonomous agent process inside ``context.working_directory``.
  The "completion" is the agent\'s final summary, not a token stream from a single
  prompt. Duration is bounded by ``context.timeout_seconds`` but capability is
  not bounded — the subprocess can read files, edit code, and shell out within
  its own loop.
- Errors are categorized by subprocess lifecycle (process not found, exit code,
  timeout, signal) rather than HTTP categories.
- ``count_tokens`` is approximated from logs/stdout; ``list_available_models``
  is hard-coded per CLI rather than fetched from an API.
- ``create_conversation`` / ``continue_conversation`` are emulated locally
  (history is replayed into the next subprocess invocation), not API-managed.

The current ``ILLMProvider`` port is an alias of ``IAgentLauncher`` because the
sole production implementation (``ClaudeCodeAdapter``) is an agent launcher.
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


class IAgentLauncher(ABC):
    """
    Interface for autonomous-agent launchers.

    Implementations launch a subprocess (Claude Code, Aider, Cursor CLI, etc.)
    that runs its own internal agentic loop in a workspace, then returns the
    agent\'s final result.

    Distinct from ``ILLMTextProvider``: the launcher\'s ``execute`` does not
    correspond to a single prompt-to-completion API call — it corresponds to an
    autonomous agentic session.
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
        Launch an agent subprocess to execute a prompt autonomously.

        The agent runs in ``context.working_directory`` and may read/edit files,
        execute shell commands, and make multi-step decisions within its own
        loop. Codetoreum awaits the subprocess; capability is not bounded by
        the duration.

        Args:
            prompt: Task description for the agent (may reference mounted context files)
            context: Execution context with working directory and parameters
            stream_callback: Optional callback for streaming chunks of the agent\'s
                output (typically the agent\'s final assistant message)

        Returns:
            ExecutionResult: Result with the agent\'s final summary and metadata

        Raises:
            PromptTooLongError: Prompt exceeds size limit
            RateLimitError: Underlying LLM provider rate limit exceeded
            AuthenticationError: Invalid credentials passed to the subprocess
            ExternalServiceError: Subprocess failure (timeout, non-zero exit, signal)
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
        Launch an agent subprocess with additional tool definitions.

        For most agent-launcher implementations (Claude Code, Aider) tool
        definitions are conveyed via MCP servers configured in the workspace
        rather than direct CLI arguments. Implementations may treat ``tools``
        as informational or raise ``UnsupportedFeatureError``.

        Args:
            prompt: Task description for the agent
            tools: Tool definitions (typically informational for CLI agents)
            context: Execution context (must include MCP configuration if tools required)
            stream_callback: Optional streaming callback

        Returns:
            ExecutionResult: Result with tool-use metadata

        Raises:
            UnsupportedFeatureError: Launcher does not support custom tool definitions
            ExternalServiceError: Subprocess failure
        """

    # Streaming

    @abstractmethod
    async def stream_completion(
        self,
        prompt: str,
        context: ExecutionContext | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream chunks of the agent\'s output as they\'re generated.

        Note: this streams chunks of the agent\'s interleaved output, not raw
        tokens — text providers stream tokens, agent launchers stream
        assistant-text segments interleaved with tool calls.

        Args:
            prompt: Task description for the agent
            context: Execution context

        Yields:
            StreamChunk: Chunks of the agent\'s output

        Raises:
            StreamingError: Streaming failure
            UnsupportedFeatureError: Launcher doesn\'t support streaming
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

        For agent launchers, conversations are emulated locally — the launcher
        stores a history that is replayed into subsequent subprocess invocations
        via ``continue_conversation``. Subprocess sessions themselves are not
        persistent.

        Args:
            system_prompt: System instructions to prepend to subsequent prompts
            parameters: Default execution parameters

        Returns:
            str: Locally-generated conversation identifier
        """

    @abstractmethod
    async def continue_conversation(
        self,
        conversation_id: str,
        message: str,
        stream_callback: StreamCallback | None = None,
    ) -> ExecutionResult:
        """
        Continue an existing conversation with a new message.

        The launcher prepends the conversation history to the prompt before
        invoking the agent subprocess. Subprocess state is not persistent
        between calls.

        Args:
            conversation_id: Identifier returned by ``create_conversation``
            message: New user message
            stream_callback: Optional streaming callback

        Returns:
            ExecutionResult: Agent\'s response in the conversation context

        Raises:
            ConversationNotFoundError: Conversation doesn\'t exist
            ExternalServiceError: Subprocess failure
        """

    # Model Information

    @abstractmethod
    async def get_model_info(self) -> ModelInfo:
        """
        Get information about the model the launcher uses.

        For agent launchers this is typically hard-coded per CLI (Claude Code →
        Claude Sonnet 4.5, etc.) rather than fetched from a model-listing API.

        Returns:
            ModelInfo: Model information
        """

    @abstractmethod
    async def list_available_models(self) -> list[ModelInfo]:
        """
        List models the launcher\'s underlying CLI supports.

        Typically hard-coded per CLI implementation; not fetched from a remote
        API.

        Returns:
            List[ModelInfo]: List of available models
        """

    # Token Management

    @abstractmethod
    async def count_tokens(
        self,
        text: str,
        model: str | None = None,
    ) -> int:
        """
        Approximate the number of tokens in ``text``.

        Agent launchers typically approximate (e.g. ~4 chars/token) because the
        CLI subprocess does not expose a token-counting endpoint. For exact
        counts, use ``ILLMTextProvider.count_tokens`` instead.

        Args:
            text: Text to estimate tokens for
            model: Optional model identifier (uses default if not specified)

        Returns:
            int: Approximate token count
        """

    @abstractmethod
    async def get_usage_stats(
        self,
        since: datetime | None = None,
    ) -> UsageStats:
        """
        Get usage statistics tracked by the launcher.

        Note: These are launcher-tracked statistics (parsed from subprocess
        logs), not authoritative billing data. For accurate billing, consult
        the underlying provider\'s console.

        Args:
            since: Start time for statistics period (may be ignored)

        Returns:
            UsageStats: Adapter-tracked usage statistics
        """
