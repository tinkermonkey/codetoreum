"""Discussion and comment-related events for vendor-agnostic integration.

Events track comments and discussions on work items across different
vendor platforms (GitHub issues, Jira comments, etc.).

Terminology (vendor-agnostic):
- Comment: A text message on a work item (issue comment, PR comment, etc.)
- Discussion Thread: A threaded conversation on a work item
- Comment Context: Metadata about where and how a comment was made
"""

from dataclasses import dataclass
from typing import Optional
from uuid import uuid4

from .adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class Comment:
    """Represents a comment in the system."""

    id: str
    author: str
    body: str
    created_at: str
    parent_id: Optional[str] = None
    is_bot: bool = False

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
    """Context information about a comment's location and purpose."""

    thread_id: Optional[str] = None
    parent_comment: Optional[Comment] = None
    is_initial_request: bool = False
    column_name: str = ""
    agent_assignment: str = ""

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
    """Emitted when a comment requires a response from the system."""

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
        # Ensure comment and context are initialized if None
        if self.comment is None:
            object.__setattr__(self, "comment", Comment("", "", "", ""))
        if self.context is None:
            object.__setattr__(self, "context", CommentContext())

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "work_item_id": self.work_item_id,
            "project_id": self.project_id,
            "comment": self.comment.to_dict(),
            "context": self.context.to_dict(),
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "CommentNeedsResponseEvent":
        """Deserialize from dictionary."""
        comment = Comment.from_dict(data.get("comment", {}))
        context = CommentContext.from_dict(data.get("context", {}))

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
    """Emitted when a comment is posted to a work item."""

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
        # Ensure comment is initialized if None
        if self.comment is None:
            object.__setattr__(self, "comment", Comment("", "", "", ""))

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "work_item_id": self.work_item_id,
            "project_id": self.project_id,
            "comment": self.comment.to_dict(),
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "CommentPostedEvent":
        """Deserialize from dictionary."""
        comment = Comment.from_dict(data.get("comment", {}))

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
