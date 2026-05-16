"""GitHub version control adapter for IVersionControlService interface.

This adapter implements version control operations (clone, branch, commit, push)
using Git CLI with GitHub-specific configuration for authentication and repository
management.

This serves as the production version control implementation for the Codetoreum
orchestrator, enabling real git operations against GitHub repositories.
"""

import logging
from pathlib import Path

from codetoreum.adapters.secondary.git_repository_adapter import GitConfig, GitRepositoryAdapter
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.version_control_service import IVersionControlService, Repository, VCSStatus

logger = logging.getLogger(__name__)


class GitHubVersionControlAdapter(IVersionControlService):
    """
    GitHub version control adapter implementing IVersionControlService.

    This adapter provides a production-ready implementation of version control
    operations, delegating to GitRepositoryAdapter for actual git command execution.
    It handles GitHub-specific configuration and authentication.

    The adapter maintains compatibility with the orchestrator's version control
    interface while providing real git operations against GitHub repositories.
    """

    def __init__(
        self,
        event_emitter: IEventEmitter | None = None,
        git_config: GitConfig | None = None,
        **kwargs,  # Accept additional kwargs for compatibility with adapter factory
    ) -> None:
        """
        Initialize the GitHub version control adapter.

        Args:
            event_emitter: Optional event emitter for domain events
            git_config: Optional Git configuration (uses defaults if None)
            **kwargs: Additional arguments (e.g., time_source) for factory compatibility

        Raises:
            ValidationError: If Git configuration is invalid
        """
        self._event_emitter = event_emitter
        self._git_config = git_config or GitConfig()
        self._repository_adapter = GitRepositoryAdapter(self._git_config)

    async def clone_repository(self, url: str, target_path: str, branch: str | None = None) -> None:
        """
        Clone a repository from GitHub.

        Args:
            url: Repository URL (HTTPS or SSH)
            target_path: Local destination path
            branch: Optional branch to clone

        Raises:
            ValidationError: Invalid URL or target path
            RepositoryError: Clone operation failed
        """
        try:
            destination = Path(target_path)
            await self._repository_adapter.clone(url, destination, branch)
            logger.info(f"Cloned repository from {url} to {target_path}")
        except Exception as e:
            logger.error(f"Failed to clone repository: {e}", exc_info=True)
            raise

    async def checkout(self, repo_path: str, branch: str) -> None:
        """
        Checkout a branch in the repository.

        Args:
            repo_path: Repository path
            branch: Branch name to checkout

        Raises:
            RepositoryError: Checkout failed
            ValidationError: Invalid branch name
        """
        try:
            path = Path(repo_path)
            await self._repository_adapter.checkout(path, branch)
            logger.info(f"Checked out branch {branch} in {repo_path}")
        except Exception as e:
            logger.error(f"Failed to checkout branch {branch}: {e}", exc_info=True)
            raise

    async def create_branch(self, repo_path: str, branch_name: str, from_branch: str | None = None) -> None:
        """
        Create a new branch in the repository.

        Args:
            repo_path: Repository path
            branch_name: Name for new branch
            from_branch: Optional branch to create from

        Raises:
            RepositoryError: Branch creation failed
            ValidationError: Invalid branch name
        """
        try:
            path = Path(repo_path)
            await self._repository_adapter.create_branch(path, branch_name, from_branch)
            logger.info(f"Created branch {branch_name} in {repo_path}")
        except Exception as e:
            logger.error(f"Failed to create branch {branch_name}: {e}", exc_info=True)
            raise

    async def commit(
        self,
        repo_path: str,
        message: str,
        author_name: str | None = None,
        author_email: str | None = None,
        files: list[str] | None = None,
    ) -> str:
        """
        Create a commit.

        Args:
            repo_path: Repository path
            message: Commit message
            author_name: Optional author name
            author_email: Optional author email
            files: Optional list of files to commit

        Returns:
            Commit hash

        Raises:
            RepositoryError: Commit failed
            ValidationError: Invalid arguments
        """
        try:
            path = Path(repo_path)
            commit_hash = await self._repository_adapter.commit(
                path, message, author_name or "", author_email or "", files
            )
            logger.info(f"Created commit {commit_hash} in {repo_path}")
            return commit_hash
        except Exception as e:
            logger.error(f"Failed to commit: {e}", exc_info=True)
            raise

    async def push(self, repo_path: str, branch: str) -> None:
        """
        Push changes to remote.

        Args:
            repo_path: Repository path
            branch: Branch to push

        Raises:
            RepositoryError: Push failed
            ValidationError: Invalid arguments
        """
        try:
            path = Path(repo_path)
            await self._repository_adapter.push(path, branch=branch)
            logger.info(f"Pushed branch {branch} from {repo_path}")
        except Exception as e:
            logger.error(f"Failed to push: {e}", exc_info=True)
            raise

    async def list_branches(self, repo_path: str, remote: bool = False) -> list[str]:
        """
        List all branches.

        Args:
            repo_path: Repository path
            remote: If True, include remote branches

        Returns:
            List of branch names

        Raises:
            RepositoryError: List operation failed
        """
        try:
            path = Path(repo_path)
            branches = await self._repository_adapter.list_branches(path, remote)
            return branches
        except Exception as e:
            logger.error(f"Failed to list branches: {e}", exc_info=True)
            raise

    async def status(self, repo_path: str) -> VCSStatus:
        """
        Return repository status.

        Args:
            repo_path: Repository path

        Returns:
            VCSStatus with current repository state

        Raises:
            RepositoryError: Status check failed
        """
        try:
            path = Path(repo_path)
            status = await self._repository_adapter.get_status(path)
            return VCSStatus(
                is_dirty=status.is_dirty,
                staged_files=status.staged_files,
                unstaged_files=status.unstaged_files,
            )
        except Exception as e:
            logger.error(f"Failed to get repository status: {e}", exc_info=True)
            raise

    async def pull(self, repo_path: str, branch: str, remote: str = "origin") -> None:
        """
        Pull latest changes from remote for the given branch.

        Args:
            repo_path: Repository path
            branch: Branch to pull
            remote: Remote name (default: "origin")

        Raises:
            RepositoryError: Pull failed
        """
        try:
            path = Path(repo_path)
            await self._repository_adapter.pull(path, branch, remote)
            logger.info(f"Pulled {branch} from {remote} into {repo_path}")
        except Exception as e:
            logger.error(f"Failed to pull: {e}", exc_info=True)
            raise

    async def get_repository(self, identifier: str) -> Repository:
        """
        Get repository information by identifier.

        Args:
            identifier: Repository identifier (ID, URL, or path)

        Returns:
            Repository metadata

        Raises:
            ResourceNotFoundError: Repository not found
        """
        from codetoreum.ports.exceptions import ResourceNotFoundError

        try:
            # For MVP, we support repository paths as identifiers
            path = Path(identifier)
            # Derive repository name from path
            repo_name = path.name
            return Repository(
                id=identifier,
                name=repo_name,
                url="",  # Not available from path
                default_branch="main",  # Assume main branch
            )
        except Exception as e:
            logger.error(f"Failed to get repository {identifier}: {e}", exc_info=True)
            raise ResourceNotFoundError(f"Repository not found: {identifier}") from e
