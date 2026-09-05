"""IActiveWorkflowRunRegistry output port."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ActiveRunInfo:
    """Information about an active workflow run.

    Value object at the port boundary. All fields are validated at
    construction to ensure contract integrity. Frozen to prevent
    accidental mutation after creation.
    """

    work_item_id: str
    run_id: str
    stage_name: str
    project_id: str
    board_id: str
    started_at: str

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not self.work_item_id:
            msg = "work_item_id must be non-empty"
            raise ValueError(msg)
        if not self.run_id:
            msg = "run_id must be non-empty"
            raise ValueError(msg)
        if not self.stage_name:
            msg = "stage_name must be non-empty"
            raise ValueError(msg)
        if not self.project_id:
            msg = "project_id must be non-empty"
            raise ValueError(msg)
        if not self.board_id:
            msg = "board_id must be non-empty"
            raise ValueError(msg)
        if not self.started_at:
            msg = "started_at must be non-empty"
            raise ValueError(msg)


class IActiveWorkflowRunRegistry(ABC):
    """Registry for tracking active workflow runs per work item."""

    @abstractmethod
    async def set_active_run(
        self,
        work_item_id: str,
        run_id: str,
        stage_name: str,
        project_id: str,
        board_id: str,
        started_at: str,
    ) -> None:
        """Register an active workflow run for a work item.

        Args:
            work_item_id: Work item being processed
            run_id: Workflow run identifier
            stage_name: Current stage name
            project_id: Project identifier
            board_id: Board identifier
            started_at: ISO timestamp when the workflow run started
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

    @abstractmethod
    async def get_all_runs(self) -> list[tuple[str, "ActiveRunInfo"]]:
        """Get all active workflow runs.

        Returns:
            List of tuples (work_item_id, ActiveRunInfo) for all active runs
        """
