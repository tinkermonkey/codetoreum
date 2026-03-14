"""In-memory active workflow run registry for testing and simulation."""

from codetoreum.ports.output.active_workflow_run_registry import (
    ActiveRunInfo,
    IActiveWorkflowRunRegistry,
)


class InMemoryActiveWorkflowRunRegistry(IActiveWorkflowRunRegistry):
    """In-memory implementation of IActiveWorkflowRunRegistry for testing."""

    def __init__(self) -> None:
        """Initialize the in-memory active workflow run registry."""
        self._runs: dict[str, ActiveRunInfo] = {}

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
        self._runs[work_item_id] = ActiveRunInfo(
            work_item_id=work_item_id,
            run_id=run_id,
            stage_name=stage_name,
            project_id=project_id,
        )

    async def get_active_run(self, work_item_id: str) -> ActiveRunInfo | None:
        """Get active run info for a work item.

        Args:
            work_item_id: Work item identifier

        Returns:
            ActiveRunInfo if an active run exists, None otherwise
        """
        return self._runs.get(work_item_id)

    async def clear_run(self, work_item_id: str) -> None:
        """Remove active run entry for a work item.

        Args:
            work_item_id: Work item identifier
        """
        self._runs.pop(work_item_id, None)
