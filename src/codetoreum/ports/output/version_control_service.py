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


@dataclass
class Repository:
    """Metadata about a repository.

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
    async def clone_repository(
        self, url: str, target_path: str, branch: str | None = None
    ) -> None:
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
    async def pull_latest(self, repo_path: str) -> None:
        """Pull latest changes from remote.

        Updates the local repository to match the remote, pulling all
        new commits, branches, and tags.

        Args:
            repo_path: Local repository path

        Raises:
            ValidationError: Invalid repo path
            RepositoryError: Pull operation failed (conflicts, network, etc.)
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
    async def commit(self, repo_path: str, message: str) -> str:
        """Create commit with all staged changes.

        Creates a commit containing staged changes and returns the commit SHA.

        Args:
            repo_path: Local repository path
            message: Commit message

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
