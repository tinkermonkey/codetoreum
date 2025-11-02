"""Workspace Context value object."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class WorkspaceType(Enum):
    """Type of workspace for execution."""
    ISSUE = "issue"  # Feature branches + PRs
    DISCUSSION = "discussion"  # Discussion comments only
    HYBRID = "hybrid"  # Can use both


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
    branch_name: Optional[str]
    create_pr: bool

    # Discussion workspace
    discussion_id: Optional[str]

    # Configuration
    allow_code_changes: bool
    create_commits: bool
    post_comments: bool

    def __post_init__(self):
        """Validate invariants after initialization."""
        # Validate workspace type specific requirements
        if self.workspace_type in [WorkspaceType.ISSUE, WorkspaceType.HYBRID]:
            if not self.branch_name:
                raise ValueError(
                    f"branch_name is required for {self.workspace_type.value} workspace"
                )

        if self.workspace_type in [WorkspaceType.DISCUSSION, WorkspaceType.HYBRID]:
            if not self.discussion_id:
                raise ValueError(
                    f"discussion_id is required for {self.workspace_type.value} workspace"
                )

        # Validate project and work item IDs
        if not self.project_id or not self.project_id.strip():
            raise ValueError("project_id cannot be empty")

        if not self.work_item_id or not self.work_item_id.strip():
            raise ValueError("work_item_id cannot be empty")

    @classmethod
    def for_issue(
        cls,
        project_id: str,
        work_item_id: str,
        branch_name: str,
        create_pr: bool = True
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
            post_comments=True
        )

    @classmethod
    def for_discussion(
        cls,
        project_id: str,
        work_item_id: str,
        discussion_id: str
    ) -> "WorkspaceContext":
        """
        Create workspace context for discussion-based work.

        Discussion workspaces only post comments, do not create
        branches or make code changes.

        Args:
            project_id: Project identifier
            work_item_id: Work item identifier
            discussion_id: Discussion/issue identifier in external system

        Returns:
            WorkspaceContext configured for discussion-based work
        """
        return cls(
            workspace_type=WorkspaceType.DISCUSSION,
            project_id=project_id,
            work_item_id=work_item_id,
            branch_name=None,
            create_pr=False,
            discussion_id=discussion_id,
            allow_code_changes=False,
            create_commits=False,
            post_comments=True
        )

    @classmethod
    def for_hybrid(
        cls,
        project_id: str,
        work_item_id: str,
        branch_name: str,
        discussion_id: str
    ) -> "WorkspaceContext":
        """
        Create workspace context for hybrid work.

        Hybrid workspaces can make code changes AND post to discussions.

        Args:
            project_id: Project identifier
            work_item_id: Work item identifier
            branch_name: Branch name to create/use
            discussion_id: Discussion/issue identifier in external system

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
            post_comments=True
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
        Check if this is discussion-based workspace.

        Returns:
            True if workspace supports discussion operations (comments)
        """
        return self.workspace_type in [WorkspaceType.DISCUSSION, WorkspaceType.HYBRID]

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
        return self.workspace_type != WorkspaceType.DISCUSSION

    def should_post_to_discussion(self) -> bool:
        """
        Check if results should be posted to discussion.

        Returns:
            True if discussion comments should be posted
        """
        return self.discussion_id is not None
