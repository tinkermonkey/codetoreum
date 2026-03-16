"""Repository-related events for git operations.

Events track changes to repository state including commits, branches,
and staged files.
"""

from dataclasses import dataclass
from uuid import uuid4

from .adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class FilesStagedEvent(CodetoreumEvent):
    """Emitted when files are staged in the repository.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Attributes:
        type (str): Fixed to "repository.files_staged"
        repository_id (str): ID of the repository
        file_paths (Tuple[str, ...]): Immutable tuple of staged file paths
        project_id (str): ID of the project containing the repository

    Example:
        >>> event = FilesStagedEvent(
        ...     type="repository.files_staged",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="mock",
        ...     repository_id="repo-1",
        ...     file_paths=("src/main.py", "tests/test_main.py"),
        ...     project_id="proj-1"
        ... )
        >>> event.file_paths = ()  # ❌ Raises FrozenInstanceError
    """

    repository_id: str = ""
    file_paths: tuple[str, ...] = ()
    project_id: str | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization and convert lists to tuples."""
        super().__post_init__()
        if not self.repository_id:
            msg = "repository_id is required"
            raise ValueError(msg)
        if not self.file_paths:
            msg = "file_paths cannot be empty"
            raise ValueError(msg)
        # Convert lists to tuples for immutability
        if isinstance(self.file_paths, list):
            object.__setattr__(self, "file_paths", tuple(self.file_paths))

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "repository_id": self.repository_id,
                "file_paths": list(self.file_paths),
                "project_id": self.project_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "FilesStagedEvent":
        """Deserialize from dictionary."""
        file_paths = data.get("file_paths", [])
        return cls(
            type=data.get("type", "repository.files_staged"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            repository_id=data.get("repository_id", ""),
            file_paths=tuple(file_paths) if file_paths else (),
            project_id=data.get("project_id"),
        )


@dataclass(frozen=True)
class CommitCreatedEvent(CodetoreumEvent):
    """Emitted when a commit is created in the repository.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Attributes:
        type (str): Fixed to "repository.commit_created"
        repository_id (str): ID of the repository
        commit_sha (str): SHA hash of the created commit
        message (str): Commit message
        author (str): Author of the commit
        changed_files (Tuple[str, ...]): Immutable tuple of changed file paths
        project_id (str): ID of the project containing the repository

    Example:
        >>> event = CommitCreatedEvent(
        ...     type="repository.commit_created",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="mock",
        ...     repository_id="repo-1",
        ...     commit_sha="abc1234",
        ...     message="Fix bug in main",
        ...     author="orchestrator",
        ...     changed_files=("src/main.py",),
        ...     project_id="proj-1"
        ... )
        >>> event.commit_sha = "def5678"  # ❌ Raises FrozenInstanceError
    """

    repository_id: str = ""
    commit_sha: str = ""
    message: str = ""
    author: str = ""
    changed_files: tuple[str, ...] = ()
    project_id: str | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization and convert lists to tuples."""
        super().__post_init__()
        if not self.repository_id:
            msg = "repository_id is required"
            raise ValueError(msg)
        if not self.commit_sha:
            msg = "commit_sha is required"
            raise ValueError(msg)
        if not self.message:
            msg = "message is required"
            raise ValueError(msg)
        if not self.author:
            msg = "author is required"
            raise ValueError(msg)
        # Convert lists to tuples for immutability
        if isinstance(self.changed_files, list):
            object.__setattr__(self, "changed_files", tuple(self.changed_files))

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "repository_id": self.repository_id,
                "commit_sha": self.commit_sha,
                "message": self.message,
                "author": self.author,
                "changed_files": list(self.changed_files),
                "project_id": self.project_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "CommitCreatedEvent":
        """Deserialize from dictionary."""
        changed_files = data.get("changed_files", [])
        return cls(
            type=data.get("type", "repository.commit_created"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            repository_id=data.get("repository_id", ""),
            commit_sha=data.get("commit_sha", ""),
            message=data.get("message", ""),
            author=data.get("author", ""),
            changed_files=tuple(changed_files) if changed_files else (),
            project_id=data.get("project_id"),
        )


@dataclass(frozen=True)
class BranchCreatedEvent(CodetoreumEvent):
    """Emitted when a branch is created in the repository.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Attributes:
        type (str): Fixed to "repository.branch_created"
        repository_id (str): ID of the repository
        branch_name (str): Name of the created branch
        base_commit (str): SHA of the commit the branch was created from
        project_id (str): ID of the project containing the repository

    Example:
        >>> event = BranchCreatedEvent(
        ...     type="repository.branch_created",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="mock",
        ...     repository_id="repo-1",
        ...     branch_name="fix/issue-123",
        ...     base_commit="abc1234",
        ...     project_id="proj-1"
        ... )
        >>> event.branch_name = "fix/issue-456"  # ❌ Raises FrozenInstanceError
    """

    repository_id: str = ""
    branch_name: str = ""
    base_commit: str = ""
    project_id: str | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.repository_id:
            msg = "repository_id is required"
            raise ValueError(msg)
        if not self.branch_name:
            msg = "branch_name is required"
            raise ValueError(msg)
        if not self.base_commit:
            msg = "base_commit is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "repository_id": self.repository_id,
                "branch_name": self.branch_name,
                "base_commit": self.base_commit,
                "project_id": self.project_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "BranchCreatedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "repository.branch_created"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            repository_id=data.get("repository_id", ""),
            branch_name=data.get("branch_name", ""),
            base_commit=data.get("base_commit", ""),
            project_id=data.get("project_id"),
        )


@dataclass(frozen=True)
class BranchPushedEvent(CodetoreumEvent):
    """Emitted when a branch is pushed to remote.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Attributes:
        type (str): Fixed to "repository.branch_pushed"
        repository_id (str): ID of the repository
        branch_name (str): Name of the pushed branch
        project_id (str): ID of the project containing the repository

    Example:
        >>> event = BranchPushedEvent(
        ...     type="repository.branch_pushed",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="mock",
        ...     repository_id="repo-1",
        ...     branch_name="fix/issue-123",
        ...     project_id="proj-1"
        ... )
        >>> event.branch_name = "fix/issue-456"  # ❌ Raises FrozenInstanceError
    """

    repository_id: str = ""
    branch_name: str = ""
    project_id: str | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.repository_id:
            msg = "repository_id is required"
            raise ValueError(msg)
        if not self.branch_name:
            msg = "branch_name is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "repository_id": self.repository_id,
                "branch_name": self.branch_name,
                "project_id": self.project_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "BranchPushedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "repository.branch_pushed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            repository_id=data.get("repository_id", ""),
            branch_name=data.get("branch_name", ""),
            project_id=data.get("project_id"),
        )
