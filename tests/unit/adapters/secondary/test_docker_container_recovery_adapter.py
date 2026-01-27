"""Unit tests for DockerContainerRecoveryAdapter.

These tests verify:
- Metadata extraction from Docker labels
- Container assessment logic
- Recovery action execution
- Error handling
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codetoreum.adapters.secondary.docker_container_recovery_adapter import (
    DockerContainerRecoveryAdapter,
)
from codetoreum.domain.types import (
    CONTAINER_LABEL_AGENT,
    CONTAINER_LABEL_EXECUTION_ID,
    CONTAINER_LABEL_PROJECT,
    CONTAINER_LABEL_TASK_ID,
    CONTAINER_LABEL_TYPE,
    CONTAINER_LABEL_WORK_ITEM_ID,
    CONTAINER_TYPE_AGENT,
)
from codetoreum.ports.exceptions import ContainerError, StorageError


class TestDockerContainerRecoveryAdapterInitialization:
    """Tests for adapter initialization."""

    def test_adapter_initialization(self):
        """Adapter should initialize with event store."""
        event_store = MagicMock()
        adapter = DockerContainerRecoveryAdapter(event_store=event_store)

        assert adapter.event_store is event_store
        assert adapter.container_timeout_hours == 2

    def test_adapter_custom_timeout(self):
        """Adapter should accept custom timeout."""
        event_store = MagicMock()
        adapter = DockerContainerRecoveryAdapter(
            event_store=event_store, container_timeout_hours=4
        )

        assert adapter.container_timeout_hours == 4


class TestDockerContainerMetadataExtraction:
    """Tests for extracting metadata from Docker labels."""

    def test_extract_metadata_valid_container(self):
        """Should extract metadata from container with all labels."""
        event_store = MagicMock()
        adapter = DockerContainerRecoveryAdapter(event_store=event_store)

        # Mock Docker container
        container = MagicMock()
        container.id = "abc123def456"
        container.short_id = "abc123"
        container.name = "test-container"
        container.attrs = {
            "Created": "2026-01-27T12:00:00Z",
            "Config": {
                "Labels": {
                    CONTAINER_LABEL_TYPE: CONTAINER_TYPE_AGENT,
                    CONTAINER_LABEL_PROJECT: "proj-1",
                    CONTAINER_LABEL_AGENT: "agent-1",
                    CONTAINER_LABEL_TASK_ID: "task-1",
                    CONTAINER_LABEL_WORK_ITEM_ID: "work-123",
                    CONTAINER_LABEL_EXECUTION_ID: "exec-456",
                }
            },
        }

        metadata = adapter._extract_metadata(container)

        assert metadata is not None
        assert metadata.container_id == "abc123def456"
        assert metadata.container_name == "test-container"
        assert metadata.project_id == "proj-1"
        assert metadata.agent_id == "agent-1"
        assert metadata.task_id == "task-1"
        assert metadata.work_item_id == "work-123"
        assert metadata.execution_id == "exec-456"

    def test_extract_metadata_missing_type_label(self):
        """Should return None if type label is missing."""
        event_store = MagicMock()
        adapter = DockerContainerRecoveryAdapter(event_store=event_store)

        # Mock Docker container without type label
        container = MagicMock()
        container.short_id = "abc123"
        container.attrs = {
            "Created": "2026-01-27T12:00:00Z",
            "Config": {
                "Labels": {
                    CONTAINER_LABEL_PROJECT: "proj-1",
                    CONTAINER_LABEL_AGENT: "agent-1",
                    CONTAINER_LABEL_TASK_ID: "task-1",
                }
            },
        }

        metadata = adapter._extract_metadata(container)

        assert metadata is None

    def test_extract_metadata_missing_required_label(self):
        """Should return None if required labels are missing."""
        event_store = MagicMock()
        adapter = DockerContainerRecoveryAdapter(event_store=event_store)

        # Mock Docker container missing project_id
        container = MagicMock()
        container.short_id = "abc123"
        container.attrs = {
            "Created": "2026-01-27T12:00:00Z",
            "Config": {
                "Labels": {
                    CONTAINER_LABEL_TYPE: CONTAINER_TYPE_AGENT,
                    CONTAINER_LABEL_AGENT: "agent-1",
                    CONTAINER_LABEL_TASK_ID: "task-1",
                }
            },
        }

        metadata = adapter._extract_metadata(container)

        assert metadata is None

    def test_extract_metadata_optional_labels(self):
        """Should handle containers with optional labels."""
        event_store = MagicMock()
        adapter = DockerContainerRecoveryAdapter(event_store=event_store)

        # Mock Docker container with only required labels
        container = MagicMock()
        container.id = "abc123"
        container.name = "test-container"
        container.attrs = {
            "Created": "2026-01-27T12:00:00Z",
            "Config": {
                "Labels": {
                    CONTAINER_LABEL_TYPE: CONTAINER_TYPE_AGENT,
                    CONTAINER_LABEL_PROJECT: "proj-1",
                    CONTAINER_LABEL_AGENT: "agent-1",
                    CONTAINER_LABEL_TASK_ID: "task-1",
                }
            },
        }

        metadata = adapter._extract_metadata(container)

        assert metadata is not None
        assert metadata.work_item_id is None
        assert metadata.execution_id is None


class TestDockerContainerAssessment:
    """Tests for container assessment logic."""

    @pytest.mark.asyncio
    async def test_assess_container_timeout(self):
        """Should kill container older than timeout."""
        event_store = MagicMock()
        adapter = DockerContainerRecoveryAdapter(
            event_store=event_store, container_timeout_hours=2
        )

        # Create metadata for old container
        from codetoreum.ports.output.container_recovery import ContainerMetadata

        metadata = ContainerMetadata(
            container_id="abc123",
            container_name="old-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            created_at=datetime.now(timezone.utc) - timedelta(hours=3),
            labels={},
        )

        assessment = await adapter.assess_container(metadata)

        assert assessment.action == "kill"
        assert assessment.reason == "container_timeout"

    @pytest.mark.asyncio
    async def test_assess_container_recent_with_execution(self):
        """Should recover recent container with valid execution."""
        event_store = MagicMock()
        adapter = DockerContainerRecoveryAdapter(
            event_store=event_store, container_timeout_hours=2
        )

        # Mock event store to return execution exists
        async def mock_get_events(aggregate_id, limit=1):
            return [{"type": "ExecutionStarted"}]

        event_store.get_events = mock_get_events

        from codetoreum.ports.output.container_recovery import ContainerMetadata

        metadata = ContainerMetadata(
            container_id="abc123",
            container_name="recent-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
            labels={},
            execution_id="exec-456",
            work_item_id="work-123",
        )

        assessment = await adapter.assess_container(metadata)

        assert assessment.action == "reconnect"
        assert assessment.with_monitoring is True
        assert assessment.execution_id == "exec-456"

    @pytest.mark.asyncio
    async def test_assess_container_no_execution(self):
        """Should kill container without valid execution."""
        event_store = MagicMock()
        adapter = DockerContainerRecoveryAdapter(
            event_store=event_store, container_timeout_hours=2
        )

        # Mock event store to return no execution
        async def mock_get_events(aggregate_id, limit=1):
            raise StorageError("Execution not found")

        event_store.get_events = mock_get_events

        from codetoreum.ports.output.container_recovery import ContainerMetadata

        metadata = ContainerMetadata(
            container_id="abc123",
            container_name="orphan-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
            labels={},
            execution_id="exec-unknown",
        )

        assessment = await adapter.assess_container(metadata)

        assert assessment.action == "kill"
        assert assessment.reason == "no_execution_found"


class TestDockerContainerActionExecution:
    """Tests for executing recovery actions."""

    @pytest.mark.asyncio
    async def test_execute_reconnect_action(self):
        """Should return success for reconnect action."""
        event_store = MagicMock()
        adapter = DockerContainerRecoveryAdapter(event_store=event_store)

        from codetoreum.ports.output.container_recovery import RecoveryAssessment

        assessment = RecoveryAssessment(
            container_id="abc123",
            action="reconnect",
            reason="execution_in_progress",
            with_monitoring=True,
            execution_id="exec-456",
        )

        # Mock Docker client
        with patch.object(adapter, "_get_client") as mock_client_method:
            mock_client = MagicMock()
            mock_client_method.return_value = mock_client

            result = await adapter.execute_recovery_action(assessment)

            assert result is True

    @pytest.mark.asyncio
    async def test_execute_kill_action(self):
        """Should kill and remove container on kill action."""
        event_store = MagicMock()
        adapter = DockerContainerRecoveryAdapter(event_store=event_store)

        from codetoreum.ports.output.container_recovery import RecoveryAssessment

        assessment = RecoveryAssessment(
            container_id="abc123",
            action="kill",
            reason="container_timeout",
            with_monitoring=False,
        )

        # Mock Docker container
        with patch.object(adapter, "_get_client") as mock_client_method:
            mock_client = MagicMock()
            mock_container = MagicMock()

            mock_client.containers.get.return_value = mock_container
            mock_client_method.return_value = mock_client

            result = await adapter.execute_recovery_action(assessment)

            assert result is True
            mock_container.kill.assert_called_once()
            mock_container.remove.assert_called_once_with(force=True)

    @pytest.mark.asyncio
    async def test_execute_action_container_not_found(self):
        """Should return False if container not found."""
        event_store = MagicMock()
        adapter = DockerContainerRecoveryAdapter(event_store=event_store)

        from codetoreum.ports.output.container_recovery import RecoveryAssessment

        assessment = RecoveryAssessment(
            container_id="nonexistent",
            action="kill",
            reason="no_execution_found",
            with_monitoring=False,
        )

        # Mock Docker client raising error
        with patch.object(adapter, "_get_client") as mock_client_method:
            mock_client = MagicMock()
            mock_client.containers.get.side_effect = Exception("Container not found")

            mock_client_method.return_value = mock_client

            result = await adapter.execute_recovery_action(assessment)

            assert result is False


class TestProcessOrphanedRepairResults:
    """Tests for processing repair cycle results."""

    @pytest.mark.asyncio
    async def test_process_orphaned_repair_results(self):
        """Should return number of processed repair cycles."""
        event_store = MagicMock()
        adapter = DockerContainerRecoveryAdapter(event_store=event_store)

        count = await adapter.process_orphaned_repair_results()

        assert count == 0  # Stub implementation
