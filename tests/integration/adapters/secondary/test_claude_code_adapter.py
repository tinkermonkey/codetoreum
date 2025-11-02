"""Integration tests for Claude Code Adapter.

These tests interact with the actual Claude Code CLI and require:
- Claude CLI installed and available in PATH
- Valid Anthropic API key
"""

import os
from pathlib import Path

import pytest

from codetoreum.adapters.secondary import ClaudeCodeAdapter, ClaudeCodeConfig
from codetoreum.ports.exceptions import AuthenticationError, LLMProviderError
from codetoreum.ports.output.llm_provider import ExecutionContext


@pytest.fixture
def claude_config():
    """Create Claude Code configuration from environment."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY environment variable not set")

    return ClaudeCodeConfig(
        default_model="claude-sonnet-4-5-20250929",
        output_format="stream-json",
        verbose=False,
        # credential_provider defaults to EnvironmentCredentialProvider which reads from env
    )


@pytest.fixture
def claude_adapter(claude_config):
    """Create Claude Code adapter instance."""
    return ClaudeCodeAdapter(claude_config)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_validate_configuration(claude_adapter):
    """Test configuration validation."""
    try:
        is_valid = await claude_adapter.validate_configuration()
        assert is_valid is True
    except LLMProviderError as e:
        if "not found" in str(e):
            pytest.skip("Claude CLI not installed")
        raise


@pytest.mark.integration
@pytest.mark.asyncio
async def test_simple_execution(claude_adapter):
    """Test simple prompt execution."""
    try:
        result = await claude_adapter.execute(
            "What is 2 + 2? Reply with just the number.",
            context=ExecutionContext(timeout_seconds=30),
        )

        assert result is not None
        assert result.content
        assert "4" in result.content
        assert result.total_tokens > 0
        assert result.completion_tokens > 0
        assert result.prompt_tokens > 0

    except LLMProviderError as e:
        if "not found" in str(e):
            pytest.skip("Claude CLI not installed")
        raise


@pytest.mark.integration
@pytest.mark.asyncio
async def test_streaming_execution(claude_adapter):
    """Test streaming prompt execution."""
    chunks_received = []

    async def stream_callback(chunk):
        chunks_received.append(chunk)

    try:
        result = await claude_adapter.execute(
            "Count from 1 to 3, one number per line.",
            context=ExecutionContext(timeout_seconds=30),
            stream_callback=stream_callback,
        )

        assert result is not None
        assert result.content
        assert len(chunks_received) > 0
        # Check that final chunk was sent
        assert any(chunk.is_final for chunk in chunks_received)

    except LLMProviderError as e:
        if "not found" in str(e):
            pytest.skip("Claude CLI not installed")
        raise


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stream_completion(claude_adapter):
    """Test async streaming generator."""
    try:
        chunks = []
        async for chunk in claude_adapter.stream_completion(
            "Say hello",
            context=ExecutionContext(timeout_seconds=30),
        ):
            chunks.append(chunk)

        assert len(chunks) > 0
        # Final chunk should be marked
        assert chunks[-1].is_final

    except LLMProviderError as e:
        if "not found" in str(e):
            pytest.skip("Claude CLI not installed")
        raise


@pytest.mark.integration
@pytest.mark.asyncio
async def test_conversation_management(claude_adapter):
    """Test conversation creation and continuation."""
    # Create conversation
    conversation_id = await claude_adapter.create_conversation(
        system_prompt="You are a helpful assistant.",
    )

    assert conversation_id is not None

    # Continue conversation
    result1 = await claude_adapter.continue_conversation(
        conversation_id,
        "My name is Alice.",
    )

    assert result1 is not None

    # Continue again
    result2 = await claude_adapter.continue_conversation(
        conversation_id,
        "What is my name?",
    )

    assert result2 is not None
    # Claude should remember the name
    assert "alice" in result2.content.lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_model_info(claude_adapter):
    """Test getting model information."""
    model_info = await claude_adapter.get_model_info()

    assert model_info is not None
    assert model_info.model_id
    assert model_info.provider == "Anthropic"
    assert model_info.context_window > 0
    assert model_info.max_output_tokens > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_available_models(claude_adapter):
    """Test listing available models."""
    models = await claude_adapter.list_available_models()

    assert isinstance(models, list)
    assert len(models) > 0
    assert all(hasattr(model, "model_id") for model in models)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_count_tokens(claude_adapter):
    """Test token counting."""
    text = "This is a test sentence."
    count = await claude_adapter.count_tokens(text)

    assert count > 0
    # Should be roughly 1/4 of character count
    assert count < len(text)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_invalid_api_key():
    """Test authentication error with invalid API key."""
    # Create a mock credential provider that returns an invalid key
    class MockInvalidCredentialProvider:
        async def get_credential(self, key: str):
            return "invalid-key-that-will-fail"

    config = ClaudeCodeConfig(
        credential_provider=MockInvalidCredentialProvider(),
    )

    adapter = ClaudeCodeAdapter(config)

    with pytest.raises((AuthenticationError, LLMProviderError)):
        await adapter.execute("Test prompt")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_context_manager(claude_config):
    """Test using adapter as async context manager."""
    async with ClaudeCodeAdapter(claude_config) as adapter:
        model_info = await adapter.get_model_info()
        assert model_info is not None
