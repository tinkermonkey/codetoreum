"""Simulation tests demonstrating mock adapter workflows.

These tests show end-to-end scenarios using mock adapters to test
orchestrator behavior without external service dependencies.
"""

import pytest

from codetoreum.adapters.secondary.configurable_identity_service import (
    ConfigurableIdentityService,
)
from codetoreum.adapters.secondary.in_memory_queue_lock_service import (
    InMemoryLockService,
)
from codetoreum.adapters.secondary.mock_code_review_adapter import MockCodeReviewAdapter
from codetoreum.adapters.testing import MockDiscussionAdapter
from codetoreum.adapters.testing.mock_board_adapter import MockBoardAdapter
from codetoreum.domain.events.adapter_events import CodetoreumEvent
from codetoreum.domain.events.board_events import WorkItemColumnChangedEvent
from codetoreum.domain.events.discussion_events import CommentNeedsResponseEvent
from codetoreum.domain.events.review_events import ReviewStatusChangedEvent
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.output.board_service import MovedByType
from codetoreum.ports.output.discussion_adapter import DiscussionMonitoringConfig


class TestBoardWorkflow:
    """Simulation tests for board workflow scenarios."""

    @pytest.fixture
    def board_adapter(self):
        """Create and configure a board adapter."""
        adapter = MockBoardAdapter()
        adapter.current_project = "demo-project"
        adapter.current_board = "main-board"
        adapter.create_board(
            "demo-project",
            "main-board",
            "Main Board",
            ["Backlog", "Ready", "In Progress", "In Review", "Done"],
        )
        return adapter

    async def test_work_item_progression(self, board_adapter):
        """Simulate work item moving through workflow stages.

        Demonstrates: tracking work item position and emitting events
        as it moves through the development workflow.
        """
        # Setup: Track all events
        events: list[WorkItemColumnChangedEvent] = []
        board_adapter.on("workitem.column_changed", events.append)

        # Add work item to backlog
        board_adapter.add_item_to_column("main-board", "Backlog", "PROJ-42")

        # Simulate progression through workflow
        transitions = [
            ("Backlog", "Ready"),
            ("Ready", "In Progress"),
            ("In Progress", "In Review"),
            ("In Review", "Done"),
        ]

        for from_col, to_col in transitions:
            await board_adapter.move_item_to_column("PROJ-42", to_col, MovedByType.HUMAN)

        # Verify events
        assert len(events) == 4
        assert events[0].from_column == "Backlog"
        assert events[0].to_column == "Ready"
        assert events[-1].from_column == "In Review"
        assert events[-1].to_column == "Done"

        # All events should have mock source
        for event in events:
            assert event.source == "mock"

    async def test_parallel_work_items(self, board_adapter):
        """Simulate multiple work items moving through workflow.

        Demonstrates: tracking multiple concurrent work items and ensuring
        events are properly associated with their items.
        """
        events: list[WorkItemColumnChangedEvent] = []
        board_adapter.on("workitem.column_changed", events.append)

        # Create multiple work items
        for i in range(3):
            board_adapter.add_item_to_column("main-board", "Backlog", f"PROJ-{i}")

        # Move them independently
        await board_adapter.move_item_to_column("PROJ-0", "In Progress", MovedByType.HUMAN)
        await board_adapter.move_item_to_column("PROJ-1", "Ready", MovedByType.HUMAN)
        await board_adapter.move_item_to_column("PROJ-2", "In Review", MovedByType.HUMAN)

        assert len(events) == 3
        assert {e.work_item_id for e in events} == {"PROJ-0", "PROJ-1", "PROJ-2"}
        assert events[0].to_column == "In Progress"
        assert events[1].to_column == "Ready"
        assert events[2].to_column == "In Review"


class TestDiscussionWorkflow:
    """Simulation tests for discussion/comment workflows."""

    @pytest.fixture
    def discussion_adapter(self):
        """Create and configure discussion adapter."""
        identity_service = ConfigurableIdentityService()
        identity_service.set_bot_username("codetoreum-bot")

        # Configure bot detection
        import re

        from codetoreum.ports.output.identity_service import BotIdentityConfig

        config = BotIdentityConfig(bot_usernames=["dependabot"], bot_patterns=[re.compile("^bot-.*")])
        identity_service.configure(config)

        return MockDiscussionAdapter(identity_service)

    async def test_human_feedback_triggers_response(self, discussion_adapter):
        """Simulate human commenting and system responding.

        Demonstrates: detecting human comments, filtering bot comments,
        and emitting events only for human feedback that needs responses.
        """
        # Setup monitoring for item
        config = DiscussionMonitoringConfig(
            project_id="demo-project",
        )
        discussion_adapter.start_monitoring("PROJ-100", config)

        # Track needs_response events
        needs_response_events: list[CommentNeedsResponseEvent] = []
        discussion_adapter.on("comment.needs_response", needs_response_events.append)

        # Simulate comments from different users
        discussion_adapter.simulate_comment("PROJ-100", "alice", "This needs unit tests")
        discussion_adapter.simulate_comment("PROJ-100", "dependabot", "Updated dependencies")
        discussion_adapter.simulate_comment("PROJ-100", "bob", "Please add error handling")

        # Only human comments should trigger needs_response
        assert len(needs_response_events) == 2
        assert needs_response_events[0].comment is not None
        assert needs_response_events[0].comment.author == "alice"
        assert needs_response_events[1].comment is not None
        assert needs_response_events[1].comment.author == "bob"

        # Verify bot comment was not included
        thread = await discussion_adapter.get_thread("PROJ-100")
        assert len(thread.comments) == 3
        authors = [c.author for c in thread.comments]
        assert "alice" in authors
        assert "bob" in authors
        assert "dependabot" in authors

    async def test_threaded_discussion(self, discussion_adapter):
        """Simulate threaded comment replies.

        Demonstrates: handling nested discussion threads and tracking
        parent-child comment relationships.
        """
        config = DiscussionMonitoringConfig(
            project_id="demo-project",
        )
        discussion_adapter.start_monitoring("PROJ-200", config)

        # Post initial comment
        initial_comment = await discussion_adapter.add_comment(
            "PROJ-200", "Ready for review, please test before merging"
        )

        # Simulate human reply to bot comment
        discussion_adapter.simulate_comment(
            "PROJ-200", "reviewer", "Testing now, will report results", parent_id=initial_comment.id
        )

        # Get full thread
        thread = await discussion_adapter.get_thread("PROJ-200")
        assert len(thread.comments) == 2
        assert thread.comments[1].parent_id == initial_comment.id


class TestCodeReviewWorkflow:
    """Simulation tests for code review workflows."""

    @pytest.fixture
    def review_adapter(self):
        """Create and configure code review adapter."""
        adapter = MockCodeReviewAdapter()
        adapter.current_project = "demo-project"
        return adapter

    async def test_review_approval_flow(self, review_adapter):
        """Simulate code review going from open to approved.

        Demonstrates: tracking review status changes and emitting
        events for workflow progression.
        """
        # Create review
        review_adapter.add_review("PR-789", "PROJ-50", status="open")

        # Track status changes
        status_events: list[ReviewStatusChangedEvent] = []
        review_adapter.on("review.status_changed", status_events.append)

        # Simulate review progression
        review_adapter.simulate_changes_requested("PR-789", "reviewer-alice")
        review_adapter.simulate_approval("PR-789", "reviewer-bob")

        # Verify progression
        assert len(status_events) == 2
        assert status_events[0].new_status == "changes_requested"
        assert status_events[0].reviewer == "reviewer-alice"
        assert status_events[1].new_status == "approved"
        assert status_events[1].reviewer == "reviewer-bob"

        # All events should have mock source
        for event in status_events:
            assert event.source == "mock"
            assert event.project_id == "demo-project"

    async def test_multiple_reviews_independent_state(self, review_adapter):
        """Simulate multiple concurrent reviews with independent states.

        Demonstrates: managing multiple code reviews in parallel without
        state interference.
        """
        # Create multiple reviews
        review_adapter.add_review("PR-100", "PROJ-100")
        review_adapter.add_review("PR-101", "PROJ-101")
        review_adapter.add_review("PR-102", "PROJ-102")

        status_events: list[ReviewStatusChangedEvent] = []
        review_adapter.on("review.status_changed", status_events.append)

        # Progress reviews differently
        review_adapter.simulate_approval("PR-100", "reviewer-1")
        review_adapter.simulate_changes_requested("PR-101", "reviewer-2")
        review_adapter.simulate_approval("PR-102", "reviewer-3")

        # Verify independent states
        assert len(status_events) == 3
        assert await review_adapter.get_review_status("PR-100") == "approved"
        assert await review_adapter.get_review_status("PR-101") == "changes_requested"
        assert await review_adapter.get_review_status("PR-102") == "approved"


class TestCombinedWorkflow:
    """Integration tests combining multiple adapters."""

    async def test_end_to_end_work_item_lifecycle(self):
        """Simulate complete work item lifecycle from creation to done.

        Demonstrates: coordinating board moves, discussions, reviews,
        and locks through a complete workflow.
        """
        # Setup adapters
        board = MockBoardAdapter()
        board.current_project = "ACME"
        board.current_board = "main"
        board.create_board("ACME", "main", "Main Board", ["Backlog", "Dev", "Review", "Done"])

        identity = ConfigurableIdentityService()
        discussion = MockDiscussionAdapter(identity)

        review = MockCodeReviewAdapter()
        review.current_project = "ACME"

        lock = InMemoryLockService(event_bus=EventBus())

        # Collect all events
        events: list[CodetoreumEvent] = []
        board.on("workitem.column_changed", events.append)
        discussion.on("comment.needs_response", events.append)
        review.on("review.status_changed", events.append)

        # Workflow:
        # 1. Item in Backlog
        board.add_item_to_column("main", "Backlog", "ACME-1")

        # 2. Move to Dev, acquire lock
        await board.move_item_to_column("ACME-1", "Dev", MovedByType.ORCHESTRATOR)
        result = await lock.try_acquire_lock("ACME", "main", "ACME-1", board_position=0)
        assert result.status.value == "acquired"

        # 3. Post initial discussion
        config = DiscussionMonitoringConfig(
            project_id="ACME",
        )
        discussion.start_monitoring("ACME-1", config)
        await discussion.add_comment("ACME-1", "Working on this now")

        # 4. Create code review
        review.add_review("PR-1", "ACME-1")

        # 5. Move to Review
        await board.move_item_to_column("ACME-1", "Review", MovedByType.ORCHESTRATOR)

        # 6. Simulate review feedback
        discussion.simulate_comment("ACME-1", "reviewer", "Looks good, needs tests")

        # 7. Request changes in review
        review.simulate_changes_requested("PR-1", "reviewer")

        # 8. Approve review
        review.simulate_approval("PR-1", "reviewer")

        # 9. Move to Done
        await board.move_item_to_column("ACME-1", "Done", MovedByType.ORCHESTRATOR)

        # 10. Release lock
        await lock.release_lock("ACME", "main", "ACME-1")

        # Verify comprehensive event trail
        assert len(events) > 0
        assert any(isinstance(e, WorkItemColumnChangedEvent) for e in events)
        assert any(isinstance(e, CommentNeedsResponseEvent) for e in events)
        assert any(isinstance(e, ReviewStatusChangedEvent) for e in events)

        # All events should have mock source for simulation
        for event in events:
            if hasattr(event, "source"):
                assert event.source == "mock"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
