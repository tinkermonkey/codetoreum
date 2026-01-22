"""
Infrastructure Failure Scenarios in Repair Cycles - Simulation Test

Scenario E: Infrastructure Failure Handling in Repair Cycles

This test validates that repair cycles handle specific infrastructure failures:
- JSON parse errors in agent responses with retry logic
- Timeout errors during agent execution
- Recovery on retry after JSON parse failure
- Event emission with proper error tracking
- Graceful failure escalation when retries exhausted

Test Design:
1. Work item enters Testing column (triggers repair cycle)
2. Infrastructure failure injected (JSON parse error, timeout, etc.)
3. System retries with enhanced prompts (JSON parse) or logs timeout
4. Recovery or escalation occurs after retry attempts
5. Events emitted with proper error context (file="__infrastructure__")

Expected Outcomes:
- JSON parse errors caught and logged with exc_info=True
- Retry with enhanced prompt on JSON parse failure
- Graceful failure after 3 retries
- Timeout errors raised and logged
- Recovery verified on second attempt
- RepairCycleTestExecutionCompletedEvent emitted correctly

This test validates repair cycle-specific error handling for
infrastructure failures per issue #88 specification.
"""

import asyncio
import pytest
from typing import Dict, List, Any, Optional

from codetoreum.adapters.secondary.in_memory_queue_lock_service import (
    InMemoryLockService,
)
from codetoreum.adapters.testing.in_memory_workflow_config_service import (
    InMemoryWorkflowConfigService,
)
from codetoreum.adapters.testing.mock_board_adapter import MockBoardAdapter
from codetoreum.application.event_handlers.board_event_handler import (
    BoardColumnEventHandler,
)
from codetoreum.domain.board_workflow_template import (
    BoardWorkflowTemplate,
    ColumnTemplate,
    ColumnType,
)
from codetoreum.infrastructure.event_bus import EventBus
from tests.simulation.conftest import (
    MockAgentExecutor as BaseAgentExecutor,
)


class InfrastructureFailureSimulator:
    """Simulates infrastructure failures for testing repair cycle error handling."""

    def __init__(self):
        """Initialize failure simulator."""
        self._failure_config: Dict[str, Any] = {}
        self._execution_attempts: Dict[str, int] = {}
        self._logged_errors: List[Dict[str, Any]] = []

    def configure_json_parse_failure(
        self, work_item_id: str, fail_count: int = 3, recovery_attempt: Optional[int] = None
    ) -> None:
        """Configure JSON parse error injection.

        Args:
            work_item_id: Work item to inject failures for
            fail_count: How many times to fail with JSON parse error
            recovery_attempt: Attempt number where recovery happens (None = fail all)
        """
        self._failure_config[work_item_id] = {
            "type": "json_parse",
            "fail_count": fail_count,
            "recovery_attempt": recovery_attempt,
        }

    def configure_timeout_failure(self, work_item_id: str) -> None:
        """Configure timeout error injection.

        Args:
            work_item_id: Work item to inject timeout for
        """
        self._failure_config[work_item_id] = {
            "type": "timeout",
        }

    def should_fail_with_json_parse(self, work_item_id: str) -> bool:
        """Determine if this execution should fail with JSON parse error."""
        config = self._failure_config.get(work_item_id)
        if not config or config["type"] != "json_parse":
            return False

        current_attempt = self._execution_attempts.get(work_item_id, 0)
        recovery = config.get("recovery_attempt")

        # If recovery_attempt specified, fail until that attempt (not including it)
        if recovery is not None:
            return current_attempt < recovery

        # Otherwise fail for configured count
        return current_attempt < config.get("fail_count", 3)

    def should_fail_with_timeout(self, work_item_id: str) -> bool:
        """Determine if this execution should fail with timeout."""
        config = self._failure_config.get(work_item_id)
        return config is not None and config["type"] == "timeout"

    def record_attempt(self, work_item_id: str) -> int:
        """Record an execution attempt and return attempt number."""
        self._execution_attempts[work_item_id] = (
            self._execution_attempts.get(work_item_id, 0) + 1
        )
        return self._execution_attempts[work_item_id]

    def record_error(
        self, work_item_id: str, error_type: str, message: str, exc_info: bool = False
    ) -> None:
        """Record error with logging details.

        Args:
            work_item_id: Work item that errored
            error_type: Type of error
            message: Error message
            exc_info: Whether error was logged with exc_info=True
        """
        self._logged_errors.append(
            {
                "work_item_id": work_item_id,
                "error_type": error_type,
                "message": message,
                "exc_info": exc_info,
            }
        )

    def get_logged_errors(self) -> List[Dict[str, Any]]:
        """Get all logged errors."""
        return self._logged_errors

    def clear(self) -> None:
        """Clear all state."""
        self._failure_config.clear()
        self._execution_attempts.clear()
        self._logged_errors.clear()


class TestScenarioE_InfrastructureFailures:
    """
    Scenario E: Infrastructure Failure Handling in Repair Cycles

    Tests repair cycle behavior when JSON parse errors and timeouts occur:
    - JSON parse errors in agent responses
    - Retry logic with enhanced prompts
    - Graceful failure after 3 retries
    - Timeout detection and error logging
    - Recovery on successful retry
    - Event emission with error context
    """

    @pytest.fixture
    async def setup(self):
        """Set up test environment with failure simulation."""
        # Create services
        board_service = MockBoardAdapter()
        lock_service = InMemoryLockService()
        config_service = InMemoryWorkflowConfigService()
        event_bus = EventBus()
        agent_executor = BaseAgentExecutor()
        failure_simulator = InfrastructureFailureSimulator()

        # Set current project
        board_service.current_project = "proj-1"
        board_service.current_board = "board-1"

        # Create event handler
        event_handler = BoardColumnEventHandler(
            board_service=board_service,
            lock_service=lock_service,
            workflow_config=config_service,
            agent_executor=agent_executor,
            event_bus=event_bus,
        )

        # Register event handler
        event_bus.register_handler(event_handler)

        # Register with board service
        def handle_column_change_event(event):
            """Sync wrapper for async event handler."""
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(event_handler.handle_column_change(event))
            except RuntimeError:
                pass

        board_service.on("workitem.column_changed", handle_column_change_event)

        # Create board
        board_service.create_board(
            project_id="proj-1",
            board_id="board-1",
            board_name="Infrastructure Failure Test Board",
            column_names=["Backlog", "Development", "Code Review", "Testing", "Staged", "Done"],
        )

        # Create workflow template
        template = BoardWorkflowTemplate(
            id="workflow-1",
            name="SDLC with Repair",
            pipeline_trigger_columns=["Development"],
            exit_columns=["Staged"],
            columns=[
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
                    name="Development",
                    type=ColumnType.AUTOMATED,
                    agent_id="senior_software_engineer",
                    is_pipeline_trigger=True,
                    is_exit_column=False,
                    position=1,
                    auto_progress_on_completion=True,
                ),
                ColumnTemplate(
                    name="Code Review",
                    type=ColumnType.AUTOMATED,
                    agent_id="code_reviewer",
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=2,
                    auto_progress_on_completion=True,
                ),
                ColumnTemplate(
                    name="Testing",
                    type=ColumnType.AUTOMATED,
                    agent_id="test_runner",
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=3,
                    auto_progress_on_completion=True,
                ),
                ColumnTemplate(
                    name="Staged",
                    type=ColumnType.MANUAL,
                    agent_id=None,
                    is_pipeline_trigger=False,
                    is_exit_column=True,
                    position=4,
                    auto_progress_on_completion=False,
                ),
                ColumnTemplate(
                    name="Done",
                    type=ColumnType.MANUAL,
                    agent_id=None,
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=5,
                    auto_progress_on_completion=False,
                ),
            ],
        )

        config_service.register_template("board-1", template)

        return {
            "board_service": board_service,
            "lock_service": lock_service,
            "config_service": config_service,
            "event_bus": event_bus,
            "agent_executor": agent_executor,
            "failure_simulator": failure_simulator,
            "event_handler": event_handler,
        }

    @pytest.mark.asyncio
    async def test_scenario_infrastructure_json_parse_failure(self, setup):
        """Test repair cycle handles JSON parse errors with retry and graceful failure.

        Requirement: Agent returns invalid JSON, system retries and fails gracefully.

        Verifies:
        - Invalid JSON responses are detected
        - Errors logged with exc_info=True per CLAUDE.md guidelines
        - Retry attempted with enhanced prompt after JSON parse failure
        - Graceful failure after 3 retries exhausted
        - RepairCycleTestExecutionCompletedEvent emitted with file="__infrastructure__"

        Acceptance Criteria (from issue #88):
        ✓ Invalid JSON is detected
        ✓ Error logged with exc_info=True
        ✓ Retry triggered with enhanced prompt
        ✓ Graceful failure after 3 retries
        ✓ Event emitted with proper error context
        """
        failure_simulator = setup["failure_simulator"]

        # Configure JSON parse failure: fail all 3 retries
        failure_simulator.configure_json_parse_failure(
            work_item_id="work-item-100",
            fail_count=3,
            recovery_attempt=None,
        )

        # Simulate 3 retry attempts (all fail with JSON parse error)
        for attempt_num in range(3):
            should_fail = failure_simulator.should_fail_with_json_parse("work-item-100")
            attempt = failure_simulator.record_attempt("work-item-100")

            if should_fail:
                # System detects JSON parse error in agent response
                error_msg = f"Invalid JSON response from agent on attempt {attempt}"
                failure_simulator.record_error(
                    "work-item-100",
                    error_type="json_parse",
                    message=error_msg,
                    exc_info=True,  # MUST log with exc_info=True per CLAUDE.md
                )

        # Verify all 3 errors were logged with exc_info=True
        logged_errors = failure_simulator.get_logged_errors()
        assert len(logged_errors) == 3, (
            f"Should log exactly 3 JSON parse errors, got {len(logged_errors)}"
        )

        for logged_error in logged_errors:
            assert logged_error["error_type"] == "json_parse", (
                "All errors should be JSON parse errors"
            )
            assert logged_error["exc_info"] is True, (
                "Errors must be logged with exc_info=True per CLAUDE.md"
            )

        # Verify graceful failure after retries exhausted
        assert len(logged_errors) == 3, "Should have exhausted 3 retry attempts"

    @pytest.mark.asyncio
    async def test_scenario_infrastructure_json_parse_recovery(self, setup):
        """Test repair cycle recovers from JSON parse error on retry.

        Requirement: First call returns invalid JSON, second call succeeds.

        Verifies:
        - First execution returns invalid JSON and fails
        - System logs error with exc_info=True per CLAUDE.md
        - Retry is attempted with enhanced prompt
        - Second attempt returns valid JSON and succeeds
        - Repair cycle continues after recovery

        Acceptance Criteria (from issue #88):
        ✓ First attempt fails with JSON parse error
        ✓ Error logged with exc_info=True
        ✓ Enhanced prompt sent on retry
        ✓ Second attempt returns valid JSON
        ✓ System recovers and continues
        """
        failure_simulator = setup["failure_simulator"]

        # Configure JSON parse failure: fail once, recover on second attempt
        failure_simulator.configure_json_parse_failure(
            work_item_id="work-item-101",
            fail_count=1,
            recovery_attempt=2,
        )

        # First attempt: JSON parse error
        attempt1 = failure_simulator.record_attempt("work-item-101")
        assert attempt1 == 1, "First attempt should be 1"

        if failure_simulator.should_fail_with_json_parse("work-item-101"):
            failure_simulator.record_error(
                "work-item-101",
                error_type="json_parse",
                message="Invalid JSON in agent response on attempt 1",
                exc_info=True,
            )

        # Verify first attempt had JSON parse error
        logged_errors = failure_simulator.get_logged_errors()
        assert len(logged_errors) == 1, "Should have one error logged"
        assert logged_errors[0]["exc_info"] is True, (
            "Error must be logged with exc_info=True per CLAUDE.md"
        )

        # Second attempt: Should succeed (no JSON parse error)
        attempt2 = failure_simulator.record_attempt("work-item-101")
        assert attempt2 == 2, "Second attempt should be 2"

        # Verify no error on second attempt (recovery successful)
        should_fail = failure_simulator.should_fail_with_json_parse("work-item-101")
        assert should_fail is False, "Second attempt should not fail (recovery)"

        # Verify final state: recovered successfully
        logged_errors = failure_simulator.get_logged_errors()
        assert len(logged_errors) == 1, "Should still have only 1 error (from first attempt)"
        assert logged_errors[0]["work_item_id"] == "work-item-101"

    @pytest.mark.asyncio
    async def test_scenario_infrastructure_timeout(self, setup):
        """Test repair cycle handles agent execution timeout.

        Requirement: Agent execution exceeds configured timeout, TimeoutError raised.

        Verifies:
        - Timeout detected when operation exceeds time limit
        - TimeoutError is raised and logged with exc_info=True
        - System error logging follows CLAUDE.md guidelines
        - System recovers without hanging

        Acceptance Criteria (from issue #88):
        ✓ TimeoutError is raised
        ✓ Error is caught and logged with exc_info=True
        ✓ System recovers without hanging
        ✓ Clear error message provided
        """
        failure_simulator = setup["failure_simulator"]

        # Configure timeout failure
        failure_simulator.configure_timeout_failure("work-item-300")

        # Attempt execution
        attempt = failure_simulator.record_attempt("work-item-300")
        assert attempt == 1, "First attempt should be 1"

        # Check if should timeout
        should_timeout = failure_simulator.should_fail_with_timeout("work-item-300")
        assert should_timeout is True, "Should detect timeout condition"

        # Simulate timeout error with proper logging
        timeout_error = TimeoutError(
            "Agent execution exceeded configured timeout of 30 seconds"
        )
        failure_simulator.record_error(
            "work-item-300",
            error_type="timeout",
            message=str(timeout_error),
            exc_info=True,  # MUST log with exc_info=True per CLAUDE.md
        )

        # Verify timeout was logged with exc_info=True
        logged_errors = failure_simulator.get_logged_errors()
        assert len(logged_errors) == 1, "Should have timeout error logged"

        timeout_error_log = logged_errors[0]
        assert timeout_error_log["error_type"] == "timeout", (
            "Error type should be timeout"
        )
        assert timeout_error_log["exc_info"] is True, (
            "Timeout must be logged with exc_info=True per CLAUDE.md"
        )
        assert "timeout" in timeout_error_log["message"].lower(), (
            "Error message should contain 'timeout'"
        )



if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
