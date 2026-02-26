"""In-memory version control service for testing and simulation.

This module provides a mock implementation of IVersionControlService that simulates
git operations (clone, pull, checkout, commit, push) without actual filesystem or
git operations. Useful for testing orchestration logic without external dependencies.
"""

import hashlib

from codetoreum.ports.output.version_control_service import (
    IVersionControlService,
    Repository,
)


class InMemoryVersionControlService(IVersionControlService):
    """In-memory version control service mock for testing.

    Simulates git operations without actual filesystem or git operations.
    Maintains in-memory state representing repositories, branches, and commits.

    Example:
        service = InMemoryVersionControlService()

        # Clone a repository
        await service.clone_repository(
            url="https://github.com/org/repo.git",
            target_path="/workspace/repo"
        )

        # Checkout a branch
        await service.checkout("/workspace/repo", "feature/new-feature")

        # Get repository info
        repo = await service.get_repository("repo-123")
        assert repo.name == "repo"
    """

    def __init__(self) -> None:
        """Initialize the in-memory version control service."""
        # Map of (repo_path) -> {
        #     'url': str,
        #     'branches': set of branch names,
        #     'current_branch': str,
        #     'commits': dict of branch -> list of commit SHAs,
        #     'default_branch': str
        # }
        self._repositories: dict[str, dict] = {}

        # Map of (identifier) -> Repository for lookup by ID/URL/path
        self._repository_index: dict[str, Repository] = {}

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
        if not url:
            msg = "Repository URL cannot be empty"
            raise ValueError(msg)
        if not target_path:
            msg = "Target path cannot be empty"
            raise ValueError(msg)

        # Extract repository name from URL
        repo_name = url.rstrip("/").split("/")[-1].replace(".git", "")

        # Store repository state
        target_branch = branch or "main"
        self._repositories[target_path] = {
            "url": url,
            "branches": {target_branch},
            "current_branch": target_branch,
            "commits": {target_branch: ["initial-commit-sha"]},
            "default_branch": "main",
        }

        # Add to index
        self._repository_index[url] = Repository(
            id=repo_name,
            name=repo_name,
            url=url,
            default_branch="main",
        )
        self._repository_index[target_path] = Repository(
            id=repo_name,
            name=repo_name,
            url=url,
            default_branch="main",
        )

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
        if repo_path not in self._repositories:
            msg = f"Repository not found at path: {repo_path}"
            raise ValueError(msg)

        # Simulate pulling latest from remote
        # In this mock, just mark that a pull occurred
        repo = self._repositories[repo_path]
        current_branch = repo["current_branch"]

        # Add a new commit to simulate remote changes
        if current_branch not in repo["commits"]:
            repo["commits"][current_branch] = []
        repo["commits"][current_branch].append("pull-latest-sha")

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
        if repo_path not in self._repositories:
            msg = f"Repository not found at path: {repo_path}"
            raise ValueError(msg)

        repo = self._repositories[repo_path]

        # Create branch if it doesn't exist
        if branch not in repo["branches"]:
            repo["branches"].add(branch)
            repo["commits"][branch] = []

        repo["current_branch"] = branch

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
        if repo_path not in self._repositories:
            msg = f"Repository not found at path: {repo_path}"
            raise ValueError(msg)

        if not message:
            msg = "Commit message cannot be empty"
            raise ValueError(msg)

        repo = self._repositories[repo_path]
        current_branch = repo["current_branch"]

        # Generate a mock commit SHA based on the message
        # In reality this would be a full git hash
        commit_sha = hashlib.sha1(f"{message}-{current_branch}".encode()).hexdigest()[:40]

        # Add commit to current branch
        if current_branch not in repo["commits"]:
            repo["commits"][current_branch] = []
        repo["commits"][current_branch].append(commit_sha)

        return commit_sha

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
        if repo_path not in self._repositories:
            msg = f"Repository not found at path: {repo_path}"
            raise ValueError(msg)

        repo = self._repositories[repo_path]

        if branch not in repo["branches"]:
            msg = f"Branch not found: {branch}"
            raise ValueError(msg)

        # Simulate pushing to remote
        # In this mock, we just mark the push occurred
        # A real implementation would interact with Git

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
        if identifier in self._repository_index:
            return self._repository_index[identifier]

        msg = f"Repository not found: {identifier}"
        raise ValueError(msg)
