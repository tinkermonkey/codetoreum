"""Unit tests for simulation ticketing router."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codetoreum.adapters.primary.routers.simulation_ticketing import (
    create_simulation_ticketing_router,
)
from codetoreum.adapters.testing.in_memory_ticket_adapter import InMemoryTicketAdapter
from codetoreum.adapters.testing.in_memory_workflow_config_service import InMemoryWorkflowConfigService
from codetoreum.adapters.testing.mock_board_adapter import MockBoardAdapter
from codetoreum.domain.board_workflow_template import BoardWorkflowTemplate, ColumnTemplate, ColumnType


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
def workflow_config_service():
    """Workflow config service with a template for the test board."""
    service = InMemoryWorkflowConfigService()

    # Register a workflow template for the test board
    # This matches the board created in board_adapter fixture
    template = BoardWorkflowTemplate(
        id="workflow-test",
        name="Test Workflow",
        board_id="board-1",
        project_id="test-project",
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
                name="Ready",
                type=ColumnType.AUTOMATED,
                agent_id="test_agent",
                is_pipeline_trigger=True,
                is_exit_column=False,
                position=1,
                auto_progress_on_completion=True,
            ),
            ColumnTemplate(
                name="In Progress",
                type=ColumnType.AUTOMATED,
                agent_id="test_agent",
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=2,
                auto_progress_on_completion=True,
            ),
            ColumnTemplate(
                name="Review",
                type=ColumnType.AUTOMATED,
                agent_id="test_agent",
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=3,
                auto_progress_on_completion=True,
            ),
            ColumnTemplate(
                name="Done",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=True,
                position=4,
                auto_progress_on_completion=False,
            ),
        ),
    )

    # Register the template for the board
    service.register_template("board-1", template)

    return service


@pytest.fixture
def client(ticket_adapter, board_adapter, workflow_config_service):
    app = FastAPI()
    router = create_simulation_ticketing_router(ticket_adapter, board_adapter, workflow_config_service)
    app.include_router(router)
    return TestClient(app)


class TestStagingColumnDetection:
    """Tests for proper staging column detection (issue #442).

    The staging column is the appropriate entry point for newly created work items.
    It should be a MANUAL column that doesn't trigger pipeline automation.
    The router should use the workflow template to find the correct staging column
    instead of blindly assuming the first column is suitable for staging.
    """

    def test_create_issue_uses_manual_column_for_staging(self, client):
        """Verify that the first MANUAL column is used for staging, not position 0."""
        # Create issue requesting placement in a target column
        resp = client.post(
            "/api/v2/simulation/ticketing/issues",
            json={
                "title": "Staging test",
                "project_id": "proj-1",
                "board_id": "board-1",
                "column": "Ready",  # Target column is "Ready" (automated, pipeline trigger)
            },
        )
        assert resp.status_code == 201
        data = resp.json()

        # Verify issue is placed in the target column (Ready)
        assert data["board_position"]["column"] == "Ready"

        # Verify that the issue was properly staged and moved (internal behavior)
        # The item should have been temporarily placed in "Backlog" (first MANUAL column)
        # then moved to "Ready" (target column) to trigger WorkItemColumnChangedEvent

    def test_staging_column_when_first_column_is_automated(self):
        """Test the key scenario from issue #442: column 0 is AUTOMATED/pipeline-trigger.

        This tests the exact bug scenario: when the first column position is an
        AUTOMATED pipeline-trigger column, the item should NOT be placed there.
        Instead, it should be staged in the first MANUAL column (at a later position).

        Setup:
        - Column 0: "Planning" (AUTOMATED, pipeline trigger)
        - Column 1: "Staging" (MANUAL)
        - Column 2: "Ready" (AUTOMATED)
        - Column 3: "Done" (MANUAL, exit column)

        Expected: New item is staged in "Staging" (col 1), not "Planning" (col 0).
        """
        # Create board with AUTOMATED column at position 0
        adapter = MockBoardAdapter()
        adapter.create_board("proj-2", "board-2", "Test Board v2", ["Planning", "Staging", "Ready", "Done"])
        adapter.current_project = "proj-2"

        # Register workflow template where column 0 is AUTOMATED/pipeline-trigger
        service = InMemoryWorkflowConfigService()
        template = BoardWorkflowTemplate(
            id="workflow-test-v2",
            name="Test Workflow v2",
            board_id="board-2",
            project_id="test-project",
            columns=(
                ColumnTemplate(
                    name="Planning",  # Position 0, but AUTOMATED/trigger
                    type=ColumnType.AUTOMATED,
                    agent_id="planner_agent",
                    is_pipeline_trigger=True,
                    is_exit_column=False,
                    position=0,
                    auto_progress_on_completion=False,
                ),
                ColumnTemplate(
                    name="Staging",  # Position 1, MANUAL (proper staging column)
                    type=ColumnType.MANUAL,
                    agent_id=None,
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=1,
                    auto_progress_on_completion=False,
                ),
                ColumnTemplate(
                    name="Ready",
                    type=ColumnType.AUTOMATED,
                    agent_id="executor_agent",
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=2,
                    auto_progress_on_completion=True,
                ),
                ColumnTemplate(
                    name="Done",
                    type=ColumnType.MANUAL,
                    agent_id=None,
                    is_pipeline_trigger=False,
                    is_exit_column=True,
                    position=3,
                    auto_progress_on_completion=False,
                ),
            ),
        )
        service.register_template("board-2", template)

        # Create test client with this board/template
        app = FastAPI()
        router = create_simulation_ticketing_router(InMemoryTicketAdapter(), adapter, service)
        app.include_router(router)
        client = TestClient(app)

        # Create issue with board placement
        resp = client.post(
            "/api/v2/simulation/ticketing/issues",
            json={
                "title": "Test staging with automated column 0",
                "project_id": "proj-2",
                "board_id": "board-2",
                "column": "Ready",  # Request placement in "Ready"
            },
        )
        assert resp.status_code == 201
        data = resp.json()

        # Verify issue ends up in the target column
        assert data["board_position"]["column"] == "Ready"
        issue_id = data["id"]

        # Verify the item's history shows it was staged in "Staging" (position 1),
        # NOT in "Planning" (position 0). This proves the fix works.
        history_resp = client.get("/api/v2/simulation/ticketing/board/board-2/history")
        assert history_resp.status_code == 200
        history = history_resp.json()

        # Expect at least 2 moves: Staging -> Ready
        # (The initial placement in Staging doesn't create a move event)
        movements = history["movements"]
        assert len(movements) >= 1, "Expected at least one movement in history"

        # First move should be from Staging to Ready (never from Planning)
        first_move = movements[0]
        assert first_move["from_column"] == "Staging", (
            f"Expected staging in 'Staging' column, but first move was from "
            f"'{first_move['from_column']}'. This indicates the old bug (staging in column 0) "
            f"is still present."
        )
        assert first_move["to_column"] == "Ready"

    def test_staging_fallback_when_no_workflow_template(self):
        """Test fallback to first column when no workflow template is registered.

        When a board doesn't have a registered workflow template, the router should
        fall back to using the first column as the staging column and not error.
        """
        # Create board without registering a workflow template
        adapter = MockBoardAdapter()
        adapter.create_board("proj-3", "board-3", "Untracked Board", ["Input", "Work", "Output"])
        adapter.current_project = "proj-3"

        # Service with NO template registered for this board
        service = InMemoryWorkflowConfigService()

        app = FastAPI()
        router = create_simulation_ticketing_router(InMemoryTicketAdapter(), adapter, service)
        app.include_router(router)
        client = TestClient(app)

        # Create issue with board placement
        # Should succeed and use first column ("Input") as fallback
        resp = client.post(
            "/api/v2/simulation/ticketing/issues",
            json={
                "title": "Test fallback without template",
                "project_id": "proj-3",
                "board_id": "board-3",
                "column": "Work",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["board_position"]["column"] == "Work"
        assert data["board_position"]["board_id"] == "board-3"

    def test_staging_warning_when_no_manual_columns(self, caplog):
        """Test warning is logged when workflow has no MANUAL columns.

        When a workflow template exists but has no MANUAL columns, the router
        should log a warning and fall back to the first column. This scenario
        is unlikely but should be handled gracefully.
        """
        # Create board
        adapter = MockBoardAdapter()
        adapter.create_board("proj-4", "board-4", "All Automated Board", ["Automated1", "Automated2", "Automated3"])
        adapter.current_project = "proj-4"

        # Register workflow template with NO MANUAL columns
        service = InMemoryWorkflowConfigService()
        template = BoardWorkflowTemplate(
            id="workflow-automated",
            name="All Automated Workflow",
            board_id="board-4",
            project_id="test-project",
            columns=(
                ColumnTemplate(
                    name="Automated1",
                    type=ColumnType.AUTOMATED,
                    agent_id="agent1",
                    is_pipeline_trigger=True,
                    is_exit_column=False,
                    position=0,
                    auto_progress_on_completion=False,
                ),
                ColumnTemplate(
                    name="Automated2",
                    type=ColumnType.AUTOMATED,
                    agent_id="agent2",
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=1,
                    auto_progress_on_completion=True,
                ),
                ColumnTemplate(
                    name="Automated3",
                    type=ColumnType.AUTOMATED,
                    agent_id="agent3",
                    is_pipeline_trigger=False,
                    is_exit_column=True,
                    position=2,
                    auto_progress_on_completion=True,
                ),
            ),
        )
        service.register_template("board-4", template)

        app = FastAPI()
        router = create_simulation_ticketing_router(InMemoryTicketAdapter(), adapter, service)
        app.include_router(router)
        client = TestClient(app)

        # Create issue with board placement
        with caplog.at_level("WARNING"):
            resp = client.post(
                "/api/v2/simulation/ticketing/issues",
                json={
                    "title": "Test no manual columns",
                    "project_id": "proj-4",
                    "board_id": "board-4",
                    "column": "Automated2",
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["board_position"]["column"] == "Automated2"

        # Verify warning was logged about no MANUAL columns
        warning_found = any(
            "No MANUAL columns found in workflow template" in record.message
            for record in caplog.records
            if record.levelname == "WARNING"
        )
        assert warning_found, "Expected warning to be logged when no MANUAL columns found in template"


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
