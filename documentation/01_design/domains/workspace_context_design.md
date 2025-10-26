# Workspace Context Domain Design

## Overview

Workspace Context is a value object/service managing workspace routing and preparation for different workspace types (issues, discussions, hybrid).

## Domain Model

```python
from dataclasses import dataclass
from typing import Optional, Dict, Any
from enum import Enum

class WorkspaceType(Enum):
    """Type of workspace for execution."""
    ISSUE = "issue"  # Feature branches + PRs
    DISCUSSION = "discussion"  # Discussion comments only
    HYBRID = "hybrid"  # Can use both

@dataclass
class WorkspaceContext:
    """
    Workspace Context value object.

    Encapsulates workspace configuration and routing logic.
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

    @classmethod
    def for_issue(cls,
                  project_id: str,
                  work_item_id: str,
                  branch_name: str,
                  create_pr: bool = True) -> 'WorkspaceContext':
        """Create workspace context for issue-based work."""
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
    def for_discussion(cls,
                      project_id: str,
                      work_item_id: str,
                      discussion_id: str) -> 'WorkspaceContext':
        """Create workspace context for discussion-based work."""
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
    def for_hybrid(cls,
                   project_id: str,
                   work_item_id: str,
                   branch_name: str,
                   discussion_id: str) -> 'WorkspaceContext':
        """Create workspace context for hybrid work."""
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

    def is_issue_workspace(self) -> bool:
        """Check if this is issue-based workspace."""
        return self.workspace_type in [WorkspaceType.ISSUE, WorkspaceType.HYBRID]

    def is_discussion_workspace(self) -> bool:
        """Check if this is discussion-based workspace."""
        return self.workspace_type in [WorkspaceType.DISCUSSION, WorkspaceType.HYBRID]

    def can_make_code_changes(self) -> bool:
        """Check if code changes are allowed."""
        return self.allow_code_changes

    def should_create_branch(self) -> bool:
        """Check if branch should be created."""
        return self.workspace_type != WorkspaceType.DISCUSSION

    def should_post_to_discussion(self) -> bool:
        """Check if results should be posted to discussion."""
        return self.discussion_id is not None
```

## Domain Service: WorkspaceRouter

```python
class WorkspaceRouter:
    """
    Domain service for routing work to appropriate workspace.

    Determines workspace type based on work item metadata.
    """

    def route_workspace(self,
                       work_item: 'WorkItem',
                       project: 'ProjectContext') -> WorkspaceContext:
        """
        Determine workspace type for work item.

        Business rules:
        - Issues with 'discussion' label → Discussion workspace
        - Issues with 'research' label → Discussion workspace
        - Issues with code-related labels → Issue workspace
        - Default → Issue workspace
        """
        discussion_labels = {"discussion", "research", "question"}

        if any(label in discussion_labels for label in work_item.labels):
            # Discussion workspace
            return WorkspaceContext.for_discussion(
                project_id=project.id,
                work_item_id=work_item.id,
                discussion_id=work_item.external_id
            )
        else:
            # Issue workspace
            branch_name = self._generate_branch_name(work_item, project)
            return WorkspaceContext.for_issue(
                project_id=project.id,
                work_item_id=work_item.id,
                branch_name=branch_name
            )

    def _generate_branch_name(self,
                             work_item: 'WorkItem',
                             project: 'ProjectContext') -> str:
        """Generate branch name following project conventions."""
        # Example: feature/issue-123-add-login
        issue_number = work_item.external_id
        title_slug = work_item.title.lower().replace(" ", "-")[:40]
        return f"{project.branch_prefix}issue-{issue_number}-{title_slug}"
```

## Workspace Preparation

```python
class WorkspacePreparationService:
    """Service for preparing workspace before agent execution."""

    async def prepare_workspace(self,
                               context: WorkspaceContext,
                               repository: 'IRepository') -> None:
        """
        Prepare workspace for execution.

        Issue workspace:
        - Create/checkout feature branch
        - Ensure branch is up to date with base branch

        Discussion workspace:
        - No branch operations needed
        """
        if context.should_create_branch():
            # Create feature branch
            await repository.create_branch(
                branch_name=context.branch_name,
                base_branch="main"
            )
            await repository.checkout(context.branch_name)

    async def finalize_workspace(self,
                                context: WorkspaceContext,
                                result: 'ExecutionResult',
                                repository: 'IRepository',
                                ticket_system: 'ITicketSystem') -> None:
        """
        Finalize workspace after execution.

        Issue workspace:
        - Commit changes
        - Push branch
        - Create PR

        Discussion workspace:
        - Post result to discussion
        """
        if context.is_issue_workspace() and context.create_commits:
            # Commit and push
            await repository.commit(
                message=f"Complete work for {context.work_item_id}",
                files=result.modified_files
            )
            await repository.push(context.branch_name)

            if context.create_pr:
                await ticket_system.create_pull_request(
                    branch=context.branch_name,
                    title=f"Fix for {context.work_item_id}",
                    body=result.output
                )

        if context.should_post_to_discussion():
            # Post to discussion
            await ticket_system.post_comment(
                discussion_id=context.discussion_id,
                comment=result.output
            )
```

## Business Rules

1. Discussion workspaces cannot make code changes
2. Issue workspaces create feature branches
3. Hybrid workspaces support both modes
4. Branch names follow project conventions
5. PR creation controlled by workspace config

## Testing

```python
def test_workspace_routing():
    work_item = WorkItem.create(
        title="Research API design",
        description="Explore options",
        project_id="proj-1",
        labels=["research"]
    )

    router = WorkspaceRouter()
    context = router.route_workspace(work_item, project)

    assert context.workspace_type == WorkspaceType.DISCUSSION
    assert not context.can_make_code_changes()

def test_issue_workspace():
    work_item = WorkItem.create(
        title="Add login feature",
        description="Implement login",
        project_id="proj-1",
        labels=["feature"]
    )

    router = WorkspaceRouter()
    context = router.route_workspace(work_item, project)

    assert context.workspace_type == WorkspaceType.ISSUE
    assert context.can_make_code_changes()
    assert context.branch_name.startswith("feature/")
```

## Migration from Legacy

| Legacy | Domain |
|--------|--------|
| workspace routing logic | WorkspaceRouter service |
| branch creation | WorkspacePreparationService |
| context dict | WorkspaceContext value object |

## References

- **Work Item**: `work_item_design.md`
- **Project Context**: `project_context_design.md`
- **Execution Result**: `execution_result_design.md`
