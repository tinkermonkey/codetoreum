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


class ICredentialProvider:
    """Interface for secure credential providers."""

    async def get_credential(self, key: str) -> Optional[str]:
        """
        Retrieve a credential securely.

        Args:
            key: Credential identifier

        Returns:
            Credential value or None if not found
        """
        raise NotImplementedError


class EnvironmentCredentialProvider(ICredentialProvider):
    """Credential provider that retrieves from environment variables."""

    async def get_credential(self, key: str) -> Optional[str]:
        """Get credential from environment."""
        import os
        return os.environ.get(key)


class SecureStoreCredentialProvider(ICredentialProvider):
    """Credential provider that uses a secure key store (placeholder for production)."""

    def __init__(self, store_path: Optional[Path] = None):
        self.store_path = store_path
        # In production, this would integrate with system keychain/vault

    async def get_credential(self, key: str) -> Optional[str]:
        """Get credential from secure store."""
        # Placeholder implementation - integrate with system keychain in production
        import os
        return os.environ.get(key)


@dataclass
class ClaudeCodeConfig:
    """Configuration for Claude Code CLI adapter."""

    # Authentication (secure references)
    api_key_credential_name: str = "ANTHROPIC_API_KEY"  # Name of credential in provider
    oauth_token_credential_name: str = "CLAUDE_CODE_OAUTH_TOKEN"  # Name of OAuth token
    credential_provider: Optional[ICredentialProvider] = None  # Secure credential provider

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

        # Initialize credential provider
        if self.config.credential_provider is None:
            self.config.credential_provider = EnvironmentCredentialProvider()

        self._validate_configuration()

        # Conversation tracking
        self._conversations: Dict[str, Dict[str, Any]] = {}

        # Track usage stats
        self._usage_stats = {
            "total_requests": 0,
            "total_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "by_model": {},
        }

    def _validate_configuration(self) -> None:
        """Validate configuration."""
        # Configuration validation will happen at runtime when credentials are retrieved
        pass

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

    async def _build_environment(
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

        # Authentication - retrieve securely from credential provider
        api_key = await self.config.credential_provider.get_credential(
            self.config.api_key_credential_name
        )
        oauth_token = await self.config.credential_provider.get_credential(
            self.config.oauth_token_credential_name
        )

        if not api_key and not oauth_token:
            raise AuthenticationError(
                f"No credentials found. Set {self.config.api_key_credential_name} "
                f"or {self.config.oauth_token_credential_name} in credential provider."
            )

        if api_key:
            env["ANTHROPIC_API_KEY"] = api_key
        elif oauth_token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token

        # Add context environment variables
        if context and context.environment_variables:
            env.update(context.environment_variables)

        return env

    def _sanitize_prompt(self, prompt: str) -> str:
        """
        Sanitize user input to prevent command injection.

        Args:
            prompt: Raw prompt text

        Returns:
            Sanitized prompt
        """
        if not prompt:
            raise ValidationError("Prompt cannot be empty")

        # Remove null bytes and control characters that could cause issues
        sanitized = prompt.replace("\x00", "").replace("\r", "\n")

        # Validate reasonable length
        if len(sanitized) > 1_000_000:  # 1MB limit
            raise PromptTooLongError("Prompt exceeds maximum length of 1MB")

        return sanitized

    def _sanitize_error_message(self, error: str) -> str:
        """
        Sanitize error messages to remove sensitive information.

        Args:
            error: Raw error message

        Returns:
            Sanitized error message
        """
        import re

        # Remove API keys (common patterns)
        sanitized = re.sub(r'sk-[a-zA-Z0-9]{20,}', '[REDACTED_API_KEY]', error)
        sanitized = re.sub(r'Bearer [a-zA-Z0-9_-]{20,}', 'Bearer [REDACTED_TOKEN]', sanitized)

        # Remove file paths that might contain sensitive info
        sanitized = re.sub(r'/home/[^/]+/', '/home/[USER]/', sanitized)
        sanitized = re.sub(r'/Users/[^/]+/', '/Users/[USER]/', sanitized)

        # Truncate to reasonable length
        if len(sanitized) > 500:
            sanitized = sanitized[:500] + "... [truncated]"

        return sanitized

    def _update_usage_stats(self, model: str, input_tokens: int, output_tokens: int) -> None:
        """Update usage statistics."""
        self._usage_stats["total_requests"] += 1
        self._usage_stats["input_tokens"] += input_tokens
        self._usage_stats["output_tokens"] += output_tokens
        self._usage_stats["total_tokens"] += input_tokens + output_tokens

        if model not in self._usage_stats["by_model"]:
            self._usage_stats["by_model"][model] = {
                "requests": 0,
                "input_tokens": 0,
                "output_tokens": 0,
            }

        self._usage_stats["by_model"][model]["requests"] += 1
        self._usage_stats["by_model"][model]["input_tokens"] += input_tokens
        self._usage_stats["by_model"][model]["output_tokens"] += output_tokens

    async def execute(
        self,
        prompt: str,
        context: Optional[ExecutionContext] = None,
        stream_callback: Optional[StreamCallback] = None,
    ) -> ExecutionResult:
        """Execute a prompt with Claude."""
        ctx = context or ExecutionContext()

        # Sanitize input
        sanitized_prompt = self._sanitize_prompt(prompt)

        # Build command with sanitized input
        cmd = self._build_command(sanitized_prompt, ctx)
        env = await self._build_environment(ctx)

        # Determine working directory
        cwd = str(ctx.working_directory) if ctx.working_directory else None

        # Execute with timeout
        start_time = datetime.now(timezone.utc)

        try:
            # Use shell=False explicitly for security
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=cwd,
                shell=False,  # Explicit: prevent shell injection
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

                # Sanitize error message to remove sensitive information
                sanitized_error = self._sanitize_error_message(error_text)

                # Parse specific errors
                if "rate limit" in error_text.lower():
                    raise RateLimitError()
                elif "authentication" in error_text.lower() or "invalid api key" in error_text.lower():
                    raise AuthenticationError("Invalid API key or OAuth token")
                else:
                    raise LLMProviderError(f"Claude execution failed: {sanitized_error}")

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

            # Update usage stats
            model = ctx.model or self.config.default_model
            self._update_usage_stats(model, usage["prompt_tokens"], usage["completion_tokens"])

            return ExecutionResult(
                content="".join(output_parts),
                model=model,
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

        Implementation Note:
        Claude Code CLI has built-in tools but doesn't support custom tool definitions via CLI.
        Tools must be provided through MCP (Model Context Protocol) servers configured in
        the execution context's .mcp.json file.

        This method validates MCP configuration and executes with the available MCP tools.
        Custom tool definitions passed to this method are not directly supported.

        Args:
            prompt: The prompt to execute
            tools: Tool definitions (informational only, not used by CLI)
            context: Execution context with MCP configuration
            stream_callback: Optional streaming callback

        Returns:
            Execution result with tool use tracked in metadata

        Raises:
            UnsupportedFeatureError: If tools are disabled or MCP not configured
        """
        if not self.config.enable_tools:
            raise UnsupportedFeatureError("Tool support is disabled in configuration")

        ctx = context or ExecutionContext()

        # Validate MCP configuration if tools are required
        if tools and self.config.enable_mcp:
            if not ctx.mcp_servers:
                # Log warning but continue - Claude has built-in tools
                import logging
                logging.warning(
                    "Tool definitions provided but no MCP servers configured. "
                    "Custom tools will not be available. Built-in Claude tools will be used."
                )

        # Execute with MCP tools available
        result = await self.execute(prompt, ctx, stream_callback)

        # Add tool information to metadata
        result.metadata["tools_available"] = len(tools)
        result.metadata["mcp_servers"] = len(ctx.mcp_servers) if ctx.mcp_servers else 0

        return result

    async def stream_completion(
        self,
        prompt: str,
        context: Optional[ExecutionContext] = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream completion tokens."""
        ctx = context or ExecutionContext()

        # Sanitize input
        sanitized_prompt = self._sanitize_prompt(prompt)

        cmd = self._build_command(sanitized_prompt, ctx)
        env = await self._build_environment(ctx)
        cwd = str(ctx.working_directory) if ctx.working_directory else None

        try:
            # Use shell=False explicitly for security
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=cwd,
                shell=False,  # Explicit: prevent shell injection
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
                error_text = stderr.decode('utf-8')
                sanitized_error = self._sanitize_error_message(error_text)
                raise StreamingError(f"Stream failed: {sanitized_error}")

            # Final chunk
            yield StreamChunk(
                content="",
                chunk_index=chunk_index,
                is_final=True,
            )

        except Exception as e:
            if isinstance(e, StreamingError):
                raise
            sanitized_error = self._sanitize_error_message(str(e))
            raise StreamingError(f"Streaming error: {sanitized_error}")

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
        Get usage statistics from adapter tracking.

        Note: These are adapter-tracked statistics, not from Claude API billing.
        For accurate billing information, consult the Anthropic Console.

        Args:
            since: Start of period (not used, returns all-time stats)

        Returns:
            Usage statistics tracked by this adapter instance
        """
        # Calculate estimated cost based on tracked usage
        total_cost = 0.0
        for model, stats in self._usage_stats["by_model"].items():
            # Use default pricing (update based on actual model pricing)
            input_cost = stats["input_tokens"] * 0.000003  # $3 per million
            output_cost = stats["output_tokens"] * 0.000015  # $15 per million
            total_cost += input_cost + output_cost

        return UsageStats(
            total_requests=self._usage_stats["total_requests"],
            total_tokens=self._usage_stats["total_tokens"],
            input_tokens=self._usage_stats["input_tokens"],
            output_tokens=self._usage_stats["output_tokens"],
            total_cost=total_cost,
            period_start=since or datetime.now(timezone.utc),
            period_end=datetime.now(timezone.utc),
            by_model=self._usage_stats["by_model"].copy(),
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
            # Use shell=False for security
            result = subprocess.run(
                [self.config.claude_cli_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                shell=False,  # Explicit: prevent shell injection
            )

            if result.returncode != 0:
                raise LLMProviderError("Claude CLI not working correctly")

            # Validate credentials are available
            try:
                api_key = await self.config.credential_provider.get_credential(
                    self.config.api_key_credential_name
                )
                oauth_token = await self.config.credential_provider.get_credential(
                    self.config.oauth_token_credential_name
                )

                if not api_key and not oauth_token:
                    raise LLMProviderError(
                        f"No credentials found. Set {self.config.api_key_credential_name} "
                        f"or {self.config.oauth_token_credential_name}"
                    )
            except Exception as e:
                raise LLMProviderError(f"Credential validation failed: {str(e)}")

            return True

        except FileNotFoundError:
            raise LLMProviderError(f"Claude CLI not found at: {self.config.claude_cli_path}")
        except subprocess.TimeoutExpired:
            raise LLMProviderError("Claude CLI version check timed out")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Async context manager exit with proper cleanup.

        Ensures cleanup happens even if exceptions occur.
        """
        try:
            # Cleanup any resources if needed
            pass
        except Exception:
            # Suppress cleanup errors to avoid masking original exception
            pass
        return False  # Don't suppress exceptions
