"""Board polling service for detecting column changes without webhooks."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, Optional, Set

from codetoreum.domain.events import WorkItemColumnChanged
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.exceptions import (
    AuthenticationError,
    ExternalServiceError,
    ResourceNotFoundError,
    ValidationError,
)
from codetoreum.ports.output.board_service import IBoardService, MovedByType

logger = logging.getLogger(__name__)


@dataclass
class BoardState:
    """Cached state for change detection.

    Attributes:
        board_id: Unique identifier for the board
        item_columns: Mapping of work_item_id -> column_name for change detection
    """

    board_id: str
    item_columns: Dict[str, str]  # work_item_id -> column_name


class BoardPollingService:
    """Fallback polling service for environments without webhook support.

    Polls board state at regular intervals to detect column changes made by
    both human users and the orchestrator. Emits WorkItemColumnChanged events
    when changes are detected.

    Attributes:
        board_service: Interface to query board state
        event_bus: Event bus for publishing detected changes
        poll_interval: Seconds between polling attempts (default: 30)
    """

    def __init__(
        self,
        board_service: IBoardService,
        event_bus: EventBus,
        poll_interval_seconds: int = 30,
    ):
        """Initialize board polling service.

        Args:
            board_service: Board service interface for querying state
            event_bus: Event bus for publishing WorkItemColumnChanged events
            poll_interval_seconds: Polling interval in seconds (default: 30)
        """
        self.board_service = board_service
        self.event_bus = event_bus
        self.poll_interval = poll_interval_seconds

        # Board state cache for change detection
        self._board_states: Dict[str, BoardState] = {}

        # Boards to poll (project_id:board_id)
        self._enabled_boards: Set[str] = set()

        self._running = False
        self._poll_task: Optional[asyncio.Task] = None

    def enable_board(self, project_id: str, board_id: str) -> None:
        """Enable polling for a board.

        Args:
            project_id: Project containing the board
            board_id: Board to enable polling for
        """
        board_key = f"{project_id}:{board_id}"
        self._enabled_boards.add(board_key)
        logger.info(f"Enabled polling for board {board_id}")

    def disable_board(self, project_id: str, board_id: str) -> None:
        """Disable polling for a board.

        Args:
            project_id: Project containing the board
            board_id: Board to disable polling for
        """
        board_key = f"{project_id}:{board_id}"
        self._enabled_boards.discard(board_key)
        logger.info(f"Disabled polling for board {board_id}")

    async def start(self) -> None:
        """Start the polling loop.

        Raises:
            RuntimeError: If service is already running
        """
        if self._running:
            logger.warning("Polling service already running")
            return

        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("Board polling service started")

    async def stop(self) -> None:
        """Stop the polling loop gracefully."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        logger.info("Board polling service stopped")

    async def _poll_loop(self) -> None:
        """Main polling loop that runs continuously."""
        while self._running:
            try:
                await self._poll_all_boards()
            except Exception as e:
                logger.error(f"Error in polling loop: {e}", exc_info=True)

            await asyncio.sleep(self.poll_interval)

    async def _poll_all_boards(self) -> None:
        """Poll all enabled boards for changes."""
        for board_key in list(self._enabled_boards):
            try:
                project_id, board_id = board_key.split(":")
                await self._poll_board(project_id, board_id)
            except Exception as e:
                logger.error(f"Error polling board {board_key}: {e}", exc_info=True)

    async def _poll_board(self, project_id: str, board_id: str) -> None:
        """Poll a single board and emit events for detected changes.

        Args:
            project_id: Project containing the board
            board_id: Board to poll
        """
        # Get board with error handling
        try:
            board = await self.board_service.get_board(project_id, board_id)
        except (AuthenticationError, ResourceNotFoundError, ValidationError) as e:
            # Permanent errors - disable polling for this board
            logger.error(
                f"Permanent error polling board {board_id}, disabling: {e}",
                exc_info=True,
                extra={
                    "project_id": project_id,
                    "board_id": board_id,
                    "error_type": type(e).__name__,
                },
            )
            # Remove from enabled boards
            if board_id in self._board_states:
                del self._board_states[board_id]
            # TODO: Emit BoardPollingFailedEvent for user notification
            return
        except ExternalServiceError as e:
            # Transient errors - log and continue (will retry next interval)
            logger.warning(
                f"Transient error polling board {board_id}: {e}",
                exc_info=True,
                extra={"project_id": project_id, "board_id": board_id},
            )
            return
        except Exception as e:
            # Unexpected errors - disable polling and alert
            logger.critical(
                f"Unexpected error polling board {board_id}: {e}",
                exc_info=True,
                extra={"project_id": project_id, "board_id": board_id},
            )
            if board_id in self._board_states:
                del self._board_states[board_id]
            return

        # Build current state with error handling
        current_state = BoardState(board_id=board_id, item_columns={})

        try:
            for column in board.columns:
                items = await self.board_service.get_items_in_column(
                    board_id, column.name
                )
                for item in items:
                    current_state.item_columns[item.work_item_id] = column.name
        except ExternalServiceError as e:
            # Transient error getting column items - log and return
            logger.warning(
                f"Error getting items in columns for board {board_id}: {e}",
                exc_info=True,
                extra={"project_id": project_id, "board_id": board_id},
            )
            return
        except Exception as e:
            # Unexpected error processing columns
            logger.error(
                f"Unexpected error processing columns for board {board_id}: {e}",
                exc_info=True,
                extra={"project_id": project_id, "board_id": board_id},
            )
            return

        # Detect changes
        previous_state = self._board_states.get(board_id)

        if previous_state:
            changes = self._detect_changes(previous_state, current_state)

            for change in changes:
                event = WorkItemColumnChanged(
                    aggregate_id=change["work_item_id"],
                    payload={
                        "work_item_id": change["work_item_id"],
                        "from_column": change["from_column"],
                        "to_column": change["to_column"],
                        "moved_by": "HUMAN",  # Assume human since we can't distinguish
                        "board_id": board_id,
                        "project_id": project_id,
                    },
                )

                # Emit event with error handling
                try:
                    await self.event_bus.publish(event)
                    logger.info(
                        f"Detected column change: {change['work_item_id']} "
                        f"{change['from_column']} -> {change['to_column']}"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to emit column change event for {change['work_item_id']}: {e}",
                        exc_info=True,
                        extra={
                            "work_item_id": change["work_item_id"],
                            "from_column": change["from_column"],
                            "to_column": change["to_column"],
                            "board_id": board_id,
                            "project_id": project_id,
                        },
                    )
                    # Continue processing other changes - don't fail entire poll
                    continue

        # Update cached state
        self._board_states[board_id] = current_state

    def _detect_changes(
        self, previous: BoardState, current: BoardState
    ) -> list[dict]:
        """Detect column changes between two board states.

        Compares previous and current state to identify work items that have
        moved to different columns.

        Args:
            previous: Previous board state
            current: Current board state

        Returns:
            List of detected changes with work_item_id, from_column, to_column
        """
        changes = []

        for work_item_id, current_column in current.item_columns.items():
            previous_column = previous.item_columns.get(work_item_id)

            if previous_column and previous_column != current_column:
                changes.append(
                    {
                        "work_item_id": work_item_id,
                        "from_column": previous_column,
                        "to_column": current_column,
                    }
                )

        return changes
