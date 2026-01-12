"""In-memory discussion adapter with event simulation for testing.

This module provides a mock implementation of IDiscussionAdapter that stores
discussion threads and comments in memory, and includes test helper methods
for simulating discussion updates via event emission.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

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
    4. Provides test helper methods for event simulation

    Intended for testing and simulation without external discussion systems
    (GitHub issues, PRs, Jira comments, etc.).

    Example:
        # Setup
        adapter = MockDiscussionAdapter(identity_service)

        # Subscribe to events
        events = []
        adapter.on("comment.needs_response", events.append)

        # Start monitoring a work item
        config = DiscussionMonitoringConfig(
            project_id="proj-1",
            column_name="In Review",
            agent_assignment="agent-1"
        )
        adapter.start_monitoring("item-1", config)

        # Simulate human comment
        adapter.simulate_comment(
            work_item_id="item-1",
            author="alice",
            body="This needs review"
        )

        # Verify event was emitted
        assert len(events) == 1
        assert events[0].comment.body == "This needs review"
    """

    def __init__(self, identity_service: IIdentityService) -> None:
        """Initialize the discussion adapter.

        Args:
            identity_service: Service for identifying bot users
        """
        super().__init__()
        self._threads: Dict[str, List[Comment]] = {}  # work_item_id -> comments
        self._monitoring: Dict[str, DiscussionMonitoringConfig] = {}  # work_item_id -> config
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

    # Helper Methods

    @staticmethod
    def _get_iso_timestamp() -> str:
        """Get current time as ISO 8601 timestamp."""
        return datetime.now(timezone.utc).isoformat()
