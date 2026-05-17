"""Issue Intake Input Port

This module defines the input port interface for handling newly opened GitHub issues
and placing them on boards for workflow orchestration.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class IssueOpenedCommand:
    """Command to handle newly opened GitHub issue"""

    project_id: str
    issue_number: str
    issue_title: str | None = None
    issue_url: str | None = None


@dataclass
class IssueIntakeResult:
    """Result of issue intake operation"""

    success: bool
    work_item_id: str
    message: str
    errors: list[str] | None = None


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
