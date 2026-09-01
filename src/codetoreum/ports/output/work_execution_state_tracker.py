"""Work execution state tracker port interface.

Provides a recovery-loop hint store for execution state tracking without
being the source of truth. The canonical execution state lives in the
event-sourced ExecutionService. This store enables fast reconnect-vs-kill
decisions at startup without replaying the full event stream.
"""

from abc import ABC, abstractmethod
from typing import Any


class IWorkExecutionStateTracker(ABC):
    """Interface for tracking work execution state for recovery decisions.

    This is a startup-only read path used to make fast recovery decisions
    without replaying the event stream. The canonical execution state lives
    in the event-sourced ExecutionService.

    Key features:
    - Fast lookup of execution state at recovery time
    - Automatic TTL (4 hours) for cleanup
    - Key format: execution:state:{project}:{work_item_id}
    - Supports reconnect vs. kill assessment

    Example:
        # Load state at startup
        state = await tracker.load_state("myproject", "item-123")
        if state:
            # Can attempt reconnect
            pass
        else:
            # Unknown execution, kill container
            pass

        # Mark execution as failed during recovery
        await tracker.mark_execution_failed(
            "myproject",
            "item-123",
            agent="claude",
            reason="Container lost connection"
        )
    """

    @abstractmethod
    async def load_state(self, project: str, work_item_id: str) -> dict[str, Any] | None:
        """Load execution state from storage.

        Retrieves the execution state for a specific work item. Returns None
        if no state exists or the state has expired.

        Args:
            project: Project identifier
            work_item_id: Work item identifier

        Returns:
            Dictionary containing execution state if found and not expired,
            None otherwise

        Raises:
            StorageError: If storage read fails
        """

    @abstractmethod
    async def mark_execution_started(
        self, project: str, work_item_id: str, agent: str
    ) -> None:
        """Mark an execution as started (in_progress).

        Records that an execution has begun, enabling recovery decisions
        at startup. The execution_tracker is read-only during recovery;
        this write happens at execution start before the container runs.

        Args:
            project: Project identifier
            work_item_id: Work item identifier
            agent: Agent identifier executing

        Returns:
            None (void operation)

        Raises:
            StorageError: If storage write fails

        Contract:
            - State record is persisted atomically
            - Record has TTL of 4 hours
            - State persists until TTL expires or execution completes
            - outcome field set to "in_progress" for recovery validation
        """

    @abstractmethod
    async def mark_execution_failed(
        self, project: str, work_item_id: str, agent: str, reason: str
    ) -> None:
        """Mark an execution as failed with a reason.

        Records that an execution has failed, typically during recovery
        operations when a container cannot be reconnected.

        Args:
            project: Project identifier
            work_item_id: Work item identifier
            agent: Agent identifier that was executing
            reason: Reason for the failure

        Returns:
            None (void operation)

        Raises:
            StorageError: If storage write fails

        Contract:
            - Failure record is persisted atomically
            - Record has TTL of 4 hours
            - Multiple marks are idempotent
            - All fields are preserved exactly
        """
