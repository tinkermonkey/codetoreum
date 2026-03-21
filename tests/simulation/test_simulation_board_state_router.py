"""
Tests for the simulation board state snapshot REST API router.

Tests the endpoints:
- GET /api/v2/sim/boards/{board_id}/state: Get current board state snapshot
  - Column-to-work-items mapping
  - Work item enrichment (title, time in column, agent assignment, execution status)
  - Thread-safe concurrent reads from board adapter
  - Concurrent title lookups from ticket adapter
"""

from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient

from codetoreum.infrastructure.simulation.bootstrap import SimulationApplicationBootstrap
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig


@pytest.mark.asyncio
class TestSimulationBoardStateRouter:
    """Test the simulation board state snapshot router endpoints."""

    @pytest.fixture
    async def bootstrap(self):
        """Create a bootstrap instance with simulation."""
        config = SimulationConfig.create_fast_config("test_board_state_router")
        bootstrap = SimulationApplicationBootstrap(config)
        await bootstrap.setup()
        yield bootstrap
        await bootstrap.teardown()

    @pytest.fixture
    def app(self, bootstrap):
        """Get the FastAPI app from the bootstrap."""
        return bootstrap.app

    async def test_board_state_unknown_board_returns_404(self, app):
        """Test GET /api/v2/sim/boards/{unknown_board}/state returns 404."""
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/boards/nonexistent-board-123/state")

        assert response.status_code == 404
        assert "Board not found" in response.json()["detail"]

    async def test_board_state_empty_board(self, app, bootstrap):
        """Test GET /api/v2/sim/boards/{board_id}/state returns empty columns for empty board."""
        # Create a board with columns but no items
        board_adapter = bootstrap.adapters.board
        board_adapter.current_project = "proj-1"

        board_adapter.create_board("proj-1", "board-1", "Test Board", ["Backlog", "In Progress", "Done"])

        # Query the board state
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/boards/board-1/state")

        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert data["board_id"] == "board-1"
        assert data["board_name"] == "Test Board"
        assert "snapshot_time" in data
        assert "columns" in data

        # Verify columns
        columns = data["columns"]
        assert len(columns) == 3
        assert columns[0]["name"] == "Backlog"
        assert columns[0]["position"] == 0
        assert columns[0]["items"] == []

        assert columns[1]["name"] == "In Progress"
        assert columns[1]["position"] == 1
        assert columns[1]["items"] == []

        assert columns[2]["name"] == "Done"
        assert columns[2]["position"] == 2
        assert columns[2]["items"] == []

    async def test_board_state_with_work_items(self, app, bootstrap):
        """Test GET /api/v2/sim/boards/{board_id}/state returns work items in columns."""
        # Setup
        board_adapter = bootstrap.adapters.board
        ticket_adapter = bootstrap.adapters.ticket_system
        board_adapter.current_project = "proj-1"

        # Create board and work items
        board_adapter.create_board("proj-1", "board-1", "Test Board", ["Backlog", "In Progress"])

        work_item_1 = await ticket_adapter.create_work_item(
            title="Fix bug in auth",
            description="Login page is broken",
            project_id="proj-1",
        )

        work_item_2 = await ticket_adapter.create_work_item(
            title="Add dark mode",
            description="User request",
            project_id="proj-1",
        )

        # Add items to board
        board_adapter.add_item_to_column("board-1", "Backlog", work_item_1.id)
        board_adapter.add_item_to_column("board-1", "In Progress", work_item_2.id)

        # Query board state
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/boards/board-1/state")

        assert response.status_code == 200
        data = response.json()

        # Verify structure
        columns = data["columns"]
        assert len(columns) == 2

        # Backlog should have 1 item
        backlog = columns[0]
        assert backlog["name"] == "Backlog"
        assert len(backlog["items"]) == 1
        backlog_item = backlog["items"][0]
        assert backlog_item["work_item_id"] == work_item_1.id
        assert backlog_item["title"] == "Fix bug in auth"
        assert backlog_item["position"] == 0
        assert backlog_item["time_in_column_seconds"] >= 0

        # In Progress should have 1 item
        in_progress = columns[1]
        assert in_progress["name"] == "In Progress"
        assert len(in_progress["items"]) == 1
        in_progress_item = in_progress["items"][0]
        assert in_progress_item["work_item_id"] == work_item_2.id
        assert in_progress_item["title"] == "Add dark mode"
        assert in_progress_item["position"] == 0
        assert in_progress_item["time_in_column_seconds"] >= 0

    async def test_board_state_work_item_enrichment_with_active_run(self, app, bootstrap):
        """Test that assigned_agent and execution_status are populated from active run registry."""
        # Setup
        board_adapter = bootstrap.adapters.board
        ticket_adapter = bootstrap.adapters.ticket_system
        run_registry = bootstrap.adapters.run_registry
        board_adapter.current_project = "proj-1"

        # Create board and work item
        board_adapter.create_board("proj-1", "board-1", "Test Board", ["Backlog", "In Progress"])

        work_item = await ticket_adapter.create_work_item(
            title="Task 1",
            description="Description",
            project_id="proj-1",
        )

        # Add item to board
        board_adapter.add_item_to_column("board-1", "Backlog", work_item.id)

        # Register active run
        await run_registry.set_active_run(
            work_item_id=work_item.id,
            run_id="agent-executor-001",
            stage_name="analysis",
            project_id="proj-1",
        )

        # Query board state
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/boards/board-1/state")

        assert response.status_code == 200
        data = response.json()

        # Verify enrichment
        items = data["columns"][0]["items"]
        assert len(items) == 1
        item = items[0]
        assert item["assigned_agent"] == "agent-executor-001"  # run_id
        assert item["execution_status"] == "analysis"  # stage_name

    async def test_board_state_work_item_no_active_run(self, app, bootstrap):
        """Test that assigned_agent and execution_status are None when no active run."""
        # Setup
        board_adapter = bootstrap.adapters.board
        ticket_adapter = bootstrap.adapters.ticket_system
        board_adapter.current_project = "proj-1"

        # Create board and work item
        board_adapter.create_board("proj-1", "board-1", "Test Board", ["Backlog"])

        work_item = await ticket_adapter.create_work_item(
            title="Task 1",
            description="Description",
            project_id="proj-1",
        )

        # Add item to board
        board_adapter.add_item_to_column("board-1", "Backlog", work_item.id)

        # Query board state (no active run registered)
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/boards/board-1/state")

        assert response.status_code == 200
        data = response.json()

        # Verify no enrichment when no active run
        items = data["columns"][0]["items"]
        assert len(items) == 1
        item = items[0]
        assert item["assigned_agent"] is None
        assert item["execution_status"] is None

    async def test_board_state_time_in_column(self, app, bootstrap):
        """Test that time_in_column_seconds is correctly calculated."""
        # Setup
        board_adapter = bootstrap.adapters.board
        ticket_adapter = bootstrap.adapters.ticket_system
        engine = bootstrap._engine
        board_adapter.current_project = "proj-1"

        # Stop auto-advance for predictable timing
        await engine.stop_auto_advance()

        # Create board and work item
        board_adapter.create_board("proj-1", "board-1", "Test Board", ["Backlog", "In Progress"])

        work_item = await ticket_adapter.create_work_item(
            title="Task 1",
            description="Description",
            project_id="proj-1",
        )

        # Record starting time
        initial_time = engine.now()

        # Add item to board
        board_adapter.add_item_to_column("board-1", "Backlog", work_item.id)

        # Advance time by 10 seconds
        await engine.advance(timedelta(seconds=10))

        # Query board state
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/boards/board-1/state")

        assert response.status_code == 200
        data = response.json()

        # Verify time in column is approximately 10 seconds (with tolerance for processing time)
        items = data["columns"][0]["items"]
        assert len(items) == 1
        item = items[0]
        time_in_column = item["time_in_column_seconds"]
        assert 9.5 < time_in_column < 10.5, f"Expected ~10s, got {time_in_column}s"

    async def test_board_state_multiple_items_in_column(self, app, bootstrap):
        """Test that multiple items in a column are returned in position order."""
        # Setup
        board_adapter = bootstrap.adapters.board
        ticket_adapter = bootstrap.adapters.ticket_system
        board_adapter.current_project = "proj-1"

        # Create board
        board_adapter.create_board("proj-1", "board-1", "Test Board", ["Backlog"])

        # Create 3 work items
        items = []
        for i in range(3):
            item = await ticket_adapter.create_work_item(
                title=f"Task {i}",
                description=f"Description {i}",
                project_id="proj-1",
            )
            items.append(item)

        # Add items to board in order
        for i, item in enumerate(items):
            board_adapter.add_item_to_column("board-1", "Backlog", item.id)

        # Query board state
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/boards/board-1/state")

        assert response.status_code == 200
        data = response.json()

        # Verify items are in position order
        backlog_items = data["columns"][0]["items"]
        assert len(backlog_items) == 3
        for i, item in enumerate(backlog_items):
            assert item["position"] == i
            assert item["work_item_id"] == items[i].id

    async def test_board_state_response_model_validation(self, app, bootstrap):
        """Test that response matches BoardStateResponse model."""
        # Setup
        board_adapter = bootstrap.adapters.board
        ticket_adapter = bootstrap.adapters.ticket_system
        board_adapter.current_project = "proj-1"

        # Create board and item
        board_adapter.create_board("proj-1", "board-1", "Test Board", ["Backlog"])

        work_item = await ticket_adapter.create_work_item(
            title="Task 1",
            description="Description",
            project_id="proj-1",
        )

        board_adapter.add_item_to_column("board-1", "Backlog", work_item.id)

        # Query board state
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/boards/board-1/state")

        assert response.status_code == 200
        data = response.json()

        # Verify required fields
        required_fields = {"board_id", "board_name", "snapshot_time", "columns"}
        assert set(data.keys()) >= required_fields

        # Verify field types
        assert isinstance(data["board_id"], str)
        assert data["board_name"] is None or isinstance(data["board_name"], str)
        assert isinstance(data["snapshot_time"], str)  # ISO datetime
        assert isinstance(data["columns"], list)

        # Verify column structure
        for column in data["columns"]:
            assert isinstance(column["name"], str)
            assert isinstance(column["position"], int)
            assert isinstance(column["items"], list)

            # Verify work item structure
            for item in column["items"]:
                assert isinstance(item["work_item_id"], str)
                assert item["title"] is None or isinstance(item["title"], str)
                assert isinstance(item["position"], int)
                assert isinstance(item["entered_column_at"], str)  # ISO datetime
                assert isinstance(item["time_in_column_seconds"], (int, float))
                assert item["time_in_column_seconds"] >= 0
                assert item["assigned_agent"] is None or isinstance(item["assigned_agent"], str)
                assert item["execution_status"] is None or isinstance(item["execution_status"], str)

    async def test_board_state_tags_in_openapi(self, app):
        """Test that endpoint is properly tagged for Swagger UI."""
        # Get OpenAPI schema
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/openapi.json")

        assert response.status_code == 200
        schema = response.json()

        # Find the board state endpoint
        paths = schema["paths"]
        board_state_endpoints = [p for p in paths.keys() if "/sim/boards/" in p and "/state" in p]

        assert len(board_state_endpoints) > 0, "No board state endpoints found in OpenAPI schema"

        # Verify tags
        for path in board_state_endpoints:
            operation = paths[path]["get"]
            assert "tags" in operation
            assert "simulation-board-state" in operation["tags"]

    async def test_board_state_missing_work_item_title(self, app, bootstrap):
        """Test that missing work item title is handled gracefully (returns None)."""
        # Setup
        board_adapter = bootstrap.adapters.board
        board_adapter.current_project = "proj-1"

        # Create board
        board_adapter.create_board("proj-1", "board-1", "Test Board", ["Backlog"])

        # Manually add an item to the board without creating it in ticket adapter
        # This simulates a work item that doesn't exist in the ticket system
        board_adapter._item_positions["fake-item-1"] = ("board-1", "Backlog", 0)
        board_adapter._item_column_entries["fake-item-1"] = board_adapter._clock.now() if board_adapter._clock else __import__(
            "datetime"
        ).datetime.now(__import__("datetime").UTC)

        # Query board state
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/boards/board-1/state")

        assert response.status_code == 200
        data = response.json()

        # Verify the item is present but title is None
        items = data["columns"][0]["items"]
        assert len(items) == 1
        item = items[0]
        assert item["work_item_id"] == "fake-item-1"
        assert item["title"] is None  # Title not found

    async def test_board_state_reflects_mutations_without_restart(self, app, bootstrap):
        """Test that board state reflects mutations from add_item_to_column without server restart."""
        # Setup
        board_adapter = bootstrap.adapters.board
        ticket_adapter = bootstrap.adapters.ticket_system
        board_adapter.current_project = "proj-1"

        # Create board
        board_adapter.create_board("proj-1", "board-1", "Test Board", ["Backlog", "In Progress"])

        # Initial query - should be empty
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/boards/board-1/state")
        assert len(response.json()["columns"][0]["items"]) == 0

        # Create and add a work item
        work_item = await ticket_adapter.create_work_item(
            title="New Task",
            description="Description",
            project_id="proj-1",
        )
        board_adapter.add_item_to_column("board-1", "Backlog", work_item.id)

        # Query again - should see the new item
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/boards/board-1/state")
        assert len(response.json()["columns"][0]["items"]) == 1
        assert response.json()["columns"][0]["items"][0]["work_item_id"] == work_item.id

        # Simulate moving the item (human move)
        await board_adapter.simulate_human_move_async(work_item.id, "In Progress")

        # Query again - should see the item in the new column
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/boards/board-1/state")
        data = response.json()
        assert len(data["columns"][0]["items"]) == 0  # Backlog is empty
        assert len(data["columns"][1]["items"]) == 1  # In Progress has 1 item
        assert data["columns"][1]["items"][0]["work_item_id"] == work_item.id

    async def test_board_state_snapshot_time_from_clock(self, app, bootstrap):
        """Test that snapshot_time comes from simulation clock."""
        # Setup
        board_adapter = bootstrap.adapters.board
        engine = bootstrap._engine
        board_adapter.current_project = "proj-1"

        # Stop auto-advance
        await engine.stop_auto_advance()

        # Create board
        board_adapter.create_board("proj-1", "board-1", "Test Board", ["Backlog"])

        # Get current engine time
        expected_time = engine.now()

        # Query board state
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/boards/board-1/state")

        assert response.status_code == 200
        data = response.json()

        # Verify snapshot_time matches engine time
        snapshot_time = datetime.fromisoformat(data["snapshot_time"])
        assert abs((snapshot_time - expected_time).total_seconds()) < 0.1

    async def test_board_state_concurrent_reads_no_deadlock(self, app, bootstrap):
        """Test that concurrent reads don't deadlock (thread safety under lock)."""
        import asyncio

        # Setup
        board_adapter = bootstrap.adapters.board
        ticket_adapter = bootstrap.adapters.ticket_system
        board_adapter.current_project = "proj-1"

        # Create board and items
        board_adapter.create_board("proj-1", "board-1", "Test Board", ["Backlog"])

        for i in range(5):
            work_item = await ticket_adapter.create_work_item(
                title=f"Task {i}",
                description=f"Description {i}",
                project_id="proj-1",
            )
            board_adapter.add_item_to_column("board-1", "Backlog", work_item.id)

        # Make concurrent requests to the same endpoint
        async def fetch_board_state():
            async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
                response = await client.get("/api/v2/sim/boards/board-1/state")
                return response.status_code

        # Launch 10 concurrent requests
        results = await asyncio.gather(*[fetch_board_state() for _ in range(10)])

        # All should succeed
        assert all(status == 200 for status in results)
        assert len(results) == 10
