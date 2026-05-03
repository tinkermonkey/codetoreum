"""Production Pipeline Execution Helpers

Utilities for:
1. Verifying event store contains expected domain events
2. Handling production-only failure modes
3. Verifying PR creation and properties
4. Correlating events across pipeline stages
"""

import logging
from datetime import UTC, datetime
from typing import Any

from codetoreum.domain.events import DomainEvent
from codetoreum.ports.output.event_store import IEventStore

logger = logging.getLogger(__name__)


class EventStoreAuditTrail:
    """Verify event store contains expected domain events with proper audit trail."""

    def __init__(self, event_store: IEventStore):
        """Initialize with event store."""
        self.event_store = event_store

    async def get_events_for_work_item(self, work_item_id: str) -> list[DomainEvent]:
        """Get all events related to a work item."""
        # Since event store is keyed by aggregate_id, we need to search
        # For production, would query by work_item_id correlate
        events = []
        try:
            # Try to get events if aggregate_id equals work_item_id
            all_events = await self.event_store.get_events(work_item_id)
            if all_events:
                events.extend(all_events)
        except KeyError:
            # Aggregate not found, continue
            logger.debug(f"No events found for work item {work_item_id}")
        except Exception as e:
            logger.error(f"Error retrieving events for work item {work_item_id}", exc_info=True)
            raise
        return events

    async def assert_event_sequence(self, aggregate_id: str, expected_types: list[str]) -> None:
        """Verify events occurred in expected sequence."""
        all_events = await self.event_store.get_events(aggregate_id)
        actual_types = [e.event_type for e in all_events]

        for i, expected_type in enumerate(expected_types):
            if i >= len(actual_types):
                raise AssertionError(
                    f"Expected event {expected_type} at position {i}, but only {len(actual_types)} events found. "
                    f"Got: {actual_types}"
                )
            if actual_types[i] != expected_type:
                raise AssertionError(
                    f"Expected event {expected_type} at position {i}, got {actual_types[i]}. "
                    f"Full sequence: {actual_types}"
                )

    async def assert_event_has_payload_key(self, aggregate_id: str, event_type: str, payload_key: str) -> Any:
        """Verify event has required payload key."""
        all_events = await self.event_store.get_events(aggregate_id)

        for event in all_events:
            if event.event_type == event_type:
                if hasattr(event, "payload") and isinstance(event.payload, dict):
                    if payload_key in event.payload:
                        return event.payload[payload_key]
                    raise AssertionError(
                        f"Event {event_type} missing payload key: {payload_key}. "
                        f"Payload keys: {list(event.payload.keys())}"
                    )

        raise AssertionError(f"Event {event_type} not found in store")

    async def get_timestamp_difference(
        self, aggregate_id: str, event_type_1: str, event_type_2: str
    ) -> float | None:
        """Get time difference between two events (seconds)."""
        all_events = await self.event_store.get_events(aggregate_id)

        event_1_time: datetime | None = None
        event_2_time: datetime | None = None

        for event in all_events:
            if event.event_type == event_type_1 and hasattr(event, "occurred_at"):
                event_1_time = event.occurred_at
            if event.event_type == event_type_2 and hasattr(event, "occurred_at"):
                event_2_time = event.occurred_at

        if event_1_time and event_2_time:
            return (event_2_time - event_1_time).total_seconds()

        return None

    async def verify_complete_audit_trail(self, aggregate_id: str) -> dict[str, Any]:
        """Verify complete audit trail for a workflow run."""
        all_events = await self.event_store.get_events(aggregate_id)

        audit_info = {
            "aggregate_id": aggregate_id,
            "total_events": len(all_events),
            "event_types": [],
            "has_start": False,
            "has_completion": False,
            "duration_seconds": None,
            "all_events_have_timestamps": True,
        }

        start_time: datetime | None = None
        end_time: datetime | None = None

        for event in all_events:
            audit_info["event_types"].append(event.event_type)

            if event.event_type in ("WorkflowCreated", "WorkflowStarted"):
                audit_info["has_start"] = True
                if hasattr(event, "occurred_at") and start_time is None:
                    start_time = event.occurred_at

            if event.event_type in ("WorkflowCompleted", "WorkflowFailed"):
                audit_info["has_completion"] = True
                if hasattr(event, "occurred_at"):
                    end_time = event.occurred_at

            if not hasattr(event, "occurred_at") or event.occurred_at is None:
                audit_info["all_events_have_timestamps"] = False

        if start_time and end_time:
            audit_info["duration_seconds"] = (end_time - start_time).total_seconds()

        return audit_info


class ProductionErrorHandler:
    """Handle production-only failure modes with proper recovery."""

    @staticmethod
    def is_rate_limit_error(error: Exception) -> bool:
        """Check if error is GitHub rate limit (429)."""
        if hasattr(error, "status_code") and error.status_code == 429:
            return True
        error_str = str(error).lower()
        return "rate limit" in error_str or "429" in error_str

    @staticmethod
    def is_auth_error(error: Exception) -> bool:
        """Check if error is authentication failure (401)."""
        if hasattr(error, "status_code") and error.status_code == 401:
            return True
        error_str = str(error).lower()
        return "unauthorized" in error_str or "authentication" in error_str

    @staticmethod
    def is_permission_error(error: Exception) -> bool:
        """Check if error is permission denied (403)."""
        if hasattr(error, "status_code") and error.status_code == 403:
            return True
        error_str = str(error).lower()
        return "forbidden" in error_str or "permission" in error_str

    @staticmethod
    def is_docker_oom_error(error: Exception) -> bool:
        """Check if error is Docker OOM kill."""
        error_str = str(error).lower()
        return "out of memory" in error_str or "oom" in error_str

    @staticmethod
    def is_docker_timeout_error(error: Exception) -> bool:
        """Check if error is Docker timeout."""
        error_str = str(error).lower()
        # Check for Docker-specific timeout indicators
        if "docker" in error_str:
            return (
                "timeout" in error_str
                or "exceeded" in error_str
                or "timed out" in error_str
                or "deadline" in error_str
            )
        return False

    @staticmethod
    def is_redis_error(error: Exception) -> bool:
        """Check if error is Redis connectivity."""
        error_str = str(error).lower()
        # Check for Redis-specific connection errors
        return (
            "redis" in error_str
            or ("econnrefused" in error_str and "6379" in error_str)  # Redis default port
        )

    @staticmethod
    def is_file_permission_error(error: Exception) -> bool:
        """Check if error is file permission denied."""
        return isinstance(error, PermissionError) or (
            "permission denied" in str(error).lower() and "/" in str(error)  # Path indicator
        )

    @staticmethod
    def classify_error(error: Exception) -> str:
        """Classify error into one of production failure modes."""
        if ProductionErrorHandler.is_rate_limit_error(error):
            return "GITHUB_RATE_LIMIT"
        elif ProductionErrorHandler.is_auth_error(error):
            return "GITHUB_AUTH_FAILURE"
        elif ProductionErrorHandler.is_file_permission_error(error):
            # Check file permission BEFORE general permission (more specific)
            return "FILE_PERMISSION_DENIED"
        elif ProductionErrorHandler.is_permission_error(error):
            return "GITHUB_PERMISSION_DENIED"
        elif ProductionErrorHandler.is_docker_oom_error(error):
            return "DOCKER_OOM_KILL"
        elif ProductionErrorHandler.is_docker_timeout_error(error):
            return "DOCKER_TIMEOUT"
        elif ProductionErrorHandler.is_redis_error(error):
            return "REDIS_CONNECTION_FAILURE"
        else:
            return "UNKNOWN"

    @staticmethod
    def get_recovery_strategy(error_type: str) -> dict[str, Any]:
        """Get recovery strategy for error type."""
        strategies = {
            "GITHUB_RATE_LIMIT": {
                "retryable": True,
                "backoff_strategy": "exponential",
                "initial_delay": 1,
                "max_delay": 60,
                "max_retries": 5,
                "alert_level": "warning",
                "recovery_action": "queue_operation",
            },
            "GITHUB_AUTH_FAILURE": {
                "retryable": False,
                "backoff_strategy": None,
                "max_retries": 0,
                "alert_level": "critical",
                "recovery_action": "manual_intervention",
                "requires_credential_refresh": True,
            },
            "GITHUB_PERMISSION_DENIED": {
                "retryable": False,
                "backoff_strategy": None,
                "max_retries": 0,
                "alert_level": "critical",
                "recovery_action": "manual_intervention",
                "requires_permission_update": True,
            },
            "DOCKER_OOM_KILL": {
                "retryable": True,
                "backoff_strategy": "exponential",
                "initial_delay": 5,
                "max_delay": 60,
                "max_retries": 3,
                "alert_level": "warning",
                "recovery_action": "increase_memory_limits",
            },
            "DOCKER_TIMEOUT": {
                "retryable": True,
                "backoff_strategy": "exponential",
                "initial_delay": 5,
                "max_delay": 30,
                "max_retries": 2,
                "alert_level": "warning",
                "recovery_action": "increase_timeout",
            },
            "REDIS_CONNECTION_FAILURE": {
                "retryable": True,
                "backoff_strategy": "exponential",
                "initial_delay": 1,
                "max_delay": 10,
                "max_retries": 5,
                "alert_level": "critical",
                "recovery_action": "queue_in_memory",
            },
            "FILE_PERMISSION_DENIED": {
                "retryable": False,
                "backoff_strategy": None,
                "max_retries": 0,
                "alert_level": "critical",
                "recovery_action": "manual_intervention",
                "requires_permission_fix": True,
            },
        }
        return strategies.get(error_type, {})


class PRVerifier:
    """Verify pull request properties."""

    @staticmethod
    def verify_pr_authorship(pr_author: str, expected_author: str = "codetoreum") -> bool:
        """Verify PR is authored by Codetoreum."""
        return pr_author.lower() == expected_author.lower()

    @staticmethod
    def verify_pr_target_repository(pr_target_repo: str, expected_repo: str) -> bool:
        """Verify PR is against correct repository."""
        return pr_target_repo.lower() == expected_repo.lower()

    @staticmethod
    def verify_pr_is_mergeable(pr_mergeable: bool, pr_conflict: bool = False) -> bool:
        """Verify PR is mergeable (no conflicts)."""
        return pr_mergeable and not pr_conflict

    @staticmethod
    def verify_pr_has_content(pr_additions: int, pr_deletions: int) -> bool:
        """Verify PR has changes (not empty)."""
        return pr_additions > 0 or pr_deletions > 0

    @staticmethod
    def verify_pr_has_valid_title(pr_title: str, min_length: int = 5) -> bool:
        """Verify PR has meaningful title."""
        return pr_title is not None and len(pr_title) >= min_length

    @staticmethod
    def verify_pr_has_valid_description(pr_description: str | None, min_length: int = 10) -> bool:
        """Verify PR has meaningful description."""
        if pr_description is None:
            return False
        return len(pr_description) >= min_length

    @staticmethod
    def verify_pr_completeness(
        pr: dict[str, Any],
        verify_description: bool = False,
    ) -> tuple[bool, list[str]]:
        """Verify PR meets all requirements.

        Returns:
            (is_complete, list_of_issues)
        """
        issues = []

        if not PRVerifier.verify_pr_authorship(pr.get("author", ""), "codetoreum"):
            issues.append(f"PR author is {pr.get('author')}, expected 'codetoreum'")

        if not PRVerifier.verify_pr_has_valid_title(pr.get("title", "")):
            issues.append(f"PR title invalid: {pr.get('title')}")

        if not PRVerifier.verify_pr_has_content(pr.get("additions", 0), pr.get("deletions", 0)):
            issues.append("PR has no content changes")

        if not PRVerifier.verify_pr_is_mergeable(pr.get("mergeable", False), pr.get("has_conflicts", True)):
            issues.append("PR is not mergeable")

        if verify_description and not PRVerifier.verify_pr_has_valid_description(pr.get("description")):
            issues.append(f"PR description invalid: {pr.get('description')}")

        return len(issues) == 0, issues
