"""Unit tests for GitHubBoardAdapter polling loop with fake GraphQL backend.

Tests verify that the internal polling loop detects column changes and emits
WorkItemColumnChangedEvent without requiring real GitHub API calls.
"""

from unittest.mock import MagicMock

import pytest

from codetoreum.adapters.secondary.github_board_adapter import GitHubBoardAdapter
from codetoreum.domain.events.board_events import WorkItemColumnChangedEvent


class FakeGraphQLClient:
    """Fake GraphQL client for testing board polling without real GitHub calls."""

    def __init__(self):
        self.board_states: dict[str, dict[str, str]] = {}

    def set_item_column(self, project_id: str, board_id: str, item_id: str, column_name: str) -> None:
        """Update an item's column in the fake backend."""
        key = f"{project_id}:{board_id}"
        if key not in self.board_states:
            self.board_states[key] = {}
        self.board_states[key][item_id] = column_name

    def get_board_state(self, project_id: str, board_id: str) -> dict[str, str]:
        """Get current board state (item_id -> column_name mapping)."""
        key = f"{project_id}:{board_id}"
        return self.board_states.get(key, {})


@pytest.fixture
def fake_graphql_client():
    """Create a fake GraphQL client for testing."""
    return FakeGraphQLClient()


def test_polling_loop_detects_column_change(fake_graphql_client):
    """Verify polling loop detects when a work item moves to a different column."""
    # Create adapter with minimal mocking
    adapter = GitHubBoardAdapter(
        ticket_adapter=None,
        graphql_client=None,
        webhook_enabled=False,
        event_emitter=MagicMock(),
        failed_event_store=None,
    )

    # Setup initial state
    fake_graphql_client.set_item_column("test-project", "board-1", "item-1", "Backlog")
    initial_state = fake_graphql_client.get_board_state("test-project", "board-1")
    adapter._last_known_state["test-project:board-1"] = initial_state.copy()

    # Verify the initial state was set
    assert "item-1" in adapter._last_known_state["test-project:board-1"]

    # Change the item's column
    fake_graphql_client.set_item_column("test-project", "board-1", "item-1", "In Progress")

    # Trigger change detection
    current_state = fake_graphql_client.get_board_state("test-project", "board-1")
    assert current_state["item-1"] == "In Progress", "Current state should have been updated"
    assert adapter._last_known_state["test-project:board-1"]["item-1"] == "Backlog", "Last known state should still be Backlog"

    changes = adapter._detect_column_changes("test-project", "board-1", current_state)

    # Verify change was detected
    assert len(changes) == 1, f"Expected 1 change, got {len(changes)}"
    assert isinstance(changes[0], WorkItemColumnChangedEvent)
    assert changes[0].work_item_id == "item-1"
    assert changes[0].from_column == "Backlog"
    assert changes[0].to_column == "In Progress"


def test_polling_loop_detects_multiple_changes(fake_graphql_client):
    """Verify polling loop detects multiple simultaneous column changes."""
    adapter = GitHubBoardAdapter(
        ticket_adapter=None,
        graphql_client=None,
        webhook_enabled=False,
        event_emitter=MagicMock(),
        failed_event_store=None,
    )

    # Setup initial state with multiple items
    fake_graphql_client.set_item_column("test-project", "board-1", "item-1", "Backlog")
    fake_graphql_client.set_item_column("test-project", "board-1", "item-2", "Backlog")
    fake_graphql_client.set_item_column("test-project", "board-1", "item-3", "In Progress")
    adapter._last_known_state["test-project:board-1"] = fake_graphql_client.get_board_state(
        "test-project", "board-1"
    ).copy()

    # Make multiple changes
    fake_graphql_client.set_item_column("test-project", "board-1", "item-1", "In Progress")
    fake_graphql_client.set_item_column("test-project", "board-1", "item-2", "In Progress")
    fake_graphql_client.set_item_column("test-project", "board-1", "item-3", "Done")

    # Detect changes
    current_state = fake_graphql_client.get_board_state("test-project", "board-1")
    changes = adapter._detect_column_changes("test-project", "board-1", current_state)

    # Verify all changes detected
    assert len(changes) == 3
    change_dict = {c.work_item_id: c for c in changes}
    assert change_dict["item-1"].from_column == "Backlog"
    assert change_dict["item-1"].to_column == "In Progress"
    assert change_dict["item-2"].from_column == "Backlog"
    assert change_dict["item-2"].to_column == "In Progress"
    assert change_dict["item-3"].from_column == "In Progress"
    assert change_dict["item-3"].to_column == "Done"


def test_polling_loop_no_changes_detected(fake_graphql_client):
    """Verify polling loop returns empty list when no changes occur."""
    adapter = GitHubBoardAdapter(
        ticket_adapter=None,
        graphql_client=None,
        webhook_enabled=False,
        event_emitter=MagicMock(),
        failed_event_store=None,
    )

    # Setup initial state
    fake_graphql_client.set_item_column("test-project", "board-1", "item-1", "In Progress")
    adapter._last_known_state["test-project:board-1"] = fake_graphql_client.get_board_state(
        "test-project", "board-1"
    ).copy()

    # Check for changes (without making any)
    current_state = fake_graphql_client.get_board_state("test-project", "board-1")
    changes = adapter._detect_column_changes("test-project", "board-1", current_state)

    # Verify no changes detected
    assert len(changes) == 0


def test_polling_loop_emits_correct_event_data(fake_graphql_client):
    """Verify polling loop emits WorkItemColumnChangedEvent with correct event data."""
    adapter = GitHubBoardAdapter(
        ticket_adapter=None,
        graphql_client=None,
        webhook_enabled=False,
        event_emitter=MagicMock(),
        failed_event_store=None,
    )

    # Setup initial state
    fake_graphql_client.set_item_column("test-project", "board-1", "item-42", "Backlog")
    adapter._last_known_state["test-project:board-1"] = fake_graphql_client.get_board_state(
        "test-project", "board-1"
    ).copy()

    # Make a change
    fake_graphql_client.set_item_column("test-project", "board-1", "item-42", "In Progress")

    # Detect changes
    current_state = fake_graphql_client.get_board_state("test-project", "board-1")
    changes = adapter._detect_column_changes("test-project", "board-1", current_state)

    # Verify event has correct fields
    assert len(changes) == 1
    event = changes[0]
    assert event.type == "workitem.column_changed"
    assert event.source == "github"
    assert event.work_item_id == "item-42"
    assert event.project_id == "test-project"
    assert event.board_id == "board-1"
    assert event.from_column == "Backlog"
    assert event.to_column == "In Progress"
    assert event.moved_by == "unknown"
