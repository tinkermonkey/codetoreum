"""Unit tests for discussion and comment events."""

import pytest
from dataclasses import FrozenInstanceError

from codetoreum.domain.events import (
    Comment,
    CommentContext,
    CommentNeedsResponseEvent,
    CommentPostedEvent,
    AgentResponsePostedEvent,
    now_iso,
)


class TestComment:
    """Test the Comment class."""

    def test_create_valid_comment(self):
        """Test creating a valid comment."""
        comment = Comment(
            id="comment-123",
            author="alice",
            body="This needs clarification",
            created_at=now_iso(),
            is_bot=False,
        )

        assert comment.id == "comment-123"
        assert comment.author == "alice"
        assert comment.body == "This needs clarification"
        assert comment.is_bot is False
        assert comment.parent_id is None

    def test_comment_as_reply(self):
        """Test creating a comment as a reply."""
        comment = Comment(
            id="comment-456",
            author="bot",
            body="I addressed that",
            created_at=now_iso(),
            parent_id="comment-123",
            is_bot=True,
        )

        assert comment.parent_id == "comment-123"
        assert comment.is_bot is True

    def test_comment_serialization(self):
        """Test comment serialization."""
        timestamp = now_iso()
        comment = Comment(
            id="c1",
            author="alice",
            body="test",
            created_at=timestamp,
            parent_id="c0",
            is_bot=False,
        )

        d = comment.to_dict()

        assert d["id"] == "c1"
        assert d["author"] == "alice"
        assert d["parent_id"] == "c0"

    def test_comment_deserialization(self):
        """Test comment deserialization."""
        timestamp = now_iso()
        d = {
            "id": "c1",
            "author": "alice",
            "body": "test",
            "created_at": timestamp,
            "parent_id": "c0",
            "is_bot": False,
        }

        comment = Comment.from_dict(d)

        assert comment.id == "c1"
        assert comment.parent_id == "c0"

    def test_comment_empty_id_raises_error(self):
        """Test that empty id raises ValueError."""
        with pytest.raises(ValueError, match="Comment id is required"):
            Comment(id="", author="alice", body="text", created_at=now_iso())

    def test_comment_empty_author_raises_error(self):
        """Test that empty author raises ValueError."""
        with pytest.raises(ValueError, match="Comment author is required"):
            Comment(id="c1", author="", body="text", created_at=now_iso())

    def test_comment_empty_body_raises_error(self):
        """Test that empty body raises ValueError."""
        with pytest.raises(ValueError, match="Comment body is required"):
            Comment(id="c1", author="alice", body="", created_at=now_iso())

    def test_comment_empty_created_at_raises_error(self):
        """Test that empty created_at raises ValueError."""
        with pytest.raises(ValueError, match="Comment created_at is required"):
            Comment(id="c1", author="alice", body="text", created_at="")

    def test_comment_invalid_iso8601_format_raises_error(self):
        """Test that invalid ISO 8601 format raises ValueError."""
        with pytest.raises(ValueError, match="created_at must be ISO 8601 format"):
            Comment(id="c1", author="alice", body="text", created_at="not-a-timestamp")

    def test_comment_created_at_with_z_suffix(self):
        """Test that ISO 8601 format with 'Z' suffix is accepted."""
        comment = Comment(
            id="c1",
            author="alice",
            body="text",
            created_at="2024-01-15T10:30:00Z"
        )
        assert comment.created_at == "2024-01-15T10:30:00Z"

    def test_comment_created_at_with_timezone_offset(self):
        """Test that ISO 8601 format with timezone offset is accepted."""
        comment = Comment(
            id="c1",
            author="alice",
            body="text",
            created_at="2024-01-15T10:30:00+00:00"
        )
        assert comment.created_at == "2024-01-15T10:30:00+00:00"

    def test_comment_immutability(self):
        """Test that Comment instances are immutable."""
        comment = Comment(
            id="c1",
            author="alice",
            body="text",
            created_at=now_iso()
        )

        with pytest.raises(FrozenInstanceError):
            comment.id = "c2"


class TestCommentContext:
    """Test the CommentContext class."""

    def test_create_valid_context(self):
        """Test creating a valid comment context."""
        context = CommentContext(
            thread_id="thread-1",
            is_initial_request=False,
            column_name="In Progress",
            agent_assignment="agent-123",
        )

        assert context.thread_id == "thread-1"
        assert context.is_initial_request is False
        assert context.column_name == "In Progress"

    def test_context_with_parent_comment(self):
        """Test context with parent comment."""
        parent = Comment(
            id="p1",
            author="alice",
            body="original",
            created_at=now_iso(),
        )

        context = CommentContext(
            parent_comment=parent,
            is_initial_request=False,
        )

        assert context.parent_comment == parent

    def test_context_initial_request(self):
        """Test context marked as initial request."""
        context = CommentContext(
            is_initial_request=True,
            column_name="Backlog",
        )

        assert context.is_initial_request is True

    def test_context_serialization(self):
        """Test context serialization."""
        parent = Comment(
            id="p1",
            author="alice",
            body="original",
            created_at=now_iso(),
        )

        context = CommentContext(
            thread_id="t1",
            parent_comment=parent,
            is_initial_request=True,
            column_name="Backlog",
            agent_assignment="a1",
        )

        d = context.to_dict()

        assert d["thread_id"] == "t1"
        assert d["is_initial_request"] is True
        assert d["parent_comment"]["id"] == "p1"

    def test_context_deserialization(self):
        """Test context deserialization."""
        d = {
            "thread_id": "t1",
            "parent_comment": {
                "id": "p1",
                "author": "alice",
                "body": "test",
                "created_at": now_iso(),
            },
            "is_initial_request": True,
            "column_name": "Backlog",
            "agent_assignment": "a1",
        }

        context = CommentContext.from_dict(d)

        assert context.thread_id == "t1"
        assert context.parent_comment is not None
        assert context.parent_comment.id == "p1"

    def test_context_immutability(self):
        """Test that CommentContext instances are immutable."""
        context = CommentContext(
            thread_id="t1",
            column_name="Backlog"
        )

        with pytest.raises(FrozenInstanceError):
            context.thread_id = "t2"

    def test_context_with_invalid_parent_comment_raises_error(self):
        """Test that CommentContext with invalid parent Comment raises error."""
        # The invalid comment will raise during Comment.__post_init__
        with pytest.raises(ValueError, match="Comment id is required"):
            CommentContext(
                parent_comment=Comment(id="", author="alice", body="test", created_at=now_iso())
            )

    def test_context_serialization_roundtrip(self):
        """Test context serialization and deserialization roundtrip."""
        parent = Comment(
            id="p1",
            author="alice",
            body="original",
            created_at=now_iso(),
        )

        original = CommentContext(
            thread_id="t1",
            parent_comment=parent,
            is_initial_request=True,
            column_name="Backlog",
            agent_assignment="a1",
        )

        d = original.to_dict()
        restored = CommentContext.from_dict(d)

        assert restored.thread_id == original.thread_id
        assert restored.is_initial_request == original.is_initial_request
        assert restored.column_name == original.column_name
        assert restored.agent_assignment == original.agent_assignment
        assert restored.parent_comment.id == original.parent_comment.id


class TestCommentNeedsResponseEvent:
    """Test CommentNeedsResponseEvent."""

    def test_create_valid_event(self):
        """Test creating a valid comment needs response event."""
        comment = Comment(
            id="c1",
            author="alice",
            body="How will this scale?",
            created_at=now_iso(),
        )

        context = CommentContext(
            thread_id="t1",
            column_name="Review",
            agent_assignment="reviewer",
        )

        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            comment=comment,
            context=context,
        )

        assert event.work_item_id == "123"
        assert event.comment.author == "alice"
        assert event.context.column_name == "Review"

    def test_missing_work_item_id(self):
        """Test that work_item_id is required."""
        comment = Comment(
            id="c1",
            author="alice",
            body="test",
            created_at=now_iso(),
        )

        with pytest.raises(ValueError, match="work_item_id"):
            CommentNeedsResponseEvent(
                type="comment.needs_response",
                timestamp=now_iso(),
                source="github",
                work_item_id="",  # Empty
                project_id="proj-1",
                comment=comment,
            )

    def test_comment_needs_response_serialization(self):
        """Test comment needs response event serialization."""
        timestamp = now_iso()
        comment = Comment(
            id="c1",
            author="alice",
            body="test",
            created_at=timestamp,
        )

        context = CommentContext(
            column_name="Review",
            agent_assignment="a1",
        )

        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=timestamp,
            source="github",
            correlation_id="corr-1",
            work_item_id="123",
            project_id="proj-1",
            comment=comment,
            context=context,
        )

        d = event.to_dict()

        assert d["work_item_id"] == "123"
        assert d["comment"]["author"] == "alice"
        assert d["context"]["column_name"] == "Review"

    def test_comment_needs_response_roundtrip(self):
        """Test comment needs response event roundtrip."""
        timestamp = now_iso()
        comment = Comment(
            id="c1",
            author="alice",
            body="test feedback",
            created_at=timestamp,
        )

        context = CommentContext(
            column_name="Review",
        )

        original = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=timestamp,
            source="github",
            work_item_id="123",
            project_id="proj-1",
            comment=comment,
            context=context,
        )

        d = original.to_dict()
        restored = CommentNeedsResponseEvent.from_dict(d)

        assert restored.work_item_id == original.work_item_id
        assert restored.comment.author == original.comment.author


class TestCommentPostedEvent:
    """Test CommentPostedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid comment posted event."""
        comment = Comment(
            id="c1",
            author="alice",
            body="This looks good",
            created_at=now_iso(),
            is_bot=False,
        )

        event = CommentPostedEvent(
            type="comment.posted",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            comment=comment,
        )

        assert event.work_item_id == "123"
        assert event.comment.author == "alice"

    def test_comment_posted_bot(self):
        """Test comment posted by bot."""
        comment = Comment(
            id="c1",
            author="codetoreum-bot",
            body="Fix applied",
            created_at=now_iso(),
            is_bot=True,
        )

        event = CommentPostedEvent(
            type="comment.posted",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            comment=comment,
        )

        assert event.comment.is_bot is True

    def test_comment_posted_serialization(self):
        """Test comment posted event serialization."""
        timestamp = now_iso()
        comment = Comment(
            id="c1",
            author="alice",
            body="test",
            created_at=timestamp,
        )

        event = CommentPostedEvent(
            type="comment.posted",
            timestamp=timestamp,
            source="github",
            work_item_id="123",
            project_id="proj-1",
            comment=comment,
        )

        d = event.to_dict()

        assert d["work_item_id"] == "123"
        assert d["comment"]["author"] == "alice"

    def test_comment_posted_roundtrip(self):
        """Test comment posted event roundtrip."""
        timestamp = now_iso()
        comment = Comment(
            id="c1",
            author="alice",
            body="Great work!",
            created_at=timestamp,
        )

        original = CommentPostedEvent(
            type="comment.posted",
            timestamp=timestamp,
            source="jira",
            correlation_id="corr-2",
            work_item_id="456",
            project_id="proj-2",
            comment=comment,
        )

        d = original.to_dict()
        restored = CommentPostedEvent.from_dict(d)

        assert restored.work_item_id == original.work_item_id
        assert restored.comment.body == original.comment.body
        assert restored.source == "jira"


class TestCommentImmutability:
    """Test immutability of Comment class (frozen dataclass)."""

    def test_comment_is_frozen(self):
        """Test that Comment is immutable (frozen dataclass)."""
        comment = Comment(
            id="comment-123",
            author="alice",
            body="This needs clarification",
            created_at=now_iso(),
            is_bot=False,
        )

        # Verify the comment is properly created
        assert comment.id == "comment-123"
        assert comment.author == "alice"
        assert comment.body == "This needs clarification"
        assert comment.is_bot is False

        # Comment is a frozen dataclass, so attempting to modify
        # any attribute should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            comment.id = "comment-456"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            comment.author = "bob"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            comment.body = "Different text"  # type: ignore

    def test_comment_bot_immutability(self):
        """Test immutability of bot comment (frozen dataclass)."""
        comment = Comment(
            id="bot-comment-1",
            author="codetoreum-bot",
            body="I've addressed the issue",
            created_at=now_iso(),
            is_bot=True,
            parent_id="comment-123",
        )

        # Verify comment attributes
        assert comment.is_bot is True
        assert comment.parent_id == "comment-123"

        # Comment is frozen, so modification should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            comment.is_bot = False  # type: ignore

        with pytest.raises(FrozenInstanceError):
            comment.parent_id = "comment-456"  # type: ignore


class TestCommentContextImmutability:
    """Test immutability of CommentContext class (frozen dataclass)."""

    def test_comment_context_is_frozen(self):
        """Test that CommentContext is immutable (frozen dataclass)."""
        context = CommentContext(
            thread_id="thread-1",
            is_initial_request=False,
            column_name="In Progress",
            agent_assignment="agent-123",
        )

        # Verify the context is properly created
        assert context.thread_id == "thread-1"
        assert context.is_initial_request is False
        assert context.column_name == "In Progress"

        # CommentContext is a frozen dataclass, so attempting to modify
        # any attribute should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            context.thread_id = "thread-2"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            context.column_name = "Done"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            context.is_initial_request = True  # type: ignore

    def test_comment_context_with_parent_comment_immutability(self):
        """Test immutability of CommentContext with nested parent comment."""
        parent = Comment(
            id="p1",
            author="alice",
            body="original",
            created_at=now_iso(),
        )

        context = CommentContext(
            parent_comment=parent,
            is_initial_request=False,
        )

        # Verify nested comment is preserved
        assert context.parent_comment == parent
        assert context.parent_comment.id == "p1"

        # Nested comment is also frozen, so modification should fail
        with pytest.raises(FrozenInstanceError):
            context.parent_comment.author = "bob"  # type: ignore

        # And the context field itself cannot be reassigned
        with pytest.raises(FrozenInstanceError):
            context.parent_comment = Comment("p2", "alice", "different", now_iso())  # type: ignore


class TestCommentNeedsResponseEventImmutability:
    """Test immutability of CommentNeedsResponseEvent (frozen dataclass)."""

    def test_comment_needs_response_event_is_frozen(self):
        """Test that CommentNeedsResponseEvent is immutable (frozen dataclass)."""
        comment = Comment(
            id="c1",
            author="alice",
            body="How will this scale?",
            created_at=now_iso(),
        )

        context = CommentContext(
            thread_id="t1",
            column_name="Review",
            agent_assignment="reviewer",
        )

        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            comment=comment,
            context=context,
        )

        # Verify the event is properly created
        assert event.work_item_id == "123"
        assert event.comment.author == "alice"
        assert event.context.column_name == "Review"

        # CommentNeedsResponseEvent is a frozen dataclass, so attempting to modify
        # any attribute should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            event.work_item_id = "456"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.comment = Comment("c2", "bob", "Different comment", now_iso())  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.context = CommentContext(thread_id="t2")  # type: ignore


class TestCommentPostedEventImmutability:
    """Test immutability of CommentPostedEvent (frozen dataclass)."""

    def test_comment_posted_event_is_frozen(self):
        """Test that CommentPostedEvent is immutable (frozen dataclass)."""
        comment = Comment(
            id="c1",
            author="alice",
            body="This looks good",
            created_at=now_iso(),
            is_bot=False,
        )

        event = CommentPostedEvent(
            type="comment.posted",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            comment=comment,
        )

        # Verify the event is properly created
        assert event.work_item_id == "123"
        assert event.comment.author == "alice"
        assert event.comment.is_bot is False

        # CommentPostedEvent is a frozen dataclass, so attempting to modify
        # any attribute should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            event.work_item_id = "456"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.comment = Comment("c2", "bob", "Different comment", now_iso())  # type: ignore

    def test_comment_posted_event_bot_comment_immutability(self):
        """Test immutability of CommentPostedEvent with bot comment (frozen dataclass)."""
        comment = Comment(
            id="c1",
            author="codetoreum-bot",
            body="Fix applied",
            created_at=now_iso(),
            is_bot=True,
        )

        event = CommentPostedEvent(
            type="comment.posted",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            comment=comment,
        )

        # Verify bot comment is properly stored
        assert event.comment.is_bot is True
        assert event.comment.author == "codetoreum-bot"

        # Nested comment is frozen, so modification should fail
        with pytest.raises(FrozenInstanceError):
            event.comment.is_bot = False  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.comment.author = "alice"  # type: ignore


class TestAgentResponsePostedEvent:
    """Test AgentResponsePostedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid agent response posted event."""
        event = AgentResponsePostedEvent(
            type="agent.response_posted",
            timestamp=now_iso(),
            source="orchestrator",
            work_item_id="issue-1",
            project_id="proj-1",
            comment_id="comment-42",
            agent_name="code-reviewer",
            conversation_id="conv-session-123",
        )

        assert event.work_item_id == "issue-1"
        assert event.project_id == "proj-1"
        assert event.comment_id == "comment-42"
        assert event.agent_name == "code-reviewer"
        assert event.conversation_id == "conv-session-123"

    def test_create_without_conversation_id(self):
        """Test creating event without conversation_id (optional field)."""
        event = AgentResponsePostedEvent(
            type="agent.response_posted",
            timestamp=now_iso(),
            source="orchestrator",
            work_item_id="issue-1",
            project_id="proj-1",
            comment_id="comment-42",
            agent_name="code-reviewer",
        )

        assert event.conversation_id is None

    def test_missing_work_item_id(self):
        """Test that work_item_id is required."""
        with pytest.raises(ValueError, match="work_item_id is required"):
            AgentResponsePostedEvent(
                type="agent.response_posted",
                timestamp=now_iso(),
                source="orchestrator",
                work_item_id="",  # Empty
                project_id="proj-1",
                comment_id="comment-42",
                agent_name="code-reviewer",
            )

    def test_missing_project_id(self):
        """Test that project_id is required."""
        with pytest.raises(ValueError, match="project_id is required"):
            AgentResponsePostedEvent(
                type="agent.response_posted",
                timestamp=now_iso(),
                source="orchestrator",
                work_item_id="issue-1",
                project_id="",  # Empty
                comment_id="comment-42",
                agent_name="code-reviewer",
            )

    def test_missing_comment_id(self):
        """Test that comment_id is required."""
        with pytest.raises(ValueError, match="comment_id is required"):
            AgentResponsePostedEvent(
                type="agent.response_posted",
                timestamp=now_iso(),
                source="orchestrator",
                work_item_id="issue-1",
                project_id="proj-1",
                comment_id="",  # Empty
                agent_name="code-reviewer",
            )

    def test_missing_agent_name(self):
        """Test that agent_name is required."""
        with pytest.raises(ValueError, match="agent_name is required"):
            AgentResponsePostedEvent(
                type="agent.response_posted",
                timestamp=now_iso(),
                source="orchestrator",
                work_item_id="issue-1",
                project_id="proj-1",
                comment_id="comment-42",
                agent_name="",  # Empty
            )

    def test_agent_response_posted_serialization(self):
        """Test agent response posted event serialization."""
        timestamp = now_iso()
        event = AgentResponsePostedEvent(
            type="agent.response_posted",
            timestamp=timestamp,
            source="orchestrator",
            correlation_id="corr-1",
            work_item_id="issue-1",
            project_id="proj-1",
            comment_id="comment-42",
            agent_name="code-reviewer",
            conversation_id="conv-abc123",
        )

        d = event.to_dict()

        assert d["work_item_id"] == "issue-1"
        assert d["project_id"] == "proj-1"
        assert d["comment_id"] == "comment-42"
        assert d["agent_name"] == "code-reviewer"
        assert d["conversation_id"] == "conv-abc123"
        assert d["timestamp"] == timestamp

    def test_agent_response_posted_roundtrip(self):
        """Test agent response posted event roundtrip."""
        timestamp = now_iso()
        event = AgentResponsePostedEvent(
            type="agent.response_posted",
            timestamp=timestamp,
            source="orchestrator",
            correlation_id="corr-2",
            work_item_id="issue-1",
            project_id="proj-1",
            comment_id="comment-42",
            agent_name="code-reviewer",
            conversation_id="conv-session-123",
        )

        d = event.to_dict()
        restored = AgentResponsePostedEvent.from_dict(d)

        assert restored.work_item_id == event.work_item_id
        assert restored.project_id == event.project_id
        assert restored.comment_id == event.comment_id
        assert restored.agent_name == event.agent_name
        assert restored.conversation_id == event.conversation_id
        assert restored.timestamp == event.timestamp

    def test_agent_response_posted_roundtrip_without_conversation_id(self):
        """Test agent response posted event roundtrip without conversation_id."""
        timestamp = now_iso()
        event = AgentResponsePostedEvent(
            type="agent.response_posted",
            timestamp=timestamp,
            source="orchestrator",
            work_item_id="issue-2",
            project_id="proj-2",
            comment_id="comment-99",
            agent_name="bug-fixer",
        )

        d = event.to_dict()
        restored = AgentResponsePostedEvent.from_dict(d)

        assert restored.work_item_id == event.work_item_id
        assert restored.conversation_id is None


class TestAgentResponsePostedEventImmutability:
    """Test immutability of AgentResponsePostedEvent (frozen dataclass)."""

    def test_agent_response_posted_event_is_frozen(self):
        """Test that AgentResponsePostedEvent is immutable (frozen dataclass)."""
        event = AgentResponsePostedEvent(
            type="agent.response_posted",
            timestamp=now_iso(),
            source="orchestrator",
            work_item_id="issue-1",
            project_id="proj-1",
            comment_id="comment-42",
            agent_name="code-reviewer",
            conversation_id="conv-session-123",
        )

        # Verify the event is properly created
        assert event.work_item_id == "issue-1"
        assert event.project_id == "proj-1"
        assert event.comment_id == "comment-42"
        assert event.agent_name == "code-reviewer"
        assert event.conversation_id == "conv-session-123"

        # AgentResponsePostedEvent is a frozen dataclass, so attempting to modify
        # any attribute should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            event.work_item_id = "issue-2"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.project_id = "proj-2"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.comment_id = "comment-99"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.agent_name = "bug-fixer"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.conversation_id = "conv-different"  # type: ignore

    def test_agent_response_posted_event_multiple_modifications_fail(self):
        """Test that multiple attempts to modify frozen event all fail."""
        event = AgentResponsePostedEvent(
            type="agent.response_posted",
            timestamp=now_iso(),
            source="orchestrator",
            work_item_id="issue-1",
            project_id="proj-1",
            comment_id="comment-42",
            agent_name="code-reviewer",
        )

        # All modification attempts should fail consistently
        for attempt in range(3):
            with pytest.raises(FrozenInstanceError):
                event.work_item_id = f"issue-{attempt}"  # type: ignore
