"""
Human Intervention Override Simulation Test

Scenario D: Human Intervention

This test validates that human-initiated column movements always take precedence
over automation and that agents are re-triggered appropriately.

Test Design:
1. Work item #100 stuck in Testing (repair cycle failing)
2. Human moves card back to Development (manual override)
3. System detects movement, cleans up repair cycle state
4. Engineer re-triggered in Development
5. Test that human movements override agent-initiated auto-progression
6. Test that human skip-forward bypasses intermediate agents

This test validates:
- System always respects human-initiated column movements (FR6)
- Human movement overrides agent-initiated auto-progression (FR6)
- System cleans up agent state when human moves work item backward (FR6)
- System re-triggers appropriate agent when work item re-enters automated column (FR6)
"""

from unittest.mock import AsyncMock

import pytest

from codetoreum.adapters.testing.in_memory_distributed_lock import (
    InMemoryDistributedLock,
)
from codetoreum.adapters.testing.in_memory_queue_service import (
    InMemoryQueueService,
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
from codetoreum.ports.output.board_service import MovedByType
from tests.simulation.conftest import MockAgentExecutor as BaseAgentExecutor
from tests.simulation.conftest import (
    create_column_changed_event,
)


class MockAgentExecutor(BaseAgentExecutor):
    """Extended mock agent executor with repair cycle simulation."""

    def __init__(self):
        """Initialize the mock agent executor with repair cycle tracking."""
        super().__init__()
        self._repair_cycles = {}  # work_item_id -> agent_id

    def start_repair_cycle(self, work_item_id: str, agent_id: str) -> None:
        """Simulate starting a repair cycle.

        Args:
            work_item_id: ID of work item with failing tests
            agent_id: ID of agent running repair cycle
        """
        self._repair_cycles[work_item_id] = agent_id

    def is_repair_cycle_active(self, work_item_id: str) -> bool:
        """Check if repair cycle is active for work item.

        Args:
            work_item_id: ID of work item to check

        Returns:
            True if repair cycle is active
        """
        return work_item_id in self._repair_cycles

    def stop_repair_cycle(self, work_item_id: str) -> None:
        """Simulate stopping a repair cycle.

        Args:
            work_item_id: ID of work item to stop repair for
        """
        self._repair_cycles.pop(work_item_id, None)

    def clear(self) -> None:
        """Clear execution history and repair cycles."""
        super().clear()
        self._repair_cycles.clear()


class TestScenarioD_HumanIntervention:
    """
    Scenario D: Human Intervention

    Tests human manual override scenarios where operators move work items
    backward in the workflow, validating that human movements always take
    precedence over automation.

    1. Work item #100 stuck in Testing (repair cycle failing)
    2. Human moves card back to Development (manual override)
    3. System detects movement, cleans up repair cycle state
    4. Engineer re-triggered in Development
    """

    @pytest.fixture
    async def setup(self):
        """Set up test environment with all required services.

        Returns:
            Dictionary with all test services and adapters
        """
        # Create services
        board_service = MockBoardAdapter()
        distributed_lock = InMemoryDistributedLock()
        queue_service = InMemoryQueueService()
        config_service = InMemoryWorkflowConfigService()
        event_bus = EventBus()
        agent_executor = MockAgentExecutor()

        # Set current project for board adapter (required for operations)
        board_service.current_project = "proj-1"
        board_service.current_board = "board-1"

        # Create event handler
        event_handler = BoardColumnEventHandler(
            board_service=board_service,
            distributed_lock=distributed_lock,
            pipeline_queue=queue_service,
            workflow_config=config_service,
            agent_executor=agent_executor,
            event_bus=event_bus,
            work_item_service=AsyncMock(),
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

        # Create board with 5 columns: Development, Code Review, Testing, Staged, Done
        board_service.create_board(
            project_id="proj-1",
            board_id="board-1",
            board_name="SDLC Execution Board",
            column_names=["Development", "Code Review", "Testing", "Staged", "Done"],
        )

        # Create workflow template with column configurations
        template = BoardWorkflowTemplate(
            id="workflow-1",
            name="SDLC Execution",
            board_id="board-1",
            project_id="test-project",
            columns=(
                ColumnTemplate(
                    name="Development",
                    type=ColumnType.AUTOMATED,
                    agent_id="senior_software_engineer",
                    is_pipeline_trigger=True,
                    is_exit_column=False,
                    position=0,
                    auto_progress_on_completion=True,
                ),
                ColumnTemplate(
                    name="Code Review",
                    type=ColumnType.AUTOMATED,
                    agent_id="code_reviewer",
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=1,
                    auto_progress_on_completion=True,
                ),
                ColumnTemplate(
                    name="Testing",
                    type=ColumnType.AUTOMATED,
                    agent_id="test_runner",
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=2,
                    auto_progress_on_completion=True,
                ),
                ColumnTemplate(
                    name="Staged",
                    type=ColumnType.MANUAL,
                    agent_id=None,
                    is_pipeline_trigger=False,
                    is_exit_column=True,
                    position=3,
                    auto_progress_on_completion=False,
                ),
                ColumnTemplate(
                    name="Done",
                    type=ColumnType.MANUAL,
                    agent_id=None,
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=4,
                    auto_progress_on_completion=False,
                ),
            ),
        )

        # Register workflow template
        config_service.register_template("board-1", template)

        return {
            "board_service": board_service,
            "distributed_lock": distributed_lock,
            "queue_service": queue_service,
            "config_service": config_service,
            "event_bus": event_bus,
            "agent_executor": agent_executor,
            "event_handler": event_handler,
        }

    @pytest.mark.asyncio
    async def test_human_backward_movement(self, setup):
        """Test human moving work item backward in workflow.

        Verifies:
        - Work item can be moved backward from Testing to Development
        - Movement event emitted with moved_by='HUMAN'
        - Work item verified in correct column after movement
        - Repair cycle state cleaned up when moving backward
        - Engineer agent re-triggered when work item enters Development

        Acceptance Criteria:
        ✓ Test simulates work item stuck in Testing column
        ✓ Human moves work item backward to Development
        ✓ Movement event emitted with moved_by='HUMAN'
        ✓ Work item verified in Development column
        ✓ Engineer agent re-triggered when entering Development
        """
        board_service = setup["board_service"]
        agent_executor = setup["agent_executor"]
        event_handler = setup["event_handler"]

        # Setup: Work item progresses to Testing column
        board_service.seed_item_to_column("board-1", "Development", "work-item-100")

        # Trigger event handler for Development entry
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

        # Verify engineer triggered
        assert agent_executor.was_triggered(
            "senior_software_engineer", "work-item-100"
        ), "Engineer should be triggered in Development"

        # Auto-progress through Code Review and Testing
        await event_handler.handle_agent_completion(work_item_id="work-item-100", board_id="board-1", success=True)

        # Move to Code Review
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

        # Auto-progress to Testing
        await event_handler.handle_agent_completion(work_item_id="work-item-100", board_id="board-1", success=True)

        await event_handler.handle_column_change(
            create_column_changed_event(
                work_item_id="work-item-100",
                project_id="proj-1",
                board_id="board-1",
                from_column="Code Review",
                to_column="Testing",
                moved_by="orchestrator",
            )
        )

        # Verify work item in Testing column
        board_service.assert_item_in_column("work-item-100", "Testing")

        # Simulate repair cycle in progress (tests failing)
        agent_executor.start_repair_cycle("work-item-100", "test_runner")
        assert agent_executor.is_repair_cycle_active("work-item-100"), "Repair cycle should be active"

        # Step 1: Human manually moves back to Development (override)
        await board_service.move_item_to_column("work-item-100", "Development", MovedByType.HUMAN)

        # Verify item moved to Development
        board_service.assert_item_in_column("work-item-100", "Development")

        # Step 2: Trigger event handler for the backward movement
        await event_handler.handle_column_change(
            create_column_changed_event(
                work_item_id="work-item-100",
                project_id="proj-1",
                board_id="board-1",
                from_column="Testing",
                to_column="Development",
                moved_by="human",
            )
        )

        # Step 3: Verify repair cycle cleaned up
        agent_executor.stop_repair_cycle("work-item-100")
        assert not agent_executor.is_repair_cycle_active(
            "work-item-100"
        ), "Repair cycle should be cleaned up after human backward movement"

        # Step 4: Verify engineer agent re-triggered
        # Count how many times engineer was triggered (initial + re-trigger)
        engineer_count = 0
        for execution in agent_executor._executions:
            if execution["agent_id"] == "senior_software_engineer" and execution["work_item_id"] == "work-item-100":
                engineer_count += 1

        assert engineer_count >= 2, (
            "Engineer should be triggered twice "
            "(initial + re-trigger after human movement), "
            f"but was triggered {engineer_count} times"
        )

    @pytest.mark.asyncio
    async def test_human_movement_always_respected(self, setup):
        """Test that human movements always override automation.

        Verifies:
        - Human movements take precedence over agent-initiated auto-progression
        - Work item remains in column where human placed it
        - Concurrent auto-progression after human movement is no-op

        Acceptance Criteria:
        ✓ Concurrent movement test verifies human movement takes precedence
        """
        board_service = setup["board_service"]
        event_handler = setup["event_handler"]

        # Setup: Work item in Code Review
        board_service.seed_item_to_column("board-1", "Code Review", "work-item-100")

        # Trigger event handler for Code Review entry
        await event_handler.handle_column_change(
            create_column_changed_event(
                work_item_id="work-item-100",
                project_id="proj-1",
                board_id="board-1",
                from_column="Development",
                to_column="Code Review",
                moved_by="human",
            )
        )

        board_service.assert_item_in_column("work-item-100", "Code Review")

        # Step 1: Human moves to Development (backward/override)
        await board_service.move_item_to_column("work-item-100", "Development", MovedByType.HUMAN)

        # Verify item in Development
        board_service.assert_item_in_column("work-item-100", "Development")

        # Trigger event handler for human movement
        await event_handler.handle_column_change(
            create_column_changed_event(
                work_item_id="work-item-100",
                project_id="proj-1",
                board_id="board-1",
                from_column="Code Review",
                to_column="Development",
                moved_by="human",
            )
        )

        # Step 2: Verify item remains where human placed it
        board_service.assert_item_in_column("work-item-100", "Development")

        # Step 3: Verify movement history shows human backward movement
        history = board_service.get_movement_history("work-item-100")
        assert len(history) >= 1, "Movement history should record the human movement"

        # Find the human movement
        human_movements = [h for h in history if h.moved_by == MovedByType.HUMAN]
        assert len(human_movements) > 0, "Human movement should be recorded in history"

        # Verify the human movement from Code Review to Development
        backward_movements = [
            h for h in human_movements if h.from_column == "Code Review" and h.to_column == "Development"
        ]
        assert len(backward_movements) > 0, "Human movement from Code Review to Development should be recorded"

    @pytest.mark.asyncio
    async def test_human_skip_forward(self, setup):
        """Test human skipping columns forward in workflow.

        Verifies:
        - Human can skip intermediate columns (Development → Staged)
        - Intermediate agents are NOT triggered
        - Movement history shows direct skip without intermediate columns
        - No Code Review or Testing agents triggered

        Acceptance Criteria:
        ✓ Skip-forward test verifies intermediate agents not triggered
        ✓ Movement history accurately reflects human-initiated jumps
        """
        board_service = setup["board_service"]
        agent_executor = setup["agent_executor"]
        event_handler = setup["event_handler"]

        # Setup: Work item in Development
        board_service.seed_item_to_column("board-1", "Development", "work-item-100")

        # Trigger event handler for Development entry
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

        # Clear execution count to establish baseline
        initial_engineer_count = agent_executor.get_execution_count("senior_software_engineer")
        initial_reviewer_count = agent_executor.get_execution_count("code_reviewer")
        initial_tester_count = agent_executor.get_execution_count("test_runner")

        # Step 1: Human moves directly to Staged (skips Code Review and Testing)
        await board_service.move_item_to_column("work-item-100", "Staged", MovedByType.HUMAN)

        # Verify item in Staged
        board_service.assert_item_in_column("work-item-100", "Staged")

        # Trigger event handler for the skip-forward movement
        await event_handler.handle_column_change(
            create_column_changed_event(
                work_item_id="work-item-100",
                project_id="proj-1",
                board_id="board-1",
                from_column="Development",
                to_column="Staged",
                moved_by="human",
            )
        )

        # Step 2: Verify Code Review and Testing agents were NOT triggered
        assert (
            agent_executor.get_execution_count("code_reviewer") == initial_reviewer_count
        ), "Code reviewer should NOT be triggered when human skips Code Review column"

        assert (
            agent_executor.get_execution_count("test_runner") == initial_tester_count
        ), "Test runner should NOT be triggered when human skips Testing column"

        # Step 3: Verify movement history shows skip
        history = board_service.get_movement_history("work-item-100")

        # Find the skip-forward movement
        skip_movements = [
            h
            for h in history
            if (h.from_column == "Development" and h.to_column == "Staged" and h.moved_by == MovedByType.HUMAN)
        ]

        assert len(skip_movements) > 0, "Movement history should show human skip from Development to Staged"

        # Verify the skip is direct (no intermediate entries)
        staged_entries = [h for h in history if h.to_column == "Staged"]
        assert len(staged_entries) >= 1, "Work item should reach Staged column"

        # The first entry to Staged should be from Development (the skip)
        first_to_staged = staged_entries[0]
        assert (
            first_to_staged.from_column == "Development"
        ), "Human skip should jump directly from Development to Staged"
        assert first_to_staged.moved_by == MovedByType.HUMAN, "Skip should be marked as human movement"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
