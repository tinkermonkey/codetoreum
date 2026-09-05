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
- Coordinates IDiscussionAdapter (comments), ICodingAgent (agent execution),
  IPromptBuilder (prompt assembly), IAgentRepository (agent lookup),
  IWorkItemService (work item lookup), IEventStore (persistence)
- Emits domain events for audit trail and observability
- Immutable session state for event sourcing integrity

Per-turn execution model (post-D5 redesign):
Each comment requiring a response becomes a fresh :meth:`ICodingAgent.execute`
invocation. Continuity across turns flows through
:attr:`StructuredPrompt.prior_outputs` — earlier dialogue turns are passed as
``ExecutionOutput`` entries so the agent sees the full thread context without
relying on a vendor-specific conversation handle. The
``llm_conversation_id`` field on :class:`ConversationalSessionState` is kept
for legacy snapshot round-trips but is no longer the source of conversational
continuity.
"""

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from codetoreum.domain.agent_execution import AgentExecution
from codetoreum.domain.conversational_session import ConversationalSessionState
from codetoreum.domain.events.board_events import WorkItemColumnChangedEvent
from codetoreum.domain.events.discussion_events import (
    AgentResponsePostedEvent,
    Comment,
    CommentContext,
    CommentNeedsResponseEvent,
    ConversationalLoopStartedEvent,
    FeedbackListeningStartedEvent,
    FeedbackListeningStoppedEvent,
)
from codetoreum.domain.types import WorkItemId
from codetoreum.domain.workspace_context import WorkspaceContext
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.ports.exceptions import (
    EmptyAgentResponseError,
    EventStoreError,
    PortError,
)
from codetoreum.ports.input.conversational_loop_service import (
    IConversationalLoopService,
)
from codetoreum.ports.output import (
    IDiscussionAdapter,
    IEventEmitter,
    IEventStore,
)
from codetoreum.ports.output.agent_repository import IAgentRepository
from codetoreum.ports.output.coding_agent import (
    CodingAgentInvocationOptions,
    CodingAgentResult,
    ICodingAgent,
)
from codetoreum.ports.output.discussion_adapter import DiscussionMonitoringConfig
from codetoreum.ports.output.prompt_builder import ExecutionOutput, IPromptBuilder
from codetoreum.ports.output.work_item_service import IWorkItemService

logger = logging.getLogger(__name__)

# Timeout for coding-agent execute() calls (5 minutes)
_CODING_AGENT_TIMEOUT_SECONDS = 300


class ConversationalLoopOrchestrator(IConversationalLoopService):
    """
    Application service for orchestrating conversational feedback loops.

    This service implements the IConversationalLoopService port interface,
    coordinating with external adapters to manage agent-human dialogue
    through comment threads on work items.

    **Responsibilities**:
    - Initialize conversational sessions when work items enter conversational columns
    - Handle comment events by executing agents via ICodingAgent and posting responses
    - Manage column transitions (session lifecycle)
    - Persist session state for restart continuity
    - Clean up sessions on error or termination

    **Dependencies**:
    - IDiscussionAdapter: Comment monitoring and posting
    - ICodingAgent: Coding-agent execution (replaces retired ILLMProvider)
    - IPromptBuilder: Vendor-agnostic prompt assembly
    - IAgentRepository: Lookup of assigned agent by name
    - IWorkItemService: Lookup of work item for prompt context
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
        coding_agent: ICodingAgent,
        prompt_builder: IPromptBuilder,
        agent_repository: IAgentRepository,
        work_item_service: IWorkItemService,
        event_store: IEventStore,
        event_emitter: IEventEmitter | None = None,
    ):
        """
        Initialize ConversationalLoopOrchestrator.

        Args:
            discussion_adapter: Adapter for comment monitoring and posting
            coding_agent: Coding-agent adapter (ICodingAgent) used to generate
                each turn's response. Replaces the retired ILLMProvider.
            prompt_builder: Prompt assembly strategy (IPromptBuilder). Used
                to build a StructuredPrompt for each turn, threading prior
                comments through ``prior_outputs``.
            agent_repository: Repository for looking up the assigned Agent
                by name (``column_config.agent_assignment``).
            work_item_service: Service for loading the WorkItem associated
                with each comment thread (passed to the prompt builder).
            event_store: Event store for session state persistence
            event_emitter: Optional event emitter for domain event publication
        """
        self.discussion_adapter = discussion_adapter
        self.coding_agent = coding_agent
        self.prompt_builder = prompt_builder
        self.agent_repository = agent_repository
        self.work_item_service = work_item_service
        self.event_store = event_store
        self._event_emitter = event_emitter

    async def initialize_loop(
        self,
        work_item_id: str,
        project_id: str,
        column_config: dict,
    ) -> ConversationalSessionState:
        """Initialize a conversational loop for a work item."""
        # Validate inputs
        if not work_item_id or not project_id:
            message = "work_item_id and project_id are required"
            raise ValueError(message)

        agent_assignment = column_config.get("agent_assignment", "")
        column_name = column_config.get("column_name")

        if not agent_assignment:
            message = "column_config must include agent_assignment"
            raise ValueError(message)

        # Create unique session identifier
        session_id = f"conv_session_{work_item_id}_{int(datetime.now(UTC).timestamp())}"

        # Initialize session state
        now_iso = datetime.now(UTC).isoformat()
        session_state = ConversationalSessionState(
            session_id=session_id,
            work_item_id=work_item_id,
            project_id=project_id,
            agent_assignment=agent_assignment,
            column_name=column_name,
            llm_conversation_id=None,
            last_processed_comment_id="__checkpoint_start",
            last_interaction_timestamp=now_iso,
            status="active",
        )

        # Start monitoring for comments
        monitoring_config = DiscussionMonitoringConfig(
            project_id=project_id,
            last_processed_comment_id=None,
        )

        try:
            self.discussion_adapter.start_monitoring(work_item_id, monitoring_config)
        except PortError as e:
            logger.error(
                "Failed to start discussion monitoring for work item %s: %s",
                work_item_id,
                str(e),
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_CONVERSATIONAL_MONITORING_START_FAILURE},
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
                extra={"error_id": ErrorRegistry.ERR_DATABASE_ERROR},
            )
            try:
                self.discussion_adapter.stop_monitoring(work_item_id)
            except PortError as cleanup_error:
                logger.warning(
                    "Failed to clean up monitoring after persistence error: %s",
                    str(cleanup_error),
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_DATABASE_ERROR},
                )
            except Exception as cleanup_error:
                logger.warning(
                    "UNEXPECTED error during cleanup after persistence error: %s",
                    str(cleanup_error),
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
                )
            raise

        if self._event_emitter:
            now = datetime.now(UTC).isoformat()
            self._event_emitter.emit(
                ConversationalLoopStartedEvent(
                    type="conversational_loop.started",
                    work_item_id=work_item_id,
                    project_id=project_id,
                    session_id=session_id,
                    agent_assignment=agent_assignment,
                    column_name=column_name,
                    timestamp=now,
                    source="orchestrator",
                )
            )
            self._event_emitter.emit(
                FeedbackListeningStartedEvent(
                    type="feedback_listening.started",
                    work_item_id=work_item_id,
                    project_id=project_id,
                    session_id=session_id,
                    timestamp=datetime.now(UTC).isoformat(),
                    source="orchestrator",
                )
            )

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
        """Handle a comment that needs an agent response."""
        work_item_id = event.work_item_id
        project_id = event.project_id

        if not work_item_id or not project_id:
            message = "CommentNeedsResponseEvent must have work_item_id and project_id"
            raise ValueError(message)

        if not event.comment or not event.comment.id:
            logger.warning(
                "Received CommentNeedsResponseEvent without comment for work item %s",
                work_item_id,
                extra={"error_id": ErrorRegistry.ERR_VALIDATION_FAILED},
            )
            return

        if not event.context:
            logger.error(
                "[%s] CommentNeedsResponseEvent missing context for work item %s",
                "ERR_CONVERSATIONAL_MISSING_CONTEXT",
                work_item_id,
                extra={"error_id": ErrorRegistry.ERR_CONVERSATIONAL_LOOP_ERROR},
            )
            message = "CommentNeedsResponseEvent must have context"
            raise ValueError(message)

        # Load active session state
        session_state = await self.load_session_state(work_item_id)

        if not session_state:
            logger.warning(
                "No active session found for work item %s, skipping comment response",
                work_item_id,
                extra={"error_id": ErrorRegistry.ERR_CONVERSATIONAL_LOOP_ERROR},
            )
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
                    extra={"error_id": ErrorRegistry.ERR_EVENT_PUBLICATION_ERROR},
                )
            except Exception as e:
                logger.error(
                    "UNEXPECTED error posting session-not-found notification for work item %s: %s",
                    work_item_id,
                    str(e),
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
                )
            return

        if session_state.status != "active":
            logger.warning(
                "Session for work item %s is %s, skipping comment response",
                work_item_id,
                session_state.status,
                extra={"error_id": ErrorRegistry.ERR_CONVERSATIONAL_LOOP_ERROR},
            )
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
                    extra={"error_id": ErrorRegistry.ERR_EVENT_PUBLICATION_ERROR},
                )
            except Exception as e:
                logger.error(
                    "UNEXPECTED error posting session-inactive notification for work item %s: %s",
                    work_item_id,
                    str(e),
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
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

            # Execute agent for this turn via ICodingAgent.execute()
            try:
                execution_result: CodingAgentResult = await asyncio.wait_for(
                    self._execute_turn(event, session_state),
                    timeout=_CODING_AGENT_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                logger.error(
                    "[%s] Coding agent timeout for work item %s after %d seconds",
                    "ERR_CONVERSATIONAL_CODING_AGENT_TIMEOUT",
                    work_item_id,
                    _CODING_AGENT_TIMEOUT_SECONDS,
                    extra={"error_id": ErrorRegistry.ERR_CONVERSATIONAL_LOOP_ERROR},
                )
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
                        extra={"error_id": "ERR_EXTERNAL_SERVICE_TIMEOUT"},
                    )
                raise EmptyAgentResponseError(work_item_id)

            if not execution_result.success or not execution_result.summary_text:
                logger.error(
                    "Coding agent returned empty/failed response for work item %s: %s",
                    work_item_id,
                    execution_result.error_summary or "no summary_text",
                    extra={"error_id": ErrorRegistry.ERR_EXTERNAL_SERVICE_ERROR},
                )
                raise EmptyAgentResponseError(work_item_id)

            # Post agent response to discussion thread
            response_comment = await self.discussion_adapter.add_comment(
                work_item_id=work_item_id,
                content=execution_result.summary_text,
                parent_id=event.comment.id,
            )

            # Validate adapter response
            if response_comment is None:
                logger.error(
                    "Discussion adapter returned None for add_comment for work item %s",
                    work_item_id,
                    extra={"error_id": ErrorRegistry.ERR_EXTERNAL_SERVICE_ERROR},
                )
                message = f"Discussion adapter returned None comment for work item {work_item_id}"
                raise ValueError(message)

            if not isinstance(response_comment, Comment):
                logger.error(
                    "Discussion adapter returned invalid comment type %s for work item %s",
                    type(response_comment).__name__,
                    work_item_id,
                    extra={"error_id": ErrorRegistry.ERR_VALIDATION_FAILED},
                )
                message = f"Discussion adapter returned invalid comment type for work item {work_item_id}"
                raise ValueError(message)

            if not response_comment.id:
                logger.error(
                    "Discussion adapter returned comment with empty ID for work item %s",
                    work_item_id,
                    extra={"error_id": ErrorRegistry.ERR_VALIDATION_FAILED},
                )
                message = f"Discussion adapter returned comment with empty ID for work item {work_item_id}"
                raise ValueError(message)

            # Update session state. Conversation continuity is now carried in
            # ``prior_outputs`` (rebuilt fresh from the thread on each turn);
            # llm_conversation_id is kept for legacy snapshot round-trips only.
            now_iso = datetime.now(UTC).isoformat()
            updated_session = ConversationalSessionState(
                session_id=session_state.session_id,
                work_item_id=session_state.work_item_id,
                project_id=session_state.project_id,
                agent_assignment=session_state.agent_assignment,
                column_name=session_state.column_name,
                llm_conversation_id=session_state.llm_conversation_id,
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
                conversation_id=session_state.llm_conversation_id,
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
                extra={"error_id": ErrorRegistry.ERR_HANDLER_EXECUTION},
            )
            raise
        except Exception as e:
            logger.critical(
                "UNEXPECTED error in comment event handler for work item %s - programming bug: %s",
                work_item_id,
                str(e),
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_HANDLER_EXECUTION},
            )
            raise

    async def _execute_turn(
        self,
        event: CommentNeedsResponseEvent,
        session_state: ConversationalSessionState,
    ) -> CodingAgentResult:
        """Execute a single conversational turn via the coding agent.

        Each call to ``handle_comment_event`` triggers a fresh invocation of
        :meth:`ICodingAgent.execute`. Conversation continuity flows through
        :attr:`StructuredPrompt.prior_outputs`: prior comment threads are
        rendered as :class:`ExecutionOutput` entries so the agent sees the
        full history without depending on any vendor-specific session handle.
        """
        # 1. Look up assigned agent + work item.
        agent = await self.agent_repository.get_by_name(session_state.agent_assignment)
        work_item = await self.work_item_service.get_work_item(WorkItemId(session_state.work_item_id))

        # 2. Build a workspace context for the discussion turn. We use the
        #    HYBRID workspace type because conversational turns may post
        #    comments and (depending on agent role) may also make code
        #    changes. The branch_name is synthetic and not used to drive
        #    a VCS branch — the orchestrator does not commit conversational
        #    turn outputs.
        synthetic_branch = f"conversational/{session_state.session_id}"
        workspace_context = WorkspaceContext.for_hybrid(
            project_id=session_state.project_id,
            work_item_id=session_state.work_item_id,
            branch_name=synthetic_branch,
            discussion_id=session_state.work_item_id,
            workspace_path=Path("/tmp/codetoreum-conversational").joinpath(session_state.session_id),
        )

        # 3. Render the comment thread into prior_outputs so the prompt
        #    builder can incorporate dialogue history. The current comment
        #    is appended as the most recent prior_output so the agent sees
        #    the human-side message in the StructuredPrompt.
        prior_outputs = self._build_prior_outputs(event, session_state)

        # 4. Build the structured prompt (vendor-agnostic). The adapter
        #    re-invokes its own IPromptBuilder inside execute(); when both
        #    builders are the same instance, the structured prompt the
        #    orchestrator and adapter produce match. Building it here
        #    surfaces validation errors early.
        structured_prompt = await self.prompt_builder.build(
            agent=agent,
            work_item=work_item,
            workspace_context=workspace_context,
            prior_outputs=prior_outputs,
        )
        # The variable is constructed for early validation and to document
        # the intent — the coding-agent adapter's own IPromptBuilder call
        # produces the prompt that drives the vendor invocation.
        del structured_prompt

        # 5. Synthesize an AgentExecution for this turn. The orchestrator
        #    does not persist its lifecycle through ExecutionService —
        #    conversational turns are tracked via ConversationalSessionState
        #    + AgentResponsePostedEvent. The execution object is required
        #    by the ICodingAgent.execute() contract (it identifies the run
        #    for event correlation on the event bus).
        # handle_comment_event() validated event.comment is not None before
        # delegating here, but mypy needs the local narrowing.
        assert event.comment is not None
        synthetic_prompt_summary = (
            f"[conversational_turn] session={session_state.session_id} " f"comment={event.comment.id}"
        )
        if agent.invocation is None:
            msg = (
                f"Agent '{agent.name}' has no `invocation` config (D6). "
                "Conversational turns require an invocation block."
            )
            raise ValueError(msg)
        execution = AgentExecution.create(
            agent_id=agent.id,
            work_item_id=session_state.work_item_id,
            workflow_id=f"conversational-{session_state.session_id}",
            stage_name="conversational_response",
            prompt=synthetic_prompt_summary,
            model=agent.invocation.model,
            session_id=session_state.session_id,
        )
        execution.start(container_name=None)
        # The synthesized execution lives only for this call; its lifecycle
        # events are not persisted (they belong to the workflow pipeline,
        # which conversational turns are outside of).
        execution.clear_events()

        # 6. Build per-invocation options from the agent's invocation block
        #    (D6 schema). Mode + model + timeout flow straight through.
        options = CodingAgentInvocationOptions(
            invocation_mode=agent.invocation.mode,
            model=agent.invocation.model,
            timeout_seconds=agent.invocation.timeout_seconds,
            cost_limit_usd=agent.invocation.cost_limit_usd,
            mode_config=dict(agent.invocation.mode_config),
        )

        return await self.coding_agent.execute(execution, workspace_context, options)

    @staticmethod
    def _build_prior_outputs(
        event: CommentNeedsResponseEvent,
        session_state: ConversationalSessionState,
    ) -> tuple[ExecutionOutput, ...]:
        """Render the available comment thread context as prior_outputs.

        Each prior comment in the thread becomes a separate
        :class:`ExecutionOutput` with ``stage_name="conversational_turn"``
        so the prompt builder can incorporate it as upstream context.
        The current comment is appended as the final ``prior_output`` so
        the agent sees the human-side message in the prompt.
        """
        del session_state  # reserved for future use (richer history pull)
        outputs: list[ExecutionOutput] = []

        if isinstance(event.context, CommentContext) and event.context.parent_comment:
            parent = event.context.parent_comment
            outputs.append(
                ExecutionOutput(
                    stage_name="conversational_turn",
                    output=f"From {parent.author}: {parent.body}",
                    created_at=parent.created_at or datetime.now(UTC).isoformat(),
                )
            )

        if isinstance(event.comment, Comment):
            outputs.append(
                ExecutionOutput(
                    stage_name="conversational_turn",
                    output=f"From {event.comment.author}: {event.comment.body}",
                    created_at=event.comment.created_at or datetime.now(UTC).isoformat(),
                )
            )

        return tuple(outputs)

    async def handle_column_change_event(
        self,
        event: WorkItemColumnChangedEvent,
    ) -> None:
        """Handle work item column transitions."""
        work_item_id = event.work_item_id
        project_id = event.project_id
        from_column = event.from_column
        to_column = event.to_column

        if not work_item_id or not project_id:
            message = "WorkItemColumnChangedEvent must have work_item_id and project_id"
            raise ValueError(message)

        logger.info(
            "Handling column change for work item %s: %s → %s",
            work_item_id,
            from_column,
            to_column,
        )

        # Load current session if exists
        session_state = await self.load_session_state(work_item_id)

        # Check if we're exiting a conversational column.
        # Guard: only terminate the session if it belongs to the column we are LEAVING.
        if (
            session_state
            and session_state.status != "terminated"
            and (not from_column or session_state.column_name == from_column)
        ):
            try:
                self.discussion_adapter.stop_monitoring(work_item_id)
            except PortError as e:
                logger.warning(
                    "Failed to stop monitoring for work item %s: %s",
                    work_item_id,
                    str(e),
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_CONVERSATIONAL_SESSION_CLEANUP_FAILURE},
                )
            except Exception as e:
                logger.warning(
                    "UNEXPECTED error stopping monitoring for work item %s: %s",
                    work_item_id,
                    str(e),
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
                )

            now_iso = datetime.now(UTC).isoformat()
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
                    extra={"error_id": ErrorRegistry.ERR_DATABASE_ERROR},
                )
                raise

            logger.info(
                "Terminated conversational session for work item %s",
                work_item_id,
            )

            if self._event_emitter:
                self._event_emitter.emit(
                    FeedbackListeningStoppedEvent(
                        type="feedback_listening.stopped",
                        work_item_id=work_item_id,
                        project_id=project_id,
                        session_id=session_state.session_id,
                        feedback_type="card_advance",
                        timestamp=datetime.now(UTC).isoformat(),
                        source="orchestrator",
                    )
                )

    async def cleanup_loop(
        self,
        work_item_id: str,
        reason: str,
    ) -> None:
        """Clean up loop state on error or manual termination (idempotent)."""
        if not work_item_id:
            message = "work_item_id is required"
            raise ValueError(message)

        logger.info(
            "Cleaning up conversational loop for work item %s, reason: %s",
            work_item_id,
            reason,
        )

        try:
            session_state = await self.load_session_state(work_item_id)

            if not session_state:
                logger.debug(
                    "No active session found for work item %s during cleanup",
                    work_item_id,
                )
                return

            try:
                self.discussion_adapter.stop_monitoring(work_item_id)
            except PortError as e:
                logger.warning(
                    "Failed to stop monitoring during cleanup for work item %s: %s",
                    work_item_id,
                    str(e),
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_CONVERSATIONAL_MONITORING_START_FAILURE},
                )
            except Exception as e:
                logger.warning(
                    "UNEXPECTED error stopping monitoring during cleanup for work item %s: %s",
                    work_item_id,
                    str(e),
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
                )

            if session_state.status != "terminated":
                now_iso = datetime.now(UTC).isoformat()
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
                        extra={"error_id": ErrorRegistry.ERR_DATABASE_ERROR},
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
                extra={"error_id": ErrorRegistry.ERR_HANDLER_EXECUTION},
            )
            raise
        except Exception as e:
            logger.critical(
                "UNEXPECTED error in cleanup handler for work item %s - programming bug: %s",
                work_item_id,
                str(e),
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_HANDLER_EXECUTION},
            )
            raise

    async def load_session_state(
        self,
        work_item_id: str,
    ) -> ConversationalSessionState | None:
        """Load persisted session state from storage."""
        if not work_item_id:
            message = "work_item_id is required"
            raise ValueError(message)

        try:
            snapshot_result = await self.event_store.get_latest_snapshot(work_item_id)

            if snapshot_result:
                if isinstance(snapshot_result, dict):
                    if "data" in snapshot_result and isinstance(snapshot_result["data"], dict):
                        snapshot = snapshot_result["data"]
                    else:
                        snapshot = snapshot_result

                    if "conversational_session_state" in snapshot:
                        return ConversationalSessionState.from_dict(snapshot["conversational_session_state"])

            return None

        except (EventStoreError, ValueError, AttributeError, KeyError, TypeError) as e:
            logger.error(
                "Failed to load session state for work item %s: %s",
                work_item_id,
                str(e),
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_QUERY_ERROR},
            )
            raise
        except Exception as e:
            logger.critical(
                "UNEXPECTED error loading session state for work item %s - programming bug: %s",
                work_item_id,
                str(e),
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
            )
            raise

    async def save_session_state(
        self,
        state: ConversationalSessionState,
    ) -> None:
        """Persist session state to storage."""
        if not state:
            message = "state is required"
            raise ValueError(message)

        try:
            snapshot_data = {
                "conversational_session_state": state.to_dict(),
            }

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
                extra={"error_id": ErrorRegistry.ERR_DATABASE_ERROR},
            )
            raise

    def _build_thread_message(
        self,
        event: CommentNeedsResponseEvent,
        session_state: ConversationalSessionState,
    ) -> str:
        """Build the message to send to the agent based on comment thread context.

        Kept for backwards-compatible use by unit tests that exercise the
        thread-text assembly directly. The production execute() path no
        longer uses this; instead, prior comments flow through
        :meth:`_build_prior_outputs` as ``ExecutionOutput`` entries.
        """
        del session_state  # signature kept for backwards compatibility
        parts: list[str] = []

        if isinstance(event.context, CommentContext) and event.context.parent_comment:
            parent = event.context.parent_comment
            parts.append(f"Previous comment from {parent.author}:")
            parts.append(parent.body)

        if isinstance(event.comment, Comment):
            parts.append(f"\nNew comment from {event.comment.author}:")
            parts.append(event.comment.body)

        return "\n".join(parts)
