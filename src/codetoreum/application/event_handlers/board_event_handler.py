"""Event handler for board column change events.

Subscribes to workitem.column_changed events and orchestrates:
- Pipeline lock acquisition/release based on column type
- Agent execution when work items enter automated columns
- Auto-progression to next column on agent completion
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from codetoreum.application.agent_execution_recovery_service import (
    AgentExecutionRecoveryService,
)
from codetoreum.application.pipeline_lock_service import (
    IQueuedPipelineLockService,
    LockStatus,
)
from codetoreum.domain.board_workflow_template import (
    BoardWorkflowTemplate,
    ColumnTemplate,
    ColumnType,
)
from codetoreum.domain.events import (
    CodetoreumEvent,
    LockStuckEvent,
)
from codetoreum.domain.events.board_events import WorkItemColumnChangedEvent
from codetoreum.domain.events.workflow_events import (
    WorkflowCompletedEvent,
    WorkflowCreatedEvent,
    WorkflowFailedEvent,
    WorkflowStageAdvancedEvent,
    WorkflowStartedEvent,
)
from codetoreum.infrastructure.event_bus import EventBus, EventHandler, event_handler
from codetoreum.ports.exceptions import ExternalServiceError, ResourceNotFoundError
from codetoreum.ports.input.work_item_command import IWorkItemCommandPort, MoveToColumnCommand
from codetoreum.ports.output.active_workflow_run_registry import (
    IActiveWorkflowRunRegistry,
)
from codetoreum.ports.output.agent_executor import IAgentExecutor
from codetoreum.ports.output.board_service import IBoardService, MovedByType, WorkItemPosition
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.event_store import IEventStore
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService

logger = logging.getLogger(__name__)


@dataclass
class _WorkflowRunMetadata:
    """Internal metadata for tracking active workflow runs.

    This is distinct from ActiveRunInfo (port-level value object) and stores
    additional state needed by BoardColumnEventHandler for event sourcing:
    - Timing information (started_at, stage progression)
    - Configuration references (board_id, template_id)

    Private dataclass to keep handler implementation details internal.
    """

    run_id: str
    project_id: str
    board_id: str
    template_id: str
    started_at: datetime
    stage_index: int
    current_column: str = ""


@event_handler("WorkItemColumnChangedEvent")
class BoardColumnEventHandler(EventHandler):
    """Handles workitem.column_changed events for board automation.

    Responds to work item column movements by:
    1. Checking if column is a pipeline trigger (lock acquisition)
    2. Checking if column is an exit column (lock release)
    3. Triggering agent execution if column has an automated agent
    4. Auto-progressing to next column on agent completion

    Example:
        handler = BoardColumnEventHandler(
            board_service=board_service,
            lock_service=lock_service,
            workflow_config=config_service,
            agent_executor=executor,
            event_bus=bus
        )
        bus.register_handler(handler)

        # Now when a WorkItemColumnChangedEvent is published:
        event = WorkItemColumnChangedEvent(
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="Backlog",
            to_column="In Development",
            moved_by="human"
        )
        await bus.publish(event)
        # Handler processes column change, acquires lock, triggers agent if needed
    """

    def __init__(
        self,
        board_service: IBoardService,
        lock_service: IQueuedPipelineLockService,
        workflow_config: IWorkflowConfigService,
        agent_executor: IAgentExecutor,
        event_bus: EventBus,
        event_store: IEventStore | None = None,
        run_registry: IActiveWorkflowRunRegistry | None = None,
        event_emitter: IEventEmitter | None = None,
        recovery_service: AgentExecutionRecoveryService | None = None,
        work_item_service: IWorkItemCommandPort | None = None,
    ):
        """
        Initialize board column event handler.

        Args:
            board_service: Board service for querying positions and moving items
            lock_service: Pipeline lock service for exclusive access coordination
            workflow_config: Configuration service for workflow templates
            agent_executor: Service for triggering agent executions
            event_bus: Event bus for publishing domain events
            event_store: Optional event store for persisting workflow lifecycle events
            run_registry: Optional registry for tracking active workflow runs
            event_emitter: Optional event emitter for CodetoreumEvent instances (e.g. LockStuckEvent)
            recovery_service: Optional recovery service for handling agent execution failures
            work_item_service: Optional command port for persisting work item column state
        """
        self.board_service = board_service
        self.lock_service = lock_service
        self.workflow_config = workflow_config
        self.agent_executor = agent_executor
        self.event_bus = event_bus
        self.event_store = event_store
        self.run_registry = run_registry
        self.event_emitter = event_emitter
        self.recovery_service = recovery_service
        self.work_item_service = work_item_service
        # Tracks active workflow runs: work_item_id -> _WorkflowRunMetadata
        # Provides compile-time key validation and type safety over untyped dict[str, Any]
        self._active_runs: dict[str, _WorkflowRunMetadata] = {}

    def get_event_types(self) -> list[str]:
        """Get list of event types this handler processes.

        Returns:
            List of event type names
        """
        return ["WorkItemColumnChangedEvent"]

    async def handle(self, event: CodetoreumEvent) -> None:
        """
        Handle column change event and trigger appropriate workflow actions.

        Args:
            event: Domain event to handle

        Raises:
            Exception: If handling fails
        """
        if not isinstance(event, WorkItemColumnChangedEvent):
            logger.warning(f"BoardColumnEventHandler received unexpected event type: {event.event_type}")
            return

        try:
            await self.handle_column_change(event)
        except Exception as e:
            work_item_id = event.work_item_id
            logger.error(
                f"Error handling column change for {work_item_id}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_BOARD_EVENT_HANDLE_COLUMN_CHANGE_FAILURE"},
            )
            raise

    async def handle_column_change(self, event: WorkItemColumnChangedEvent) -> None:
        """
        Process column movement and trigger appropriate actions.

        Workflow:
        1. Retrieve workflow configuration for the board
        2. Get column configuration for the target column
        3. If pipeline trigger column: try to acquire lock (returns after handling)
            - If acquired: trigger agent if configured
            - If queued: emit WorkItemQueued event
        4. If exit column: release lock and grant to next in queue (independent of step 3)
        5. If automated column: trigger agent (independent of steps 3 and 4)

        Args:
            event: WorkItemColumnChangedEvent with column movement details
        """
        # Required fields are guaranteed non-empty by WorkItemColumnChangedEvent.__post_init__
        work_item_id: str = event.work_item_id
        board_id: str = event.board_id
        project_id: str = event.project_id
        from_column: str = event.from_column or ""
        to_column: str = event.to_column

        logger.info(f"Processing column change for {work_item_id}: {from_column} -> {to_column}")

        # Persist the new column on the work item so API queries reflect current state
        if self.work_item_service is not None:
            try:
                await self.work_item_service.move_to_column(MoveToColumnCommand(work_item_id, to_column))
            except Exception:
                logger.warning(
                    "Failed to persist column update for work item %s to '%s'",
                    work_item_id,
                    to_column,
                    exc_info=True,
                )

        # Get workflow configuration for this board
        config = await self.workflow_config.get_board_workflow_template(board_id)

        if not config:
            logger.warning(f"No workflow config found for board {board_id}, skipping automation")
            return

        column_config = config.get_column_config(to_column)

        if not column_config:
            logger.warning(f"Unknown column '{to_column}' in board {board_id}, skipping automation")
            return

        # Check if this is a pipeline trigger column (requires lock)
        if column_config.is_pipeline_trigger:
            await self._handle_pipeline_trigger(work_item_id, project_id, board_id, column_config, config)
            # Continue to check for other column types (don't return here)
        else:
            # Check if this is an exit column (releases lock)
            if column_config.is_exit_column:
                await self._handle_exit_column(work_item_id, project_id, board_id, column_config, config)

            # Trigger agent if column has one, is automated, NOT a repair cycle column,
            # NOT a PR review cycle column, and NOT a conversational column. Repair cycle columns
            # and PR review cycle columns are driven by their respective handlers; conversational
            # columns are driven by WorkflowOrchestrator via ConversationalLoopOrchestrator.
            # Dispatching the agent executor here for these types would cause double-dispatch
            # race conditions or immediate execution failure.
            if (
                column_config.agent_id
                and column_config.type == ColumnType.AUTOMATED
                and not column_config.repair_cycle_agents
                and not column_config.pr_review_cycle_config
                and getattr(column_config, "execution_type", "task_queue") != "conversational"
            ):
                # Start workflow run lifecycle tracking before triggering the agent.
                # This is normally done in _handle_pipeline_trigger (which acquires the lock
                # first), but when an automated column is triggered directly (bypassing the
                # pipeline trigger column), the active run must still be registered so the
                # executor's run_registry.get_active_run() succeeds.
                if work_item_id not in self._active_runs:
                    await self._start_workflow_run(work_item_id, project_id, board_id, column_config, config)
                await self._trigger_agent(work_item_id, column_config, board_id)

    async def _handle_pipeline_trigger(
        self,
        work_item_id: str,
        project_id: str,
        board_id: str,
        column_config: ColumnTemplate,
        workflow_config: BoardWorkflowTemplate,
    ) -> None:
        """
        Handle work item entering pipeline trigger column.

        Attempts to acquire pipeline lock. If successful, triggers agent immediately.
        If lock is held, queues work item and emits WorkItemQueued event.

        Args:
            work_item_id: ID of work item entering trigger column
            project_id: ID of project containing the board
            board_id: ID of board
            column_config: Configuration of the trigger column
            workflow_config: Full workflow template for the board
        """
        # Get item position for queue ordering with error handling
        try:
            position = await self._find_item_position(board_id, work_item_id, workflow_config)
            if position is None:
                raise ResourceNotFoundError("work_item", work_item_id)
        except ResourceNotFoundError:
            logger.error(
                f"Cannot acquire lock for {work_item_id}: work item not found on board",
                exc_info=True,
                extra={
                    "error_id": "ERR_BOARD_EVENT_ITEM_NOT_FOUND",
                    "work_item_id": work_item_id,
                    "board_id": board_id,
                },
            )
            # TODO: Emit WorkItemNotFoundEvent
            return
        except ExternalServiceError as e:
            logger.error(
                f"Board service error while getting position for {work_item_id}: {e}",
                exc_info=True,
                extra={
                    "error_id": "ERR_BOARD_EVENT_BOARD_SERVICE_ERROR",
                    "work_item_id": work_item_id,
                    "board_id": board_id,
                },
            )
            # Could retry or emit error event
            return

        # Try acquire lock with error handling
        try:
            result = await self.lock_service.try_acquire_lock(
                project_id=project_id,
                board_id=board_id,
                work_item_id=work_item_id,
                board_position=position.position,
            )
        except ValueError as e:
            # Invalid parameters (negative position, empty IDs)
            logger.error(
                f"Invalid parameters for lock acquisition on {work_item_id}: {e}",
                exc_info=True,
                extra={
                    "error_id": "ERR_BOARD_EVENT_INVALID_LOCK_PARAMS",
                    "work_item_id": work_item_id,
                    "board_id": board_id,
                    "position": position.position,
                },
            )
            return
        except Exception as e:
            logger.error(
                f"Lock service failed for {work_item_id}: {e}",
                exc_info=True,
                extra={
                    "error_id": "ERR_BOARD_EVENT_LOCK_ACQUISITION_FAILURE",
                    "work_item_id": work_item_id,
                    "board_id": board_id,
                    "project_id": project_id,
                },
            )
            # TODO: Emit LockAcquisitionFailedEvent
            return

        if result.status == LockStatus.ACQUIRED:
            logger.info(f"Lock acquired for {work_item_id}")

            # Start workflow run lifecycle tracking
            await self._start_workflow_run(work_item_id, project_id, board_id, column_config, workflow_config)

            # Trigger agent if column has one, is NOT a conversational column, and is NOT a PR review cycle column.
            # Conversational columns are handled by WorkflowOrchestrator via
            # ConversationalLoopOrchestrator — dispatching the executor here would
            # cause a double-dispatch failure. PR review cycle columns are driven by
            # PRReviewCycleDispatchHandler; dispatching here would cause double-dispatch.
            if (
                column_config.agent_id
                and getattr(column_config, "execution_type", "task_queue") != "conversational"
                and not column_config.pr_review_cycle_config
            ):
                await self._trigger_agent(work_item_id, column_config, board_id)

        elif result.status == LockStatus.QUEUED:
            logger.info(
                f"Lock held, {work_item_id} queued at position {result.queue_position} "
                f"(queue length: {result.queue_length})"
            )

        elif result.status == LockStatus.ALREADY_HELD:
            logger.info(
                f"{work_item_id} re-entering pipeline trigger column (already holds lock). "
                f"Re-triggering agent if configured."
            )
            # Even though the lock is already held, we should still trigger the agent
            # when re-entering the column (e.g., after reviewer rejection in maker-checker flow).
            # Skip conversational columns — handled by WorkflowOrchestrator via CLO.
            # Skip PR review cycle columns — driven by PRReviewCycleDispatchHandler.
            if (
                column_config.agent_id
                and getattr(column_config, "execution_type", "task_queue") != "conversational"
                and not column_config.pr_review_cycle_config
            ):
                await self._trigger_agent(work_item_id, column_config, board_id)

    async def _handle_exit_column(
        self,
        work_item_id: str,
        project_id: str,
        board_id: str,
        column_config: ColumnTemplate,
        workflow_config: BoardWorkflowTemplate,
    ) -> None:
        """
        Handle work item entering exit column (releases pipeline lock).

        Releases the lock held by this work item and grants it to the next
        queued work item. If next work item has an agent assigned, triggers
        its execution.

        Args:
            work_item_id: ID of work item entering exit column
            project_id: ID of project containing the board
            board_id: ID of board
            column_config: Configuration of the exit column
            workflow_config: Full workflow template for the board
        """
        # Release lock with error handling
        try:
            release_result = await self.lock_service.release_lock(
                project_id=project_id,
                board_id=board_id,
                work_item_id=work_item_id,
            )
        except ValueError as e:
            # Work item doesn't hold lock (race condition or already released)
            logger.warning(
                f"Cannot release lock for {work_item_id}: {e}",
                exc_info=True,
                extra={
                    "error_id": "ERR_BOARD_EVENT_LOCK_NOT_HELD",
                    "work_item_id": work_item_id,
                    "board_id": board_id,
                },
            )
            return
        except Exception as e:
            logger.critical(
                f"Lock service failed to release lock for {work_item_id}: {e}",
                exc_info=True,
                extra={
                    "error_id": "ERR_BOARD_EVENT_LOCK_RELEASE_CRITICAL_FAILURE",
                    "work_item_id": work_item_id,
                    "board_id": board_id,
                },
            )
            # CRITICAL: Lock cannot be released — emit LockStuckEvent for manual intervention.
            # LockStuckEvent is a CodetoreumEvent; emit via IEventEmitter (not EventBus,
            # which requires CodetoreumEvent with aggregate_id/aggregate_type/occurred_at fields).
            if self.event_emitter:
                try:
                    self.event_emitter.emit(
                        LockStuckEvent(
                            type="lock.stuck",
                            timestamp=datetime.now(UTC).isoformat(),
                            source="board_event_handler",
                            project_id=project_id,
                            board_id=board_id,
                            work_item_id=work_item_id,
                            reason=str(e),
                        )
                    )
                except Exception as emit_err:
                    logger.error(
                        f"Failed to emit LockStuckEvent for '{work_item_id}': {emit_err}",
                        exc_info=True,
                        extra={"error_id": "ERR_BOARD_EVENT_LOCK_STUCK_EMIT_FAILURE"},
                    )
            else:
                logger.warning(
                    f"LockStuckEvent not emitted for '{work_item_id}': "
                    "no event_emitter configured on BoardColumnEventHandler",
                    extra={"work_item_id": work_item_id},
                )
            return

        logger.info(f"Lock released for {work_item_id}, next work item: {release_result.next_work_item_id}")

        # Complete workflow run lifecycle tracking
        await self._complete_workflow_run(work_item_id, column_config.name)

        # Trigger agent for next queued item if one exists
        if release_result.next_work_item_id:
            try:
                next_position = await self._find_item_position(
                    board_id, release_result.next_work_item_id, workflow_config
                )
                next_column_config = (
                    workflow_config.get_column_config(next_position.column_name) if next_position else None
                )

                if next_column_config and next_column_config.agent_id:
                    logger.info(f"Triggering agent for next queued item: {release_result.next_work_item_id}")
                    await self._trigger_agent(release_result.next_work_item_id, next_column_config, board_id)
            except ResourceNotFoundError as e:
                logger.warning(
                    f"Next queued item {release_result.next_work_item_id} not found: {e}",
                    exc_info=True,
                    extra={
                        "error_id": "ERR_BOARD_EVENT_NEXT_ITEM_NOT_FOUND",
                        "work_item_id": release_result.next_work_item_id,
                    },
                )
                # Item was deleted - OK, lock is released
            except Exception as e:
                logger.error(
                    f"Failed to trigger next item {release_result.next_work_item_id}: {e}",
                    exc_info=True,
                    extra={
                        "error_id": "ERR_BOARD_EVENT_NEXT_AGENT_TRIGGER_FAILURE",
                        "work_item_id": release_result.next_work_item_id,
                    },
                )
                # Next item holds lock but agent never triggered — emit event for observability.
                # LockStuckEvent is a CodetoreumEvent; emit via IEventEmitter (not EventBus,
                # which requires CodetoreumEvent with aggregate_id/aggregate_type/occurred_at fields).
                if self.event_emitter:
                    try:
                        self.event_emitter.emit(
                            LockStuckEvent(
                                type="lock.stuck",
                                timestamp=datetime.now(UTC).isoformat(),
                                source="board_event_handler",
                                project_id=project_id,
                                board_id=board_id,
                                work_item_id=release_result.next_work_item_id,
                                reason=str(e),
                            )
                        )
                    except Exception as emit_err:
                        logger.error(
                            f"Failed to emit LockStuckEvent for '{release_result.next_work_item_id}': {emit_err}",
                            exc_info=True,
                            extra={"error_id": "ERR_BOARD_EVENT_LOCK_STUCK_EMIT_FAILURE"},
                        )
                else:
                    logger.warning(
                        f"LockStuckEvent not emitted for '{release_result.next_work_item_id}': "
                        "no event_emitter configured on BoardColumnEventHandler",
                        extra={"work_item_id": release_result.next_work_item_id},
                    )

    # ========================================================================
    # Workflow Run Lifecycle Tracking
    # ========================================================================

    async def _start_workflow_run(
        self,
        work_item_id: str,
        project_id: str,
        board_id: str,
        column_config: ColumnTemplate,
        workflow_config: BoardWorkflowTemplate,
    ) -> None:
        """Persist WorkflowCreated + WorkflowStarted events when pipeline begins."""
        if not self.event_store:
            return

        workflow_run_id = str(uuid4())
        now = datetime.now(UTC)

        self._active_runs[work_item_id] = _WorkflowRunMetadata(
            run_id=workflow_run_id,
            project_id=project_id,
            board_id=board_id,
            template_id=workflow_config.id,
            started_at=now,
            stage_index=0,
            current_column=column_config.name,
        )

        created = WorkflowCreatedEvent(
            type="workflow.created",
            timestamp=now.isoformat(),
            source="board_event_handler",
            workflow_id=workflow_run_id,
            work_item_id=work_item_id,
            pipeline_id=workflow_config.id,
            stage_name=column_config.name,
            project_id=project_id,
        )
        started = WorkflowStartedEvent(
            type="workflow.started",
            timestamp=now.isoformat(),
            source="board_event_handler",
            workflow_id=workflow_run_id,
            work_item_id=work_item_id,
            stage_name=column_config.name,
        )
        try:
            await self.event_store.append(workflow_run_id, [created, started])
            logger.info(
                f"Starting workflow run {workflow_run_id} for {work_item_id}: "
                f"stage={column_config.name}, template_id={workflow_config.id}, "
                f"agent_id={column_config.agent_id or 'none'}, "
                f"board_id={board_id}",
                extra={
                    "workflow_run_id": workflow_run_id,
                    "work_item_id": work_item_id,
                    "stage_name": column_config.name,
                    "template_id": workflow_config.id,
                    "agent_id": column_config.agent_id or "none",
                    "board_id": board_id,
                    "project_id": project_id,
                },
            )
        except Exception as e:
            logger.error(
                f"Failed to persist workflow run start for {work_item_id}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_BOARD_EVENT_WORKFLOW_RUN_START_FAILURE"},
            )

        # Also register in active run registry if available
        if self.run_registry:
            try:
                await self.run_registry.set_active_run(
                    work_item_id=work_item_id,
                    run_id=workflow_run_id,
                    stage_name=column_config.name,
                    project_id=project_id,
                    board_id=board_id,
                )
            except Exception as e:
                logger.error(
                    f"Failed to register active run for {work_item_id}: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_BOARD_EVENT_RUN_REGISTRY_FAILURE"},
                )

    async def _advance_workflow_stage(
        self,
        work_item_id: str,
        from_stage: str,
        to_stage: str,
    ) -> None:
        """Persist WorkflowStageAdvanced event on auto-progression."""
        if not self.event_store or work_item_id not in self._active_runs:
            return

        run_info = self._active_runs[work_item_id]
        run_info.stage_index += 1
        workflow_run_id = run_info.run_id

        event = WorkflowStageAdvancedEvent(
            type="workflow.stage_advanced",
            timestamp=datetime.now(UTC).isoformat(),
            source="board_event_handler",
            workflow_id=workflow_run_id,
            work_item_id=work_item_id,
            from_stage=from_stage,
            to_stage=to_stage,
        )
        try:
            await self.event_store.append(workflow_run_id, [event])
        except Exception as e:
            logger.error(
                f"Failed to persist stage advance for {work_item_id}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_BOARD_EVENT_WORKFLOW_STAGE_ADVANCE_FAILURE"},
            )

    async def _complete_workflow_run(
        self,
        work_item_id: str,
        exit_column: str,
    ) -> None:
        """Persist WorkflowCompleted event when pipeline reaches exit column."""
        if not self.event_store or work_item_id not in self._active_runs:
            return

        run_info = self._active_runs.pop(work_item_id)
        workflow_run_id = run_info.run_id
        now = datetime.now(UTC)
        duration = (now - run_info.started_at).total_seconds()

        event = WorkflowCompletedEvent(
            type="workflow.completed",
            timestamp=now.isoformat(),
            source="board_event_handler",
            workflow_id=workflow_run_id,
            work_item_id=work_item_id,
            final_stage=exit_column,
            completed_at=now.isoformat(),
        )
        try:
            await self.event_store.append(workflow_run_id, [event])
            logger.debug(f"Workflow run {workflow_run_id} completed for {work_item_id} ({duration:.1f}s)")
        except Exception as e:
            logger.error(
                f"Failed to persist workflow run completion for {work_item_id}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_BOARD_EVENT_WORKFLOW_RUN_COMPLETE_FAILURE"},
            )

    async def _fail_workflow_run(
        self,
        work_item_id: str,
        reason: str,
    ) -> None:
        """Persist WorkflowFailed event on agent failure."""
        if not self.event_store or work_item_id not in self._active_runs:
            return

        run_info = self._active_runs.pop(work_item_id)
        workflow_run_id = run_info.run_id
        now = datetime.now(UTC)

        event = WorkflowFailedEvent(
            type="workflow.failed",
            timestamp=now.isoformat(),
            source="board_event_handler",
            workflow_id=workflow_run_id,
            work_item_id=work_item_id,
            failed_stage="",
            reason=reason,
            failed_at=now.isoformat(),
        )
        try:
            await self.event_store.append(workflow_run_id, [event])
            logger.debug(f"Workflow run {workflow_run_id} failed for {work_item_id}: {reason}")
        except Exception as e:
            logger.error(
                f"Failed to persist workflow run failure for {work_item_id}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_BOARD_EVENT_WORKFLOW_RUN_FAIL_FAILURE"},
            )

    async def _trigger_agent(self, work_item_id: str, column_config: ColumnTemplate, board_id: str = "board-1") -> None:
        """
        Trigger agent execution for a work item with failure recovery.

        Execution flow:
        1. Update registry with current stage
        2. Execute agent (fire-and-forget)
        3. If execution fails before task creation:
           - Log the failure with context
           - Use recovery service to fail workflow run
           - Release the pipeline lock to unblock next queued item
           - Emit alert for manual intervention

        Args:
            work_item_id: ID of work item to process
            column_config: Column configuration with agent assignment
            board_id: ID of the board containing the work item (default: "board-1")

        Raises:
            Exception: Logs error but doesn't re-raise to prevent event
                      handler failures from stopping other handlers
        """
        if not column_config.agent_id:
            logger.warning(f"Column {column_config.name} has no agent assigned")
            return

        logger.info(f"Triggering agent '{column_config.agent_id}' for {work_item_id}")

        # Update registry with current stage (so executor knows which stage is active)
        if self.run_registry and work_item_id in self._active_runs:
            run_info = self._active_runs[work_item_id]
            try:
                await self.run_registry.set_active_run(
                    work_item_id=work_item_id,
                    run_id=run_info.run_id,
                    stage_name=column_config.name,
                    project_id=run_info.project_id,
                    board_id=run_info.board_id,
                )
            except Exception as e:
                logger.error(
                    f"Failed to update active run registry for {work_item_id}: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_BOARD_EVENT_RUN_REGISTRY_UPDATE_FAILURE"},
                )
                return

        try:
            await self.agent_executor.execute(
                work_item_id=work_item_id, agent_id=column_config.agent_id, board_id=board_id
            )
        except Exception as e:
            logger.error(
                f"Agent execution failed for {work_item_id}: {e}",
                exc_info=True,
                extra={
                    "error_id": "ERR_BOARD_EVENT_AGENT_EXECUTION_FAILURE",
                    "work_item_id": work_item_id,
                },
            )

            # Handle synchronous execution failure (before task creation, lock still held)
            if work_item_id in self._active_runs:
                run_info = self._active_runs[work_item_id]
                project_id = run_info.project_id

                # Use recovery service to fail workflow run (wrapped in try/except to ensure
                # lock release is not skipped even if recovery service fails)
                if self.recovery_service:
                    try:
                        await self.recovery_service.handle_agent_execution_failure(
                            work_item_id=work_item_id,
                            board_id=board_id,
                            error=e,
                            project_id=project_id,
                        )
                    except Exception as recovery_err:
                        logger.error(
                            f"Recovery service failed for {work_item_id}: {recovery_err}",
                            exc_info=True,
                            extra={
                                "error_id": "ERR_BOARD_EVENT_RECOVERY_SERVICE_FAILURE",
                                "work_item_id": work_item_id,
                            },
                        )
                        # Continue to lock release (lock release must not be skipped)

                # Release the lock to unblock next queued item (critical for pipeline unblocking)
                try:
                    release_result = await self.lock_service.release_lock(
                        project_id=project_id,
                        board_id=board_id,
                        work_item_id=work_item_id,
                    )
                    logger.info(
                        f"Released lock for {work_item_id} due to execution failure, "
                        f"next item: {release_result.next_work_item_id}",
                        extra={"error_id": "INFO_BOARD_EVENT_LOCK_RELEASED_AFTER_FAILURE"},
                    )
                except ValueError as lock_err:
                    logger.warning(
                        f"Cannot release lock for {work_item_id}: {lock_err} " f"(may have already released)",
                        exc_info=True,
                        extra={"error_id": "ERR_BOARD_EVENT_LOCK_RELEASE_NOT_HELD"},
                    )
                except Exception as lock_err:
                    logger.critical(
                        f"Failed to release lock for {work_item_id} after execution failure: {lock_err} "
                        f"— PIPELINE IS BLOCKED",
                        exc_info=True,
                        extra={
                            "error_id": "ERR_BOARD_EVENT_LOCK_RELEASE_CRITICAL_FAILURE",
                            "work_item_id": work_item_id,
                        },
                    )
                    # Emit LockStuckEvent for manual intervention
                    if self.event_emitter:
                        try:
                            self.event_emitter.emit(
                                LockStuckEvent(
                                    type="lock.stuck",
                                    timestamp=datetime.now(UTC).isoformat(),
                                    source="board_event_handler._trigger_agent",
                                    project_id=project_id,
                                    board_id=board_id,
                                    work_item_id=work_item_id,
                                    reason=f"Failed to release lock after execution failure: {lock_err}",
                                )
                            )
                        except Exception as emit_err:
                            logger.error(
                                f"Failed to emit LockStuckEvent for '{work_item_id}': {emit_err}",
                                exc_info=True,
                                extra={"error_id": "ERR_BOARD_EVENT_LOCK_STUCK_EMIT_FAILURE"},
                            )

    async def handle_agent_completion(
        self,
        work_item_id: str,
        board_id: str,
        success: bool,
    ) -> None:
        """
        Handle agent completion and auto-progression to next column.

        If agent completed successfully and column has auto_progress_on_completion
        enabled, automatically moves work item to next column in workflow.

        Args:
            work_item_id: ID of work item that agent processed
            board_id: ID of board containing work item
            success: Whether agent execution succeeded

        Raises:
            Exception: Re-raised after logging if auto-progression fails
        """
        if not success:
            logger.warning(f"Agent failed for {work_item_id}, skipping auto-progression")
            try:
                config = await self.workflow_config.get_board_workflow_template(board_id)
                if config:
                    current_position = await self._find_item_position(board_id, work_item_id, config)
                    column_config = config.get_column_config(current_position.column_name) if current_position else None
                    if column_config and column_config.on_failure_column:
                        await self.board_service.move_item_to_column(
                            work_item_id, column_config.on_failure_column, MovedByType.ORCHESTRATOR
                        )
                        logger.info(f"Moved {work_item_id} to failure column '{column_config.on_failure_column}'")
            except Exception as e:
                logger.error(
                    f"Failed to move {work_item_id} to failure column: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_BOARD_EVENT_FAILURE_COLUMN_MOVE"},
                )
            await self._fail_workflow_run(work_item_id, "Agent execution failed")
            return

        try:
            config = await self.workflow_config.get_board_workflow_template(board_id)
            if not config:
                logger.warning(f"No workflow config for board {board_id}, skipping auto-progression")
                return

            current_position = await self._find_item_position(board_id, work_item_id, config)
            if not current_position and work_item_id in self._active_runs:
                # Board service couldn't locate the item (e.g. externally-triggered work item
                # not yet visible to the board adapter). Fall back to our own tracking.
                tracked_column = self._active_runs[work_item_id].current_column
                if tracked_column:
                    current_position = WorkItemPosition(
                        work_item_id=work_item_id,
                        column_name=tracked_column,
                        position=0,
                    )
            if not current_position:
                logger.warning(
                    f"Work item {work_item_id} not found in any column on board {board_id}, skipping auto-progression"
                )
                return
            current_column_config = config.get_column_config(current_position.column_name)

            if not current_column_config:
                logger.warning(f"Current column '{current_position.column_name}' not found in config")
                return

            if not current_column_config.auto_progress_on_completion:
                logger.info(f"Auto-progression disabled for {current_position.column_name}")
                return

            next_column_name = config.get_next_column(current_position.column_name)
            if not next_column_name:
                logger.info(f"No next column for {current_position.column_name}, workflow complete")
                return

            logger.info(f"Auto-progressing {work_item_id} from {current_position.column_name} to {next_column_name}")

            await self._advance_workflow_stage(work_item_id, current_position.column_name, next_column_name)

            await self.board_service.move_item_to_column(work_item_id, next_column_name, MovedByType.ORCHESTRATOR)

        except Exception as e:
            logger.error(
                f"Error during auto-progression for {work_item_id}: {e}",
                exc_info=True,
                extra={
                    "error_id": "ERR_BOARD_EVENT_AUTO_PROGRESSION_FAILURE",
                    "work_item_id": work_item_id,
                },
            )
            raise

    async def _find_item_position(
        self,
        board_id: str,
        work_item_id: str,
        config: BoardWorkflowTemplate,
    ) -> WorkItemPosition | None:
        """Find a work item's current board position.

        Tries get_item_position() first (O(1) for most adapters). Falls back to
        scanning all columns via get_items_in_column() for adapters that require
        explicit board context (e.g. GitHubBoardAdapter with GitHub Projects v2).
        """
        try:
            return await self.board_service.get_item_position(work_item_id)
        except ResourceNotFoundError:
            return None
        except ValueError as e:
            if "board context" not in str(e):
                raise
            # Adapter requires board context — scan columns instead
        except NotImplementedError:
            pass

        for column in config.columns:
            try:
                items = await self.board_service.get_items_in_column(board_id, column.name)
                for item in items:
                    if item.work_item_id == work_item_id:
                        return item
            except Exception as e:
                logger.debug(f"Error scanning column '{column.name}' for {work_item_id}: {e}")
        return None
