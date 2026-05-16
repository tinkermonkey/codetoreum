"""Discussion and comment-related events for vendor-agnostic integration.

Events track comments and discussions on work items across different
vendor platforms (GitHub issues, Jira comments, etc.).

Terminology (vendor-agnostic):
- Comment: A text message on a work item (issue comment, PR comment, etc.)
- Discussion Thread: A threaded conversation on a work item
- Comment Context: Metadata about where and how a comment was made
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from .adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class Comment:
    """Represents a comment in the system.

    **Immutability**: This is an immutable object (frozen dataclass). All fields
    are read-only after construction to ensure data integrity and thread safety.
    Events and value objects in the event sourcing system must be immutable to
    prevent accidental modifications. Attempting to modify any field will raise
    `FrozenInstanceError`.

    Attributes:
        id (str): Unique identifier for the comment
        author (str): Username of the comment author
        body (str): The text content of the comment
        created_at (str): ISO 8601 timestamp when the comment was created
        parent_id (Optional[str]): ID of parent comment if this is a reply, None if top-level
        is_bot (bool): Whether the comment was authored by a bot (default: False)

    Example:
        >>> comment = Comment(
        ...     id="comment-1",
        ...     author="user123",
        ...     body="This is a comment",
        ...     created_at="2025-01-14T10:30:00+00:00"
        ... )
        >>> comment.body = "Modified text"  # ❌ Raises FrozenInstanceError
    """

    id: str
    author: str
    body: str
    created_at: str
    parent_id: str | None = None
    is_bot: bool = False

    def __post_init__(self) -> None:
        """Validate comment after initialization."""
        if not self.id:
            msg = "Comment id is required"
            raise ValueError(msg)
        if not self.author:
            msg = "Comment author is required"
            raise ValueError(msg)
        if not self.body:
            msg = "Comment body is required"
            raise ValueError(msg)
        if not self.created_at:
            msg = "Comment created_at is required"
            raise ValueError(msg)
        # Validate ISO 8601 timestamp
        try:
            datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as e:
            msg = f"created_at must be ISO 8601 format: {e}"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
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
    def from_dict(cls, data: dict[str, Any]) -> "Comment":
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

    **Immutability**: This is an immutable object (frozen dataclass). All fields
    are read-only after construction to ensure data integrity and thread safety.
    Events and value objects in the event sourcing system must be immutable to
    prevent accidental modifications. Attempting to modify any field will raise
    `FrozenInstanceError`.

    **Invariants Enforced**:
    - If `is_initial_request=True`, then `parent_comment` must be None (initial requests
      cannot be replies to other comments)
    - If `parent_comment` is not None, then `thread_id` must be set (replies require
      threading context)

    Attributes:
        thread_id (Optional[str]): ID of the discussion thread, None if not part of thread
        parent_comment (Optional[Comment]): The parent comment if this is a reply, None otherwise
        is_initial_request (bool): Whether this is the initial request comment (default: False)
        column_name (Optional[str]): Name of the board column where comment was made, None if not applicable
        agent_assignment (Optional[str]): Agent assigned to handle the comment, None if unassigned

    Example:
        >>> context = CommentContext(
        ...     thread_id="thread-1",
        ...     is_initial_request=True,
        ...     column_name="In Progress"
        ... )
        >>> context.column_name = "Review"  # ❌ Raises FrozenInstanceError

    Example: Creating an initial request (factory method recommended)
        >>> context = CommentContext.for_initial_request(
        ...     column_name="Backlog",
        ...     agent_assignment="agent-1"
        ... )

    Example: Creating a reply to a parent comment (factory method recommended)
        >>> parent = Comment(id="c1", author="alice", body="original", created_at="...")
        >>> context = CommentContext.for_reply(
        ...     thread_id="thread-1",
        ...     parent_comment=parent,
        ... )
    """

    thread_id: str | None = None
    parent_comment: Comment | None = None
    is_initial_request: bool = False
    column_name: str | None = None
    agent_assignment: str | None = None

    def __post_init__(self) -> None:
        """Validate comment context after initialization."""
        # Invariant 1: Initial requests cannot have parent comments
        if self.is_initial_request and self.parent_comment is not None:
            msg = (
                "Initial requests cannot have parent comments. A comment cannot be both an initial request and a reply."
            )
            raise ValueError(msg)

        # Invariant 2: Replies with parent comments must have thread_id
        if self.parent_comment is not None and not self.thread_id:
            msg = (
                "Replies with parent comments must have thread_id. "
                "Threading context is required to track discussion relationships."
            )
            raise ValueError(msg)

    @classmethod
    def for_initial_request(
        cls,
        column_name: str | None = None,
        agent_assignment: str | None = None,
    ) -> "CommentContext":
        """Factory method to create context for an initial request comment.

        Use this when creating context for the initial/first comment on a work item.
        This ensures that `is_initial_request=True` and `parent_comment=None`,
        which satisfies the type invariants.

        Args:
            column_name: Name of the board column where comment was made (optional)
            agent_assignment: Agent assigned to handle the comment (optional)

        Returns:
            CommentContext: Context configured for an initial request

        Example:
            >>> context = CommentContext.for_initial_request(
            ...     column_name="Backlog",
            ...     agent_assignment="agent-1"
            ... )
            >>> context.is_initial_request
            True
            >>> context.parent_comment
            None
        """
        return cls(
            thread_id=None,
            parent_comment=None,
            is_initial_request=True,
            column_name=column_name,
            agent_assignment=agent_assignment,
        )

    @classmethod
    def for_reply(
        cls,
        thread_id: str,
        parent_comment: Comment,
        column_name: str | None = None,
        agent_assignment: str | None = None,
    ) -> "CommentContext":
        """Factory method to create context for a reply to a parent comment.

        Use this when creating context for a reply/follow-up comment in a discussion thread.
        This ensures that `thread_id` is set, `parent_comment` is provided, and
        `is_initial_request=False`, which satisfies the type invariants.

        Args:
            thread_id: ID of the discussion thread
            parent_comment: The parent comment being replied to
            column_name: Name of the board column where comment was made (optional)
            agent_assignment: Agent assigned to handle the comment (optional)

        Returns:
            CommentContext: Context configured for a reply

        Raises:
            ValueError: If thread_id is empty or parent_comment is None

        Example:
            >>> parent = Comment(id="c1", author="alice", body="original", created_at="...")
            >>> context = CommentContext.for_reply(
            ...     thread_id="thread-1",
            ...     parent_comment=parent,
            ...     column_name="Review"
            ... )
            >>> context.is_initial_request
            False
            >>> context.parent_comment.id
            'c1'
        """
        if not thread_id:
            msg = "thread_id cannot be empty for replies"
            raise ValueError(msg)
        if parent_comment is None:
            msg = "parent_comment cannot be None for replies"
            raise ValueError(msg)

        return cls(
            thread_id=thread_id,
            parent_comment=parent_comment,
            is_initial_request=False,
            column_name=column_name,
            agent_assignment=agent_assignment,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "thread_id": self.thread_id,
            "parent_comment": self.parent_comment.to_dict() if self.parent_comment else None,
            "is_initial_request": self.is_initial_request,
            "column_name": self.column_name,
            "agent_assignment": self.agent_assignment,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CommentContext":
        """Deserialize from dictionary."""
        parent = None
        if data.get("parent_comment"):
            parent = Comment.from_dict(data["parent_comment"])

        return cls(
            thread_id=data.get("thread_id"),
            parent_comment=parent,
            is_initial_request=data.get("is_initial_request", False),
            column_name=data.get("column_name"),
            agent_assignment=data.get("agent_assignment"),
        )


@dataclass(frozen=True)
class CommentNeedsResponseEvent(CodetoreumEvent):
    """Emitted when a comment requires a response from the system.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Attributes:
        type (str): Fixed to "comment.needs_response"
        work_item_id (str): ID of the work item containing the comment
        project_id (str): ID of the project containing the work item
        comment (Optional[Comment]): The comment object requiring response, None if not available
        context (Optional[CommentContext]): Context information about the comment, None if not available

    Example:
        >>> event = CommentNeedsResponseEvent(
        ...     type="comment.needs_response",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="github",
        ...     work_item_id="issue-1",
        ...     project_id="proj-1"
        ... )
        >>> event.work_item_id = "issue-2"  # ❌ Raises FrozenInstanceError
    """

    work_item_id: str = ""
    project_id: str = ""
    comment: Comment | None = None
    context: CommentContext | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        # Note: comment and context are optional and can be None
        # Do not auto-initialize them as this prevents tests from checking None handling

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "project_id": self.project_id,
                "comment": self.comment.to_dict() if self.comment else None,
                "context": self.context.to_dict() if self.context else None,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CommentNeedsResponseEvent":
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

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Attributes:
        type (str): Fixed to "comment.posted"
        work_item_id (str): ID of the work item where comment was posted
        project_id (str): ID of the project containing the work item
        comment (Optional[Comment]): The comment object that was posted, None if not available

    Example:
        >>> event = CommentPostedEvent(
        ...     type="comment.posted",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="github",
        ...     work_item_id="issue-1",
        ...     project_id="proj-1"
        ... )
        >>> event.project_id = "proj-2"  # ❌ Raises FrozenInstanceError
    """

    work_item_id: str = ""
    project_id: str = ""
    comment: Comment | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        # Note: comment is optional and can be None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "project_id": self.project_id,
                "comment": self.comment.to_dict() if self.comment else None,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CommentPostedEvent":
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


@dataclass(frozen=True)
class AgentResponsePostedEvent(CodetoreumEvent):
    """Emitted when an agent posts a response to a human comment.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    **Purpose**: This event tracks the posting of agent responses in conversational
    feedback loops, enabling session persistence and audit trail reconstruction. It
    includes LLM conversation context for session continuity across interactions.

    Attributes:
        type (str): Fixed to "agent.response_posted"
        work_item_id (str): ID of the work item the response was posted to
        project_id (str): ID of the project containing the work item
        comment_id (str): ID of the human comment being responded to
        response_comment_id (str): ID of the agent's response comment posted by the adapter
        agent_name (str): Name of the agent posting the response
        conversation_id (Optional[str]): LLM conversation session ID for context continuity
        timestamp (str): ISO 8601 timestamp when response was posted

    Example:
        >>> event = AgentResponsePostedEvent(
        ...     type="agent.response_posted",
        ...     timestamp="2025-01-14T10:35:00+00:00",
        ...     source="orchestrator",
        ...     work_item_id="issue-1",
        ...     project_id="proj-1",
        ...     comment_id="comment-42",
        ...     response_comment_id="comment-43",
        ...     agent_name="code-reviewer",
        ...     conversation_id="conv-session-123"
        ... )
        >>> event.agent_name = "different-agent"  # ❌ Raises FrozenInstanceError
    """

    work_item_id: str = ""
    project_id: str = ""
    comment_id: str = ""
    response_comment_id: str = ""
    agent_name: str = ""
    conversation_id: str | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        if not self.comment_id:
            msg = "comment_id is required"
            raise ValueError(msg)
        if not self.response_comment_id:
            msg = "response_comment_id is required"
            raise ValueError(msg)
        if not self.agent_name:
            msg = "agent_name is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "project_id": self.project_id,
                "comment_id": self.comment_id,
                "response_comment_id": self.response_comment_id,
                "agent_name": self.agent_name,
                "conversation_id": self.conversation_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentResponsePostedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "agent.response_posted"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            project_id=data.get("project_id", ""),
            comment_id=data.get("comment_id", ""),
            response_comment_id=data.get("response_comment_id", ""),
            agent_name=data.get("agent_name", ""),
            conversation_id=data.get("conversation_id"),
        )


@dataclass(frozen=True)
class ConversationalLoopStartedEvent(CodetoreumEvent):
    """Emitted when a conversational loop session starts for a work item.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Attributes:
        type (str): Fixed to "conversational_loop.started"
        work_item_id (str): ID of the work item for which the loop started
        project_id (str): ID of the project containing the work item
        session_id (str): Unique identifier for this conversational session
        agent_assignment (str): The agent assigned to this conversational loop
        column_name (Optional[str]): Name of the board column where the loop started

    Example:
        >>> event = ConversationalLoopStartedEvent(
        ...     type="conversational_loop.started",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="orchestrator",
        ...     work_item_id="issue-1",
        ...     project_id="proj-1",
        ...     session_id="session-abc",
        ...     agent_assignment="code-reviewer"
        ... )
        >>> event.session_id = "new-session"  # ❌ Raises FrozenInstanceError
    """

    work_item_id: str = ""
    project_id: str = ""
    session_id: str = ""
    agent_assignment: str = ""
    column_name: str | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        if not self.session_id:
            msg = "session_id is required"
            raise ValueError(msg)
        if not self.agent_assignment:
            msg = "agent_assignment is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "project_id": self.project_id,
                "session_id": self.session_id,
                "agent_assignment": self.agent_assignment,
                "column_name": self.column_name,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationalLoopStartedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "conversational_loop.started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            project_id=data.get("project_id", ""),
            session_id=data.get("session_id", ""),
            agent_assignment=data.get("agent_assignment", ""),
            column_name=data.get("column_name"),
        )


@dataclass(frozen=True)
class FeedbackListeningStartedEvent(CodetoreumEvent):
    """Emitted when the system begins listening for feedback on a work item session.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Attributes:
        type (str): Fixed to "feedback_listening.started"
        work_item_id (str): ID of the work item being listened for
        project_id (str): ID of the project containing the work item
        session_id (str): Unique identifier for the conversational session

    Example:
        >>> event = FeedbackListeningStartedEvent(
        ...     type="feedback_listening.started",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="orchestrator",
        ...     work_item_id="issue-1",
        ...     project_id="proj-1",
        ...     session_id="session-abc"
        ... )
        >>> event.session_id = "new-session"  # ❌ Raises FrozenInstanceError
    """

    work_item_id: str = ""
    project_id: str = ""
    session_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        if not self.session_id:
            msg = "session_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "project_id": self.project_id,
                "session_id": self.session_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FeedbackListeningStartedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "feedback_listening.started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            project_id=data.get("project_id", ""),
            session_id=data.get("session_id", ""),
        )


@dataclass(frozen=True)
class FeedbackListeningStoppedEvent(CodetoreumEvent):
    """Emitted when the system stops listening for feedback on a work item session.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Attributes:
        type (str): Fixed to "feedback_listening.stopped"
        work_item_id (str): ID of the work item being listened for
        project_id (str): ID of the project containing the work item
        session_id (str): Unique identifier for the conversational session
        feedback_type (str): Reason listening stopped. One of "card_advance",
                             "error", or "manual".

    Example:
        >>> event = FeedbackListeningStoppedEvent(
        ...     type="feedback_listening.stopped",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="orchestrator",
        ...     work_item_id="issue-1",
        ...     project_id="proj-1",
        ...     session_id="session-abc",
        ...     feedback_type="card_advance"
        ... )
        >>> event.feedback_type = "manual"  # ❌ Raises FrozenInstanceError
    """

    work_item_id: str = ""
    project_id: str = ""
    session_id: str = ""
    feedback_type: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        if not self.session_id:
            msg = "session_id is required"
            raise ValueError(msg)
        valid_feedback_types = {"card_advance", "error", "manual"}
        if self.feedback_type not in valid_feedback_types:
            msg = f"feedback_type must be one of {valid_feedback_types}, got {self.feedback_type!r}"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "project_id": self.project_id,
                "session_id": self.session_id,
                "feedback_type": self.feedback_type,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FeedbackListeningStoppedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "feedback_listening.stopped"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            project_id=data.get("project_id", ""),
            session_id=data.get("session_id", ""),
            feedback_type=data.get("feedback_type", ""),
        )
