# IRepository Output Port Design

## Overview

The `IRepository` port provides an abstraction for source code repository management, primarily Git operations. The orchestrator uses this port to manage project repositories, branches, and commits.

## Port Interface

```python
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime

class IRepository(ABC):
    """Interface for source code repository operations."""

    @abstractmethod
    async def clone(self,
                    url: str,
                    destination: Path,
                    branch: Optional[str] = None) -> None:
        """Clone a repository."""
        pass

    @abstractmethod
    async def checkout(self,
                      repo_path: Path,
                      branch: str,
                      create: bool = False) -> None:
        """Checkout a branch."""
        pass

    @abstractmethod
    async def create_branch(self,
                           repo_path: Path,
                           branch_name: str,
                           from_branch: Optional[str] = None) -> None:
        """Create a new branch."""
        pass

    @abstractmethod
    async def commit(self,
                    repo_path: Path,
                    message: str,
                    author_name: str,
                    author_email: str,
                    files: Optional[List[str]] = None) -> str:
        """Create a commit. Returns commit SHA."""
        pass

    @abstractmethod
    async def push(self,
                   repo_path: Path,
                   remote: str = "origin",
                   branch: Optional[str] = None,
                   force: bool = False) -> None:
        """Push commits to remote."""
        pass

    @abstractmethod
    async def pull(self,
                   repo_path: Path,
                   remote: str = "origin",
                   branch: Optional[str] = None) -> None:
        """Pull commits from remote."""
        pass

    @abstractmethod
    async def diff(self,
                   repo_path: Path,
                   base: str,
                   target: str) -> str:
        """Get diff between two refs."""
        pass

    @abstractmethod
    async def status(self, repo_path: Path) -> RepositoryStatus:
        """Get repository status."""
        pass

    @abstractmethod
    async def list_branches(self,
                           repo_path: Path,
                           remote: bool = False) -> List[str]:
        """List branches."""
        pass

    @abstractmethod
    async def merge(self,
                    repo_path: Path,
                    branch: str,
                    strategy: str = "merge") -> MergeResult:
        """Merge a branch."""
        pass
```

## Data Models

```python
@dataclass
class RepositoryStatus:
    """Repository status information."""
    current_branch: str
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
    merge_commit: Optional[str]
```

## Adapter Implementations

### Git Adapter

```python
class GitRepositoryAdapter(IRepository):
    """Git CLI implementation."""

    async def clone(self,
                    url: str,
                    destination: Path,
                    branch: Optional[str] = None) -> None:
        """Clone using git CLI."""
        cmd = ["git", "clone", url, str(destination)]
        if branch:
            cmd.extend(["-b", branch])

        result = await self._run_command(cmd)
        if result.returncode != 0:
            raise RepositoryError(f"Clone failed: {result.stderr}")

    async def commit(self,
                    repo_path: Path,
                    message: str,
                    author_name: str,
                    author_email: str,
                    files: Optional[List[str]] = None) -> str:
        """Create a commit."""
        # Stage files
        if files:
            await self._run_command(
                ["git", "add"] + files,
                cwd=repo_path
            )
        else:
            await self._run_command(
                ["git", "add", "-A"],
                cwd=repo_path
            )

        # Commit
        result = await self._run_command(
            ["git", "commit", "-m", message,
             f"--author={author_name} <{author_email}>"],
            cwd=repo_path
        )

        # Get commit SHA
        sha_result = await self._run_command(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path
        )
        return sha_result.stdout.strip()
```

### In-Memory Adapter (Testing)

```python
class InMemoryRepositoryAdapter(IRepository):
    """Mock repository for testing."""

    def __init__(self):
        self.repositories: Dict[str, Dict[str, Any]] = {}
        self.operations: List[str] = []

    async def clone(self,
                    url: str,
                    destination: Path,
                    branch: Optional[str] = None) -> None:
        """Simulate clone."""
        self.operations.append(f"clone:{url}")
        self.repositories[str(destination)] = {
            'url': url,
            'current_branch': branch or 'main',
            'commits': [],
            'branches': [branch or 'main']
        }
```

## Integration Points

### Used By
- Workflow Orchestrator
- Workspace Context (IssuesWorkspaceContext)
- Repository Manager (application service)

### Dependencies
- None (standalone port)

## Implementation Notes

1. **Credentials**: Managed externally (SSH keys, tokens)
2. **Concurrency**: Handle concurrent access to same repository
3. **Error Handling**: Parse git errors for meaningful messages
4. **Performance**: Use shallow clones when full history not needed
5. **Safety**: Validate branch names and commit messages
