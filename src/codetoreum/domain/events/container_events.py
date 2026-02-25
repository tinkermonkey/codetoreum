"""Container execution domain events for artifact and output tracking.

Events track the lifecycle of container command execution, including completion
of commands and file outputs that trigger downstream event subscriptions
(e.g., storage persistence).

All events are immutable (frozen dataclasses) to maintain event sourcing
audit trail integrity and enable observability integration.
"""

from dataclasses import dataclass
from uuid import uuid4

from .adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class ContainerExecutionCompletedEvent(CodetoreumEvent):
    """Emitted when container command execution completes.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    This event is emitted by FakeContainerAdapter (testing) and production
    container adapters to signal that a command has completed, including
    tracking files written to the output directory. This enables downstream
    handlers (e.g., InMemoryStorageAdapter) to subscribe and automatically
    persist artifacts to storage.

    Attributes:
        type (str): Fixed to "container.execution_completed"
        container_id (str): Unique container identifier
        command (str): Command that was executed
        exit_code (int): Exit code from command execution
        output_files (tuple[str, ...]): Immutable tuple of files written to /output/
        project_id (Optional[str]): Project ID if available
        timestamp (str): ISO 8601 timestamp when execution completed

    Example:
        >>> event = ContainerExecutionCompletedEvent(
        ...     type="container.execution_completed",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="fake_container",
        ...     container_id="container-123",
        ...     command="pytest tests/",
        ...     exit_code=0,
        ...     output_files=("test_results.json", "coverage.xml"),
        ...     project_id="proj-1"
        ... )
        >>> event.output_files = ("new_file.txt",)  # ❌ Raises FrozenInstanceError
    """

    container_id: str = ""
    command: str = ""
    exit_code: int = 0
    output_files: tuple[str, ...] = ()
    project_id: str | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization and convert lists to tuples."""
        super().__post_init__()
        if not self.container_id:
            msg = "container_id is required"
            raise ValueError(msg)
        if not self.command:
            msg = "command is required"
            raise ValueError(msg)
        if self.exit_code < 0:
            msg = "exit_code must be >= 0"
            raise ValueError(msg)
        # Convert lists to tuples for immutability
        if isinstance(self.output_files, list):
            object.__setattr__(self, "output_files", tuple(self.output_files))

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "container_id": self.container_id,
                "command": self.command,
                "exit_code": self.exit_code,
                "output_files": list(self.output_files),
                "project_id": self.project_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ContainerExecutionCompletedEvent":
        """Deserialize from dictionary."""
        output_files = data.get("output_files", [])
        return cls(
            type=data.get("type", "container.execution_completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            container_id=data.get("container_id", ""),
            command=data.get("command", ""),
            exit_code=data.get("exit_code", 0),
            output_files=tuple(output_files) if output_files else (),
            project_id=data.get("project_id"),
        )
