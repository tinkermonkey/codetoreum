"""Unit tests for GitHubBoardAdapter.add_item_to_column.

add_item_to_column must actually ADD the backing issue to the GitHub Project
board (addProjectV2ItemById) before setting its column — it is not a no-op
alias of move_item_to_column. These tests mock the GraphQL client and the work
item query port so no live GitHub access is needed.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.adapters.secondary.github_board_adapter import GitHubBoardAdapter
from codetoreum.ports.exceptions import ResourceNotFoundError
from codetoreum.ports.output.board_service import (
    BoardColumn,
    MovedByType,
    ProjectBoard,
)


def _make_adapter() -> GitHubBoardAdapter:
    ticket_adapter = MagicMock()
    ticket_adapter.config.organization = "tinkermonkey"
    ticket_adapter._get_repo = MagicMock(return_value="rounds")

    graphql = AsyncMock()
    work_item_service = AsyncMock()

    adapter = GitHubBoardAdapter(
        ticket_adapter=ticket_adapter,
        graphql_client=graphql,
        webhook_enabled=False,
        work_item_service=work_item_service,
    )
    adapter._current_project_id = "rounds"
    adapter._current_board_id = "PVT_board"

    # Pre-populate the field/option caches normally filled by get_board(), and
    # stub get_board so we don't hit GraphQL for the board fetch.
    adapter._status_field_id_cache["PVT_board"] = "FIELD_status"
    adapter._option_id_cache["PVT_board"] = {"Backlog": "OPT_backlog"}
    board = ProjectBoard(
        id="PVT_board",
        name="Board",
        project_id="rounds",
        columns=(BoardColumn(id="OPT_backlog", name="Backlog", position=0, work_item_ids=()),),
    )
    adapter.get_board = AsyncMock(return_value=board)  # type: ignore[method-assign]
    return adapter


@pytest.mark.asyncio
async def test_add_item_to_column_adds_issue_then_sets_status():
    adapter = _make_adapter()

    # work item UUID -> external issue number
    adapter._work_item_service.get_work_item.return_value = MagicMock(id="wi-uuid-1", external_id="79")
    # GraphQL responses, in call order: issue node id, addProjectV2ItemById, set status
    adapter._graphql.execute.side_effect = [
        {"repository": {"issue": {"id": "I_issue79"}}},
        {"addProjectV2ItemById": {"item": {"id": "PVTI_new"}}},
        {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_new"}}},
    ]

    emitted: list = []
    adapter.emit = MagicMock(side_effect=lambda e: emitted.append(e))  # type: ignore[method-assign]

    result = await adapter.add_item_to_column("wi-uuid-1", "Backlog", MovedByType.GITHUB_WEBHOOK)

    # Three GraphQL calls were made.
    assert adapter._graphql.execute.await_count == 3
    calls = adapter._graphql.execute.await_args_list

    # 1) issue node id lookup carries owner/repo/number
    assert calls[0].args[1] == {"owner": "tinkermonkey", "repo": "rounds", "number": 79}
    # 2) addProjectV2ItemById uses the resolved issue node id as contentId
    assert calls[1].args[1] == {"projectId": "PVT_board", "contentId": "I_issue79"}
    # 3) status mutation targets the freshly created PVTI
    assert calls[2].args[1]["itemId"] == "PVTI_new"
    assert calls[2].args[1]["optionId"] == "OPT_backlog"

    # PVTI cached under the UUID so a later move() succeeds before the next poll.
    assert adapter._pvti_node_id_by_uuid["wi-uuid-1"] == "PVTI_new"

    # Initial placement: from_column is None.
    assert result.from_column is None
    assert result.to_column == "Backlog"
    assert result.work_item_id == "wi-uuid-1"

    # Event emitted with from_column=None (initial placement, not a transition).
    assert len(emitted) == 1
    assert emitted[0].from_column is None
    assert emitted[0].to_column == "Backlog"
    assert emitted[0].work_item_id == "wi-uuid-1"


@pytest.mark.asyncio
async def test_add_item_to_column_rejects_item_without_external_id():
    adapter = _make_adapter()
    adapter._work_item_service.get_work_item.return_value = MagicMock(id="wi-uuid-1", external_id=None)

    with pytest.raises(ResourceNotFoundError):
        await adapter.add_item_to_column("wi-uuid-1", "Backlog", MovedByType.GITHUB_WEBHOOK)

    # No board mutation attempted.
    adapter._graphql.execute.assert_not_awaited()
