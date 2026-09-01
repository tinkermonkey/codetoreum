"""In-memory work execution state tracker for testing and simulation."""

from typing import Any

from codetoreum.ports.output.work_execution_state_tracker import (
    IWorkExecutionStateTracker,
)


class InMemoryWorkExecutionStateTracker(IWorkExecutionStateTracker):
    """In-memory implementation of IWorkExecutionStateTracker for testing."""

    def __init__(self) -> None:
        """Initialize the in-memory work execution state tracker."""
        self._state: dict[tuple[str, str], dict[str, Any]] = {}

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
        key = (project, work_item_id)
        return self._state.get(key)

    async def mark_execution_started(
        self, project: str, work_item_id: str, agent: str
    ) -> None:
        """Mark an execution as started (in_progress).

        Records that an execution has begun, enabling recovery decisions
        at startup.

        Args:
            project: Project identifier
            work_item_id: Work item identifier
            agent: Agent identifier executing

        Raises:
            StorageError: If storage write fails
        """
        key = (project, work_item_id)
        self._state[key] = {
            "outcome": "in_progress",
            "agent": agent,
        }

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
        key = (project, work_item_id)
        self._state[key] = {
            "status": "failed",
            "agent": agent,
            "reason": reason,
        }
