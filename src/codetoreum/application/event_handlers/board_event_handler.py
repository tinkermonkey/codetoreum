"""Event handler for board column change events.

Subscribes to workitem.column_changed events and orchestrates:
- Pipeline lock acquisition/release based on column type
- Agent execution when work items enter automated columns
- Auto-progression to next column on agent completion
"""

import logging
from datetime import UTC, datetime
from uuid import uuid4

from codetoreum.application.agent_execution_recovery_service import (
    AgentExecutionRecoveryService,
)
from codetoreum.application.pipeline_lock_service import IPipelineLockService
from codetoreum.domain.board_workflow_template import (
    BoardWorkflowTemplate,
    ColumnTemplate,
    ColumnType,
)
from codetoreum.domain.events import (
    AgentExecutionCompletedEvent,
    CodetoreumEvent,
    LockStuckEvent,
)
from codetoreum.domain.events.board_events import BoardSyncFailedEvent, WorkItemColumnChangedEvent
from codetoreum.domain.events.workflow_events import (
    WorkflowCompletedEvent,
    WorkflowCreatedEvent,
    WorkflowFailedEvent,
    WorkflowStageAdvancedEvent,
    WorkflowStartedEvent,
)
from codetoreum.infrastructure.event_bus import EventBus, EventHandler, event_handler
from codetoreum.ports.exceptions import ExternalServiceError, ResourceNotFoundError
from codetoreum.ports.input.work_item_command import IWorkItemCommandPort
from codetoreum.ports.output.active_workflow_run_registry import (
    IActiveWorkflowRunRegistry,
)
from codetoreum.ports.output.agent_executor import IAgentExecutor
from codetoreum.ports.output.board_service import IBoardService, MovedByType, WorkItemPosition
from codetoreum.ports.output.distributed_lock import (
    IDistributedLock,
)
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.event_store import IEventStore
from codetoreum.ports.output.pipeline_queue import (
    IPipelineQueue,
    QueueEntry,
)
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService

logger = logging.getLogger(__name__)


@event_handler("WorkItemColumnChangedEvent", "AgentExecutionCompletedEvent")
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
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            workflow_config=config_service,
            agent_executor=executor,
            event_bus=bus,
            work_item_service=work_item_service,
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
        workflow_config: IWorkflowConfigService,
        agent_executor: IAgentExecutor,
        event_bus: EventBus,
        work_item_service: IWorkItemCommandPort,
        lock_service: IPipelineLockService | None = None,
        distributed_lock: IDistributedLock | None = None,
        pipeline_queue: IPipelineQueue | None = None,
        event_store: IEventStore | None = None,
        run_registry: IActiveWorkflowRunRegistry | None = None,
        event_emitter: IEventEmitter | None = None,
        recovery_service: AgentExecutionRecoveryService | None = None,
    ):
        """
        Initialize board column event handler.

        Args:
            board_service: Board service for querying positions and moving items
            workflow_config: Configuration service for workflow templates
            agent_executor: Service for triggering agent executions
            event_bus: Event bus for publishing domain events
            work_item_service: Command port for persisting work item column state
            lock_service: Optional unified pipeline lock service (preferred if provided)
            distributed_lock: Optional distributed lock (used if lock_service not provided)
            pipeline_queue: Optional pipeline queue (used if lock_service not provided)
            event_store: Optional event store for persisting workflow lifecycle events
            run_registry: Optional registry for tracking active workflow runs
            event_emitter: Optional event emitter for CodetoreumEvent instances (e.g. LockStuckEvent)
            recovery_service: Optional recovery service for handling agent execution failures
        """
        self.board_service = board_service
        self.lock_service = lock_service
        self.distributed_lock = distributed_lock
        self.pipeline_queue = pipeline_queue
        self.workflow_config = workflow_config
        self.agent_executor = agent_executor
        self.event_bus = event_bus
        self.event_store = event_store
        self.run_registry = run_registry
        self.event_emitter = event_emitter
        self.recovery_service = recovery_service
        self.work_item_service = work_item_service

        # Validate that either lock_service or both distributed_lock and pipeline_queue are provided
        if lock_service is None and (distributed_lock is None or pipeline_queue is None):
            raise ValueError(
                "Either lock_service or both distributed_lock and pipeline_queue must be provided"
            )

    def get_event_types(self) -> list[str]:
        """Get list of event types this handler processes.

        Returns:
            List of event type names
        """
        return ["WorkItemColumnChangedEvent", "AgentExecutionCompletedEvent"]

    async def handle(self, event: CodetoreumEvent) -> None:
        """
        Handle a domain event and trigger appropriate workflow actions.

        Dispatches by concrete event type:
        - WorkItemColumnChangedEvent → column-movement automation
          (lock acquisition, agent dispatch, exit handling).
        - AgentExecutionCompletedEvent → auto-progression to the next
          column once the agent executor publishes completion.

        Args:
            event: Domain event to handle

        Raises:
            Exception: If handling fails
        """
        if isinstance(event, WorkItemColumnChangedEvent):
            try:
                await self.handle_column_change(event)
            except Exception as e:
                logger.error(
                    f"Error handling column change for {event.work_item_id}: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_BOARD_EVENT_HANDLE_COLUMN_CHANGE_FAILURE"},
                )
                raise
            return

        if isinstance(event, AgentExecutionCompletedEvent):
            try:
                await self.handle_agent_execution_completed(event)
            except Exception as e:
                logger.error(
                    f"Error handling agent execution completion for {event.work_item_id}: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_BOARD_EVENT_HANDLE_AGENT_COMPLETION_FAILURE"},
                )
                raise
            return

        logger.warning(f"BoardColumnEventHandler received unexpected event type: {event.event_type}")

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
                existing_run = None
                if self.run_registry:
                    try:
                        existing_run = await self.run_registry.get_active_run(work_item_id)
                    except Exception:
                        logger.debug(f"Failed to check existing run for {work_item_id}")

                if existing_run is None:
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
            position = await self._find_item_position(board_id, work_item_id, workflow_config, project_id=project_id)
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

        # Try to acquire lock
        lock_key = f"{project_id}:{board_id}"

        try:
            if self.lock_service:
                # Use unified lock service API
                result = await self.lock_service.try_acquire_lock(
                    project_id=project_id,
                    board_id=board_id,
                    work_item_id=work_item_id,
                    board_position=position.position,
                )
                queue_length = result.queue_length
            else:
                # Use separate lock and queue APIs
                queue_entry = QueueEntry(
                    work_item_id=work_item_id,
                    stage_name=column_config.name,
                    board_position=position.position,
                    enqueued_at=datetime.now(UTC),
                    metadata={"project_id": project_id, "board_id": board_id},
                )
                await self.pipeline_queue.enqueue(queue_key=lock_key, entry=queue_entry)
                queue_length = await self.pipeline_queue.length(lock_key)

                lock_result = await self.distributed_lock.try_acquire(
                    lock_key=lock_key,
                    holder_id=work_item_id,
                    ttl_seconds=7200,
                    holder_metadata={
                        "project_id": project_id,
                        "board_id": board_id,
                        "queue_length_at_acquire": str(queue_length),
                    },
                )
                # Adapt old API result to match new API
                from codetoreum.application.pipeline_lock_service import (
                    LockAcquisitionResult,
                    LockStatus,
                )

                if lock_result.status.value == "acquired":
                    result = LockAcquisitionResult(
                        status=LockStatus.ACQUIRED,
                        work_item_id=work_item_id,
                        queue_length=queue_length,
                    )
                elif lock_result.status.value == "already_held_by_self":
                    result = LockAcquisitionResult(
                        status=LockStatus.ALREADY_HELD,
                        work_item_id=work_item_id,
                        queue_length=queue_length,
                    )
                else:
                    result = LockAcquisitionResult(
                        status=LockStatus.QUEUED,
                        work_item_id=work_item_id,
                        queue_position=0,
                        queue_length=queue_length,
                    )
        except Exception as e:
            logger.error(
                f"Lock acquisition failed for {work_item_id}: {e}",
                exc_info=True,
            )
            return

        # Check if lock was acquired or re-entered (ALREADY_HELD means work item holds lock and re-entered column)
        if result.status.name in ("ACQUIRED", "ALREADY_HELD"):
            status_msg = "Lock acquired" if result.status.name == "ACQUIRED" else "Lock already held (re-entry)"
            logger.info(f"{status_msg} for {work_item_id}")

            # Start workflow run lifecycle tracking (only on first acquisition)
            if result.status.name == "ACQUIRED":
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

        elif result.status.value == "already_held_by_other":
            logger.info(f"Lock held by {result.holder_id}, {work_item_id} queued")

        elif result.status.value == "already_held_by_self":
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
                # Check if workflow run is already registered
                existing_run = None
                if self.run_registry:
                    try:
                        existing_run = await self.run_registry.get_active_run(work_item_id)
                    except Exception:
                        logger.debug(f"Failed to check existing run for {work_item_id}")

                if existing_run is None:
                    await self._start_workflow_run(
                        work_item_id,
                        project_id,
                        board_id,
                        column_config,
                        workflow_config,
                    )
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
        # Release lock
        lock_key = f"{project_id}:{board_id}"

        try:
            if self.lock_service:
                # Use unified lock service API
                release_result = await self.lock_service.release_lock(
                    project_id=project_id,
                    board_id=board_id,
                    work_item_id=work_item_id,
                )
                released = True
            else:
                # Use separate lock API
                release_result = await self.distributed_lock.release(
                    lock_key=lock_key,
                    holder_id=work_item_id,
                )
                released = release_result.released
        except Exception as e:
            logger.critical(
                f"Lock release failed for {work_item_id}: {e}",
                exc_info=True,
            )
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
                    logger.error(f"Failed to emit LockStuckEvent: {emit_err}", exc_info=True)
            return

        if not released:
            if self.lock_service:
                logger.warning(f"Lock not released for {work_item_id}: unknown error")
            else:
                logger.warning(
                    f"Lock not released for {work_item_id}: {release_result.reason.value if release_result.reason else 'unknown'}"
                )
            return

        logger.info(f"Lock released for {work_item_id}")

        # Complete workflow run lifecycle tracking
        await self._complete_workflow_run(work_item_id, column_config.name)

        # If using unified lock service and there's a next item, trigger its agent
        if self.lock_service and hasattr(release_result, "next_work_item_id") and release_result.next_work_item_id:
            # Find the pipeline trigger column (where agent was originally triggered)
            trigger_column = next(
                (col for col in workflow_config.columns if col.is_pipeline_trigger),
                None
            )
            if trigger_column and trigger_column.agent_id:
                await self._trigger_agent(
                    work_item_id=release_result.next_work_item_id,
                    column_config=trigger_column,
                    board_id=board_id,
                )

        # PipelineOrchestrator subscribes to PipelineLockReleasedEvent and
        # orchestrates granting the lock to the next queued item

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
                    started_at=now.isoformat(),
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
        if not self.event_store or not self.run_registry:
            return

        active_run = await self.run_registry.get_active_run(work_item_id)
        if not active_run:
            return

        workflow_run_id = active_run.run_id

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
        if not self.event_store or not self.run_registry:
            return

        active_run = await self.run_registry.get_active_run(work_item_id)
        if not active_run:
            return

        workflow_run_id = active_run.run_id
        now = datetime.now(UTC)
        # Calculate duration from start time
        started = datetime.fromisoformat(active_run.started_at)
        duration = int((now - started).total_seconds())

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
        if not self.event_store or not self.run_registry:
            return

        run_info = await self.run_registry.get_active_run(work_item_id)
        if run_info is None:
            return

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
            await self.run_registry.clear_run(work_item_id)
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
        if self.run_registry:
            run_info = await self.run_registry.get_active_run(work_item_id)
            if run_info:
                try:
                    await self.run_registry.set_active_run(
                        work_item_id=work_item_id,
                        run_id=run_info.run_id,
                        stage_name=column_config.name,
                        project_id=run_info.project_id,
                        board_id=run_info.board_id,
                        started_at=run_info.started_at,
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
            if self.run_registry:
                run_info = await self.run_registry.get_active_run(work_item_id)
                if run_info:
                    project_id = run_info.project_id
                else:
                    return

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
                lock_key = f"{project_id}:{board_id}"
                try:
                    if self.lock_service:
                        # Use unified lock service API
                        release_result = await self.lock_service.release_lock(
                            project_id=project_id,
                            board_id=board_id,
                            work_item_id=work_item_id,
                        )
                        released = True
                    else:
                        # Use separate lock API
                        release_result = await self.distributed_lock.release(
                            lock_key=lock_key,
                            holder_id=work_item_id,
                        )
                        released = release_result.released

                    if released:
                        logger.info(
                            f"Released lock for {work_item_id} due to execution failure",
                            extra={"error_id": "INFO_BOARD_EVENT_LOCK_RELEASED_AFTER_FAILURE"},
                        )
                    else:
                        logger.warning(
                            f"Cannot release lock for {work_item_id}: {release_result.reason.value if release_result.reason else 'unknown'}",
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

    async def handle_agent_execution_completed(
        self,
        event: AgentExecutionCompletedEvent,
    ) -> None:
        """
        Bridge `AgentExecutionCompletedEvent` to the auto-progression logic.

        The executor publishes `AgentExecutionCompletedEvent` on the event bus
        when it finishes processing a work item. This handler is subscribed to
        that event by the production and simulation bootstraps; it unwraps the
        event fields and delegates to `handle_agent_completion`, which contains
        the actual board-progression logic.

        The previous wiring used `ExecutionServiceAgentExecutor.set_completion_handler`
        to register `handle_agent_completion` as a direct callback. The event-bus
        path replaces it; INV-05 in `bootstrap/ARCHITECTURE.md` §6 now describes
        the subscription requirement instead of the callback requirement.

        Args:
            event: Completion event published by the agent executor.
        """
        await self.handle_agent_completion(
            work_item_id=event.work_item_id,
            board_id=event.board_id,
            success=event.success,
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
            logger.warning(f"Agent failed for {work_item_id}, routing to on_failure_column")
            try:
                config = await self.workflow_config.get_board_workflow_template(board_id)
                if config:
                    current_position = await self._find_item_position(board_id, work_item_id, config)
                    if not current_position and self.run_registry:
                        # Board service couldn't locate the item (no real Projects v2 board for
                        # this project, or the item is invisible at this moment). Fall back to
                        # our own tracking — mirrors the success-path fallback below.
                        run_info = await self.run_registry.get_active_run(work_item_id)
                        if run_info and run_info.stage_name:
                            current_position = WorkItemPosition(
                                work_item_id=work_item_id,
                                column_name=run_info.stage_name,
                                position=0,
                            )
                    column_config = config.get_column_config(current_position.column_name) if current_position else None
                    if column_config and column_config.on_failure_column:
                        # Set board context so GitHubBoardAdapter._move_item_to_column_locked
                        # doesn't raise "Project and board context required" -- mirrors the
                        # success-path pattern below.
                        if self.run_registry:
                            run_meta = await self.run_registry.get_active_run(work_item_id)
                            if run_meta:
                                await self.board_service.get_board(run_meta.project_id, board_id)
                        await self.board_service.move_item_to_column(
                            work_item_id, column_config.on_failure_column, MovedByType.ORCHESTRATOR
                        )
                        logger.info(f"Moved {work_item_id} to failure column '{column_config.on_failure_column}'")
                    else:
                        logger.warning(
                            f"Cannot route {work_item_id} to on_failure_column: "
                            f"current_position={current_position}, "
                            f"column_config={column_config}, "
                            f"on_failure_column={column_config.on_failure_column if column_config else None}"
                        )
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
            if not current_position and self.run_registry:
                # Board service couldn't locate the item (e.g. externally-triggered work item
                # not yet visible to the board adapter). Fall back to our own tracking.
                run_info = await self.run_registry.get_active_run(work_item_id)
                if run_info and run_info.stage_name:
                    current_position = WorkItemPosition(
                        work_item_id=work_item_id,
                        column_name=run_info.stage_name,
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

            try:
                # Set board context so GitHubBoardAdapter._move_item_to_column_locked
                # doesn't raise "Project and board context required".
                if self.run_registry:
                    run_meta = await self.run_registry.get_active_run(work_item_id)
                    if run_meta:
                        await self.board_service.get_board(run_meta.project_id, board_id)
                await self.board_service.move_item_to_column(work_item_id, next_column_name, MovedByType.ORCHESTRATOR)
            except Exception as board_err:
                # External board sync failures (missing context, wrong node ID, token scope) must
                # not block internal auto-progression — the workflow stage was already advanced.
                logger.warning(
                    f"Board sync failed during auto-progression for {work_item_id} "
                    f"(internal state already updated to '{next_column_name}'): {board_err}",
                    extra={"error_id": "ERR_BOARD_EVENT_SYNC_FAILURE", "work_item_id": work_item_id},
                )
                # D-E: surface the silent drift as a first-class domain event so
                # audit consumers / dashboards / reconciliation jobs can detect
                # work items whose external board column does not match the
                # internal authoritative state. Keep the warning above for
                # log readers, but make the failure addressable in the event
                # stream too.
                if self.event_emitter:
                    project_id_for_event = ""
                    if self.run_registry:
                        run_meta = await self.run_registry.get_active_run(work_item_id)
                        if run_meta:
                            project_id_for_event = run_meta.project_id
                    try:
                        self.event_emitter.emit(
                            BoardSyncFailedEvent(
                                type="board.sync_failed",
                                timestamp=datetime.now(UTC).isoformat(),
                                source="board_event_handler",
                                work_item_id=work_item_id,
                                project_id=project_id_for_event,
                                board_id=board_id,
                                intended_column=next_column_name,
                                error_message=str(board_err)[:500],
                                failed_at=datetime.now(UTC).isoformat(),
                            )
                        )
                    except Exception as emit_err:
                        logger.error(
                            f"Failed to emit BoardSyncFailedEvent for {work_item_id}: {emit_err}",
                            exc_info=True,
                            extra={
                                "error_id": "ERR_BOARD_EVENT_SYNC_FAILURE_EMIT",
                                "work_item_id": work_item_id,
                            },
                        )

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
        project_id: str | None = None,
    ) -> WorkItemPosition | None:
        """Find a work item's current board position.

        Tries get_item_position() first (O(1) for most adapters). Falls back to
        scanning all columns via get_items_in_column() for adapters that require
        explicit board context (e.g. GitHubBoardAdapter with GitHub Projects v2).

        D-L: Codetoreum identifies work items by an internal UUID
        (``work_item.id``), while board adapters like GitHubBoardAdapter
        populate column entries with the external system's identity
        (issue number for GitHub Projects v2). To bridge the two we also
        compare against the work item's ``external_id`` — typically the
        GitHub issue number — when scanning columns.

        ``project_id`` is used to establish board context before the
        column scan (GitHubBoardAdapter requires this; in-memory adapters
        ignore it). When omitted, the scan path will still try, but
        adapters needing context will fail at get_items_in_column.
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

        # Establish board context so adapters like GitHubBoardAdapter can
        # serve get_items_in_column without raising "project_id must be a
        # non-empty string". Mirrors the success-path pattern in
        # handle_agent_completion.
        if project_id:
            try:
                await self.board_service.get_board(project_id, board_id)
            except Exception as e:
                logger.debug(f"Could not set board context for {board_id}: {e}")

        # Resolve the work item's external_id (if any) so we can match
        # against board adapters that key by the external system's id.
        # The handler holds IWorkItemCommandPort (command-side) which has
        # no get_work_item; if a richer service was injected, use it.
        external_id: str | None = None
        get_wi = getattr(self.work_item_service, "get_work_item", None)
        if get_wi is not None:
            try:
                wi = await get_wi(work_item_id)
                external_id = getattr(wi, "external_id", None)
            except Exception as e:
                logger.debug(f"Could not load external_id for {work_item_id}: {e}")

        for column in config.columns:
            try:
                items = await self.board_service.get_items_in_column(board_id, column.name)
                for item in items:
                    if item.work_item_id == work_item_id or (external_id and item.work_item_id == external_id):
                        return item
            except Exception as e:
                logger.debug(f"Error scanning column '{column.name}' for {work_item_id}: {e}")
        return None
