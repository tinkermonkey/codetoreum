"""Tests for active workflow run registry implementations.

Tests verify:
- ActiveRunInfo includes started_at field
- Registry persistence and retrieval
- Duration calculation capability
"""

from datetime import UTC, datetime, timedelta

import pytest

from codetoreum.adapters.secondary.redis_active_workflow_run_registry import (
    RedisActiveWorkflowRunRegistry,
)
from codetoreum.adapters.testing.in_memory_active_workflow_run_registry import (
    InMemoryActiveWorkflowRunRegistry,
)
from codetoreum.ports.output.active_workflow_run_registry import ActiveRunInfo


class MockRedis:
    """Mock Redis client for testing."""

    def __init__(self):
        """Initialize mock Redis storage."""
        self._data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        """Mock Redis GET operation."""
        return self._data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> str:
        """Mock Redis SET operation."""
        self._data[key] = value
        return "OK"

    async def delete(self, key: str) -> int:
        """Mock Redis DELETE operation."""
        if key in self._data:
            del self._data[key]
            return 1
        return 0

    async def scan_iter(self, match: str | None = None) -> list[str]:
        """Mock Redis SCAN_ITER operation."""
        if match:
            import fnmatch

            return [k for k in self._data.keys() if fnmatch.fnmatch(k, match)]
        return list(self._data.keys())


@pytest.mark.asyncio
class TestInMemoryActiveWorkflowRunRegistry:
    """Tests for InMemoryActiveWorkflowRunRegistry."""

    async def test_set_and_get_active_run(self):
        """Test setting and retrieving an active run."""
        registry = InMemoryActiveWorkflowRunRegistry()

        now = datetime.now(UTC)
        await registry.set_active_run(
            work_item_id="wi-123",
            run_id="run-456",
            stage_name="review",
            project_id="proj-1",
            board_id="board-1",
            started_at=now.isoformat(),
        )

        result = await registry.get_active_run("wi-123")

        assert result is not None
        assert result.work_item_id == "wi-123"
        assert result.run_id == "run-456"
        assert result.stage_name == "review"
        assert result.project_id == "proj-1"
        assert result.board_id == "board-1"
        assert result.started_at == now.isoformat()

    async def test_clear_run(self):
        """Test clearing an active run."""
        registry = InMemoryActiveWorkflowRunRegistry()

        now = datetime.now(UTC)
        await registry.set_active_run(
            work_item_id="wi-123",
            run_id="run-456",
            stage_name="design",
            project_id="proj-1",
            board_id="board-1",
            started_at=now.isoformat(),
        )

        await registry.clear_run("wi-123")

        result = await registry.get_active_run("wi-123")
        assert result is None

    async def test_update_stage_preserves_started_at(self):
        """Test that updating stage preserves the original started_at time."""
        registry = InMemoryActiveWorkflowRunRegistry()

        now = datetime.now(UTC)
        await registry.set_active_run(
            work_item_id="wi-123",
            run_id="run-456",
            stage_name="design",
            project_id="proj-1",
            board_id="board-1",
            started_at=now.isoformat(),
        )

        # Update stage
        run_info = await registry.get_active_run("wi-123")
        assert run_info is not None

        await registry.set_active_run(
            work_item_id="wi-123",
            run_id=run_info.run_id,
            stage_name="review",  # Changed stage
            project_id=run_info.project_id,
            board_id=run_info.board_id,
            started_at=run_info.started_at,  # Preserve original started_at
        )

        updated = await registry.get_active_run("wi-123")
        assert updated is not None
        assert updated.stage_name == "review"
        assert updated.started_at == now.isoformat()

    async def test_calculate_duration_from_started_at(self):
        """Test that duration can be calculated from started_at timestamp."""
        registry = InMemoryActiveWorkflowRunRegistry()

        now = datetime.now(UTC)
        earlier = now - timedelta(minutes=5)

        await registry.set_active_run(
            work_item_id="wi-123",
            run_id="run-456",
            stage_name="coding",
            project_id="proj-1",
            board_id="board-1",
            started_at=earlier.isoformat(),
        )

        run_info = await registry.get_active_run("wi-123")
        assert run_info is not None

        # Calculate duration
        started = datetime.fromisoformat(run_info.started_at)
        duration = int((now - started).total_seconds())

        # Should be approximately 300 seconds (5 minutes)
        assert 295 <= duration <= 305

    async def test_get_all_runs(self):
        """Test retrieving all active runs."""
        registry = InMemoryActiveWorkflowRunRegistry()

        now = datetime.now(UTC)

        await registry.set_active_run(
            work_item_id="wi-1",
            run_id="run-1",
            stage_name="design",
            project_id="proj-1",
            board_id="board-1",
            started_at=now.isoformat(),
        )

        await registry.set_active_run(
            work_item_id="wi-2",
            run_id="run-2",
            stage_name="review",
            project_id="proj-1",
            board_id="board-1",
            started_at=now.isoformat(),
        )

        all_runs = await registry.get_all_runs()

        assert len(all_runs) == 2
        work_item_ids = [wi for wi, _ in all_runs]
        assert "wi-1" in work_item_ids
        assert "wi-2" in work_item_ids


@pytest.mark.asyncio
class TestRedisActiveWorkflowRunRegistry:
    """Tests for RedisActiveWorkflowRunRegistry."""

    async def test_set_and_get_active_run(self):
        """Test setting and retrieving an active run via Redis."""
        redis = MockRedis()
        registry = RedisActiveWorkflowRunRegistry(redis_client=redis)

        now = datetime.now(UTC)
        await registry.set_active_run(
            work_item_id="wi-123",
            run_id="run-456",
            stage_name="design",
            project_id="proj-1",
            board_id="board-1",
            started_at=now.isoformat(),
        )

        result = await registry.get_active_run("wi-123")

        assert result is not None
        assert result.work_item_id == "wi-123"
        assert result.run_id == "run-456"
        assert result.stage_name == "design"
        assert result.project_id == "proj-1"
        assert result.board_id == "board-1"
        assert result.started_at == now.isoformat()

    async def test_persistence_across_instances(self):
        """Test that data persists across registry instances."""
        redis = MockRedis()

        now = datetime.now(UTC)

        # Create first instance and set data
        registry1 = RedisActiveWorkflowRunRegistry(redis_client=redis)
        await registry1.set_active_run(
            work_item_id="wi-123",
            run_id="run-456",
            stage_name="review",
            project_id="proj-1",
            board_id="board-1",
            started_at=now.isoformat(),
        )

        # Create second instance and retrieve same data
        registry2 = RedisActiveWorkflowRunRegistry(redis_client=redis)
        result = await registry2.get_active_run("wi-123")

        assert result is not None
        assert result.started_at == now.isoformat()

    async def test_invalid_run_info_returns_none(self):
        """Test that corrupted JSON returns None gracefully."""
        redis = MockRedis()
        registry = RedisActiveWorkflowRunRegistry(redis_client=redis)

        # Store invalid JSON
        await redis.set("codetoreum:workflow:run:wi-123", '{"invalid": json}')

        result = await registry.get_active_run("wi-123")

        assert result is None

    async def test_missing_started_at_field_returns_none(self):
        """Test that missing started_at field results in None."""
        import json

        redis = MockRedis()
        registry = RedisActiveWorkflowRunRegistry(redis_client=redis)

        # Store JSON missing started_at field
        data = {
            "work_item_id": "wi-123",
            "run_id": "run-456",
            "stage_name": "design",
            "project_id": "proj-1",
            "board_id": "board-1",
            # Missing started_at
        }
        await redis.set("codetoreum:workflow:run:wi-123", json.dumps(data))

        result = await registry.get_active_run("wi-123")

        # Should return None due to missing required field
        assert result is None

    async def test_clear_run(self):
        """Test clearing an active run from Redis."""
        redis = MockRedis()
        registry = RedisActiveWorkflowRunRegistry(redis_client=redis)

        now = datetime.now(UTC)
        await registry.set_active_run(
            work_item_id="wi-123",
            run_id="run-456",
            stage_name="coding",
            project_id="proj-1",
            board_id="board-1",
            started_at=now.isoformat(),
        )

        await registry.clear_run("wi-123")

        result = await registry.get_active_run("wi-123")
        assert result is None


@pytest.mark.asyncio
class TestActiveRunInfoValidation:
    """Tests for ActiveRunInfo validation."""

    def test_active_run_info_requires_started_at(self):
        """Test that ActiveRunInfo requires started_at field."""
        with pytest.raises(ValueError, match="started_at must be non-empty"):
            ActiveRunInfo(
                work_item_id="wi-123",
                run_id="run-456",
                stage_name="design",
                project_id="proj-1",
                board_id="board-1",
                started_at="",
            )

    def test_active_run_info_valid_construction(self):
        """Test valid ActiveRunInfo construction."""
        now = datetime.now(UTC)
        info = ActiveRunInfo(
            work_item_id="wi-123",
            run_id="run-456",
            stage_name="design",
            project_id="proj-1",
            board_id="board-1",
            started_at=now.isoformat(),
        )

        assert info.work_item_id == "wi-123"
        assert info.started_at == now.isoformat()

    def test_active_run_info_frozen(self):
        """Test that ActiveRunInfo is immutable."""
        now = datetime.now(UTC)
        info = ActiveRunInfo(
            work_item_id="wi-123",
            run_id="run-456",
            stage_name="design",
            project_id="proj-1",
            board_id="board-1",
            started_at=now.isoformat(),
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            info.stage_name = "review"
