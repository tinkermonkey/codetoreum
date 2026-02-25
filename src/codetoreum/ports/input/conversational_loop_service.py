"""Conversational Loop Service Input Port

This module defines the input port interface for conversational loop orchestration.
The conversational loop service manages feedback loops where AI agents engage in
back-and-forth dialogue with human stakeholders through comment threads.

The service is responsible for:
- Initializing monitoring when work items enter conversational columns
- Handling comment events and executing agent responses
- Managing column transitions (entry/exit of conversational columns)
- Cleaning up loop state on exit or error
- Persisting and restoring session state for restart continuity
"""

from abc import ABC, abstractmethod

from codetoreum.domain.conversational_session import ConversationalSessionState
from codetoreum.domain.events.board_events import WorkItemColumnChangedEvent
from codetoreum.domain.events.discussion_events import CommentNeedsResponseEvent


class IConversationalLoopService(ABC):
    """Application service port for orchestrating conversational feedback loops.

    This port defines the contract for initializing and managing conversational loops
    where AI agents respond to human comments on work items. It follows hexagonal
    architecture principles, with the interface defining pure orchestration operations
    without implementation details.

    The service implementation will:
    - Subscribe to domain events (comment.needs_response, workitem.column_changed)
    - Manage session state per work item
    - Coordinate with IDiscussionAdapter for comment monitoring and posting
    - Coordinate with ILLMProvider for agent execution with context
    - Persist session state to IEventStore for restart continuity

    **Event Subscription Pattern**:
    Implementations must subscribe to these EventBus events:
    - `comment.needs_response` → `handle_comment_event()`
    - `workitem.column_changed` → `handle_column_change_event()`

    **Session State Lifecycle**:
    - "active": Actively monitoring for comments and posting agent responses
    - "suspended": Temporarily paused (e.g., due to errors or user request)
    - "terminated": Loop completed or explicitly cleaned up
    """

    @abstractmethod
    async def initialize_loop(
        self, work_item_id: str, project_id: str, column_config: dict
    ) -> ConversationalSessionState:
        """Initialize a conversational loop when work item enters a conversational column.

        This operation sets up a new feedback loop by:
        1. Creating a unique session identifier
        2. Initializing session state with provided configuration
        3. Starting the discussion adapter's monitoring (via IDiscussionAdapter.start_monitoring())
        4. Persisting session state to IEventStore

        **Parameters**:
        - work_item_id: Unique identifier of the work item (e.g., GitHub issue #42)
        - project_id: Unique identifier of the project containing the work item
        - column_config: Dictionary with configuration:
            - `column_name`: Name of the board column (e.g., "In Review", "Feedback Needed")
            - `agent_assignment`: Name of the agent assigned to handle responses
            - Additional metadata for agent context

        **Returns**:
        - ConversationalSessionState: The initialized session state with:
            - session_id: Unique identifier for this session
            - llm_conversation_id: None initially (created on first agent execution)
            - last_processed_comment_id: "__checkpoint_start" sentinel value
            - status: Set to "active"

        **Raises**:
        - ValueError: If work_item_id, project_id is missing, or column_config is missing required fields
        - PortError: If starting monitoring fails
        - EventStoreError: If persisting session state fails
        """

    @abstractmethod
    async def handle_comment_event(self, event: CommentNeedsResponseEvent) -> None:
        """Handle a human comment requiring an agent response.

        This operation processes a comment that needs a response by:
        1. Loading session state from storage (via load_session_state())
        2. Verifying session is active and matches the work item
        3. Building thread context:
            - Retrieving parent comment(s) if this is a reply
            - Including previous interaction history from session state
            - Compiling full conversation context for agent
        4. Executing the assigned agent via ILLMProvider.continue_conversation():
            - Passing conversation_id for context continuity
            - Including thread context in the execution
            - Retrieving agent's response
        5. Posting the agent's response to the discussion thread (via IDiscussionAdapter.add_comment())
        6. Updating session state:
            - Setting last_processed_comment_id to the incoming comment's ID
            - Updating last_interaction_timestamp
            - Optionally updating llm_conversation_id if provider returns new session
        7. Persisting updated session state (via save_session_state())
        8. Emitting AgentResponsePostedEvent for audit trail

        **Parameters**:
        - event: CommentNeedsResponseEvent with:
            - work_item_id: The work item receiving the comment
            - project_id: The project context
            - comment: The human comment requiring response
            - context: Thread context including parent comments and column info

        **Events Emitted**:
        - AgentResponsePostedEvent: Tracks the agent's response posting

        **Raises**:
        - WorkItemNotFoundError: If work item doesn't exist
        - SessionNotFoundError: If no active session exists for the work item
        - SessionInactiveError: If session is suspended or terminated
        - PortError: If adding comment fails
        - LLMProviderError: If agent execution fails
        - ValidationError: If event data is invalid or missing
        """

    @abstractmethod
    async def handle_column_change_event(self, event: WorkItemColumnChangedEvent) -> None:
        """Handle work item column transition (entry/exit of conversational column).

        This operation responds to work item movement between board columns by:

        **If work item is exiting a conversational column**:
        1. Loading current session state
        2. Stopping discussion monitoring (via IDiscussionAdapter.stop_monitoring())
        3. Marking session as terminated
        4. Persisting terminated session state
        5. Emitting ConversationalSessionEndedEvent with exit reason

        **If work item is entering a conversational column**:
        1. Checking if a session already exists (e.g., re-entry)
        2. If new, calling initialize_loop() to set up monitoring
        3. If existing, resuming monitoring if suspended

        **If moving between two conversational columns**:
        1. Updating session state with new column_name
        2. Continuing monitoring without interruption
        3. Emitting event for audit trail

        **Parameters**:
        - event: WorkItemColumnChangedEvent with:
            - work_item_id: The work item that moved
            - project_id: The project context
            - from_column: Previous column name
            - to_column: New column name

        **Events Emitted**:
        - ConversationalSessionEndedEvent: If exiting conversational column

        **Raises**:
        - WorkItemNotFoundError: If work item doesn't exist
        - ValidationError: If event data is invalid
        - PortError: If starting/stopping monitoring fails
        """

    @abstractmethod
    async def cleanup_loop(self, work_item_id: str, reason: str) -> None:
        """Clean up loop state due to error handling or manual termination.

        This operation performs cleanup when a conversational loop needs to be
        terminated unexpectedly (e.g., agent errors, manual user request) by:
        1. Loading current session state (if exists)
        2. Stopping discussion monitoring (via IDiscussionAdapter.stop_monitoring())
        3. Marking session as terminated
        4. Persisting terminated session state
        5. Emitting ConversationalSessionEndedEvent with cleanup reason

        This method is idempotent—calling it multiple times on the same work item
        is safe and will not raise errors if session already terminated.

        **Parameters**:
        - work_item_id: The work item whose loop should be cleaned up
        - reason: Human-readable reason for cleanup (e.g., "Agent execution error",
            "Manual user termination", "Work item deleted")

        **Events Emitted**:
        - ConversationalSessionEndedEvent: Tracks cleanup reason

        **Raises**:
        - PortError: If stopping monitoring fails (should not prevent cleanup)
        """

    @abstractmethod
    async def load_session_state(self, work_item_id: str) -> ConversationalSessionState | None:
        """Load persisted session state from storage.

        Retrieves the current session state for a work item from the event store,
        enabling restart continuity and state recovery after orchestrator restarts.

        The session state includes:
        - last_processed_comment_id: Resume checkpoint for comment monitoring
        - llm_conversation_id: LLM context for conversation continuity
        - session status: Whether loop is active, suspended, or terminated

        **Parameters**:
        - work_item_id: The work item whose session to load

        **Returns**:
        - ConversationalSessionState: The loaded session state, or None if no session exists
            for this work item (normal when work item hasn't entered a conversational column yet)

        **Raises**:
        - ValidationError: If work_item_id is invalid or empty
        - EventStoreError: If storage retrieval fails
        """

    @abstractmethod
    async def save_session_state(self, state: ConversationalSessionState) -> None:
        """Persist session state to storage.

        Saves the session state to the event store, enabling:
        - **Restart continuity**: Orchestrator can load state and resume monitoring
        - **Audit trail**: Complete record of session lifecycle through state snapshots
        - **Hot failover**: Multiple orchestrator instances can share session state

        This is typically called after:
        - initialize_loop(): Store newly created session
        - handle_comment_event(): Update last_processed_comment_id and timestamp
        - handle_column_change_event(): Update column_name or status
        - cleanup_loop(): Mark session as terminated

        **Parameters**:
        - state: The ConversationalSessionState object to persist

        **Raises**:
        - ValidationError: If state is invalid (validation happens in ConversationalSessionState)
        - EventStoreError: If storage operation fails
        """
