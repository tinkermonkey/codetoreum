"""Unit tests for simulation ticketing router."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codetoreum.adapters.primary.routers.simulation_ticketing import (
    create_simulation_ticketing_router,
)
from codetoreum.adapters.testing.in_memory_ticket_adapter import InMemoryTicketAdapter
from codetoreum.adapters.testing.mock_board_adapter import MockBoardAdapter


@pytest.fixture
def ticket_adapter():
    return InMemoryTicketAdapter()


@pytest.fixture
def board_adapter():
    adapter = MockBoardAdapter()
    adapter.create_board("proj-1", "board-1", "Test Board", ["Backlog", "Ready", "In Progress", "Review", "Done"])
    adapter.current_project = "proj-1"
    return adapter


@pytest.fixture
def client(ticket_adapter, board_adapter):
    app = FastAPI()
    router = create_simulation_ticketing_router(ticket_adapter, board_adapter)
    app.include_router(router)
    return TestClient(app)


class TestCreateIssue:
    """Tests for POST /issues endpoint."""

    def test_create_issue_basic(self, client):
        resp = client.post(
            "/api/v2/simulation/ticketing/issues",
            json={
                "title": "Test issue",
                "project_id": "proj-1",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Test issue"
        assert data["project_id"] == "proj-1"
        assert data["priority"] == "medium"
        assert data["id"]

    def test_create_issue_with_board_placement(self, client):
        resp = client.post(
            "/api/v2/simulation/ticketing/issues",
            json={
                "title": "Board issue",
                "project_id": "proj-1",
                "board_id": "board-1",
                "column": "Backlog",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["board_position"] is not None
        assert data["board_position"]["board_id"] == "board-1"
        assert data["board_position"]["column"] == "Backlog"

    def test_create_issue_with_labels(self, client):
        resp = client.post(
            "/api/v2/simulation/ticketing/issues",
            json={
                "title": "Labeled issue",
                "project_id": "proj-1",
                "labels": ["bug", "urgent"],
                "priority": "high",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "bug" in data["labels"]
        assert data["priority"] == "high"

    def test_create_issue_invalid_priority(self, client):
        resp = client.post(
            "/api/v2/simulation/ticketing/issues",
            json={
                "title": "Bad priority",
                "project_id": "proj-1",
                "priority": "super_high",
            },
        )
        assert resp.status_code == 400

    def test_create_issue_empty_title(self, client):
        resp = client.post(
            "/api/v2/simulation/ticketing/issues",
            json={
                "title": "",
                "project_id": "proj-1",
            },
        )
        assert resp.status_code == 422


class TestListIssues:
    """Tests for GET /issues endpoint."""

    def test_list_empty(self, client):
        resp = client.get("/api/v2/simulation/ticketing/issues")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["issues"] == []

    def test_list_after_create(self, client):
        client.post(
            "/api/v2/simulation/ticketing/issues",
            json={
                "title": "Issue 1",
                "project_id": "proj-1",
            },
        )
        client.post(
            "/api/v2/simulation/ticketing/issues",
            json={
                "title": "Issue 2",
                "project_id": "proj-1",
            },
        )
        resp = client.get("/api/v2/simulation/ticketing/issues", params={"project_id": "proj-1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    def test_list_filter_by_project(self, client):
        client.post(
            "/api/v2/simulation/ticketing/issues",
            json={
                "title": "Proj 1 issue",
                "project_id": "proj-1",
            },
        )
        client.post(
            "/api/v2/simulation/ticketing/issues",
            json={
                "title": "Proj 2 issue",
                "project_id": "proj-2",
            },
        )
        resp = client.get("/api/v2/simulation/ticketing/issues", params={"project_id": "proj-1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["issues"][0]["project_id"] == "proj-1"


class TestGetIssue:
    """Tests for GET /issues/{id} endpoint."""

    def test_get_existing_issue(self, client):
        create_resp = client.post(
            "/api/v2/simulation/ticketing/issues",
            json={
                "title": "Get me",
                "project_id": "proj-1",
            },
        )
        issue_id = create_resp.json()["id"]

        resp = client.get(f"/api/v2/simulation/ticketing/issues/{issue_id}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Get me"

    def test_get_nonexistent_issue(self, client):
        resp = client.get("/api/v2/simulation/ticketing/issues/nonexistent-id")
        assert resp.status_code == 404


class TestMoveIssue:
    """Tests for POST /issues/{id}/move endpoint."""

    def test_move_issue(self, client):
        # Create and place on board
        create_resp = client.post(
            "/api/v2/simulation/ticketing/issues",
            json={
                "title": "Move me",
                "project_id": "proj-1",
                "board_id": "board-1",
                "column": "Backlog",
            },
        )
        issue_id = create_resp.json()["id"]

        # Move to Ready
        resp = client.post(
            f"/api/v2/simulation/ticketing/issues/{issue_id}/move",
            json={
                "target_column": "Ready",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["from_column"] == "Backlog"
        assert data["to_column"] == "Ready"
        assert data["moved_by"] == "human"

    def test_move_nonexistent_issue(self, client):
        resp = client.post(
            "/api/v2/simulation/ticketing/issues/nonexistent/move",
            json={
                "target_column": "Ready",
            },
        )
        assert resp.status_code == 404

    def test_move_to_invalid_column(self, client):
        create_resp = client.post(
            "/api/v2/simulation/ticketing/issues",
            json={
                "title": "Bad move",
                "project_id": "proj-1",
                "board_id": "board-1",
                "column": "Backlog",
            },
        )
        issue_id = create_resp.json()["id"]

        resp = client.post(
            f"/api/v2/simulation/ticketing/issues/{issue_id}/move",
            json={
                "target_column": "Nonexistent Column",
            },
        )
        assert resp.status_code == 400


class TestAddComment:
    """Tests for POST /issues/{id}/comment endpoint."""

    def test_add_comment(self, client):
        create_resp = client.post(
            "/api/v2/simulation/ticketing/issues",
            json={
                "title": "Comment target",
                "project_id": "proj-1",
            },
        )
        issue_id = create_resp.json()["id"]

        resp = client.post(
            f"/api/v2/simulation/ticketing/issues/{issue_id}/comment",
            json={
                "body": "This looks good!",
                "author": "reviewer",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["body"] == "This looks good!"
        assert data["author"] == "reviewer"
        assert data["work_item_id"] == issue_id

    def test_add_comment_nonexistent_issue(self, client):
        resp = client.post(
            "/api/v2/simulation/ticketing/issues/nonexistent/comment",
            json={
                "body": "Orphan comment",
            },
        )
        assert resp.status_code == 404


class TestBoardColumns:
    """Tests for GET /board/{board_id}/columns endpoint."""

    def test_get_columns(self, client):
        resp = client.get(
            "/api/v2/simulation/ticketing/board/board-1/columns",
            params={
                "project_id": "proj-1",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["board_id"] == "board-1"
        assert len(data["columns"]) == 5
        assert data["columns"][0]["name"] == "Backlog"

    def test_get_columns_nonexistent_board(self, client):
        resp = client.get(
            "/api/v2/simulation/ticketing/board/nonexistent/columns",
            params={
                "project_id": "proj-1",
            },
        )
        assert resp.status_code == 404

    def test_columns_show_item_counts(self, client):
        # Place an item
        create_resp = client.post(
            "/api/v2/simulation/ticketing/issues",
            json={
                "title": "Counted item",
                "project_id": "proj-1",
                "board_id": "board-1",
                "column": "Backlog",
            },
        )
        resp = client.get(
            "/api/v2/simulation/ticketing/board/board-1/columns",
            params={
                "project_id": "proj-1",
            },
        )
        data = resp.json()
        backlog = next(c for c in data["columns"] if c["name"] == "Backlog")
        assert backlog["item_count"] == 1


class TestBoardItems:
    """Tests for GET /board/{board_id}/items endpoint."""

    def test_get_items(self, client):
        create_resp = client.post(
            "/api/v2/simulation/ticketing/issues",
            json={
                "title": "Board item",
                "project_id": "proj-1",
                "board_id": "board-1",
                "column": "Backlog",
            },
        )
        issue_id = create_resp.json()["id"]

        resp = client.get(
            "/api/v2/simulation/ticketing/board/board-1/items",
            params={
                "project_id": "proj-1",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["work_item_id"] == issue_id
        assert data["items"][0]["column_name"] == "Backlog"


class TestBoardHistory:
    """Tests for GET /board/{board_id}/history endpoint."""

    def test_empty_history(self, client):
        resp = client.get("/api/v2/simulation/ticketing/board/board-1/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    def test_history_after_move(self, client):
        # Create and place
        create_resp = client.post(
            "/api/v2/simulation/ticketing/issues",
            json={
                "title": "History item",
                "project_id": "proj-1",
                "board_id": "board-1",
                "column": "Backlog",
            },
        )
        issue_id = create_resp.json()["id"]

        # Move
        client.post(
            f"/api/v2/simulation/ticketing/issues/{issue_id}/move",
            json={
                "target_column": "Ready",
            },
        )

        resp = client.get("/api/v2/simulation/ticketing/board/board-1/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["movements"][0]["from_column"] == "Backlog"
        assert data["movements"][0]["to_column"] == "Ready"
        assert data["movements"][0]["moved_by"] == "human"
