"""Monitoring lifecycle protocol for event-emitting services.

This module defines the standard lifecycle for services that emit events
to the orchestrator, enabling coordinated startup and shutdown of
change detection mechanisms (polling, webhooks, etc.).

All event-emitting services implement IMonitoredService to provide
a consistent interface for controlling when they actively monitor
for changes.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class MonitoringState(Enum):
    """State of a monitoring service."""

    STOPPED = "stopped"
    STARTING = "starting"
    ACTIVE = "active"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class MonitoringStatus:
    """Current status of monitoring for a service.

    Attributes:
        state: Current monitoring state (ACTIVE, STOPPED, ERROR, etc.)
        project_id: Project being monitored
        started_at: ISO 8601 timestamp when monitoring started (None if stopped)
        error_message: Error message if state is ERROR, None otherwise
    """

    state: MonitoringState
    project_id: str
    started_at: str | None = None
    error_message: str | None = None


@dataclass
class MonitoringConfig:
    """Base configuration for monitoring services.

    Specifies how a service should monitor for changes. Subclasses can
    extend this with service-specific configuration (e.g., polling intervals,
    webhook settings, rate limits).

    Attributes:
        project_id: Project to monitor
        poll_interval_seconds: For polling-based detection, interval between checks.
                              If None, service uses its default interval.
        webhook_enabled: Whether to enable webhook-based detection if available.
                        Some services support both polling and webhooks;
                        this flag controls webhook preference.
    """

    project_id: str
    poll_interval_seconds: int | None = None
    webhook_enabled: bool = True


class IMonitoredService(ABC):
    """Standard monitoring lifecycle for event-emitting services.

    Services that emit events to the orchestrator must implement this interface
    to provide consistent control over when change detection is active.
    This allows the orchestrator to:
    1. Start monitoring when a project is activated
    2. Stop monitoring when a project is archived
    3. Query current monitoring state for diagnostics

    Detection mechanisms (polling, webhooks, etc.) are internal to the adapter
    implementation. The orchestrator only controls the lifecycle, not the method.

    Events emitted:
        Service-specific events (see implementing class docstrings)
        Generally prefixed with: board.*, comment.*, review.*, lock.*
    """

    @abstractmethod
    async def start_monitoring(
        self, project_id: str, config: MonitoringConfig
    ) -> None:
        """Begin monitoring for changes.

        Adapters should activate their change detection mechanism
        (polling, webhooks, or combined). Detection mechanism is
        adapter-internal; orchestrator doesn't specify how.

        Args:
            project_id: Project to monitor for changes
            config: Configuration for monitoring behavior

        Raises:
            ValidationError: If project_id is invalid or config is malformed
            ResourceNotFoundError: If project doesn't exist in external system
            ExternalServiceError: If unable to start monitoring (e.g., webhook
                                 registration fails)
        """

    @abstractmethod
    async def stop_monitoring(self, project_id: str) -> None:
        """Stop monitoring for changes.

        Adapters should deactivate their change detection mechanism.
        After this call, no events should be emitted for this project.

        Args:
            project_id: Project to stop monitoring

        Raises:
            ValidationError: If project_id is invalid
            ResourceNotFoundError: If not currently monitoring this project
            ExternalServiceError: If unable to stop monitoring (e.g., webhook
                                 deregistration fails)
        """

    @abstractmethod
    async def get_monitoring_status(self, project_id: str) -> MonitoringStatus:
        """Query current monitoring state.

        Returns details about the monitoring lifecycle for diagnostics
        and operational visibility.

        Args:
            project_id: Project to query status for

        Returns:
            MonitoringStatus with current state, start time, and any errors

        Raises:
            ValidationError: If project_id is invalid
        """
