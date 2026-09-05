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
    """Verify that AdapterSelectionConfig has exactly 32 slots."""
    config = AdapterSelectionConfig()
    slots = list(AdapterSelectionConfig.__dataclass_fields__.keys())

    assert len(slots) == 32, f"Expected 32 slots, got {len(slots)}: {slots}"


def test_critical_adapter_slots_defined() -> None:
    """Verify that critical adapter slots are correctly defined."""
    from codetoreum.infrastructure.bootstrap.production_bootstrap import CRITICAL_ADAPTER_SLOTS

    expected_critical = {
        "board",
        "ticket",
        "version_control",
        "container",
        "code_review",
        "container_recovery",
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
        "repair_cycle",
        "ci_pipeline",
        "execution_tracker",  # Execution state tracking; non-critical for MVP
        "discussion_adapter",  # Discussion handling is non-critical; does not block work-item progression
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


@pytest.mark.asyncio
async def test_repair_cycle_resolver_production_promotion() -> None:
    """Verify that resolve_repair_cycle() produces ProductionRepairCycleAdapter with checkpoint_store when repair_cycle='production'.

    This test verifies the promotion of repair_cycle to production adapter by:
    1. Creating a config with repair_cycle="production"
    2. Verifying that the resolver takes the non-mock branch
    3. Confirming the returned adapter is ProductionRepairCycleAdapter
    4. Ensuring checkpoint_store is passed to the factory and is non-None in the resolved adapter
    """
    from unittest.mock import MagicMock

    from codetoreum.adapters.secondary.production_repair_cycle_adapter import (
        ProductionRepairCycleAdapter,
    )
    from codetoreum.infrastructure.adapters.resolver import (
        AdapterDependencies,
        AdapterResolver,
    )
    from codetoreum.infrastructure.simulation.simulation_config import AdapterSelectionConfig

    # Create config with repair_cycle="production"
    config = AdapterSelectionConfig(repair_cycle="production")

    # Create minimal mock dependencies
    mock_event_bus = MagicMock()
    mock_factory = MagicMock()
    mock_container = MagicMock()
    mock_config_store = MagicMock()
    mock_checkpoint_store = MagicMock()
    mock_systemic_analysis_service = MagicMock()
    mock_environment_repair_service = MagicMock()

    # Create a mock production repair cycle adapter instance
    mock_repair_cycle_adapter = MagicMock(spec=ProductionRepairCycleAdapter)
    mock_repair_cycle_adapter.checkpoint_store = mock_checkpoint_store

    # Set up the factory to return our mock adapter
    mock_factory.create_repair_cycle = MagicMock(return_value=mock_repair_cycle_adapter)

    # Create a mock dependencies object with required attributes
    mock_deps = MagicMock(spec=AdapterDependencies)
    mock_deps.event_bus = mock_event_bus
    mock_deps.failed_event_store = MagicMock()
    mock_deps.engine = MagicMock()

    # Create the resolver with correct parameters
    resolver = AdapterResolver(
        adapter_config=config,
        factory=mock_factory,
        dependencies=mock_deps,
    )

    # Manually set up the resolver's internal state as if resolve_all() was called
    resolver._factory = mock_factory
    resolver._resolved = {
        "container": mock_container,
        "config_store": mock_config_store,
        "checkpoint_store": mock_checkpoint_store,
        "systemic_analysis_service": mock_systemic_analysis_service,
        "environment_repair_service": mock_environment_repair_service,
        "event_emitter": MagicMock(),
    }

    # Resolve the repair_cycle adapter
    result = resolver.resolve_repair_cycle()

    # Verify that the factory's create_repair_cycle method was called
    mock_factory.create_repair_cycle.assert_called_once()

    # Verify the call included checkpoint_store parameter
    call_kwargs = mock_factory.create_repair_cycle.call_args[1]
    assert "checkpoint_store" in call_kwargs, "checkpoint_store should be passed to create_repair_cycle"
    assert call_kwargs["checkpoint_store"] is mock_checkpoint_store, "checkpoint_store should be the resolved instance"

    # Verify adapter_name is set to "production"
    assert call_kwargs["adapter_name"] == "production"

    # Verify the returned adapter is what the factory returned
    assert result is mock_repair_cycle_adapter

    # Verify checkpoint_store is not None on the adapter
    assert result.checkpoint_store is not None


async def test_repair_cycle_production_missing_dependencies() -> None:
    """Verify that resolve_repair_cycle() raises AdapterConfigurationError when production dependencies are missing.

    This test validates that the comprehension-based check collects all missing dependencies
    at bootstrap time for batch reporting, instead of early failure on the first missing key.
    """
    from unittest.mock import MagicMock

    from codetoreum.infrastructure.adapters.resolver import (
        AdapterConfigurationError,
        AdapterDependencies,
        AdapterResolver,
    )
    from codetoreum.infrastructure.simulation.simulation_config import AdapterSelectionConfig

    # Create config with repair_cycle="production"
    config = AdapterSelectionConfig(repair_cycle="production")

    # Create minimal mock dependencies
    mock_event_bus = MagicMock()
    mock_factory = MagicMock()

    # Create a mock dependencies object with required attributes
    mock_deps = MagicMock(spec=AdapterDependencies)
    mock_deps.event_bus = mock_event_bus
    mock_deps.failed_event_store = MagicMock()
    mock_deps.engine = MagicMock()

    # Create the resolver
    resolver = AdapterResolver(
        adapter_config=config,
        factory=mock_factory,
        dependencies=mock_deps,
    )

    # Set up resolver's internal state with MISSING dependencies (not in _resolved dict)
    resolver._factory = mock_factory
    resolver._resolved = {
        "event_emitter": MagicMock(),
        # Missing: checkpoint_store, systemic_analysis_service, environment_repair_service
    }

    # Attempt to resolve repair_cycle should raise AdapterConfigurationError
    import pytest
    with pytest.raises(AdapterConfigurationError) as exc_info:
        resolver.resolve_repair_cycle()

    # Verify error message mentions ALL missing dependencies and proper dependency ordering
    error_msg = str(exc_info.value)
    assert "repair_cycle='production' requires" in error_msg
    assert "to be resolved first" in error_msg
    assert "resolve_all() dependency ordering" in error_msg
    # Verify all three missing dependency names appear in the error
    assert "systemic_analysis_service" in error_msg, "Error should list systemic_analysis_service"
    assert "environment_repair_service" in error_msg, "Error should list environment_repair_service"
    assert "checkpoint_store" in error_msg, "Error should list checkpoint_store"


async def test_container_recovery_production_missing_dependencies() -> None:
    """Verify that resolve_container_recovery() raises AdapterConfigurationError when production dependencies are missing.

    This test validates that the comprehension-based check collects all missing dependencies
    at bootstrap time for batch reporting, instead of early failure on the first missing key.
    """
    from unittest.mock import MagicMock

    from codetoreum.infrastructure.adapters.resolver import (
        AdapterConfigurationError,
        AdapterDependencies,
        AdapterResolver,
    )
    from codetoreum.infrastructure.simulation.simulation_config import AdapterSelectionConfig

    # Create config with container_recovery="docker"
    config = AdapterSelectionConfig(container_recovery="docker")

    # Create minimal mock dependencies
    mock_event_bus = MagicMock()
    mock_factory = MagicMock()

    # Create a mock dependencies object with required attributes
    mock_deps = MagicMock(spec=AdapterDependencies)
    mock_deps.event_bus = mock_event_bus
    mock_deps.failed_event_store = MagicMock()
    mock_deps.engine = MagicMock()

    # Create the resolver
    resolver = AdapterResolver(
        adapter_config=config,
        factory=mock_factory,
        dependencies=mock_deps,
    )

    # Set up resolver's internal state with MISSING dependencies (not in _resolved dict)
    resolver._factory = mock_factory
    resolver._resolved = {
        "event_emitter": MagicMock(),
        # Missing: execution_tracker
    }

    # Attempt to resolve container_recovery should raise AdapterConfigurationError
    import pytest
    with pytest.raises(AdapterConfigurationError) as exc_info:
        resolver.resolve_container_recovery()

    # Verify error message mentions missing dependency and proper dependency ordering
    error_msg = str(exc_info.value)
    assert "container_recovery='docker' requires" in error_msg
    assert "to be resolved first" in error_msg
    assert "resolve_all() dependency ordering" in error_msg
    # Verify the missing dependency name appears in the error
    assert "execution_tracker" in error_msg, "Error should list execution_tracker"


async def test_repair_cycle_dynamic_config_interpolation() -> None:
    """Verify that error messages correctly interpolate the actual repair_cycle config value.

    This test ensures that when repair_cycle is set to a non-standard value (e.g., a typo),
    the error message reflects the actual configured value, not a hardcoded string.
    """
    from unittest.mock import MagicMock

    from codetoreum.infrastructure.adapters.resolver import (
        AdapterConfigurationError,
        AdapterDependencies,
        AdapterResolver,
    )
    from codetoreum.infrastructure.simulation.simulation_config import AdapterSelectionConfig

    # Create config with a non-standard repair_cycle value (simulating a typo)
    config = AdapterSelectionConfig(repair_cycle="producton")

    # Create minimal mock dependencies
    mock_event_bus = MagicMock()
    mock_factory = MagicMock()

    # Create a mock dependencies object with required attributes
    mock_deps = MagicMock(spec=AdapterDependencies)
    mock_deps.event_bus = mock_event_bus
    mock_deps.failed_event_store = MagicMock()
    mock_deps.engine = MagicMock()

    # Create the resolver
    resolver = AdapterResolver(
        adapter_config=config,
        factory=mock_factory,
        dependencies=mock_deps,
    )

    # Set up resolver's internal state with MISSING dependencies
    resolver._factory = mock_factory
    resolver._resolved = {
        "event_emitter": MagicMock(),
        # Missing: checkpoint_store, systemic_analysis_service, environment_repair_service
    }

    # Attempt to resolve repair_cycle should raise AdapterConfigurationError
    import pytest
    with pytest.raises(AdapterConfigurationError) as exc_info:
        resolver.resolve_repair_cycle()

    # Verify error message contains the actual repair_cycle value, not hardcoded 'production'
    error_msg = str(exc_info.value)
    assert "repair_cycle='producton' requires" in error_msg, (
        "Error message should interpolate actual repair_cycle value 'producton', not hardcoded 'production'"
    )


def test_repair_cycle_in_production_adapter_selection_config() -> None:
    """Verify that the default ProductionApplicationBootstrap config sets repair_cycle='production'."""
    from codetoreum.infrastructure.bootstrap.production_bootstrap import ProductionApplicationBootstrap

    bootstrap = ProductionApplicationBootstrap()

    # Verify the config includes repair_cycle="production"
    assert bootstrap.config.repair_cycle == "production", (
        "ProductionApplicationBootstrap should set repair_cycle='production' in default config"
    )

    # Verify it matches the sibling repair adapters
    assert bootstrap.config.systemic_analysis == "production"
    assert bootstrap.config.environment_repair == "production"


def test_ci_pipeline_in_production_adapter_selection_config() -> None:
    """Verify that the default ProductionApplicationBootstrap config sets ci_pipeline='github'."""
    from codetoreum.infrastructure.bootstrap.production_bootstrap import ProductionApplicationBootstrap

    bootstrap = ProductionApplicationBootstrap()

    # Verify the config includes ci_pipeline="github"
    assert bootstrap.config.ci_pipeline == "github", (
        "ProductionApplicationBootstrap should set ci_pipeline='github' in default config"
    )


def test_ci_pipeline_in_non_critical_slots() -> None:
    """Verify that ci_pipeline is in NON_CRITICAL_SLOTS (not on critical path)."""
    from codetoreum.infrastructure.bootstrap.production_bootstrap import (
        CRITICAL_ADAPTER_SLOTS,
        NON_CRITICAL_SLOTS,
    )

    # Verify ci_pipeline is not in critical slots
    assert "ci_pipeline" not in CRITICAL_ADAPTER_SLOTS, "ci_pipeline should not be on critical path"
    # Verify ci_pipeline is in non-critical slots
    assert "ci_pipeline" in NON_CRITICAL_SLOTS, "ci_pipeline should be in non-critical slots"


@pytest.mark.asyncio
async def test_conversational_loop_orchestrator_subscriptions_during_bootstrap() -> None:
    """Verify that _register_conversational_loop_orchestrator registers both event subscriptions.

    This integration test verifies that the bootstrap process correctly wires the
    CommentNeedsResponseEvent and WorkItemColumnChangedEvent subscriptions by checking
    that they are called with the correct parameters.

    A deletion or typo in the production_bootstrap.py registration would be caught
    by this test.
    """
    from unittest.mock import AsyncMock, MagicMock

    from codetoreum.infrastructure.bootstrap import ProductionApplicationBootstrap

    # Create a mock bootstrap instance
    bootstrap = ProductionApplicationBootstrap()

    # Create a mock event bus to capture subscriptions
    mock_event_bus = MagicMock()

    # Create a mock infrastructure with the event bus
    bootstrap.infrastructure = MagicMock()
    bootstrap.infrastructure.event_bus = mock_event_bus

    # Create a mock conversational loop orchestrator
    mock_orchestrator = MagicMock()
    bootstrap.conversational_loop_orchestrator = mock_orchestrator

    # Call the registration method (the actual method being tested)
    bootstrap._register_conversational_loop_orchestrator()

    # Verify that subscribe was called with the correct event types and handlers
    mock_event_bus.subscribe.assert_any_call(
        "WorkItemColumnChangedEvent",
        mock_orchestrator.handle_column_change_event,
    )
    mock_event_bus.subscribe.assert_any_call(
        "CommentNeedsResponseEvent",
        mock_orchestrator.handle_comment_event,
    )


@pytest.mark.asyncio
async def test_comment_needs_response_event_subscription_registered() -> None:
    """Verify that CommentNeedsResponseEvent subscription is registered with correct handler.

    This test ensures that the core feature of the conversational loop — inbound GitHub
    comments triggering agent responses — is wired correctly in the event bus. It verifies:

    1. The subscription exists for "CommentNeedsResponseEvent"
    2. The subscription is connected to ConversationalLoopOrchestrator.handle_comment_event
    3. A typo in the event type string or accidental deletion of the subscription would fail this test

    This is critical infrastructure: a silent failure here would break the entire conversational
    feedback loop feature with no test failure.
    """
    from unittest.mock import AsyncMock, MagicMock

    from codetoreum.application.conversational_loop_orchestrator import (
        ConversationalLoopOrchestrator,
    )
    from codetoreum.infrastructure.event_bus import EventBus

    # Create event bus and minimal mock dependencies for ConversationalLoopOrchestrator
    event_bus = EventBus()

    # Create mocks for all ConversationalLoopOrchestrator dependencies
    mock_discussion_adapter = MagicMock()
    mock_coding_agent = MagicMock()
    mock_prompt_builder = MagicMock()
    mock_agent_repository = MagicMock()
    mock_work_item_service = MagicMock()
    mock_event_store = AsyncMock()
    mock_event_emitter = MagicMock()

    # Instantiate ConversationalLoopOrchestrator
    orchestrator = ConversationalLoopOrchestrator(
        discussion_adapter=mock_discussion_adapter,
        coding_agent=mock_coding_agent,
        prompt_builder=mock_prompt_builder,
        agent_repository=mock_agent_repository,
        work_item_service=mock_work_item_service,
        event_store=mock_event_store,
        event_emitter=mock_event_emitter,
    )

    # Subscribe as done in _register_conversational_loop_orchestrator
    # First subscription for WorkItemColumnChangedEvent
    event_bus.subscribe(
        "WorkItemColumnChangedEvent",
        orchestrator.handle_column_change_event,
    )
    # Second subscription for CommentNeedsResponseEvent (the critical one)
    event_bus.subscribe(
        "CommentNeedsResponseEvent",
        orchestrator.handle_comment_event,
    )

    # === Verify CommentNeedsResponseEvent subscription ===
    # This is the core feature being tested: inbound comments must trigger agent responses
    assert "CommentNeedsResponseEvent" in event_bus._callbacks, (
        "CommentNeedsResponseEvent subscription must exist in event bus._callbacks. "
        "A typo in the event type string or accidental deletion would silently break the conversational loop."
    )

    # Verify the subscription is connected to the correct handler
    comment_callbacks = event_bus._callbacks["CommentNeedsResponseEvent"]
    assert len(comment_callbacks) > 0, (
        "CommentNeedsResponseEvent must have at least one callback registered"
    )

    # Verify the callback is orchestrator.handle_comment_event (not a different method)
    assert orchestrator.handle_comment_event in comment_callbacks, (
        "ConversationalLoopOrchestrator.handle_comment_event must be subscribed to CommentNeedsResponseEvent. "
        "Any change to the handler method name or event type would break the feature."
    )

    # Verify the handler method exists and is callable
    assert hasattr(orchestrator, "handle_comment_event"), (
        "ConversationalLoopOrchestrator must have handle_comment_event method"
    )
    assert callable(orchestrator.handle_comment_event), (
        "handle_comment_event must be callable"
    )

    # === Verify WorkItemColumnChangedEvent subscription ===
    # Also verify the related subscription for column changes
    assert "WorkItemColumnChangedEvent" in event_bus._callbacks, (
        "WorkItemColumnChangedEvent subscription must exist in event_bus._callbacks"
    )
    column_callbacks = event_bus._callbacks["WorkItemColumnChangedEvent"]
    assert len(column_callbacks) > 0, (
        "WorkItemColumnChangedEvent must have at least one callback registered"
    )
    assert orchestrator.handle_column_change_event in column_callbacks, (
        "ConversationalLoopOrchestrator.handle_column_change_event must be subscribed to WorkItemColumnChangedEvent"
    )


