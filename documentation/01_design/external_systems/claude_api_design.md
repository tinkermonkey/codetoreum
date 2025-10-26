# Claude API External System - Detailed Design

## Overview

The Claude API provides AI intelligence for all agent operations in the Codetoreum platform. This external system is responsible for code generation, analysis, reasoning, and conversational interactions. This document details the abstraction layer, authentication mechanisms, and mock implementations for Claude API integration.

## System Purpose

**Primary Functions**:
1. AI-powered code generation and modification
2. Requirements analysis and documentation
3. Code review and feedback
4. Conversational Q&A
5. Test failure analysis and fixing
6. Architecture and design recommendations

## Port Interface Design

### ILLMProvider Interface

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any, Callable, AsyncGenerator
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class LLMModel(Enum):
    """Available LLM models."""
    CLAUDE_SONNET_4_5 = "claude-sonnet-4-5-20250929"
    CLAUDE_SONNET_4 = "claude-sonnet-4-20250514"
    CLAUDE_OPUS_4 = "claude-opus-4-20250514"
    GPT4_TURBO = "gpt-4-turbo"
    GPT4 = "gpt-4"
    MOCK = "mock"

@dataclass
class LLMMessage:
    """A message in a conversation."""
    role: str  # 'user', 'assistant', 'system'
    content: str
    timestamp: datetime

@dataclass
class LLMExecutionContext:
    """Context for LLM execution."""
    work_dir: str                    # Working directory
    project: str                     # Project name
    agent: str                       # Agent name
    task_id: str                     # Task identifier
    session_id: Optional[str] = None # For conversation continuity
    tools_enabled: bool = True       # Enable tool use
    max_tokens: Optional[int] = None # Response length limit
    temperature: float = 1.0         # Sampling temperature
    custom_params: Dict[str, Any] = None

@dataclass
class LLMResponse:
    """Response from LLM execution."""
    content: str                     # Generated text
    session_id: Optional[str] = None # Session ID for continuity
    tokens_used: Dict[str, int] = None  # {'input': X, 'output': Y}
    model: str = None                # Model used
    finish_reason: str = None        # 'stop', 'length', 'tool_use'
    tool_calls: List[Dict] = None    # Tool invocations
    metadata: Dict[str, Any] = None  # Additional metadata

@dataclass
class StreamEvent:
    """A streaming event from LLM."""
    type: str                        # Event type
    data: Dict[str, Any]             # Event data
    timestamp: datetime

class ILLMProvider(ABC):
    """
    Port interface for LLM providers.

    Abstracts Claude API, OpenAI API, local models, etc.
    """

    @abstractmethod
    async def execute(
        self,
        prompt: str,
        context: LLMExecutionContext,
        stream_callback: Optional[Callable[[StreamEvent], None]] = None
    ) -> LLMResponse:
        """
        Execute a prompt with the LLM.

        Args:
            prompt: The prompt/instruction for the LLM
            context: Execution context with project info
            stream_callback: Optional callback for streaming events

        Returns:
            LLMResponse with generated content
        """
        pass

    @abstractmethod
    async def execute_conversational(
        self,
        messages: List[LLMMessage],
        context: LLMExecutionContext,
        stream_callback: Optional[Callable[[StreamEvent], None]] = None
    ) -> LLMResponse:
        """
        Execute a multi-turn conversation.

        Args:
            messages: Conversation history
            context: Execution context
            stream_callback: Optional callback for streaming

        Returns:
            LLMResponse with next assistant message
        """
        pass

    @abstractmethod
    async def stream_execute(
        self,
        prompt: str,
        context: LLMExecutionContext
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Execute with streaming response.

        Yields StreamEvent objects as they arrive.
        """
        pass

    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the model.

        Returns:
            Dict with model capabilities, limits, pricing, etc.
        """
        pass

    @abstractmethod
    async def validate_auth(self) -> bool:
        """
        Validate authentication credentials.

        Returns:
            True if authentication is valid
        """
        pass
```

## Production Adapter: ClaudeCodeAdapter

### Implementation Structure

```python
import asyncio
import json
import subprocess
from pathlib import Path
from typing import Optional, Callable

class ClaudeCodeAdapter(ILLMProvider):
    """
    Production adapter for Claude Code CLI.

    Uses the official Claude CLI for code-focused operations.
    """

    def __init__(
        self,
        oauth_token: Optional[str] = None,
        api_key: Optional[str] = None,
        default_model: LLMModel = LLMModel.CLAUDE_SONNET_4_5
    ):
        """
        Initialize Claude Code adapter.

        Args:
            oauth_token: Claude Code subscription token (CLAUDE_CODE_OAUTH_TOKEN)
            api_key: Anthropic API key for pay-per-use (ANTHROPIC_API_KEY)
            default_model: Default model to use
        """
        if not oauth_token and not api_key:
            raise ValueError("Either oauth_token or api_key required")

        self.oauth_token = oauth_token
        self.api_key = api_key
        self.default_model = default_model

    async def execute(
        self,
        prompt: str,
        context: LLMExecutionContext,
        stream_callback: Optional[Callable[[StreamEvent], None]] = None
    ) -> LLMResponse:
        """
        Execute prompt using Claude Code CLI.

        Runs claude command with streaming JSON output.
        """
        # Build command
        cmd = self._build_claude_command(
            prompt=prompt,
            context=context
        )

        # Set environment
        env = self._build_environment()

        # Execute process
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=context.work_dir
        )

        # Stream and collect output
        result_content = []
        tokens_used = {'input': 0, 'output': 0}
        session_id = None

        async for line in process.stdout:
            if not line:
                break

            try:
                event = json.loads(line.decode())

                # Forward to callback if provided
                if stream_callback:
                    stream_event = self._convert_to_stream_event(event)
                    stream_callback(stream_event)

                # Extract data
                event_type = event.get('type')

                if event_type == 'assistant':
                    # Extract text content
                    content = event.get('message', {}).get('content', [])
                    for item in content:
                        if item.get('type') == 'text':
                            result_content.append(item.get('text', ''))

                elif event_type == 'usage':
                    # Track token usage
                    tokens_used['input'] += event.get('input_tokens', 0)
                    tokens_used['output'] += event.get('output_tokens', 0)

                # Capture session ID for continuity
                if 'session_id' in event:
                    session_id = event['session_id']

            except json.JSONDecodeError:
                # Non-JSON output, log as warning
                pass

        # Wait for process completion
        await process.wait()

        if process.returncode != 0:
            stderr = await process.stderr.read()
            raise LLMExecutionError(f"Claude execution failed: {stderr.decode()}")

        return LLMResponse(
            content=''.join(result_content),
            session_id=session_id,
            tokens_used=tokens_used,
            model=self.default_model.value,
            finish_reason='stop'
        )

    def _build_claude_command(
        self,
        prompt: str,
        context: LLMExecutionContext
    ) -> List[str]:
        """Build Claude CLI command."""
        cmd = [
            'claude',
            '--print',
            '--verbose',
            '--output-format', 'stream-json',
            '--model', self.default_model.value,
            '--permission-mode', 'bypassPermissions'
        ]

        # Add session continuity
        if context.session_id:
            cmd.extend(['--resume', context.session_id])

        # Add temperature
        if context.temperature != 1.0:
            cmd.extend(['--temperature', str(context.temperature)])

        # Add max tokens
        if context.max_tokens:
            cmd.extend(['--max-tokens', str(context.max_tokens)])

        # Add prompt
        cmd.append(prompt)

        return cmd

    def _build_environment(self) -> Dict[str, str]:
        """Build environment variables for Claude CLI."""
        env = os.environ.copy()

        if self.oauth_token:
            env['CLAUDE_CODE_OAUTH_TOKEN'] = self.oauth_token
        elif self.api_key:
            env['ANTHROPIC_API_KEY'] = self.api_key

        return env

    def _convert_to_stream_event(self, claude_event: Dict) -> StreamEvent:
        """Convert Claude CLI event to StreamEvent."""
        return StreamEvent(
            type=claude_event.get('type', 'unknown'),
            data=claude_event,
            timestamp=datetime.utcnow()
        )

    async def validate_auth(self) -> bool:
        """Test authentication by running simple command."""
        try:
            cmd = ['claude', '--version']
            env = self._build_environment()

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )

            await process.wait()
            return process.returncode == 0
        except Exception:
            return False

    def get_model_info(self) -> Dict[str, Any]:
        """Return model capabilities."""
        return {
            'name': self.default_model.value,
            'provider': 'Anthropic',
            'max_tokens': 200000,
            'context_window': 200000,
            'supports_tools': True,
            'supports_vision': True,
            'supports_streaming': True
        }


class ClaudeAPIAdapter(ILLMProvider):
    """
    Alternative adapter using Anthropic Python SDK.

    Direct API access without CLI dependency.
    """

    def __init__(
        self,
        api_key: str,
        default_model: LLMModel = LLMModel.CLAUDE_SONNET_4_5
    ):
        import anthropic
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.default_model = default_model

    async def execute(
        self,
        prompt: str,
        context: LLMExecutionContext,
        stream_callback: Optional[Callable[[StreamEvent], None]] = None
    ) -> LLMResponse:
        """Execute using Anthropic SDK."""
        response = await self.client.messages.create(
            model=self.default_model.value,
            max_tokens=context.max_tokens or 4096,
            temperature=context.temperature,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        content = ''.join([
            block.text for block in response.content
            if hasattr(block, 'text')
        ])

        return LLMResponse(
            content=content,
            tokens_used={
                'input': response.usage.input_tokens,
                'output': response.usage.output_tokens
            },
            model=response.model,
            finish_reason=response.stop_reason
        )
```

## Mock Adapter: MockLLMProvider

```python
import hashlib
from typing import Dict

class MockLLMProvider(ILLMProvider):
    """
    Mock LLM provider for testing and simulation.

    Returns predetermined responses based on prompt hashing.
    Fully deterministic for reproducible testing.
    """

    def __init__(
        self,
        responses: Optional[Dict[str, str]] = None,
        default_response: str = "Mock LLM response",
        response_delay_ms: int = 0
    ):
        """
        Initialize mock provider.

        Args:
            responses: Dict mapping prompt hash -> response
            default_response: Fallback response
            response_delay_ms: Simulated delay (for realism)
        """
        self.responses = responses or {}
        self.default_response = default_response
        self.response_delay_ms = response_delay_ms
        self.call_count = 0
        self.call_history: List[Dict[str, Any]] = []

    async def execute(
        self,
        prompt: str,
        context: LLMExecutionContext,
        stream_callback: Optional[Callable[[StreamEvent], None]] = None
    ) -> LLMResponse:
        """Return predetermined response."""
        self.call_count += 1

        # Record call
        self.call_history.append({
            'prompt': prompt,
            'context': context,
            'timestamp': datetime.utcnow()
        })

        # Simulate delay
        if self.response_delay_ms > 0:
            await asyncio.sleep(self.response_delay_ms / 1000)

        # Find response
        prompt_hash = self._hash_prompt(prompt)
        response_text = self.responses.get(
            prompt_hash,
            self.default_response
        )

        # Simulate streaming if callback provided
        if stream_callback:
            await self._simulate_streaming(response_text, stream_callback)

        return LLMResponse(
            content=response_text,
            session_id=f"mock-session-{self.call_count}",
            tokens_used={'input': 100, 'output': 200},
            model=LLMModel.MOCK.value,
            finish_reason='stop'
        )

    def _hash_prompt(self, prompt: str) -> str:
        """Create hash of prompt for lookup."""
        # Hash first 200 chars (ignoring variable data)
        normalized = prompt[:200].lower().strip()
        return hashlib.md5(normalized.encode()).hexdigest()

    async def _simulate_streaming(
        self,
        content: str,
        callback: Callable
    ):
        """Simulate streaming output."""
        words = content.split()

        for i, word in enumerate(words):
            event = StreamEvent(
                type='text_delta',
                data={'text': word + ' '},
                timestamp=datetime.utcnow()
            )
            callback(event)

            # Small delay between words
            await asyncio.sleep(0.01)

    async def validate_auth(self) -> bool:
        """Mock always validates."""
        return True

    def get_model_info(self) -> Dict[str, Any]:
        """Return mock model info."""
        return {
            'name': 'mock',
            'provider': 'Mock',
            'max_tokens': 999999,
            'context_window': 999999,
            'supports_tools': True,
            'supports_vision': True,
            'supports_streaming': True,
            'is_mock': True
        }

    def add_response(self, prompt_prefix: str, response: str):
        """Helper to add predetermined response."""
        prompt_hash = self._hash_prompt(prompt_prefix)
        self.responses[prompt_hash] = response

    def get_call_history(self) -> List[Dict[str, Any]]:
        """Get all calls made to this provider."""
        return self.call_history
```

## Deterministic Testing Support

```python
class DeterministicMockProvider(MockLLMProvider):
    """
    Mock provider with scenario-based responses.

    Maps prompts to specific scenarios for end-to-end testing.
    """

    def __init__(self, scenario: str):
        """
        Initialize with a scenario.

        Scenarios:
        - 'business_analysis': Realistic business analyst responses
        - 'code_generation': Realistic code generation
        - 'code_review': Review with issues found
        - 'approval': Review with approval
        """
        super().__init__()
        self.scenario = scenario
        self._load_scenario_responses()

    def _load_scenario_responses(self):
        """Load responses for scenario."""
        if self.scenario == 'business_analysis':
            self.responses = {
                # Business analyst prompt -> requirements doc
                self._hash_prompt("You are a Business Analyst"): """
## Requirements Analysis

### User Stories
1. As a user, I want to view my dashboard...
2. As an admin, I want to manage users...

### Acceptance Criteria
- Dashboard loads in <2 seconds
- User management supports CRUD operations

### Technical Considerations
- Use React for frontend
- PostgreSQL for database
""",
            }

        elif self.scenario == 'code_review':
            self.responses = {
                self._hash_prompt("You are a Code Reviewer"): """
## Code Review

### Issues
1. [Missing Error Handling]: Add try/catch blocks in API calls
2. [Inefficient Query]: Use database index for user lookup

### Approval
[CHANGES REQUESTED]
""",
            }

        elif self.scenario == 'approval':
            self.responses = {
                self._hash_prompt("You are a Code Reviewer"): """
## Code Review

No issues found. Code meets quality standards.

### Approval
[APPROVED]
""",
            }
```

## Configuration

```python
@dataclass
class ClaudeConfig:
    """Claude adapter configuration."""

    # Authentication (one required)
    oauth_token: Optional[str] = None
    api_key: Optional[str] = None

    # Model selection
    model: LLMModel = LLMModel.CLAUDE_SONNET_4_5

    # Execution settings
    default_max_tokens: int = 4096
    default_temperature: float = 1.0
    timeout_seconds: int = 300

    # CLI settings (for ClaudeCodeAdapter)
    cli_path: str = "claude"
    permission_mode: str = "bypassPermissions"

    # Rate limiting
    max_requests_per_minute: int = 60
    max_tokens_per_minute: int = 40000

    def validate(self):
        """Validate configuration."""
        if not self.oauth_token and not self.api_key:
            raise ValueError("Either oauth_token or api_key required")

        if self.model not in LLMModel:
            raise ValueError(f"Invalid model: {self.model}")
```

## Error Handling

```python
class LLMExecutionError(Exception):
    """Base exception for LLM execution failures."""
    pass

class AuthenticationError(LLMExecutionError):
    """Raised when authentication fails."""
    pass

class RateLimitError(LLMExecutionError):
    """Raised when rate limit exceeded."""

    def __init__(self, retry_after: int, *args):
        super().__init__(*args)
        self.retry_after = retry_after

class TokenLimitError(LLMExecutionError):
    """Raised when token limit exceeded."""
    pass

class ModelUnavailableError(LLMExecutionError):
    """Raised when model is unavailable."""
    pass
```

## Rate Limiting

```python
import time
from collections import deque

class RateLimiter:
    """
    Token bucket rate limiter for Claude API.

    Prevents exceeding API rate limits.
    """

    def __init__(
        self,
        max_requests_per_minute: int = 60,
        max_tokens_per_minute: int = 40000
    ):
        self.max_requests_per_minute = max_requests_per_minute
        self.max_tokens_per_minute = max_tokens_per_minute

        self.request_timestamps: deque = deque()
        self.token_usage: deque = deque()

    async def acquire(self, estimated_tokens: int = 1000):
        """
        Wait until request can be made without exceeding limits.

        Args:
            estimated_tokens: Estimated tokens for this request
        """
        while True:
            now = time.time()
            one_minute_ago = now - 60

            # Remove old entries
            while self.request_timestamps and self.request_timestamps[0] < one_minute_ago:
                self.request_timestamps.popleft()

            while self.token_usage and self.token_usage[0][0] < one_minute_ago:
                self.token_usage.popleft()

            # Check if we can make request
            requests_in_window = len(self.request_timestamps)
            tokens_in_window = sum(tokens for _, tokens in self.token_usage)

            can_proceed = (
                requests_in_window < self.max_requests_per_minute and
                tokens_in_window + estimated_tokens < self.max_tokens_per_minute
            )

            if can_proceed:
                # Record this request
                self.request_timestamps.append(now)
                self.token_usage.append((now, estimated_tokens))
                return

            # Wait and retry
            await asyncio.sleep(1)

    def record_actual_usage(self, actual_tokens: int):
        """Update last entry with actual token usage."""
        if self.token_usage:
            timestamp, _ = self.token_usage[-1]
            self.token_usage[-1] = (timestamp, actual_tokens)
```

## Testing Strategy

### Unit Tests

```python
import pytest

@pytest.fixture
def mock_provider():
    return MockLLMProvider(
        responses={},
        default_response="Test response"
    )

async def test_mock_execution(mock_provider):
    """Test mock provider execution."""
    context = LLMExecutionContext(
        work_dir="/workspace/test",
        project="test-project",
        agent="test-agent",
        task_id="test-123"
    )

    response = await mock_provider.execute(
        prompt="Test prompt",
        context=context
    )

    assert response.content == "Test response"
    assert mock_provider.call_count == 1

async def test_deterministic_scenario():
    """Test deterministic scenario responses."""
    provider = DeterministicMockProvider(scenario='code_review')

    context = LLMExecutionContext(
        work_dir="/workspace/test",
        project="test-project",
        agent="code_reviewer",
        task_id="test-123"
    )

    response = await provider.execute(
        prompt="You are a Code Reviewer...",
        context=context
    )

    assert "[CHANGES REQUESTED]" in response.content
```

### Integration Tests

```python
@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("CLAUDE_CODE_OAUTH_TOKEN"),
    reason="No Claude token"
)
async def test_claude_real_api():
    """Test real Claude API."""
    adapter = ClaudeCodeAdapter(
        oauth_token=os.getenv("CLAUDE_CODE_OAUTH_TOKEN")
    )

    context = LLMExecutionContext(
        work_dir="/tmp/test",
        project="test-project",
        agent="test-agent",
        task_id="test-123"
    )

    response = await adapter.execute(
        prompt="Say 'Hello World' and nothing else.",
        context=context
    )

    assert "Hello World" in response.content
    assert response.tokens_used['input'] > 0
```

## Deployment Considerations

### Cost Management

Claude API pricing (approximate):
- **Sonnet 4.5**: $3/M input tokens, $15/M output tokens
- **Opus 4**: $15/M input tokens, $75/M output tokens

**Mitigation**:
- Token usage tracking and reporting
- Budget alerts
- Model selection per task type
- Caching for repeated prompts

### Context Window Management

```python
class ContextWindowManager:
    """
    Manage context window for large inputs.

    Ensures prompts fit within model limits.
    """

    def __init__(self, max_tokens: int = 200000):
        self.max_tokens = max_tokens

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count (rough approximation)."""
        # ~4 chars per token average
        return len(text) // 4

    def truncate_if_needed(
        self,
        prompt: str,
        max_output_tokens: int = 4096
    ) -> str:
        """Truncate prompt to fit in context window."""
        available_tokens = self.max_tokens - max_output_tokens
        prompt_tokens = self.estimate_tokens(prompt)

        if prompt_tokens <= available_tokens:
            return prompt

        # Truncate to fit
        target_chars = available_tokens * 4
        return prompt[:target_chars] + "\n\n[Content truncated to fit context window]"
```

## Summary

The Claude API integration provides:
1. **Clean abstraction** through ILLMProvider port
2. **Multiple adapters**: CLI-based and SDK-based
3. **Mock provider** with deterministic scenarios
4. **Rate limiting** to prevent API throttling
5. **Error handling** with specific exception types
6. **Cost tracking** for token usage
7. **Context management** for large inputs
8. **Full testing** support with mock implementations

This design enables the platform to use Claude AI while maintaining flexibility to swap in alternative LLM providers (GPT-4, Aider, local models) without changing core business logic.
