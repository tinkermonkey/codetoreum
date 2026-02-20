"""Repair cycle checkpoint store port interface.

Defines the contract for persisting and retrieving repair cycle checkpoints
to support resuming after failures or interruptions.
"""

from abc import ABC, abstractmethod
from typing import Optional

from codetoreum.domain.repair_cycle_types import RepairCycleCheckpoint


class IRepairCycleCheckpointStore(ABC):
    """Interface for checkpoint storage and retrieval.

    Handles persistence of repair cycle state to support resuming after
    container crashes or other infrastructure failures. Checkpoints are
    automatically expired after 24 hours.

    Key features:
    - Atomic save and retrieve operations
    - Automatic TTL (24 hours) for cleanup
    - Key format: repair_cycle:{workflow_run_id}:{test_type}
    - Supports validation against stale or corrupted checkpoints

    Example:
        # Save checkpoint
        checkpoint = RepairCycleCheckpoint(
            workflow_run_id="run-123",
            test_type="unit",
            iteration=2,
            total_agent_calls=5,
            ...
        )
        await store.save_checkpoint(checkpoint)

        # Retrieve checkpoint
        checkpoint = await store.get_checkpoint("run-123", "unit")
        if checkpoint:
            # Resume from checkpoint
            pass
    """

    @abstractmethod
    async def save_checkpoint(self, checkpoint: RepairCycleCheckpoint) -> None:
        """Save a repair cycle checkpoint to persistent storage.

        Saves the complete cycle state including current iteration, agent
        calls, and test results. Checkpoints are automatically expired
        after 24 hours.

        Args:
            checkpoint: Checkpoint to save (immutable)

        Returns:
            None (void operation)

        Raises:
            PersistenceError: If storage write fails
            ValueError: If checkpoint is invalid

        Contract:
            - Checkpoint is persisted atomically
            - Checkpoint has TTL of 24 hours
            - Multiple saves of same checkpoint are idempotent
            - All fields of checkpoint are preserved exactly
        """
        pass

    @abstractmethod
    async def get_checkpoint(
        self,
        workflow_run_id: str,
        test_type: str,
    ) -> Optional[RepairCycleCheckpoint]:
        """Retrieve a repair cycle checkpoint.

        Retrieves the most recent checkpoint for the specified pipeline run
        and test type. Returns None if no checkpoint exists or checkpoint
        has expired.

        Args:
            workflow_run_id: Pipeline run identifier
            test_type: Test type (unit, integration, e2e)

        Returns:
            RepairCycleCheckpoint if found and not expired, None otherwise

        Raises:
            PersistenceError: If storage read fails

        Contract:
            - Returns None for missing checkpoints (no error)
            - Returns None for expired checkpoints (24 hour TTL)
            - Returned checkpoint is validated (all fields correct)
            - Multiple reads return identical checkpoint
        """
        pass

    @abstractmethod
    async def delete_checkpoint(
        self,
        workflow_run_id: str,
        test_type: Optional[str] = None,
    ) -> None:
        """Delete checkpoint(s) for a pipeline run.

        Deletes checkpoints after successful completion or manual cleanup.
        If test_type is None, deletes all checkpoints for the pipeline run.

        Args:
            workflow_run_id: Pipeline run identifier
            test_type: Optional specific test type, or None for all

        Returns:
            None (void operation)

        Raises:
            PersistenceError: If storage delete fails

        Contract:
            - Deletion is atomic
            - Deletion is idempotent (deleting missing checkpoint is safe)
            - Can delete single test type or all for pipeline run
        """
        pass

    @abstractmethod
    async def checkpoint_exists(
        self,
        workflow_run_id: str,
        test_type: str,
    ) -> bool:
        """Check if a non-expired checkpoint exists.

        Quick check for checkpoint existence without retrieving full data.

        Args:
            workflow_run_id: Pipeline run identifier
            test_type: Test type (unit, integration, e2e)

        Returns:
            True if checkpoint exists and has not expired, False otherwise

        Raises:
            PersistenceError: If storage check fails

        Contract:
            - Returns False for missing checkpoints
            - Returns False for expired checkpoints
            - Does not throw on missing checkpoints
        """
        pass
