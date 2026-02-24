"""Unit tests for EventBusWiring."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock

from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.event_bus_wiring import EventBusWiring, wire_adapters_to_event_bus


# ====================================================================================
# Mock Adapters
# ====================================================================================


class MockBoardService:
    """Mock board service for testing."""

    def __init__(self):
        """Initialize mock board service."""
        self.event_handlers = {}

    def on(self, event_type: str, handler):
        """Register event handler."""
        self.event_handlers[event_type] = handler

    def emit_event(self, event_type: str, event):
        """Emit event."""
        if event_type in self.event_handlers:
            self.event_handlers[event_type](event)


class MockDiscussionAdapter:
    """Mock discussion adapter for testing."""

    def __init__(self):
        """Initialize mock discussion adapter."""
        self.event_handlers = {}

    def on(self, event_type: str, handler):
        """Register event handler."""
        self.event_handlers[event_type] = handler

    def emit_event(self, event_type: str, event):
        """Emit event."""
        if event_type in self.event_handlers:
            self.event_handlers[event_type](event)


class MockLockService:
    """Mock lock service for testing."""

    def __init__(self):
        """Initialize mock lock service."""
        self.event_handlers = {}

    def on(self, event_type: str, handler):
        """Register event handler."""
        self.event_handlers[event_type] = handler

    def emit_event(self, event_type: str, event):
        """Emit event."""
        if event_type in self.event_handlers:
            self.event_handlers[event_type](event)


class MockCodeReviewService:
    """Mock code review service for testing."""

    def __init__(self):
        """Initialize mock review service."""
        self.event_handlers = {}

    def on(self, event_type: str, handler):
        """Register event handler."""
        self.event_handlers[event_type] = handler

    def emit_event(self, event_type: str, event):
        """Emit event."""
        if event_type in self.event_handlers:
            self.event_handlers[event_type](event)


class AdapterWithoutEventMethod:
    """Adapter that doesn't implement on() method."""
    pass


# ====================================================================================
# Fixtures
# ====================================================================================


@pytest.fixture
def event_bus():
    """Create an event bus."""
    return AsyncMock(spec=EventBus)


@pytest.fixture
def board_service():
    """Create a mock board service."""
    return MockBoardService()


@pytest.fixture
def discussion_adapter():
    """Create a mock discussion adapter."""
    return MockDiscussionAdapter()


@pytest.fixture
def lock_service():
    """Create a mock lock service."""
    return MockLockService()


@pytest.fixture
def review_service():
    """Create a mock code review service."""
    return MockCodeReviewService()


@pytest.fixture
def wiring(event_bus):
    """Create event bus wiring."""
    return EventBusWiring(event_bus)


# ====================================================================================
# Tests for EventBusWiring Initialization
# ====================================================================================


class TestEventBusWiringInitialization:
    """Tests for EventBusWiring initialization."""

    def test_wiring_initializes_with_event_bus(self, event_bus):
        """Test wiring initializes with event bus."""
        wiring = EventBusWiring(event_bus)
        assert wiring._event_bus == event_bus

    def test_wiring_initializes_empty_adapters_set(self, event_bus):
        """Test wiring initializes with empty adapters set."""
        wiring = EventBusWiring(event_bus)
        assert wiring._wired_adapters == set()

    def test_wiring_initializes_empty_pending_tasks(self, event_bus):
        """Test wiring initializes with empty pending tasks."""
        wiring = EventBusWiring(event_bus)
        assert wiring._pending_tasks == set()


# ====================================================================================
# Tests for Board Service Wiring
# ====================================================================================


class TestBoardServiceWiring:
    """Tests for wiring board service."""

    def test_wire_board_service(self, wiring, board_service):
        """Test wire_board_service() wires board service."""
        wiring.wire_board_service(board_service)

        # Check that handlers were registered
        assert "workitem.column_changed" in board_service.event_handlers
        assert "board.reconciled" in board_service.event_handlers

    def test_wire_board_service_adds_to_wired_adapters(self, wiring, board_service):
        """Test wire_board_service() adds to wired adapters set."""
        wiring.wire_board_service(board_service)
        assert "board_service" in wiring._wired_adapters

    def test_wire_board_service_without_on_method(self, wiring, caplog):
        """Test wire_board_service() with adapter missing on() method."""
        adapter = AdapterWithoutEventMethod()
        wiring.wire_board_service(adapter)

        # Should log warning and skip wiring
        assert "does not implement on() method" in caplog.text.lower()
        assert "board_service" not in wiring._wired_adapters

    def test_wire_board_service_registers_correct_events(self, wiring, board_service):
        """Test wire_board_service() registers correct event types."""
        wiring.wire_board_service(board_service)

        # Verify correct events were registered
        assert len(board_service.event_handlers) == 2
        assert "workitem.column_changed" in board_service.event_handlers
        assert "board.reconciled" in board_service.event_handlers


# ====================================================================================
# Tests for Discussion Adapter Wiring
# ====================================================================================


class TestDiscussionAdapterWiring:
    """Tests for wiring discussion adapter."""

    def test_wire_discussion_adapter(self, wiring, discussion_adapter):
        """Test wire_discussion_adapter() wires discussion adapter."""
        wiring.wire_discussion_adapter(discussion_adapter)

        # Check that handlers were registered
        assert "comment.needs_response" in discussion_adapter.event_handlers
        assert "comment.posted" in discussion_adapter.event_handlers

    def test_wire_discussion_adapter_adds_to_wired_adapters(self, wiring, discussion_adapter):
        """Test wire_discussion_adapter() adds to wired adapters set."""
        wiring.wire_discussion_adapter(discussion_adapter)
        assert "discussion_adapter" in wiring._wired_adapters

    def test_wire_discussion_adapter_without_on_method(self, wiring, caplog):
        """Test wire_discussion_adapter() with adapter missing on() method."""
        adapter = AdapterWithoutEventMethod()
        wiring.wire_discussion_adapter(adapter)

        # Should log warning and skip wiring
        assert "does not implement on() method" in caplog.text.lower()
        assert "discussion_adapter" not in wiring._wired_adapters

    def test_wire_discussion_adapter_registers_correct_events(self, wiring, discussion_adapter):
        """Test wire_discussion_adapter() registers correct event types."""
        wiring.wire_discussion_adapter(discussion_adapter)

        # Verify correct events were registered
        assert len(discussion_adapter.event_handlers) == 2
        assert "comment.needs_response" in discussion_adapter.event_handlers
        assert "comment.posted" in discussion_adapter.event_handlers


# ====================================================================================
# Tests for Lock Service Wiring
# ====================================================================================


class TestLockServiceWiring:
    """Tests for wiring lock service."""

    def test_wire_lock_service(self, wiring, lock_service):
        """Test wire_lock_service() wires lock service."""
        wiring.wire_lock_service(lock_service)

        # Check that handlers were registered
        assert "lock.acquired" in lock_service.event_handlers
        assert "lock.released" in lock_service.event_handlers
        assert "lock.stale_detected" in lock_service.event_handlers

    def test_wire_lock_service_adds_to_wired_adapters(self, wiring, lock_service):
        """Test wire_lock_service() adds to wired adapters set."""
        wiring.wire_lock_service(lock_service)
        assert "lock_service" in wiring._wired_adapters

    def test_wire_lock_service_without_on_method(self, wiring, caplog):
        """Test wire_lock_service() with adapter missing on() method."""
        adapter = AdapterWithoutEventMethod()
        wiring.wire_lock_service(adapter)

        # Should log warning and skip wiring
        assert "does not implement on() method" in caplog.text.lower()
        assert "lock_service" not in wiring._wired_adapters

    def test_wire_lock_service_registers_correct_events(self, wiring, lock_service):
        """Test wire_lock_service() registers correct event types."""
        wiring.wire_lock_service(lock_service)

        # Verify correct events were registered
        assert len(lock_service.event_handlers) == 3
        assert "lock.acquired" in lock_service.event_handlers
        assert "lock.released" in lock_service.event_handlers
        assert "lock.stale_detected" in lock_service.event_handlers


# ====================================================================================
# Tests for Code Review Service Wiring
# ====================================================================================


class TestCodeReviewServiceWiring:
    """Tests for wiring code review service."""

    def test_wire_review_service(self, wiring, review_service):
        """Test wire_review_service() wires review service."""
        wiring.wire_review_service(review_service)

        # Check that handlers were registered
        assert "review.status_changed" in review_service.event_handlers
        assert "review.comment_added" in review_service.event_handlers

    def test_wire_review_service_adds_to_wired_adapters(self, wiring, review_service):
        """Test wire_review_service() adds to wired adapters set."""
        wiring.wire_review_service(review_service)
        assert "review_service" in wiring._wired_adapters

    def test_wire_review_service_without_on_method(self, wiring, caplog):
        """Test wire_review_service() with adapter missing on() method."""
        adapter = AdapterWithoutEventMethod()
        wiring.wire_review_service(adapter)

        # Should log warning and skip wiring
        assert "does not implement on() method" in caplog.text.lower()
        assert "review_service" not in wiring._wired_adapters

    def test_wire_review_service_registers_correct_events(self, wiring, review_service):
        """Test wire_review_service() registers correct event types."""
        wiring.wire_review_service(review_service)

        # Verify correct events were registered
        assert len(review_service.event_handlers) == 2
        assert "review.status_changed" in review_service.event_handlers
        assert "review.comment_added" in review_service.event_handlers


# ====================================================================================
# Tests for Bulk Wiring
# ====================================================================================


class TestBulkWiring:
    """Tests for bulk adapter wiring."""

    def test_wire_all_adapters_with_all_provided(
        self,
        wiring,
        board_service,
        discussion_adapter,
        lock_service,
        review_service,
    ):
        """Test wire_all_adapters() with all adapters."""
        wiring.wire_all_adapters(
            board_service=board_service,
            discussion_adapter=discussion_adapter,
            lock_service=lock_service,
            review_service=review_service,
        )

        # Check that all adapters were wired
        assert len(wiring._wired_adapters) == 4
        assert "board_service" in wiring._wired_adapters
        assert "discussion_adapter" in wiring._wired_adapters
        assert "lock_service" in wiring._wired_adapters
        assert "review_service" in wiring._wired_adapters

    def test_wire_all_adapters_with_partial_adapters(self, wiring, board_service, discussion_adapter):
        """Test wire_all_adapters() with partial adapters."""
        wiring.wire_all_adapters(
            board_service=board_service,
            discussion_adapter=discussion_adapter,
        )

        # Check that only provided adapters were wired
        assert len(wiring._wired_adapters) == 2
        assert "board_service" in wiring._wired_adapters
        assert "discussion_adapter" in wiring._wired_adapters

    def test_wire_all_adapters_with_no_adapters(self, wiring):
        """Test wire_all_adapters() with no adapters."""
        wiring.wire_all_adapters()

        # Check that no adapters were wired
        assert len(wiring._wired_adapters) == 0

    def test_wire_all_adapters_with_none_values(self, wiring, board_service):
        """Test wire_all_adapters() handles None values correctly."""
        wiring.wire_all_adapters(
            board_service=board_service,
            discussion_adapter=None,
            lock_service=None,
            review_service=None,
        )

        # Check that only provided adapter was wired
        assert len(wiring._wired_adapters) == 1
        assert "board_service" in wiring._wired_adapters


# ====================================================================================
# Tests for Adapter Tracking
# ====================================================================================


class TestAdapterTracking:
    """Tests for adapter tracking."""

    def test_get_wired_adapters(self, wiring, board_service, discussion_adapter):
        """Test get_wired_adapters() returns set of wired adapters."""
        wiring.wire_board_service(board_service)
        wiring.wire_discussion_adapter(discussion_adapter)

        adapters = wiring.get_wired_adapters()
        assert adapters == {"board_service", "discussion_adapter"}

    def test_get_wired_adapters_returns_copy(self, wiring, board_service):
        """Test get_wired_adapters() returns a copy."""
        wiring.wire_board_service(board_service)

        adapters1 = wiring.get_wired_adapters()
        adapters2 = wiring.get_wired_adapters()

        # Should be equal but not the same object
        assert adapters1 == adapters2
        assert adapters1 is not adapters2

    def test_get_wired_adapters_empty(self, wiring):
        """Test get_wired_adapters() when no adapters wired."""
        adapters = wiring.get_wired_adapters()
        assert adapters == set()


# ====================================================================================
# Tests for Event Publishing
# ====================================================================================


class TestEventPublishing:
    """Tests for event publishing to event bus."""

    @pytest.mark.asyncio
    async def test_event_published_to_bus(self, wiring, board_service, event_bus):
        """Test event is published to event bus."""
        wiring.wire_board_service(board_service)

        # Emit an event from the board service
        test_event = Mock()
        board_service.emit_event("workitem.column_changed", test_event)

        # Give time for async task to complete
        await asyncio.sleep(0.1)

        # Verify event bus publish was called
        event_bus.publish.assert_called()

    @pytest.mark.asyncio
    async def test_multiple_events_published(self, wiring, board_service, event_bus):
        """Test multiple events are published to event bus."""
        wiring.wire_board_service(board_service)

        # Emit multiple events
        event1 = Mock()
        event2 = Mock()
        board_service.emit_event("workitem.column_changed", event1)
        board_service.emit_event("board.reconciled", event2)

        # Give time for async tasks to complete
        await asyncio.sleep(0.1)

        # Verify event bus publish was called multiple times
        assert event_bus.publish.call_count >= 2

    def test_event_publisher_created(self, wiring):
        """Test event publisher is created."""
        publisher = wiring._create_event_publisher()
        assert callable(publisher)

    @pytest.mark.asyncio
    async def test_event_publisher_is_callback(self, wiring):
        """Test event publisher is a valid callback."""
        publisher = wiring._create_event_publisher()
        test_event = Mock()

        # Should not raise exception when called in async context
        publisher(test_event)
        # Give time for background task to start
        await asyncio.sleep(0.01)


# ====================================================================================
# Tests for Error Handling
# ====================================================================================


class TestErrorHandling:
    """Tests for error handling in event publishing."""

    @pytest.mark.asyncio
    async def test_event_bus_error_logged(self, wiring, board_service, event_bus, caplog):
        """Test event bus errors are logged."""
        # Make event bus publish raise an exception
        event_bus.publish.side_effect = Exception("Event bus error")

        wiring.wire_board_service(board_service)

        # Emit an event
        test_event = Mock()
        board_service.emit_event("workitem.column_changed", test_event)

        # Give time for async task to complete
        await asyncio.sleep(0.1)

        # Error should be logged
        assert "Error publishing event" in caplog.text or "event_bus" in caplog.text.lower()

    def test_has_event_method_checks_callable(self, wiring):
        """Test _has_event_method checks if method is callable."""
        # Adapter with callable on method
        adapter_with_method = Mock()
        adapter_with_method.on = Mock()
        assert wiring._has_event_method(adapter_with_method) is True

        # Adapter with non-callable on attribute
        adapter_with_attribute = Mock()
        adapter_with_attribute.on = "not_callable"
        assert wiring._has_event_method(adapter_with_attribute) is False

        # Adapter without on attribute
        adapter_without = Mock(spec=[])
        assert wiring._has_event_method(adapter_without) is False


# ====================================================================================
# Tests for Factory Function
# ====================================================================================


class TestWireAdaptersFactoryFunction:
    """Tests for wire_adapters_to_event_bus factory function."""

    def test_wire_adapters_factory_creates_wiring(self, event_bus, board_service):
        """Test factory function creates EventBusWiring."""
        wiring = wire_adapters_to_event_bus(
            event_bus,
            board_service=board_service,
        )
        assert isinstance(wiring, EventBusWiring)

    def test_wire_adapters_factory_wires_adapters(self, event_bus, board_service, discussion_adapter):
        """Test factory function wires all provided adapters."""
        wiring = wire_adapters_to_event_bus(
            event_bus,
            board_service=board_service,
            discussion_adapter=discussion_adapter,
        )

        adapters = wiring.get_wired_adapters()
        assert "board_service" in adapters
        assert "discussion_adapter" in adapters

    def test_wire_adapters_factory_with_no_adapters(self, event_bus):
        """Test factory function with no adapters."""
        wiring = wire_adapters_to_event_bus(event_bus)
        assert isinstance(wiring, EventBusWiring)
        assert wiring.get_wired_adapters() == set()

    def test_wire_adapters_factory_returns_wiring(self, event_bus):
        """Test factory function returns EventBusWiring instance."""
        wiring = wire_adapters_to_event_bus(event_bus)
        assert hasattr(wiring, "wire_board_service")
        assert hasattr(wiring, "wire_all_adapters")
        assert hasattr(wiring, "get_wired_adapters")


# ====================================================================================
# Integration Tests
# ====================================================================================


class TestEventBusWiringIntegration:
    """Integration tests for event bus wiring."""

    def test_wire_all_services_sequentially(
        self,
        wiring,
        board_service,
        discussion_adapter,
        lock_service,
        review_service,
    ):
        """Test wiring all services sequentially."""
        wiring.wire_board_service(board_service)
        wiring.wire_discussion_adapter(discussion_adapter)
        wiring.wire_lock_service(lock_service)
        wiring.wire_review_service(review_service)

        adapters = wiring.get_wired_adapters()
        assert len(adapters) == 4

    def test_wire_duplicate_adapter_overwrites(self, wiring, board_service):
        """Test wiring same adapter twice."""
        wiring.wire_board_service(board_service)
        wiring.wire_board_service(board_service)

        # Should still only have one board_service in wired adapters
        assert len(wiring.get_wired_adapters()) == 1

    @pytest.mark.asyncio
    async def test_full_wiring_and_event_flow(
        self,
        event_bus,
        board_service,
        discussion_adapter,
        caplog,
    ):
        """Test full wiring and event flow."""
        wiring = EventBusWiring(event_bus)

        # Wire adapters
        wiring.wire_board_service(board_service)
        wiring.wire_discussion_adapter(discussion_adapter)

        # Emit events
        event1 = Mock()
        event2 = Mock()
        board_service.emit_event("workitem.column_changed", event1)
        discussion_adapter.emit_event("comment.needs_response", event2)

        # Give time for async tasks
        await asyncio.sleep(0.1)

        # Verify events were published
        assert event_bus.publish.call_count >= 2
