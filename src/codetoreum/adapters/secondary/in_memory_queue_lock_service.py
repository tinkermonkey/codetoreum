"""In-memory queue-based lock service for testing and local development.

Implements IPipelineLockService with in-memory state management. Suitable for
testing and development environments where distributed state is not required.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime

from codetoreum.application.pipeline_lock_service import (
    IPipelineLockService,
    LockAcquisitionResult,
    LockReleaseResult,
    LockStatus,
)
from codetoreum.infrastructure.event_bus import EventBus


@dataclass
class QueueItem:
    """Item in the queue."""
    work_item_id: str
    board_position: int


@dataclass
class QueueState:
    """Current state of a lock and queue."""
    lock_holder: str | None
    queue: list[QueueItem]


@dataclass
class LockState:
    """State of a lock and its queue."""
    lock_holder: str | None = None  # Work item ID holding the lock
    lock_acquired_at: datetime | None = None
    queue: list[str] = field(default_factory=list)  # Work item IDs in queue order
    board_positions: dict[str, int] = field(default_factory=dict)  # work_item_id -> board position


class InMemoryLockService(IPipelineLockService):
    """In-memory implementation of pipeline lock service.

    Manages locks and queues entirely in memory. Thread-safe via asyncio.Lock.
    Suitable for testing and local development.
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        stale_threshold_seconds: int = 7200,
    ):
        """Initialize the lock service.

        Args:
            event_bus: Optional event bus for emitting lock events
            stale_threshold_seconds: Time threshold for considering a lock stale (default 2 hours)
        """
        self.event_bus = event_bus
        self.stale_threshold_seconds = stale_threshold_seconds
        self._lock_state: dict[str, LockState] = {}
        self._lock = asyncio.Lock()  # Protects _lock_state

    def _get_lock_key(self, project_id: str, board_id: str) -> str:
        """Generate a unique key for a lock."""
        return f"{project_id}:{board_id}"

    def _get_or_create_state(self, lock_key: str) -> LockState:
        """Get or create lock state for a key."""
        if lock_key not in self._lock_state:
            self._lock_state[lock_key] = LockState()
        return self._lock_state[lock_key]

    def _is_lock_stale(self, state: LockState) -> bool:
        """Check if lock has exceeded stale threshold."""
        if state.lock_acquired_at is None:
            return False
        elapsed = (datetime.now(UTC) - state.lock_acquired_at).total_seconds()
        return elapsed > self.stale_threshold_seconds

    def _recover_stale_lock(self, state: LockState) -> str | None:
        """Recover a stale lock and return next holder."""
        if not self._is_lock_stale(state):
            return None

        # Release the stale lock and promote next in queue
        state.lock_holder = None
        state.lock_acquired_at = None

        if state.queue:
            next_holder = state.queue.pop(0)
            state.lock_holder = next_holder
            state.lock_acquired_at = datetime.now(UTC)
            return next_holder

        return None

    async def try_acquire_lock(
        self,
        project_id: str,
        board_id: str,
        work_item_id: str,
        board_position: int,
    ) -> LockAcquisitionResult:
        """Attempt to acquire a lock for a work item.

        Args:
            project_id: Project identifier
            board_id: Board identifier
            work_item_id: Work item identifier
            board_position: Position on the board

        Returns:
            LockAcquisitionResult with status and queue information
        """
        async with self._lock:
            lock_key = self._get_lock_key(project_id, board_id)
            state = self._get_or_create_state(lock_key)

            # Update board position
            state.board_positions[work_item_id] = board_position

            # Check for stale lock and recover
            if state.lock_holder is not None:
                self._recover_stale_lock(state)

            # Case 1: Lock is free
            if state.lock_holder is None:
                state.lock_holder = work_item_id
                state.lock_acquired_at = datetime.now(UTC)
                queue_length = len(state.queue)
                return LockAcquisitionResult(
                    status=LockStatus.ACQUIRED,
                    work_item_id=work_item_id,
                    queue_length=queue_length,
                )

            # Case 2: Work item already holds lock
            if state.lock_holder == work_item_id:
                queue_length = len(state.queue)
                return LockAcquisitionResult(
                    status=LockStatus.ALREADY_HELD,
                    work_item_id=work_item_id,
                    queue_length=queue_length,
                )

            # Case 3: Lock held by another, queue this work item
            if work_item_id not in state.queue:
                # Insert in position order (lowest board position first)
                insert_pos = 0
                for i, queued_id in enumerate(state.queue):
                    queued_pos = state.board_positions.get(queued_id, float("inf"))
                    if board_position < queued_pos:
                        insert_pos = i
                        break
                    insert_pos = i + 1

                state.queue.insert(insert_pos, work_item_id)

            queue_position = state.queue.index(work_item_id)
            queue_length = len(state.queue)

            return LockAcquisitionResult(
                status=LockStatus.QUEUED,
                work_item_id=work_item_id,
                queue_position=queue_position,
                queue_length=queue_length,
            )

    async def release_lock(
        self,
        project_id: str,
        board_id: str,
        work_item_id: str,
    ) -> LockReleaseResult:
        """Release a held lock and promote next queued work item.

        Args:
            project_id: Project identifier
            board_id: Board identifier
            work_item_id: Work item holding the lock

        Returns:
            LockReleaseResult with next holder information

        Raises:
            ValueError: If work item doesn't hold the lock
        """
        async with self._lock:
            lock_key = self._get_lock_key(project_id, board_id)
            state = self._get_or_create_state(lock_key)

            if state.lock_holder != work_item_id:
                raise ValueError(f"Work item {work_item_id} does not hold lock for {lock_key}")

            state.lock_holder = None
            state.lock_acquired_at = None

            next_work_item_id = None
            if state.queue:
                next_work_item_id = state.queue.pop(0)
                state.lock_holder = next_work_item_id
                state.lock_acquired_at = datetime.now(UTC)

            queue_length = len(state.queue)

            return LockReleaseResult(
                released_work_item_id=work_item_id,
                next_work_item_id=next_work_item_id,
                queue_length_after_release=queue_length,
            )

    async def update_queue_positions(
        self,
        project_id: str,
        board_id: str,
        position_updates: dict[str, int],
    ) -> None:
        """Update queue positions for work items.

        Args:
            project_id: Project identifier
            board_id: Board identifier
            position_updates: Mapping of work_item_id to new position
        """
        async with self._lock:
            lock_key = self._get_lock_key(project_id, board_id)
            state = self._get_or_create_state(lock_key)

            # Update board positions
            for work_item_id, position in position_updates.items():
                state.board_positions[work_item_id] = position

            # Re-sort queue based on updated positions
            queue_items = state.queue[:]
            queue_items.sort(
                key=lambda item: state.board_positions.get(item, float("inf"))
            )
            state.queue = queue_items

    async def get_queue_state(self, project_id: str, board_id: str) -> QueueState:
        """Get current queue state for diagnostic/testing purposes.

        Args:
            project_id: Project identifier
            board_id: Board identifier

        Returns:
            QueueState with lock holder and queue items
        """
        async with self._lock:
            lock_key = self._get_lock_key(project_id, board_id)
            state = self._get_or_create_state(lock_key)

            queue_items = [
                QueueItem(
                    work_item_id=item,
                    board_position=state.board_positions.get(item, -1)
                )
                for item in state.queue
            ]

            return QueueState(
                lock_holder=state.lock_holder,
                queue=queue_items,
            )
