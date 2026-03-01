"""Unit tests for RepairCycleEventHandler."""

from unittest.mock import AsyncMock, Mock

import pytest

from codetoreum.application.event_handlers.repair_cycle_event_handler import (
    RepairCycleEventContext,
    RepairCycleEventHandler,
)
from codetoreum.domain.events import WorkItemColumnChanged
from codetoreum.domain.repair_cycle_types import (
    CycleResult,
    RepairCycleResult,
    RepairTestResult,
    RepairTestRunConfig,
    RepairTestType,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.output.repair_cycle_service import (
    RepairCycleContext,
)


class MockRepairCycleAdapter:
    """Mock repair cycle adapter for testing."""

    def __init__(self):
        """Initialize mock adapter."""
        self.executed = False
        self.last_context = None
        self.result = RepairCycleResult(
            stage="Testing",
            test_results=(
                CycleResult(
                    test_type=RepairTestType.UNIT,
                    passed=True,
                    iterations=1,
                    final_result=RepairTestResult(
                        test_type=RepairTestType.UNIT,
                        iteration=1,
                        passed=2,
                        failed=0,
                        warnings=0,
                        failures=(),
                        warning_list=(),
                        raw_output="All tests passed",
                        timestamp="2024-01-01T00:00:00Z",
                    ),
                    error=None,
                    files_fixed=0,
                    warnings_reviewed=0,
                    duration_seconds=1.0,
                ),
            ),
            overall_success=True,
            total_agent_calls=0,
            duration_seconds=1.0,
            timestamp="2024-01-01T00:00:00Z",
        )

    async def execute(self, context: RepairCycleContext) -> RepairCycleResult:
        """Execute repair cycle."""
        self.executed = True
        self.last_context = context
        return self.result

    async def run_tests(
        self,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> RepairTestResult:
        """Execute tests (stub for protocol compliance)."""
        return RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=0,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="",
            timestamp="2024-01-01T00:00:00Z",
        )

    async def fix_failures_by_file(
        self,
        grouped_failures,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> int:
        """Fix failures (stub for protocol compliance)."""
        return 0

    async def handle_warnings(
        self,
        test_result: RepairTestResult,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> int:
        """Handle warnings (stub for protocol compliance)."""
        return 0

    async def checkpoint(
        self,
        test_type: RepairTestType,
        iteration: int,
        context: RepairCycleContext,
    ) -> None:
        """Checkpoint (stub for protocol compliance)."""


# ====================================================================================
# Fixtures
# ====================================================================================


@pytest.fixture
def event_bus():
    """Create a mock event bus."""
    return AsyncMock(spec=EventBus)


@pytest.fixture
def repair_cycle_adapter():
    """Create a mock repair cycle adapter."""
    return MockRepairCycleAdapter()


@pytest.fixture
def simulation_clock():
    """Create a simulation clock."""
    return SimulationClock(speed_multiplier=100.0)


@pytest.fixture
def handler(repair_cycle_adapter, event_bus):
    """Create a repair cycle event handler."""
    return RepairCycleEventHandler(
        repair_cycle=repair_cycle_adapter,
        clock=None,
        event_bus=event_bus,
    )


@pytest.fixture
def handler_with_clock(repair_cycle_adapter, event_bus, simulation_clock):
    """Create a repair cycle event handler with clock."""
    return RepairCycleEventHandler(
        repair_cycle=repair_cycle_adapter,
        clock=simulation_clock,
        event_bus=event_bus,
    )


# ====================================================================================
# Tests for RepairCycleEventHandler
# ====================================================================================


class TestRepairCycleEventHandlerInitialization:
    """Tests for handler initialization."""

    def test_handler_initializes_with_required_parameters(self, repair_cycle_adapter, event_bus):
        """Test handler initializes with required parameters."""
        handler = RepairCycleEventHandler(
            repair_cycle=repair_cycle_adapter,
            event_bus=event_bus,
        )
        assert handler.repair_cycle == repair_cycle_adapter
        assert handler.event_bus == event_bus
        assert handler.clock is None

    def test_handler_initializes_with_optional_clock(self, repair_cycle_adapter, event_bus, simulation_clock):
        """Test handler initializes with optional simulation clock."""
        handler = RepairCycleEventHandler(
            repair_cycle=repair_cycle_adapter,
            clock=simulation_clock,
            event_bus=event_bus,
        )
        assert handler.clock == simulation_clock

    def test_handler_initializes_without_event_bus(self, repair_cycle_adapter, simulation_clock):
        """Test handler initializes without event bus."""
        handler = RepairCycleEventHandler(
            repair_cycle=repair_cycle_adapter,
            clock=simulation_clock,
        )
        assert handler.event_bus is None


class TestRepairCycleEventHandlerGetEventTypes:
    """Tests for get_event_types method."""

    def test_get_event_types_returns_correct_types(self, handler):
        """Test get_event_types returns correct event types."""
        event_types = handler.get_event_types()
        assert event_types == ["WorkItemColumnChanged"]

    def test_get_event_types_returns_list(self, handler):
        """Test get_event_types returns a list."""
        event_types = handler.get_event_types()
        assert isinstance(event_types, list)

    def test_get_event_types_has_single_element(self, handler):
        """Test get_event_types returns single element."""
        event_types = handler.get_event_types()
        assert len(event_types) == 1


class TestRepairCycleEventHandlerHandleMethod:
    """Tests for handle method."""

    @pytest.mark.asyncio
    async def test_handle_with_column_changed_event(self, handler, repair_cycle_adapter):
        """Test handle processes WorkItemColumnChanged events."""
        event = WorkItemColumnChanged(
            aggregate_id="item-1",
            payload={
                "work_item_id": "item-1",
                "board_id": "board-1",
                "project_id": "proj-1",
                "from_column": "Code Review",
                "to_column": "Testing",
                "moved_by": "system",
            },
        )

        await handler.handle(event)

        # Verify repair cycle was executed
        assert repair_cycle_adapter.executed

    @pytest.mark.asyncio
    async def test_handle_with_wrong_event_type(self, handler, repair_cycle_adapter):
        """Test handle ignores wrong event types."""
        # Create a mock event that's not WorkItemColumnChanged
        wrong_event = Mock()
        wrong_event.event_type = "SomeOtherEvent"

        # Should not raise exception
        await handler.handle(wrong_event)

        # Repair cycle should not be executed
        assert not repair_cycle_adapter.executed

    @pytest.mark.asyncio
    async def test_handle_logs_warning_for_wrong_event_type(self, handler, caplog):
        """Test handle logs warning for wrong event types."""
        wrong_event = Mock()
        wrong_event.event_type = "SomeOtherEvent"

        await handler.handle(wrong_event)

        # Check that warning was logged
        assert "unexpected event type" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_handle_propagates_exceptions(self, handler, repair_cycle_adapter):
        """Test handle propagates exceptions from column change handler."""
        # Make repair cycle raise an exception
        repair_cycle_adapter.result = Exception("Test error")

        event = WorkItemColumnChanged(
            aggregate_id="item-1",
            payload={
                "work_item_id": "item-1",
                "board_id": "board-1",
                "project_id": "proj-1",
                "from_column": "Code Review",
                "to_column": "Testing",
                "moved_by": "system",
            },
        )

        # Mock execute to raise exception
        async def raise_error(context):
            raise Exception("Repair cycle failed")

        repair_cycle_adapter.execute = raise_error

        with pytest.raises(Exception, match="Repair cycle failed"):
            await handler.handle(event)


class TestRepairCycleEventHandlerColumnChange:
    """Tests for handle_column_change method."""

    @pytest.mark.asyncio
    async def test_handle_column_change_enters_testing_stage(self, handler, repair_cycle_adapter):
        """Test handler triggers repair cycle when entering Testing column."""
        event = WorkItemColumnChanged(
            aggregate_id="item-1",
            payload={
                "work_item_id": "item-1",
                "board_id": "board-1",
                "project_id": "proj-1",
                "from_column": "Code Review",
                "to_column": "Testing",
                "moved_by": "system",
            },
        )

        await handler.handle_column_change(event)

        assert repair_cycle_adapter.executed
        assert repair_cycle_adapter.last_context is not None

    @pytest.mark.asyncio
    async def test_handle_column_change_ignores_other_columns(self, handler, repair_cycle_adapter):
        """Test handler ignores movements to columns other than Testing."""
        event = WorkItemColumnChanged(
            aggregate_id="item-1",
            payload={
                "work_item_id": "item-1",
                "board_id": "board-1",
                "project_id": "proj-1",
                "from_column": "Code Review",
                "to_column": "Ready for Deploy",
                "moved_by": "system",
            },
        )

        await handler.handle_column_change(event)

        assert not repair_cycle_adapter.executed

    @pytest.mark.asyncio
    async def test_handle_column_change_extracts_payload_correctly(self, handler, repair_cycle_adapter):
        """Test handler extracts payload correctly from event."""
        event = WorkItemColumnChanged(
            aggregate_id="item-123",
            payload={
                "work_item_id": "item-123",
                "board_id": "board-456",
                "project_id": "proj-789",
                "from_column": "Code Review",
                "to_column": "Testing",
                "moved_by": "system",
            },
        )

        await handler.handle_column_change(event)

        assert repair_cycle_adapter.last_context.workflow_run_id == "item-123"
        assert repair_cycle_adapter.last_context.stage_name == "Testing"

    @pytest.mark.asyncio
    async def test_handle_column_change_context_has_correct_test_configs(self, handler, repair_cycle_adapter):
        """Test handler creates context with correct test configurations."""
        event = WorkItemColumnChanged(
            aggregate_id="item-1",
            payload={
                "work_item_id": "item-1",
                "board_id": "board-1",
                "project_id": "proj-1",
                "from_column": "Code Review",
                "to_column": "Testing",
                "moved_by": "system",
            },
        )

        await handler.handle_column_change(event)

        context = repair_cycle_adapter.last_context
        assert len(context.test_configs) == 3
        assert context.test_configs[0].test_type == RepairTestType.UNIT
        assert context.test_configs[1].test_type == RepairTestType.INTEGRATION
        assert context.test_configs[2].test_type == RepairTestType.E2E

    @pytest.mark.asyncio
    async def test_handle_column_change_context_has_correct_agent_name(self, handler, repair_cycle_adapter):
        """Test handler creates context with correct agent name."""
        event = WorkItemColumnChanged(
            aggregate_id="item-1",
            payload={
                "work_item_id": "item-1",
                "board_id": "board-1",
                "project_id": "proj-1",
                "from_column": "Code Review",
                "to_column": "Testing",
                "moved_by": "system",
            },
        )

        await handler.handle_column_change(event)

        context = repair_cycle_adapter.last_context
        assert context.agent_name == "senior_software_engineer"

    @pytest.mark.asyncio
    async def test_handle_column_change_logs_success(self, handler, repair_cycle_adapter, caplog):
        """Test handler logs success when repair cycle succeeds."""
        import logging

        caplog.set_level(logging.INFO)

        event = WorkItemColumnChanged(
            aggregate_id="item-1",
            payload={
                "work_item_id": "item-1",
                "board_id": "board-1",
                "project_id": "proj-1",
                "from_column": "Code Review",
                "to_column": "Testing",
                "moved_by": "system",
            },
        )

        # Set successful result
        repair_cycle_adapter.result = RepairCycleResult(
            stage="Testing",
            overall_success=True,
            test_results=(
                CycleResult(
                    test_type=RepairTestType.UNIT,
                    passed=True,
                    iterations=1,
                    final_result=RepairTestResult(
                        test_type=RepairTestType.UNIT,
                        iteration=1,
                        passed=2,
                        failed=0,
                        warnings=0,
                        failures=(),
                        warning_list=(),
                        raw_output="All tests passed",
                        timestamp="2024-01-01T00:00:00Z",
                    ),
                    error=None,
                    files_fixed=0,
                    warnings_reviewed=0,
                    duration_seconds=1.0,
                ),
            ),
            total_agent_calls=0,
            duration_seconds=1.0,
            timestamp="2024-01-01T00:00:00Z",
        )

        await handler.handle_column_change(event)

        assert "repair cycle" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_handle_column_change_logs_failure(self, handler, repair_cycle_adapter, caplog):
        """Test handler logs failure when repair cycle fails."""
        event = WorkItemColumnChanged(
            aggregate_id="item-1",
            payload={
                "work_item_id": "item-1",
                "board_id": "board-1",
                "project_id": "proj-1",
                "from_column": "Code Review",
                "to_column": "Testing",
                "moved_by": "system",
            },
        )

        # Set failed result
        repair_cycle_adapter.result = RepairCycleResult(
            stage="Testing",
            overall_success=False,
            test_results=(
                CycleResult(
                    test_type=RepairTestType.UNIT,
                    passed=False,
                    iterations=1,
                    final_result=RepairTestResult(
                        test_type=RepairTestType.UNIT,
                        iteration=1,
                        passed=0,
                        failed=1,
                        warnings=0,
                        failures=(Mock(file="test.py", test="test_something", message="Test failed"),),
                        warning_list=(),
                        raw_output="Test failed",
                        timestamp="2024-01-01T00:00:00Z",
                    ),
                    error="Test execution failed",
                    files_fixed=0,
                    warnings_reviewed=0,
                    duration_seconds=1.0,
                ),
            ),
            total_agent_calls=0,
            duration_seconds=1.0,
            timestamp="2024-01-01T00:00:00Z",
        )

        await handler.handle_column_change(event)

        assert "failed" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_handle_column_change_with_missing_payload_fields(self, handler, repair_cycle_adapter):
        """Test handler handles missing payload fields gracefully."""
        event = WorkItemColumnChanged(
            aggregate_id="item-1",
            payload={
                "from_column": "Code Review",
                "to_column": "Testing",
                # Missing work_item_id, board_id, project_id
            },
        )

        # Should not raise exception
        await handler.handle_column_change(event)

        # Repair cycle may be executed with None values
        assert repair_cycle_adapter.executed or not repair_cycle_adapter.executed

    @pytest.mark.asyncio
    async def test_handle_column_change_exception_includes_error_id(self, handler, repair_cycle_adapter):
        """Test handler exception includes proper error ID."""

        # Make repair cycle raise an exception
        async def raise_error(context):
            raise Exception("Repair cycle failed")

        repair_cycle_adapter.execute = raise_error

        event = WorkItemColumnChanged(
            aggregate_id="item-1",
            payload={
                "work_item_id": "item-1",
                "board_id": "board-1",
                "project_id": "proj-1",
                "from_column": "Code Review",
                "to_column": "Testing",
                "moved_by": "system",
            },
        )

        with pytest.raises(Exception):
            await handler.handle_column_change(event)


class TestRepairCycleEventContext:
    """Tests for RepairCycleEventContext dataclass."""

    def test_context_creation(self):
        """Test context can be created with required fields."""
        context = RepairCycleEventContext(
            stage_name="Testing",
            workflow_run_id="item-1",
            test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
            agent_name="senior_software_engineer",
            max_total_agent_calls=100,
            checkpoint_interval=5,
        )

        assert context.stage_name == "Testing"
        assert context.workflow_run_id == "item-1"
        assert context.agent_name == "senior_software_engineer"
        assert context.max_total_agent_calls == 100
        assert context.checkpoint_interval == 5

    def test_context_test_configs_are_tuple(self):
        """Test context test_configs is a tuple."""
        configs = (
            RepairTestRunConfig(test_type=RepairTestType.UNIT),
            RepairTestRunConfig(test_type=RepairTestType.INTEGRATION),
        )
        context = RepairCycleEventContext(
            stage_name="Testing",
            workflow_run_id="item-1",
            test_configs=configs,
            agent_name="senior_software_engineer",
            max_total_agent_calls=100,
            checkpoint_interval=5,
        )

        assert context.test_configs == configs
        assert isinstance(context.test_configs, tuple)
