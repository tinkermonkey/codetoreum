"""Tests for WorkflowOrchestrator repair-cycle completion: board move + read-model mirror.

ORCHESTRATOR board moves suppress WorkItemColumnChangedEvent, so the repair-cycle
handler must mirror the new column onto the work item read model itself —
otherwise reads stay stuck in the agent column while the board advances.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.application.workflow_orchestrator import WorkflowOrchestrator
from codetoreum.domain.events.repair_cycle_events import RepairCycleCompletedEvent
from codetoreum.domain.repair_cycle_types import CycleResult, RepairTestResult, RepairTestType
from codetoreum.ports.output.board_service import MovedByType


def _completed_event(*, overall_success: bool, work_item_id="item-1", board_id="board-1"):
    final_result = RepairTestResult(
        test_type=RepairTestType.UNIT,
        iteration=1,
        passed=1,
        failed=0,
        warnings=0,
        failures=(),
        warning_list=(),
        raw_output="ok",
        timestamp="2026-06-10T00:00:00+00:00",
    )
    cycle_result = CycleResult(
        test_type=RepairTestType.UNIT,
        passed=True,
        iterations=1,
        final_result=final_result,
        error=None,
        files_fixed=0,
        warnings_reviewed=0,
        duration_seconds=1.0,
    )
    return RepairCycleCompletedEvent(
        type="repair_cycle.completed",
        timestamp="2026-06-10T00:00:00+00:00",
        source="repair_cycle",
        overall_success=overall_success,
        test_results=(cycle_result,),
        total_agent_calls=1,
        duration_seconds=1.0,
        workflow_run_id="run-1",
        work_item_id=work_item_id,
        board_id=board_id,
    )


def _orchestrator(*, board_service, workflow_config, work_item_service):
    # event_bus=None so __init__ does not subscribe; we call the handler directly.
    return WorkflowOrchestrator(
        task_queue=AsyncMock(),
        config=MagicMock(),
        workflow_state=AsyncMock(),
        decision_events=AsyncMock(),
        event_store=AsyncMock(),
        ticket_system=AsyncMock(),
        event_bus=None,
        board_service=board_service,
        workflow_config=workflow_config,
        work_item_service=work_item_service,
    )


def _template(*, next_column=None, on_failure_column=None):
    template = MagicMock()
    template.get_next_column = MagicMock(return_value=next_column)
    column_config = MagicMock()
    column_config.on_failure_column = on_failure_column
    template.get_column_config = MagicMock(return_value=column_config)
    return template


@pytest.mark.asyncio
async def test_repair_success_advances_and_mirrors_next_column():
    board = AsyncMock()
    board.get_item_position.return_value = MagicMock(column_name="Development")
    workflow_config = AsyncMock()
    workflow_config.get_board_workflow_template.return_value = _template(next_column="Testing")
    work_item_service = AsyncMock()

    orch = _orchestrator(board_service=board, workflow_config=workflow_config, work_item_service=work_item_service)

    await orch._handle_repair_cycle_completed(_completed_event(overall_success=True))

    board.move_item_to_column.assert_awaited_once_with("item-1", "Testing", MovedByType.ORCHESTRATOR)
    work_item_service.record_board_position.assert_awaited_once_with("item-1", "Testing")


@pytest.mark.asyncio
async def test_repair_failure_routes_and_mirrors_failure_column():
    board = AsyncMock()
    board.get_item_position.return_value = MagicMock(column_name="Development")
    workflow_config = AsyncMock()
    workflow_config.get_board_workflow_template.return_value = _template(on_failure_column="Backlog")
    work_item_service = AsyncMock()

    orch = _orchestrator(board_service=board, workflow_config=workflow_config, work_item_service=work_item_service)

    await orch._handle_repair_cycle_completed(_completed_event(overall_success=False))

    board.move_item_to_column.assert_awaited_once_with("item-1", "Backlog", MovedByType.ORCHESTRATOR)
    work_item_service.record_board_position.assert_awaited_once_with("item-1", "Backlog")


@pytest.mark.asyncio
async def test_repair_success_at_terminal_column_does_not_move_or_mirror():
    board = AsyncMock()
    board.get_item_position.return_value = MagicMock(column_name="Done")
    workflow_config = AsyncMock()
    workflow_config.get_board_workflow_template.return_value = _template(next_column=None)
    work_item_service = AsyncMock()

    orch = _orchestrator(board_service=board, workflow_config=workflow_config, work_item_service=work_item_service)

    await orch._handle_repair_cycle_completed(_completed_event(overall_success=True))

    board.move_item_to_column.assert_not_awaited()
    work_item_service.record_board_position.assert_not_awaited()
