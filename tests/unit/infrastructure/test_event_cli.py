"""Unit tests for EventCLI infrastructure utility."""

import pytest
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock

from codetoreum.infrastructure.event_cli import EventCLI
from codetoreum.ports.output.event_store import IEventStore


class MockEvent:
    """Mock event for testing."""

    def __init__(
        self,
        event_id: str = "event-123",
        event_type: str = "test.event",
        aggregate_type: str = "test",
        aggregate_id: str = "agg-123",
        occurred_at: datetime | None = None,
        stream_version: int = 1,
        data: dict | None = None,
    ) -> None:
        """Initialize mock event."""
        self.event_id = event_id
        self.event_type = event_type
        self.aggregate_type = aggregate_type
        self.aggregate_id = aggregate_id
        self.occurred_at = occurred_at or datetime.now(UTC)
        self.stream_version = stream_version
        self.data = data or {}


class TestEventCLIInitialization:
    """Test EventCLI initialization."""

    def test_init_with_event_store(self) -> None:
        """Test initializing EventCLI with event store."""
        mock_store = MagicMock(spec=IEventStore)
        cli = EventCLI(mock_store)

        assert cli.event_store is mock_store


class TestEventCLIListEvents:
    """Test EventCLI list_events method."""

    @pytest.mark.asyncio
    async def test_list_events_empty_result(self) -> None:
        """Test listing events when event store returns empty."""
        mock_store = AsyncMock(spec=IEventStore)
        mock_store.get_events_by_type = AsyncMock(return_value=[])

        cli = EventCLI(mock_store)

        # Should not raise an exception
        await cli.list_events(event_type="test.event", limit=50)

    @pytest.mark.asyncio
    async def test_list_events_by_type(self) -> None:
        """Test listing events filtered by type."""
        events = [
            MockEvent(event_id="e1", event_type="test.created"),
            MockEvent(event_id="e2", event_type="test.created"),
        ]

        mock_store = AsyncMock(spec=IEventStore)
        mock_store.get_events_by_type = AsyncMock(return_value=events)

        cli = EventCLI(mock_store)
        await cli.list_events(event_type="test.created", limit=10)

        mock_store.get_events_by_type.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_events_by_stream_id(self) -> None:
        """Test listing events filtered by stream ID."""
        events = [
            MockEvent(event_id="e1", aggregate_id="stream-123"),
            MockEvent(event_id="e2", aggregate_id="stream-123"),
        ]

        mock_store = AsyncMock(spec=IEventStore)
        mock_store.get_events = AsyncMock(return_value=events)

        cli = EventCLI(mock_store)
        await cli.list_events(stream_id="stream-123", limit=10)

        mock_store.get_events.assert_called()

    @pytest.mark.asyncio
    async def test_list_events_with_time_filter(self) -> None:
        """Test listing events with since timestamp filter."""
        since = datetime(2025, 1, 1, tzinfo=UTC)
        events = [
            MockEvent(event_id="e1", occurred_at=datetime(2025, 1, 2, tzinfo=UTC)),
        ]

        mock_store = AsyncMock(spec=IEventStore)
        mock_store.get_events_since = AsyncMock(return_value=events)

        cli = EventCLI(mock_store)
        await cli.list_events(since=since, limit=10)

        mock_store.get_events_since.assert_called()

    @pytest.mark.asyncio
    async def test_list_all_events(self) -> None:
        """Test listing all events without filters."""
        stream_events = [MockEvent(event_id="e1")]

        mock_store = AsyncMock(spec=IEventStore)
        mock_store.get_all_stream_ids = AsyncMock(return_value=["stream-1", "stream-2"])
        mock_store.get_events = AsyncMock(return_value=stream_events)

        cli = EventCLI(mock_store)
        await cli.list_events(limit=50)

        mock_store.get_all_stream_ids.assert_called_once()
