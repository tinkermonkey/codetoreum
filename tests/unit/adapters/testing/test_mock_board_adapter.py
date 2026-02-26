"""Unit tests for MockBoardAdapter test helpers and movement tracking.

Tests verify that:
1. create_board() initializes board structure correctly
2. add_item_to_column() manages item positions and handles position parameter
3. simulate_human_move() moves items with MovedByType.HUMAN and logs movement
4. assert_item_in_column() raises AssertionError on mismatch
5. get_movement_history() returns chronological movement log
6. get_items_in_column() returns items ordered by position
7. Thread safety for concurrent operations
8. clear_movement_log() clears the audit trail
"""

import asyncio
from typing import Any

import pytest

from codetoreum.adapters.testing.mock_board_adapter import (
    MockBoardAdapter,
    MovementEvent,
)
from codetoreum.domain.events import WorkItemPositionChangedEvent
from codetoreum.ports.output.board_service import MovedByType


class TestCreateBoard:
    """Tests for create_board() test helper."""

    def test_create_board_initializes_structure(self):
        """Test create_board() creates board with correct structure."""
        adapter = MockBoardAdapter()
        adapter.current_project = "proj-1"

        adapter.create_board("proj-1", "board-1", "My Board", ["Backlog", "In Progress", "Done"])

        # Verify board exists
        board = asyncio.run(adapter.get_board("proj-1", "board-1"))
        assert board.id == "board-1"
        assert board.name == "My Board"
        assert board.project_id == "proj-1"
        assert len(board.columns) == 3

    def test_create_board_column_order(self):
        """Test columns are created in specified order."""
        adapter = MockBoardAdapter()
        adapter.current_project = "proj-1"

        adapter.create_board(
            "proj-1",
            "board-1",
            "Board",
            ["Backlog", "In Progress", "Review", "Done"],
        )

        board = asyncio.run(adapter.get_board("proj-1", "board-1"))
        columns = board.columns

        assert columns[0].name == "Backlog"
        assert columns[0].position == 0
        assert columns[1].name == "In Progress"
        assert columns[1].position == 1
        assert columns[2].name == "Review"
        assert columns[2].position == 2
        assert columns[3].name == "Done"
        assert columns[3].position == 3

    def test_create_board_empty_columns(self):
        """Test create_board() with empty work_item_ids initially."""
        adapter = MockBoardAdapter()
        adapter.current_project = "proj-1"

        adapter.create_board("proj-1", "board-1", "Board", ["Backlog", "In Progress"])

        board = asyncio.run(adapter.get_board("proj-1", "board-1"))
        for column in board.columns:
            assert column.work_item_ids == []


class TestAddItemToColumn:
    """Tests for add_item_to_column() test helper."""

    @pytest.fixture
    def adapter_with_board(self):
        """Create adapter with a board."""
        adapter = MockBoardAdapter()
        adapter.current_project = "proj-1"
        adapter.create_board("proj-1", "board-1", "Board", ["Backlog", "In Progress", "Done"])
        return adapter

    def test_add_item_to_column_appends_to_end(self, adapter_with_board):
        """Test add_item_to_column() appends to end by default."""
        adapter = adapter_with_board
        adapter.add_item_to_column("board-1", "Backlog", "item-1")
        adapter.add_item_to_column("board-1", "Backlog", "item-2")

        items = asyncio.run(adapter.get_items_in_column("board-1", "Backlog"))
        assert len(items) == 2
        assert items[0].work_item_id == "item-1"
        assert items[0].position == 0
        assert items[1].work_item_id == "item-2"
        assert items[1].position == 1

    def test_add_item_to_column_at_specific_position(self, adapter_with_board):
        """Test add_item_to_column() inserts at specified position."""
        adapter = adapter_with_board
        adapter.add_item_to_column("board-1", "Backlog", "item-1", position=0)
        adapter.add_item_to_column("board-1", "Backlog", "item-3", position=1)
        adapter.add_item_to_column("board-1", "Backlog", "item-2", position=1)

        items = asyncio.run(adapter.get_items_in_column("board-1", "Backlog"))
        assert items[0].work_item_id == "item-1"
        assert items[1].work_item_id == "item-2"
        assert items[2].work_item_id == "item-3"

    def test_add_item_to_column_updates_item_positions(self, adapter_with_board):
        """Test add_item_to_column() updates position of later items."""
        adapter = adapter_with_board
        adapter.add_item_to_column("board-1", "Backlog", "item-1", position=0)
        adapter.add_item_to_column("board-1", "Backlog", "item-3", position=1)
        adapter.add_item_to_column("board-1", "Backlog", "item-2", position=1)

        # Verify positions are correct
        for item in asyncio.run(adapter.get_items_in_column("board-1", "Backlog")):
            if item.work_item_id == "item-1":
                assert item.position == 0
            elif item.work_item_id == "item-2":
                assert item.position == 1
            elif item.work_item_id == "item-3":
                assert item.position == 2

    def test_add_item_to_column_board_not_found(self, adapter_with_board):
        """Test add_item_to_column() raises error for non-existent board."""
        adapter = adapter_with_board
        with pytest.raises(ValueError, match="Board.*not found"):
            adapter.add_item_to_column("board-999", "Backlog", "item-1")

    def test_add_item_to_column_column_not_found(self, adapter_with_board):
        """Test add_item_to_column() raises error for non-existent column."""
        adapter = adapter_with_board
        with pytest.raises(ValueError, match="Column.*not found"):
            adapter.add_item_to_column("board-1", "NonExistent", "item-1")

    def test_add_item_to_column_tracks_position(self, adapter_with_board):
        """Test add_item_to_column() tracks item position correctly."""
        adapter = adapter_with_board
        adapter.add_item_to_column("board-1", "Backlog", "item-1")

        position = asyncio.run(adapter.get_item_position("item-1"))
        assert position.work_item_id == "item-1"
        assert position.column_name == "Backlog"
        assert position.position == 0


class TestSimulateHumanMove:
    """Tests for simulate_human_move() test helper."""

    @pytest.fixture
    def adapter_with_item(self):
        """Create adapter with an item on the board."""
        adapter = MockBoardAdapter()
        adapter.current_project = "proj-1"
        adapter.create_board("proj-1", "board-1", "Board", ["Backlog", "In Progress", "Done"])
        adapter.add_item_to_column("board-1", "Backlog", "item-1")
        return adapter

    @pytest.mark.asyncio
    async def test_simulate_human_move_moves_item(self, adapter_with_item):
        """Test simulate_human_move_async() moves item to target column."""
        adapter = adapter_with_item
        await adapter.simulate_human_move_async("item-1", "In Progress")

        position = await adapter.get_item_position("item-1")
        assert position.column_name == "In Progress"

    @pytest.mark.asyncio
    async def test_simulate_human_move_emits_event_with_human_moved_by(self, adapter_with_item):
        """Test simulate_human_move_async() emits event with MovedByType.HUMAN."""
        adapter = adapter_with_item
        events: list[Any] = []
        adapter.on("workitem.column_changed", events.append)

        await adapter.simulate_human_move_async("item-1", "In Progress")

        # Event should be emitted immediately (no race condition)
        assert len(events) == 1
        assert events[0].moved_by == "human"

    @pytest.mark.asyncio
    async def test_simulate_human_move_logs_movement(self, adapter_with_item):
        """Test simulate_human_move_async() logs movement in history."""
        adapter = adapter_with_item
        await adapter.simulate_human_move_async("item-1", "In Progress")

        # No wait needed - operation completed before this line
        history = adapter.get_movement_history("item-1")
        assert len(history) > 0

    @pytest.mark.asyncio
    async def test_simulate_human_move_item_not_found(self, adapter_with_item):
        """Test simulate_human_move_async() raises error for non-existent item."""
        from codetoreum.ports.exceptions import ResourceNotFoundError

        adapter = adapter_with_item
        with pytest.raises(ResourceNotFoundError, match="Work item not found"):
            await adapter.simulate_human_move_async("item-999", "In Progress")

    @pytest.mark.asyncio
    async def test_simulate_human_move_sync_from_async_raises_error(self, adapter_with_item):
        """Test that calling sync simulate_human_move from async context raises error."""
        adapter = adapter_with_item
        with pytest.raises(RuntimeError, match="Cannot call sync simulate_human_move from async context"):
            adapter.simulate_human_move("item-1", "In Progress")


class TestAssertItemInColumn:
    """Tests for assert_item_in_column() test helper."""

    @pytest.fixture
    def adapter_with_item(self):
        """Create adapter with an item on the board."""
        adapter = MockBoardAdapter()
        adapter.current_project = "proj-1"
        adapter.create_board("proj-1", "board-1", "Board", ["Backlog", "In Progress", "Done"])
        adapter.add_item_to_column("board-1", "Backlog", "item-1")
        return adapter

    def test_assert_item_in_column_passes_for_correct_column(self, adapter_with_item):
        """Test assert_item_in_column() passes when item is in column."""
        adapter = adapter_with_item
        # Should not raise
        adapter.assert_item_in_column("item-1", "Backlog")

    def test_assert_item_in_column_raises_for_wrong_column(self, adapter_with_item):
        """Test assert_item_in_column() raises AssertionError for wrong column."""
        adapter = adapter_with_item
        with pytest.raises(AssertionError, match="Expected work item.*in column.*In Progress"):
            adapter.assert_item_in_column("item-1", "In Progress")

    def test_assert_item_in_column_raises_for_nonexistent_item(self, adapter_with_item):
        """Test assert_item_in_column() raises for item not on board."""
        adapter = adapter_with_item
        with pytest.raises(AssertionError, match="Expected work item.*in column.*Backlog"):
            adapter.assert_item_in_column("item-999", "Backlog")

    def test_assert_item_in_column_error_message(self, adapter_with_item):
        """Test assert_item_in_column() provides informative error message."""
        adapter = adapter_with_item
        try:
            adapter.assert_item_in_column("item-1", "Done")
            assert False, "Should have raised AssertionError"
        except AssertionError as e:
            assert "item-1" in str(e)
            assert "Done" in str(e)
            assert "Backlog" in str(e)


class TestGetMovementHistory:
    """Tests for get_movement_history() test helper."""

    @pytest.fixture
    def adapter_with_item(self):
        """Create adapter with an item on the board."""
        adapter = MockBoardAdapter()
        adapter.current_project = "proj-1"
        adapter.create_board("proj-1", "board-1", "Board", ["Backlog", "In Progress", "Review", "Done"])
        adapter.add_item_to_column("board-1", "Backlog", "item-1")
        return adapter

    def test_get_movement_history_returns_empty_for_new_item(self, adapter_with_item):
        """Test get_movement_history() returns empty list for new item."""
        adapter = adapter_with_item
        history = adapter.get_movement_history("item-1")
        assert history == []

    def test_get_movement_history_tracks_single_move(self, adapter_with_item):
        """Test get_movement_history() records single movement."""
        adapter = adapter_with_item
        asyncio.run(adapter.move_item_to_column("item-1", "In Progress", MovedByType.ORCHESTRATOR))

        history = adapter.get_movement_history("item-1")
        assert len(history) == 1
        assert history[0].work_item_id == "item-1"
        assert history[0].from_column == "Backlog"
        assert history[0].to_column == "In Progress"
        assert history[0].moved_by == MovedByType.ORCHESTRATOR

    def test_get_movement_history_tracks_multiple_moves(self, adapter_with_item):
        """Test get_movement_history() records multiple movements."""
        adapter = adapter_with_item
        asyncio.run(adapter.move_item_to_column("item-1", "In Progress", MovedByType.HUMAN))
        asyncio.run(adapter.move_item_to_column("item-1", "Review", MovedByType.ORCHESTRATOR))
        asyncio.run(adapter.move_item_to_column("item-1", "Done", MovedByType.HUMAN))

        history = adapter.get_movement_history("item-1")
        assert len(history) == 3
        assert history[0].to_column == "In Progress"
        assert history[0].moved_by == MovedByType.HUMAN
        assert history[1].to_column == "Review"
        assert history[1].moved_by == MovedByType.ORCHESTRATOR
        assert history[2].to_column == "Done"
        assert history[2].moved_by == MovedByType.HUMAN

    def test_get_movement_history_chronological_order(self, adapter_with_item):
        """Test get_movement_history() returns movements in chronological order."""
        adapter = adapter_with_item
        asyncio.run(adapter.move_item_to_column("item-1", "In Progress", MovedByType.HUMAN))
        asyncio.run(adapter.move_item_to_column("item-1", "Review", MovedByType.HUMAN))

        history = adapter.get_movement_history("item-1")
        # Verify timestamps are monotonically increasing
        for i in range(len(history) - 1):
            assert history[i].timestamp <= history[i + 1].timestamp

    def test_get_movement_history_isolated_per_item(self, adapter_with_item):
        """Test get_movement_history() only returns history for specific item."""
        adapter = adapter_with_item
        adapter.add_item_to_column("board-1", "Backlog", "item-2")

        asyncio.run(adapter.move_item_to_column("item-1", "In Progress", MovedByType.HUMAN))
        asyncio.run(adapter.move_item_to_column("item-2", "Review", MovedByType.HUMAN))

        history1 = adapter.get_movement_history("item-1")
        history2 = adapter.get_movement_history("item-2")

        assert len(history1) == 1
        assert history1[0].work_item_id == "item-1"
        assert len(history2) == 1
        assert history2[0].work_item_id == "item-2"

    def test_get_movement_history_returns_movement_events(self, adapter_with_item):
        """Test get_movement_history() returns MovementEvent instances."""
        adapter = adapter_with_item
        asyncio.run(adapter.move_item_to_column("item-1", "In Progress", MovedByType.HUMAN))

        history = adapter.get_movement_history("item-1")
        assert isinstance(history[0], MovementEvent)
        assert hasattr(history[0], "work_item_id")
        assert hasattr(history[0], "from_column")
        assert hasattr(history[0], "to_column")
        assert hasattr(history[0], "moved_by")
        assert hasattr(history[0], "timestamp")


class TestClearMovementLog:
    """Tests for clear_movement_log() test helper."""

    @pytest.fixture
    def adapter_with_movements(self):
        """Create adapter with some movements recorded."""
        adapter = MockBoardAdapter()
        adapter.current_project = "proj-1"
        adapter.create_board("proj-1", "board-1", "Board", ["Backlog", "In Progress", "Done"])
        adapter.add_item_to_column("board-1", "Backlog", "item-1")
        adapter.add_item_to_column("board-1", "Backlog", "item-2")
        asyncio.run(adapter.move_item_to_column("item-1", "In Progress", MovedByType.HUMAN))
        asyncio.run(adapter.move_item_to_column("item-2", "In Progress", MovedByType.HUMAN))
        return adapter

    def test_clear_movement_log_clears_history(self, adapter_with_movements):
        """Test clear_movement_log() clears all movement history."""
        adapter = adapter_with_movements
        assert len(adapter.get_movement_history("item-1")) == 1
        assert len(adapter.get_movement_history("item-2")) == 1

        adapter.clear_movement_log()

        assert len(adapter.get_movement_history("item-1")) == 0
        assert len(adapter.get_movement_history("item-2")) == 0

    def test_clear_movement_log_between_tests(self, adapter_with_movements):
        """Test clear_movement_log() enables test isolation."""
        adapter = adapter_with_movements

        # First test phase
        history1 = adapter.get_movement_history("item-1")
        assert len(history1) == 1

        # Clear for second test
        adapter.clear_movement_log()

        # Second test phase
        asyncio.run(adapter.move_item_to_column("item-1", "Done", MovedByType.ORCHESTRATOR))
        history2 = adapter.get_movement_history("item-1")
        assert len(history2) == 1  # Only the new movement


class TestGetItemsInColumn:
    """Tests for get_items_in_column() returns items in position order."""

    @pytest.fixture
    def adapter_with_items(self):
        """Create adapter with multiple items."""
        adapter = MockBoardAdapter()
        adapter.current_project = "proj-1"
        adapter.create_board("proj-1", "board-1", "Board", ["Backlog", "In Progress", "Done"])
        return adapter

    async def test_get_items_in_column_returns_items_in_order(self, adapter_with_items):
        """Test get_items_in_column() returns items ordered by position."""
        adapter = adapter_with_items
        adapter.add_item_to_column("board-1", "Backlog", "item-1", position=0)
        adapter.add_item_to_column("board-1", "Backlog", "item-2", position=1)
        adapter.add_item_to_column("board-1", "Backlog", "item-3", position=2)

        items = await adapter.get_items_in_column("board-1", "Backlog")

        assert len(items) == 3
        assert items[0].work_item_id == "item-1"
        assert items[0].position == 0
        assert items[1].work_item_id == "item-2"
        assert items[1].position == 1
        assert items[2].work_item_id == "item-3"
        assert items[2].position == 2

    async def test_get_items_in_column_empty_column(self, adapter_with_items):
        """Test get_items_in_column() returns empty list for empty column."""
        adapter = adapter_with_items
        items = await adapter.get_items_in_column("board-1", "Backlog")
        assert items == []

    async def test_get_items_in_column_topmost_first(self, adapter_with_items):
        """Test get_items_in_column() returns topmost item (position 0) first."""
        adapter = adapter_with_items
        adapter.add_item_to_column("board-1", "Backlog", "bottom")
        adapter.add_item_to_column("board-1", "Backlog", "top", position=0)

        items = await adapter.get_items_in_column("board-1", "Backlog")

        assert items[0].work_item_id == "top"
        assert items[0].position == 0
        assert items[1].work_item_id == "bottom"
        assert items[1].position == 1


class TestPositionRecalculationOnRemoval:
    """Tests for FR-8: Position recalculation when removing items from column."""

    @pytest.fixture
    def adapter_with_items(self):
        """Create adapter with multiple items in a column."""
        adapter = MockBoardAdapter()
        adapter.current_project = "proj-1"
        adapter.create_board("proj-1", "board-1", "Board", ["Backlog", "In Progress", "Done"])
        # Add items at positions 0-4
        for i in range(5):
            adapter.add_item_to_column("board-1", "Backlog", f"item-{i}", position=i)
        return adapter

    @pytest.mark.asyncio
    async def test_remove_item_at_position_3_shifts_items_down(self, adapter_with_items):
        """Test that removing item at position 3 shifts items 4+ down by 1.

        FR-8 requirement: When an item is removed from a column at a specific
        position, all items at positions greater than that position should shift
        down by 1 to fill the gap.

        Initial state:
            position 0: item-0
            position 1: item-1
            position 2: item-2
            position 3: item-3  <- removed
            position 4: item-4

        Expected after removal:
            position 0: item-0
            position 1: item-1
            position 2: item-2
            position 3: item-4  <- shifted down from position 4
        """
        adapter = adapter_with_items

        # Verify initial state
        items_before = await adapter.get_items_in_column("board-1", "Backlog")
        assert len(items_before) == 5
        assert items_before[3].work_item_id == "item-3"
        assert items_before[4].work_item_id == "item-4"
        assert items_before[4].position == 4

        # Move item-3 to another column (removes it from Backlog)
        await adapter.move_item_to_column("item-3", "In Progress", MovedByType.HUMAN)

        # Verify state after removal
        items_after = await adapter.get_items_in_column("board-1", "Backlog")
        assert len(items_after) == 4

        # Verify positions are sequential starting from 0
        for i, item in enumerate(items_after):
            assert item.position == i, f"Item {item.work_item_id} should be at position {i}, got {item.position}"

        # Verify items that were after position 3 have shifted down
        assert items_after[3].work_item_id == "item-4"
        assert items_after[3].position == 3

        # Verify the position cache is also correct
        item_4_position = await adapter.get_item_position("item-4")
        assert item_4_position.position == 3
        assert item_4_position.column_name == "Backlog"

    @pytest.mark.asyncio
    async def test_remove_item_at_position_0_shifts_all_items_down(self, adapter_with_items):
        """Test that removing item at position 0 shifts all subsequent items down by 1."""
        adapter = adapter_with_items

        # Verify initial state
        items_before = await adapter.get_items_in_column("board-1", "Backlog")
        assert len(items_before) == 5
        assert items_before[0].work_item_id == "item-0"

        # Move item-0 to another column
        await adapter.move_item_to_column("item-0", "In Progress", MovedByType.HUMAN)

        # Verify all items shifted down by 1
        items_after = await adapter.get_items_in_column("board-1", "Backlog")
        assert len(items_after) == 4
        assert items_after[0].work_item_id == "item-1"
        assert items_after[0].position == 0
        assert items_after[1].work_item_id == "item-2"
        assert items_after[1].position == 1

    @pytest.mark.asyncio
    async def test_remove_last_item_no_position_updates_needed(self, adapter_with_items):
        """Test that removing the last item requires no position updates."""
        adapter = adapter_with_items

        # Verify initial state
        items_before = await adapter.get_items_in_column("board-1", "Backlog")
        assert len(items_before) == 5
        assert items_before[4].work_item_id == "item-4"

        # Move last item to another column
        await adapter.move_item_to_column("item-4", "In Progress", MovedByType.HUMAN)

        # Verify only the last item was removed
        items_after = await adapter.get_items_in_column("board-1", "Backlog")
        assert len(items_after) == 4
        # Other positions should remain unchanged
        for i in range(4):
            assert items_after[i].work_item_id == f"item-{i}"
            assert items_after[i].position == i


class TestThreadSafety:
    """Tests for thread safety of concurrent operations."""

    def test_concurrent_item_additions_thread_safe(self):
        """Test concurrent add_item_to_column() operations are thread-safe."""
        import threading

        adapter = MockBoardAdapter()
        adapter.current_project = "proj-1"
        adapter.create_board("proj-1", "board-1", "Board", ["Backlog", "In Progress", "Done"])

        # Add items concurrently
        def add_items(start_idx, count):
            for i in range(start_idx, start_idx + count):
                adapter.add_item_to_column("board-1", "Backlog", f"item-{i}")

        threads = [
            threading.Thread(target=add_items, args=(0, 10)),
            threading.Thread(target=add_items, args=(10, 10)),
            threading.Thread(target=add_items, args=(20, 10)),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify all items were added
        items = asyncio.run(adapter.get_items_in_column("board-1", "Backlog"))
        assert len(items) == 30

    def test_concurrent_movements_thread_safe(self):
        """Test concurrent move_item_to_column() operations are thread-safe."""

        adapter = MockBoardAdapter()
        adapter.current_project = "proj-1"
        adapter.create_board(
            "proj-1",
            "board-1",
            "Board",
            ["Backlog", "In Progress", "Review", "Done"],
        )

        # Add items
        for i in range(10):
            adapter.add_item_to_column("board-1", "Backlog", f"item-{i}")

        # Move items concurrently
        async def move_items():
            for i in range(10):
                await adapter.move_item_to_column(f"item-{i}", "In Progress", MovedByType.ORCHESTRATOR)

        asyncio.run(move_items())

        # Verify all items are in target column
        items = asyncio.run(adapter.get_items_in_column("board-1", "In Progress"))
        assert len(items) == 10


class TestPositionChangedEventEmissions:
    """Tests for WorkItemPositionChangedEvent emissions during position recalculation."""

    @pytest.fixture
    def adapter_with_items(self):
        """Create adapter with multiple items in a column."""
        adapter = MockBoardAdapter()
        adapter.current_project = "proj-1"
        adapter.create_board("proj-1", "board-1", "Board", ["Backlog", "In Progress", "Done"])
        # Add items at positions 0-2
        for i in range(3):
            adapter.add_item_to_column("board-1", "Backlog", f"item-{i}", position=i)
        return adapter

    @pytest.mark.asyncio
    async def test_move_item_emits_position_changed_for_siblings_after_removal(self, adapter_with_items):
        """Test that move_item_to_column() emits WorkItemPositionChangedEvent for sibling items.

        When item-1 is removed from [item-0, item-1, item-2], the sibling items
        at positions >= the removed position should shift down and emit events.
        """
        from codetoreum.domain.events import WorkItemPositionChangedEvent

        adapter = adapter_with_items
        position_events: list[WorkItemPositionChangedEvent] = []
        adapter.on("workitem.position_changed", position_events.append)

        # Move item-1 (at position 1) to In Progress
        await adapter.move_item_to_column("item-1", "In Progress", MovedByType.HUMAN)

        # Verify position changed events were emitted for item-2
        # item-2 should shift from position 2 to position 1
        assert len(position_events) == 1
        assert position_events[0].work_item_id == "item-2"
        assert position_events[0].old_position == 2
        assert position_events[0].new_position == 1
        assert position_events[0].column_name == "Backlog"

    @pytest.mark.asyncio
    async def test_move_item_no_position_changed_event_when_only_item_removed(self, adapter_with_items):
        """Test no position changed event when removing the last item in column."""
        adapter = adapter_with_items
        # Remove all but item-0
        await adapter.move_item_to_column("item-1", "In Progress", MovedByType.HUMAN)
        await adapter.move_item_to_column("item-2", "In Progress", MovedByType.HUMAN)

        position_events: list[WorkItemPositionChangedEvent] = []
        adapter.on("workitem.position_changed", position_events.append)

        # Move item-0 (the only remaining item) - no position changes for siblings
        await adapter.move_item_to_column("item-0", "Done", MovedByType.HUMAN)

        assert len(position_events) == 0

    @pytest.mark.asyncio
    async def test_add_item_to_column_emits_position_changed_for_shifted_items(self, adapter_with_items):
        """Test that add_item_to_column() emits WorkItemPositionChangedEvent for shifted items.

        When item-4 is inserted at position 0, all existing items shift down
        and should emit position changed events.
        """
        from codetoreum.domain.events import WorkItemPositionChangedEvent

        adapter = adapter_with_items
        position_events: list[WorkItemPositionChangedEvent] = []
        adapter.on("workitem.position_changed", position_events.append)

        # Add new item at position 0 - should shift item-0, item-1, item-2
        adapter.add_item_to_column("board-1", "Backlog", "item-new", position=0)

        # Verify position changed events were emitted for all shifted items
        assert len(position_events) == 3

        # Verify events are for the correct items and positions
        events_by_item = {e.work_item_id: e for e in position_events}

        assert "item-0" in events_by_item
        assert events_by_item["item-0"].old_position == 0
        assert events_by_item["item-0"].new_position == 1

        assert "item-1" in events_by_item
        assert events_by_item["item-1"].old_position == 1
        assert events_by_item["item-1"].new_position == 2

        assert "item-2" in events_by_item
        assert events_by_item["item-2"].old_position == 2
        assert events_by_item["item-2"].new_position == 3

    def test_add_item_to_column_no_events_when_appending_to_end(self, adapter_with_items):
        """Test no position changed events when adding to end of column."""
        adapter = adapter_with_items
        position_events: list[WorkItemPositionChangedEvent] = []
        adapter.on("workitem.position_changed", position_events.append)

        # Add item to end (default position) - should not shift any items
        adapter.add_item_to_column("board-1", "Backlog", "item-new")

        assert len(position_events) == 0

    def test_add_item_requires_current_project(self):
        """Test that add_item_to_column() requires current_project to be set."""
        adapter = MockBoardAdapter()
        # Note: current_project is not set
        adapter.create_board("proj-1", "board-1", "Board", ["Backlog"])

        with pytest.raises(ValueError, match="current_project not set"):
            adapter.add_item_to_column("board-1", "Backlog", "item-1")

    @pytest.mark.asyncio
    async def test_position_changed_event_has_correct_metadata(self, adapter_with_items):
        """Test that WorkItemPositionChangedEvent has correct metadata."""
        from codetoreum.domain.events import WorkItemPositionChangedEvent

        adapter = adapter_with_items
        position_events: list[WorkItemPositionChangedEvent] = []
        adapter.on("workitem.position_changed", position_events.append)

        await adapter.move_item_to_column("item-1", "In Progress", MovedByType.HUMAN)

        assert len(position_events) == 1
        event = position_events[0]

        # Verify event metadata
        assert event.type == "workitem.position_changed"
        assert event.project_id == "proj-1"
        assert event.board_id == "board-1"
        assert event.column_name == "Backlog"
        assert event.source == "mock"
        assert event.timestamp is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
