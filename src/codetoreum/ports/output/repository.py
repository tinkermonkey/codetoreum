"""IRepository output port interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from codetoreum.domain.types import BranchName, CommitHash, RemoteName, RepositoryId

# ============================================================================
# Data Models
# ============================================================================


@dataclass
class RepositoryStatus:
    """Repository status information."""

    current_branch: BranchName
    is_dirty: bool
    staged_files: List[str]
    unstaged_files: List[str]
    untracked_files: List[str]
    ahead_count: int
    behind_count: int


@dataclass
class MergeResult:
    """Result of merge operation."""

    success: bool
    conflicts: List[str]
    merge_commit: Optional[CommitHash]


# ============================================================================
# Port Interface
# ============================================================================


class IRepository(ABC):
    """Interface for source code repository operations."""

    @abstractmethod
    async def clone(
        self,
        url: str,
        destination: Path,
        branch: Optional[BranchName] = None,
    ) -> RepositoryId:
        """
        Clone a repository.

        Args:
            url: Repository URL
            destination: Local destination path
            branch: Optional branch to clone

        Returns:
            RepositoryId: Identifier for the cloned repository

        Raises:
            RepositoryError: Clone operation failed
            ValidationError: Invalid URL or destination
        """
        pass

    @abstractmethod
    async def checkout(
        self,
        repo_path: Path,
        branch: BranchName,
        create: bool = False,
    ) -> None:
        """
        Checkout a branch.

        Args:
            repo_path: Repository path
            branch: Branch name to checkout
            create: Create branch if it doesn't exist

        Raises:
            RepositoryError: Checkout failed
            ResourceNotFoundError: Branch doesn't exist and create=False
        """
        pass

    @abstractmethod
    async def create_branch(
        self,
        repo_path: Path,
        branch_name: BranchName,
        from_branch: Optional[BranchName] = None,
    ) -> None:
        """
        Create a new branch.

        Args:
            repo_path: Repository path
            branch_name: Name for new branch
            from_branch: Optional branch to create from (defaults to current)

        Raises:
            RepositoryError: Branch creation failed
            ValidationError: Invalid branch name
        """
        pass

    @abstractmethod
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
            repo_path: Repository path
            message: Commit message
            author_name: Commit author name
            author_email: Commit author email
            files: Optional list of files to commit (commits all if None)

        Returns:
            str: Commit SHA

        Raises:
            RepositoryError: Commit failed
            ValidationError: Invalid author information
        """
        pass

    @abstractmethod
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
            repo_path: Repository path
            remote: Remote name
            branch: Branch to push (defaults to current)
            force: Force push (use with caution)

        Raises:
            RepositoryError: Push failed
            AuthenticationError: Invalid credentials
        """
        pass

    @abstractmethod
    async def pull(
        self,
        repo_path: Path,
        remote: str = "origin",
        branch: Optional[str] = None,
    ) -> None:
        """
        Pull commits from remote.

        Args:
            repo_path: Repository path
            remote: Remote name
            branch: Branch to pull (defaults to current)

        Raises:
            RepositoryError: Pull failed
            MergeConflictError: Merge conflicts detected
        """
        pass

    @abstractmethod
    async def fetch(
        self,
        repo_path: Path,
        remote: str = "origin",
        prune: bool = False,
    ) -> None:
        """
        Fetch from remote.

        Args:
            repo_path: Repository path
            remote: Remote name
            prune: Remove references to deleted remote branches

        Raises:
            RepositoryError: Fetch failed
        """
        pass

    @abstractmethod
    async def diff(
        self,
        repo_path: Path,
        base: str,
        target: str,
    ) -> str:
        """
        Get diff between two refs.

        Args:
            repo_path: Repository path
            base: Base ref (commit, branch, tag)
            target: Target ref (commit, branch, tag)

        Returns:
            str: Diff output

        Raises:
            RepositoryError: Diff failed
            ResourceNotFoundError: Ref doesn't exist
        """
        pass

    @abstractmethod
    async def status(self, repo_path: Path) -> RepositoryStatus:
        """
        Get repository status.

        Args:
            repo_path: Repository path

        Returns:
            RepositoryStatus: Current repository status

        Raises:
            RepositoryError: Status check failed
        """
        pass

    @abstractmethod
    async def list_branches(
        self,
        repo_path: Path,
        remote: bool = False,
    ) -> List[str]:
        """
        List branches.

        Args:
            repo_path: Repository path
            remote: List remote branches instead of local

        Returns:
            List[str]: List of branch names

        Raises:
            RepositoryError: List operation failed
        """
        pass

    @abstractmethod
    async def merge(
        self,
        repo_path: Path,
        branch: str,
        strategy: str = "merge",
    ) -> MergeResult:
        """
        Merge a branch.

        Args:
            repo_path: Repository path
            branch: Branch to merge into current branch
            strategy: Merge strategy (merge, rebase, squash)

        Returns:
            MergeResult: Result of merge operation

        Raises:
            RepositoryError: Merge failed
            MergeConflictError: Conflicts detected
        """
        pass

    @abstractmethod
    async def get_file_content(
        self,
        repo_path: Path,
        file_path: str,
        ref: Optional[str] = None,
    ) -> str:
        """
        Get content of a file at a specific ref.

        Args:
            repo_path: Repository path
            file_path: Path to file within repository
            ref: Optional ref (commit, branch, tag) - uses working tree if None

        Returns:
            str: File content

        Raises:
            ResourceNotFoundError: File or ref doesn't exist
            RepositoryError: Read operation failed
        """
        pass

    @abstractmethod
    async def get_commit_info(
        self,
        repo_path: Path,
        commit_sha: str,
    ) -> dict:
        """
        Get information about a commit.

        Args:
            repo_path: Repository path
            commit_sha: Commit SHA

        Returns:
            dict: Commit information (author, message, timestamp, etc.)

        Raises:
            ResourceNotFoundError: Commit doesn't exist
            RepositoryError: Query failed
        """
        pass

    @abstractmethod
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
            repo_path: Repository path
            branch: Branch to get history for (defaults to current)
            limit: Maximum number of commits to return
            since: Only return commits after this date

        Returns:
            List[dict]: List of commit information

        Raises:
            RepositoryError: Query failed
        """
        pass

    @abstractmethod
    async def add_remote(
        self,
        repo_path: Path,
        name: str,
        url: str,
    ) -> None:
        """
        Add a remote.

        Args:
            repo_path: Repository path
            name: Remote name
            url: Remote URL

        Raises:
            RepositoryError: Add remote failed
            ValidationError: Invalid remote configuration
        """
        pass

    @abstractmethod
    async def remove_remote(
        self,
        repo_path: Path,
        name: str,
    ) -> None:
        """
        Remove a remote.

        Args:
            repo_path: Repository path
            name: Remote name

        Raises:
            ResourceNotFoundError: Remote doesn't exist
            RepositoryError: Remove remote failed
        """
        pass
