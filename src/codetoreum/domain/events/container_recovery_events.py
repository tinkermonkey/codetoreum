"""Container recovery domain events for orchestrator startup recovery.

Events track the lifecycle of container recovery operations at orchestrator
startup, including discovery, assessment, reconnection, and cleanup actions.

All events are immutable (frozen dataclasses) to maintain event sourcing
audit trail integrity and enable observability integration.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional
from uuid import uuid4

from .adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class ContainerRecoveredEvent(CodetoreumEvent):
    """Emitted when a container is successfully reconnected during recovery.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "container_recovery.recovered"
        container_id (str): Docker container ID
        container_name (str): Container name for identification
        project_id (str): Project ID the container belongs to
        agent_id (str): Agent ID the container is running
        work_item_id (Optional[str]): Work item ID if available
        execution_id (Optional[str]): Execution ID if available
        uptime_seconds (float): Container uptime in seconds at recovery
        recovery_action (str): Recovery action taken ("reconnect_with_monitoring" or "reconnect_limited")
        timestamp (str): ISO 8601 timestamp when recovery occurred
    """

    container_id: str = ""
    container_name: str = ""
    project_id: str = ""
    agent_id: str = ""
    work_item_id: Optional[str] = None
    execution_id: Optional[str] = None
    uptime_seconds: float = 0.0
    recovery_action: Literal["reconnect_with_monitoring", "reconnect_limited"] = "reconnect_with_monitoring"

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.container_id:
            raise ValueError("container_id is required")
        if not self.container_name:
            raise ValueError("container_name is required")
        if not self.project_id:
            raise ValueError("project_id is required")
        if not self.agent_id:
            raise ValueError("agent_id is required")
        if self.uptime_seconds < 0:
            raise ValueError("uptime_seconds must be >= 0")
        if self.recovery_action not in ("reconnect_with_monitoring", "reconnect_limited"):
            raise ValueError("recovery_action must be one of: reconnect_with_monitoring, reconnect_limited")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "container_id": self.container_id,
            "container_name": self.container_name,
            "project_id": self.project_id,
            "agent_id": self.agent_id,
            "work_item_id": self.work_item_id,
            "execution_id": self.execution_id,
            "uptime_seconds": self.uptime_seconds,
            "recovery_action": self.recovery_action,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ContainerRecoveredEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "container_recovery.recovered"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            container_id=data.get("container_id", ""),
            container_name=data.get("container_name", ""),
            project_id=data.get("project_id", ""),
            agent_id=data.get("agent_id", ""),
            work_item_id=data.get("work_item_id"),
            execution_id=data.get("execution_id"),
            uptime_seconds=data.get("uptime_seconds", 0.0),
            recovery_action=data.get("recovery_action", "reconnect_with_monitoring"),
        )


@dataclass(frozen=True)
class ContainerKilledEvent(CodetoreumEvent):
    """Emitted when a container is killed during recovery cleanup.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "container_recovery.killed"
        container_id (str): Docker container ID
        container_name (str): Container name for identification
        project_id (Optional[str]): Project ID (may be missing if labels incomplete)
        agent_id (Optional[str]): Agent ID (may be missing if labels incomplete)
        work_item_id (Optional[str]): Work item ID if available
        kill_reason (str): Reason for killing - Agent container reasons:
            container_timeout (age >2h), agent_mismatch, no_execution_found,
            execution_state_lookup_failed, execution_not_in_progress, unmanaged,
            incomplete_metadata, repair_cycle_wrong_assessment_path. Repair cycle
            container reasons: completed_during_downtime, checkpoint_stale (>60min
            stale + >2h old), no_checkpoint (>2h old).
        uptime_seconds (float): Container uptime in seconds before kill
        execution_marked_failed (bool): True if execution state was updated to failed
        timestamp (str): ISO 8601 timestamp when container was killed
    """

    container_id: str = ""
    container_name: str = ""
    project_id: Optional[str] = None
    agent_id: Optional[str] = None
    work_item_id: Optional[str] = None
    kill_reason: Literal[
        "container_timeout",
        "agent_mismatch",
        "no_execution_found",
        "execution_state_lookup_failed",
        "execution_not_in_progress",
        "unmanaged",
        "incomplete_metadata",
        "repair_cycle_wrong_assessment_path",
        "completed_during_downtime",
        "checkpoint_stale",
        "no_checkpoint"
    ] = "unmanaged"
    uptime_seconds: float = 0.0
    execution_marked_failed: bool = False

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.container_id:
            raise ValueError("container_id is required")
        if not self.container_name:
            raise ValueError("container_name is required")
        if self.uptime_seconds < 0:
            raise ValueError("uptime_seconds must be >= 0")
        valid_reasons = (
            "container_timeout",
            "agent_mismatch",
            "no_execution_found",
            "execution_state_lookup_failed",
            "execution_not_in_progress",
            "unmanaged",
            "incomplete_metadata",
            "repair_cycle_wrong_assessment_path",
            "completed_during_downtime",
            "checkpoint_stale",
            "no_checkpoint"
        )
        if self.kill_reason not in valid_reasons:
            raise ValueError(f"kill_reason must be one of: {', '.join(valid_reasons)}")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "container_id": self.container_id,
            "container_name": self.container_name,
            "project_id": self.project_id,
            "agent_id": self.agent_id,
            "work_item_id": self.work_item_id,
            "kill_reason": self.kill_reason,
            "uptime_seconds": self.uptime_seconds,
            "execution_marked_failed": self.execution_marked_failed,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ContainerKilledEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "container_recovery.killed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            container_id=data.get("container_id", ""),
            container_name=data.get("container_name", ""),
            project_id=data.get("project_id"),
            agent_id=data.get("agent_id"),
            work_item_id=data.get("work_item_id"),
            kill_reason=data.get("kill_reason", "unmanaged"),
            uptime_seconds=data.get("uptime_seconds", 0.0),
            execution_marked_failed=data.get("execution_marked_failed", False),
        )


@dataclass(frozen=True)
class ContainerRecoveryCompletedEvent(CodetoreumEvent):
    """Emitted when the full container recovery cycle completes.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "container_recovery.completed"
        containers_recovered (int): Number of containers successfully recovered
        containers_killed (int): Number of containers killed during cleanup
        errors_encountered (int): Number of errors during recovery process
        repair_cycles_processed (int): Number of repair cycles completed
        started_at (str): ISO 8601 timestamp when recovery started
        completed_at (str): ISO 8601 timestamp when recovery completed
        duration_seconds (float): Total recovery duration in seconds
        timestamp (str): ISO 8601 timestamp when event created
    """

    containers_recovered: int = 0
    containers_killed: int = 0
    errors_encountered: int = 0
    repair_cycles_processed: int = 0
    started_at: str = ""
    completed_at: str = ""
    duration_seconds: float = 0.0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if self.containers_recovered < 0:
            raise ValueError("containers_recovered must be >= 0")
        if self.containers_killed < 0:
            raise ValueError("containers_killed must be >= 0")
        if self.errors_encountered < 0:
            raise ValueError("errors_encountered must be >= 0")
        if self.repair_cycles_processed < 0:
            raise ValueError("repair_cycles_processed must be >= 0")
        if not self.started_at:
            raise ValueError("started_at is required")
        if not self.completed_at:
            raise ValueError("completed_at is required")
        if self.duration_seconds < 0:
            raise ValueError("duration_seconds must be >= 0")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "containers_recovered": self.containers_recovered,
            "containers_killed": self.containers_killed,
            "errors_encountered": self.errors_encountered,
            "repair_cycles_processed": self.repair_cycles_processed,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ContainerRecoveryCompletedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "container_recovery.completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            containers_recovered=data.get("containers_recovered", 0),
            containers_killed=data.get("containers_killed", 0),
            errors_encountered=data.get("errors_encountered", 0),
            repair_cycles_processed=data.get("repair_cycles_processed", 0),
            started_at=data.get("started_at", ""),
            completed_at=data.get("completed_at", ""),
            duration_seconds=data.get("duration_seconds", 0.0),
        )
