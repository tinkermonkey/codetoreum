"""Issue Intake Input Port

This module defines the input port interface for handling newly opened GitHub issues
and placing them on boards for workflow orchestration.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class IssueOpenedCommand:
    """Command to handle newly opened GitHub issue."""

    project_id: str
    issue_number: str
    issue_title: str | None = None
    issue_url: str | None = None

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not self.project_id or not self.project_id.strip():
            msg = "project_id must be non-empty"
            raise ValueError(msg)
        if not self.issue_number or not self.issue_number.strip():
            msg = "issue_number must be non-empty"
            raise ValueError(msg)


@dataclass(frozen=True)
class IssueIntakeResult:
    """Result of issue intake operation."""

    success: bool
    work_item_id: str
    message: str
    errors: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not self.work_item_id or not self.work_item_id.strip():
            msg = "work_item_id must be non-empty"
            raise ValueError(msg)
        if not self.message or not self.message.strip():
            msg = "message must be non-empty"
            raise ValueError(msg)


class IIssueIntakePort(ABC):
    """
    Input port for issue intake operations.

    This port accepts issues from external sources (e.g., GitHub webhooks)
    and places them on boards for workflow orchestration. The implementation
    coordinates with the board service to find the appropriate board and
    initial column, then places the item to trigger orchestration.
    """

    @abstractmethod
    async def on_issue_opened(self, command: IssueOpenedCommand) -> IssueIntakeResult:
        """
        Handle newly opened GitHub issue.

        Places the issue in the initial column on the project's board,
        which triggers a WorkItemColumnChangedEvent for orchestration.

        Args:
            command: Command with issue information

        Returns:
            Result with success status and work item ID

        Raises:
            Exception: If project doesn't exist or placement fails
        """
