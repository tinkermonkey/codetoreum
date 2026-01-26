"""End-to-end simulation test for ConversationalLoopOrchestrator.

This simulation test demonstrates a complete multi-turn conversational workflow
without external dependencies, showing how the orchestrator handles real-world
scenarios like:
- Session initialization on column entry
- Multi-turn conversations with context continuity
- Column transitions and session cleanup
- Error recovery and idempotency
"""

import pytest
from datetime import datetime, timezone
from typing import Dict, List, Optional

from codetoreum.application.conversational_loop_orchestrator import (
    ConversationalLoopOrchestrator,
)
from codetoreum.domain.conversational_session import ConversationalSessionState
from codetoreum.domain.events.discussion_events import (
    Comment,
    CommentContext,
    CommentNeedsResponseEvent,
)
from codetoreum.domain.events.board_events import WorkItemColumnChangedEvent


class SimulatedDiscussionAdapter:
    """Simulated discussion adapter with realistic behavior."""

    def __init__(self):
        self.work_items: Dict[str, dict] = {}
        self.comments: Dict[str, List[Comment]] = {}
        self.monitoring_active: Dict[str, bool] = {}

    def start_monitoring(self, work_item_id: str, config: dict) -> None:
        """Start monitoring for comments."""
        self.work_items[work_item_id] = config
        self.monitoring_active[work_item_id] = True
        if work_item_id not in self.comments:
            self.comments[work_item_id] = []

    def stop_monitoring(self, work_item_id: str) -> None:
        """Stop monitoring for comments."""
        self.monitoring_active[work_item_id] = False

    async def add_comment(
        self,
        work_item_id: str,
        content: str,
        parent_id: Optional[str] = None,
    ) -> Comment:
        """Post a comment."""
        if work_item_id not in self.comments:
            self.comments[work_item_id] = []

        comment_id = f"comment-{len(self.comments[work_item_id]) + 1}"
        comment = Comment(
            id=comment_id,
            author="agent",
            body=content,
            created_at=datetime.now(timezone.utc).isoformat(),
            parent_id=parent_id,
            is_bot=True,
        )

        self.comments[work_item_id].append(comment)
        return comment

    def on(self, event_type: str, handler) -> None:
        """Subscribe to events."""
        pass

    async def get_thread(self, work_item_id: str) -> dict:
        """Get thread."""
        return {"id": f"thread-{work_item_id}", "comments": self.comments.get(work_item_id, [])}


class SimulatedLLMProvider:
    """Simulated LLM provider with deterministic responses."""

    def __init__(self):
        self.conversations: Dict[str, List[str]] = {}
        self.response_templates = [
            "That's a good question. Here's my analysis: {context}",
            "I've reviewed your feedback. The issue is: {context}",
            "Regarding your point about {context}, I agree.",
        ]
        self.response_counter = 0
        self.generated_conversation_ids: Dict[str, str] = {}  # Map from empty/None to generated ID

    async def execute_prompt(self, prompt: str, context=None, stream_callback=None):
        """Execute a one-time prompt."""
        class Result:
            content = "Initial analysis complete"
            conversation_id = None
            duration_ms = 50

        return Result()

    async def continue_conversation(
        self,
        conversation_id: str,
        message: str,
        stream_callback=None,
    ):
        """Continue a conversation."""
        # Handle empty string as "create new conversation"
        if not conversation_id:
            # Generate a unique conversation ID on first call
            # Use a deterministic ID based on the message
            conversation_id = f"conv-sim-{hash(message) % 10000}"

        # Track conversation
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = []
        self.conversations[conversation_id].append(message)

        # Generate response
        self.response_counter += 1
        template = self.response_templates[self.response_counter % len(self.response_templates)]
        response = template.format(context=message[:30])

        # Store conversation_id in a local var for use in Result class
        final_conv_id = conversation_id

        class Result:
            content = response
            conversation_id = final_conv_id
            duration_ms = 100

        return Result()

    async def get_model_info(self):
        """Get model info."""
        return {"model": "simulated-claude", "supports_conversations": True}


class SimulatedEventStore:
    """Simulated event store with simple in-memory storage."""

    def __init__(self):
        self.events: List[dict] = []
        self.snapshots: Dict[str, dict] = {}
        self.stream_versions: Dict[str, int] = {}  # Track current version per stream

    async def append(self, stream_id: str, events: List, expected_version: Optional[int] = None) -> None:
        """Append events to a stream."""
        for event in events:
            # Convert event to dict if it's an object with to_dict method
            if hasattr(event, 'to_dict'):
                event_dict = event.to_dict()
                event_dict['aggregate_id'] = stream_id
            else:
                event_dict = event
                if isinstance(event_dict, dict):
                    event_dict['aggregate_id'] = stream_id

            self.events.append(event_dict)

            # Store snapshots
            if event_dict.get("type") == "conversational_session_snapshot":
                aggregate_id = event_dict.get("aggregate_id")
                state = event_dict.get("data", {}).get("conversational_session_state")
                if aggregate_id and state:
                    self.snapshots[aggregate_id] = state

    async def get_events(self, aggregate_id: str, from_version: int = 0) -> List[dict]:
        """Get events for aggregate."""
        return [e for e in self.events if e.get("aggregate_id") == aggregate_id]

    async def get_all_events(self, from_timestamp=None, to_timestamp=None) -> List[dict]:
        """Get all events."""
        return self.events

    async def get_stream_version(self, stream_id: str) -> int:
        """Get current version of a stream."""
        # Count events for this stream
        events_for_stream = [e for e in self.events if e.get("aggregate_id") == stream_id]
        return len(events_for_stream)

    async def save_snapshot(self, stream_id: str, version: int, snapshot: dict) -> None:
        """Save a snapshot."""
        self.snapshots[stream_id] = snapshot
        self.stream_versions[stream_id] = version

    async def get_latest_snapshot(self, stream_id: str) -> Optional[Dict]:
        """Get latest snapshot."""
        if stream_id in self.snapshots:
            return {"data": self.snapshots[stream_id]}
        return None


@pytest.fixture
def simulated_orchestrator():
    """Create orchestrator with simulated adapters."""
    discussion_adapter = SimulatedDiscussionAdapter()
    llm_provider = SimulatedLLMProvider()
    event_store = SimulatedEventStore()

    orchestrator = ConversationalLoopOrchestrator(
        discussion_adapter=discussion_adapter,
        llm_provider=llm_provider,
        event_store=event_store,
    )

    return orchestrator, discussion_adapter, llm_provider, event_store


class TestConversationalLoopSimulation:
    """Simulation tests for complete conversational workflows."""

    async def test_simple_qa_conversation(self, simulated_orchestrator):
        """Simulate a simple question-answer conversation.

        Scenario:
        1. Engineer asks code review question
        2. Agent responds with analysis
        3. Engineer asks follow-up question
        4. Agent continues conversation with context
        """
        orchestrator, discussion_adapter, llm_provider, event_store = simulated_orchestrator

        # Setup
        work_item_id = "issue-123"
        project_id = "project-main"

        # Step 1: Initialize conversation session
        session = await orchestrator.initialize_loop(
            work_item_id,
            project_id,
            {
                "column_name": "Code Review",
                "agent_assignment": "senior-engineer",
            }
        )

        assert session.status == "active"

        # Step 2: Engineer posts first question
        q1 = Comment(
            id="c1",
            author="engineer",
            body="Is this error handling approach secure?",
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

        event1 = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id=work_item_id,
            project_id=project_id,
            comment=q1,
            context=CommentContext(
                column_name="Code Review",
                agent_assignment="senior-engineer",
            ),
        )

        await orchestrator.handle_comment_event(event1)

        # Verify response was posted
        assert len(discussion_adapter.comments[work_item_id]) >= 1

        # Step 3: Engineer asks follow-up
        q2 = Comment(
            id="c2",
            author="engineer",
            body="What about input validation?",
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            parent_id="c1",
        )

        event2 = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id=work_item_id,
            project_id=project_id,
            comment=q2,
            context=CommentContext.for_reply(
                thread_id="thread-issue-123",
                parent_comment=q1,
                column_name="Code Review",
                agent_assignment="senior-engineer",
            ),
        )

        await orchestrator.handle_comment_event(event2)

        # Verify LLM maintains conversation context
        assert len(llm_provider.conversations) > 0
        for conv_id, messages in llm_provider.conversations.items():
            assert len(messages) >= 2, "Conversation should have multiple messages"

        # Step 4: Work item moves to merged
        column_change = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id=work_item_id,
            project_id=project_id,
            board_id="board-main",
            from_column="Code Review",
            to_column="Merged",
        )

        await orchestrator.handle_column_change_event(column_change)

        # Verify session is terminated
        final_session = await orchestrator.load_session_state(work_item_id)
        assert final_session.status == "terminated"

    async def test_multiple_concurrent_sessions(self, simulated_orchestrator):
        """Simulate multiple independent conversations running concurrently.

        Scenario:
        1. Multiple issues enter Code Review column
        2. Each has independent conversational loops
        3. Agents maintain separate contexts per issue
        4. Issues progress independently
        """
        orchestrator, discussion_adapter, llm_provider, event_store = simulated_orchestrator

        project_id = "project-main"
        sessions = {}

        # Initialize 3 concurrent review sessions
        for issue_num in range(1, 4):
            work_item_id = f"issue-{issue_num}"

            session = await orchestrator.initialize_loop(
                work_item_id,
                project_id,
                {
                    "column_name": "Code Review",
                    "agent_assignment": f"reviewer-{issue_num}",
                }
            )

            sessions[work_item_id] = session

        # Each issue gets a question
        for issue_num in range(1, 4):
            work_item_id = f"issue-{issue_num}"

            comment = Comment(
                id=f"c{issue_num}",
                author="user",
                body=f"Question about issue {issue_num}",
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

        # Verify all sessions remain independent and active
        for work_item_id, session in sessions.items():
            loaded = await orchestrator.load_session_state(work_item_id)
            assert loaded is not None
            assert loaded.status == "active"
            assert loaded.agent_assignment == f"reviewer-{work_item_id[-1]}"

        # Progress some issues to completion
        for issue_num in [1, 3]:
            work_item_id = f"issue-{issue_num}"

            column_change = WorkItemColumnChangedEvent(
                type="workitem.column_changed",
                timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                source="github",
                work_item_id=work_item_id,
                project_id=project_id,
                board_id="board-main",
                from_column="Code Review",
                to_column="Merged",
            )

            await orchestrator.handle_column_change_event(column_change)

        # Verify proper cleanup
        for issue_num in [1, 3]:
            work_item_id = f"issue-{issue_num}"
            session = await orchestrator.load_session_state(work_item_id)
            assert session.status == "terminated"

        # Issue 2 should still be active
        session2 = await orchestrator.load_session_state("issue-2")
        assert session2.status == "active"

    async def test_session_recovery_after_restart(self, simulated_orchestrator):
        """Simulate orchestrator restart and session recovery.

        Scenario:
        1. Start conversational session on issue
        2. Exchange messages and build LLM conversation state
        3. Simulate orchestrator restart
        4. Resume from checkpoint and continue conversation
        5. Verify full context is maintained
        """
        orchestrator, discussion_adapter, llm_provider, event_store = simulated_orchestrator

        work_item_id = "issue-100"
        project_id = "project-main"

        # Step 1: Start session and exchange messages
        session1 = await orchestrator.initialize_loop(
            work_item_id,
            project_id,
            {"column_name": "Review", "agent_assignment": "reviewer"},
        )

        # First message
        c1 = Comment(
            id="c1",
            author="user",
            body="First question",
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

        event1 = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id=work_item_id,
            project_id=project_id,
            comment=c1,
        )

        await orchestrator.handle_comment_event(event1)

        # Get checkpoint
        checkpoint1 = await orchestrator.load_session_state(work_item_id)
        assert checkpoint1.last_processed_comment_id == "c1"

        # Second message
        c2 = Comment(
            id="c2",
            author="user",
            body="Second question",
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

        event2 = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id=work_item_id,
            project_id=project_id,
            comment=c2,
        )

        await orchestrator.handle_comment_event(event2)

        checkpoint2 = await orchestrator.load_session_state(work_item_id)
        assert checkpoint2.last_processed_comment_id == "c2"

        # Step 2: Simulate restart - create new orchestrator with same event store
        orchestrator_restarted = ConversationalLoopOrchestrator(
            discussion_adapter=discussion_adapter,
            llm_provider=llm_provider,
            event_store=event_store,
        )

        # Step 3: Resume conversation
        recovered_session = await orchestrator_restarted.load_session_state(work_item_id)
        assert recovered_session is not None
        assert recovered_session.session_id == session1.session_id
        assert recovered_session.last_processed_comment_id == "c2"
        print(f"✓ Recovered session: {recovered_session.session_id}")

        # Step 4: Continue conversation with restored context
        c3 = Comment(
            id="c3",
            author="user",
            body="Third question",
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

        event3 = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id=work_item_id,
            project_id=project_id,
            comment=c3,
        )

        await orchestrator_restarted.handle_comment_event(event3)

        # Verify conversation continued
        final_session = await orchestrator_restarted.load_session_state(work_item_id)
        assert final_session.last_processed_comment_id == "c3"

    async def test_graceful_cleanup_on_errors(self, simulated_orchestrator):
        """Simulate graceful error handling and cleanup.

        Scenario:
        1. Start conversational session
        2. Encounter error during comment handling
        3. Cleanup gracefully
        4. Verify idempotency (cleanup can be called again safely)
        """
        orchestrator, discussion_adapter, llm_provider, event_store = simulated_orchestrator

        work_item_id = "issue-200"
        project_id = "project-main"

        # Initialize session
        session = await orchestrator.initialize_loop(
            work_item_id,
            project_id,
            {"column_name": "Review", "agent_assignment": "reviewer"},
        )

        # Simulate error and cleanup
        await orchestrator.cleanup_loop(work_item_id, "Simulated error condition")

        # Verify session is terminated
        terminated = await orchestrator.load_session_state(work_item_id)
        assert terminated.status == "terminated"

        # Cleanup again - should be idempotent
        await orchestrator.cleanup_loop(work_item_id, "Second cleanup attempt")

        # Verify still terminated
        still_terminated = await orchestrator.load_session_state(work_item_id)
        assert still_terminated.status == "terminated"

    async def test_checkpoint_resume_optimization(self, simulated_orchestrator):
        """Simulate checkpoint-based resume for efficiency.

        Scenario:
        1. Process 10 comments in conversation
        2. Each update moves checkpoint forward
        3. Restore from checkpoint - should skip old comments
        4. Resume from exact last processed point
        """
        orchestrator, discussion_adapter, llm_provider, event_store = simulated_orchestrator

        work_item_id = "issue-300"
        project_id = "project-main"

        # Initialize
        session = await orchestrator.initialize_loop(
            work_item_id,
            project_id,
            {"column_name": "Review", "agent_assignment": "reviewer"},
        )

        # Process multiple comments
        comment_ids = []
        for i in range(1, 6):
            comment = Comment(
                id=f"comment-{i}",
                author="user",
                body=f"Message {i}",
                created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )
            comment_ids.append(f"comment-{i}")

            event = CommentNeedsResponseEvent(
                type="comment.needs_response",
                timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                source="github",
                work_item_id=work_item_id,
                project_id=project_id,
                comment=comment,
            )

            await orchestrator.handle_comment_event(event)

        # Get checkpoint
        checkpoint = await orchestrator.load_session_state(work_item_id)
        assert checkpoint.last_processed_comment_id == "comment-5"

        # Simulate restart
        orchestrator_restarted = ConversationalLoopOrchestrator(
            discussion_adapter=discussion_adapter,
            llm_provider=llm_provider,
            event_store=event_store,
        )

        # Resume
        restored = await orchestrator_restarted.load_session_state(work_item_id)
        assert restored.last_processed_comment_id == "comment-5"

        # Continue from checkpoint
        comment6 = Comment(
            id="comment-6",
            author="user",
            body="Message 6",
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

        event6 = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="github",
            work_item_id=work_item_id,
            project_id=project_id,
            comment=comment6,
        )

        await orchestrator_restarted.handle_comment_event(event6)

        final = await orchestrator_restarted.load_session_state(work_item_id)
        assert final.last_processed_comment_id == "comment-6"
