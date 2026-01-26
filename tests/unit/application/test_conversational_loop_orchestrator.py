"""Unit tests for ConversationalLoopOrchestrator application service.

Tests verify the core orchestration logic without external dependencies:
- Session initialization and lifecycle
- Comment handling and agent response execution
- Column transition handling
- Session state persistence and recovery
- Error handling and edge cases
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from codetoreum.application.conversational_loop_orchestrator import (
    ConversationalLoopOrchestrator,
)
from codetoreum.domain.conversational_session import ConversationalSessionState
from codetoreum.domain.events.discussion_events import (
    Comment,
    CommentContext,
    CommentNeedsResponseEvent,
    AgentResponsePostedEvent,
)
from codetoreum.domain.events.board_events import WorkItemColumnChangedEvent


@pytest.fixture
def mock_discussion_adapter():
    """Create a mock discussion adapter."""
    adapter = MagicMock()
    adapter.start_monitoring = MagicMock(return_value=None)  # Synchronous method
    adapter.stop_monitoring = MagicMock(return_value=None)   # Synchronous method
    adapter.add_comment = AsyncMock()
    return adapter


@pytest.fixture
def mock_llm_provider():
    """Create a mock LLM provider."""
    provider = MagicMock()
    provider.continue_conversation = AsyncMock()
    return provider


@pytest.fixture
def mock_event_store():
    """Create a mock event store."""
    store = MagicMock()
    store.append = AsyncMock()
    store.get_events = AsyncMock(return_value=[])
    store.get_latest_snapshot = AsyncMock(return_value=None)
    store.get_stream_version = AsyncMock(return_value=0)
    store.save_snapshot = AsyncMock()
    return store


@pytest.fixture
def orchestrator(mock_discussion_adapter, mock_llm_provider, mock_event_store):
    """Create a ConversationalLoopOrchestrator instance with mocks."""
    return ConversationalLoopOrchestrator(
        discussion_adapter=mock_discussion_adapter,
        llm_provider=mock_llm_provider,
        event_store=mock_event_store,
    )


@pytest.fixture
def sample_session_state():
    """Create a sample session state for testing."""
    return ConversationalSessionState(
        session_id="sess-001",
        work_item_id="issue-42",
        project_id="proj-1",
        agent_assignment="code-reviewer",
        column_name="In Review",
        llm_conversation_id="conv-abc123",
        last_processed_comment_id="comment-10",
        last_interaction_timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        status="active",
    )


@pytest.fixture
def sample_comment():
    """Create a sample comment for testing."""
    return Comment(
        id="comment-11",
        author="user123",
        body="Can you explain section 2 in more detail?",
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        parent_id=None,
        is_bot=False,
    )


class TestInitializeLoop:
    """Test suite for initialize_loop method."""

    async def test_initialize_loop_success(self, orchestrator, mock_discussion_adapter, mock_event_store):
        """Test successful loop initialization."""
        work_item_id = "issue-42"
        project_id = "proj-1"
        column_config = {
            "column_name": "In Review",
            "agent_assignment": "code-reviewer",
        }

        result = await orchestrator.initialize_loop(work_item_id, project_id, column_config)

        # Verify session was initialized
        assert result.work_item_id == work_item_id
        assert result.project_id == project_id
        assert result.column_name == "In Review"
        assert result.agent_assignment == "code-reviewer"
        assert result.status == "active"
        assert result.session_id is not None
        assert result.last_processed_comment_id == "__checkpoint_start"  # Sentinel value

        # Verify discussion adapter was started
        mock_discussion_adapter.start_monitoring.assert_called_once()
        call_args = mock_discussion_adapter.start_monitoring.call_args
        assert call_args[0][0] == work_item_id  # First positional arg
        assert call_args[0][1]["column_name"] == "In Review"  # Config

        # Verify session state was persisted
        mock_event_store.save_snapshot.assert_called_once()

    async def test_initialize_loop_domain_validation(self, orchestrator, mock_discussion_adapter, mock_event_store):
        """Test that initialized session state passes domain model validation."""
        work_item_id = "issue-42"
        project_id = "proj-1"
        column_config = {
            "column_name": "In Review",
            "agent_assignment": "code-reviewer",
        }

        # This should not raise ValueError for empty last_processed_comment_id
        result = await orchestrator.initialize_loop(work_item_id, project_id, column_config)

        # Verify the state object is valid and can be serialized/deserialized
        state_dict = result.to_dict()
        assert state_dict["last_processed_comment_id"] == "__checkpoint_start"

        # Verify we can reconstruct from dict
        reconstructed = ConversationalSessionState.from_dict(state_dict)
        assert reconstructed.last_processed_comment_id == "__checkpoint_start"

    async def test_initialize_loop_missing_work_item_id(self, orchestrator):
        """Test initialization fails with missing work_item_id."""
        with pytest.raises(ValueError, match="work_item_id and project_id are required"):
            await orchestrator.initialize_loop(
                "",
                "proj-1",
                {"column_name": "In Review", "agent_assignment": "reviewer"}
            )

    async def test_initialize_loop_missing_column_name(self, orchestrator):
        """Test initialization fails with missing column_name."""
        with pytest.raises(ValueError, match="column_name and agent_assignment"):
            await orchestrator.initialize_loop(
                "issue-42",
                "proj-1",
                {"agent_assignment": "reviewer"}  # Missing column_name
            )

    async def test_initialize_loop_monitoring_failure(self, orchestrator, mock_discussion_adapter, mock_event_store):
        """Test initialization cleanup on monitoring start failure."""
        mock_discussion_adapter.start_monitoring.side_effect = Exception("Monitoring failed")

        with pytest.raises(Exception, match="Monitoring failed"):
            await orchestrator.initialize_loop(
                "issue-42",
                "proj-1",
                {"column_name": "In Review", "agent_assignment": "reviewer"}
            )

        # Verify monitoring was attempted
        mock_discussion_adapter.start_monitoring.assert_called_once()
        # Event store should NOT be called since monitoring failed
        mock_event_store.append.assert_not_called()

    async def test_initialize_loop_persistence_failure(self, orchestrator, mock_discussion_adapter, mock_event_store):
        """Test initialization cleanup on persistence failure."""
        from codetoreum.ports.exceptions import EventStoreError

        mock_event_store.save_snapshot.side_effect = EventStoreError("Storage failed")

        with pytest.raises(EventStoreError, match="Storage failed"):
            await orchestrator.initialize_loop(
                "issue-42",
                "proj-1",
                {"column_name": "In Review", "agent_assignment": "reviewer"}
            )

        # Verify cleanup was attempted
        mock_discussion_adapter.start_monitoring.assert_called_once()
        mock_discussion_adapter.stop_monitoring.assert_called_once_with("issue-42")


class TestHandleCommentEvent:
    """Test suite for handle_comment_event method."""

    async def test_handle_comment_success(
        self,
        orchestrator,
        mock_discussion_adapter,
        mock_llm_provider,
        mock_event_store,
        sample_session_state,
        sample_comment,
    ):
        """Test successful comment handling and response posting."""
        # Mock session state loading
        snapshot_data = {
            "conversational_session_state": sample_session_state.to_dict()
        }
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=snapshot_data)

        # Mock agent execution
        mock_execution_result = MagicMock()
        mock_execution_result.content = "This is the agent's response."
        mock_execution_result.conversation_id = "conv-abc123"
        mock_llm_provider.continue_conversation = AsyncMock(return_value=mock_execution_result)

        # Mock comment posting
        mock_response_comment = MagicMock()
        mock_response_comment.id = "comment-12"
        mock_discussion_adapter.add_comment = AsyncMock(return_value=mock_response_comment)

        # Create event with comment
        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id="issue-42",
            project_id="proj-1",
            comment=sample_comment,
            context=CommentContext(
                column_name="In Review",
                agent_assignment="code-reviewer",
            ),
        )

        # Handle comment event
        await orchestrator.handle_comment_event(event)

        # Verify agent execution
        mock_llm_provider.continue_conversation.assert_called_once()
        call_kwargs = mock_llm_provider.continue_conversation.call_args[1]
        assert call_kwargs["conversation_id"] == "conv-abc123"
        assert "Can you explain section 2" in call_kwargs["message"]

        # Verify response posting
        mock_discussion_adapter.add_comment.assert_called_once()
        call_kwargs = mock_discussion_adapter.add_comment.call_args[1]
        assert call_kwargs["work_item_id"] == "issue-42"
        assert call_kwargs["content"] == "This is the agent's response."
        assert call_kwargs["parent_id"] == sample_comment.id

        # Verify session state was persisted with updated checkpoint
        mock_event_store.save_snapshot.assert_called_once()

        # Verify AgentResponsePostedEvent was emitted
        mock_event_store.append.assert_called_once()
        call_args = mock_event_store.append.call_args
        assert call_args[0][0] == "issue-42"  # stream_id
        events = call_args[0][1]
        assert len(events) == 1
        assert isinstance(events[0], AgentResponsePostedEvent)
        assert events[0].work_item_id == "issue-42"
        assert events[0].project_id == "proj-1"
        assert events[0].comment_id == sample_comment.id  # Human comment being responded to
        assert events[0].agent_name == "code-reviewer"
        assert events[0].conversation_id == "conv-abc123"

    async def test_handle_comment_empty_response(
        self,
        orchestrator,
        mock_discussion_adapter,
        mock_llm_provider,
        mock_event_store,
        sample_session_state,
        sample_comment,
    ):
        """Test that empty agent responses raise EmptyAgentResponseError."""
        from codetoreum.ports.exceptions import EmptyAgentResponseError

        # Mock session state loading
        snapshot_data = {
            "conversational_session_state": sample_session_state.to_dict()
        }
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=snapshot_data)

        # Mock agent execution returning empty content
        mock_execution_result = MagicMock()
        mock_execution_result.content = ""  # Empty response
        mock_execution_result.conversation_id = "conv-abc123"
        mock_llm_provider.continue_conversation = AsyncMock(
            return_value=mock_execution_result
        )

        # Create event with comment
        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id="issue-42",
            project_id="proj-1",
            comment=sample_comment,
            context=CommentContext(
                column_name="In Review",
                agent_assignment="code-reviewer",
            ),
        )

        # Handle comment event should raise EmptyAgentResponseError
        with pytest.raises(EmptyAgentResponseError) as exc_info:
            await orchestrator.handle_comment_event(event)

        assert exc_info.value.work_item_id == "issue-42"
        assert "empty response" in str(exc_info.value).lower()

        # Verify agent execution was called
        mock_llm_provider.continue_conversation.assert_called_once()

        # Verify no comment was posted (agent response never reached posting stage)
        mock_discussion_adapter.add_comment.assert_not_called()

        # Verify no success event was emitted
        mock_event_store.append.assert_not_called()

    async def test_handle_comment_no_session(self, orchestrator, mock_event_store, sample_comment):
        """Test comment handling when no session exists."""
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=None)

        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id="issue-42",
            project_id="proj-1",
            comment=sample_comment,
        )

        # Should handle gracefully - no exception, just skip
        await orchestrator.handle_comment_event(event)

    async def test_handle_comment_suspended_session(
        self,
        orchestrator,
        mock_event_store,
        sample_session_state,
        sample_comment,
    ):
        """Test comment handling skips suspended sessions."""
        # Create suspended session
        suspended_state = ConversationalSessionState(
            session_id=sample_session_state.session_id,
            work_item_id=sample_session_state.work_item_id,
            project_id=sample_session_state.project_id,
            agent_assignment=sample_session_state.agent_assignment,
            column_name=sample_session_state.column_name,
            llm_conversation_id=sample_session_state.llm_conversation_id,
            last_processed_comment_id=sample_session_state.last_processed_comment_id,
            last_interaction_timestamp=sample_session_state.last_interaction_timestamp,
            status="suspended",
        )

        snapshot_data = {
            "conversational_session_state": suspended_state.to_dict()
        }
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=snapshot_data)

        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id="issue-42",
            project_id="proj-1",
            comment=sample_comment,
        )

        # Should handle gracefully - no exception
        await orchestrator.handle_comment_event(event)

    async def test_handle_comment_missing_comment_body(self, orchestrator, mock_event_store):
        """Test comment event without comment body is skipped."""
        mock_event_store.get_events = AsyncMock(return_value=[])

        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id="issue-42",
            project_id="proj-1",
            comment=None,  # No comment
        )

        # Should handle gracefully (log warning and return)
        await orchestrator.handle_comment_event(event)

    async def test_handle_comment_duplicate_prevention(
        self,
        orchestrator,
        mock_discussion_adapter,
        mock_llm_provider,
        mock_event_store,
        sample_session_state,
        sample_comment,
    ):
        """Test duplicate response prevention (FR-4.4)."""
        # Create session where the comment has already been processed
        processed_state = ConversationalSessionState(
            session_id=sample_session_state.session_id,
            work_item_id=sample_session_state.work_item_id,
            project_id=sample_session_state.project_id,
            agent_assignment=sample_session_state.agent_assignment,
            column_name=sample_session_state.column_name,
            llm_conversation_id=sample_session_state.llm_conversation_id,
            last_processed_comment_id="comment-11",  # Same as incoming comment
            last_interaction_timestamp=sample_session_state.last_interaction_timestamp,
            status="active",
        )

        snapshot_data = {
            "conversational_session_state": processed_state.to_dict()
        }
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=snapshot_data)

        # Create event with same comment ID
        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id="issue-42",
            project_id="proj-1",
            comment=sample_comment,  # ID: "comment-11"
            context=CommentContext(
                column_name="In Review",
                agent_assignment="code-reviewer",
            ),
        )

        # Handle comment event - should skip due to duplicate
        await orchestrator.handle_comment_event(event)

        # Verify agent was NOT executed
        mock_llm_provider.continue_conversation.assert_not_called()

        # Verify comment was NOT posted
        mock_discussion_adapter.add_comment.assert_not_called()


class TestHandleColumnChangeEvent:
    """Test suite for handle_column_change_event method."""

    async def test_handle_column_change_exit_conversational(
        self,
        orchestrator,
        mock_discussion_adapter,
        mock_event_store,
        sample_session_state,
    ):
        """Test column change when exiting conversational column."""
        snapshot_data = {
            "conversational_session_state": sample_session_state.to_dict()
        }
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=snapshot_data)

        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id="issue-42",
            project_id="proj-1",
            board_id="board-1",
            from_column="In Review",
            to_column="Testing",
        )

        await orchestrator.handle_column_change_event(event)

        # Verify monitoring was stopped
        mock_discussion_adapter.stop_monitoring.assert_called_once_with("issue-42")

        # Verify session state was persisted as terminated
        mock_event_store.save_snapshot.assert_called_once()

    async def test_handle_column_change_no_session(self, orchestrator, mock_event_store, mock_discussion_adapter):
        """Test column change when no session exists."""
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=None)

        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id="issue-42",
            project_id="proj-1",
            board_id="board-1",
            from_column="In Progress",
            to_column="Testing",
        )

        # Should handle gracefully
        await orchestrator.handle_column_change_event(event)

        # Monitoring should NOT be stopped if no session
        mock_discussion_adapter.stop_monitoring.assert_not_called()

    async def test_handle_column_change_missing_work_item_id(self, orchestrator):
        """Test column change event validation."""
        with pytest.raises(ValueError, match="work_item_id is required"):
            WorkItemColumnChangedEvent(
                type="workitem.column_changed",
                timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                source="github",
                work_item_id="",  # Missing - caught at event creation
                project_id="proj-1",
                board_id="board-1",
                from_column="In Progress",
                to_column="Testing",
            )


class TestCleanupLoop:
    """Test suite for cleanup_loop method."""

    async def test_cleanup_loop_success(
        self,
        orchestrator,
        mock_discussion_adapter,
        mock_event_store,
        sample_session_state,
    ):
        """Test successful loop cleanup."""
        snapshot_data = {
            "conversational_session_state": sample_session_state.to_dict()
        }
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=snapshot_data)

        await orchestrator.cleanup_loop("issue-42", "Agent execution error")

        # Verify monitoring was stopped
        mock_discussion_adapter.stop_monitoring.assert_called_once_with("issue-42")

        # Verify session was marked terminated
        mock_event_store.save_snapshot.assert_called_once()

    async def test_cleanup_loop_no_session(self, orchestrator, mock_event_store, mock_discussion_adapter):
        """Test cleanup loop when no session exists (idempotent)."""
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=None)

        # Should not raise
        await orchestrator.cleanup_loop("issue-42", "Cleanup reason")

        # Monitoring should not be stopped if no session
        mock_discussion_adapter.stop_monitoring.assert_not_called()

    async def test_cleanup_loop_idempotent(
        self,
        orchestrator,
        mock_event_store,
        sample_session_state,
    ):
        """Test cleanup loop is idempotent - safe to call multiple times."""
        # Session already terminated
        terminated_state = ConversationalSessionState(
            session_id=sample_session_state.session_id,
            work_item_id=sample_session_state.work_item_id,
            project_id=sample_session_state.project_id,
            agent_assignment=sample_session_state.agent_assignment,
            column_name=sample_session_state.column_name,
            llm_conversation_id=sample_session_state.llm_conversation_id,
            last_processed_comment_id=sample_session_state.last_processed_comment_id,
            last_interaction_timestamp=sample_session_state.last_interaction_timestamp,
            status="terminated",
        )

        snapshot_data = {
            "conversational_session_state": terminated_state.to_dict()
        }
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=snapshot_data)

        # Should handle gracefully - no exception
        await orchestrator.cleanup_loop("issue-42", "Already terminated")

    async def test_cleanup_loop_monitoring_failure_continues(
        self,
        orchestrator,
        mock_discussion_adapter,
        mock_event_store,
        sample_session_state,
    ):
        """Test cleanup continues even if monitoring stop fails."""
        snapshot_data = {
            "conversational_session_state": sample_session_state.to_dict()
        }
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=snapshot_data)
        mock_discussion_adapter.stop_monitoring.side_effect = Exception("Monitoring stop failed")

        # Should not raise - cleanup continues
        await orchestrator.cleanup_loop("issue-42", "Error cleanup")

        # But should still attempt to persist state
        mock_event_store.save_snapshot.assert_called_once()


class TestLoadSessionState:
    """Test suite for load_session_state method."""

    async def test_load_session_state_exists(self, orchestrator, mock_event_store, sample_session_state):
        """Test loading existing session state."""
        snapshot_data = {
            "conversational_session_state": sample_session_state.to_dict()
        }
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=snapshot_data)

        result = await orchestrator.load_session_state("issue-42")

        assert result is not None
        assert result.work_item_id == "issue-42"
        assert result.session_id == sample_session_state.session_id

    async def test_load_session_state_not_exists(self, orchestrator, mock_event_store):
        """Test loading session state when none exists."""
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=None)

        result = await orchestrator.load_session_state("issue-42")

        assert result is None

    async def test_load_session_state_invalid_work_item_id(self, orchestrator):
        """Test loading session with invalid work_item_id."""
        with pytest.raises(ValueError, match="work_item_id is required"):
            await orchestrator.load_session_state("")


class TestSaveSessionState:
    """Test suite for save_session_state method."""

    async def test_save_session_state_success(self, orchestrator, mock_event_store, sample_session_state):
        """Test successful session state persistence."""
        await orchestrator.save_session_state(sample_session_state)

        # Verify snapshot was saved
        mock_event_store.save_snapshot.assert_called_once()
        call_args = mock_event_store.save_snapshot.call_args[1]
        assert call_args["stream_id"] == "issue-42"
        assert "conversational_session_state" in call_args["snapshot"]

    async def test_save_session_state_none(self, orchestrator):
        """Test saving None session state."""
        with pytest.raises(ValueError, match="state is required"):
            await orchestrator.save_session_state(None)

    async def test_save_session_state_failure(self, orchestrator, mock_event_store, sample_session_state):
        """Test session state persistence failure."""
        from codetoreum.ports.exceptions import EventStoreError

        mock_event_store.save_snapshot.side_effect = EventStoreError("Storage failed")

        with pytest.raises(EventStoreError, match="Storage failed"):
            await orchestrator.save_session_state(sample_session_state)


class TestBuildThreadMessage:
    """Test suite for _build_thread_message helper method."""

    def test_build_thread_message_with_context(self, orchestrator, sample_comment, sample_session_state):
        """Test building thread message with full context."""
        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id="issue-42",
            project_id="proj-1",
            comment=sample_comment,
            context=CommentContext(
                column_name="In Review",
                agent_assignment="code-reviewer",
            ),
        )

        message = orchestrator._build_thread_message(event, sample_session_state)

        assert "In Review" in message
        assert "code-reviewer" in message
        assert "Can you explain section 2" in message
        assert "user123" in message

    def test_build_thread_message_without_context(self, orchestrator, sample_comment, sample_session_state):
        """Test building thread message without context."""
        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id="issue-42",
            project_id="proj-1",
            comment=sample_comment,
            context=None,
        )

        message = orchestrator._build_thread_message(event, sample_session_state)

        assert "Can you explain section 2" in message
        assert "user123" in message
