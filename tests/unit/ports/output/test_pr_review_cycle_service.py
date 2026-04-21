"""Unit tests for PR Review Cycle port interface (output port).

Tests cover:
- PRReviewCycleRequest frozen dataclass validation
- PRReviewCycleStateData frozen dataclass validation
- IPRReviewCycle ABC enforcement
- Immutability of frozen dataclasses
- __post_init__ validation for all constraints
"""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from codetoreum.domain.pr_review_cycle_types import PRReviewCycleConfig, PRReviewCycleState, PRReviewStatus
from codetoreum.ports.output.pr_review_cycle_service import (
    IPRReviewCycle,
    PRReviewCycleRequest,
    PRReviewCycleStateData,
)


class TestPRReviewCycleRequest:
    """Tests for PRReviewCycleRequest frozen dataclass."""

    @staticmethod
    def _create_test_config() -> PRReviewCycleConfig:
        """Create a minimal config for testing."""
        return PRReviewCycleConfig(
            code_review_agent="agent-1",
            verifier_agent="agent-2",
            consolidation_agent="agent-3",
            on_issues_found_column="Review",
            on_approved_column="Done",
        )

    def test_create_valid_request(self):
        """Test creating a valid request."""
        config = self._create_test_config()
        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="123",
            pr_url="https://github.com/owner/repo/pull/123",
            discussion_id="discussion-1",
            cycle_number=1,
            config=config,
            workflow_run_id="run-1",
        )
        assert request.work_item_id == "item-1"
        assert request.project_id == "proj-1"
        assert request.board_id == "board-1"
        assert request.pr_id == "123"
        assert request.pr_url == "https://github.com/owner/repo/pull/123"
        assert request.discussion_id == "discussion-1"
        assert request.cycle_number == 1
        assert request.config == config
        assert request.workflow_run_id == "run-1"

    def test_request_frozen(self):
        """Test request is immutable (frozen)."""
        config = self._create_test_config()
        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="123",
            pr_url="https://github.com/owner/repo/pull/123",
            discussion_id="discussion-1",
            cycle_number=1,
            config=config,
            workflow_run_id="run-1",
        )
        with pytest.raises(FrozenInstanceError):
            request.work_item_id = "item-2"

    def test_request_with_none_optional_fields(self):
        """Test request accepts None for optional pr_id, pr_url, discussion_id."""
        config = self._create_test_config()
        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id=None,
            pr_url=None,
            discussion_id=None,
            cycle_number=1,
            config=config,
            workflow_run_id="run-1",
        )
        assert request.pr_id is None
        assert request.pr_url is None
        assert request.discussion_id is None

    def test_request_empty_work_item_id(self):
        """Test request rejects empty work_item_id."""
        config = self._create_test_config()
        with pytest.raises(ValueError, match="work_item_id must be a non-empty string"):
            PRReviewCycleRequest(
                work_item_id="",
                project_id="proj-1",
                board_id="board-1",
                pr_id="123",
                pr_url="https://github.com/owner/repo/pull/123",
                discussion_id="discussion-1",
                cycle_number=1,
                config=config,
                workflow_run_id="run-1",
            )

    def test_request_empty_project_id(self):
        """Test request rejects empty project_id."""
        config = self._create_test_config()
        with pytest.raises(ValueError, match="project_id must be a non-empty string"):
            PRReviewCycleRequest(
                work_item_id="item-1",
                project_id="",
                board_id="board-1",
                pr_id="123",
                pr_url="https://github.com/owner/repo/pull/123",
                discussion_id="discussion-1",
                cycle_number=1,
                config=config,
                workflow_run_id="run-1",
            )

    def test_request_empty_board_id(self):
        """Test request rejects empty board_id."""
        config = self._create_test_config()
        with pytest.raises(ValueError, match="board_id must be a non-empty string"):
            PRReviewCycleRequest(
                work_item_id="item-1",
                project_id="proj-1",
                board_id="",
                pr_id="123",
                pr_url="https://github.com/owner/repo/pull/123",
                discussion_id="discussion-1",
                cycle_number=1,
                config=config,
                workflow_run_id="run-1",
            )

    def test_request_empty_workflow_run_id(self):
        """Test request rejects empty workflow_run_id."""
        config = self._create_test_config()
        with pytest.raises(ValueError, match="workflow_run_id must be a non-empty string"):
            PRReviewCycleRequest(
                work_item_id="item-1",
                project_id="proj-1",
                board_id="board-1",
                pr_id="123",
                pr_url="https://github.com/owner/repo/pull/123",
                discussion_id="discussion-1",
                cycle_number=1,
                config=config,
                workflow_run_id="",
            )

    def test_request_cycle_number_zero(self):
        """Test request rejects cycle_number of 0."""
        config = self._create_test_config()
        with pytest.raises(ValueError, match="cycle_number must be a positive integer \\(1-based\\)"):
            PRReviewCycleRequest(
                work_item_id="item-1",
                project_id="proj-1",
                board_id="board-1",
                pr_id="123",
                pr_url="https://github.com/owner/repo/pull/123",
                discussion_id="discussion-1",
                cycle_number=0,
                config=config,
                workflow_run_id="run-1",
            )

    def test_request_cycle_number_negative(self):
        """Test request rejects negative cycle_number."""
        config = self._create_test_config()
        with pytest.raises(ValueError, match="cycle_number must be a positive integer \\(1-based\\)"):
            PRReviewCycleRequest(
                work_item_id="item-1",
                project_id="proj-1",
                board_id="board-1",
                pr_id="123",
                pr_url="https://github.com/owner/repo/pull/123",
                discussion_id="discussion-1",
                cycle_number=-1,
                config=config,
                workflow_run_id="run-1",
            )

    def test_request_cycle_number_as_bool(self):
        """Test request rejects boolean value for cycle_number."""
        config = self._create_test_config()
        # Note: In Python, bool is a subclass of int, but isinstance(True, bool) returns True
        # The validation specifically checks isinstance(self.cycle_number, bool) to reject it
        with pytest.raises(ValueError, match="cycle_number must be a positive integer \\(1-based\\)"):
            # We use type() to create an instance that's considered a bool
            request = PRReviewCycleRequest(
                work_item_id="item-1",
                project_id="proj-1",
                board_id="board-1",
                pr_id="123",
                pr_url="https://github.com/owner/repo/pull/123",
                discussion_id="discussion-1",
                cycle_number=True,  # This is a bool, which should be rejected
                config=config,
                workflow_run_id="run-1",
            )

    def test_request_empty_pr_id_when_not_none(self):
        """Test request rejects empty string for pr_id when not None."""
        config = self._create_test_config()
        with pytest.raises(ValueError, match="pr_id must be a non-empty string or None"):
            PRReviewCycleRequest(
                work_item_id="item-1",
                project_id="proj-1",
                board_id="board-1",
                pr_id="",
                pr_url="https://github.com/owner/repo/pull/123",
                discussion_id="discussion-1",
                cycle_number=1,
                config=config,
                workflow_run_id="run-1",
            )

    def test_request_empty_pr_url_when_not_none(self):
        """Test request rejects empty string for pr_url when not None."""
        config = self._create_test_config()
        with pytest.raises(ValueError, match="pr_url must be a non-empty string or None"):
            PRReviewCycleRequest(
                work_item_id="item-1",
                project_id="proj-1",
                board_id="board-1",
                pr_id="123",
                pr_url="",
                discussion_id="discussion-1",
                cycle_number=1,
                config=config,
                workflow_run_id="run-1",
            )

    def test_request_empty_discussion_id_when_not_none(self):
        """Test request rejects empty string for discussion_id when not None."""
        config = self._create_test_config()
        with pytest.raises(ValueError, match="discussion_id must be a non-empty string or None"):
            PRReviewCycleRequest(
                work_item_id="item-1",
                project_id="proj-1",
                board_id="board-1",
                pr_id="123",
                pr_url="https://github.com/owner/repo/pull/123",
                discussion_id="",
                cycle_number=1,
                config=config,
                workflow_run_id="run-1",
            )

    def test_request_invalid_config_type(self):
        """Test request rejects invalid config type."""
        with pytest.raises(ValueError, match="config must be a PRReviewCycleConfig instance"):
            PRReviewCycleRequest(
                work_item_id="item-1",
                project_id="proj-1",
                board_id="board-1",
                pr_id="123",
                pr_url="https://github.com/owner/repo/pull/123",
                discussion_id="discussion-1",
                cycle_number=1,
                config="not a config",  # Invalid type
                workflow_run_id="run-1",
            )

    def test_request_invalid_config_dict(self):
        """Test request rejects dict for config."""
        with pytest.raises(ValueError, match="config must be a PRReviewCycleConfig instance"):
            PRReviewCycleRequest(
                work_item_id="item-1",
                project_id="proj-1",
                board_id="board-1",
                pr_id="123",
                pr_url="https://github.com/owner/repo/pull/123",
                discussion_id="discussion-1",
                cycle_number=1,
                config={},  # Invalid type
                workflow_run_id="run-1",
            )


class TestPRReviewCycleStateData:
    """Tests for PRReviewCycleStateData frozen dataclass."""

    @staticmethod
    def _create_test_config() -> PRReviewCycleConfig:
        """Create a minimal config for testing."""
        return PRReviewCycleConfig(
            code_review_agent="agent-1",
            verifier_agent="agent-2",
            consolidation_agent="agent-3",
            on_issues_found_column="Review",
            on_approved_column="Done",
        )

    def test_create_valid_state_data(self):
        """Test creating valid state data."""
        now = datetime.now(UTC).isoformat()
        config = self._create_test_config()
        cycle_state = PRReviewCycleState(
            cycle_id="cycle-1",
            pr_id="pr-123",
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            status=PRReviewStatus.PENDING,
            cycle_number=1,
            current_phase="init",
            findings=[],
            phase_outputs=[],
            config=config,
            started_at=now,
            updated_at=now,
        )
        state = PRReviewCycleStateData(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            cycle_number=1,
            cycle_state=cycle_state,
            created_at=now,
            updated_at=now,
        )
        assert state.work_item_id == "item-1"
        assert state.project_id == "proj-1"
        assert state.board_id == "board-1"
        assert state.cycle_number == 1
        assert state.cycle_state == cycle_state
        assert state.created_at == now
        assert state.updated_at == now

    def test_state_data_frozen(self):
        """Test state data is immutable (frozen)."""
        now = datetime.now(UTC).isoformat()
        config = self._create_test_config()
        cycle_state = PRReviewCycleState(
            cycle_id="cycle-1",
            pr_id="pr-123",
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            status=PRReviewStatus.PENDING,
            cycle_number=1,
            current_phase="init",
            findings=[],
            phase_outputs=[],
            config=config,
            started_at=now,
            updated_at=now,
        )
        state = PRReviewCycleStateData(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            cycle_number=1,
            cycle_state=cycle_state,
            created_at=now,
            updated_at=now,
        )
        with pytest.raises(FrozenInstanceError):
            state.work_item_id = "item-2"

    def test_state_data_empty_work_item_id(self):
        """Test state data rejects empty work_item_id."""
        now = datetime.now(UTC).isoformat()
        config = self._create_test_config()
        cycle_state = PRReviewCycleState(
            cycle_id="cycle-1",
            pr_id="pr-123",
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            status=PRReviewStatus.PENDING,
            cycle_number=1,
            current_phase="init",
            findings=[],
            phase_outputs=[],
            config=config,
            started_at=now,
            updated_at=now,
        )
        with pytest.raises(ValueError, match="work_item_id must be a non-empty string"):
            PRReviewCycleStateData(
                work_item_id="",
                project_id="proj-1",
                board_id="board-1",
                cycle_number=1,
                cycle_state=cycle_state,
                created_at=now,
                updated_at=now,
            )

    def test_state_data_empty_project_id(self):
        """Test state data rejects empty project_id."""
        now = datetime.now(UTC).isoformat()
        config = self._create_test_config()
        cycle_state = PRReviewCycleState(
            cycle_id="cycle-1",
            pr_id="pr-123",
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            status=PRReviewStatus.PENDING,
            cycle_number=1,
            current_phase="init",
            findings=[],
            phase_outputs=[],
            config=config,
            started_at=now,
            updated_at=now,
        )
        with pytest.raises(ValueError, match="project_id must be a non-empty string"):
            PRReviewCycleStateData(
                work_item_id="item-1",
                project_id="",
                board_id="board-1",
                cycle_number=1,
                cycle_state=cycle_state,
                created_at=now,
                updated_at=now,
            )

    def test_state_data_empty_board_id(self):
        """Test state data rejects empty board_id."""
        now = datetime.now(UTC).isoformat()
        config = self._create_test_config()
        cycle_state = PRReviewCycleState(
            cycle_id="cycle-1",
            pr_id="pr-123",
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            status=PRReviewStatus.PENDING,
            cycle_number=1,
            current_phase="init",
            findings=[],
            phase_outputs=[],
            config=config,
            started_at=now,
            updated_at=now,
        )
        with pytest.raises(ValueError, match="board_id must be a non-empty string"):
            PRReviewCycleStateData(
                work_item_id="item-1",
                project_id="proj-1",
                board_id="",
                cycle_number=1,
                cycle_state=cycle_state,
                created_at=now,
                updated_at=now,
            )

    def test_state_data_cycle_number_zero(self):
        """Test state data rejects cycle_number of 0."""
        now = datetime.now(UTC).isoformat()
        config = self._create_test_config()
        cycle_state = PRReviewCycleState(
            cycle_id="cycle-1",
            pr_id="pr-123",
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            status=PRReviewStatus.PENDING,
            cycle_number=1,
            current_phase="init",
            findings=[],
            phase_outputs=[],
            config=config,
            started_at=now,
            updated_at=now,
        )
        with pytest.raises(ValueError, match="cycle_number must be a positive integer \\(1-based\\)"):
            PRReviewCycleStateData(
                work_item_id="item-1",
                project_id="proj-1",
                board_id="board-1",
                cycle_number=0,
                cycle_state=cycle_state,
                created_at=now,
                updated_at=now,
            )

    def test_state_data_cycle_number_negative(self):
        """Test state data rejects negative cycle_number."""
        now = datetime.now(UTC).isoformat()
        config = self._create_test_config()
        cycle_state = PRReviewCycleState(
            cycle_id="cycle-1",
            pr_id="pr-123",
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            status=PRReviewStatus.PENDING,
            cycle_number=1,
            current_phase="init",
            findings=[],
            phase_outputs=[],
            config=config,
            started_at=now,
            updated_at=now,
        )
        with pytest.raises(ValueError, match="cycle_number must be a positive integer \\(1-based\\)"):
            PRReviewCycleStateData(
                work_item_id="item-1",
                project_id="proj-1",
                board_id="board-1",
                cycle_number=-5,
                cycle_state=cycle_state,
                created_at=now,
                updated_at=now,
            )

    def test_state_data_cycle_number_as_bool(self):
        """Test state data rejects boolean value for cycle_number."""
        now = datetime.now(UTC).isoformat()
        config = self._create_test_config()
        cycle_state = PRReviewCycleState(
            cycle_id="cycle-1",
            pr_id="pr-123",
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            status=PRReviewStatus.PENDING,
            cycle_number=1,
            current_phase="init",
            findings=[],
            phase_outputs=[],
            config=config,
            started_at=now,
            updated_at=now,
        )
        with pytest.raises(ValueError, match="cycle_number must be a positive integer \\(1-based\\)"):
            PRReviewCycleStateData(
                work_item_id="item-1",
                project_id="proj-1",
                board_id="board-1",
                cycle_number=True,  # This is a bool, which should be rejected
                cycle_state=cycle_state,
                created_at=now,
                updated_at=now,
            )

    def test_state_data_invalid_cycle_state_type(self):
        """Test state data rejects invalid cycle_state type."""
        now = datetime.now(UTC).isoformat()
        with pytest.raises(ValueError, match="cycle_state must be a PRReviewCycleState instance"):
            PRReviewCycleStateData(
                work_item_id="item-1",
                project_id="proj-1",
                board_id="board-1",
                cycle_number=1,
                cycle_state="not a state",  # Invalid type
                created_at=now,
                updated_at=now,
            )

    def test_state_data_empty_created_at(self):
        """Test state data rejects empty created_at."""
        now = datetime.now(UTC).isoformat()
        config = self._create_test_config()
        cycle_state = PRReviewCycleState(
            cycle_id="cycle-1",
            pr_id="pr-123",
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            status=PRReviewStatus.PENDING,
            cycle_number=1,
            current_phase="init",
            findings=[],
            phase_outputs=[],
            config=config,
            started_at=now,
            updated_at=now,
        )
        with pytest.raises(ValueError, match="created_at must be a non-empty ISO timestamp string"):
            PRReviewCycleStateData(
                work_item_id="item-1",
                project_id="proj-1",
                board_id="board-1",
                cycle_number=1,
                cycle_state=cycle_state,
                created_at="",
                updated_at=now,
            )

    def test_state_data_empty_updated_at(self):
        """Test state data rejects empty updated_at."""
        now = datetime.now(UTC).isoformat()
        config = self._create_test_config()
        cycle_state = PRReviewCycleState(
            cycle_id="cycle-1",
            pr_id="pr-123",
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            status=PRReviewStatus.PENDING,
            cycle_number=1,
            current_phase="init",
            findings=[],
            phase_outputs=[],
            config=config,
            started_at=now,
            updated_at=now,
        )
        with pytest.raises(ValueError, match="updated_at must be a non-empty ISO timestamp string"):
            PRReviewCycleStateData(
                work_item_id="item-1",
                project_id="proj-1",
                board_id="board-1",
                cycle_number=1,
                cycle_state=cycle_state,
                created_at=now,
                updated_at="",
            )


class TestIPRReviewCycle:
    """Tests for IPRReviewCycle abstract base class."""

    def test_abc_cannot_instantiate(self):
        """Test ABC cannot be instantiated directly."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IPRReviewCycle()

    def test_abc_subclass_missing_all_methods(self):
        """Test subclass missing all methods raises TypeError."""

        class IncompleteImpl(IPRReviewCycle):
            pass

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteImpl()

    def test_abc_subclass_missing_one_method(self):
        """Test subclass missing one method raises TypeError."""

        class PartialImpl(IPRReviewCycle):
            async def start_pr_review_cycle(self, request):
                pass

            async def get_cycle_state(self, work_item_id, project_id):
                pass

            async def save_cycle_state(self, state):
                pass

            async def remove_cycle_state(self, work_item_id, project_id):
                pass

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            PartialImpl()

    def test_abc_subclass_with_all_methods(self):
        """Test subclass with all methods can be instantiated."""

        class CompleteImpl(IPRReviewCycle):
            async def start_pr_review_cycle(self, request):
                pass

            async def get_cycle_state(self, work_item_id, project_id):
                pass

            async def save_cycle_state(self, state):
                pass

            async def remove_cycle_state(self, work_item_id, project_id):
                pass

            async def load_active_cycles(self, project_id):
                pass

        # Should not raise
        impl = CompleteImpl()
        assert isinstance(impl, IPRReviewCycle)
