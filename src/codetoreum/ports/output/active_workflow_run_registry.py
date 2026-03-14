"""IActiveWorkflowRunRegistry output port."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ActiveRunInfo:
    """Information about an active workflow run."""

    work_item_id: str
    run_id: str
    stage_name: str
    project_id: str


class IActiveWorkflowRunRegistry(ABC):
    """Registry for tracking active workflow runs per work item."""

    @abstractmethod
    async def set_active_run(
        self,
        work_item_id: str,
        run_id: str,
        stage_name: str,
        project_id: str,
    ) -> None:
        """Register an active workflow run for a work item.

        Args:
            work_item_id: Work item being processed
            run_id: Workflow run identifier
            stage_name: Current stage name
            project_id: Project identifier
        """

    @abstractmethod
    async def get_active_run(self, work_item_id: str) -> ActiveRunInfo | None:
        """Get active run info for a work item.

        Args:
            work_item_id: Work item identifier

        Returns:
            ActiveRunInfo if an active run exists, None otherwise
        """

    @abstractmethod
    async def clear_run(self, work_item_id: str) -> None:
        """Remove active run entry for a work item.

        Args:
            work_item_id: Work item identifier
        """
