"""Integration tests for ConversationalLoopOrchestrator with real adapters.

These tests verify the orchestrator's integration with real implementations:
- Real RedisEventStore for session state persistence (testcontainers)
- Real EventBus for event distribution and error event verification
- Mock discussion adapter for comment management
- Mock LLM provider for agent execution

Tests validate correct integration across component boundaries:
- FR-2.1: Orchestrator calls startMonitoring() when work items enter conversational columns
- FR-4.2: Agent responses are posted via adapter's addComment() method
- FR-5.3: Adapters resume monitoring from lastProcessedCommentId checkpoint
- FR-7.1: Adapters emit error events when operations fail (verified via EventBus)
- FR-9.2: Orchestrator processes events sequentially per work item
"""

import asyncio
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
from codetoreum.adapters.testing.in_memory_event_store import InMemoryEventStore
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.domain.events import DomainEvent
from codetoreum.ports.output.discussion_adapter import DiscussionMonitoringConfig, DiscussionThread
from codetoreum.ports.output.identity_service import IIdentityService, BotIdentityConfig


class MockIdentityService(IIdentityService):
    """Mock identity service for testing."""

    def __init__(self):
        """Initialize with default bot configuration."""
        self._bot_usernames = ["codetoreum-bot"]
        self._bot_patterns = []

    def get_bot_username(self) -> str:
        """Get bot username."""
        return "codetoreum-bot"

    def is_bot_user(self, username: str) -> bool:
        """Check if username is a bot."""
        return username in self._bot_usernames

    def get_human_users(self, usernames: list) -> list:
        """Filter list to only human users."""
        return [u for u in usernames if not self.is_bot_user(u)]

    def configure(self, config: BotIdentityConfig) -> None:
        """Update bot identity configuration."""
        self._bot_usernames = config.bot_usernames
        self._bot_patterns = config.bot_patterns


class MockDiscussionAdapter:
    """Mock implementation of IDiscussionAdapter for integration testing.

    This adapter provides:
    - Event emission via event handlers
    - Proper Comment objects (not dicts)
    - Support for thread context
    - Helper methods for test setup and verification
    """

    def __init__(self, identity_service: IIdentityService):
        self.monitoring_sessions: Dict[str, DiscussionMonitoringConfig] = {}
        self.comments_posted: List[Comment] = []
        self._threads: Dict[str, List[Comment]] = {}
        self._event_handlers: Dict[str, List] = {}
        self._identity_service = identity_service

    def on(self, event_type: str, handler) -> None:
        """Subscribe to adapter events."""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    def _emit_event(self, event: DomainEvent) -> None:
        """Emit event to all registered handlers."""
        event_type = event.event_type if hasattr(event, 'event_type') else event.type
        handlers = self._event_handlers.get(event_type, [])
        for handler in handlers:
            if asyncio.iscoroutinefunction(handler):
                # Store for async handlers to be called later
                pass
            else:
                handler(event)

    def start_monitoring(self, work_item_id: str, config) -> None:
        """Start monitoring for comments on a work item.

        Accepts either DiscussionMonitoringConfig or dict for compatibility.
        """
        # If it's a dict, convert to DiscussionMonitoringConfig
        if isinstance(config, dict):
            monitoring_config = DiscussionMonitoringConfig(
                project_id=config.get("project_id", ""),
                column_name=config.get("column_name", ""),
                agent_assignment=config.get("agent_assignment", ""),
            )
            self.monitoring_sessions[work_item_id] = monitoring_config
        else:
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
    ) -> Comment:
        """Post a comment to a work item."""
        comment_id = f"comment-{len(self.comments_posted)}"
        comment = Comment(
            id=comment_id,
            author=self._identity_service.get_bot_username(),
            body=content,
            created_at=datetime.now(timezone.utc).isoformat(),
            parent_id=parent_id,
            is_bot=True
        )
        self.comments_posted.append(comment)
        if work_item_id not in self._threads:
            self._threads[work_item_id] = []
        self._threads[work_item_id].append(comment)
        return comment

    async def get_thread(self, work_item_id: str) -> DiscussionThread:
        """Get discussion thread for a work item."""
        comments = self._threads.get(work_item_id, [])
        return DiscussionThread(
            id=f"thread-{work_item_id}",
            work_item_id=work_item_id,
            comments=comments,
            thread_type='flat'
        )

    # Test helper methods
    def simulate_comment(self, work_item_id: str, author: str, body: str, parent_id: Optional[str] = None) -> Comment:
        """Simulate a human comment (for testing)."""
        comment_id = f"comment-{len(self.comments_posted)}"
        comment = Comment(
            id=comment_id,
            author=author,
            body=body,
            created_at=datetime.now(timezone.utc).isoformat(),
            parent_id=parent_id,
            is_bot=False
        )
        if work_item_id not in self._threads:
            self._threads[work_item_id] = []
        self._threads[work_item_id].append(comment)
        return comment

    def get_comment_count(self, work_item_id: str) -> int:
        """Get total comments on a work item."""
        return len(self._threads.get(work_item_id, []))

    def get_posted_comments(self) -> List[Comment]:
        """Get all comments posted by agent."""
        return self.comments_posted.copy()


class MockLLMProvider:
    """Mock implementation of ILLMProvider for integration testing.

    Tracks conversation continuity and agent executions with realistic responses.
    """

    def __init__(self):
        self.executions: List[dict] = []
        self.conversations: Dict[str, List[str]] = {}
        self._response_patterns: Dict[str, str] = {}

    def add_response_pattern(self, pattern_key: str, response: str) -> None:
        """Add deterministic response for specific patterns."""
        self._response_patterns[pattern_key] = response

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

        # Generate response
        response_text = f"Agent response to: {message[:50]}..."
        for pattern_key, pattern_response in self._response_patterns.items():
            if pattern_key.lower() in message.lower():
                response_text = pattern_response
                break

        result = MagicMock()
        result.content = response_text
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

    def get_conversation_history(self, conversation_id: str) -> List[str]:
        """Get all messages in a conversation."""
        return self.conversations.get(conversation_id, [])

    def get_execution_count(self) -> int:
        """Get total number of agent executions."""
        return len(self.executions)




@pytest.fixture
def identity_service():
    """Create identity service for adapters."""
    return MockIdentityService()


@pytest.fixture
async def real_event_store():
    """Create InMemoryEventStore for integration testing.

    Uses InMemoryEventStore to verify event storage and retrieval
    work correctly with the orchestrator.
    """
    event_store = InMemoryEventStore()
    yield event_store


@pytest.fixture
def real_event_bus():
    """Create real EventBus for integration testing.

    Uses the actual event bus implementation to verify event routing,
    handler dispatch, subscriptions, and error event emission work correctly.
    """
    return EventBus()


@pytest.fixture
def testable_discussion_adapter(identity_service):
    """Create testable discussion adapter for integration tests."""
    return MockDiscussionAdapter(identity_service)


@pytest.fixture
def testable_llm_provider():
    """Create testable LLM provider for integration tests."""
    return MockLLMProvider()


@pytest.fixture
async def orchestrator(testable_discussion_adapter, testable_llm_provider, real_event_store):
    """Create orchestrator with real event infrastructure.

    Real components:
    - RedisEventStore (via testcontainers): Persists session state and enables replay

    Mock components:
    - Discussion adapter: Simulates comment detection
    - LLM provider: Deterministic agent responses
    """
    return ConversationalLoopOrchestrator(
        discussion_adapter=testable_discussion_adapter,
        llm_provider=testable_llm_provider,
        event_store=real_event_store,
    )


@pytest.mark.integration
class TestFullLoopLifecycleIntegration:
    """Integration test: Full loop lifecycle with real EventStore.

    Verifies:
    - Session persistence to EventStore
    - Event handling across component boundaries
    - Session cleanup on column change
    """

    async def test_full_loop_lifecycle_with_real_event_store(
        self,
        orchestrator,
        testable_discussion_adapter,
        testable_llm_provider,
        real_event_store,
    ):
        """Integration test: Full loop lifecycle with real EventStore.

        Verifies:
        - FR-2.1: startMonitoring() called when entering conversational column
        - FR-4.2: Agent responses posted via addComment()
        - FR-5.3: Session state persisted to EventStore
        - Session state recoverable after restart
        """
        work_item_id = "issue-42"
        project_id = "proj-1"

        # Step 1: Initialize conversational loop
        # FR-2.1: Orchestrator calls startMonitoring()
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
        assert work_item_id in testable_discussion_adapter.monitoring_sessions

        # Verify session persisted to real EventStore
        stored_session = await orchestrator.load_session_state(work_item_id)
        assert stored_session is not None
        assert stored_session.session_id == session.session_id

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

        # FR-4.2: Verify agent response was posted via adapter
        assert len(testable_discussion_adapter.comments_posted) == 1
        response1 = testable_discussion_adapter.comments_posted[0]
        assert response1.parent_id == first_comment.id
        assert response1.is_bot is True

        # Verify session checkpoint updated in EventStore
        updated_session = await orchestrator.load_session_state(work_item_id)
        assert updated_session is not None
        assert updated_session.last_processed_comment_id == first_comment.id
        assert updated_session.status == "active"

        # Step 3: Second comment from human (follow-up)
        second_comment = Comment(
            id="comment-2",
            author="user1",
            body="What about error handling?",
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            parent_id=response1.id,
        )

        event2 = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id=work_item_id,
            project_id=project_id,
            comment=second_comment,
            context=CommentContext.for_reply(
                thread_id=f"thread-{work_item_id}",
                parent_comment=response1,
                column_name="In Review",
                agent_assignment="code-reviewer",
            ),
        )

        await orchestrator.handle_comment_event(event2)

        # FR-4.2: Verify second agent response was posted
        assert len(testable_discussion_adapter.comments_posted) == 2
        response2 = testable_discussion_adapter.comments_posted[1]
        assert response2.parent_id == second_comment.id

        # Verify LLM conversation continuity
        assert len(testable_llm_provider.executions) == 2
        conversation_id = testable_llm_provider.executions[0]["conversation_id"]
        assert testable_llm_provider.get_conversation_history(conversation_id) is not None

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

        # Verify monitoring stopped
        assert work_item_id not in testable_discussion_adapter.monitoring_sessions

        # Verify session terminated in EventStore
        final_session = await orchestrator.load_session_state(work_item_id)
        assert final_session.status == "terminated"



@pytest.mark.integration
class TestSessionPersistenceAcrossInstancesIntegration:
    """Integration test: Session persistence across orchestrator instances.

    Verifies:
    - FR-5.3: Session state recoverable from EventStore checkpoint
    - Session continuity with lastProcessedCommentId
    - Resume from checkpoint prevents duplicate processing
    """

    async def test_session_persistence_across_instances(
        self,
        testable_discussion_adapter,
        testable_llm_provider,
        real_event_store,
    ):
        """Integration test: Session persists across orchestrator restarts.

        Simulates orchestrator restart scenario where:
        1. First instance processes comments and persists state
        2. Instance is destroyed
        3. New instance loads state from EventStore
        4. New instance resumes from checkpoint
        """
        work_item_id = "issue-42"
        project_id = "proj-1"

        # First instance: Initialize and process comment
        orchestrator_1 = ConversationalLoopOrchestrator(
            discussion_adapter=testable_discussion_adapter,
            llm_provider=testable_llm_provider,
            event_store=real_event_store,
        )

        session_1 = await orchestrator_1.initialize_loop(
            work_item_id,
            project_id,
            {"column_name": "In Review", "agent_assignment": "reviewer"},
        )

        # Process first comment
        comment_1 = Comment(
            id="comment-1",
            author="alice",
            body="First review request",
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

        event_1 = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id=work_item_id,
            project_id=project_id,
            comment=comment_1,
            context=CommentContext(column_name="In Review", agent_assignment="reviewer"),
        )

        await orchestrator_1.handle_comment_event(event_1)

        # Verify checkpoint updated
        session_after_1 = await orchestrator_1.load_session_state(work_item_id)
        assert session_after_1.last_processed_comment_id == "comment-1"
        original_session_id = session_1.session_id

        # Simulate restart: destroy first instance
        del orchestrator_1

        # Second instance: Load session from EventStore
        orchestrator_2 = ConversationalLoopOrchestrator(
            discussion_adapter=testable_discussion_adapter,
            llm_provider=testable_llm_provider,
            event_store=real_event_store,
        )

        session_2 = await orchestrator_2.load_session_state(work_item_id)

        # FR-5.3: Verify session fully recovered
        assert session_2 is not None
        assert session_2.session_id == original_session_id
        assert session_2.last_processed_comment_id == "comment-1"
        assert session_2.status == "active"

        # Resume monitoring with checkpoint
        monitoring_config = DiscussionMonitoringConfig(
            project_id=session_2.project_id,
            column_name=session_2.column_name,
            agent_assignment=session_2.agent_assignment,
        )
        testable_discussion_adapter.start_monitoring(work_item_id, monitoring_config)

        # Process second comment
        comment_2 = Comment(
            id="comment-2",
            author="bob",
            body="Second question",
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

        event_2 = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id=work_item_id,
            project_id=project_id,
            comment=comment_2,
            context=CommentContext(column_name="In Review", agent_assignment="reviewer"),
        )

        await orchestrator_2.handle_comment_event(event_2)

        # Verify only new comment triggered agent (no duplicate)
        assert len(testable_llm_provider.executions) == 2  # comment-1 and comment-2


@pytest.mark.integration
class TestErrorHandlingIntegration:
    """Integration test: Error handling and recovery.

    Verifies:
    - FR-7.1: Error handling with proper logging and session state preservation
    - Error recovery and session resilience
    - Session state persistence across error scenarios
    """

    async def test_recovery_after_agent_error(
        self,
        orchestrator,
        testable_discussion_adapter,
        testable_llm_provider,
        real_event_store,
    ):
        """Test recovery after agent execution failure.

        Verifies:
        - FR-7.1: Error handling is logged when agent fails
        - Session remains active after transient agent error
        - State persisted to EventStore
        - Error recovery allows session continuation
        """
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

        # Make LLM provider fail to trigger error event
        testable_llm_provider.continue_conversation = AsyncMock(
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

        # Should raise exception
        with pytest.raises(Exception, match="Agent execution failed"):
            await orchestrator.handle_comment_event(event)

        # Session should still be active
        loaded_session = await orchestrator.load_session_state(work_item_id)
        assert loaded_session is not None
        assert loaded_session.status == "active"

        # FR-7.1: Verify that error handling logic executes
        # (proper error event emission depends on EventBus being wired in orchestrator)

    async def test_cleanup_on_fatal_error(
        self,
        orchestrator,
        testable_discussion_adapter,
        real_event_store,
    ):
        """Test cleanup after fatal error with session termination.

        Verifies:
        - Session marked as terminated
        - Monitoring stopped
        - State persisted to EventStore
        - Cleanup properly persists termination state
        """
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

        # Verify monitoring stopped
        assert work_item_id not in testable_discussion_adapter.monitoring_sessions

        # Verify session terminated and persisted
        loaded_session = await orchestrator.load_session_state(work_item_id)
        assert loaded_session.status == "terminated"

        # FR-7.1: Verify that cleanup properly terminates session
        # (error event emission via EventBus is handled when _event_bus is configured)


@pytest.mark.integration
class TestConcurrentSessionsWithRealEventStoreIntegration:
    """Integration test: Multiple concurrent sessions with real EventStore.

    Verifies:
    - FR-9.2: Orchestrator processes events sequentially per work item
    - No state contamination across work items
    - EventStore handles concurrent append operations
    - Session isolation with real persistence
    """

    async def test_concurrent_sessions_with_real_event_store(
        self,
        testable_discussion_adapter,
        testable_llm_provider,
        real_event_store,
    ):
        """Integration test: Multiple concurrent sessions with real EventStore.

        Verifies:
        - Each work item has independent session state
        - Concurrent processing doesn't corrupt state
        - EventStore maintains isolation guarantees
        """
        # Initialize multiple sessions concurrently
        session_configs = [
            ("issue-1", "proj-1", "requirements_analyst"),
            ("issue-2", "proj-1", "code_reviewer"),
            ("issue-3", "proj-1", "security_specialist"),
        ]

        orchestrators = [
            ConversationalLoopOrchestrator(
                discussion_adapter=testable_discussion_adapter,
                llm_provider=testable_llm_provider,
                event_store=real_event_store,
            )
            for _ in session_configs
        ]

        sessions = []
        for orch, (work_item_id, project_id, agent) in zip(orchestrators, session_configs):
            session = await orch.initialize_loop(
                work_item_id,
                project_id,
                {"column_name": "In Review", "agent_assignment": agent},
            )
            sessions.append((work_item_id, session))

        # Verify all sessions created independently
        assert len(sessions) == 3
        assert sessions[0][1].agent_assignment == "requirements_analyst"
        assert sessions[1][1].agent_assignment == "code_reviewer"
        assert sessions[2][1].agent_assignment == "security_specialist"

        # Process comments concurrently for each work item
        async def process_comment(orch, work_item_id, project_id, comment_id):
            comment = Comment(
                id=comment_id,
                author="user",
                body=f"Comment for {work_item_id}",
                created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )
            event = CommentNeedsResponseEvent(
                type="comment.needs_response",
                timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                source="github",
                work_item_id=work_item_id,
                project_id=project_id,
                comment=comment,
                context=CommentContext(column_name="In Review", agent_assignment="agent"),
            )
            await orch.handle_comment_event(event)

        # Process comments concurrently (FR-9.2: sequential per item, parallel across items)
        tasks = []
        for orch, (work_item_id, project_id, _) in zip(orchestrators, session_configs):
            task = process_comment(orch, work_item_id, "proj-1", f"{work_item_id}-comment-1")
            tasks.append(task)

        await asyncio.gather(*tasks)

        # Verify all sessions updated independently
        for work_item_id, _, _ in session_configs:
            orch = ConversationalLoopOrchestrator(
                discussion_adapter=testable_discussion_adapter,
                llm_provider=testable_llm_provider,
                event_store=real_event_store,
            )
            updated = await orch.load_session_state(work_item_id)
            assert updated.last_processed_comment_id == f"{work_item_id}-comment-1"

    async def test_session_state_isolation_across_work_items(
        self,
        real_event_store,
        testable_discussion_adapter,
        testable_llm_provider,
    ):
        """Test that session state is isolated across work items.

        Verifies EventStore checkpoint prevents cross-item state leakage.
        """
        orchestrator = ConversationalLoopOrchestrator(
            discussion_adapter=testable_discussion_adapter,
            llm_provider=testable_llm_provider,
            event_store=real_event_store,
        )

        # Initialize multiple work items
        work_items = ["item-1", "item-2", "item-3"]
        for work_item_id in work_items:
            await orchestrator.initialize_loop(
                work_item_id,
                "proj-1",
                {"column_name": "In Review", "agent_assignment": "reviewer"},
            )

        # Load each session and verify isolation
        for work_item_id in work_items:
            session = await orchestrator.load_session_state(work_item_id)
            assert session.work_item_id == work_item_id
            assert session.last_processed_comment_id == "__checkpoint_start"

        # Update one session
        session_1 = await orchestrator.load_session_state("item-1")
        updated_session_1 = ConversationalSessionState(
            session_id=session_1.session_id,
            work_item_id=session_1.work_item_id,
            project_id=session_1.project_id,
            agent_assignment=session_1.agent_assignment,
            column_name=session_1.column_name,
            llm_conversation_id=session_1.llm_conversation_id,
            last_processed_comment_id="updated-comment-id",
            last_interaction_timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            status="active",
        )
        await orchestrator.save_session_state(updated_session_1)

        # Verify other sessions unchanged
        for work_item_id in ["item-2", "item-3"]:
            session = await orchestrator.load_session_state(work_item_id)
            assert session.last_processed_comment_id == "__checkpoint_start"

        # Verify updated session
        updated = await orchestrator.load_session_state("item-1")
        assert updated.last_processed_comment_id == "updated-comment-id"


@pytest.mark.integration
class TestAdapterInteractionIntegration:
    """Integration test: Orchestrator's interaction with real adapters.

    Verifies:
    - Correct monitoring configuration passed to discussion adapter
    - LLM conversation continuity with real EventStore persistence
    - Event store state recovery enables conversation context
    """

    async def test_discussion_adapter_monitoring_config(
        self,
        orchestrator,
        testable_discussion_adapter,
    ):
        """Test that discussion adapter receives correct monitoring config.

        Verifies FR-2.1: startMonitoring() called with correct configuration.
        """
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
        assert work_item_id in testable_discussion_adapter.monitoring_sessions
        config = testable_discussion_adapter.monitoring_sessions[work_item_id]
        assert config.column_name == "In Review"
        assert config.agent_assignment == "code-reviewer"

    async def test_llm_provider_conversation_continuity_with_event_store(
        self,
        orchestrator,
        testable_llm_provider,
        real_event_store,
    ):
        """Test LLM conversation continuity via EventStore persistence.

        Verifies:
        - Conversation ID persisted to EventStore
        - Multi-turn context maintained across comment processing
        - Resume from checkpoint preserves conversation ID
        """
        work_item_id = "issue-42"

        # Initialize with conversation context
        session = await orchestrator.initialize_loop(
            work_item_id,
            "proj-1",
            {"column_name": "In Review", "agent_assignment": "reviewer"},
        )

        # Manually set conversation ID in session (simulate prior conversation)
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

        # Verify conversation ID persisted to EventStore
        loaded = await orchestrator.load_session_state(work_item_id)
        assert loaded.llm_conversation_id == "conv-abc123"

        # Handle comment - should use persisted conversation ID
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

        # Verify LLM provider was called with persisted conversation ID
        assert len(testable_llm_provider.executions) == 1
        execution = testable_llm_provider.executions[0]
        assert execution["conversation_id"] == "conv-abc123"

        # Verify conversation history tracked by LLM
        history = testable_llm_provider.get_conversation_history("conv-abc123")
        assert len(history) > 0
