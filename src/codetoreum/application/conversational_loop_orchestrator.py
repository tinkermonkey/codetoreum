"""Conversational Loop Orchestrator application service.

This service orchestrates feedback loops where AI agents engage in back-and-forth
dialogue with human stakeholders through comment threads on work items.

It manages the complete lifecycle of conversational sessions:
- Initialization when work items enter conversational columns
- Comment handling and agent response execution
- Column transition logic (entry/exit of conversational columns)
- Session state persistence for restart continuity
- Cleanup on errors or manual termination

Architecture:
- Pure orchestration layer (no business logic in domain)
- Coordinates IDiscussionAdapter (comments), ILLMProvider (agent), IEventStore (persistence)
- Emits domain events for audit trail and observability
- Immutable session state for event sourcing integrity
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from codetoreum.domain.conversational_session import ConversationalSessionState
from codetoreum.domain.events.board_events import WorkItemColumnChangedEvent
from codetoreum.domain.events.discussion_events import (
    AgentResponsePostedEvent,
    Comment,
    CommentContext,
    CommentNeedsResponseEvent,
)
from codetoreum.ports.exceptions import EmptyAgentResponseError
from codetoreum.ports.exceptions import EventStoreError
from codetoreum.ports.exceptions import PortError
from codetoreum.ports.input.conversational_loop_service import (
    IConversationalLoopService,
)
from codetoreum.ports.output import (
    IDiscussionAdapter,
    IEventStore,
    ILLMProvider,
)

logger = logging.getLogger(__name__)

# Timeout for LLM provider calls (5 minutes)
_LLM_PROVIDER_TIMEOUT_SECONDS = 300


class ConversationalLoopOrchestrator(IConversationalLoopService):
    """
    Application service for orchestrating conversational feedback loops.

    This service implements the IConversationalLoopService port interface,
    coordinating with external adapters to manage agent-human dialogue
    through comment threads on work items.

    **Responsibilities**:
    - Initialize conversational sessions when work items enter conversational columns
    - Handle comment events by executing agents and posting responses
    - Manage column transitions (session lifecycle)
    - Persist session state for restart continuity
    - Clean up sessions on error or termination

    **Dependencies**:
    - IDiscussionAdapter: Comment monitoring and posting
    - ILLMProvider: Agent execution with conversation context
    - IEventStore: Session state persistence

    **Event Subscriptions**:
    The service subscribes to these domain events (setup via event bus):
    - `comment.needs_response`: Triggers handle_comment_event()
    - `workitem.column_changed`: Triggers handle_column_change_event()

    **Session State Storage**:
    Session state is persisted per work item using a key pattern:
    `conversational_session:{work_item_id}`
    """

    def __init__(
        self,
        discussion_adapter: IDiscussionAdapter,
        llm_provider: ILLMProvider,
        event_store: IEventStore,
    ):
        """
        Initialize ConversationalLoopOrchestrator.

        Args:
            discussion_adapter: Adapter for comment monitoring and posting
            llm_provider: LLM provider for agent execution
            event_store: Event store for session state persistence
        """
        self.discussion_adapter = discussion_adapter
        self.llm_provider = llm_provider
        self.event_store = event_store

    async def initialize_loop(
        self,
        work_item_id: str,
        project_id: str,
        column_config: dict,
    ) -> ConversationalSessionState:
        """Initialize a conversational loop for a work item.

        **Workflow**:
        1. Create unique session identifier
        2. Initialize session state with configuration
        3. Start discussion adapter monitoring
        4. Create and persist session state
        5. Emit ConversationalSessionStartedEvent for audit trail

        Args:
            work_item_id: Unique identifier of the work item
            project_id: Unique identifier of the project
            column_config: Configuration dictionary with:
                - column_name: Name of the board column
                - agent_assignment: Name of the agent assigned to handle responses
                - (optional) other metadata for agent context

        Returns:
            ConversationalSessionState: The initialized session state

        Raises:
            ValueError: If required configuration is missing
            DiscussionAdapterError: If starting monitoring fails
            EventStoreError: If persisting session state fails
        """
        # Validate inputs
        if not work_item_id or not project_id:
            raise ValueError("work_item_id and project_id are required")

        column_name = column_config.get("column_name", "")
        agent_assignment = column_config.get("agent_assignment", "")

        if not column_name or not agent_assignment:
            raise ValueError("column_config must include column_name and agent_assignment")

        # Create unique session identifier
        session_id = f"conv_session_{work_item_id}_{int(datetime.now(timezone.utc).timestamp())}"

        # Initialize session state
        now_iso = datetime.now(timezone.utc).isoformat()
        session_state = ConversationalSessionState(
            session_id=session_id,
            work_item_id=work_item_id,
            project_id=project_id,
            agent_assignment=agent_assignment,
            column_name=column_name,
            llm_conversation_id=None,  # Will be created on first agent execution
            last_processed_comment_id="__checkpoint_start",  # Sentinel: no comments processed yet
            last_interaction_timestamp=now_iso,
            status="active",
        )

        # Start monitoring for comments
        monitoring_config = {
            "project_id": project_id,
            "column_name": column_name,
            "agent_assignment": agent_assignment,
            "last_processed_comment_id": None,
        }

        try:
            self.discussion_adapter.start_monitoring(work_item_id, monitoring_config)
        except PortError as e:
            logger.error(
                "Failed to start discussion monitoring for work item %s: %s",
                work_item_id,
                str(e),
                exc_info=True,
                extra={"error_id": "ERR_CONVERSATIONAL_MONITORING_START_FAILURE"}
            )
            raise

        # Persist session state
        try:
            await self.save_session_state(session_state)
        except EventStoreError as e:
            logger.error(
                "Failed to persist session state for work item %s: %s",
                work_item_id,
                str(e),
                exc_info=True,
                extra={"error_id": "ERR_CONVERSATIONAL_SESSION_PERSIST_FAILURE"}
            )
            # Attempt cleanup on persistence failure
            try:
                self.discussion_adapter.stop_monitoring(work_item_id)
            except PortError as cleanup_error:
                logger.warning(
                    "Failed to clean up monitoring after persistence error: %s",
                    str(cleanup_error),
                    exc_info=True,
                    extra={"error_id": "ERR_CONVERSATIONAL_CLEANUP_AFTER_PERSIST_FAILURE"}
                )
            except Exception as cleanup_error:
                # Unexpected error during cleanup - log but re-raise original persistence error
                logger.warning(
                    "UNEXPECTED error during cleanup after persistence error: %s",
                    str(cleanup_error),
                    exc_info=True,
                    extra={"error_id": "ERR_CONVERSATIONAL_CLEANUP_AFTER_PERSIST_UNEXPECTED"}
                )
            raise

        logger.info(
            "Initialized conversational loop for work item %s with session %s",
            work_item_id,
            session_id,
        )

        return session_state

    async def handle_comment_event(
        self,
        event: CommentNeedsResponseEvent,
    ) -> None:
        """Handle a comment that needs an agent response.

        **Workflow**:
        1. Load active session state from storage
        2. Verify session is active and matches work item
        3. Build thread context (parent comments, history)
        4. Execute assigned agent with conversation continuity
        5. Post agent response to discussion thread
        6. Update session state with checkpoint
        7. Persist updated session state
        8. Emit AgentResponsePostedEvent for audit trail

        Args:
            event: CommentNeedsResponseEvent containing:
                - work_item_id: The work item receiving comment
                - project_id: The project context
                - comment: The human comment requiring response
                - context: Thread context with parent comments and column info

        Raises:
            ValueError: If event data is invalid
            SessionNotFoundError: If no active session exists
            SessionInactiveError: If session is suspended or terminated
            DiscussionAdapterError: If adding comment fails
            LLMProviderError: If agent execution fails
            EventStoreError: If persisting session state fails
        """
        work_item_id = event.work_item_id
        project_id = event.project_id

        # Validate event
        if not work_item_id or not project_id:
            raise ValueError("CommentNeedsResponseEvent must have work_item_id and project_id")

        if not event.comment or not event.comment.id:
            logger.warning(
                "Received CommentNeedsResponseEvent without comment for work item %s",
                work_item_id,
                extra={"error_id": "ERR_CONVERSATIONAL_COMMENT_EVENT_VALIDATION_FAILURE"}
            )
            return

        if not event.context:
            logger.error(
                "[%s] CommentNeedsResponseEvent missing context for work item %s",
                "ERR_CONVERSATIONAL_MISSING_CONTEXT",
                work_item_id,
            )
            raise ValueError("CommentNeedsResponseEvent must have context")

        # Load active session state
        session_state = await self.load_session_state(work_item_id)

        if not session_state:
            logger.warning(
                "No active session found for work item %s, skipping comment response",
                work_item_id,
                extra={"error_id": "ERR_CONVERSATIONAL_NO_ACTIVE_SESSION"}
            )

            # Notify user that no session exists for this work item
            try:
                notification = (
                    "⚠️ **No Active Conversational Session Found**\n\n"
                    "This work item is not currently in a conversational workflow column. "
                    "The AI agent cannot respond to comments at this time.\n\n"
                    "**Possible Reasons**:\n"
                    "- This work item may have been moved out of the conversational column\n"
                    "- The conversational session may have been terminated\n\n"
                    "**Next Steps**:\n"
                    "1. Move the work item back to a conversational workflow column to continue\n"
                    "2. Contact support if you believe this is unexpected\n\n"
                    "*This notification was generated because no active conversational session was found.*"
                )
                await self.discussion_adapter.add_comment(
                    work_item_id=work_item_id,
                    content=notification,
                    parent_id=event.comment.id if event.comment else None,
                )
            except PortError as e:
                logger.error(
                    "Failed to post session-not-found notification for work item %s: %s",
                    work_item_id,
                    str(e),
                    exc_info=True,
                    extra={"error_id": "ERR_CONVERSATIONAL_NO_SESSION_NOTIFICATION_FAILURE"}
                )
            except Exception as e:
                # Unexpected error posting notification - log but continue
                logger.error(
                    "UNEXPECTED error posting session-not-found notification for work item %s: %s",
                    work_item_id,
                    str(e),
                    exc_info=True,
                    extra={"error_id": "ERR_CONVERSATIONAL_NO_SESSION_NOTIFICATION_UNEXPECTED"}
                )

            return

        # Verify session is active
        if session_state.status != "active":
            logger.warning(
                "Session for work item %s is %s, skipping comment response",
                work_item_id,
                session_state.status,
                extra={"error_id": "ERR_CONVERSATIONAL_SESSION_NOT_ACTIVE"}
            )

            # Notify user that session is not active
            try:
                status_display = {
                    "suspended": "suspended",
                    "terminated": "terminated",
                    "paused": "paused",
                }.get(session_state.status, session_state.status)

                notification = (
                    f"⚠️ **Conversational Session {status_display.title()}**\n\n"
                    f"The conversational session for this work item is currently {status_display} "
                    f"and cannot process new comments at this time.\n\n"
                    "**Next Steps**:\n"
                    "1. Check the work item's workflow column status\n"
                    "2. If needed, move the work item back to an active conversational column\n"
                    "3. Or create a new conversational session by moving the work item to a conversational column\n\n"
                    "*This notification was generated because the conversational session is not in an active state.*"
                )
                await self.discussion_adapter.add_comment(
                    work_item_id=work_item_id,
                    content=notification,
                    parent_id=event.comment.id if event.comment else None,
                )
            except PortError as e:
                logger.error(
                    "Failed to post session-inactive notification for work item %s: %s",
                    work_item_id,
                    str(e),
                    exc_info=True,
                    extra={"error_id": "ERR_CONVERSATIONAL_SESSION_INACTIVE_NOTIFICATION_FAILURE"}
                )
            except Exception as e:
                # Unexpected error posting notification - log but continue
                logger.error(
                    "UNEXPECTED error posting session-inactive notification for work item %s: %s",
                    work_item_id,
                    str(e),
                    exc_info=True,
                    extra={"error_id": "ERR_CONVERSATIONAL_SESSION_INACTIVE_NOTIFICATION_UNEXPECTED"}
                )

            return

        logger.info(
            "Handling comment event for work item %s, session %s",
            work_item_id,
            session_state.session_id,
        )

        try:
            # Prevent duplicate responses (FR-4.4)
            if event.comment.id == session_state.last_processed_comment_id:
                logger.debug(
                    "Comment %s already processed (checkpoint: %s), skipping",
                    event.comment.id,
                    session_state.last_processed_comment_id,
                )
                return

            # Build thread context message
            thread_message = self._build_thread_message(event, session_state)

            # Execute agent with conversation context - protected by timeout
            try:
                execution_result = await asyncio.wait_for(
                    self.llm_provider.continue_conversation(
                        conversation_id=session_state.llm_conversation_id or "",
                        message=thread_message,
                    ),
                    timeout=_LLM_PROVIDER_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                logger.error(
                    "[%s] LLM provider timeout for work item %s after %d seconds",
                    "ERR_CONVERSATIONAL_LLM_TIMEOUT",
                    work_item_id,
                    _LLM_PROVIDER_TIMEOUT_SECONDS,
                )
                # Notify user about timeout
                try:
                    await self.discussion_adapter.add_comment(
                        work_item_id=work_item_id,
                        content="⚠️ Response generation timed out after 5 minutes. Please try again.",
                        parent_id=event.comment.id,
                    )
                except PortError as e:
                    logger.error(
                        "Failed to post timeout notification for work item %s: %s",
                        work_item_id,
                        str(e),
                        exc_info=True,
                        extra={"error_id": "ERR_CONVERSATIONAL_LLM_TIMEOUT_NOTIFICATION_FAILURE"}
                    )
                raise EmptyAgentResponseError(work_item_id)

            if not execution_result.content:
                logger.error(
                    "Agent execution returned empty response for work item %s",
                    work_item_id,
                    extra={"error_id": "ERR_CONVERSATIONAL_EMPTY_AGENT_RESPONSE"}
                )
                raise EmptyAgentResponseError(work_item_id)

            # Post agent response to discussion thread
            response_comment = await self.discussion_adapter.add_comment(
                work_item_id=work_item_id,
                content=execution_result.content,
                parent_id=event.comment.id,  # Reply to the human comment
            )

            # Validate adapter response (ensure comment object is valid)
            if response_comment is None:
                logger.error(
                    "Discussion adapter returned None for add_comment for work item %s",
                    work_item_id,
                    extra={"error_id": "ERR_CONVERSATIONAL_ADAPTER_RETURNED_NONE"}
                )
                raise ValueError(f"Discussion adapter returned None comment for work item {work_item_id}")

            if not isinstance(response_comment, Comment):
                logger.error(
                    "Discussion adapter returned invalid comment type %s for work item %s",
                    type(response_comment).__name__,
                    work_item_id,
                    extra={"error_id": "ERR_CONVERSATIONAL_ADAPTER_INVALID_COMMENT_TYPE"}
                )
                raise ValueError(f"Discussion adapter returned invalid comment type for work item {work_item_id}")

            if not response_comment.id:
                logger.error(
                    "Discussion adapter returned comment with empty ID for work item %s",
                    work_item_id,
                    extra={"error_id": "ERR_CONVERSATIONAL_ADAPTER_EMPTY_COMMENT_ID"}
                )
                raise ValueError(f"Discussion adapter returned comment with empty ID for work item {work_item_id}")

            # Update session state
            now_iso = datetime.now(timezone.utc).isoformat()
            updated_session = ConversationalSessionState(
                session_id=session_state.session_id,
                work_item_id=session_state.work_item_id,
                project_id=session_state.project_id,
                agent_assignment=session_state.agent_assignment,
                column_name=session_state.column_name,
                llm_conversation_id=execution_result.conversation_id or session_state.llm_conversation_id,
                last_processed_comment_id=event.comment.id,
                last_interaction_timestamp=now_iso,
                status=session_state.status,
            )

            # Persist updated session state
            await self.save_session_state(updated_session)

            # Emit audit event
            response_event = AgentResponsePostedEvent(
                type="agent.response_posted",
                timestamp=now_iso,
                source="orchestrator",
                work_item_id=work_item_id,
                project_id=project_id,
                comment_id=event.comment.id,
                response_comment_id=response_comment.id,
                agent_name=session_state.agent_assignment,
                conversation_id=execution_result.conversation_id,
            )
            await self.event_store.append(work_item_id, [response_event])

            logger.info(
                "Posted agent response to work item %s, responding to comment %s",
                work_item_id,
                event.comment.id,
            )

        except (PortError, ValueError, AttributeError) as e:
            logger.error(
                "Error handling comment event for work item %s: %s",
                work_item_id,
                str(e),
                exc_info=True,
                extra={"error_id": "ERR_CONVERSATIONAL_COMMENT_HANDLER_FAILURE"}
            )
            # FR-7.1: Error is logged with full context (exc_info=True) for observability
            # Don't clean up session on transient errors - let it retry
            raise
        except Exception as e:
            # Catch unexpected programming errors and system-level errors
            logger.critical(
                "UNEXPECTED error in comment event handler for work item %s - programming bug: %s",
                work_item_id,
                str(e),
                exc_info=True,
                extra={"error_id": "ERR_CONVERSATIONAL_COMMENT_HANDLER_UNEXPECTED"}
            )
            raise

    async def handle_column_change_event(
        self,
        event: WorkItemColumnChangedEvent,
    ) -> None:
        """Handle work item column transitions.

        **Workflow**:

        **If exiting a conversational column**:
        1. Load session state
        2. Stop discussion monitoring
        3. Mark session as terminated
        4. Persist updated session state

        **If entering a conversational column**:
        1. Check if session exists
        2. If new, call initialize_loop()
        3. If existing, resume monitoring if suspended

        **If moving between conversational columns**:
        1. Update column_name in session state
        2. Continue monitoring without interruption

        Args:
            event: WorkItemColumnChangedEvent with:
                - work_item_id: The work item that moved
                - project_id: The project context
                - from_column: Previous column name
                - to_column: New column name

        Raises:
            ValueError: If event data is invalid
            DiscussionAdapterError: If starting/stopping monitoring fails
            EventStoreError: If persisting state fails
        """
        work_item_id = event.work_item_id
        project_id = event.project_id
        from_column = getattr(event, "from_column", "")
        to_column = getattr(event, "to_column", "")

        if not work_item_id or not project_id:
            raise ValueError("WorkItemColumnChangedEvent must have work_item_id and project_id")

        logger.info(
            "Handling column change for work item %s: %s → %s",
            work_item_id,
            from_column,
            to_column,
        )

        # Load current session if exists
        session_state = await self.load_session_state(work_item_id)

        # Check if we're exiting a conversational column
        if session_state and session_state.status != "terminated":
            # Stop monitoring (work item leaving the conversational context)
            try:
                self.discussion_adapter.stop_monitoring(work_item_id)
            except PortError as e:
                logger.warning(
                    "Failed to stop monitoring for work item %s: %s",
                    work_item_id,
                    str(e),
                    exc_info=True,
                    extra={"error_id": "ERR_CONVERSATIONAL_MONITORING_STOP_FAILURE"}
                )
            except Exception as e:
                # Unexpected error during monitoring stop - log but continue
                logger.warning(
                    "UNEXPECTED error stopping monitoring for work item %s: %s",
                    work_item_id,
                    str(e),
                    exc_info=True,
                    extra={"error_id": "ERR_CONVERSATIONAL_MONITORING_STOP_UNEXPECTED"}
                )

            # Mark session as terminated
            now_iso = datetime.now(timezone.utc).isoformat()
            terminated_session = ConversationalSessionState(
                session_id=session_state.session_id,
                work_item_id=session_state.work_item_id,
                project_id=session_state.project_id,
                agent_assignment=session_state.agent_assignment,
                column_name=from_column,
                llm_conversation_id=session_state.llm_conversation_id,
                last_processed_comment_id=session_state.last_processed_comment_id,
                last_interaction_timestamp=now_iso,
                status="terminated",
            )

            try:
                await self.save_session_state(terminated_session)
            except EventStoreError as e:
                logger.error(
                    "Failed to persist terminated session state for work item %s: %s",
                    work_item_id,
                    str(e),
                    exc_info=True,
                    extra={"error_id": "ERR_CONVERSATIONAL_TERMINATE_SESSION_PERSIST_FAILURE"}
                )
                raise

            logger.info(
                "Terminated conversational session for work item %s",
                work_item_id,
            )

        # Check if we're entering a conversational column (new session)
        elif not session_state and to_column.lower() in ["conversational", "feedback"]:
            # Initialize new session for this column
            try:
                await self.initialize_loop(
                    work_item_id=work_item_id,
                    project_id=project_id,
                    column_config={
                        "column_name": to_column,
                        "agent_assignment": getattr(event.context, "agent_assignment", "default-agent") if hasattr(event, "context") else "default-agent",
                    },
                )
                logger.info(
                    "Initialized conversational session on column entry for work item %s",
                    work_item_id,
                )
            except (PortError, ValueError) as e:
                logger.error(
                    "Failed to initialize conversational loop on column entry for work item %s: %s",
                    work_item_id,
                    str(e),
                    exc_info=True,
                    extra={"error_id": "ERR_CONVERSATIONAL_LOOP_INIT_FAILURE"}
                )

                # Post error comment to work item so user is notified
                try:
                    error_comment = (
                        f"❌ **Conversational Mode Failed to Initialize**\n\n"
                        f"The AI agent failed to start monitoring this work item for conversational feedback.\n\n"
                        f"**Error Details**: {str(e)}\n\n"
                        f"**Next Steps**:\n"
                        f"1. Move the work item to a different column\n"
                        f"2. Contact support if the issue persists\n\n"
                        f"*This notification was generated because monitoring initialization failed.*"
                    )
                    await self.discussion_adapter.add_comment(
                        work_item_id=work_item_id,
                        content=error_comment,
                    )
                except PortError as comment_error:
                    logger.error(
                        "Failed to post error notification comment for work item %s: %s",
                        work_item_id,
                        str(comment_error),
                        exc_info=True,
                        extra={"error_id": "ERR_CONVERSATIONAL_LOOP_INIT_NOTIFICATION_FAILURE"}
                    )
                except Exception as comment_error:
                    # Unexpected error posting comment - log but continue
                    logger.error(
                        "UNEXPECTED error posting error notification comment for work item %s: %s",
                        work_item_id,
                        str(comment_error),
                        exc_info=True,
                        extra={"error_id": "ERR_CONVERSATIONAL_LOOP_INIT_NOTIFICATION_UNEXPECTED"}
                    )

                # Re-raise to trigger alerts and prevent execution from continuing
                raise

    async def cleanup_loop(
        self,
        work_item_id: str,
        reason: str,
    ) -> None:
        """Clean up loop state on error or manual termination.

        This method is idempotent - safe to call multiple times on the same work item.

        **Workflow**:
        1. Load session state (if exists)
        2. Stop discussion monitoring
        3. Mark session as terminated
        4. Persist updated state

        Args:
            work_item_id: The work item whose loop should be cleaned up
            reason: Human-readable reason for cleanup

        Raises:
            DiscussionAdapterError: If stopping monitoring fails (should not prevent cleanup)
        """
        if not work_item_id:
            raise ValueError("work_item_id is required")

        logger.info(
            "Cleaning up conversational loop for work item %s, reason: %s",
            work_item_id,
            reason,
        )

        try:
            # Load current session if exists
            session_state = await self.load_session_state(work_item_id)

            if not session_state:
                logger.debug(
                    "No active session found for work item %s during cleanup",
                    work_item_id,
                )
                return

            # Stop monitoring (best effort - don't let failures prevent cleanup continuation)
            try:
                self.discussion_adapter.stop_monitoring(work_item_id)
            except PortError as e:
                logger.warning(
                    "Failed to stop monitoring during cleanup for work item %s: %s",
                    work_item_id,
                    str(e),
                    exc_info=True,
                    extra={"error_id": "ERR_CONVERSATIONAL_CLEANUP_MONITORING_STOP_FAILURE"}
                )
            except Exception as e:
                # Unexpected error during best-effort cleanup - log but continue
                logger.warning(
                    "UNEXPECTED error stopping monitoring during cleanup for work item %s: %s",
                    work_item_id,
                    str(e),
                    exc_info=True,
                    extra={"error_id": "ERR_CONVERSATIONAL_CLEANUP_MONITORING_STOP_UNEXPECTED"}
                )

            # Mark session as terminated if not already
            if session_state.status != "terminated":
                now_iso = datetime.now(timezone.utc).isoformat()
                terminated_session = ConversationalSessionState(
                    session_id=session_state.session_id,
                    work_item_id=session_state.work_item_id,
                    project_id=session_state.project_id,
                    agent_assignment=session_state.agent_assignment,
                    column_name=session_state.column_name,
                    llm_conversation_id=session_state.llm_conversation_id,
                    last_processed_comment_id=session_state.last_processed_comment_id,
                    last_interaction_timestamp=now_iso,
                    status="terminated",
                )

                try:
                    await self.save_session_state(terminated_session)
                except EventStoreError as e:
                    logger.error(
                        "Failed to persist cleanup state for work item %s: %s",
                        work_item_id,
                        str(e),
                        exc_info=True,
                        extra={"error_id": "ERR_CONVERSATIONAL_CLEANUP_PERSIST_FAILURE"}
                    )
                    raise

            logger.info(
                "Cleaned up conversational loop for work item %s",
                work_item_id,
            )

        except (PortError, ValueError) as e:
            logger.error(
                "Error during cleanup for work item %s: %s",
                work_item_id,
                str(e),
                exc_info=True,
                extra={"error_id": "ERR_CONVERSATIONAL_CLEANUP_HANDLER_FAILURE"}
            )
            raise
        except Exception as e:
            # Catch unexpected programming errors and system-level errors
            logger.critical(
                "UNEXPECTED error in cleanup handler for work item %s - programming bug: %s",
                work_item_id,
                str(e),
                exc_info=True,
                extra={"error_id": "ERR_CONVERSATIONAL_CLEANUP_HANDLER_UNEXPECTED"}
            )
            raise

    async def load_session_state(
        self,
        work_item_id: str,
    ) -> Optional[ConversationalSessionState]:
        """Load persisted session state from storage.

        Args:
            work_item_id: The work item whose session to load

        Returns:
            ConversationalSessionState if session exists, None otherwise

        Raises:
            ValueError: If work_item_id is invalid
            EventStoreError: If storage retrieval fails
        """
        if not work_item_id:
            raise ValueError("work_item_id is required")

        try:
            # Try to load session state from snapshot (fast path)
            snapshot_result = await self.event_store.get_latest_snapshot(work_item_id)

            if snapshot_result:
                # Handle both formats: raw snapshot data and wrapped snapshot
                # Wrapped format: {"version": int, "data": {...}, "timestamp": ...}
                # Raw format: {...session data...}
                if isinstance(snapshot_result, dict):
                    if "data" in snapshot_result and isinstance(snapshot_result["data"], dict):
                        # Wrapped format from InMemoryEventStore
                        snapshot = snapshot_result["data"]
                    else:
                        # Raw format (for compatibility)
                        snapshot = snapshot_result

                    if "conversational_session_state" in snapshot:
                        return ConversationalSessionState.from_dict(snapshot["conversational_session_state"])

            # No snapshot found - session doesn't exist
            return None

        except (EventStoreError, ValueError, AttributeError, KeyError, TypeError) as e:
            logger.error(
                "Failed to load session state for work item %s: %s",
                work_item_id,
                str(e),
                exc_info=True,
                extra={"error_id": "ERR_CONVERSATIONAL_LOAD_SESSION_FAILURE"}
            )
            raise
        except Exception as e:
            # Catch unexpected programming errors and system-level errors
            logger.critical(
                "UNEXPECTED error loading session state for work item %s - programming bug: %s",
                work_item_id,
                str(e),
                exc_info=True,
                extra={"error_id": "ERR_CONVERSATIONAL_LOAD_SESSION_UNEXPECTED"}
            )
            raise

    async def save_session_state(
        self,
        state: ConversationalSessionState,
    ) -> None:
        """Persist session state to storage.

        Args:
            state: The ConversationalSessionState object to persist

        Raises:
            ValueError: If state is invalid
            EventStoreError: If storage operation fails
        """
        if not state:
            raise ValueError("state is required")

        try:
            # Save session state as a snapshot in the event store
            # This enables fast recovery without replaying all events
            snapshot_data = {
                "conversational_session_state": state.to_dict(),
            }

            # Use the proper snapshot API - snapshots are versioned by stream
            # Get current version to snapshot with
            version = await self.event_store.get_stream_version(state.work_item_id)

            await self.event_store.save_snapshot(
                stream_id=state.work_item_id,
                version=version,
                snapshot=snapshot_data,
            )

            logger.debug(
                "Persisted session state for work item %s, session %s",
                state.work_item_id,
                state.session_id,
            )

        except Exception as e:
            logger.error(
                "Failed to persist session state for work item %s: %s",
                state.work_item_id,
                str(e),
                exc_info=True,
                extra={"error_id": "ERR_CONVERSATIONAL_SAVE_SESSION_FAILURE"}
            )
            raise

    def _build_thread_message(
        self,
        event: CommentNeedsResponseEvent,
        session_state: ConversationalSessionState,
    ) -> str:
        """Build the message to send to the LLM based on comment thread context.

        Args:
            event: The comment needs response event with context
            session_state: Current session state

        Returns:
            Formatted message with thread context for the agent
        """
        parts = []

        # Add context about where we are
        if isinstance(event.context, CommentContext):
            if event.context.column_name:
                parts.append(f"Work item: {event.context.column_name}")
            if event.context.agent_assignment:
                parts.append(f"Assigned agent: {event.context.agent_assignment}")

            # Add parent comment if available
            if event.context.parent_comment:
                parent = event.context.parent_comment
                parts.append(f"\nPrevious comment from {parent.author}:")
                parts.append(parent.body)

        # Add the current comment
        if isinstance(event.comment, Comment):
            parts.append(f"\nNew comment from {event.comment.author}:")
            parts.append(event.comment.body)

        return "\n".join(parts)
