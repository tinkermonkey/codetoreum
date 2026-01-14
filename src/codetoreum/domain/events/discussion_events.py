"""Discussion and comment-related events for vendor-agnostic integration.

Events track comments and discussions on work items across different
vendor platforms (GitHub issues, Jira comments, etc.).

Terminology (vendor-agnostic):
- Comment: A text message on a work item (issue comment, PR comment, etc.)
- Discussion Thread: A threaded conversation on a work item
- Comment Context: Metadata about where and how a comment was made
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from .adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class Comment:
    """Represents a comment in the system.

    **Note**: This is an immutable object (frozen dataclass). All fields are
    read-only after construction to maintain data integrity.

    Attributes:
        id (str): Unique identifier for the comment
        author (str): Username of the comment author
        body (str): The text content of the comment
        created_at (str): ISO 8601 timestamp when the comment was created
        parent_id (Optional[str]): ID of parent comment if this is a reply, None if top-level
        is_bot (bool): Whether the comment was authored by a bot (default: False)
    """

    id: str
    author: str
    body: str
    created_at: str
    parent_id: Optional[str] = None
    is_bot: bool = False

    def __post_init__(self) -> None:
        """Validate comment after initialization."""
        if not self.id:
            raise ValueError("Comment id is required")
        if not self.author:
            raise ValueError("Comment author is required")
        if not self.body:
            raise ValueError("Comment body is required")
        if not self.created_at:
            raise ValueError("Comment created_at is required")
        # Validate ISO 8601 timestamp
        try:
            datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as e:
            raise ValueError(f"created_at must be ISO 8601 format: {e}")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "author": self.author,
            "body": self.body,
            "created_at": self.created_at,
            "parent_id": self.parent_id,
            "is_bot": self.is_bot,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Comment":
        """Deserialize from dictionary."""
        return cls(
            id=data.get("id", ""),
            author=data.get("author", ""),
            body=data.get("body", ""),
            created_at=data.get("created_at", ""),
            parent_id=data.get("parent_id"),
            is_bot=data.get("is_bot", False),
        )


@dataclass(frozen=True)
class CommentContext:
    """Context information about a comment's location and purpose.

    **Note**: This is an immutable object (frozen dataclass). All fields are
    read-only after construction to maintain data integrity.

    Attributes:
        thread_id (Optional[str]): ID of the discussion thread, None if not part of thread
        parent_comment (Optional[Comment]): The parent comment if this is a reply, None otherwise
        is_initial_request (bool): Whether this is the initial request comment (default: False)
        column_name (str): Name of the board column where comment was made (empty if not applicable)
        agent_assignment (str): Agent assigned to handle the comment (empty if unassigned)
    """

    thread_id: Optional[str] = None
    parent_comment: Optional[Comment] = None
    is_initial_request: bool = False
    column_name: str = ""
    agent_assignment: str = ""

    def __post_init__(self) -> None:
        """Validate comment context after initialization."""
        # thread_id is optional, no validation needed
        # parent_comment is optional, but if provided it's a Comment object (validated by Comment)
        # is_initial_request is bool, no validation needed
        # column_name is optional (can be empty), no validation needed
        # agent_assignment is optional (can be empty), no validation needed
        # No required string fields to validate for CommentContext

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "thread_id": self.thread_id,
            "parent_comment": self.parent_comment.to_dict() if self.parent_comment else None,
            "is_initial_request": self.is_initial_request,
            "column_name": self.column_name,
            "agent_assignment": self.agent_assignment,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CommentContext":
        """Deserialize from dictionary."""
        parent = None
        if data.get("parent_comment"):
            parent = Comment.from_dict(data["parent_comment"])

        return cls(
            thread_id=data.get("thread_id"),
            parent_comment=parent,
            is_initial_request=data.get("is_initial_request", False),
            column_name=data.get("column_name", ""),
            agent_assignment=data.get("agent_assignment", ""),
        )


@dataclass(frozen=True)
class CommentNeedsResponseEvent(CodetoreumEvent):
    """Emitted when a comment requires a response from the system.

    **Note**: This is an immutable event (frozen dataclass). All fields are
    read-only after construction to maintain audit trail integrity per the
    event sourcing architecture.

    Attributes:
        type (str): Fixed to "comment.needs_response"
        work_item_id (str): ID of the work item containing the comment
        project_id (str): ID of the project containing the work item
        comment (Optional[Comment]): The comment object requiring response, None if not available
        context (Optional[CommentContext]): Context information about the comment, None if not available
    """

    work_item_id: str = ""
    project_id: str = ""
    comment: Optional[Comment] = None
    context: Optional[CommentContext] = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            raise ValueError("work_item_id is required")
        if not self.project_id:
            raise ValueError("project_id is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "work_item_id": self.work_item_id,
            "project_id": self.project_id,
            "comment": self.comment.to_dict() if self.comment else None,
            "context": self.context.to_dict() if self.context else None,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "CommentNeedsResponseEvent":
        """Deserialize from dictionary."""
        comment = Comment.from_dict(data.get("comment", {})) if data.get("comment") else None
        context = CommentContext.from_dict(data.get("context", {})) if data.get("context") else None

        return cls(
            type=data.get("type", "comment.needs_response"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            project_id=data.get("project_id", ""),
            comment=comment,
            context=context,
        )


@dataclass(frozen=True)
class CommentPostedEvent(CodetoreumEvent):
    """Emitted when a comment is posted to a work item.

    **Note**: This is an immutable event (frozen dataclass). All fields are
    read-only after construction to maintain audit trail integrity per the
    event sourcing architecture.

    Attributes:
        type (str): Fixed to "comment.posted"
        work_item_id (str): ID of the work item where comment was posted
        project_id (str): ID of the project containing the work item
        comment (Optional[Comment]): The comment object that was posted, None if not available
    """

    work_item_id: str = ""
    project_id: str = ""
    comment: Optional[Comment] = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            raise ValueError("work_item_id is required")
        if not self.project_id:
            raise ValueError("project_id is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "work_item_id": self.work_item_id,
            "project_id": self.project_id,
            "comment": self.comment.to_dict() if self.comment else None,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "CommentPostedEvent":
        """Deserialize from dictionary."""
        comment = Comment.from_dict(data.get("comment", {})) if data.get("comment") else None

        return cls(
            type=data.get("type", "comment.posted"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            project_id=data.get("project_id", ""),
            comment=comment,
        )
