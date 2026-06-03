"""Tests for FileBackedDistributedLock implementation.

Concrete implementation of TestDistributedLockContract using the
file-backed adapter.
"""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from codetoreum.adapters.secondary.file_backed_distributed_lock import FileBackedDistributedLock
from codetoreum.ports.output.distributed_lock import AcquireStatus, ReleaseReason
from tests.unit.ports.output.test_distributed_lock_contract import TestDistributedLockContract


class TestFileBackedDistributedLock(TestDistributedLockContract):
    """Test FileBackedDistributedLock against the contract."""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """Set up and tear down test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.lock_file = Path(self.temp_dir) / "test_lock.jsonl"
        yield
        # Cleanup
        if self.lock_file.exists():
            self.lock_file.unlink()
        if self.lock_file.with_suffix(".jsonl.lock").exists():
            self.lock_file.with_suffix(".jsonl.lock").unlink()

    async def create_lock(self) -> FileBackedDistributedLock:
        """Create a FileBackedDistributedLock instance."""
        return FileBackedDistributedLock(file_path=str(self.lock_file))

    @pytest.mark.asyncio
    async def test_persistence_across_instances(self):
        """Lock state should persist across instance creation."""
        # Create first instance and acquire lock
        lock1 = await self.create_lock()
        await lock1.try_acquire("test-key", "holder-1", ttl_seconds=3600)

        # Delete lock1 to release the PID lockfile
        del lock1

        # Create second instance from same file
        lock2 = FileBackedDistributedLock(file_path=str(self.lock_file))

        # Should see the lock
        holder = await lock2.get_holder("test-key")
        assert holder is not None
        assert holder.holder_id == "holder-1"

    @pytest.mark.asyncio
    async def test_smoke_test_file_operations(self):
        """Smoke test: write state, terminate, restart, verify state preserved."""
        # Initial setup
        lock1 = await self.create_lock()

        # Perform operations
        await lock1.try_acquire("key-1", "holder-1", ttl_seconds=7200)
        await lock1.try_acquire("key-2", "holder-2", ttl_seconds=7200)

        # Verify state
        holders = await lock1.get_all_holders()
        assert len(holders) == 2

        # Delete lock1 to release the PID lockfile
        del lock1

        # Simulate process restart by creating new instance
        lock2 = FileBackedDistributedLock(file_path=str(self.lock_file))

        # Verify state is preserved
        holders_after_restart = await lock2.get_all_holders()
        assert len(holders_after_restart) == 2

        holder_ids = {h.holder_id for h in holders_after_restart}
        assert holder_ids == {"holder-1", "holder-2"}

    @pytest.mark.asyncio
    async def test_single_process_guard(self):
        """Second process should fail to acquire lock."""
        # First instance
        lock1 = FileBackedDistributedLock(file_path=str(self.lock_file))

        # Second instance should fail
        with pytest.raises(RuntimeError, match="already in use"):
            FileBackedDistributedLock(file_path=str(self.lock_file))

    @pytest.mark.asyncio
    async def test_file_format_jsonl(self):
        """File should be in JSONL format."""
        lock = await self.create_lock()

        # Write some entries
        await lock.try_acquire("key-1", "holder-1")
        await lock.try_acquire("key-2", "holder-2")
        await lock.release("key-1", "holder-1")

        # Read and verify JSONL format
        with open(self.lock_file) as f:
            lines = f.readlines()

        # Each line should be valid JSON
        import json

        for line in lines:
            if line.strip():
                entry = json.loads(line)
                assert "type" in entry

    # ===== TTL Expiry Tests =====

    @pytest.mark.asyncio
    async def test_try_acquire_reclaims_expired_locks(self):
        """try_acquire should reclaim expired locks."""
        lock = await self.create_lock()

        # Acquire a lock with 1 second TTL
        await lock.try_acquire("test-key", "holder-1", ttl_seconds=1)

        # Mock datetime to simulate time passing beyond TTL
        original_now = datetime.now(UTC)
        future_time = original_now + timedelta(seconds=2)

        with patch("codetoreum.adapters.secondary.file_backed_distributed_lock.datetime") as mock_datetime:
            mock_datetime.now.return_value = future_time
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            # Try to acquire the expired lock with a different holder
            result = await lock.try_acquire("test-key", "holder-2", ttl_seconds=3600)

            # Should succeed because the lock expired and was reclaimed
            assert result.status == AcquireStatus.ACQUIRED
            assert result.holder_id == "holder-2"

    @pytest.mark.asyncio
    async def test_get_holder_returns_none_for_expired_locks(self):
        """get_holder should return None for expired locks."""
        lock = await self.create_lock()

        # Acquire a lock with 1 second TTL
        await lock.try_acquire("test-key", "holder-1", ttl_seconds=1)

        # Verify it's held
        holder = await lock.get_holder("test-key")
        assert holder is not None

        # Mock datetime to simulate expiry
        original_now = datetime.now(UTC)
        future_time = original_now + timedelta(seconds=2)

        with patch("codetoreum.adapters.secondary.file_backed_distributed_lock.datetime") as mock_datetime:
            mock_datetime.now.return_value = future_time
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            # get_holder should return None for expired lock
            holder = await lock.get_holder("test-key")
            assert holder is None

    @pytest.mark.asyncio
    async def test_get_all_holders_filters_expired_locks(self):
        """get_all_holders should filter out expired locks."""
        lock = await self.create_lock()

        # Acquire multiple locks with different TTLs
        await lock.try_acquire("key-1", "holder-1", ttl_seconds=1)
        await lock.try_acquire("key-2", "holder-2", ttl_seconds=3600)

        # Verify both are held
        holders = await lock.get_all_holders()
        assert len(holders) == 2

        # Mock datetime to simulate expiry of first lock only
        original_now = datetime.now(UTC)
        future_time = original_now + timedelta(seconds=2)

        with patch("codetoreum.adapters.secondary.file_backed_distributed_lock.datetime") as mock_datetime:
            mock_datetime.now.return_value = future_time
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            # get_all_holders should only return non-expired locks
            holders = await lock.get_all_holders()
            assert len(holders) == 1
            assert holders[0].holder_id == "holder-2"

    @pytest.mark.asyncio
    async def test_release_fails_on_expired_locks(self):
        """release should fail on expired locks."""
        lock = await self.create_lock()

        # Acquire a lock with 1 second TTL
        await lock.try_acquire("test-key", "holder-1", ttl_seconds=1)

        # Mock datetime to simulate expiry
        original_now = datetime.now(UTC)
        future_time = original_now + timedelta(seconds=2)

        with patch("codetoreum.adapters.secondary.file_backed_distributed_lock.datetime") as mock_datetime:
            mock_datetime.now.return_value = future_time
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            # Release should fail because lock has expired
            result = await lock.release("test-key", "holder-1")
            assert result.released is False
            assert result.reason == ReleaseReason.NOT_HELD

    @pytest.mark.asyncio
    async def test_renew_fails_on_expired_locks(self):
        """renew should fail on expired locks."""
        lock = await self.create_lock()

        # Acquire a lock with 1 second TTL
        await lock.try_acquire("test-key", "holder-1", ttl_seconds=1)

        # Mock datetime to simulate expiry
        original_now = datetime.now(UTC)
        future_time = original_now + timedelta(seconds=2)

        with patch("codetoreum.adapters.secondary.file_backed_distributed_lock.datetime") as mock_datetime:
            mock_datetime.now.return_value = future_time
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            # Renew should fail because lock has expired
            result = await lock.renew("test-key", "holder-1", ttl_seconds=3600)
            assert result is False

    @pytest.mark.asyncio
    async def test_expired_lock_prevents_holder_check(self):
        """Expired locks should be treated as not held."""
        lock = await self.create_lock()

        # Acquire a lock with short TTL
        await lock.try_acquire("test-key", "holder-1", ttl_seconds=1)

        # Verify it's held
        holder = await lock.get_holder("test-key")
        assert holder is not None
        assert holder.holder_id == "holder-1"

        # Mock datetime to simulate expiry
        original_now = datetime.now(UTC)
        future_time = original_now + timedelta(seconds=2)

        with patch("codetoreum.adapters.secondary.file_backed_distributed_lock.datetime") as mock_datetime:
            mock_datetime.now.return_value = future_time
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            # After expiry, holder-1 trying to acquire the same key should succeed
            result = await lock.try_acquire("test-key", "holder-1", ttl_seconds=3600)
            assert result.status == AcquireStatus.ACQUIRED
