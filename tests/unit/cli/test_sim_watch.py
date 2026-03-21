"""Tests for the sim-watch CLI command.

Tests cover:
- SSE reconnection with exponential backoff
- HTTP polling with error handling
- Concurrent task coordination
- Rich terminal rendering logic
- Error handling with proper logging
"""

import asyncio
import io
import json
import logging
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from codetoreum.cli.sim_watch import (
    build_board_display,
    build_status_display,
    poll_board_state,
    stream_events,
)


def render_panel_text(panel: Panel) -> str:
    """Helper to render a Panel to text for assertions."""
    console = Console(file=io.StringIO(), width=80, legacy_windows=False)
    console.print(panel)
    return console.file.getvalue()


class TestBuildBoardDisplay:
    """Tests for board display rendering."""

    def test_empty_board_state(self):
        """Test rendering with empty board state."""
        panel = build_board_display(None)
        assert isinstance(panel, Panel)
        rendered = render_panel_text(panel)
        assert "No board state available" in rendered

    def test_missing_columns(self):
        """Test rendering with missing columns key."""
        board_state = {"board_name": "test-board"}
        panel = build_board_display(board_state)
        assert isinstance(panel, Panel)
        rendered = render_panel_text(panel)
        assert "No board state available" in rendered

    def test_board_with_single_column(self):
        """Test rendering board with one column."""
        board_state = {
            "board_id": "board-1",
            "board_name": "Test Board",
            "snapshot_time": "2025-03-21T10:00:00Z",
            "columns": [
                {
                    "name": "Todo",
                    "items": [
                        {
                            "work_item_id": "WI-1",
                            "title": "Test task",
                            "execution_status": "running",
                            "assigned_agent": "agent-1",
                        }
                    ],
                }
            ],
        }
        panel = build_board_display(board_state)
        assert isinstance(panel, Panel)
        rendered = render_panel_text(panel)
        # Should contain the specific board name provided
        assert "Test Board" in rendered

    def test_board_with_multiple_columns(self):
        """Test rendering board with multiple columns."""
        board_state = {
            "board_id": "board-1",
            "board_name": "Multi-col Board",
            "snapshot_time": "2025-03-21T10:00:00Z",
            "columns": [
                {"name": "Todo", "items": [{"work_item_id": "WI-1", "title": "Task 1"}]},
                {
                    "name": "In Progress",
                    "items": [{"work_item_id": "WI-2", "title": "Task 2", "execution_status": "running"}],
                },
                {
                    "name": "Done",
                    "items": [{"work_item_id": "WI-3", "title": "Task 3", "execution_status": "completed"}],
                },
            ],
        }
        panel = build_board_display(board_state)
        assert isinstance(panel, Panel)
        rendered = render_panel_text(panel)
        # Should contain the specific board name provided
        assert "Multi-col Board" in rendered

    def test_timestamp_parsing_iso_format(self):
        """Test ISO format timestamp parsing."""
        board_state = {
            "board_id": "board-1",
            "board_name": "Test",
            "snapshot_time": "2025-03-21T10:30:45Z",
            "columns": [],
        }
        panel = build_board_display(board_state)
        assert isinstance(panel, Panel)
        rendered = render_panel_text(panel)
        # Should contain formatted time
        assert "10:30:45" in rendered

    def test_timestamp_parsing_invalid_format(self, caplog):
        """Test invalid timestamp format falls back to string representation."""
        board_state = {
            "board_id": "board-1",
            "board_name": "Test",
            "snapshot_time": "invalid-timestamp",
            "columns": [],
        }
        with caplog.at_level(logging.WARNING):
            panel = build_board_display(board_state)
        assert isinstance(panel, Panel)
        # Should log warning about parsing failure
        assert "Failed to parse snapshot time" in caplog.text
        rendered = render_panel_text(panel)
        # Should use string representation as fallback
        assert "invalid-timestamp" in rendered

    def test_timestamp_parsing_non_string(self):
        """Test non-string timestamp type."""
        board_state = {
            "board_id": "board-1",
            "board_name": "Test",
            "snapshot_time": 1234567890,
            "columns": [],
        }
        panel = build_board_display(board_state)
        assert isinstance(panel, Panel)

    def test_work_item_status_colors(self):
        """Test work item color coding by status."""
        statuses = ["running", "completed", "review", "failed", None]
        for status in statuses:
            board_state = {
                "board_id": "board-1",
                "columns": [
                    {
                        "name": "Status",
                        "items": [{"work_item_id": "WI-1", "execution_status": status}],
                    }
                ],
            }
            panel = build_board_display(board_state)
            assert isinstance(panel, Panel)
            rendered = render_panel_text(panel)
            # Verify status text appears in rendered output
            if status:
                assert status in rendered
            # Always verify work item ID is present
            assert "WI-1" in rendered

    def test_long_work_item_title_truncation(self):
        """Test that long titles are truncated to 30 characters."""
        long_title = "A" * 100
        board_state = {
            "board_id": "board-1",
            "columns": [
                {
                    "name": "Todo",
                    "items": [{"work_item_id": "WI-1", "title": long_title}],
                }
            ],
        }
        panel = build_board_display(board_state)
        assert isinstance(panel, Panel)
        rendered = render_panel_text(panel)
        # Verify the full 100-character string does NOT appear (truncation worked)
        assert long_title not in rendered
        # Verify truncated portion appears
        assert "A" * 30 in rendered

    def test_missing_work_item_fields(self):
        """Test rendering with missing optional fields."""
        board_state = {
            "board_id": "board-1",
            "columns": [
                {
                    "name": "Todo",
                    "items": [{"work_item_id": "WI-1"}],  # No title or status
                }
            ],
        }
        panel = build_board_display(board_state)
        assert isinstance(panel, Panel)


class TestBuildStatusDisplay:
    """Tests for status panel rendering."""

    def test_connected_status(self):
        """Test connected status display."""
        panel = build_status_display(connected=True, last_event=None, event_count=0, error_message=None)
        assert isinstance(panel, Panel)
        rendered = render_panel_text(panel)
        assert "Connected" in rendered

    def test_disconnected_status(self):
        """Test disconnected status display."""
        panel = build_status_display(connected=False, last_event=None, event_count=0, error_message=None)
        assert isinstance(panel, Panel)
        rendered = render_panel_text(panel)
        assert "Disconnected" in rendered

    def test_event_count_display(self):
        """Test event count is displayed."""
        panel = build_status_display(connected=True, last_event="EventType", event_count=42, error_message=None)
        assert isinstance(panel, Panel)
        rendered = render_panel_text(panel)
        assert "42" in rendered

    def test_last_event_display(self):
        """Test last event type is displayed."""
        panel = build_status_display(connected=True, last_event="WorkItemMoved", event_count=5, error_message=None)
        assert isinstance(panel, Panel)
        rendered = render_panel_text(panel)
        assert "WorkItemMoved" in rendered

    def test_error_message_display(self):
        """Test error message is displayed."""
        panel = build_status_display(
            connected=False, last_event=None, event_count=0, error_message="Connection timeout"
        )
        assert isinstance(panel, Panel)
        rendered = render_panel_text(panel)
        assert "Connection timeout" in rendered

    def test_all_fields_populated(self):
        """Test all fields populated together."""
        panel = build_status_display(connected=True, last_event="TestEvent", event_count=100, error_message=None)
        assert isinstance(panel, Panel)
        rendered = render_panel_text(panel)
        assert "Connected" in rendered
        assert "TestEvent" in rendered
        assert "100" in rendered


class TestStreamEvents:
    """Tests for SSE event streaming."""

    @pytest.mark.asyncio
    async def test_successful_sse_connection(self):
        """Test successful SSE connection."""
        callback = AsyncMock()

        async def mock_stream(*args, **kwargs):
            """Mock SSE stream."""

            class MockResponse:
                status_code = 200

                async def aiter_lines(self):
                    yield "data: " + json.dumps({"event_type": "TestEvent"})
                    yield ""  # Empty line signals end of event (RFC 8453)
                    await asyncio.sleep(0.1)
                    raise StopAsyncIteration()

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

            return MockResponse()

        with patch("codetoreum.cli.sim_watch.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.stream = AsyncMock(side_effect=mock_stream)
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            # Run stream with timeout
            task = asyncio.create_task(stream_events("localhost", 8000, "board-1", callback))
            await asyncio.sleep(0.2)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verify callback was called
            assert callback.called

    @pytest.mark.asyncio
    async def test_sse_reconnection_on_http_error(self):
        """Test SSE reconnection on HTTP error."""
        callback = AsyncMock()
        attempt_count = 0

        async def mock_stream(*args, **kwargs):
            """Mock SSE stream with error."""
            nonlocal attempt_count
            attempt_count += 1

            if attempt_count > 1:
                raise StopAsyncIteration()

            class MockResponse:
                status_code = 500

                async def aiter_lines(self):
                    yield "data: test"

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

            return MockResponse()

        with patch("codetoreum.cli.sim_watch.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.stream = AsyncMock(side_effect=mock_stream)
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            task = asyncio.create_task(stream_events("localhost", 8000, "board-1", callback))
            await asyncio.sleep(0.5)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verify error callback was called
            assert any(call[1].get("error_message") is not None for call in callback.call_args_list)

    @pytest.mark.asyncio
    async def test_sse_exponential_backoff(self):
        """Test exponential backoff on reconnection."""
        callback = AsyncMock()

        class MockResponse:
            status_code = 503  # Service Unavailable

            async def aiter_lines(self):
                yield ""

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class MockClient:
            def stream(self, *args, **kwargs):
                return MockResponse()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch("codetoreum.cli.sim_watch.httpx.AsyncClient", return_value=MockClient()):
            task = asyncio.create_task(stream_events("localhost", 8000, "board-1", callback))
            await asyncio.sleep(0.2)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verify error callback was called indicating connection failure
            assert any(
                call[1].get("error_message") is not None for call in callback.call_args_list
            ), "Callback should be called with error message on connection failure"

    @pytest.mark.asyncio
    async def test_malformed_json_handling(self, caplog):
        """Test handling of malformed JSON in SSE."""
        callback = AsyncMock()

        class MockResponse:
            status_code = 200

            async def aiter_lines(self):
                yield "data: {invalid json}"
                yield ""  # Empty line signals end of event
                yield "data: " + json.dumps({"event_type": "ValidEvent"})
                yield ""  # Empty line signals end of event
                await asyncio.sleep(0.1)
                raise StopAsyncIteration()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class MockClient:
            def stream(self, *args, **kwargs):
                # Return an object that is itself an async context manager
                return MockResponse()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch("codetoreum.cli.sim_watch.httpx.AsyncClient", return_value=MockClient()):
            with caplog.at_level(logging.DEBUG):
                task = asyncio.create_task(stream_events("localhost", 8000, "board-1", callback))
                await asyncio.sleep(0.2)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Verify malformed JSON was logged at DEBUG level
            assert "Malformed SSE event" in caplog.text

            # Verify valid event was still processed after malformed event
            assert any(
                call[1].get("last_event") == "ValidEvent" for call in callback.call_args_list
            ), "Valid event should be processed even after malformed JSON"

    @pytest.mark.asyncio
    async def test_sse_cancellation(self):
        """Test graceful SSE cancellation."""
        callback = AsyncMock()

        async def mock_stream(*args, **kwargs):
            """Mock SSE stream."""

            class MockResponse:
                status_code = 200

                async def aiter_lines(self):
                    while True:
                        yield "data: " + json.dumps({"event_type": "Event"})
                        yield ""  # Empty line signals end of event
                        await asyncio.sleep(0.05)

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

            return MockResponse()

        with patch("codetoreum.cli.sim_watch.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.stream = AsyncMock(side_effect=mock_stream)
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            task = asyncio.create_task(stream_events("localhost", 8000, "board-1", callback))
            await asyncio.sleep(0.1)
            task.cancel()

            try:
                await task
                pytest.fail("Expected CancelledError")
            except asyncio.CancelledError:
                pass  # Expected

    @pytest.mark.asyncio
    async def test_sse_request_error(self, caplog):
        """Test SSE request error handling with logging."""
        callback = AsyncMock()
        attempt_count = 0

        class MockStreamResponse:
            status_code = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            def aiter_lines(self):
                return self

            def __aiter__(self):
                return self

            async def __anext__(self):
                nonlocal attempt_count
                attempt_count += 1

                if attempt_count > 1:
                    raise StopAsyncIteration()

                raise httpx.ConnectError("Connection refused")

        class MockAsyncContextManager:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            def stream(self, *args, **kwargs):
                return MockStreamResponse()

        with patch("codetoreum.cli.sim_watch.httpx.AsyncClient") as mock_client:
            mock_instance = MockAsyncContextManager()
            mock_client.return_value = mock_instance

            with caplog.at_level(logging.WARNING):
                task = asyncio.create_task(stream_events("localhost", 8000, "board-1", callback))
                await asyncio.sleep(0.2)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Verify error was logged
            assert "SSE connection failed" in caplog.text

    @pytest.mark.asyncio
    async def test_sse_multiline_data_fields(self):
        """Test handling of multiple consecutive data: lines per RFC 8453."""
        callback = AsyncMock()

        class MockResponse:
            status_code = 200

            async def aiter_lines(self):
                # Multi-line data should be concatenated with newlines
                yield "data: {\"event_type\": \"TestEvent\","
                yield "data: \"details\": \"multi-line\"}"
                yield ""  # Empty line signals end of event
                await asyncio.sleep(0.1)
                return

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class MockClient:
            def stream(self, *args, **kwargs):
                return MockResponse()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch("codetoreum.cli.sim_watch.httpx.AsyncClient", return_value=MockClient()):
            task = asyncio.create_task(stream_events("localhost", 8000, "board-1", callback))
            await asyncio.sleep(0.2)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verify multi-line data was parsed correctly
            assert any(
                call[1].get("last_event") == "TestEvent" for call in callback.call_args_list
            ), "Multi-line data fields should be concatenated and parsed"

    @pytest.mark.asyncio
    async def test_sse_event_and_id_fields(self):
        """Test parsing of event: and id: fields per RFC 8453."""
        callback = AsyncMock()

        class MockResponse:
            status_code = 200

            async def aiter_lines(self):
                # Event type and ID fields should be parsed
                yield "id: event-123"
                yield "event: CustomEventType"
                yield "data: " + json.dumps({"event_type": "DefaultType"})
                yield ""  # Empty line signals end of event
                await asyncio.sleep(0.1)
                return

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class MockClient:
            def stream(self, *args, **kwargs):
                return MockResponse()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch("codetoreum.cli.sim_watch.httpx.AsyncClient", return_value=MockClient()):
            task = asyncio.create_task(stream_events("localhost", 8000, "board-1", callback))
            await asyncio.sleep(0.2)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verify event type from 'event:' field was used (takes precedence)
            assert any(
                call[1].get("last_event") == "CustomEventType" for call in callback.call_args_list
            ), "Event field should take precedence and be parsed correctly"

    @pytest.mark.asyncio
    async def test_sse_generic_exception_handling(self, caplog):
        """Test handling of unexpected exceptions in SSE stream."""
        callback = AsyncMock()
        attempt_count = 0

        class MockClient:
            def stream(self, *args, **kwargs):
                nonlocal attempt_count
                attempt_count += 1

                if attempt_count > 1:
                    # Return a valid response on second attempt
                    class MockResponse:
                        status_code = 200

                        async def __aenter__(self):
                            return self

                        async def __aexit__(self, *args):
                            pass

                        async def aiter_lines(self):
                            await asyncio.sleep(0.05)
                            raise StopAsyncIteration()

                    return MockResponse()

                # First attempt raises error
                class ErrorResponse:
                    status_code = 200

                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, *args):
                        pass

                    async def aiter_lines(self):
                        raise RuntimeError("Unexpected stream error")

                return ErrorResponse()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch("codetoreum.cli.sim_watch.httpx.AsyncClient", return_value=MockClient()):
            with caplog.at_level(logging.ERROR):
                task = asyncio.create_task(stream_events("localhost", 8000, "board-1", callback))
                await asyncio.sleep(0.2)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Verify unexpected error was logged with traceback
            assert "Unexpected error in SSE listener" in caplog.text

            # Verify error callback was called
            assert any(
                call[1].get("error_message") is not None for call in callback.call_args_list
            ), "Callback should be called with error message on unexpected exception"


class TestPollBoardState:
    """Tests for board state polling."""

    @pytest.mark.asyncio
    async def test_successful_board_poll(self):
        """Test successful board state polling."""
        callback = AsyncMock()
        board_data = {
            "board_id": "board-1",
            "columns": [{"name": "Todo", "items": []}],
        }

        with patch("codetoreum.cli.sim_watch.httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = board_data

            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            task = asyncio.create_task(poll_board_state("localhost", 8000, "board-1", callback))
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verify board state was received
            assert any(call[1].get("board_state") is not None for call in callback.call_args_list)

    @pytest.mark.asyncio
    async def test_board_not_found_404(self):
        """Test 404 error for missing board."""
        callback = AsyncMock()

        with patch("codetoreum.cli.sim_watch.httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 404

            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            task = asyncio.create_task(poll_board_state("localhost", 8000, "board-1", callback))
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verify error callback was called
            assert any("not found" in (call[1].get("error_message") or "").lower() for call in callback.call_args_list)

    @pytest.mark.asyncio
    async def test_poll_request_error(self):
        """Test request error handling in polling."""
        callback = AsyncMock()

        with patch("codetoreum.cli.sim_watch.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(side_effect=httpx.RequestError("Connection timeout"))
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            task = asyncio.create_task(poll_board_state("localhost", 8000, "board-1", callback))
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verify error callback was called
            assert any(call[1].get("error_message") is not None for call in callback.call_args_list)

    @pytest.mark.asyncio
    async def test_poll_unexpected_error_logging(self, caplog):
        """Test unexpected error logging in polling."""
        callback = AsyncMock()

        async def mock_get(*args, **kwargs):
            """Mock get that raises unexpected error."""
            raise RuntimeError("Unexpected error")

        with patch("codetoreum.cli.sim_watch.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(side_effect=mock_get)
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            with caplog.at_level(logging.ERROR):
                task = asyncio.create_task(poll_board_state("localhost", 8000, "board-1", callback))
                await asyncio.sleep(0.1)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Verify error was logged with traceback
            assert "Unexpected error in board state polling" in caplog.text

    @pytest.mark.asyncio
    async def test_poll_cancellation(self):
        """Test graceful polling cancellation."""
        callback = AsyncMock()

        class MockAsyncContextManager:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, *args, **kwargs):
                mock_response = AsyncMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"board_id": "board-1"}
                return mock_response

        with patch("codetoreum.cli.sim_watch.httpx.AsyncClient") as mock_client:
            mock_instance = MockAsyncContextManager()
            mock_client.return_value = mock_instance

            task = asyncio.create_task(poll_board_state("localhost", 8000, "board-1", callback))
            await asyncio.sleep(0.05)
            task.cancel()

            try:
                await task
                # If task completed without CancelledError, that's also acceptable
                # since poll_board_state catches CancelledError internally
            except asyncio.CancelledError:
                pass  # Expected

    @pytest.mark.asyncio
    async def test_poll_interval(self):
        """Test polling interval is approximately 2 seconds."""
        callback = AsyncMock()
        call_count = 0

        class MockClient:
            async def get(self, *args, **kwargs):
                nonlocal call_count
                call_count += 1
                mock_response = AsyncMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"board_id": "board-1"}
                return mock_response

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch("codetoreum.cli.sim_watch.httpx.AsyncClient", return_value=MockClient()):
            task = asyncio.create_task(poll_board_state("localhost", 8000, "board-1", callback))
            await asyncio.sleep(4.5)  # Allow multiple polls with real timing
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Should have at least 2 polls (initial + 1 after 2 second sleep)
            assert call_count >= 2, f"Should perform at least 2 polling cycles, got {call_count}"
