"""Contract tests for IPipelineLockService interface."""

from abc import ABC, abstractmethod

import pytest

from codetoreum.ports.output.pipeline_lock_service import IPipelineLockService


class TestPipelineLockServiceContract(ABC):
    """Abstract contract tests for IPipelineLockService implementations.

    Subclasses must implement create_service() to provide a concrete
    IPipelineLockService implementation to test.
    """

    @abstractmethod
    async def create_service(self) -> IPipelineLockService:
        """Create and return an IPipelineLockService instance for testing."""
        pass

    @pytest.mark.asyncio
    async def test_try_acquire_lock_returns_success_true(self):
        """Acquiring lock should return (True, "") on success."""
        service = await self.create_service()

        success, reason = await service.try_acquire_lock(
            "proj-123", "board-456", "item-789"
        )

        assert success is True
        assert reason == ""

    @pytest.mark.asyncio
    async def test_try_acquire_lock_twice_returns_failure(self):
        """Acquiring same lock twice should fail."""
        service = await self.create_service()

        # First acquisition succeeds
        success1, _ = await service.try_acquire_lock(
            "proj-123", "board-456", "item-789"
        )
        assert success1 is True

        # Second acquisition fails
        success2, reason = await service.try_acquire_lock(
            "proj-123", "board-456", "item-789"
        )
        assert success2 is False
        assert len(reason) > 0  # Should have a reason

    @pytest.mark.asyncio
    async def test_release_lock_succeeds_for_holder(self):
        """Releasing lock should succeed if held by the work_item_id."""
        service = await self.create_service()

        await service.try_acquire_lock("proj-123", "board-456", "item-789")
        released = await service.release_lock("proj-123", "board-456", "item-789")

        assert released is True

    @pytest.mark.asyncio
    async def test_release_lock_fails_if_not_held(self):
        """Releasing lock should fail if not currently held."""
        service = await self.create_service()

        released = await service.release_lock("proj-123", "board-456", "item-789")

        assert released is False

    @pytest.mark.asyncio
    async def test_get_lock_returns_lock_when_held(self):
        """Get lock should return lock object when held."""
        service = await self.create_service()

        await service.try_acquire_lock("proj-123", "board-456", "item-789")
        lock = await service.get_lock("proj-123", "board-456")

        assert lock is not None
        assert lock.work_item_id == "item-789"
        assert lock.project_id == "proj-123"

    @pytest.mark.asyncio
    async def test_get_lock_returns_none_when_not_held(self):
        """Get lock should return None when no lock is held."""
        service = await self.create_service()

        lock = await service.get_lock("proj-123", "board-456")

        assert lock is None

    @pytest.mark.asyncio
    async def test_get_all_locks_includes_held_locks(self):
        """Get all locks should include all currently held locks."""
        service = await self.create_service()

        # Acquire a lock
        await service.try_acquire_lock("proj-1", "board-1", "item-1")

        locks = await service.get_all_locks()

        assert len(locks) >= 1
        lock_ids = [lock.work_item_id for lock in locks]
        assert "item-1" in lock_ids

    @pytest.mark.asyncio
    async def test_different_projects_independent(self):
        """Locks should be independent per project."""
        service = await self.create_service()

        # Acquire in proj-1
        success1, _ = await service.try_acquire_lock(
            "proj-1", "board-1", "item-1"
        )

        # Should succeed in proj-2
        success2, _ = await service.try_acquire_lock(
            "proj-2", "board-1", "item-1"
        )

        assert success1 is True
        assert success2 is True

    @pytest.mark.asyncio
    async def test_acquire_after_release_succeeds(self):
        """Should be able to acquire lock after releasing it."""
        service = await self.create_service()

        # Acquire
        await service.try_acquire_lock("proj-123", "board-456", "item-789")

        # Release
        await service.release_lock("proj-123", "board-456", "item-789")

        # Acquire again
        success, _ = await service.try_acquire_lock(
            "proj-123", "board-456", "item-789"
        )

        assert success is True

    @pytest.mark.asyncio
    async def test_invalid_parameters_handled(self):
        """Invalid parameters should be handled appropriately."""
        service = await self.create_service()

        # Empty project_id
        success, reason = await service.try_acquire_lock("", "board-456", "item-789")

        # Should either fail or succeed but not raise
        assert isinstance(success, bool)
        assert isinstance(reason, str)
