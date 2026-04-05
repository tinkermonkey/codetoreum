"""Tests for NullEventEmitter - null-object pattern event emitter.

Verifies that:
1. NullEventEmitter is a no-op implementation with mutable _warned state
2. One-time warning log is only emitted on first emit() call
3. Subsequent emit() calls are silent (no additional warnings)
4. on(), off(), and once() methods are no-ops
5. Event mutation state is properly tracked
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

from codetoreum.domain.events import CodetoreumEvent, now_iso
from codetoreum.ports.output.event_emitter import NullEventEmitter


class TestNullEventEmitter:
    """Tests for the NullEventEmitter null-object implementation."""

    def test_emit_first_call_logs_warning(self):
        """First emit() call should log a warning about event DI wiring failure."""
        emitter = NullEventEmitter()
        event = CodetoreumEvent(
            type="test.event",
            timestamp=now_iso(),
            source="test",
        )

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            emitter.emit(event)

            # Verify warning was logged
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args[0][0]
            assert "NullEventEmitter.emit() called" in call_args
            assert "DI wiring" in call_args or "event" in call_args

    def test_emit_subsequent_calls_silent(self):
        """Subsequent emit() calls should be silent (no logging)."""
        emitter = NullEventEmitter()
        event = CodetoreumEvent(
            type="test.event",
            timestamp=now_iso(),
            source="test",
        )

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            # First emit
            emitter.emit(event)
            first_call_count = mock_logger.warning.call_count

            # Second emit
            emitter.emit(event)
            second_call_count = mock_logger.warning.call_count

            # No additional warnings should be logged
            assert second_call_count == first_call_count
            assert mock_logger.warning.call_count == 1

    def test_warned_flag_mutable_state_tracking(self):
        """_warned flag should track mutable state for one-time warning."""
        emitter = NullEventEmitter()

        # Initial state
        assert emitter._warned is False

        event = CodetoreumEvent(
            type="test.event",
            timestamp=now_iso(),
            source="test",
        )

        # After first emit, flag should be True
        with patch("logging.getLogger"):
            emitter.emit(event)
            assert emitter._warned is True

    def test_on_is_noop(self):
        """on() method should be a no-op."""
        emitter = NullEventEmitter()

        def handler(event):
            pass

        # Should not raise
        emitter.on("test.event", handler)

        # Emitting should still be a no-op
        event = CodetoreumEvent(
            type="test.event",
            timestamp=now_iso(),
            source="test",
        )

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            # Record initial warning call count
            emitter.emit(event)
            initial_calls = mock_logger.warning.call_count

            # Handler should never be called (noop)
            with patch.object(handler, "__call__") as mock_handler:
                emitter.emit(event)
                mock_handler.assert_not_called()

    def test_off_is_noop(self):
        """off() method should be a no-op."""
        emitter = NullEventEmitter()

        def handler(event):
            pass

        # Should not raise even though handler wasn't registered
        emitter.off("test.event", handler)

    def test_once_is_noop(self):
        """once() method should be a no-op (no handlers registered)."""
        emitter = NullEventEmitter()
        call_count = [0]

        def handler(event):
            call_count[0] += 1

        emitter.once("test.event", handler)

        event = CodetoreumEvent(
            type="test.event",
            timestamp=now_iso(),
            source="test",
        )

        with patch("logging.getLogger"):
            # Emit multiple times
            emitter.emit(event)
            emitter.emit(event)
            emitter.emit(event)

            # Handler should never be called
            assert call_count[0] == 0

    def test_multiple_emitter_instances_independent(self):
        """Each NullEventEmitter instance should have independent _warned state."""
        emitter1 = NullEventEmitter()
        emitter2 = NullEventEmitter()

        event = CodetoreumEvent(
            type="test.event",
            timestamp=now_iso(),
            source="test",
        )

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            # First emitter emits - should log warning
            emitter1.emit(event)
            assert mock_logger.warning.call_count == 1

            # Second emitter emits - should also log warning (independent state)
            emitter2.emit(event)
            assert mock_logger.warning.call_count == 2

            # Subsequent calls on each should be silent
            emitter1.emit(event)
            emitter2.emit(event)
            assert mock_logger.warning.call_count == 2
