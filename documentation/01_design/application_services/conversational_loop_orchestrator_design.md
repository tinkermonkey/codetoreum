# ConversationalLoopOrchestrator Design Document

## Overview

The **ConversationalLoopOrchestrator** is an application service that orchestrates feedback loops where AI agents engage in back-and-forth dialogue with human stakeholders through comment threads on work items. It is the implementation of the `IConversationalLoopService` input port.

**Phase 3 Implementation**: This service enables multi-turn agent-human conversations within the workflow, allowing agents to clarify requirements, answer questions, and iterate based on feedback without requiring full re-execution of the workflow stage.

## Purpose

The ConversationalLoopOrchestrator enables:

- **Interactive Q&A**: Agents respond to human comments with context continuity
- **Clarification Loops**: Iterate on requirements and design through dialogue
- **Multi-turn Context**: Maintain conversation history via LLM session IDs
- **Session Persistence**: Survive orchestrator restarts without losing context
- **Event Audit Trail**: Complete record of all interactions for compliance

## Architecture

### Hexagonal Architecture Compliance

The service follows strict hexagonal architecture principles:

```
Domain Layer (Pure)
├── ConversationalSessionState (immutable value object)
├── Events (immutable dataclasses)
└── No external dependencies

Application Layer (Orchestration)
└── ConversationalLoopOrchestrator
    ├── Pure orchestration logic
    ├── Coordinates with ports
    └── No business logic in adapters

Ports (Interfaces/Contracts)
├── Input: IConversationalLoopService
├── Output: IDiscussionAdapter
├── Output: ILLMProvider
└── Output: IEventStore

Adapters (Implementations)
├── GitHub Discussion Adapter
├── Claude Code LLM Provider
└── Event Store (InMemory/Redis currently, Elasticsearch planned)
```

### Key Design Principles

1. **No External Dependencies in Domain**: All external interactions through port interfaces
2. **Immutable State**: Domain events and session state are frozen dataclasses
3. **Event Sourcing**: All state changes captured as immutable events
4. **Hexagonal Ports**: Adapter implementations can change without affecting domain
5. **Pure Orchestration**: Service layer coordinates but doesn't contain business logic

## Implementation

### Core Components

#### 1. ConversationalSessionState (Domain Model)

Immutable value object representing session state at a point in time.

```python
@dataclass(frozen=True)
class ConversationalSessionState:
    session_id: str                    # Unique session identifier
    work_item_id: str                  # The issue/item being discussed
    project_id: str                    # Project context
    agent_assignment: str              # Name of agent handling responses
    column_name: str                   # Board column (e.g., "In Review")
    llm_conversation_id: Optional[str] # LLM session for context
    last_processed_comment_id: str     # Resume checkpoint
    last_interaction_timestamp: str    # ISO 8601 timestamp
    status: Literal["active", "suspended", "terminated"]
```

**State Transitions**:
- `"active"`: Actively monitoring and posting responses
- `"suspended"`: Temporarily paused (not implemented yet)
- `"terminated"`: Session completed or cleaned up

#### 2. ConversationalLoopOrchestrator (Application Service)

```python
class ConversationalLoopOrchestrator(IConversationalLoopService):
    async def initialize_loop(
        work_item_id: str,
        project_id: str,
        column_config: dict
    ) -> ConversationalSessionState

    async def handle_comment_event(
        event: CommentNeedsResponseEvent
    ) -> None

    async def handle_column_change_event(
        event: WorkItemColumnChangedEvent
    ) -> None

    async def cleanup_loop(
        work_item_id: str,
        reason: str
    ) -> None

    async def load_session_state(
        work_item_id: str
    ) -> Optional[ConversationalSessionState]

    async def save_session_state(
        state: ConversationalSessionState
    ) -> None
```

### Workflow Lifecycle

```
Work item enters conversational column
        ↓
    initialize_loop()
        ├─ Create unique session_id
        ├─ Start IDiscussionAdapter monitoring
        ├─ Create immutable ConversationalSessionState
        ├─ Persist session state to IEventStore
        └─ Return session

    Comment received → CommentNeedsResponseEvent
        ↓
    handle_comment_event()
        ├─ Load session state
        ├─ Build thread context (parents, history)
        ├─ Execute agent via ILLMProvider.continue_conversation()
        │   └─ Pass conversation_id for context
        ├─ Post response via IDiscussionAdapter.add_comment()
        ├─ Update session checkpoint
        ├─ Persist updated session state
        └─ Emit AgentResponsePostedEvent

    Column change → WorkItemColumnChangedEvent
        ↓
    handle_column_change_event()
        └─ If exiting conversational column:
            ├─ Stop monitoring
            ├─ Mark session terminated
            └─ Persist updated state

    Error or manual termination
        ↓
    cleanup_loop()
        ├─ Stop monitoring (best effort)
        ├─ Mark session terminated
        ├─ Persist state
        └─ Idempotent (safe to call multiple times)
```

## Port Interfaces

### Required Output Ports

#### IDiscussionAdapter

Manages comment monitoring and posting on work items.

```python
class IDiscussionAdapter(ABC):
    def start_monitoring(
        work_item_id: str,
        config: dict
    ) -> None:
        """Start monitoring for comments on a work item."""

    def stop_monitoring(work_item_id: str) -> None:
        """Stop monitoring for comments."""

    async def add_comment(
        work_item_id: str,
        content: str,
        parent_id: Optional[str] = None
    ) -> dict:
        """Post a comment (optionally as reply to parent)."""

    async def get_thread(work_item_id: str) -> dict:
        """Retrieve full discussion thread for a work item."""
```

**Implementation**: GitHub Discussion Adapter
- Monitors GitHub issues via webhooks (with polling fallback)
- Posts comments via GitHub REST API
- Filters bot comments using IIdentityService
- Emits `comment.needs_response` events

#### ILLMProvider

Executes agents with conversation context continuity.

```python
class ILLMProvider(ABC):
    async def continue_conversation(
        conversation_id: str,
        message: str,
        stream_callback: Optional[StreamCallback] = None
    ) -> ExecutionResult:
        """Continue an existing conversation session."""
        # Returns:
        # - content: Agent's response text
        # - conversation_id: Session ID (may differ from input)
        # - Other metadata
```

**Key Feature**: `conversation_id` enables multi-turn context

- First call: `conversation_id = ""` → LLM creates new session
- Returns: `conversation_id = "conv-abc123"` for session tracking
- Subsequent calls: Pass same ID to maintain context
- LLM remembers conversation history

**Implementation**: Claude Code Adapter
- Uses Claude Code's conversation API
- Maintains session context for multi-turn interactions
- Supports streaming for long responses

#### IEventStore

Persists session state for restart continuity.

```python
class IEventStore(ABC):
    async def append(event: dict) -> None
        """Append event to store."""

    async def get_events(
        aggregate_id: str,
        from_version: int = 0
    ) -> List[dict]:
        """Retrieve events for an aggregate."""
```

**Storage Pattern**: Session State Snapshots
- Event type: `"conversational_session_snapshot"`
- Aggregate ID: `work_item_id`
- Data: Serialized `ConversationalSessionState.to_dict()`
- Used for quick state recovery (vs. full event replay)

**Implementation**: Event Store (abstracted via IEventStore)
- Production: Redis-based event store (RedisEventStore) with background persistence
- Testing: In-memory event store (InMemoryEventStore)
- Future: Elasticsearch for advanced querying and time-series indices
- Enables checkpoint-based resume
- Provides audit trail for compliance

### Event Bus Subscriptions

The service subscribes to these domain events (typically via dependency injection):

```python
# In event bus wiring:
event_bus.subscribe("comment.needs_response", orchestrator.handle_comment_event)
event_bus.subscribe("workitem.column_changed", orchestrator.handle_column_change_event)
```

## Domain Events

### Incoming Events

#### CommentNeedsResponseEvent

Emitted by IDiscussionAdapter when a human comment requires agent response.

```python
@dataclass(frozen=True)
class CommentNeedsResponseEvent(CodetoreumEvent):
    work_item_id: str
    project_id: str
    comment: Optional[Comment]  # The human comment
    context: Optional[CommentContext]  # Parent comments, column, etc.
```

#### WorkItemColumnChangedEvent

Emitted by board polling service when work item moves between columns.

```python
@dataclass(frozen=True)
class WorkItemColumnChangedEvent(CodetoreumEvent):
    work_item_id: str
    project_id: str
    from_column: str
    to_column: str
```

### Outgoing Events

#### AgentResponsePostedEvent

Emitted after agent response is successfully posted.

```python
@dataclass(frozen=True)
class AgentResponsePostedEvent(CodetoreumEvent):
    work_item_id: str
    project_id: str
    comment_id: str  # The human comment being responded to
    agent_name: str
    conversation_id: Optional[str]  # LLM session ID
    timestamp: str  # When response was posted
```

Used for:
- Audit trail
- Observability
- Analytics on conversation patterns
- Debugging multi-turn interactions

## Error Handling

### Transient Errors

Errors during agent execution or comment posting are propagated:
- Session state remains active
- Can be retried (another comment event will trigger retry)
- Circuit breakers handled at adapter level

Example: LLM timeout during response generation
```python
try:
    execution_result = await self.llm_provider.continue_conversation(...)
except Exception as e:
    logger.error(f"Error handling comment: {e}", exc_info=True)
    raise  # Session remains active for retry
```

### Fatal Errors

Use `cleanup_loop()` for fatal errors that should terminate the session:
- Out of memory
- Unconfigured agent
- Work item deleted
- User request

Example:
```python
try:
    await orchestrator.handle_comment_event(event)
except OutOfMemoryError:
    await orchestrator.cleanup_loop(work_item_id, "Out of memory")
```

### Idempotency

Operations are designed to be idempotent:
- `cleanup_loop()` safe to call multiple times
- Loading non-existent session returns None (not error)
- Comment without body is silently skipped

## Session State Persistence

### Storage Strategy

**Why Event Sourcing?**
- Complete audit trail of all interactions
- Enables event replay for debugging
- Restart continuity without duplicate processing
- Compliance requirements

**Checkpoint Pattern**:
1. Session state snapshot created on each update
2. Contains `last_processed_comment_id` checkpoint
3. Resume skips all comments up to checkpoint
4. Efficient for high-frequency interactions

### State Recovery After Restart

```python
# Before restart
session = await orchestrator.load_session_state("issue-42")
# session.last_processed_comment_id = "comment-15"

# After restart with new orchestrator instance
session = await orchestrator.load_session_state("issue-42")
# Recovers from checkpoint
# Monitoring resumes from "comment-15"
```

## Multi-Turn Conversation Example

```
Initial State:
├─ Work item #42 moves to "Code Review" column
├─ initialize_loop() creates session with llm_conversation_id = None

Turn 1:
├─ Human: "Is this error handling correct?"
├─ Agent executes with message, gets back conversation_id = "conv-abc123"
├─ Session state saved with llm_conversation_id = "conv-abc123"

Turn 2:
├─ Human: "What about edge cases?"
├─ Agent called with conversation_id = "conv-abc123"
├─ LLM remembers previous context automatically
├─ Agent response considers previous exchange

Turn 3:
├─ Human: "Can you refactor the code?"
├─ Agent called with conversation_id = "conv-abc123" (3 turn context)
├─ LLM has full conversation history

Work item exits "Code Review":
├─ handle_column_change_event() called
├─ Session marked terminated
├─ Monitoring stopped
```

## Testing Strategy

### Unit Tests
- Session state creation and validation
- Event handling logic
- Checkpoint updates
- Error paths

### Integration Tests
- Interaction with mock adapters
- Session persistence across restarts
- Multiple concurrent sessions
- Error recovery

### Simulation Tests
- Complete multi-turn conversations
- Concurrent independent sessions
- Orchestrator restart scenarios
- Graceful cleanup

## Configuration

No configuration needed beyond adapter setup.

**Dependencies injected**:
- `discussion_adapter: IDiscussionAdapter`
- `llm_provider: ILLMProvider`
- `event_store: IEventStore`

**Example initialization**:
```python
orchestrator = ConversationalLoopOrchestrator(
    discussion_adapter=github_discussion_adapter,
    llm_provider=claude_code_adapter,
    event_store=elasticsearch_event_store,
)

# Subscribe to events
event_bus.subscribe("comment.needs_response", orchestrator.handle_comment_event)
event_bus.subscribe("workitem.column_changed", orchestrator.handle_column_change_event)
```

## Implementation Details

### Thread Message Building

When a comment is received, context is built:

```python
def _build_thread_message(event, session_state) -> str:
    parts = []

    # Add work item context
    parts.append(f"Work item: {event.context.column_name}")
    parts.append(f"Assigned agent: {event.context.agent_assignment}")

    # Add parent comment if reply
    if event.context.parent_comment:
        parts.append(f"Previous comment from {parent.author}:")
        parts.append(parent.body)

    # Add current comment
    parts.append(f"New comment from {comment.author}:")
    parts.append(comment.body)

    return "\n".join(parts)
```

The message is then passed to LLM with conversation_id for context continuity.

### Session ID Generation

Session IDs are created deterministically:

```python
session_id = f"conv_session_{work_item_id}_{int(datetime.now().timestamp())}"
# Example: conv_session_issue-42_1704067800
```

This ensures:
- Uniqueness (timestamp component)
- Traceability (work_item_id component)
- Human-readable format

## Performance Considerations

### Checkpoint-Based Resume

- First comment: Agent execution latency (100-500ms typical)
- Resume after restart: Load session (~50ms) + monitor from checkpoint
- No replay of previous comments (checkpoint prevents duplication)

### Concurrent Sessions

- Each work item has independent session
- No cross-work-item contention
- Horizontal scaling via multiple orchestrator instances

### Session Persistence

- Snapshots stored in event store
- Quick recovery (~50ms) vs. full replay
- Daily index rollover (Elasticsearch)

## Future Enhancements

1. **Suspended State**: Pause conversation without cleanup
   - Used for long-running reviews requiring manual intervention
   - Resume when resumed by user

2. **Conversation Timeout**: Auto-terminate after N hours
   - Prevent unbounded session growth
   - Graceful cleanup with reason logging

3. **Context Compression**: Summarize old messages for large conversations
   - Prevent LLM token bloat
   - Maintain context relevance

4. **Multi-Agent Conversations**: Hand off between agents
   - Route follow-ups to different agents
   - Maintain full conversation context

## Related Documentation

- **IConversationalLoopService**: `/workspace/src/codetoreum/ports/input/conversational_loop_service.py`
- **ConversationalSessionState**: `/workspace/src/codetoreum/domain/conversational_session.py`
- **Discussion Events**: `/workspace/src/codetoreum/domain/events/discussion_events.py`
- **IDiscussionAdapter**: `/workspace/src/codetoreum/ports/output/discussion_adapter.py`
- **ILLMProvider**: `/workspace/src/codetoreum/ports/output/llm_provider.py`
- **Event Sourcing**: `/workspace/documentation/01_design/infrastructure/event_sourcing_implementation.md`

## Summary

The ConversationalLoopOrchestrator enables multi-turn agent-human interactions within the workflow by:

- **Initializing sessions** when work items enter conversational columns
- **Managing conversations** with context continuity via LLM conversation IDs
- **Persisting state** for restart resilience
- **Emitting events** for audit trail and observability
- **Handling errors** gracefully with idempotent operations
- **Following hexagonal architecture** with pure domain, clean ports, and swappable adapters

This enables Phase 3 of the Codetoreum evolution: Interactive AI agents that clarify requirements and iterate based on feedback within the workflow context.
