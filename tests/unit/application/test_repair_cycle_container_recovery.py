"""Unit tests for repair cycle container recovery.

These tests verify:
- Repair cycle container discovery via label filtering
- Checkpoint staleness detection (>60 minutes)
- Container age assessment (>2 hours)
- Correct recovery action determination based on checkpoint/age
- Orphaned result processing and storage scanning
- Integration with checkpoint store
"""

from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codetoreum.adapters.secondary.docker_container_recovery_adapter import (
    CHECKPOINT_STALENESS_THRESHOLD,
    REPAIR_CYCLE_AGE_THRESHOLD,
    DockerContainerRecoveryAdapter,
)
from codetoreum.adapters.testing.in_memory_checkpoint_store import (
    InMemoryCheckpointStore,
)
from codetoreum.domain.repair_cycle_types import RepairCycleCheckpoint, CycleResult
from codetoreum.ports.output.container_recovery import (
    ContainerMetadata,
    RecoveryAssessment,
)
from codetoreum.ports.exceptions import StorageError


def create_test_checkpoint(
    pipeline_run_id: str,
    test_type: str = "all",
    iteration: int = 1,
    timestamp_offset: timedelta = timedelta(minutes=0),
) -> RepairCycleCheckpoint:
    """Helper to create a test checkpoint with specified timestamp offset."""
    now = datetime.now(timezone.utc)
    checkpoint_time = now - timestamp_offset
    expires_at = checkpoint_time + timedelta(hours=24)

    return RepairCycleCheckpoint(
        pipeline_run_id=pipeline_run_id,
        test_type=test_type,
        iteration=iteration,
        total_agent_calls=5,
        files_fixed=1,
        warnings_reviewed=2,
        elapsed_seconds=300.0,
        test_results=(),  # Empty tuple of CycleResult
        timestamp=checkpoint_time.isoformat(),
        expires_at=expires_at.isoformat(),
    )


class TestGetRunningRepairCycleContainers:
    """Tests for get_running_repair_cycle_containers method."""

    @pytest.mark.asyncio
    async def test_lists_repair_cycle_containers_only(self):
        """Should only return containers with repair-cycle label."""
        tracking_storage = AsyncMock()
        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=AsyncMock(),
            tracking_storage=tracking_storage,
        )

        # Mock Docker client to return containers
        mock_container_repair = MagicMock()
        mock_container_repair.id = "repair-123"
        mock_container_repair.name = "repair-cycle-container"
        mock_container_repair.short_id = "repair-123"
        mock_container_repair.attrs = {
            "Config": {
                "Labels": {
                    "org.codetoreum.type": "repair-cycle",
                    "org.codetoreum.project": "proj-1",
                    "org.codetoreum.agent": "agent-1",
                    "org.codetoreum.task_id": "task-1",
                    "org.codetoreum.work_item_id": "100",
                    "org.codetoreum.pipeline_run_id": "run-abc",
                    "org.codetoreum.execution_id": "exec-123",
                }
            },
            "Created": "2025-01-27T10:00:00Z",
        }

        mock_client = MagicMock()
        mock_client.containers.list.return_value = [mock_container_repair]

        with patch.object(adapter, "_get_client", return_value=mock_client):
            containers = await adapter.get_running_repair_cycle_containers()

        # Verify Docker API was called with correct filter
        mock_client.containers.list.assert_called_once()
        call_args = mock_client.containers.list.call_args
        assert call_args[1]["filters"]["label"] == [
            "org.codetoreum.type=repair-cycle"
        ]
        assert call_args[1]["all"] is False

        # Verify container was returned
        assert len(containers) == 1
        assert containers[0].container_id == "repair-123"

    @pytest.mark.asyncio
    async def test_filters_out_agent_containers(self):
        """Should only return repair-cycle containers, not agent containers."""
        tracking_storage = AsyncMock()
        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=AsyncMock(),
            tracking_storage=tracking_storage,
        )

        mock_client = MagicMock()
        # API should be called with repair-cycle filter
        mock_client.containers.list.return_value = []

        with patch.object(adapter, "_get_client", return_value=mock_client):
            containers = await adapter.get_running_repair_cycle_containers()

        # Verify the filter specifically asks for repair-cycle type
        mock_client.containers.list.assert_called_once()
        call_args = mock_client.containers.list.call_args
        assert "repair-cycle" in str(call_args[1]["filters"]["label"])


class TestRepairCycleContainerAssessment:
    """Tests for assess_repair_cycle_container method."""

    @pytest.mark.asyncio
    async def test_kills_if_result_completed_during_downtime(self):
        """Should kill container if result found completed in storage."""
        tracking_storage = AsyncMock()
        checkpoint_store = InMemoryCheckpointStore()

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=AsyncMock(),
            tracking_storage=tracking_storage,
            checkpoint_store=checkpoint_store,
        )

        # Storage has completed result
        completed_result = {
            "overall_success": True,
            "iterations": 3,
            "processed": False,
        }
        tracking_storage.get.return_value = completed_result

        metadata = ContainerMetadata(
            container_id="repair-123",
            container_name="repair-cycle-1",
            project_id="proj-1",
            agent_id="repair-agent",
            task_id="task-1",
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
            labels=MappingProxyType({"org.codetoreum.type": "repair-cycle"}),
            work_item_id="100",
            pipeline_run_id="run-abc",
            execution_id="exec-123",
        )

        assessment = await adapter.assess_repair_cycle_container(metadata)

        assert assessment.action == "kill"
        assert assessment.reason == "completed_during_downtime"
        assert assessment.with_monitoring is False

    @pytest.mark.asyncio
    async def test_kills_if_stale_checkpoint_and_old_container(self):
        """Should kill if checkpoint >60min old AND container >2 hours old."""
        tracking_storage = AsyncMock()
        tracking_storage.get.return_value = None  # No completed result
        checkpoint_store = InMemoryCheckpointStore()

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=AsyncMock(),
            tracking_storage=tracking_storage,
            checkpoint_store=checkpoint_store,
        )

        # Save a stale checkpoint (65 min old > 60 min threshold)
        old_checkpoint = create_test_checkpoint(
            "run-abc", timestamp_offset=timedelta(minutes=65)
        )
        await checkpoint_store.save_checkpoint(old_checkpoint)

        metadata = ContainerMetadata(
            container_id="repair-123",
            container_name="repair-cycle-1",
            project_id="proj-1",
            agent_id="repair-agent",
            task_id="task-1",
            created_at=datetime.now(timezone.utc) - timedelta(hours=3),  # 3h old
            labels=MappingProxyType({"org.codetoreum.type": "repair-cycle"}),
            work_item_id="100",
            pipeline_run_id="run-abc",
            execution_id="exec-123",
        )

        assessment = await adapter.assess_repair_cycle_container(metadata)

        assert assessment.action == "kill"
        assert assessment.reason == "checkpoint_stale"
        assert assessment.with_monitoring is False

    @pytest.mark.asyncio
    async def test_kills_if_no_checkpoint_and_old_container(self):
        """Should kill if no checkpoint AND container >2 hours old."""
        tracking_storage = AsyncMock()
        tracking_storage.get.return_value = None  # No completed result
        checkpoint_store = InMemoryCheckpointStore()

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=AsyncMock(),
            tracking_storage=tracking_storage,
            checkpoint_store=checkpoint_store,
        )

        # No checkpoint saved

        metadata = ContainerMetadata(
            container_id="repair-123",
            container_name="repair-cycle-1",
            project_id="proj-1",
            agent_id="repair-agent",
            task_id="task-1",
            created_at=datetime.now(timezone.utc) - timedelta(hours=3),  # 3h old
            labels=MappingProxyType({"org.codetoreum.type": "repair-cycle"}),
            work_item_id="100",
            pipeline_run_id="run-abc",
            execution_id="exec-123",
        )

        assessment = await adapter.assess_repair_cycle_container(metadata)

        assert assessment.action == "kill"
        assert assessment.reason == "no_checkpoint"
        assert assessment.with_monitoring is False

    @pytest.mark.asyncio
    async def test_reconnects_if_fresh_checkpoint_despite_old_container(self):
        """Should reconnect with monitoring if checkpoint is fresh even if container is old."""
        tracking_storage = AsyncMock()
        tracking_storage.get.return_value = None  # No completed result
        checkpoint_store = InMemoryCheckpointStore()

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=AsyncMock(),
            tracking_storage=tracking_storage,
            checkpoint_store=checkpoint_store,
        )

        # Save a fresh checkpoint (30 min old < 60 min threshold) despite old container
        fresh_checkpoint = create_test_checkpoint(
            "run-abc", iteration=5, timestamp_offset=timedelta(minutes=30)
        )
        await checkpoint_store.save_checkpoint(fresh_checkpoint)

        metadata = ContainerMetadata(
            container_id="repair-123",
            container_name="repair-cycle-1",
            project_id="proj-1",
            agent_id="repair-agent",
            task_id="task-1",
            created_at=datetime.now(timezone.utc) - timedelta(hours=3),  # 3h old
            labels=MappingProxyType({"org.codetoreum.type": "repair-cycle"}),
            work_item_id="100",
            pipeline_run_id="run-abc",
            execution_id="exec-123",
        )

        assessment = await adapter.assess_repair_cycle_container(metadata)

        assert assessment.action == "reconnect"
        assert assessment.reason == "valid_repair_cycle"
        assert assessment.with_monitoring is True

    @pytest.mark.asyncio
    async def test_reconnects_if_container_recent(self):
        """Should reconnect if container is recent (<2 hours)."""
        tracking_storage = AsyncMock()
        tracking_storage.get.return_value = None  # No completed result
        checkpoint_store = InMemoryCheckpointStore()

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=AsyncMock(),
            tracking_storage=tracking_storage,
            checkpoint_store=checkpoint_store,
        )

        # No checkpoint, but container is recent

        metadata = ContainerMetadata(
            container_id="repair-123",
            container_name="repair-cycle-1",
            project_id="proj-1",
            agent_id="repair-agent",
            task_id="task-1",
            created_at=datetime.now(timezone.utc) - timedelta(minutes=30),  # 30 min
            labels=MappingProxyType({"org.codetoreum.type": "repair-cycle"}),
            work_item_id="100",
            pipeline_run_id="run-abc",
            execution_id="exec-123",
        )

        assessment = await adapter.assess_repair_cycle_container(metadata)

        assert assessment.action == "reconnect"
        assert assessment.reason == "valid_repair_cycle"
        assert assessment.with_monitoring is True

    @pytest.mark.asyncio
    async def test_handles_storage_error_gracefully(self):
        """Should handle storage errors when checking for completed results."""
        tracking_storage = AsyncMock()
        tracking_storage.get.side_effect = StorageError("Storage unavailable")
        checkpoint_store = InMemoryCheckpointStore()

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=AsyncMock(),
            tracking_storage=tracking_storage,
            checkpoint_store=checkpoint_store,
        )

        metadata = ContainerMetadata(
            container_id="repair-123",
            container_name="repair-cycle-1",
            project_id="proj-1",
            agent_id="repair-agent",
            task_id="task-1",
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
            labels=MappingProxyType({"org.codetoreum.type": "repair-cycle"}),
            work_item_id="100",
            pipeline_run_id="run-abc",
            execution_id="exec-123",
        )

        # Should not raise, should continue with other checks
        assessment = await adapter.assess_repair_cycle_container(metadata)

        # Should make a decision despite storage error
        assert assessment is not None
        assert assessment.container_id == "repair-123"


class TestCheckpointStalenessThresholds:
    """Tests for checkpoint staleness and container age thresholds."""

    def test_checkpoint_staleness_threshold_is_60_minutes(self):
        """CHECKPOINT_STALENESS_THRESHOLD should be 60 minutes."""
        assert CHECKPOINT_STALENESS_THRESHOLD == timedelta(minutes=60)

    def test_repair_cycle_age_threshold_is_2_hours(self):
        """REPAIR_CYCLE_AGE_THRESHOLD should be 2 hours."""
        assert REPAIR_CYCLE_AGE_THRESHOLD == timedelta(hours=2)


class TestOrphanedRepairResultsProcessing:
    """Tests for process_orphaned_repair_results method."""

    @pytest.mark.asyncio
    async def test_scans_storage_for_repair_results(self):
        """Should scan storage using repair_cycle:result:* pattern."""
        tracking_storage = AsyncMock()
        tracking_storage.scan.return_value = []

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=AsyncMock(),
            tracking_storage=tracking_storage,
        )

        processed = await adapter.process_orphaned_repair_results()

        tracking_storage.scan.assert_called_once_with("repair_cycle:result:*")
        assert processed == 0

    @pytest.mark.asyncio
    async def test_processes_unprocessed_completed_results(self):
        """Should process completed results marked as unprocessed."""
        tracking_storage = AsyncMock()

        # Simulated storage keys and values
        result_key = "repair_cycle:result:proj-1:100:run-abc"
        completed_result = {
            "overall_success": True,
            "iterations": 3,
            "processed": False,  # Not yet marked as processed
        }

        tracking_storage.scan.return_value = [result_key]
        tracking_storage.get.return_value = completed_result

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=AsyncMock(),
            tracking_storage=tracking_storage,
        )

        processed = await adapter.process_orphaned_repair_results()

        # Should mark as processed and store back
        tracking_storage.set.assert_called_once()
        set_call_args = tracking_storage.set.call_args
        assert set_call_args[0][0] == result_key
        assert set_call_args[0][1]["processed"] is True
        assert set_call_args[1]["ttl"] == 86400  # 24 hour TTL

        assert processed == 1

    @pytest.mark.asyncio
    async def test_skips_already_processed_results(self):
        """Should skip results already marked as processed."""
        tracking_storage = AsyncMock()

        result_key = "repair_cycle:result:proj-1:100:run-abc"
        processed_result = {
            "overall_success": True,
            "iterations": 3,
            "processed": True,  # Already processed
        }

        tracking_storage.scan.return_value = [result_key]
        tracking_storage.get.return_value = processed_result

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=AsyncMock(),
            tracking_storage=tracking_storage,
        )

        processed = await adapter.process_orphaned_repair_results()

        # Should not call set since already processed
        tracking_storage.set.assert_not_called()
        assert processed == 0

    @pytest.mark.asyncio
    async def test_skips_incomplete_results(self):
        """Should skip results that don't have overall_success set."""
        tracking_storage = AsyncMock()

        result_key = "repair_cycle:result:proj-1:100:run-abc"
        incomplete_result = {
            "iterations": 2,
            # overall_success is None or missing
            "processed": False,
        }

        tracking_storage.scan.return_value = [result_key]
        tracking_storage.get.return_value = incomplete_result

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=AsyncMock(),
            tracking_storage=tracking_storage,
        )

        processed = await adapter.process_orphaned_repair_results()

        tracking_storage.set.assert_not_called()
        assert processed == 0

    @pytest.mark.asyncio
    async def test_handles_invalid_key_format(self):
        """Should handle malformed storage keys gracefully."""
        tracking_storage = AsyncMock()

        # Invalid key format (not enough parts)
        invalid_key = "repair_cycle:result:proj-1"
        tracking_storage.scan.return_value = [invalid_key]
        tracking_storage.get.return_value = {"overall_success": True}

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=AsyncMock(),
            tracking_storage=tracking_storage,
        )

        processed = await adapter.process_orphaned_repair_results()

        # Should not crash, should skip malformed key
        assert processed == 0

    @pytest.mark.asyncio
    async def test_handles_storage_errors(self):
        """Should handle storage errors during processing."""
        tracking_storage = AsyncMock()
        tracking_storage.scan.side_effect = StorageError("Scan failed")

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=AsyncMock(),
            tracking_storage=tracking_storage,
        )

        # Should re-raise StorageError (as per spec)
        with pytest.raises(StorageError):
            await adapter.process_orphaned_repair_results()

    @pytest.mark.asyncio
    async def test_continues_on_per_result_errors(self):
        """Should continue processing remaining results if one fails."""
        tracking_storage = AsyncMock()

        result_key_1 = "repair_cycle:result:proj-1:100:run-abc"
        result_key_2 = "repair_cycle:result:proj-1:101:run-def"

        tracking_storage.scan.return_value = [result_key_1, result_key_2]

        # First result succeeds, second fails
        good_result = {"overall_success": True, "processed": False}
        tracking_storage.get.side_effect = [good_result, Exception("Get failed")]

        adapter = DockerContainerRecoveryAdapter(
            execution_tracker=AsyncMock(),
            tracking_storage=tracking_storage,
        )

        processed = await adapter.process_orphaned_repair_results()

        # Should have processed the first one despite error on second
        assert processed == 1
        assert tracking_storage.set.call_count == 1
