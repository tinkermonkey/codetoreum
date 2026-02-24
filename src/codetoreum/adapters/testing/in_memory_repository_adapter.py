"""In-memory repository adapter for testing."""

import asyncio
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from codetoreum.domain.types import BranchName, CommitHash, RemoteName, RepositoryId
from codetoreum.ports.exceptions import (
    ResourceNotFoundError,
    ValidationError,
)
from codetoreum.ports.output.repository import (
    IRepository,
    MergeResult,
    RepositoryStatus,
)
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.domain.events.repository_events import (
    CommitCreatedEvent,
    BranchCreatedEvent,
    FilesStagedEvent,
)
from codetoreum.adapters.secondary.mock_event_emitter import MockEventEmitter


class InMemoryRepositoryAdapter(IRepository):
    """
    In-memory repository implementation for testing.

    Simulates git operations using in-memory data structures. Useful for
    testing without requiring actual git repositories.

    Note: This adapter is thread-safe for concurrent test execution. All
    dictionary and list modifications are protected by a lock.
    """

    def __init__(self, event_emitter: Optional[IEventEmitter] = None):
        """Initialize the in-memory repository adapter with thread-safe storage.

        Args:
            event_emitter: Optional IEventEmitter for emitting domain events.
                          Defaults to MockEventEmitter.
        """
        # Repository storage: repo_id -> repo_data
        self._repositories: Dict[str, Dict] = {}

        # File storage: (repo_id, path) -> content
        self._files: Dict[tuple[str, str], str] = {}

        # Commit storage: (repo_id, commit_sha) -> commit_info
        self._commits: Dict[tuple[str, str], Dict] = {}

        # Branch storage: (repo_id, branch_name) -> commit_sha
        self._branches: Dict[tuple[str, str], str] = {}

        # Remote storage: (repo_id, remote_name) -> url
        self._remotes: Dict[tuple[str, str], str] = {}

        # Thread safety for concurrent test execution
        self._lock = threading.Lock()

        # Event emission
        self._event_emitter = event_emitter or MockEventEmitter()

    async def clone(
        self,
        url: str,
        destination: Path,
        branch: Optional[BranchName] = None,
    ) -> RepositoryId:
        """
        Clone a repository.

        Args:
            url: Repository URL to clone from
            destination: Local path to clone to
            branch: Optional branch to checkout (defaults to "main")

        Returns:
            Repository ID

        Raises:
            ValidationError: If url or destination is None/empty
        """
        if not url:
            raise ValidationError("Repository URL is required")

        if not destination:
            raise ValidationError("Destination path is required")

        with self._lock:
            repo_id = str(uuid4())
            default_branch = branch or BranchName("main")

            # Initialize repository
            self._repositories[repo_id] = {
                "id": repo_id,
                "url": url,
                "path": str(destination),
                "current_branch": default_branch,
                "created_at": datetime.now(timezone.utc),
            }

            # Create default branch
            initial_commit = str(uuid4())
            self._branches[(repo_id, default_branch)] = initial_commit

            # Create initial commit
            self._commits[(repo_id, initial_commit)] = {
                "sha": initial_commit,
                "message": "Initial commit",
                "author_name": "System",
                "author_email": "system@codetoreum.local",
                "timestamp": datetime.now(timezone.utc),
                "parent": None,
            }

            # Add origin remote
            self._remotes[(repo_id, "origin")] = url

            return RepositoryId(repo_id)

    async def checkout(
        self,
        repo_path: Path,
        branch: BranchName,
        create: bool = False,
    ) -> None:
        """
        Checkout a branch.

        Args:
            repo_path: Path to the repository
            branch: Branch name to checkout
            create: Whether to create the branch if it doesn't exist

        Raises:
            ResourceNotFoundError: If repository or branch doesn't exist (and create=False)
            ValidationError: If repo_path or branch is None/empty
        """
        if not repo_path:
            raise ValidationError("Repository path is required")

        if not branch:
            raise ValidationError("Branch name is required")

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            if (repo_id, branch) not in self._branches:
                if create:
                    # Create new branch from current HEAD
                    current_branch = self._repositories[repo_id]["current_branch"]
                    current_commit = self._branches[(repo_id, current_branch)]
                    self._branches[(repo_id, branch)] = current_commit
                else:
                    raise ResourceNotFoundError("Branch", branch)

            self._repositories[repo_id]["current_branch"] = branch

    async def create_branch(
        self,
        repo_path: Path,
        branch_name: BranchName,
        from_branch: Optional[BranchName] = None,
    ) -> None:
        """
        Create a new branch.

        Args:
            repo_path: Path to the repository
            branch_name: Name of the new branch
            from_branch: Optional source branch (defaults to current branch)

        Raises:
            ResourceNotFoundError: If repository or source branch doesn't exist
            ValidationError: If repo_path or branch_name is None/empty
        """
        if not repo_path:
            raise ValidationError("Repository path is required")

        if not branch_name:
            raise ValidationError("Branch name is required")

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            source_branch = from_branch or self._repositories[repo_id]["current_branch"]

            if (repo_id, source_branch) not in self._branches:
                raise ResourceNotFoundError("Branch", source_branch)

            # Create new branch pointing to same commit as source
            source_commit = self._branches[(repo_id, source_branch)]
            self._branches[(repo_id, branch_name)] = source_commit

            # Emit domain event
            self._event_emitter.emit(
                BranchCreatedEvent(
                    type="repository.branch_created",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    source="mock",
                    repository_id=repo_id,
                    branch_name=str(branch_name),
                    base_commit=str(source_commit),
                    project_id=None,
                )
            )

    async def commit(
        self,
        repo_path: Path,
        message: str,
        author_name: str,
        author_email: str,
        files: Optional[List[str]] = None,
    ) -> CommitHash:
        """
        Create a commit.

        Args:
            repo_path: Path to the repository
            message: Commit message
            author_name: Author name
            author_email: Author email
            files: Optional list of files to commit

        Returns:
            Commit hash

        Raises:
            ResourceNotFoundError: If repository doesn't exist
            ValidationError: If required parameters are None/empty
        """
        if not repo_path:
            raise ValidationError("Repository path is required")

        if not message or not message.strip():
            raise ValidationError("Commit message is required")

        if not author_name or not author_email:
            raise ValidationError("Author name and email are required")

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            current_branch = self._repositories[repo_id]["current_branch"]
            parent_commit = self._branches.get((repo_id, current_branch))

            # Create new commit
            commit_sha = CommitHash(str(uuid4()))
            changed_files = files or []

            self._commits[(repo_id, commit_sha)] = {
                "sha": commit_sha,
                "message": message,
                "author_name": author_name,
                "author_email": author_email,
                "timestamp": datetime.now(timezone.utc),
                "parent": parent_commit,
                "files": changed_files,
            }

            # Update branch pointer
            self._branches[(repo_id, current_branch)] = commit_sha

            # Emit FilesStagedEvent if files were provided
            if changed_files:
                self._event_emitter.emit(
                    FilesStagedEvent(
                        type="repository.files_staged",
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        source="mock",
                        repository_id=repo_id,
                        file_paths=tuple(changed_files),
                        project_id=None,
                    )
                )

            # Emit CommitCreatedEvent
            self._event_emitter.emit(
                CommitCreatedEvent(
                    type="repository.commit_created",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    source="mock",
                    repository_id=repo_id,
                    commit_sha=str(commit_sha),
                    message=message,
                    author=f"{author_name} <{author_email}>",
                    changed_files=tuple(changed_files),
                    project_id=None,
                )
            )

            return commit_sha

    async def push(
        self,
        repo_path: Path,
        remote: str = "origin",
        branch: Optional[str] = None,
        force: bool = False,
    ) -> None:
        """
        Push commits to remote.

        Args:
            repo_path: Path to the repository
            remote: Remote name (default "origin")
            branch: Optional branch name (defaults to current branch)
            force: Whether to force push

        Raises:
            ResourceNotFoundError: If repository, remote, or branch doesn't exist
            ValidationError: If repo_path is None/empty
        """
        if not repo_path:
            raise ValidationError("Repository path is required")

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            if (repo_id, remote) not in self._remotes:
                raise ResourceNotFoundError("Remote", remote)

            # In-memory simulation, just mark as pushed
            target_branch = branch or self._repositories[repo_id]["current_branch"]

            if (repo_id, target_branch) not in self._branches:
                raise ResourceNotFoundError("Branch", target_branch)

        # Simulate push delay
        await asyncio.sleep(0.01)

    async def pull(
        self,
        repo_path: Path,
        remote: str = "origin",
        branch: Optional[str] = None,
    ) -> None:
        """
        Pull commits from remote.

        Args:
            repo_path: Path to the repository
            remote: Remote name (default "origin")
            branch: Optional branch name

        Raises:
            ResourceNotFoundError: If repository or remote doesn't exist
            ValidationError: If repo_path is None/empty
        """
        if not repo_path:
            raise ValidationError("Repository path is required")

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            if (repo_id, remote) not in self._remotes:
                raise ResourceNotFoundError("Remote", remote)

        # Simulate pull delay
        await asyncio.sleep(0.01)

    async def fetch(
        self,
        repo_path: Path,
        remote: str = "origin",
        prune: bool = False,
    ) -> None:
        """
        Fetch from remote.

        Args:
            repo_path: Path to the repository
            remote: Remote name (default "origin")
            prune: Whether to prune deleted branches

        Raises:
            ResourceNotFoundError: If repository or remote doesn't exist
            ValidationError: If repo_path is None/empty
        """
        if not repo_path:
            raise ValidationError("Repository path is required")

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            if (repo_id, remote) not in self._remotes:
                raise ResourceNotFoundError("Remote", remote)

        # Simulate fetch delay
        await asyncio.sleep(0.01)

    async def diff(
        self,
        repo_path: Path,
        base: str,
        target: str,
    ) -> str:
        """
        Get diff between two refs.

        Args:
            repo_path: Path to the repository
            base: Base ref (commit, branch, tag)
            target: Target ref to compare against

        Returns:
            Diff output as string

        Raises:
            ResourceNotFoundError: If repository doesn't exist
            ValidationError: If any parameter is None/empty
        """
        if not repo_path:
            raise ValidationError("Repository path is required")

        if not base:
            raise ValidationError("Base ref is required")

        if not target:
            raise ValidationError("Target ref is required")

        repo_id = self._get_repo_id_by_path(repo_path)

        # Return mock diff
        return f"""diff --git a/file.txt b/file.txt
index abc123..def456 100644
--- a/file.txt
+++ b/file.txt
@@ -1,3 +1,3 @@
 line 1
-old line 2
+new line 2
 line 3
"""

    async def status(self, repo_path: Path) -> RepositoryStatus:
        """
        Get repository status.

        Args:
            repo_path: Path to the repository

        Returns:
            Repository status information

        Raises:
            ResourceNotFoundError: If repository doesn't exist
            ValidationError: If repo_path is None/empty
        """
        if not repo_path:
            raise ValidationError("Repository path is required")

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            current_branch = self._repositories[repo_id]["current_branch"]

            return RepositoryStatus(
                current_branch=current_branch,
                is_dirty=False,
                staged_files=[],
                unstaged_files=[],
                untracked_files=[],
                ahead_count=0,
                behind_count=0,
            )

    async def list_branches(
        self,
        repo_path: Path,
        remote: bool = False,
    ) -> List[str]:
        """
        List branches.

        Args:
            repo_path: Path to the repository
            remote: Whether to list remote branches

        Returns:
            List of branch names

        Raises:
            ResourceNotFoundError: If repository doesn't exist
            ValidationError: If repo_path is None/empty
        """
        if not repo_path:
            raise ValidationError("Repository path is required")

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            branches = [
                branch for (rid, branch) in self._branches.keys()
                if rid == repo_id
            ]

            return branches

    async def merge(
        self,
        repo_path: Path,
        branch: str,
        strategy: str = "merge",
    ) -> MergeResult:
        """
        Merge a branch.

        Args:
            repo_path: Path to the repository
            branch: Branch name to merge
            strategy: Merge strategy (default "merge")

        Returns:
            Merge result with status and conflicts

        Raises:
            ResourceNotFoundError: If repository or branch doesn't exist
            ValidationError: If repo_path or branch is None/empty
        """
        if not repo_path:
            raise ValidationError("Repository path is required")

        if not branch:
            raise ValidationError("Branch name is required")

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            if (repo_id, branch) not in self._branches:
                raise ResourceNotFoundError("Branch", branch)

            current_branch = self._repositories[repo_id]["current_branch"]
            current_commit = self._branches[(repo_id, current_branch)]
            merge_commit = self._branches[(repo_id, branch)]

            # Create merge commit
            new_commit = CommitHash(str(uuid4()))

            self._commits[(repo_id, new_commit)] = {
                "sha": new_commit,
                "message": f"Merge branch '{branch}' into '{current_branch}'",
                "author_name": "System",
                "author_email": "system@codetoreum.local",
                "timestamp": datetime.now(timezone.utc),
                "parent": current_commit,
                "merge_parent": merge_commit,
            }

            # Update current branch
            self._branches[(repo_id, current_branch)] = new_commit

            return MergeResult(
                success=True,
                conflicts=[],
                merge_commit=new_commit,
            )

    async def get_file_content(
        self,
        repo_path: Path,
        file_path: str,
        ref: Optional[str] = None,
    ) -> str:
        """
        Get content of a file at a specific ref.

        Args:
            repo_path: Path to the repository
            file_path: Path to the file within the repository
            ref: Optional ref (commit, branch, tag)

        Returns:
            File content as string (empty if file doesn't exist)

        Raises:
            ResourceNotFoundError: If repository doesn't exist
            ValidationError: If repo_path or file_path is None/empty
        """
        if not repo_path:
            raise ValidationError("Repository path is required")

        if not file_path:
            raise ValidationError("File path is required")

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            file_key = (repo_id, file_path)

            if file_key in self._files:
                return self._files[file_key]

            # Return empty content if file doesn't exist
            return ""

    async def get_commit_info(
        self,
        repo_path: Path,
        commit_sha: str,
    ) -> dict:
        """
        Get information about a commit.

        Args:
            repo_path: Path to the repository
            commit_sha: Commit SHA hash

        Returns:
            Dictionary with commit information

        Raises:
            ResourceNotFoundError: If repository or commit doesn't exist
            ValidationError: If repo_path or commit_sha is None/empty
        """
        if not repo_path:
            raise ValidationError("Repository path is required")

        if not commit_sha:
            raise ValidationError("Commit SHA is required")

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            commit_key = (repo_id, commit_sha)

            if commit_key not in self._commits:
                raise ResourceNotFoundError("Commit", commit_sha)

            commit = self._commits[commit_key]
            return {
                "sha": commit["sha"],
                "message": commit["message"],
                "author": {
                    "name": commit["author_name"],
                    "email": commit["author_email"],
                },
                "timestamp": commit["timestamp"].isoformat(),
                "parent": commit.get("parent"),
            }

    async def get_commit_history(
        self,
        repo_path: Path,
        branch: Optional[str] = None,
        limit: int = 100,
        since: Optional[datetime] = None,
    ) -> List[dict]:
        """
        Get commit history.

        Args:
            repo_path: Path to the repository
            branch: Optional branch name (defaults to current branch)
            limit: Maximum number of commits to return (default 100)
            since: Optional timestamp to filter commits after

        Returns:
            List of commit information dictionaries

        Raises:
            ResourceNotFoundError: If repository or branch doesn't exist
            ValidationError: If repo_path is None/empty
        """
        if not repo_path:
            raise ValidationError("Repository path is required")

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            target_branch = branch or self._repositories[repo_id]["current_branch"]

            if (repo_id, target_branch) not in self._branches:
                raise ResourceNotFoundError("Branch", target_branch)

            # Get commits starting from branch HEAD
            commits = []
            current_commit = self._branches[(repo_id, target_branch)]

            while current_commit and len(commits) < limit:
                commit_key = (repo_id, current_commit)
                if commit_key in self._commits:
                    commit = self._commits[commit_key]

                    if since and commit["timestamp"] < since:
                        break

                    commits.append({
                        "sha": commit["sha"],
                        "message": commit["message"],
                        "author": {
                            "name": commit["author_name"],
                            "email": commit["author_email"],
                        },
                        "timestamp": commit["timestamp"].isoformat(),
                    })

                    current_commit = commit.get("parent")
                else:
                    break

            return commits

    async def add_remote(
        self,
        repo_path: Path,
        name: str,
        url: str,
    ) -> None:
        """
        Add a remote.

        Args:
            repo_path: Path to the repository
            name: Remote name
            url: Remote URL

        Raises:
            ResourceNotFoundError: If repository doesn't exist
            ValidationError: If any parameter is None/empty
        """
        if not repo_path:
            raise ValidationError("Repository path is required")

        if not name or not name.strip():
            raise ValidationError("Remote name is required")

        if not url or not url.strip():
            raise ValidationError("Remote URL is required")

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            self._remotes[(repo_id, name)] = url

    async def remove_remote(
        self,
        repo_path: Path,
        name: str,
    ) -> None:
        """
        Remove a remote.

        Args:
            repo_path: Path to the repository
            name: Remote name to remove

        Raises:
            ResourceNotFoundError: If repository or remote doesn't exist
            ValidationError: If repo_path or name is None/empty
        """
        if not repo_path:
            raise ValidationError("Repository path is required")

        if not name:
            raise ValidationError("Remote name is required")

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            remote_key = (repo_id, name)

            if remote_key not in self._remotes:
                raise ResourceNotFoundError("Remote", name)

            del self._remotes[remote_key]

    # Helper methods

    def _get_repo_id_by_path(self, repo_path: Path) -> str:
        """
        Get repository ID by path (internal helper).

        Args:
            repo_path: Path to the repository

        Returns:
            Repository ID

        Raises:
            ResourceNotFoundError: If repository doesn't exist
        """
        path_str = str(repo_path)

        with self._lock:
            for repo_id, repo_data in self._repositories.items():
                if repo_data["path"] == path_str:
                    return repo_id

        raise ResourceNotFoundError("Repository", path_str)

    def set_file_content(self, repo_path: Path, file_path: str, content: str) -> None:
        """
        Set file content (for testing).

        Args:
            repo_path: Path to the repository
            file_path: Path to the file within the repository
            content: File content to set
        """
        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            self._files[(repo_id, file_path)] = content

    def clear(self) -> None:
        """
        Clear all repositories (for testing).

        This is a testing helper method to reset the adapter state.
        """
        with self._lock:
            self._repositories.clear()
            self._files.clear()
            self._commits.clear()
            self._branches.clear()
            self._remotes.clear()

    def get_repository_count(self) -> int:
        """
        Get number of repositories (for testing).

        Returns:
            Number of repositories in storage
        """
        with self._lock:
            return len(self._repositories)
