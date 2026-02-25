"""Unit tests for mock adapters and event simulation.

Tests verify that:
1. Mock adapters implement port interfaces correctly
2. Event emission works as expected
3. Test helper methods properly simulate state changes
4. Events have correct source='mock' and ISO timestamps
"""

import re
from datetime import datetime
from typing import Any

import pytest

from codetoreum.adapters.secondary.configurable_identity_service import (
    ConfigurableIdentityService,
)
from codetoreum.adapters.secondary.in_memory_pipeline_lock_service import (
    InMemoryPipelineLockService,
)
from codetoreum.adapters.secondary.mock_code_review_adapter import MockCodeReviewAdapter
from codetoreum.adapters.secondary.mock_discussion_adapter import MockDiscussionAdapter
from codetoreum.adapters.testing.mock_board_adapter import MockBoardAdapter
from codetoreum.domain.events.board_events import (
    BoardReconciledEvent,
    WorkItemColumnChangedEvent,
)
from codetoreum.domain.events.discussion_events import (
    CommentNeedsResponseEvent,
)
from codetoreum.domain.events.lock_events import LockAcquiredEvent
from codetoreum.domain.events.review_events import ReviewStatusChangedEvent
from codetoreum.ports.output.board_service import BoardConfig
from codetoreum.ports.output.discussion_adapter import DiscussionMonitoringConfig
from codetoreum.ports.output.monitoring import MonitoringConfig


class TestMockBoardAdapter:
    """Tests for MockBoardAdapter event simulation."""

    @pytest.fixture
    def adapter(self):
        """Create a mock board adapter for testing."""
        adapter = MockBoardAdapter()
        adapter.current_project = "proj-1"
        adapter.current_board = "board-1"
        adapter.create_board("proj-1", "board-1", "Test Board", ["Backlog", "In Progress", "Done"])
        return adapter

    async def test_get_board(self, adapter):
        """Test retrieving board configuration."""
        board = await adapter.get_board("proj-1", "board-1")
        assert board.id == "board-1"
        assert board.project_id == "proj-1"
        assert len(board.columns) == 3
        assert board.columns[0].name == "Backlog"
        assert board.columns[1].name == "In Progress"
        assert board.columns[2].name == "Done"

    async def test_get_board_not_found(self, adapter):
        """Test retrieving non-existent board raises error."""
        with pytest.raises(ValueError, match="Board not found"):
            await adapter.get_board("proj-1", "board-999")

    async def test_add_work_item(self, adapter):
        """Test adding work item to board."""
        adapter.add_item_to_column("board-1", "Backlog", "item-1")
        item_pos = await adapter.get_item_position("item-1")
        assert item_pos.column_name == "Backlog"
        assert item_pos.position == 0

    async def test_simulate_column_change_emits_event(self, adapter):
        """Test move_item_to_column emits correct event."""
        from codetoreum.ports.output.board_service import MovedByType

        adapter.add_item_to_column("board-1", "Backlog", "item-1")
        events: list[Any] = []
        adapter.on("workitem.column_changed", events.append)

        await adapter.move_item_to_column("item-1", "In Progress", MovedByType.HUMAN)

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, WorkItemColumnChangedEvent)
        assert event.work_item_id == "item-1"
        assert event.from_column == "Backlog"
        assert event.to_column == "In Progress"
        assert event.moved_by == "human"
        assert event.source == "mock"

    async def test_simulate_column_change_by_orchestrator(self, adapter):
        """Test move_item_to_column with orchestrator as mover."""
        from codetoreum.ports.output.board_service import MovedByType

        adapter.add_item_to_column("board-1", "Backlog", "item-1")
        events: list[Any] = []
        adapter.on("workitem.column_changed", events.append)

        await adapter.move_item_to_column("item-1", "In Progress", MovedByType.ORCHESTRATOR)

        assert len(events) == 1
        assert events[0].moved_by == "orchestrator"

    async def test_move_item_to_column_emits_event(self, adapter):
        """Test move_item_to_column emits event."""
        from codetoreum.ports.output.board_service import MovedByType

        adapter.add_item_to_column("board-1", "Backlog", "item-1")
        events: list[Any] = []
        adapter.on("workitem.column_changed", events.append)

        await adapter.move_item_to_column("item-1", "In Progress", MovedByType.ORCHESTRATOR)

        assert len(events) == 1
        assert events[0].to_column == "In Progress"

    async def test_reconcile_board_emits_event(self, adapter):
        """Test reconcile_board emits event."""
        events: list[Any] = []
        adapter.on("board.reconciled", events.append)

        config = BoardConfig(
            board_id="board-1",
            expected_columns=["Backlog", "In Progress", "Review", "Done"],
            auto_create_missing=True,
        )
        result = await adapter.reconcile_board("board-1", config)

        assert len(events) == 1
        assert isinstance(events[0], BoardReconciledEvent)
        assert events[0].source == "mock"
        assert "Review" in result.columns_added

    async def test_event_timestamp_is_iso_format(self, adapter):
        """Test that emitted events have valid ISO 8601 timestamps."""
        from codetoreum.ports.output.board_service import MovedByType

        adapter.add_item_to_column("board-1", "Backlog", "item-1")
        events: list[Any] = []
        adapter.on("workitem.column_changed", events.append)

        await adapter.move_item_to_column("item-1", "Done", MovedByType.HUMAN)

        event = events[0]
        # Should not raise ValueError
        datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))

    async def test_start_monitoring(self, adapter):
        """Test monitoring lifecycle."""
        config = MonitoringConfig(project_id="proj-1")
        await adapter.start_monitoring("proj-1", config)

        status = await adapter.get_monitoring_status("proj-1")
        assert status.state.value == "active"
        assert status.project_id == "proj-1"

    async def test_stop_monitoring(self, adapter):
        """Test stopping monitoring."""
        config = MonitoringConfig(project_id="proj-1")
        await adapter.start_monitoring("proj-1", config)
        await adapter.stop_monitoring("proj-1")

        status = await adapter.get_monitoring_status("proj-1")
        assert status.state.value == "stopped"


class TestMockDiscussionAdapter:
    """Tests for MockDiscussionAdapter event simulation."""

    @pytest.fixture
    def identity_service(self):
        """Create a configurable identity service."""
        service = ConfigurableIdentityService()
        service.set_bot_username("codetoreum-bot")
        return service

    @pytest.fixture
    def adapter(self, identity_service):
        """Create a mock discussion adapter."""
        return MockDiscussionAdapter(identity_service)

    async def test_add_comment_by_bot(self, adapter):
        """Test adding comment by bot."""
        comment = await adapter.add_comment("item-1", "This looks good")
        assert comment.author == "codetoreum-bot"
        assert comment.body == "This looks good"
        assert comment.is_bot is True

    async def test_simulate_comment_by_human_emits_event(self, adapter):
        """Test simulate_comment by human emits needs_response event."""
        config = DiscussionMonitoringConfig(
            project_id="proj-1",
        )
        adapter.start_monitoring("item-1", config)

        events: list[Any] = []
        adapter.on("comment.needs_response", events.append)

        adapter.simulate_comment("item-1", "alice", "Please review this")

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, CommentNeedsResponseEvent)
        assert event.comment is not None
        assert event.comment.author == "alice"
        assert event.comment.body == "Please review this"
        assert event.source == "mock"

    async def test_simulate_comment_by_bot_no_event(self, adapter):
        """Test simulate_comment by bot doesn't emit needs_response event."""
        config = DiscussionMonitoringConfig(
            project_id="proj-1",
        )
        adapter.start_monitoring("item-1", config)

        events: list[Any] = []
        adapter.on("comment.needs_response", events.append)

        # Register bot username
        adapter._identity_service._bot_usernames.append("dependabot")
        adapter.simulate_comment("item-1", "dependabot", "Updated dependencies")

        assert len(events) == 0

    async def test_get_thread(self, adapter):
        """Test retrieving discussion thread."""
        adapter._threads["item-1"] = []
        adapter.simulate_comment("item-1", "alice", "First comment")
        adapter.simulate_comment("item-1", "bob", "Second comment")

        thread = await adapter.get_thread("item-1")
        assert thread.work_item_id == "item-1"
        assert len(thread.comments) == 2
        assert thread.comments[0].author == "alice"
        assert thread.comments[1].author == "bob"

    async def test_start_monitoring(self, adapter):
        """Test starting work-item-specific monitoring."""
        config = DiscussionMonitoringConfig(
            project_id="proj-1",
        )
        adapter.start_monitoring("item-1", config)
        assert "item-1" in adapter._monitoring

    async def test_stop_monitoring(self, adapter):
        """Test stopping monitoring."""
        config = DiscussionMonitoringConfig(
            project_id="proj-1",
        )
        adapter.start_monitoring("item-1", config)
        adapter.stop_monitoring("item-1")
        assert "item-1" not in adapter._monitoring

    # Test Helper Methods

    async def test_simulate_bot_comment(self, adapter):
        """Test simulate_bot_comment helper."""
        comment = adapter.simulate_bot_comment("item-1", "This looks good")
        assert comment.author == "codetoreum-bot"
        assert comment.body == "This looks good"
        assert comment.is_bot is True
        assert adapter.get_comment_count("item-1") == 1

    async def test_simulate_bot_comment_emits_event_when_monitored(self, adapter):
        """Test simulate_bot_comment emits event when monitoring."""
        config = DiscussionMonitoringConfig(
            project_id="proj-1",
        )
        adapter.start_monitoring("item-1", config)

        events: list[Any] = []
        adapter.on("comment.posted", events.append)

        comment = adapter.simulate_bot_comment("item-1", "Processing...")
        assert len(events) == 1
        assert events[0].comment is not None
        assert events[0].comment.id == comment.id
        assert events[0].source == "mock"

    async def test_create_thread(self, adapter):
        """Test create_thread helper."""
        initial = adapter.create_thread("item-1", "Please review this")
        assert initial.author == "requester"
        assert initial.body == "Please review this"
        assert initial.parent_id is None
        assert adapter.thread_exists("item-1")

    async def test_create_thread_with_custom_author(self, adapter):
        """Test create_thread with custom author."""
        initial = adapter.create_thread("item-1", "Comment", author="alice")
        assert initial.author == "alice"
        assert adapter.get_comment_count("item-1") == 1

    async def test_get_comments_by_author(self, adapter):
        """Test get_comments_by_author helper."""
        adapter.create_thread("item-1", "First", author="alice")
        adapter.simulate_comment("item-1", "bob", "Second")
        adapter.simulate_comment("item-1", "alice", "Third")

        alice_comments = adapter.get_comments_by_author("item-1", "alice")
        bob_comments = adapter.get_comments_by_author("item-1", "bob")

        assert len(alice_comments) == 2
        assert len(bob_comments) == 1
        assert all(c.author == "alice" for c in alice_comments)

    async def test_get_comments_by_author_nonexistent_item(self, adapter):
        """Test get_comments_by_author returns empty list for nonexistent item."""
        comments = adapter.get_comments_by_author("item-999", "alice")
        assert comments == []

    async def test_get_comment_count(self, adapter):
        """Test get_comment_count helper."""
        assert adapter.get_comment_count("item-1") == 0

        adapter.create_thread("item-1", "First")
        assert adapter.get_comment_count("item-1") == 1

        adapter.simulate_comment("item-1", "bob", "Second")
        assert adapter.get_comment_count("item-1") == 2

    async def test_thread_exists(self, adapter):
        """Test thread_exists helper."""
        assert not adapter.thread_exists("item-1")

        adapter.create_thread("item-1", "First")
        assert adapter.thread_exists("item-1")

    async def test_is_monitoring(self, adapter):
        """Test is_monitoring helper."""
        assert not adapter.is_monitoring("item-1")

        config = DiscussionMonitoringConfig(
            project_id="proj-1",
        )
        adapter.start_monitoring("item-1", config)
        assert adapter.is_monitoring("item-1")

    async def test_clear_threads(self, adapter):
        """Test clear_threads helper."""
        adapter.create_thread("item-1", "First")
        adapter.create_thread("item-2", "Second")

        assert adapter.get_comment_count("item-1") == 1
        assert adapter.get_comment_count("item-2") == 1

        adapter.clear_threads()

        assert adapter.get_comment_count("item-1") == 0
        assert adapter.get_comment_count("item-2") == 0
        assert not adapter.thread_exists("item-1")

    async def test_clear_monitoring(self, adapter):
        """Test clear_monitoring helper."""
        config = DiscussionMonitoringConfig(
            project_id="proj-1",
        )
        adapter.start_monitoring("item-1", config)
        adapter.start_monitoring("item-2", config)

        assert adapter.is_monitoring("item-1")
        assert adapter.is_monitoring("item-2")

        adapter.clear_monitoring()

        assert not adapter.is_monitoring("item-1")
        assert not adapter.is_monitoring("item-2")

    async def test_get_thread_info(self, adapter):
        """Test get_thread_info helper."""
        # Non-existent thread
        info = adapter.get_thread_info("item-1")
        assert info["exists"] is False
        assert info["comment_count"] == 0
        assert info["is_monitored"] is False
        assert info["authors"] == []

        # Create thread with multiple comments
        adapter.create_thread("item-1", "First", author="alice")
        adapter.simulate_comment("item-1", "bob", "Second")
        adapter.simulate_comment("item-1", "alice", "Third")

        info = adapter.get_thread_info("item-1")
        assert info["exists"] is True
        assert info["comment_count"] == 3
        assert info["is_monitored"] is False
        assert set(info["authors"]) == {"alice", "bob"}

    async def test_get_thread_info_with_monitoring(self, adapter):
        """Test get_thread_info shows monitoring state."""
        config = DiscussionMonitoringConfig(
            project_id="proj-1",
        )
        adapter.create_thread("item-1", "Initial")
        adapter.start_monitoring("item-1", config)

        info = adapter.get_thread_info("item-1")
        assert info["is_monitored"] is True

    async def test_helper_methods_integration(self, adapter):
        """Test multiple helper methods working together."""
        # Setup
        adapter.create_thread("item-1", "Please review", author="requester")

        config = DiscussionMonitoringConfig(
            project_id="proj-1",
        )
        adapter.start_monitoring("item-1", config)

        # Add various comments
        adapter.simulate_comment("item-1", "reviewer", "I reviewed it")
        adapter.simulate_bot_comment("item-1", "Thanks for the review")

        # Verify with helpers
        info = adapter.get_thread_info("item-1")
        assert info["comment_count"] == 3
        assert info["is_monitored"] is True

        reviewer_comments = adapter.get_comments_by_author("item-1", "reviewer")
        assert len(reviewer_comments) == 1

        # Cleanup
        adapter.clear_threads()
        assert adapter.get_comment_count("item-1") == 0

    # Required Test Helpers (FR-8.3, FR-9.1)

    async def test_simulate_column_change_emits_event(self, adapter):
        """Test simulate_column_change emits WorkItemColumnChangedEvent."""
        config = DiscussionMonitoringConfig(
            project_id="proj-1",
        )
        adapter.start_monitoring("item-1", config)

        events: list[Any] = []
        adapter.on("workitem.column_changed", events.append)

        adapter.simulate_column_change("item-1", "Backlog", "In Review")

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, WorkItemColumnChangedEvent)
        assert event.work_item_id == "item-1"
        assert event.project_id == "proj-1"
        assert event.from_column == "Backlog"
        assert event.to_column == "In Review"
        assert event.moved_by == "unknown"
        assert event.source == "mock"

    async def test_simulate_column_change_not_monitoring_raises_error(self, adapter):
        """Test simulate_column_change raises error if not monitoring."""
        with pytest.raises(ValueError, match="Not monitoring work item"):
            adapter.simulate_column_change("item-1", "Backlog", "In Review")

    async def test_get_processed_comment_ids_empty(self, adapter):
        """Test get_processed_comment_ids returns empty set initially."""
        processed = adapter.get_processed_comment_ids("item-1")
        assert processed == set()

    async def test_get_processed_comment_ids_tracks_human_comments(self, adapter):
        """Test get_processed_comment_ids tracks processed human comments."""
        config = DiscussionMonitoringConfig(
            project_id="proj-1",
        )
        adapter.start_monitoring("item-1", config)

        # Simulate human comments
        adapter.simulate_comment("item-1", "alice", "First comment")
        adapter.simulate_comment("item-1", "bob", "Second comment")

        # Get processed comment IDs
        processed = adapter.get_processed_comment_ids("item-1")

        assert len(processed) == 2

    async def test_get_processed_comment_ids_excludes_bot_comments(self, adapter):
        """Test get_processed_comment_ids doesn't track bot comments."""
        config = DiscussionMonitoringConfig(
            project_id="proj-1",
        )
        adapter.start_monitoring("item-1", config)

        # Simulate human comment
        adapter.simulate_comment("item-1", "alice", "Review this")

        # Add bot comment (doesn't emit event, not tracked as processed)
        adapter.simulate_bot_comment("item-1", "Acknowledged")

        processed = adapter.get_processed_comment_ids("item-1")

        # Only human comment tracked
        assert len(processed) == 1

    async def test_get_processed_comment_ids_returns_copy(self, adapter):
        """Test get_processed_comment_ids returns a copy (not reference)."""
        config = DiscussionMonitoringConfig(
            project_id="proj-1",
        )
        adapter.start_monitoring("item-1", config)
        adapter.simulate_comment("item-1", "alice", "Comment")

        processed1 = adapter.get_processed_comment_ids("item-1")
        processed2 = adapter.get_processed_comment_ids("item-1")

        # Should be equal but not the same object
        assert processed1 == processed2
        assert processed1 is not processed2

    async def test_reset_monitoring_state_clears_monitoring(self, adapter):
        """Test reset_monitoring_state clears monitoring config."""
        config = DiscussionMonitoringConfig(
            project_id="proj-1",
        )
        adapter.start_monitoring("item-1", config)
        assert adapter.is_monitoring("item-1")

        adapter.reset_monitoring_state("item-1")

        assert not adapter.is_monitoring("item-1")

    async def test_reset_monitoring_state_preserves_thread(self, adapter):
        """Test reset_monitoring_state preserves comment queue."""
        config = DiscussionMonitoringConfig(
            project_id="proj-1",
        )
        adapter.start_monitoring("item-1", config)
        adapter.create_thread("item-1", "Initial comment")

        assert adapter.get_comment_count("item-1") == 1

        adapter.reset_monitoring_state("item-1")

        # Thread still exists with comments
        assert adapter.thread_exists("item-1")
        assert adapter.get_comment_count("item-1") == 1

    async def test_reset_monitoring_state_not_monitoring_raises_error(self, adapter):
        """Test reset_monitoring_state raises error if not monitoring."""
        with pytest.raises(ValueError, match="Not monitoring work item"):
            adapter.reset_monitoring_state("item-1")

    async def test_reset_monitoring_state_vs_clear_monitoring(self, adapter):
        """Test reset_monitoring_state only clears one item vs clear_monitoring all."""
        config = DiscussionMonitoringConfig(
            project_id="proj-1",
        )
        adapter.start_monitoring("item-1", config)
        adapter.start_monitoring("item-2", config)

        adapter.reset_monitoring_state("item-1")

        # Only item-1 cleared
        assert not adapter.is_monitoring("item-1")
        assert adapter.is_monitoring("item-2")


class TestMockCodeReviewAdapter:
    """Tests for MockCodeReviewAdapter event simulation."""

    @pytest.fixture
    def adapter(self):
        """Create a mock code review adapter."""
        adapter = MockCodeReviewAdapter()
        adapter.current_project = "proj-1"
        adapter.add_review("pr-1", "item-1", status="open")
        return adapter

    async def test_add_review(self, adapter):
        """Test adding a code review."""
        assert "pr-1" in adapter._reviews
        review = await adapter.get_review_for_work_item("item-1")
        assert review is not None
        assert review.id == "pr-1"

    async def test_get_review_status(self, adapter):
        """Test querying review status."""
        status = await adapter.get_review_status("pr-1")
        assert status == "open"

    async def test_simulate_approval_emits_event(self, adapter):
        """Test simulate_approval emits status change event."""
        events: list[Any] = []
        adapter.on("review.status_changed", events.append)

        adapter.simulate_approval("pr-1", "reviewer-1")

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, ReviewStatusChangedEvent)
        assert event.new_status == "approved"
        assert event.previous_status == "open"
        assert event.reviewer == "reviewer-1"
        assert event.source == "mock"

    async def test_simulate_changes_requested_emits_event(self, adapter):
        """Test simulate_changes_requested emits status change event."""
        events: list[Any] = []
        adapter.on("review.status_changed", events.append)

        adapter.simulate_changes_requested("pr-1", "reviewer-1")

        assert len(events) == 1
        assert events[0].new_status == "changes_requested"

    async def test_approve_method_emits_event(self, adapter):
        """Test approve method emits event."""
        events: list[Any] = []
        adapter.on("review.status_changed", events.append)

        await adapter.approve("pr-1")

        assert len(events) == 1
        assert events[0].new_status == "approved"

    async def test_monitoring_lifecycle(self, adapter):
        """Test monitoring lifecycle."""
        config = MonitoringConfig(project_id="proj-1")
        await adapter.start_monitoring("proj-1", config)

        status = await adapter.get_monitoring_status("proj-1")
        assert status.state.value == "active"

        await adapter.stop_monitoring("proj-1")
        status = await adapter.get_monitoring_status("proj-1")
        assert status.state.value == "stopped"


class TestInMemoryPipelineLockService:
    """Tests for InMemoryPipelineLockService."""

    @pytest.fixture
    def service(self):
        """Create a pipeline lock service."""
        return InMemoryPipelineLockService()

    async def test_try_acquire_lock_success(self, service):
        """Test successful lock acquisition."""
        events: list[Any] = []
        service.on("lock.acquired", events.append)

        success, reason = await service.try_acquire_lock("proj-1", "board-1", "item-1")

        assert success is True
        assert reason == "lock acquired"
        assert len(events) == 1

    async def test_try_acquire_lock_contention(self, service):
        """Test lock acquisition when already locked."""
        await service.try_acquire_lock("proj-1", "board-1", "item-1")

        success, reason = await service.try_acquire_lock("proj-1", "board-1", "item-2")

        assert success is False
        assert "already held by" in reason

    async def test_lock_acquired_event_emitted(self, service):
        """Test that lock acquired events are correct."""
        events: list[Any] = []
        service.on("lock.acquired", events.append)

        await service.try_acquire_lock("proj-1", "board-1", "item-1")

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, LockAcquiredEvent)
        assert event.work_item_id == "item-1"
        assert event.acquisition_method == "normal"
        assert event.source == "mock"

    async def test_release_lock_emits_event(self, service):
        """Test lock release emits event."""
        await service.try_acquire_lock("proj-1", "board-1", "item-1")

        events: list[Any] = []
        service.on("lock.released", events.append)

        success = await service.release_lock("proj-1", "board-1", "item-1")

        assert success is True
        assert len(events) == 1
        assert events[0].reason == "completed"

    async def test_release_lock_wrong_holder(self, service):
        """Test releasing lock held by different item."""
        await service.try_acquire_lock("proj-1", "board-1", "item-1")

        success = await service.release_lock("proj-1", "board-1", "item-2")

        assert success is False

    async def test_get_all_locks(self, service):
        """Test retrieving all active locks."""
        await service.try_acquire_lock("proj-1", "board-1", "item-1")
        await service.try_acquire_lock("proj-1", "board-2", "item-2")

        locks = await service.get_all_locks()

        assert len(locks) == 2
        assert any(lock.work_item_id == "item-1" for lock in locks)
        assert any(lock.work_item_id == "item-2" for lock in locks)

    async def test_simulate_lock_acquired(self, service):
        """Test direct lock acquired event simulation."""
        events: list[Any] = []
        service.on("lock.acquired", events.append)

        service.simulate_lock_acquired("proj-1", "board-1", "item-1", "stale_recovery")

        assert len(events) == 1
        assert events[0].acquisition_method == "stale_recovery"

    async def test_simulate_lock_released(self, service):
        """Test direct lock released event simulation."""
        events: list[Any] = []
        service.on("lock.released", events.append)

        service.simulate_lock_released("proj-1", "board-1", "item-1", "timeout", next_in_queue="item-2")

        assert len(events) == 1
        assert events[0].reason == "timeout"
        assert events[0].next_in_queue == "item-2"


class TestConfigurableIdentityService:
    """Tests for ConfigurableIdentityService."""

    @pytest.fixture
    def service(self):
        """Create an identity service."""
        return ConfigurableIdentityService()

    def test_is_bot_user_exact_match(self, service):
        """Test bot detection with exact username match."""
        from codetoreum.ports.output.identity_service import BotIdentityConfig

        config = BotIdentityConfig(bot_usernames=["dependabot", "renovate"], bot_patterns=[])
        service.configure(config)

        assert service.is_bot_user("dependabot") is True
        assert service.is_bot_user("renovate") is True
        assert service.is_bot_user("alice") is False

    def test_is_bot_user_pattern_match(self, service):
        """Test bot detection with regex pattern."""
        from codetoreum.ports.output.identity_service import BotIdentityConfig

        config = BotIdentityConfig(bot_usernames=[], bot_patterns=[re.compile("^bot-.*"), re.compile(".*-bot$")])
        service.configure(config)

        assert service.is_bot_user("bot-ci") is True
        assert service.is_bot_user("codetoreum-bot") is True
        assert service.is_bot_user("alice") is False

    def test_get_human_users(self, service):
        """Test filtering to get only human users."""
        from codetoreum.ports.output.identity_service import BotIdentityConfig

        config = BotIdentityConfig(bot_usernames=["dependabot"], bot_patterns=[re.compile("^bot-.*")])
        service.configure(config)

        humans = service.get_human_users(["alice", "dependabot", "bob", "bot-ci"])

        assert humans == ["alice", "bob"]

    def test_get_bot_username(self, service):
        """Test getting configured bot username."""
        assert service.get_bot_username() == "codetoreum-bot"

    def test_set_bot_username(self, service):
        """Test setting bot username."""
        service.set_bot_username("my-custom-bot")
        assert service.get_bot_username() == "my-custom-bot"

    def test_configure_with_empty_config_raises(self, service):
        """Test that configuring with empty lists raises error."""
        from codetoreum.ports.output.identity_service import BotIdentityConfig

        with pytest.raises(ValueError, match="At least one of"):
            config = BotIdentityConfig(bot_usernames=[], bot_patterns=[])
            service.configure(config)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
