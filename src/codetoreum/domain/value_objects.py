"""Value objects for the domain layer."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, TypeVar, Generic
from uuid import uuid4

if TYPE_CHECKING:
    from codetoreum.domain.agent import AgentCapability

from codetoreum.domain.exceptions import DomainError


# ============================================================================
# Project Configuration Value Object
# ============================================================================


@dataclass(frozen=True)
class ProjectConfig:
    """Immutable project configuration from projects.yaml.

    Represents the complete configuration for a single project including
    repository details and enabled status. Frozen to ensure immutability
    in the domain layer.

    Attributes:
        repo_url: Repository URL (SSH or HTTPS format).
                 Examples: "git@github.com:org/repo.git",
                          "https://github.com/org/repo.git"
        branch: Branch name to checkout and track for this project (e.g., "main")
        enabled: Whether this project is actively processed by the orchestrator.
                Only enabled projects are included in orchestration cycles.
        org: Organization or namespace identifier for the project.
             Used for namespacing pipeline locks, queue state, and other
             per-project resources to maintain isolation.

    Example:
        >>> config = ProjectConfig(
        ...     repo_url="https://github.com/acme/api-service.git",
        ...     branch="main",
        ...     enabled=True,
        ...     org="acme-org"
        ... )
    """

    repo_url: str
    branch: str
    enabled: bool
    org: str

    def __post_init__(self) -> None:
        """Validate project configuration."""
        if not self.repo_url or not self.repo_url.strip():
            raise DomainError("ProjectConfig.repo_url cannot be empty")
        if not self.branch or not self.branch.strip():
            raise DomainError("ProjectConfig.branch cannot be empty")
        if not self.org or not self.org.strip():
            raise DomainError("ProjectConfig.org cannot be empty")


# ============================================================================
# Type-Safe Identifiers (Generic Base)
# ============================================================================

T = TypeVar("T", bound="TypeSafeId")


@dataclass(frozen=True)
class TypeSafeId(Generic[T]):
    """Generic base class for type-safe identifiers."""

    value: str
    _type_name: str = field(default="", init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Validate identifier."""
        if not self.value:
            object.__setattr__(self, "_type_name", self.__class__.__name__)
            raise DomainError(f"{self._type_name} cannot be empty")

    @classmethod
    def generate(cls: type[T]) -> T:
        """Generate new unique identifier."""
        return cls(value=str(uuid4()))

    @classmethod
    def from_string(cls: type[T], value: str) -> T:
        """Create from string value."""
        return cls(value=value)

    def __str__(self) -> str:
        """Return string representation."""
        return self.value


@dataclass(frozen=True)
class WorkItemId(TypeSafeId["WorkItemId"]):
    """Type-safe identifier for work items."""

    pass


@dataclass(frozen=True)
class WorkflowId(TypeSafeId["WorkflowId"]):
    """Type-safe identifier for workflows."""

    pass


@dataclass(frozen=True)
class AgentId(TypeSafeId["AgentId"]):
    """Type-safe identifier for agents."""

    pass


@dataclass(frozen=True)
class ExecutionId(TypeSafeId["ExecutionId"]):
    """Type-safe identifier for agent executions."""

    pass


# ============================================================================
# Capability and Requirement Value Objects
# ============================================================================


@dataclass(frozen=True)
class Requirement:
    """Represents a skill requirement for work."""

    skill: str
    min_proficiency: float
    is_required: bool = True

    def __post_init__(self) -> None:
        """Validate proficiency range."""
        if not 0.0 <= self.min_proficiency <= 1.0:
            raise DomainError("Min proficiency must be between 0.0 and 1.0")

    def is_satisfied_by(self, capability: "AgentCapability") -> bool:
        """
        Check if capability satisfies this requirement.

        Args:
            capability: Agent capability to check

        Returns:
            True if capability meets requirement
        """
        from codetoreum.domain.agent import AgentCapability

        return (
            capability.skill == self.skill
            and capability.proficiency >= self.min_proficiency
        )


# ============================================================================
# Execution Result Value Object
# ============================================================================


@dataclass(frozen=True)
class ExecutionResult:
    """
    Execution Result value object.

    Immutable representation of agent execution outcome.
    """

    # Status
    success: bool
    exit_code: int

    # Output
    output: str
    error_message: Optional[str]

    # Files modified (for code changes)
    modified_files: List[str]
    added_files: List[str]
    deleted_files: List[str]

    # Metrics
    input_tokens: int
    output_tokens: int
    duration_seconds: float

    # Session continuity
    session_id: Optional[str]

    # Metadata
    metadata: Dict[str, Any]

    # Timestamp
    timestamp: datetime

    def __post_init__(self) -> None:
        """Validate execution result."""
        if self.input_tokens < 0:
            raise DomainError("Input tokens cannot be negative")
        if self.output_tokens < 0:
            raise DomainError("Output tokens cannot be negative")
        if self.duration_seconds < 0:
            raise DomainError("Duration cannot be negative")

    @classmethod
    def success_result(
        cls,
        output: str,
        input_tokens: int,
        output_tokens: int,
        duration_seconds: float,
        modified_files: Optional[List[str]] = None,
        added_files: Optional[List[str]] = None,
        deleted_files: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ExecutionResult":
        """Create successful execution result."""
        return cls(
            success=True,
            exit_code=0,
            output=output,
            error_message=None,
            modified_files=modified_files or [],
            added_files=added_files or [],
            deleted_files=deleted_files or [],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_seconds=duration_seconds,
            session_id=session_id,
            metadata=metadata or {},
            timestamp=datetime.now(timezone.utc),
        )

    @classmethod
    def failure_result(
        cls,
        error_message: str,
        exit_code: int,
        output: str = "",
        duration_seconds: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ExecutionResult":
        """Create failed execution result."""
        return cls(
            success=False,
            exit_code=exit_code,
            output=output,
            error_message=error_message,
            modified_files=[],
            added_files=[],
            deleted_files=[],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_seconds=duration_seconds,
            session_id=None,
            metadata=metadata or {},
            timestamp=datetime.now(timezone.utc),
        )

    def get_total_tokens(self) -> int:
        """Get total tokens used."""
        return self.input_tokens + self.output_tokens

    def has_file_changes(self) -> bool:
        """Check if execution made file changes."""
        return bool(self.modified_files or self.added_files or self.deleted_files)

    def get_all_affected_files(self) -> List[str]:
        """Get all files affected by execution."""
        return list(
            set(self.modified_files + self.added_files + self.deleted_files)
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "exit_code": self.exit_code,
            "output": self.output,
            "error_message": self.error_message,
            "modified_files": self.modified_files,
            "added_files": self.added_files,
            "deleted_files": self.deleted_files,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.get_total_tokens(),
            "duration_seconds": self.duration_seconds,
            "session_id": self.session_id,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


# ============================================================================
# Container Configuration Value Object
# ============================================================================


@dataclass(frozen=True)
class ContainerConfig:
    """Configuration for container creation."""

    image: str  # Image name:tag
    name: Optional[str] = None  # Container name
    command: Optional[List[str]] = None  # Command to run
    entrypoint: Optional[List[str]] = None
    working_dir: str = "/workspace"
    user: str = "1000:1000"  # UID:GID
    environment: Optional[Dict[str, str]] = None
    volumes: Optional[Dict[str, Dict[str, str]]] = None  # {host: {bind: path, mode}}
    network: Optional[str] = None
    auto_remove: bool = False  # --rm flag
    detached: bool = False  # -d flag
    stdin_open: bool = False  # -i flag
    tty: bool = False  # -t flag

    def __post_init__(self) -> None:
        """Validate container configuration."""
        if not self.image:
            raise DomainError("Container image cannot be empty")
        if self.volumes:
            for host_path, config in self.volumes.items():
                if "bind" not in config:
                    raise DomainError(f"Volume config for {host_path} must have 'bind'")
                mode = config.get("mode", "rw")
                if mode not in ["rw", "ro"]:
                    raise DomainError(f"Volume mode must be 'rw' or 'ro', got {mode}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "image": self.image,
            "name": self.name,
            "command": self.command,
            "entrypoint": self.entrypoint,
            "working_dir": self.working_dir,
            "user": self.user,
            "environment": self.environment or {},
            "volumes": self.volumes or {},
            "network": self.network,
            "auto_remove": self.auto_remove,
            "detached": self.detached,
            "stdin_open": self.stdin_open,
            "tty": self.tty,
        }


# ============================================================================
# Execution Context Value Object
# ============================================================================


@dataclass(frozen=True)
class ExecutionContext:
    """Complete context for agent execution."""

    # Work context
    work_item_id: str
    workflow_id: str
    stage_name: str

    # Agent context
    agent_id: str
    model: str
    timeout_seconds: int

    # Workspace context
    workspace_type: str
    branch_name: Optional[str]
    discussion_id: Optional[str]

    # Project context
    project_id: str
    repository_url: str
    tech_stack: List[str]

    # Permissions
    filesystem_write_allowed: bool
    can_make_commits: bool
    requires_docker: bool

    # MCP servers
    mcp_servers: List[str]

    # Session continuity
    previous_session_id: Optional[str]

    # Metadata
    metadata: Dict[str, Any]

    def __post_init__(self) -> None:
        """Validate execution context."""
        if self.timeout_seconds <= 0:
            raise DomainError("Timeout must be positive")
        if not self.work_item_id:
            raise DomainError("Work item ID cannot be empty")
        if not self.workflow_id:
            raise DomainError("Workflow ID cannot be empty")
        if not self.agent_id:
            raise DomainError("Agent ID cannot be empty")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "work_item_id": self.work_item_id,
            "workflow_id": self.workflow_id,
            "stage_name": self.stage_name,
            "agent_id": self.agent_id,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "workspace_type": self.workspace_type,
            "branch_name": self.branch_name,
            "discussion_id": self.discussion_id,
            "project_id": self.project_id,
            "repository_url": self.repository_url,
            "tech_stack": self.tech_stack,
            "filesystem_write_allowed": self.filesystem_write_allowed,
            "can_make_commits": self.can_make_commits,
            "requires_docker": self.requires_docker,
            "mcp_servers": self.mcp_servers,
            "previous_session_id": self.previous_session_id,
            "metadata": self.metadata,
        }


# ============================================================================
# Time Range Value Object
# ============================================================================


@dataclass(frozen=True)
class TimeRange:
    """Value object for time ranges."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        """Validate time range."""
        if self.end < self.start:
            raise DomainError("End time must be after start time")

    def duration_seconds(self) -> float:
        """Get duration in seconds."""
        return (self.end - self.start).total_seconds()

    def contains(self, timestamp: datetime) -> bool:
        """Check if timestamp is within range."""
        return self.start <= timestamp <= self.end

    def overlaps(self, other: "TimeRange") -> bool:
        """Check if ranges overlap."""
        return self.start <= other.end and other.start <= self.end


# ============================================================================
# Token Usage Value Object
# ============================================================================


@dataclass(frozen=True)
class TokenUsage:
    """Token usage metrics."""

    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        """Validate token counts."""
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise DomainError("Token counts cannot be negative")

    @property
    def total_tokens(self) -> int:
        """Get total tokens."""
        return self.input_tokens + self.output_tokens

    def add(self, other: "TokenUsage") -> "TokenUsage":
        """Add two token usages."""
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )

    def to_dict(self) -> Dict[str, int]:
        """Serialize to dictionary."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }
