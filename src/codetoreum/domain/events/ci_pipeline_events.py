"""CI pipeline domain events for CI status tracking and check execution.

Events track the lifecycle of CI operations including status queries for pull
requests and execution of local CI checks within repair cycles.

**Immutability**: All events are immutable (frozen dataclasses) to maintain
event sourcing audit trail integrity. Events represent immutable facts about
CI operations—they cannot be modified after creation.
"""

from dataclasses import dataclass
from uuid import uuid4

from .adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class CIPipelineStatusCheckedEvent(CodetoreumEvent):
    """Emitted when a PR's CI pipeline status is queried.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Tracks the querying of CI status from an external CI system for a pull request,
    including the status at the time of the query.

    Attributes:
        type (str): Fixed to "ci.pipeline_status_checked"
        pr_id (str): Pull request identifier
        project_id (str): Project containing the PR
        status (str): CI status at time of check (pending, running, passed, failed, skipped)
        check_count (int): Number of checks in the pipeline
        passed_count (int): Number of checks that passed
        failed_count (int): Number of checks that failed
        timestamp (str): ISO 8601 timestamp when status was checked
    """

    pr_id: str = ""
    project_id: str = ""
    status: str = ""
    check_count: int = 0
    passed_count: int = 0
    failed_count: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.pr_id:
            msg = "pr_id is required"
            raise ValueError(msg)
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        if not self.status:
            msg = "status is required"
            raise ValueError(msg)
        if self.check_count < 0:
            msg = "check_count must be a non-negative integer"
            raise ValueError(msg)
        if self.passed_count < 0:
            msg = "passed_count must be a non-negative integer"
            raise ValueError(msg)
        if self.failed_count < 0:
            msg = "failed_count must be a non-negative integer"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "pr_id": self.pr_id,
                "project_id": self.project_id,
                "status": self.status,
                "check_count": self.check_count,
                "passed_count": self.passed_count,
                "failed_count": self.failed_count,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "CIPipelineStatusCheckedEvent":
        """Deserialize from dictionary.

        Raises:
            KeyError: If required fields (pr_id, project_id, status) are missing.
        """
        return cls(
            type=data.get("type", "ci.pipeline_status_checked"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pr_id=data["pr_id"],
            project_id=data["project_id"],
            status=data["status"],
            check_count=data.get("check_count", 0),
            passed_count=data.get("passed_count", 0),
            failed_count=data.get("failed_count", 0),
        )


@dataclass(frozen=True)
class CIRunStartedEvent(CodetoreumEvent):
    """Emitted when local CI execution starts.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Tracks the beginning of CI check execution within a working directory,
    typically as part of a repair cycle or local validation.

    Attributes:
        type (str): Fixed to "ci.run_started"
        project_id (str): Project being checked
        workflow_run_id (str): ID of the workflow run this is part of
        working_directory (str): Directory where CI is executing
        timeout_seconds (int): Timeout for CI execution
        timestamp (str): ISO 8601 timestamp when execution started
    """

    project_id: str = ""
    workflow_run_id: str = ""
    working_directory: str = ""
    timeout_seconds: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)
        if not self.working_directory:
            msg = "working_directory is required"
            raise ValueError(msg)
        if self.timeout_seconds <= 0:
            msg = "timeout_seconds must be a positive integer"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "project_id": self.project_id,
                "workflow_run_id": self.workflow_run_id,
                "working_directory": self.working_directory,
                "timeout_seconds": self.timeout_seconds,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "CIRunStartedEvent":
        """Deserialize from dictionary.

        Raises:
            KeyError: If required fields (project_id, workflow_run_id,
                     working_directory, timeout_seconds) are missing.
        """
        return cls(
            type=data.get("type", "ci.run_started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            project_id=data["project_id"],
            workflow_run_id=data["workflow_run_id"],
            working_directory=data["working_directory"],
            timeout_seconds=data["timeout_seconds"],
        )


@dataclass(frozen=True)
class CIRunCompletedEvent(CodetoreumEvent):
    """Emitted when local CI execution completes.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Tracks the completion of CI check execution with results summary, including
    the number of passed and failed checks.

    Attributes:
        type (str): Fixed to "ci.run_completed"
        project_id (str): Project that was checked
        workflow_run_id (str): ID of the workflow run this is part of
        passed (int): Number of checks that passed
        failed (int): Number of checks that failed
        output (str): Full output/logs from CI execution
        timestamp (str): ISO 8601 timestamp when execution completed
    """

    project_id: str = ""
    workflow_run_id: str = ""
    passed: int = 0
    failed: int = 0
    output: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)
        if self.passed < 0:
            msg = "passed must be a non-negative integer"
            raise ValueError(msg)
        if self.failed < 0:
            msg = "failed must be a non-negative integer"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "project_id": self.project_id,
                "workflow_run_id": self.workflow_run_id,
                "passed": self.passed,
                "failed": self.failed,
                "output": self.output,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "CIRunCompletedEvent":
        """Deserialize from dictionary.

        Raises:
            KeyError: If required fields (project_id, workflow_run_id, passed,
                     failed) are missing.
        """
        return cls(
            type=data.get("type", "ci.run_completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            project_id=data["project_id"],
            workflow_run_id=data["workflow_run_id"],
            passed=data["passed"],
            failed=data["failed"],
            output=data.get("output", ""),
        )
