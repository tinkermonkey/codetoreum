"""In-memory implementation of IDistributedLock for testing."""

from datetime import UTC, datetime, timedelta
from types import MappingProxyType

from codetoreum.ports.output.distributed_lock import (
    AcquireResult,
    AcquireStatus,
    IDistributedLock,
    LockHolder,
    ReleaseReason,
    ReleaseResult,
)


class InMemoryDistributedLock(IDistributedLock):
    """In-memory distributed lock implementation for testing."""

    def __init__(self):
        """Initialize the lock service."""
        self._locks: dict[str, dict] = {}

    async def try_acquire(
        self,
        lock_key: str,
        holder_id: str,
        ttl_seconds: int = 7200,
        holder_metadata: dict[str, str] | MappingProxyType[str, str] | None = None,
    ) -> AcquireResult:
        """Attempt to acquire a lock."""
        if lock_key not in self._locks:
            # Lock is free, acquire it
            acquired_at = datetime.now(UTC)
            self._locks[lock_key] = {
                "holder_id": holder_id,
                "acquired_at": acquired_at,
                "ttl_seconds": ttl_seconds,
                "holder_metadata": holder_metadata or {},
            }
            return AcquireResult(
                status=AcquireStatus.ACQUIRED,
                lock_key=lock_key,
                holder_id=holder_id,
                acquired_at=acquired_at,
            )

        # Lock is held
        existing_holder = self._locks[lock_key]["holder_id"]
        if existing_holder == holder_id:
            # Same holder trying to acquire again (reentrant)
            return AcquireResult(
                status=AcquireStatus.ALREADY_HELD_BY_SELF,
                lock_key=lock_key,
                holder_id=holder_id,
                acquired_at=None,
            )

        # Different holder
        return AcquireResult(
            status=AcquireStatus.ALREADY_HELD_BY_OTHER,
            lock_key=lock_key,
            holder_id=existing_holder,
            acquired_at=None,
        )

    async def release(
        self,
        lock_key: str,
        holder_id: str,
    ) -> ReleaseResult:
        """Release a lock."""
        if lock_key not in self._locks:
            # Lock not held
            return ReleaseResult(
                released=False,
                reason=ReleaseReason.NOT_HELD,
                lock_key=lock_key,
            )

        existing_holder = self._locks[lock_key]["holder_id"]
        if existing_holder != holder_id:
            # Held by different holder
            return ReleaseResult(
                released=False,
                reason=ReleaseReason.HELD_BY_OTHER,
                lock_key=lock_key,
            )

        # Release the lock
        del self._locks[lock_key]
        return ReleaseResult(
            released=True,
            reason=None,
            lock_key=lock_key,
        )

    async def get_holder(self, lock_key: str) -> LockHolder | None:
        """Get the current lock holder."""
        if lock_key not in self._locks:
            return None

        lock_data = self._locks[lock_key]
        acquired_at = lock_data["acquired_at"]
        expires_at = acquired_at + timedelta(seconds=lock_data["ttl_seconds"])

        return LockHolder(
            lock_key=lock_key,
            holder_id=lock_data["holder_id"],
            acquired_at=acquired_at,
            ttl_seconds=lock_data["ttl_seconds"],
            expires_at=expires_at,
            holder_metadata=MappingProxyType(lock_data.get("holder_metadata", {})),
        )

    async def get_all_holders(self) -> list[LockHolder]:
        """Get all current lock holders."""
        holders = []
        for lock_key, lock_data in self._locks.items():
            acquired_at = lock_data["acquired_at"]
            expires_at = acquired_at + timedelta(seconds=lock_data["ttl_seconds"])

            holders.append(
                LockHolder(
                    lock_key=lock_key,
                    holder_id=lock_data["holder_id"],
                    acquired_at=acquired_at,
                    ttl_seconds=lock_data["ttl_seconds"],
                    expires_at=expires_at,
                    holder_metadata=MappingProxyType(lock_data.get("holder_metadata", {})),
                )
            )
        return holders

    async def renew(
        self,
        lock_key: str,
        holder_id: str,
        ttl_seconds: int,
    ) -> bool:
        """Renew a lock's TTL."""
        if lock_key not in self._locks:
            return False

        lock_data = self._locks[lock_key]
        if lock_data["holder_id"] != holder_id:
            return False

        # Update TTL
        lock_data["ttl_seconds"] = ttl_seconds
        return True
