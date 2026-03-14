"""Event handler for board column change events.

Subscribes to workitem.column_changed events and orchestrates:
- Pipeline lock acquisition/release based on column type
- Agent execution when work items enter automated columns
- Auto-progression to next column on agent completion
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

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
    DomainEvent,
    LockStuckEvent,
    WorkflowCompleted,
    WorkflowCreated,
    WorkflowFailed,
    WorkflowStageAdvanced,
    WorkflowStarted,
    WorkItemColumnChanged,
)
from codetoreum.infrastructure.event_bus import EventBus, EventHandler, event_handler
from codetoreum.ports.exceptions import ExternalServiceError, ResourceNotFoundError
from codetoreum.ports.output.active_workflow_run_registry import IActiveWorkflowRunRegistry
from codetoreum.ports.output.agent_executor import IAgentExecutor
from codetoreum.ports.output.board_service import IBoardService, MovedByType
from codetoreum.ports.output.event_store import IEventStore
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService

logger = logging.getLogger(__name__)


@event_handler("WorkItemColumnChanged")
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

        # Now when a WorkItemColumnChanged event is published:
        event = WorkItemColumnChanged(
            aggregate_id="item-1",
            payload={
                "work_item_id": "item-1",
                "board_id": "board-1",
                "project_id": "proj-1",
                "from_column": "Backlog",
                "to_column": "In Development",
                "moved_by": "human"
            }
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
        """
        self.board_service = board_service
        self.lock_service = lock_service
        self.workflow_config = workflow_config
        self.agent_executor = agent_executor
        self.event_bus = event_bus
        self.event_store = event_store
        self.run_registry = run_registry
        # Tracks active workflow runs: work_item_id -> run metadata
        self._active_runs: dict[str, dict[str, Any]] = {}

    def get_event_types(self) -> list[str]:
        """Get list of event types this handler processes.

        Returns:
            List of event type names
        """
        return ["WorkItemColumnChanged"]

    async def handle(self, event: DomainEvent) -> None:
        """
        Handle column change event and trigger appropriate workflow actions.

        Args:
            event: Domain event to handle

        Raises:
            Exception: If handling fails
        """
        if not isinstance(event, WorkItemColumnChanged):
            logger.warning(f"BoardColumnEventHandler received unexpected event type: {event.event_type}")
            return

        try:
            await self.handle_column_change(event)
        except Exception as e:
            logger.error(
                f"Error handling column change for {event.payload.get('work_item_id')}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_BOARD_EVENT_HANDLE_COLUMN_CHANGE_FAILURE"},
            )
            raise

    async def handle_column_change(self, event: WorkItemColumnChanged) -> None:
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
            event: WorkItemColumnChanged event with column movement details
        """
        work_item_id: str = event.payload.get("work_item_id") or ""
        board_id: str = event.payload.get("board_id") or ""
        project_id: str = event.payload.get("project_id") or ""
        from_column: str = event.payload.get("from_column") or ""
        to_column: str = event.payload.get("to_column") or ""

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
            return

        # Check if this is an exit column (releases lock)
        if column_config.is_exit_column:
            await self._handle_exit_column(work_item_id, project_id, board_id, column_config, config)

        # Trigger agent if column has one and is automated
        if column_config.agent_id and column_config.type == ColumnType.AUTOMATED:
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
            position = await self.board_service.get_item_position(work_item_id)
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

            # Trigger agent if column has one
            if column_config.agent_id:
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
            # when re-entering the column (e.g., after reviewer rejection in maker-checker flow)
            if column_config.agent_id:
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
            # CRITICAL: Lock may be stuck
            # TODO: Emit LockStuckEvent for manual intervention
            return

        logger.info(f"Lock released for {work_item_id}, next work item: {release_result.next_work_item_id}")

        # Complete workflow run lifecycle tracking
        await self._complete_workflow_run(work_item_id, column_config.name)

        # Trigger agent for next queued item if one exists
        if release_result.next_work_item_id:
            try:
                next_position = await self.board_service.get_item_position(release_result.next_work_item_id)
                next_column_config = workflow_config.get_column_config(next_position.column_name)

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
                # EventBus.publish is typed for DomainEvent; LockStuckEvent is a CodetoreumEvent
                # but satisfies the same duck-typed interface (event_type property, metadata dict).
                await self.event_bus.publish(
                    LockStuckEvent(  # type: ignore[arg-type]
                        type="lock.stuck",
                        timestamp=datetime.now(UTC).isoformat(),
                        source="board_event_handler",
                        project_id=project_id,
                        board_id=board_id,
                        work_item_id=release_result.next_work_item_id,
                        reason=str(e),
                    )
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
        stage_count = len([c for c in workflow_config.columns if c.agent_id])

        self._active_runs[work_item_id] = {
            "run_id": workflow_run_id,
            "project_id": project_id,
            "board_id": board_id,
            "template_id": workflow_config.id,
            "started_at": now,
            "stage_index": 0,
        }

        created = WorkflowCreated(
            aggregate_id=workflow_run_id,
            payload={
                "work_item_id": work_item_id,
                "template_id": workflow_config.id,
                "project_id": project_id,
                "stage_count": stage_count,
            },
        )
        started = WorkflowStarted(
            aggregate_id=workflow_run_id,
            payload={
                "started_at": now.isoformat(),
                "work_item_id": work_item_id,
                "first_stage": column_config.name,
            },
        )
        try:
            await self.event_store.append(workflow_run_id, [created, started])
            logger.debug(f"Workflow run {workflow_run_id} started for {work_item_id}")
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
        run_info["stage_index"] += 1
        workflow_run_id = run_info["run_id"]

        event = WorkflowStageAdvanced(
            aggregate_id=workflow_run_id,
            payload={
                "stage_index": run_info["stage_index"],
                "from_stage": from_stage,
                "to_stage": to_stage,
            },
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
        workflow_run_id = run_info["run_id"]
        now = datetime.now(UTC)
        duration = (now - run_info["started_at"]).total_seconds()

        event = WorkflowCompleted(
            aggregate_id=workflow_run_id,
            payload={
                "completed_at": now.isoformat(),
                "work_item_id": work_item_id,
                "duration_seconds": duration,
                "exit_column": exit_column,
            },
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
        workflow_run_id = run_info["run_id"]
        now = datetime.now(UTC)

        event = WorkflowFailed(
            aggregate_id=workflow_run_id,
            payload={
                "failed_at": now.isoformat(),
                "reason": reason,
                "failed_stage": "",
                "work_item_id": work_item_id,
            },
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
        Trigger agent execution for a work item.

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
                    run_id=run_info["run_id"],
                    stage_name=column_config.name,
                    project_id=run_info.get("project_id", ""),
                )
            except Exception as e:
                logger.error(
                    f"Failed to update active run registry for {work_item_id}: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_BOARD_EVENT_RUN_REGISTRY_UPDATE_FAILURE"},
                )

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
            Exception: Logs error but doesn't re-raise
        """
        if not success:
            logger.warning(f"Agent failed for {work_item_id}, skipping auto-progression")
            await self._fail_workflow_run(work_item_id, "Agent execution failed")
            return

        try:
            config = await self.workflow_config.get_board_workflow_template(board_id)
            if not config:
                logger.warning(f"No workflow config for board {board_id}, skipping auto-progression")
                return

            current_position = await self.board_service.get_item_position(work_item_id)
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
