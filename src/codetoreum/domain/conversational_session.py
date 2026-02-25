"""Conversational session state for feedback loop tracking.

This module provides immutable value objects for managing conversational loop sessions
where AI agents engage in back-and-forth dialogue with human stakeholders through
comment threads on work items.

The session state captures all information needed for:
- Restart continuity: Resume monitoring from last_processed_comment_id
- LLM context continuity: Pass llm_conversation_id to continue_conversation() API
- Audit trail: Complete lifecycle tracking via immutable state snapshots
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ConversationalSessionState:
    """Persistent state for a conversational feedback loop session.

    **Immutability**: This is an immutable value object (frozen dataclass). All fields
    are read-only after construction to ensure data integrity and prevent accidental
    modifications. This immutability is critical for event sourcing, as state snapshots
    must be immutable facts. Attempting to modify any field will raise `FrozenInstanceError`.

    **Purpose**: This value object represents the complete state of a conversational loop
    at a point in time, enabling:
    - **Session persistence**: Store and retrieve session state from event store
    - **Restart continuity**: Resume monitoring from last_processed_comment_id checkpoint
    - **LLM context continuity**: Maintain conversation history via llm_conversation_id
    - **Audit trail**: Complete record of session lifecycle through state snapshots

    **State Transitions**:
    - "active": Actively monitoring for comments and posting responses
    - "suspended": Temporarily paused (e.g., due to errors or user request)
    - "terminated": Loop completed or explicitly cleaned up

    Attributes:
        session_id (str): Unique identifier for this conversational session
        work_item_id (str): ID of the work item containing the discussion thread
        project_id (str): ID of the project containing the work item
        agent_assignment (str): Name of the agent assigned to this feedback loop
        column_name (Optional[str]): Name of the board column where the work item is located,
            None if not tracked (board context is optional metadata, not core session concern).
        llm_conversation_id (Optional[str]): LLM provider's conversation session ID,
            used to maintain context across multiple agent responses (e.g., for
            Claude Code's --session-id flag). None if not yet created.
        last_processed_comment_id (str): ID of the last comment processed/responded to.
            Used as resume checkpoint: adapter skips all comments up to this ID.
        last_interaction_timestamp (str): ISO 8601 timestamp of the most recent
            agent response posted or comment received, for lifecycle tracking.
        status (Literal["active", "suspended", "terminated"]): Current state of
            the conversational loop lifecycle.

    Example:
        >>> state = ConversationalSessionState(
        ...     session_id="sess-001",
        ...     work_item_id="issue-42",
        ...     project_id="proj-1",
        ...     agent_assignment="code-reviewer",
        ...     column_name="In Review",
        ...     llm_conversation_id="conv-abc123",
        ...     last_processed_comment_id="comment-10",
        ...     last_interaction_timestamp="2025-01-14T10:35:00+00:00",
        ...     status="active"
        ... )
        >>> state.status = "suspended"  # ❌ Raises FrozenInstanceError
        >>> new_state = ConversationalSessionState(
        ...     session_id=state.session_id,
        ...     work_item_id=state.work_item_id,
        ...     project_id=state.project_id,
        ...     agent_assignment=state.agent_assignment,
        ...     column_name=state.column_name,
        ...     llm_conversation_id=state.llm_conversation_id,
        ...     last_processed_comment_id="comment-11",  # Updated
        ...     last_interaction_timestamp="2025-01-14T10:40:00+00:00",  # Updated
        ...     status="active"
        ... )  # ✅ Create new state object (immutability preserved)
    """

    session_id: str
    work_item_id: str
    project_id: str
    agent_assignment: str
    column_name: str | None
    llm_conversation_id: str | None
    last_processed_comment_id: str
    last_interaction_timestamp: str
    status: Literal["active", "suspended", "terminated"]

    def __post_init__(self) -> None:
        """Validate session state after initialization."""
        if not self.session_id:
            raise ValueError("session_id is required")
        if not self.work_item_id:
            raise ValueError("work_item_id is required")
        if not self.project_id:
            raise ValueError("project_id is required")
        if not self.agent_assignment:
            raise ValueError("agent_assignment is required")
        if not self.last_processed_comment_id:
            raise ValueError("last_processed_comment_id is required")
        if not self.last_interaction_timestamp:
            raise ValueError("last_interaction_timestamp is required")
        # Validate ISO 8601 timestamp
        try:
            from datetime import datetime
            datetime.fromisoformat(self.last_interaction_timestamp.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as e:
            raise ValueError(f"last_interaction_timestamp must be ISO 8601 format: {e}")
        # Validate status is one of the allowed values
        if self.status not in ("active", "suspended", "terminated"):
            raise ValueError(f"status must be one of: 'active', 'suspended', 'terminated', got '{self.status}'")

    def to_dict(self) -> dict:
        """Serialize to dictionary for storage."""
        return {
            "session_id": self.session_id,
            "work_item_id": self.work_item_id,
            "project_id": self.project_id,
            "agent_assignment": self.agent_assignment,
            "column_name": self.column_name,
            "llm_conversation_id": self.llm_conversation_id,
            "last_processed_comment_id": self.last_processed_comment_id,
            "last_interaction_timestamp": self.last_interaction_timestamp,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConversationalSessionState":
        """Deserialize from dictionary."""
        return cls(
            session_id=data.get("session_id", ""),
            work_item_id=data.get("work_item_id", ""),
            project_id=data.get("project_id", ""),
            agent_assignment=data.get("agent_assignment", ""),
            column_name=data.get("column_name"),
            llm_conversation_id=data.get("llm_conversation_id"),
            last_processed_comment_id=data.get("last_processed_comment_id", ""),
            last_interaction_timestamp=data.get("last_interaction_timestamp", ""),
            status=data.get("status", "active"),
        )
