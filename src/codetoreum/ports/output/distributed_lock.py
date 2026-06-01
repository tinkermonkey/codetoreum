"""Distributed lock service port interface for pipeline coordination.

This interface defines contracts for a distributed lock primitive with no knowledge
of queues, work items, workflow runs, or downstream orchestration. A lock has a key
and a holder; operations are atomic at the storage layer.

Production implementation: RedisDistributedLock (SET NX EX).
Local-dev / harness: FileBackedDistributedLock (JSONL + fsync).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AcquireStatus(str, Enum):
    """Status of lock acquisition attempt."""

    ACQUIRED = "acquired"
    ALREADY_HELD_BY_SELF = "already_held_by_self"
    ALREADY_HELD_BY_OTHER = "already_held_by_other"


class ReleaseReason(str, Enum):
    """Reason why a lock release was not successful."""

    NOT_HELD = "not_held"
    HELD_BY_OTHER = "held_by_other"


@dataclass(frozen=True)
class AcquireResult:
    """Result of a lock acquisition attempt."""

    status: AcquireStatus
    lock_key: str
    holder_id: str
    acquired_at: datetime | None

    def __post_init__(self) -> None:
        """Validate result consistency."""
        if self.status == AcquireStatus.ACQUIRED:
            if self.acquired_at is None:
                msg = "acquired_at must be set when status is ACQUIRED"
                raise ValueError(msg)
        else:
            if self.acquired_at is not None:
                msg = "acquired_at must be None when status is not ACQUIRED"
                raise ValueError(msg)


@dataclass(frozen=True)
class ReleaseResult:
    """Result of a lock release attempt."""

    released: bool
    reason: ReleaseReason | None
    lock_key: str

    def __post_init__(self) -> None:
        """Validate result consistency."""
        if self.released:
            if self.reason is not None:
                msg = "reason must be None when released is True"
                raise ValueError(msg)
        else:
            if self.reason is None:
                msg = "reason must be set when released is False"
                raise ValueError(msg)


@dataclass(frozen=True)
class LockHolder:
    """Represents the current holder of a lock."""

    lock_key: str
    holder_id: str
    acquired_at: datetime
    ttl_seconds: int
    expires_at: datetime
    holder_metadata: dict[str, str]

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not isinstance(self.lock_key, str) or not self.lock_key:
            msg = "lock_key must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.holder_id, str) or not self.holder_id:
            msg = "holder_id must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.acquired_at, datetime):
            msg = "acquired_at must be a datetime object"
            raise ValueError(msg)

        if not isinstance(self.ttl_seconds, int) or self.ttl_seconds <= 0:
            msg = "ttl_seconds must be a positive integer"
            raise ValueError(msg)

        if not isinstance(self.expires_at, datetime):
            msg = "expires_at must be a datetime object"
            raise ValueError(msg)

        if not isinstance(self.holder_metadata, dict):
            msg = "holder_metadata must be a dict"
            raise ValueError(msg)

        if self.expires_at <= self.acquired_at:
            msg = "expires_at must be after acquired_at"
            raise ValueError(msg)


class IDistributedLock(ABC):
    """Distributed lock primitive for pipeline coordination.

    Knows nothing about queues, work items, workflow runs, or downstream
    orchestration. A lock has a key and a holder; operations are atomic at
    the storage layer.

    The adapter emits PipelineLockAcquiredEvent on every successful acquire
    and PipelineLockReleasedEvent on every successful release. Callers and
    subscribers MUST treat these events as the only public signal of state
    change — no other side effects are emitted from the adapter.

    Example:
        # Attempt to acquire lock
        result = await lock.try_acquire(
            lock_key="proj-1:board-1",
            holder_id="item-123",
            ttl_seconds=7200,
            holder_metadata={"project_id": "proj-1", "board_id": "board-1"}
        )

        if result.status == AcquireStatus.ACQUIRED:
            # Lock acquired, process item
            await process_item()
            # Release when done
            await lock.release("proj-1:board-1", "item-123")
    """

    @abstractmethod
    async def try_acquire(
        self,
        lock_key: str,
        holder_id: str,
        ttl_seconds: int = 7200,
        holder_metadata: dict[str, str] | None = None,
    ) -> AcquireResult:
        """Attempt to acquire the lock for the given holder.

        Args:
            lock_key: Opaque namespaced identifier (e.g. f"{project_id}:{board_id}").
                The adapter treats this as a black box; key namespacing is the
                caller's concern.
            holder_id: Opaque holder identity (codetoreum convention: work_item_id).
            ttl_seconds: Safety TTL. The lock auto-releases after this if not
                refreshed. Default 7200 (2h). The TTL is a last-resort safety
                net; the primary recovery mechanism is the orchestrator's
                startup orphan scan.
            holder_metadata: Optional opaque dict stored alongside the holder
                and included in emitted events. Lets subscribers (e.g.
                PipelineOrchestrator) recover context like project_id and
                board_id without parsing lock_key. The adapter does not
                interpret the contents.

        Returns:
            AcquireResult with status ∈ {ACQUIRED, ALREADY_HELD_BY_OTHER, ALREADY_HELD_BY_SELF}.

        Emits:
            PipelineLockAcquiredEvent on ACQUIRED. Not on ALREADY_HELD_BY_* —
            those are no-op transitions.
        """

    @abstractmethod
    async def release(
        self,
        lock_key: str,
        holder_id: str,
    ) -> ReleaseResult:
        """Release the lock if held by the given holder.

        Idempotent. Calling release when the lock is not held returns
        ReleaseResult(released=False, reason="not_held") with no error.
        Calling release when the lock is held by a different holder returns
        ReleaseResult(released=False, reason="held_by_other") with no error.

        Args:
            lock_key: The lock key to release.
            holder_id: The holder ID that must match the current holder.

        Returns:
            ReleaseResult with released=True on successful release,
            released=False with reason on no-op cases.

        Emits:
            PipelineLockReleasedEvent on successful release. Not on no-op cases.
        """

    @abstractmethod
    async def get_holder(self, lock_key: str) -> LockHolder | None:
        """Return the current holder, or None if unlocked.

        Used for diagnostics and the orphan-scan startup behaviour.

        Args:
            lock_key: The lock key to check.

        Returns:
            LockHolder if a lock is held, None otherwise.
        """

    @abstractmethod
    async def get_all_holders(self) -> list[LockHolder]:
        """Return all currently held locks across all keys.

        Used by PipelineOrchestrator's startup orphan scan (each holder cross-
        referenced against IActiveWorkflowRunRegistry; mismatches release
        through the normal release() path).

        Returns:
            List of LockHolder objects for all currently held locks.
        """

    @abstractmethod
    async def renew(
        self,
        lock_key: str,
        holder_id: str,
        ttl_seconds: int,
    ) -> bool:
        """Extend the TTL on a held lock.

        Returns False if not held by this holder.

        Optional in practice — only callers that hold long-running locks need
        to refresh. Codetoreum's current usage relies on the default 2h TTL
        and never renews.

        Args:
            lock_key: The lock key to renew.
            holder_id: The holder ID that must match the current holder.
            ttl_seconds: The new TTL in seconds.

        Returns:
            True if renewed, False if not held by this holder.
        """
