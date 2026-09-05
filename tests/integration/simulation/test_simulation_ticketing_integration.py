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
        with TestClient(bootstrap.app) as test_client:
            yield test_client

    @pytest.fixture
    def seeded_client(self, seeded_bootstrap):
        """TestClient with seeded data."""
        bootstrap, seeder = seeded_bootstrap
        with TestClient(bootstrap.app) as test_client:
            yield test_client, seeder

    # =========================================================================
    # Bootstrap Integration Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_bootstrap_has_board_adapter(self, bootstrap):
        """Test that bootstrap creates a board adapter."""
        assert bootstrap.adapters.board is not None

    # =========================================================================
    # End-to-End Flow Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_create_ticket_via_api(self, seeded_client):
        """Test creating a ticket through the simulation API."""
        client, seeder = seeded_client
        project_id = seeder._current_project_id

        resp = client.post(
            "/api/v2/simulation/ticketing/issues",
            json={
                "title": "Integration test issue",
                "description": "Created via API",
                "project_id": project_id,
                "labels": ["integration-test"],
                "priority": "high",
                "board_id": "board-1",
                "column": "Backlog",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Integration test issue"
        assert data["board_position"]["column"] == "Backlog"

    @pytest.mark.asyncio
    async def test_seeded_items_visible_on_board(self, seeded_client):
        """Test that items seeded by default scenario are visible on the board."""
        client, seeder = seeded_client
        project_id = seeder._current_project_id

        resp = client.get(
            "/api/v2/simulation/ticketing/board/board-1/items",
            params={
                "project_id": project_id,
            },
        )
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
