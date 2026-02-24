"""Unit tests for conversational session state value object."""

import pytest
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

from codetoreum.domain.conversational_session import ConversationalSessionState


class TestConversationalSessionState:
    """Test ConversationalSessionState value object."""

    def test_create_valid_session_state(self):
        """Test creating a valid conversational session state."""
        state = ConversationalSessionState(
            session_id="sess-001",
            work_item_id="issue-42",
            project_id="proj-1",
            agent_assignment="code-reviewer",
            column_name="In Review",
            llm_conversation_id="conv-abc123",
            last_processed_comment_id="comment-10",
            last_interaction_timestamp="2025-01-14T10:35:00+00:00",
            status="active"
        )

        assert state.session_id == "sess-001"
        assert state.work_item_id == "issue-42"
        assert state.project_id == "proj-1"
        assert state.agent_assignment == "code-reviewer"
        assert state.column_name == "In Review"
        assert state.llm_conversation_id == "conv-abc123"
        assert state.last_processed_comment_id == "comment-10"
        assert state.last_interaction_timestamp == "2025-01-14T10:35:00+00:00"
        assert state.status == "active"

    def test_create_with_none_llm_conversation_id(self):
        """Test creating session state with None llm_conversation_id (optional)."""
        state = ConversationalSessionState(
            session_id="sess-002",
            work_item_id="issue-43",
            project_id="proj-1",
            agent_assignment="bug-fixer",
            column_name="In Progress",
            llm_conversation_id=None,
            last_processed_comment_id="comment-5",
            last_interaction_timestamp="2025-01-14T10:40:00+00:00",
            status="suspended"
        )

        assert state.llm_conversation_id is None
        assert state.status == "suspended"

    def test_all_status_values(self):
        """Test all valid status values."""
        valid_statuses: list[str] = ["active", "suspended", "terminated"]
        for status in valid_statuses:
            state = ConversationalSessionState(
                session_id=f"sess-{status}",
                work_item_id="issue-1",
                project_id="proj-1",
                agent_assignment="agent",
                column_name="column",
                llm_conversation_id=None,
                last_processed_comment_id="comment-1",
                last_interaction_timestamp="2025-01-14T10:00:00+00:00",
                status=status  # type: ignore
            )
            assert state.status == status

    def test_missing_session_id(self):
        """Test that session_id is required."""
        with pytest.raises(ValueError, match="session_id is required"):
            ConversationalSessionState(
                session_id="",
                work_item_id="issue-42",
                project_id="proj-1",
                agent_assignment="code-reviewer",
                column_name="In Review",
                llm_conversation_id="conv-abc123",
                last_processed_comment_id="comment-10",
                last_interaction_timestamp="2025-01-14T10:35:00+00:00",
                status="active"
            )

    def test_missing_work_item_id(self):
        """Test that work_item_id is required."""
        with pytest.raises(ValueError, match="work_item_id is required"):
            ConversationalSessionState(
                session_id="sess-001",
                work_item_id="",
                project_id="proj-1",
                agent_assignment="code-reviewer",
                column_name="In Review",
                llm_conversation_id="conv-abc123",
                last_processed_comment_id="comment-10",
                last_interaction_timestamp="2025-01-14T10:35:00+00:00",
                status="active"
            )

    def test_missing_project_id(self):
        """Test that project_id is required."""
        with pytest.raises(ValueError, match="project_id is required"):
            ConversationalSessionState(
                session_id="sess-001",
                work_item_id="issue-42",
                project_id="",
                agent_assignment="code-reviewer",
                column_name="In Review",
                llm_conversation_id="conv-abc123",
                last_processed_comment_id="comment-10",
                last_interaction_timestamp="2025-01-14T10:35:00+00:00",
                status="active"
            )

    def test_missing_agent_assignment(self):
        """Test that agent_assignment is required."""
        with pytest.raises(ValueError, match="agent_assignment is required"):
            ConversationalSessionState(
                session_id="sess-001",
                work_item_id="issue-42",
                project_id="proj-1",
                agent_assignment="",
                column_name="In Review",
                llm_conversation_id="conv-abc123",
                last_processed_comment_id="comment-10",
                last_interaction_timestamp="2025-01-14T10:35:00+00:00",
                status="active"
            )

    def test_column_name_is_optional(self):
        """Test that column_name is optional (can be None for pure discussion tracking)."""
        state = ConversationalSessionState(
            session_id="sess-001",
            work_item_id="issue-42",
            project_id="proj-1",
            agent_assignment="code-reviewer",
            column_name=None,  # Now optional - board context is auxiliary
            llm_conversation_id="conv-abc123",
            last_processed_comment_id="comment-10",
            last_interaction_timestamp="2025-01-14T10:35:00+00:00",
            status="active"
        )
        assert state.column_name is None

    def test_missing_last_processed_comment_id(self):
        """Test that last_processed_comment_id is required."""
        with pytest.raises(ValueError, match="last_processed_comment_id is required"):
            ConversationalSessionState(
                session_id="sess-001",
                work_item_id="issue-42",
                project_id="proj-1",
                agent_assignment="code-reviewer",
                column_name="In Review",
                llm_conversation_id="conv-abc123",
                last_processed_comment_id="",
                last_interaction_timestamp="2025-01-14T10:35:00+00:00",
                status="active"
            )

    def test_missing_last_interaction_timestamp(self):
        """Test that last_interaction_timestamp is required."""
        with pytest.raises(ValueError, match="last_interaction_timestamp is required"):
            ConversationalSessionState(
                session_id="sess-001",
                work_item_id="issue-42",
                project_id="proj-1",
                agent_assignment="code-reviewer",
                column_name="In Review",
                llm_conversation_id="conv-abc123",
                last_processed_comment_id="comment-10",
                last_interaction_timestamp="",
                status="active"
            )

    def test_invalid_iso8601_timestamp(self):
        """Test that invalid ISO 8601 timestamp raises error."""
        with pytest.raises(ValueError, match="last_interaction_timestamp must be ISO 8601 format"):
            ConversationalSessionState(
                session_id="sess-001",
                work_item_id="issue-42",
                project_id="proj-1",
                agent_assignment="code-reviewer",
                column_name="In Review",
                llm_conversation_id="conv-abc123",
                last_processed_comment_id="comment-10",
                last_interaction_timestamp="not-a-timestamp",
                status="active"
            )

    def test_iso8601_timestamp_with_z_suffix(self):
        """Test that ISO 8601 format with 'Z' suffix is accepted."""
        state = ConversationalSessionState(
            session_id="sess-001",
            work_item_id="issue-42",
            project_id="proj-1",
            agent_assignment="code-reviewer",
            column_name="In Review",
            llm_conversation_id="conv-abc123",
            last_processed_comment_id="comment-10",
            last_interaction_timestamp="2025-01-14T10:35:00Z",
            status="active"
        )
        assert state.last_interaction_timestamp == "2025-01-14T10:35:00Z"

    def test_iso8601_timestamp_with_timezone_offset(self):
        """Test that ISO 8601 format with timezone offset is accepted."""
        state = ConversationalSessionState(
            session_id="sess-001",
            work_item_id="issue-42",
            project_id="proj-1",
            agent_assignment="code-reviewer",
            column_name="In Review",
            llm_conversation_id="conv-abc123",
            last_processed_comment_id="comment-10",
            last_interaction_timestamp="2025-01-14T10:35:00+02:30",
            status="active"
        )
        assert state.last_interaction_timestamp == "2025-01-14T10:35:00+02:30"

    def test_invalid_status_value(self):
        """Test that invalid status value raises error."""
        with pytest.raises(ValueError, match="status must be one of"):
            ConversationalSessionState(
                session_id="sess-001",
                work_item_id="issue-42",
                project_id="proj-1",
                agent_assignment="code-reviewer",
                column_name="In Review",
                llm_conversation_id="conv-abc123",
                last_processed_comment_id="comment-10",
                last_interaction_timestamp="2025-01-14T10:35:00+00:00",
                status="invalid"  # type: ignore
            )

    def test_session_state_serialization(self):
        """Test session state serialization to dictionary."""
        state = ConversationalSessionState(
            session_id="sess-001",
            work_item_id="issue-42",
            project_id="proj-1",
            agent_assignment="code-reviewer",
            column_name="In Review",
            llm_conversation_id="conv-abc123",
            last_processed_comment_id="comment-10",
            last_interaction_timestamp="2025-01-14T10:35:00+00:00",
            status="active"
        )

        d = state.to_dict()

        assert d["session_id"] == "sess-001"
        assert d["work_item_id"] == "issue-42"
        assert d["project_id"] == "proj-1"
        assert d["agent_assignment"] == "code-reviewer"
        assert d["column_name"] == "In Review"
        assert d["llm_conversation_id"] == "conv-abc123"
        assert d["last_processed_comment_id"] == "comment-10"
        assert d["last_interaction_timestamp"] == "2025-01-14T10:35:00+00:00"
        assert d["status"] == "active"

    def test_session_state_deserialization(self):
        """Test session state deserialization from dictionary."""
        d = {
            "session_id": "sess-002",
            "work_item_id": "issue-43",
            "project_id": "proj-2",
            "agent_assignment": "bug-fixer",
            "column_name": "In Progress",
            "llm_conversation_id": "conv-def456",
            "last_processed_comment_id": "comment-20",
            "last_interaction_timestamp": "2025-01-14T11:00:00+00:00",
            "status": "suspended"
        }

        state = ConversationalSessionState.from_dict(d)

        assert state.session_id == "sess-002"
        assert state.work_item_id == "issue-43"
        assert state.project_id == "proj-2"
        assert state.agent_assignment == "bug-fixer"
        assert state.column_name == "In Progress"
        assert state.llm_conversation_id == "conv-def456"
        assert state.last_processed_comment_id == "comment-20"
        assert state.last_interaction_timestamp == "2025-01-14T11:00:00+00:00"
        assert state.status == "suspended"

    def test_session_state_roundtrip(self):
        """Test session state serialization and deserialization roundtrip."""
        original = ConversationalSessionState(
            session_id="sess-003",
            work_item_id="issue-44",
            project_id="proj-3",
            agent_assignment="reviewer",
            column_name="Review",
            llm_conversation_id="conv-ghi789",
            last_processed_comment_id="comment-30",
            last_interaction_timestamp="2025-01-14T12:00:00+00:00",
            status="active"
        )

        d = original.to_dict()
        restored = ConversationalSessionState.from_dict(d)

        assert restored.session_id == original.session_id
        assert restored.work_item_id == original.work_item_id
        assert restored.project_id == original.project_id
        assert restored.agent_assignment == original.agent_assignment
        assert restored.column_name == original.column_name
        assert restored.llm_conversation_id == original.llm_conversation_id
        assert restored.last_processed_comment_id == original.last_processed_comment_id
        assert restored.last_interaction_timestamp == original.last_interaction_timestamp
        assert restored.status == original.status

    def test_session_state_roundtrip_without_conversation_id(self):
        """Test roundtrip with None conversation_id."""
        original = ConversationalSessionState(
            session_id="sess-004",
            work_item_id="issue-45",
            project_id="proj-4",
            agent_assignment="fixer",
            column_name="Fixing",
            llm_conversation_id=None,
            last_processed_comment_id="comment-1",
            last_interaction_timestamp="2025-01-14T13:00:00+00:00",
            status="terminated"
        )

        d = original.to_dict()
        restored = ConversationalSessionState.from_dict(d)

        assert restored.llm_conversation_id is None

    def test_from_dict_with_missing_fields_uses_defaults(self):
        """Test that from_dict handles missing fields with defaults."""
        # Minimal dict with only required fields
        d = {
            "session_id": "sess-005",
            "work_item_id": "issue-46",
            "project_id": "proj-5",
            "agent_assignment": "agent",
            "column_name": "col",
            "last_processed_comment_id": "comment",
            "last_interaction_timestamp": "2025-01-14T14:00:00+00:00",
            # Missing: llm_conversation_id, status
        }

        state = ConversationalSessionState.from_dict(d)

        assert state.llm_conversation_id is None
        assert state.status == "active"  # Default value


class TestConversationalSessionStateImmutability:
    """Test immutability of ConversationalSessionState (frozen dataclass)."""

    def test_session_state_is_frozen(self):
        """Test that ConversationalSessionState is immutable (frozen dataclass)."""
        state = ConversationalSessionState(
            session_id="sess-001",
            work_item_id="issue-42",
            project_id="proj-1",
            agent_assignment="code-reviewer",
            column_name="In Review",
            llm_conversation_id="conv-abc123",
            last_processed_comment_id="comment-10",
            last_interaction_timestamp="2025-01-14T10:35:00+00:00",
            status="active"
        )

        # Verify the state is properly created
        assert state.session_id == "sess-001"
        assert state.work_item_id == "issue-42"
        assert state.status == "active"

        # ConversationalSessionState is a frozen dataclass, so attempting to modify
        # any attribute should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            state.session_id = "sess-002"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            state.work_item_id = "issue-99"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            state.project_id = "proj-2"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            state.agent_assignment = "different-agent"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            state.column_name = "Done"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            state.llm_conversation_id = "conv-different"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            state.last_processed_comment_id = "comment-99"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            state.last_interaction_timestamp = "2025-01-15T00:00:00+00:00"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            state.status = "terminated"  # type: ignore

    def test_session_state_immutability_pattern(self):
        """Test the immutability pattern for session state updates."""
        original_state = ConversationalSessionState(
            session_id="sess-001",
            work_item_id="issue-42",
            project_id="proj-1",
            agent_assignment="code-reviewer",
            column_name="In Review",
            llm_conversation_id="conv-abc123",
            last_processed_comment_id="comment-10",
            last_interaction_timestamp="2025-01-14T10:35:00+00:00",
            status="active"
        )

        # To update state, create a new instance (immutability pattern)
        updated_state = ConversationalSessionState(
            session_id=original_state.session_id,
            work_item_id=original_state.work_item_id,
            project_id=original_state.project_id,
            agent_assignment=original_state.agent_assignment,
            column_name=original_state.column_name,
            llm_conversation_id=original_state.llm_conversation_id,
            last_processed_comment_id="comment-11",  # Updated
            last_interaction_timestamp="2025-01-14T10:40:00+00:00",  # Updated
            status=original_state.status
        )

        # Original is unchanged
        assert original_state.last_processed_comment_id == "comment-10"
        assert original_state.last_interaction_timestamp == "2025-01-14T10:35:00+00:00"

        # New state has updates
        assert updated_state.last_processed_comment_id == "comment-11"
        assert updated_state.last_interaction_timestamp == "2025-01-14T10:40:00+00:00"

    def test_multiple_modification_attempts_fail(self):
        """Test that multiple attempts to modify frozen state all fail."""
        state = ConversationalSessionState(
            session_id="sess-001",
            work_item_id="issue-42",
            project_id="proj-1",
            agent_assignment="code-reviewer",
            column_name="In Review",
            llm_conversation_id="conv-abc123",
            last_processed_comment_id="comment-10",
            last_interaction_timestamp="2025-01-14T10:35:00+00:00",
            status="active"
        )

        # All modification attempts should fail consistently
        for attempt in range(3):
            with pytest.raises(FrozenInstanceError):
                state.session_id = f"sess-{attempt}"  # type: ignore
