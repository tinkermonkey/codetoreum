"""Git repository adapter for IRepository interface."""

import asyncio
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from codetoreum.domain.types import BranchName, CommitHash, RepositoryId
from codetoreum.ports.exceptions import (
    AuthenticationError,
    MergeConflictError,
    RepositoryError,
    ResourceNotFoundError,
    ValidationError,
)
from codetoreum.ports.output.repository import (
    IRepository,
    MergeResult,
    RepositoryStatus,
)


@dataclass
class GitConfig:
    """Configuration for Git repository adapter."""

    # Git executable
    git_path: str = "git"

    # Default author (used when not specified)
    default_author_name: Optional[str] = None
    default_author_email: Optional[str] = None

    # Authentication
    ssh_key_path: Optional[str] = None
    credential_helper: Optional[str] = None

    # Behavior
    default_branch: str = "main"
    auto_create_remote_branch: bool = True

    # Timeouts
    timeout_seconds: int = 300


class GitRepositoryAdapter(IRepository):
    """
    Git repository adapter using Git CLI.

    This adapter implements repository operations using the git command-line tool.
    It provides a clean interface for cloning, branching, committing, and pushing.
    """

    def __init__(self, config: GitConfig):
        """
        Initialize Git adapter.

        Args:
            config: Git configuration
        """
        self.config = config

    async def _run_git_command(
        self,
        args: List[str],
        cwd: Optional[Path] = None,
        env: Optional[dict] = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """
        Run git command asynchronously.

        Args:
            args: Git command arguments
            cwd: Working directory
            env: Environment variables
            check: Raise exception on non-zero exit code

        Returns:
            Completed process

        Raises:
            RepositoryError: Command failed
        """
        cmd = [self.config.git_path] + args

        loop = asyncio.get_event_loop()

        def _run():
            try:
                result = subprocess.run(
                    cmd,
                    cwd=cwd,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=self.config.timeout_seconds,
                    check=check,
                )
                return result
            except subprocess.CalledProcessError as e:
                # Check for specific error conditions
                error_text = e.stderr.lower()

                if "authentication" in error_text or "permission denied" in error_text:
                    raise AuthenticationError(f"Git authentication failed: {e.stderr}")
                elif "conflict" in error_text or "merge conflict" in error_text:
                    raise MergeConflictError(f"Merge conflict detected: {e.stderr}")
                elif "not found" in error_text:
                    raise ResourceNotFoundError("Git resource", str(args))
                else:
                    raise RepositoryError(f"Git command failed: {e.stderr}")
            except subprocess.TimeoutExpired:
                raise RepositoryError(f"Git command timed out after {self.config.timeout_seconds}s")
            except FileNotFoundError:
                raise RepositoryError(f"Git executable not found at: {self.config.git_path}")

        return await loop.run_in_executor(None, _run)

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

        # Build clone command
        args = ["clone"]

        if branch:
            args.extend(["--branch", branch])

        args.extend([url, str(destination)])

        # Execute clone
        await self._run_git_command(args)

        # Return repository ID (using destination path as ID)
        return RepositoryId(str(destination.absolute()))

    async def checkout(
        self,
        repo_path: Path,
        branch: BranchName,
        create: bool = False,
    ) -> None:
        """Checkout a branch."""
        if not repo_path or not repo_path.exists():
            raise ValidationError(f"Repository path does not exist: {repo_path}")

        args = ["checkout"]

        if create:
            args.append("-b")

        args.append(branch)

        await self._run_git_command(args, cwd=repo_path)

    async def create_branch(
        self,
        repo_path: Path,
        branch_name: BranchName,
        from_branch: Optional[BranchName] = None,
    ) -> None:
        """Create a new branch."""
        if not repo_path or not repo_path.exists():
            raise ValidationError(f"Repository path does not exist: {repo_path}")

        args = ["branch", branch_name]

        if from_branch:
            args.append(from_branch)

        await self._run_git_command(args, cwd=repo_path)

    async def commit(
        self,
        repo_path: Path,
        message: str,
        author_name: str,
        author_email: str,
        files: Optional[List[str]] = None,
    ) -> CommitHash:
        """Create a commit."""
        if not repo_path or not repo_path.exists():
            raise ValidationError(f"Repository path does not exist: {repo_path}")

        if not message:
            raise ValidationError("Commit message is required")

        # Stage files
        if files:
            for file in files:
                await self._run_git_command(["add", file], cwd=repo_path)
        else:
            await self._run_git_command(["add", "."], cwd=repo_path)

        # Set up environment with author info
        import os

        env = os.environ.copy()
        env["GIT_AUTHOR_NAME"] = author_name
        env["GIT_AUTHOR_EMAIL"] = author_email
        env["GIT_COMMITTER_NAME"] = author_name
        env["GIT_COMMITTER_EMAIL"] = author_email

        # Create commit
        await self._run_git_command(["commit", "-m", message], cwd=repo_path, env=env)

        # Get commit SHA
        result = await self._run_git_command(["rev-parse", "HEAD"], cwd=repo_path)
        commit_sha = result.stdout.strip()

        return CommitHash(commit_sha)

    async def push(
        self,
        repo_path: Path,
        remote: str = "origin",
        branch: Optional[str] = None,
        force: bool = False,
    ) -> None:
        """Push commits to remote."""
        if not repo_path or not repo_path.exists():
            raise ValidationError(f"Repository path does not exist: {repo_path}")

        args = ["push"]

        if force:
            args.append("--force")

        args.append(remote)

        if branch:
            # Set upstream if auto-create is enabled
            if self.config.auto_create_remote_branch:
                args.extend(["--set-upstream", branch])
            else:
                args.append(branch)

        await self._run_git_command(args, cwd=repo_path)

    async def pull(
        self,
        repo_path: Path,
        remote: str = "origin",
        branch: Optional[str] = None,
    ) -> None:
        """Pull commits from remote."""
        if not repo_path or not repo_path.exists():
            raise ValidationError(f"Repository path does not exist: {repo_path}")

        args = ["pull", remote]

        if branch:
            args.append(branch)

        await self._run_git_command(args, cwd=repo_path)

    async def fetch(
        self,
        repo_path: Path,
        remote: str = "origin",
        prune: bool = False,
    ) -> None:
        """Fetch from remote."""
        if not repo_path or not repo_path.exists():
            raise ValidationError(f"Repository path does not exist: {repo_path}")

        args = ["fetch", remote]

        if prune:
            args.append("--prune")

        await self._run_git_command(args, cwd=repo_path)

    async def diff(
        self,
        repo_path: Path,
        base: str,
        target: str,
    ) -> str:
        """Get diff between two refs."""
        if not repo_path or not repo_path.exists():
            raise ValidationError(f"Repository path does not exist: {repo_path}")

        result = await self._run_git_command(
            ["diff", f"{base}...{target}"],
            cwd=repo_path,
            check=False,
        )

        return result.stdout

    async def status(self, repo_path: Path) -> RepositoryStatus:
        """Get repository status."""
        if not repo_path or not repo_path.exists():
            raise ValidationError(f"Repository path does not exist: {repo_path}")

        # Get current branch
        result = await self._run_git_command(
            ["rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path,
        )
        current_branch = BranchName(result.stdout.strip())

        # Get status (short format)
        result = await self._run_git_command(
            ["status", "--short", "--porcelain"],
            cwd=repo_path,
        )

        # Parse status output
        staged_files = []
        unstaged_files = []
        untracked_files = []

        for line in result.stdout.splitlines():
            if not line:
                continue

            status_code = line[:2]
            filename = line[3:]

            if status_code[0] in ("M", "A", "D", "R", "C"):
                staged_files.append(filename)
            if status_code[1] in ("M", "D"):
                unstaged_files.append(filename)
            if status_code == "??":
                untracked_files.append(filename)

        # Check ahead/behind remote
        ahead_count = 0
        behind_count = 0

        try:
            result = await self._run_git_command(
                ["rev-list", "--left-right", "--count", f"origin/{current_branch}...HEAD"],
                cwd=repo_path,
                check=False,
            )

            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split()
                if len(parts) == 2:
                    behind_count, ahead_count = map(int, parts)
        except Exception:
            # Remote tracking branch may not exist
            pass

        return RepositoryStatus(
            current_branch=current_branch,
            is_dirty=bool(staged_files or unstaged_files or untracked_files),
            staged_files=staged_files,
            unstaged_files=unstaged_files,
            untracked_files=untracked_files,
            ahead_count=ahead_count,
            behind_count=behind_count,
        )

    async def list_branches(
        self,
        repo_path: Path,
        remote: bool = False,
    ) -> List[str]:
        """List branches."""
        if not repo_path or not repo_path.exists():
            raise ValidationError(f"Repository path does not exist: {repo_path}")

        args = ["branch", "--list"]

        if remote:
            args.append("--remote")

        result = await self._run_git_command(args, cwd=repo_path)

        # Parse branch list
        branches = []
        for line in result.stdout.splitlines():
            # Remove leading * and whitespace
            branch = line.strip().lstrip("* ")
            if branch:
                # Remove remote prefix if present
                if remote and "/" in branch:
                    branch = branch.split("/", 1)[1]
                branches.append(branch)

        return branches

    async def merge(
        self,
        repo_path: Path,
        branch: str,
        strategy: str = "merge",
    ) -> MergeResult:
        """Merge a branch."""
        if not repo_path or not repo_path.exists():
            raise ValidationError(f"Repository path does not exist: {repo_path}")

        if strategy not in ("merge", "rebase", "squash"):
            raise ValidationError(f"Invalid merge strategy: {strategy}")

        try:
            if strategy == "merge":
                await self._run_git_command(["merge", branch], cwd=repo_path)
            elif strategy == "rebase":
                await self._run_git_command(["rebase", branch], cwd=repo_path)
            elif strategy == "squash":
                await self._run_git_command(["merge", "--squash", branch], cwd=repo_path)

            # Get merge commit SHA
            result = await self._run_git_command(["rev-parse", "HEAD"], cwd=repo_path)
            commit_sha = CommitHash(result.stdout.strip())

            return MergeResult(
                success=True,
                conflicts=[],
                merge_commit=commit_sha,
            )

        except MergeConflictError as e:
            # Get list of conflicted files
            result = await self._run_git_command(
                ["diff", "--name-only", "--diff-filter=U"],
                cwd=repo_path,
                check=False,
            )

            conflicts = [line.strip() for line in result.stdout.splitlines() if line.strip()]

            return MergeResult(
                success=False,
                conflicts=conflicts,
                merge_commit=None,
            )

    async def get_file_content(
        self,
        repo_path: Path,
        file_path: str,
        ref: Optional[str] = None,
    ) -> str:
        """Get content of a file at a specific ref."""
        if not repo_path or not repo_path.exists():
            raise ValidationError(f"Repository path does not exist: {repo_path}")

        if ref:
            # Get file from git object database
            result = await self._run_git_command(
                ["show", f"{ref}:{file_path}"],
                cwd=repo_path,
            )
            return result.stdout
        else:
            # Read from working tree
            full_path = repo_path / file_path
            if not full_path.exists():
                raise ResourceNotFoundError("File", file_path)

            return full_path.read_text()

    async def get_commit_info(
        self,
        repo_path: Path,
        commit_sha: str,
    ) -> dict:
        """Get information about a commit."""
        if not repo_path or not repo_path.exists():
            raise ValidationError(f"Repository path does not exist: {repo_path}")

        # Get commit info in JSON format
        result = await self._run_git_command(
            [
                "show",
                "--format=%H%n%an%n%ae%n%at%n%s%n%b",
                "--no-patch",
                commit_sha,
            ],
            cwd=repo_path,
        )

        lines = result.stdout.splitlines()
        if len(lines) < 5:
            raise RepositoryError(f"Invalid commit info format for {commit_sha}")

        return {
            "sha": lines[0],
            "author_name": lines[1],
            "author_email": lines[2],
            "timestamp": datetime.fromtimestamp(int(lines[3]), tz=timezone.utc),
            "subject": lines[4],
            "body": "\n".join(lines[5:]) if len(lines) > 5 else "",
        }

    async def get_commit_history(
        self,
        repo_path: Path,
        branch: Optional[str] = None,
        limit: int = 100,
        since: Optional[datetime] = None,
    ) -> List[dict]:
        """Get commit history."""
        if not repo_path or not repo_path.exists():
            raise ValidationError(f"Repository path does not exist: {repo_path}")

        args = [
            "log",
            f"--max-count={limit}",
            "--format=%H|%an|%ae|%at|%s",
        ]

        if since:
            args.append(f"--since={since.isoformat()}")

        if branch:
            args.append(branch)

        result = await self._run_git_command(args, cwd=repo_path)

        commits = []
        for line in result.stdout.splitlines():
            if not line:
                continue

            parts = line.split("|", 4)
            if len(parts) == 5:
                commits.append(
                    {
                        "sha": parts[0],
                        "author_name": parts[1],
                        "author_email": parts[2],
                        "timestamp": datetime.fromtimestamp(int(parts[3]), tz=timezone.utc),
                        "subject": parts[4],
                    }
                )

        return commits

    async def add_remote(
        self,
        repo_path: Path,
        name: str,
        url: str,
    ) -> None:
        """Add a remote."""
        if not repo_path or not repo_path.exists():
            raise ValidationError(f"Repository path does not exist: {repo_path}")

        if not name or not url:
            raise ValidationError("Remote name and URL are required")

        await self._run_git_command(["remote", "add", name, url], cwd=repo_path)

    async def remove_remote(
        self,
        repo_path: Path,
        name: str,
    ) -> None:
        """Remove a remote."""
        if not repo_path or not repo_path.exists():
            raise ValidationError(f"Repository path does not exist: {repo_path}")

        if not name:
            raise ValidationError("Remote name is required")

        await self._run_git_command(["remote", "remove", name], cwd=repo_path)

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        pass
