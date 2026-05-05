"""Unit tests for GitHubBoardAdapter field and option ID lookup methods.

Tests cover:
- _find_status_field_id: Extraction of Status field ID from ProjectBoard
- _find_option_id: Lookup of option ID by column name
- Edge cases: missing field IDs, nonexistent columns, empty names
- Integration: Field IDs correctly passed to GraphQL mutations
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.adapters.secondary.github_board_adapter import GitHubBoardAdapter
from codetoreum.adapters.secondary.github_ticket_adapter import (
    GitHubConfig,
    GitHubTicketAdapter,
)
from codetoreum.infrastructure.http.github_graphql_client import GitHubGraphQLClient
from codetoreum.ports.output.board_service import BoardColumn, ProjectBoard


@pytest.fixture
def github_config():
    """GitHub configuration fixture."""
    return GitHubConfig(
        token="test-token",
        organization="test-org",
        repository="test-repo",
    )


@pytest.fixture
def mock_graphql_client():
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
def sample_board_with_field_id():
    """Create a sample board with status_field_id set."""
    return ProjectBoard(
        id="board-456",
        name="Test Board",
        project_id="proj-123",
        columns=(
            BoardColumn(
                id="opt-1",
                name="Backlog",
                position=0,
                work_item_ids=("1", "2"),
            ),
            BoardColumn(
                id="opt-2",
                name="In Progress",
                position=1,
                work_item_ids=("3",),
            ),
            BoardColumn(
                id="opt-3",
                name="Review",
                position=2,
                work_item_ids=(),
            ),
            BoardColumn(
                id="opt-4",
                name="Done",
                position=3,
                work_item_ids=(),
            ),
        ),
        status_field_id="PVTF_lADOA1",
    )


class TestFindStatusFieldId:
    """Tests for _find_status_field_id method."""

    def test_find_status_field_id_returns_field_id(self, board_adapter, sample_board_with_field_id):
        """Test that _find_status_field_id extracts field ID from board."""
        field_id = board_adapter._find_status_field_id(sample_board_with_field_id)

        assert field_id is not None
        assert field_id == "PVTF_lADOA1"

    def test_find_status_field_id_returns_none_when_not_set(self, board_adapter):
        """Test that _find_status_field_id returns None if field ID not set."""
        board = ProjectBoard(
            id="board-456",
            name="Test Board",
            project_id="proj-123",
            columns=(
                BoardColumn(
                    id="opt-1",
                    name="Backlog",
                    position=0,
                    work_item_ids=(),
                ),
            ),
            status_field_id=None,
        )

        field_id = board_adapter._find_status_field_id(board)

        assert field_id is None

    def test_find_status_field_id_validates_empty_string(self, board_adapter):
        """Test that ProjectBoard rejects empty string field ID."""
        # Empty string should be rejected by ProjectBoard validation
        with pytest.raises(ValueError, match="status_field_id must be None or a non-empty string"):
            ProjectBoard(
                id="board-456",
                name="Test Board",
                project_id="proj-123",
                columns=(
                    BoardColumn(
                        id="opt-1",
                        name="Backlog",
                        position=0,
                        work_item_ids=(),
                    ),
                ),
                status_field_id="",
            )

    def test_find_status_field_id_various_field_formats(self, board_adapter):
        """Test _find_status_field_id with various field ID formats."""
        for field_id_value in ["PVTF_kwDOA1234", "field-123", "F1", "status-field"]:
            board = ProjectBoard(
                id="board-456",
                name="Test Board",
                project_id="proj-123",
                columns=(
                    BoardColumn(
                        id="opt-1",
                        name="Backlog",
                        position=0,
                        work_item_ids=(),
                    ),
                ),
                status_field_id=field_id_value,
            )

            field_id = board_adapter._find_status_field_id(board)

            assert field_id == field_id_value


class TestFindOptionId:
    """Tests for _find_option_id method."""

    def test_find_option_id_by_column_name(self, board_adapter, sample_board_with_field_id):
        """Test that _find_option_id finds correct option ID by column name."""
        option_id = board_adapter._find_option_id(sample_board_with_field_id, "PVTF_lADOA1", "In Progress")

        assert option_id is not None
        assert option_id == "opt-2"

    def test_find_option_id_backlog(self, board_adapter, sample_board_with_field_id):
        """Test finding option ID for Backlog column."""
        option_id = board_adapter._find_option_id(sample_board_with_field_id, None, "Backlog")

        assert option_id == "opt-1"

    def test_find_option_id_review(self, board_adapter, sample_board_with_field_id):
        """Test finding option ID for Review column."""
        option_id = board_adapter._find_option_id(sample_board_with_field_id, None, "Review")

        assert option_id == "opt-3"

    def test_find_option_id_done(self, board_adapter, sample_board_with_field_id):
        """Test finding option ID for Done column."""
        option_id = board_adapter._find_option_id(sample_board_with_field_id, None, "Done")

        assert option_id == "opt-4"

    def test_find_option_id_not_found(self, board_adapter, sample_board_with_field_id):
        """Test that _find_option_id returns None for nonexistent column."""
        option_id = board_adapter._find_option_id(sample_board_with_field_id, None, "Nonexistent")

        assert option_id is None

    def test_find_option_id_empty_column_name(self, board_adapter, sample_board_with_field_id):
        """Test that _find_option_id returns None for empty column name."""
        option_id = board_adapter._find_option_id(sample_board_with_field_id, None, "")

        assert option_id is None

    def test_find_option_id_case_sensitive(self, board_adapter, sample_board_with_field_id):
        """Test that _find_option_id is case-sensitive in column name matching."""
        # "in progress" (lowercase) should not match "In Progress"
        option_id = board_adapter._find_option_id(sample_board_with_field_id, None, "in progress")

        assert option_id is None

    def test_find_option_id_whitespace_sensitive(self, board_adapter, sample_board_with_field_id):
        """Test that _find_option_id is whitespace-sensitive in column name matching."""
        # "In Progress " (trailing space) should not match "In Progress"
        option_id = board_adapter._find_option_id(sample_board_with_field_id, None, "In Progress ")

        assert option_id is None

    def test_find_option_id_field_id_parameter_unused(self, board_adapter, sample_board_with_field_id):
        """Test that field_id parameter doesn't affect option lookup."""
        # Option lookup is based on column name only, not field_id
        option_id_1 = board_adapter._find_option_id(sample_board_with_field_id, "PVTF_lADOA1", "In Progress")
        option_id_2 = board_adapter._find_option_id(sample_board_with_field_id, None, "In Progress")
        option_id_3 = board_adapter._find_option_id(sample_board_with_field_id, "different-field-id", "In Progress")

        assert option_id_1 == option_id_2 == option_id_3 == "opt-2"

    def test_find_option_id_with_many_columns(self, board_adapter):
        """Test _find_option_id with a large number of columns."""
        # Create a board with many columns
        columns = [
            BoardColumn(
                id=f"opt-{i}",
                name=f"Stage-{i}",
                position=i,
                work_item_ids=(),
            )
            for i in range(50)
        ]

        board = ProjectBoard(
            id="board-456",
            name="Large Board",
            project_id="proj-123",
            columns=tuple(columns),
            status_field_id="PVTF_large",
        )

        # Should find the last column
        option_id = board_adapter._find_option_id(board, None, "Stage-49")

        assert option_id == "opt-49"

    def test_find_option_id_empty_board(self, board_adapter):
        """Test _find_option_id with a board that has no columns."""
        board = ProjectBoard(
            id="board-456",
            name="Empty Board",
            project_id="proj-123",
            columns=(),
            status_field_id="PVTF_empty",
        )

        option_id = board_adapter._find_option_id(board, None, "Backlog")

        assert option_id is None


class TestFieldIdPropagationThroughParsing:
    """Tests for field ID extraction during board parsing."""

    @pytest.mark.asyncio
    async def test_status_field_id_extracted_during_parsing(self, board_adapter, mock_graphql_client):
        """Test that status_field_id is extracted and stored during _parse_board_response."""
        graphql_response = {
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
                        }
                    ]
                },
            }
        }

        mock_graphql_client.execute.return_value = graphql_response

        board = await board_adapter.get_board("proj-123", "board-456")

        # Verify status_field_id was extracted
        assert board.status_field_id == "PVTF_lADOA1"

    @pytest.mark.asyncio
    async def test_column_ids_are_option_ids(self, board_adapter, mock_graphql_client):
        """Test that column.id values are the option IDs from the Status field."""
        graphql_response = {
            "node": {
                "id": "PVT_kwDOA1",
                "title": "Test Project",
                "fields": {
                    "nodes": [
                        {
                            "id": "PVTF_lADOA1",
                            "name": "Status",
                            "options": [
                                {"id": "status-backlog-opt", "name": "Backlog"},
                                {"id": "status-progress-opt", "name": "In Progress"},
                                {"id": "status-review-opt", "name": "Review"},
                            ],
                        }
                    ]
                },
                "items": {"nodes": []},
            }
        }

        mock_graphql_client.execute.return_value = graphql_response

        board = await board_adapter.get_board("proj-123", "board-456")

        # Verify that column IDs match the option IDs
        assert board.columns[0].id == "status-backlog-opt"
        assert board.columns[1].id == "status-progress-opt"
        assert board.columns[2].id == "status-review-opt"

    @pytest.mark.asyncio
    async def test_field_and_option_ids_used_in_move_operation(self, board_adapter, mock_graphql_client):
        """Test that extracted field and option IDs are used in move_item_to_column."""
        graphql_response = {
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
                        }
                    ]
                },
            }
        }

        mutation_response = {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_1"}}}

        # Set context
        board_adapter._current_project_id = "proj-123"
        board_adapter._current_board_id = "board-456"

        # Mock both calls: first for get_board, second for mutation
        mock_graphql_client.execute.side_effect = [graphql_response, mutation_response]

        from codetoreum.ports.output.board_service import MovedByType

        result = await board_adapter.move_item_to_column("1", "In Progress", MovedByType.ORCHESTRATOR)

        assert result.to_column == "In Progress"

        # Verify mutation was called with correct IDs
        mutation_call = mock_graphql_client.execute.call_args_list[1]
        mutation_vars = mutation_call[0][1]

        assert mutation_vars["fieldId"] == "PVTF_lADOA1"
        assert mutation_vars["optionId"] == "opt-2"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
