"""Contract tests for ILLMProvider interface.

These tests verify the data models and contracts for the LLM provider port.
"""

from pathlib import Path
from types import MappingProxyType
from uuid import uuid4

import pytest

from codetoreum.ports.output.llm_provider import ExecutionContext, ToolDefinition


class TestExecutionContextValidation:
    """Test ExecutionContext validation and construction."""

    def test_valid_execution_context(self) -> None:
        """Test creating a valid execution context."""
        context = ExecutionContext(
            model="claude-3.5-sonnet",
            temperature=0.7,
            max_tokens=2000,
        )

        assert context.model == "claude-3.5-sonnet"
        assert context.temperature == 0.7
        assert context.max_tokens == 2000

    def test_model_none_valid(self) -> None:
        """Test that model can be None."""
        context = ExecutionContext(model=None)
        assert context.model is None

    def test_model_empty_string_invalid(self) -> None:
        """Test that empty model string raises ValueError."""
        with pytest.raises(ValueError, match="model must be a non-empty string or None"):
            ExecutionContext(model="")

    def test_temperature_valid_range(self) -> None:
        """Test temperature values within valid range."""
        for temp in [0.0, 0.5, 1.0, 2.0]:
            context = ExecutionContext(temperature=temp)
            assert context.temperature == temp

    def test_temperature_below_range(self) -> None:
        """Test that temperature below 0 raises ValueError."""
        with pytest.raises(ValueError, match="temperature must be a number between 0.0 and 2.0"):
            ExecutionContext(temperature=-0.1)

    def test_temperature_above_range(self) -> None:
        """Test that temperature above 2.0 raises ValueError."""
        with pytest.raises(ValueError, match="temperature must be a number between 0.0 and 2.0"):
            ExecutionContext(temperature=2.1)

    def test_temperature_invalid_type(self) -> None:
        """Test that invalid temperature type raises ValueError."""
        with pytest.raises(ValueError, match="temperature must be a number between 0.0 and 2.0"):
            ExecutionContext(temperature="0.7")  # type: ignore

    def test_max_tokens_positive_integer(self) -> None:
        """Test max_tokens with positive integer."""
        context = ExecutionContext(max_tokens=1000)
        assert context.max_tokens == 1000

    def test_max_tokens_none(self) -> None:
        """Test that max_tokens can be None."""
        context = ExecutionContext(max_tokens=None)
        assert context.max_tokens is None

    def test_max_tokens_zero_invalid(self) -> None:
        """Test that max_tokens of 0 raises ValueError."""
        with pytest.raises(ValueError, match="max_tokens must be a positive integer or None"):
            ExecutionContext(max_tokens=0)

    def test_max_tokens_negative_invalid(self) -> None:
        """Test that negative max_tokens raises ValueError."""
        with pytest.raises(ValueError, match="max_tokens must be a positive integer or None"):
            ExecutionContext(max_tokens=-100)

    def test_max_tokens_boolean_invalid(self) -> None:
        """Test that boolean max_tokens raises ValueError."""
        with pytest.raises(ValueError, match="max_tokens must be a positive integer or None"):
            ExecutionContext(max_tokens=True)  # type: ignore

    def test_top_p_valid_range(self) -> None:
        """Test top_p values within valid range."""
        for p in [0.0, 0.5, 1.0]:
            context = ExecutionContext(top_p=p)
            assert context.top_p == p

    def test_top_p_below_range(self) -> None:
        """Test that top_p below 0 raises ValueError."""
        with pytest.raises(ValueError, match="top_p must be a number between 0.0 and 1.0"):
            ExecutionContext(top_p=-0.1)

    def test_top_p_above_range(self) -> None:
        """Test that top_p above 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="top_p must be a number between 0.0 and 1.0"):
            ExecutionContext(top_p=1.1)

    def test_frequency_penalty_valid_range(self) -> None:
        """Test frequency_penalty values within valid range."""
        for penalty in [-2.0, -1.0, 0.0, 1.0, 2.0]:
            context = ExecutionContext(frequency_penalty=penalty)
            assert context.frequency_penalty == penalty

    def test_frequency_penalty_below_range(self) -> None:
        """Test that frequency_penalty below -2.0 raises ValueError."""
        with pytest.raises(ValueError, match="frequency_penalty must be a number between -2.0 and 2.0"):
            ExecutionContext(frequency_penalty=-2.1)

    def test_frequency_penalty_above_range(self) -> None:
        """Test that frequency_penalty above 2.0 raises ValueError."""
        with pytest.raises(ValueError, match="frequency_penalty must be a number between -2.0 and 2.0"):
            ExecutionContext(frequency_penalty=2.1)

    def test_presence_penalty_valid_range(self) -> None:
        """Test presence_penalty values within valid range."""
        for penalty in [-2.0, -1.0, 0.0, 1.0, 2.0]:
            context = ExecutionContext(presence_penalty=penalty)
            assert context.presence_penalty == penalty

    def test_presence_penalty_below_range(self) -> None:
        """Test that presence_penalty below -2.0 raises ValueError."""
        with pytest.raises(ValueError, match="presence_penalty must be a number between -2.0 and 2.0"):
            ExecutionContext(presence_penalty=-2.1)

    def test_presence_penalty_above_range(self) -> None:
        """Test that presence_penalty above 2.0 raises ValueError."""
        with pytest.raises(ValueError, match="presence_penalty must be a number between -2.0 and 2.0"):
            ExecutionContext(presence_penalty=2.1)

    def test_conversation_id_valid(self) -> None:
        """Test conversation_id with valid string."""
        context = ExecutionContext(conversation_id="conv-123")
        assert context.conversation_id == "conv-123"

    def test_conversation_id_none(self) -> None:
        """Test that conversation_id can be None."""
        context = ExecutionContext(conversation_id=None)
        assert context.conversation_id is None

    def test_conversation_id_empty_invalid(self) -> None:
        """Test that empty conversation_id raises ValueError."""
        with pytest.raises(ValueError, match="conversation_id must be a non-empty string or None"):
            ExecutionContext(conversation_id="")

    def test_message_history_coerced_to_tuple(self) -> None:
        """Test that message_history list is coerced to tuple."""
        context = ExecutionContext(message_history=[{"role": "user", "content": "hello"}])
        assert isinstance(context.message_history, tuple)
        assert context.message_history == ({"role": "user", "content": "hello"},)

    def test_system_prompt_valid(self) -> None:
        """Test system_prompt with valid string."""
        prompt = "You are a helpful assistant."
        context = ExecutionContext(system_prompt=prompt)
        assert context.system_prompt == prompt

    def test_system_prompt_none(self) -> None:
        """Test that system_prompt can be None."""
        context = ExecutionContext(system_prompt=None)
        assert context.system_prompt is None

    def test_system_prompt_empty_invalid(self) -> None:
        """Test that empty system_prompt raises ValueError."""
        with pytest.raises(ValueError, match="system_prompt must be a non-empty string or None"):
            ExecutionContext(system_prompt="")

    def test_timeout_seconds_positive(self) -> None:
        """Test timeout_seconds with positive integer."""
        context = ExecutionContext(timeout_seconds=300)
        assert context.timeout_seconds == 300

    def test_timeout_seconds_zero_invalid(self) -> None:
        """Test that zero timeout_seconds raises ValueError."""
        with pytest.raises(ValueError, match="timeout_seconds must be a positive integer"):
            ExecutionContext(timeout_seconds=0)

    def test_timeout_seconds_negative_invalid(self) -> None:
        """Test that negative timeout_seconds raises ValueError."""
        with pytest.raises(ValueError, match="timeout_seconds must be a positive integer"):
            ExecutionContext(timeout_seconds=-1)

    def test_timeout_seconds_boolean_invalid(self) -> None:
        """Test that boolean timeout_seconds raises ValueError."""
        with pytest.raises(ValueError, match="timeout_seconds must be a positive integer"):
            ExecutionContext(timeout_seconds=True)  # type: ignore

    def test_retry_on_error_boolean(self) -> None:
        """Test retry_on_error with boolean values."""
        context1 = ExecutionContext(retry_on_error=True)
        context2 = ExecutionContext(retry_on_error=False)
        assert context1.retry_on_error is True
        assert context2.retry_on_error is False

    def test_retry_on_error_invalid(self) -> None:
        """Test that non-boolean retry_on_error raises ValueError."""
        with pytest.raises(ValueError, match="retry_on_error must be a boolean"):
            ExecutionContext(retry_on_error="true")  # type: ignore

    def test_cache_response_boolean(self) -> None:
        """Test cache_response with boolean values."""
        context1 = ExecutionContext(cache_response=True)
        context2 = ExecutionContext(cache_response=False)
        assert context1.cache_response is True
        assert context2.cache_response is False

    def test_cache_response_invalid(self) -> None:
        """Test that non-boolean cache_response raises ValueError."""
        with pytest.raises(ValueError, match="cache_response must be a boolean"):
            ExecutionContext(cache_response="false")  # type: ignore

    def test_working_directory_valid(self) -> None:
        """Test working_directory with Path object."""
        path = Path("/workspace")
        context = ExecutionContext(working_directory=path)
        assert context.working_directory == path

    def test_working_directory_none(self) -> None:
        """Test that working_directory can be None."""
        context = ExecutionContext(working_directory=None)
        assert context.working_directory is None

    def test_working_directory_invalid(self) -> None:
        """Test that string working_directory raises ValueError."""
        with pytest.raises(ValueError, match="working_directory must be a Path or None"):
            ExecutionContext(working_directory="/workspace")  # type: ignore

    def test_mounted_context_files_coerced_to_mapping_proxy(self) -> None:
        """Test that mounted_context_files dict is coerced to MappingProxyType."""
        context = ExecutionContext(mounted_context_files={"file.txt": "/path/to/file.txt"})
        assert isinstance(context.mounted_context_files, MappingProxyType)

    def test_available_files_coerced_to_tuple(self) -> None:
        """Test that available_files list is coerced to tuple."""
        context = ExecutionContext(available_files=["file1.txt", "file2.txt"])
        assert isinstance(context.available_files, tuple)
        assert context.available_files == ("file1.txt", "file2.txt")

    def test_environment_variables_coerced_to_mapping_proxy(self) -> None:
        """Test that environment_variables dict is coerced to MappingProxyType."""
        context = ExecutionContext(environment_variables={"VAR": "value"})
        assert isinstance(context.environment_variables, MappingProxyType)

    def test_mcp_servers_coerced_to_tuple(self) -> None:
        """Test that mcp_servers list is coerced to tuple."""
        servers = [{"name": "server1", "command": "python server.py"}]
        context = ExecutionContext(mcp_servers=servers)
        assert isinstance(context.mcp_servers, tuple)

    def test_user_id_valid(self) -> None:
        """Test user_id with valid string."""
        context = ExecutionContext(user_id="user-123")
        assert context.user_id == "user-123"

    def test_user_id_none(self) -> None:
        """Test that user_id can be None."""
        context = ExecutionContext(user_id=None)
        assert context.user_id is None

    def test_session_id_valid(self) -> None:
        """Test session_id with valid string."""
        context = ExecutionContext(session_id="session-123")
        assert context.session_id == "session-123"

    def test_session_id_none(self) -> None:
        """Test that session_id can be None."""
        context = ExecutionContext(session_id=None)
        assert context.session_id is None

    def test_session_id_empty_invalid(self) -> None:
        """Test that empty session_id raises ValueError."""
        with pytest.raises(ValueError, match="session_id must be a non-empty string or None"):
            ExecutionContext(session_id="")

    def test_execution_id_valid(self) -> None:
        """Test execution_id with valid string."""
        exec_id = str(uuid4())
        context = ExecutionContext(execution_id=exec_id)
        assert context.execution_id == exec_id

    def test_execution_id_none(self) -> None:
        """Test that execution_id can be None."""
        context = ExecutionContext(execution_id=None)
        assert context.execution_id is None

    def test_metadata_coerced_to_mapping_proxy(self) -> None:
        """Test that metadata dict is coerced to MappingProxyType."""
        context = ExecutionContext(metadata={"key": "value"})
        assert isinstance(context.metadata, MappingProxyType)

    def test_execution_context_immutable(self) -> None:
        """Test that ExecutionContext is immutable."""
        context = ExecutionContext(model="test-model")

        with pytest.raises(AttributeError):
            context.model = "new-model"  # type: ignore

    def test_execution_context_all_defaults(self) -> None:
        """Test creating ExecutionContext with all defaults."""
        context = ExecutionContext()

        assert context.model is None
        assert context.temperature == 0.7
        assert context.max_tokens is None
        assert context.top_p == 1.0
        assert context.frequency_penalty == 0.0
        assert context.presence_penalty == 0.0
        assert context.conversation_id is None
        assert context.message_history == ()
        assert context.system_prompt is None
        assert context.timeout_seconds == 300
        assert context.retry_on_error is True
        assert context.cache_response is False
        assert context.working_directory is None
        assert isinstance(context.mounted_context_files, MappingProxyType)
        assert context.available_files == ()
        assert isinstance(context.environment_variables, MappingProxyType)
        assert context.mcp_servers == ()
        assert context.user_id is None
        assert context.session_id is None
        assert context.execution_id is None
        assert isinstance(context.metadata, MappingProxyType)


class TestToolDefinitionValidation:
    """Test ToolDefinition validation and construction."""

    def test_valid_tool_definition(self) -> None:
        """Test creating a valid tool definition."""
        tool = ToolDefinition(
            name="search",
            description="Search the web",
            parameters=MappingProxyType(
                {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "description": "Max results"},
                }
            ),
            required=("query",),
        )

        assert tool.name == "search"
        assert tool.description == "Search the web"
        assert "query" in tool.parameters
        assert tool.required == ("query",)

    def test_tool_definition_empty_required(self) -> None:
        """Test tool definition with empty required tuple."""
        tool = ToolDefinition(
            name="greet",
            description="Greet user",
            parameters=MappingProxyType({}),
            required=(),
        )

        assert tool.required == ()

    def test_tool_definition_immutable(self) -> None:
        """Test that ToolDefinition is immutable."""
        tool = ToolDefinition(
            name="test",
            description="Test tool",
            parameters=MappingProxyType({}),
        )

        with pytest.raises(AttributeError):
            tool.name = "modified"  # type: ignore
