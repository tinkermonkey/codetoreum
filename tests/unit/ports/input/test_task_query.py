"""
Unit tests for Task Query Input Port

Tests the data structures, enums, and interface contract of the
ITaskQueryPort without requiring implementations.
"""

import pytest
from datetime import datetime, timedelta
from codetoreum.ports.input.task_query import (
    ITaskQueryPort,
    ExecutionStatus,
    ExecutionStatusInfo,
    ExecutionListItem,
    ExecutionListResult,
    ArtifactInfo,
    ArtifactListResult,
    ExecutionHistory,
    ExecutionHistoryEntry,
)


class TestExecutionStatus:
    """Tests for ExecutionStatus enum"""

    def test_execution_status_values(self):
        """Test that all execution statuses have correct values"""
        assert ExecutionStatus.PENDING.value == "pending"
        assert ExecutionStatus.RUNNING.value == "running"
        assert ExecutionStatus.COMPLETED.value == "completed"
        assert ExecutionStatus.FAILED.value == "failed"
        assert ExecutionStatus.CANCELLED.value == "cancelled"
        assert ExecutionStatus.PAUSED.value == "paused"

    def test_execution_status_membership(self):
        """Test execution status enum membership"""
        assert ExecutionStatus.COMPLETED in ExecutionStatus
        assert "unknown" not in [s.value for s in ExecutionStatus]


class TestExecutionStatusInfo:
    """Tests for ExecutionStatusInfo dataclass"""

    def test_minimal_status_info(self):
        """Test creating status info with minimal fields"""
        info = ExecutionStatusInfo(
            execution_id="exec-123",
            workflow_run_id="wf-123",
            work_item_id="item-123",
            project_name="test-project",
            pipeline_name="ci-pipeline",
            stage_name="build",
            agent_name="builder-agent",
            status=ExecutionStatus.RUNNING
        )

        assert info.execution_id == "exec-123"
        assert info.workflow_run_id == "wf-123"
        assert info.work_item_id == "item-123"
        assert info.project_name == "test-project"
        assert info.pipeline_name == "ci-pipeline"
        assert info.stage_name == "build"
        assert info.agent_name == "builder-agent"
        assert info.status == ExecutionStatus.RUNNING
        assert info.started_at is None
        assert info.completed_at is None
        assert info.duration_seconds is None
        assert info.error_message is None
        assert info.retry_count == 0
        assert info.metadata == {}

    def test_full_status_info(self):
        """Test creating status info with all fields"""
        started = datetime(2024, 1, 1, 12, 0, 0)
        completed = datetime(2024, 1, 1, 12, 5, 0)
        metadata = {"attempt": 1, "logs": "path/to/logs"}

        info = ExecutionStatusInfo(
            execution_id="exec-123",
            workflow_run_id="wf-123",
            work_item_id="item-123",
            project_name="test-project",
            pipeline_name="ci-pipeline",
            stage_name="build",
            agent_name="builder-agent",
            status=ExecutionStatus.COMPLETED,
            started_at=started,
            completed_at=completed,
            duration_seconds=300.0,
            error_message=None,
            retry_count=1,
            metadata=metadata
        )

        assert info.execution_id == "exec-123"
        assert info.status == ExecutionStatus.COMPLETED
        assert info.started_at == started
        assert info.completed_at == completed
        assert info.duration_seconds == 300.0
        assert info.retry_count == 1
        assert info.metadata == metadata


class TestExecutionListItem:
    """Tests for ExecutionListItem dataclass"""

    def test_list_item_creation(self):
        """Test creating execution list item"""
        started = datetime(2024, 1, 1, 12, 0, 0)

        item = ExecutionListItem(
            execution_id="exec-123",
            workflow_run_id="wf-123",
            work_item_id="item-123",
            stage_name="build",
            agent_name="builder-agent",
            status=ExecutionStatus.RUNNING,
            started_at=started,
            duration_seconds=150.5
        )

        assert item.execution_id == "exec-123"
        assert item.workflow_run_id == "wf-123"
        assert item.work_item_id == "item-123"
        assert item.stage_name == "build"
        assert item.agent_name == "builder-agent"
        assert item.status == ExecutionStatus.RUNNING
        assert item.started_at == started
        assert item.duration_seconds == 150.5


class TestExecutionListResult:
    """Tests for ExecutionListResult dataclass"""

    def test_list_result_creation(self):
        """Test creating execution list result"""
        executions = [
            ExecutionListItem(
                execution_id=f"exec-{i}",
                workflow_run_id="wf-123",
                work_item_id="item-123",
                stage_name="build",
                agent_name="builder-agent",
                status=ExecutionStatus.COMPLETED
            )
            for i in range(3)
        ]

        result = ExecutionListResult(
            executions=executions,
            total_count=50,
            page=1,
            page_size=10,
            has_next=True
        )

        assert len(result.executions) == 3
        assert result.total_count == 50
        assert result.page == 1
        assert result.page_size == 10
        assert result.has_next is True

    def test_empty_list_result(self):
        """Test creating empty execution list result"""
        result = ExecutionListResult(
            executions=[],
            total_count=0,
            page=1,
            page_size=10,
            has_next=False
        )

        assert len(result.executions) == 0
        assert result.total_count == 0
        assert result.has_next is False


class TestArtifactInfo:
    """Tests for ArtifactInfo dataclass"""

    def test_artifact_info_creation(self):
        """Test creating artifact info"""
        created = datetime(2024, 1, 1, 12, 0, 0)
        metadata = {"encoding": "utf-8", "hash": "abc123"}

        artifact = ArtifactInfo(
            artifact_id="art-123",
            execution_id="exec-123",
            artifact_type="code",
            name="main.py",
            path="/artifacts/main.py",
            size_bytes=1024,
            created_at=created,
            mime_type="text/x-python",
            metadata=metadata
        )

        assert artifact.artifact_id == "art-123"
        assert artifact.execution_id == "exec-123"
        assert artifact.artifact_type == "code"
        assert artifact.name == "main.py"
        assert artifact.path == "/artifacts/main.py"
        assert artifact.size_bytes == 1024
        assert artifact.created_at == created
        assert artifact.mime_type == "text/x-python"
        assert artifact.metadata == metadata


class TestArtifactListResult:
    """Tests for ArtifactListResult dataclass"""

    def test_artifact_list_creation(self):
        """Test creating artifact list result"""
        artifacts = [
            ArtifactInfo(
                artifact_id=f"art-{i}",
                execution_id="exec-123",
                artifact_type="log",
                name=f"log-{i}.txt",
                path=f"/artifacts/log-{i}.txt",
                size_bytes=512,
                created_at=datetime.now()
            )
            for i in range(3)
        ]

        result = ArtifactListResult(
            artifacts=artifacts,
            total_count=3
        )

        assert len(result.artifacts) == 3
        assert result.total_count == 3


class TestExecutionHistoryEntry:
    """Tests for ExecutionHistoryEntry dataclass"""

    def test_history_entry_creation(self):
        """Test creating execution history entry"""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        details = {"stage": "build", "result": "success"}

        entry = ExecutionHistoryEntry(
            timestamp=timestamp,
            event_type="StageCompleted",
            message="Build stage completed successfully",
            details=details
        )

        assert entry.timestamp == timestamp
        assert entry.event_type == "StageCompleted"
        assert entry.message == "Build stage completed successfully"
        assert entry.details == details


class TestExecutionHistory:
    """Tests for ExecutionHistory dataclass"""

    def test_execution_history_creation(self):
        """Test creating execution history"""
        entries = [
            ExecutionHistoryEntry(
                timestamp=datetime.now(),
                event_type=f"Event{i}",
                message=f"Event {i} occurred"
            )
            for i in range(5)
        ]

        history = ExecutionHistory(
            execution_id="exec-123",
            entries=entries,
            total_entries=5
        )

        assert history.execution_id == "exec-123"
        assert len(history.entries) == 5
        assert history.total_entries == 5


class TestITaskQueryPortInterface:
    """Tests for ITaskQueryPort interface contract"""

    def test_interface_is_abstract(self):
        """Test that ITaskQueryPort cannot be instantiated directly"""
        with pytest.raises(TypeError):
            ITaskQueryPort()

    def test_interface_has_required_methods(self):
        """Test that interface defines all required methods"""
        required_methods = [
            'get_execution_status',
            'list_executions',
            'get_artifacts',
            'get_execution_history',
            'get_workflow_executions'
        ]

        for method_name in required_methods:
            assert hasattr(ITaskQueryPort, method_name)
            method = getattr(ITaskQueryPort, method_name)
            assert callable(method)

    def test_concrete_implementation_requirements(self):
        """Test that concrete implementation must implement all methods"""

        class IncompletePort(ITaskQueryPort):
            async def get_execution_status(self, execution_id):
                pass
            # Missing: list_executions, get_artifacts, get_execution_history, get_workflow_executions

        with pytest.raises(TypeError):
            IncompletePort()

    def test_complete_implementation(self):
        """Test that complete implementation can be instantiated"""

        class CompletePort(ITaskQueryPort):
            async def get_execution_status(self, execution_id):
                return ExecutionStatusInfo(
                    execution_id=execution_id,
                    workflow_run_id="wf-123",
                    work_item_id="item-123",
                    project_name="test",
                    pipeline_name="ci",
                    stage_name="build",
                    agent_name="agent",
                    status=ExecutionStatus.RUNNING
                )

            async def list_executions(
                self,
                workflow_run_id=None,
                work_item_id=None,
                project_name=None,
                status=None,
                page=1,
                page_size=50
            ):
                return ExecutionListResult(
                    executions=[],
                    total_count=0,
                    page=page,
                    page_size=page_size,
                    has_next=False
                )

            async def get_artifacts(self, execution_id, artifact_type=None):
                return ArtifactListResult(artifacts=[], total_count=0)

            async def get_execution_history(self, execution_id, limit=None):
                return ExecutionHistory(
                    execution_id=execution_id,
                    entries=[],
                    total_entries=0
                )

            async def get_workflow_executions(self, workflow_run_id):
                return ExecutionListResult(
                    executions=[],
                    total_count=0,
                    page=1,
                    page_size=50,
                    has_next=False
                )

        port = CompletePort()
        assert isinstance(port, ITaskQueryPort)


@pytest.mark.asyncio
class TestTaskQueryPortBehavior:
    """Tests for expected behavior of implementations"""

    async def test_get_execution_status_returns_info(self):
        """Test that get_execution_status returns ExecutionStatusInfo"""

        class MockPort(ITaskQueryPort):
            async def get_execution_status(self, execution_id):
                return ExecutionStatusInfo(
                    execution_id=execution_id,
                    workflow_run_id="wf-123",
                    work_item_id="item-123",
                    project_name="test",
                    pipeline_name="ci",
                    stage_name="build",
                    agent_name="agent",
                    status=ExecutionStatus.COMPLETED
                )

            async def list_executions(
                self,
                workflow_run_id=None,
                work_item_id=None,
                project_name=None,
                status=None,
                page=1,
                page_size=50
            ):
                return ExecutionListResult(
                    executions=[],
                    total_count=0,
                    page=page,
                    page_size=page_size,
                    has_next=False
                )

            async def get_artifacts(self, execution_id, artifact_type=None):
                return ArtifactListResult(artifacts=[], total_count=0)

            async def get_execution_history(self, execution_id, limit=None):
                return ExecutionHistory(
                    execution_id=execution_id,
                    entries=[],
                    total_entries=0
                )

            async def get_workflow_executions(self, workflow_run_id):
                return ExecutionListResult(
                    executions=[],
                    total_count=0,
                    page=1,
                    page_size=50,
                    has_next=False
                )

        port = MockPort()
        status = await port.get_execution_status("exec-123")

        assert isinstance(status, ExecutionStatusInfo)
        assert status.execution_id == "exec-123"
        assert status.status == ExecutionStatus.COMPLETED

    async def test_list_executions_supports_filtering(self):
        """Test that list_executions supports optional filters"""

        class MockPort(ITaskQueryPort):
            async def get_execution_status(self, execution_id):
                return ExecutionStatusInfo(
                    execution_id=execution_id,
                    workflow_run_id="wf-123",
                    work_item_id="item-123",
                    project_name="test",
                    pipeline_name="ci",
                    stage_name="build",
                    agent_name="agent",
                    status=ExecutionStatus.RUNNING
                )

            async def list_executions(
                self,
                workflow_run_id=None,
                work_item_id=None,
                project_name=None,
                status=None,
                page=1,
                page_size=50
            ):
                # Verify parameters are passed correctly
                return ExecutionListResult(
                    executions=[],
                    total_count=0,
                    page=page,
                    page_size=page_size,
                    has_next=False
                )

            async def get_artifacts(self, execution_id, artifact_type=None):
                return ArtifactListResult(artifacts=[], total_count=0)

            async def get_execution_history(self, execution_id, limit=None):
                return ExecutionHistory(
                    execution_id=execution_id,
                    entries=[],
                    total_entries=0
                )

            async def get_workflow_executions(self, workflow_run_id):
                return ExecutionListResult(
                    executions=[],
                    total_count=0,
                    page=1,
                    page_size=50,
                    has_next=False
                )

        port = MockPort()

        # Test with filters
        result = await port.list_executions(
            project_name="test",
            status=ExecutionStatus.COMPLETED,
            page=2,
            page_size=25
        )

        assert isinstance(result, ExecutionListResult)
        assert result.page == 2
        assert result.page_size == 25
