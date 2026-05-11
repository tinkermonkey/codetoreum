"""In-memory work item branch tracker for testing and simulation."""

from codetoreum.ports.output.work_item_branch_tracker import IWorkItemBranchTracker


class InMemoryWorkItemBranchTracker(IWorkItemBranchTracker):
    """In-memory implementation of IWorkItemBranchTracker for testing."""

    def __init__(self) -> None:
        """Initialize the in-memory work item branch tracker."""
        self._branches: dict[str, str] = {}

    async def set_branch(self, work_item_id: str, branch_name: str) -> None:
        """Record that a work item is being processed on a given branch.

        Args: work_item_id: Work item identifier
            branch_name: Branch name where work is being done
        """
        self._branches[work_item_id] = branch_name

    async def get_branch(self, work_item_id: str) -> str | None:
        """Get the branch name for a work item.

        Args: work_item_id: Work item identifier

        Returns: Branch name if tracked, None otherwise
        """
        return self._branches.get(work_item_id)

    async def clear(self, work_item_id: str) -> None:
        """Remove branch tracking for a work item.

        Args: work_item_id: Work item identifier
        """
        self._branches.pop(work_item_id, None)
