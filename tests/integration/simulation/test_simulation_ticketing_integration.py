"""Integration tests for simulation ticketing through full bootstrap."""

import pytest
from fastapi.testclient import TestClient

from codetoreum.infrastructure.simulation import (
    SimulationApplicationBootstrap,
    SimulationConfig,
    SimulationDataSeeder,
)


class TestSimulationTicketingIntegration:
    """
    Integration tests that verify the full flow:
    bootstrap -> seed -> create ticket -> move on board -> verify events.
    """

    @pytest.fixture
    async def bootstrap(self):
        """Create and setup full bootstrap."""
        config = SimulationConfig.create_fast_config("ticketing_integration")
        bootstrap = SimulationApplicationBootstrap(config)
        await bootstrap.setup()
        yield bootstrap
        await bootstrap.teardown()

    @pytest.fixture
    async def seeded_bootstrap(self, bootstrap):
        """Bootstrap with default scenario seeded."""
        seeder = SimulationDataSeeder(bootstrap)
        await seeder.seed_default_scenario()
        return bootstrap, seeder

    @pytest.fixture
    def client(self, bootstrap):
        """TestClient for the bootstrapped FastAPI app."""
        return TestClient(bootstrap.app)

    @pytest.fixture
    def seeded_client(self, seeded_bootstrap):
        """TestClient with seeded data."""
        bootstrap, seeder = seeded_bootstrap
        return TestClient(bootstrap.app), seeder

    # =========================================================================
    # Bootstrap Integration Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_bootstrap_has_board_adapter(self, bootstrap):
        """Test that bootstrap creates a board adapter."""
        assert bootstrap.adapters.board is not None

    @pytest.mark.asyncio
    async def test_bootstrap_wires_board_to_orchestrator(self, bootstrap):
        """Test that MultiProjectOrchestrator receives board_service."""
        orchestrator = bootstrap.services.multi_project_orchestrator
        assert orchestrator._board_service is not None

    # =========================================================================
    # End-to-End Flow Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_create_ticket_via_api(self, seeded_client):
        """Test creating a ticket through the simulation API."""
        client, seeder = seeded_client
        project_id = seeder._current_project_id

        resp = client.post("/api/v2/simulation/ticketing/issues", json={
            "title": "Integration test issue",
            "description": "Created via API",
            "project_id": project_id,
            "labels": ["integration-test"],
            "priority": "high",
            "board_id": "board-1",
            "column": "Backlog",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Integration test issue"
        assert data["board_position"]["column"] == "Backlog"

    @pytest.mark.asyncio
    async def test_move_ticket_emits_event(self, seeded_client):
        """Test that moving a ticket emits a WorkItemColumnChangedEvent."""
        client, seeder = seeded_client
        project_id = seeder._current_project_id

        # Create and place on board
        resp = client.post("/api/v2/simulation/ticketing/issues", json={
            "title": "Event test issue",
            "project_id": project_id,
            "board_id": "board-1",
            "column": "Backlog",
        })
        issue_id = resp.json()["id"]

        # Move to Ready
        resp = client.post(f"/api/v2/simulation/ticketing/issues/{issue_id}/move", json={
            "target_column": "Ready",
        })
        assert resp.status_code == 200

        # Verify movement in board adapter history
        history = seeder._board_adapter.get_movement_history(issue_id)
        assert len(history) == 1
        assert history[0].from_column == "Backlog"
        assert history[0].to_column == "Ready"

    @pytest.mark.asyncio
    async def test_full_workflow_simulation(self, seeded_client):
        """Test a complete workflow: create -> backlog -> ready -> in progress."""
        client, seeder = seeded_client
        project_id = seeder._current_project_id

        # Create ticket in Backlog
        resp = client.post("/api/v2/simulation/ticketing/issues", json={
            "title": "Full workflow issue",
            "project_id": project_id,
            "board_id": "board-1",
            "column": "Backlog",
        })
        issue_id = resp.json()["id"]

        # Move Backlog -> Ready
        resp = client.post(f"/api/v2/simulation/ticketing/issues/{issue_id}/move", json={
            "target_column": "Ready",
        })
        assert resp.status_code == 200

        # Move Ready -> In Progress
        resp = client.post(f"/api/v2/simulation/ticketing/issues/{issue_id}/move", json={
            "target_column": "In Progress",
        })
        assert resp.status_code == 200

        # Add comment
        resp = client.post(f"/api/v2/simulation/ticketing/issues/{issue_id}/comment", json={
            "body": "Work started on this issue",
            "author": "dev-agent",
        })
        assert resp.status_code == 200

        # Verify board state
        resp = client.get("/api/v2/simulation/ticketing/board/board-1/columns", params={
            "project_id": project_id,
        })
        data = resp.json()
        in_progress = next(c for c in data["columns"] if c["name"] == "In Progress")
        assert issue_id in in_progress["work_item_ids"]

        # Verify history shows both moves
        resp = client.get("/api/v2/simulation/ticketing/board/board-1/history")
        history = resp.json()
        issue_moves = [m for m in history["movements"] if m["work_item_id"] == issue_id]
        assert len(issue_moves) == 2

    @pytest.mark.asyncio
    async def test_seeded_items_visible_on_board(self, seeded_client):
        """Test that items seeded by default scenario are visible on the board."""
        client, seeder = seeded_client
        project_id = seeder._current_project_id

        resp = client.get("/api/v2/simulation/ticketing/board/board-1/items", params={
            "project_id": project_id,
        })
        assert resp.status_code == 200
        data = resp.json()
        # Default scenario creates 3 work items in Backlog
        assert data["total"] == 3
        for item in data["items"]:
            assert item["column_name"] == "Backlog"

    @pytest.mark.asyncio
    async def test_simulation_ticketing_routes_only_in_simulation(self, bootstrap):
        """Test that ticketing routes exist in the simulation app."""
        routes = [r.path for r in bootstrap.app.routes]
        assert "/api/v2/simulation/ticketing/issues" in routes
        assert "/api/v2/simulation/ticketing/issues/{issue_id}/move" in routes
        assert "/api/v2/simulation/ticketing/board/{board_id}/columns" in routes
