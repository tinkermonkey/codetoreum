"""GitHub version control adapter implementing IVersionControlService."""

import logging
import subprocess
from pathlib import Path

from codetoreum.adapters.secondary.git_repository_adapter import GitConfig, GitRepositoryAdapter
from codetoreum.ports.exceptions import ResourceNotFoundError
from codetoreum.ports.output.version_control_service import IVersionControlService, Repository, VCSStatus

logger = logging.getLogger(__name__)


class GitHubVersionControlAdapter(IVersionControlService):
    """GitHub version control adapter implementing IVersionControlService."""

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
            return commit_hash
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
        try:
            path = Path(repo_path)
            await self._repository_adapter.pull(path, remote=remote, branch=branch)
            logger.info(f"Pulled {branch} from {remote} into {repo_path}")
        except Exception as e:
            logger.error(f"Failed to pull: {e}", exc_info=True)
            raise

    async def get_repository(self, identifier: str) -> Repository:
        try:
            # For MVP, we support repository paths as identifiers
            path = Path(identifier)
            repo_name = path.name

            # Get the remote URL from the repository
            try:
                url = subprocess.run(
                    ["git", "remote", "get-url", "origin"],  # noqa: S607
                    cwd=path,
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.strip()
            except (subprocess.CalledProcessError, FileNotFoundError):
                # Fallback: use file path as URL
                url = f"file://{path.absolute()}"

            return Repository(
                id=identifier,
                name=repo_name,
                url=url,
                default_branch="main",
            )
        except Exception as e:
            logger.error(f"Failed to get repository {identifier}: {e}", exc_info=True)
            raise ResourceNotFoundError(f"Repository not found: {identifier}") from e
