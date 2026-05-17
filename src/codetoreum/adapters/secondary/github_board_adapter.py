"""GitHub Projects v2 board adapter with event emission.

Implements IBoardService interface for GitHub Projects v2, supporting:
- Board structure queries via GraphQL API
- Work item movement between columns
- Board reconciliation with expected configuration
- Change detection via webhooks or adaptive polling
- Event emission for column changes and board reconciliation
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

from codetoreum.adapters.secondary.github_ticket_adapter import GitHubTicketAdapter
from codetoreum.domain.events.board_events import (
    BoardReconciledEvent,
    WorkItemColumnChangedEvent,
)
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.http.github_graphql_client import (
    GitHubGraphQLClient,
)
from codetoreum.ports.exceptions import (
    AuthenticationError,
    ExternalServiceError,
    ResourceNotFoundError,
    ValidationError,
)
from codetoreum.ports.output.board_service import (
    BoardColumn,
    BoardConfig,
    ColumnMovementResult,
    IBoardService,
    MovedByType,
    ProjectBoard,
    ReconciliationResult,
    WorkItemPosition,
)
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.monitoring import (
    MonitoringConfig,
    MonitoringState,
    MonitoringStatus,
)


class GitHubBoardAdapter(IBoardService):
    """GitHub Projects v2 board adapter with event emission.

    Provides board management and change detection for GitHub Projects v2.
    Supports both webhook-based (real-time) and polling-based (fallback) change detection.
    """

    def __init__(
        self,
        ticket_adapter: GitHubTicketAdapter | None = None,
        graphql_client: GitHubGraphQLClient | None = None,
        webhook_enabled: bool = True,
        event_emitter: "IEventEmitter | None" = None,
    ):
        """Initialize GitHub board adapter.

        Args:
            ticket_adapter: GitHub ticket adapter for issue metadata
            graphql_client: GitHub GraphQL client for Projects v2 API
            webhook_enabled: If False, use polling fallback
            event_emitter: Optional event emitter (unused, for adapter factory compatibility)
        """
        self._ticket_adapter = ticket_adapter
        self._graphql = graphql_client
        self._webhook_enabled = webhook_enabled
        self._event_emitter = event_emitter

        # Monitoring state
        self._monitoring: dict[str, MonitoringStatus] = {}
        self._polling_tasks: dict[str, asyncio.Task] = {}

        # Event handlers
        self._event_handlers: dict[str, list[Callable]] = {}

        # State tracking for polling
        self._last_known_state: dict[str, dict[str, str]] = {}
        self._polling_intervals: dict[str, float] = {}
        self._activity_counters: dict[str, dict[str, int]] = {}

        # Cache for GitHub Projects v2 field and option IDs (adapter-internal, not in port)
        self._status_field_id_cache: dict[str, str] = {}
        self._option_id_cache: dict[str, dict[str, str]] = {}

        # Current context for event emission
        self._current_project_id: str | None = None
        self._current_board_id: str | None = None

    # IEventEmitter implementation

    def on(self, event_type: str, handler: Callable) -> None:
        """Register event handler.

        Args:
            event_type: Type of event to listen for
            handler: Callable to invoke when event is emitted
        """
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    def off(self, event_type: str, handler: Callable) -> None:
        """Unregister event handler.

        Args:
            event_type: Type of event
            handler: Callable to remove
        """
        if event_type in self._event_handlers and handler in self._event_handlers[event_type]:
            self._event_handlers[event_type].remove(handler)

    def emit(self, event: Any) -> None:
        """Emit event to all registered handlers.

        Args:
            event: Event to emit
        """
        event_type = getattr(event, "type", None)
        if event_type in self._event_handlers:
            for handler in self._event_handlers[event_type]:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(
                        f"Event handler failed for {event_type}: {e}",
                        exc_info=True,
                        extra={
                            "error_id": ErrorRegistry.ERR_HANDLER_EXECUTION,
                            "event_type": event_type,
                            "event_id": getattr(event, "event_id", None),
                            "handler": getattr(handler, "__name__", str(handler)),
                        },
                    )
                    # Continue processing other handlers - don't re-raise

    # IMonitoredService implementation

    async def start_monitoring(self, project_id: str, config: MonitoringConfig) -> None:
        """Start monitoring board for changes.

        Args:
            project_id: Project containing the board
            config: Monitoring configuration
        """
        key = project_id

        self._monitoring[key] = MonitoringStatus(
            state=MonitoringState.ACTIVE,
            project_id=project_id,
            started_at=datetime.now(UTC).isoformat(),
        )

        # Initialize activity tracking
        self._activity_counters[key] = {
            "changes_detected": 0,
            "no_changes": 0,
        }
        self._polling_intervals[key] = 60.0  # Initial 60s interval

        # Start polling if webhooks disabled
        if not self._webhook_enabled and hasattr(config, "board_id"):
            board_id = config.board_id
            poll_key = f"{project_id}:{board_id}"
            self._polling_tasks[poll_key] = asyncio.create_task(self._poll_board_changes(project_id, board_id))

    async def stop_monitoring(self, project_id: str) -> None:
        """Stop monitoring board for changes.

        Args:
            project_id: Project to stop monitoring
        """
        key = project_id

        # Cancel all polling tasks for this project
        tasks_to_cancel = [k for k in self._polling_tasks.keys() if k.startswith(f"{project_id}:")]
        for task_key in tasks_to_cancel:
            task = self._polling_tasks[task_key]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self._polling_tasks[task_key]

        if key in self._monitoring:
            self._monitoring[key].state = MonitoringState.STOPPED

    def get_monitoring_status(self, project_id: str) -> MonitoringStatus:
        """Get monitoring status for a project.

        Args:
            project_id: Project to query

        Returns:
            Current monitoring status
        """
        key = project_id
        if key in self._monitoring:
            return self._monitoring[key]

        return MonitoringStatus(
            state=MonitoringState.STOPPED,
            project_id=project_id,
        )

    # Query Operations

    async def get_board(self, project_id: str, board_id: str) -> ProjectBoard:
        """Query board structure via GraphQL.

        Args:
            project_id: Project containing the board
            board_id: Board to retrieve (GitHub Projects v2 node ID)

        Returns:
            ProjectBoard with all columns and work items

        Raises:
            ResourceNotFoundError: Board doesn't exist
            ExternalServiceError: GraphQL API error
        """
        query = """
        query GetProjectBoard($projectId: ID!) {
          node(id: $projectId) {
            ... on ProjectV2 {
              id
              title
              fields(first: 20) {
                nodes {
                  ... on ProjectV2SingleSelectField {
                    id
                    name
                    options {
                      id
                      name
                    }
                  }
                }
              }
              items(first: 100) {
                nodes {
                  id
                  content {
                    ... on Issue {
                      id
                      number
                    }
                  }
                  fieldValues(first: 20) {
                    nodes {
                      ... on ProjectV2ItemFieldSingleSelectValue {
                        field {
                          ... on ProjectV2SingleSelectField {
                            name
                          }
                        }
                        name
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """

        try:
            result = await self._graphql.execute(query, {"projectId": board_id})
            board_node = result.get("node")

            if not board_node:
                msg = "Board"
                raise ResourceNotFoundError(msg, board_id)

            return self._parse_board_response(project_id, board_id, board_node)
        except ExternalServiceError:
            raise
        except Exception as e:
            msg = "GitHub"
            raise ExternalServiceError(msg, f"Failed to fetch board: {e!s}")

    async def get_columns(self, board_id: str) -> list[BoardColumn]:
        """Get all columns for a board.

        Args:
            board_id: Board to query

        Returns:
            List of columns ordered by position

        Raises:
            ResourceNotFoundError: Board doesn't exist
            ExternalServiceError: GraphQL API error
        """
        # Query the board to get columns
        # Note: project_id is not directly available, use empty string
        board = await self.get_board("", board_id)
        return board.columns

    async def get_items_in_column(self, board_id: str, column_name: str) -> list[WorkItemPosition]:
        """Get work items in a specific column ordered by position.

        Args:
            board_id: Board to query
            column_name: Name of column to query

        Returns:
            List of WorkItemPosition objects in the column

        Raises:
            ResourceNotFoundError: Board or column doesn't exist
            ExternalServiceError: GraphQL API error
        """
        board = await self.get_board("", board_id)

        for column in board.columns:
            if column.name == column_name:
                return [
                    WorkItemPosition(work_item_id=item_id, column_name=column_name, position=index)
                    for index, item_id in enumerate(column.work_item_ids)
                ]

        msg = "Column"
        raise ResourceNotFoundError(msg, column_name)

    async def get_item_position(self, work_item_id: str) -> WorkItemPosition:
        """Get current column position of a work item.

        Args:
            work_item_id: Item to locate

        Returns:
            WorkItemPosition with column and position details

        Raises:
            ResourceNotFoundError: Work item not found
            ExternalServiceError: GraphQL API error
        """
        # This would require querying all boards or maintaining a reverse index
        # For now, raise not implemented - clients should track this
        msg = "get_item_position requires board context; use get_items_in_column instead"
        raise NotImplementedError(msg)

    # Command Operations

    async def move_item_to_column(
        self, work_item_id: str, target_column: str, moved_by: MovedByType
    ) -> ColumnMovementResult:
        """Move work item to target column.

        Args:
            work_item_id: Item to move
            target_column: Target column name
            moved_by: Type of entity that initiated the move

        Returns:
            ColumnMovementResult: Details of the movement operation

        Raises:
            ResourceNotFoundError: Work item or column doesn't exist
            ValidationError: Invalid target column
            ExternalServiceError: GraphQL mutation failed

        Events:
            Emits 'workitem.column_changed' event with moved_by value
        """
        if not self._current_project_id or not self._current_board_id:
            msg = "Project and board context required; call within get_board context or set context explicitly"
            raise ValidationError(msg)

        # Get current position first
        board = await self.get_board(self._current_project_id, self._current_board_id)
        from_column: str | None = None

        for column in board.columns:
            if work_item_id in column.work_item_ids:
                from_column = column.name
                break

        if not from_column:
            msg = "WorkItem"
            raise ResourceNotFoundError(msg, work_item_id)

        # Validate target column exists
        target_col = None
        for column in board.columns:
            if column.name == target_column:
                target_col = column
                break

        if not target_col:
            msg = f"Target column '{target_column}' not found on board"
            raise ValidationError(msg)

        # Execute mutation to move item
        mutation = """
        mutation UpdateProjectV2ItemFieldValue(
          $projectId: ID!
          $itemId: ID!
          $fieldId: ID!
          $optionId: String!
        ) {
          updateProjectV2ItemFieldValue(
            input: {
              projectId: $projectId
              itemId: $itemId
              fieldId: $fieldId
              value: {singleSelectOptionId: $optionId}
            }
          ) {
            projectV2Item {
              id
            }
          }
        }
        """

        # Find the status field and option ID from board data
        status_field_id = self._find_status_field_id(board)
        option_id = self._find_option_id(board, status_field_id, target_column)

        if not status_field_id or not option_id:
            msg = f"Cannot find field mapping for column '{target_column}'"
            raise ValidationError(msg)

        try:
            await self._graphql.execute(
                mutation,
                {
                    "projectId": self._current_board_id,
                    "itemId": work_item_id,
                    "fieldId": status_field_id,
                    "optionId": option_id,
                },
            )
        except ExternalServiceError:
            raise

        # Create timestamp for result
        timestamp = datetime.now(UTC).isoformat()

        # Emit event
        self.emit(
            WorkItemColumnChangedEvent(
                type="workitem.column_changed",
                timestamp=timestamp,
                source="github",
                work_item_id=work_item_id,
                project_id=self._current_project_id,
                board_id=self._current_board_id,
                from_column=from_column,
                to_column=target_column,
                moved_by=moved_by.value,
            )
        )

        # Return movement result
        return ColumnMovementResult(
            work_item_id=work_item_id,
            from_column=from_column,
            to_column=target_column,
            moved_by=moved_by,
            timestamp=timestamp,
        )

    async def add_item_to_column(
        self, work_item_id: str, target_column: str, moved_by: MovedByType
    ) -> ColumnMovementResult:
        """Add newly created work item to initial column.

        Places a newly created work item in its initial column. This differs from
        move_item_to_column in that it's the item's first placement, not a transition.

        Args:
            work_item_id: Item to place (must be newly created)
            target_column: Target column name (e.g., "Backlog")
            moved_by: Type of entity initiating the placement (HUMAN or ORCHESTRATOR)

        Returns:
            ColumnMovementResult: Details of the placement operation

        Raises:
            ResourceNotFoundError: Work item or target column doesn't exist
            ExternalServiceError: Service communication failure
        """
        # For GitHub, adding to a column is the same as moving to a column
        # since the item already exists at this point. The semantic difference
        # (new placement vs. movement) is handled at the adapter level but the
        # actual GitHub operation is identical.
        return await self.move_item_to_column(work_item_id, target_column, moved_by)

    async def get_all_boards(self) -> list[ProjectBoard]:
        """Get all boards across all projects.

        Returns all boards managed by this service, including structure and items.
        Used for cross-board queries like SLA monitoring.

        Returns:
            List[ProjectBoard]: All boards with columns and items

        Raises:
            ExternalServiceError: Service communication failure
        """
        # For GitHub, we would need to query all projects the bot has access to
        # This is a complex operation that requires iterating through organizations
        # and projects. For now, return empty list as this is not directly supported
        # by the current GitHub adapter configuration.
        # In a real implementation, this would:
        # 1. List all projects accessible to the authenticated user
        # 2. For each project, call get_board()
        # 3. Return all boards
        return []

    async def get_board_items(self, project_id: str, board_id: str) -> list[WorkItemPosition]:
        """Get all work items on a board with their column positions and entry times.

        Returns all items across all columns on the specified board,
        including their current column, position, and entry timestamp.

        Args:
            project_id: Project containing the board
            board_id: Board to query

        Returns:
            List[WorkItemPosition]: All items with column, position, and entry time

        Raises:
            ResourceNotFoundError: Board doesn't exist
            ExternalServiceError: Service communication failure
        """
        # Get the full board structure
        board = await self.get_board(project_id, board_id)

        # Flatten all items across all columns into a single list
        items: list[WorkItemPosition] = []
        for column in board.columns:
            for position, work_item_id in enumerate(column.work_item_ids):
                items.append(
                    WorkItemPosition(
                        work_item_id=work_item_id,
                        column_name=column.name,
                        position=position,
                        entered_column_at=None,  # GitHub API doesn't provide entry timestamps
                    )
                )

        return items

    async def reconcile_board(self, board_id: str, config: BoardConfig) -> ReconciliationResult:
        """Reconcile board structure with expected configuration.

        Args:
            board_id: Board to reconcile
            config: Board reconciliation configuration

        Returns:
            ReconciliationResult with summary of changes

        Raises:
            ResourceNotFoundError: Board doesn't exist
            ExternalServiceError: GraphQL API error

        Events:
            Emits 'board.reconciled' event with changes summary
        """
        # Get current board state
        board = await self.get_board("", board_id)
        current_columns = {col.name for col in board.columns}
        expected_columns = set(config.expected_columns)

        columns_added = list(expected_columns - current_columns)
        columns_removed = list(current_columns - expected_columns)

        # Create missing columns if auto_create_missing
        if config.auto_create_missing and columns_added:
            for column_name in columns_added:
                await self._create_column(board_id, column_name)

        # Create reconciliation result
        result = ReconciliationResult(
            board_id=board_id,
            columns_added=columns_added,
            columns_removed=columns_removed,
            columns_renamed=[],
            orphaned_items=[],
        )

        # Extract project_id from board or use empty
        project_id = board.project_id or ""

        # Emit event
        self.emit(
            BoardReconciledEvent(
                type="board.reconciled",
                timestamp=datetime.now(UTC).isoformat(),
                source="github",
                project_id=project_id,
                board_id=config.board_id,
                columns_added=columns_added,
                columns_removed=columns_removed,
                items_moved=0,
            )
        )

        return result

    # Webhook Handler

    async def handle_webhook(self, payload: dict) -> None:
        """Process GitHub Projects v2 webhook payload.

        Handles projects_v2_item.edited events with field_value changes.

        Args:
            payload: GitHub webhook payload
        """
        if payload.get("action") != "edited":
            return

        changes = payload.get("changes", {})
        if "field_value" not in changes:
            return

        field_change = changes["field_value"]
        if field_change.get("field_type") != "single_select":
            return

        # Extract IDs from webhook payload
        item_data = payload.get("projects_v2_item", {})
        work_item_id = self._extract_work_item_id(item_data)

        if not work_item_id:
            return

        # Emit event with moved_by='human'
        self.emit(
            WorkItemColumnChangedEvent(
                type="workitem.column_changed",
                timestamp=datetime.now(UTC).isoformat(),
                source="github",
                work_item_id=work_item_id,
                project_id=payload.get("organization", {}).get("id", ""),
                board_id=item_data.get("project_node_id", ""),
                from_column=field_change.get("from", ""),
                to_column=field_change.get("to", ""),
                moved_by="human",
            )
        )

    # Private Methods

    async def _poll_board_changes(self, project_id: str, board_id: str) -> None:
        """Poll board for changes with adaptive intervals.

        Implements adaptive polling with intervals from 30-300 seconds
        based on activity detection:
        - 60s initial interval
        - 30s when changes detected in last 3 polls (high activity)
        - 300s when no changes in last 5 polls (low activity)

        Args:
            project_id: Project containing board
            board_id: Board to poll
        """
        key = f"{project_id}:{board_id}"

        try:
            while True:
                interval = self._polling_intervals.get(key, 60.0)
                await asyncio.sleep(interval)

                # Query current state
                board = await self.get_board(project_id, board_id)
                current_state = self._extract_item_positions(board)

                # Detect changes
                changes = self._detect_column_changes(project_id, board_id, current_state)

                # Update activity counters
                counter = self._activity_counters.get(
                    key,
                    {
                        "changes_detected": 0,
                        "no_changes": 0,
                    },
                )

                if changes:
                    counter["changes_detected"] += 1
                    counter["no_changes"] = 0

                    # Emit events for each change
                    for change in changes:
                        self.emit(change)

                    # High activity: decrease interval to 30s
                    if counter["changes_detected"] >= 3:
                        self._polling_intervals[key] = 30.0
                else:
                    counter["no_changes"] += 1
                    counter["changes_detected"] = 0

                    # Low activity: increase interval to 300s
                    if counter["no_changes"] >= 5:
                        self._polling_intervals[key] = 300.0
                    else:
                        # Reset to 60s during normal activity
                        self._polling_intervals[key] = 60.0

                self._activity_counters[key] = counter
                self._last_known_state[key] = current_state

        except asyncio.CancelledError:
            logger.info(f"Polling cancelled for {project_id}:{board_id}")
        except (AuthenticationError, ResourceNotFoundError, ValidationError) as e:
            # Permanent errors - stop polling and update monitoring state
            logger.error(
                f"Permanent error in board polling for {project_id}:{board_id}: {e}",
                exc_info=True,
                extra={
                    "error_id": ErrorRegistry.ERR_BOARD_ERROR,
                    "project_id": project_id,
                    "board_id": board_id,
                    "error_type": type(e).__name__,
                },
            )
            if project_id in self._monitoring:
                self._monitoring[project_id].state = MonitoringState.ERROR
        except ExternalServiceError as e:
            # Transient errors - log and continue polling
            logger.warning(
                f"External service error during board polling for {project_id}:{board_id}: {e}",
                exc_info=True,
                extra={
                    "error_id": ErrorRegistry.ERR_EXTERNAL_SERVICE_ERROR,
                    "project_id": project_id,
                    "board_id": board_id,
                },
            )
        except Exception as e:
            # Unexpected errors - log critically and stop polling
            logger.critical(
                f"Unexpected error during board polling for {project_id}:{board_id}: {e}",
                exc_info=True,
                extra={
                    "error_id": ErrorRegistry.ERR_BOARD_ERROR,
                    "project_id": project_id,
                    "board_id": board_id,
                },
            )
            if project_id in self._monitoring:
                self._monitoring[project_id].state = MonitoringState.ERROR

    def _detect_column_changes(
        self,
        project_id: str,
        board_id: str,
        current_state: dict[str, str],
    ) -> list[WorkItemColumnChangedEvent]:
        """Detect column changes by comparing states.

        Args:
            project_id: Project ID
            board_id: Board ID
            current_state: Current work item positions (item_id -> column_name)

        Returns:
            List of WorkItemColumnChangedEvent for detected changes
        """
        key = f"{project_id}:{board_id}"

        if key not in self._last_known_state:
            return []

        last_state = self._last_known_state[key]
        changes: list[WorkItemColumnChangedEvent] = []

        for work_item_id, current_column in current_state.items():
            if work_item_id in last_state:
                last_column = last_state[work_item_id]
                if last_column != current_column:
                    changes.append(
                        WorkItemColumnChangedEvent(
                            type="workitem.column_changed",
                            timestamp=datetime.now(UTC).isoformat(),
                            source="github",
                            work_item_id=work_item_id,
                            project_id=project_id,
                            board_id=board_id,
                            from_column=last_column,
                            to_column=current_column,
                            moved_by="unknown",
                        )
                    )

        return changes

    def _extract_item_positions(self, board: ProjectBoard) -> dict[str, str]:
        """Extract work item -> column mapping from board.

        Args:
            board: Project board

        Returns:
            Dictionary mapping work_item_id -> column_name
        """
        positions: dict[str, str] = {}

        for column in board.columns:
            for work_item_id in column.work_item_ids:
                positions[work_item_id] = column.name

        return positions

    def _parse_board_response(
        self,
        project_id: str,
        board_id: str,
        node: dict[str, Any],
    ) -> ProjectBoard:
        """Parse GraphQL board response into ProjectBoard.

        Extracts and caches the Status field ID and option IDs to avoid
        additional GraphQL calls during column moves.

        Args:
            project_id: Project ID
            board_id: Board ID
            node: GraphQL node response

        Returns:
            ProjectBoard object with cached field and option IDs

        Raises:
            ExternalServiceError: Invalid response format
        """
        try:
            board_name = node.get("title", "Unknown")

            # Extract fields and options
            fields_data = node.get("fields", {}).get("nodes", [])
            status_field = None
            status_field_id = None

            for field in fields_data:
                if field.get("name") == "Status":
                    status_field = field
                    status_field_id = field.get("id")
                    if status_field_id:
                        self._status_field_id_cache[board_id] = status_field_id
                    break

            if not status_field:
                msg = "GitHub"
                raise ExternalServiceError(msg, "Status field not found on board")

            # Build column map with option IDs and cache them in adapter state
            columns_by_id: dict[str, str] = {}
            if board_id not in self._option_id_cache:
                self._option_id_cache[board_id] = {}
            for option in status_field.get("options", []):
                option_id = option.get("id", "")
                option_name = option.get("name", "")
                columns_by_id[option_id] = option_name
                self._option_id_cache[board_id][option_name] = option_id

            # Extract items and their positions
            items_data = node.get("items", {}).get("nodes", [])
            columns_by_name: dict[str, list[str]] = {}

            for item in items_data:
                # Extract issue number from content
                content = item.get("content", {})
                issue_number = content.get("number")

                if not issue_number:
                    continue

                # Find which column this item is in
                field_values = item.get("fieldValues", {}).get("nodes", [])

                for field_value in field_values:
                    field_info = field_value.get("field", {})
                    if field_info.get("name") == "Status":
                        column_name = field_value.get("name", "")
                        if column_name:
                            if column_name not in columns_by_name:
                                columns_by_name[column_name] = []
                            # Use issue number as work_item_id
                            columns_by_name[column_name].append(str(issue_number))

            # Create BoardColumn objects ordered by position
            columns: list[BoardColumn] = []
            for position, option in enumerate(status_field.get("options", [])):
                column_name = option.get("name", "")
                column_id = option.get("id", "")
                work_items = columns_by_name.get(column_name, [])

                columns.append(
                    BoardColumn(
                        id=column_id,
                        name=column_name,
                        position=position,
                        work_item_ids=work_items,
                    )
                )

            return ProjectBoard(
                id=board_id,
                name=board_name,
                project_id=project_id,
                columns=columns,
            )

        except (KeyError, TypeError) as e:
            msg = "GitHub"
            raise ExternalServiceError(msg, f"Invalid board response format: {e!s}")

    def _find_status_field_id(self, board: ProjectBoard) -> str | None:
        """Find status field ID from board data.

        Retrieves the cached Status field ID that was populated when
        the board was first fetched via _parse_board_response.

        Args:
            board: Project board to look up

        Returns:
            Status field ID or None if not cached
        """
        return self._status_field_id_cache.get(board.id)

    def _find_option_id(
        self,
        board: ProjectBoard,
        _field_id: str | None,
        column_name: str,
    ) -> str | None:
        """Find option ID for a column name.

        Retrieves the cached option ID from adapter state.
        The option ID is populated when the board is first fetched
        via _parse_board_response.

        Args:
            board: Project board to look up
            _field_id: Status field ID (unused, included for interface compatibility)
            column_name: Column name to find

        Returns:
            Option ID for the column or None if not found
        """
        board_cache = self._option_id_cache.get(board.id)
        if board_cache:
            return board_cache.get(column_name)
        return None

    async def _create_column(self, board_id: str, column_name: str) -> None:
        """Create a new column on the board.

        NOT ON MVP CRITICAL PATH. This method is only needed for dynamic board
        configuration (reconcile_board with auto_create_missing=True). In the MVP,
        the board structure is pre-configured on GitHub and this method is not called.

        Implementation requires a GitHub Projects v2 mutation to add a new option
        to the Status field, which requires extracting the field ID and building
        the proper GraphQL mutation.

        Args:
            board_id: Board to add column to
            column_name: Name of new column

        Raises:
            NotImplementedError: Feature deferred beyond MVP scope
            ExternalServiceError: GraphQL mutation failed
        """
        msg = (
            "Column creation is not on the MVP critical path. "
            "This feature is only needed for auto_create_missing=True in board reconciliation. "
            "In the MVP, board structure is pre-configured and this method should not be called."
        )
        raise NotImplementedError(msg)

    def _extract_work_item_id(self, item_data: dict) -> str | None:
        """Extract work item ID from webhook item data.

        Args:
            item_data: projects_v2_item from webhook payload

        Returns:
            Work item ID or None
        """
        # GitHub webhook provides content_node_id (GitHub node ID)
        # Convert to issue number if possible
        content_node_id = item_data.get("content_node_id", "")
        # Could map this to issue number via GraphQL query
        # For now, use the node_id
        return content_node_id or None
