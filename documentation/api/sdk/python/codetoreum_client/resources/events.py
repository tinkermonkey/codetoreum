"""Events resource client (WebSocket)"""
import json
from typing import Callable, Iterator, Optional


class EventsResource:
    """Client for real-time event streaming via WebSocket."""

    def __init__(self, client):
        self.client = client

    def stream(self) -> Iterator[dict]:
        """
        Stream real-time events via WebSocket.

        Yields:
            Event dictionaries

        Example:
            >>> for event in client.events.stream():
            ...     print(f"{event['type']}: {event['data']}")

        Note:
            Requires websockets library: pip install websockets
        """
        try:
            import websockets
            import asyncio
        except ImportError:
            raise ImportError(
                "WebSocket support requires 'websockets' library. "
                "Install with: pip install websockets"
            )

        ws_url = self.client.base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/api/v2/events/stream?token={self.client.api_token}"

        async def _stream():
            async with websockets.connect(ws_url) as websocket:
                async for message in websocket:
                    yield json.loads(message)

        # Run async generator
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async_gen = _stream()
        while True:
            try:
                event = loop.run_until_complete(async_gen.__anext__())
                yield event
            except StopAsyncIteration:
                break
