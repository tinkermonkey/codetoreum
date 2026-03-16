"""In-memory version control service for testing and simulation.

This module provides a mock implementation of IVersionControlService that simulates
git operations (clone, pull, checkout, commit, push) without actual filesystem or
git operations. Useful for testing orchestration logic without external dependencies.
"""

from __future__ import annotations

import hashlib
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codetoreum.ports.output.event_emitter import IEventEmitter

from codetoreum.ports.exceptions import (
    RepositoryError,
    ResourceNotFoundError,
    ValidationError,
)
from codetoreum.ports.output.version_control_service import (
    IVersionControlService,
    Repository,
    VCSStatus,
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

    def __init__(self, event_emitter: IEventEmitter | None = None) -> None:
        """Initialize the in-memory version control service.

        Args:
            event_emitter: Optional event emitter for VCS domain events
        """
        # Map of (repo_path) -> {
        #     'url': str,
        #     'branches': set of branch names,
        #     'current_branch': str,
        #     'commits': dict of branch -> list of commit SHAs,
        #     'default_branch': str,
        #     'pushed_branches': set of branch names that have been pushed
        # }
        self._repositories: dict[str, dict] = {}

        # Map of (identifier) -> Repository for lookup by ID/URL/path
        self._repository_index: dict[str, Repository] = {}

        # Map of repo_path -> list of staged file paths
        self._staged_files: dict[str, list[str]] = {}

        # Map of repo_path -> {file_path -> content}
        self._working_tree: dict[str, dict[str, str]] = {}

        # Counter for unique commit SHAs (avoids SHA collisions)
        self._commit_counter = 0

        # Thread safety for concurrent test execution
        self._lock = threading.Lock()

        self._event_emitter = event_emitter

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
            raise ValidationError(msg)
        if not target_path:
            msg = "Target path cannot be empty"
            raise ValidationError(msg)

        with self._lock:
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
                "pushed_branches": set(),
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
            raise RepositoryError(msg)

        with self._lock:
            repo = self._repositories[repo_path]

            # Check if branch is new before creating it (for event emission)
            branch_is_new = branch not in repo["branches"]

            # Capture base commit from current branch before switching (for event)
            current_branch_commits = repo["commits"].get(repo["current_branch"], ["initial-commit-sha"])
            base_commit = current_branch_commits[-1] if current_branch_commits else "initial-commit-sha"

            # Create branch if it doesn't exist
            if branch_is_new:
                repo["branches"].add(branch)
                repo["commits"][branch] = []

            repo["current_branch"] = branch

        # Emit BranchCreatedEvent if branch was newly created
        if self._event_emitter and branch_is_new:
            from codetoreum.domain.events.repository_events import BranchCreatedEvent

            event = BranchCreatedEvent(
                type="repository.branch_created",
                timestamp=datetime.now(UTC).isoformat(),
                source="in_memory_vcs",
                repository_id=repo_path,
                branch_name=branch,
                base_commit=base_commit,
            )
            self._event_emitter.emit(event)

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
            files: Optional list of files to commit explicitly (bypasses staging area)

        Returns:
            str: Commit SHA (full hash)

        Raises:
            ValidationError: Invalid repo path or message
            RepositoryError: Commit failed (no changes staged, etc.)
        """
        if repo_path not in self._repositories:
            msg = f"Repository not found at path: {repo_path}"
            raise RepositoryError(msg)

        if not message:
            msg = "Commit message cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            repo = self._repositories[repo_path]
            current_branch = repo["current_branch"]

            # Generate a unique commit SHA using counter + message hash
            # This ensures two commits with the same message produce different SHAs
            self._commit_counter += 1
            sha_base = hashlib.sha256(f"{message}-{current_branch}-{self._commit_counter}".encode()).hexdigest()[:40]
            commit_sha = sha_base

            # Add commit to current branch
            if current_branch not in repo["commits"]:
                repo["commits"][current_branch] = []
            repo["commits"][current_branch].append(commit_sha)

            # Determine which files were committed and handle staging area accordingly
            if files is not None:
                # Explicit files provided - commit them directly without modifying staging area
                # This maintains separation between explicit file commits and staged commits
                committed_files = list(files)
            else:
                # Use staged files if no explicit files provided
                committed_files = list(self._staged_files.get(repo_path, []))

                # Clear staging area and remove committed files from working tree (only when committing staged files)
                if repo_path in self._staged_files:
                    self._staged_files[repo_path].clear()
                if repo_path in self._working_tree:
                    working_tree = self._working_tree[repo_path]
                    for file_path in committed_files:
                        working_tree.pop(file_path, None)

        # Emit CommitCreatedEvent if event emitter is configured
        if self._event_emitter:
            from codetoreum.domain.events.repository_events import CommitCreatedEvent

            event = CommitCreatedEvent(
                type="repository.commit_created",
                timestamp=datetime.now(UTC).isoformat(),
                source="in_memory_vcs",
                repository_id=repo_path,
                commit_sha=commit_sha,
                message=message,
                author="orchestrator",
                changed_files=tuple(committed_files),
            )
            self._event_emitter.emit(event)

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
            raise RepositoryError(msg)

        with self._lock:
            repo = self._repositories[repo_path]

            if branch not in repo["branches"]:
                msg = f"Branch not found: {branch}"
                raise RepositoryError(msg)

            # Mark the branch as pushed
            repo["pushed_branches"].add(branch)

        # Emit BranchPushedEvent if event emitter is configured
        if self._event_emitter:
            from codetoreum.domain.events.repository_events import BranchPushedEvent

            event = BranchPushedEvent(
                type="repository.branch_pushed",
                timestamp=datetime.now(UTC).isoformat(),
                source="in_memory_vcs",
                repository_id=repo_path,
                branch_name=branch,
            )
            self._event_emitter.emit(event)

    async def create_branch(self, repo_path: str, branch_name: str, from_branch: str | None = None) -> None:
        """Create a new branch in the in-memory repository."""
        if repo_path not in self._repositories:
            msg = f"Repository not found at path: {repo_path}"
            raise RepositoryError(msg)

        with self._lock:
            repo = self._repositories[repo_path]
            branch_is_new = branch_name not in repo["branches"]

            # Get base commit from from_branch or current branch
            if from_branch and from_branch in repo["commits"]:
                base_commits = repo["commits"][from_branch]
            else:
                current_branch = repo["current_branch"]
                base_commits = repo["commits"].get(current_branch, ["initial-commit-sha"])
            base_commit = base_commits[-1] if base_commits else "initial-commit-sha"

            repo["branches"].add(branch_name)
            if branch_name not in repo["commits"]:
                repo["commits"][branch_name] = []

        # Emit BranchCreatedEvent if event emitter is configured
        if self._event_emitter and branch_is_new:
            from codetoreum.domain.events.repository_events import BranchCreatedEvent

            event = BranchCreatedEvent(
                type="repository.branch_created",
                timestamp=datetime.now(UTC).isoformat(),
                source="in_memory_vcs",
                repository_id=repo_path,
                branch_name=branch_name,
                base_commit=base_commit,
            )
            self._event_emitter.emit(event)

    async def list_branches(self, repo_path: str, remote: bool = False) -> list[str]:
        """List all branches in the in-memory repository."""
        if repo_path not in self._repositories:
            msg = f"Repository not found at path: {repo_path}"
            raise RepositoryError(msg)

        with self._lock:
            repo = self._repositories[repo_path]
            branches = list(repo["branches"])

        if remote:
            # Include remote branches with 'origin/' prefix
            remote_branches = [f"origin/{b}" for b in branches]
            return branches + remote_branches

        return branches

    async def status(self, repo_path: str) -> VCSStatus:
        """Return repository status derived from actual repository state.

        Returns status based on tracked staged and unstaged files.
        """
        if repo_path not in self._repositories:
            msg = f"Repository not found at path: {repo_path}"
            raise RepositoryError(msg)

        with self._lock:
            staged = tuple(self._staged_files.get(repo_path, []))
            working = set(self._working_tree.get(repo_path, {}).keys())
            staged_set = set(staged)
            unstaged = tuple(working - staged_set)

            return VCSStatus(
                is_dirty=len(staged) > 0 or len(unstaged) > 0,
                staged_files=staged,
                unstaged_files=unstaged,
            )

    async def pull(self, repo_path: str, branch: str, remote: str = "origin") -> None:
        """Pull latest changes - no-op in simulation (already up to date).

        In simulation mode, repositories are always up to date since they're
        in-memory with single-writer semantics. No actual remote synchronization
        occurs. This method is a no-op (type b: hardcoded but acceptable).
        """
        if repo_path not in self._repositories:
            msg = f"Repository not found at path: {repo_path}"
            raise RepositoryError(msg)
        # No-op in simulation: single-writer in-memory model means always current

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
        with self._lock:
            if identifier in self._repository_index:
                return self._repository_index[identifier]

        raise ResourceNotFoundError("Repository", identifier)

    # Test helper methods

    def seed_working_tree_file(self, repo_path: str, file_path: str, content: str) -> None:
        """Seed a file in the working tree for testing.

        This test helper adds a file to the working tree without staging it,
        simulating an agent having modified a file. The file will appear in
        unstaged_files when status() is called.

        Args:
            repo_path: Local repository path
            file_path: Path to the file within the repository
            content: File content to seed

        Raises:
            RepositoryError: Repository not found
        """
        if repo_path not in self._repositories:
            msg = f"Repository not found at path: {repo_path}"
            raise RepositoryError(msg)

        with self._lock:
            if repo_path not in self._working_tree:
                self._working_tree[repo_path] = {}
            self._working_tree[repo_path][file_path] = content

    def stage_files(self, repo_path: str, files: list[str]) -> None:
        """Stage files for commit (test helper).

        Adds files to the staging area, making them appear in staged_files
        when status() is called.

        Args:
            repo_path: Local repository path
            files: List of file paths to stage

        Raises:
            RepositoryError: Repository not found
        """
        if repo_path not in self._repositories:
            msg = f"Repository not found at path: {repo_path}"
            raise RepositoryError(msg)

        with self._lock:
            if repo_path not in self._staged_files:
                self._staged_files[repo_path] = []
            for file_path in files:
                if file_path not in self._staged_files[repo_path]:
                    self._staged_files[repo_path].append(file_path)
