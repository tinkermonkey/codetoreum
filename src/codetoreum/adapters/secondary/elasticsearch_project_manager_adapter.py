"""Elasticsearch-backed project manager adapter for production multi-project orchestration.

Reads project configurations from the Elasticsearch config store and uses git
to clone/pull project repositories into a local workspace directory.
"""

import asyncio
import logging
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from codetoreum.domain.events.project_events import (
    ProjectClonedEvent,
    ProjectCloneFailedEvent,
)
from codetoreum.domain.repository_url import extract_repo_name
from codetoreum.domain.value_objects import ProjectConfig as DomainProjectConfig
from codetoreum.ports.exceptions import ExternalServiceError, ResourceNotFoundError
from codetoreum.ports.output.config_store import ConfigNotFoundError, IConfigStore
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.project_manager_service import IProjectManagerService

logger = logging.getLogger(__name__)


class ElasticsearchProjectManagerAdapter(IProjectManagerService):
    """Production project manager backed by Elasticsearch config store.

    Reads all registered projects from the config-projects ES index.
    Every registered project is treated as enabled. Uses git subprocess
    calls to clone or update project repositories on the local filesystem.
    """

    def __init__(
        self,
        config_store: IConfigStore,
        base_workspace: str = "/tmp/codetoreum-workspaces",
        event_emitter: IEventEmitter | None = None,
        github_token: str | None = None,
    ) -> None:
        self._config_store = config_store
        self._base_workspace = base_workspace
        self._event_emitter = event_emitter
        self._github_token = github_token or os.getenv("GITHUB_TOKEN")

    async def reload_config(self) -> None:
        """No-op — config is read live from Elasticsearch on each call."""

    async def get_enabled_projects(self) -> list[str]:
        """Return all project IDs registered in the config store (all are enabled)."""
        try:
            projects = await self._config_store.list_projects()
            return sorted(p.id for p in projects)
        except Exception as e:
            msg = f"Failed to list projects from config store: {e}"
            raise ExternalServiceError(service="project_manager", message=msg) from e

    async def get_project_config(self, project_name: str) -> DomainProjectConfig:
        """Fetch project config from ES and convert to the domain ProjectConfig."""
        try:
            store_cfg = await self._config_store.get_project_config(project_name)
        except ConfigNotFoundError as e:
            raise ResourceNotFoundError("project", project_name) from e
        except Exception as e:
            msg = f"Failed to get project config '{project_name}': {e}"
            raise ExternalServiceError(service="project_manager", message=msg) from e

        metadata = dict(store_cfg.metadata)
        repo_url = (
            metadata.get("repository_url") or f"https://github.com/{store_cfg.github_org}/{store_cfg.github_repo}.git"
        )
        branch = metadata.get("default_branch") or "main"

        return DomainProjectConfig(
            repo_url=repo_url,
            branch=branch,
            enabled=True,
            org=store_cfg.github_org,
        )

    async def get_project_path(self, project_name: str) -> str:
        """Return the local workspace path for the project repository."""
        config = await self.get_project_config(project_name)
        repo_name = extract_repo_name(config.repo_url)
        return str(Path(self._base_workspace) / repo_name)

    async def ensure_project_cloned(self, project_name: str) -> str:
        """Clone or pull the project repository to the local workspace.

        Uses HTTPS clone with optional GITHUB_TOKEN for private repos.
        Emits ProjectClonedEvent on success, ProjectCloneFailedEvent on error.
        """
        config = await self.get_project_config(project_name)
        workspace_path = await self.get_project_path(project_name)
        repo_dir = Path(workspace_path)

        clone_url = self._inject_token(config.repo_url)

        now_iso = datetime.now(UTC).isoformat()
        try:
            if repo_dir.exists() and (repo_dir / ".git").exists():
                await self._git_pull(repo_dir, config.branch)
            else:
                repo_dir.parent.mkdir(parents=True, exist_ok=True)
                await self._git_clone(clone_url, repo_dir, config.branch)
                await self._git_checkout(repo_dir, config.branch)

            logger.info(f"Project '{project_name}' ready at {workspace_path}")
            await self._emit(
                ProjectClonedEvent(
                    type="project.cloned",
                    timestamp=now_iso,
                    source="elasticsearch_project_manager",
                    project_name=project_name,
                    repo_url=config.repo_url,
                    workspace_path=workspace_path,
                    branch=config.branch,
                )
            )
            return workspace_path

        except ExternalServiceError:
            raise
        except Exception as e:
            msg = f"Failed to clone/pull project '{project_name}': {e}"
            logger.error(msg, exc_info=True)
            await self._emit(
                ProjectCloneFailedEvent(
                    type="project.clone_failed",
                    timestamp=now_iso,
                    source="elasticsearch_project_manager",
                    project_name=project_name,
                    repo_url=config.repo_url,
                    error_message=str(e),
                    will_retry=True,
                )
            )
            raise ExternalServiceError(service="project_manager", message=msg) from e

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _inject_token(self, repo_url: str) -> str:
        """Insert GITHUB_TOKEN into HTTPS URL if available."""
        if self._github_token and repo_url.startswith("https://github.com/"):
            return repo_url.replace(
                "https://github.com/",
                f"https://{self._github_token}@github.com/",
            )
        return repo_url

    async def _git_clone(self, url: str, dest: Path, branch: str) -> None:
        await self._run_git(["clone", "--branch", branch, "--single-branch", url, str(dest)])

    async def _git_pull(self, repo_dir: Path, branch: str) -> None:
        await self._run_git(["fetch", "origin"], cwd=repo_dir)
        await self._run_git(["checkout", branch], cwd=repo_dir)
        await self._run_git(["pull", "origin", branch, "--ff-only"], cwd=repo_dir)

    async def _git_checkout(self, repo_dir: Path, branch: str) -> None:
        await self._run_git(["checkout", branch], cwd=repo_dir)

    async def _run_git(self, args: list[str], cwd: Path | None = None) -> str:
        """Run a git command in a thread pool and return stdout."""
        cmd = ["git"] + args

        def _run() -> str:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=120,
                check=True,
                shell=False,
            )
            return result.stdout

        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, _run)
        except subprocess.CalledProcessError as e:
            msg = f"git {args[0]} failed: {e.stderr.strip()}"
            raise ExternalServiceError(service="git", message=msg) from e
        except subprocess.TimeoutExpired as e:
            msg = f"git {args[0]} timed out"
            raise ExternalServiceError(service="git", message=msg) from e

    async def _emit(self, event: object) -> None:
        if self._event_emitter:
            try:
                self._event_emitter.emit(event)
            except Exception:
                logger.warning("Failed to emit project event", exc_info=True)
