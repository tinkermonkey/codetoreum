---
name: review-github-version-control-adapter
description: Architectural review of GitHubVersionControlAdapter — bugs found, fixes applied, documentation created
metadata:
  type: project
---

## Findings from review of GitHubVersionControlAdapter (2026-05-17)

### CRITICAL bug fixed
`status()` called `self._repository_adapter.get_status(path)` but `GitRepositoryAdapter`
exposes the method as `status()`, not `get_status()`. This would raise `AttributeError` at
runtime on every call to `IVersionControlService.status()`. Fixed by renaming to
`self._repository_adapter.status(path)` and assigning to `repo_status` to avoid shadowing
the method name.

### MAJOR violation fixed
`get_repository()` contained a direct `subprocess.run(["git", "remote", "get-url", ...])` call.
This bypassed `GitRepositoryAdapter` entirely — violating the delegation contract and
re-introducing raw subprocess execution into the wrapping adapter. The pattern also lost
argument sanitization, timeout management, and error classification that `GitRepositoryAdapter`
provides.

Fix: removed `subprocess` import entirely; replaced with:
1. `self._repository_adapter.status(path)` to validate path exists and get current branch
2. Plain file read of `.git/config` parsed by module-level `_parse_remote_url()` helper
   (reading a static config file is not a subprocess concern)

### MINOR improvement
`commit()` now explicitly returns `str(commit_hash)` rather than returning the `CommitHash`
newtype directly. `CommitHash` is a `str` subclass so it worked, but the explicit cast
makes the port boundary translation clear.

### Design question answered: IRepository vs IVersionControlService distinction
These two ports are correct and serve different consumers:
- `IRepository` (GitRepositoryAdapter): low-level git operations, rich domain types
  (BranchName, CommitHash, RepositoryStatus, CommitInfo, MergeResult). Used by infrastructure
  and anything needing full git semantics.
- `IVersionControlService` (GitHubVersionControlAdapter): higher-level, string-typed
  orchestration contract. Used by WorkflowOrchestrator and WorkspaceRouter. Vendor-agnostic.

### Known gap identified
No `MockVersionControlService` adapter exists for simulation. Simulation scenarios use
`InMemoryRepositoryAdapter` (IRepository) directly. If application services call
`IVersionControlService` in simulation, a `MockVersionControlAdapter` is needed in
`src/codetoreum/adapters/testing/`.

### Documentation created
`documentation/architecture/adapters/production/github-version-control-adapter.md`

**Why:** Port was implemented but had no documentation, no design review, and the two bugs above.

**How to apply:** When reviewing delegation adapters (adapters that wrap other adapters),
check: (1) all method names match the wrapped adapter's actual API, (2) no subprocess calls
in the wrapper body, (3) return type newtypes are explicitly cast at the port boundary.
