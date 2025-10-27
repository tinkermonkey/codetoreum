"""Unit tests for MockLLMAdapter."""

import pytest

from codetoreum.adapters.testing import MockLLMAdapter
from codetoreum.ports.exceptions import ValidationError
from codetoreum.ports.output.llm_provider import ExecutionContext, ToolDefinition


@pytest.mark.asyncio
class TestMockLLMAdapter:
    """Tests for MockLLMAdapter."""

    @pytest.fixture
    def adapter(self):
        """Create adapter instance."""
        return MockLLMAdapter(default_response="Mock response")

    async def test_execute_basic(self, adapter):
        """Test basic execution."""
        result = await adapter.execute("Hello, how are you?")

        assert result.content == "Mock response"
        assert result.role == "assistant"
        assert result.prompt_tokens > 0
        assert result.completion_tokens > 0

    async def test_execute_empty_prompt(self, adapter):
        """Test execution with empty prompt raises error."""
        with pytest.raises(ValidationError):
            await adapter.execute("")

    async def test_execute_with_pattern(self, adapter):
        """Test execution with pattern matching."""
        adapter.add_response_pattern(r"calculate", "The answer is 42")

        result = await adapter.execute("Please calculate 40 + 2")
        assert result.content == "The answer is 42"

    async def test_execute_with_delay(self):
        """Test execution with simulated delay."""
        adapter = MockLLMAdapter(delay_seconds=0.01)

        import time
        start = time.time()
        await adapter.execute("Test")
        duration = time.time() - start

        assert duration >= 0.01

    async def test_execute_with_tools(self, adapter):
        """Test execution with tools."""
        tools = [
            ToolDefinition(
                name="calculator",
                description="Calculate math expressions",
                parameters={"expression": "string"},
            )
        ]

        result = await adapter.execute_with_tools(
            "Use calculator to compute 5 + 3",
            tools,
        )

        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].tool_name == "calculator"

    async def test_stream_completion(self, adapter):
        """Test streaming completions."""
        chunks = []
        async for chunk in adapter.stream_completion("Tell me a story"):
            chunks.append(chunk)

        assert len(chunks) > 0
        assert chunks[-1].is_final

    async def test_create_conversation(self, adapter):
        """Test creating a conversation."""
        conv_id = await adapter.create_conversation(
            system_prompt="You are a helpful assistant"
        )

        assert conv_id is not None

    async def test_continue_conversation(self, adapter):
        """Test continuing a conversation."""
        conv_id = await adapter.create_conversation()

        result = await adapter.continue_conversation(
            conv_id,
            "Hello",
        )

        assert result.conversation_id == conv_id

    async def test_get_model_info(self, adapter):
        """Test getting model info."""
        info = await adapter.get_model_info()

        assert info.model_id == "mock-model-v1"
        assert info.provider == "mock"
        assert info.supports_tools
        assert info.supports_streaming

    async def test_list_available_models(self, adapter):
        """Test listing available models."""
        models = await adapter.list_available_models()

        assert len(models) >= 1
        assert any(m.model_id == "mock-model-v1" for m in models)

    async def test_count_tokens(self, adapter):
        """Test counting tokens."""
        count = await adapter.count_tokens("Hello world how are you")

        assert count == 5

    async def test_get_usage_stats(self, adapter):
        """Test getting usage stats."""
        await adapter.execute("Test 1")
        await adapter.execute("Test 2")

        stats = await adapter.get_usage_stats()

        assert stats.total_requests == 2
        assert stats.total_tokens > 0

    async def test_reset_stats(self, adapter):
        """Test resetting stats."""
        await adapter.execute("Test")

        adapter.reset_stats()
        stats = await adapter.get_usage_stats()

        assert stats.total_requests == 0

    async def test_clear_patterns(self, adapter):
        """Test clearing response patterns."""
        adapter.add_response_pattern("test", "response")
        adapter.clear_patterns()

        result = await adapter.execute("test")
        assert result.content == "Mock response"

    async def test_multiple_patterns(self, adapter):
        """Test multiple response patterns."""
        adapter.add_response_pattern(r"hello", "Hi there!")
        adapter.add_response_pattern(r"goodbye", "See you later!")

        result1 = await adapter.execute("hello world")
        assert result1.content == "Hi there!"

        result2 = await adapter.execute("goodbye friend")
        assert result2.content == "See you later!"
