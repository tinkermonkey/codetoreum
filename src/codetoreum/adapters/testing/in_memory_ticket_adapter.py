"""In-memory ticket system adapter for testing."""

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

from codetoreum.domain.comment import Comment
from codetoreum.domain.types import CommentId, ProjectId, UserId, WorkItemId
from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus
from codetoreum.ports.exceptions import (
    ResourceNotFoundError,
    ValidationError,
)
from codetoreum.ports.output.ticket_system import ITicketSystem


class InMemoryTicketAdapter(ITicketSystem):
    """
    In-memory implementation of ticket system for testing.

    Uses simple dictionary-based storage. Useful for unit and integration tests
    where you don't want external dependencies.
    """

    def __init__(self):
        """Initialize the in-memory ticket adapter."""
        self._work_items: Dict[str, WorkItem] = {}
        self._comments: Dict[str, List[Comment]] = {}  # work_item_id -> comments
        self._webhooks: Dict[str, Dict[str, Any]] = {}
        self._relationships: Dict[str, List[tuple[str, str]]] = {}  # source_id -> [(target_id, relationship)]
        self._next_work_item_number = 1

    async def get_work_item(self, item_id: WorkItemId) -> WorkItem:
        """Retrieve a work item by ID."""
        work_item = self._work_items.get(str(item_id))
        if not work_item:
            raise ResourceNotFoundError("WorkItem", str(item_id))
        return work_item

    async def create_work_item(
        self,
        title: str,
        description: str,
        project_id: ProjectId,
        labels: Optional[List[str]] = None,
        assignee: Optional[UserId] = None,
        priority: Optional[WorkItemPriority] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> WorkItem:
        """Create a new work item."""
        if not title or not title.strip():
            raise ValidationError("Title cannot be empty")

        if not description:
            description = ""

        work_item = WorkItem.create(
            title=title,
            description=description,
            project_id=str(project_id),
            labels=labels or [],
            priority=priority or WorkItemPriority.MEDIUM,
            external_id=f"#{self._next_work_item_number}",
            external_url=f"http://example.com/issues/{self._next_work_item_number}",
        )

        self._next_work_item_number += 1
        self._work_items[work_item.id] = work_item
        self._comments[work_item.id] = []

        # Clear events after storage
        work_item.clear_events()

        return work_item

    async def update_work_item(
        self, item_id: WorkItemId, updates: Dict[str, Any]
    ) -> WorkItem:
        """Update an existing work item."""
        work_item = await self.get_work_item(item_id)

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

        work_item.updated_at = datetime.now(timezone.utc)
        work_item.clear_events()
        return work_item

    async def delete_work_item(self, item_id: WorkItemId) -> None:
        """Delete a work item."""
        if str(item_id) not in self._work_items:
            raise ResourceNotFoundError("WorkItem", str(item_id))

        del self._work_items[str(item_id)]
        if str(item_id) in self._comments:
            del self._comments[str(item_id)]
        if str(item_id) in self._relationships:
            del self._relationships[str(item_id)]

    async def update_status(
        self,
        item_id: WorkItemId,
        status: WorkItemStatus,
        reason: Optional[str] = None,
    ) -> WorkItem:
        """Update work item status."""
        work_item = await self.get_work_item(item_id)

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
        project_id: Optional[ProjectId] = None,
        status: Optional[WorkItemStatus] = None,
        assignee: Optional[UserId] = None,
        labels: Optional[List[str]] = None,
        created_after: Optional[datetime] = None,
        updated_after: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[WorkItem]:
        """List work items with filters."""
        results = list(self._work_items.values())

        # Apply filters
        if project_id:
            results = [wi for wi in results if wi.project_id == str(project_id)]
        if status:
            results = [wi for wi in results if wi.status == status]
        if assignee:
            results = [wi for wi in results if wi.assigned_agent_id == str(assignee)]
        if labels:
            results = [
                wi for wi in results
                if all(label in wi.labels for label in labels)
            ]
        if created_after:
            results = [wi for wi in results if wi.created_at > created_after]
        if updated_after:
            results = [wi for wi in results if wi.updated_at > updated_after]

        # Apply pagination
        results = results[offset:offset + limit]

        return results

    async def search_work_items(
        self,
        query: str,
        project_id: Optional[ProjectId] = None,
        limit: int = 100,
    ) -> List[WorkItem]:
        """Full-text search for work items."""
        results = list(self._work_items.values())

        if project_id:
            results = [wi for wi in results if wi.project_id == str(project_id)]

        # Simple text search in title and description
        query_lower = query.lower()
        results = [
            wi for wi in results
            if query_lower in wi.title.lower() or query_lower in wi.description.lower()
        ]

        return results[:limit]

    async def get_work_item_stream(
        self,
        project_id: Optional[ProjectId] = None,
        since: Optional[datetime] = None,
    ) -> AsyncIterator[WorkItem]:
        """Stream work item updates in real-time."""
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
        author: Optional[UserId] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Comment:
        """Add a comment to a work item."""
        # Verify work item exists
        await self.get_work_item(item_id)

        if not body or not body.strip():
            raise ValidationError("Comment body cannot be empty")

        comment = Comment(
            id=CommentId(str(uuid4())),
            work_item_id=item_id,
            author_id=author or UserId("system"),
            body=body,
            created_at=datetime.now(timezone.utc),
        )

        self._comments[str(item_id)].append(comment)
        return comment

    async def get_comments(
        self,
        item_id: WorkItemId,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Comment]:
        """Get comments for a work item."""
        # Verify work item exists
        await self.get_work_item(item_id)

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
        """Create relationship between work items."""
        # Verify both work items exist
        await self.get_work_item(source_id)
        await self.get_work_item(target_id)

        if str(source_id) not in self._relationships:
            self._relationships[str(source_id)] = []

        self._relationships[str(source_id)].append((str(target_id), relationship))

    async def get_related_items(
        self,
        item_id: WorkItemId,
        relationship: Optional[str] = None,
    ) -> List[WorkItem]:
        """Get related work items."""
        # Verify work item exists
        await self.get_work_item(item_id)

        relationships = self._relationships.get(str(item_id), [])

        if relationship:
            relationships = [
                (target, rel) for target, rel in relationships if rel == relationship
            ]

        related_ids = [target for target, _ in relationships]
        return [self._work_items[wid] for wid in related_ids if wid in self._work_items]

    async def register_webhook(
        self,
        url: str,
        events: List[str],
        project_id: Optional[ProjectId] = None,
    ) -> str:
        """Register a webhook for events."""
        if not url or not url.startswith(("http://", "https://")):
            raise ValidationError("Invalid webhook URL")

        if not events:
            raise ValidationError("At least one event type is required")

        webhook_id = str(uuid4())
        self._webhooks[webhook_id] = {
            "url": url,
            "events": events,
            "project_id": str(project_id) if project_id else None,
            "created_at": datetime.now(timezone.utc),
        }

        return webhook_id

    async def unregister_webhook(self, webhook_id: str) -> None:
        """Unregister a webhook."""
        if webhook_id not in self._webhooks:
            raise ResourceNotFoundError("Webhook", webhook_id)

        del self._webhooks[webhook_id]

    # Helper methods for testing

    def clear(self) -> None:
        """Clear all stored data."""
        self._work_items.clear()
        self._comments.clear()
        self._webhooks.clear()
        self._relationships.clear()
        self._next_work_item_number = 1

    def get_all_work_items(self) -> List[WorkItem]:
        """Get all work items (for testing)."""
        return list(self._work_items.values())

    def get_webhook_count(self) -> int:
        """Get number of registered webhooks (for testing)."""
        return len(self._webhooks)
