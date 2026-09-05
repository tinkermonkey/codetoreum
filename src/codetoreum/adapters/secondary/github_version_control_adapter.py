"""GitHub version control adapter implementing IVersionControlService."""

import logging
from pathlib import Path

from codetoreum.adapters.secondary.git_repository_adapter import GitConfig, GitRepositoryAdapter
from codetoreum.ports.exceptions import ResourceNotFoundError
from codetoreum.ports.output.failed_event_store import IFailedEventStore
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
        failed_event_store: IFailedEventStore | None = None,
    ) -> None:
        self._git_config = git_config or GitConfig()
        self._repository_adapter = GitRepositoryAdapter(self._git_config)
        self.failed_event_store = failed_event_store

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

    async def create_pull_request(
        self,
        repo_path: str,
        head: str,
        base: str,
        title: str,
        body: str = "",
    ) -> str:
        """Open a GitHub PR from ``head`` into ``base``.

        Looks up the remote origin to derive owner/repo, then calls
        ``POST /repos/{owner}/{repo}/pulls`` with the server's
        ``GITHUB_TOKEN``. Idempotent: if a PR already exists for the same
        head→base pair, returns its URL instead of raising.
        """
        import os

        import httpx

        path = Path(repo_path)
        # Resolve origin URL via the underlying git CLI (uses the env-scrub +
        # token extraheader path from GitRepositoryAdapter._run_git_command).
        result = await self._repository_adapter._run_git_command(
            ["remote", "get-url", "origin"],
            cwd=path,
        )
        origin_url = result.stdout.strip()

        owner, repo = _parse_github_owner_repo(origin_url)
        if not owner or not repo:
            from codetoreum.ports.exceptions import RepositoryError

            msg = f"Could not parse GitHub owner/repo from origin URL: {origin_url}"
            raise RepositoryError(msg)

        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            from codetoreum.ports.exceptions import AuthenticationError

            msg = "GITHUB_TOKEN not set; cannot create pull request"
            raise AuthenticationError(msg)

        url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        payload = {"head": head, "base": base, "title": title, "body": body}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)

        if response.status_code == 201:
            pr_url = response.json().get("html_url", "")
            logger.info(f"Opened pull request {pr_url} ({head} -> {base}) for {owner}/{repo}")
            return pr_url

        # GitHub returns 422 with a specific error when a PR already
        # exists for this head/base. Resolve to the existing PR URL.
        if response.status_code == 422:
            existing = await self._find_open_pull_request(
                client_factory=lambda: httpx.AsyncClient(timeout=30.0),
                owner=owner,
                repo=repo,
                head=head,
                base=base,
                headers=headers,
            )
            if existing:
                logger.info(f"Pull request already exists for {head} -> {base}: {existing}")
                return existing

        # Any other error is fatal.
        from codetoreum.ports.exceptions import ExternalServiceError

        msg = (
            f"GitHub PR creation failed ({response.status_code}) for "
            f"{owner}/{repo} {head}->{base}: {response.text[:300]}"
        )
        logger.error(msg)
        raise ExternalServiceError(service="github", message=msg)

    async def update_pull_request_title(
        self,
        repo_path: str,
        head: str,
        base: str,
        new_title: str,
    ) -> bool:
        """Update the title of an open PR if it exists and differs (idempotent).

        Looks up an existing PR for head→base. If found and the title differs,
        updates it via PATCH /repos/{owner}/{repo}/pulls/{number}. If the title
        already matches, skips the API call and returns False (idempotent no-op).
        If no PR exists, returns False silently.

        Args:
            repo_path: Local repository path.
            head: Source branch name.
            base: Target branch name.
            new_title: The new PR title.

        Returns:
            bool: True if the title was updated, False if no update was needed
            (PR already had the title or PR does not exist).

        Raises:
            AuthenticationError: Credentials missing or invalid.
            ExternalServiceError: Provider rejected the request.
        """
        import os

        import httpx

        path = Path(repo_path)
        result = await self._repository_adapter._run_git_command(
            ["remote", "get-url", "origin"],
            cwd=path,
        )
        origin_url = result.stdout.strip()

        owner, repo = _parse_github_owner_repo(origin_url)
        if not owner or not repo:
            from codetoreum.ports.exceptions import RepositoryError

            msg = f"Could not parse GitHub owner/repo from origin URL: {origin_url}"
            raise RepositoryError(msg)

        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            from codetoreum.ports.exceptions import AuthenticationError

            msg = "GITHUB_TOKEN not set; cannot update pull request"
            raise AuthenticationError(msg)

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        # Look up the existing PR
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls?" f"head={owner}:{head}&base={base}&state=open"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)

        if response.status_code != 200:
            logger.warning(f"Failed to list PRs for {head}->{base}: {response.status_code}")
            return False

        items = response.json()
        if not isinstance(items, list) or not items:
            logger.debug(f"No open PR found for {head} -> {base}")
            return False

        pr_data = items[0]
        pr_number = pr_data.get("number")
        current_title = pr_data.get("title", "")

        # Check if title already matches (idempotent)
        if current_title == new_title:
            logger.debug(f"PR #{pr_number} already has title '{new_title}'; skipping update")
            return False

        # Update the PR title
        update_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        payload = {"title": new_title}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.patch(update_url, headers=headers, json=payload)

        if response.status_code == 200:
            logger.info(
                f"Updated PR #{pr_number} title from '{current_title}' to '{new_title}' "
                f"({head} -> {base}) for {owner}/{repo}"
            )
            return True

        from codetoreum.ports.exceptions import ExternalServiceError

        msg = (
            f"GitHub PR title update failed ({response.status_code}) for "
            f"{owner}/{repo} PR #{pr_number}: {response.text[:300]}"
        )
        logger.error(msg)
        raise ExternalServiceError(service="github", message=msg)

    async def _find_open_pull_request(
        self,
        *,
        client_factory,
        owner: str,
        repo: str,
        head: str,
        base: str,
        headers: dict,
    ) -> str | None:
        """Look up an existing PR for head→base, or None."""
        import httpx as _httpx  # noqa: F401  (caller already has it)

        url = f"https://api.github.com/repos/{owner}/{repo}/pulls?" f"head={owner}:{head}&base={base}&state=open"
        async with client_factory() as c:
            resp = await c.get(url, headers=headers)
        if resp.status_code != 200:
            return None
        items = resp.json()
        if isinstance(items, list) and items:
            return items[0].get("html_url")
        return None

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
                untracked_files=repo_status.untracked_files,
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


def _parse_github_owner_repo(url: str) -> tuple[str | None, str | None]:
    """Extract (owner, repo) from a GitHub HTTPS or SSH remote URL.

    Accepts:
        https://github.com/owner/repo.git
        https://github.com/owner/repo
        git@github.com:owner/repo.git
    Returns (None, None) when the URL is not a github.com remote.
    """
    s = url.strip()
    if s.endswith(".git"):
        s = s[:-4]
    if s.startswith("git@github.com:"):
        path = s[len("git@github.com:") :]
    elif s.startswith("https://github.com/"):
        path = s[len("https://github.com/") :]
    elif s.startswith("http://github.com/"):
        path = s[len("http://github.com/") :]
    else:
        return None, None
    parts = path.split("/", 1)
    if len(parts) != 2:
        return None, None
    return parts[0], parts[1]
