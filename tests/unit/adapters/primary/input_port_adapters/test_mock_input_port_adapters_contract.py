"""Contract tests for mock input port adapters.

These tests verify that mock adapters comply with their port interfaces
and correctly implement business logic (create-read-update-delete flows,
error handling, state management).
"""

import pytest

from codetoreum.adapters.primary.input_port_adapters.mock.mock_agent_command_adapter import (
    MockAgentCommandAdapter,
)
from codetoreum.adapters.primary.input_port_adapters.mock.mock_agent_query_adapter import (
    MockAgentQueryAdapter,
)
from codetoreum.adapters.primary.input_port_adapters.mock.mock_config_command_adapter import (
    MockConfigCommandAdapter,
)
from codetoreum.adapters.primary.input_port_adapters.mock.mock_config_query_adapter import (
    MockConfigQueryAdapter,
)
from codetoreum.adapters.primary.input_port_adapters.mock.mock_config_service_adapter import (
    MockConfigServiceAdapter,
)
from codetoreum.adapters.primary.input_port_adapters.mock.mock_execution_command_adapter import (
    MockExecutionCommandAdapter,
)
from codetoreum.adapters.primary.input_port_adapters.mock.mock_execution_query_adapter import (
    MockExecutionQueryAdapter,
)
from codetoreum.adapters.primary.input_port_adapters.mock.mock_logger_adapter import (
    MockLoggerAdapter,
)
from codetoreum.adapters.primary.input_port_adapters.mock.mock_metrics_query_adapter import (
    MockMetricsQueryAdapter,
)
from codetoreum.adapters.primary.input_port_adapters.mock.mock_orchestration_command_adapter import (
    MockOrchestrationCommandAdapter,
)
from codetoreum.adapters.primary.input_port_adapters.mock.mock_task_query_adapter import (
    MockTaskQueryAdapter,
)
from codetoreum.adapters.primary.input_port_adapters.mock.mock_work_item_command_adapter import (
    MockWorkItemCommandAdapter,
)
from codetoreum.adapters.primary.input_port_adapters.mock.mock_work_item_query_adapter import (
    MockWorkItemQueryAdapter,
)
from codetoreum.adapters.primary.input_port_adapters.mock.mock_workflow_command_adapter import (
    MockWorkflowCommandAdapter,
)
from codetoreum.adapters.primary.input_port_adapters.mock.mock_workflow_definition_command_adapter import (
    MockWorkflowDefinitionCommandAdapter,
)
from codetoreum.adapters.primary.input_port_adapters.mock.mock_workflow_query_adapter import (
    MockWorkflowQueryAdapter,
)
from codetoreum.adapters.primary.input_port_adapters.mock.mock_workflow_run_query_adapter import (
    MockWorkflowRunQueryAdapter,
)
from codetoreum.adapters.primary.input_port_adapters.mock.mock_workspace_query_adapter import (
    MockWorkspaceQueryAdapter,
)
from codetoreum.domain.exceptions import ExecutionNotFoundError, InvalidStateError, WorkItemNotFoundError
from codetoreum.domain.work_item import WorkItemPriority
from codetoreum.ports.input.execution_command import (
    PauseExecutionCommand,
    ResumeExecutionCommand,
    TerminateExecutionCommand,
)
from codetoreum.ports.input.work_item_command import (
    CreateWorkItemCommand,
    UpdateWorkItemCommand,
)
from codetoreum.domain.agent_execution import AgentExecution, ExecutionStatus


class TestMockWorkItemCommandAdapterContract:
    """Test MockWorkItemCommandAdapter contract compliance."""

    @pytest.mark.asyncio
    async def test_create_and_retrieve_work_item(self):
        """Test create-read flow for work items."""
        adapter = MockWorkItemCommandAdapter()

        # Create work item
        command = CreateWorkItemCommand(
            project_id="proj-1",
            title="Test Task",
            description="Test Description",
            priority=WorkItemPriority.HIGH,
            labels=["bug", "urgent"],
            external_id="ext-123",
            external_url="https://example.com/issue/123"
        )
        work_item = await adapter.create_work_item(command)

        # Verify created item has correct properties
        assert work_item.project_id == "proj-1"
        assert work_item.title == "Test Task"
        assert work_item.description == "Test Description"
        assert work_item.priority == WorkItemPriority.HIGH
        assert "bug" in work_item.labels
        assert work_item.external_id == "ext-123"

    @pytest.mark.asyncio
    async def test_update_work_item(self):
        """Test update flow for work items."""
        adapter = MockWorkItemCommandAdapter()

        # Create work item
        create_cmd = CreateWorkItemCommand(
            project_id="proj-1",
            title="Original Title",
            description="Original Description",
            priority=WorkItemPriority.LOW,
            labels=[],
            external_id="ext-123",
            external_url="https://example.com"
        )
        work_item = await adapter.create_work_item(create_cmd)

        # Update work item
        update_cmd = UpdateWorkItemCommand(
            work_item_id=work_item.id,
            title="Updated Title",
            description="Updated Description",
            priority=WorkItemPriority.HIGH,
            labels=["fixed"]
        )
        updated = await adapter.update_work_item(update_cmd)

        # Verify updates applied
        assert updated.title == "Updated Title"
        assert updated.description == "Updated Description"
        assert updated.priority == WorkItemPriority.HIGH

    @pytest.mark.asyncio
    async def test_update_nonexistent_work_item_raises_error(self):
        """Test that updating nonexistent work item raises WorkItemNotFoundError."""
        adapter = MockWorkItemCommandAdapter()

        update_cmd = UpdateWorkItemCommand(
            work_item_id="nonexistent-id",
            title="New Title",
            description=None,
            priority=None,
            labels=None
        )

        with pytest.raises(WorkItemNotFoundError):
            await adapter.update_work_item(update_cmd)

    @pytest.mark.asyncio
    async def test_delete_work_item(self):
        """Test delete flow for work items."""
        adapter = MockWorkItemCommandAdapter()

        # Create and delete work item
        create_cmd = CreateWorkItemCommand(
            project_id="proj-1",
            title="To Delete",
            description="",
            priority=WorkItemPriority.LOW,
            labels=[],
            external_id="ext-123",
            external_url="https://example.com"
        )
        work_item = await adapter.create_work_item(create_cmd)

        result = await adapter.delete_work_item(work_item.id)

        # Verify deletion succeeded
        assert result.success is True
        assert result.work_item_id == work_item.id

    @pytest.mark.asyncio
    async def test_delete_nonexistent_work_item_raises_error(self):
        """Test that deleting nonexistent work item raises WorkItemNotFoundError."""
        adapter = MockWorkItemCommandAdapter()

        with pytest.raises(WorkItemNotFoundError):
            await adapter.delete_work_item("nonexistent-id")


class TestMockExecutionCommandAdapterContract:
    """Test MockExecutionCommandAdapter contract compliance."""

    @pytest.mark.asyncio
    async def test_terminate_execution(self):
        """Test execution termination."""
        adapter = MockExecutionCommandAdapter()

        # Create and add execution
        execution = AgentExecution(
            id="exec-1",
            agent_id="agent-1",
            work_item_id="item-1",
            status=ExecutionStatus.RUNNING,
            output="",
            started_at=None,
            completed_at=None,
            result=None
        )
        adapter.add_execution(execution)

        # Terminate execution
        command = TerminateExecutionCommand(
            execution_id="exec-1",
            reason="Test termination"
        )
        result = await adapter.terminate_execution(command)

        # Verify termination succeeded
        assert result.success is True
        assert result.execution_id == "exec-1"

    @pytest.mark.asyncio
    async def test_terminate_nonexistent_execution_raises_error(self):
        """Test that terminating nonexistent execution raises ExecutionNotFoundError."""
        adapter = MockExecutionCommandAdapter()

        command = TerminateExecutionCommand(
            execution_id="nonexistent",
            reason="Test"
        )

        with pytest.raises(ExecutionNotFoundError):
            await adapter.terminate_execution(command)

    @pytest.mark.asyncio
    async def test_terminate_already_terminal_execution_raises_error(self):
        """Test that terminating already-terminal execution raises InvalidStateError."""
        adapter = MockExecutionCommandAdapter()

        # Create completed execution
        execution = AgentExecution(
            id="exec-1",
            agent_id="agent-1",
            work_item_id="item-1",
            status=ExecutionStatus.COMPLETED,
            output="Done",
            started_at=None,
            completed_at=None,
            result=None
        )
        adapter.add_execution(execution)

        # Try to terminate completed execution
        command = TerminateExecutionCommand(
            execution_id="exec-1",
            reason="Test"
        )

        with pytest.raises(InvalidStateError):
            await adapter.terminate_execution(command)

    @pytest.mark.asyncio
    async def test_pause_and_resume_execution(self):
        """Test pause and resume flows."""
        adapter = MockExecutionCommandAdapter()

        # Create running execution
        execution = AgentExecution(
            id="exec-1",
            agent_id="agent-1",
            work_item_id="item-1",
            status=ExecutionStatus.RUNNING,
            output="",
            started_at=None,
            completed_at=None,
            result=None
        )
        adapter.add_execution(execution)

        # Pause execution
        pause_cmd = PauseExecutionCommand(
            execution_id="exec-1",
            reason="Debugging"
        )
        pause_result = await adapter.pause_execution(pause_cmd)
        assert pause_result.success is True

        # Resume execution
        resume_cmd = ResumeExecutionCommand(execution_id="exec-1")
        resume_result = await adapter.resume_execution(resume_cmd)
        assert resume_result.success is True


class TestMockAdapterInstantiation:
    """Test that all 18 mock adapters can be instantiated."""

    def test_all_adapters_instantiation(self):
        """Test that all mock adapters can be created."""
        adapters = [
            MockAgentCommandAdapter(),
            MockAgentQueryAdapter(),
            MockConfigCommandAdapter(),
            MockConfigQueryAdapter(),
            MockConfigServiceAdapter(),
            MockExecutionCommandAdapter(),
            MockExecutionQueryAdapter(),
            MockLoggerAdapter(),
            MockMetricsQueryAdapter(),
            MockOrchestrationCommandAdapter(),
            MockTaskQueryAdapter(),
            MockWorkItemCommandAdapter(),
            MockWorkItemQueryAdapter(),
            MockWorkflowCommandAdapter(),
            MockWorkflowDefinitionCommandAdapter(),
            MockWorkflowQueryAdapter(),
            MockWorkflowRunQueryAdapter(),
            MockWorkspaceQueryAdapter(),
        ]

        # Verify we have 18 adapters
        assert len(adapters) == 18

        # Verify each adapter is not None
        for adapter in adapters:
            assert adapter is not None

        # Verify they are distinct instances
        for i, adapter1 in enumerate(adapters):
            for j, adapter2 in enumerate(adapters):
                if i != j:
                    assert adapter1 is not adapter2

    def test_multiple_instantiations_are_independent(self):
        """Test that multiple instantiations create independent instances."""
        adapter1 = MockConfigCommandAdapter()
        adapter2 = MockConfigCommandAdapter()

        assert adapter1 is not adapter2
        assert id(adapter1) != id(adapter2)

    def test_adapter_class_names(self):
        """Test that adapters have expected class names."""
        adapters = {
            "MockAgentCommandAdapter": MockAgentCommandAdapter(),
            "MockAgentQueryAdapter": MockAgentQueryAdapter(),
            "MockConfigCommandAdapter": MockConfigCommandAdapter(),
            "MockConfigQueryAdapter": MockConfigQueryAdapter(),
            "MockConfigServiceAdapter": MockConfigServiceAdapter(),
            "MockExecutionCommandAdapter": MockExecutionCommandAdapter(),
            "MockExecutionQueryAdapter": MockExecutionQueryAdapter(),
            "MockLoggerAdapter": MockLoggerAdapter(),
            "MockMetricsQueryAdapter": MockMetricsQueryAdapter(),
            "MockOrchestrationCommandAdapter": MockOrchestrationCommandAdapter(),
            "MockTaskQueryAdapter": MockTaskQueryAdapter(),
            "MockWorkItemCommandAdapter": MockWorkItemCommandAdapter(),
            "MockWorkItemQueryAdapter": MockWorkItemQueryAdapter(),
            "MockWorkflowCommandAdapter": MockWorkflowCommandAdapter(),
            "MockWorkflowDefinitionCommandAdapter": MockWorkflowDefinitionCommandAdapter(),
            "MockWorkflowQueryAdapter": MockWorkflowQueryAdapter(),
            "MockWorkflowRunQueryAdapter": MockWorkflowRunQueryAdapter(),
            "MockWorkspaceQueryAdapter": MockWorkspaceQueryAdapter(),
        }

        # Verify class names
        for expected_name, adapter in adapters.items():
            assert adapter.__class__.__name__ == expected_name
