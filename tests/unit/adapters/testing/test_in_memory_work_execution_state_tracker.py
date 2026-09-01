"""Unit tests for InMemoryWorkExecutionStateTracker."""

from __future__ import annotations

import pytest

from codetoreum.adapters.testing.in_memory_work_execution_state_tracker import (
    InMemoryWorkExecutionStateTracker,
)


@pytest.fixture
def tracker():
    return InMemoryWorkExecutionStateTracker()


class TestInMemoryWorkExecutionStateTrackerRoundTrip:
    @pytest.mark.asyncio
    async def test_load_state_after_mark_failed(self, tracker):
        await tracker.mark_execution_failed(
            project="myproject",
            work_item_id="item-123",
            agent="claude",
            reason="Container lost connection",
        )
        state = await tracker.load_state("myproject", "item-123")
        assert state is not None
        assert state["outcome"] == "failed"
        assert state["agent"] == "claude"
        assert state["reason"] == "Container lost connection"

    @pytest.mark.asyncio
    async def test_load_missing_state_returns_none(self, tracker):
        assert await tracker.load_state("myproject", "does-not-exist") is None

    @pytest.mark.asyncio
    async def test_mark_execution_failed_multiple_times_is_idempotent(self, tracker):
        await tracker.mark_execution_failed(
            project="myproject",
            work_item_id="item-123",
            agent="claude",
            reason="First failure",
        )
        await tracker.mark_execution_failed(
            project="myproject",
            work_item_id="item-123",
            agent="claude",
            reason="Second failure",
        )
        state = await tracker.load_state("myproject", "item-123")
        assert state is not None
        assert state["reason"] == "Second failure"


class TestInMemoryWorkExecutionStateTrackerStarted:
    @pytest.mark.asyncio
    async def test_mark_execution_started_stores_in_progress_state(self, tracker):
        await tracker.mark_execution_started(
            project="myproject",
            work_item_id="item-123",
            agent="claude",
        )
        state = await tracker.load_state("myproject", "item-123")
        assert state is not None
        assert state["outcome"] == "in_progress"
        assert state["agent"] == "claude"

    @pytest.mark.asyncio
    async def test_mark_execution_started_overwrites_failed_state(self, tracker):
        await tracker.mark_execution_failed(
            project="myproject",
            work_item_id="item-123",
            agent="claude",
            reason="Previous failure",
        )
        await tracker.mark_execution_started(
            project="myproject",
            work_item_id="item-123",
            agent="claude",
        )
        state = await tracker.load_state("myproject", "item-123")
        assert state is not None
        assert state["outcome"] == "in_progress"
        assert state["agent"] == "claude"
        assert "reason" not in state


class TestInMemoryWorkExecutionStateTrackerMultiProject:
    @pytest.mark.asyncio
    async def test_different_projects_isolated(self, tracker):
        await tracker.mark_execution_failed(
            project="project-a",
            work_item_id="item-1",
            agent="claude",
            reason="Error in A",
        )
        await tracker.mark_execution_failed(
            project="project-b",
            work_item_id="item-1",
            agent="claude",
            reason="Error in B",
        )
        state_a = await tracker.load_state("project-a", "item-1")
        state_b = await tracker.load_state("project-b", "item-1")
        assert state_a["reason"] == "Error in A"
        assert state_b["reason"] == "Error in B"
