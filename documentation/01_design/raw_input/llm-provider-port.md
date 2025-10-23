# ILLMProvider Port

## Overview

The `ILLMProvider` port defines the interface for integrating with Large Language Model providers. This port abstracts the complexity of different LLM APIs and provides a unified interface for AI-powered agent execution.

## Interface Definition

```python
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Callable, AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class ILLMProvider(ABC):
    """
    Interface for Large Language Model providers.
    
    This port abstracts LLM operations, supporting various providers
    like Claude, GPT-4, PaLM, and local models.
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
            prompt: The prompt to execute
            context: Execution context with parameters and history
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
    
    @abstractmethod
    async def execute_structured(self,
                                prompt: str,
                                schema: Dict[str, Any],
                                context: Optional[ExecutionContext] = None) -> StructuredResult:
        """
        Execute prompt expecting structured output.
        
        Args:
            prompt: The prompt to execute
            schema: JSON schema for expected output
            context: Execution context
            
        Returns:
            StructuredResult: Parsed structured response
            
        Raises:
            ValidationError: Response doesn't match schema
            UnsupportedFeatureError: Provider doesn't support structured output
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
    
    @abstractmethod
    async def get_conversation_history(self,
                                      conversation_id: ConversationId) -> List[Message]:
        """
        Get conversation message history.
        
        Args:
            conversation_id: Conversation to get history for
            
        Returns:
            List[Message]: Conversation messages
            
        Raises:
            ConversationNotFoundError: Conversation doesn't exist
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
    
    # Code Execution
    
    @abstractmethod
    async def execute_code_generation(self,
                                     specification: str,
                                     language: str,
                                     context: Optional[CodeContext] = None) -> CodeResult:
        """
        Generate code from specification.
        
        Args:
            specification: Code requirements
            language: Programming language
            context: Code generation context
            
        Returns:
            CodeResult: Generated code with metadata
            
        Raises:
            UnsupportedLanguageError: Language not supported
        """
        pass
    
    @abstractmethod
    async def execute_code_review(self,
                                 code: str,
                                 language: str,
                                 review_criteria: Optional[List[str]] = None) -> ReviewResult:
        """
        Review code for issues and improvements.
        
        Args:
            code: Code to review
            language: Programming language
            review_criteria: Specific review criteria
            
        Returns:
            ReviewResult: Review findings and suggestions
        """
        pass
    
    # Model Information
    
    @abstractmethod
    async def get_model_info(self) -> ModelInfo:
        """
        Get information about the current model.
        
        Returns:
            ModelInfo: Model capabilities and limits
        """
        pass
    
    @abstractmethod
    async def list_available_models(self) -> List[ModelInfo]:
        """
        List all available models from this provider.
        
        Returns:
            List[ModelInfo]: Available models
        """
        pass
    
    @abstractmethod
    async def validate_prompt(self,
                            prompt: str,
                            context: Optional[ExecutionContext] = None) -> ValidationResult:
        """
        Validate prompt before execution.
        
        Args:
            prompt: Prompt to validate
            context: Execution context
            
        Returns:
            ValidationResult: Validation results
        """
        pass
    
    # Token Management
    
    @abstractmethod
    async def count_tokens(self,
                         text: str,
                         model: Optional[str] = None) -> int:
        """
        Count tokens in text.
        
        Args:
            text: Text to count tokens for
            model: Specific model to use for counting
            
        Returns:
            int: Token count
        """
        pass
    
    @abstractmethod
    async def get_usage_stats(self,
                            since: Optional[datetime] = None) -> UsageStats:
        """
        Get usage statistics.
        
        Args:
            since: Get stats since this time
            
        Returns:
            UsageStats: Token usage and costs
        """
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
    
    # Workspace context
    working_directory: Optional[str] = None
    available_files: List[str] = field(default_factory=list)
    environment_variables: Dict[str, str] = field(default_factory=dict)
    
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
        """Calculate cost based on token usage."""
        # Provider-specific cost calculation
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

### Tool Definitions

```python
@dataclass
class ToolDefinition:
    """Definition of a tool/function available to LLM."""
    
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema
    required_params: List[str] = field(default_factory=list)
    
    # Execution
    handler: Optional[Callable] = None
    async_handler: Optional[Callable] = None
    
    # Constraints
    max_calls_per_turn: Optional[int] = None
    requires_confirmation: bool = False

@dataclass
class ToolCall:
    """A tool call made by the LLM."""
    
    tool_name: str
    arguments: Dict[str, Any]
    call_id: str = field(default_factory=lambda: str(uuid4()))
    
    # Result
    result: Optional[Any] = None
    error: Optional[str] = None
    
    # Metadata
    timestamp: datetime = field(default_factory=datetime.utcnow)
```

## Implementation Examples

### Claude Provider

```python
class ClaudeProvider(ILLMProvider):
    """Anthropic Claude implementation."""
    
    def __init__(self, api_key: str, model: str = "claude-3-opus-20240229"):
        self.client = Anthropic(api_key=api_key)
        self.model = model
    
    async def execute(self,
                     prompt: str,
                     context: Optional[ExecutionContext] = None,
                     stream_callback: Optional[StreamCallback] = None) -> ExecutionResult:
        context = context or ExecutionContext()
        
        # Prepare messages
        messages = self._prepare_messages(prompt, context)
        
        # Count tokens
        prompt_tokens = await self.count_tokens(str(messages))
        
        if prompt_tokens > 200000:  # Claude's limit
            raise PromptTooLongError(f"Prompt exceeds limit: {prompt_tokens}")
        
        try:
            # Execute with streaming
            if stream_callback:
                return await self._execute_streaming(
                    messages, 
                    context, 
                    stream_callback
                )
            
            # Execute without streaming
            response = await self.client.messages.create(
                model=self.model,
                messages=messages,
                max_tokens=context.max_tokens or 4096,
                temperature=context.temperature,
                system=context.system_prompt
            )
            
            return ExecutionResult(
                content=response.content[0].text,
                model=response.model,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens
            )
            
        except AnthropicRateLimitError as e:
            raise RateLimitError(retry_after=e.retry_after)
        except AnthropicAPIError as e:
            raise ExternalServiceError("Claude", str(e))
    
    async def _execute_streaming(self,
                                messages: List[Dict],
                                context: ExecutionContext,
                                stream_callback: StreamCallback) -> ExecutionResult:
        """Execute with streaming."""
        chunks = []
        chunk_index = 0
        
        async with self.client.messages.stream(
            model=self.model,
            messages=messages,
            max_tokens=context.max_tokens or 4096,
            temperature=context.temperature
        ) as stream:
            async for chunk in stream:
                stream_chunk = StreamChunk(
                    content=chunk.delta.text or "",
                    chunk_index=chunk_index,
                    is_final=chunk.type == "message_stop"
                )
                
                chunks.append(stream_chunk.content)
                await stream_callback(stream_chunk)
                chunk_index += 1
        
        # Get final message info
        final_message = await stream.get_final_message()
        
        return ExecutionResult(
            content="".join(chunks),
            model=final_message.model,
            prompt_tokens=final_message.usage.input_tokens,
            completion_tokens=final_message.usage.output_tokens,
            total_tokens=final_message.usage.input_tokens + final_message.usage.output_tokens
        )
```

### OpenAI Provider

```python
class OpenAIProvider(ILLMProvider):
    """OpenAI GPT implementation."""
    
    def __init__(self, api_key: str, model: str = "gpt-4-turbo"):
        self.client = OpenAI(api_key=api_key)
        self.model = model
    
    async def execute_with_tools(self,
                                prompt: str,
                                tools: List[ToolDefinition],
                                context: Optional[ExecutionContext] = None,
                                stream_callback: Optional[StreamCallback] = None) -> ExecutionResult:
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

### Mock Provider for Testing

```python
class MockLLMProvider(ILLMProvider):
    """Mock LLM provider for testing."""
    
    def __init__(self,
                 responses: Optional[Dict[str, str]] = None,
                 latency_ms: int = 0,
                 should_fail: bool = False):
        self.responses = responses or {"default": "Mock response"}
        self.latency_ms = latency_ms
        self.should_fail = should_fail
        self.conversations: Dict[ConversationId, List[Message]] = {}
        self.call_history: List[Dict[str, Any]] = []
    
    async def execute(self,
                     prompt: str,
                     context: Optional[ExecutionContext] = None,
                     stream_callback: Optional[StreamCallback] = None) -> ExecutionResult:
        # Record call
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
        response = self.responses.get("default")
        for key, value in self.responses.items():
            if key in prompt:
                response = value
                break
        
        # Simulate streaming
        if stream_callback:
            words = response.split()
            for i, word in enumerate(words):
                chunk = StreamChunk(
                    content=word + " ",
                    chunk_index=i,
                    is_final=(i == len(words) - 1)
                )
                await stream_callback(chunk)
        
        # Return result
        return ExecutionResult(
            content=response,
            model="mock-model",
            prompt_tokens=len(prompt.split()),
            completion_tokens=len(response.split()),
            total_tokens=len(prompt.split()) + len(response.split())
        )
```

## Testing

### Unit Tests

```python
class TestLLMProvider:
    """Test LLM provider implementations."""
    
    @pytest.fixture
    def mock_provider(self):
        return MockLLMProvider(
            responses={
                "hello": "Hello! How can I help you?",
                "code": "def hello():\n    print('Hello, World!')"
            }
        )
    
    async def test_basic_execution(self, mock_provider):
        """Test basic prompt execution."""
        result = await mock_provider.execute("Say hello")
        
        assert "Hello" in result.content
        assert result.prompt_tokens > 0
        assert result.completion_tokens > 0
    
    async def test_streaming_execution(self, mock_provider):
        """Test streaming response."""
        chunks = []
        
        async def collect_chunks(chunk: StreamChunk):
            chunks.append(chunk)
        
        result = await mock_provider.execute(
            "Say hello",
            stream_callback=collect_chunks
        )
        
        assert len(chunks) > 0
        assert chunks[-1].is_final
        assert "".join(c.content for c in chunks).strip() == result.content.strip()
    
    async def test_conversation_context(self, mock_provider):
        """Test conversation continuity."""
        # Create conversation
        conv_id = await mock_provider.create_conversation(
            system_prompt="You are a helpful assistant"
        )
        
        # First message
        result1 = await mock_provider.continue_conversation(
            conv_id,
            "Remember the number 42"
        )
        
        # Second message
        result2 = await mock_provider.continue_conversation(
            conv_id,
            "What number did I ask you to remember?"
        )
        
        # Check history
        history = await mock_provider.get_conversation_history(conv_id)
        assert len(history) == 4  # 2 user + 2 assistant
```

### Integration Tests

```python
class TestClaudeIntegration:
    """Integration tests for Claude provider."""
    
    @pytest.mark.integration
    async def test_real_claude_execution(self):
        """Test with real Claude API."""
        provider = ClaudeProvider(api_key=os.getenv("CLAUDE_API_KEY"))
        
        result = await provider.execute(
            "Write a haiku about testing software",
            context=ExecutionContext(
                temperature=0.5,
                max_tokens=100
            )
        )
        
        assert result.content
        assert "\n" in result.content  # Haiku has line breaks
        assert result.total_tokens > 0
```

## Error Handling

### Retry Strategy

```python
class RetryingLLMProvider(ILLMProvider):
    """LLM provider with automatic retry."""
    
    def __init__(self, 
                 delegate: ILLMProvider,
                 max_retries: int = 3,
                 backoff_factor: float = 2.0):
        self.delegate = delegate
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
    
    async def execute(self, prompt: str, context: Optional[ExecutionContext] = None, 
                     stream_callback: Optional[StreamCallback] = None) -> ExecutionResult:
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                return await self.delegate.execute(prompt, context, stream_callback)
            except RateLimitError as e:
                wait_time = e.retry_after or (self.backoff_factor ** attempt)
                await asyncio.sleep(wait_time)
                last_error = e
            except ExternalServiceError as e:
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(self.backoff_factor ** attempt)
                last_error = e
        
        raise last_error
```

## Performance Optimization

### Caching

```python
class CachedLLMProvider(ILLMProvider):
    """LLM provider with response caching."""
    
    def __init__(self,
                 delegate: ILLMProvider,
                 cache: ICache,
                 ttl_seconds: int = 3600):
        self.delegate = delegate
        self.cache = cache
        self.ttl = ttl_seconds
    
    async def execute(self, prompt: str, context: Optional[ExecutionContext] = None,
                     stream_callback: Optional[StreamCallback] = None) -> ExecutionResult:
        # Generate cache key
        cache_key = self._generate_cache_key(prompt, context)
        
        # Check cache
        cached = await self.cache.get(cache_key)
        if cached:
            result = ExecutionResult(**cached)
            result.cached = True
            return result
        
        # Execute and cache
        result = await self.delegate.execute(prompt, context, stream_callback)
        
        # Don't cache streaming responses
        if not stream_callback:
            await self.cache.set(
                cache_key,
                result.__dict__,
                ttl=self.ttl
            )
        
        return result
```

## Next Steps

- Review [IEventStore Port](event-store-port.md)
- Explore [Secondary Adapters](../adapters/secondary/00-overview.md)
- See [Application Services](../services/00-overview.md)
