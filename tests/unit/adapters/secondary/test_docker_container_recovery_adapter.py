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
        """Adapter should initialize with required dependencies."""
        execution_tracker = MagicMock()
        tracking_storage = MagicMock()

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=execution_tracker, tracking_storage=tracking_storage
        )

        assert adapter.execution_tracker is execution_tracker
        assert adapter.tracking_storage is tracking_storage
        assert adapter.container_timeout_hours == 2

    def test_adapter_custom_timeout(self):
        """Adapter should accept custom timeout."""
        execution_tracker = MagicMock()
        tracking_storage = MagicMock()

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=execution_tracker,
            tracking_storage=tracking_storage,
            container_timeout_hours=4,
        )

        assert adapter.container_timeout_hours == 4


class TestDockerContainerMetadataExtraction:
    """Tests for extracting metadata from Docker labels."""

    def test_extract_metadata_valid_container(self):
        """Should extract metadata from container with all labels."""
        execution_tracker = MagicMock()
        tracking_storage = MagicMock()

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=execution_tracker, tracking_storage=tracking_storage
        )

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

    def test_extract_metadata_missing_labels(self):
        """Should return None when required labels are missing."""
        execution_tracker = MagicMock()
        tracking_storage = MagicMock()

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=execution_tracker, tracking_storage=tracking_storage
        )

        # Mock Docker container without required labels
        container = MagicMock()
        container.short_id = "abc123"
        container.attrs = {
            "Created": "2026-01-27T12:00:00Z",
            "Config": {"Labels": {CONTAINER_LABEL_PROJECT: "proj-1"}},
        }

        metadata = adapter._extract_metadata(container)

        assert metadata is None


class TestDockerContainerAssessment:
    """Tests for container assessment logic."""

    @pytest.mark.asyncio
    async def test_assess_container_timeout(self):
        """Container older than 2 hours should be killed."""
        execution_tracker = MagicMock()
        tracking_storage = MagicMock()

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=execution_tracker,
            tracking_storage=tracking_storage,
            container_timeout_hours=2,
        )

        # Create metadata for a 3-hour-old container
        created_at = datetime.now(timezone.utc) - timedelta(hours=3)
        from codetoreum.ports.output.container_recovery import ContainerMetadata

        metadata = ContainerMetadata(
            container_id="container-1",
            container_name="old-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            created_at=created_at,
            labels={CONTAINER_LABEL_TYPE: CONTAINER_TYPE_AGENT},
        )

        assessment = await adapter.assess_container(metadata)

        assert assessment.action == "kill"
        assert assessment.reason == "container_timeout"

    @pytest.mark.asyncio
    async def test_assess_container_no_work_item_id(self):
        """Container without work_item_id should reconnect without monitoring."""
        execution_tracker = MagicMock()
        tracking_storage = MagicMock()

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=execution_tracker, tracking_storage=tracking_storage
        )

        created_at = datetime.now(timezone.utc) - timedelta(hours=1)
        from codetoreum.ports.output.container_recovery import ContainerMetadata

        metadata = ContainerMetadata(
            container_id="container-1",
            container_name="test-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            created_at=created_at,
            labels={CONTAINER_LABEL_TYPE: CONTAINER_TYPE_AGENT},
            work_item_id=None,  # No work item
        )

        assessment = await adapter.assess_container(metadata)

        assert assessment.action == "reconnect"
        assert assessment.reason == "valid_but_limited"
        assert assessment.with_monitoring is False

    @pytest.mark.asyncio
    async def test_assess_container_execution_not_in_progress(self):
        """Container with non-in_progress execution should be killed."""
        execution_tracker = AsyncMock()
        tracking_storage = MagicMock()

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=execution_tracker, tracking_storage=tracking_storage
        )

        created_at = datetime.now(timezone.utc) - timedelta(hours=1)
        from codetoreum.ports.output.container_recovery import ContainerMetadata

        metadata = ContainerMetadata(
            container_id="container-1",
            container_name="test-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            created_at=created_at,
            labels={CONTAINER_LABEL_TYPE: CONTAINER_TYPE_AGENT},
            work_item_id="work-123",
            execution_id="exec-456",
        )

        # Mock execution state with completed outcome
        execution_tracker.load_state.return_value = {
            "outcome": "completed",
            "agent": "agent-1",
        }

        assessment = await adapter.assess_container(metadata)

        assert assessment.action == "kill"
        assert assessment.reason == "execution_not_in_progress"

    @pytest.mark.asyncio
    async def test_assess_container_agent_mismatch(self):
        """Container with mismatched agent should be killed."""
        execution_tracker = AsyncMock()
        tracking_storage = MagicMock()

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=execution_tracker, tracking_storage=tracking_storage
        )

        created_at = datetime.now(timezone.utc) - timedelta(hours=1)
        from codetoreum.ports.output.container_recovery import ContainerMetadata

        metadata = ContainerMetadata(
            container_id="container-1",
            container_name="test-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            created_at=created_at,
            labels={CONTAINER_LABEL_TYPE: CONTAINER_TYPE_AGENT},
            work_item_id="work-123",
            execution_id="exec-456",
        )

        # Mock execution state with different agent
        execution_tracker.load_state.return_value = {
            "outcome": "in_progress",
            "agent": "agent-2",
        }

        assessment = await adapter.assess_container(metadata)

        assert assessment.action == "kill"
        assert assessment.reason == "agent_mismatch"

    @pytest.mark.asyncio
    async def test_assess_container_valid_execution(self):
        """Container with valid execution should be reconnected with monitoring."""
        execution_tracker = AsyncMock()
        tracking_storage = MagicMock()

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=execution_tracker, tracking_storage=tracking_storage
        )

        created_at = datetime.now(timezone.utc) - timedelta(hours=1)
        from codetoreum.ports.output.container_recovery import ContainerMetadata

        metadata = ContainerMetadata(
            container_id="container-1",
            container_name="test-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            created_at=created_at,
            labels={CONTAINER_LABEL_TYPE: CONTAINER_TYPE_AGENT},
            work_item_id="work-123",
            execution_id="exec-456",
        )

        # Mock execution state with valid state
        execution_tracker.load_state.return_value = {
            "outcome": "in_progress",
            "agent": "agent-1",
        }

        assessment = await adapter.assess_container(metadata)

        assert assessment.action == "reconnect"
        assert assessment.reason == "valid_execution"
        assert assessment.with_monitoring is True
        assert assessment.execution_id == "exec-456"
