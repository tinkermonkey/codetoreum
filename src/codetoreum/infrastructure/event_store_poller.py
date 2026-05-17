"""Event store poller for bridging persisted events to the in-process event bus.

This service polls the event store for new events at regular intervals and publishes
them to the event bus, enabling cross-process event distribution. This is critical for
workflows where events are written to persistent storage (e.g., by CLI triggers) and
need to be processed by handlers registered on the in-process event bus.

The poller:
- Maintains a cursor (last_polled_timestamp) to avoid re-processing events
- Polls at configurable intervals (default 1 second)
- Handles transient failures gracefully
- Stops cleanly on shutdown
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.output.event_store import IEventStore

logger = logging.getLogger(__name__)


class EventStorePoller:
    """
    Polls the event store for new events and publishes them to the event bus.

    Usage:
        poller = EventStorePoller(event_store, event_bus, poll_interval_seconds=1)
        await poller.start()
        # ... poller runs in background ...
        await poller.stop()
    """

    def __init__(
        self,
        event_store: IEventStore,
        event_bus: EventBus,
        poll_interval_seconds: float = 1.0,
    ):
        """
        Initialize event store poller.

        Args:
            event_store: Event store to poll for new events
            event_bus: Event bus to publish events to
            poll_interval_seconds: Polling interval in seconds (default: 1)
        """
        self.event_store = event_store
        self.event_bus = event_bus
        self.poll_interval_seconds = poll_interval_seconds

        # Polling state
        self._running = False
        self._poll_task: asyncio.Task | None = None
        self._last_polled_timestamp = datetime.now(UTC) - timedelta(minutes=5)  # Start from 5 minutes ago

    async def start(self) -> None:
        """
        Start the event store poller.

        Starts a background task that continuously polls the event store
        for new events and publishes them to the event bus.

        Raises:
            RuntimeError: If poller is already running
        """
        if self._running:
            message = "Event store poller is already running"
            raise RuntimeError(message)

        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info(
            f"Started event store poller (poll_interval={self.poll_interval_seconds}s)",
            extra={"poll_interval_seconds": self.poll_interval_seconds},
        )

    async def stop(self) -> None:
        """
        Stop the event store poller.

        Cancels the polling loop and waits for it to finish.
        """
        if not self._running:
            return

        self._running = False

        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

        logger.info("Stopped event store poller")

    async def _poll_loop(self) -> None:
        """
        Poll loop that continuously fetches and publishes events.

        This runs until stop() is called. On transient errors, it logs and
        continues polling. On fatal errors, it logs and exits.
        """
        while self._running:
            try:
                await self._poll_once()
                await asyncio.sleep(self.poll_interval_seconds)
            except asyncio.CancelledError:
                # Graceful shutdown requested
                break
            except Exception as e:
                logger.error(
                    f"Error in event store poll loop: {e}",
                    exc_info=True,
                    extra={"error_type": type(e).__name__},
                )
                # Continue polling despite errors
                await asyncio.sleep(self.poll_interval_seconds)

    async def _poll_once(self) -> None:
        """
        Poll the event store once and publish any new events.

        This method:
        1. Queries the event store for events since last_polled_timestamp
        2. Updates last_polled_timestamp
        3. Publishes each event to the event bus
        4. Handles errors per-event without stopping the poll
        """
        try:
            # Query for events since last poll
            events = await self.event_store.get_events_since(
                since=self._last_polled_timestamp,
                stream_id=None,  # Poll all streams
            )

            if not events:
                return

            # Update last polled time to now (before processing)
            # This ensures we don't re-process events if polling is interrupted
            self._last_polled_timestamp = datetime.now(UTC)

            # Publish each event to the bus
            for event in events:
                try:
                    await self.event_bus.publish(event)
                    logger.debug(
                        f"Published event {event.event_type} (ID: {event.event_id}) from event store to bus",
                        extra={
                            "event_type": event.event_type,
                            "event_id": str(event.event_id),
                        },
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to publish event {event.event_type} to bus: {e}",
                        exc_info=True,
                        extra={
                            "event_type": event.event_type,
                            "event_id": str(event.event_id),
                            "error_type": type(e).__name__,
                        },
                    )
                    # Continue publishing other events despite this error

        except Exception as e:
            logger.error(
                f"Error polling event store: {e}",
                exc_info=True,
                extra={"error_type": type(e).__name__},
            )
            # Don't update last_polled_timestamp on error, so we retry next time
