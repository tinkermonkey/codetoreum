"""Distributed lock primitive port interface.

IDistributedLock is a dumb distributed lock primitive that knows nothing about
queues, work items, or downstream orchestration. It has a key and a holder;
operations are atomic at the storage layer.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from types import MappingProxyType


class AcquireStatus(Enum):
    """Status codes returned by try_acquire()."""
    ACQUIRED = "acquired"  # Lock was free; now held by requested holder
    ALREADY_HELD_BY_SELF = "already_held_by_self"  # Reentrant — same holder, no-op
    ALREADY_HELD_BY_OTHER = "already_held_by_other"  # Different holder has the lock


class ReleaseReason(Enum):
    """Reasons for unsuccessful release."""
    NOT_HELD = "not_held"  # Lock is not currently held
    HELD_BY_OTHER = "held_by_other"  # Lock is held by a different holder


@dataclass(frozen=True)
class AcquireResult:
    """Result of an acquire attempt."""
    status: AcquireStatus
    lock_key: str
    holder_id: str  # The current holder (may be != requested on ALREADY_HELD_BY_OTHER)
    acquired_at: datetime | None  # Set if status == ACQUIRED; None otherwise


@dataclass(frozen=True)
class ReleaseResult:
    """Result of a release attempt."""
    released: bool  # True if the lock was held and is now free
    reason: ReleaseReason | None  # Set if released=False; explains why
    lock_key: str


@dataclass(frozen=True)
class LockHolder:
    """Current holder of a lock."""
    lock_key: str
    holder_id: str
    acquired_at: datetime
    ttl_seconds: int
    expires_at: datetime
    holder_metadata: MappingProxyType[str, str]  # Immutable view of metadata dict


class IDistributedLock(ABC):
    """Distributed lock primitive.

    Knows nothing about queues, work items, workflow runs, or downstream
    orchestration. A lock has a key and a holder; operations are atomic at
    the storage layer.

    Production implementation: RedisDistributedLock (SET NX EX).
    Local-dev / harness: FileBackedDistributedLock (JSONL + fsync).

    Callers are responsible for emitting domain events (PipelineLockAcquiredEvent,
    PipelineLockReleasedEvent) based on returned AcquireResult and ReleaseResult
    status codes. This separation lets callers inject context (project_id, board_id)
    that the lock primitive itself lacks.
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
            Callers MUST emit PipelineLockAcquiredEvent when status == ACQUIRED.
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

        Callers MUST emit PipelineLockReleasedEvent when released == True.
        """

    @abstractmethod
    async def get_holder(self, lock_key: str) -> LockHolder | None:
        """Return the current holder, or None if unlocked.

        Used for diagnostics and the orphan-scan startup behaviour.
        """

    @abstractmethod
    async def get_all_holders(self) -> list[LockHolder]:
        """Return all currently held locks across all keys.

        Used by PipelineOrchestrator's startup orphan scan (each holder cross-
        referenced against IActiveWorkflowRunRegistry; mismatches release
        through the normal release() path).
        """

    @abstractmethod
    async def renew(
        self,
        lock_key: str,
        holder_id: str,
        ttl_seconds: int,
    ) -> bool:
        """Extend the TTL on a held lock. Returns False if not held by this holder.

        Optional in practice — only callers that hold long-running locks need
        to refresh. Codetoreum's current usage relies on the default 2h TTL
        and never renews.
        """
