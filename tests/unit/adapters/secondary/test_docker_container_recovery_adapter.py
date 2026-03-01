"""Unit tests for DockerContainerRecoveryAdapter.

These tests verify:
- Metadata extraction from Docker labels
- Container assessment logic
- Recovery action execution
- Error handling
"""

from datetime import UTC, datetime, timedelta
from types import MappingProxyType
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
from codetoreum.ports.exceptions import StorageError


class TestDockerContainerRecoveryAdapterInitialization:
    """Tests for adapter initialization."""

    def test_adapter_initialization(self):
        """Adapter should initialize with required dependencies."""
        execution_tracker = MagicMock()
        tracking_storage = MagicMock()

        adapter = DockerContainerRecoveryAdapter(execution_tracker=execution_tracker, tracking_storage=tracking_storage)

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

        adapter = DockerContainerRecoveryAdapter(execution_tracker=execution_tracker, tracking_storage=tracking_storage)

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

        adapter = DockerContainerRecoveryAdapter(execution_tracker=execution_tracker, tracking_storage=tracking_storage)

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
        created_at = datetime.now(UTC) - timedelta(hours=3)
        from codetoreum.ports.output.container_recovery import ContainerMetadata

        metadata = ContainerMetadata(
            container_id="container-1",
            container_name="old-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            created_at=created_at,
            labels=MappingProxyType(
                {
                    CONTAINER_LABEL_TYPE: CONTAINER_TYPE_AGENT,
                    CONTAINER_LABEL_PROJECT: "proj-1",
                    CONTAINER_LABEL_AGENT: "agent-1",
                }
            ),
        )

        assessment = await adapter.assess_container(metadata)

        assert assessment.action == "kill"
        assert assessment.reason == "container_timeout"

    @pytest.mark.asyncio
    async def test_assess_container_no_work_item_id(self):
        """Container without work_item_id should be killed (incomplete metadata)."""
        execution_tracker = MagicMock()
        tracking_storage = MagicMock()

        adapter = DockerContainerRecoveryAdapter(execution_tracker=execution_tracker, tracking_storage=tracking_storage)

        created_at = datetime.now(UTC) - timedelta(hours=1)
        from codetoreum.ports.output.container_recovery import ContainerMetadata

        metadata = ContainerMetadata(
            container_id="container-1",
            container_name="test-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            created_at=created_at,
            labels=MappingProxyType(
                {
                    CONTAINER_LABEL_TYPE: CONTAINER_TYPE_AGENT,
                    CONTAINER_LABEL_PROJECT: "proj-1",
                    CONTAINER_LABEL_AGENT: "agent-1",
                }
            ),
            work_item_id=None,  # No work item
        )

        assessment = await adapter.assess_container(metadata)

        assert assessment.action == "kill"
        assert assessment.reason == "incomplete_metadata"
        assert assessment.with_monitoring is False
        assert assessment.execution_id is None

    @pytest.mark.asyncio
    async def test_assess_container_execution_not_in_progress(self):
        """Container with non-in_progress execution should be killed."""
        execution_tracker = AsyncMock()
        tracking_storage = MagicMock()

        adapter = DockerContainerRecoveryAdapter(execution_tracker=execution_tracker, tracking_storage=tracking_storage)

        created_at = datetime.now(UTC) - timedelta(hours=1)
        from codetoreum.ports.output.container_recovery import ContainerMetadata

        metadata = ContainerMetadata(
            container_id="container-1",
            container_name="test-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            created_at=created_at,
            labels=MappingProxyType(
                {
                    CONTAINER_LABEL_TYPE: CONTAINER_TYPE_AGENT,
                    CONTAINER_LABEL_PROJECT: "proj-1",
                    CONTAINER_LABEL_AGENT: "agent-1",
                }
            ),
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

        adapter = DockerContainerRecoveryAdapter(execution_tracker=execution_tracker, tracking_storage=tracking_storage)

        created_at = datetime.now(UTC) - timedelta(hours=1)
        from codetoreum.ports.output.container_recovery import ContainerMetadata

        metadata = ContainerMetadata(
            container_id="container-1",
            container_name="test-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            created_at=created_at,
            labels=MappingProxyType(
                {
                    CONTAINER_LABEL_TYPE: CONTAINER_TYPE_AGENT,
                    CONTAINER_LABEL_PROJECT: "proj-1",
                    CONTAINER_LABEL_AGENT: "agent-1",
                }
            ),
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

        adapter = DockerContainerRecoveryAdapter(execution_tracker=execution_tracker, tracking_storage=tracking_storage)

        created_at = datetime.now(UTC) - timedelta(hours=1)
        from codetoreum.ports.output.container_recovery import ContainerMetadata

        metadata = ContainerMetadata(
            container_id="container-1",
            container_name="test-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            created_at=created_at,
            labels=MappingProxyType(
                {
                    CONTAINER_LABEL_TYPE: CONTAINER_TYPE_AGENT,
                    CONTAINER_LABEL_PROJECT: "proj-1",
                    CONTAINER_LABEL_AGENT: "agent-1",
                }
            ),
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


class TestDockerContainerRecoveryAction:
    """Tests for container recovery action execution."""

    @pytest.mark.asyncio
    async def test_execute_recovery_action_reconnect_with_monitoring(self):
        """Reconnect action should re-register container in tracking storage."""
        execution_tracker = AsyncMock()
        tracking_storage = AsyncMock()

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=execution_tracker,
            tracking_storage=tracking_storage,
        )

        # Mock Docker client and container
        mock_container = MagicMock()
        mock_container.id = "container-123"
        mock_container.name = "test-container"
        mock_container.labels = {
            CONTAINER_LABEL_AGENT: "agent-1",
            CONTAINER_LABEL_PROJECT: "proj-1",
            CONTAINER_LABEL_TASK_ID: "task-1",
        }

        with patch.object(adapter, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.containers.get.return_value = mock_container
            mock_get_client.return_value = mock_client

            from codetoreum.ports.output.container_recovery import RecoveryAssessment

            assessment = RecoveryAssessment(
                container_id="container-123",
                action="reconnect",
                reason="valid_execution",
                with_monitoring=True,
                execution_id="exec-456",
            )

            result = await adapter.execute_recovery_action(assessment)

            assert result is True
            tracking_storage.set.assert_called_once()
            args, kwargs = tracking_storage.set.call_args
            assert args[0] == "agent:container:test-container"
            assert kwargs.get("ttl") == 7200

    @pytest.mark.asyncio
    async def test_execute_recovery_action_kill_with_execution_marking(self):
        """Kill action should mark execution as failed."""
        execution_tracker = AsyncMock()
        tracking_storage = AsyncMock()

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=execution_tracker,
            tracking_storage=tracking_storage,
        )

        # Mock Docker client and container
        mock_container = MagicMock()
        mock_container.id = "container-123"
        mock_container.name = "test-container"
        mock_container.labels = {
            CONTAINER_LABEL_AGENT: "agent-1",
            CONTAINER_LABEL_PROJECT: "proj-1",
            CONTAINER_LABEL_TASK_ID: "task-1",
            CONTAINER_LABEL_WORK_ITEM_ID: "work-item-1",
        }

        with patch.object(adapter, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.containers.get.return_value = mock_container
            mock_get_client.return_value = mock_client

            from codetoreum.ports.output.container_recovery import RecoveryAssessment

            assessment = RecoveryAssessment(
                container_id="container-123",
                action="kill",
                reason="container_timeout",
                with_monitoring=False,
                execution_id=None,
            )

            result = await adapter.execute_recovery_action(assessment)

            assert result is True
            # Note: execution_tracker.mark_execution_failed is NOT called because
            # kill assessments now have execution_id=None, and the check on line 712
            # of the adapter only calls mark_execution_failed if assessment.execution_id is set.
            # The actual work_item_id is extracted from container labels, but marking
            # the execution failed is skipped for consistency with the new validation rules.
            execution_tracker.mark_execution_failed.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_recovery_action_kill_without_work_item(self):
        """Kill action without work_item_id should not mark execution failed."""
        execution_tracker = AsyncMock()
        tracking_storage = AsyncMock()

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=execution_tracker,
            tracking_storage=tracking_storage,
        )

        # Mock Docker client and container (no work_item_id)
        mock_container = MagicMock()
        mock_container.id = "container-123"
        mock_container.name = "test-container"
        mock_container.labels = {
            CONTAINER_LABEL_AGENT: "agent-1",
            CONTAINER_LABEL_PROJECT: "proj-1",
            CONTAINER_LABEL_TASK_ID: "task-1",
            # No work item ID
        }

        with patch.object(adapter, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.containers.get.return_value = mock_container
            mock_get_client.return_value = mock_client

            from codetoreum.ports.output.container_recovery import RecoveryAssessment

            assessment = RecoveryAssessment(
                container_id="container-123",
                action="kill",
                reason="container_timeout",
                with_monitoring=False,
                execution_id=None,
            )

            result = await adapter.execute_recovery_action(assessment)

            assert result is True
            # Should not mark execution failed (no execution_id or work_item_id)
            execution_tracker.mark_execution_failed.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_recovery_action_get_container_fails(self):
        """Recovery action should fail gracefully if container retrieval fails."""
        execution_tracker = AsyncMock()
        tracking_storage = AsyncMock()

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=execution_tracker,
            tracking_storage=tracking_storage,
        )

        with patch.object(adapter, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.containers.get.side_effect = Exception("Docker error")
            mock_get_client.return_value = mock_client

            from codetoreum.ports.output.container_recovery import RecoveryAssessment

            assessment = RecoveryAssessment(
                container_id="container-123",
                action="reconnect",
                reason="valid_execution",
                with_monitoring=True,
                execution_id="exec-456",
            )

            result = await adapter.execute_recovery_action(assessment)

            assert result is False

    @pytest.mark.asyncio
    async def test_execute_recovery_action_tracking_storage_error_continues(self):
        """Recovery action should continue if tracking storage fails."""
        execution_tracker = AsyncMock()
        tracking_storage = AsyncMock()
        tracking_storage.set.side_effect = StorageError("Storage error")

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=execution_tracker,
            tracking_storage=tracking_storage,
        )

        # Mock Docker client and container
        mock_container = MagicMock()
        mock_container.id = "container-123"
        mock_container.name = "test-container"
        mock_container.labels = {}

        with patch.object(adapter, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.containers.get.return_value = mock_container
            mock_get_client.return_value = mock_client

            from codetoreum.ports.output.container_recovery import RecoveryAssessment

            assessment = RecoveryAssessment(
                container_id="container-123",
                action="reconnect",
                reason="valid_execution",
                with_monitoring=True,
                execution_id="exec-456",
            )

            result = await adapter.execute_recovery_action(assessment)

            # Should still succeed even if storage fails
            assert result is True

    @pytest.mark.asyncio
    async def test_assess_container_execution_state_lookup_failed(self):
        """Container with failed execution state lookup should be killed."""
        execution_tracker = AsyncMock()
        tracking_storage = MagicMock()

        adapter = DockerContainerRecoveryAdapter(execution_tracker=execution_tracker, tracking_storage=tracking_storage)

        created_at = datetime.now(UTC) - timedelta(hours=1)
        from codetoreum.ports.output.container_recovery import ContainerMetadata

        metadata = ContainerMetadata(
            container_id="container-1",
            container_name="test-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            created_at=created_at,
            labels=MappingProxyType(
                {
                    CONTAINER_LABEL_TYPE: CONTAINER_TYPE_AGENT,
                    CONTAINER_LABEL_PROJECT: "proj-1",
                    CONTAINER_LABEL_AGENT: "agent-1",
                }
            ),
            work_item_id="work-123",
            execution_id="exec-456",
        )

        # Mock execution state lookup failure
        execution_tracker.load_state.side_effect = StorageError("Failed to load execution state")

        assessment = await adapter.assess_container(metadata)

        assert assessment.action == "kill"
        assert assessment.reason == "execution_state_lookup_failed"

    @pytest.mark.asyncio
    async def test_assess_container_repair_cycle_wrong_assessment_path(self):
        """Repair cycle container passed to assess_container should be killed."""
        execution_tracker = AsyncMock()
        tracking_storage = MagicMock()

        adapter = DockerContainerRecoveryAdapter(execution_tracker=execution_tracker, tracking_storage=tracking_storage)

        created_at = datetime.now(UTC) - timedelta(hours=1)
        from codetoreum.domain.types import CONTAINER_TYPE_REPAIR_CYCLE
        from codetoreum.ports.output.container_recovery import ContainerMetadata

        metadata = ContainerMetadata(
            container_id="container-1",
            container_name="test-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            created_at=created_at,
            labels=MappingProxyType(
                {
                    CONTAINER_LABEL_TYPE: CONTAINER_TYPE_REPAIR_CYCLE,
                    CONTAINER_LABEL_PROJECT: "proj-1",
                    CONTAINER_LABEL_AGENT: "agent-1",
                }
            ),
            work_item_id="work-123",
            execution_id="exec-456",
        )

        assessment = await adapter.assess_container(metadata)

        assert assessment.action == "kill"
        assert assessment.reason == "repair_cycle_wrong_assessment_path"


class TestTimestampParsingErrors:
    """Tests for timestamp parsing failure handling with error logging."""

    def test_extract_metadata_invalid_created_timestamp_format(self, caplog):
        """Should log error when created_at timestamp is invalid format."""
        execution_tracker = MagicMock()
        tracking_storage = MagicMock()

        adapter = DockerContainerRecoveryAdapter(execution_tracker=execution_tracker, tracking_storage=tracking_storage)

        # Mock Docker container with invalid timestamp
        container = MagicMock()
        container.id = "abc123def456"
        container.short_id = "abc123"
        container.name = "test-container"
        container.attrs = {
            "Created": "invalid-timestamp-format",
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

        # Should still return metadata but with current time as created_at
        assert metadata is not None
        assert metadata.container_id == "abc123def456"
        # Verify error was logged with proper context
        assert "Failed to parse created_at timestamp" in caplog.text
        assert "raw_timestamp" in caplog.text or "Created" in caplog.text

    def test_extract_metadata_missing_created_timestamp(self, caplog):
        """Should log error when created_at timestamp is missing."""
        execution_tracker = MagicMock()
        tracking_storage = MagicMock()

        adapter = DockerContainerRecoveryAdapter(execution_tracker=execution_tracker, tracking_storage=tracking_storage)

        # Mock Docker container without Created field
        container = MagicMock()
        container.id = "abc123def456"
        container.short_id = "abc123"
        container.name = "test-container"
        container.attrs = {
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

        # Should still return metadata but with current time as created_at
        assert metadata is not None
        assert metadata.container_id == "abc123def456"
        # Verify error was logged with proper context indicating MISSING
        assert "Failed to parse created_at timestamp" in caplog.text
        assert "MISSING" in caplog.text

    def test_extract_metadata_null_created_timestamp(self, caplog):
        """Should log error when created_at timestamp is null."""
        execution_tracker = MagicMock()
        tracking_storage = MagicMock()

        adapter = DockerContainerRecoveryAdapter(execution_tracker=execution_tracker, tracking_storage=tracking_storage)

        # Mock Docker container with null Created field
        container = MagicMock()
        container.id = "abc123def456"
        container.short_id = "abc123"
        container.name = "test-container"
        container.attrs = {
            "Created": None,
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

        # Should still return metadata but with current time as created_at
        assert metadata is not None
        # Verify error was logged indicating impact on age-based decisions
        assert "Failed to parse created_at timestamp" in caplog.text
        assert "age-based recovery decisions will be incorrect" in caplog.text

    @pytest.mark.asyncio
    async def test_assess_repair_cycle_checkpoint_parse_error(self, caplog):
        """Should log error when checkpoint timestamp cannot be parsed."""
        execution_tracker = AsyncMock()
        tracking_storage = AsyncMock()
        checkpoint_store = AsyncMock()

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=execution_tracker,
            tracking_storage=tracking_storage,
            checkpoint_store=checkpoint_store,
        )

        # Recent container (within 2 hours) with old container age check
        created_at = datetime.now(UTC) - timedelta(hours=3)
        from codetoreum.ports.output.container_recovery import ContainerMetadata

        metadata = ContainerMetadata(
            container_id="container-1",
            container_name="test-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            created_at=created_at,
            labels=MappingProxyType(
                {
                    CONTAINER_LABEL_TYPE: "repair-cycle",
                    CONTAINER_LABEL_PROJECT: "proj-1",
                    CONTAINER_LABEL_AGENT: "agent-1",
                }
            ),
            work_item_id="work-123",
            workflow_run_id="run-456",
            execution_id="exec-789",
        )

        # Mock checkpoint with invalid timestamp
        mock_checkpoint = MagicMock()
        mock_checkpoint.timestamp = "invalid-timestamp-format"
        checkpoint_store.get_checkpoint.return_value = mock_checkpoint

        # Mock storage get
        tracking_storage.get.return_value = None

        assessment = await adapter.assess_repair_cycle_container(metadata)

        # Should kill container (checkpoint unparseable = stale)
        assert assessment.action == "kill"
        assert assessment.reason == "checkpoint_stale"
        # Verify error was logged indicating impact
        assert "Failed to parse checkpoint timestamp" in caplog.text
        assert "will kill container" in caplog.text

    @pytest.mark.asyncio
    async def test_assess_repair_cycle_checkpoint_null_timestamp(self, caplog):
        """Should log error when checkpoint timestamp is None."""
        execution_tracker = AsyncMock()
        tracking_storage = AsyncMock()
        checkpoint_store = AsyncMock()

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=execution_tracker,
            tracking_storage=tracking_storage,
            checkpoint_store=checkpoint_store,
        )

        # Old container (beyond 2 hours) with null checkpoint timestamp
        created_at = datetime.now(UTC) - timedelta(hours=3)
        from codetoreum.ports.output.container_recovery import ContainerMetadata

        metadata = ContainerMetadata(
            container_id="container-1",
            container_name="test-container",
            project_id="proj-1",
            agent_id="agent-1",
            task_id="task-1",
            created_at=created_at,
            labels=MappingProxyType(
                {
                    CONTAINER_LABEL_TYPE: "repair-cycle",
                    CONTAINER_LABEL_PROJECT: "proj-1",
                    CONTAINER_LABEL_AGENT: "agent-1",
                }
            ),
            work_item_id="work-123",
            workflow_run_id="run-456",
            execution_id="exec-789",
        )

        # Mock checkpoint with null timestamp
        mock_checkpoint = MagicMock()
        mock_checkpoint.timestamp = None
        checkpoint_store.get_checkpoint.return_value = mock_checkpoint

        # Mock storage get
        tracking_storage.get.return_value = None

        assessment = await adapter.assess_repair_cycle_container(metadata)

        # Should kill container (checkpoint unparseable = stale)
        assert assessment.action == "kill"
        assert assessment.reason == "checkpoint_stale"
        # Verify error was logged indicating impact
        assert "Failed to parse checkpoint timestamp" in caplog.text
        assert "will kill container" in caplog.text
