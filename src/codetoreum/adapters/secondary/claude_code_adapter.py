"""Claude Code adapter for ILLMProvider interface."""

import asyncio
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from codetoreum.ports.exceptions import (
    AuthenticationError,
    ConversationNotFoundError,
    ExternalServiceError,
    LLMProviderError,
    PromptTooLongError,
    RateLimitError,
    StreamingError,
    UnsupportedFeatureError,
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


@dataclass
class ClaudeCodeConfig:
    """Configuration for Claude Code CLI adapter."""

    # Authentication
    api_key: Optional[str] = None  # Anthropic API key
    oauth_token: Optional[str] = None  # Claude Code OAuth token

    # CLI configuration
    claude_cli_path: str = "claude"  # Path to Claude CLI executable
    default_model: str = "claude-sonnet-4-5-20250929"
    permission_mode: str = "bypassPermissions"  # or "askForPermissions"

    # Output configuration
    output_format: str = "stream-json"  # or "text"
    verbose: bool = False

    # Execution limits
    default_timeout_seconds: int = 300  # 5 minutes
    max_context_tokens: int = 200000

    # Features
    enable_mcp: bool = True
    enable_tools: bool = True


class ClaudeCodeAdapter(ILLMProvider):
    """
    Claude Code CLI adapter for LLM operations.

    This adapter executes the Claude Code CLI to run prompts with the
    Claude AI model. It supports streaming, tool use, and containerized execution.
    """

    def __init__(self, config: ClaudeCodeConfig):
        """
        Initialize Claude Code adapter.

        Args:
            config: Claude Code configuration
        """
        self.config = config
        self._validate_configuration()

        # Conversation tracking
        self._conversations: Dict[str, Dict[str, Any]] = {}

    def _validate_configuration(self) -> None:
        """Validate configuration."""
        if not self.config.api_key and not self.config.oauth_token:
            raise LLMProviderError("Either api_key or oauth_token must be provided")

    def _build_command(
        self,
        prompt: str,
        context: Optional[ExecutionContext] = None,
    ) -> List[str]:
        """
        Build Claude CLI command.

        Args:
            prompt: Prompt to execute
            context: Execution context

        Returns:
            Command as list of arguments
        """
        ctx = context or ExecutionContext()

        cmd = [
            self.config.claude_cli_path,
            "--print",
            "--output-format",
            self.config.output_format,
            "--permission-mode",
            self.config.permission_mode,
        ]

        # Model selection
        model = ctx.model or self.config.default_model
        cmd.extend(["--model", model])

        # Verbose output
        if self.config.verbose:
            cmd.append("--verbose")

        # MCP configuration
        if self.config.enable_mcp and ctx.mcp_servers:
            mcp_config_path = ctx.working_directory / ".mcp.json" if ctx.working_directory else None
            if mcp_config_path and mcp_config_path.exists():
                cmd.extend(["--mcp-config", str(mcp_config_path)])

        # Conversation continuity
        if ctx.conversation_id:
            cmd.extend(["--session-id", ctx.conversation_id])

        # Add the prompt (must be last)
        cmd.append(prompt)

        return cmd

    def _build_environment(
        self,
        context: Optional[ExecutionContext] = None,
    ) -> Dict[str, str]:
        """
        Build environment variables.

        Args:
            context: Execution context

        Returns:
            Environment variables dictionary
        """
        import os

        env = os.environ.copy()

        # Authentication
        if self.config.api_key:
            env["ANTHROPIC_API_KEY"] = self.config.api_key
        elif self.config.oauth_token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = self.config.oauth_token

        # Add context environment variables
        if context and context.environment_variables:
            env.update(context.environment_variables)

        return env

    async def execute(
        self,
        prompt: str,
        context: Optional[ExecutionContext] = None,
        stream_callback: Optional[StreamCallback] = None,
    ) -> ExecutionResult:
        """Execute a prompt with Claude."""
        ctx = context or ExecutionContext()

        # Build command
        cmd = self._build_command(prompt, ctx)
        env = self._build_environment(ctx)

        # Determine working directory
        cwd = str(ctx.working_directory) if ctx.working_directory else None

        # Execute with timeout
        start_time = datetime.now(timezone.utc)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=cwd,
            )

            # Process streaming output
            output_parts: List[str] = []
            conversation_id = ctx.conversation_id
            usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            chunk_index = 0

            async def read_stream():
                nonlocal conversation_id, usage, chunk_index

                async for line in process.stdout:
                    if not line:
                        break

                    try:
                        event = json.loads(line.decode("utf-8"))

                        # Extract text content
                        if event.get("type") == "assistant":
                            content_items = event.get("message", {}).get("content", [])
                            for item in content_items:
                                if item.get("type") == "text":
                                    text = item.get("text", "")
                                    output_parts.append(text)

                                    # Call stream callback
                                    if stream_callback:
                                        chunk = StreamChunk(
                                            content=text,
                                            chunk_index=chunk_index,
                                            is_final=False,
                                        )
                                        await stream_callback(chunk)
                                        chunk_index += 1

                        # Track usage
                        if "usage" in event:
                            usage["prompt_tokens"] += event["usage"].get("input_tokens", 0)
                            usage["completion_tokens"] += event["usage"].get("output_tokens", 0)
                            usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]

                        # Capture conversation ID
                        if "session_id" in event:
                            conversation_id = event["session_id"]

                    except json.JSONDecodeError:
                        # Skip non-JSON lines
                        pass

            # Read with timeout
            timeout = ctx.timeout_seconds
            try:
                await asyncio.wait_for(read_stream(), timeout=timeout)
            except asyncio.TimeoutError:
                process.kill()
                raise ExternalServiceError("Claude", "Execution timeout")

            # Wait for process completion
            await process.wait()

            # Check exit code
            if process.returncode != 0:
                stderr = await process.stderr.read()
                error_text = stderr.decode("utf-8")

                # Parse specific errors
                if "rate limit" in error_text.lower():
                    raise RateLimitError()
                elif "authentication" in error_text.lower() or "invalid api key" in error_text.lower():
                    raise AuthenticationError("Invalid API key or OAuth token")
                else:
                    raise LLMProviderError(f"Claude execution failed: {error_text}")

            # Send final chunk
            if stream_callback:
                final_chunk = StreamChunk(
                    content="",
                    chunk_index=chunk_index,
                    is_final=True,
                )
                await stream_callback(final_chunk)

            # Build result
            end_time = datetime.now(timezone.utc)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            return ExecutionResult(
                content="".join(output_parts),
                model=ctx.model or self.config.default_model,
                completion_tokens=usage["completion_tokens"],
                prompt_tokens=usage["prompt_tokens"],
                total_tokens=usage["total_tokens"],
                started_at=start_time,
                completed_at=end_time,
                duration_ms=duration_ms,
                conversation_id=conversation_id,
                metadata={
                    "exit_code": process.returncode,
                    "working_directory": cwd,
                },
            )

        except FileNotFoundError:
            raise LLMProviderError(f"Claude CLI not found at: {self.config.claude_cli_path}")
        except Exception as e:
            if isinstance(e, (LLMProviderError, AuthenticationError, RateLimitError)):
                raise
            raise LLMProviderError(f"Execution error: {str(e)}")

    async def execute_with_tools(
        self,
        prompt: str,
        tools: List[ToolDefinition],
        context: Optional[ExecutionContext] = None,
        stream_callback: Optional[StreamCallback] = None,
    ) -> ExecutionResult:
        """
        Execute prompt with tool calling.

        Note: Claude Code CLI doesn't directly support tool definitions.
        This would need to be implemented via MCP servers or custom tooling.
        """
        if not self.config.enable_tools:
            raise UnsupportedFeatureError("Tool support is disabled")

        # For now, execute without explicit tool support
        # Tools would be available via MCP servers if configured
        return await self.execute(prompt, context, stream_callback)

    async def stream_completion(
        self,
        prompt: str,
        context: Optional[ExecutionContext] = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream completion tokens."""
        ctx = context or ExecutionContext()

        cmd = self._build_command(prompt, ctx)
        env = self._build_environment(ctx)
        cwd = str(ctx.working_directory) if ctx.working_directory else None

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=cwd,
            )

            chunk_index = 0

            async for line in process.stdout:
                if not line:
                    break

                try:
                    event = json.loads(line.decode("utf-8"))

                    if event.get("type") == "assistant":
                        content_items = event.get("message", {}).get("content", [])
                        for item in content_items:
                            if item.get("type") == "text":
                                chunk = StreamChunk(
                                    content=item.get("text", ""),
                                    chunk_index=chunk_index,
                                    is_final=False,
                                )
                                yield chunk
                                chunk_index += 1

                except json.JSONDecodeError:
                    pass

            await process.wait()

            if process.returncode != 0:
                stderr = await process.stderr.read()
                raise StreamingError(f"Stream failed: {stderr.decode('utf-8')}")

            # Final chunk
            yield StreamChunk(
                content="",
                chunk_index=chunk_index,
                is_final=True,
            )

        except Exception as e:
            if isinstance(e, StreamingError):
                raise
            raise StreamingError(f"Streaming error: {str(e)}")

    async def create_conversation(
        self,
        system_prompt: Optional[str] = None,
        parameters: Optional[ExecutionContext] = None,
    ) -> str:
        """
        Create a new conversation.

        Note: Claude Code CLI manages sessions internally.
        This creates a local tracking entry.
        """
        import uuid

        conversation_id = str(uuid.uuid4())

        self._conversations[conversation_id] = {
            "system_prompt": system_prompt,
            "parameters": parameters,
            "created_at": datetime.now(timezone.utc),
            "message_count": 0,
        }

        return conversation_id

    async def continue_conversation(
        self,
        conversation_id: str,
        message: str,
        stream_callback: Optional[StreamCallback] = None,
    ) -> ExecutionResult:
        """Continue an existing conversation."""
        if conversation_id not in self._conversations:
            raise ConversationNotFoundError(f"Conversation {conversation_id} not found")

        conv_data = self._conversations[conversation_id]

        # Build context with conversation ID
        context = conv_data.get("parameters") or ExecutionContext()
        context.conversation_id = conversation_id

        # Execute with conversation context
        result = await self.execute(message, context, stream_callback)

        # Update conversation tracking
        conv_data["message_count"] += 1
        conv_data["last_message_at"] = datetime.now(timezone.utc)

        return result

    async def get_model_info(self) -> ModelInfo:
        """Get information about the current model."""
        model = self.config.default_model

        # Model information for Claude Sonnet 4.5
        return ModelInfo(
            model_id=model,
            provider="Anthropic",
            display_name="Claude Sonnet 4.5",
            context_window=200000,
            max_output_tokens=8192,
            supports_tools=True,
            supports_streaming=True,
            cost_per_input_token=0.000003,  # $3 per million tokens
            cost_per_output_token=0.000015,  # $15 per million tokens
            metadata={
                "version": "20250929",
                "capabilities": ["vision", "tools", "streaming", "long_context"],
            },
        )

    async def list_available_models(self) -> List[ModelInfo]:
        """List available Claude models."""
        return [
            await self.get_model_info(),
            ModelInfo(
                model_id="claude-sonnet-3-5-20241022",
                provider="Anthropic",
                display_name="Claude 3.5 Sonnet",
                context_window=200000,
                max_output_tokens=8192,
                supports_tools=True,
                supports_streaming=True,
                cost_per_input_token=0.000003,
                cost_per_output_token=0.000015,
            ),
            ModelInfo(
                model_id="claude-opus-4-20250514",
                provider="Anthropic",
                display_name="Claude Opus 4",
                context_window=200000,
                max_output_tokens=16384,
                supports_tools=True,
                supports_streaming=True,
                cost_per_input_token=0.000015,
                cost_per_output_token=0.000075,
            ),
        ]

    async def count_tokens(
        self,
        text: str,
        model: Optional[str] = None,
    ) -> int:
        """
        Count tokens in text.

        Note: This is an approximation. Exact token counts require the tokenizer.
        """
        # Rough approximation: ~4 characters per token for English text
        return len(text) // 4

    async def get_usage_stats(
        self,
        since: Optional[datetime] = None,
    ) -> UsageStats:
        """
        Get usage statistics.

        Note: Claude Code CLI doesn't provide usage tracking.
        This returns placeholder data.
        """
        return UsageStats(
            total_requests=0,
            total_tokens=0,
            input_tokens=0,
            output_tokens=0,
            total_cost=0.0,
            period_start=since or datetime.now(timezone.utc),
            period_end=datetime.now(timezone.utc),
            by_model={},
        )

    def supports_feature(self, feature: str) -> bool:
        """Check if a feature is supported."""
        supported_features = {
            "streaming": True,
            "tools": self.config.enable_tools,
            "mcp": self.config.enable_mcp,
            "vision": True,
            "long_context": True,
            "conversations": True,
        }

        return supported_features.get(feature, False)

    async def validate_configuration(self) -> bool:
        """Validate Claude Code configuration."""
        # Check CLI exists
        try:
            result = subprocess.run(
                [self.config.claude_cli_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                raise LLMProviderError("Claude CLI not working correctly")

            return True

        except FileNotFoundError:
            raise LLMProviderError(f"Claude CLI not found at: {self.config.claude_cli_path}")
        except subprocess.TimeoutExpired:
            raise LLMProviderError("Claude CLI version check timed out")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        pass
