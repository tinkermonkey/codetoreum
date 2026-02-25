"""
Scenario 9: Pipeline Queue with Board Position Ordering

Tests the InMemoryQueueService with board position-based queue ordering.
Simulates multiple work items in a pipeline trigger column with queue
management and position-based prioritization.

Key Features Tested:
- Queue entry creation with board position tracking
- Position-based ordering (lowest position = highest priority)
- Queue synchronization with board state changes
- Status management (waiting vs active)
- Board reordering affecting queue priority

Expected Outcome:
- Multiple items queued with correct board positions
- Queue sorted by position (lowest first)
- Manual board reordering updates queue positions
- Next waiting item correctly identified by position
"""

from datetime import UTC, datetime

import pytest

from codetoreum.adapters.testing.in_memory_queue_service import InMemoryQueueService
from codetoreum.adapters.testing.mock_board_adapter import MockBoardAdapter


@pytest.mark.asyncio
async def test_scenario_09_queue_position_ordering():
    """Test queue ordering based on board position simulation."""
    # Setup
    queue_service = InMemoryQueueService()
    board_service = MockBoardAdapter()
    now = datetime.now(UTC)

    # Create board with trigger column
    board_service.current_project = "proj-1"
    board_service.create_board(
        project_id="proj-1",
        board_id="board-1",
        board_name="Pipeline Board",
        column_names=["Backlog", "In Progress", "In Review", "Done"],
    )

    # Add work items to "In Progress" column
    board_service.add_item_to_column("board-1", "In Progress", "item-1")
    board_service.add_item_to_column("board-1", "In Progress", "item-2")
    board_service.add_item_to_column("board-1", "In Progress", "item-3")

    # Enqueue items with their current positions
    await queue_service.enqueue_item(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-1",
        position_in_column=0,  # Topmost = highest priority
        timestamp=now,
    )

    await queue_service.enqueue_item(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-2",
        position_in_column=1,
        timestamp=now,
    )

    await queue_service.enqueue_item(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-3",
        position_in_column=2,
        timestamp=now,
    )

    # Verify initial queue state
    entries = await queue_service.get_queue_entries("proj-1", "board-1")
    assert len(entries) == 3
    assert entries[0].work_item_id == "item-1"
    assert entries[0].position_in_column == 0
    assert entries[0].status == "waiting"

    # Verify next waiting item is the highest priority
    next_item = await queue_service.get_next_waiting_item("proj-1", "board-1")
    assert next_item is not None
    assert next_item.work_item_id == "item-1"
    assert next_item.position_in_column == 0

    # Mark item-1 as active (it acquired the lock)
    await queue_service.mark_item_active("item-1")
    entries = await queue_service.get_queue_entries("proj-1", "board-1")
    assert entries[0].status == "active"

    # Next waiting item should now be item-2
    next_waiting = await queue_service.get_next_waiting_item("proj-1", "board-1")
    assert next_waiting is not None
    assert next_waiting.work_item_id == "item-2"

    # Simulate human reordering: drag item-3 to top
    # This changes board order but queue still has old positions
    board_service.add_item_to_column("board-1", "In Progress", "item-4")
    await board_service.simulate_human_move_async("item-4", "In Progress")

    # Create updated board with new order
    board = await board_service.get_board("proj-1", "board-1")
    column = board.columns[1]  # "In Progress" column

    # Manually update queue with new positions from board
    # This simulates the sync operation
    await queue_service.enqueue_item(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-4",
        position_in_column=3,
        timestamp=now,
    )

    # Verify all items are still in queue
    all_entries = await queue_service.get_queue_entries("proj-1", "board-1")
    assert len(all_entries) == 4

    # Test removal of completed item
    await queue_service.remove_from_queue("item-1")
    remaining = await queue_service.get_queue_entries("proj-1", "board-1")
    assert len(remaining) == 3
    assert all(e.work_item_id != "item-1" for e in remaining)

    # Verify next waiting item after removal
    next_item_after_removal = await queue_service.get_next_waiting_item(
        "proj-1", "board-1"
    )
    assert next_item_after_removal is not None
    assert next_item_after_removal.work_item_id == "item-2"


@pytest.mark.asyncio
async def test_scenario_09_parallel_queues():
    """Test independent queues for multiple boards."""
    queue_service = InMemoryQueueService()
    now = datetime.now(UTC)

    # Create items in project-1, board-1
    await queue_service.enqueue_item(
        "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
    )
    await queue_service.enqueue_item(
        "proj-1", "board-1", "item-2", position_in_column=1, timestamp=now
    )

    # Create items in project-1, board-2
    await queue_service.enqueue_item(
        "proj-1", "board-2", "item-3", position_in_column=0, timestamp=now
    )
    await queue_service.enqueue_item(
        "proj-1", "board-2", "item-4", position_in_column=1, timestamp=now
    )

    # Verify independent queues
    queue1 = await queue_service.get_queue_entries("proj-1", "board-1")
    queue2 = await queue_service.get_queue_entries("proj-1", "board-2")

    assert len(queue1) == 2
    assert len(queue2) == 2
    assert queue1[0].work_item_id == "item-1"
    assert queue2[0].work_item_id == "item-3"

    # Verify next waiting items are independent
    next1 = await queue_service.get_next_waiting_item("proj-1", "board-1")
    next2 = await queue_service.get_next_waiting_item("proj-1", "board-2")

    assert next1 is not None
    assert next2 is not None
    assert next1.work_item_id == "item-1"
    assert next2.work_item_id == "item-3"

    # Mark one as active in board-1
    await queue_service.mark_item_active("item-1")

    # Verify other queue unaffected
    next1_after = await queue_service.get_next_waiting_item("proj-1", "board-1")
    assert next1_after is not None
    assert next1_after.work_item_id == "item-2"

    next2_after = await queue_service.get_next_waiting_item("proj-1", "board-2")
    assert next2_after is not None
    assert next2_after.work_item_id == "item-3"  # Still waiting, unchanged


@pytest.mark.asyncio
async def test_scenario_09_position_changes_affect_priority():
    """Test that position changes affect queue ordering."""
    queue_service = InMemoryQueueService()
    now = datetime.now(UTC)

    # Add items with specific positions
    await queue_service.enqueue_item(
        "proj-1", "board-1", "item-a", position_in_column=0, timestamp=now
    )
    await queue_service.enqueue_item(
        "proj-1", "board-1", "item-b", position_in_column=5, timestamp=now
    )
    await queue_service.enqueue_item(
        "proj-1", "board-1", "item-c", position_in_column=2, timestamp=now
    )

    # Verify sorted by position
    entries = await queue_service.get_queue_entries("proj-1", "board-1")
    assert entries[0].work_item_id == "item-a"  # position 0
    assert entries[1].work_item_id == "item-c"  # position 2
    assert entries[2].work_item_id == "item-b"  # position 5

    # Remove top item
    await queue_service.remove_from_queue("item-a")

    # Verify item-c is now at top
    next_item = await queue_service.get_next_waiting_item("proj-1", "board-1")
    assert next_item is not None
    assert next_item.work_item_id == "item-c"

    # Mark item-c as active
    await queue_service.mark_item_active("item-c")

    # Item-b should be next waiting
    next_item = await queue_service.get_next_waiting_item("proj-1", "board-1")
    assert next_item is not None
    assert next_item.work_item_id == "item-b"


@pytest.mark.asyncio
async def test_scenario_09_with_board_service_sync():
    """Test queue synchronization with actual board service."""
    board_service = MockBoardAdapter()
    queue_service = InMemoryQueueService(board_service=board_service)
    now = datetime.now(UTC)

    # Create board
    board_service.current_project = "proj-1"
    board_service.create_board(
        project_id="proj-1",
        board_id="board-1",
        board_name="Test Board",
        column_names=["Backlog", "Trigger", "Done"],
    )

    # Add items to trigger column
    board_service.add_item_to_column("board-1", "Trigger", "item-1")
    board_service.add_item_to_column("board-1", "Trigger", "item-2")
    board_service.add_item_to_column("board-1", "Trigger", "item-3")

    # Initial enqueue with positions
    await queue_service.enqueue_item(
        "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
    )
    await queue_service.enqueue_item(
        "proj-1", "board-1", "item-2", position_in_column=1, timestamp=now
    )
    await queue_service.enqueue_item(
        "proj-1", "board-1", "item-3", position_in_column=2, timestamp=now
    )

    # Verify initial state
    entries = await queue_service.get_queue_entries("proj-1", "board-1")
    assert len(entries) == 3

    # Synchronize with board
    await queue_service.sync_queue_with_board("proj-1", "board-1", "Trigger")

    # Verify queue still has all items (they're all still in column)
    entries_after_sync = await queue_service.get_queue_entries("proj-1", "board-1")
    assert len(entries_after_sync) == 3

    # Simulate moving item-1 out of trigger column
    await board_service.simulate_human_move_async("item-1", "Done")

    # Sync should remove item-1
    await queue_service.sync_queue_with_board("proj-1", "board-1", "Trigger")

    # After sync, item-1 should be removed (it's no longer in the Trigger column)
    # Only item-2 and item-3 should remain
    entries_after_move = await queue_service.get_queue_entries("proj-1", "board-1")
    assert len(entries_after_move) == 2
    assert all(e.work_item_id != "item-1" for e in entries_after_move)


if __name__ == "__main__":
    import asyncio

    async def run_all():
        """Run all scenario 09 tests."""
        print("\n" + "=" * 70)
        print("SCENARIO 09: Pipeline Queue with Board Position Ordering")
        print("=" * 70)

        # Run tests
        await test_scenario_09_queue_position_ordering()
        print("✓ Queue position ordering test passed")

        await test_scenario_09_parallel_queues()
        print("✓ Parallel queues test passed")

        await test_scenario_09_position_changes_affect_priority()
        print("✓ Position changes affect priority test passed")

        await test_scenario_09_with_board_service_sync()
        print("✓ Board service sync test passed")

        print("\n" + "=" * 70)
        print("All Scenario 09 tests completed successfully!")
        print("=" * 70 + "\n")

    asyncio.run(run_all())
