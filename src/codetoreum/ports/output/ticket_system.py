"""ITicketSystem output port interface."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

from codetoreum.domain.comment import Comment
from codetoreum.domain.types import ProjectId, UserId, WorkItemId
from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus


class ITicketSystem(ABC):
    """
    Interface for ticket/issue management systems.

    This port abstracts operations for work item management,
    supporting various backends like GitHub Issues, Jira, Linear, etc.
    """

    # Work Item Operations

    @abstractmethod
    async def get_work_item(self, item_id: WorkItemId) -> WorkItem:
        """
        Retrieve a work item by ID.

        Args:
            item_id: Unique identifier for the work item

        Returns:
            WorkItem: The requested work item

        Raises:
            WorkItemNotFoundError: Work item doesn't exist
            ExternalServiceError: Service communication failure
        """
        pass

    @abstractmethod
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
        """
        Create a new work item.

        Args:
            title: Work item title
            description: Work item description
            project_id: Project identifier
            labels: Optional list of labels
            assignee: Optional assignee user ID
            priority: Optional priority level
            metadata: Optional additional metadata

        Returns:
            WorkItem: Newly created work item

        Raises:
            ValidationError: Invalid input data
            ProjectNotFoundError: Project doesn't exist
            ExternalServiceError: Service communication failure
        """
        pass

    @abstractmethod
    async def update_work_item(
        self, item_id: WorkItemId, updates: Dict[str, Any]
    ) -> WorkItem:
        """
        Update an existing work item.

        Args:
            item_id: Work item identifier
            updates: Dictionary of fields to update

        Returns:
            WorkItem: Updated work item

        Raises:
            WorkItemNotFoundError: Work item doesn't exist
            ValidationError: Invalid update data
            ExternalServiceError: Service communication failure
        """
        pass

    @abstractmethod
    async def delete_work_item(self, item_id: WorkItemId) -> None:
        """
        Delete a work item.

        Args:
            item_id: Work item identifier

        Raises:
            WorkItemNotFoundError: Work item doesn't exist
            ExternalServiceError: Service communication failure
        """
        pass

    @abstractmethod
    async def update_status(
        self,
        item_id: WorkItemId,
        status: WorkItemStatus,
        reason: Optional[str] = None,
    ) -> WorkItem:
        """
        Update work item status.

        Args:
            item_id: Work item identifier
            status: New status
            reason: Optional reason for status change

        Returns:
            WorkItem: Updated work item

        Raises:
            WorkItemNotFoundError: Work item doesn't exist
            ValidationError: Invalid status transition
            ExternalServiceError: Service communication failure
        """
        pass

    # Query Operations

    @abstractmethod
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
        """
        List work items with filters.

        Args:
            project_id: Filter by project
            status: Filter by status
            assignee: Filter by assignee
            labels: Filter by labels (work item must have all specified labels)
            created_after: Filter by creation date
            updated_after: Filter by update date
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List[WorkItem]: List of matching work items

        Raises:
            ValidationError: Invalid filter parameters
            ProjectNotFoundError: Project doesn't exist
            ExternalServiceError: Service communication failure
        """
        pass

    @abstractmethod
    async def search_work_items(
        self,
        query: str,
        project_id: Optional[ProjectId] = None,
        limit: int = 100,
    ) -> List[WorkItem]:
        """
        Full-text search for work items.

        Args:
            query: Search query string
            project_id: Optional project filter
            limit: Maximum number of results

        Returns:
            List[WorkItem]: List of matching work items

        Raises:
            ProjectNotFoundError: Project doesn't exist
            ExternalServiceError: Service communication failure
        """
        pass

    @abstractmethod
    async def get_work_item_stream(
        self,
        project_id: Optional[ProjectId] = None,
        since: Optional[datetime] = None,
    ) -> AsyncIterator[WorkItem]:
        """
        Stream work item updates in real-time.

        Args:
            project_id: Optional project filter
            since: Only stream items updated since this timestamp

        Yields:
            WorkItem: Work items as they are created/updated

        Raises:
            ProjectNotFoundError: Project doesn't exist (if project_id specified)
            ExternalServiceError: Service communication failure
        """
        pass

    # Comment Operations

    @abstractmethod
    async def add_comment(
        self,
        item_id: WorkItemId,
        body: str,
        author: Optional[UserId] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Comment:
        """
        Add a comment to a work item.

        Args:
            item_id: Work item identifier
            body: Comment text
            author: Optional author user ID
            metadata: Optional additional metadata

        Returns:
            Comment: Newly created comment

        Raises:
            WorkItemNotFoundError: Work item doesn't exist
            ValidationError: Invalid comment data
            ExternalServiceError: Service communication failure
        """
        pass

    @abstractmethod
    async def get_comments(
        self,
        item_id: WorkItemId,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Comment]:
        """
        Get comments for a work item.

        Args:
            item_id: Work item identifier
            since: Only return comments created after this timestamp
            limit: Maximum number of comments to return

        Returns:
            List[Comment]: List of comments

        Raises:
            WorkItemNotFoundError: Work item doesn't exist
            ExternalServiceError: Service communication failure
        """
        pass

    # Relationship Operations

    @abstractmethod
    async def link_work_items(
        self,
        source_id: WorkItemId,
        target_id: WorkItemId,
        relationship: str,
    ) -> None:
        """
        Create relationship between work items.

        Common relationships: blocks, relates-to, parent-of, child-of

        Args:
            source_id: Source work item ID
            target_id: Target work item ID
            relationship: Type of relationship

        Raises:
            WorkItemNotFoundError: One or both work items don't exist
            ValidationError: Invalid relationship type
            ExternalServiceError: Service communication failure
        """
        pass

    @abstractmethod
    async def get_related_items(
        self,
        item_id: WorkItemId,
        relationship: Optional[str] = None,
    ) -> List[WorkItem]:
        """
        Get related work items.

        Args:
            item_id: Work item identifier
            relationship: Optional filter by relationship type

        Returns:
            List[WorkItem]: List of related work items

        Raises:
            WorkItemNotFoundError: Work item doesn't exist
            ExternalServiceError: Service communication failure
        """
        pass

    # Webhook Operations

    @abstractmethod
    async def register_webhook(
        self,
        url: str,
        events: List[str],
        project_id: Optional[ProjectId] = None,
    ) -> str:
        """
        Register a webhook for events.

        Args:
            url: Webhook URL to POST events to
            events: List of event types to subscribe to
            project_id: Optional project filter

        Returns:
            str: Webhook identifier

        Raises:
            ValidationError: Invalid webhook configuration
            ProjectNotFoundError: Project doesn't exist
            ExternalServiceError: Service communication failure
        """
        pass

    @abstractmethod
    async def unregister_webhook(self, webhook_id: str) -> None:
        """
        Unregister a webhook.

        Args:
            webhook_id: Webhook identifier

        Raises:
            ResourceNotFoundError: Webhook doesn't exist
            ExternalServiceError: Service communication failure
        """
        pass
