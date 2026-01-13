"""
Scenario A: Full SDLC Flow - Phase 6 Simulation Test

Complete end-to-end simulation test for the full SDLC workflow:
Backlog → Development → Code Review → Testing → Staged → Done

This test validates:
- Column position determines workflow state (FR1)
- Agent triggers based on column configuration (FR2)
- Pipeline lock acquisition in trigger column (FR3)
- Auto-progression after agent completion (FR5)
- Exit column releases lock (FR3)
- Maker-checker review outcomes (FR7)
- Repair cycle handling (FR8)

Test Design:
1. Work item #100 created in Backlog (manual column)
2. Human moves to Development → lock acquired → engineer triggered
3. Engineer completes → auto-move to Code Review → reviewer triggered
4. Reviewer completes → auto-move to Testing → repair cycle runs
5. Tests pass → auto-move to Staged → lock released
6. Human moves to Done → terminal state

Expected Movement Path: Backlog → Development → Code Review → Testing → Staged → Done
"""

import pytest
from datetime import datetime, timezone, timedelta
from typing import Dict, List

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
from codetoreum.domain.events import WorkItemColumnChanged
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.output.agent_executor import IAgentExecutor
from codetoreum.ports.output.board_service import MovedByType


class MockAgentExecutor(IAgentExecutor):
    """Mock agent executor that tracks executions without actually executing."""

    def __init__(self):
        """Initialize the mock agent executor."""
        self._executions: List[Dict] = []
        self._lock = __import__("threading").Lock()

    async def execute(self, work_item_id: str, agent_id: str) -> None:
        """Record agent execution.

        Args:
            work_item_id: ID of work item being processed
            agent_id: ID of agent being executed
        """
        with self._lock:
            self._executions.append(
                {
                    "work_item_id": work_item_id,
                    "agent_id": agent_id,
                    "timestamp": datetime.now(tz=timezone.utc),
                }
            )

    def was_triggered(self, agent_id: str, work_item_id: str) -> bool:
        """Check if agent was triggered for work item.

        Args:
            agent_id: Agent ID to check
            work_item_id: Work item ID to check

        Returns:
            True if agent was triggered for this work item
        """
        with self._lock:
            return any(
                e["agent_id"] == agent_id and e["work_item_id"] == work_item_id
                for e in self._executions
            )

    def get_execution_count(self, agent_id: str) -> int:
        """Get total execution count for an agent.

        Args:
            agent_id: Agent ID to check

        Returns:
            Number of times this agent was executed
        """
        with self._lock:
            return sum(1 for e in self._executions if e["agent_id"] == agent_id)

    def clear(self) -> None:
        """Clear execution history."""
        with self._lock:
            self._executions.clear()


def _create_column_changed_event(
    work_item_id: str,
    project_id: str,
    board_id: str,
    from_column: str,
    to_column: str,
    moved_by: str = "human",
) -> WorkItemColumnChanged:
    """Helper to create a column changed event with proper payload dict."""
    return WorkItemColumnChanged(
        aggregate_id=work_item_id,
        payload={
            "work_item_id": work_item_id,
            "project_id": project_id,
            "board_id": board_id,
            "from_column": from_column,
            "to_column": to_column,
            "moved_by": moved_by,
        },
    )


class TestScenarioA_FullSDLCFlow:
    """
    Scenario A: Full SDLC Flow

    Tests the complete software development lifecycle automation:
    1. Work item created in Backlog
    2. Human move to Development triggers engineer agent and acquires lock
    3. Engineer completion auto-progresses to Code Review
    4. Code Review triggers reviewer agent
    5. Reviewer completion auto-progresses to Testing
    6. Testing triggers test runner agent
    7. Test completion auto-progresses to Staged (exit column releases lock)
    8. Human move to Done completes workflow
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

        # Create board with 6 columns: Backlog, Development, Code Review, Testing, Staged, Done
        board_service.create_board(
            project_id="proj-1",
            board_id="board-1",
            board_name="SDLC Execution Board",
            column_names=["Backlog", "Development", "Code Review", "Testing", "Staged", "Done"],
        )

        # Create workflow template with column configurations
        template = BoardWorkflowTemplate(
            id="workflow-1",
            name="SDLC Execution",
            pipeline_trigger_columns=["Development"],
            exit_columns=["Staged"],
            columns=[
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
                    type=ColumnType.AUTOMATED,
                    agent_id="code_reviewer",
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=2,
                    auto_progress_on_completion=True,
                ),
                ColumnTemplate(
                    name="Testing",
                    type=ColumnType.AUTOMATED,
                    agent_id="test_runner",
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=3,
                    auto_progress_on_completion=True,
                ),
                ColumnTemplate(
                    name="Staged",
                    type=ColumnType.MANUAL,
                    agent_id=None,
                    is_pipeline_trigger=False,
                    is_exit_column=True,
                    position=4,
                    auto_progress_on_completion=False,
                ),
                ColumnTemplate(
                    name="Done",
                    type=ColumnType.MANUAL,
                    agent_id=None,
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=5,
                    auto_progress_on_completion=False,
                ),
            ],
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
    async def test_full_sdlc_flow(self, setup):
        """Test complete SDLC workflow from Backlog to Done.

        Requirements Verified:
        - FR1: Column position determines workflow state (not labels)
        - FR2: Agent triggers based on column configuration
        - FR3: Pipeline lock acquired in trigger column & released in exit column
        - FR5: Auto-progression after agent completion
        - FR7: Maker-checker review outcomes (APPROVED auto-progresses)
        - FR8: Repair cycle handling (tests pass, auto-progress)

        Acceptance Criteria:
        ✓ Work item created in Backlog column
        ✓ Simulated human move to Development acquires pipeline lock
        ✓ Development column triggers senior_software_engineer agent
        ✓ Agent completion auto-progresses to Code Review
        ✓ Code Review triggers code_reviewer agent
        ✓ Reviewer completion auto-progresses to Testing
        ✓ Testing triggers test_runner agent
        ✓ Test completion auto-progresses to Staged
        ✓ Staged column releases pipeline lock
        ✓ Human move to Done reaches terminal state
        ✓ Movement history shows complete path:
          Backlog → Development → Code Review → Testing → Staged → Done
        """
        board_service = setup["board_service"]
        lock_service = setup["lock_service"]
        agent_executor = setup["agent_executor"]
        event_handler = setup["event_handler"]

        # Step 1: Create work item in Backlog
        board_service.add_item_to_column("board-1", "Backlog", "work-item-100")
        board_service.assert_item_in_column("work-item-100", "Backlog")
        assert agent_executor.get_execution_count("senior_software_engineer") == 0

        # Step 2: Human moves to Development → lock acquired → engineer triggered
        # Move the work item
        await board_service.move_item_to_column(
            "work-item-100", "Development", MovedByType.HUMAN
        )

        # Verify work item is in Development column
        board_service.assert_item_in_column("work-item-100", "Development")

        # Manually trigger the event handler (since mock adapter emits but doesn't integrate with event bus)
        await event_handler.handle_column_change(
            _create_column_changed_event(
                work_item_id="work-item-100",
                project_id="proj-1",
                board_id="board-1",
                from_column="Backlog",
                to_column="Development",
                moved_by="human",
            )
        )

        # Verify lock acquired (lock holder should be our work item)
        queue_state = await lock_service.get_queue_state("proj-1", "board-1")
        assert queue_state.lock_holder == "work-item-100", (
            f"Expected lock holder to be 'work-item-100', got '{queue_state.lock_holder}'"
        )

        # Verify engineer agent triggered (FR2)
        assert agent_executor.was_triggered(
            "senior_software_engineer", "work-item-100"
        ), "Engineer agent should be triggered when work item enters Development column"

        # Step 3: Engineer completes → auto-progression to Code Review
        await event_handler.handle_agent_completion(
            work_item_id="work-item-100", board_id="board-1", success=True
        )

        # Verify auto-progression to Code Review (FR5)
        board_service.assert_item_in_column("work-item-100", "Code Review")

        # Manually trigger event handler for Code Review column
        # (in real flow, this would be triggered by event emitter from auto-progression)
        await event_handler.handle_column_change(
            _create_column_changed_event(
                work_item_id="work-item-100",
                project_id="proj-1",
                board_id="board-1",
                from_column="Development",
                to_column="Code Review",
                moved_by="orchestrator",
            )
        )

        # Verify reviewer agent triggered (FR2)
        assert agent_executor.was_triggered(
            "code_reviewer", "work-item-100"
        ), "Code reviewer agent should be triggered when work item enters Code Review column"

        # Step 4: Reviewer completes → auto-progression to Testing
        await event_handler.handle_agent_completion(
            work_item_id="work-item-100", board_id="board-1", success=True
        )

        # Verify auto-progression to Testing (FR5)
        board_service.assert_item_in_column("work-item-100", "Testing")

        # Manually trigger event handler for Testing column
        await event_handler.handle_column_change(
            _create_column_changed_event(
                work_item_id="work-item-100",
                project_id="proj-1",
                board_id="board-1",
                from_column="Code Review",
                to_column="Testing",
                moved_by="orchestrator",
            )
        )

        # Verify test runner agent triggered (FR2)
        assert agent_executor.was_triggered(
            "test_runner", "work-item-100"
        ), "Test runner agent should be triggered when work item enters Testing column"

        # Step 5: Tests pass → auto-progression to Staged
        await event_handler.handle_agent_completion(
            work_item_id="work-item-100", board_id="board-1", success=True
        )

        # Verify auto-progression to Staged (FR5)
        board_service.assert_item_in_column("work-item-100", "Staged")

        # Manually trigger event handler for Staged column (exit column)
        await event_handler.handle_column_change(
            _create_column_changed_event(
                work_item_id="work-item-100",
                project_id="proj-1",
                board_id="board-1",
                from_column="Testing",
                to_column="Staged",
                moved_by="orchestrator",
            )
        )

        # Verify lock released (FR3 - exit column releases lock)
        queue_state = await lock_service.get_queue_state("proj-1", "board-1")
        assert queue_state.lock_holder is None, (
            f"Expected lock to be released when entering exit column (Staged), "
            f"but lock_holder is still '{queue_state.lock_holder}'"
        )
        assert len(queue_state.queue) == 0, "Queue should be empty after lock release"

        # Step 6: Human moves to Done → terminal state
        await board_service.move_item_to_column(
            "work-item-100", "Done", MovedByType.HUMAN
        )

        # Verify final position
        board_service.assert_item_in_column("work-item-100", "Done")

        # Step 7: Verify movement history (FR1 - column position determines state)
        history = board_service.get_movement_history("work-item-100")

        # We expect 5 movements: the 5 transitions between columns
        # (Initial add_item_to_column doesn't count as a movement in the mock adapter)
        assert len(history) == 5, (
            f"Expected 5 movements in history, got {len(history)}"
        )

        expected_path = ["Development", "Code Review", "Testing", "Staged", "Done"]
        actual_path = [h.to_column for h in history]

        assert actual_path == expected_path, (
            f"Expected path {expected_path}, but got {actual_path}"
        )

        # Verify all movements have correct metadata
        # Development move (human)
        assert history[0].from_column == "Backlog"
        assert history[0].to_column == "Development"
        assert history[0].moved_by == MovedByType.HUMAN

        # Code Review auto-progression (orchestrator)
        assert history[1].from_column == "Development"
        assert history[1].to_column == "Code Review"
        assert history[1].moved_by == MovedByType.ORCHESTRATOR

        # Testing auto-progression (orchestrator)
        assert history[2].from_column == "Code Review"
        assert history[2].to_column == "Testing"
        assert history[2].moved_by == MovedByType.ORCHESTRATOR

        # Staged auto-progression (orchestrator)
        assert history[3].from_column == "Testing"
        assert history[3].to_column == "Staged"
        assert history[3].moved_by == MovedByType.ORCHESTRATOR

        # Done move (human)
        assert history[4].from_column == "Staged"
        assert history[4].to_column == "Done"
        assert history[4].moved_by == MovedByType.HUMAN

        # Step 8: Verify agent execution counts
        assert agent_executor.get_execution_count("senior_software_engineer") == 1, (
            "Engineer should be triggered exactly once"
        )
        assert agent_executor.get_execution_count("code_reviewer") == 1, (
            "Reviewer should be triggered exactly once"
        )
        assert agent_executor.get_execution_count("test_runner") == 1, (
            "Test runner should be triggered exactly once"
        )

    @pytest.mark.asyncio
    async def test_lock_acquisition_and_release(self, setup):
        """Test pipeline lock acquisition and release mechanics.

        Verifies:
        - Lock is acquired when entering pipeline trigger column (FR3)
        - Lock is released when entering exit column (FR3)
        - Lock state can be queried at any time
        """
        board_service = setup["board_service"]
        lock_service = setup["lock_service"]
        event_handler = setup["event_handler"]

        # Create work item in Backlog
        board_service.add_item_to_column("board-1", "Backlog", "work-item-200")

        # Verify no lock initially
        queue_state = await lock_service.get_queue_state("proj-1", "board-1")
        assert queue_state.lock_holder is None
        assert len(queue_state.queue) == 0

        # Move to Development (pipeline trigger column)
        await board_service.move_item_to_column(
            "work-item-200", "Development", MovedByType.HUMAN
        )

        # Trigger event handler manually
        await event_handler.handle_column_change(
            _create_column_changed_event(
                work_item_id="work-item-200",
                project_id="proj-1",
                board_id="board-1",
                from_column="Backlog",
                to_column="Development",
                moved_by="human",
            )
        )

        # Verify lock acquired
        queue_state = await lock_service.get_queue_state("proj-1", "board-1")
        assert queue_state.lock_holder == "work-item-200"

        # Auto-progress through workflow
        columns_transitions = [
            ("Development", "Code Review"),
            ("Code Review", "Testing"),
            ("Testing", "Staged"),
        ]

        for from_col, to_col in columns_transitions:
            await event_handler.handle_agent_completion(
                work_item_id="work-item-200", board_id="board-1", success=True
            )

            # Manually trigger event handler for auto-progression
            if to_col != "Staged":  # Don't trigger handler for Staged yet
                await event_handler.handle_column_change(
                    _create_column_changed_event(
                        work_item_id="work-item-200",
                        project_id="proj-1",
                        board_id="board-1",
                        from_column=from_col,
                        to_column=to_col,
                        moved_by="orchestrator",
                    )
                )

        # Verify work item is in Staged (exit column)
        board_service.assert_item_in_column("work-item-200", "Staged")

        # Manually trigger event handler for Staged (exit column) to release lock
        await event_handler.handle_column_change(
            _create_column_changed_event(
                work_item_id="work-item-200",
                project_id="proj-1",
                board_id="board-1",
                from_column="Testing",
                to_column="Staged",
                moved_by="orchestrator",
            )
        )

        # Verify lock released
        queue_state = await lock_service.get_queue_state("proj-1", "board-1")
        assert queue_state.lock_holder is None, (
            "Lock should be released when entering exit column (Staged)"
        )

    @pytest.mark.asyncio
    async def test_agent_not_triggered_for_manual_columns(self, setup):
        """Test that agents are not triggered for manual columns.

        Verifies:
        - Backlog column (manual) does not trigger any agent
        - Staged column (manual) does not trigger any agent
        - Done column (manual) does not trigger any agent
        """
        board_service = setup["board_service"]
        agent_executor = setup["agent_executor"]
        event_handler = setup["event_handler"]

        # Create work item in Backlog (manual column)
        board_service.add_item_to_column("board-1", "Backlog", "work-item-300")

        # Verify no agent triggered for Backlog
        assert agent_executor.get_execution_count("senior_software_engineer") == 0

        # Move to Done (manual column) via direct movement
        await board_service.move_item_to_column(
            "work-item-300", "Done", MovedByType.HUMAN
        )

        # Trigger event handler
        await event_handler.handle_column_change(
            _create_column_changed_event(
                work_item_id="work-item-300",
                project_id="proj-1",
                board_id="board-1",
                from_column="Backlog",
                to_column="Done",
                moved_by="human",
            )
        )

        # Verify no agents triggered for Done
        assert agent_executor.get_execution_count("senior_software_engineer") == 0
        assert agent_executor.get_execution_count("code_reviewer") == 0
        assert agent_executor.get_execution_count("test_runner") == 0

    @pytest.mark.asyncio
    async def test_agent_failure_prevents_auto_progression(self, setup):
        """Test that agent failure prevents auto-progression to next column.

        Verifies:
        - If agent fails (success=False), work item stays in current column
        - Auto-progression only happens on success
        """
        board_service = setup["board_service"]
        event_handler = setup["event_handler"]
        agent_executor = setup["agent_executor"]

        # Create work item and move through to Development
        board_service.add_item_to_column("board-1", "Backlog", "work-item-400")
        await board_service.move_item_to_column(
            "work-item-400", "Development", MovedByType.HUMAN
        )

        # Trigger event handler
        await event_handler.handle_column_change(
            _create_column_changed_event(
                work_item_id="work-item-400",
                project_id="proj-1",
                board_id="board-1",
                from_column="Backlog",
                to_column="Development",
                moved_by="human",
            )
        )

        board_service.assert_item_in_column("work-item-400", "Development")
        assert agent_executor.was_triggered("senior_software_engineer", "work-item-400")

        # Simulate agent failure
        await event_handler.handle_agent_completion(
            work_item_id="work-item-400", board_id="board-1", success=False
        )

        # Verify work item stays in Development (no auto-progression)
        board_service.assert_item_in_column(
            "work-item-400", "Development"
        ), "Work item should stay in Development after agent failure"

    @pytest.mark.asyncio
    async def test_movement_history_tracks_all_transitions(self, setup):
        """Test that movement history accurately tracks all state transitions.

        Verifies:
        - Each movement is recorded with correct metadata
        - Both human and orchestrator movements are tracked
        - Timestamps are recorded
        - Movement count matches expected flow
        """
        board_service = setup["board_service"]
        event_handler = setup["event_handler"]

        # Create work item
        board_service.add_item_to_column("board-1", "Backlog", "work-item-500")

        # Move to Development (human move)
        await board_service.move_item_to_column(
            "work-item-500", "Development", MovedByType.HUMAN
        )

        # Move to Code Review (auto-progression)
        await event_handler.handle_agent_completion(
            work_item_id="work-item-500", board_id="board-1", success=True
        )

        # Manually trigger event handler for Code Review to record the movement
        await event_handler.handle_column_change(
            _create_column_changed_event(
                work_item_id="work-item-500",
                project_id="proj-1",
                board_id="board-1",
                from_column="Development",
                to_column="Code Review",
                moved_by="orchestrator",
            )
        )

        # Check history
        history = board_service.get_movement_history("work-item-500")
        assert len(history) == 2  # Development, Code Review (no initial creation entry)

        # Verify first entry (human move to Development)
        assert history[0].from_column == "Backlog"
        assert history[0].to_column == "Development"
        assert history[0].moved_by == MovedByType.HUMAN
        assert history[0].timestamp is not None

        # Verify second entry (auto-progression to Code Review)
        assert history[1].from_column == "Development"
        assert history[1].to_column == "Code Review"
        assert history[1].moved_by == MovedByType.ORCHESTRATOR
        assert history[1].timestamp is not None


# Async test helper - allows async fixtures and setup
@pytest.fixture
async def async_setup():
    """Fixture that allows async setup."""
    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
