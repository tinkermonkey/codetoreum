"""Unit tests for ActiveRunInfo value object validation."""

import pytest

from codetoreum.ports.output.active_workflow_run_registry import ActiveRunInfo


class TestActiveRunInfo:
    """Tests for ActiveRunInfo __post_init__ validation."""

    def test_create_valid(self):
        """Happy path: all fields present."""
        info = ActiveRunInfo(
            work_item_id="wi-1",
            run_id="run-1",
            stage_name="coding",
            project_id="proj-1",
            board_id="board-1",
        )
        assert info.work_item_id == "wi-1"
        assert info.run_id == "run-1"
        assert info.stage_name == "coding"
        assert info.project_id == "proj-1"
        assert info.board_id == "board-1"

    def test_empty_work_item_id_raises(self):
        """Empty work_item_id must raise ValueError."""
        with pytest.raises(ValueError, match="work_item_id"):
            ActiveRunInfo(work_item_id="", run_id="run-1", stage_name="coding", project_id="proj-1", board_id="board-1")

    def test_empty_run_id_raises(self):
        """Empty run_id must raise ValueError."""
        with pytest.raises(ValueError, match="run_id"):
            ActiveRunInfo(work_item_id="wi-1", run_id="", stage_name="coding", project_id="proj-1", board_id="board-1")

    def test_empty_stage_name_raises(self):
        """Empty stage_name must raise ValueError."""
        with pytest.raises(ValueError, match="stage_name"):
            ActiveRunInfo(work_item_id="wi-1", run_id="run-1", stage_name="", project_id="proj-1", board_id="board-1")

    def test_empty_project_id_raises(self):
        """Empty project_id must raise ValueError."""
        with pytest.raises(ValueError, match="project_id"):
            ActiveRunInfo(work_item_id="wi-1", run_id="run-1", stage_name="coding", project_id="", board_id="board-1")

    def test_empty_board_id_raises(self):
        """Empty board_id must raise ValueError."""
        with pytest.raises(ValueError, match="board_id"):
            ActiveRunInfo(work_item_id="wi-1", run_id="run-1", stage_name="coding", project_id="proj-1", board_id="")

    def test_is_frozen(self):
        """ActiveRunInfo must be immutable after construction."""
        from dataclasses import FrozenInstanceError

        info = ActiveRunInfo(
            work_item_id="wi-1", run_id="run-1", stage_name="coding", project_id="proj-1", board_id="board-1"
        )
        with pytest.raises(FrozenInstanceError):
            info.work_item_id = "wi-2"  # type: ignore
