"""
Protocol types for event bus adapter integration.

These protocols define the interfaces that adapters must implement
to work with the event bus wiring system.
"""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol


class EventEmitter(Protocol):
    """Protocol for objects that emit events to the event bus."""

    def on(self, event_type: str, handler: Callable[[Any], Awaitable[None]]) -> None:
        """Register an event handler for a specific event type."""
        ...


class IBoardService(EventEmitter, Protocol):
    """Protocol for board service implementations."""

    async def move_item_to_column(self, work_item_id: str, column_name: str, moved_by: str) -> None:
        """Move a work item to a specific column."""
        ...

    async def get_item_position(self, work_item_id: str):
        """Get the column and position of a work item."""
        ...


class IDiscussionAdapter(EventEmitter, Protocol):
    """Protocol for discussion adapter implementations."""

    def start_monitoring(self, work_item_id: str, config: Any) -> None:
        """Start monitoring discussions for a work item."""
        ...

    def stop_monitoring(self, work_item_id: str) -> None:
        """Stop monitoring discussions for a work item."""
        ...


class IPipelineLockService(EventEmitter, Protocol):
    """Protocol for pipeline lock service implementations."""

    async def try_acquire_lock(
        self, project_id: str, board_id: str, work_item_id: str
    ) -> tuple[bool, str]:
        """Try to acquire a pipeline lock for a work item."""
        ...

    async def release_lock(
        self, project_id: str, board_id: str, work_item_id: str
    ) -> None:
        """Release a pipeline lock for a work item."""
        ...


class ICodeReviewService(EventEmitter, Protocol):
    """Protocol for code review service implementations."""

    async def get_review_status(self, work_item_id: str) -> str:
        """Get the current review status of a work item."""
        ...
