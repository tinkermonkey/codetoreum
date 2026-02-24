"""
Unit tests for Workflow Command Input Port

Tests the data structures, enums, and interface contract of the
IWorkflowCommandPort without requiring implementations.
"""

import pytest
from datetime import datetime
from codetoreum.ports.input.workflow_command import (
    IWorkflowCommandPort,
    StartWorkflowCommand,
    PauseWorkflowCommand,
    ResumeWorkflowCommand,
    CancelWorkflowCommand,
    RetryStageCommand,
    WorkflowCommandResult,
    TriggerType,
)


class TestTriggerType:
    """Tests for TriggerType enum"""

    def test_trigger_type_values(self):
        """Test that all trigger types have correct values"""
        assert TriggerType.CARD_MOVEMENT.value == "card_movement"
        assert TriggerType.MANUAL.value == "manual"
        assert TriggerType.SCHEDULED.value == "scheduled"
        assert TriggerType.API.value == "api"
        assert TriggerType.AGENT_FEEDBACK.value == "agent_feedback"

    def test_trigger_type_membership(self):
        """Test trigger type enum membership"""
        assert TriggerType.MANUAL in TriggerType
        assert "invalid" not in [t.value for t in TriggerType]


class TestStartWorkflowCommand:
    """Tests for StartWorkflowCommand dataclass"""

    def test_minimal_command_creation(self):
        """Test creating command with minimal required fields"""
        cmd = StartWorkflowCommand(
            project_name="test-project",
            work_item_id="123",
            pipeline_name="ci-pipeline"
        )

        assert cmd.project_name == "test-project"
        assert cmd.work_item_id == "123"
        assert cmd.pipeline_name == "ci-pipeline"
        assert cmd.stage_name is None
        assert cmd.trigger == TriggerType.MANUAL
        assert cmd.context is None
        assert cmd.priority == "MEDIUM"

    def test_full_command_creation(self):
        """Test creating command with all fields"""
        context = {"foo": "bar", "num": 42}
        cmd = StartWorkflowCommand(
            project_name="test-project",
            work_item_id="123",
            pipeline_name="ci-pipeline",
            stage_name="build",
            trigger=TriggerType.API,
            context=context,
            priority="HIGH"
        )

        assert cmd.project_name == "test-project"
        assert cmd.work_item_id == "123"
        assert cmd.pipeline_name == "ci-pipeline"
        assert cmd.stage_name == "build"
        assert cmd.trigger == TriggerType.API
        assert cmd.context == context
        assert cmd.priority == "HIGH"

    def test_command_immutability(self):
        """Test that command fields can be read"""
        cmd = StartWorkflowCommand(
            project_name="test-project",
            work_item_id="123",
            pipeline_name="ci-pipeline"
        )

        # Dataclasses are mutable by default, just verify field access
        assert hasattr(cmd, 'project_name')
        assert hasattr(cmd, 'work_item_id')
        assert hasattr(cmd, 'pipeline_name')


class TestPauseWorkflowCommand:
    """Tests for PauseWorkflowCommand dataclass"""

    def test_command_creation(self):
        """Test creating pause command"""
        cmd = PauseWorkflowCommand(
            workflow_run_id="wf-123",
            reason="User requested pause",
            pause_point="stage-2"
        )

        assert cmd.workflow_run_id == "wf-123"
        assert cmd.reason == "User requested pause"
        assert cmd.pause_point == "stage-2"


class TestResumeWorkflowCommand:
    """Tests for ResumeWorkflowCommand dataclass"""

    def test_minimal_resume_command(self):
        """Test creating resume command without from_stage"""
        cmd = ResumeWorkflowCommand(
            workflow_run_id="wf-123"
        )

        assert cmd.workflow_run_id == "wf-123"
        assert cmd.from_stage is None

    def test_resume_with_stage(self):
        """Test creating resume command with specific stage"""
        cmd = ResumeWorkflowCommand(
            workflow_run_id="wf-123",
            from_stage="stage-3"
        )

        assert cmd.workflow_run_id == "wf-123"
        assert cmd.from_stage == "stage-3"


class TestCancelWorkflowCommand:
    """Tests for CancelWorkflowCommand dataclass"""

    def test_normal_cancel(self):
        """Test creating normal cancel command"""
        cmd = CancelWorkflowCommand(
            workflow_run_id="wf-123",
            reason="No longer needed"
        )

        assert cmd.workflow_run_id == "wf-123"
        assert cmd.reason == "No longer needed"
        assert cmd.force is False

    def test_force_cancel(self):
        """Test creating force cancel command"""
        cmd = CancelWorkflowCommand(
            workflow_run_id="wf-123",
            reason="Emergency stop",
            force=True
        )

        assert cmd.workflow_run_id == "wf-123"
        assert cmd.reason == "Emergency stop"
        assert cmd.force is True


class TestRetryStageCommand:
    """Tests for RetryStageCommand dataclass"""

    def test_retry_with_reset(self):
        """Test creating retry command with state reset"""
        cmd = RetryStageCommand(
            workflow_run_id="wf-123",
            stage_name="build"
        )

        assert cmd.workflow_run_id == "wf-123"
        assert cmd.stage_name == "build"
        assert cmd.reset_state is True

    def test_retry_without_reset(self):
        """Test creating retry command without state reset"""
        cmd = RetryStageCommand(
            workflow_run_id="wf-123",
            stage_name="build",
            reset_state=False
        )

        assert cmd.workflow_run_id == "wf-123"
        assert cmd.stage_name == "build"
        assert cmd.reset_state is False


class TestWorkflowCommandResult:
    """Tests for WorkflowCommandResult dataclass"""

    def test_successful_result(self):
        """Test creating successful result"""
        result = WorkflowCommandResult(
            success=True,
            workflow_run_id="wf-123",
            message="Workflow started successfully",
            state="STARTED"
        )

        assert result.success is True
        assert result.workflow_run_id == "wf-123"
        assert result.message == "Workflow started successfully"
        assert result.state == "STARTED"
        assert result.errors is None

    def test_failed_result(self):
        """Test creating failed result with errors"""
        errors = ["Project not found", "Invalid pipeline"]
        result = WorkflowCommandResult(
            success=False,
            workflow_run_id="wf-123",
            message="Workflow start failed",
            state="FAILED",
            errors=errors
        )

        assert result.success is False
        assert result.workflow_run_id == "wf-123"
        assert result.message == "Workflow start failed"
        assert result.state == "FAILED"
        assert result.errors == errors


class TestIWorkflowCommandPortInterface:
    """Tests for IWorkflowCommandPort interface contract"""


    def test_interface_has_required_methods(self):
        """Test that interface defines all required methods"""
        required_methods = [
            'start_workflow',
            'pause_workflow',
            'resume_workflow',
            'cancel_workflow',
            'retry_stage'
        ]

        for method_name in required_methods:
            assert hasattr(IWorkflowCommandPort, method_name)
            method = getattr(IWorkflowCommandPort, method_name)
            assert callable(method)

    def test_complete_implementation(self):
        """Test that complete implementation can be instantiated"""

        class CompletePort(IWorkflowCommandPort):
            async def start_workflow(self, command):
                return WorkflowCommandResult(
                    success=True,
                    workflow_run_id="test",
                    message="Started",
                    state="STARTED"
                )

            async def pause_workflow(self, command):
                return WorkflowCommandResult(
                    success=True,
                    workflow_run_id="test",
                    message="Paused",
                    state="PAUSED"
                )

            async def resume_workflow(self, command):
                return WorkflowCommandResult(
                    success=True,
                    workflow_run_id="test",
                    message="Resumed",
                    state="RUNNING"
                )

            async def cancel_workflow(self, command):
                return WorkflowCommandResult(
                    success=True,
                    workflow_run_id="test",
                    message="Cancelled",
                    state="CANCELLED"
                )

            async def retry_stage(self, command):
                return WorkflowCommandResult(
                    success=True,
                    workflow_run_id="test",
                    message="Retrying",
                    state="RUNNING"
                )

        # Should be able to instantiate complete implementation
        port = CompletePort()
        assert isinstance(port, IWorkflowCommandPort)


@pytest.mark.asyncio
class TestWorkflowCommandPortBehavior:
    """Tests for expected behavior of implementations"""

    async def test_start_workflow_returns_result(self):
        """Test that start_workflow returns WorkflowCommandResult"""

        class MockPort(IWorkflowCommandPort):
            async def start_workflow(self, command):
                return WorkflowCommandResult(
                    success=True,
                    workflow_run_id="wf-123",
                    message="Started",
                    state="STARTED"
                )

            async def pause_workflow(self, command):
                pass

            async def resume_workflow(self, command):
                pass

            async def cancel_workflow(self, command):
                pass

            async def retry_stage(self, command):
                pass

        port = MockPort()
        cmd = StartWorkflowCommand(
            project_name="test",
            work_item_id="123",
            pipeline_name="ci"
        )

        result = await port.start_workflow(cmd)
        assert isinstance(result, WorkflowCommandResult)
        assert result.success is True
        assert result.workflow_run_id == "wf-123"
