"""
Tests for SimulationApplicationBootstrap PR #401 fixes.

Verifies:
1. failed_event_store is typed as IFailedEventStore port interface, not concrete adapter
2. teardown() properly re-raises exceptions to notify callers
3. DLQ retry handler raises exception for unknown event types instead of silent deletion
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codetoreum.adapters.testing.in_memory_failed_event_store import (
    InMemoryFailedEventStore,
)
from codetoreum.infrastructure.simulation.bootstrap import SimulationApplicationBootstrap
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig
from codetoreum.ports.output.failed_event_store import IFailedEventStore


@pytest.mark.asyncio
class TestBootstrapFailedEventStoreTyping:
    """Tests for failed_event_store port interface typing (Fix #1)."""

    async def test_failed_event_store_typed_as_port_interface(self) -> None:
        """Verify failed_event_store is typed as IFailedEventStore, not concrete adapter."""
        config = SimulationConfig.create_fast_config("test")
        bootstrap = SimulationApplicationBootstrap(config)

        await bootstrap.setup()

        # Verify infrastructure is created
        assert bootstrap.infrastructure is not None

        # Verify failed_event_store exists
        assert bootstrap.infrastructure.failed_event_store is not None

        # Verify it's an instance of IFailedEventStore (the port interface)
        failed_event_store = bootstrap.infrastructure.failed_event_store
        assert isinstance(failed_event_store, IFailedEventStore)

        # Simulation uses InMemoryFailedEventStore, not the production DLQ adapter
        assert isinstance(failed_event_store, InMemoryFailedEventStore)

        # Verify port interface methods are available
        assert hasattr(failed_event_store, "add_failed_event")
        assert hasattr(failed_event_store, "get_stats")
        assert hasattr(failed_event_store, "list_events")
        assert hasattr(failed_event_store, "get_event")
        assert hasattr(failed_event_store, "remove_event")
        assert hasattr(failed_event_store, "clear")

        await bootstrap.teardown()

    async def test_failed_event_store_lifecycle_methods_accessible(self) -> None:
        """Verify lifecycle methods are accessible through adapter instance check."""
        config = SimulationConfig.create_fast_config("test")
        bootstrap = SimulationApplicationBootstrap(config)

        await bootstrap.setup()

        # Verify infrastructure-specific lifecycle methods are accessible
        failed_event_store = bootstrap.infrastructure.failed_event_store
        assert isinstance(failed_event_store, InMemoryFailedEventStore)

        # These test-utility methods are available on InMemoryFailedEventStore
        assert hasattr(failed_event_store, "mark_retry_succeeded")
        assert hasattr(failed_event_store, "mark_retry_failed")

        await bootstrap.teardown()


@pytest.mark.asyncio
class TestBootstrapTeardownExceptionHandling:
    """Tests for teardown exception re-raising (Fix #2)."""

    async def test_teardown_reraises_engine_stop_failure(self) -> None:
        """Verify teardown re-raises exceptions from engine.stop()."""
        config = SimulationConfig.create_fast_config("test")
        bootstrap = SimulationApplicationBootstrap(config)

        await bootstrap.setup()

        # Mock the engine to raise an exception on stop
        with patch.object(bootstrap._engine, "stop", side_effect=RuntimeError("Mock engine failure")):
            # Teardown should re-raise the exception
            with pytest.raises(RuntimeError, match="Mock engine failure"):
                await bootstrap.teardown()

            # _is_setup should NOT be cleared because teardown didn't complete
            assert bootstrap._is_setup is True

    async def test_teardown_reraises_dlq_stop_failure(self) -> None:
        """Verify teardown re-raises exceptions during teardown steps.

        Simulation uses InMemoryFailedEventStore which has no stop_retry_processor.
        We verify the general teardown re-raise behaviour by patching engine.stop,
        which is a teardown step that does exist in the simulation bootstrap.
        """
        config = SimulationConfig.create_fast_config("test")
        bootstrap = SimulationApplicationBootstrap(config)

        await bootstrap.setup()

        # Verify simulation uses InMemoryFailedEventStore (not the production DLQ adapter)
        failed_event_store = bootstrap.infrastructure.failed_event_store
        assert isinstance(failed_event_store, InMemoryFailedEventStore)

        # Patch engine.stop to simulate a teardown failure
        with patch.object(bootstrap._engine, "stop", side_effect=RuntimeError("Mock teardown stop failure")):
            # Teardown should re-raise the exception
            with pytest.raises(RuntimeError, match="Mock teardown stop failure"):
                await bootstrap.teardown()

            # _is_setup should NOT be cleared because teardown didn't complete
            assert bootstrap._is_setup is True

    async def test_teardown_is_noop_when_not_setup(self) -> None:
        """Verify teardown is safe when bootstrap was never set up."""
        config = SimulationConfig.create_fast_config("test")
        bootstrap = SimulationApplicationBootstrap(config)

        # Should not raise even though we're calling teardown without setup
        await bootstrap.teardown()

        # _is_setup should still be False
        assert bootstrap._is_setup is False

    async def test_teardown_state_preserved_on_failure(self) -> None:
        """Verify teardown doesn't clear state if an exception occurs."""
        config = SimulationConfig.create_fast_config("test")
        bootstrap = SimulationApplicationBootstrap(config)

        await bootstrap.setup()

        # Save references to check if they're cleared
        original_adapters = bootstrap.adapters
        original_infrastructure = bootstrap.infrastructure
        original_engine = bootstrap._engine

        # Mock engine to fail during stop
        with patch.object(bootstrap._engine, "stop", side_effect=RuntimeError("Mock stop failure")):
            with pytest.raises(RuntimeError):
                await bootstrap.teardown()

            # State should NOT be cleared when teardown fails
            assert bootstrap.adapters is original_adapters
            assert bootstrap.infrastructure is original_infrastructure
            assert bootstrap._engine is original_engine
            assert bootstrap._is_setup is True


@pytest.mark.asyncio
class TestBootstrapDLQRetryHandlerUnknownEventType:
    """Tests for DLQ retry handler unknown event type handling (Fix #3)."""

    async def test_dlq_retry_handler_raises_on_unknown_event_type(self) -> None:
        """Verify DLQ retry handler raises exception for unknown event types."""
        config = SimulationConfig.create_fast_config("test")
        bootstrap = SimulationApplicationBootstrap(config)

        await bootstrap.setup()

        # Create the retry handler
        retry_handler = bootstrap._create_dlq_retry_handler()

        # Call with unknown event type - should raise ValueError
        with pytest.raises(ValueError, match="Unknown event type"):
            await retry_handler("UnknownEventType", {"data": "test"})

        await bootstrap.teardown()

    async def test_dlq_retry_handler_succeeds_for_known_event_types(self) -> None:
        """Verify DLQ retry handler succeeds for known event types."""
        config = SimulationConfig.create_fast_config("test")
        bootstrap = SimulationApplicationBootstrap(config)

        await bootstrap.setup()

        # Create the retry handler
        retry_handler = bootstrap._create_dlq_retry_handler()

        # Mock the event bus to track calls
        event_bus = bootstrap.infrastructure.event_bus
        original_publish = event_bus.publish
        publish_calls = []

        async def mock_publish(event):
            publish_calls.append(event)
            # Don't call the original - we just want to track the call

        event_bus.publish = mock_publish

        try:
            # Test WorkItemColumnChanged - should succeed
            await retry_handler(
                "WorkItemColumnChanged",
                {
                    "work_item_id": "test-123",
                    "board_id": "board-1",
                    "project_id": "proj-1",
                    "from_column": "Backlog",
                    "to_column": "In Progress",
                    "moved_by": "test-user",
                },
            )
            assert len(publish_calls) == 1
            assert publish_calls[0].event_type == "WorkItemColumnChangedEvent"

            # Test BoardReconciled - should succeed
            await retry_handler(
                "BoardReconciled",
                {
                    "board_id": "board-1",
                    "project_id": "proj-1",
                    "columns_added": [],
                    "columns_removed": [],
                },
            )
            assert len(publish_calls) == 2
            assert publish_calls[1].event_type == "BoardReconciledEvent"
        finally:
            event_bus.publish = original_publish
            await bootstrap.teardown()

    async def test_dlq_retry_handler_with_event_bus_unavailable(self) -> None:
        """Verify DLQ retry handler behavior when event bus is unavailable."""
        config = SimulationConfig.create_fast_config("test")
        bootstrap = SimulationApplicationBootstrap(config)

        await bootstrap.setup()

        # Create the retry handler before clearing infrastructure
        # The handler captures the event_bus reference at creation time
        retry_handler = bootstrap._create_dlq_retry_handler()

        # Clear the infrastructure AFTER handler creation
        # This simulates event_bus being available at creation but cleared later
        original_infrastructure = bootstrap.infrastructure
        bootstrap.infrastructure = None

        # The handler should still have the event bus reference captured
        # so it should work fine with unknown event types
        with pytest.raises(ValueError, match="Unknown event type"):
            await retry_handler("UnknownType", {})

        # Restore infrastructure for cleanup
        bootstrap.infrastructure = original_infrastructure
        await bootstrap.teardown()


@pytest.mark.asyncio
class TestBootstrapIntegrationFixes:
    """Integration tests combining multiple fixes."""

    async def test_setup_and_teardown_with_all_fixes(self) -> None:
        """Verify full setup/teardown cycle with all fixes applied."""
        config = SimulationConfig.create_fast_config("test")
        bootstrap = SimulationApplicationBootstrap(config)

        # Setup
        app = await bootstrap.setup()

        # Verify failed_event_store is typed correctly
        assert isinstance(bootstrap.infrastructure.failed_event_store, IFailedEventStore)

        # Verify DLQ retry handler works
        retry_handler = bootstrap._create_dlq_retry_handler()

        # Unknown event type should raise
        with pytest.raises(ValueError):
            await retry_handler("UnknownType", {})

        # Known event type should work
        event_bus = bootstrap.infrastructure.event_bus
        original_publish = event_bus.publish
        publish_called = False

        async def mock_publish(event):
            nonlocal publish_called
            publish_called = True

        event_bus.publish = mock_publish

        try:
            await retry_handler(
                "WorkItemColumnChanged",
                {
                    "work_item_id": "test-123",
                    "board_id": "board-1",
                    "project_id": "proj-1",
                    "from_column": "Backlog",
                    "to_column": "In Progress",
                    "moved_by": "test-user",
                },
            )
            assert publish_called
        finally:
            event_bus.publish = original_publish

        # Teardown should succeed without raising
        await bootstrap.teardown()

        # Verify clean state
        assert bootstrap._is_setup is False
