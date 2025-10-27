"""Mock LLM provider adapter for testing."""

import asyncio
import re
from datetime import datetime, timezone
from typing import AsyncIterator, Dict, List, Optional, Pattern
from uuid import uuid4

from codetoreum.ports.exceptions import (
    RateLimitError,
    UnsupportedFeatureError,
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


class MockLLMAdapter(ILLMProvider):
    """
    Mock LLM provider for testing.

    Returns predefined responses based on prompt patterns. Useful for
    deterministic testing without calling real LLM APIs.
    """

    def __init__(
        self,
        default_response: str = "Mock LLM response",
        delay_seconds: float = 0.0,
        simulate_rate_limits: bool = False,
    ):
        """
        Initialize the mock LLM adapter.

        Args:
            default_response: Default response text when no pattern matches
            delay_seconds: Simulated execution delay
            simulate_rate_limits: Whether to simulate rate limiting
        """
        self._default_response = default_response
        self._delay_seconds = delay_seconds
        self._simulate_rate_limits = simulate_rate_limits

        # Pattern-based responses
        self._response_patterns: List[tuple[Pattern, str]] = []

        # Usage tracking
        self._total_requests = 0
        self._total_tokens = 0
        self._input_tokens = 0
        self._output_tokens = 0

        # Conversations
        self._conversations: Dict[str, List[Dict[str, str]]] = {}

        # Model info
        self._model_info = ModelInfo(
            model_id="mock-model-v1",
            provider="mock",
            display_name="Mock Model v1",
            context_window=100000,
            max_output_tokens=4096,
            supports_tools=True,
            supports_streaming=True,
            cost_per_input_token=0.0,
            cost_per_output_token=0.0,
        )

    def add_response_pattern(self, pattern: str, response: str) -> None:
        """
        Add a pattern-based response.

        Args:
            pattern: Regex pattern to match against prompts
            response: Response to return when pattern matches
        """
        compiled_pattern = re.compile(pattern, re.IGNORECASE | re.DOTALL)
        self._response_patterns.append((compiled_pattern, response))

    def _get_response_for_prompt(self, prompt: str) -> str:
        """Get response for a given prompt based on patterns."""
        for pattern, response in self._response_patterns:
            if pattern.search(prompt):
                return response
        return self._default_response

    async def execute(
        self,
        prompt: str,
        context: Optional[ExecutionContext] = None,
        stream_callback: Optional[StreamCallback] = None,
    ) -> ExecutionResult:
        """Execute a prompt with the LLM."""
        if not prompt or not prompt.strip():
            raise ValidationError("Prompt cannot be empty")

        if self._simulate_rate_limits and self._total_requests > 100:
            raise RateLimitError("Mock rate limit exceeded")

        # Simulate delay
        if self._delay_seconds > 0:
            await asyncio.sleep(self._delay_seconds)

        started_at = datetime.now(timezone.utc)

        # Get response
        response = self._get_response_for_prompt(prompt)

        # Calculate mock tokens
        prompt_tokens = len(prompt.split())
        completion_tokens = len(response.split())

        # Update usage stats
        self._total_requests += 1
        self._input_tokens += prompt_tokens
        self._output_tokens += completion_tokens
        self._total_tokens += prompt_tokens + completion_tokens

        completed_at = datetime.now(timezone.utc)
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
        tools: List[ToolDefinition],
        context: Optional[ExecutionContext] = None,
        stream_callback: Optional[StreamCallback] = None,
    ) -> ExecutionResult:
        """Execute prompt with tool/function calling capabilities."""
        # For mock, just execute normally and optionally include tool calls
        result = await self.execute(prompt, context, stream_callback)

        # Check if prompt mentions any tool names, simulate tool call
        tool_calls = []
        for tool in tools:
            if tool.name.lower() in prompt.lower():
                tool_calls.append(
                    ToolCall(
                        tool_name=tool.name,
                        arguments={},
                        call_id=str(uuid4()),
                    )
                )

        result.tool_calls = tool_calls
        return result

    async def stream_completion(
        self,
        prompt: str,
        context: Optional[ExecutionContext] = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream completion tokens as they're generated."""
        if not prompt or not prompt.strip():
            raise ValidationError("Prompt cannot be empty")

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
                timestamp=datetime.now(timezone.utc),
            )
            yield chunk

    async def _simulate_streaming(
        self,
        response: str,
        callback: StreamCallback,
    ) -> None:
        """Simulate streaming by calling callback with chunks."""
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
        system_prompt: Optional[str] = None,
        parameters: Optional[ExecutionContext] = None,
    ) -> str:
        """Create a new conversation session."""
        conversation_id = str(uuid4())
        self._conversations[conversation_id] = []

        if system_prompt:
            self._conversations[conversation_id].append({
                "role": "system",
                "content": system_prompt,
            })

        return conversation_id

    async def continue_conversation(
        self,
        conversation_id: str,
        message: str,
        stream_callback: Optional[StreamCallback] = None,
    ) -> ExecutionResult:
        """Continue an existing conversation."""
        if conversation_id not in self._conversations:
            from codetoreum.ports.exceptions import ConversationNotFoundError
            raise ConversationNotFoundError(f"Conversation {conversation_id} not found")

        # Add user message
        self._conversations[conversation_id].append({
            "role": "user",
            "content": message,
        })

        # Execute
        context = ExecutionContext(conversation_id=conversation_id)
        result = await self.execute(message, context, stream_callback)

        # Add assistant response
        self._conversations[conversation_id].append({
            "role": "assistant",
            "content": result.content,
        })

        return result

    async def get_model_info(self) -> ModelInfo:
        """Get information about the current model."""
        return self._model_info

    async def list_available_models(self) -> List[ModelInfo]:
        """List all available models from this provider."""
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
            ),
        ]

    async def count_tokens(
        self,
        text: str,
        model: Optional[str] = None,
    ) -> int:
        """Count tokens in text."""
        # Simple word-based token counting for mock
        return len(text.split())

    async def get_usage_stats(
        self,
        since: Optional[datetime] = None,
    ) -> UsageStats:
        """Get usage statistics."""
        return UsageStats(
            total_requests=self._total_requests,
            total_tokens=self._total_tokens,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            total_cost=0.0,
            period_start=since or datetime.now(timezone.utc),
            period_end=datetime.now(timezone.utc),
            by_model={
                self._model_info.model_id: {
                    "requests": self._total_requests,
                    "tokens": self._total_tokens,
                }
            },
        )

    # Helper methods for testing

    def reset_stats(self) -> None:
        """Reset usage statistics."""
        self._total_requests = 0
        self._total_tokens = 0
        self._input_tokens = 0
        self._output_tokens = 0

    def clear_conversations(self) -> None:
        """Clear all conversations."""
        self._conversations.clear()

    def clear_patterns(self) -> None:
        """Clear all response patterns."""
        self._response_patterns.clear()

    def set_default_response(self, response: str) -> None:
        """Set the default response text."""
        self._default_response = response

    def get_request_count(self) -> int:
        """Get total number of requests made."""
        return self._total_requests
