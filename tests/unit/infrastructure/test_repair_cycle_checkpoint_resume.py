"""Unit tests for repair cycle checkpoint and resume functionality.

Tests checkpoint save/retrieve, resume from checkpoint, and circuit breaker
integration with checkpointing.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from codetoreum.adapters.testing.in_memory_checkpoint_store import (
    InMemoryCheckpointStore,
)
from codetoreum.adapters.testing.mock_repair_cycle_adapter import MockRepairCycleAdapter
from codetoreum.domain.repair_cycle_types import (
    RepairCycleCheckpoint,
    RepairTestRunConfig,
    RepairTestType,
)
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock


@dataclass
class _RepairCycleContextImpl:
    """Concrete implementation of RepairCycleContext Protocol for testing."""
    stage_name: str
    workflow_run_id: str
    test_configs: tuple[RepairTestRunConfig, ...]
    agent_name: str
    max_total_agent_calls: int
    checkpoint_interval: int


def _create_repair_cycle_context(**kwargs: Any) -> _RepairCycleContextImpl:
    """Factory function to create RepairCycleContext instances for testing."""
    defaults: dict[str, Any] = {
        "stage_name": "code_review",
        "workflow_run_id": "run-123",
        "test_configs": (),
        "agent_name": "reviewer",
        "max_total_agent_calls": 10,
        "checkpoint_interval": 1,
    }
    defaults.update(kwargs)
    return _RepairCycleContextImpl(**defaults)


@pytest.mark.asyncio
class TestCheckpointStorage:
    """Tests for checkpoint persistence and retrieval."""

    @pytest.fixture
    def store(self):
        """Create checkpoint store."""
        return InMemoryCheckpointStore()

    @pytest.fixture
    def checkpoint(self):
        """Create a valid checkpoint."""
        now = datetime.now(UTC)
        return RepairCycleCheckpoint(
            workflow_run_id="run-123",
            test_type=RepairTestType.UNIT,
            iteration=2,
            total_agent_calls=5,
            files_fixed=2,
            warnings_reviewed=0,
            elapsed_seconds=60.0,
            test_results=(),
            timestamp=now.isoformat(),
            expires_at=now.isoformat(),
        )

    async def test_save_checkpoint(self, store, checkpoint):
        """Test saving checkpoint."""
        await store.save_checkpoint(checkpoint)
        assert await store.checkpoint_exists("run-123", "UNIT")

    async def test_retrieve_checkpoint(self, store, checkpoint):
        """Test retrieving saved checkpoint."""
        await store.save_checkpoint(checkpoint)
        retrieved = await store.get_checkpoint("run-123", "UNIT")
        assert retrieved is not None
        assert retrieved.workflow_run_id == "run-123"
        assert retrieved.test_type == RepairTestType.UNIT
        assert retrieved.iteration == 2
        assert retrieved.total_agent_calls == 5

    async def test_checkpoint_not_found(self, store):
        """Test retrieving non-existent checkpoint."""
        result = await store.get_checkpoint("run-999", "UNIT")
        assert result is None

    async def test_checkpoint_exists_false_for_missing(self, store):
        """Test checkpoint_exists returns False for missing checkpoint."""
        exists = await store.checkpoint_exists("run-999", "UNIT")
        assert exists is False

    async def test_delete_checkpoint_specific(self, store, checkpoint):
        """Test deleting specific checkpoint."""
        await store.save_checkpoint(checkpoint)
        assert await store.checkpoint_exists("run-123", "UNIT")
        await store.delete_checkpoint("run-123", "UNIT")
        assert not await store.checkpoint_exists("run-123", "UNIT")

    async def test_delete_checkpoint_all_for_pipeline(self, store):
        """Test deleting all checkpoints for pipeline run."""
        now = datetime.now(UTC)

        # Create checkpoints for multiple test types
        for test_type in [RepairTestType.UNIT, RepairTestType.INTEGRATION, RepairTestType.E2E]:
            checkpoint = RepairCycleCheckpoint(
                workflow_run_id="run-123",
                test_type=test_type,
                iteration=1,
                total_agent_calls=1,
                files_fixed=0,
                warnings_reviewed=0,
                elapsed_seconds=10.0,
                test_results=(),
                timestamp=now.isoformat(),
                expires_at=now.isoformat(),
            )
            await store.save_checkpoint(checkpoint)

        # Delete all for pipeline run
        await store.delete_checkpoint("run-123")

        # Verify all deleted
        for test_type in [RepairTestType.UNIT, RepairTestType.INTEGRATION, RepairTestType.E2E]:
            exists = await store.checkpoint_exists("run-123", test_type.value)
            assert not exists

    async def test_delete_checkpoint_idempotent(self, store):
        """Test that deleting non-existent checkpoint is safe."""
        # Should not raise
        await store.delete_checkpoint("run-999", "UNIT")

    async def test_multiple_checkpoints_different_pipeline_runs(self, store):
        """Test storing checkpoints for different pipeline runs."""
        now = datetime.now(UTC)

        # Create checkpoints for different runs
        for i in range(1, 4):
            checkpoint = RepairCycleCheckpoint(
                workflow_run_id=f"run-{i}",
                test_type=RepairTestType.UNIT,
                iteration=i,
                total_agent_calls=i,
                files_fixed=0,
                warnings_reviewed=0,
                elapsed_seconds=10.0 * i,
                test_results=(),
                timestamp=now.isoformat(),
                expires_at=now.isoformat(),
            )
            await store.save_checkpoint(checkpoint)

        # Verify each can be retrieved correctly
        for i in range(1, 4):
            retrieved = await store.get_checkpoint(f"run-{i}", "UNIT")
            assert retrieved is not None
            assert retrieved.total_agent_calls == i

    async def test_checkpoint_validation_fails_on_invalid_input(self, store):
        """Test that invalid checkpoint raises error."""
        with pytest.raises(ValueError):
            checkpoint = RepairCycleCheckpoint(
                workflow_run_id="",  # Empty - invalid
                test_type=RepairTestType.UNIT,
                iteration=1,
                total_agent_calls=0,
                files_fixed=0,
                warnings_reviewed=0,
                elapsed_seconds=0.0,
                test_results=(),
                timestamp=datetime.now(UTC).isoformat(),
                expires_at=datetime.now(UTC).isoformat(),
            )


@pytest.mark.asyncio
class TestRepairCycleCheckpoint:
    """Tests for checkpoint functionality in repair cycle."""

    @pytest.fixture
    def store(self):
        """Create checkpoint store."""
        return InMemoryCheckpointStore()

    @pytest.fixture
    def clock(self):
        """Create simulation clock."""
        return SimulationClock()

    @pytest.fixture
    def adapter(self, clock, store):
        """Create adapter with checkpoint store."""
        return MockRepairCycleAdapter(clock=clock, checkpoint_store=store)

    @pytest.fixture
    def context(self):
        """Create repair cycle context."""
        return _create_repair_cycle_context(
            stage_name="code_review",
            workflow_run_id="run-123",
            test_configs=(
                RepairTestRunConfig(test_type=RepairTestType.UNIT, max_iterations=3),
            ),
            agent_name="reviewer",
            max_total_agent_calls=10,
            checkpoint_interval=1,
        )

    async def test_checkpoint_saves_state(self, adapter, context, store):
        """Test that checkpoint saves current state."""
        adapter.set_iterations_until_success(RepairTestType.UNIT, 2)

        # Manually call checkpoint
        await adapter.checkpoint(RepairTestType.UNIT, 1, context)

        # Verify checkpoint was saved
        checkpoint = await store.get_checkpoint("run-123", "UNIT")
        assert checkpoint is not None
        assert checkpoint.iteration == 1

    async def test_checkpoint_includes_agent_calls(self, adapter, context, store):
        """Test checkpoint includes agent call count."""
        adapter.total_agent_calls = 5
        adapter.set_iterations_until_success(RepairTestType.UNIT, 2)

        await adapter.checkpoint(RepairTestType.UNIT, 1, context)

        checkpoint = await store.get_checkpoint("run-123", "UNIT")
        assert checkpoint.total_agent_calls == 5

    async def test_checkpoint_includes_files_fixed(self, adapter, context, store):
        """Test checkpoint includes files fixed count."""
        adapter._files_fixed = 3
        await adapter.checkpoint(RepairTestType.UNIT, 1, context)

        checkpoint = await store.get_checkpoint("run-123", "UNIT")
        assert checkpoint.files_fixed == 3

    async def test_checkpoint_without_store_is_safe(self, clock, context):
        """Test checkpoint without store configured is safe (no-op)."""
        adapter = MockRepairCycleAdapter(clock=clock, checkpoint_store=None)
        # Should not raise
        await adapter.checkpoint(RepairTestType.UNIT, 1, context)


@pytest.mark.asyncio
class TestRepairCycleResume:
    """Tests for resume functionality."""

    @pytest.fixture
    def store(self):
        """Create checkpoint store."""
        return InMemoryCheckpointStore()

    @pytest.fixture
    def clock(self):
        """Create simulation clock."""
        return SimulationClock()

    @pytest.fixture
    def adapter(self, clock, store):
        """Create adapter with checkpoint store."""
        return MockRepairCycleAdapter(clock=clock, checkpoint_store=store)

    @pytest.fixture
    def context(self):
        """Create repair cycle context."""
        return _create_repair_cycle_context(
            stage_name="code_review",
            workflow_run_id="run-123",
            test_configs=(
                RepairTestRunConfig(test_type=RepairTestType.UNIT, max_iterations=3),
            ),
            agent_name="reviewer",
            max_total_agent_calls=10,
            checkpoint_interval=1,
        )

    async def test_resume_from_checkpoint(self, adapter, context, store):
        """Test resuming execution from checkpoint."""
        # Save checkpoint with state
        now = datetime.now(UTC)
        checkpoint = RepairCycleCheckpoint(
            workflow_run_id="run-123",
            test_type=RepairTestType.UNIT,
            iteration=2,
            total_agent_calls=3,
            files_fixed=2,
            warnings_reviewed=0,
            elapsed_seconds=30.0,
            test_results=(),
            timestamp=now.isoformat(),
            expires_at=(now + __import__("datetime").timedelta(hours=24)).isoformat(),
        )
        await store.save_checkpoint(checkpoint)

        # Try to resume
        retrieved_checkpoint = await adapter.try_resume_from_checkpoint(context)

        assert retrieved_checkpoint is not None
        assert retrieved_checkpoint.iteration == 2
        assert retrieved_checkpoint.total_agent_calls == 3

    async def test_resume_restores_state(self, adapter, context, store):
        """Test that resume restores internal state."""
        now = datetime.now(UTC)
        checkpoint = RepairCycleCheckpoint(
            workflow_run_id="run-123",
            test_type=RepairTestType.UNIT,
            iteration=2,
            total_agent_calls=5,
            files_fixed=3,
            warnings_reviewed=1,
            elapsed_seconds=45.0,
            test_results=(),
            timestamp=now.isoformat(),
            expires_at=(now + __import__("datetime").timedelta(hours=24)).isoformat(),
        )
        await store.save_checkpoint(checkpoint)

        adapter._restore_checkpoint_state(checkpoint)

        assert adapter.total_agent_calls == 5
        assert adapter._files_fixed == 3
        assert adapter._warnings_reviewed == 1
        assert adapter._elapsed_time == 45.0

    async def test_execute_without_checkpoint_starts_fresh(self, adapter, context):
        """Test execute starts fresh if no checkpoint exists."""
        # Set project so events are emitted
        adapter.current_project = "test-project"

        adapter.set_iterations_until_success(RepairTestType.UNIT, 1)
        result = await adapter.execute(context)

        # Should have started event
        events = adapter.get_all_events()
        started_events = [e for e in events if e["type"] == "repair_cycle.started"]
        assert len(started_events) > 0
