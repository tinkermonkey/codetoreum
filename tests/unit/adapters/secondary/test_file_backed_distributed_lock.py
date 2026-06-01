"""Tests for FileBackedDistributedLock implementation.

Concrete implementation of TestDistributedLockContract using the
file-backed adapter.
"""

import tempfile
from pathlib import Path

import pytest

from codetoreum.adapters.secondary.file_backed_distributed_lock import FileBackedDistributedLock
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
