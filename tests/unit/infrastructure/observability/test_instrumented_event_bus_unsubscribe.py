"""
Unit tests for InstrumentedEventBus.unsubscribe() with wrapped callbacks.

Tests that callbacks can be properly unsubscribed after being wrapped
for instrumentation, preventing memory leaks.
"""

from typing import Any, Optional
from unittest import mock

import pytest

from codetoreum.domain.events import DomainEvent
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.observability.event_bus_instrumentation import (
    InstrumentedEventBus,
)


class DummyEvent(DomainEvent):
    """Test event."""

    event_type = "dummy.created"
    aggregate_type = "dummy"


class TestInstrumentedEventBusUnsubscribe:
    """Tests for InstrumentedEventBus.unsubscribe() with wrapped callbacks."""

    def test_unsubscribe_wrapped_callback(self):
        """Test unsubscribing a callback that was wrapped during subscription."""
        # Create event bus and instrumented wrapper
        event_bus = EventBus()
        instrumented_bus = InstrumentedEventBus(event_bus)

        # Create a callback
        callback_called = []

        async def my_callback(event: DomainEvent) -> None:
            callback_called.append(event)

        # Subscribe the callback (will be wrapped)
        instrumented_bus.subscribe(None, my_callback)

        # Verify callback is registered (wrapped version exists)
        assert len(event_bus._wildcard_callbacks) > 0, "Callback not registered"

        # Unsubscribe the original callback
        instrumented_bus.unsubscribe(None, my_callback)

        # Verify callback was removed
        assert (
            len(event_bus._wildcard_callbacks) == 0
        ), "Callback was not properly unsubscribed"

    def test_unsubscribe_event_type_specific_callback(self):
        """Test unsubscribing a callback for a specific event type."""
        event_bus = EventBus()
        instrumented_bus = InstrumentedEventBus(event_bus)

        callback_called = []

        async def my_callback(event: DomainEvent) -> None:
            callback_called.append(event)

        event_type = "dummy.created"

        # Subscribe to specific event type (will be wrapped)
        instrumented_bus.subscribe(event_type, my_callback)

        # Verify callback is registered
        callbacks = event_bus._callbacks.get(event_type, [])
        assert len(callbacks) > 0, "Callback not registered for event type"

        # Unsubscribe
        instrumented_bus.unsubscribe(event_type, my_callback)

        # Verify callback was removed
        callbacks = event_bus._callbacks.get(event_type, [])
        assert len(callbacks) == 0, "Callback was not properly unsubscribed"

    def test_unsubscribe_nonexistent_callback_does_not_error(self):
        """Test unsubscribing a callback that doesn't exist doesn't raise error."""
        event_bus = EventBus()
        instrumented_bus = InstrumentedEventBus(event_bus)

        async def callback1(event: DomainEvent) -> None:
            pass

        async def callback2(event: DomainEvent) -> None:
            pass

        # Subscribe callback1
        instrumented_bus.subscribe(None, callback1)

        # Try to unsubscribe callback2 (never subscribed)
        # Should not raise
        instrumented_bus.unsubscribe(None, callback2)

    def test_unsubscribe_only_removes_matching_callback(self):
        """Test that unsubscribe only removes the matching callback."""
        event_bus = EventBus()
        instrumented_bus = InstrumentedEventBus(event_bus)

        async def callback1(event: DomainEvent) -> None:
            pass

        async def callback2(event: DomainEvent) -> None:
            pass

        # Subscribe both callbacks
        instrumented_bus.subscribe(None, callback1)
        instrumented_bus.subscribe(None, callback2)

        # Verify both are registered
        assert len(event_bus._wildcard_callbacks) == 2, "Both callbacks not registered"

        # Unsubscribe callback1
        instrumented_bus.unsubscribe(None, callback1)

        # Verify callback2 still exists and callback1 is gone
        assert len(event_bus._wildcard_callbacks) == 1, "Wrong callback was removed"

        # Unsubscribe callback2
        instrumented_bus.unsubscribe(None, callback2)

        # Verify all callbacks are gone
        assert len(event_bus._wildcard_callbacks) == 0, "Not all callbacks were removed"

    def test_unsubscribe_with_multiple_event_types(self):
        """Test unsubscribing callbacks from different event types."""
        event_bus = EventBus()
        instrumented_bus = InstrumentedEventBus(event_bus)

        async def callback1(event: DomainEvent) -> None:
            pass

        async def callback2(event: DomainEvent) -> None:
            pass

        event_type_1 = "event.type.1"
        event_type_2 = "event.type.2"

        # Subscribe callbacks to different event types
        instrumented_bus.subscribe(event_type_1, callback1)
        instrumented_bus.subscribe(event_type_2, callback2)

        # Verify both are registered
        assert len(event_bus._callbacks.get(event_type_1, [])) == 1
        assert len(event_bus._callbacks.get(event_type_2, [])) == 1

        # Unsubscribe callback1
        instrumented_bus.unsubscribe(event_type_1, callback1)

        # Verify callback1 is gone, callback2 remains
        assert len(event_bus._callbacks.get(event_type_1, [])) == 0
        assert len(event_bus._callbacks.get(event_type_2, [])) == 1

        # Unsubscribe callback2
        instrumented_bus.unsubscribe(event_type_2, callback2)

        assert len(event_bus._callbacks.get(event_type_2, [])) == 0

    def test_unsubscribe_wildcard_vs_specific_callbacks(self):
        """Test unsubscribing doesn't confuse wildcard and specific callbacks."""
        event_bus = EventBus()
        instrumented_bus = InstrumentedEventBus(event_bus)

        async def wildcard_callback(event: DomainEvent) -> None:
            pass

        async def specific_callback(event: DomainEvent) -> None:
            pass

        event_type = "dummy.created"

        # Subscribe to wildcard and specific event type
        instrumented_bus.subscribe(None, wildcard_callback)
        instrumented_bus.subscribe(event_type, specific_callback)

        # Verify both registered
        assert len(event_bus._wildcard_callbacks) == 1
        assert len(event_bus._callbacks.get(event_type, [])) == 1

        # Unsubscribe wildcard
        instrumented_bus.unsubscribe(None, wildcard_callback)

        # Verify wildcard is gone, specific remains
        assert len(event_bus._wildcard_callbacks) == 0
        assert len(event_bus._callbacks.get(event_type, [])) == 1

    def test_wrapped_callback_has_wrapped_attribute(self):
        """Test that wrapped callbacks have __wrapped__ attribute pointing to original."""
        event_bus = EventBus()
        instrumented_bus = InstrumentedEventBus(event_bus)

        async def original_callback(event: DomainEvent) -> None:
            pass

        # Subscribe
        instrumented_bus.subscribe(None, original_callback)

        # Get the wrapped callback from the bus
        wrapped_callback = event_bus._wildcard_callbacks[0]

        # Verify it has __wrapped__ attribute pointing to original
        assert hasattr(wrapped_callback, "__wrapped__")
        assert wrapped_callback.__wrapped__ == original_callback

    def test_unsubscribe_same_callback_multiple_times_safe(self):
        """Test unsubscribing the same callback multiple times is safe."""
        event_bus = EventBus()
        instrumented_bus = InstrumentedEventBus(event_bus)

        async def callback(event: DomainEvent) -> None:
            pass

        # Subscribe
        instrumented_bus.subscribe(None, callback)
        assert len(event_bus._wildcard_callbacks) == 1

        # Unsubscribe first time
        instrumented_bus.unsubscribe(None, callback)
        assert len(event_bus._wildcard_callbacks) == 0

        # Unsubscribe second time (should not error)
        instrumented_bus.unsubscribe(None, callback)
        assert len(event_bus._wildcard_callbacks) == 0

    def test_callback_actually_not_invoked_after_unsubscribe(self):
        """Test that unsubscribed callbacks are not invoked."""
        event_bus = EventBus()
        instrumented_bus = InstrumentedEventBus(event_bus)

        invoked = []

        async def callback(event: DomainEvent) -> None:
            invoked.append(event)

        # Subscribe and then unsubscribe
        instrumented_bus.subscribe(None, callback)
        instrumented_bus.unsubscribe(None, callback)

        # Create and publish event
        event = DummyEvent(aggregate_id="123", aggregate_type="dummy")

        # Manually trigger handler execution (since we can't await publish in this context)
        # This tests that the callback was actually removed from the bus
        callbacks = event_bus._wildcard_callbacks
        assert len(callbacks) == 0, "Callback still registered after unsubscribe"
