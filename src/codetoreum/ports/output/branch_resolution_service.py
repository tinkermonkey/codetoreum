"""Branch resolution service port interface.

This interface defines the contract for resolving branches for work items.
It separates the decision-making concern (which branch to use) from low-level
git operations already handled by IVersionControlService.

The service determines whether to create a new branch or reuse an existing one
based on issue metadata, using various resolution strategies (exact match,
parent issue, sibling, fuzzy match, or create new).
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from codetoreum.domain.value_objects import BranchResolution

from .event_emitter import IEventEmitter


class IBranchResolutionService(IEventEmitter, ABC):
    """Branch resolution service with event emission capability.

    Provides vendor-agnostic abstraction for determining which branch to use
    for a work item. This service makes strategic decisions about branch
    creation and reuse, emitting events to track resolution decisions.

    The service is used by the orchestrator to:
    1. Analyze work item metadata (issue title, description, relationships)
    2. Query existing branches for matches
    3. Decide whether to create new or reuse existing branch
    4. Return resolution decision with confidence and reasoning

    Events emitted:
        - 'branch.resolved' → BranchResolvedEvent
                             When a branch resolution decision is made (primary audit event)
        - 'branch.reused' → BranchReusedEvent
                             When an existing branch is selected for reuse
        - 'branch.created' → BranchResolutionCreatedEvent
                             When a new branch is created

    Example:
        # Resolve branch for a work item
        resolution = await service.resolve_branch(
            project_id="proj-123",
            issue_id="issue-456",
            issue_metadata={
                "title": "Fix authentication bug",
                "description": "Users cannot login via OAuth",
                "labels": ["bug", "high-priority"],
                "parent_issue": "issue-100"
            },
            repo_path="/workspace/my-repo"
        )

        # Resolution includes action and confidence
        if resolution.action == "reuse":
            print(f"Reuse existing: {resolution.branch_name}")
        else:
            print(f"Create new: {resolution.branch_name}")
    """

    @abstractmethod
    async def resolve_branch(
        self,
        project_id: str,
        issue_id: str,
        issue_metadata: Mapping[str, Any],
        repo_path: str,
    ) -> BranchResolution:
        """Resolve branch for a work item.

        Analyzes issue metadata and determines which branch to use, whether
        to create a new branch or reuse an existing one.

        Args:
            project_id: Project identifier
            issue_id: Issue/work item identifier
            issue_metadata: Immutable mapping of issue details (title,
                           description, labels, relationships, etc.)
                           The mapping must not be modified during resolution.
            repo_path: Local repository path (required for querying branches)

        Returns:
            BranchResolution: Resolution decision including action (create/reuse),
                             branch name, confidence level, and reasoning

        Raises:
            ExternalServiceError: If ticket system, version control, or other
                                external service communication fails

        Events:
            Emits events as documented in class docstring: BranchResolvedEvent
            (always), plus BranchReusedEvent or BranchResolutionCreatedEvent
            depending on the resolution action (reuse vs. create)
        """
