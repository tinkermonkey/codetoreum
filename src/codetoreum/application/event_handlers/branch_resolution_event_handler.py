"""Event handler for branch resolution events.

Subscribes to branch resolution events and maintains an audit trail:
- BranchResolvedEvent: Primary audit event for all branch resolutions
- BranchReusedEvent: Outcome-specific event when existing branch is selected
- BranchResolutionCreatedEvent: Outcome-specific event when new branch is created

All events are logged with structured fields for audit trail and metrics.
"""

import logging

from codetoreum.domain.events import DomainEvent
from codetoreum.domain.events.branch_events import (
    BranchResolutionCreatedEvent,
    BranchResolvedEvent,
    BranchReusedEvent,
)
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.event_bus import EventBus, EventHandler, event_handler
from codetoreum.infrastructure.observability.instrumentation import (
    instrument_async_function,
)

logger = logging.getLogger(__name__)


@event_handler("BranchResolvedEvent", "BranchReusedEvent", "BranchResolutionCreatedEvent")
class BranchResolutionEventHandler(EventHandler):
    """Handles branch resolution events for audit trail and metrics.

    Subscribes to branch resolution events and logs them with structured fields
    for complete audit trail and metrics tracking.

    Example:
        handler = BranchResolutionEventHandler()
        bus.register_handler(handler)

        # When a branch resolution occurs:
        event = BranchResolvedEvent(
            project_id="proj-1",
            issue_id="123",
            action="reuse",
            branch_name="feature/issue-123-fix-auth",
            confidence=0.95,
            reason="Exact match found for issue #123",
            resolution_strategy="exact_match"
        )
        await bus.publish(event)
        # Handler logs event with structured fields for audit trail
    """

    def __init__(self, event_bus: EventBus | None = None):
        """
        Initialize branch resolution event handler.

        Args:
            event_bus: Optional event bus for publishing additional events
        """
        self._event_bus = event_bus

    @property
    def event_bus(self) -> EventBus | None:
        """Get the event bus if configured."""
        return self._event_bus

    def get_event_types(self) -> list[str]:
        """Get list of event types this handler processes.

        Returns:
            List of event type names
        """
        return ["BranchResolvedEvent", "BranchReusedEvent", "BranchResolutionCreatedEvent"]

    @instrument_async_function(
        name="branch_resolution_event_handler.handle",
        attributes={
            "component": "branch_resolution",
            "layer": "application",
        },
    )
    async def handle(self, event: DomainEvent) -> None:
        """
        Handle branch resolution event and log with structured fields.

        Args:
            event: Domain event to handle

        Raises:
            Exception: If handling fails (logged and re-raised)
        """
        try:
            if isinstance(event, BranchResolvedEvent):
                await self._handle_branch_resolved(event)
            elif isinstance(event, BranchReusedEvent):
                await self._handle_branch_reused(event)
            elif isinstance(event, BranchResolutionCreatedEvent):
                await self._handle_branch_created(event)
            else:
                logger.warning(
                    f"BranchResolutionEventHandler received unexpected event type: {event.event_type}"
                )
        except Exception as e:
            logger.error(
                f"Error handling branch resolution event: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_BRANCH_RESOLUTION_ERROR},
            )
            raise

    @instrument_async_function(
        name="branch_resolution_event_handler.handle_branch_resolved",
        attributes={
            "component": "branch_resolution",
            "layer": "application",
        },
    )
    async def _handle_branch_resolved(self, event: BranchResolvedEvent) -> None:
        """
        Log branch resolved event with structured audit trail fields.

        Args:
            event: BranchResolvedEvent to process
        """
        logger.info(
            f"Branch resolved: {event.action} '{event.branch_name}' for issue #{event.issue_id}",
            extra={
                "event_type": event.type,
                "event_id": event.event_id,
                "project_id": event.project_id,
                "issue_id": event.issue_id,
                "branch_name": event.branch_name,
                "action": event.action,
                "confidence": event.confidence,
                "resolution_strategy": event.resolution_strategy,
                "parent_issue_id": event.parent_issue_id,
                "reason": event.reason,
                "timestamp": event.timestamp,
                "source": event.source,
            },
        )

    @instrument_async_function(
        name="branch_resolution_event_handler.handle_branch_reused",
        attributes={
            "component": "branch_resolution",
            "layer": "application",
        },
    )
    async def _handle_branch_reused(self, event: BranchReusedEvent) -> None:
        """
        Log branch reused event with structured audit trail fields.

        Args:
            event: BranchReusedEvent to process
        """
        logger.info(
            f"Branch reused: '{event.branch_name}' for issue #{event.issue_id}",
            extra={
                "event_type": event.type,
                "event_id": event.event_id,
                "project_id": event.project_id,
                "issue_id": event.issue_id,
                "branch_name": event.branch_name,
                "confidence": event.confidence,
                "resolution_strategy": event.resolution_strategy,
                "parent_issue_id": event.parent_issue_id,
                "reason": event.reason,
                "timestamp": event.timestamp,
                "source": event.source,
            },
        )

    @instrument_async_function(
        name="branch_resolution_event_handler.handle_branch_created",
        attributes={
            "component": "branch_resolution",
            "layer": "application",
        },
    )
    async def _handle_branch_created(self, event: BranchResolutionCreatedEvent) -> None:
        """
        Log branch created event with structured audit trail fields.

        Args:
            event: BranchResolutionCreatedEvent to process
        """
        logger.info(
            f"Branch created: '{event.branch_name}' for issue #{event.issue_id}",
            extra={
                "event_type": event.type,
                "event_id": event.event_id,
                "project_id": event.project_id,
                "issue_id": event.issue_id,
                "branch_name": event.branch_name,
                "confidence": event.confidence,
                "reason": event.reason,
                "resolution_strategy": event.resolution_strategy,
                "parent_issue_id": event.parent_issue_id,
                "timestamp": event.timestamp,
                "source": event.source,
            },
        )
