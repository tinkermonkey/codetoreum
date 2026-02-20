"""In-memory checkpoint store for testing and simulation.

Provides a fast, thread-safe checkpoint store implementation for
testing repair cycle checkpoint/resume functionality without
persistence overhead.
"""

import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from codetoreum.domain.repair_cycle_types import RepairCycleCheckpoint
from codetoreum.ports.output.repair_cycle_checkpoint_store import IRepairCycleCheckpointStore


class InMemoryCheckpointStore(IRepairCycleCheckpointStore):
    """In-memory implementation of repair cycle checkpoint store.

    Thread-safe, in-memory storage for repair cycle checkpoints.
    Automatically expires checkpoints after 24 hours.

    Features:
    - Fast in-memory storage (no I/O)
    - Thread-safe operations with RLock
    - Automatic TTL enforcement (24 hours)
    - Deterministic behavior for testing
    - Inspection methods for test verification

    Usage in tests:
        store = InMemoryCheckpointStore()
        await store.save_checkpoint(checkpoint)
        retrieved = await store.get_checkpoint("run-123", "unit")
        assert retrieved is not None
    """

    def __init__(self) -> None:
        """Initialize in-memory checkpoint store."""
        self._checkpoints: Dict[
            Tuple[str, str], Tuple[RepairCycleCheckpoint, datetime]
        ] = {}  # Key: (workflow_run_id, test_type), Value: (checkpoint, saved_time)
        self._lock = threading.RLock()

    async def save_checkpoint(self, checkpoint: RepairCycleCheckpoint) -> None:
        """Save checkpoint with automatic expiration."""
        if not checkpoint:
            raise ValueError("checkpoint cannot be None")

        with self._lock:
            # Convert enum to string for key
            test_type_str = checkpoint.test_type.value if hasattr(checkpoint.test_type, 'value') else str(checkpoint.test_type)
            key = (checkpoint.workflow_run_id, test_type_str)
            saved_time = datetime.now(timezone.utc)
            self._checkpoints[key] = (checkpoint, saved_time)

    async def get_checkpoint(
        self,
        workflow_run_id: str,
        test_type: str,
    ) -> Optional[RepairCycleCheckpoint]:
        """Retrieve checkpoint if it exists and hasn't expired."""
        with self._lock:
            key = (workflow_run_id, test_type)

            if key not in self._checkpoints:
                return None

            checkpoint, saved_time = self._checkpoints[key]

            # Check if checkpoint has expired (24 hours)
            now = datetime.now(timezone.utc)
            if now - saved_time > timedelta(hours=24):
                # Expired - remove it
                del self._checkpoints[key]
                return None

            return checkpoint

    async def delete_checkpoint(
        self,
        workflow_run_id: str,
        test_type: Optional[str] = None,
    ) -> None:
        """Delete checkpoint(s) for a pipeline run."""
        with self._lock:
            if test_type is not None:
                # Delete specific test type
                key = (workflow_run_id, test_type)
                self._checkpoints.pop(key, None)
            else:
                # Delete all for pipeline run
                keys_to_delete = [
                    key
                    for key in self._checkpoints.keys()
                    if key[0] == workflow_run_id
                ]
                for key in keys_to_delete:
                    del self._checkpoints[key]

    async def checkpoint_exists(
        self,
        workflow_run_id: str,
        test_type: str,
    ) -> bool:
        """Check if checkpoint exists and hasn't expired."""
        checkpoint = await self.get_checkpoint(workflow_run_id, test_type)
        return checkpoint is not None

    # ==================== Test/Inspection Methods ====================

    def get_all_checkpoints(self) -> Dict[Tuple[str, str], RepairCycleCheckpoint]:
        """Get all stored checkpoints (for testing)."""
        with self._lock:
            now = datetime.now(timezone.utc)
            return {
                key: checkpoint
                for key, (checkpoint, saved_time) in self._checkpoints.items()
                if now - saved_time <= timedelta(hours=24)
            }

    def clear(self) -> None:
        """Clear all checkpoints (for testing)."""
        with self._lock:
            self._checkpoints.clear()

    def get_checkpoint_count(self) -> int:
        """Get number of stored checkpoints (for testing)."""
        with self._lock:
            now = datetime.now(timezone.utc)
            return sum(
                1
                for saved_time in (t for _, t in self._checkpoints.values())
                if now - saved_time <= timedelta(hours=24)
            )
