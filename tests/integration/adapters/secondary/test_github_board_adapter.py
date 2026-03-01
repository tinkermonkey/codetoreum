"""Integration tests for GitHub Projects v2 board adapter.

Tests cover:
- Board structure queries
- Work item movement
- Board reconciliation
- Webhook event processing
- Polling-based change detection
- Event emission
"""

from unittest.mock import AsyncMock

import pytest

from codetoreum.adapters.secondary.github_board_adapter import GitHubBoardAdapter
from codetoreum.adapters.secondary.github_ticket_adapter import (
    GitHubConfig,
    GitHubTicketAdapter,
)
from codetoreum.domain.events.board_events import (
    WorkItemColumnChangedEvent,
)
from codetoreum.infrastructure.http.github_graphql_client import (
    GitHubGraphQLClient,
    GitHubGraphQLConfig,
)
from codetoreum.ports.exceptions import (
    ExternalServiceError,
    ValidationError,
)
from codetoreum.ports.output.board_service import (
    MovedByType,
)


@pytest.fixture
def github_config():
    """GitHub configuration fixture."""
    return GitHubConfig(
        token="test-token",
        organization="test-org",
        repository="test-repo",
    )


@pytest.fixture
def graphql_config():
    """GitHub GraphQL configuration fixture."""
    return GitHubGraphQLConfig(token="test-token")


@pytest.fixture
def mock_graphql_client(graphql_config):
    """Mock GraphQL client fixture."""
    return AsyncMock(spec=GitHubGraphQLClient)


@pytest.fixture
def ticket_adapter(github_config):
    """GitHub ticket adapter fixture."""
    return GitHubTicketAdapter(github_config)


@pytest.fixture
def board_adapter(ticket_adapter, mock_graphql_client):
    """GitHub board adapter fixture."""
    return GitHubBoardAdapter(
        ticket_adapter=ticket_adapter,
        graphql_client=mock_graphql_client,
        webhook_enabled=True,
    )


@pytest.fixture
def sample_board_response():
    """Sample GraphQL board response."""
    return {
        "node": {
            "id": "PVT_kwDOA1",
            "title": "Test Project",
            "fields": {
                "nodes": [
                    {
                        "id": "PVTF_lADOA1",
                        "name": "Status",
                        "options": [
                            {"id": "opt-1", "name": "Backlog"},
                            {"id": "opt-2", "name": "In Progress"},
                            {"id": "opt-3", "name": "Review"},
                            {"id": "opt-4", "name": "Done"},
                        ],
                    }
                ]
            },
            "items": {
                "nodes": [
                    {
                        "id": "PVTI_1",
                        "content": {"number": 1, "id": "I_1"},
                        "fieldValues": {
                            "nodes": [
                                {
                                    "field": {"name": "Status"},
                                    "name": "Backlog",
                                }
                            ]
                        },
                    },
                    {
                        "id": "PVTI_2",
                        "content": {"number": 2, "id": "I_2"},
                        "fieldValues": {
                            "nodes": [
                                {
                                    "field": {"name": "Status"},
                                    "name": "In Progress",
                                }
                            ]
                        },
                    },
                    {
                        "id": "PVTI_3",
                        "content": {"number": 3, "id": "I_3"},
                        "fieldValues": {
                            "nodes": [
                                {
                                    "field": {"name": "Status"},
                                    "name": "Review",
                                }
                            ]
                        },
                    },
                ]
            },
        }
    }


class TestGetBoard:
    """Tests for get_board method."""

    @pytest.mark.asyncio
    async def test_get_board_success(self, board_adapter, mock_graphql_client, sample_board_response):
        """Test successful board retrieval."""
        mock_graphql_client.execute.return_value = sample_board_response

        result = await board_adapter.get_board("proj-123", "board-456")

        assert result.id == "board-456"
        assert result.name == "Test Project"
        assert len(result.columns) == 4
        assert result.columns[0].name == "Backlog"
        assert result.columns[0].work_item_ids == ("1",)
        assert result.columns[1].name == "In Progress"
        assert result.columns[1].work_item_ids == ("2",)
        assert result.columns[2].name == "Review"
        assert result.columns[2].work_item_ids == ("3",)
        assert result.columns[3].name == "Done"
        assert result.columns[3].work_item_ids == ()

    @pytest.mark.asyncio
    async def test_get_board_not_found(self, board_adapter, mock_graphql_client):
        """Test board not found error."""
        mock_graphql_client.execute.return_value = {"node": None}

        with pytest.raises(Exception):  # Catches ResourceNotFoundError
            await board_adapter.get_board("proj-123", "board-456")

    @pytest.mark.asyncio
    async def test_get_board_api_error(self, board_adapter, mock_graphql_client):
        """Test API error handling."""
        mock_graphql_client.execute.side_effect = ExternalServiceError("GitHub", "API error")

        with pytest.raises(ExternalServiceError):
            await board_adapter.get_board("proj-123", "board-456")


class TestMoveItemToColumn:
    """Tests for move_item_to_column method."""

    @pytest.mark.asyncio
    async def test_move_item_to_column_no_context(self, board_adapter):
        """Test move without project/board context."""
        with pytest.raises(ValidationError):
            await board_adapter.move_item_to_column("item-1", "In Progress", MovedByType.ORCHESTRATOR)


class TestWebhookHandler:
    """Tests for handle_webhook method."""

    @pytest.mark.asyncio
    async def test_webhook_column_changed(self, board_adapter):
        """Test webhook processes column change."""
        events = []
        board_adapter.on("workitem.column_changed", lambda e: events.append(e))

        payload = {
            "action": "edited",
            "projects_v2_item": {
                "id": "PVTI_1",
                "content_node_id": "I_1",
                "project_node_id": "PVT_1",
            },
            "organization": {"id": "org-1"},
            "changes": {
                "field_value": {
                    "field_type": "single_select",
                    "from": "Backlog",
                    "to": "In Progress",
                }
            },
        }

        await board_adapter.handle_webhook(payload)

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, WorkItemColumnChangedEvent)
        assert event.from_column == "Backlog"
        assert event.to_column == "In Progress"
        assert event.moved_by == "human"

    @pytest.mark.asyncio
    async def test_webhook_ignores_non_edited(self, board_adapter):
        """Test webhook ignores non-edited actions."""
        events = []
        board_adapter.on("workitem.column_changed", lambda e: events.append(e))

        payload = {
            "action": "created",
            "projects_v2_item": {"id": "PVTI_1"},
        }

        await board_adapter.handle_webhook(payload)

        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_webhook_ignores_non_field_changes(self, board_adapter):
        """Test webhook ignores non-field changes."""
        events = []
        board_adapter.on("workitem.column_changed", lambda e: events.append(e))

        payload = {
            "action": "edited",
            "projects_v2_item": {"id": "PVTI_1"},
            "changes": {"title": {"from": "Old", "to": "New"}},
        }

        await board_adapter.handle_webhook(payload)

        assert len(events) == 0


class TestPollingMechanism:
    """Tests for polling-based change detection."""

    @pytest.mark.asyncio
    async def test_polling_detects_changes(self, board_adapter, mock_graphql_client, sample_board_response):
        """Test polling detects column changes."""
        events = []
        board_adapter.on("workitem.column_changed", lambda e: events.append(e))

        # First poll returns item in Backlog
        response1 = sample_board_response.copy()

        # Second poll returns item moved to In Progress
        response2 = {
            "node": {
                "id": "PVT_kwDOA1",
                "title": "Test Project",
                "fields": sample_board_response["node"]["fields"],
                "items": {
                    "nodes": [
                        {
                            "id": "PVTI_1",
                            "content": {"number": 1, "id": "I_1"},
                            "fieldValues": {
                                "nodes": [
                                    {
                                        "field": {"name": "Status"},
                                        "name": "In Progress",
                                    }
                                ]
                            },
                        }
                    ]
                },
            }
        }

        mock_graphql_client.execute.side_effect = [response1, response2]

        # Manually call state detection
        board1 = board_adapter._parse_board_response("proj-123", "board-456", response1["node"])
        state1 = board_adapter._extract_item_positions(board1)

        board2 = board_adapter._parse_board_response("proj-123", "board-456", response2["node"])
        state2 = board_adapter._extract_item_positions(board2)

        board_adapter._last_known_state["proj-123:board-456"] = state1
        changes = board_adapter._detect_column_changes("proj-123", "board-456", state2)

        assert len(changes) == 1
        assert changes[0].work_item_id == "1"
        assert changes[0].from_column == "Backlog"
        assert changes[0].to_column == "In Progress"
        assert changes[0].moved_by == "unknown"


class TestEventEmission:
    """Tests for event emission functionality."""

    def test_on_registers_handler(self, board_adapter):
        """Test event handler registration."""
        called = []

        def handler(event):
            called.append(event)

        board_adapter.on("test.event", handler)

        assert len(board_adapter._event_handlers.get("test.event", [])) == 1

    def test_off_unregisters_handler(self, board_adapter):
        """Test event handler unregistration."""

        def handler(event):
            pass

        board_adapter.on("test.event", handler)
        board_adapter.off("test.event", handler)

        assert len(board_adapter._event_handlers.get("test.event", [])) == 0

    def test_emit_calls_handlers(self, board_adapter):
        """Test event emission calls handlers."""
        events = []

        def handler(event):
            events.append(event)

        board_adapter.on("test.event", handler)

        class TestEvent:
            type = "test.event"

        event = TestEvent()
        board_adapter.emit(event)

        assert len(events) == 1
        assert events[0] == event


class TestErrorHandling:
    """Tests for error handling and recovery."""

    @pytest.mark.asyncio
    async def test_invalid_board_response(self, board_adapter, mock_graphql_client):
        """Test handling of invalid board response."""
        mock_graphql_client.execute.return_value = {
            "node": {
                "id": "PVT_1",
                "title": "Test",
                # Missing fields and items
            }
        }

        with pytest.raises(ExternalServiceError):
            await board_adapter.get_board("proj-123", "board-456")

    @pytest.mark.asyncio
    async def test_graphql_error_handling(self, board_adapter, mock_graphql_client):
        """Test GraphQL error handling."""
        mock_graphql_client.execute.side_effect = ExternalServiceError("GitHub", "GraphQL error: Rate limit exceeded")

        with pytest.raises(ExternalServiceError):
            await board_adapter.get_board("proj-123", "board-456")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
