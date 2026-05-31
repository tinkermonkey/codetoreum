"""Version control service port interface (synchronous, no events).

This interface defines contracts for version control operations (git operations
like clone, commit, push, etc.). Unlike event-emitting services, version
control operations are synchronous command-style interfaces with no event
emission.

This is essentially an alias/wrapper for the existing IRepository port,
providing a consistency point and documentation for how version control
services fit into the adapter architecture.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class VCSStatus:
    """Repository status information for IVersionControlService.

    Simplified status for version control operations. Frozen to prevent
    accidental mutation after creation.
    """

    is_dirty: bool
    staged_files: tuple[str, ...]
    unstaged_files: tuple[str, ...]


@dataclass(frozen=True)
class Repository:
    """Metadata about a repository.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation.

    Attributes:
        id: Unique identifier for the repository
        name: Repository name
        url: Repository URL (may be SSH, HTTPS, or file path)
        default_branch: Default branch (typically "main" or "master")
    """

    id: str
    name: str
    url: str
    default_branch: str

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not isinstance(self.id, str) or not self.id:
            msg = "id must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.name, str) or not self.name:
            msg = "name must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.url, str) or not self.url:
            msg = "url must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.default_branch, str) or not self.default_branch:
            msg = "default_branch must be a non-empty string"
            raise ValueError(msg)


class IVersionControlService(ABC):
    """Version control operations (synchronous, no events).

    Provides vendor-agnostic abstraction for version control systems
    (Git, Mercurial, etc.). These are synchronous command operations
    without event emission, used for repository setup and state management.

    This service is used by the orchestrator to:
    1. Clone repositories for agent execution
    2. Check out specific branches
    3. Commit changes made by agents
    4. Push changes back to remote

    Note: This interface explicitly has NO event emission. Version control
    operations are orchestrator-controlled actions, not changes detected
    from external systems. Events related to code reviews are handled by
    ICodeReviewService instead.

    Example:
        async with service as svc:
            # Clone repository
            await svc.clone_repository(
                url="https://github.com/org/repo.git",
                target_path="/workspace/repo"
            )

            # Check out a feature branch
            await svc.checkout("/workspace/repo", "feature/new-feature")

            # Make changes (agent execution happens here)
            # ... agent modifies files ...

            # Commit and push
            commit_sha = await svc.commit(
                "/workspace/repo",
                "Agent: Implemented feature X"
            )
            await svc.push("/workspace/repo", "feature/new-feature")

            # Query repository info
            repo = await svc.get_repository("repo-123")
    """

    @abstractmethod
    async def clone_repository(self, url: str, target_path: str, branch: str | None = None) -> None:
        """Clone a repository to local path.

        Args:
            url: Repository URL (HTTPS, SSH, or file path)
            target_path: Local destination path
            branch: Optional branch to clone (defaults to remote default)

        Raises:
            ValidationError: Invalid URL or target path
            RepositoryError: Clone operation failed (network, auth, etc.)
        """

    @abstractmethod
    async def checkout(self, repo_path: str, branch: str) -> None:
        """Checkout specific branch.

        Switches the repository to the specified branch.

        Args:
            repo_path: Local repository path
            branch: Branch name to check out

        Raises:
            ValidationError: Invalid repo path or branch name
            RepositoryError: Checkout failed (branch doesn't exist, etc.)
        """

    @abstractmethod
    async def commit(
        self,
        repo_path: str,
        message: str,
        author_name: str | None = None,
        author_email: str | None = None,
        files: list[str] | None = None,
    ) -> str:
        """Create commit with all staged changes.

        Creates a commit containing staged changes and returns the commit SHA.

        Args:
            repo_path: Local repository path
            message: Commit message
            author_name: Optional commit author name
            author_email: Optional commit author email
            files: Optional list of files to include (all if None)

        Returns:
            str: Commit SHA (full hash)

        Raises:
            ValidationError: Invalid repo path or message
            RepositoryError: Commit failed (no changes staged, etc.)
        """

    @abstractmethod
    async def push(self, repo_path: str, branch: str) -> None:
        """Push branch to remote.

        Pushes the specified branch to the remote repository, making
        local commits available to others.

        Args:
            repo_path: Local repository path
            branch: Branch to push

        Raises:
            ValidationError: Invalid repo path or branch name
            RepositoryError: Push failed (auth, rejected, etc.)
        """

    @abstractmethod
    async def create_branch(self, repo_path: str, branch_name: str, from_branch: str | None = None) -> None:
        """Create a new branch.

        Args:
            repo_path: Local repository path
            branch_name: Name for new branch
            from_branch: Optional branch to create from (defaults to current branch if None)

        Raises:
            ValidationError: Invalid repo path or branch name
            RepositoryError: Branch creation failed
        """

    @abstractmethod
    async def list_branches(self, repo_path: str, remote: bool = False) -> list[str]:
        """List all branches.

        Args:
            repo_path: Local repository path
            remote: If True, include remote branches (prefixed with 'origin/')

        Returns:
            list[str]: List of branch names

        Raises:
            RepositoryError: List operation failed
        """

    @abstractmethod
    async def status(self, repo_path: str) -> VCSStatus:
        """Return repository status.

        Args:
            repo_path: Local repository path

        Returns:
            VCSStatus: Current repository status

        Raises:
            RepositoryError: Status check failed
        """

    @abstractmethod
    async def pull(self, repo_path: str, branch: str, remote: str = "origin") -> None:
        """Pull latest changes from remote for the given branch.

        Args:
            repo_path: Local repository path
            branch: Branch to pull
            remote: Remote name (default: "origin")

        Raises:
            RepositoryError: Pull failed
        """

    @abstractmethod
    async def get_repository(self, identifier: str) -> Repository:
        """Retrieve repository metadata.

        Gets information about a repository (name, URL, default branch).
        The identifier could be an ID, URL, or local path depending on
        the implementation.

        Args:
            identifier: Repository identifier (ID, URL, or path)

        Returns:
            Repository: Repository metadata

        Raises:
            ResourceNotFoundError: Repository not found
            ExternalServiceError: Service communication failure
        """

    @abstractmethod
    async def create_pull_request(
        self,
        repo_path: str,
        head: str,
        base: str,
        title: str,
        body: str = "",
    ) -> str:
        """Open a pull request from ``head`` into ``base`` on the remote.

        Used after a successful agent push to surface the work for human
        review. Idempotent on the head branch: if a PR already exists for
        ``head`` -> ``base``, the existing PR URL is returned instead of
        raising.

        Args:
            repo_path: Local repository path (used to look up the remote
                URL, e.g. via ``git remote get-url origin``).
            head: Source branch name (must already be pushed).
            base: Target branch name (typically the project default branch).
            title: PR title.
            body: PR body. May be empty.

        Returns:
            PR URL on the hosting provider. The exact format is
            implementation-specific (e.g. ``https://github.com/owner/repo/pull/123``).

        Raises:
            ResourceNotFoundError: Repository or branch not found on remote.
            AuthenticationError: Credentials are missing or invalid.
            ExternalServiceError: Provider rejected the request for any
                other reason.
        """
