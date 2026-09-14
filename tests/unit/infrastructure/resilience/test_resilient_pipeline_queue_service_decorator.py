"""Unit tests for ResilientPipelineQueueServiceDecorator."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.resilience.decorators import ResilientPipelineQueueServiceDecorator
from codetoreum.ports.output.failed_event_store import FailureReason
from codetoreum.ports.output.pipeline_queue_service import (
    IPipelineQueueService,
    PipelineQueueEntry,
    QueueValidationError,
)


class MockQueueService:
    """Mock queue service for testing."""

    def __init__(self):
        self.is_item_in_queue = AsyncMock(return_value=False)
        self.enqueue_item = AsyncMock()
        self.mark_item_active = AsyncMock()
        self.remove_from_queue = AsyncMock(return_value=False)
        self.get_next_waiting_item = AsyncMock(return_value=None)
        self.get_queue_entries = AsyncMock(return_value=[])
        self.sync_queue_with_board = AsyncMock()
        self.failed_event_store = AsyncMock()


@pytest.mark.asyncio
class TestResilientPipelineQueueServiceDecorator:
    """Tests for ResilientPipelineQueueServiceDecorator."""

    async def test_is_item_in_queue_success(self):
        """Test successful is_item_in_queue pass-through."""
        mock_adapter = MockQueueService()
        mock_adapter.is_item_in_queue.return_value = True
        mock_adapter.failed_event_store = AsyncMock()

        decorator = ResilientPipelineQueueServiceDecorator(wrapped=mock_adapter)

        result = await decorator.is_item_in_queue("work-item-1")

        assert result is True
        mock_adapter.is_item_in_queue.assert_called_once_with("work-item-1")

    async def test_is_item_in_queue_failure_routes_to_dlq(self):
        """Test is_item_in_queue failure is routed to DLQ with safe default."""
        mock_adapter = MockQueueService()
        error = RuntimeError("Queue service error")
        mock_adapter.is_item_in_queue.side_effect = error
        mock_adapter.failed_event_store = AsyncMock()

        decorator = ResilientPipelineQueueServiceDecorator(wrapped=mock_adapter)

        result = await decorator.is_item_in_queue("work-item-1")

        assert result is False
        mock_adapter.failed_event_store.add_failed_event.assert_called_once()
        call_args = mock_adapter.failed_event_store.add_failed_event.call_args
        assert call_args.kwargs["event_type"] == "queue_service.is_item_in_queue"
        assert call_args.kwargs["failure_reason"] == FailureReason.PROCESSING_ERROR

    async def test_enqueue_item_success(self):
        """Test successful enqueue_item pass-through."""
        mock_adapter = MockQueueService()
        mock_adapter.enqueue_item.return_value = None
        mock_adapter.failed_event_store = AsyncMock()

        decorator = ResilientPipelineQueueServiceDecorator(wrapped=mock_adapter)

        await decorator.enqueue_item("proj-1", "board-1", "item-1", 0, datetime.now())

        mock_adapter.enqueue_item.assert_called_once()

    async def test_enqueue_item_failure_raises_and_routes_to_dlq(self):
        """Test enqueue_item failure raises exception and routes to DLQ."""
        mock_adapter = MockQueueService()
        error = RuntimeError("Enqueue failed")
        mock_adapter.enqueue_item.side_effect = error
        mock_adapter.failed_event_store = AsyncMock()

        decorator = ResilientPipelineQueueServiceDecorator(wrapped=mock_adapter)

        with pytest.raises(RuntimeError, match="Enqueue failed"):
            await decorator.enqueue_item("proj-1", "board-1", "item-1", 0, datetime.now())

        mock_adapter.failed_event_store.add_failed_event.assert_called_once()
        call_args = mock_adapter.failed_event_store.add_failed_event.call_args
        assert call_args.kwargs["event_type"] == "queue_service.enqueue_item"
        assert call_args.kwargs["error_message"].startswith("RuntimeError:")

    async def test_mark_item_active_failure_raises_and_routes_to_dlq(self):
        """Test mark_item_active failure raises exception and routes to DLQ."""
        mock_adapter = MockQueueService()
        error = RuntimeError("Mark active failed")
        mock_adapter.mark_item_active.side_effect = error
        mock_adapter.failed_event_store = AsyncMock()

        decorator = ResilientPipelineQueueServiceDecorator(wrapped=mock_adapter)

        with pytest.raises(RuntimeError, match="Mark active failed"):
            await decorator.mark_item_active("item-1")

        mock_adapter.failed_event_store.add_failed_event.assert_called_once()

    async def test_remove_from_queue_failure_raises_and_routes_to_dlq(self):
        """Test remove_from_queue failure raises exception and routes to DLQ."""
        mock_adapter = MockQueueService()
        error = RuntimeError("Remove failed")
        mock_adapter.remove_from_queue.side_effect = error
        mock_adapter.failed_event_store = AsyncMock()

        decorator = ResilientPipelineQueueServiceDecorator(wrapped=mock_adapter)

        with pytest.raises(RuntimeError, match="Remove failed"):
            await decorator.remove_from_queue("item-1")

        mock_adapter.failed_event_store.add_failed_event.assert_called_once()

    async def test_get_next_waiting_item_failure_returns_none_and_routes_to_dlq(self):
        """Test get_next_waiting_item failure returns None and routes to DLQ."""
        mock_adapter = MockQueueService()
        error = RuntimeError("Get next failed")
        mock_adapter.get_next_waiting_item.side_effect = error
        mock_adapter.failed_event_store = AsyncMock()

        decorator = ResilientPipelineQueueServiceDecorator(wrapped=mock_adapter)

        result = await decorator.get_next_waiting_item("proj-1", "board-1")

        assert result is None
        mock_adapter.failed_event_store.add_failed_event.assert_called_once()

    async def test_get_queue_entries_failure_returns_empty_list_and_routes_to_dlq(self):
        """Test get_queue_entries failure returns empty list and routes to DLQ."""
        mock_adapter = MockQueueService()
        error = RuntimeError("Get entries failed")
        mock_adapter.get_queue_entries.side_effect = error
        mock_adapter.failed_event_store = AsyncMock()

        decorator = ResilientPipelineQueueServiceDecorator(wrapped=mock_adapter)

        result = await decorator.get_queue_entries("proj-1", "board-1")

        assert result == []
        mock_adapter.failed_event_store.add_failed_event.assert_called_once()

    async def test_sync_queue_with_board_failure_raises_and_routes_to_dlq(self):
        """Test sync_queue_with_board failure raises exception and routes to DLQ."""
        mock_adapter = MockQueueService()
        error = RuntimeError("Sync failed")
        mock_adapter.sync_queue_with_board.side_effect = error
        mock_adapter.failed_event_store = AsyncMock()

        decorator = ResilientPipelineQueueServiceDecorator(wrapped=mock_adapter)

        with pytest.raises(RuntimeError, match="Sync failed"):
            await decorator.sync_queue_with_board("proj-1", "board-1", "In Progress")

        mock_adapter.failed_event_store.add_failed_event.assert_called_once()
        call_args = mock_adapter.failed_event_store.add_failed_event.call_args
        # sync_queue_with_board uses ERR_QUEUE_SYNC_ERROR
        assert call_args.kwargs["event_type"] == "queue_service.sync_queue_with_board"

    async def test_failed_event_store_not_available(self):
        """Test that decorator works when failed_event_store is None."""
        mock_adapter = MockQueueService()
        mock_adapter.failed_event_store = None
        error = RuntimeError("Query failed")
        mock_adapter.is_item_in_queue.side_effect = error

        decorator = ResilientPipelineQueueServiceDecorator(wrapped=mock_adapter)
        decorator.failed_event_store = None

        result = await decorator.is_item_in_queue("item-1")

        assert result is False

    async def test_failed_event_store_propagated(self):
        """Test that decorator propagates failed_event_store attribute."""
        mock_adapter = MockQueueService()
        mock_failed_store = AsyncMock()
        mock_adapter.failed_event_store = mock_failed_store

        decorator = ResilientPipelineQueueServiceDecorator(wrapped=mock_adapter)

        assert decorator.failed_event_store is mock_failed_store

    async def test_failed_event_store_missing_from_adapter(self):
        """Test that decorator handles missing failed_event_store gracefully."""
        mock_adapter = MagicMock(spec=IPipelineQueueService)
        # Remove failed_event_store attribute
        if hasattr(mock_adapter, "failed_event_store"):
            delattr(mock_adapter, "failed_event_store")

        decorator = ResilientPipelineQueueServiceDecorator(wrapped=mock_adapter)

        assert decorator.failed_event_store is None

    async def test_read_operations_return_safe_defaults_on_failure(self):
        """Test that all read operations return safe defaults on failure."""
        mock_adapter = MockQueueService()
        mock_adapter.failed_event_store = AsyncMock()

        # Make all read operations fail
        mock_adapter.is_item_in_queue.side_effect = RuntimeError("Failed")
        mock_adapter.get_next_waiting_item.side_effect = RuntimeError("Failed")
        mock_adapter.get_queue_entries.side_effect = RuntimeError("Failed")

        decorator = ResilientPipelineQueueServiceDecorator(wrapped=mock_adapter)

        # All should return safe defaults
        assert await decorator.is_item_in_queue("item-1") is False
        assert await decorator.get_next_waiting_item("proj-1", "board-1") is None
        assert await decorator.get_queue_entries("proj-1", "board-1") == []

    async def test_write_operations_raise_on_failure(self):
        """Test that all write operations raise on failure."""
        mock_adapter = MockQueueService()
        mock_adapter.failed_event_store = AsyncMock()

        # Make all write operations fail
        mock_adapter.enqueue_item.side_effect = RuntimeError("Write failed")
        mock_adapter.mark_item_active.side_effect = RuntimeError("Write failed")
        mock_adapter.remove_from_queue.side_effect = RuntimeError("Write failed")
        mock_adapter.sync_queue_with_board.side_effect = RuntimeError("Write failed")

        decorator = ResilientPipelineQueueServiceDecorator(wrapped=mock_adapter)

        # All should raise
        with pytest.raises(RuntimeError):
            await decorator.enqueue_item("proj-1", "board-1", "item-1", 0, datetime.now())

        with pytest.raises(RuntimeError):
            await decorator.mark_item_active("item-1")

        with pytest.raises(RuntimeError):
            await decorator.remove_from_queue("item-1")

        with pytest.raises(RuntimeError):
            await decorator.sync_queue_with_board("proj-1", "board-1", "In Progress")

    async def test_dlq_write_failure_logged_gracefully(self):
        """Test that DLQ write failures are logged but don't prevent operation."""
        mock_adapter = MockQueueService()
        mock_failed_store = AsyncMock()
        mock_failed_store.add_failed_event.side_effect = RuntimeError("DLQ write failed")
        mock_adapter.failed_event_store = mock_failed_store
        mock_adapter.is_item_in_queue.side_effect = RuntimeError("Query failed")

        decorator = ResilientPipelineQueueServiceDecorator(wrapped=mock_adapter)

        # Should still return safe default even if DLQ write fails
        result = await decorator.is_item_in_queue("item-1")
        assert result is False

    async def test_error_ids_used_correctly(self):
        """Test that correct error IDs are used in logging."""
        mock_adapter = MockQueueService()
        mock_adapter.failed_event_store = AsyncMock()

        decorator = ResilientPipelineQueueServiceDecorator(wrapped=mock_adapter)

        # Test read operation uses ERR_QUEUE_OPERATION_FAILURE
        mock_adapter.is_item_in_queue.side_effect = RuntimeError("Query failed")
        with patch("codetoreum.infrastructure.resilience.decorators.logger") as mock_logger:
            await decorator.is_item_in_queue("item-1")
            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args
            assert call_args.kwargs["extra"]["error_id"] == ErrorRegistry.ERR_QUEUE_OPERATION_FAILURE

        # Test sync operation uses ERR_QUEUE_SYNC_ERROR
        mock_adapter.sync_queue_with_board.side_effect = RuntimeError("Sync failed")
        with patch("codetoreum.infrastructure.resilience.decorators.logger") as mock_logger:
            with pytest.raises(RuntimeError):
                await decorator.sync_queue_with_board("proj-1", "board-1", "column")
            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args
            assert call_args.kwargs["extra"]["error_id"] == ErrorRegistry.ERR_QUEUE_SYNC_ERROR

    async def test_read_operation_raises_queue_validation_error_on_is_item_in_queue(self):
        """Test is_item_in_queue raises QueueValidationError when adapter does."""
        mock_adapter = MockQueueService()
        error = QueueValidationError("Invalid work_item_id")
        mock_adapter.is_item_in_queue.side_effect = error
        mock_adapter.failed_event_store = AsyncMock()

        decorator = ResilientPipelineQueueServiceDecorator(wrapped=mock_adapter)

        with pytest.raises(QueueValidationError, match="Invalid work_item_id"):
            await decorator.is_item_in_queue("work-item-1")

    async def test_read_operation_raises_queue_validation_error_on_get_next_waiting_item(self):
        """Test get_next_waiting_item raises QueueValidationError when adapter does."""
        mock_adapter = MockQueueService()
        error = QueueValidationError("Invalid parameters")
        mock_adapter.get_next_waiting_item.side_effect = error
        mock_adapter.failed_event_store = AsyncMock()

        decorator = ResilientPipelineQueueServiceDecorator(wrapped=mock_adapter)

        with pytest.raises(QueueValidationError, match="Invalid parameters"):
            await decorator.get_next_waiting_item("proj-1", "board-1")

    async def test_read_operation_raises_queue_validation_error_on_get_queue_entries(self):
        """Test get_queue_entries raises QueueValidationError when adapter does."""
        mock_adapter = MockQueueService()
        error = QueueValidationError("Invalid parameters")
        mock_adapter.get_queue_entries.side_effect = error
        mock_adapter.failed_event_store = AsyncMock()

        decorator = ResilientPipelineQueueServiceDecorator(wrapped=mock_adapter)

        with pytest.raises(QueueValidationError, match="Invalid parameters"):
            await decorator.get_queue_entries("proj-1", "board-1")
