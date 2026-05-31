"""Workspace Context value object."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class WorkspaceType(Enum):
    """Type of workspace for execution."""

    ISSUE = "issue"  # Feature branches + PRs
    HYBRID = "hybrid"  # Feature branches + PRs + discussion posting


@dataclass(frozen=True)
class WorkspaceContext:
    """
    Workspace Context value object.

    Encapsulates workspace configuration and routing logic.
    This is an immutable value object that determines how agent
    execution results are handled (branch creation, PR creation,
    discussion comments, etc.).

    Immutability is enforced via frozen=True dataclass parameter.
    """

    workspace_type: WorkspaceType
    project_id: str
    work_item_id: str

    # Issue workspace
    branch_name: str | None
    create_pr: bool

    # Discussion workspace
    discussion_id: str | None

    # Configuration
    allow_code_changes: bool
    create_commits: bool
    post_comments: bool

    # Host-side workspace path (D6). Optional at construction time because
    # WorkspaceRouter.route_workspace produces a logical context before the
    # repository is cloned; the orchestrator populates this via
    # WorkspaceContext.with_workspace_path() once the path is known so the
    # coding-agent adapter can mount/cwd to it. ICodingAgent strategies
    # raise ValueError if this is None at execute time.
    workspace_path: Path | None = None

    def __post_init__(self) -> None:
        """Validate invariants after initialization."""
        # Validate workspace type specific requirements
        if self.workspace_type in [WorkspaceType.ISSUE, WorkspaceType.HYBRID]:
            if not self.branch_name:
                msg = f"branch_name is required for {self.workspace_type.value} workspace"
                raise ValueError(msg)

        if self.workspace_type == WorkspaceType.HYBRID:
            if not self.discussion_id:
                msg = "discussion_id is required for hybrid workspace"
                raise ValueError(msg)

        # Validate project and work item IDs
        if not self.project_id or not self.project_id.strip():
            msg = "project_id cannot be empty"
            raise ValueError(msg)

        if not self.work_item_id or not self.work_item_id.strip():
            msg = "work_item_id cannot be empty"
            raise ValueError(msg)

    @classmethod
    def for_issue(
        cls,
        project_id: str,
        work_item_id: str,
        branch_name: str,
        create_pr: bool = True,
        workspace_path: Path | None = None,
    ) -> "WorkspaceContext":
        """
        Create workspace context for issue-based work.

        Issue workspaces create feature branches and optionally
        create pull requests.

        Args:
            project_id: Project identifier
            work_item_id: Work item identifier
            branch_name: Branch name to create/use
            create_pr: Whether to create pull request (default: True)
            workspace_path: Optional host-side workspace path. The
                orchestrator typically populates this via
                ``with_workspace_path()`` after the repository is cloned.

        Returns:
            WorkspaceContext configured for issue-based work
        """
        return cls(
            workspace_type=WorkspaceType.ISSUE,
            project_id=project_id,
            work_item_id=work_item_id,
            branch_name=branch_name,
            create_pr=create_pr,
            discussion_id=None,
            allow_code_changes=True,
            create_commits=True,
            post_comments=True,
            workspace_path=workspace_path,
        )

    @classmethod
    def for_hybrid(
        cls,
        project_id: str,
        work_item_id: str,
        branch_name: str,
        discussion_id: str,
        workspace_path: Path | None = None,
    ) -> "WorkspaceContext":
        """
        Create workspace context for hybrid work.

        Hybrid workspaces can make code changes AND post to discussions.

        Args:
            project_id: Project identifier
            work_item_id: Work item identifier
            branch_name: Branch name to create/use
            discussion_id: Discussion/issue identifier in external system
            workspace_path: Optional host-side workspace path. The
                orchestrator typically populates this via
                ``with_workspace_path()`` after the repository is cloned.

        Returns:
            WorkspaceContext configured for hybrid work
        """
        return cls(
            workspace_type=WorkspaceType.HYBRID,
            project_id=project_id,
            work_item_id=work_item_id,
            branch_name=branch_name,
            create_pr=True,
            discussion_id=discussion_id,
            allow_code_changes=True,
            create_commits=True,
            post_comments=True,
            workspace_path=workspace_path,
        )

    def with_workspace_path(self, workspace_path: Path) -> "WorkspaceContext":
        """Return a copy of this context with the workspace_path populated.

        WorkspaceContext is frozen, so callers cannot mutate the field
        directly. This helper is the canonical way for the orchestrator to
        attach the cloned repository path before handing the context to the
        coding-agent adapter.

        Args:
            workspace_path: Host-side absolute path to the cloned repo
                that the agent should mount (containerised mode) or run
                in (host mode).

        Returns:
            A new WorkspaceContext instance with ``workspace_path`` set.
        """
        return WorkspaceContext(
            workspace_type=self.workspace_type,
            project_id=self.project_id,
            work_item_id=self.work_item_id,
            branch_name=self.branch_name,
            create_pr=self.create_pr,
            discussion_id=self.discussion_id,
            allow_code_changes=self.allow_code_changes,
            create_commits=self.create_commits,
            post_comments=self.post_comments,
            workspace_path=workspace_path,
        )

    def with_branch_name(self, branch_name: str) -> "WorkspaceContext":
        """Return a copy of this context with the branch_name replaced.

        ``WorkspaceRouter.route_workspace`` produces a placeholder branch
        name derived from the work item title; the real branch is decided
        inside ``prepare_workspace`` once the resolution service / git
        state is available. This helper lets the router publish the
        resolved name back into the immutable context so downstream
        consumers (``ExecutionContextBuilder``, the post-execution push
        in ``ExecutionService._commit_workspace``) see the branch that
        was actually checked out — instead of the original placeholder.

        Args:
            branch_name: The resolved branch name that the workspace was
                checked out onto.

        Returns:
            A new WorkspaceContext instance with ``branch_name`` set.
        """
        return WorkspaceContext(
            workspace_type=self.workspace_type,
            project_id=self.project_id,
            work_item_id=self.work_item_id,
            branch_name=branch_name,
            create_pr=self.create_pr,
            discussion_id=self.discussion_id,
            allow_code_changes=self.allow_code_changes,
            create_commits=self.create_commits,
            post_comments=self.post_comments,
            workspace_path=self.workspace_path,
        )

    # Query methods
    def is_issue_workspace(self) -> bool:
        """
        Check if this is issue-based workspace.

        Returns:
            True if workspace supports issue operations (branch, PR)
        """
        return self.workspace_type in [WorkspaceType.ISSUE, WorkspaceType.HYBRID]

    def is_discussion_workspace(self) -> bool:
        """
        Check if this workspace posts to discussion threads.

        Returns:
            True if workspace supports discussion operations (comments)
        """
        return self.workspace_type == WorkspaceType.HYBRID

    def can_make_code_changes(self) -> bool:
        """
        Check if code changes are allowed.

        Returns:
            True if code changes are allowed
        """
        return self.allow_code_changes

    def should_create_branch(self) -> bool:
        """
        Check if branch should be created.

        Returns:
            True if branch creation is needed
        """
        return self.branch_name is not None

    def should_post_to_discussion(self) -> bool:
        """
        Check if results should be posted to discussion.

        Returns:
            True if discussion comments should be posted
        """
        return self.discussion_id is not None
