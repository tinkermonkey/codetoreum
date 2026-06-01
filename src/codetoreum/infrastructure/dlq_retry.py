"""DLQ retry handler for reconstructing and republishing failed domain events."""

import logging
from typing import TYPE_CHECKING

from codetoreum.infrastructure.event_serialization import EventSerializer
from codetoreum.infrastructure.error_ids import ErrorRegistry

if TYPE_CHECKING:
    from codetoreum.infrastructure.event_bus import EventBus

logger = logging.getLogger(__name__)


async def create_dlq_retry_handler(event_bus: "EventBus"):
    """Create a DLQ retry handler that reconstructs and republishes failed events.

    Args:
        event_bus: The event bus to publish reconstructed events to

    Returns:
        An async callable handler with signature (event_type: str, event_data: dict) -> None
    """

    async def dlq_retry_handler(event_type: str, event_data: dict) -> None:
        """Retry handler - reconstructs and republishes failed events to the event bus.

        This handler is used by the DLQ retry processor to recover from transient failures.
        It reconstructs the original domain event from stored type and data, then publishes
        it to the event bus. If this succeeds, the event is removed from the DLQ. If it fails
        (raises an exception), the DLQ will schedule another retry.

        Args:
            event_type: The name of the domain event class (e.g., "WorkItemCreatedEvent")
            event_data: The serialized event data (dict)

        Raises:
            ValueError: If the event type is not registered
            Exception: If reconstruction or publication fails (will trigger DLQ retry)
        """
        logger.info(
            f"Retrying failed event type={event_type}",
            extra={"event_data": event_data},
        )
        try:
            # Look up event class by type name in registry
            event_class = EventSerializer._codetoeum_event_registry.get(event_type)
            if event_class is None:
                raise ValueError(f"Unknown event type: {event_type}")
            # Reconstruct event using from_dict()
            reconstructed_event = event_class.from_dict(event_data)
            # Publish to event bus
            await event_bus.publish(reconstructed_event)
        except Exception as e:
            logger.error(
                f"Failed to reconstruct and publish event type={event_type}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
            )
            raise

    return dlq_retry_handler
