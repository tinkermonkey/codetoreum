"""Contract tests for IBoardService interface."""

from abc import ABC, abstractmethod

import pytest

from codetoreum.ports.exceptions import ResourceNotFoundError, ValidationError
from codetoreum.ports.output.board_service import (
    BoardConfig,
    IBoardService,
    ProjectBoard,
)


class TestBoardServiceContract(ABC):
    """Abstract contract tests for IBoardService implementations.

    Subclasses must implement create_service() to provide a concrete
    IBoardService implementation to test.
    """

    @abstractmethod
    async def create_service(self) -> IBoardService:
        """Create and return an IBoardService instance for testing."""
        pass

    @abstractmethod
    async def setup_test_board(self, service: IBoardService, project_id: str, board_id: str) -> ProjectBoard:
        """Set up a test board with sample data."""
        pass

    @pytest.mark.asyncio
    async def test_get_board_returns_board_with_columns(self):
        """Get board should return complete board structure."""
        service = await self.create_service()
        board = await self.setup_test_board(service, "proj-123", "board-456")

        retrieved = await service.get_board("proj-123", "board-456")

        assert retrieved.id == board.id
        assert retrieved.project_id == "proj-123"
        assert len(retrieved.columns) > 0

    @pytest.mark.asyncio
    async def test_get_columns_returns_ordered_columns(self):
        """Get columns should return columns in position order."""
        service = await self.create_service()
        await self.setup_test_board(service, "proj-123", "board-456")

        columns = await service.get_columns("board-456")

        assert len(columns) > 0
        # Verify columns are ordered by position
        positions = [col.position for col in columns]
        assert positions == sorted(positions)

    @pytest.mark.asyncio
    async def test_get_items_in_column_returns_items(self):
        """Get items in column should return work item IDs."""
        service = await self.create_service()
        board = await self.setup_test_board(service, "proj-123", "board-456")

        if board.columns:
            column_name = board.columns[0].name
            items = await service.get_items_in_column("board-456", column_name)

            # Should return a list (may be empty)
            assert isinstance(items, list)

    @pytest.mark.asyncio
    async def test_move_item_to_column_changes_position(self):
        """Moving item should update its column."""
        from codetoreum.ports.output.board_service import MovedByType

        service = await self.create_service()
        board = await self.setup_test_board(service, "proj-123", "board-456")

        if len(board.columns) >= 2 and board.columns[0].work_item_ids:
            item_id = board.columns[0].work_item_ids[0]
            target_column = board.columns[1].name

            await service.move_item_to_column(item_id, target_column, MovedByType.HUMAN)

            position = await service.get_item_position(item_id)
            assert position.column_name == target_column

    @pytest.mark.asyncio
    async def test_reconcile_board_with_expected_columns(self):
        """Reconcile board should match expected column structure."""
        service = await self.create_service()
        await self.setup_test_board(service, "proj-123", "board-456")

        config = BoardConfig(
            board_id="board-456",
            expected_columns=["Backlog", "In Progress", "Review", "Done"],
            auto_create_missing=True,
        )

        result = await service.reconcile_board("board-456", config)

        # Reconciliation should complete
        assert isinstance(result.columns_added, list)
        assert isinstance(result.columns_removed, list)
        assert isinstance(result.columns_renamed, list)
        assert isinstance(result.orphaned_items, list)

    @pytest.mark.asyncio
    async def test_get_item_position_returns_column_and_position(self):
        """Get item position should return column name and position."""
        service = await self.create_service()
        board = await self.setup_test_board(service, "proj-123", "board-456")

        if board.columns and board.columns[0].work_item_ids:
            item_id = board.columns[0].work_item_ids[0]
            position = await service.get_item_position(item_id)

            assert position.column_name == board.columns[0].name
            assert isinstance(position.position, int)
            assert position.position >= 0

    @pytest.mark.asyncio
    async def test_board_not_found_raises_error(self):
        """Querying nonexistent board should raise ResourceNotFoundError."""
        service = await self.create_service()

        with pytest.raises(ResourceNotFoundError) as exc_info:
            await service.get_board("proj-123", "nonexistent-board")
        assert exc_info.value.resource_type == "board"
        assert exc_info.value.resource_id == "nonexistent-board"

    @pytest.mark.asyncio
    async def test_column_not_found_raises_error(self):
        """Querying nonexistent column should raise ResourceNotFoundError."""
        service = await self.create_service()
        await self.setup_test_board(service, "proj-123", "board-456")

        with pytest.raises(ResourceNotFoundError) as exc_info:
            await service.get_items_in_column("board-456", "NonexistentColumn")
        assert exc_info.value.resource_type == "column"

    # Negative Test Cases

    @pytest.mark.asyncio
    async def test_empty_string_board_id_validation(self):
        """Test that empty string in board_id raises ValidationError."""
        service = await self.create_service()

        with pytest.raises((ValueError, ValidationError, TypeError)):
            await service.get_board("proj-123", "")

    @pytest.mark.asyncio
    async def test_empty_string_column_name_validation(self):
        """Test that empty string in column_name raises ValidationError."""
        service = await self.create_service()
        board = await self.setup_test_board(service, "proj-123", "board-456")

        with pytest.raises((ValueError, ValidationError, TypeError)):
            await service.get_items_in_column("board-456", "")

    @pytest.mark.asyncio
    async def test_sql_injection_pattern_in_board_id(self):
        """Test that SQL injection patterns in board_id are rejected."""
        service = await self.create_service()

        with pytest.raises((ValueError, ResourceNotFoundError)):
            await service.get_board("proj-123", "'; DROP TABLE boards; --")

    @pytest.mark.asyncio
    async def test_xss_pattern_in_column_name(self):
        """Test that XSS patterns in column names are handled safely."""
        service = await self.create_service()
        board = await self.setup_test_board(service, "proj-123", "board-456")

        # Attempt with XSS pattern
        with pytest.raises((ValueError, ResourceNotFoundError)):
            await service.get_items_in_column("board-456", "<script>alert('XSS')</script>")

    @pytest.mark.asyncio
    async def test_move_item_to_nonexistent_column_fails(self):
        """Test that moving item to nonexistent column fails appropriately."""
        from codetoreum.ports.output.board_service import MovedByType

        service = await self.create_service()
        board = await self.setup_test_board(service, "proj-123", "board-456")

        if board.columns and board.columns[0].work_item_ids:
            item_id = board.columns[0].work_item_ids[0]

            with pytest.raises((ValueError, ResourceNotFoundError)):
                await service.move_item_to_column(
                    item_id, "NonexistentColumn12345", MovedByType.HUMAN
                )

    @pytest.mark.asyncio
    async def test_get_item_position_nonexistent_item_fails(self):
        """Test that querying nonexistent item position fails."""
        service = await self.create_service()
        await self.setup_test_board(service, "proj-123", "board-456")

        with pytest.raises((ValueError, ResourceNotFoundError)):
            await service.get_item_position("nonexistent-item-id-12345")
