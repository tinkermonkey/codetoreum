"""In-memory ticket system adapter for testing."""

import asyncio
import logging
import threading
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from codetoreum.adapters.secondary.mock_event_emitter import MockEventEmitter
from codetoreum.domain.comment import Comment
from codetoreum.domain.events.discussion_events import (
    Comment as DiscussionComment,
)
from codetoreum.domain.events.discussion_events import (
    CommentPostedEvent,
)
from codetoreum.domain.events.work_item_events import (
    WorkItemCreatedEvent,
    WorkItemUpdatedEvent,
)
from codetoreum.domain.types import CommentId, ProjectId, UserId, WorkItemId
from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus
from codetoreum.ports.exceptions import (
    ResourceNotFoundError,
    ValidationError,
)
from codetoreum.ports.output.ticket_system import ITicketSystem

logger = logging.getLogger(__name__)


class InMemoryTicketAdapter(MockEventEmitter, ITicketSystem):
    """
    In-memory implementation of ticket system for testing.

    Uses simple dictionary-based storage with thread-safe operations. Useful for unit
    and integration tests where you don't want external dependencies.

    Note: This adapter is thread-safe for concurrent test execution but is designed
    for testing purposes only. All dictionary and list modifications are protected
    by a lock.
    """

    def __init__(self):
        """Initialize the in-memory ticket adapter with thread-safe storage."""
        super().__init__()
        self._work_items: dict[str, WorkItem] = {}
        self._comments: dict[str, list[Comment]] = {}  # work_item_id -> comments
        self._webhooks: dict[str, dict[str, Any]] = {}
        self._relationships: dict[str, list[tuple[str, str]]] = {}  # source_id -> [(target_id, relationship)]
        self._children: dict[str, list[str]] = {}  # parent_id -> list of child work_item_ids
        self._next_work_item_number = 1
        self._lock = threading.Lock()  # Thread safety for concurrent test execution

    # ===== Query Operations =====

    async def get_work_item(self, item_id: WorkItemId) -> WorkItem:
        """
        Retrieve a work item by ID.

        Args:
            item_id: The unique identifier of the work item

        Returns:
            The requested work item

        Raises:
            ResourceNotFoundError: If the work item does not exist
        """
        with self._lock:
            work_item = self._work_items.get(str(item_id))
            if not work_item:
                msg = "WorkItem"
                raise ResourceNotFoundError(msg, str(item_id))
            return work_item

    async def create_work_item(
        self,
        title: str,
        description: str,
        project_id: ProjectId,
        labels: list[str] | None = None,
        assignee: UserId | None = None,
        priority: WorkItemPriority | None = None,
        metadata: dict[str, Any] | None = None,
        parent_issue_id: str | None = None,
        pr_id: str | None = None,
        discussion_id: str | None = None,
    ) -> WorkItem:
        """
        Create a new work item.

        Args:
            title: Work item title (required, cannot be empty)
            description: Work item description
            project_id: Project identifier (required)
            labels: Optional list of labels
            assignee: Optional assignee user ID
            priority: Optional priority level
            metadata: Optional metadata dictionary
            parent_issue_id: Optional parent issue ID for sub-issues
            pr_id: Optional PR identifier (e.g., GitHub PR number)
            discussion_id: Optional discussion thread identifier

        Returns:
            The created work item

        Raises:
            ValidationError: If required fields are missing or invalid
        """
        if not title or not title.strip():
            msg = "Title cannot be empty"
            raise ValidationError(msg)

        if not project_id:
            msg = "Project ID cannot be empty"
            raise ValidationError(msg)

        if not description:
            description = ""

        with self._lock:
            work_item = WorkItem.create(
                title=title,
                description=description,
                project_id=str(project_id),
                labels=labels or [],
                priority=priority or WorkItemPriority.MEDIUM,
                external_id=f"#{self._next_work_item_number}",
                external_url=f"http://example.com/issues/{self._next_work_item_number}",
                pr_id=pr_id,
                discussion_id=discussion_id,
            )

            self._next_work_item_number += 1
            self._work_items[work_item.id] = work_item
            self._comments[work_item.id] = []

            # Track parent-child relationship
            if parent_issue_id is not None:
                parent_key = str(parent_issue_id)
                if parent_key not in self._children:
                    self._children[parent_key] = []
                self._children[parent_key].append(work_item.id)

            # Clear events after storage
            work_item.clear_events()

            # Emit creation event
            event = WorkItemCreatedEvent(
                type="workitem.created",
                timestamp=datetime.now(UTC).isoformat(),
                source="in_memory_ticket",
                work_item_id=work_item.id,
                project_id=str(project_id),
                title=title,
                parent_issue_id=parent_issue_id,
            )
            self.emit(event)

            return work_item

    async def get_child_issues(self, parent_id) -> list[WorkItem]:
        """Get all child work items for a parent."""
        with self._lock:
            child_ids = self._children.get(str(parent_id), [])
            return [self._work_items[cid] for cid in child_ids if cid in self._work_items]

    async def update_work_item(self, item_id: WorkItemId, updates: dict[str, Any]) -> WorkItem:
        """
        Update an existing work item.

        Args:
            item_id: The unique identifier of the work item to update
            updates: Dictionary of fields to update (title, description, labels, priority)

        Returns:
            The updated work item

        Raises:
            ResourceNotFoundError: If the work item does not exist
            ValidationError: If updates dictionary is None or empty
        """
        if not item_id:
            msg = "Work item ID cannot be empty"
            raise ValidationError(msg)

        if updates is None:
            msg = "Updates dictionary cannot be None"
            raise ValidationError(msg)

        work_item = await self.get_work_item(item_id)

        with self._lock:
            # Apply updates
            if "title" in updates:
                work_item.title = updates["title"]
            if "description" in updates:
                work_item.description = updates["description"]
            if "labels" in updates:
                work_item.update_labels(updates["labels"])
            if "priority" in updates:
                priority = updates["priority"]
                if isinstance(priority, str):
                    priority = WorkItemPriority[priority.upper()]
                work_item.update_priority(priority)

            work_item.updated_at = datetime.now(UTC)
            work_item.clear_events()

            # Emit update event
            event = WorkItemUpdatedEvent(
                type="workitem.updated",
                timestamp=datetime.now(UTC).isoformat(),
                source="in_memory_ticket",
                work_item_id=work_item.id,
                project_id=work_item.project_id,
                changes=dict(updates),
            )
            self.emit(event)

            return work_item

    async def delete_work_item(self, item_id: WorkItemId) -> None:
        """
        Delete a work item.

        Args:
            item_id: The unique identifier of the work item to delete

        Raises:
            ResourceNotFoundError: If the work item does not exist
            ValidationError: If item_id is None or empty
        """
        if not item_id:
            msg = "Work item ID cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            if str(item_id) not in self._work_items:
                msg = "WorkItem"
                raise ResourceNotFoundError(msg, str(item_id))

            del self._work_items[str(item_id)]
            if str(item_id) in self._comments:
                del self._comments[str(item_id)]
            if str(item_id) in self._relationships:
                del self._relationships[str(item_id)]

    async def update_status(
        self,
        item_id: WorkItemId,
        status: WorkItemStatus,
        reason: str | None = None,
    ) -> WorkItem:
        """
        Update work item status.

        Args:
            item_id: The unique identifier of the work item
            status: The new status to set
            reason: Optional reason for status change

        Returns:
            The updated work item

        Raises:
            ResourceNotFoundError: If the work item does not exist
            ValidationError: If item_id or status is None/empty
        """
        if not item_id:
            msg = "Work item ID cannot be empty"
            raise ValidationError(msg)

        if not status:
            msg = "Status cannot be None"
            raise ValidationError(msg)

        work_item = await self.get_work_item(item_id)

        with self._lock:
            # Transition based on target status
            if status == WorkItemStatus.IN_PROGRESS and work_item.status == WorkItemStatus.ASSIGNED:
                work_item.start()
            elif status == WorkItemStatus.UNDER_REVIEW:
                if work_item.status == WorkItemStatus.IN_PROGRESS:
                    work_item.mark_under_review()
            elif status == WorkItemStatus.COMPLETED:
                work_item.complete()
            elif status == WorkItemStatus.FAILED:
                work_item.fail(reason or "Manual status update")
            elif status == WorkItemStatus.BLOCKED:
                work_item.block(reason or "Manual block")
            elif status == WorkItemStatus.NEW and work_item.status == WorkItemStatus.BLOCKED:
                work_item.unblock()

            work_item.clear_events()
            return work_item

    async def list_work_items(
        self,
        project_id: ProjectId | None = None,
        status: WorkItemStatus | None = None,
        assignee: UserId | None = None,
        labels: list[str] | None = None,
        created_after: datetime | None = None,
        updated_after: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[WorkItem]:
        """
        List work items with optional filters.

        Args:
            project_id: Filter by project ID
            status: Filter by status
            assignee: Filter by assignee user ID
            labels: Filter by labels (all must match)
            created_after: Filter by creation date
            updated_after: Filter by update date
            limit: Maximum number of results (default 100)
            offset: Number of results to skip (default 0)

        Returns:
            List of work items matching the filters
        """
        with self._lock:
            results = list(self._work_items.values())

            # Apply filters
            if project_id:
                results = [wi for wi in results if wi.project_id == str(project_id)]
            if status:
                results = [wi for wi in results if wi.status == status]
            if assignee:
                results = [wi for wi in results if wi.assigned_agent_id == str(assignee)]
            if labels:
                results = [wi for wi in results if all(label in wi.labels for label in labels)]
            if created_after:
                results = [wi for wi in results if wi.created_at > created_after]
            if updated_after:
                results = [wi for wi in results if wi.updated_at > updated_after]

            # Apply pagination
            results = results[offset : offset + limit]

            return results

    async def search_work_items(
        self,
        query: str,
        project_id: ProjectId | None = None,
        limit: int = 100,
    ) -> list[WorkItem]:
        """
        Full-text search for work items.

        Args:
            query: Search query string
            project_id: Optional project ID to filter by
            limit: Maximum number of results (default 100)

        Returns:
            List of work items matching the search query

        Raises:
            ValidationError: If query is None or empty
        """
        if not query or not query.strip():
            msg = "Search query cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            results = list(self._work_items.values())

            if project_id:
                results = [wi for wi in results if wi.project_id == str(project_id)]

            # Simple text search in title and description
            query_lower = query.lower()
            results = [wi for wi in results if query_lower in wi.title.lower() or query_lower in wi.description.lower()]

            return results[:limit]

    async def get_work_item_stream(
        self,
        project_id: ProjectId | None = None,
        since: datetime | None = None,
    ) -> AsyncIterator[WorkItem]:
        """
        Stream work item updates in real-time.

        Args:
            project_id: Optional project ID to filter by
            since: Optional timestamp to get updates after

        Yields:
            Work items matching the filters
        """
        # For testing, just yield existing items
        work_items = await self.list_work_items(project_id=project_id)

        if since:
            work_items = [wi for wi in work_items if wi.updated_at > since]

        for work_item in work_items:
            await asyncio.sleep(0.01)  # Simulate streaming delay
            yield work_item

    async def add_comment(
        self,
        item_id: WorkItemId,
        body: str,
        author: UserId | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Comment:
        """
        Add a comment to a work item.

        Args:
            item_id: The unique identifier of the work item
            body: Comment text content
            author: Optional author user ID (defaults to "system")
            metadata: Optional metadata dictionary

        Returns:
            The created comment

        Raises:
            ResourceNotFoundError: If the work item does not exist
            ValidationError: If item_id or body is None/empty
        """
        if not item_id:
            msg = "Work item ID cannot be empty"
            raise ValidationError(msg)

        if not body or not body.strip():
            msg = "Comment body cannot be empty"
            raise ValidationError(msg)

        # Verify work item exists
        work_item = await self.get_work_item(item_id)

        with self._lock:
            comment = Comment(
                id=CommentId(str(uuid4())),
                work_item_id=item_id,
                author_id=author or UserId("system"),
                body=body,
                created_at=datetime.now(UTC),
            )

            self._comments[str(item_id)].append(comment)

            # Emit comment posted event
            discussion_comment = DiscussionComment(
                id=comment.id,
                author=str(comment.author_id),
                body=body,
                created_at=datetime.now(UTC).isoformat(),
            )
            event = CommentPostedEvent(
                type="comment.posted",
                timestamp=datetime.now(UTC).isoformat(),
                source="in_memory_ticket",
                work_item_id=str(item_id),
                project_id=work_item.project_id,
                comment=discussion_comment,
            )
            self.emit(event)

            return comment

    async def get_comments(
        self,
        item_id: WorkItemId,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[Comment]:
        """
        Get comments for a work item.

        Args:
            item_id: The unique identifier of the work item
            since: Optional timestamp to get comments after
            limit: Maximum number of comments to return (default 100)

        Returns:
            List of comments for the work item

        Raises:
            ResourceNotFoundError: If the work item does not exist
            ValidationError: If item_id is None or empty
        """
        if not item_id:
            msg = "Work item ID cannot be empty"
            raise ValidationError(msg)

        # Verify work item exists
        await self.get_work_item(item_id)

        with self._lock:
            comments = self._comments.get(str(item_id), [])

            if since:
                comments = [c for c in comments if c.created_at > since]

            return comments[:limit]

    async def link_work_items(
        self,
        source_id: WorkItemId,
        target_id: WorkItemId,
        relationship: str,
    ) -> None:
        """
        Create relationship between work items.

        Args:
            source_id: The source work item ID
            target_id: The target work item ID
            relationship: Type of relationship (e.g., "blocks", "depends_on")

        Raises:
            ResourceNotFoundError: If either work item does not exist
            ValidationError: If any parameter is None or empty
        """
        if not source_id:
            msg = "Source work item ID cannot be empty"
            raise ValidationError(msg)

        if not target_id:
            msg = "Target work item ID cannot be empty"
            raise ValidationError(msg)

        if not relationship or not relationship.strip():
            msg = "Relationship type cannot be empty"
            raise ValidationError(msg)

        # Verify both work items exist
        await self.get_work_item(source_id)
        await self.get_work_item(target_id)

        with self._lock:
            if str(source_id) not in self._relationships:
                self._relationships[str(source_id)] = []

            self._relationships[str(source_id)].append((str(target_id), relationship))

    async def get_related_items(
        self,
        item_id: WorkItemId,
        relationship: str | None = None,
    ) -> list[WorkItem]:
        """
        Get related work items.

        Args:
            item_id: The work item ID
            relationship: Optional relationship type to filter by

        Returns:
            List of related work items

        Raises:
            ResourceNotFoundError: If the work item does not exist
            ValidationError: If item_id is None or empty
        """
        if not item_id:
            msg = "Work item ID cannot be empty"
            raise ValidationError(msg)

        # Verify work item exists
        await self.get_work_item(item_id)

        with self._lock:
            relationships = self._relationships.get(str(item_id), [])

            if relationship:
                relationships = [(target, rel) for target, rel in relationships if rel == relationship]

            related_ids = [target for target, _ in relationships]
            return [self._work_items[wid] for wid in related_ids if wid in self._work_items]

    async def register_webhook(
        self,
        url: str,
        events: list[str],
        project_id: ProjectId | None = None,
    ) -> str:
        """
        Register a webhook for events.

        Args:
            url: Webhook URL (must start with http:// or https://)
            events: List of event types to subscribe to
            project_id: Optional project ID to filter events

        Returns:
            Webhook ID

        Raises:
            ValidationError: If url or events are invalid
        """
        if not url or not url.startswith(("http://", "https://")):
            msg = "Invalid webhook URL"
            raise ValidationError(msg)

        if not events:
            msg = "At least one event type is required"
            raise ValidationError(msg)

        with self._lock:
            webhook_id = str(uuid4())
            self._webhooks[webhook_id] = {
                "url": url,
                "events": events,
                "project_id": str(project_id) if project_id else None,
                "created_at": datetime.now(UTC),
            }

            return webhook_id

    async def unregister_webhook(self, webhook_id: str) -> None:
        """
        Unregister a webhook.

        Args:
            webhook_id: The webhook ID to unregister

        Raises:
            ResourceNotFoundError: If the webhook does not exist
            ValidationError: If webhook_id is None or empty
        """
        if not webhook_id:
            msg = "Webhook ID cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            if webhook_id not in self._webhooks:
                msg = "Webhook"
                raise ResourceNotFoundError(msg, webhook_id)

            del self._webhooks[webhook_id]

    # Helper methods for testing

    def clear(self) -> None:
        """
        Clear all stored data.

        This is a testing helper method to reset the adapter state.
        """
        with self._lock:
            self._work_items.clear()
            self._comments.clear()
            self._webhooks.clear()
            self._relationships.clear()
            self._children.clear()
            self._handlers.clear()
            self._next_work_item_number = 1

    def get_all_work_items(self) -> list[WorkItem]:
        """
        Get all work items (for testing).

        Returns:
            List of all work items in storage
        """
        with self._lock:
            return list(self._work_items.values())

    def get_webhook_count(self) -> int:
        """
        Get number of registered webhooks (for testing).

        Returns:
            Number of registered webhooks
        """
        with self._lock:
            return len(self._webhooks)
