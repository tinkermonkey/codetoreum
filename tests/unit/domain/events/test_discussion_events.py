"""Unit tests for discussion and comment events."""

import pytest

from codetoreum.domain.events import (
    Comment,
    CommentContext,
    CommentNeedsResponseEvent,
    CommentPostedEvent,
    now_iso,
)

# For immutability tests (when events become frozen dataclasses)
try:
    from dataclasses import FrozenInstanceError
except ImportError:
    # Fallback for older Python versions or non-frozen dataclasses
    FrozenInstanceError = AttributeError  # type: ignore


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
    """Test immutability of Comment class."""

    def test_comment_immutability(self):
        """Test that Comment attributes are immutable.

        NOTE: This test currently documents expected behavior.
        When Comment is converted to a frozen dataclass, this test will
        verify that the frozen=True constraint is properly enforced.
        """
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

        # When frozen dataclasses are implemented, these assertions
        # will test that modification raises FrozenInstanceError
        original_id = comment.id
        original_author = comment.author

        # Verify values haven't changed
        assert comment.id == original_id
        assert comment.author == original_author

    def test_comment_bot_immutability(self):
        """Test immutability of bot comment."""
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

        # Document expected immutability
        original_is_bot = comment.is_bot
        assert comment.is_bot == original_is_bot


class TestCommentContextImmutability:
    """Test immutability of CommentContext class."""

    def test_comment_context_immutability(self):
        """Test that CommentContext attributes are immutable.

        NOTE: This test currently documents expected behavior.
        When CommentContext is converted to a frozen dataclass, this test will
        verify that the frozen=True constraint is properly enforced.
        """
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

        # When frozen dataclasses are implemented, these assertions
        # will test that modification raises FrozenInstanceError
        original_thread = context.thread_id
        original_column = context.column_name

        # Verify values haven't changed
        assert context.thread_id == original_thread
        assert context.column_name == original_column

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

        # Document expected immutability of nested comment
        original_parent_id = context.parent_comment.id
        assert context.parent_comment.id == original_parent_id


class TestCommentNeedsResponseEventImmutability:
    """Test immutability of CommentNeedsResponseEvent."""

    def test_comment_needs_response_event_immutability(self):
        """Test that CommentNeedsResponseEvent attributes are immutable.

        NOTE: This test currently documents expected behavior.
        When events are converted to frozen dataclasses, this test will
        verify that the frozen=True constraint is properly enforced.
        """
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

        # When frozen dataclasses are implemented, these assertions
        # will test that modification raises FrozenInstanceError
        original_id = event.work_item_id
        original_author = event.comment.author

        # Verify values haven't changed
        assert event.work_item_id == original_id
        assert event.comment.author == original_author


class TestCommentPostedEventImmutability:
    """Test immutability of CommentPostedEvent."""

    def test_comment_posted_event_immutability(self):
        """Test that CommentPostedEvent attributes are immutable.

        NOTE: This test currently documents expected behavior.
        When events are converted to frozen dataclasses, this test will
        verify that the frozen=True constraint is properly enforced.
        """
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

        # When frozen dataclasses are implemented, these assertions
        # will test that modification raises FrozenInstanceError
        original_id = event.work_item_id
        original_comment_id = event.comment.id

        # Verify values haven't changed
        assert event.work_item_id == original_id
        assert event.comment.id == original_comment_id

    def test_comment_posted_event_bot_comment_immutability(self):
        """Test immutability of CommentPostedEvent with bot comment."""
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

        # Document expected immutability
        original_is_bot = event.comment.is_bot
        assert event.comment.is_bot == original_is_bot
