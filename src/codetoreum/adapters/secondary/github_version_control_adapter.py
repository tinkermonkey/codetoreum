"""GitHub version control adapter implementing IVersionControlService."""

import logging
from pathlib import Path

from codetoreum.adapters.secondary.git_repository_adapter import GitConfig, GitRepositoryAdapter
from codetoreum.ports.exceptions import ResourceNotFoundError
from codetoreum.ports.output.version_control_service import IVersionControlService, Repository, VCSStatus

logger = logging.getLogger(__name__)


class GitHubVersionControlAdapter(IVersionControlService):
    """GitHub version control adapter implementing IVersionControlService.

    Wraps GitRepositoryAdapter (IRepository) to expose the higher-level
    IVersionControlService contract consumed by application services such as
    WorkflowOrchestrator and WorkspaceRouter.

    All git subprocess execution is delegated to GitRepositoryAdapter, which
    owns argument sanitization, timeout management, and error classification.
    This adapter is responsible only for:
    - Translating string-typed port parameters to Path objects expected by IRepository
    - Projecting the richer RepositoryStatus onto the simplified VCSStatus contract
    - Constructing the Repository metadata value object for get_repository()
    """

    def __init__(
        self,
        git_config: GitConfig | None = None,
    ) -> None:
        self._git_config = git_config or GitConfig()
        self._repository_adapter = GitRepositoryAdapter(self._git_config)

    async def clone_repository(self, url: str, target_path: str, branch: str | None = None) -> None:
        try:
            destination = Path(target_path)
            await self._repository_adapter.clone(url, destination, branch)
            logger.info(f"Cloned repository from {url} to {target_path}")
        except Exception as e:
            logger.error(f"Failed to clone repository: {e}", exc_info=True)
            raise

    async def checkout(self, repo_path: str, branch: str) -> None:
        try:
            path = Path(repo_path)
            await self._repository_adapter.checkout(path, branch)
            logger.info(f"Checked out branch {branch} in {repo_path}")
        except Exception as e:
            logger.error(f"Failed to checkout branch {branch}: {e}", exc_info=True)
            raise

    async def create_branch(self, repo_path: str, branch_name: str, from_branch: str | None = None) -> None:
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
        try:
            path = Path(repo_path)
            commit_hash = await self._repository_adapter.commit(
                path, message, author_name or "", author_email or "", files
            )
            logger.info(f"Created commit {commit_hash} in {repo_path}")
            return str(commit_hash)
        except Exception as e:
            logger.error(f"Failed to commit: {e}", exc_info=True)
            raise

    async def push(self, repo_path: str, branch: str) -> None:
        try:
            path = Path(repo_path)
            await self._repository_adapter.push(path, branch=branch)
            logger.info(f"Pushed branch {branch} from {repo_path}")
        except Exception as e:
            logger.error(f"Failed to push: {e}", exc_info=True)
            raise

    async def list_branches(self, repo_path: str, remote: bool = False) -> list[str]:
        try:
            path = Path(repo_path)
            branches = await self._repository_adapter.list_branches(path, remote)
            return branches
        except Exception as e:
            logger.error(f"Failed to list branches: {e}", exc_info=True)
            raise

    async def status(self, repo_path: str) -> VCSStatus:
        try:
            path = Path(repo_path)
            repo_status = await self._repository_adapter.status(path)
            return VCSStatus(
                is_dirty=repo_status.is_dirty,
                staged_files=repo_status.staged_files,
                unstaged_files=repo_status.unstaged_files,
            )
        except Exception as e:
            logger.error(f"Failed to get repository status: {e}", exc_info=True)
            raise

    async def pull(self, repo_path: str, branch: str, remote: str = "origin") -> None:
        try:
            path = Path(repo_path)
            await self._repository_adapter.pull(path, remote=remote, branch=branch)
            logger.info(f"Pulled {branch} from {remote} into {repo_path}")
        except Exception as e:
            logger.error(f"Failed to pull: {e}", exc_info=True)
            raise

    async def get_repository(self, identifier: str) -> Repository:
        try:
            path = Path(identifier)
            repo_name = path.name

            # Validate the repository path by delegating existence check to the adapter.
            # status() raises ValidationError if the path does not exist.
            await self._repository_adapter.status(path)

            # Read the remote URL from .git/config as a plain file read.
            # All subprocess execution stays inside GitRepositoryAdapter; reading a
            # static config file is not a subprocess concern.
            git_config_path = path / ".git" / "config"
            if git_config_path.exists():
                url: str = _parse_remote_url(git_config_path.read_text()) or f"file://{path.absolute()}"
            else:
                url = f"file://{path.absolute()}"

            default_branch = self._git_config.default_branch

            return Repository(
                id=identifier,
                name=repo_name,
                url=url,
                default_branch=default_branch,
            )
        except ResourceNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to get repository {identifier}: {e}", exc_info=True)
            raise ResourceNotFoundError(f"Repository not found: {identifier}") from e


def _parse_remote_url(git_config_text: str) -> str | None:
    """Extract the origin remote URL from a .git/config file text content.

    Parses the INI-style git config format to find the [remote "origin"] section
    and return its url value. Returns None if no origin remote is configured.

    Args:
        git_config_text: Raw text content of a .git/config file.

    Returns:
        The URL string for the origin remote, or None if not found.
    """
    in_origin_section = False
    for line in git_config_text.splitlines():
        stripped = line.strip()
        if stripped == '[remote "origin"]':
            in_origin_section = True
            continue
        if in_origin_section:
            if stripped.startswith("["):
                break
            if stripped.startswith("url"):
                parts = stripped.split("=", 1)
                if len(parts) == 2:
                    return parts[1].strip()
    return None
