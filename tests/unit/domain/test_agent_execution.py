"""Unit tests for AgentExecution entity."""

import pytest
from datetime import datetime
from time import sleep

from codetoreum.domain import (
    AgentExecution,
    DomainError,
    ExecutionCompleted,
    ExecutionFailed,
    ExecutionInitialized,
    ExecutionStarted,
    ExecutionStatus,
    ExecutionTimeout,
)


class TestAgentExecutionCreation:
    """Test agent execution creation."""

    def test_create_execution(self):
        """Test creating execution with valid data."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement feature X",
            model="claude-sonnet-4-5",
        )

        assert execution.id is not None
        assert execution.agent_id == "agent-1"
        assert execution.work_item_id == "work-1"
        assert execution.workflow_id == "workflow-1"
        assert execution.stage_name == "coding"
        assert execution.prompt == "Implement feature X"
        assert execution.model == "claude-sonnet-4-5"
        assert execution.status == ExecutionStatus.INITIALIZED
        assert execution.session_id is None
        assert execution.container_name is None
        assert execution.output is None
        assert execution.error_message is None
        assert execution.exit_code is None
        assert execution.input_tokens == 0
        assert execution.output_tokens == 0
        assert execution.duration_seconds is None
        assert execution.initialized_at is not None
        assert execution.started_at is None
        assert execution.completed_at is None

    def test_create_execution_with_session_id(self):
        """Test creating execution with session ID."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Continue from previous",
            model="claude-sonnet-4-5",
            session_id="session-123",
        )

        assert execution.session_id == "session-123"

    def test_create_emits_event(self):
        """Test that creation emits ExecutionInitialized event."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement feature",
            model="claude-sonnet-4-5",
        )

        events = execution.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], ExecutionInitialized)
        assert events[0].payload["agent_id"] == "agent-1"
        assert events[0].payload["work_item_id"] == "work-1"
        assert events[0].payload["stage_name"] == "coding"


class TestAgentExecutionLifecycle:
    """Test execution lifecycle transitions."""

    def test_start_execution(self):
        """Test starting execution."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )
        execution.clear_events()

        execution.start(container_name="agent-container-1")

        assert execution.status == ExecutionStatus.RUNNING
        assert execution.started_at is not None
        assert execution.container_name == "agent-container-1"

        events = execution.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], ExecutionStarted)
        assert events[0].payload["container_name"] == "agent-container-1"

    def test_start_execution_without_container(self):
        """Test starting execution without container."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )

        execution.start()

        assert execution.status == ExecutionStatus.RUNNING
        assert execution.container_name is None

    def test_start_non_initialized_execution_raises_error(self):
        """Test that starting non-initialized execution raises error."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )
        execution.start()

        with pytest.raises(DomainError) as exc:
            execution.start()
        assert "Cannot start execution in status running" in str(exc.value)

    def test_complete_execution(self):
        """Test completing execution successfully."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )
        execution.start()
        sleep(0.01)  # Small delay to ensure duration is measurable
        execution.clear_events()

        execution.complete(
            output="Feature implemented successfully",
            input_tokens=1000,
            output_tokens=2000,
            session_id="session-456",
        )

        assert execution.status == ExecutionStatus.COMPLETED
        assert execution.output == "Feature implemented successfully"
        assert execution.input_tokens == 1000
        assert execution.output_tokens == 2000
        assert execution.exit_code == 0
        assert execution.session_id == "session-456"
        assert execution.completed_at is not None
        assert execution.duration_seconds is not None
        assert execution.duration_seconds > 0

        events = execution.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], ExecutionCompleted)
        assert events[0].payload["input_tokens"] == 1000
        assert events[0].payload["output_tokens"] == 2000

    def test_complete_without_session_id(self):
        """Test completing without updating session ID."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
            session_id="original-session",
        )
        execution.start()

        execution.complete(output="Done", input_tokens=100, output_tokens=200)

        assert execution.session_id == "original-session"

    def test_complete_non_running_execution_raises_error(self):
        """Test that completing non-running execution raises error."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )

        with pytest.raises(DomainError) as exc:
            execution.complete(output="Done", input_tokens=100, output_tokens=200)
        assert "Cannot complete execution in status initialized" in str(exc.value)

    def test_fail_execution(self):
        """Test failing execution."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )
        execution.start()
        sleep(0.01)
        execution.clear_events()

        execution.fail(error_message="Container crashed", exit_code=137)

        assert execution.status == ExecutionStatus.FAILED
        assert execution.error_message == "Container crashed"
        assert execution.exit_code == 137
        assert execution.completed_at is not None
        assert execution.duration_seconds is not None

        events = execution.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], ExecutionFailed)
        assert events[0].payload["error_message"] == "Container crashed"
        assert events[0].payload["exit_code"] == 137

    def test_fail_before_start(self):
        """Test failing execution before it starts."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )

        execution.fail(error_message="Failed to initialize", exit_code=1)

        assert execution.status == ExecutionStatus.FAILED
        assert execution.duration_seconds is None  # Never started

    def test_fail_without_exit_code(self):
        """Test failing without exit code."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )
        execution.start()

        execution.fail(error_message="Unknown error")

        assert execution.exit_code is None

    def test_fail_completed_execution_raises_error(self):
        """Test that failing completed execution raises error."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )
        execution.start()
        execution.complete(output="Done", input_tokens=100, output_tokens=200)

        with pytest.raises(DomainError):
            execution.fail(error_message="Should not work")

    def test_timeout_execution(self):
        """Test timing out execution."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )
        execution.start()
        sleep(0.01)
        execution.clear_events()

        execution.timeout()

        assert execution.status == ExecutionStatus.TIMEOUT
        assert execution.error_message == "Execution exceeded timeout"
        assert execution.exit_code == -1
        assert execution.completed_at is not None
        assert execution.duration_seconds is not None

        events = execution.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], ExecutionTimeout)

    def test_timeout_non_running_execution_raises_error(self):
        """Test that timing out non-running execution raises error."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )

        with pytest.raises(DomainError):
            execution.timeout()


class TestAgentExecutionQueryMethods:
    """Test query methods."""

    def test_is_completed(self):
        """Test is_completed returns True when completed."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )
        execution.start()
        execution.complete(output="Done", input_tokens=100, output_tokens=200)

        assert execution.is_completed()

    def test_is_completed_when_not_completed(self):
        """Test is_completed returns False when not completed."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )

        assert not execution.is_completed()

    def test_is_failed_when_failed(self):
        """Test is_failed returns True when failed."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )
        execution.start()
        execution.fail("Error")

        assert execution.is_failed()

    def test_is_failed_when_timeout(self):
        """Test is_failed returns True when timed out."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )
        execution.start()
        execution.timeout()

        assert execution.is_failed()

    def test_is_failed_when_not_failed(self):
        """Test is_failed returns False when not failed."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )

        assert not execution.is_failed()

    def test_is_terminal_when_completed(self):
        """Test is_terminal returns True when completed."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )
        execution.start()
        execution.complete(output="Done", input_tokens=100, output_tokens=200)

        assert execution.is_terminal()

    def test_is_terminal_when_failed(self):
        """Test is_terminal returns True when failed."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )
        execution.start()
        execution.fail("Error")

        assert execution.is_terminal()

    def test_is_terminal_when_timeout(self):
        """Test is_terminal returns True when timed out."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )
        execution.start()
        execution.timeout()

        assert execution.is_terminal()

    def test_is_terminal_when_running(self):
        """Test is_terminal returns False when running."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )
        execution.start()

        assert not execution.is_terminal()

    def test_get_total_tokens(self):
        """Test get_total_tokens returns sum of input and output tokens."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )
        execution.start()
        execution.complete(output="Done", input_tokens=1500, output_tokens=2500)

        assert execution.get_total_tokens() == 4000

    def test_get_total_tokens_before_completion(self):
        """Test get_total_tokens returns 0 before completion."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )

        assert execution.get_total_tokens() == 0


class TestAgentExecutionEventManagement:
    """Test event management."""

    def test_get_pending_events(self):
        """Test getting pending events."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )
        execution.start()

        events = execution.get_pending_events()

        assert len(events) == 2
        assert isinstance(events[0], ExecutionInitialized)
        assert isinstance(events[1], ExecutionStarted)

    def test_clear_events(self):
        """Test clearing pending events."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )

        execution.clear_events()

        assert len(execution.get_pending_events()) == 0

    def test_get_pending_events_returns_copy(self):
        """Test that get_pending_events returns a copy."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement",
            model="claude-sonnet-4-5",
        )

        events = execution.get_pending_events()
        events.clear()

        # Original events should still be there
        assert len(execution.get_pending_events()) == 1


class TestAgentExecutionCompleteLifecycle:
    """Test complete execution lifecycles."""

    def test_successful_execution_lifecycle(self):
        """Test complete successful execution lifecycle."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement feature X",
            model="claude-sonnet-4-5",
        )

        assert execution.status == ExecutionStatus.INITIALIZED
        assert not execution.is_terminal()

        execution.start(container_name="container-1")
        assert execution.status == ExecutionStatus.RUNNING
        assert not execution.is_terminal()
        assert not execution.is_completed()

        execution.complete(
            output="Feature implemented",
            input_tokens=1000,
            output_tokens=2000,
            session_id="session-1",
        )

        assert execution.status == ExecutionStatus.COMPLETED
        assert execution.is_completed()
        assert execution.is_terminal()
        assert not execution.is_failed()
        assert execution.get_total_tokens() == 3000
        assert execution.exit_code == 0

        events = execution.get_pending_events()
        assert len(events) == 3
        assert isinstance(events[0], ExecutionInitialized)
        assert isinstance(events[1], ExecutionStarted)
        assert isinstance(events[2], ExecutionCompleted)

    def test_failed_execution_lifecycle(self):
        """Test complete failed execution lifecycle."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement feature X",
            model="claude-sonnet-4-5",
        )

        execution.start()
        execution.fail("Execution error", exit_code=1)

        assert execution.status == ExecutionStatus.FAILED
        assert execution.is_failed()
        assert execution.is_terminal()
        assert not execution.is_completed()
        assert execution.error_message == "Execution error"
        assert execution.exit_code == 1

    def test_timeout_execution_lifecycle(self):
        """Test complete timeout execution lifecycle."""
        execution = AgentExecution.create(
            agent_id="agent-1",
            work_item_id="work-1",
            workflow_id="workflow-1",
            stage_name="coding",
            prompt="Implement feature X",
            model="claude-sonnet-4-5",
        )

        execution.start()
        execution.timeout()

        assert execution.status == ExecutionStatus.TIMEOUT
        assert execution.is_failed()
        assert execution.is_terminal()
        assert not execution.is_completed()
        assert execution.error_message is not None
        assert "timeout" in execution.error_message.lower()
        assert execution.exit_code == -1
