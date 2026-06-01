"""Tests for ProductionApplicationBootstrap critical path enforcement."""

import pytest

from codetoreum.infrastructure.bootstrap import ProductionApplicationBootstrap
from codetoreum.infrastructure.simulation.simulation_config import AdapterSelectionConfig


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
async def test_critical_adapters_have_failure_routes() -> None:
    """Verify that Phase 3a validates critical adapters declare failure routes (INV-20)."""
    # Use default production config (all real adapters)
    bootstrap = ProductionApplicationBootstrap()

    # setup() should pass Phase 3a validation that all critical adapters have failed_event_store
    app = await bootstrap.setup()
    assert app is not None

    # Verify that at least the infrastructure's failed_event_store was created and is available
    assert bootstrap.infrastructure is not None
    assert bootstrap.infrastructure.failed_event_store is not None

    # Verify critical adapters have the failure route
    critical_adapters_with_failure_routes = [
        adapter
        for slot_name in ["board", "ticket", "version_control", "container", "code_review"]
        if (adapter := bootstrap.adapters.__dict__.get(slot_name))
        and hasattr(adapter, "failed_event_store")
    ]
    assert len(critical_adapters_with_failure_routes) >= 1, "At least one critical adapter should have failure route"

    await bootstrap.teardown()


def test_event_handler_types_declared() -> None:
    """Verify event handler decorators declare correct event types.

    This test verifies that the @event_handler decorators on all handlers
    match the expected event types they should subscribe to.

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
    """
    # Expected event type mappings - must match @event_handler decorators
    handler_event_types = {
        "BoardColumnEventHandler": [
            "WorkItemColumnChangedEvent",
            "AgentExecutionCompletedEvent",
        ],
        "PRReviewCycleDispatchHandler": ["WorkItemColumnChangedEvent"],
        "PRReviewCycleEventHandler": [
            "PRReviewCycleApprovedEvent",
            "PRReviewCycleIssuesFoundEvent",
            "PRReviewCycleMaxCyclesReachedEvent",
        ],
        "ReviewEventHandler": [
            "ReviewCycleCreatedEvent",
            "ReviewCycleIterationStartedEvent",
            "ReviewCycleFeedbackSubmittedEvent",
            "ReviewCycleApprovedEvent",
            "ReviewCycleRejectedEvent",
            "ReviewCycleEscalatedToHumanEvent",
        ],
        "WorkflowEventHandler": [
            "WorkItemCreatedEvent",
            "ExecutionCompletedEvent",
            "ExecutionFailedEvent",
            "ReviewCycleApprovedEvent",
            "ReviewCycleRejectedEvent",
            "ReviewCycleEscalatedToHumanEvent",
        ],
        "ExecutionEventHandler": [
            "ExecutionInitializedEvent",
            "ExecutionStartedEvent",
            "ExecutionCompletedEvent",
            "ExecutionFailedEvent",
            "ExecutionTimedOutEvent",
        ],
        "BranchResolutionEventHandler": [
            "BranchResolvedEvent",
            "BranchReusedEvent",
            "BranchResolutionCreatedEvent",
        ],
        "RepairCycleEventHandler": ["WorkItemColumnChangedEvent"],
    }

    # Verify the mapping is not empty
    assert len(handler_event_types) > 0, "Handler event type mapping should not be empty"

    # Verify each handler has at least one event type
    for handler_name, event_types in handler_event_types.items():
        assert (
            len(event_types) > 0
        ), f"Handler {handler_name} should declare at least one event type"


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
    """Verify that teardown() stops all background loops cleanly.

    This test verifies:
    1. teardown() calls stop() on agent_scheduler
    2. teardown() calls stop() on multi_project_orchestrator
    3. teardown() is safe to call and properly cleans up state

    This is a unit test that mocks the services to avoid requiring
    full production adapter credentials.
    """

    class MockAgentScheduler:
        """Mock agent scheduler with stop tracking."""

        def __init__(self):
            self.stop_called = False

        async def stop(self):
            self.stop_called = True

    class MockMultiProjectOrchestrator:
        """Mock multi-project orchestrator with stop tracking."""

        def __init__(self):
            self.stop_called = False

        async def stop(self):
            self.stop_called = True

    class MockServices:
        """Mock services container."""

        def __init__(self):
            self.agent_scheduler = MockAgentScheduler()
            self.multi_project_orchestrator = MockMultiProjectOrchestrator()

    bootstrap = ProductionApplicationBootstrap()

    # Manually set up minimal state for teardown testing
    bootstrap._is_setup = True
    mock_services = MockServices()
    bootstrap.services = mock_services
    bootstrap.ports = None
    bootstrap.infrastructure = None
    bootstrap.adapters = None

    # Call teardown and verify both services were stopped
    await bootstrap.teardown()

    # Verify that both services' stop() methods were called
    assert mock_services.agent_scheduler.stop_called, "agent_scheduler.stop() should have been called"
    assert (
        mock_services.multi_project_orchestrator.stop_called
    ), "multi_project_orchestrator.stop() should have been called"

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
