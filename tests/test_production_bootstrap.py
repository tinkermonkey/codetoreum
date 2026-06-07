"""Tests for ProductionApplicationBootstrap critical path enforcement."""

import os

import pytest

from codetoreum.infrastructure.bootstrap import ProductionApplicationBootstrap
from codetoreum.infrastructure.simulation.simulation_config import AdapterSelectionConfig


def _infrastructure_available() -> bool:
    """Check if required infrastructure services are available for testing."""
    # For this test to run, we need Elasticsearch and Redis running locally
    # This is typically only available in full integration test environments
    import socket

    def service_available(host: str, port: int) -> bool:
        try:
            socket.create_connection((host, port), timeout=0.5)
            return True
        except (TimeoutError, ConnectionRefusedError):
            return False

    # Check if Elasticsearch and Redis are available
    es_available = service_available("localhost", 9200)
    redis_available = service_available("localhost", 6380)

    return es_available and redis_available


@pytest.mark.asyncio
async def test_critical_path_mock_detection_raises_error() -> None:
    """Verify that critical path validation detects and rejects mock adapters."""
    # Critical-path slots seeded with mock variants — board / container / etc.
    # all live in CRITICAL_ADAPTER_SLOTS, so Phase 3 validation must reject this.
    bad_config = AdapterSelectionConfig(
        board="mock",
        ticket="in_memory",
        version_control="in_memory",
        container="fake",
        code_review="mock",
        event_store="in_memory",
    )

    bootstrap = ProductionApplicationBootstrap(adapter_config=bad_config)

    # Setup should fail during critical path validation (Phase 3)
    with pytest.raises(RuntimeError, match="Mock adapters detected on critical execution path"):
        await bootstrap.setup()


def test_in_memory_event_store_not_on_critical_path() -> None:
    """Verify that in-memory event store is in NON_CRITICAL_SLOTS, not CRITICAL_ADAPTER_SLOTS."""
    from codetoreum.infrastructure.bootstrap.production_bootstrap import (
        CRITICAL_ADAPTER_SLOTS,
        NON_CRITICAL_SLOTS,
    )

    # Verify event_store is not in critical slots
    assert "event_store" not in CRITICAL_ADAPTER_SLOTS, "event_store should not be on critical path for MVP"
    # Verify event_store is in non-critical slots
    assert "event_store" in NON_CRITICAL_SLOTS, "event_store should be in non-critical slots for MVP"


def test_get_adapter_slot_info_before_setup_raises() -> None:
    """Verify that get_adapter_slot_info raises if called before setup."""
    bootstrap = ProductionApplicationBootstrap()

    with pytest.raises(RuntimeError, match="get_adapter_slot_info.*before setup"):
        bootstrap.get_adapter_slot_info()


@pytest.mark.asyncio
@pytest.mark.skipif(not _infrastructure_available(), reason="Requires Elasticsearch and Redis to be running locally")
async def test_critical_adapters_have_failure_routes() -> None:
    """Verify that Phase 3a validates critical adapters declare failure routes (INV-20).

    This test requires live Elasticsearch and Redis services for infrastructure
    exclusivity verification (Phase 1c). It verifies that critical adapters
    are properly configured with failure routes via the DLQ.
    """
    # Use default production config (all real adapters)
    bootstrap = ProductionApplicationBootstrap()

    # setup() should pass Phase 3a validation that all critical adapters have failed_event_store
    app = await bootstrap.setup()
    assert app is not None

    # Verify that at least the infrastructure's failed_event_store was created and is available
    assert bootstrap.infrastructure is not None
    assert bootstrap.infrastructure.failed_event_store is not None

    # Verify critical adapters have non-None failure routes (exactly 5 critical adapters)
    critical_adapters_with_failure_routes = [
        adapter
        for slot_name in ["board", "ticket", "version_control", "container", "code_review"]
        if (adapter := bootstrap.adapters.__dict__.get(slot_name))
        and getattr(adapter, "failed_event_store", None) is not None
    ]
    assert (
        len(critical_adapters_with_failure_routes) == 5
    ), "All 5 critical adapters should have non-None failure routes"

    # Verify DLQ retry processor was started (Phase 5d-2)
    # The failed_event_store should be a DeadLetterQueueFailedEventStoreAdapter
    # wrapping a running DeadLetterQueue instance
    from codetoreum.adapters.secondary.failed_event_store_adapter import (
        DeadLetterQueueFailedEventStoreAdapter,
    )

    failed_event_store = bootstrap.infrastructure.failed_event_store
    assert isinstance(
        failed_event_store, DeadLetterQueueFailedEventStoreAdapter
    ), "failed_event_store should be DeadLetterQueueFailedEventStoreAdapter in production"

    # Check that the underlying DLQ's retry processor is running
    dlq = failed_event_store._dead_letter_queue
    assert dlq is not None, "DeadLetterQueue should be initialized"
    assert dlq._running is True, "DLQ retry processor should be running (Phase 5d-2)"

    await bootstrap.teardown()


@pytest.mark.asyncio
async def test_event_handler_types_declared() -> None:
    """Verify event handler decorators declare correct event types with live event bus subscriptions.

    This test verifies that:
    1. The @event_handler decorators on all handlers declare the correct event types
    2. The event bus has live subscribers for every event type each handler claims to handle

    The mapping here must match the @event_handler decorators in
    src/codetoreum/application/event_handlers/:
    - BoardColumnEventHandler
    - PRReviewCycleDispatchHandler
    - PRReviewCycleEventHandler
    - ReviewEventHandler
    - WorkflowEventHandler (Lifecycle Event Handler Registration)
    - ExecutionEventHandler (Lifecycle Event Handler Registration)
    - BranchResolutionEventHandler (Lifecycle Event Handler Registration)
    - RepairCycleEventHandler (Lifecycle Event Handler Registration)
    - PipelineOrchestrator (Lock/Queue Coordination)
    """
    from unittest.mock import MagicMock

    from codetoreum.application.event_handlers import (
        BoardColumnEventHandler,
        BranchResolutionEventHandler,
        ExecutionEventHandler,
        PRReviewCycleEventHandler,
        RepairCycleEventHandler,
        ReviewEventHandler,
        WorkflowEventHandler,
    )
    from codetoreum.application.event_handlers.pipeline_orchestrator import (
        PipelineOrchestrator,
    )
    from codetoreum.application.event_handlers.pr_review_cycle_dispatch_handler import (
        PRReviewCycleDispatchHandler,
    )
    from codetoreum.infrastructure.event_bus import EventBus

    # Create event bus instance to test live subscriptions
    event_bus = EventBus()

    # Minimal mock dependencies for handler instantiation
    mock_services = {
        "review_service": MagicMock(),
        "ci_pipeline_service": MagicMock(),
        "orchestrator": MagicMock(),
        "execution_service": MagicMock(),
    }

    mock_adapters = {
        "board": MagicMock(),
        "pr_review_cycle": MagicMock(),
        "workflow_config": MagicMock(),
        "work_item_service": MagicMock(),
        "run_registry": MagicMock(),
        "distributed_lock": MagicMock(),
        "pipeline_queue": MagicMock(),
        "orphan_scan_registry": MagicMock(),
        "event_emitter": MagicMock(),
    }

    # Instantiate all handlers and register with event bus
    handlers = [
        # Board column handler
        BoardColumnEventHandler(
            board_service=mock_adapters["board"],
            workflow_config=mock_adapters["workflow_config"],
            agent_executor=MagicMock(),
            event_bus=event_bus,
            work_item_service=MagicMock(),
            distributed_lock=MagicMock(),
            pipeline_queue=MagicMock(),
        ),
        # PR Review Cycle Dispatch Handler
        PRReviewCycleDispatchHandler(
            pr_review_cycle=mock_adapters["pr_review_cycle"],
            workflow_config=mock_adapters["workflow_config"],
            work_item_service=mock_adapters["work_item_service"],
            active_workflow_run_registry=mock_adapters["run_registry"],
        ),
        # PR Review Cycle Event Handler
        PRReviewCycleEventHandler(
            board_service=mock_adapters["board"],
        ),
        # Review Event Handler
        ReviewEventHandler(
            review_service=mock_services["review_service"],
            ci_pipeline_service=mock_services["ci_pipeline_service"],
        ),
        # Workflow Event Handler
        WorkflowEventHandler(
            orchestrator=mock_services["orchestrator"],
        ),
        # Execution Event Handler
        ExecutionEventHandler(
            execution_service=mock_services["execution_service"],
        ),
        # Branch Resolution Event Handler
        BranchResolutionEventHandler(
            event_bus=event_bus,
        ),
        # Repair Cycle Event Handler
        RepairCycleEventHandler(
            repair_cycle=MagicMock(),
            workflow_config=mock_adapters["workflow_config"],
            event_bus=event_bus,
            ci_pipeline_service=mock_services["ci_pipeline_service"],
        ),
        # Pipeline Orchestrator
        PipelineOrchestrator(
            distributed_lock=mock_adapters["distributed_lock"],
            pipeline_queue=mock_adapters["pipeline_queue"],
            run_registry=mock_adapters["run_registry"],
            event_emitter=mock_adapters["event_emitter"],
            orphan_scan_registry=mock_adapters["orphan_scan_registry"],
        ),
    ]

    # Register all handlers with the event bus
    for handler in handlers:
        event_bus.register_handler(handler)

    # Expected event type mappings - must match @event_handler decorators
    expected_handler_event_types = {
        "BoardColumnEventHandler": {
            "WorkItemColumnChangedEvent",
            "AgentExecutionCompletedEvent",
        },
        "PRReviewCycleDispatchHandler": {"WorkItemColumnChangedEvent"},
        "PRReviewCycleEventHandler": {
            "PRReviewCycleApprovedEvent",
            "PRReviewCycleIssuesFoundEvent",
            "PRReviewCycleMaxCyclesReachedEvent",
        },
        "ReviewEventHandler": {
            "ReviewCycleCreatedEvent",
            "ReviewCycleIterationStartedEvent",
            "ReviewCycleFeedbackSubmittedEvent",
            "ReviewCycleApprovedEvent",
            "ReviewCycleRejectedEvent",
            "ReviewCycleEscalatedToHumanEvent",
        },
        "WorkflowEventHandler": {
            "WorkItemCreatedEvent",
            "ExecutionCompletedEvent",
            "ExecutionFailedEvent",
            "ReviewCycleApprovedEvent",
            "ReviewCycleRejectedEvent",
            "ReviewCycleEscalatedToHumanEvent",
        },
        "ExecutionEventHandler": {
            "ExecutionInitializedEvent",
            "ExecutionStartedEvent",
            "ExecutionCompletedEvent",
            "ExecutionFailedEvent",
            "ExecutionTimedOutEvent",
        },
        "BranchResolutionEventHandler": {
            "BranchResolvedEvent",
            "BranchReusedEvent",
            "BranchResolutionCreatedEvent",
        },
        "RepairCycleEventHandler": {"WorkItemColumnChangedEvent"},
        "PipelineOrchestrator": {
            "PipelineLockAcquiredEvent",
            "PipelineLockReleasedEvent",
        },
    }

    # Verify the mapping is not empty
    assert len(expected_handler_event_types) > 0, "Handler event type mapping should not be empty"

    # Verify each handler has at least one event type declared
    for handler_name, event_types in expected_handler_event_types.items():
        assert len(event_types) > 0, f"Handler {handler_name} should declare at least one event type"

    # Verify that the event bus has live subscribers for all declared event types
    for handler_name, expected_event_types in expected_handler_event_types.items():
        for event_type in expected_event_types:
            assert (
                event_type in event_bus._handlers
            ), f"Event bus should have subscribers for {event_type} (declared by {handler_name})"

            # Verify at least one handler is subscribed to this event type
            subscribers = event_bus._handlers[event_type]
            assert len(subscribers) > 0, f"Event type {event_type} should have at least one subscriber"

    # Verify the total number of registered handlers matches our expectations
    total_registered_handlers = sum(len(handlers) for handlers in event_bus._handlers.values())
    assert total_registered_handlers > 0, "Event bus should have registered handlers for the declared event types"


@pytest.mark.asyncio
async def test_adapter_selection_config_has_31_slots() -> None:
    """Verify that AdapterSelectionConfig has exactly 31 slots."""
    config = AdapterSelectionConfig()
    slots = list(AdapterSelectionConfig.__dataclass_fields__.keys())

    assert len(slots) == 31, f"Expected 31 slots, got {len(slots)}: {slots}"


def test_critical_adapter_slots_defined() -> None:
    """Verify that critical adapter slots are correctly defined."""
    from codetoreum.infrastructure.bootstrap.production_bootstrap import CRITICAL_ADAPTER_SLOTS

    expected_critical = {
        "board",
        "ticket",
        "version_control",
        "container",
        "code_review",
    }

    assert expected_critical == CRITICAL_ADAPTER_SLOTS


def test_non_critical_adapter_slots_defined() -> None:
    """Verify that non-critical adapter slots are correctly defined."""
    from codetoreum.infrastructure.bootstrap.production_bootstrap import NON_CRITICAL_SLOTS

    expected_non_critical = {
        "event_store",  # InMemoryEventStore acceptable for MVP
        "review_cycle",
        "pr_review_cycle",
        "systemic_analysis",
        "environment_repair",
    }

    assert expected_non_critical == NON_CRITICAL_SLOTS


@pytest.mark.asyncio
async def test_validate_event_emitter_raises_when_capturing_mock_detected() -> None:
    """Verify that _validate_event_emitter_is_production raises RuntimeError when CapturingMockEventEmitter is detected."""
    from codetoreum.adapters.testing import CapturingMockEventEmitter

    bootstrap = ProductionApplicationBootstrap()
    # Manually set adapters with CapturingMockEventEmitter to simulate the misconfiguration
    bootstrap.adapters = type("Adapters", (), {"event_emitter": CapturingMockEventEmitter()})()

    with pytest.raises(RuntimeError, match="CapturingMockEventEmitter"):
        bootstrap._validate_event_emitter_is_production()


@pytest.mark.asyncio
async def test_validate_event_emitter_raises_when_none() -> None:
    """Verify that _validate_event_emitter_is_production raises RuntimeError when event_emitter is None."""
    bootstrap = ProductionApplicationBootstrap()
    # Manually set adapters with None event_emitter
    bootstrap.adapters = type("Adapters", (), {"event_emitter": None})()

    with pytest.raises(RuntimeError, match="event_emitter not resolved"):
        bootstrap._validate_event_emitter_is_production()


@pytest.mark.asyncio
async def test_validate_event_emitter_raises_when_adapters_none() -> None:
    """Verify that _validate_event_emitter_is_production raises RuntimeError when adapters is None."""
    bootstrap = ProductionApplicationBootstrap()
    bootstrap.adapters = None

    with pytest.raises(RuntimeError, match="event_emitter not resolved"):
        bootstrap._validate_event_emitter_is_production()


@pytest.mark.asyncio
async def test_validate_event_emitter_passes_with_non_capturing_adapter() -> None:
    """Verify that _validate_event_emitter_is_production passes validation with non-capturing emitter."""

    # Create a simple non-capturing mock object (not CapturingMockEventEmitter)
    class MockEventEmitter:
        pass

    bootstrap = ProductionApplicationBootstrap()
    # Manually set adapters with a non-capturing adapter
    bootstrap.adapters = type("Adapters", (), {"event_emitter": MockEventEmitter()})()

    # Should not raise any exception
    bootstrap._validate_event_emitter_is_production()


@pytest.mark.asyncio
async def test_graceful_shutdown_stops_background_loops() -> None:
    """Verify that teardown() stops the real background work cleanly.

    The application is fully event-driven (INV-13): there is NO application-layer
    poll loop. The background work teardown must wind down is:
    1. the agent scheduler consumer loop      -> agent_scheduler.stop()
    2. the adapter-internal board poll loops   -> board adapter close()
    3. in-flight detached event publishes      -> event_bus.drain()  (graceful-
       shutdown window for publish_detached; see event-bus.md §6 / ADR-0001)

    MultiProjectOrchestrator is an admin-query-only service with no loop (INV-13),
    so teardown must NOT try to stop it. This test guards that design: an MPO with
    a stop() present must be left untouched.

    This is a unit test that mocks the services/adapters to avoid requiring full
    production adapter credentials or live infrastructure.
    """

    class MockAgentScheduler:
        """Mock agent scheduler with stop tracking."""

        def __init__(self):
            self.stop_called = False

        async def stop(self):
            self.stop_called = True

    class MockMultiProjectOrchestrator:
        """Admin-query-only service (INV-13). Present to guard that teardown does
        NOT stop it -- there is no loop to stop."""

        def __init__(self):
            self.stop_called = False

        async def stop(self):
            self.stop_called = True

    class MockBoardAdapter:
        """Mock board adapter; close() stops its internal poll loops."""

        def __init__(self):
            self.close_called = False

        async def close(self):
            self.close_called = True

    class MockEventBus:
        """Mock event bus; drain() awaits in-flight detached publishes."""

        def __init__(self):
            self.drain_called = False

        async def drain(self, timeout: float = 10.0):
            self.drain_called = True

        def get_statistics(self):
            return {}

    class MockServices:
        """Mock services container."""

        def __init__(self):
            self.agent_scheduler = MockAgentScheduler()
            self.multi_project_orchestrator = MockMultiProjectOrchestrator()

    class MockAdapters:
        """Mock adapters container (board + no event store)."""

        def __init__(self, board):
            self.board = board
            self.event_store = None

    class MockInfrastructure:
        """Mock infrastructure container (event bus only)."""

        def __init__(self, event_bus):
            self.event_bus = event_bus

    bootstrap = ProductionApplicationBootstrap()

    # Manually set up minimal state for teardown testing
    bootstrap._is_setup = True
    mock_services = MockServices()
    mock_board = MockBoardAdapter()
    mock_bus = MockEventBus()
    bootstrap.services = mock_services
    bootstrap.ports = None
    bootstrap.infrastructure = MockInfrastructure(mock_bus)
    bootstrap.adapters = MockAdapters(mock_board)

    await bootstrap.teardown()

    # The real background work is wound down...
    assert mock_services.agent_scheduler.stop_called, "agent_scheduler.stop() should have been called"
    assert mock_board.close_called, "board adapter close() should stop its internal poll loops"
    assert mock_bus.drain_called, "event_bus.drain() should drain in-flight detached publishes"

    # ...but MPO has no loop and must NOT be stopped (INV-13).
    assert (
        not mock_services.multi_project_orchestrator.stop_called
    ), "MPO is admin-query only (INV-13); teardown must not stop it"

    # Verify state was properly cleaned up
    assert bootstrap.services is None, "Services should be cleared after teardown"
    assert bootstrap._is_setup is False, "Bootstrap should be marked as not set up after teardown"


@pytest.mark.asyncio
async def test_teardown_safe_when_not_setup() -> None:
    """Verify that teardown() is safe to call even if setup was not completed."""
    bootstrap = ProductionApplicationBootstrap()

    # teardown() should not raise even if setup was never called
    await bootstrap.teardown()

    # Verify it's still safe to call again
    await bootstrap.teardown()


@pytest.mark.asyncio
async def test_board_reconciliation_runs_at_bootstrap() -> None:
    """Verify that board reconciliation is invoked during bootstrap Phase 5c.

    This test verifies that _reconcile_board_structures is called and:
    1. Retrieves projects from config_store
    2. Gets board workflow templates for each project
    3. Calls reconcile_board on the board service for each template
    4. Non-fatal - doesn't block bootstrap if reconciliation fails
    """
    from unittest.mock import AsyncMock, MagicMock, patch

    # Create a bootstrap instance with minimal setup
    bootstrap = ProductionApplicationBootstrap()

    # Mock the adapters
    mock_adapters = MagicMock()
    mock_config_store = AsyncMock()
    mock_workflow_config = AsyncMock()
    mock_board_service = AsyncMock()

    bootstrap.adapters = mock_adapters
    bootstrap.adapters.config_store = mock_config_store
    bootstrap.adapters.workflow_config = mock_workflow_config
    bootstrap.adapters.board = mock_board_service

    # Create mock project config
    mock_project_config = MagicMock()
    mock_project_config.id = "proj-1"
    mock_config_store.list_projects = AsyncMock(return_value=[mock_project_config])

    # Create mock board workflow template
    from codetoreum.domain.board_workflow_template import BoardWorkflowTemplate, ColumnTemplate

    mock_column_1 = MagicMock(spec=ColumnTemplate)
    mock_column_1.name = "Backlog"

    mock_column_2 = MagicMock(spec=ColumnTemplate)
    mock_column_2.name = "In Progress"

    mock_template = MagicMock(spec=BoardWorkflowTemplate)
    mock_template.board_id = "board-1"
    mock_template.columns = (mock_column_1, mock_column_2)

    mock_workflow_config.list_board_workflow_templates = AsyncMock(return_value=[mock_template])

    # Mock reconciliation result
    from codetoreum.ports.output.board_service import ReconciliationResult

    mock_result = MagicMock(spec=ReconciliationResult)
    mock_result.columns_added = []
    mock_result.columns_removed = []
    mock_result.columns_renamed = []
    mock_board_service.reconcile_board = AsyncMock(return_value=mock_result)

    # Call the reconciliation method
    await bootstrap._reconcile_board_structures()

    # Verify the flow
    mock_config_store.list_projects.assert_called_once()
    mock_workflow_config.list_board_workflow_templates.assert_called_once_with("proj-1")
    mock_board_service.reconcile_board.assert_called_once()

    # Verify reconcile_board was called with the correct board_id and column config
    call_args = mock_board_service.reconcile_board.call_args
    assert call_args is not None
    board_id, board_config = call_args[0]
    assert board_id == "board-1"
    assert board_config.board_id == "board-1"
    assert board_config.expected_columns == ("Backlog", "In Progress")
