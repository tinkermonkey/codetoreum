"""IWorkItemBranchTracker output port."""

from abc import ABC, abstractmethod


class IWorkItemBranchTracker(ABC):
    """Tracks the VCS branch associated with each work item during processing."""

    @abstractmethod
    async def set_branch(self, work_item_id: str, branch_name: str) -> None:
        """Record that a work item is being processed on a given branch.

        Args:
            work_item_id: Work item identifier
            branch_name: Branch name where work is being done
        """

    @abstractmethod
    async def get_branch(self, work_item_id: str) -> str | None:
        """Get the branch name for a work item.

        Args:
            work_item_id: Work item identifier

        Returns:
            Branch name if tracked, None otherwise
        """

    @abstractmethod
    async def clear(self, work_item_id: str) -> None:
        """Remove branch tracking for a work item.

        Args:
            work_item_id: Work item identifier
        """
