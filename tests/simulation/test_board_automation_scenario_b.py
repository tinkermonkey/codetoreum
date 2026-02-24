"""
Pipeline Lock Contention Simulation Test

Complete simulation test for pipeline lock contention where multiple work items
attempt to enter the Development column.

This test validates:
- Pipeline lock acquired in trigger column (FR3)
- Lock contention adds work items to queue (FR3)
- Queue ordering by board position (FR4)
- Topmost work item has highest priority (FR4)
- Lock release grants lock to next in queue (FR3)
- Queue order updates when humans reorder cards (FR4)

Test Design:
1. Work item #100 in Development (holds lock)
2. Human moves #101 to Development → added to queue
3. Human moves #102 to Development → added to queue (position 2)
4. #100 completes, moves to Code Review → lock released
5. #101 acquires lock (was first in queue)
6. #102 still waiting in queue
7. Human reorders #102 to top → queue order updates
8. #101 completes, releases lock
9. #102 acquires lock (new first in queue)
"""

import pytest

from codetoreum.adapters.secondary.in_memory_queue_lock_service import (
    InMemoryLockService,
)
from codetoreum.adapters.testing.in_memory_workflow_config_service import (
    InMemoryWorkflowConfigService,
)
from codetoreum.adapters.testing.mock_board_adapter import MockBoardAdapter
from codetoreum.application.event_handlers.board_event_handler import (
    BoardColumnEventHandler,
)
from codetoreum.domain.board_workflow_template import (
    BoardWorkflowTemplate,
    ColumnTemplate,
    ColumnType,
)
from codetoreum.infrastructure.event_bus import EventBus
from tests.simulation.conftest import MockAgentExecutor, create_column_changed_event


class TestScenarioB_LockContention:
    """
    Scenario B: Lock Contention

    Tests the pipeline lock queue mechanism when multiple work items
    attempt to enter the Development trigger column:

    1. Work item #100 in Development (holds lock)
    2. Human moves #101 to Development → added to queue
    3. Human moves #102 to Development → added to queue (position 2)
    4. #100 completes, moves to Code Review → lock released
    5. #101 acquires lock (was first in queue)
    6. #102 still waiting in queue
    7. Human reorders #102 to top → queue order updates
    8. #101 completes, releases lock
    9. #102 acquires lock (new first in queue)
    """

    @pytest.fixture
    async def setup(self):
        """Set up test environment with all required services.

        Returns:
            Dictionary with all test services and adapters
        """
        # Create services
        board_service = MockBoardAdapter()
        lock_service = InMemoryLockService()
        config_service = InMemoryWorkflowConfigService()
        event_bus = EventBus()
        agent_executor = MockAgentExecutor()

        # Set current project for board adapter (required for operations)
        board_service.current_project = "proj-1"
        board_service.current_board = "board-1"

        # Create event handler
        event_handler = BoardColumnEventHandler(
            board_service=board_service,
            lock_service=lock_service,
            workflow_config=config_service,
            agent_executor=agent_executor,
            event_bus=event_bus,
        )

        # Register event handler with bus
        event_bus.register_handler(event_handler)

        # Register event handler with board service to handle auto-progression events
        import asyncio

        def handle_column_change_event(event):
            """Sync wrapper for async event handler."""
            try:
                loop = asyncio.get_running_loop()
                # We're in an async context, schedule as task
                loop.create_task(event_handler.handle_column_change(event))
            except RuntimeError:
                # No running loop (shouldn't happen in pytest-asyncio)
                pass

        board_service.on("workitem.column_changed", handle_column_change_event)

        # Create board with 3 columns: Backlog, Development, Code Review
        board_service.create_board(
            project_id="proj-1",
            board_id="board-1",
            board_name="Lock Contention Test Board",
            column_names=["Backlog", "Development", "Code Review"],
        )

        # Create workflow template with Development as pipeline trigger
        template = BoardWorkflowTemplate(
            id="workflow-1",
            name="Lock Contention",
            pipeline_trigger_columns=("Development",),
            exit_columns=("Code Review",),
            columns=(
                ColumnTemplate(
                    name="Backlog",
                    type=ColumnType.MANUAL,
                    agent_id=None,
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=0,
                    auto_progress_on_completion=False,
                ),
                ColumnTemplate(
                    name="Development",
                    type=ColumnType.AUTOMATED,
                    agent_id="senior_software_engineer",
                    is_pipeline_trigger=True,
                    is_exit_column=False,
                    position=1,
                    auto_progress_on_completion=True,
                ),
                ColumnTemplate(
                    name="Code Review",
                    type=ColumnType.MANUAL,
                    agent_id=None,
                    is_pipeline_trigger=False,
                    is_exit_column=True,
                    position=2,
                    auto_progress_on_completion=False,
                ),
            ),
        )

        # Register workflow template
        config_service.register_template("board-1", template)

        return {
            "board_service": board_service,
            "lock_service": lock_service,
            "config_service": config_service,
            "event_bus": event_bus,
            "agent_executor": agent_executor,
            "event_handler": event_handler,
        }

    @pytest.mark.asyncio
    async def test_lock_contention_queue_ordering(self, setup):
        """Test queue ordering and lock handoff.

        Requirements Verified:
        - FR3: Pipeline lock acquired in trigger column
        - FR3: Lock contention adds work items to queue
        - FR4: Queue ordering by board position
        - FR4: Topmost work item has highest priority
        - FR3: Lock release grants lock to next in queue
        - FR4: Next queued work item moves to position 0

        Acceptance Criteria:
        ✓ Test verifies first work item acquires lock
        ✓ Second work item added to queue at position 0
        ✓ Third work item added to queue at position 1
        ✓ Queue ordering matches board position (topmost first)
        ✓ Lock release grants lock to first queued work item
        ✓ Next queued work item moves to position 0
        """
        board_service = setup["board_service"]
        lock_service = setup["lock_service"]
        agent_executor = setup["agent_executor"]
        event_handler = setup["event_handler"]

        # Step 1: Work item #100 in Development (holds lock)
        board_service.add_item_to_column("board-1", "Development", "work-item-100", position=0)

        # Manually trigger event handler to acquire lock
        await event_handler.handle_column_change(
            create_column_changed_event(
                work_item_id="work-item-100",
                project_id="proj-1",
                board_id="board-1",
                from_column="Backlog",
                to_column="Development",
                moved_by="human",
            )
        )

        queue_state = await lock_service.get_queue_state("proj-1", "board-1")
        assert queue_state.lock_holder == "work-item-100", (
            f"Expected lock holder to be 'work-item-100', got '{queue_state.lock_holder}'"
        )
        assert len(queue_state.queue) == 0, (
            f"Expected empty queue after first work item, got {len(queue_state.queue)} items"
        )

        # Verify engineer agent triggered
        assert agent_executor.was_triggered(
            "senior_software_engineer", "work-item-100"
        ), "Engineer should be triggered for first work item"

        # Step 2: Human moves #101 to Development → added to queue
        board_service.add_item_to_column("board-1", "Development", "work-item-101", position=1)

        # Manually trigger event handler
        await event_handler.handle_column_change(
            create_column_changed_event(
                work_item_id="work-item-101",
                project_id="proj-1",
                board_id="board-1",
                from_column="Backlog",
                to_column="Development",
                moved_by="human",
            )
        )

        queue_state = await lock_service.get_queue_state("proj-1", "board-1")
        assert queue_state.lock_holder == "work-item-100", (
            "Lock holder should still be work-item-100"
        )
        assert len(queue_state.queue) == 1, (
            f"Expected 1 item in queue, got {len(queue_state.queue)}"
        )
        assert queue_state.queue[0].work_item_id == "work-item-101", (
            f"Expected first queue item to be 'work-item-101', got '{queue_state.queue[0].work_item_id}'"
        )

        # Step 3: Human moves #102 to Development → added to queue (position 2)
        board_service.add_item_to_column("board-1", "Development", "work-item-102", position=2)

        # Manually trigger event handler
        await event_handler.handle_column_change(
            create_column_changed_event(
                work_item_id="work-item-102",
                project_id="proj-1",
                board_id="board-1",
                from_column="Backlog",
                to_column="Development",
                moved_by="human",
            )
        )

        queue_state = await lock_service.get_queue_state("proj-1", "board-1")
        assert len(queue_state.queue) == 2, (
            f"Expected 2 items in queue, got {len(queue_state.queue)}"
        )
        assert queue_state.queue[0].work_item_id == "work-item-101", (
            f"Expected first queue item to be 'work-item-101', got '{queue_state.queue[0].work_item_id}'"
        )
        assert queue_state.queue[1].work_item_id == "work-item-102", (
            f"Expected second queue item to be 'work-item-102', got '{queue_state.queue[1].work_item_id}'"
        )

        # Step 4: #100 completes and moves to Code Review
        await event_handler.handle_agent_completion(
            work_item_id="work-item-100", board_id="board-1", success=True
        )

        # Manually trigger event handler for Code Review (exit column)
        await event_handler.handle_column_change(
            create_column_changed_event(
                work_item_id="work-item-100",
                project_id="proj-1",
                board_id="board-1",
                from_column="Development",
                to_column="Code Review",
                moved_by="orchestrator",
            )
        )

        # Verify lock released and granted to #101
        queue_state = await lock_service.get_queue_state("proj-1", "board-1")
        assert queue_state.lock_holder == "work-item-101", (
            f"Expected lock holder to be 'work-item-101' after #100 completion, "
            f"got '{queue_state.lock_holder}'"
        )
        assert len(queue_state.queue) == 1, (
            f"Expected 1 item in queue after handoff, got {len(queue_state.queue)}"
        )
        assert queue_state.queue[0].work_item_id == "work-item-102", (
            f"Expected remaining queue item to be 'work-item-102', "
            f"got '{queue_state.queue[0].work_item_id}'"
        )

        # Verify agent triggered for #101 (which now holds lock)
        assert agent_executor.was_triggered(
            "senior_software_engineer", "work-item-101"
        ), "Engineer should be triggered when #101 acquires lock"

        # Step 5: #102 still waiting
        board_service.assert_item_in_column("work-item-102", "Development")
        queue_state = await lock_service.get_queue_state("proj-1", "board-1")
        assert queue_state.lock_holder == "work-item-101", (
            "Lock holder should still be work-item-101"
        )
        assert len(queue_state.queue) == 1, (
            "Queue should have exactly 1 waiting item (#102)"
        )

    @pytest.mark.asyncio
    async def test_queue_reordering_by_position(self, setup):
        """Test queue reordering when humans reorder cards.

        Requirements Verified:
        - FR4: Queue order updates when humans reorder cards

        Acceptance Criteria:
        ✓ Queue reordering test verifies position updates affect queue order
        ✓ Queue reordering causes different work item to acquire lock next
        """
        board_service = setup["board_service"]
        lock_service = setup["lock_service"]
        agent_executor = setup["agent_executor"]
        event_handler = setup["event_handler"]

        # Set up: #100 holds lock, #101 and #102 queued
        board_service.add_item_to_column("board-1", "Development", "work-item-100", position=0)
        board_service.add_item_to_column("board-1", "Development", "work-item-101", position=1)
        board_service.add_item_to_column("board-1", "Development", "work-item-102", position=2)

        # Simulate moves to trigger lock logic
        await event_handler.handle_column_change(
            create_column_changed_event(
                work_item_id="work-item-100",
                project_id="proj-1",
                board_id="board-1",
                from_column="Backlog",
                to_column="Development",
                moved_by="human",
            )
        )
        await event_handler.handle_column_change(
            create_column_changed_event(
                work_item_id="work-item-101",
                project_id="proj-1",
                board_id="board-1",
                from_column="Backlog",
                to_column="Development",
                moved_by="human",
            )
        )
        await event_handler.handle_column_change(
            create_column_changed_event(
                work_item_id="work-item-102",
                project_id="proj-1",
                board_id="board-1",
                from_column="Backlog",
                to_column="Development",
                moved_by="human",
            )
        )

        # Verify initial queue order
        queue_state = await lock_service.get_queue_state("proj-1", "board-1")
        assert queue_state.lock_holder == "work-item-100", (
            "Lock holder should be work-item-100"
        )
        assert queue_state.queue[0].work_item_id == "work-item-101", (
            "First queue item should be work-item-101"
        )
        assert queue_state.queue[1].work_item_id == "work-item-102", (
            "Second queue item should be work-item-102"
        )

        # Simulate human reordering: #102 moved to position 1 (after lock holder at 0)
        # This updates the board positions directly, which would normally come from
        # a board UI reordering action. The lock service then reorders its queue based
        # on these new board positions.
        await lock_service.update_queue_positions("proj-1", "board-1", {
            "work-item-102": 0,
            "work-item-101": 1,
        })

        # Verify queue reordered
        queue_state = await lock_service.get_queue_state("proj-1", "board-1")
        assert queue_state.lock_holder == "work-item-100", (
            "Lock holder should still be work-item-100"
        )
        assert queue_state.queue[0].work_item_id == "work-item-102", (
            f"After reorder, first queue item should be 'work-item-102', "
            f"got '{queue_state.queue[0].work_item_id}'"
        )
        assert queue_state.queue[1].work_item_id == "work-item-101", (
            f"After reorder, second queue item should be 'work-item-101', "
            f"got '{queue_state.queue[1].work_item_id}'"
        )

        # Release lock through event handler to properly trigger next agent
        await event_handler.handle_agent_completion(
            work_item_id="work-item-100", board_id="board-1", success=True
        )

        # Trigger exit column event to release lock
        await event_handler.handle_column_change(
            create_column_changed_event(
                work_item_id="work-item-100",
                project_id="proj-1",
                board_id="board-1",
                from_column="Development",
                to_column="Code Review",
                moved_by="orchestrator",
            )
        )

        # Verify new lock state after event handler processes release
        queue_state = await lock_service.get_queue_state("proj-1", "board-1")
        assert queue_state.lock_holder == "work-item-102", (
            f"After reorder and lock release, lock holder should be 'work-item-102', "
            f"got '{queue_state.lock_holder}'"
        )
        assert len(queue_state.queue) == 1, (
            f"Queue should have 1 remaining item, got {len(queue_state.queue)}"
        )
        assert queue_state.queue[0].work_item_id == "work-item-101", (
            f"Remaining queue item should be 'work-item-101', "
            f"got '{queue_state.queue[0].work_item_id}'"
        )

        # Verify agent triggered for #102 (which now holds lock after reorder)
        assert agent_executor.was_triggered(
            "senior_software_engineer", "work-item-102"
        ), "Engineer should be triggered when #102 acquires lock after reorder"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
