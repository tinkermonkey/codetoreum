"""Unit tests for BranchResolutionEventHandler."""

from unittest.mock import AsyncMock, Mock

import pytest

from codetoreum.application.event_handlers.branch_resolution_event_handler import (
    BranchResolutionEventHandler,
)
from codetoreum.domain.events.branch_events import (
    BranchResolutionCreatedEvent,
    BranchResolvedEvent,
    BranchReusedEvent,
)
from codetoreum.infrastructure.event_bus import EventBus


class TestBranchResolutionEventHandlerInitialization:
    """Test BranchResolutionEventHandler initialization."""

    def test_handler_initialization_without_event_bus(self):
        """Test handler initializes without event bus."""
        handler = BranchResolutionEventHandler()
        assert handler.event_bus is None

    def test_handler_initialization_with_event_bus(self):
        """Test handler initializes with event bus."""
        mock_bus = Mock(spec=EventBus)
        handler = BranchResolutionEventHandler(event_bus=mock_bus)
        assert handler.event_bus is mock_bus

    def test_handler_has_event_types(self):
        """Test handler is decorated with correct event types."""
        handler = BranchResolutionEventHandler()

        # Check that event_handler decorator adds get_event_types method
        assert hasattr(handler, "get_event_types")
        event_types = handler.get_event_types()
        assert "BranchResolvedEvent" in event_types
        assert "BranchReusedEvent" in event_types
        assert "BranchResolutionCreatedEvent" in event_types


class TestBranchResolvedEventHandler:
    """Test handling of BranchResolvedEvent."""

    @pytest.mark.asyncio
    async def test_handle_branch_resolved_event(self, caplog):
        """Test handler logs BranchResolvedEvent with structured fields."""
        import logging

        caplog.set_level(logging.INFO)
        handler = BranchResolutionEventHandler()

        event = BranchResolvedEvent(
            type="branch.resolved",
            timestamp="2025-01-14T10:30:00+00:00",
            source="branch_resolution",
            project_id="proj-1",
            issue_id="123",
            action="reuse",
            branch_name="feature/issue-123-fix-auth",
            confidence=0.95,
            reason="Exact match found for issue #123",
            resolution_strategy="exact_match",
        )

        await handler.handle(event)

        # Verify event was logged with structured fields
        assert "Branch resolved: reuse 'feature/issue-123-fix-auth' for issue #123" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_branch_reused_event(self, caplog):
        """Test handler logs BranchReusedEvent with structured fields."""
        import logging

        caplog.set_level(logging.INFO)
        handler = BranchResolutionEventHandler()

        event = BranchReusedEvent(
            type="branch.reused",
            timestamp="2025-01-14T10:30:00+00:00",
            source="branch_resolution",
            project_id="proj-1",
            issue_id="123",
            branch_name="feature/issue-123-fix-auth",
            confidence=0.95,
            reason="Exact match found for issue #123",
            resolution_strategy="exact_match",
        )

        await handler.handle(event)

        # Verify event was logged with structured fields
        assert "Branch reused: 'feature/issue-123-fix-auth' for issue #123" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_branch_created_event(self, caplog):
        """Test handler logs BranchResolutionCreatedEvent with structured fields."""
        import logging

        caplog.set_level(logging.INFO)
        handler = BranchResolutionEventHandler()

        event = BranchResolutionCreatedEvent(
            type="branch.created",
            timestamp="2025-01-14T10:30:00+00:00",
            source="branch_resolution",
            project_id="proj-1",
            issue_id="124",
            branch_name="feature/issue-124-new-feature",
            reason="No existing branch found, creating new",
        )

        await handler.handle(event)

        # Verify event was logged with structured fields
        assert "Branch created: 'feature/issue-124-new-feature' for issue #124" in caplog.text


class TestBranchResolutionEventHandlerErrorHandling:
    """Test error handling in BranchResolutionEventHandler."""

    @pytest.mark.asyncio
    async def test_handle_unexpected_event_type(self, caplog):
        """Test handler logs warning for unexpected event type."""
        handler = BranchResolutionEventHandler()

        # Create a mock event with unexpected type
        mock_event = Mock()
        mock_event.event_type = "unknown.event"

        await handler.handle(mock_event)

        # Verify warning was logged
        assert "unexpected event type" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_handle_unexpected_event_logs_warning(self, caplog):
        """Test handler logs warning for unexpected event type."""
        import logging

        caplog.set_level(logging.WARNING)
        handler = BranchResolutionEventHandler()

        # Create a mock event with unexpected type
        mock_event = Mock()
        mock_event.event_type = "unknown.event"

        # Handler should not raise, just log warning
        await handler.handle(mock_event)
        assert "unexpected event type" in caplog.text.lower()


class TestBranchResolutionEventHandlerIntegration:
    """Integration tests for BranchResolutionEventHandler with event bus."""

    @pytest.mark.asyncio
    async def test_handler_registered_with_event_bus(self):
        """Test handler can be registered with event bus."""
        mock_bus = Mock(spec=EventBus)
        handler = BranchResolutionEventHandler(event_bus=mock_bus)

        # Handler should be ready to register with event bus
        assert handler is not None
        assert handler.get_event_types() is not None
