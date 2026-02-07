"""Discussion adapter port interface with event emission.

This interface defines contracts for managing discussions/comments on work items,
including posting comments, retrieving threads, and monitoring for new responses.

Discussions are vendor-agnostic abstractions over GitHub issue comments, PR reviews,
JIRA issue discussions, etc. Unlike other services, discussion monitoring is
work-item-specific rather than project-wide, enabling granular subscription
to discussion updates.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Literal, Optional

from codetoreum.domain.events import Comment, CommentContext

from .event_emitter import IEventEmitter


@dataclass
class DiscussionMonitoringConfig:
    """Configuration for work-item-specific discussion monitoring.

    Unlike project-wide monitoring (IMonitoredService), discussion monitoring
    is work-item-specific, allowing selective subscription to specific issues.

    This configuration focuses on discussion-specific concerns (what comments
    have been processed) rather than workflow/board context (column, agent assignment).
    Board context should be tracked separately in the orchestration layer.

    Attributes:
        project_id: Project containing the work item
        last_processed_comment_id: Last comment ID already processed,
                                  used to avoid reprocessing comments
    """

    project_id: str
    last_processed_comment_id: Optional[str] = None


@dataclass
class DiscussionThread:
    """Represents a complete discussion thread on a work item.

    Attributes:
        id: Unique identifier for the thread
        work_item_id: Work item this thread is on
        comments: All comments in the thread
        thread_type: 'flat' for sequential comments, 'nested' for threaded replies
    """

    id: str
    work_item_id: str
    comments: List[Comment]
    thread_type: Literal["flat", "nested"]


class IDiscussionAdapter(IEventEmitter, ABC):
    """Discussion/comment management with event emission.

    Provides vendor-agnostic abstraction for discussions on work items
    (GitHub issue comments, PR reviews, JIRA comments, etc.). Unlike
    other services, monitoring is work-item-specific, not project-wide.

    This adapter enables:
    1. Posting comments to work items
    2. Retrieving discussion threads
    3. Monitoring specific work items for new comments

    Events emitted:
        - 'comment.needs_response' → CommentNeedsResponseEvent
                                     When a comment requires agent response
        - 'comment.posted' → CommentPostedEvent
                            When any comment is posted (monitoring active)

    Example:
        async with adapter as adp:
            # Start monitoring a specific work item
            config = DiscussionMonitoringConfig(
                project_id="proj-123"
            )
            adp.start_monitoring("issue-789", config)

            # Subscribe to new comments
            adp.on("comment.needs_response", handle_comment)

            # Query thread
            thread = await adp.get_thread("issue-789")

            # Post a response
            comment = await adp.add_comment(
                work_item_id="issue-789",
                content="This looks good to me!"
            )

            # Stop monitoring when done
            adp.stop_monitoring("issue-789")
    """

    # Query Operations

    @abstractmethod
    async def get_thread(self, work_item_id: str) -> DiscussionThread:
        """Retrieve full discussion thread for a work item.

        Returns all comments on the work item, including replies if applicable.

        Args:
            work_item_id: Work item to retrieve discussion for

        Returns:
            DiscussionThread: Complete thread with all comments

        Raises:
            ResourceNotFoundError: Work item doesn't exist or has no discussion
            ExternalServiceError: Service communication failure
        """
        pass

    # Command Operations

    @abstractmethod
    async def add_comment(
        self,
        work_item_id: str,
        content: str,
        parent_id: Optional[str] = None,
    ) -> Comment:
        """Post a comment to a work item.

        Adds a comment to the work item's discussion thread. If parent_id is
        provided and the system supports threading, creates a reply.

        Args:
            work_item_id: Work item to comment on
            content: Comment text (supports markdown if platform supports it)
            parent_id: Optional parent comment ID for threaded replies

        Returns:
            Comment: Newly posted comment with server-assigned ID and timestamp

        Raises:
            ResourceNotFoundError: Work item doesn't exist
            ValidationError: Comment content is invalid or too long
            ExternalServiceError: Service communication failure

        Events:
            Emits 'comment.posted' event with new comment
        """
        pass

    # Work-Item-Specific Monitoring

    @abstractmethod
    def start_monitoring(
        self, work_item_id: str, config: DiscussionMonitoringConfig
    ) -> None:
        """Start monitoring a specific work item for new comments.

        Enables change detection for a particular work item's discussion thread.
        When new comments are posted (especially those requiring response),
        events are emitted.

        This is work-item-specific monitoring, not project-wide. Use this
        to subscribe to individual issues/items.

        Args:
            work_item_id: Work item to monitor for discussion updates
            config: Monitoring configuration with context

        Raises:
            ValidationError: If work_item_id or config is invalid
            ResourceNotFoundError: Work item doesn't exist
            ExternalServiceError: If unable to start monitoring
        """
        pass

    @abstractmethod
    def stop_monitoring(self, work_item_id: str) -> None:
        """Stop monitoring a specific work item for new comments.

        Disables change detection for the work item. After this call,
        no events will be emitted for this item's discussion.

        Args:
            work_item_id: Work item to stop monitoring

        Raises:
            ValidationError: If work_item_id is invalid
            ResourceNotFoundError: If not currently monitoring this item
        """
        pass
