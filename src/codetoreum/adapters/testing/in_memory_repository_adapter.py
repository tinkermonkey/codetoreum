"""In-memory repository adapter for testing."""

import asyncio
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


class InMemoryRepositoryAdapter(IRepository):
    """
    In-memory repository implementation for testing.

    Simulates git operations using in-memory data structures. Useful for
    testing without requiring actual git repositories.
    """

    def __init__(self):
        """Initialize the in-memory repository adapter."""
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

    async def clone(
        self,
        url: str,
        destination: Path,
        branch: Optional[BranchName] = None,
    ) -> RepositoryId:
        """Clone a repository."""
        if not url:
            raise ValidationError("Repository URL is required")

        if not destination:
            raise ValidationError("Destination path is required")

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
        """Checkout a branch."""
        repo_id = self._get_repo_id_by_path(repo_path)

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
        """Create a new branch."""
        repo_id = self._get_repo_id_by_path(repo_path)

        if not branch_name:
            raise ValidationError("Branch name is required")

        source_branch = from_branch or self._repositories[repo_id]["current_branch"]

        if (repo_id, source_branch) not in self._branches:
            raise ResourceNotFoundError("Branch", source_branch)

        # Create new branch pointing to same commit as source
        source_commit = self._branches[(repo_id, source_branch)]
        self._branches[(repo_id, branch_name)] = source_commit

    async def commit(
        self,
        repo_path: Path,
        message: str,
        author_name: str,
        author_email: str,
        files: Optional[List[str]] = None,
    ) -> CommitHash:
        """Create a commit."""
        repo_id = self._get_repo_id_by_path(repo_path)

        if not message or not message.strip():
            raise ValidationError("Commit message is required")

        if not author_name or not author_email:
            raise ValidationError("Author name and email are required")

        current_branch = self._repositories[repo_id]["current_branch"]
        parent_commit = self._branches.get((repo_id, current_branch))

        # Create new commit
        commit_sha = CommitHash(str(uuid4()))

        self._commits[(repo_id, commit_sha)] = {
            "sha": commit_sha,
            "message": message,
            "author_name": author_name,
            "author_email": author_email,
            "timestamp": datetime.now(timezone.utc),
            "parent": parent_commit,
            "files": files or [],
        }

        # Update branch pointer
        self._branches[(repo_id, current_branch)] = commit_sha

        return commit_sha

    async def push(
        self,
        repo_path: Path,
        remote: str = "origin",
        branch: Optional[str] = None,
        force: bool = False,
    ) -> None:
        """Push commits to remote."""
        repo_id = self._get_repo_id_by_path(repo_path)

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
        """Pull commits from remote."""
        repo_id = self._get_repo_id_by_path(repo_path)

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
        """Fetch from remote."""
        repo_id = self._get_repo_id_by_path(repo_path)

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
        """Get diff between two refs."""
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
        """Get repository status."""
        repo_id = self._get_repo_id_by_path(repo_path)
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
        """List branches."""
        repo_id = self._get_repo_id_by_path(repo_path)

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
        """Merge a branch."""
        repo_id = self._get_repo_id_by_path(repo_path)

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
        """Get content of a file at a specific ref."""
        repo_id = self._get_repo_id_by_path(repo_path)

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
        """Get information about a commit."""
        repo_id = self._get_repo_id_by_path(repo_path)

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
        """Get commit history."""
        repo_id = self._get_repo_id_by_path(repo_path)

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
        """Add a remote."""
        repo_id = self._get_repo_id_by_path(repo_path)

        if not name or not url:
            raise ValidationError("Remote name and URL are required")

        self._remotes[(repo_id, name)] = url

    async def remove_remote(
        self,
        repo_path: Path,
        name: str,
    ) -> None:
        """Remove a remote."""
        repo_id = self._get_repo_id_by_path(repo_path)

        remote_key = (repo_id, name)

        if remote_key not in self._remotes:
            raise ResourceNotFoundError("Remote", name)

        del self._remotes[remote_key]

    # Helper methods

    def _get_repo_id_by_path(self, repo_path: Path) -> str:
        """Get repository ID by path."""
        path_str = str(repo_path)

        for repo_id, repo_data in self._repositories.items():
            if repo_data["path"] == path_str:
                return repo_id

        raise ResourceNotFoundError("Repository", path_str)

    def set_file_content(self, repo_path: Path, file_path: str, content: str) -> None:
        """Set file content (for testing)."""
        repo_id = self._get_repo_id_by_path(repo_path)
        self._files[(repo_id, file_path)] = content

    def clear(self) -> None:
        """Clear all repositories (for testing)."""
        self._repositories.clear()
        self._files.clear()
        self._commits.clear()
        self._branches.clear()
        self._remotes.clear()

    def get_repository_count(self) -> int:
        """Get number of repositories (for testing)."""
        return len(self._repositories)
