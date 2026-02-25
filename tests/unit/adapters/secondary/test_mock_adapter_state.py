"""Unit tests for mock adapter state consistency.

Tests verify that:
1. move_item_to_column updates all state structures atomically
2. Concurrent state access remains consistent
3. State resets completely between tests
4. Board state consistent after all operations
"""

import asyncio

import pytest

from codetoreum.adapters.testing.mock_board_adapter import MockBoardAdapter
from codetoreum.ports.output.board_service import MovedByType


@pytest.fixture
def mock_board_adapter():
    """Create a mock board adapter for testing."""
    adapter = MockBoardAdapter()
    adapter.current_project = "proj-1"
    adapter.current_board = "board-1"
    adapter.create_board("proj-1", "board-1", "Test Board", ["Backlog", "In Progress", "Done"])
    return adapter


@pytest.mark.asyncio
class TestMockAdapterStateConsistency:
    """Test suite for mock adapter state consistency."""

    async def test_move_item_updates_all_state_structures(self, mock_board_adapter):
        """Test that moving item updates all internal state structures."""
        adapter = mock_board_adapter

        # Create item in column A
        adapter.add_item_to_column("board-1", "Backlog", "item-1")

        # Verify item in Backlog
        position = await adapter.get_item_position("item-1")
        assert position.column_name == "Backlog"

        # Move to In Progress
        await adapter.move_item_to_column("item-1", "In Progress", MovedByType.ORCHESTRATOR)

        # Verify item in In Progress
        position = await adapter.get_item_position("item-1")
        assert position.column_name == "In Progress"

        # Verify item NOT in Backlog
        board = await adapter.get_board("proj-1", "board-1")
        backlog_items = [col.work_item_ids for col in board.columns if col.name == "Backlog"]
        backlog_flat = [item for sublist in backlog_items for item in sublist]
        assert "item-1" not in backlog_flat

    async def test_concurrent_state_access_consistency(self, mock_board_adapter):
        """Test that concurrent state access remains consistent."""
        adapter = mock_board_adapter

        # Add multiple items
        for i in range(5):
            adapter.add_item_to_column("board-1", "Backlog", f"item-{i}")

        # Move items concurrently
        tasks = [
            adapter.move_item_to_column(f"item-{i}", "In Progress", MovedByType.HUMAN)
            for i in range(5)
        ]

        await asyncio.gather(*tasks)

        # Verify all items are in In Progress
        board = await adapter.get_board("proj-1", "board-1")
        in_progress_items = [
            item for col in board.columns if col.name == "In Progress" for item in col.work_item_ids
        ]

        assert len(in_progress_items) == 5
        for i in range(5):
            assert f"item-{i}" in in_progress_items

    async def test_state_reset_between_operations(self, mock_board_adapter):
        """Test that state resets correctly between operations."""
        adapter = mock_board_adapter

        # Add items and move them
        adapter.add_item_to_column("board-1", "Backlog", "item-1")
        await adapter.move_item_to_column("item-1", "Done", MovedByType.ORCHESTRATOR)

        # Verify item in Done
        position = await adapter.get_item_position("item-1")
        assert position.column_name == "Done"

        # Create a new adapter instance to verify clean state
        new_adapter = MockBoardAdapter()
        new_adapter.current_project = "proj-1"
        new_adapter.current_board = "board-1"
        new_adapter.create_board("proj-1", "board-1", "New Board", ["Backlog", "In Progress", "Done"])

        # Verify new adapter has no previous items
        board = await new_adapter.get_board("proj-1", "board-1")
        all_items = [item for col in board.columns for item in col.work_item_ids]
        assert "item-1" not in all_items

    async def test_board_state_consistency_after_multiple_operations(self, mock_board_adapter):
        """Test that board state remains consistent after multiple operations."""
        adapter = mock_board_adapter

        # Add items to multiple columns
        adapter.add_item_to_column("board-1", "Backlog", "item-1")
        adapter.add_item_to_column("board-1", "Backlog", "item-2")
        adapter.add_item_to_column("board-1", "In Progress", "item-3")

        # Move items around
        await adapter.move_item_to_column("item-1", "In Progress", MovedByType.HUMAN)
        await adapter.move_item_to_column("item-3", "Done", MovedByType.ORCHESTRATOR)
        await adapter.move_item_to_column("item-2", "In Progress", MovedByType.HUMAN)

        # Verify final state consistency
        board = await adapter.get_board("proj-1", "board-1")

        backlog_items = [
            item for col in board.columns if col.name == "Backlog" for item in col.work_item_ids
        ]
        in_progress_items = [
            item for col in board.columns if col.name == "In Progress" for item in col.work_item_ids
        ]
        done_items = [item for col in board.columns if col.name == "Done" for item in col.work_item_ids]

        # Verify each item is in exactly one column
        assert len(backlog_items) == 0
        assert len(in_progress_items) == 2
        assert "item-1" in in_progress_items
        assert "item-2" in in_progress_items
        assert len(done_items) == 1
        assert "item-3" in done_items

        # Verify no item is duplicated
        all_items = backlog_items + in_progress_items + done_items
        assert len(all_items) == len(set(all_items))
        assert len(all_items) == 3
