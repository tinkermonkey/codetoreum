"""IRepository output port interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from codetoreum.domain.types import BranchName, CommitHash, RepositoryId

# ============================================================================
# Data Models
# ============================================================================


@dataclass(frozen=True)
class RepositoryStatus:
    """Repository status information.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation. File lists are converted
    to tuples for true immutability - the dataclass is only shallowly frozen when
    fields contain mutable types, so we enforce deep immutability via conversion.
    """

    current_branch: BranchName
    is_dirty: bool
    staged_files: tuple[str, ...]
    unstaged_files: tuple[str, ...]
    untracked_files: tuple[str, ...]
    ahead_count: int
    behind_count: int

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not isinstance(self.current_branch, str) or not self.current_branch:
            msg = "current_branch must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.is_dirty, bool):
            msg = "is_dirty must be a boolean"
            raise ValueError(msg)

        if not isinstance(self.staged_files, tuple):
            msg = "staged_files must be a tuple of strings"
            raise ValueError(msg)

        if not all(isinstance(f, str) for f in self.staged_files):
            msg = "all staged_files must be strings"
            raise ValueError(msg)

        if not isinstance(self.unstaged_files, tuple):
            msg = "unstaged_files must be a tuple of strings"
            raise ValueError(msg)

        if not all(isinstance(f, str) for f in self.unstaged_files):
            msg = "all unstaged_files must be strings"
            raise ValueError(msg)

        if not isinstance(self.untracked_files, tuple):
            msg = "untracked_files must be a tuple of strings"
            raise ValueError(msg)

        if not all(isinstance(f, str) for f in self.untracked_files):
            msg = "all untracked_files must be strings"
            raise ValueError(msg)

        # Explicitly reject bool (subclass of int)
        if isinstance(self.ahead_count, bool):
            msg = "ahead_count must be a non-negative integer, got bool"
            raise ValueError(msg)

        if not isinstance(self.ahead_count, int) or self.ahead_count < 0:
            msg = "ahead_count must be a non-negative integer"
            raise ValueError(msg)

        # Explicitly reject bool (subclass of int)
        if isinstance(self.behind_count, bool):
            msg = "behind_count must be a non-negative integer, got bool"
            raise ValueError(msg)

        if not isinstance(self.behind_count, int) or self.behind_count < 0:
            msg = "behind_count must be a non-negative integer"
            raise ValueError(msg)


@dataclass(frozen=True)
class MergeResult:
    """Result of merge operation.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation. Conflicts list is converted
    to a tuple for true immutability - the dataclass is only shallowly frozen when
    fields contain mutable types, so we enforce deep immutability via conversion.
    """

    success: bool
    conflicts: tuple[str, ...]
    merge_commit: CommitHash | None

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not isinstance(self.success, bool):
            msg = "success must be a boolean"
            raise ValueError(msg)

        if not isinstance(self.conflicts, tuple):
            msg = "conflicts must be a tuple of strings"
            raise ValueError(msg)

        # Validate all conflict items are strings
        if not all(isinstance(c, str) for c in self.conflicts):
            msg = "all conflicts must be strings"
            raise ValueError(msg)

        # Validate merge_commit is either None or a valid commit hash string
        if self.merge_commit is not None:
            if not isinstance(self.merge_commit, str) or not self.merge_commit:
                msg = "merge_commit must be a non-empty string or None"
                raise ValueError(msg)


@dataclass(frozen=True)
class CommitAuthor:
    """Commit author information.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation.
    """

    name: str
    email: str

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not isinstance(self.name, str) or not self.name:
            msg = "name must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.email, str) or not self.email:
            msg = "email must be a non-empty string"
            raise ValueError(msg)


@dataclass(frozen=True)
class CommitInfo:
    """Complete commit information.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation.
    """

    sha: str
    author: CommitAuthor
    message: str
    timestamp: datetime
    parent_shas: tuple[str, ...] = ()
    body: str = ""

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not isinstance(self.sha, str) or not self.sha:
            msg = "sha must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.author, CommitAuthor):
            msg = "author must be a CommitAuthor instance"
            raise ValueError(msg)

        if not isinstance(self.message, str) or not self.message:
            msg = "message must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.timestamp, datetime):
            msg = "timestamp must be a datetime instance"
            raise ValueError(msg)

        if not isinstance(self.parent_shas, tuple):
            msg = "parent_shas must be a tuple of strings"
            raise ValueError(msg)

        if not all(isinstance(sha, str) for sha in self.parent_shas):
            msg = "all parent_shas must be strings"
            raise ValueError(msg)

        if not isinstance(self.body, str):
            msg = "body must be a string"
            raise ValueError(msg)


# ============================================================================
# Port Interface
# ============================================================================


class IRepository(ABC):
    """Interface for source code repository operations."""

    @abstractmethod
    async def clone(
        self,
        url: str,
        destination: Path,
        branch: BranchName | None = None,
    ) -> RepositoryId:
        """
        Clone a repository.

        Args:
            url: Repository URL
            destination: Local destination path
            branch: Optional branch to clone

        Returns:
            RepositoryId: Identifier for the cloned repository

        Raises:
            RepositoryError: Clone operation failed
            ValidationError: Invalid URL or destination
        """

    @abstractmethod
    async def checkout(
        self,
        repo_path: Path,
        branch: BranchName,
        create: bool = False,
    ) -> None:
        """
        Checkout a branch.

        Args:
            repo_path: Repository path
            branch: Branch name to checkout
            create: Create branch if it doesn't exist

        Raises:
            RepositoryError: Checkout failed
            ResourceNotFoundError: Branch doesn't exist and create=False
        """

    @abstractmethod
    async def create_branch(
        self,
        repo_path: Path,
        branch_name: BranchName,
        from_branch: BranchName | None = None,
    ) -> None:
        """
        Create a new branch.

        Args:
            repo_path: Repository path
            branch_name: Name for new branch
            from_branch: Optional branch to create from (defaults to current)

        Raises:
            RepositoryError: Branch creation failed
            ValidationError: Invalid branch name
        """

    @abstractmethod
    async def stage_files(
        self,
        repo_path: Path,
        files: list[str],
    ) -> None:
        """
        Stage files for commit.

        Adds the specified files to the repository's staging area. This is a
        prerequisite to committing - staging and committing are independent
        operations that follow real git semantics.

        Args:
            repo_path: Repository path
            files: List of file paths to stage

        Raises:
            RepositoryError: Stage operation failed
            ValidationError: Invalid file paths or repo_path
        """

    @abstractmethod
    async def commit(
        self,
        repo_path: Path,
        message: str,
        author_name: str,
        author_email: str,
        files: list[str] | None = None,
    ) -> CommitHash:
        """
        Create a commit.

        Args:
            repo_path: Repository path
            message: Commit message
            author_name: Commit author name
            author_email: Commit author email
            files: Optional list of files to commit (commits all if None)

        Returns:
            str: Commit SHA

        Raises:
            RepositoryError: Commit failed
            ValidationError: Invalid author information
        """

    @abstractmethod
    async def push(
        self,
        repo_path: Path,
        remote: str = "origin",
        branch: str | None = None,
        force: bool = False,
    ) -> None:
        """
        Push commits to remote.

        Args:
            repo_path: Repository path
            remote: Remote name
            branch: Branch to push (defaults to current)
            force: Force push (use with caution)

        Raises:
            RepositoryError: Push failed
            AuthenticationError: Invalid credentials
        """

    @abstractmethod
    async def pull(
        self,
        repo_path: Path,
        remote: str = "origin",
        branch: str | None = None,
    ) -> None:
        """
        Pull commits from remote.

        Args:
            repo_path: Repository path
            remote: Remote name
            branch: Branch to pull (defaults to current)

        Raises:
            RepositoryError: Pull failed
            MergeConflictError: Merge conflicts detected
        """

    @abstractmethod
    async def fetch(
        self,
        repo_path: Path,
        remote: str = "origin",
        prune: bool = False,
    ) -> None:
        """
        Fetch from remote.

        Args:
            repo_path: Repository path
            remote: Remote name
            prune: Remove references to deleted remote branches

        Raises:
            RepositoryError: Fetch failed
        """

    @abstractmethod
    async def diff(
        self,
        repo_path: Path,
        base: str,
        target: str,
    ) -> str:
        """
        Get diff between two refs.

        Args:
            repo_path: Repository path
            base: Base ref (commit, branch, tag)
            target: Target ref (commit, branch, tag)

        Returns:
            str: Diff output

        Raises:
            RepositoryError: Diff failed
            ResourceNotFoundError: Ref doesn't exist
        """

    @abstractmethod
    async def status(self, repo_path: Path) -> RepositoryStatus:
        """
        Get repository status.

        Args:
            repo_path: Repository path

        Returns:
            RepositoryStatus: Current repository status

        Raises:
            RepositoryError: Status check failed
        """

    @abstractmethod
    async def list_branches(
        self,
        repo_path: Path,
        remote: bool = False,
    ) -> list[str]:
        """
        List branches.

        Args:
            repo_path: Repository path
            remote: List remote branches instead of local

        Returns:
            List[str]: List of branch names

        Raises:
            RepositoryError: List operation failed
        """

    @abstractmethod
    async def merge(
        self,
        repo_path: Path,
        branch: str,
        strategy: str = "merge",
    ) -> MergeResult:
        """
        Merge a branch.

        Args:
            repo_path: Repository path
            branch: Branch to merge into current branch
            strategy: Merge strategy (merge, rebase, squash)

        Returns:
            MergeResult: Result of merge operation

        Raises:
            RepositoryError: Merge failed
            MergeConflictError: Conflicts detected
        """

    @abstractmethod
    async def get_file_content(
        self,
        repo_path: Path,
        file_path: str,
        ref: str | None = None,
    ) -> str:
        """
        Get content of a file at a specific ref.

        Args:
            repo_path: Repository path
            file_path: Path to file within repository
            ref: Optional ref (commit, branch, tag) - uses working tree if None

        Returns:
            str: File content

        Raises:
            ResourceNotFoundError: File or ref doesn't exist
            RepositoryError: Read operation failed
        """

    @abstractmethod
    async def get_commit_info(
        self,
        repo_path: Path,
        commit_sha: str,
    ) -> CommitInfo:
        """
        Get information about a commit.

        Args:
            repo_path: Repository path
            commit_sha: Commit SHA

        Returns:
            CommitInfo: Complete commit information with typed fields

        Raises:
            ResourceNotFoundError: Commit doesn't exist
            RepositoryError: Query failed
        """

    @abstractmethod
    async def get_commit_history(
        self,
        repo_path: Path,
        branch: str | None = None,
        limit: int = 100,
        since: datetime | None = None,
    ) -> list[CommitInfo]:
        """
        Get commit history.

        Args:
            repo_path: Repository path
            branch: Branch to get history for (defaults to current)
            limit: Maximum number of commits to return
            since: Only return commits after this date

        Returns:
            List[CommitInfo]: List of commit information with typed fields

        Raises:
            RepositoryError: Query failed
        """

    @abstractmethod
    async def add_remote(
        self,
        repo_path: Path,
        name: str,
        url: str,
    ) -> None:
        """
        Add a remote.

        Args:
            repo_path: Repository path
            name: Remote name
            url: Remote URL

        Raises:
            RepositoryError: Add remote failed
            ValidationError: Invalid remote configuration
        """

    @abstractmethod
    async def remove_remote(
        self,
        repo_path: Path,
        name: str,
    ) -> None:
        """
        Remove a remote.

        Args:
            repo_path: Repository path
            name: Remote name

        Raises:
            ResourceNotFoundError: Remote doesn't exist
            RepositoryError: Remove remote failed
        """
