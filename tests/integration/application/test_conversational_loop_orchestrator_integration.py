"""Integration tests for ConversationalLoopOrchestrator with mock adapters.

These tests verify the orchestrator's integration with adapter implementations:
- Interaction with discussion adapter for monitoring and comment posting
- Interaction with LLM provider for agent execution
- Interaction with event store for session state persistence
- Error handling and recovery across components
"""

import pytest
from datetime import datetime, timezone
from typing import Dict, List, Optional
from unittest.mock import AsyncMock

from codetoreum.application.conversational_loop_orchestrator import (
    ConversationalLoopOrchestrator,
)
from codetoreum.domain.conversational_session import ConversationalSessionState
from codetoreum.domain.events.discussion_events import (
    Comment,
    CommentContext,
    CommentNeedsResponseEvent,
)


class MockDiscussionAdapter:
    """Mock implementation of IDiscussionAdapter for testing."""

    def __init__(self):
        self.monitoring_sessions: Dict[str, dict] = {}
        self.comments_posted: List[dict] = []

    def start_monitoring(self, work_item_id: str, config: dict) -> None:
        """Start monitoring for comments on a work item."""
        self.monitoring_sessions[work_item_id] = config

    def stop_monitoring(self, work_item_id: str) -> None:
        """Stop monitoring for comments."""
        if work_item_id in self.monitoring_sessions:
            del self.monitoring_sessions[work_item_id]

    async def add_comment(
        self,
        work_item_id: str,
        content: str,
        parent_id: Optional[str] = None,
    ) -> dict:
        """Post a comment to a work item."""
        comment = {
            "id": f"comment-{len(self.comments_posted) + 1}",
            "work_item_id": work_item_id,
            "content": content,
            "parent_id": parent_id,
            "posted_at": datetime.now(timezone.utc).isoformat(),
        }
        self.comments_posted.append(comment)
        return comment

    def on(self, event_type: str, handler) -> None:
        """Subscribe to adapter events."""
        pass

    async def get_thread(self, work_item_id: str) -> dict:
        """Get discussion thread for a work item."""
        return {
            "id": f"thread-{work_item_id}",
            "comments": [],
        }


class MockLLMProvider:
    """Mock implementation of ILLMProvider for testing."""

    def __init__(self):
        self.executions: List[dict] = []
        self.conversations: Dict[str, List[str]] = {}

    async def execute_prompt(self, prompt: str, context=None, stream_callback=None):
        """Execute a one-time prompt."""
        from unittest.mock import MagicMock
        result = MagicMock()
        result.content = "Mock response to prompt"
        result.conversation_id = None
        return result

    async def continue_conversation(
        self,
        conversation_id: str,
        message: str,
        stream_callback=None,
    ):
        """Continue an existing conversation."""
        from unittest.mock import MagicMock

        # Track conversation
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = []
        self.conversations[conversation_id].append(message)

        # Record execution
        self.executions.append({
            "conversation_id": conversation_id,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        result = MagicMock()
        result.content = f"Agent response to: {message[:50]}..."
        result.conversation_id = conversation_id or "conv-new-session"
        result.duration_ms = 100
        result.finish_reason = "stop"
        return result

    async def get_model_info(self):
        """Get model information."""
        return {
            "model": "mock-model",
            "supports_conversations": True,
        }


class EventObject:
    """Simple event object wrapper for mock event store."""
    def __init__(self, event_dict: dict):
        # Store just the 'data' field of the event, matching what the orchestrator expects
        self.data = event_dict.get("data", {})

    def get(self, key, default=None):
        """Dict-like access for backwards compatibility."""
        return self.data.get(key, default)


class MockEventStore:
    """Mock implementation of IEventStore for testing."""

    def __init__(self):
        self.events: List[dict] = []
        self.snapshots: Dict[str, dict] = {}

    async def append(self, event: dict) -> None:
        """Append event to store."""
        self.events.append(event)
        # Extract session state from snapshot events
        if event.get("type") == "conversational_session_snapshot":
            aggregate_id = event.get("aggregate_id")
            state_data = event.get("data", {}).get("conversational_session_state")
            if aggregate_id and state_data:
                self.snapshots[aggregate_id] = state_data

    async def get_events(self, aggregate_id: str, from_version: int = 0) -> List:
        """Get events for an aggregate."""
        matching_events = [
            e for e in self.events
            if e.get("aggregate_id") == aggregate_id or e.get("work_item_id") == aggregate_id
        ]
        # Wrap dict events in EventObject to provide .data attribute
        return [EventObject(e) for e in matching_events]

    async def get_all_events(self, from_timestamp=None, to_timestamp=None) -> List[dict]:
        """Get all events in time range."""
        return self.events

    def get_latest_snapshot(self, aggregate_id: str) -> Optional[dict]:
        """Get latest session state snapshot."""
        return self.snapshots.get(aggregate_id)


@pytest.fixture
def mock_discussion_adapter():
    """Create a mock discussion adapter."""
    return MockDiscussionAdapter()


@pytest.fixture
def mock_llm_provider():
    """Create a mock LLM provider."""
    return MockLLMProvider()


@pytest.fixture
def mock_event_store():
    """Create a mock event store."""
    return MockEventStore()


@pytest.fixture
def orchestrator(mock_discussion_adapter, mock_llm_provider, mock_event_store):
    """Create orchestrator with mock adapters."""
    return ConversationalLoopOrchestrator(
        discussion_adapter=mock_discussion_adapter,
        llm_provider=mock_llm_provider,
        event_store=mock_event_store,
    )


class TestFullConversationFlow:
    """Test complete conversational flow from initialization to completion."""

    async def test_complete_conversation_flow(
        self,
        orchestrator,
        mock_discussion_adapter,
        mock_llm_provider,
        mock_event_store,
    ):
        """Test a complete conversation flow from start to finish."""
        work_item_id = "issue-42"
        project_id = "proj-1"

        # Step 1: Initialize conversational loop
        session = await orchestrator.initialize_loop(
            work_item_id,
            project_id,
            {
                "column_name": "In Review",
                "agent_assignment": "code-reviewer",
            }
        )

        assert session.status == "active"
        assert session.work_item_id == work_item_id
        assert work_item_id in mock_discussion_adapter.monitoring_sessions

        # Step 2: First comment from human
        first_comment = Comment(
            id="comment-1",
            author="user1",
            body="Can you review this code?",
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

        event1 = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id=work_item_id,
            project_id=project_id,
            comment=first_comment,
            context=CommentContext(
                column_name="In Review",
                agent_assignment="code-reviewer",
            ),
        )

        await orchestrator.handle_comment_event(event1)

        # Verify agent response was posted
        assert len(mock_discussion_adapter.comments_posted) == 1
        response1 = mock_discussion_adapter.comments_posted[0]
        assert response1["parent_id"] == first_comment.id
        assert response1["work_item_id"] == work_item_id

        # Verify session state was updated
        updated_session = await orchestrator.load_session_state(work_item_id)
        assert updated_session is not None
        assert updated_session.last_processed_comment_id == first_comment.id
        assert updated_session.status == "active"

        # Step 3: Second comment from human (follow-up question)
        second_comment = Comment(
            id="comment-2",
            author="user1",
            body="What about error handling?",
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            parent_id=response1["id"],
        )

        # Create a Comment object for the parent instead of using dict
        parent_comment = Comment(
            id=response1["id"],
            author="bot",
            body=response1["content"],
            created_at=response1["posted_at"],
        )

        event2 = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id=work_item_id,
            project_id=project_id,
            comment=second_comment,
            context=CommentContext(
                column_name="In Review",
                agent_assignment="code-reviewer",
                parent_comment=parent_comment,
            ),
        )

        await orchestrator.handle_comment_event(event2)

        # Verify second agent response was posted
        assert len(mock_discussion_adapter.comments_posted) == 2
        response2 = mock_discussion_adapter.comments_posted[1]
        assert response2["parent_id"] == second_comment.id

        # Verify conversation context was maintained in LLM
        assert len(mock_llm_provider.executions) == 2
        assert mock_llm_provider.executions[0]["message"] is not None
        assert mock_llm_provider.executions[1]["message"] is not None

        # Step 4: Work item moves out of review column
        from codetoreum.domain.events.board_events import WorkItemColumnChangedEvent

        column_change_event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id=work_item_id,
            project_id=project_id,
            board_id="board-1",
            from_column="In Review",
            to_column="Testing",
        )

        await orchestrator.handle_column_change_event(column_change_event)

        # Verify monitoring was stopped
        assert work_item_id not in mock_discussion_adapter.monitoring_sessions

        # Verify session is terminated
        final_session = await orchestrator.load_session_state(work_item_id)
        assert final_session.status == "terminated"

    async def test_multiple_conversations_independent(
        self,
        orchestrator,
        mock_discussion_adapter,
        mock_event_store,
    ):
        """Test multiple independent conversations on different work items."""
        # Initialize two separate conversations
        session1 = await orchestrator.initialize_loop(
            "issue-1",
            "proj-1",
            {"column_name": "In Review", "agent_assignment": "reviewer-a"},
        )

        session2 = await orchestrator.initialize_loop(
            "issue-2",
            "proj-1",
            {"column_name": "In Review", "agent_assignment": "reviewer-b"},
        )

        # Verify both are independent
        assert session1.work_item_id != session2.work_item_id
        assert session1.agent_assignment != session2.agent_assignment
        assert len(mock_discussion_adapter.monitoring_sessions) == 2

        # Load both sessions
        loaded1 = await orchestrator.load_session_state("issue-1")
        loaded2 = await orchestrator.load_session_state("issue-2")

        assert loaded1.session_id == session1.session_id
        assert loaded2.session_id == session2.session_id


class TestErrorRecovery:
    """Test error handling and recovery scenarios."""

    async def test_recovery_after_agent_error(
        self,
        orchestrator,
        mock_discussion_adapter,
        mock_llm_provider,
        mock_event_store,
    ):
        """Test recovery after agent execution failure."""
        work_item_id = "issue-42"
        project_id = "proj-1"

        # Initialize session
        session = await orchestrator.initialize_loop(
            work_item_id,
            project_id,
            {"column_name": "In Review", "agent_assignment": "reviewer"},
        )

        # Create comment that will trigger agent
        comment = Comment(
            id="comment-1",
            author="user1",
            body="Review this",
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

        # Make LLM provider fail
        mock_llm_provider.continue_conversation = AsyncMock(
            side_effect=Exception("Agent execution failed")
        )

        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id=work_item_id,
            project_id=project_id,
            comment=comment,
        )

        # Should raise exception but session should still exist
        with pytest.raises(Exception, match="Agent execution failed"):
            await orchestrator.handle_comment_event(event)

        # Session should still be active (not cleaned up on transient error)
        loaded_session = await orchestrator.load_session_state(work_item_id)
        assert loaded_session is not None
        assert loaded_session.status == "active"

    async def test_cleanup_on_fatal_error(
        self,
        orchestrator,
        mock_discussion_adapter,
        mock_event_store,
    ):
        """Test cleanup after fatal error."""
        work_item_id = "issue-42"
        project_id = "proj-1"

        # Initialize session
        session = await orchestrator.initialize_loop(
            work_item_id,
            project_id,
            {"column_name": "In Review", "agent_assignment": "reviewer"},
        )

        # Cleanup due to fatal error
        await orchestrator.cleanup_loop(work_item_id, "Fatal error: out of memory")

        # Verify monitoring was stopped
        assert work_item_id not in mock_discussion_adapter.monitoring_sessions

        # Verify session is terminated
        loaded_session = await orchestrator.load_session_state(work_item_id)
        assert loaded_session.status == "terminated"


class TestSessionPersistence:
    """Test session state persistence across restarts."""

    async def test_session_state_survives_restart(
        self,
        orchestrator,
        mock_discussion_adapter,
        mock_llm_provider,
        mock_event_store,
    ):
        """Test that session state survives orchestrator restart."""
        work_item_id = "issue-42"
        project_id = "proj-1"

        # Initialize and run conversation
        session1 = await orchestrator.initialize_loop(
            work_item_id,
            project_id,
            {"column_name": "In Review", "agent_assignment": "reviewer"},
        )

        # Simulate comment
        comment = Comment(
            id="comment-1",
            author="user1",
            body="Review this",
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id=work_item_id,
            project_id=project_id,
            comment=comment,
        )

        await orchestrator.handle_comment_event(event)

        # Get session state after interaction
        session_after_comment = await orchestrator.load_session_state(work_item_id)
        assert session_after_comment.last_processed_comment_id == comment.id

        # Simulate restart: create new orchestrator instance with same event store
        orchestrator_restarted = ConversationalLoopOrchestrator(
            discussion_adapter=mock_discussion_adapter,
            llm_provider=mock_llm_provider,
            event_store=mock_event_store,
        )

        # Load session from restarted instance
        session_reloaded = await orchestrator_restarted.load_session_state(work_item_id)

        # Verify state is fully recovered
        assert session_reloaded is not None
        assert session_reloaded.session_id == session1.session_id
        assert session_reloaded.last_processed_comment_id == comment.id
        assert session_reloaded.status == "active"

    async def test_session_checkpoint_for_resume(
        self,
        orchestrator,
        mock_discussion_adapter,
        mock_event_store,
    ):
        """Test that session checkpoint enables efficient resume."""
        work_item_id = "issue-42"

        # Initialize
        session = await orchestrator.initialize_loop(
            work_item_id,
            "proj-1",
            {"column_name": "In Review", "agent_assignment": "reviewer"},
        )

        # Simulate processing multiple comments
        for i in range(3):
            # Load session
            current = await orchestrator.load_session_state(work_item_id)

            # Simulate comment processing
            comment = Comment(
                id=f"comment-{i}",
                author="user1",
                body="Comment",
                created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )

            event = CommentNeedsResponseEvent(
                type="comment.needs_response",
                timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                source="github",
                work_item_id=work_item_id,
                project_id="proj-1",
                comment=comment,
            )

            await orchestrator.handle_comment_event(event)

        # Final session should have last checkpoint
        final_session = await orchestrator.load_session_state(work_item_id)
        assert final_session.last_processed_comment_id == "comment-2"


class TestAdapterInteraction:
    """Test orchestrator's interaction with adapters."""

    async def test_discussion_adapter_monitoring_config(
        self,
        orchestrator,
        mock_discussion_adapter,
    ):
        """Test that discussion adapter receives correct monitoring config."""
        work_item_id = "issue-42"

        await orchestrator.initialize_loop(
            work_item_id,
            "proj-1",
            {
                "column_name": "In Review",
                "agent_assignment": "code-reviewer",
            }
        )

        # Verify monitoring config passed to adapter
        assert work_item_id in mock_discussion_adapter.monitoring_sessions
        config = mock_discussion_adapter.monitoring_sessions[work_item_id]
        assert config["column_name"] == "In Review"
        assert config["agent_assignment"] == "code-reviewer"

    async def test_llm_provider_conversation_continuity(
        self,
        orchestrator,
        mock_llm_provider,
        mock_event_store,
    ):
        """Test that LLM provider receives conversation IDs for context continuity."""
        work_item_id = "issue-42"

        # Initialize with conversation context
        session = await orchestrator.initialize_loop(
            work_item_id,
            "proj-1",
            {"column_name": "In Review", "agent_assignment": "reviewer"},
        )

        # Manually set conversation ID in session
        updated_session = ConversationalSessionState(
            session_id=session.session_id,
            work_item_id=session.work_item_id,
            project_id=session.project_id,
            agent_assignment=session.agent_assignment,
            column_name=session.column_name,
            llm_conversation_id="conv-abc123",
            last_processed_comment_id="__checkpoint_start",
            last_interaction_timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            status="active",
        )
        await orchestrator.save_session_state(updated_session)

        # Handle comment
        comment = Comment(
            id="comment-1",
            author="user1",
            body="Question?",
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id=work_item_id,
            project_id="proj-1",
            comment=comment,
        )

        await orchestrator.handle_comment_event(event)

        # Verify LLM provider was called with conversation ID
        assert len(mock_llm_provider.executions) == 1
        execution = mock_llm_provider.executions[0]
        assert execution["conversation_id"] == "conv-abc123"
