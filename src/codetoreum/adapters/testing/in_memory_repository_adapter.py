"""In-memory repository adapter for testing."""

import asyncio
import difflib
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from codetoreum.adapters.secondary.mock_event_emitter import MockEventEmitter
from codetoreum.domain.events.repository_events import (
    BranchCreatedEvent,
    CommitCreatedEvent,
    FilesStagedEvent,
)
from codetoreum.domain.types import BranchName, CommitHash, RepositoryId
from codetoreum.ports.exceptions import (
    ResourceNotFoundError,
    ValidationError,
)
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.repository import (
    CommitAuthor,
    CommitInfo,
    IRepository,
    MergeResult,
    RepositoryStatus,
)


class InMemoryRepositoryAdapter(IRepository):
    """
    In-memory repository implementation for testing.

    Simulates git operations using in-memory data structures. Useful for
    testing without requiring actual git repositories.

    Note: This adapter is thread-safe for concurrent test execution. All
    dictionary and list modifications are protected by a lock.
    """

    def __init__(
        self,
        event_emitter: IEventEmitter | None = None,
        time_source: Callable[[], datetime] | None = None,
    ):
        """Initialize the in-memory repository adapter with thread-safe storage.

        Args:
            event_emitter: Optional IEventEmitter for emitting domain events.
                          Defaults to MockEventEmitter.
            time_source: Optional callable returning current datetime for simulation clock control.
                        Defaults to datetime.now(UTC).
        """
        # Repository storage: repo_id -> repo_data
        self._repositories: dict[str, dict] = {}

        # File storage: (repo_id, path) -> content
        self._files: dict[tuple[str, str], str] = {}

        # Commit storage: (repo_id, commit_sha) -> commit_info
        self._commits: dict[tuple[str, str], dict] = {}

        # Branch storage: (repo_id, branch_name) -> commit_sha
        self._branches: dict[tuple[str, str], str] = {}

        # Remote storage: (repo_id, remote_name) -> url
        self._remotes: dict[tuple[str, str], str] = {}

        # Staging area: repo_id -> list of staged file paths
        self._staged_files: dict[str, list[str]] = {}

        # Working tree: repo_id -> {path -> content}
        self._working_tree: dict[str, dict[str, str]] = {}

        # Thread safety for concurrent test execution
        self._lock = threading.Lock()

        # Event emission
        self._event_emitter = event_emitter or MockEventEmitter()
        self._time_source = time_source or (lambda: datetime.now(UTC))

    async def clone(
        self,
        url: str,
        destination: Path,
        branch: BranchName | None = None,
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
            msg = "Repository URL is required"
            raise ValidationError(msg)

        if not destination:
            msg = "Destination path is required"
            raise ValidationError(msg)

        with self._lock:
            repo_id = str(uuid4())
            default_branch = branch or BranchName("main")

            # Initialize repository
            self._repositories[repo_id] = {
                "id": repo_id,
                "url": url,
                "path": str(destination),
                "current_branch": default_branch,
                "created_at": self._time_source(),
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
                "timestamp": self._time_source(),
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
            msg = "Repository path is required"
            raise ValidationError(msg)

        if not branch:
            msg = "Branch name is required"
            raise ValidationError(msg)

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            if (repo_id, branch) not in self._branches:
                if create:
                    # Create new branch from current HEAD
                    current_branch = self._repositories[repo_id]["current_branch"]
                    current_commit = self._branches[(repo_id, current_branch)]
                    self._branches[(repo_id, branch)] = current_commit
                else:
                    msg = "Branch"
                    raise ResourceNotFoundError(msg, branch)

            self._repositories[repo_id]["current_branch"] = branch

    async def create_branch(
        self,
        repo_path: Path,
        branch_name: BranchName,
        from_branch: BranchName | None = None,
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
            msg = "Repository path is required"
            raise ValidationError(msg)

        if not branch_name:
            msg = "Branch name is required"
            raise ValidationError(msg)

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            source_branch = from_branch or self._repositories[repo_id]["current_branch"]

            if (repo_id, source_branch) not in self._branches:
                msg = "Branch"
                raise ResourceNotFoundError(msg, source_branch)

            # Create new branch pointing to same commit as source
            source_commit = self._branches[(repo_id, source_branch)]
            self._branches[(repo_id, branch_name)] = source_commit

            # Emit domain event
            # Note: source="mock" identifies this as a test/simulation event for traceability
            self._event_emitter.emit(
                BranchCreatedEvent(
                    type="repository.branch_created",
                    timestamp=self._time_source().isoformat(),
                    source="mock",
                    repository_id=repo_id,
                    branch_name=str(branch_name),
                    base_commit=str(source_commit),
                    project_id=None,
                )
            )

    async def stage_files(
        self,
        repo_path: Path,
        files: list[str],
    ) -> None:
        """
        Stage files for commit.

        Adds the specified files to the repository's staging area. This is a
        prerequisite to committing - staging and committing are independent
        operations that follow real git semantics.

        Args:
            repo_path: Path to the repository
            files: List of file paths to stage

        Raises:
            ResourceNotFoundError: If repository doesn't exist
            ValidationError: If repo_path or files is None/empty
        """
        if not repo_path:
            msg = "Repository path is required"
            raise ValidationError(msg)

        if not files:
            msg = "Files list is required and cannot be empty"
            raise ValidationError(msg)

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            # Initialize staging area for this repo if needed
            if repo_id not in self._staged_files:
                self._staged_files[repo_id] = []

            # Add files to staging area (avoiding duplicates)
            for file_path in files:
                if file_path not in self._staged_files[repo_id]:
                    self._staged_files[repo_id].append(file_path)

            # Emit FilesStagedEvent
            # Note: source="mock" identifies this as a test/simulation event for traceability
            self._event_emitter.emit(
                FilesStagedEvent(
                    type="repository.files_staged",
                    timestamp=self._time_source().isoformat(),
                    source="mock",
                    repository_id=repo_id,
                    file_paths=tuple(files),
                    project_id=None,
                )
            )

    async def commit(
        self,
        repo_path: Path,
        message: str,
        author_name: str,
        author_email: str,
        files: list[str] | None = None,
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
            msg = "Repository path is required"
            raise ValidationError(msg)

        if not message or not message.strip():
            msg = "Commit message is required"
            raise ValidationError(msg)

        if not author_name or not author_email:
            msg = "Author name and email are required"
            raise ValidationError(msg)

        repo_id = self._get_repo_id_by_path(repo_path)

        # Capture repository path and determine changed files (locked section only)
        with self._lock:
            current_branch = self._repositories[repo_id]["current_branch"]
            parent_commit = self._branches.get((repo_id, current_branch))
            repo_path_str = self._repositories[repo_id]["path"]

            # Determine which files to commit
            if files is not None:
                # Explicit files provided - commit them directly without modifying staging area
                # This maintains separation between explicit file commits and staged commits
                changed_files = list(files)  # Make a copy
            else:
                # Use staged files if no explicit files provided
                # Make a copy to avoid referencing the mutable list
                changed_files = list(self._staged_files.get(repo_id, []))

                # Clear staging area after commit (only when committing staged files)
                if repo_id in self._staged_files:
                    self._staged_files[repo_id].clear()

            # Capture file contents from in-memory stores (while locked)
            file_contents_from_memory = {}
            for file_path in changed_files:
                # First priority: working tree (files modified via set_working_tree_file)
                if repo_id in self._working_tree and file_path in self._working_tree[repo_id]:
                    file_contents_from_memory[file_path] = self._working_tree[repo_id][file_path]
                # Second priority: in-memory store (files set via set_file_content test helper)
                elif (repo_id, file_path) in self._files:
                    file_contents_from_memory[file_path] = self._files[(repo_id, file_path)]

        # Capture file contents at commit time - do disk I/O outside the lock
        # to avoid blocking concurrent operations. Only read disk for files not in memory.
        file_contents = dict(file_contents_from_memory)
        for file_path in changed_files:
            if file_path not in file_contents:
                # Fall back to reading from disk (for contract tests that write to disk)
                # This is done outside the lock to avoid blocking
                disk_path = Path(repo_path_str) / file_path
                if disk_path.exists():
                    file_contents[file_path] = disk_path.read_text()
                else:
                    # File doesn't exist - could be a deletion
                    file_contents[file_path] = ""

        # Create commit with locked access (atomic operation)
        with self._lock:
            commit_sha = CommitHash(str(uuid4()))

            self._commits[(repo_id, commit_sha)] = {
                "sha": commit_sha,
                "message": message,
                "author_name": author_name,
                "author_email": author_email,
                "timestamp": self._time_source(),
                "parent": parent_commit,
                "files": changed_files,
                "file_contents": file_contents,  # Store snapshot at commit time
            }

            # Update branch pointer
            self._branches[(repo_id, current_branch)] = commit_sha

            # Emit CommitCreatedEvent
            # Note: source="mock" identifies this as a test/simulation event for traceability
            self._event_emitter.emit(
                CommitCreatedEvent(
                    type="repository.commit_created",
                    timestamp=self._time_source().isoformat(),
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
        branch: str | None = None,
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
            msg = "Repository path is required"
            raise ValidationError(msg)

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            if (repo_id, remote) not in self._remotes:
                msg = "Remote"
                raise ResourceNotFoundError(msg, remote)

            # In-memory simulation, just mark as pushed
            target_branch = branch or self._repositories[repo_id]["current_branch"]

            if (repo_id, target_branch) not in self._branches:
                msg = "Branch"
                raise ResourceNotFoundError(msg, target_branch)

        # Simulate push delay
        await asyncio.sleep(0.01)

    async def pull(
        self,
        repo_path: Path,
        remote: str = "origin",
        branch: str | None = None,
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
            msg = "Repository path is required"
            raise ValidationError(msg)

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            if (repo_id, remote) not in self._remotes:
                msg = "Remote"
                raise ResourceNotFoundError(msg, remote)

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
            msg = "Repository path is required"
            raise ValidationError(msg)

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            if (repo_id, remote) not in self._remotes:
                msg = "Remote"
                raise ResourceNotFoundError(msg, remote)

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
            msg = "Repository path is required"
            raise ValidationError(msg)

        if not base:
            msg = "Base ref is required"
            raise ValidationError(msg)

        if not target:
            msg = "Target ref is required"
            raise ValidationError(msg)

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            # Resolve refs to commit SHAs
            base_commit = self._resolve_ref_to_commit(repo_id, base)
            target_commit = self._resolve_ref_to_commit(repo_id, target)

            # Get files at each commit
            base_files = self._get_files_at_commit(repo_id, base_commit)
            target_files = self._get_files_at_commit(repo_id, target_commit)

            # Collect all file paths that differ
            all_paths = set(base_files.keys()) | set(target_files.keys())
            diff_output = []

            for file_path in sorted(all_paths):
                base_content = base_files.get(file_path, "")
                target_content = target_files.get(file_path, "")

                # Skip if content is identical
                if base_content == target_content:
                    continue

                # Add diff --git header
                diff_output.append(f"diff --git a/{file_path} b/{file_path}\n")

                # Generate unified diff for this file
                base_lines = base_content.splitlines(keepends=True)
                target_lines = target_content.splitlines(keepends=True)

                diff_lines = list(
                    difflib.unified_diff(
                        base_lines,
                        target_lines,
                        fromfile=f"a/{file_path}",
                        tofile=f"b/{file_path}",
                    )
                )

                if diff_lines:
                    diff_output.extend(diff_lines)

            return "".join(diff_output)

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
            msg = "Repository path is required"
            raise ValidationError(msg)

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            current_branch = self._repositories[repo_id]["current_branch"]
            staged = tuple(self._staged_files.get(repo_id, []))
            working = dict(self._working_tree.get(repo_id, {}))
            staged_set = set(staged)

            # Unstaged: in working tree, not staged
            unstaged = tuple(sorted(p for p in working if p not in staged_set))

            # Untracked: in working tree, not in any committed files
            # Use current HEAD to get actual committed files (not just _files test helper data)
            current_commit = self._branches.get((repo_id, current_branch))
            if current_commit:
                committed_files = set(self._get_files_at_commit(repo_id, current_commit).keys())
            else:
                committed_files = set()
            untracked = tuple(sorted(p for p in working if p not in committed_files))

            return RepositoryStatus(
                current_branch=current_branch,
                is_dirty=len(staged) > 0 or len(unstaged) > 0,
                staged_files=staged,  # Return as tuple for immutability
                unstaged_files=unstaged,
                untracked_files=untracked,
                ahead_count=0,
                behind_count=0,
            )

    async def list_branches(
        self,
        repo_path: Path,
        remote: bool = False,
    ) -> list[str]:
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
            msg = "Repository path is required"
            raise ValidationError(msg)

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            branches = [branch for (rid, branch) in self._branches.keys() if rid == repo_id]

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
            msg = "Repository path is required"
            raise ValidationError(msg)

        if not branch:
            msg = "Branch name is required"
            raise ValidationError(msg)

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            if (repo_id, branch) not in self._branches:
                msg = "Branch"
                raise ResourceNotFoundError(msg, branch)

            current_branch = self._repositories[repo_id]["current_branch"]
            current_commit = self._branches[(repo_id, current_branch)]
            merge_commit = self._branches[(repo_id, branch)]

            # Find common ancestor
            ancestor = self._find_common_ancestor(repo_id, current_commit, merge_commit)

            # Compute file trees once - reuse for both conflict detection and merge result
            ancestor_files = self._get_files_at_commit(repo_id, ancestor) if ancestor else {}
            current_files = self._get_files_at_commit(repo_id, current_commit)
            branch_files = self._get_files_at_commit(repo_id, merge_commit)

            # Detect conflicts
            conflicts = []
            all_paths = set(ancestor_files.keys()) | set(current_files.keys()) | set(branch_files.keys())

            for path in all_paths:
                ancestor_content = ancestor_files.get(path)
                current_content = current_files.get(path)
                branch_content = branch_files.get(path)

                # A conflict exists if the same file was modified on both branches
                # relative to the ancestor, AND the changes are different
                current_modified = current_content != ancestor_content
                branch_modified = branch_content != ancestor_content

                if current_modified and branch_modified and current_content != branch_content:
                    conflicts.append(path)

            # If conflicts exist, return failure
            if conflicts:
                return MergeResult(
                    success=False,
                    conflicts=tuple(sorted(conflicts)),
                    merge_commit=None,
                )

            # Create merge commit with combined file snapshot
            new_commit = CommitHash(str(uuid4()))

            # Start with files from current branch
            merged_files = dict(current_files)
            # Add/update with files from merge branch that don't conflict
            for path, content in branch_files.items():
                if path not in merged_files or merged_files[path] == ancestor_files.get(path):
                    # File doesn't exist on current branch, or current branch didn't modify it from ancestor
                    merged_files[path] = content

            self._commits[(repo_id, new_commit)] = {
                "sha": new_commit,
                "message": f"Merge branch '{branch}' into '{current_branch}'",
                "author_name": "System",
                "author_email": "system@codetoreum.local",
                "timestamp": self._time_source(),
                "parent": current_commit,
                "merge_parent": merge_commit,
                "files": list(merged_files.keys()),
                "file_contents": merged_files,
            }

            # Update current branch
            self._branches[(repo_id, current_branch)] = new_commit

            return MergeResult(
                success=True,
                conflicts=(),
                merge_commit=new_commit,
            )

    async def get_file_content(
        self,
        repo_path: Path,
        file_path: str,
        ref: str | None = None,
    ) -> str:
        """
        Get content of a file at a specific ref.

        Args:
            repo_path: Path to the repository
            file_path: Path to the file within the repository
            ref: Optional ref (commit, branch, tag)

        Returns:
            File content as string

        Raises:
            ResourceNotFoundError: If repository or file doesn't exist
            ValidationError: If repo_path or file_path is None/empty
        """
        if not repo_path:
            msg = "Repository path is required"
            raise ValidationError(msg)

        if not file_path:
            msg = "File path is required"
            raise ValidationError(msg)

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            # If ref is specified, resolve it to a commit and get file content at that commit
            if ref is not None:
                commit_sha = self._resolve_ref_to_commit(repo_id, ref)
                files_at_commit = self._get_files_at_commit(repo_id, commit_sha)
                if file_path not in files_at_commit:
                    raise ResourceNotFoundError("File", file_path)
                return files_at_commit[file_path]

            # If no ref specified, use working tree or fall back to in-memory store
            file_key = (repo_id, file_path)

            if file_key not in self._files:
                raise ResourceNotFoundError("File", file_path)

            return self._files[file_key]

    async def get_commit_info(
        self,
        repo_path: Path,
        commit_sha: str,
    ) -> CommitInfo:
        """
        Get information about a commit.

        Args:
            repo_path: Path to the repository
            commit_sha: Commit SHA hash

        Returns:
            CommitInfo with typed commit information

        Raises:
            ResourceNotFoundError: If repository or commit doesn't exist
            ValidationError: If repo_path or commit_sha is None/empty
        """
        if not repo_path:
            msg = "Repository path is required"
            raise ValidationError(msg)

        if not commit_sha:
            msg = "Commit SHA is required"
            raise ValidationError(msg)

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            commit_key = (repo_id, commit_sha)

            if commit_key not in self._commits:
                msg = "Commit"
                raise ResourceNotFoundError(msg, commit_sha)

            commit = self._commits[commit_key]
            parent_shas = (commit["parent"],) if commit.get("parent") else ()
            author = CommitAuthor(
                name=commit["author_name"],
                email=commit["author_email"],
            )
            return CommitInfo(
                sha=commit["sha"],
                author=author,
                message=commit["message"],
                timestamp=commit["timestamp"],
                parent_shas=parent_shas,
            )

    async def get_commit_history(
        self,
        repo_path: Path,
        branch: str | None = None,
        limit: int = 100,
        since: datetime | None = None,
    ) -> list[CommitInfo]:
        """
        Get commit history.

        Args:
            repo_path: Path to the repository
            branch: Optional branch name (defaults to current branch)
            limit: Maximum number of commits to return (default 100)
            since: Optional timestamp to filter commits after

        Returns:
            List of CommitInfo with typed commit information

        Raises:
            ResourceNotFoundError: If repository or branch doesn't exist
            ValidationError: If repo_path is None/empty
        """
        if not repo_path:
            msg = "Repository path is required"
            raise ValidationError(msg)

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            target_branch = branch or self._repositories[repo_id]["current_branch"]

            if (repo_id, target_branch) not in self._branches:
                msg = "Branch"
                raise ResourceNotFoundError(msg, target_branch)

            # Get commits starting from branch HEAD
            commits: list[CommitInfo] = []
            current_commit: str | None = self._branches[(repo_id, target_branch)]

            while current_commit and len(commits) < limit:
                commit_key = (repo_id, current_commit)
                if commit_key in self._commits:
                    commit = self._commits[commit_key]

                    if since and commit["timestamp"] < since:
                        break

                    parent_sha = commit.get("parent")
                    parent_shas: tuple[str, ...] = (str(parent_sha),) if parent_sha else ()
                    author = CommitAuthor(
                        name=commit["author_name"],
                        email=commit["author_email"],
                    )
                    commits.append(
                        CommitInfo(
                            sha=commit["sha"],
                            author=author,
                            message=commit["message"],
                            timestamp=commit["timestamp"],
                            parent_shas=parent_shas,
                        )
                    )

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
            msg = "Repository path is required"
            raise ValidationError(msg)

        if not name or not name.strip():
            msg = "Remote name is required"
            raise ValidationError(msg)

        if not url or not url.strip():
            msg = "Remote URL is required"
            raise ValidationError(msg)

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
            msg = "Repository path is required"
            raise ValidationError(msg)

        if not name:
            msg = "Remote name is required"
            raise ValidationError(msg)

        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            remote_key = (repo_id, name)

            if remote_key not in self._remotes:
                msg = "Remote"
                raise ResourceNotFoundError(msg, name)

            del self._remotes[remote_key]

    # Helper methods

    def _resolve_ref_to_commit(self, repo_id: str, ref: str) -> str:
        """
        Resolve a ref (branch name or commit SHA) to a commit SHA.

        Args:
            repo_id: Repository ID
            ref: Branch name or commit SHA (HEAD resolves to current branch)

        Returns:
            Commit SHA

        Raises:
            ResourceNotFoundError: If ref cannot be resolved
        """
        # Handle HEAD - points to current branch
        if ref == "HEAD":
            current_branch = self._repositories[repo_id]["current_branch"]
            return self._branches[(repo_id, current_branch)]

        # Check if it's a branch
        if (repo_id, ref) in self._branches:
            return self._branches[(repo_id, ref)]

        # Check if it's a commit SHA
        if (repo_id, ref) in self._commits:
            return ref

        msg = "Ref"
        raise ResourceNotFoundError(msg, ref)

    def _get_files_at_commit(self, repo_id: str, commit_sha: str) -> dict[str, str]:
        """
        Get all files and their contents at a specific commit.

        Args:
            repo_id: Repository ID
            commit_sha: Commit SHA

        Returns:
            Dictionary of file paths to content at that commit
        """
        # Collect all files that were changed at this commit or any ancestor
        # We track which files have been seen (in case a file is modified multiple times in history)
        files_at_commit = {}
        seen_files = set()

        # Walk backwards from the given commit
        current_commit: str | None = commit_sha
        visited: set[str] = set()

        while current_commit and current_commit not in visited:
            visited.add(current_commit)

            commit_key = (repo_id, current_commit)
            if commit_key not in self._commits:
                break

            commit = self._commits[commit_key]

            # Use file_contents snapshot from commit (preferred)
            # or fall back to files list for backwards compatibility
            if "file_contents" in commit:
                for file_path, content in commit["file_contents"].items():
                    if file_path not in seen_files:
                        seen_files.add(file_path)
                        files_at_commit[file_path] = content
            elif "files" in commit:
                for file_path in commit["files"]:
                    if file_path not in seen_files:
                        seen_files.add(file_path)
                        file_key = (repo_id, file_path)
                        if file_key in self._files:
                            files_at_commit[file_path] = self._files[file_key]

            # Move to parent commit
            current_commit = commit.get("parent")

        return files_at_commit

    def _find_common_ancestor(self, repo_id: str, commit1: str, commit2: str) -> str | None:
        """
        Find the common ancestor of two commits.

        Args:
            repo_id: Repository ID
            commit1: First commit SHA
            commit2: Second commit SHA

        Returns:
            Common ancestor SHA or None if not found
        """
        # Get ancestry chain for commit1
        ancestors1: set[str] = set()
        current: str | None = commit1
        visited: set[str] = set()

        while current and current not in visited:
            visited.add(current)
            ancestors1.add(current)

            commit_key = (repo_id, current)
            if commit_key not in self._commits:
                break

            current = self._commits[commit_key].get("parent")

        # Walk commit2's ancestry looking for first common ancestor
        current = commit2
        visited.clear()

        while current and current not in visited:
            visited.add(current)

            if current in ancestors1:
                return current

            commit_key = (repo_id, current)
            if commit_key not in self._commits:
                break

            current = self._commits[commit_key].get("parent")

        return None

    def set_working_tree_file(self, repo_path: Path, file_path: str, content: str) -> None:
        """
        Set a file in the working tree (for testing).

        Args:
            repo_path: Path to the repository
            file_path: Path to the file within the repository
            content: File content to set
        """
        repo_id = self._get_repo_id_by_path(repo_path)

        with self._lock:
            if repo_id not in self._working_tree:
                self._working_tree[repo_id] = {}

            self._working_tree[repo_id][file_path] = content

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

        msg = "Repository"
        raise ResourceNotFoundError(msg, path_str)

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
            self._staged_files.clear()
            self._working_tree.clear()

    def get_repository_count(self) -> int:
        """
        Get number of repositories (for testing).

        Returns:
            Number of repositories in storage
        """
        with self._lock:
            return len(self._repositories)
