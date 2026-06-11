"""Issue Intake Service

This application service handles placing newly opened issues on boards
for workflow orchestration. It coordinates board lookup, initial column
resolution, and item placement.
"""

import logging

from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.ports.exceptions import PortError
from codetoreum.ports.input.issue_intake import (
    IIssueIntakePort,
    IssueIntakeResult,
    IssueOpenedCommand,
)
from codetoreum.ports.input.work_item_query import IWorkItemQueryPort
from codetoreum.ports.output.board_service import IBoardService, MovedByType
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService

logger = logging.getLogger(__name__)


class IssueIntakeService(IIssueIntakePort):
    """
    Application service for issue intake.

    Coordinates with board service and workflow config service to:
    1. Find the board for a project
    2. Resolve the initial column from the workflow template
    3. Place the issue on the board (triggers WorkItemColumnChangedEvent)
    """

    def __init__(
        self,
        board_service: IBoardService,
        workflow_config_service: IWorkflowConfigService,
        work_item_service: IWorkItemQueryPort,
    ):
        """
        Initialize issue intake service.

        Args:
            board_service: Board service for placing items
            workflow_config_service: Workflow config service for resolving columns
            work_item_service: Query port to resolve an issue number to its
                canonical work item UUID (the identifier the board port expects)
        """
        self.board_service = board_service
        self.workflow_config = workflow_config_service
        self._work_item_service = work_item_service

    async def on_issue_opened(self, command: IssueOpenedCommand) -> IssueIntakeResult:
        """
        Handle newly opened GitHub issue.

        Places the issue in the initial column on the project's board,
        which triggers a WorkItemColumnChangedEvent for orchestration.

        Args:
            command: Command with issue information

        Returns:
            Result with success status and work item ID
        """
        issue_number = command.issue_number
        project_id = command.project_id

        try:
            # Get all boards to find the board for this project
            all_boards = await self.board_service.get_all_boards()
            project_boards = [b for b in all_boards if b.project_id == project_id]

            if not project_boards:
                message = f"No boards configured for project {project_id}"
                logger.warning(message)
                return IssueIntakeResult(
                    success=False,
                    work_item_id=issue_number,
                    message=message,
                    errors=(message,),
                )

            # Use the first board (assuming project has at least one)
            board = project_boards[0]

            # Get workflow template to find the initial column
            template = await self.workflow_config.get_board_workflow_template(board.id)

            if not template:
                message = f"No workflow template configured for board {board.id}"
                logger.warning(message)
                return IssueIntakeResult(
                    success=False,
                    work_item_id=issue_number,
                    message=message,
                    errors=(message,),
                )

            # Find the initial column (position 0)
            initial_column = next((c for c in template.columns if c.position == 0), None)

            if not initial_column:
                message = f"No initial column (position 0) found in template for board {board.id}"
                logger.warning(message)
                return IssueIntakeResult(
                    success=False,
                    work_item_id=issue_number,
                    message=message,
                    errors=(message,),
                )

            # The board port speaks canonical work item UUIDs, not issue
            # numbers. Resolve the UUID for this freshly opened issue.
            work_item = await self._work_item_service.find_by_external_id(str(issue_number))
            if work_item is None:
                message = (
                    f"No Codetoreum work item registered for issue {issue_number} "
                    f"in project {project_id}; cannot place it on the board"
                )
                logger.warning(message)
                return IssueIntakeResult(
                    success=False,
                    work_item_id=issue_number,
                    message=message,
                    errors=(message,),
                )

            # Place the issue in the initial column
            # This triggers a WorkItemColumnChangedEvent with from_column=None
            await self.board_service.add_item_to_column(
                work_item_id=work_item.id,
                target_column=initial_column.name,
                moved_by=MovedByType.GITHUB_WEBHOOK,
            )

            logger.info(
                "Placed newly opened issue %s in column %s on board %s",
                issue_number,
                initial_column.name,
                board.id,
            )

            return IssueIntakeResult(
                success=True,
                work_item_id=issue_number,
                message=f"Issue {issue_number} placed in column {initial_column.name}",
            )

        except PortError as e:
            message = f"Error handling opened issue {issue_number} for project {project_id}: {e}"
            logger.error(
                message,
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
            )
            return IssueIntakeResult(
                success=False,
                work_item_id=issue_number,
                message=message,
                errors=(str(e),),
            )
