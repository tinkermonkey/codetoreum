"""Unit tests for ConversationalLoopOrchestrator application service.

Tests verify the core orchestration logic without external dependencies:
- Session initialization and lifecycle
- Comment handling and agent response execution
- Column transition handling
- Session state persistence and recovery
- Error handling and edge cases
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.application.conversational_loop_orchestrator import (
    ConversationalLoopOrchestrator,
)
from codetoreum.domain.agent import Agent, AgentCapability, AgentType, CommitPolicy
from codetoreum.domain.coding_agent_types import AgentInvocationConfig, InvocationMode
from codetoreum.domain.conversational_session import ConversationalSessionState
from codetoreum.domain.events.board_events import WorkItemColumnChangedEvent
from codetoreum.domain.events.discussion_events import (
    AgentResponsePostedEvent,
    Comment,
    CommentContext,
    CommentNeedsResponseEvent,
)
from codetoreum.domain.work_item import (
    WorkItem,
    WorkItemPriority,
    WorkItemStatus,
)
from codetoreum.ports.output.coding_agent import CodingAgentResult


@pytest.fixture
def mock_discussion_adapter():
    """Create a mock discussion adapter."""
    adapter = MagicMock()
    adapter.start_monitoring = MagicMock(return_value=None)  # Synchronous method
    adapter.stop_monitoring = MagicMock(return_value=None)  # Synchronous method
    adapter.add_comment = AsyncMock()
    return adapter


@pytest.fixture
def mock_coding_agent():
    """Create a mock ICodingAgent."""
    from codetoreum.domain.coding_agent_types import InvocationMode

    agent = MagicMock()
    agent.supported_invocation_modes = MagicMock(
        return_value=frozenset({InvocationMode.CONTAINERIZED, InvocationMode.HOST})
    )
    agent.execute = AsyncMock(
        return_value=CodingAgentResult(
            success=True,
            summary_text="default mock response",
            total_cost_usd=Decimal("0.00"),
            total_input_tokens=0,
            total_output_tokens=0,
            tool_call_count=0,
            duration_ms=0,
            error_summary=None,
        )
    )
    return agent


@pytest.fixture
def mock_prompt_builder():
    """Create a mock IPromptBuilder."""
    builder = MagicMock()
    builder.build = AsyncMock()
    return builder


@pytest.fixture
def sample_agent():
    """Create a sample Agent for tests."""
    agent = Agent(
        id="agent-1",
        name="code-reviewer",
        display_name="Code Reviewer",
        agent_type=AgentType.REVIEWER,
        capabilities={"code_review": AgentCapability(skill="code_review", proficiency=0.9)},
        role_description="Reviews code changes for correctness",
        max_retries=3,
        requires_dev_container=False,
        makes_code_changes=False,
        filesystem_write_allowed=True,
        mcp_servers=[],
        metadata={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        coding_agent="claude_code",
        invocation=AgentInvocationConfig(
            mode=InvocationMode.CONTAINERIZED,
            model="claude-sonnet-4-5",
            timeout_seconds=300,
            mode_config={"image": "codetoreum-agent:latest"},
        ),
    )
    return agent


@pytest.fixture
def mock_agent_repository(sample_agent):
    """Create a mock IAgentRepository."""
    repo = MagicMock()
    repo.get_by_name = AsyncMock(return_value=sample_agent)
    repo.get_by_id = AsyncMock(return_value=sample_agent)
    return repo


@pytest.fixture
def sample_work_item():
    """Create a sample WorkItem for tests."""
    return WorkItem(
        id="issue-42",
        project_id="proj-1",
        title="Test issue",
        description="Test description",
        status=WorkItemStatus.IN_PROGRESS,
        priority=WorkItemPriority.MEDIUM,
        labels=[],
        external_id="42",
        external_url=None,
        assigned_agent_id="agent-1",
        assigned_at=datetime.now(UTC),
        current_workflow_id=None,
        current_stage=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def mock_work_item_service(sample_work_item):
    """Create a mock IWorkItemService."""
    service = MagicMock()
    service.get_work_item = AsyncMock(return_value=sample_work_item)
    return service


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
def orchestrator(
    mock_discussion_adapter,
    mock_coding_agent,
    mock_prompt_builder,
    mock_agent_repository,
    mock_work_item_service,
    mock_event_store,
):
    """Create a ConversationalLoopOrchestrator instance with mocks."""
    return ConversationalLoopOrchestrator(
        discussion_adapter=mock_discussion_adapter,
        coding_agent=mock_coding_agent,
        prompt_builder=mock_prompt_builder,
        agent_repository=mock_agent_repository,
        work_item_service=mock_work_item_service,
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
        last_interaction_timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        status="active",
    )


@pytest.fixture
def sample_comment():
    """Create a sample comment for testing."""
    return Comment(
        id="comment-11",
        author="user123",
        body="Can you explain section 2 in more detail?",
        created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
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
        # Config is now DiscussionMonitoringConfig object (not a dict)
        config = call_args[0][1]
        assert config.project_id == project_id

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
                "", "proj-1", {"column_name": "In Review", "agent_assignment": "reviewer"}
            )

    async def test_initialize_loop_missing_agent_assignment(self, orchestrator):
        """Test initialization fails with missing required agent_assignment."""
        with pytest.raises(ValueError, match="agent_assignment"):
            await orchestrator.initialize_loop(
                "issue-42",
                "proj-1",
                {"column_name": "In Review"},  # Missing agent_assignment
            )

    async def test_initialize_loop_monitoring_failure(self, orchestrator, mock_discussion_adapter, mock_event_store):
        """Test initialization cleanup on monitoring start failure."""
        mock_discussion_adapter.start_monitoring.side_effect = Exception("Monitoring failed")

        with pytest.raises(Exception, match="Monitoring failed"):
            await orchestrator.initialize_loop(
                "issue-42", "proj-1", {"column_name": "In Review", "agent_assignment": "reviewer"}
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
                "issue-42", "proj-1", {"column_name": "In Review", "agent_assignment": "reviewer"}
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
        mock_coding_agent,
        mock_prompt_builder,
        mock_event_store,
        sample_session_state,
        sample_comment,
    ):
        """Test successful comment handling and response posting."""
        # Mock session state loading
        snapshot_data = {"conversational_session_state": sample_session_state.to_dict()}
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=snapshot_data)

        # Mock agent execution
        mock_coding_agent.execute = AsyncMock(
            return_value=CodingAgentResult(
                success=True,
                summary_text="This is the agent's response.",
                total_cost_usd=Decimal("0.00"),
                total_input_tokens=0,
                total_output_tokens=0,
                tool_call_count=0,
                duration_ms=0,
                error_summary=None,
            )
        )

        # Mock comment posting with proper Comment object
        mock_response_comment = Comment(
            id="comment-12",
            author="codetoreum-bot",
            body="This is the agent's response.",
            created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            parent_id=None,
            is_bot=True,
        )
        mock_discussion_adapter.add_comment = AsyncMock(return_value=mock_response_comment)

        # Create event with comment
        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
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

        # Verify agent execution. The execute() call signature is
        # (execution, workspace_context, options) — we just confirm it was called
        # and that the comment text reached the prompt builder.
        mock_coding_agent.execute.assert_called_once()
        # Verify prompt_builder.build received prior_outputs containing the
        # current comment text (the agent-facing channel for thread context).
        builder_call = mock_prompt_builder.build.call_args
        prior_outputs = builder_call.kwargs["prior_outputs"]
        assert any("Can you explain section 2" in po.output for po in prior_outputs)

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
        assert events[0].response_comment_id == "comment-12"  # Agent's response comment ID
        assert events[0].agent_name == "code-reviewer"
        # conversation_id flows from session_state.llm_conversation_id (kept for legacy)
        assert events[0].conversation_id == "conv-abc123"

    async def test_handle_comment_empty_response(
        self,
        orchestrator,
        mock_discussion_adapter,
        mock_coding_agent,
        mock_event_store,
        sample_session_state,
        sample_comment,
    ):
        """Test that empty agent responses raise EmptyAgentResponseError."""
        from codetoreum.ports.exceptions import EmptyAgentResponseError

        # Mock session state loading
        snapshot_data = {"conversational_session_state": sample_session_state.to_dict()}
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=snapshot_data)

        # Mock agent execution returning empty content
        mock_coding_agent.execute = AsyncMock(
            return_value=CodingAgentResult(
                success=True,
                summary_text="",  # Empty response
                total_cost_usd=Decimal("0.00"),
                total_input_tokens=0,
                total_output_tokens=0,
                tool_call_count=0,
                duration_ms=0,
                error_summary=None,
            )
        )

        # Create event with comment
        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
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
        mock_coding_agent.execute.assert_called_once()

        # Verify no comment was posted (agent response never reached posting stage)
        mock_discussion_adapter.add_comment.assert_not_called()

        # Verify no success event was emitted
        mock_event_store.append.assert_not_called()

        # Verify session state was NOT updated (snapshot not saved)
        mock_event_store.save_snapshot.assert_not_called()

    async def test_handle_comment_no_session(self, orchestrator, mock_event_store, sample_comment):
        """Test comment handling when no session exists."""
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=None)

        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id="issue-42",
            project_id="proj-1",
            comment=sample_comment,
            context=CommentContext(
                column_name="In Review",
                agent_assignment="code-reviewer",
            ),
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

        snapshot_data = {"conversational_session_state": suspended_state.to_dict()}
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=snapshot_data)

        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id="issue-42",
            project_id="proj-1",
            comment=sample_comment,
            context=CommentContext(
                column_name="In Review",
                agent_assignment="code-reviewer",
            ),
        )

        # Should handle gracefully - no exception
        await orchestrator.handle_comment_event(event)

    async def test_handle_comment_missing_comment_body(self, orchestrator, mock_event_store):
        """Test comment event without comment body is skipped."""
        mock_event_store.get_events = AsyncMock(return_value=[])

        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id="issue-42",
            project_id="proj-1",
            comment=None,  # No comment
            context=CommentContext(
                column_name="In Review",
                agent_assignment="code-reviewer",
            ),
        )

        # Should handle gracefully (log warning and return)
        await orchestrator.handle_comment_event(event)

    async def test_handle_comment_duplicate_prevention(
        self,
        orchestrator,
        mock_discussion_adapter,
        mock_coding_agent,
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

        snapshot_data = {"conversational_session_state": processed_state.to_dict()}
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=snapshot_data)

        # Create event with same comment ID
        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
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
        mock_coding_agent.execute.assert_not_called()

        # Verify comment was NOT posted
        mock_discussion_adapter.add_comment.assert_not_called()

    async def test_handle_comment_adapter_returns_none(
        self,
        orchestrator,
        mock_discussion_adapter,
        mock_coding_agent,
        mock_event_store,
        sample_session_state,
        sample_comment,
    ):
        """Test error handling when adapter returns None for add_comment."""
        # Mock session state loading
        snapshot_data = {"conversational_session_state": sample_session_state.to_dict()}
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=snapshot_data)

        # Mock agent execution
        mock_coding_agent.execute = AsyncMock(
            return_value=CodingAgentResult(
                success=True,
                summary_text="This is the agent's response.",
                total_cost_usd=Decimal("0.00"),
                total_input_tokens=0,
                total_output_tokens=0,
                tool_call_count=0,
                duration_ms=0,
                error_summary=None,
            )
        )

        # Mock adapter returning None (invalid response)
        mock_discussion_adapter.add_comment = AsyncMock(return_value=None)

        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id="issue-42",
            project_id="proj-1",
            comment=sample_comment,
            context=CommentContext(
                column_name="In Review",
                agent_assignment="code-reviewer",
            ),
        )

        # Should raise ValueError when adapter returns None
        with pytest.raises(ValueError, match="returned None"):
            await orchestrator.handle_comment_event(event)

    async def test_handle_comment_adapter_returns_invalid_type(
        self,
        orchestrator,
        mock_discussion_adapter,
        mock_coding_agent,
        mock_event_store,
        sample_session_state,
        sample_comment,
    ):
        """Test error handling when adapter returns invalid comment type."""
        # Mock session state loading
        snapshot_data = {"conversational_session_state": sample_session_state.to_dict()}
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=snapshot_data)

        # Mock agent execution
        mock_coding_agent.execute = AsyncMock(
            return_value=CodingAgentResult(
                success=True,
                summary_text="This is the agent's response.",
                total_cost_usd=Decimal("0.00"),
                total_input_tokens=0,
                total_output_tokens=0,
                tool_call_count=0,
                duration_ms=0,
                error_summary=None,
            )
        )

        # Mock adapter returning invalid type
        mock_discussion_adapter.add_comment = AsyncMock(return_value={"id": "comment-12"})  # dict instead of Comment

        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id="issue-42",
            project_id="proj-1",
            comment=sample_comment,
            context=CommentContext(
                column_name="In Review",
                agent_assignment="code-reviewer",
            ),
        )

        # Should raise ValueError when adapter returns wrong type
        with pytest.raises(ValueError, match="invalid comment type"):
            await orchestrator.handle_comment_event(event)

    async def test_handle_comment_adapter_returns_comment_no_id(
        self,
        orchestrator,
        mock_discussion_adapter,
        mock_coding_agent,
        mock_event_store,
        sample_session_state,
        sample_comment,
    ):
        """Test error handling when adapter returns comment with no ID."""
        # Mock session state loading
        snapshot_data = {"conversational_session_state": sample_session_state.to_dict()}
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=snapshot_data)

        # Mock agent execution
        mock_coding_agent.execute = AsyncMock(
            return_value=CodingAgentResult(
                success=True,
                summary_text="This is the agent's response.",
                total_cost_usd=Decimal("0.00"),
                total_input_tokens=0,
                total_output_tokens=0,
                tool_call_count=0,
                duration_ms=0,
                error_summary=None,
            )
        )

        # Mock adapter returning comment with empty ID
        # Create a mock that will pass isinstance(obj, Comment) check
        bad_comment = MagicMock(spec=Comment)
        bad_comment.id = ""  # Empty ID
        mock_discussion_adapter.add_comment = AsyncMock(return_value=bad_comment)

        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id="issue-42",
            project_id="proj-1",
            comment=sample_comment,
            context=CommentContext(
                column_name="In Review",
                agent_assignment="code-reviewer",
            ),
        )

        # Should raise ValueError when comment has no ID
        with pytest.raises(ValueError, match="empty ID"):
            await orchestrator.handle_comment_event(event)

    async def test_handle_comment_with_none_conversation_id(
        self,
        orchestrator,
        mock_discussion_adapter,
        mock_coding_agent,
        mock_event_store,
        sample_session_state,
        sample_comment,
    ):
        """Test that None conversation_id falls back to session state value."""
        # Mock session state loading with existing conversation ID
        session_with_conv = ConversationalSessionState(
            session_id=sample_session_state.session_id,
            work_item_id=sample_session_state.work_item_id,
            project_id=sample_session_state.project_id,
            agent_assignment=sample_session_state.agent_assignment,
            column_name=sample_session_state.column_name,
            llm_conversation_id="conv-existing-123",  # Pre-existing conversation ID
            last_processed_comment_id=sample_session_state.last_processed_comment_id,
            last_interaction_timestamp=sample_session_state.last_interaction_timestamp,
            status="active",
        )
        snapshot_data = {"conversational_session_state": session_with_conv.to_dict()}
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=snapshot_data)

        # Mock agent execution returning None for conversation_id
        mock_coding_agent.execute = AsyncMock(
            return_value=CodingAgentResult(
                success=True,
                summary_text="This is the agent's response.",
                total_cost_usd=Decimal("0.00"),
                total_input_tokens=0,
                total_output_tokens=0,
                tool_call_count=0,
                duration_ms=0,
                error_summary=None,
            )
        )

        # Mock adapter returning comment with ID
        posted_comment = MagicMock(spec=Comment)
        posted_comment.id = "comment-xyz789"
        mock_discussion_adapter.add_comment = AsyncMock(return_value=posted_comment)

        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id="issue-42",
            project_id="proj-1",
            comment=sample_comment,
            context=CommentContext(
                column_name="In Review",
                agent_assignment="code-reviewer",
            ),
        )

        # Handle comment event should succeed with fallback
        await orchestrator.handle_comment_event(event)

        # Verify agent execution was called
        mock_coding_agent.execute.assert_called_once()

        # Verify comment was posted
        mock_discussion_adapter.add_comment.assert_called_once()

        # Verify snapshot was saved with FALLBACK conversation ID (existing one)
        mock_event_store.save_snapshot.assert_called_once()
        # Check the snapshot kwarg
        saved_snapshot = mock_event_store.save_snapshot.call_args.kwargs["snapshot"]
        assert saved_snapshot["conversational_session_state"]["llm_conversation_id"] == "conv-existing-123"

    async def test_handle_comment_column_change_between_conversational_columns(
        self,
        orchestrator,
        mock_discussion_adapter,
        mock_coding_agent,
        mock_event_store,
        sample_session_state,
        sample_comment,
    ):
        """Test comment handling when work item's column has changed.

        This tests the behavior described in the docstring where a work item
        moves between conversational columns. Per implementation review, the
        code does NOT terminate the session on column change, but instead
        continues processing. This test documents current behavior.
        """
        # Mock session state loading with "In Progress" column
        session_in_progress = ConversationalSessionState(
            session_id=sample_session_state.session_id,
            work_item_id=sample_session_state.work_item_id,
            project_id=sample_session_state.project_id,
            agent_assignment=sample_session_state.agent_assignment,
            column_name="In Progress",  # Original column (conversational)
            llm_conversation_id=sample_session_state.llm_conversation_id,
            last_processed_comment_id=sample_session_state.last_processed_comment_id,
            last_interaction_timestamp=sample_session_state.last_interaction_timestamp,
            status="active",
        )
        snapshot_data = {"conversational_session_state": session_in_progress.to_dict()}
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=snapshot_data)

        # Mock agent execution
        mock_coding_agent.execute = AsyncMock(
            return_value=CodingAgentResult(
                success=True,
                summary_text="Agent response to the comment.",
                total_cost_usd=Decimal("0.00"),
                total_input_tokens=0,
                total_output_tokens=0,
                tool_call_count=0,
                duration_ms=0,
                error_summary=None,
            )
        )

        # Mock adapter returning comment with ID
        posted_comment = MagicMock(spec=Comment)
        posted_comment.id = "comment-xyz789"
        mock_discussion_adapter.add_comment = AsyncMock(return_value=posted_comment)

        # Mock stream version for snapshot
        mock_event_store.get_stream_version = AsyncMock(return_value=5)

        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id="issue-42",
            project_id="proj-1",
            comment=sample_comment,
            context=CommentContext(
                column_name="In Review",  # Different conversational column than session
                agent_assignment="code-reviewer",
            ),
        )

        # Handle comment event - implementation continues processing despite column change
        await orchestrator.handle_comment_event(event)

        # Verify LLM execution was called (doesn't terminate on column change)
        mock_coding_agent.execute.assert_called_once()

        # Verify comment was posted
        mock_discussion_adapter.add_comment.assert_called_once()

        # Verify session state was updated (snapshot saved)
        # Even though column changed, session continues with existing context
        mock_event_store.save_snapshot.assert_called_once()

    async def test_handle_comment_event_store_failure_after_comment_posted(
        self,
        orchestrator,
        mock_discussion_adapter,
        mock_coding_agent,
        mock_event_store,
        sample_session_state,
        sample_comment,
    ):
        """Test partial failure scenario where comment is posted but event store fails."""
        # Mock session state loading
        snapshot_data = {"conversational_session_state": sample_session_state.to_dict()}
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=snapshot_data)

        # Mock agent execution
        mock_coding_agent.execute = AsyncMock(
            return_value=CodingAgentResult(
                success=True,
                summary_text="This is the agent's response.",
                total_cost_usd=Decimal("0.00"),
                total_input_tokens=0,
                total_output_tokens=0,
                tool_call_count=0,
                duration_ms=0,
                error_summary=None,
            )
        )

        # Mock adapter successfully posting comment
        posted_comment = MagicMock(spec=Comment)
        posted_comment.id = "comment-xyz789"
        mock_discussion_adapter.add_comment = AsyncMock(return_value=posted_comment)

        # Mock event store failure during snapshot save (after comment posted)
        mock_event_store.save_snapshot = AsyncMock(side_effect=Exception("Storage failed"))

        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id="issue-42",
            project_id="proj-1",
            comment=sample_comment,
            context=CommentContext(
                column_name="In Review",
                agent_assignment="code-reviewer",
            ),
        )

        # Handle comment event should raise the storage error
        with pytest.raises(Exception, match="Storage failed"):
            await orchestrator.handle_comment_event(event)

        # Verify comment WAS posted (partial failure - can't roll back)
        mock_discussion_adapter.add_comment.assert_called_once()

        # Verify agent execution WAS called
        mock_coding_agent.execute.assert_called_once()

        # Verify the exception happened during snapshot save
        mock_event_store.save_snapshot.assert_called_once()


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
        snapshot_data = {"conversational_session_state": sample_session_state.to_dict()}
        mock_event_store.get_latest_snapshot = AsyncMock(return_value=snapshot_data)

        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
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
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
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
                timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
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
        snapshot_data = {"conversational_session_state": sample_session_state.to_dict()}
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

        snapshot_data = {"conversational_session_state": terminated_state.to_dict()}
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
        snapshot_data = {"conversational_session_state": sample_session_state.to_dict()}
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
        snapshot_data = {"conversational_session_state": sample_session_state.to_dict()}
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
        """Test building thread message with full context (discussion thread context only)."""
        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id="issue-42",
            project_id="proj-1",
            comment=sample_comment,
            context=CommentContext(
                column_name="In Review",  # Column context is optional, not included in message
                agent_assignment="code-reviewer",  # Agent context is optional, not included in message
            ),
        )

        message = orchestrator._build_thread_message(event, sample_session_state)

        # Message includes comment content, not column/agent context (decoupled)
        assert "Can you explain section 2" in message
        assert "user123" in message
        # Board-level context (column_name, agent_assignment) no longer mixed into discussion context
        assert "In Review" not in message
        assert "code-reviewer" not in message

    def test_build_thread_message_without_context(self, orchestrator, sample_comment, sample_session_state):
        """Test building thread message without context."""
        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id="issue-42",
            project_id="proj-1",
            comment=sample_comment,
            context=None,
        )

        message = orchestrator._build_thread_message(event, sample_session_state)

        assert "Can you explain section 2" in message
        assert "user123" in message

    def test_build_thread_message_with_optional_context(self, orchestrator, sample_comment, sample_session_state):
        """Test building thread message with optional context fields (now all optional)."""
        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id="issue-42",
            project_id="proj-1",
            comment=sample_comment,
            context=CommentContext(
                column_name=None,  # Now optional
                agent_assignment=None,  # Now optional
            ),
        )

        message = orchestrator._build_thread_message(event, sample_session_state)

        # Message still includes comment content
        assert "Can you explain section 2" in message
        assert "user123" in message
        # Board context fields not included (decoupled from discussion context)
        assert "Work item:" not in message
        assert "Assigned agent:" not in message

    def test_build_thread_message_with_parent_comment(self, orchestrator, sample_comment, sample_session_state):
        """Test building thread message includes parent comment context."""
        parent = Comment(
            id="comment-10",
            author="alice",
            body="What's your approach to this?",
            created_at=datetime.now(UTC).isoformat(),
        )

        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id="issue-42",
            project_id="proj-1",
            comment=sample_comment,
            context=CommentContext(
                thread_id="thread-42",
                parent_comment=parent,
                is_initial_request=False,
            ),
        )

        message = orchestrator._build_thread_message(event, sample_session_state)

        # Should include parent comment and current comment
        assert "What's your approach to this?" in message
        assert "alice" in message
        assert "Can you explain section 2" in message
        assert "user123" in message


class TestHandleCommentEventContextValidation:
    """Test suite for CommentNeedsResponseEvent context validation."""

    async def test_handle_comment_event_with_context_none(
        self,
        orchestrator,
        mock_event_store,
        sample_comment,
    ):
        """Test handle_comment_event raises ValueError when context is None."""
        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id="issue-42",
            project_id="proj-1",
            comment=sample_comment,
            context=None,  # Missing required context
        )

        with pytest.raises(ValueError, match="CommentNeedsResponseEvent must have context"):
            await orchestrator.handle_comment_event(event)
