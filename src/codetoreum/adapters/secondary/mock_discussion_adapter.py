"""In-memory discussion adapter with event simulation for testing.

This module provides a mock implementation of IDiscussionAdapter that stores
discussion threads and comments in memory, and includes test helper methods
for simulating discussion updates via event emission.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from codetoreum.domain.events.board_events import WorkItemColumnChangedEvent
from codetoreum.domain.events.discussion_events import (
    Comment,
    CommentContext,
    CommentNeedsResponseEvent,
    CommentPostedEvent,
)
from codetoreum.ports.output.discussion_adapter import (
    DiscussionMonitoringConfig,
    DiscussionThread,
    IDiscussionAdapter,
)
from codetoreum.ports.output.identity_service import IIdentityService

from .mock_event_emitter import MockEventEmitter


class MockDiscussionAdapter(MockEventEmitter, IDiscussionAdapter):
    """In-memory discussion adapter with event simulation.

    Provides a mock implementation of IDiscussionAdapter that:
    1. Stores discussion threads and comments in memory
    2. Tracks monitoring state for work items
    3. Emits events when comments are posted
    4. Provides comprehensive test helper methods for setup and verification

    Intended for testing and simulation without external discussion systems
    (GitHub issues, PRs, Jira comments, etc.).

    Test Helper Methods (FR-8.3, FR-9.1):
        - simulate_column_change() - Simulate column changes (emits WorkItemColumnChangedEvent)
        - get_processed_comment_ids() - Get processed comment IDs (duplicate prevention)
        - reset_monitoring_state() - Reset monitoring for restart simulation
        - simulate_comment() - Simulate human comment requiring response
        - simulate_bot_comment() - Simulate bot/system comment
        - create_thread() - Create discussion thread with initial comment
        - get_comments_by_author() - Query comments by author
        - get_comment_count() - Get total comments on item
        - thread_exists() - Check if thread exists
        - is_monitoring() - Check monitoring state
        - clear_threads() - Clear all threads (cleanup)
        - clear_monitoring() - Clear all monitoring state (cleanup)
        - get_thread_info() - Get diagnostic thread info

    Example: Basic Event Simulation
        # Setup
        adapter = MockDiscussionAdapter(identity_service)
        config = DiscussionMonitoringConfig(
            project_id="proj-1",
            column_name="In Review",
            agent_assignment="agent-1"
        )
        adapter.start_monitoring("item-1", config)

        # Simulate human comment
        events = []
        adapter.on("comment.needs_response", events.append)
        adapter.simulate_comment("item-1", "alice", "This needs review")

        # Verify
        assert len(events) == 1
        assert events[0].comment.body == "This needs review"

    Example: Test Setup with Helpers
        # Create discussion thread with multiple comments
        adapter.create_thread("item-1", "Please review this PR", author="requester")
        adapter.simulate_comment("item-1", "reviewer", "Looks good")
        adapter.simulate_bot_comment("item-1", "Approved by orchestrator")

        # Verify with helpers
        assert adapter.get_comment_count("item-1") == 3
        assert len(adapter.get_comments_by_author("item-1", "reviewer")) == 1

        # Check diagnostic info
        info = adapter.get_thread_info("item-1")
        assert info['comment_count'] == 3
        assert set(info['authors']) == {"requester", "reviewer", "codetoreum-bot"}

    Example: Cleanup Between Tests
        # Setup and test
        adapter.create_thread("item-1", "Comment")
        adapter.start_monitoring("item-1", config)
        # ... run test ...

        # Cleanup
        adapter.clear_threads()
        adapter.clear_monitoring()
        assert not adapter.thread_exists("item-1")
        assert not adapter.is_monitoring("item-1")
    """

    def __init__(self, identity_service: IIdentityService) -> None:
        """Initialize the discussion adapter.

        Args:
            identity_service: Service for identifying bot users
        """
        super().__init__()
        self._threads: Dict[str, List[Comment]] = {}  # work_item_id -> comments
        self._monitoring: Dict[str, DiscussionMonitoringConfig] = {}  # work_item_id -> config
        self._processed_comment_ids: Dict[str, set] = {}  # work_item_id -> set of comment IDs
        self._identity_service = identity_service

    # Query Operations

    async def get_thread(self, work_item_id: str) -> DiscussionThread:
        """Retrieve full discussion thread for a work item.

        Args:
            work_item_id: Work item to retrieve discussion for

        Returns:
            DiscussionThread: Complete thread with all comments

        Raises:
            ValueError: Work item doesn't exist or has no discussion
        """
        if work_item_id not in self._threads:
            raise ValueError(f"No discussion thread for work item: {work_item_id}")

        return DiscussionThread(
            id=f"thread-{work_item_id}",
            work_item_id=work_item_id,
            comments=self._threads[work_item_id].copy(),
            thread_type='flat'
        )

    # Command Operations

    async def add_comment(
        self,
        work_item_id: str,
        content: str,
        parent_id: Optional[str] = None,
    ) -> Comment:
        """Post a comment to a work item.

        Args:
            work_item_id: Work item to comment on
            content: Comment text
            parent_id: Optional parent comment ID for threaded replies

        Returns:
            Comment: Newly posted comment

        Raises:
            ValueError: Work item doesn't have a discussion thread
        """
        if work_item_id not in self._threads:
            self._threads[work_item_id] = []

        comment = Comment(
            id=f"comment-{len(self._threads[work_item_id])}",
            author=self._identity_service.get_bot_username(),
            body=content,
            created_at=self._get_iso_timestamp(),
            parent_id=parent_id,
            is_bot=True
        )

        self._threads[work_item_id].append(comment)

        if work_item_id in self._monitoring:
            config = self._monitoring[work_item_id]
            self.emit(CommentPostedEvent(
                type='comment.posted',
                work_item_id=work_item_id,
                project_id=config.project_id,
                comment=comment,
                timestamp=self._get_iso_timestamp(),
                source='mock'
            ))

        return comment

    # Work-Item-Specific Monitoring

    def start_monitoring(
        self,
        work_item_id: str,
        config: DiscussionMonitoringConfig
    ) -> None:
        """Start monitoring a specific work item for new comments.

        Args:
            work_item_id: Work item to monitor
            config: Monitoring configuration

        Raises:
            ValueError: If work_item_id or config is invalid
        """
        if not work_item_id:
            raise ValueError("work_item_id cannot be empty")
        if not config.project_id:
            raise ValueError("config.project_id cannot be empty")

        self._monitoring[work_item_id] = config

        # Initialize thread if needed
        if work_item_id not in self._threads:
            self._threads[work_item_id] = []

    def stop_monitoring(self, work_item_id: str) -> None:
        """Stop monitoring a specific work item for new comments.

        Args:
            work_item_id: Work item to stop monitoring

        Raises:
            ValueError: If not currently monitoring this item
        """
        if work_item_id not in self._monitoring:
            raise ValueError(f"Not monitoring work item: {work_item_id}")
        del self._monitoring[work_item_id]

    # Test Helper Methods

    def simulate_comment(
        self,
        work_item_id: str,
        author: str,
        body: str,
        parent_id: Optional[str] = None,
        is_initial: bool = False
    ) -> None:
        """Test helper: Simulate human comment requiring response.

        Simulates a human comment being posted to a work item discussion,
        optionally emitting a "needs_response" event.

        Args:
            work_item_id: Work item to comment on
            author: Username of the commenter
            body: Comment text
            parent_id: Optional parent comment ID for threaded replies
            is_initial: Whether this is the initial request comment
        """
        # Initialize thread if needed
        if work_item_id not in self._threads:
            self._threads[work_item_id] = []

        comment = Comment(
            id=f"comment-{len(self._threads[work_item_id])}",
            author=author,
            body=body,
            created_at=self._get_iso_timestamp(),
            parent_id=parent_id,
            is_bot=self._identity_service.is_bot_user(author)
        )

        self._threads[work_item_id].append(comment)

        # Only emit event if monitoring this item and comment is from human
        if not comment.is_bot and work_item_id in self._monitoring:
            config = self._monitoring[work_item_id]

            # Track processed comment
            if work_item_id not in self._processed_comment_ids:
                self._processed_comment_ids[work_item_id] = set()
            self._processed_comment_ids[work_item_id].add(comment.id)

            context = CommentContext(
                thread_id=f"thread-{work_item_id}",
                parent_comment=None,
                is_initial_request=is_initial,
                column_name=config.column_name,
                agent_assignment=config.agent_assignment
            )
            self.emit(CommentNeedsResponseEvent(
                type='comment.needs_response',
                work_item_id=work_item_id,
                project_id=config.project_id,
                comment=comment,
                context=context,
                timestamp=self._get_iso_timestamp(),
                source='mock'
            ))

    def simulate_bot_comment(
        self,
        work_item_id: str,
        body: str,
        parent_id: Optional[str] = None
    ) -> Comment:
        """Test helper: Simulate bot comment.

        Simulates a bot (system) comment being posted to a work item discussion.
        This is similar to add_comment() but intended for test setup.

        Args:
            work_item_id: Work item to comment on
            body: Comment text
            parent_id: Optional parent comment ID for threaded replies

        Returns:
            Comment: The posted comment

        Example:
            comment = adapter.simulate_bot_comment("item-1", "Processing...")
            assert comment.is_bot is True
            assert comment.author == "codetoreum-bot"
        """
        # Initialize thread if needed
        if work_item_id not in self._threads:
            self._threads[work_item_id] = []

        comment = Comment(
            id=f"comment-{len(self._threads[work_item_id])}",
            author=self._identity_service.get_bot_username(),
            body=body,
            created_at=self._get_iso_timestamp(),
            parent_id=parent_id,
            is_bot=True
        )

        self._threads[work_item_id].append(comment)

        # Emit event if monitoring this item
        if work_item_id in self._monitoring:
            config = self._monitoring[work_item_id]
            self.emit(CommentPostedEvent(
                type='comment.posted',
                work_item_id=work_item_id,
                project_id=config.project_id,
                comment=comment,
                timestamp=self._get_iso_timestamp(),
                source='mock'
            ))

        return comment

    def create_thread(
        self,
        work_item_id: str,
        initial_comment_body: str,
        author: str = "requester"
    ) -> Comment:
        """Test helper: Create a discussion thread with initial comment.

        Sets up a discussion thread for a work item with an initial comment.
        Useful for test setup.

        Args:
            work_item_id: Work item to create thread for
            initial_comment_body: Content of the initial comment
            author: Author of the initial comment

        Returns:
            Comment: The initial comment

        Example:
            initial = adapter.create_thread("item-1", "Please review this PR")
            assert initial.author == "requester"
        """
        if work_item_id not in self._threads:
            self._threads[work_item_id] = []

        comment = Comment(
            id=f"comment-{len(self._threads[work_item_id])}",
            author=author,
            body=initial_comment_body,
            created_at=self._get_iso_timestamp(),
            parent_id=None,
            is_bot=self._identity_service.is_bot_user(author)
        )

        self._threads[work_item_id].append(comment)
        return comment

    def get_comments_by_author(
        self,
        work_item_id: str,
        author: str
    ) -> List[Comment]:
        """Test helper: Get all comments from a specific author.

        Args:
            work_item_id: Work item to query
            author: Username to filter by

        Returns:
            List[Comment]: Comments from the specified author

        Example:
            comments = adapter.get_comments_by_author("item-1", "alice")
            assert len(comments) == 2
        """
        if work_item_id not in self._threads:
            return []

        return [c for c in self._threads[work_item_id] if c.author == author]

    def get_comment_count(self, work_item_id: str) -> int:
        """Test helper: Get total number of comments on a work item.

        Args:
            work_item_id: Work item to query

        Returns:
            int: Number of comments (0 if no thread exists)

        Example:
            count = adapter.get_comment_count("item-1")
            assert count == 3
        """
        if work_item_id not in self._threads:
            return 0
        return len(self._threads[work_item_id])

    def thread_exists(self, work_item_id: str) -> bool:
        """Test helper: Check if a discussion thread exists for a work item.

        Args:
            work_item_id: Work item to check

        Returns:
            bool: True if thread exists, False otherwise

        Example:
            assert adapter.thread_exists("item-1") is True
        """
        return work_item_id in self._threads

    def is_monitoring(self, work_item_id: str) -> bool:
        """Test helper: Check if currently monitoring a work item.

        Args:
            work_item_id: Work item to check

        Returns:
            bool: True if monitoring, False otherwise

        Example:
            assert adapter.is_monitoring("item-1") is True
        """
        return work_item_id in self._monitoring

    def clear_threads(self) -> None:
        """Test helper: Clear all discussion threads.

        Useful for cleaning up between test cases.

        Example:
            adapter.clear_threads()
            assert adapter.get_comment_count("item-1") == 0
        """
        self._threads.clear()

    def clear_monitoring(self) -> None:
        """Test helper: Clear all monitoring state.

        Stops monitoring all work items and clears the monitoring config.

        Example:
            adapter.clear_monitoring()
            assert adapter.is_monitoring("item-1") is False
        """
        self._monitoring.clear()

    def get_thread_info(self, work_item_id: str) -> Dict[str, Any]:
        """Test helper: Get diagnostic info about a discussion thread.

        Provides thread metadata without raising exceptions for missing threads.

        Args:
            work_item_id: Work item to query

        Returns:
            Dict with keys: 'exists', 'comment_count', 'is_monitored', 'authors'

        Example:
            info = adapter.get_thread_info("item-1")
            assert info['comment_count'] == 3
            assert 'alice' in info['authors']
        """
        return {
            'exists': work_item_id in self._threads,
            'comment_count': len(self._threads.get(work_item_id, [])),
            'is_monitored': work_item_id in self._monitoring,
            'authors': list(set(
                c.author for c in self._threads.get(work_item_id, [])
            ))
        }

    def simulate_column_change(
        self,
        work_item_id: str,
        from_column: str,
        to_column: str
    ) -> None:
        """Test helper: Simulate work item column change.

        Emits WorkItemColumnChangedEvent to trigger loop exit/entry.

        Args:
            work_item_id: Work item being moved
            from_column: Source column name
            to_column: Destination column name

        Raises:
            ValueError: Work item is not being monitored

        Example:
            adapter.start_monitoring("item-1", config)
            adapter.simulate_column_change("item-1", "Backlog", "In Review")
            # WorkItemColumnChangedEvent is emitted
        """
        if work_item_id not in self._monitoring:
            raise ValueError(f"Not monitoring work item: {work_item_id}")

        config = self._monitoring[work_item_id]

        event = WorkItemColumnChangedEvent(
            type='workitem.column_changed',
            work_item_id=work_item_id,
            project_id=config.project_id,
            board_id=f"board-{config.project_id}",
            from_column=from_column,
            to_column=to_column,
            moved_by="unknown",
            timestamp=self._get_iso_timestamp(),
            source='mock'
        )

        self.emit(event)

    def get_processed_comment_ids(self, work_item_id: str) -> set:
        """Test helper: Get set of processed comment IDs for verification.

        Used in tests to verify duplicate prevention logic.

        Args:
            work_item_id: Work item to query

        Returns:
            Set of processed comment IDs (empty set if no comments processed)

        Example:
            adapter.simulate_comment("item-1", "alice", "Review this")
            processed = adapter.get_processed_comment_ids("item-1")
            assert len(processed) == 1
        """
        return self._processed_comment_ids.get(work_item_id, set()).copy()

    def reset_monitoring_state(self, work_item_id: str) -> None:
        """Test helper: Reset monitoring state for restart simulation.

        Used to simulate orchestrator restart - clears in-memory state
        but preserves comment queue.

        Args:
            work_item_id: Work item to reset monitoring for

        Raises:
            ValueError: Work item is not being monitored

        Example:
            adapter.start_monitoring("item-1", config)
            adapter.simulate_comment("item-1", "alice", "Comment")
            adapter.reset_monitoring_state("item-1")
            assert not adapter.is_monitoring("item-1")
            assert adapter.thread_exists("item-1")  # Thread still exists
        """
        if work_item_id not in self._monitoring:
            raise ValueError(f"Not monitoring work item: {work_item_id}")

        del self._monitoring[work_item_id]

    # Helper Methods

    @staticmethod
    def _get_iso_timestamp() -> str:
        """Get current time as ISO 8601 timestamp."""
        return datetime.now(timezone.utc).isoformat()
