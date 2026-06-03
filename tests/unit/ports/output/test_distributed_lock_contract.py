"""Contract tests for IDistributedLock interface.

These abstract tests define the contract that all IDistributedLock
implementations must satisfy. Subclasses provide specific implementations
to test via create_lock().
"""

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta

import pytest

from codetoreum.ports.output.distributed_lock import (
    AcquireStatus,
    IDistributedLock,
    ReleaseReason,
)


class TestDistributedLockContract(ABC):
    """Abstract contract tests for IDistributedLock implementations.

    Subclasses must implement create_lock() to provide a concrete
    IDistributedLock implementation to test.

    These tests verify:
    - Lock acquisition and release semantics
    - Idempotency and no-op behavior
    - TTL and expiration handling
    - Metadata preservation
    - Error and edge case handling
    """

    @abstractmethod
    async def create_lock(self) -> IDistributedLock:
        """Create and return an IDistributedLock instance for testing."""

    # ===== try_acquire Tests =====

    @pytest.mark.asyncio
    async def test_try_acquire_initial_lock_succeeds(self):
        """Initial lock acquisition should succeed."""
        lock = await self.create_lock()

        result = await lock.try_acquire("test-key-1", "holder-1")

        assert result.status == AcquireStatus.ACQUIRED
        assert result.lock_key == "test-key-1"
        assert result.holder_id == "holder-1"
        assert result.acquired_at is not None

    @pytest.mark.asyncio
    async def test_try_acquire_already_held_by_other(self):
        """Acquiring an already-held lock should return ALREADY_HELD_BY_OTHER."""
        lock = await self.create_lock()

        await lock.try_acquire("test-key-1", "holder-1")
        result = await lock.try_acquire("test-key-1", "holder-2")

        assert result.status == AcquireStatus.ALREADY_HELD_BY_OTHER
        assert result.holder_id == "holder-1"

    @pytest.mark.asyncio
    async def test_try_acquire_already_held_by_self(self):
        """Re-acquiring own lock should return ALREADY_HELD_BY_SELF."""
        lock = await self.create_lock()

        await lock.try_acquire("test-key-1", "holder-1")
        result = await lock.try_acquire("test-key-1", "holder-1")

        assert result.status == AcquireStatus.ALREADY_HELD_BY_SELF
        assert result.holder_id == "holder-1"

    @pytest.mark.asyncio
    async def test_try_acquire_with_metadata(self):
        """Metadata should be stored and retrievable."""
        lock = await self.create_lock()
        metadata = {"project_id": "proj-1", "board_id": "board-1"}

        await lock.try_acquire("test-key-1", "holder-1", holder_metadata=metadata)
        holder = await lock.get_holder("test-key-1")

        assert holder is not None
        assert holder.holder_metadata == metadata

    @pytest.mark.asyncio
    async def test_try_acquire_with_custom_ttl(self):
        """Custom TTL should be stored."""
        lock = await self.create_lock()

        result = await lock.try_acquire("test-key-1", "holder-1", ttl_seconds=3600)
        holder = await lock.get_holder("test-key-1")

        assert holder is not None
        assert holder.ttl_seconds == 3600

    @pytest.mark.asyncio
    async def test_try_acquire_preserves_acquired_at(self):
        """acquired_at timestamp should be set correctly."""
        lock = await self.create_lock()
        before = datetime.now(UTC)

        result = await lock.try_acquire("test-key-1", "holder-1")

        assert result.acquired_at is not None
        assert result.acquired_at >= before
        assert result.acquired_at <= datetime.now(UTC)

    @pytest.mark.asyncio
    async def test_try_acquire_multiple_independent_locks(self):
        """Different lock keys should be independent."""
        lock = await self.create_lock()

        result1 = await lock.try_acquire("key-1", "holder-1")
        result2 = await lock.try_acquire("key-2", "holder-2")

        assert result1.status == AcquireStatus.ACQUIRED
        assert result2.status == AcquireStatus.ACQUIRED

    # ===== release Tests =====

    @pytest.mark.asyncio
    async def test_release_successful_lock(self):
        """Releasing a held lock should succeed."""
        lock = await self.create_lock()

        await lock.try_acquire("test-key-1", "holder-1")
        result = await lock.release("test-key-1", "holder-1")

        assert result.released is True
        assert result.reason is None

    @pytest.mark.asyncio
    async def test_release_not_held_lock(self):
        """Releasing a non-existent lock should return NOT_HELD."""
        lock = await self.create_lock()

        result = await lock.release("test-key-1", "holder-1")

        assert result.released is False
        assert result.reason == ReleaseReason.NOT_HELD

    @pytest.mark.asyncio
    async def test_release_wrong_holder(self):
        """Releasing a lock held by different holder should return HELD_BY_OTHER."""
        lock = await self.create_lock()

        await lock.try_acquire("test-key-1", "holder-1")
        result = await lock.release("test-key-1", "holder-2")

        assert result.released is False
        assert result.reason == ReleaseReason.HELD_BY_OTHER

    @pytest.mark.asyncio
    async def test_release_idempotent(self):
        """Releasing twice should be idempotent."""
        lock = await self.create_lock()

        await lock.try_acquire("test-key-1", "holder-1")
        await lock.release("test-key-1", "holder-1")
        result = await lock.release("test-key-1", "holder-1")

        assert result.released is False
        assert result.reason == ReleaseReason.NOT_HELD

    @pytest.mark.asyncio
    async def test_release_clears_holder(self):
        """get_holder should return None after release."""
        lock = await self.create_lock()

        await lock.try_acquire("test-key-1", "holder-1")
        await lock.release("test-key-1", "holder-1")
        holder = await lock.get_holder("test-key-1")

        assert holder is None

    # ===== get_holder Tests =====

    @pytest.mark.asyncio
    async def test_get_holder_returns_none_for_unheld_lock(self):
        """get_holder should return None for unheld lock."""
        lock = await self.create_lock()

        holder = await lock.get_holder("test-key-1")

        assert holder is None

    @pytest.mark.asyncio
    async def test_get_holder_returns_holder_info(self):
        """get_holder should return holder information."""
        lock = await self.create_lock()

        await lock.try_acquire("test-key-1", "holder-1", ttl_seconds=3600)
        holder = await lock.get_holder("test-key-1")

        assert holder is not None
        assert holder.lock_key == "test-key-1"
        assert holder.holder_id == "holder-1"
        assert holder.ttl_seconds == 3600
        assert holder.expires_at > holder.acquired_at

    # ===== get_all_holders Tests =====

    @pytest.mark.asyncio
    async def test_get_all_holders_empty(self):
        """get_all_holders should return empty list when no locks held."""
        lock = await self.create_lock()

        holders = await lock.get_all_holders()

        assert holders == []

    @pytest.mark.asyncio
    async def test_get_all_holders_single_lock(self):
        """get_all_holders should return single lock."""
        lock = await self.create_lock()

        await lock.try_acquire("test-key-1", "holder-1")
        holders = await lock.get_all_holders()

        assert len(holders) == 1
        assert holders[0].holder_id == "holder-1"

    @pytest.mark.asyncio
    async def test_get_all_holders_multiple_locks(self):
        """get_all_holders should return all locks."""
        lock = await self.create_lock()

        await lock.try_acquire("key-1", "holder-1")
        await lock.try_acquire("key-2", "holder-2")
        await lock.try_acquire("key-3", "holder-3")

        holders = await lock.get_all_holders()

        assert len(holders) == 3
        holder_ids = {h.holder_id for h in holders}
        assert holder_ids == {"holder-1", "holder-2", "holder-3"}

    # ===== renew Tests =====

    @pytest.mark.asyncio
    async def test_renew_held_lock_succeeds(self):
        """Renewing a held lock should succeed."""
        lock = await self.create_lock()

        await lock.try_acquire("test-key-1", "holder-1", ttl_seconds=3600)
        result = await lock.renew("test-key-1", "holder-1", ttl_seconds=7200)

        assert result is True

    @pytest.mark.asyncio
    async def test_renew_unheld_lock_fails(self):
        """Renewing an unheld lock should fail."""
        lock = await self.create_lock()

        result = await lock.renew("test-key-1", "holder-1", ttl_seconds=7200)

        assert result is False

    @pytest.mark.asyncio
    async def test_renew_wrong_holder_fails(self):
        """Renewing with wrong holder should fail."""
        lock = await self.create_lock()

        await lock.try_acquire("test-key-1", "holder-1")
        result = await lock.renew("test-key-1", "holder-2", ttl_seconds=7200)

        assert result is False

    @pytest.mark.asyncio
    async def test_renew_updates_ttl(self):
        """Renewing should update TTL."""
        lock = await self.create_lock()

        await lock.try_acquire("test-key-1", "holder-1", ttl_seconds=3600)
        before_ttl = (await lock.get_holder("test-key-1")).ttl_seconds

        await lock.renew("test-key-1", "holder-1", ttl_seconds=7200)
        after_ttl = (await lock.get_holder("test-key-1")).ttl_seconds

        assert before_ttl == 3600
        assert after_ttl == 7200

    # ===== Edge Cases =====

    @pytest.mark.asyncio
    async def test_acquire_release_acquire_cycle(self):
        """Should be able to re-acquire after release."""
        lock = await self.create_lock()

        # First acquisition
        result1 = await lock.try_acquire("test-key-1", "holder-1")
        assert result1.status == AcquireStatus.ACQUIRED

        # Release
        await lock.release("test-key-1", "holder-1")

        # Re-acquire with different holder
        result2 = await lock.try_acquire("test-key-1", "holder-2")
        assert result2.status == AcquireStatus.ACQUIRED
        assert result2.holder_id == "holder-2"

    @pytest.mark.asyncio
    async def test_lock_holder_immutability(self):
        """LockHolder should be immutable (frozen dataclass)."""
        lock = await self.create_lock()

        await lock.try_acquire("test-key-1", "holder-1")
        holder = await lock.get_holder("test-key-1")

        # Attempt to modify should fail
        with pytest.raises((AttributeError, TypeError, Exception)):
            holder.holder_id = "modified"

    @pytest.mark.asyncio
    async def test_concurrent_acquire_attempts(self):
        """Concurrent acquires should be atomic."""
        lock = await self.create_lock()

        # These would race in concurrent execution
        result1 = await lock.try_acquire("test-key-1", "holder-1")
        result2 = await lock.try_acquire("test-key-1", "holder-2")

        # One should succeed, one should fail
        if result1.status == AcquireStatus.ACQUIRED:
            assert result2.status == AcquireStatus.ALREADY_HELD_BY_OTHER
        else:
            assert result2.status == AcquireStatus.ACQUIRED
            assert result1.status == AcquireStatus.ALREADY_HELD_BY_OTHER
