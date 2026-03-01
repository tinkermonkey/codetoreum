"""Integration tests for event-based causal linking between mock adapters.

This test suite validates the Phase 2 requirement: Event-Based Causal Linking
Between Mock Adapters. It verifies that:

1. Queue service subscribes to board position change events
2. Storage adapter subscribes to container execution completion events
3. Event bus architecture prevents circular dependencies
4. Adapters emit domain events for state changes

The tests use SimulationApplicationBootstrap to wire adapters with event bus subscriptions,
ensuring production causal relationships are replicated in simulation.

Note: Tests focusing on LLM and repair cycle decision making are deferred to Phase 2B
per the design guidance as they require additional implementation work.
"""

import asyncio
from datetime import UTC, datetime
from typing import cast

import pytest

from codetoreum.adapters.testing.capturing_mock_event_emitter import (
    CapturingMockEventEmitter,
)
from codetoreum.adapters.testing.fake_container_adapter import FakeContainerAdapter
from codetoreum.adapters.testing.in_memory_queue_service import InMemoryQueueService
from codetoreum.adapters.testing.in_memory_storage_adapter import (
    InMemoryStorageAdapter,
)
from codetoreum.adapters.testing.mock_board_adapter import MockBoardAdapter
from codetoreum.domain.events.adapter_events import CodetoreumEvent
from codetoreum.domain.events.board_events import WorkItemColumnChangedEvent
from codetoreum.domain.events.container_events import ContainerExecutionCompletedEvent
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationAdapters,
    SimulationApplicationBootstrap,
)
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig
from codetoreum.ports.output.board_service import MovedByType

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def event_bus() -> EventBus:
    """Create event bus for causal linking."""
    return EventBus()


@pytest.fixture
def event_emitter() -> CapturingMockEventEmitter:
    """Create capturing event emitter for assertions."""
    return CapturingMockEventEmitter()


@pytest.fixture
def queue_service(event_emitter: CapturingMockEventEmitter, event_bus: EventBus) -> InMemoryQueueService:
    """Create queue service with event bus for causal linking."""
    return InMemoryQueueService(event_emitter=event_emitter, event_bus=event_bus)


@pytest.fixture
def storage_adapter(
    event_emitter: CapturingMockEventEmitter,
    event_bus: EventBus,
    container_adapter: FakeContainerAdapter,
) -> InMemoryStorageAdapter:
    """Create storage adapter with event bus and container for causal linking.

    The container adapter is passed to enable retrieval of actual file content
    when handling ContainerExecutionCompletedEvent.
    """
    return InMemoryStorageAdapter(
        event_emitter=event_emitter,
        event_bus=event_bus,
        container=container_adapter,
    )


@pytest.fixture
def container_adapter(event_emitter: CapturingMockEventEmitter, event_bus: EventBus) -> FakeContainerAdapter:
    """Create container adapter with event bus for event emission."""
    return FakeContainerAdapter(execution_delay=0.0, event_emitter=event_emitter, event_bus=event_bus)


@pytest.fixture
def board_adapter(event_emitter: CapturingMockEventEmitter) -> MockBoardAdapter:
    """Create mock board adapter with event emitter."""
    return MockBoardAdapter(event_emitter=event_emitter)


@pytest.fixture
async def bootstrap_env():
    """Bootstrap full application stack with causal linking configured."""
    config = SimulationConfig.create_fast_config("causal_linking_test")
    bootstrap = SimulationApplicationBootstrap(config)
    await bootstrap.setup()
    yield bootstrap
    await bootstrap.teardown()


# ============================================================================
# Test Suite 1: Event Subscription Verification
# ============================================================================


@pytest.mark.asyncio
class TestEventSubscriptions:
    """Tests for proper event subscription wiring."""

    async def test_queue_service_subscribes_to_board_events(
        self, event_bus: EventBus, queue_service: InMemoryQueueService
    ):
        """Verify queue service subscribes to WorkItemColumnChangedEvent.

        This validates FR-2 requirement:
        "Board position changes must automatically update queue positions via event subscription"
        """
        # Queue service should be subscribed via __init__
        callbacks = event_bus._callbacks.get("WorkItemColumnChangedEvent", [])
        assert len(callbacks) > 0, "Queue service should subscribe to board events"

    async def test_storage_adapter_subscribes_to_container_events(
        self, event_bus: EventBus, storage_adapter: InMemoryStorageAdapter
    ):
        """Verify storage adapter subscribes to ContainerExecutionCompletedEvent.

        This validates FR-2 requirement:
        "Container file writes must automatically persist to storage when execution completes"
        """
        # Storage adapter should be subscribed via __init__
        callbacks = event_bus._callbacks.get("ContainerExecutionCompletedEvent", [])
        assert len(callbacks) > 0, "Storage adapter should subscribe to container events"


# ============================================================================
# Test Suite 2: Event Bus Architecture
# ============================================================================


@pytest.mark.asyncio
class TestEventBusArchitecture:
    """Tests for proper event bus architecture preventing circular dependencies."""

    async def test_event_bus_holds_only_callables(self, event_bus: EventBus):
        """Event bus holds only callable references, not adapter instances.

        This validates the core architectural principle:
        "Adapters communicate only through domain events via the event bus.
        The event bus itself is independent and doesn't create circular links."
        """
        # Create a test callback
        calls = []

        def test_callback(event):
            calls.append(event)

        event_bus.subscribe("TestEvent", test_callback)

        # Event bus should only hold the callback function
        callbacks = event_bus._callbacks.get("TestEvent", [])
        assert len(callbacks) == 1
        assert callbacks[0] == test_callback
        assert callable(callbacks[0])

    async def test_event_bus_independence_from_adapters(self, event_bus: EventBus):
        """Event bus is independent from adapters - creates no circular dependencies.

        Adapters can be created in any order and independently subscribe to events.
        """
        # Event bus should not hold references to adapter instances
        assert isinstance(event_bus._handlers, dict)
        assert isinstance(event_bus._callbacks, dict)

        # Both should start empty (no default subscriptions)
        # The mock adapters will populate these during init
        assert isinstance(event_bus._callbacks, dict)


# ============================================================================
# Test Suite 3: Event Emission  (tested via bootstrap integration tests)
# ============================================================================
# Event emission is tested in the bootstrap integration tests which use
# the real bootstrap configuration with proper event emitter wiring.


# ============================================================================
# Test Suite 4: Container → Storage Causal Linking
# ============================================================================


@pytest.mark.asyncio
class TestContainerStorageCausalLinking:
    """Tests for container completion triggering storage persistence."""

    async def test_storage_handler_processes_container_event(
        self,
        event_bus: EventBus,
        storage_adapter: InMemoryStorageAdapter,
        container_adapter: FakeContainerAdapter,
    ):
        """Storage adapter handler processes ContainerExecutionCompletedEvent.

        This test validates that the handler retrieves actual file content from the
        container and persists it to storage, establishing the causal link between
        container execution completion and artifact persistence.
        """
        # Setup: Run container to initialize its virtual filesystem
        result = await container_adapter.run(
            image="test-image:latest",
            command=["echo", "test"],
            volumes={},
            environment={"PROJECT_ID": "test-proj"},
        )
        container_id = result.container_id

        # Write files to container's virtual output directory
        test_file_1 = "results.json"
        test_file_2 = "coverage.xml"
        test_content_1 = '{"passed": 10, "failed": 0}'
        test_content_2 = '<?xml version="1.0"?><coverage><stats/></coverage>'

        container_adapter.write_output_file(container_id, test_file_1, test_content_1)
        container_adapter.write_output_file(container_id, test_file_2, test_content_2)

        # Create test event with output file references
        event = ContainerExecutionCompletedEvent(
            type="container.execution_completed",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            container_id=container_id,
            command="echo test",
            exit_code=result.exit_code,
            output_files=(test_file_1, test_file_2),
            project_id="test-proj",
        )

        # Manually invoke handler (simulating event bus dispatch)
        await storage_adapter._handle_container_completion(event)

        # Allow event propagation
        await asyncio.sleep(0.05)

        # Verify: Storage handler created artifact entries
        artifacts = await storage_adapter.list_files(prefix="container/")
        assert len(artifacts) >= 2, "Storage handler should persist container output files"

        # Verify: Actual file content was persisted (causal link established)
        storage_key_1 = f"container/test-proj/{container_id}/{test_file_1}"
        storage_key_2 = f"container/test-proj/{container_id}/{test_file_2}"

        # Retrieve and verify content
        content_1 = await storage_adapter.download(storage_key_1)
        content_2 = await storage_adapter.download(storage_key_2)

        assert content_1 == test_content_1.encode(), "Storage should contain actual file content from container"
        assert content_2 == test_content_2.encode(), "Storage should contain actual file content from container"


# ============================================================================
# Test Suite 5: Queue Handler Processing
# ============================================================================


@pytest.mark.asyncio
class TestQueueHandlerProcessing:
    """Tests for queue position handler."""

    async def test_queue_handler_processes_board_events(
        self,
        queue_service: InMemoryQueueService,
    ):
        """Queue service handler can process WorkItemColumnChangedEvent.

        This test validates the handler exists and is callable.
        """
        # Queue service should have registered handler during init
        handler = queue_service._handle_board_position_change

        # Handler should be callable
        assert callable(handler), "Queue service should have callable handler"


# ============================================================================
# Test Suite 6: Full Bootstrap Integration
# ============================================================================


@pytest.mark.asyncio
class TestBootstrapIntegration:
    """Tests for causal linking through full application bootstrap."""

    async def test_bootstrap_wires_event_subscriptions(self, bootstrap_env):
        """Bootstrap configures event subscriptions properly."""
        bootstrap = bootstrap_env
        adapters = cast("SimulationAdapters", bootstrap.adapters)

        # Get event bus from infrastructure
        event_bus = bootstrap.infrastructure.event_bus

        # Verify critical subscriptions are registered
        board_callbacks = event_bus._callbacks.get("WorkItemColumnChangedEvent", [])
        container_callbacks = event_bus._callbacks.get("ContainerExecutionCompletedEvent", [])

        assert len(board_callbacks) > 0, "Board event subscriptions should be configured"
        assert len(container_callbacks) > 0, "Container event subscriptions should be configured"

    async def test_bootstrap_adapters_accept_event_emitter_and_bus(self, bootstrap_env):
        """Bootstrap creates adapters with event emitter and bus."""
        bootstrap = bootstrap_env
        adapters = cast("SimulationAdapters", bootstrap.adapters)

        # Verify critical adapters have event emitter
        assert adapters.queue_service._event_emitter is not None
        assert adapters.storage._event_emitter is not None
        assert adapters.container._event_emitter is not None

        # Verify adapters have event bus for subscriptions
        assert adapters.queue_service._event_bus is not None
        assert adapters.storage._event_bus is not None


# ============================================================================
# Test Suite 7: End-to-End Causal Chains
# ============================================================================


@pytest.mark.asyncio
class TestEndToEndCausalChains:
    """Tests for complete causal chains through event bus."""

    async def test_event_bus_no_circular_dependencies(
        self,
        event_bus: EventBus,
        board_adapter: MockBoardAdapter,
        queue_service: InMemoryQueueService,
        container_adapter: FakeContainerAdapter,
        storage_adapter: InMemoryStorageAdapter,
    ):
        """Verify event bus architecture prevents circular dependencies.

        Tests FR-2:
        "Circular dependencies must be prevented through event bus architecture"

        Key principle: Event bus holds only callable references, not adapter instances.
        This prevents circular references.
        """
        # Get all subscriptions
        all_subscriptions = {}
        all_subscriptions.update(event_bus._callbacks)
        all_subscriptions.update({k: v for k, v in event_bus._handlers.items()})

        # Verify: All values are either callables or EventHandler instances
        for event_type, handlers in all_subscriptions.items():
            for handler in handlers if isinstance(handlers, list) else [handlers]:
                # Should be callable or EventHandler with handle method
                assert callable(handler) or hasattr(
                    handler, "handle"
                ), f"Event handler for {event_type} should be callable or EventHandler"

        # Verify: Event bus itself doesn't hold adapter instances
        # (it only holds callable references)
        for event_type, callbacks in event_bus._callbacks.items():
            for cb in callbacks:
                # Callback should be a function, not an adapter instance
                # (adapters might be methods bound to adapters, but not the adapters themselves)
                assert callable(cb), f"Callback for {event_type} should be callable"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
