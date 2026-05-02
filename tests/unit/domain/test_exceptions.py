"""Tests for domain layer exceptions."""

import pytest

from codetoreum.domain.exceptions import (
    AgentNotFoundError,
    ConfigNotFoundError,
    DomainError,
    ExecutionNotFoundError,
    InvalidStateError,
    PipelineNotFoundError,
    TestOutputParseError as ParseError,
    WorkItemNotFoundError,
    WorkspaceNotFoundError,
)


class TestDomainError:
    """Test cases for DomainError base exception."""

    def test_domain_error_initialization(self):
        """Test basic domain error initialization."""
        message = "Test domain error"
        error = DomainError(message)
        assert error.message == message
        assert str(error) == message

    def test_domain_error_is_exception(self):
        """Test that DomainError is an Exception."""
        error = DomainError("test")
        assert isinstance(error, Exception)

    def test_domain_error_can_be_raised(self):
        """Test that DomainError can be raised and caught."""
        with pytest.raises(DomainError) as exc_info:
            raise DomainError("Test error message")
        assert exc_info.value.message == "Test error message"


class TestAgentNotFoundError:
    """Test cases for AgentNotFoundError."""

    def test_initialization_with_agent_id(self):
        """Test AgentNotFoundError with agent ID."""
        agent_id = "agent-123"
        error = AgentNotFoundError(agent_id)
        assert error.agent_id == agent_id
        assert "agent-123" in str(error)
        assert "Agent not found" in str(error)

    def test_is_domain_error(self):
        """Test that AgentNotFoundError is a DomainError."""
        error = AgentNotFoundError("agent-456")
        assert isinstance(error, DomainError)

    def test_can_be_raised_and_caught(self):
        """Test that AgentNotFoundError can be raised and caught."""
        with pytest.raises(AgentNotFoundError):
            raise AgentNotFoundError("agent-789")


class TestExecutionNotFoundError:
    """Test cases for ExecutionNotFoundError."""

    def test_initialization_with_execution_id(self):
        """Test ExecutionNotFoundError with execution ID."""
        execution_id = "exec-123"
        error = ExecutionNotFoundError(execution_id)
        assert error.execution_id == execution_id
        assert "exec-123" in str(error)
        assert "Execution not found" in str(error)

    def test_is_domain_error(self):
        """Test that ExecutionNotFoundError is a DomainError."""
        error = ExecutionNotFoundError("exec-456")
        assert isinstance(error, DomainError)

    def test_can_be_raised_and_caught(self):
        """Test that ExecutionNotFoundError can be raised and caught."""
        with pytest.raises(ExecutionNotFoundError):
            raise ExecutionNotFoundError("exec-789")


class TestWorkItemNotFoundError:
    """Test cases for WorkItemNotFoundError."""

    def test_initialization_with_work_item_id(self):
        """Test WorkItemNotFoundError with work item ID."""
        work_item_id = "work-123"
        error = WorkItemNotFoundError(work_item_id)
        assert error.work_item_id == work_item_id
        assert "work-123" in str(error)
        assert "Work item not found" in str(error)

    def test_is_domain_error(self):
        """Test that WorkItemNotFoundError is a DomainError."""
        error = WorkItemNotFoundError("work-456")
        assert isinstance(error, DomainError)

    def test_can_be_raised_and_caught(self):
        """Test that WorkItemNotFoundError can be raised and caught."""
        with pytest.raises(WorkItemNotFoundError):
            raise WorkItemNotFoundError("work-789")


class TestWorkspaceNotFoundError:
    """Test cases for WorkspaceNotFoundError."""

    def test_initialization_with_workspace_id(self):
        """Test WorkspaceNotFoundError with workspace ID."""
        workspace_id = "ws-123"
        error = WorkspaceNotFoundError(workspace_id)
        assert error.workspace_id == workspace_id
        assert "ws-123" in str(error)
        assert "Workspace not found" in str(error)

    def test_is_domain_error(self):
        """Test that WorkspaceNotFoundError is a DomainError."""
        error = WorkspaceNotFoundError("ws-456")
        assert isinstance(error, DomainError)

    def test_can_be_raised_and_caught(self):
        """Test that WorkspaceNotFoundError can be raised and caught."""
        with pytest.raises(WorkspaceNotFoundError):
            raise WorkspaceNotFoundError("ws-789")


class TestParseErrorException:
    """Test cases for ParseError (TestOutputParseError)."""

    def test_initialization_with_test_output(self):
        """Test ParseError with test output details."""
        message = "Invalid test output format"
        test_type = "pytest"
        raw_data = {"key": "value"}
        error = ParseError(message, test_type, raw_data)
        assert error.message == message
        assert error.test_type == test_type
        assert error.raw_data == raw_data
        assert message in str(error)

    def test_initialization_with_string_raw_data(self):
        """Test ParseError with string raw data."""
        message = "Parse error"
        test_type = "unittest"
        raw_data = "unparseable output"
        error = ParseError(message, test_type, raw_data)
        assert error.raw_data == "unparseable output"

    def test_initialization_with_list_raw_data(self):
        """Test ParseError with list raw data."""
        message = "Parse error"
        test_type = "nose"
        raw_data = ["line1", "line2"]
        error = ParseError(message, test_type, raw_data)
        assert error.raw_data == ["line1", "line2"]

    def test_is_domain_error(self):
        """Test that ParseError is a DomainError."""
        error = ParseError("error", "pytest", {})
        assert isinstance(error, DomainError)

    def test_can_be_raised_and_caught(self):
        """Test that ParseError can be raised and caught."""
        with pytest.raises(ParseError):
            raise ParseError("error", "pytest", {})


class TestPipelineNotFoundError:
    """Test cases for PipelineNotFoundError."""

    def test_initialization_with_pipeline_id(self):
        """Test PipelineNotFoundError with pipeline ID."""
        pipeline_id = "pipeline-123"
        error = PipelineNotFoundError(pipeline_id)
        assert error.pipeline_id == pipeline_id
        assert "pipeline-123" in str(error)
        assert "Pipeline not found" in str(error)

    def test_is_domain_error(self):
        """Test that PipelineNotFoundError is a DomainError."""
        error = PipelineNotFoundError("pipeline-456")
        assert isinstance(error, DomainError)

    def test_can_be_raised_and_caught(self):
        """Test that PipelineNotFoundError can be raised and caught."""
        with pytest.raises(PipelineNotFoundError):
            raise PipelineNotFoundError("pipeline-789")


class TestConfigNotFoundError:
    """Test cases for ConfigNotFoundError."""

    def test_initialization_with_config_id(self):
        """Test ConfigNotFoundError with config ID."""
        config_id = "config-123"
        error = ConfigNotFoundError(config_id)
        assert error.config_id == config_id
        assert "config-123" in str(error)
        assert "Configuration not found" in str(error)

    def test_is_domain_error(self):
        """Test that ConfigNotFoundError is a DomainError."""
        error = ConfigNotFoundError("config-456")
        assert isinstance(error, DomainError)

    def test_can_be_raised_and_caught(self):
        """Test that ConfigNotFoundError can be raised and caught."""
        with pytest.raises(ConfigNotFoundError):
            raise ConfigNotFoundError("config-789")


class TestInvalidStateError:
    """Test cases for InvalidStateError."""

    def test_initialization_with_message(self):
        """Test InvalidStateError with message."""
        message = "Cannot transition from pending to completed"
        error = InvalidStateError(message)
        assert error.message == message
        assert message in str(error)

    def test_is_domain_error(self):
        """Test that InvalidStateError is a DomainError."""
        error = InvalidStateError("Invalid state")
        assert isinstance(error, DomainError)

    def test_can_be_raised_and_caught(self):
        """Test that InvalidStateError can be raised and caught."""
        with pytest.raises(InvalidStateError):
            raise InvalidStateError("Invalid state transition")

    def test_custom_error_messages(self):
        """Test InvalidStateError with various custom messages."""
        messages = [
            "State transition from A to B is invalid",
            "Cannot update completed work item",
            "Agent is in wrong state for execution",
        ]
        for msg in messages:
            error = InvalidStateError(msg)
            assert msg in str(error)
