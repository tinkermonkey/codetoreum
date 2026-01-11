"""Metrics collector for adapter events."""

import logging
from typing import Dict, Any, Optional

from codetoreum.domain.events import DomainEvent
from codetoreum.infrastructure.event_bus import EventBus

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Collects metrics from adapter events via event bus.

    Subscribes to adapter events and records metrics for:
    - Column changes and workflow progression
    - Lock acquisitions and releases
    - Review status changes
    - Comment activity

    Metrics are aggregated and can be exposed via Prometheus or other systems.
    """

    def __init__(self, event_bus: Optional[EventBus] = None):
        """
        Initialize metrics collector.

        Args:
            event_bus: Event bus to subscribe to for events
        """
        self.event_bus = event_bus

        # Metrics
        self._metrics: Dict[str, Any] = {
            "column_changes": {},  # {column_name: count}
            "lock_acquisitions": 0,
            "lock_releases": 0,
            "lock_wait_time_ms": [],  # List of wait times
            "reviews_approved": 0,
            "reviews_changes_requested": 0,
            "comments_processed": 0,
            "agents_triggered": 0,
            "errors": 0,
        }

        # Subscribe to events if bus provided
        if self.event_bus:
            self._subscribe_to_events()

    def _subscribe_to_events(self) -> None:
        """Subscribe to adapter events for metrics collection."""
        if not self.event_bus:
            return

        # Board events
        self.event_bus.subscribe(
            "workitem.column_changed",
            self._record_column_change
        )

        # Lock events
        self.event_bus.subscribe(
            "lock.acquired",
            self._record_lock_acquisition
        )
        self.event_bus.subscribe(
            "lock.released",
            self._record_lock_release
        )

        # Review events
        self.event_bus.subscribe(
            "review.status_changed",
            self._record_review_status
        )

        # Discussion events
        self.event_bus.subscribe(
            "comment.posted",
            self._record_comment
        )
        self.event_bus.subscribe(
            "comment.needs_response",
            self._record_comment_needs_response
        )

        logger.info("MetricsCollector subscribed to adapter events")

    async def _record_column_change(self, event: DomainEvent) -> None:
        """
        Record column change metric.

        Args:
            event: workitem.column_changed event
        """
        try:
            # Handle both dict and object event formats
            if hasattr(event, 'payload'):
                to_column = event.payload.get("to_column")
            else:
                to_column = getattr(event, "to_column", None)

            if not to_column:
                return

            # Track column changes
            if to_column not in self._metrics["column_changes"]:
                self._metrics["column_changes"][to_column] = 0
            self._metrics["column_changes"][to_column] += 1

            # Track agent triggering if agent would be triggered
            if hasattr(event, 'payload'):
                agent_name = event.payload.get("agent_name")
            else:
                agent_name = getattr(event, "agent_name", None)

            if agent_name:
                self._metrics["agents_triggered"] += 1

            logger.debug(
                f"Recorded column change to '{to_column}' "
                f"(total: {self._metrics['column_changes'][to_column]})"
            )

        except Exception as e:
            logger.error(f"Error recording column change metric: {e}")
            self._metrics["errors"] += 1

    async def _record_lock_acquisition(self, event: DomainEvent) -> None:
        """
        Record lock acquisition metric.

        Args:
            event: lock.acquired event
        """
        try:
            self._metrics["lock_acquisitions"] += 1

            if hasattr(event, 'payload'):
                acquisition_method = event.payload.get("acquisition_method", "unknown")
            else:
                acquisition_method = getattr(event, "acquisition_method", "unknown")

            logger.debug(
                f"Recorded lock acquisition "
                f"(method: {acquisition_method}, total: {self._metrics['lock_acquisitions']})"
            )

        except Exception as e:
            logger.error(f"Error recording lock acquisition metric: {e}")
            self._metrics["errors"] += 1

    async def _record_lock_release(self, event: DomainEvent) -> None:
        """
        Record lock release metric.

        Args:
            event: lock.released event
        """
        try:
            self._metrics["lock_releases"] += 1

            # Record lock duration if available
            if hasattr(event, 'payload'):
                duration_ms = event.payload.get("duration_ms")
                reason = event.payload.get("reason", "unknown")
            else:
                duration_ms = getattr(event, "duration_ms", None)
                reason = getattr(event, "reason", "unknown")

            if duration_ms:
                self._metrics["lock_wait_time_ms"].append(duration_ms)

            logger.debug(
                f"Recorded lock release "
                f"(reason: {reason}, total: {self._metrics['lock_releases']})"
            )

        except Exception as e:
            logger.error(f"Error recording lock release metric: {e}")
            self._metrics["errors"] += 1

    async def _record_review_status(self, event: DomainEvent) -> None:
        """
        Record review status change metric.

        Args:
            event: review.status_changed event
        """
        try:
            if hasattr(event, 'payload'):
                new_status = event.payload.get("new_status")
            else:
                new_status = getattr(event, "new_status", None)

            if new_status == "approved":
                self._metrics["reviews_approved"] += 1
                logger.debug(
                    f"Recorded review approval "
                    f"(total approved: {self._metrics['reviews_approved']})"
                )
            elif new_status == "changes_requested":
                self._metrics["reviews_changes_requested"] += 1
                logger.debug(
                    f"Recorded changes requested "
                    f"(total: {self._metrics['reviews_changes_requested']})"
                )

        except Exception as e:
            logger.error(f"Error recording review status metric: {e}")
            self._metrics["errors"] += 1

    async def _record_comment(self, event: DomainEvent) -> None:
        """
        Record comment posted metric.

        Args:
            event: comment.posted event
        """
        try:
            self._metrics["comments_processed"] += 1
            logger.debug(
                f"Recorded comment posted "
                f"(total: {self._metrics['comments_processed']})"
            )

        except Exception as e:
            logger.error(f"Error recording comment metric: {e}")
            self._metrics["errors"] += 1

    async def _record_comment_needs_response(self, event: DomainEvent) -> None:
        """
        Record comment requiring response metric.

        Args:
            event: comment.needs_response event
        """
        try:
            # Also counts as agent trigger
            self._metrics["agents_triggered"] += 1
            logger.debug(f"Recorded comment requiring response")

        except Exception as e:
            logger.error(f"Error recording comment response metric: {e}")
            self._metrics["errors"] += 1

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get collected metrics.

        Returns:
            Dictionary with current metrics
        """
        # Calculate averages
        avg_lock_wait_ms = None
        if self._metrics["lock_wait_time_ms"]:
            avg_lock_wait_ms = sum(self._metrics["lock_wait_time_ms"]) / len(
                self._metrics["lock_wait_time_ms"]
            )

        return {
            "column_changes": self._metrics["column_changes"],
            "lock_acquisitions": self._metrics["lock_acquisitions"],
            "lock_releases": self._metrics["lock_releases"],
            "avg_lock_wait_ms": avg_lock_wait_ms,
            "reviews_approved": self._metrics["reviews_approved"],
            "reviews_changes_requested": self._metrics["reviews_changes_requested"],
            "comments_processed": self._metrics["comments_processed"],
            "agents_triggered": self._metrics["agents_triggered"],
            "errors": self._metrics["errors"],
        }

    def reset_metrics(self) -> None:
        """Reset all metrics (for testing)."""
        self._metrics = {
            "column_changes": {},
            "lock_acquisitions": 0,
            "lock_releases": 0,
            "lock_wait_time_ms": [],
            "reviews_approved": 0,
            "reviews_changes_requested": 0,
            "comments_processed": 0,
            "agents_triggered": 0,
            "errors": 0,
        }
        logger.info("Metrics collector reset")
