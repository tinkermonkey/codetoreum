"""Value objects for the domain layer."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Generic, Literal, Self, TypeVar, get_args
from uuid import uuid4

if TYPE_CHECKING:
    from codetoreum.domain.agent import AgentCapability

from codetoreum.domain.exceptions import DomainError


class CommitPolicy(Enum):
    """Declares what an agent does with file changes it produces.

    NONE       – analysis/comment-only agents (code_reviewer, systemic_analysis).
                 ExecutionService skips the commit step entirely.
    ON_SUCCESS – code-producing agents (senior_software_engineer, qa_engineer, devops).
                 Commit + push only when the container exits 0.
    ALWAYS     – partial-progress agents that should checkpoint even on failure
                 (e.g. a repair-cycle code_fix that commits partial work before retrying).
    """

    NONE = "none"
    ON_SUCCESS = "on_success"
    ALWAYS = "always"


# ============================================================================
# Branch Resolution Strategy Constants
# ============================================================================

# Derive valid strategies from the Literal type annotation in BranchResolution
# This ensures the constants stay synchronized with the type definition
_RESOLUTION_STRATEGY_LITERAL = Literal["exact_match", "parent_issue", "sibling", "fuzzy", "new"]
VALID_RESOLUTION_STRATEGIES = set(get_args(_RESOLUTION_STRATEGY_LITERAL))
VALID_REUSE_STRATEGIES = VALID_RESOLUTION_STRATEGIES - {"new"}

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
        github_project_id: GitHub Projects v2 node ID for board reconciliation.
                          Required for board reconciliation with GitHub Projects v2.
                          If not provided, board reconciliation is skipped.
                          Example: "PVT_kwDOANYYRs4AbZKf"

    Example:
        >>> config = ProjectConfig(
        ...     repo_url="https://github.com/acme/api-service.git",
        ...     branch="main",
        ...     enabled=True,
        ...     org="acme-org",
        ...     github_project_id="PVT_kwDOANYYRs4AbZKf"
        ... )
    """

    repo_url: str
    branch: str
    enabled: bool
    org: str
    github_project_id: str | None = None

    def __post_init__(self) -> None:
        """Validate project configuration."""
        if not self.repo_url or not self.repo_url.strip():
            msg = "ProjectConfig.repo_url cannot be empty"
            raise DomainError(msg)
        if not self.branch or not self.branch.strip():
            msg = "ProjectConfig.branch cannot be empty"
            raise DomainError(msg)
        if not self.org or not self.org.strip():
            msg = "ProjectConfig.org cannot be empty"
            raise DomainError(msg)


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
            msg = f"{self._type_name} cannot be empty"
            raise DomainError(msg)

    @classmethod
    def generate(cls) -> Self:
        """Generate new unique identifier."""
        return cls(value=str(uuid4()))

    @classmethod
    def from_string(cls, value: str) -> Self:
        """Create from string value."""
        return cls(value=value)

    def __str__(self) -> str:
        """Return string representation."""
        return self.value


@dataclass(frozen=True)
class WorkItemId(TypeSafeId["WorkItemId"]):
    """Type-safe identifier for work items."""


@dataclass(frozen=True)
class WorkflowId(TypeSafeId["WorkflowId"]):
    """Type-safe identifier for workflows."""


@dataclass(frozen=True)
class AgentId(TypeSafeId["AgentId"]):
    """Type-safe identifier for agents."""


@dataclass(frozen=True)
class ExecutionId(TypeSafeId["ExecutionId"]):
    """Type-safe identifier for agent executions."""


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
            msg = "Min proficiency must be between 0.0 and 1.0"
            raise DomainError(msg)

    def is_satisfied_by(self, capability: "AgentCapability") -> bool:
        """
        Check if capability satisfies this requirement.

        Args:
            capability: Agent capability to check

        Returns:
            True if capability meets requirement
        """

        return capability.skill == self.skill and capability.proficiency >= self.min_proficiency


# ============================================================================
# Execution Result Value Object
# ============================================================================


@dataclass(frozen=True)
class ExecutionResult:
    """
    Execution Result value object.

    **IMMUTABILITY**: Frozen dataclass with immutable collection types (tuples instead of lists).
    All collections are immutable: file lists use tuples and metadata dict is wrapped in
    MappingProxyType to prevent in-place mutations. This prevents breaking the immutability
    contract while still allowing field reassignment to be blocked by dataclass frozen=True.

    Immutable representation of agent execution outcome.
    """

    # Status
    success: bool
    exit_code: int

    # Output
    output: str
    error_message: str | None

    # Metrics (required fields before optional)
    input_tokens: int
    output_tokens: int
    duration_seconds: float

    # Timestamp
    timestamp: datetime

    # Files modified (for code changes) - immutable tuples instead of mutable lists
    modified_files: tuple[str, ...] = ()
    added_files: tuple[str, ...] = ()
    deleted_files: tuple[str, ...] = ()

    # Session continuity
    session_id: str | None = None

    # Metadata - wrapped in MappingProxyType for deep immutability
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate execution result and wrap mutable collections."""
        if self.input_tokens < 0:
            msg = "Input tokens cannot be negative"
            raise DomainError(msg)
        if self.output_tokens < 0:
            msg = "Output tokens cannot be negative"
            raise DomainError(msg)
        if self.duration_seconds < 0:
            msg = "Duration cannot be negative"
            raise DomainError(msg)
        # Wrap metadata dict in MappingProxyType for immutability
        object.__setattr__(self, "metadata", MappingProxyType(self.metadata))

    @classmethod
    def success_result(
        cls,
        output: str,
        input_tokens: int,
        output_tokens: int,
        duration_seconds: float,
        modified_files: list[str] | None = None,
        added_files: list[str] | None = None,
        deleted_files: list[str] | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ExecutionResult":
        """Create successful execution result."""
        return cls(
            success=True,
            exit_code=0,
            output=output,
            error_message=None,
            modified_files=tuple(modified_files or []),
            added_files=tuple(added_files or []),
            deleted_files=tuple(deleted_files or []),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_seconds=duration_seconds,
            session_id=session_id,
            metadata=metadata or {},
            timestamp=datetime.now(UTC),
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
        metadata: dict[str, Any] | None = None,
    ) -> "ExecutionResult":
        """Create failed execution result."""
        return cls(
            success=False,
            exit_code=exit_code,
            output=output,
            error_message=error_message,
            modified_files=(),
            added_files=(),
            deleted_files=(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_seconds=duration_seconds,
            session_id=None,
            metadata=metadata or {},
            timestamp=datetime.now(UTC),
        )

    def get_total_tokens(self) -> int:
        """Get total tokens used."""
        return self.input_tokens + self.output_tokens

    def has_file_changes(self) -> bool:
        """Check if execution made file changes."""
        return bool(self.modified_files or self.added_files or self.deleted_files)

    def get_all_affected_files(self) -> list[str]:
        """Get all files affected by execution."""
        return list(set(self.modified_files + self.added_files + self.deleted_files))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "exit_code": self.exit_code,
            "output": self.output,
            "error_message": self.error_message,
            "modified_files": list(self.modified_files),
            "added_files": list(self.added_files),
            "deleted_files": list(self.deleted_files),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.get_total_tokens(),
            "duration_seconds": self.duration_seconds,
            "session_id": self.session_id,
            "metadata": dict(self.metadata),
            "timestamp": self.timestamp.isoformat(),
        }


# ============================================================================
# Container Configuration Value Object
# ============================================================================


@dataclass(frozen=True)
class ContainerConfig:
    """Configuration for container creation.

    **IMMUTABILITY**: Frozen dataclass with immutable collection types (tuples instead of lists).
    All collections are immutable: command and entrypoint use tuples, and environment and
    volumes dicts are wrapped in MappingProxyType to prevent in-place mutations.
    """

    image: str  # Image name:tag
    name: str | None = None  # Container name
    command: tuple[str, ...] | None = None  # Command to run - immutable tuple
    entrypoint: tuple[str, ...] | None = None  # Immutable tuple
    working_dir: str = "/workspace"
    user: str = "1000:1000"  # UID:GID
    environment: Mapping[str, str] | None = None  # Wrapped in MappingProxyType in __post_init__
    volumes: Mapping[str, Mapping[str, str]] | None = None  # {host: {bind: path, mode}} - wrapped in __post_init__
    network: str | None = None
    auto_remove: bool = False  # --rm flag
    detached: bool = False  # -d flag
    stdin_open: bool = False  # -i flag
    tty: bool = False  # -t flag

    def __post_init__(self) -> None:
        """Validate container configuration and wrap mutable collections."""
        if not self.image:
            msg = "Container image cannot be empty"
            raise DomainError(msg)
        # Convert lists to tuples for immutability
        if self.command is not None and isinstance(self.command, list):
            object.__setattr__(self, "command", tuple(self.command))
        if self.entrypoint is not None and isinstance(self.entrypoint, list):
            object.__setattr__(self, "entrypoint", tuple(self.entrypoint))
        # Wrap environment dict in MappingProxyType for immutability
        if self.environment is not None:
            object.__setattr__(self, "environment", MappingProxyType(self.environment))
        # Wrap volumes dict and nested dicts in MappingProxyType for deep immutability
        if self.volumes:
            for host_path, config in self.volumes.items():
                if "bind" not in config:
                    msg = f"Volume config for {host_path} must have 'bind'"
                    raise DomainError(msg)
                mode = config.get("mode", "rw")
                if mode not in ["rw", "ro"]:
                    msg = f"Volume mode must be 'rw' or 'ro', got {mode}"
                    raise DomainError(msg)
            # Wrap nested volume configs in MappingProxyType, then wrap the outer dict
            wrapped_volumes = {host: MappingProxyType(config) for host, config in self.volumes.items()}
            object.__setattr__(self, "volumes", MappingProxyType(wrapped_volumes))

    def get_command_as_list(self) -> list[str] | None:
        """Get command as mutable list for adapter compatibility.

        Converts immutable tuple to mutable list for passing to port interfaces
        that expect mutable types, while maintaining domain layer immutability.

        Returns:
            list[str] | None: Command as list, or None if not set
        """
        return list(self.command) if self.command else None

    def get_environment_as_dict(self) -> dict[str, str] | None:
        """Get environment as mutable dict for adapter compatibility.

        Converts immutable Mapping to mutable dict for passing to port interfaces
        that expect mutable types, while maintaining domain layer immutability.

        Returns:
            dict[str, str] | None: Environment as dict, or None if not set
        """
        return dict(self.environment) if self.environment else None

    def get_volumes_as_dict(self) -> dict[str, str] | None:
        """Get volumes as mutable dict for adapter compatibility.

        Converts immutable nested Mapping to mutable dict in adapter format for passing to port
        interfaces that expect mutable types, while maintaining domain layer immutability.

        Format: {host_path: "container_path:mode"} (e.g., {"/host/path": "/container/path:ro"})

        Returns:
            dict[str, str] | None: Volumes as dict in adapter format, or None if not set
        """
        if not self.volumes:
            return None
        result = {}
        for host, config in self.volumes.items():
            container_path = config["bind"]
            mode = config.get("mode", "rw")
            result[host] = f"{container_path}:{mode}"
        return result

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        # Convert tuples to lists for serialization
        command = list(self.command) if self.command else None
        entrypoint = list(self.entrypoint) if self.entrypoint else None
        # Convert MappingProxyType dicts to regular dicts for serialization
        environment = dict(self.environment) if self.environment else {}
        volumes = {}
        if self.volumes:
            for host, config in self.volumes.items():
                volumes[host] = dict(config)
        return {
            "image": self.image,
            "name": self.name,
            "command": command,
            "entrypoint": entrypoint,
            "working_dir": self.working_dir,
            "user": self.user,
            "environment": environment,
            "volumes": volumes,
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
    """Complete context for agent execution.

    **IMMUTABILITY**: Frozen dataclass with immutable collection types (tuples instead of lists).
    All collections are immutable: tech_stack and mcp_servers use tuples, and metadata dict is
    wrapped in MappingProxyType to prevent in-place mutations.
    """

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
    branch_name: str | None
    discussion_id: str | None

    # Project context
    project_id: str
    repository_url: str
    tech_stack: tuple[str, ...] = ()

    # Permissions
    filesystem_write_allowed: bool = False
    can_make_commits: bool = False
    requires_docker: bool = False

    # MCP servers - immutable tuple instead of mutable list
    mcp_servers: tuple[str, ...] = ()

    # Commit behaviour — derived from Agent.commit_policy at context build time
    commit_policy: CommitPolicy = CommitPolicy.ON_SUCCESS

    # Local repository checkout path — set by workspace preparation; used by
    # ExecutionService to run vcs.status/commit/push after the container exits
    repository_path: str | None = None

    # Session continuity
    previous_session_id: str | None = None

    # Environment variables (from project config)
    environment_variables: Mapping[str, str] | None = None

    # Workflow integrations (mirrored from ProjectContext.auto_create_pull_requests)
    auto_create_pull_requests: bool = True

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate execution context and wrap mutable collections."""
        if self.timeout_seconds <= 0:
            msg = "Timeout must be positive"
            raise DomainError(msg)
        if not self.work_item_id:
            msg = "Work item ID cannot be empty"
            raise DomainError(msg)
        if not self.workflow_id:
            msg = "Workflow ID cannot be empty"
            raise DomainError(msg)
        if not self.agent_id:
            msg = "Agent ID cannot be empty"
            raise DomainError(msg)
        # Wrap environment_variables dict in MappingProxyType for immutability
        if self.environment_variables is not None:
            object.__setattr__(self, "environment_variables", MappingProxyType(self.environment_variables))
        # Wrap metadata dict in MappingProxyType for immutability
        object.__setattr__(self, "metadata", MappingProxyType(self.metadata))

    def to_dict(self) -> dict[str, Any]:
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
            "tech_stack": list(self.tech_stack),
            "filesystem_write_allowed": self.filesystem_write_allowed,
            "can_make_commits": self.can_make_commits,
            "requires_docker": self.requires_docker,
            "mcp_servers": list(self.mcp_servers),
            "previous_session_id": self.previous_session_id,
            "environment_variables": dict(self.environment_variables) if self.environment_variables else None,
            "metadata": dict(self.metadata),
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
            msg = "End time must be after start time"
            raise DomainError(msg)

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
            msg = "Token counts cannot be negative"
            raise DomainError(msg)

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

    def to_dict(self) -> dict[str, int]:
        """Serialize to dictionary."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


# ============================================================================
# Branch Resolution Value Object
# ============================================================================


@dataclass(frozen=True)
class BranchResolution:
    """Immutable value object representing a branch resolution decision.

    **IMMUTABILITY**: Frozen dataclass ensuring the resolution decision cannot
    be modified after creation. This is a value object—it represents a decision
    result with no lifecycle, immutable from the moment it is created.

    Represents a decision about which branch to use for a work item, including
    the action (create or reuse), the branch name, confidence level, and reasoning.

    Attributes:
        action: Literal["create", "reuse"]. Whether to create a new branch or
               reuse an existing one.
        branch_name: The name of the branch to use/create.
        confidence: Float from 0.0 to 1.0 indicating confidence in the decision.
                   1.0 = certain, 0.5 = uncertain, 0.0 = no confidence.
        reason: Human-readable explanation of the resolution decision.
        parent_issue_id: Optional ID of the parent issue if resolved via
                        parent issue relationship. None if not applicable.
        resolution_strategy: The strategy used to reach this decision.
                           Must be one of: "exact_match", "parent_issue",
                           "sibling", "fuzzy", "new".

    Example:
        >>> resolution = BranchResolution(
        ...     action="reuse",
        ...     branch_name="feature/issue-123-fix-auth",
        ...     confidence=0.95,
        ...     reason="Exact match found for issue #123",
        ...     parent_issue_id=None,
        ...     resolution_strategy="exact_match"
        ... )
        >>> resolution.action = "create"  # ❌ Raises FrozenInstanceError
    """

    action: Literal["create", "reuse"]
    branch_name: str
    confidence: float
    reason: str
    resolution_strategy: _RESOLUTION_STRATEGY_LITERAL
    parent_issue_id: str | None = None

    def __post_init__(self) -> None:
        """Validate branch resolution."""
        if not self.branch_name or not self.branch_name.strip():
            msg = "BranchResolution.branch_name cannot be empty"
            raise DomainError(msg)
        if not 0.0 <= self.confidence <= 1.0:
            msg = "BranchResolution.confidence must be between 0.0 and 1.0"
            raise DomainError(msg)
        if not self.reason or not self.reason.strip():
            msg = "BranchResolution.reason cannot be empty"
            raise DomainError(msg)
        if self.resolution_strategy not in VALID_RESOLUTION_STRATEGIES:
            msg = f"BranchResolution.resolution_strategy must be one of {VALID_RESOLUTION_STRATEGIES}, got {self.resolution_strategy}"
            raise DomainError(msg)
        # Cross-field validation: action and resolution_strategy must be compatible
        if self.action == "create" and self.resolution_strategy != "new":
            msg = f"BranchResolution: action='create' requires resolution_strategy='new', got '{self.resolution_strategy}'"
            raise DomainError(msg)
        if self.action == "reuse" and self.resolution_strategy == "new":
            msg = "BranchResolution: action='reuse' cannot use resolution_strategy='new'"
            raise DomainError(msg)
        # Cross-field validation: parent_issue strategy requires parent_issue_id
        if self.resolution_strategy == "parent_issue" and self.parent_issue_id is None:
            msg = "BranchResolution: resolution_strategy='parent_issue' requires parent_issue_id to be set"
            raise DomainError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "action": self.action,
            "branch_name": self.branch_name,
            "confidence": self.confidence,
            "reason": self.reason,
            "parent_issue_id": self.parent_issue_id,
            "resolution_strategy": self.resolution_strategy,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BranchResolution":
        """Create from dictionary for deserialization.

        Args:
            data: Dictionary with resolution fields.

        Returns:
            BranchResolution instance.

        Raises:
            ValueError: If required fields are missing or invalid.
        """
        try:
            return cls(
                action=data["action"],
                branch_name=data["branch_name"],
                confidence=data["confidence"],
                reason=data["reason"],
                resolution_strategy=data["resolution_strategy"],
                parent_issue_id=data.get("parent_issue_id"),
            )
        except KeyError as e:
            msg = f"Missing required field: {e}"
            raise ValueError(msg) from e
