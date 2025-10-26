# LLM Provider Adapters - Detailed Design

## Overview

LLM Provider adapters connect the core orchestration domain to AI language model services. They implement the `ILLMProvider` output port interface, enabling prompt execution, response streaming, session management, and tool integration.

## Port Interface Definition

### ILLMProvider Interface

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Callable, AsyncIterator
from dataclasses import dataclass
from enum import Enum

class ExecutionMode(Enum):
    """Execution mode for LLM provider."""
    STANDARD = "standard"  # Normal execution
    STREAMING = "streaming"  # Stream responses
    BATCH = "batch"  # Batch multiple prompts

@dataclass
class ExecutionContext:
    """Context for LLM execution."""
    work_dir: str  # Working directory path
    project: str  # Project name
    agent: str  # Agent name
    task_id: str  # Task identifier
    model: str  # LLM model identifier
    timeout: int  # Execution timeout in seconds
    use_docker: bool  # Execute in Docker container
    mcp_servers: List[Dict[str, Any]]  # MCP server configurations
    session_id: Optional[str] = None  # For session continuity
    metadata: Dict[str, Any] = None  # Additional metadata

@dataclass
class ExecutionResult:
    """Result from LLM execution."""
    output: str  # Primary output text
    session_id: Optional[str]  # Session ID for continuity
    usage: Dict[str, int]  # Token usage (input_tokens, output_tokens)
    duration_ms: float  # Execution duration
    metadata: Dict[str, Any]  # Additional result metadata

class ILLMProvider(ABC):
    """
    Output port interface for LLM providers.

    Implementations connect to AI language model services
    (Claude Code, Aider, GPT-4, etc.) and handle prompt
    execution, streaming, and session management.
    """

    @abstractmethod
    async def execute_prompt(
        self,
        prompt: str,
        context: ExecutionContext,
        stream_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> ExecutionResult:
        """
        Execute a prompt with the LLM.

        Args:
            prompt: The prompt text to execute
            context: Execution context with configuration
            stream_callback: Optional callback for streaming events

        Returns:
            ExecutionResult with output and metadata

        Raises:
            LLMProviderError: For execution errors
            TimeoutError: If execution exceeds timeout
            AuthenticationError: For auth failures
        """
        pass

    @abstractmethod
    async def execute_prompt_streaming(
        self,
        prompt: str,
        context: ExecutionContext
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Execute a prompt with streaming response.

        Args:
            prompt: The prompt text to execute
            context: Execution context with configuration

        Yields:
            Stream events as dictionaries

        Raises:
            LLMProviderError: For execution errors
            TimeoutError: If execution exceeds timeout
        """
        pass

    @abstractmethod
    async def validate_configuration(self) -> bool:
        """
        Validate that the provider is properly configured.

        Returns:
            True if configuration is valid

        Raises:
            ConfigurationError: If configuration is invalid
        """
        pass

    @abstractmethod
    def supports_feature(self, feature: str) -> bool:
        """
        Check if provider supports a specific feature.

        Args:
            feature: Feature name (e.g., 'streaming', 'mcp', 'vision')

        Returns:
            True if feature is supported
        """
        pass
```

---

## Adapter Implementations

### 1. Claude Code Adapter (Production)

#### Purpose
Execute prompts using Claude via the Claude Code CLI, supporting containerized execution, MCP servers, and streaming responses.

#### Configuration

```python
@dataclass
class ClaudeCodeConfig:
    """Configuration for Claude Code adapter."""

    # Authentication
    auth_type: str  # 'oauth' or 'api_key'
    oauth_token: Optional[str] = None
    api_key: Optional[str] = None

    # Execution
    claude_cli_path: str = 'claude'  # Path to Claude CLI
    default_model: str = 'claude-sonnet-4-5-20250929'
    default_timeout: int = 300  # 5 minutes
    permission_mode: str = 'bypassPermissions'  # or 'askForPermissions'

    # Output
    output_format: str = 'stream-json'  # or 'text'
    verbose: bool = True

    # Docker integration
    docker_enabled: bool = True
    docker_image_pattern: str = '{project}-agent:latest'

    # Features
    enable_mcp: bool = True
    enable_tools: bool = True
```

#### Implementation

```python
import subprocess
import json
import asyncio
from typing import Dict, Any, Optional, Callable, AsyncIterator
from pathlib import Path

class ClaudeCodeAdapter(ILLMProvider):
    """Production adapter for Claude Code CLI."""

    def __init__(self, config: ClaudeCodeConfig):
        self.config = config
        self._validate_auth()

    def _validate_auth(self) -> None:
        """Validate authentication configuration."""
        if self.config.auth_type == 'oauth' and not self.config.oauth_token:
            raise ConfigurationError("OAuth token required but not provided")
        if self.config.auth_type == 'api_key' and not self.config.api_key:
            raise ConfigurationError("API key required but not provided")

    async def execute_prompt(
        self,
        prompt: str,
        context: ExecutionContext,
        stream_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> ExecutionResult:
        """Execute prompt via Claude Code CLI."""

        if context.use_docker:
            return await self._execute_in_docker(prompt, context, stream_callback)
        else:
            return await self._execute_local(prompt, context, stream_callback)

    async def _execute_local(
        self,
        prompt: str,
        context: ExecutionContext,
        stream_callback: Optional[Callable]
    ) -> ExecutionResult:
        """Execute Claude Code locally."""

        # Build command
        cmd = self._build_command(prompt, context)

        # Set environment
        env = self._build_environment(context)

        # Execute
        start_time = asyncio.get_event_loop().time()

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=context.work_dir
        )

        # Stream output
        output_parts = []
        session_id = None
        usage = {'input_tokens': 0, 'output_tokens': 0}

        async for line in process.stdout:
            if not line:
                break

            try:
                event = json.loads(line.decode('utf-8'))

                # Forward to stream callback
                if stream_callback:
                    stream_callback(event)

                # Extract text from assistant messages
                if event.get('type') == 'assistant':
                    content = event.get('message', {}).get('content', [])
                    for item in content:
                        if item.get('type') == 'text':
                            output_parts.append(item.get('text', ''))

                # Track usage
                if 'usage' in event:
                    usage['input_tokens'] += event['usage'].get('input_tokens', 0)
                    usage['output_tokens'] += event['usage'].get('output_tokens', 0)

                # Capture session ID
                if 'session_id' in event:
                    session_id = event['session_id']

            except json.JSONDecodeError:
                # Non-JSON output, ignore
                pass

        # Wait for completion
        await process.wait()

        if process.returncode != 0:
            stderr = await process.stderr.read()
            raise LLMProviderError(
                f"Claude Code execution failed: {stderr.decode('utf-8')}"
            )

        duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000

        return ExecutionResult(
            output=''.join(output_parts),
            session_id=session_id,
            usage=usage,
            duration_ms=duration_ms,
            metadata={'exit_code': process.returncode}
        )

    async def _execute_in_docker(
        self,
        prompt: str,
        context: ExecutionContext,
        stream_callback: Optional[Callable]
    ) -> ExecutionResult:
        """Execute Claude Code in Docker container."""

        from .docker_runner import DockerAgentRunner

        runner = DockerAgentRunner(
            project_name=context.project,
            docker_image=self.config.docker_image_pattern.format(
                project=context.project
            )
        )

        result = await runner.run_agent_in_container(
            prompt=prompt,
            context=context,
            mcp_servers=context.mcp_servers,
            stream_callback=stream_callback
        )

        return result

    def _build_command(
        self,
        prompt: str,
        context: ExecutionContext
    ) -> List[str]:
        """Build Claude CLI command."""

        cmd = [
            self.config.claude_cli_path,
            '--print',
            '--output-format', self.config.output_format,
            '--model', context.model or self.config.default_model,
            '--permission-mode', self.config.permission_mode
        ]

        if self.config.verbose:
            cmd.append('--verbose')

        # Session continuity
        if context.session_id:
            cmd.extend(['--session-id', context.session_id])

        # MCP servers
        if self.config.enable_mcp and context.mcp_servers:
            mcp_config_path = Path(context.work_dir) / '.mcp.json'
            if mcp_config_path.exists():
                cmd.extend(['--mcp-config', str(mcp_config_path)])

        # Prompt (must be last)
        cmd.append(prompt)

        return cmd

    def _build_environment(self, context: ExecutionContext) -> Dict[str, str]:
        """Build environment variables for execution."""

        import os
        env = os.environ.copy()

        # Authentication
        if self.config.auth_type == 'oauth':
            env['CLAUDE_CODE_OAUTH_TOKEN'] = self.config.oauth_token
        else:
            env['ANTHROPIC_API_KEY'] = self.config.api_key

        # Additional context
        if context.metadata:
            for key, value in context.metadata.items():
                if isinstance(value, str):
                    env[key.upper()] = value

        return env

    async def execute_prompt_streaming(
        self,
        prompt: str,
        context: ExecutionContext
    ) -> AsyncIterator[Dict[str, Any]]:
        """Execute with streaming response."""

        cmd = self._build_command(prompt, context)
        env = self._build_environment(context)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=context.work_dir
        )

        async for line in process.stdout:
            if not line:
                break

            try:
                event = json.loads(line.decode('utf-8'))
                yield event
            except json.JSONDecodeError:
                pass

        await process.wait()

    async def validate_configuration(self) -> bool:
        """Validate Claude Code configuration."""

        # Check CLI exists
        try:
            proc = await asyncio.create_subprocess_exec(
                self.config.claude_cli_path,
                '--version',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.wait()
            if proc.returncode != 0:
                raise ConfigurationError("Claude CLI not found or not working")
        except FileNotFoundError:
            raise ConfigurationError(
                f"Claude CLI not found at {self.config.claude_cli_path}"
            )

        # Validate authentication
        self._validate_auth()

        return True

    def supports_feature(self, feature: str) -> bool:
        """Check feature support."""

        supported = {
            'streaming': True,
            'mcp': self.config.enable_mcp,
            'tools': self.config.enable_tools,
            'vision': True,  # Claude models support vision
            'session_continuity': True,
            'docker': self.config.docker_enabled
        }

        return supported.get(feature, False)
```

---

### 2. Mock LLM Adapter (Testing/Mock)

#### Purpose
Provide deterministic, predictable LLM responses for testing without API calls or costs.

#### Implementation

```python
from typing import Dict, Any, Optional, Callable, AsyncIterator
import asyncio
import hashlib

class MockLLMAdapter(ILLMProvider):
    """Mock adapter for testing without actual LLM calls."""

    def __init__(
        self,
        responses: Optional[Dict[str, str]] = None,
        default_response: str = "Mock LLM response",
        simulate_delay: float = 0.1,
        simulate_streaming: bool = True
    ):
        """
        Initialize mock adapter.

        Args:
            responses: Dict mapping prompt patterns to responses
            default_response: Default response if no pattern matches
            simulate_delay: Simulated execution delay in seconds
            simulate_streaming: Whether to simulate streaming behavior
        """
        self.responses = responses or {}
        self.default_response = default_response
        self.simulate_delay = simulate_delay
        self.simulate_streaming = simulate_streaming

        # Track calls for testing assertions
        self.call_history: List[Dict[str, Any]] = []
        self.call_count = 0

    async def execute_prompt(
        self,
        prompt: str,
        context: ExecutionContext,
        stream_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> ExecutionResult:
        """Execute mock prompt."""

        self.call_count += 1

        # Record call
        call_record = {
            'prompt': prompt,
            'context': context,
            'timestamp': asyncio.get_event_loop().time()
        }
        self.call_history.append(call_record)

        # Find matching response
        response = self._find_response(prompt)

        # Simulate delay
        if self.simulate_delay > 0:
            await asyncio.sleep(self.simulate_delay)

        # Simulate streaming
        if self.simulate_streaming and stream_callback:
            await self._simulate_streaming(response, stream_callback)

        # Calculate mock usage
        usage = {
            'input_tokens': len(prompt.split()),
            'output_tokens': len(response.split())
        }

        return ExecutionResult(
            output=response,
            session_id=f"mock-session-{self.call_count}",
            usage=usage,
            duration_ms=self.simulate_delay * 1000,
            metadata={
                'mock': True,
                'call_number': self.call_count
            }
        )

    async def _simulate_streaming(
        self,
        response: str,
        stream_callback: Callable
    ) -> None:
        """Simulate streaming behavior."""

        # Split response into chunks
        words = response.split()
        chunk_size = max(1, len(words) // 10)  # ~10 chunks

        for i in range(0, len(words), chunk_size):
            chunk_words = words[i:i + chunk_size]
            chunk_text = ' '.join(chunk_words)

            # Emit assistant event
            event = {
                'type': 'assistant',
                'message': {
                    'role': 'assistant',
                    'content': [
                        {
                            'type': 'text',
                            'text': chunk_text + ' '
                        }
                    ]
                }
            }
            stream_callback(event)

            # Small delay between chunks
            await asyncio.sleep(0.01)

        # Emit final usage event
        usage_event = {
            'type': 'usage',
            'usage': {
                'input_tokens': len(response.split()) // 2,
                'output_tokens': len(response.split())
            }
        }
        stream_callback(usage_event)

    def _find_response(self, prompt: str) -> str:
        """Find response for prompt."""

        # Exact match
        if prompt in self.responses:
            return self.responses[prompt]

        # Pattern match (simple substring matching)
        for pattern, response in self.responses.items():
            if pattern.lower() in prompt.lower():
                return response

        # Hash-based matching for deterministic responses
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
        if prompt_hash in self.responses:
            return self.responses[prompt_hash]

        # Default
        return self.default_response

    async def execute_prompt_streaming(
        self,
        prompt: str,
        context: ExecutionContext
    ) -> AsyncIterator[Dict[str, Any]]:
        """Mock streaming execution."""

        response = self._find_response(prompt)
        words = response.split()

        for i, word in enumerate(words):
            event = {
                'type': 'assistant',
                'message': {
                    'role': 'assistant',
                    'content': [
                        {
                            'type': 'text',
                            'text': word + ' '
                        }
                    ]
                }
            }
            yield event
            await asyncio.sleep(0.01)

    async def validate_configuration(self) -> bool:
        """Mock configuration always valid."""
        return True

    def supports_feature(self, feature: str) -> bool:
        """Mock supports all features."""
        return True

    # Test helper methods

    def add_response(self, pattern: str, response: str) -> None:
        """Add a response pattern for testing."""
        self.responses[pattern] = response

    def reset(self) -> None:
        """Reset call history and count."""
        self.call_history.clear()
        self.call_count = 0

    def get_call_count(self) -> int:
        """Get number of calls made."""
        return self.call_count

    def get_last_prompt(self) -> Optional[str]:
        """Get the last prompt that was executed."""
        if not self.call_history:
            return None
        return self.call_history[-1]['prompt']

    def assert_called_with(self, expected_prompt_substring: str) -> bool:
        """Assert that adapter was called with prompt containing substring."""
        for call in self.call_history:
            if expected_prompt_substring in call['prompt']:
                return True
        return False
```

---

## Exception Definitions

```python
class LLMProviderError(Exception):
    """Base exception for LLM provider errors."""
    pass

class TimeoutError(LLMProviderError):
    """Execution exceeded timeout."""
    pass

class AuthenticationError(LLMProviderError):
    """Authentication failed."""
    pass

class ConfigurationError(LLMProviderError):
    """Configuration is invalid."""
    pass

class ModelNotAvailableError(LLMProviderError):
    """Requested model is not available."""
    pass
```

---

## Adapter Registry

```python
from typing import Dict, Type, Optional

class LLMProviderRegistry:
    """Registry for LLM provider implementations."""

    def __init__(self):
        self._providers: Dict[str, Type[ILLMProvider]] = {}

    def register(self, name: str, provider_class: Type[ILLMProvider]) -> None:
        """Register a provider implementation."""
        self._providers[name] = provider_class

    def create(
        self,
        name: str,
        config: Optional[Any] = None
    ) -> ILLMProvider:
        """Create a provider instance by name."""
        if name not in self._providers:
            raise ValueError(f"Unknown LLM provider: {name}")

        provider_class = self._providers[name]

        if config:
            return provider_class(config)
        else:
            return provider_class()

    def list_providers(self) -> List[str]:
        """List registered provider names."""
        return list(self._providers.keys())

# Global registry
llm_provider_registry = LLMProviderRegistry()

# Register built-in providers
llm_provider_registry.register('claude-code', ClaudeCodeAdapter)
llm_provider_registry.register('mock', MockLLMAdapter)
```

---

## Usage Examples

### Production Usage

```python
# Create Claude Code adapter
config = ClaudeCodeConfig(
    auth_type='oauth',
    oauth_token=os.getenv('CLAUDE_CODE_OAUTH_TOKEN'),
    docker_enabled=True
)

llm = ClaudeCodeAdapter(config)

# Execute prompt
context = ExecutionContext(
    work_dir='/workspace/project',
    project='my-project',
    agent='business_analyst',
    task_id='task-123',
    model='claude-sonnet-4-5-20250929',
    timeout=300,
    use_docker=True,
    mcp_servers=[]
)

result = await llm.execute_prompt(
    "Analyze the following requirement and provide recommendations...",
    context,
    stream_callback=lambda event: print(event)
)

print(f"Output: {result.output}")
print(f"Tokens: {result.usage}")
```

### Testing Usage

```python
# Create mock adapter with predefined responses
llm = MockLLMAdapter(
    responses={
        "analyze": "## Analysis\n\nThis is a test analysis.",
        "review": "## Review\n\nNo issues found."
    },
    simulate_delay=0.05
)

# Execute
result = await llm.execute_prompt("Please analyze this code", context)

# Assertions
assert llm.get_call_count() == 1
assert llm.assert_called_with("analyze")
assert "Analysis" in result.output
```

---

## Testing Strategy

### Unit Tests

```python
import pytest

class TestClaudeCodeAdapter:
    """Unit tests for Claude Code adapter."""

    @pytest.mark.asyncio
    async def test_execute_prompt_local(self, mock_subprocess):
        """Test local execution."""
        # Mock subprocess execution
        # Assert correct command built
        # Assert environment configured
        pass

    @pytest.mark.asyncio
    async def test_streaming_callback(self, mock_subprocess):
        """Test streaming callback invoked."""
        # Mock streaming output
        # Create callback spy
        # Assert callback called with events
        pass

class TestMockLLMAdapter:
    """Unit tests for mock adapter."""

    @pytest.fixture
    def adapter(self):
        return MockLLMAdapter()

    @pytest.mark.asyncio
    async def test_deterministic_responses(self, adapter):
        """Test responses are deterministic."""
        adapter.add_response("test", "Test response")

        result1 = await adapter.execute_prompt("test", context)
        result2 = await adapter.execute_prompt("test", context)

        assert result1.output == result2.output

    @pytest.mark.asyncio
    async def test_call_tracking(self, adapter):
        """Test call history tracking."""
        await adapter.execute_prompt("prompt1", context)
        await adapter.execute_prompt("prompt2", context)

        assert adapter.get_call_count() == 2
        assert adapter.assert_called_with("prompt1")
```

---

## Performance Considerations

### Streaming Optimization
- Use async generators for streaming to avoid buffering entire response
- Forward stream events immediately to callbacks
- Handle backpressure if downstream is slow

### Timeout Management
- Set appropriate timeouts based on model and prompt complexity
- Use asyncio.wait_for for hard timeouts
- Clean up resources on timeout

### Resource Management
- Close subprocess streams properly
- Handle process cleanup on errors
- Limit concurrent executions to avoid resource exhaustion

---

## Security Considerations

### Credential Management
- Never log tokens or API keys
- Use environment variables for secrets
- Rotate credentials regularly
- Support credential managers (e.g., AWS Secrets Manager)

### Prompt Injection Prevention
- Sanitize user input in prompts
- Use structured prompts with clear sections
- Validate prompt length limits

### Docker Security
- Run containers with minimal privileges
- Limit network access
- Use read-only mounts where possible
- Scan images for vulnerabilities

---

## Observability

### Metrics
- Track execution latency (p50, p95, p99)
- Monitor token usage and costs
- Count errors by type
- Track timeout rate

### Logging
- Log all executions with correlation IDs
- Log token usage for cost tracking
- Structured logging with context

### Events
- Emit events for execution start/complete
- Track model and prompt metadata
- Enable cost analysis and optimization
