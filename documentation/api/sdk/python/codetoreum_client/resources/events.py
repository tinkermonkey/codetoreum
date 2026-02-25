"""Events resource client (WebSocket)"""
import json
from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..client import CodetoreumClient


class EventsResource:
    """Client for real-time event streaming via WebSocket."""

    def __init__(self, client: "CodetoreumClient") -> None:
        self.client = client

    def stream(self) -> Iterator[dict[str, Any]]:
        """
        Stream real-time events via WebSocket (synchronous interface).

        Yields:
            Event dictionaries

        Example:
            >>> for event in client.events.stream():
            ...     print(f"{event['type']}: {event['data']}")

        Note:
            - Requires websockets library: pip install websockets
            - This method creates its own event loop and should NOT be called
              from within an existing async context. Use stream_async() instead.
            - For production use, prefer stream_async() in an async application.

        Warning:
            This synchronous wrapper may cause issues if called from within
            an existing async context. Always use stream_async() in async code.
        """
        try:
            import asyncio

            import websockets
        except ImportError:
            raise ImportError(
                "WebSocket support requires 'websockets' library. "
                "Install with: pip install websockets"
            )

        # Check if we're already in an event loop
        try:
            loop = asyncio.get_running_loop()
            raise RuntimeError(
                "stream() cannot be called from within an async context. "
                "Use stream_async() instead or run in a separate thread."
            )
        except RuntimeError:
            # No running loop, safe to proceed
            pass

        ws_url = self.client.base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/api/v2/events/stream?token={self.client.api_token}"

        async def _stream() -> AsyncIterator[dict[str, Any]]:
            async with websockets.connect(ws_url) as websocket:
                async for message in websocket:
                    yield json.loads(message)

        # Create new event loop for synchronous interface
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async_gen = _stream()
        try:
            while True:
                try:
                    event = loop.run_until_complete(async_gen.__anext__())
                    yield event
                except StopAsyncIteration:
                    break
        finally:
            loop.close()

    async def stream_async(self) -> AsyncIterator[dict[str, Any]]:
        """
        Stream real-time events via WebSocket (async interface).

        This is the preferred method for use in async applications.

        Yields:
            Event dictionaries

        Example:
            >>> async for event in client.events.stream_async():
            ...     print(f"{event['type']}: {event['data']}")

        Note:
            Requires websockets library: pip install websockets
        """
        try:
            import websockets
        except ImportError:
            raise ImportError(
                "WebSocket support requires 'websockets' library. "
                "Install with: pip install websockets"
            )

        ws_url = self.client.base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/api/v2/events/stream?token={self.client.api_token}"

        async with websockets.connect(ws_url) as websocket:
            async for message in websocket:
                yield json.loads(message)
