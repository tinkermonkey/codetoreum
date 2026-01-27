"""Metrics collector for adapter events."""

import logging
from typing import Dict, Any, Optional

from codetoreum.domain.events import DomainEvent
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.event_types import EventTypes

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
            # Repair cycle metrics
            "repair_cycles_started": 0,
            "repair_cycles_completed": 0,
            "repair_cycles_successful": 0,
            "repair_cycles_failed": 0,
            "repair_cycles_fast_failed": 0,
            "repair_cycle_duration_seconds": [],  # List of durations
            "repair_cycle_test_iterations": {},  # {test_type: count}
            "repair_cycle_files_fixed": [],  # List of file counts per cycle
            "repair_cycle_agent_calls": [],  # List of agent call counts per cycle
            "repair_cycle_test_executions": {},  # {test_type: count}
            "repair_cycle_file_fixes": {},  # {file_path: count}
            "repair_cycle_warnings_reviewed": 0,
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
            EventTypes.WORKITEM_COLUMN_CHANGED,
            self._record_column_change
        )

        # Lock events
        self.event_bus.subscribe(
            EventTypes.LOCK_ACQUIRED,
            self._record_lock_acquisition
        )
        self.event_bus.subscribe(
            EventTypes.LOCK_RELEASED,
            self._record_lock_release
        )

        # Review events
        self.event_bus.subscribe(
            EventTypes.REVIEW_STATUS_CHANGED,
            self._record_review_status
        )

        # Discussion events
        self.event_bus.subscribe(
            EventTypes.COMMENT_POSTED,
            self._record_comment
        )
        self.event_bus.subscribe(
            EventTypes.COMMENT_NEEDS_RESPONSE,
            self._record_comment_needs_response
        )

        # Repair cycle events
        self.event_bus.subscribe(
            EventTypes.REPAIR_CYCLE_STARTED,
            self._record_repair_cycle_started
        )
        self.event_bus.subscribe(
            EventTypes.REPAIR_CYCLE_TEST_EXECUTION_COMPLETED,
            self._record_repair_cycle_test_execution
        )
        self.event_bus.subscribe(
            EventTypes.REPAIR_CYCLE_FILE_FIX_COMPLETED,
            self._record_repair_cycle_file_fix
        )
        self.event_bus.subscribe(
            EventTypes.REPAIR_CYCLE_WARNING_REVIEW_COMPLETED,
            self._record_repair_cycle_warning_review
        )
        self.event_bus.subscribe(
            EventTypes.REPAIR_CYCLE_FAST_FAIL,
            self._record_repair_cycle_fast_fail
        )
        self.event_bus.subscribe(
            EventTypes.REPAIR_CYCLE_COMPLETED,
            self._record_repair_cycle_completed
        )

        logger.info("MetricsCollector subscribed to adapter events")

    def _get_event_attribute(self, event: DomainEvent, attribute: str, default: Any = None) -> Any:
        """
        Extract an attribute from an event supporting both dict and object formats.

        Handles events that may be either:
        - Objects with attributes
        - Objects with a payload dict containing the attribute

        Args:
            event: Event object
            attribute: Attribute name to extract
            default: Default value if attribute not found

        Returns:
            Attribute value or default
        """
        # Try as object attribute first
        if hasattr(event, attribute):
            return getattr(event, attribute, default)

        # Try as payload dict entry
        if hasattr(event, 'payload') and isinstance(event.payload, dict):
            return event.payload.get(attribute, default)

        return default

    async def _record_column_change(self, event: DomainEvent) -> None:
        """
        Record column change metric.

        Args:
            event: workitem.column_changed event
        """
        try:
            to_column = self._get_event_attribute(event, "to_column")
            if not to_column:
                return

            # Track column changes
            if to_column not in self._metrics["column_changes"]:
                self._metrics["column_changes"][to_column] = 0
            self._metrics["column_changes"][to_column] += 1

            # Track agent triggering if agent would be triggered
            agent_name = self._get_event_attribute(event, "agent_name")
            if agent_name:
                self._metrics["agents_triggered"] += 1

            logger.debug(
                f"Recorded column change to '{to_column}' "
                f"(total: {self._metrics['column_changes'][to_column]})"
            )

        except Exception as e:
            logger.error(
                f"Error recording column change metric: {e}",
                exc_info=True,
                extra={"error_id": "ERR_METRICS_COLUMN_CHANGE_FAILED"}
            )
            self._metrics["errors"] += 1

    async def _record_lock_acquisition(self, event: DomainEvent) -> None:
        """
        Record lock acquisition metric.

        Args:
            event: lock.acquired event
        """
        try:
            self._metrics["lock_acquisitions"] += 1
            acquisition_method = self._get_event_attribute(event, "acquisition_method", "unknown")

            logger.debug(
                f"Recorded lock acquisition "
                f"(method: {acquisition_method}, total: {self._metrics['lock_acquisitions']})"
            )

        except Exception as e:
            logger.error(
                f"Error recording lock acquisition metric: {e}",
                exc_info=True,
                extra={"error_id": "ERR_METRICS_LOCK_ACQUISITION_FAILED"}
            )
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
            duration_ms = self._get_event_attribute(event, "duration_ms")
            reason = self._get_event_attribute(event, "reason", "unknown")

            if duration_ms:
                self._metrics["lock_wait_time_ms"].append(duration_ms)

            logger.debug(
                f"Recorded lock release "
                f"(reason: {reason}, total: {self._metrics['lock_releases']})"
            )

        except Exception as e:
            logger.error(
                f"Error recording lock release metric: {e}",
                exc_info=True,
                extra={"error_id": "ERR_METRICS_LOCK_RELEASE_FAILED"}
            )
            self._metrics["errors"] += 1

    async def _record_review_status(self, event: DomainEvent) -> None:
        """
        Record review status change metric.

        Args:
            event: review.status_changed event
        """
        try:
            new_status = self._get_event_attribute(event, "new_status")

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
            logger.error(
                f"Error recording review status metric: {e}",
                exc_info=True,
                extra={"error_id": "ERR_METRICS_REVIEW_STATUS_FAILED"}
            )
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
            logger.error(
                f"Error recording comment metric: {e}",
                exc_info=True,
                extra={"error_id": "ERR_METRICS_COMMENT_FAILED"}
            )
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
            logger.error(
                f"Error recording comment response metric: {e}",
                exc_info=True,
                extra={"error_id": "ERR_METRICS_COMMENT_RESPONSE_FAILED"}
            )
            self._metrics["errors"] += 1

    async def _record_repair_cycle_started(self, event: DomainEvent) -> None:
        """
        Record repair cycle started metric.

        Args:
            event: repair_cycle.started event
        """
        try:
            self._metrics["repair_cycles_started"] += 1
            stage_name = self._get_event_attribute(event, "stage_name")
            logger.debug(
                f"Recorded repair cycle started for stage '{stage_name}' "
                f"(total: {self._metrics['repair_cycles_started']})"
            )

        except Exception as e:
            logger.error(
                f"Error recording repair cycle started metric: {e}",
                exc_info=True,
                extra={"error_id": "ERR_METRICS_REPAIR_CYCLE_STARTED_FAILED"}
            )
            self._metrics["errors"] += 1

    async def _record_repair_cycle_test_execution(self, event: DomainEvent) -> None:
        """
        Record repair cycle test execution metric.

        Args:
            event: repair_cycle.test_execution_completed event
        """
        try:
            test_type = self._get_event_attribute(event, "test_type")
            passed_count = self._get_event_attribute(event, "passed_count", 0)
            failed_count = self._get_event_attribute(event, "failed_count", 0)
            iteration = self._get_event_attribute(event, "iteration", 0)

            if test_type not in self._metrics["repair_cycle_test_executions"]:
                self._metrics["repair_cycle_test_executions"][test_type] = 0

            self._metrics["repair_cycle_test_executions"][test_type] += 1

            logger.debug(
                f"Recorded repair cycle test execution: {test_type} iteration {iteration} "
                f"(passed: {passed_count}, failed: {failed_count})"
            )

        except Exception as e:
            logger.error(
                f"Error recording repair cycle test execution metric: {e}",
                exc_info=True,
                extra={"error_id": "ERR_METRICS_REPAIR_CYCLE_TEST_FAILED"}
            )
            self._metrics["errors"] += 1

    async def _record_repair_cycle_file_fix(self, event: DomainEvent) -> None:
        """
        Record repair cycle file fix metric.

        Args:
            event: repair_cycle.file_fix_completed event
        """
        try:
            file_path = self._get_event_attribute(event, "file_path")
            fixed = self._get_event_attribute(event, "fixed", False)
            iterations_used = self._get_event_attribute(event, "iterations_used", 0)

            if file_path not in self._metrics["repair_cycle_file_fixes"]:
                self._metrics["repair_cycle_file_fixes"][file_path] = 0

            if fixed:
                self._metrics["repair_cycle_file_fixes"][file_path] += 1

            logger.debug(
                f"Recorded repair cycle file fix: {file_path} "
                f"(fixed: {fixed}, iterations: {iterations_used})"
            )

        except Exception as e:
            logger.error(
                f"Error recording repair cycle file fix metric: {e}",
                exc_info=True,
                extra={"error_id": "ERR_METRICS_REPAIR_CYCLE_FILE_FIX_FAILED"}
            )
            self._metrics["errors"] += 1

    async def _record_repair_cycle_warning_review(self, event: DomainEvent) -> None:
        """
        Record repair cycle warning review metric.

        Args:
            event: repair_cycle.warning_review_completed event
        """
        try:
            warnings_reviewed = self._get_event_attribute(event, "warnings_reviewed", 0)
            self._metrics["repair_cycle_warnings_reviewed"] += warnings_reviewed

            logger.debug(
                f"Recorded repair cycle warning review "
                f"(warnings reviewed: {warnings_reviewed})"
            )

        except Exception as e:
            logger.error(
                f"Error recording repair cycle warning review metric: {e}",
                exc_info=True,
                extra={"error_id": "ERR_METRICS_REPAIR_CYCLE_WARNING_REVIEW_FAILED"}
            )
            self._metrics["errors"] += 1

    async def _record_repair_cycle_fast_fail(self, event: DomainEvent) -> None:
        """
        Record repair cycle fast-fail metric.

        Args:
            event: repair_cycle.fast_fail event
        """
        try:
            reason = self._get_event_attribute(event, "reason")
            self._metrics["repair_cycles_fast_failed"] += 1

            logger.debug(
                f"Recorded repair cycle fast-fail "
                f"(reason: {reason}, total: {self._metrics['repair_cycles_fast_failed']})"
            )

        except Exception as e:
            logger.error(
                f"Error recording repair cycle fast-fail metric: {e}",
                exc_info=True,
                extra={"error_id": "ERR_METRICS_REPAIR_CYCLE_FAST_FAIL_FAILED"}
            )
            self._metrics["errors"] += 1

    async def _record_repair_cycle_completed(self, event: DomainEvent) -> None:
        """
        Record repair cycle completed metric.

        Args:
            event: repair_cycle.completed event
        """
        try:
            overall_success = self._get_event_attribute(event, "overall_success", False)
            total_iterations = self._get_event_attribute(event, "total_iterations", 0)
            total_agent_calls = self._get_event_attribute(event, "total_agent_calls", 0)
            duration_seconds = self._get_event_attribute(event, "duration_seconds", 0.0)

            self._metrics["repair_cycles_completed"] += 1

            if overall_success:
                self._metrics["repair_cycles_successful"] += 1
            else:
                self._metrics["repair_cycles_failed"] += 1

            self._metrics["repair_cycle_duration_seconds"].append(duration_seconds)
            self._metrics["repair_cycle_test_iterations"][str(total_iterations)] = (
                self._metrics["repair_cycle_test_iterations"].get(str(total_iterations), 0) + 1
            )
            self._metrics["repair_cycle_agent_calls"].append(total_agent_calls)

            logger.debug(
                f"Recorded repair cycle completed "
                f"(success: {overall_success}, iterations: {total_iterations}, "
                f"agent_calls: {total_agent_calls}, duration: {duration_seconds}s)"
            )

        except Exception as e:
            logger.error(
                f"Error recording repair cycle completed metric: {e}",
                exc_info=True,
                extra={"error_id": "ERR_METRICS_REPAIR_CYCLE_COMPLETED_FAILED"}
            )
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

        # Calculate repair cycle averages
        avg_repair_cycle_duration_seconds = None
        if self._metrics["repair_cycle_duration_seconds"]:
            avg_repair_cycle_duration_seconds = (
                sum(self._metrics["repair_cycle_duration_seconds"]) /
                len(self._metrics["repair_cycle_duration_seconds"])
            )

        avg_repair_cycle_agent_calls = None
        if self._metrics["repair_cycle_agent_calls"]:
            avg_repair_cycle_agent_calls = (
                sum(self._metrics["repair_cycle_agent_calls"]) /
                len(self._metrics["repair_cycle_agent_calls"])
            )

        # Calculate repair cycle success rate
        repair_cycle_success_rate = None
        if self._metrics["repair_cycles_completed"] > 0:
            repair_cycle_success_rate = (
                self._metrics["repair_cycles_successful"] /
                self._metrics["repair_cycles_completed"] * 100
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
            # Repair cycle metrics
            "repair_cycles_started": self._metrics["repair_cycles_started"],
            "repair_cycles_completed": self._metrics["repair_cycles_completed"],
            "repair_cycles_successful": self._metrics["repair_cycles_successful"],
            "repair_cycles_failed": self._metrics["repair_cycles_failed"],
            "repair_cycles_fast_failed": self._metrics["repair_cycles_fast_failed"],
            "repair_cycle_success_rate_percent": repair_cycle_success_rate,
            "avg_repair_cycle_duration_seconds": avg_repair_cycle_duration_seconds,
            "repair_cycle_test_executions": self._metrics["repair_cycle_test_executions"],
            "repair_cycle_test_iterations": self._metrics["repair_cycle_test_iterations"],
            "avg_repair_cycle_agent_calls": avg_repair_cycle_agent_calls,
            "repair_cycle_file_fixes": self._metrics["repair_cycle_file_fixes"],
            "repair_cycle_warnings_reviewed": self._metrics["repair_cycle_warnings_reviewed"],
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
            # Repair cycle metrics
            "repair_cycles_started": 0,
            "repair_cycles_completed": 0,
            "repair_cycles_successful": 0,
            "repair_cycles_failed": 0,
            "repair_cycles_fast_failed": 0,
            "repair_cycle_duration_seconds": [],
            "repair_cycle_test_iterations": {},
            "repair_cycle_files_fixed": [],
            "repair_cycle_agent_calls": [],
            "repair_cycle_test_executions": {},
            "repair_cycle_file_fixes": {},
            "repair_cycle_warnings_reviewed": 0,
        }
        logger.info("Metrics collector reset")
