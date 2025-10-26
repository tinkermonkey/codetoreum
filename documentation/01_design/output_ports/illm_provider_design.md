# ILLMProvider Output Port Design

## Overview

The `ILLMProvider` port defines the interface for integrating with Large Language Model providers. This port abstracts the complexity of different LLM APIs and provides a unified interface for AI-powered agent execution within containerized environments.

**Critical Design Note**: Based on the design changes, general purpose containerized agents will receive context through mounted files rather than direct prompt parameters, allowing for much larger context without hitting token limits.

## Port Interface

### Core Interface Definition

```python
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Callable, AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

class ILLMProvider(ABC):
    """
    Interface for Large Language Model providers.

    This port abstracts LLM operations, supporting various providers
    like Claude, GPT-4, and local models. For Codetoreum, providers
    run in containerized environments with context mounted as files.
    """

    # Core Execution

    @abstractmethod
    async def execute(self,
                     prompt: str,
                     context: Optional[ExecutionContext] = None,
                     stream_callback: Optional[StreamCallback] = None) -> ExecutionResult:
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
    async def execute_with_tools(self,
                                prompt: str,
                                tools: List[ToolDefinition],
                                context: Optional[ExecutionContext] = None,
                                stream_callback: Optional[StreamCallback] = None) -> ExecutionResult:
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
        """
        pass

    # Streaming

    @abstractmethod
    async def stream_completion(self,
                               prompt: str,
                               context: Optional[ExecutionContext] = None) -> AsyncIterator[StreamChunk]:
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
        """
        pass

    # Conversation Management

    @abstractmethod
    async def create_conversation(self,
                                 system_prompt: Optional[str] = None,
                                 parameters: Optional[ModelParameters] = None) -> ConversationId:
        """
        Create a new conversation session.

        Args:
            system_prompt: System instructions
            parameters: Model parameters

        Returns:
            ConversationId: Unique conversation identifier

        Raises:
            ExternalServiceError: Provider service error
        """
        pass

    @abstractmethod
    async def continue_conversation(self,
                                   conversation_id: ConversationId,
                                   message: str,
                                   stream_callback: Optional[StreamCallback] = None) -> ExecutionResult:
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
        """
        pass

    # Model Information

    @abstractmethod
    async def get_model_info(self) -> ModelInfo:
        """Get information about the current model."""
        pass

    @abstractmethod
    async def list_available_models(self) -> List[ModelInfo]:
        """List all available models from this provider."""
        pass

    # Token Management

    @abstractmethod
    async def count_tokens(self,
                         text: str,
                         model: Optional[str] = None) -> int:
        """Count tokens in text."""
        pass

    @abstractmethod
    async def get_usage_stats(self,
                            since: Optional[datetime] = None) -> UsageStats:
        """Get usage statistics (token usage and costs)."""
        pass
```

## Data Models

### ExecutionContext

```python
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
    conversation_id: Optional[ConversationId] = None
    message_history: List[Message] = field(default_factory=list)
    system_prompt: Optional[str] = None

    # Execution options
    timeout_seconds: int = 300
    retry_on_error: bool = True
    cache_response: bool = False

    # Workspace context (NEW for redesign)
    working_directory: Optional[Path] = None
    mounted_context_files: Dict[str, Path] = field(default_factory=dict)
    available_files: List[str] = field(default_factory=list)
    environment_variables: Dict[str, str] = field(default_factory=dict)

    # MCP Server configuration
    mcp_servers: List[Dict[str, Any]] = field(default_factory=list)

    # Metadata
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### ExecutionResult

```python
@dataclass
class ExecutionResult:
    """Result from LLM execution."""

    # Response content
    content: str
    role: str = "assistant"

    # Tool calls (if any)
    tool_calls: List[ToolCall] = field(default_factory=list)

    # Metadata
    model: str = None
    completion_tokens: int = 0
    prompt_tokens: int = 0
    total_tokens: int = 0

    # Timing
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime = field(default_factory=datetime.utcnow)
    duration_ms: int = 0

    # Additional data
    finish_reason: str = "stop"
    conversation_id: Optional[ConversationId] = None
    cached: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_cost(self) -> float:
        """Calculate cost based on token usage (provider-specific)."""
        return 0.0
```

### StreamCallback

```python
StreamCallback = Callable[[StreamChunk], Awaitable[None]]

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
```

## Adapter Implementations

### Claude Code Adapter (Containerized)

**File**: `src/adapters/secondary/llm_providers/claude_code_adapter.py`

This is the **primary adapter** for Codetoreum, running Claude Code in containerized environments.

```python
class ClaudeCodeAdapter(ILLMProvider):
    """
    Claude Code adapter running in Docker containers.

    This adapter executes Claude Code within isolated containers with:
    - Mounted project files (read-only or read-write)
    - Mounted context files in /context directory
    - Environment variables from project configuration
    - MCP server configurations
    - No git/github/ssh credentials (managed by orchestrator)
    """

    def __init__(self,
                 container_runtime: IContainer,
                 model: str = "claude-sonnet-4-5-20250929",
                 timeout: int = 300):
        self.container = container_runtime
        self.model = model
        self.timeout = timeout

    async def execute(self,
                     prompt: str,
                     context: Optional[ExecutionContext] = None,
                     stream_callback: Optional[StreamCallback] = None) -> ExecutionResult:
        """
        Execute Claude Code in a container.

        The prompt should reference context files mounted in /context/:
        Example: "See /context/issue.md for the requirement details"
        """
        context = context or ExecutionContext()

        # Prepare container volumes
        volumes = self._prepare_volumes(context)

        # Prepare environment variables
        env_vars = self._prepare_environment(context)

        # Prepare MCP configuration
        mcp_config = self._prepare_mcp_config(context.mcp_servers)

        # Execute in container
        result = await self.container.run(
            image="anthropic/claude-code:latest",
            command=["claude-code", "run", "--prompt", prompt],
            volumes=volumes,
            environment=env_vars,
            timeout=self.timeout,
            stream_callback=self._wrap_stream_callback(stream_callback)
        )

        return self._parse_container_result(result)

    def _prepare_volumes(self, context: ExecutionContext) -> Dict[str, str]:
        """
        Prepare volume mounts for the container.

        Returns:
            Dict mapping host paths to container paths
        """
        volumes = {}

        # Mount project directory (read-only or read-write based on config)
        if context.working_directory:
            mode = "rw"  # or "ro" based on agent config
            volumes[str(context.working_directory)] = f"/workspace:{mode}"

        # Mount context files (read-only)
        for name, path in context.mounted_context_files.items():
            volumes[str(path)] = f"/context/{name}:ro"

        # Mount MCP config if present
        if context.mcp_servers:
            volumes["/tmp/mcp-config.json"] = "/mcp/config.json:ro"

        return volumes

    def _prepare_environment(self, context: ExecutionContext) -> Dict[str, str]:
        """Prepare environment variables for the container."""
        env = {
            "ANTHROPIC_MODEL": context.model or self.model,
            "ANTHROPIC_MAX_TOKENS": str(context.max_tokens or 4096),
            "ANTHROPIC_TEMPERATURE": str(context.temperature),
        }

        # Add project-level environment variables
        env.update(context.environment_variables)

        # Note: NO git credentials, github credentials, or ssh keys
        # The orchestrator manages all git operations

        return env
```

**Key Features**:
- Runs in isolated containers
- Context passed through mounted files (not in prompts)
- No access to credentials (git, github, ssh)
- Configurable file access (read-only vs read-write)
- MCP server support for artifact storage and logging
- Stream callback support for real-time updates

### OpenAI Adapter (Direct API)

**File**: `src/adapters/secondary/llm_providers/openai_adapter.py`

```python
class OpenAIAdapter(ILLMProvider):
    """OpenAI GPT implementation."""

    def __init__(self, api_key: str, model: str = "gpt-4-turbo"):
        self.client = OpenAI(api_key=api_key)
        self.model = model

    async def execute_with_tools(self,
                                prompt: str,
                                tools: List[ToolDefinition],
                                context: Optional[ExecutionContext] = None,
                                stream_callback: Optional[StreamCallback] = None) -> ExecutionResult:
        """Execute with function calling support."""
        context = context or ExecutionContext()

        # Convert tools to OpenAI format
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters
                }
            }
            for tool in tools
        ]

        # Execute with tools
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=self._prepare_messages(prompt, context),
            tools=openai_tools,
            tool_choice="auto",
            temperature=context.temperature
        )

        # Process tool calls
        tool_calls = []
        if response.choices[0].message.tool_calls:
            for tc in response.choices[0].message.tool_calls:
                tool_calls.append(ToolCall(
                    tool_name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                    call_id=tc.id
                ))

        return ExecutionResult(
            content=response.choices[0].message.content or "",
            tool_calls=tool_calls,
            model=response.model,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens
        )
```

### Mock Provider (Testing)

**File**: `src/adapters/secondary/llm_providers/mock_provider.py`

```python
class MockLLMProvider(ILLMProvider):
    """Mock LLM provider for testing with deterministic responses."""

    def __init__(self,
                 responses: Optional[Dict[str, str]] = None,
                 latency_ms: int = 0,
                 should_fail: bool = False):
        self.responses = responses or {"default": "Mock response"}
        self.latency_ms = latency_ms
        self.should_fail = should_fail
        self.call_history: List[Dict[str, Any]] = []

    async def execute(self,
                     prompt: str,
                     context: Optional[ExecutionContext] = None,
                     stream_callback: Optional[StreamCallback] = None) -> ExecutionResult:
        """Execute with predetermined response."""
        # Record call for verification
        self.call_history.append({
            "prompt": prompt,
            "context": context,
            "timestamp": datetime.utcnow()
        })

        # Simulate failure
        if self.should_fail:
            raise ExternalServiceError("Mock", "Simulated failure")

        # Simulate latency
        if self.latency_ms:
            await asyncio.sleep(self.latency_ms / 1000)

        # Find matching response
        response = self._find_response(prompt)

        # Simulate streaming
        if stream_callback:
            await self._stream_response(response, stream_callback)

        return ExecutionResult(
            content=response,
            model="mock-model",
            prompt_tokens=len(prompt.split()),
            completion_tokens=len(response.split()),
            total_tokens=len(prompt.split()) + len(response.split())
        )

    def _find_response(self, prompt: str) -> str:
        """Find matching response based on prompt content."""
        for key, value in self.responses.items():
            if key in prompt.lower():
                return value
        return self.responses.get("default", "Mock response")
```

## Error Handling

```python
class LLMProviderError(Exception):
    """Base exception for LLM provider operations."""
    pass

class PromptTooLongError(LLMProviderError):
    """Prompt exceeds token limit."""
    def __init__(self, token_count: int, max_tokens: int):
        super().__init__(f"Prompt too long: {token_count} > {max_tokens}")
        self.token_count = token_count
        self.max_tokens = max_tokens

class RateLimitError(LLMProviderError):
    """Rate limit exceeded."""
    def __init__(self, retry_after: Optional[int] = None):
        super().__init__(f"Rate limit exceeded, retry after {retry_after}s")
        self.retry_after = retry_after

class ToolExecutionError(LLMProviderError):
    """Tool execution failed."""
    pass

class UnsupportedFeatureError(LLMProviderError):
    """Provider doesn't support requested feature."""
    pass
```

## Context File Mounting (Redesign Feature)

A key design change is that context is passed through mounted files rather than inline in prompts:

### Context File Structure

```
/context/
  ├── issue.md              # Issue/ticket details
  ├── pull_request.md       # PR information (if applicable)
  ├── code_snippets/        # Referenced code files
  │   ├── file1.py
  │   └── file2.py
  └── previous_output.md    # Output from previous stage
```

### Prompt Example

Instead of:
```
Here is the issue:
Title: Fix authentication bug
Description: [long description...]
```

Use:
```
Please analyze the issue described in /context/issue.md and implement a fix.
Refer to /context/previous_output.md for the design specification.
```

## Integration Points

### Used By
- Workflow Orchestrator (application service)
- Agent Scheduler (application service)
- Pipeline Manager (application service)

### Dependencies
- **IContainer** (for Claude Code adapter)
- ILogger (for logging LLM interactions)
- IMetrics (for tracking token usage)

## Implementation Notes

1. **Context files over inline context** - Always mount context as files for large contexts
2. **No credentials in containers** - Orchestrator manages all git/github operations
3. **Stream when possible** - Better UX for long-running operations
4. **Handle rate limits gracefully** - Implement exponential backoff
5. **Track token usage** - For cost monitoring and optimization
6. **Deterministic testing** - Use mock provider for reliable tests
