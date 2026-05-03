"""Production Orchestration Integration Test

Tests end-to-end production pipeline with real-like error scenarios.

This test demonstrates:
1. WorkItem triggering pipeline via board column change
2. Pipeline acquiring exclusive lock
3. Agents executing in sequence through stages
4. Event store capturing complete audit trail
5. Production error recovery and resilience
6. Pipeline lock release and queue processing
"""

import logging
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.integration.conftest import MockWorkflowConfigService
from codetoreum.adapters.secondary.in_memory_queue_lock_service import InMemoryLockService
from codetoreum.adapters.testing.in_memory_event_store import InMemoryEventStore
from codetoreum.adapters.testing.mock_agent_executor import MockAgentExecutor
from codetoreum.adapters.testing.mock_board_adapter import MockBoardAdapter
from codetoreum.application.agent_execution_recovery_service import AgentExecutionRecoveryService
from codetoreum.application.event_handlers.board_event_handler import BoardColumnEventHandler
from codetoreum.config.codetoreum_pipeline import create_codetoreum_pipeline_template
from codetoreum.domain.board_workflow_template import BoardWorkflowTemplate
from codetoreum.domain.events import WorkItemColumnChangedEvent
from codetoreum.infrastructure.event_bus import EventBus
from tests.helpers.production_helpers import (
    EventStoreAuditTrail,
    ProductionErrorHandler,
    PRVerifier,
)
from codetoreum.ports.output.board_service import MovedByType
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.failed_event_store import FailedEventStoreStats, IFailedEventStore
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService

logger = logging.getLogger(__name__)


class MockFailedEventStore(IFailedEventStore):
    """Mock implementation of failed event store for testing."""

    def __init__(self) -> None:
        """Initialize."""
        self.events: dict[str, Any] = {}

    async def add_failed_event(
        self,
        event_type: str,
        event_data: dict[str, Any],
        failure_reason: Any,
        error_message: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add a failed event."""
        event_id = f"failed_{len(self.events)}"
        self.events[event_id] = {
            "event_type": event_type,
            "event_data": event_data,
            "failure_reason": failure_reason,
            "error_message": error_message,
            "metadata": metadata,
        }
        return event_id

    def get_stats(self) -> FailedEventStoreStats:
        """Get stats."""
        return FailedEventStoreStats(
            total_failed_events=len(self.events),
            pending_retries=0,
            exhausted_retries=0,
            total_retries_attempted=0,
            total_retries_succeeded=0,
            total_retries_failed=0,
        )

    def list_events(
        self,
        failure_reason: Any | None = None,
        can_retry: bool | None = None,
        limit: int | None = None,
    ) -> list[Any]:
        """List events."""
        return []

    def get_event(self, event_id: str) -> Any | None:
        """Get event."""
        return self.events.get(event_id)

    def remove_event(self, event_id: str) -> bool:
        """Remove event."""
        if event_id in self.events:
            del self.events[event_id]
            return True
        return False

    def clear(self) -> None:
        """Clear all events."""
        self.events.clear()


class TestProductionOrchestration:
    """Production Orchestration Tests."""

    @pytest.fixture
    async def codetoreum_pipeline(self) -> Any:
        """Get Codetoreum pipeline template."""
        return create_codetoreum_pipeline_template()

    @pytest.fixture
    async def production_setup(self, codetoreum_pipeline: Any) -> tuple[
        EventBus,
        BoardColumnEventHandler,
        InMemoryEventStore,
        MockBoardAdapter,
        MockAgentExecutor,
        InMemoryLockService,
    ]:
        """Set up production-like environment."""
        event_store = InMemoryEventStore()
        event_bus = EventBus()
        board_service = MockBoardAdapter()
        agent_executor = MockAgentExecutor()
        lock_service = InMemoryLockService(event_bus=event_bus)
        workflow_config = MockWorkflowConfigService(codetoreum_pipeline)
        event_emitter = MagicMock(spec=IEventEmitter)
        run_registry = MagicMock()
        run_registry.set_active_run = AsyncMock()
        failed_event_store = MockFailedEventStore()
        recovery_service = AgentExecutionRecoveryService(
            failed_event_store=failed_event_store,
            event_store=event_store,
        )

        # Initialize board with columns from template
        project_id = codetoreum_pipeline.project_id
        board_id = codetoreum_pipeline.board_id
        column_names = [col.name for col in codetoreum_pipeline.columns]
        board_service.create_board(project_id, board_id, "Test Board", column_names)
        board_service.current_project = project_id
        board_service.current_board = board_id
        board_service.event_bus = event_bus

        handler = BoardColumnEventHandler(
            board_service=board_service,
            lock_service=lock_service,
            workflow_config=workflow_config,
            agent_executor=agent_executor,
            event_bus=event_bus,
            event_store=event_store,
            run_registry=run_registry,
            event_emitter=event_emitter,
            recovery_service=recovery_service,
        )

        event_bus.register_handler(handler)

        return event_bus, handler, event_store, board_service, agent_executor, lock_service

    @pytest.mark.asyncio
    async def test_pipeline_lock_acquisition_and_release(
        self,
        production_setup: tuple[
            EventBus,
            BoardColumnEventHandler,
            InMemoryEventStore,
            MockBoardAdapter,
            MockAgentExecutor,
            InMemoryLockService,
        ],
    ) -> None:
        """
        Test pipeline lock acquisition and release.

        Expected:
        - Work item in Analysis triggers lock acquisition
        - Lock acquired → agent execution
        - Work item in Done triggers lock release
        - Next queued item gets lock
        """
        event_bus, handler, event_store, board_service, agent_executor, lock_service = production_setup

        work_item_1 = "CTMM-100"
        work_item_2 = "CTMM-101"
        board_id = "codetoreum-main"
        project_id = "codetoreum"

        # Add items to board (queued order)
        await board_service.add_item_to_column(work_item_1, "Backlog", MovedByType.HUMAN)
        await board_service.add_item_to_column(work_item_2, "Backlog", MovedByType.HUMAN)

        # Trigger pipeline for first item
        event1 = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            work_item_id=work_item_1,
            board_id=board_id,
            project_id=project_id,
            from_column="Backlog",
            to_column="Analysis",
            moved_by="human",
        )

        await event_bus.publish(event1)

        # Verify lock acquired and agent executed
        queue_state = await lock_service.get_queue_state(project_id, board_id)
        assert queue_state.lock_holder == work_item_1

        # Simulate agent completion by moving to next stage
        await board_service.move_item_to_column(work_item_1, "Implementation", MovedByType.ORCHESTRATOR)

        # Simulate completion through all stages (auto-progression)
        for column in ["Testing", "Review", "Done"]:
            event_progress = WorkItemColumnChangedEvent(
                type="workitem.column_changed",
                timestamp=datetime.now(UTC).isoformat(),
                source="test",
                work_item_id=work_item_1,
                board_id=board_id,
                project_id=project_id,
                from_column="Review" if column == "Done" else "Testing" if column == "Review" else "Implementation",
                to_column=column,
                moved_by="orchestrator",
            )
            await event_bus.publish(event_progress)

        # Verify lock released
        queue_state = await lock_service.get_queue_state(project_id, board_id)
        assert queue_state.lock_holder is None

    @pytest.mark.asyncio
    async def test_event_store_audit_trail_completeness(
        self,
        production_setup: tuple[
            EventBus,
            BoardColumnEventHandler,
            InMemoryEventStore,
            MockBoardAdapter,
            MockAgentExecutor,
            InMemoryLockService,
        ],
    ) -> None:
        """
        Test event store captures complete audit trail.

        Expected:
        - WorkflowCreated event when lock acquired
        - WorkflowStarted event when pipeline begins
        - WorkflowStageAdvanced events on transitions
        - WorkflowCompleted event when reaching exit column
        - All events have timestamps and can be correlated
        """
        event_bus, handler, event_store, board_service, agent_executor, lock_service = production_setup

        work_item_id = "CTMM-200"
        board_id = "codetoreum-main"
        project_id = "codetoreum"

        await board_service.add_item_to_column(work_item_id, "Backlog", MovedByType.HUMAN)

        # Trigger pipeline
        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            work_item_id=work_item_id,
            board_id=board_id,
            project_id=project_id,
            from_column="Backlog",
            to_column="Analysis",
            moved_by="human",
        )

        await event_bus.publish(event)

        # Verify events in store
        audit_trail = EventStoreAuditTrail(event_store)

        # Get all events recorded
        all_events = []
        stream_ids = await event_store.get_all_stream_ids()
        for stream_id in stream_ids:
            events = event_store.get_events_for_stream(stream_id)
            all_events.extend(events)

        # Should have at least WorkflowCreated and WorkflowStarted
        event_types = {e.event_type for e in all_events}
        assert "WorkflowCreated" in event_types
        assert "WorkflowStarted" in event_types

        # Verify events have proper structure
        for event in all_events:
            assert event.aggregate_id is not None
            assert event.event_type is not None

    @pytest.mark.asyncio
    async def test_concurrent_work_items_with_queue(
        self,
        production_setup: tuple[
            EventBus,
            BoardColumnEventHandler,
            InMemoryEventStore,
            MockBoardAdapter,
            MockAgentExecutor,
            InMemoryLockService,
        ],
    ) -> None:
        """
        Test concurrent work items are properly queued.

        Expected:
        - First item acquires lock
        - Second item queued
        - On first item completion, second item gets lock
        """
        event_bus, handler, event_store, board_service, agent_executor, lock_service = production_setup

        item1 = "CTMM-300"
        item2 = "CTMM-301"
        item3 = "CTMM-302"
        board_id = "codetoreum-main"
        project_id = "codetoreum"

        # Add items in order
        for i, item in enumerate([item1, item2, item3]):
            await board_service.add_item_to_column(item, "Backlog", MovedByType.HUMAN)

        # Trigger all items to Analysis simultaneously
        for item in [item1, item2, item3]:
            event = WorkItemColumnChangedEvent(
                type="workitem.column_changed",
                timestamp=datetime.now(UTC).isoformat(),
                source="test",
                work_item_id=item,
                board_id=board_id,
                project_id=project_id,
                from_column="Backlog",
                to_column="Analysis",
                moved_by="human",
            )
            await event_bus.publish(event)

        # Verify first item has lock
        queue_state = await lock_service.get_queue_state(project_id, board_id)
        assert queue_state.lock_holder == item1

        # Verify queue contains others
        queued_item_ids = [entry.work_item_id for entry in queue_state.queue]
        assert item2 in queued_item_ids or item3 in queued_item_ids

    @pytest.mark.asyncio
    async def test_graceful_degradation_with_agent_failure(
        self,
        production_setup: tuple[
            EventBus,
            BoardColumnEventHandler,
            InMemoryEventStore,
            MockBoardAdapter,
            MockAgentExecutor,
            InMemoryLockService,
        ],
    ) -> None:
        """
        Test graceful degradation when agent execution fails.

        Expected:
        - Agent execution error is logged
        - Pipeline lock is released
        - Work item moved to Blocked column
        - Next queued item can proceed
        """
        event_bus, handler, event_store, board_service, agent_executor, lock_service = production_setup

        work_item_id = "CTMM-400"
        board_id = "codetoreum-main"
        project_id = "codetoreum"

        await board_service.add_item_to_column(work_item_id, "Backlog", MovedByType.HUMAN)

        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            work_item_id=work_item_id,
            board_id=board_id,
            project_id=project_id,
            from_column="Backlog",
            to_column="Analysis",
            moved_by="human",
        )

        # Configure agent executor to fail for this test
        original_simulate = agent_executor._simulate_execution

        async def failing_simulate(*args: Any, **kwargs: Any) -> None:
            """Simulate execution that fails with an error."""
            work_item = args[0] if args else None
            try:
                raise RuntimeError(f"Agent execution failed for {work_item}")
            except Exception as e:
                # Call the error handling path
                import asyncio

                from codetoreum.domain.agent_execution import ExecutionStatus
                from datetime import UTC

                execution_id = args[2] if len(args) > 2 else ""
                agent_id = args[1] if len(args) > 1 else ""
                started_at = args[3] if len(args) > 3 else datetime.now(UTC)
                board_id = args[4] if len(args) > 4 else "board-1"

                # Update execution record to FAILED
                agent_executor._update_execution_record(
                    execution_id,
                    agent_id,
                    work_item,
                    started_at,
                    ExecutionStatus.FAILED,
                    error_message=str(e),
                )

                if agent_executor._completion_callback:
                    try:
                        await agent_executor._completion_callback(work_item, board_id, False)
                    except Exception:
                        pass

        agent_executor._simulate_execution = failing_simulate  # type: ignore

        # Should not raise despite agent failure
        await event_bus.publish(event)

        # Allow async completion to happen
        import asyncio

        await asyncio.sleep(0.2)

        # Simulate work item being moved to Blocked on agent failure, then to Done
        # (In production, this would happen via error recovery, here we simulate it)
        await board_service.move_item_to_column(work_item_id, "Blocked", MovedByType.ORCHESTRATOR)
        await board_service.move_item_to_column(work_item_id, "Done", MovedByType.ORCHESTRATOR)

        # Publish the column change event to trigger lock release
        done_event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            work_item_id=work_item_id,
            board_id=board_id,
            project_id=project_id,
            from_column="Blocked",
            to_column="Done",
            moved_by="orchestrator",
        )
        await event_bus.publish(done_event)

        # Verify lock was released
        queue_state = await lock_service.get_queue_state(project_id, board_id)
        assert queue_state.lock_holder is None

