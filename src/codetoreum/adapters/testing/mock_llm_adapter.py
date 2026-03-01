"""Mock LLM provider adapter for testing."""

import asyncio
import re
import threading
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from re import Pattern
from typing import TYPE_CHECKING
from uuid import uuid4

from codetoreum.ports.exceptions import (
    RateLimitError,
    ValidationError,
)
from codetoreum.ports.output.llm_provider import (
    ExecutionContext,
    ExecutionResult,
    ILLMProvider,
    ModelInfo,
    StreamCallback,
    StreamChunk,
    ToolCall,
    ToolDefinition,
    UsageStats,
)

if TYPE_CHECKING:
    from codetoreum.infrastructure.simulation.proportional_delay_calculator import (
        ProportionalDelayCalculator,
    )
    from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
    from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig


class MockLLMAdapter(ILLMProvider):
    """
    Mock LLM provider for testing.

    Returns predefined responses based on prompt patterns. Useful for
    deterministic testing without calling real LLM APIs.

    This adapter is thread-safe for concurrent test execution. All shared
    state modifications are protected by a lock.

    Attributes:
        _default_response: Default response when no pattern matches
        _delay_seconds: Simulated execution delay
        _simulate_rate_limits: Whether to simulate rate limiting behavior
    """

    def __init__(
        self,
        default_response: str = "Mock LLM response",
        delay_seconds: float = 0.0,
        simulate_rate_limits: bool = False,
        model_name: str = "mock-model-v1",
        cost_per_input_token: float = 0.0,
        cost_per_output_token: float = 0.0,
        context_window: int = 100000,
        max_output_tokens: int = 4096,
        config: "SimulationConfig | None" = None,
        clock: "SimulationClock | None" = None,
    ):
        """
        Initialize the mock LLM adapter.

        Args:
            default_response: Default response text when no pattern matches
            delay_seconds: Simulated execution delay in seconds
            simulate_rate_limits: Whether to simulate rate limiting (fails after 100 requests)
            model_name: Name of the mock model
            cost_per_input_token: Cost per input token (default: 0.0 for testing)
            cost_per_output_token: Cost per output token (default: 0.0 for testing)
            context_window: Maximum context window size
            max_output_tokens: Maximum output tokens
            config: Optional SimulationConfig for fidelity-based timing
            clock: Optional SimulationClock for time manipulation
        """
        if delay_seconds < 0:
            msg = "Delay seconds cannot be negative"
            raise ValidationError(msg)

        self._default_response = default_response
        self._delay_seconds = delay_seconds
        self._simulate_rate_limits = simulate_rate_limits
        self._config = config
        self._clock = clock

        # Lazy-load delay calculator to avoid circular import
        self._delay_calculator: ProportionalDelayCalculator | None = None

        # Pattern-based responses
        self._response_patterns: list[tuple[Pattern, str]] = []

        # Usage tracking
        self._total_requests = 0
        self._total_tokens = 0
        self._input_tokens = 0
        self._output_tokens = 0

        # Conversations
        self._conversations: dict[str, list[dict[str, str]]] = {}

        # Model info (configurable)
        self._model_info = ModelInfo(
            model_id=model_name,
            provider="mock",
            display_name=model_name.replace("-", " ").title(),
            context_window=context_window,
            max_output_tokens=max_output_tokens,
            supports_tools=True,
            supports_streaming=True,
            cost_per_input_token=cost_per_input_token,
            cost_per_output_token=cost_per_output_token,
        )

        # Thread safety
        self._lock = threading.Lock()

        # Counter for probabilistic failures (deterministic for reproducibility)
        self._execution_counter = 0

    def add_response_pattern(self, pattern: str, response: str) -> None:
        """
        Add a pattern-based response.

        Args:
            pattern: Regex pattern to match against prompts
            response: Response to return when pattern matches

        Raises:
            ValidationError: If pattern or response is empty
        """
        if not pattern:
            msg = "Pattern cannot be empty"
            raise ValidationError(msg)
        if not response:
            msg = "Response cannot be empty"
            raise ValidationError(msg)

        compiled_pattern = re.compile(pattern, re.IGNORECASE | re.DOTALL)
        with self._lock:
            self._response_patterns.append((compiled_pattern, response))

    def _should_fail_for_high_fidelity(self) -> bool:
        """
        Determine if execution should fail based on HIGH fidelity probabilistic failures.

        Uses counter-based approach for reproducibility in tests (not random).
        Only applies to HIGH fidelity level.

        Returns:
            True if execution should timeout/fail, False otherwise
        """
        if not self._config:
            return False

        from codetoreum.infrastructure.simulation.simulation_config import FidelityLevel

        if self._config.fidelity_level != FidelityLevel.HIGH:
            return False

        # Counter-based: fail approximately every 25 executions (~4% failure rate)
        # This is deterministic for reproducibility
        with self._lock:
            self._execution_counter += 1
            should_fail = self._execution_counter % 25 == 0

        return should_fail

    def _get_response_for_prompt(self, prompt: str) -> str:
        """
        Get response for a given prompt based on patterns.

        Args:
            prompt: The input prompt

        Returns:
            Response string (either pattern-matched or default)
        """
        with self._lock:
            for pattern, response in self._response_patterns:
                if pattern.search(prompt):
                    return response
            return self._default_response

    def _calculate_delay_seconds(self, prompt: str, response: str) -> float:
        """
        Calculate delay based on fidelity level and token count.

        Uses ProportionalDelayCalculator for centralized fidelity-aware timing.
        Falls back to fixed delay_seconds if no config provided.

        Args:
            prompt: The input prompt
            response: The generated response

        Returns:
            Delay in seconds
        """
        if not self._config:
            return self._delay_seconds

        if self._delay_calculator is None:
            from codetoreum.infrastructure.simulation.proportional_delay_calculator import (
                ProportionalDelayCalculator,
            )

            self._delay_calculator = ProportionalDelayCalculator(self._config)
        return self._delay_calculator.calculate_llm_delay(prompt, response)

    async def execute(
        self,
        prompt: str,
        context: ExecutionContext | None = None,
        stream_callback: StreamCallback | None = None,
    ) -> ExecutionResult:
        """
        Execute a prompt with the LLM.

        Args:
            prompt: The prompt to execute (required, non-empty)
            context: Optional execution context
            stream_callback: Optional callback for streaming

        Returns:
            Execution result with generated content

        Raises:
            ValidationError: If prompt is empty
            RateLimitError: If rate limits are simulated and exceeded or HIGH fidelity
        """
        if not prompt or not prompt.strip():
            msg = "Prompt cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            if self._simulate_rate_limits and self._total_requests >= 100:
                msg = "Mock rate limit exceeded (100 requests)"
                raise RateLimitError(msg)

        # HIGH fidelity: probabilistic timeout/failure
        if self._should_fail_for_high_fidelity():
            msg = "LLM execution timeout (HIGH fidelity probabilistic failure)"
            raise RateLimitError(msg)

        started_at = datetime.now(UTC)

        # Get response
        response = self._get_response_for_prompt(prompt)

        # Calculate delay based on fidelity level
        delay_seconds = self._calculate_delay_seconds(prompt, response)

        # Apply delay using clock if available, otherwise use asyncio.sleep
        if delay_seconds > 0:
            if self._clock:
                # Use simulated clock for time manipulation support
                await self._clock.sleep(delay_seconds)
            else:
                # Fall back to asyncio.sleep for real-time execution
                await asyncio.sleep(delay_seconds)

        # Calculate mock tokens
        prompt_tokens = len(prompt.split())
        completion_tokens = len(response.split())

        # Update usage stats
        with self._lock:
            self._total_requests += 1
            self._input_tokens += prompt_tokens
            self._output_tokens += completion_tokens
            self._total_tokens += prompt_tokens + completion_tokens

        completed_at = datetime.now(UTC)
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)

        # If streaming callback provided, simulate streaming
        if stream_callback:
            await self._simulate_streaming(response, stream_callback)

        result = ExecutionResult(
            content=response,
            role="assistant",
            model=self._model_info.model_id,
            completion_tokens=completion_tokens,
            prompt_tokens=prompt_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            finish_reason="stop",
            conversation_id=context.conversation_id if context else None,
        )

        return result

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
            tools: List of available tools
            context: Optional execution context
            stream_callback: Optional callback for streaming

        Returns:
            Execution result with optional tool calls

        Raises:
            ValidationError: If prompt is empty or tools list is invalid
        """
        if not tools:
            msg = "Tools list cannot be empty for tool execution"
            raise ValidationError(msg)

        # For mock, just execute normally and optionally include tool calls
        result = await self.execute(prompt, context, stream_callback)

        # Check if prompt mentions any tool names, simulate tool call
        tool_calls = []
        prompt_lower = prompt.lower()
        for tool in tools:
            if tool.name and tool.name.lower() in prompt_lower:
                tool_calls.append(
                    ToolCall(
                        tool_name=tool.name,
                        arguments={},
                        call_id=str(uuid4()),
                    )
                )

        object.__setattr__(result, 'tool_calls', tuple(tool_calls))
        return result

    async def stream_completion(
        self,
        prompt: str,
        context: ExecutionContext | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream completion tokens as they're generated.

        Args:
            prompt: The prompt to execute
            context: Optional execution context

        Yields:
            StreamChunk objects with incremental content

        Raises:
            ValidationError: If prompt is empty
        """
        if not prompt or not prompt.strip():
            msg = "Prompt cannot be empty"
            raise ValidationError(msg)

        # Get response
        response = self._get_response_for_prompt(prompt)

        # Split into words and stream
        words = response.split()
        for i, word in enumerate(words):
            if self._delay_seconds > 0:
                await asyncio.sleep(self._delay_seconds / len(words))

            chunk = StreamChunk(
                content=word + (" " if i < len(words) - 1 else ""),
                chunk_index=i,
                is_final=(i == len(words) - 1),
                timestamp=datetime.now(UTC),
            )
            yield chunk

    async def _simulate_streaming(
        self,
        response: str,
        callback: StreamCallback,
    ) -> None:
        """
        Simulate streaming by calling callback with chunks.

        Args:
            response: The complete response to stream
            callback: Callback function to receive chunks
        """
        words = response.split()
        for i, word in enumerate(words):
            chunk = StreamChunk(
                content=word + (" " if i < len(words) - 1 else ""),
                chunk_index=i,
                is_final=(i == len(words) - 1),
            )
            await callback(chunk)

    async def create_conversation(
        self,
        system_prompt: str | None = None,
        parameters: ExecutionContext | None = None,
    ) -> str:
        """
        Create a new conversation session.

        Args:
            system_prompt: Optional system prompt to initialize conversation
            parameters: Optional execution parameters

        Returns:
            Unique conversation ID
        """
        conversation_id = str(uuid4())

        with self._lock:
            self._conversations[conversation_id] = []

            if system_prompt:
                self._conversations[conversation_id].append(
                    {
                        "role": "system",
                        "content": system_prompt,
                    }
                )

        return conversation_id

    async def continue_conversation(
        self,
        conversation_id: str,
        message: str,
        stream_callback: StreamCallback | None = None,
    ) -> ExecutionResult:
        """
        Continue an existing conversation.

        Args:
            conversation_id: ID of the conversation to continue
            message: User message to add
            stream_callback: Optional callback for streaming

        Returns:
            Execution result with assistant response

        Raises:
            ResourceNotFoundError: If conversation does not exist
            ValidationError: If message is empty
        """
        if not message or not message.strip():
            msg = "Message cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            if conversation_id not in self._conversations:
                from codetoreum.ports.exceptions import ResourceNotFoundError

                msg = "Conversation"
                raise ResourceNotFoundError(msg, conversation_id)

            # Add user message
            self._conversations[conversation_id].append(
                {
                    "role": "user",
                    "content": message,
                }
            )

        # Execute
        context = ExecutionContext(conversation_id=conversation_id)
        result = await self.execute(message, context, stream_callback)

        # Add assistant response
        with self._lock:
            self._conversations[conversation_id].append(
                {
                    "role": "assistant",
                    "content": result.content,
                }
            )

        return result

    async def get_model_info(self) -> ModelInfo:
        """
        Get information about the current model.

        Returns:
            ModelInfo object with model specifications
        """
        return self._model_info

    async def list_available_models(self) -> list[ModelInfo]:
        """
        List all available models from this provider.

        Returns:
            List of available model info objects
        """
        return [
            self._model_info,
            ModelInfo(
                model_id="mock-model-v2",
                provider="mock",
                display_name="Mock Model v2",
                context_window=200000,
                max_output_tokens=8192,
                supports_tools=True,
                supports_streaming=True,
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
            ),
        ]

    async def count_tokens(
        self,
        text: str,
        model: str | None = None,
    ) -> int:
        """
        Count tokens in text.

        Args:
            text: Text to count tokens for
            model: Optional model name (ignored in mock)

        Returns:
            Token count (simple word-based counting for mock)
        """
        if not text:
            return 0
        return len(text.split())

    async def get_usage_stats(
        self,
        since: datetime | None = None,
    ) -> UsageStats:
        """
        Get usage statistics.

        Args:
            since: Optional start timestamp for stats period

        Returns:
            Usage statistics object
        """
        with self._lock:
            return UsageStats(
                total_requests=self._total_requests,
                total_tokens=self._total_tokens,
                input_tokens=self._input_tokens,
                output_tokens=self._output_tokens,
                total_cost=0.0,
                period_start=since or datetime.now(UTC),
                period_end=datetime.now(UTC),
                by_model={
                    self._model_info.model_id: {
                        "requests": self._total_requests,
                        "tokens": self._total_tokens,
                    }
                },
            )

    # Helper methods for testing

    def reset_stats(self) -> None:
        """Reset usage statistics to zero."""
        with self._lock:
            self._total_requests = 0
            self._total_tokens = 0
            self._input_tokens = 0
            self._output_tokens = 0

    def clear_conversations(self) -> None:
        """Clear all conversation history."""
        with self._lock:
            self._conversations.clear()

    def clear_patterns(self) -> None:
        """Clear all response patterns."""
        with self._lock:
            self._response_patterns.clear()

    def set_default_response(self, response: str) -> None:
        """
        Set the default response text.

        Args:
            response: New default response

        Raises:
            ValidationError: If response is empty
        """
        if not response:
            msg = "Default response cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            self._default_response = response

    def get_request_count(self) -> int:
        """
        Get total number of requests made.

        Returns:
            Total request count
        """
        with self._lock:
            return self._total_requests
