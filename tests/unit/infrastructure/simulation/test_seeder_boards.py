"""Unit tests for simulation data seeder board operations."""

from typing import AsyncGenerator

import pytest

from codetoreum.infrastructure.simulation import (
    SimulationApplicationBootstrap,
    SimulationConfig,
    SimulationDataSeeder,
)
from codetoreum.ports.exceptions import ValidationError


class TestSeederBoardOperations:
    """Test cases for board creation and item placement in SimulationDataSeeder."""

    @pytest.fixture
    async def bootstrap(self) -> AsyncGenerator[SimulationApplicationBootstrap, None]:
        """Create and setup bootstrap."""
        config = SimulationConfig.create_fast_config("test")
        bootstrap = SimulationApplicationBootstrap(config)
        await bootstrap.setup()
        yield bootstrap
        await bootstrap.teardown()

    @pytest.fixture
    async def seeder(
        self, bootstrap: SimulationApplicationBootstrap
    ) -> AsyncGenerator[SimulationDataSeeder, None]:
        """Create seeder instance with a project."""
        seeder = SimulationDataSeeder(bootstrap)
        await seeder.create_project(name="test-project", description="Test")
        yield seeder

    # =========================================================================
    # Board Creation Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_create_board(self, seeder):
        """Test creating a board with columns."""
        result = await seeder.create_board(
            board_id="board-1",
            board_name="Test Board",
            column_names=["Backlog", "Ready", "In Progress", "Done"],
        )
        assert result is seeder  # Returns self for chaining
        assert "board-1" in seeder.created_items.boards

    @pytest.mark.asyncio
    async def test_create_board_sets_adapter_context(self, seeder):
        """Test that create_board sets current_project on the adapter."""
        await seeder.create_board(
            board_id="board-1",
            board_name="Test Board",
            column_names=["Backlog", "Done"],
        )
        assert seeder._board_adapter.current_project == seeder._current_project_id
        assert seeder._board_adapter.current_board == "board-1"

    @pytest.mark.asyncio
    async def test_create_board_requires_project(self, bootstrap):
        """Test that create_board raises error without project context."""
        seeder = SimulationDataSeeder(bootstrap)
        with pytest.raises(ValidationError, match="No project context"):
            await seeder.create_board(
                board_id="board-1",
                board_name="Test Board",
                column_names=["Backlog"],
            )

    @pytest.mark.asyncio
    async def test_create_board_columns_accessible(self, seeder):
        """Test that board columns are retrievable after creation."""
        await seeder.create_board(
            board_id="board-1",
            board_name="Test Board",
            column_names=["Backlog", "Ready", "In Progress", "Done"],
        )
        board = await seeder._board_adapter.get_board(seeder._current_project_id, "board-1")
        assert len(board.columns) == 4
        assert board.columns[0].name == "Backlog"
        assert board.columns[3].name == "Done"

    # =========================================================================
    # Item Placement Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_place_item_on_board(self, seeder):
        """Test placing a work item on a board."""
        await seeder.create_board(
            board_id="board-1",
            board_name="Test Board",
            column_names=["Backlog", "Done"],
        )
        await seeder.create_work_items(count=1, title_prefix="Test Issue")

        work_item_id = seeder.created_items.work_items[0]
        result = await seeder.place_item_on_board("board-1", "Backlog", work_item_id)
        assert result is seeder

        # Verify placement
        pos = await seeder._board_adapter.get_item_position(work_item_id)
        assert pos.column_name == "Backlog"

    @pytest.mark.asyncio
    async def test_place_item_requires_project(self, bootstrap):
        """Test that place_item_on_board raises error without project context."""
        seeder = SimulationDataSeeder(bootstrap)
        with pytest.raises(ValidationError, match="No project context"):
            await seeder.place_item_on_board("board-1", "Backlog", "item-1")

    # =========================================================================
    # Pre-built Scenario Board Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_default_scenario_creates_board(self, bootstrap):
        """Test that seed_default_scenario creates a board."""
        seeder = SimulationDataSeeder(bootstrap)
        await seeder.seed_default_scenario()

        assert "board-1" in seeder.created_items.boards
        board = await seeder._board_adapter.get_board(seeder._current_project_id, "board-1")
        assert len(board.columns) == 5

    @pytest.mark.asyncio
    async def test_default_scenario_places_items_in_backlog(self, bootstrap):
        """Test that seed_default_scenario places all items in Backlog."""
        seeder = SimulationDataSeeder(bootstrap)
        await seeder.seed_default_scenario()

        for work_item_id in seeder.created_items.work_items:
            pos = await seeder._board_adapter.get_item_position(work_item_id)
            assert pos.column_name == "Backlog"

    @pytest.mark.asyncio
    async def test_simple_workflow_creates_board(self, bootstrap):
        """Test that seed_simple_workflow creates a board."""
        seeder = SimulationDataSeeder(bootstrap)
        await seeder.seed_simple_workflow()
        assert "board-1" in seeder.created_items.boards

    @pytest.mark.asyncio
    async def test_review_cycle_creates_board(self, bootstrap):
        """Test that seed_review_cycle creates a board."""
        seeder = SimulationDataSeeder(bootstrap)
        await seeder.seed_review_cycle()
        assert "board-1" in seeder.created_items.boards

    @pytest.mark.asyncio
    async def test_parallel_workflow_creates_board(self, bootstrap):
        """Test that seed_parallel_workflow creates a board."""
        seeder = SimulationDataSeeder(bootstrap)
        await seeder.seed_parallel_workflow()
        assert "board-1" in seeder.created_items.boards

    @pytest.mark.asyncio
    async def test_failure_scenario_creates_board(self, bootstrap):
        """Test that seed_failure_scenario creates a board."""
        seeder = SimulationDataSeeder(bootstrap)
        await seeder.seed_failure_scenario()
        assert "board-1" in seeder.created_items.boards

    # =========================================================================
    # YAML Scenario Board Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_seed_from_yaml_with_boards(self, bootstrap, tmp_path):
        """Test that seed_from_yaml processes boards and placements."""
        yaml_content = """
name: "Board Test Scenario"
version: "1.0"
projects:
  - name: "yaml-project"
    description: "Test"
workflows: []
agents: []
work_items:
  - title: "YAML Issue"
    priority: "medium"
    status: "new"
boards:
  - board_id: "yaml-board"
    board_name: "YAML Board"
    columns: ["Backlog", "Ready", "Done"]
board_placements:
  - work_item_title: "YAML Issue"
    column: "Backlog"
"""
        yaml_file = tmp_path / "test_scenario.yaml"
        yaml_file.write_text(yaml_content)

        seeder = SimulationDataSeeder(bootstrap)
        await seeder.seed_from_yaml(yaml_file)

        assert "yaml-board" in seeder.created_items.boards
        assert len(seeder.created_items.work_items) == 1

        # Verify the work item was placed on the board
        work_item_id = seeder.created_items.work_items[0]
        pos = await seeder._board_adapter.get_item_position(work_item_id)
        assert pos.column_name == "Backlog"

    # =========================================================================
    # CreatedItems Board Tracking Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_created_items_tracks_boards(self, seeder):
        """Test that CreatedItems.boards tracks created boards."""
        await seeder.create_board("b1", "Board 1", ["Backlog", "Done"])
        await seeder.create_board("b2", "Board 2", ["Todo", "Done"])

        assert seeder.created_items.boards == ["b1", "b2"]

    @pytest.mark.asyncio
    async def test_created_items_clear_includes_boards(self, seeder):
        """Test that CreatedItems.clear() clears boards."""
        await seeder.create_board("b1", "Board 1", ["Backlog", "Done"])
        seeder.created_items.clear()
        assert seeder.created_items.boards == []
