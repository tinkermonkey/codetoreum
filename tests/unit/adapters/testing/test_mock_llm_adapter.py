"""Unit tests for MockLLMAdapter."""

import time

import pytest

from codetoreum.adapters.testing import MockLLMAdapter
from codetoreum.infrastructure.simulation.simulation_config import (
    FidelityLevel,
    SimulationConfig,
)
from codetoreum.ports.exceptions import ValidationError
from codetoreum.ports.output.llm_provider import ToolDefinition


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
        conv_id = await adapter.create_conversation(system_prompt="You are a helpful assistant")

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

    async def test_proportional_timing_low_fidelity(self):
        """Test LOW fidelity level has zero delay."""
        config = SimulationConfig.create_fast_config(
            "test",
            fidelity_level=FidelityLevel.LOW,
            ms_per_token=50.0,
        )
        adapter = MockLLMAdapter(config=config)

        start = time.time()
        await adapter.execute("short prompt")
        duration = time.time() - start

        # LOW fidelity should have minimal delay
        assert duration < 0.05

    async def test_proportional_timing_medium_fidelity_scales_with_tokens(self):
        """Test MEDIUM fidelity latency scales with token count."""
        config = SimulationConfig.create_fast_config(
            "test",
            fidelity_level=FidelityLevel.MEDIUM,
            ms_per_token=10.0,  # Reduced for fast test
            speed_multiplier=1.0,  # Real-time for measurement
        )
        adapter = MockLLMAdapter(config=config)
        # Register a response pattern to ensure we get the long response
        adapter.add_response_pattern(
            r"test.*test",
            "ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok ok",
        )

        # Short prompt (estimated ~50 tokens total)
        short_prompt = "test"
        start = time.time()
        await adapter.execute(short_prompt)
        duration_short = time.time() - start

        # Long prompt (estimated ~500+ tokens total)
        long_prompt = "test " * 50
        start = time.time()
        await adapter.execute(long_prompt)
        duration_long = time.time() - start

        # Latency should scale approximately with token count
        # Longer response should take noticeably more time
        assert duration_long > duration_short * 2, f"Expected ~5x+ scaling, got {duration_long / duration_short:.1f}x"

    async def test_proportional_timing_high_fidelity_scales_with_tokens(self):
        """Test HIGH fidelity latency scales with token count."""
        config = SimulationConfig.create_fast_config(
            "test",
            fidelity_level=FidelityLevel.HIGH,
            ms_per_token=50.0,
            speed_multiplier=1.0,  # Real-time for measurement
        )
        adapter = MockLLMAdapter(config=config)

        # Short prompt
        short_prompt = "test"
        start = time.time()
        await adapter.execute(short_prompt)
        duration_short = time.time() - start

        # Long prompt
        long_prompt = "test " * 100
        start = time.time()
        await adapter.execute(long_prompt)
        duration_long = time.time() - start

        # Latency should scale with tokens
        assert duration_long > duration_short * 3

    async def test_proportional_timing_with_custom_clock(self):
        """Test proportional timing works with SimulationClock."""
        from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock

        config = SimulationConfig.create_fast_config(
            "test",
            fidelity_level=FidelityLevel.MEDIUM,
            ms_per_token=100.0,
            speed_multiplier=10.0,  # 10x faster
        )
        clock = SimulationClock(speed_multiplier=10.0)

        adapter = MockLLMAdapter(config=config, clock=clock)

        start = time.time()
        await adapter.execute("short test")
        duration = time.time() - start

        # With 10x multiplier, delays should be ~1/10th of real time
        # We expect minimal delay due to simulated fast execution
        assert duration < 0.5
