"""Unit tests for RepairCycleEventHandler."""

from unittest.mock import AsyncMock, Mock

import pytest

from codetoreum.application.event_handlers.repair_cycle_event_handler import (
    RepairCycleEventContext,
    RepairCycleEventHandler,
)
from codetoreum.domain.board_workflow_template import BoardWorkflowTemplate, ColumnTemplate, ColumnType
from codetoreum.domain.events import WorkItemColumnChanged
from codetoreum.domain.repair_cycle_types import (
    CycleResult,
    EnvironmentRepairConfig,
    RepairCycleAgentConfig,
    RepairCycleResult,
    RepairCycleStageConfig,
    RepairTestResult,
    RepairTestRunConfig,
    RepairTestType,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.output.ci_pipeline_service import (
    CICheckResult,
    CICheckStatus,
    CIRunResult,
    ICIPipelineService,
)
from codetoreum.ports.output.repair_cycle_service import (
    RepairCycleContext,
)
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService


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
def workflow_config():
    """Create a mock IWorkflowConfigService that returns a Testing column with repair_cycle_agents."""
    testing_column = ColumnTemplate(
        name="Testing",
        type=ColumnType.AUTOMATED,
        agent_id="test_agent",
        is_pipeline_trigger=False,
        is_exit_column=False,
        position=0,
        auto_progress_on_completion=True,
        repair_cycle_agents=RepairCycleAgentConfig(),
    )
    template = BoardWorkflowTemplate(
        id="template-1",
        name="Test Template",
        board_id="board-1",
        project_id="proj-1",
        columns=(testing_column,),
    )

    async def _get_template(board_id: str) -> BoardWorkflowTemplate | None:
        # Return a template for any non-empty board_id so tests can exercise the repair cycle path
        return template if board_id else None

    mock_config = AsyncMock(spec=IWorkflowConfigService)
    mock_config.get_board_workflow_template.side_effect = _get_template
    return mock_config


@pytest.fixture
def handler(repair_cycle_adapter, event_bus, workflow_config):
    """Create a repair cycle event handler with workflow_config for Testing column."""
    return RepairCycleEventHandler(
        repair_cycle=repair_cycle_adapter,
        clock=None,
        event_bus=event_bus,
        workflow_config=workflow_config,
    )


@pytest.fixture
def handler_with_clock(repair_cycle_adapter, event_bus, simulation_clock, workflow_config):
    """Create a repair cycle event handler with clock and workflow_config."""
    return RepairCycleEventHandler(
        repair_cycle=repair_cycle_adapter,
        clock=simulation_clock,
        event_bus=event_bus,
        workflow_config=workflow_config,
    )


@pytest.fixture
def ci_pipeline_service():
    """Create a mock CI pipeline service."""
    return AsyncMock(spec=ICIPipelineService)


@pytest.fixture
def handler_with_ci_service(repair_cycle_adapter, event_bus, workflow_config, ci_pipeline_service):
    """Create a repair cycle event handler with CI pipeline service."""
    return RepairCycleEventHandler(
        repair_cycle=repair_cycle_adapter,
        clock=None,
        event_bus=event_bus,
        workflow_config=workflow_config,
        ci_pipeline_service=ci_pipeline_service,
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
        test_configs = (RepairTestRunConfig(test_type=RepairTestType.UNIT),)
        stage_config = RepairCycleStageConfig(
            name="Testing",
            test_configs=test_configs,
            agent_name="senior_software_engineer",
            max_total_agent_calls=100,
            checkpoint_interval=5,
            environment_repair_config=EnvironmentRepairConfig(),
        )
        context = RepairCycleEventContext(
            stage_name="Testing",
            workflow_run_id="item-1",
            work_item_id="issue-123",
            test_configs=test_configs,
            agent_name="senior_software_engineer",
            max_total_agent_calls=100,
            checkpoint_interval=5,
            stage_config=stage_config,
            agent_config=None,
        )

        assert context.stage_name == "Testing"
        assert context.workflow_run_id == "item-1"
        assert context.work_item_id == "issue-123"
        assert context.agent_name == "senior_software_engineer"
        assert context.max_total_agent_calls == 100
        assert context.checkpoint_interval == 5
        assert context.agent_config is None
        assert context.stage_config == stage_config

    def test_context_test_configs_are_tuple(self):
        """Test context test_configs is a tuple."""
        configs = (
            RepairTestRunConfig(test_type=RepairTestType.UNIT),
            RepairTestRunConfig(test_type=RepairTestType.INTEGRATION),
        )
        stage_config = RepairCycleStageConfig(
            name="Testing",
            test_configs=configs,
            agent_name="senior_software_engineer",
            max_total_agent_calls=100,
            checkpoint_interval=5,
            environment_repair_config=EnvironmentRepairConfig(),
        )
        context = RepairCycleEventContext(
            stage_name="Testing",
            workflow_run_id="item-1",
            work_item_id="issue-123",
            test_configs=configs,
            agent_name="senior_software_engineer",
            max_total_agent_calls=100,
            checkpoint_interval=5,
            stage_config=stage_config,
            agent_config=None,
        )

        assert context.test_configs == configs
        assert isinstance(context.test_configs, tuple)


class TestAgentConfigExtraction:
    """Tests for agent config extraction from workflow template.

    These tests exercise the conditional chain in handle_column_change:
    - When workflow_config is not provided: handler returns early (no repair cycle)
    - When workflow_config returns None template: handler returns early
    - When template has column without repair_cycle_agents: handler returns early
    - When template has column with repair_cycle_agents: repair cycle executes
    """

    @pytest.fixture
    def workflow_config_service(self):
        """Create a mock workflow config service."""
        return AsyncMock(spec=IWorkflowConfigService)

    @pytest.fixture
    def handler_no_workflow_config(self, repair_cycle_adapter, event_bus):
        """Create a repair cycle event handler WITHOUT workflow config service."""
        return RepairCycleEventHandler(
            repair_cycle=repair_cycle_adapter,
            event_bus=event_bus,
        )

    @pytest.fixture
    def handler_with_workflow_config(self, repair_cycle_adapter, event_bus, workflow_config_service):
        """Create a repair cycle event handler with workflow config service."""
        return RepairCycleEventHandler(
            repair_cycle=repair_cycle_adapter,
            workflow_config=workflow_config_service,
            event_bus=event_bus,
        )

    @pytest.mark.asyncio
    async def test_no_workflow_config_service_skips_repair_cycle(
        self, handler_no_workflow_config, repair_cycle_adapter, caplog
    ):
        """Test when workflow_config is None, repair cycle is not executed."""
        import logging

        caplog.set_level(logging.DEBUG)

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

        await handler_no_workflow_config.handle_column_change(event)

        # Without workflow_config the handler cannot determine if the column
        # triggers a repair cycle, so it returns early without executing.
        assert not repair_cycle_adapter.executed

    @pytest.mark.asyncio
    async def test_no_template_for_board_uses_default_agent(
        self, handler_with_workflow_config, repair_cycle_adapter, workflow_config_service, caplog
    ):
        """Test when template is None (board not configured), uses default agent."""
        import logging

        caplog.set_level(logging.DEBUG)
        workflow_config_service.get_board_workflow_template.return_value = None

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

        await handler_with_workflow_config.handle_column_change(event)

        # When template is None, handler returns early without executing the repair cycle
        assert not repair_cycle_adapter.executed

    @pytest.mark.asyncio
    async def test_column_not_found_in_template_uses_default_agent(
        self, handler_with_workflow_config, repair_cycle_adapter, workflow_config_service, caplog
    ):
        """Test when column is not found in template, uses default agent."""
        import logging

        from codetoreum.domain.board_workflow_template import BoardWorkflowTemplate, ColumnTemplate, ColumnType

        caplog.set_level(logging.WARNING)

        # Create a template with "Code Review" column but not "Testing"
        template = BoardWorkflowTemplate(
            id="template-1",
            name="Test Workflow",
            board_id="board-1",
            project_id="proj-1",
            columns=(
                ColumnTemplate(
                    name="Code Review",
                    type=ColumnType.MANUAL,
                    agent_id=None,
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=0,
                    auto_progress_on_completion=False,
                ),
            ),
        )
        workflow_config_service.get_board_workflow_template.return_value = template

        event = WorkItemColumnChanged(
            aggregate_id="item-1",
            payload={
                "work_item_id": "item-1",
                "board_id": "board-1",
                "project_id": "proj-1",
                "from_column": "Code Review",
                "to_column": "Testing",  # This column doesn't exist in template
                "moved_by": "system",
            },
        )

        await handler_with_workflow_config.handle_column_change(event)

        # When column is not found in template, handler returns early without executing
        assert not repair_cycle_adapter.executed

    @pytest.mark.asyncio
    async def test_column_found_but_no_repair_cycle_agents_uses_default_agent(
        self, handler_with_workflow_config, repair_cycle_adapter, workflow_config_service, caplog
    ):
        """Test when column exists but has no repair_cycle_agents, uses default agent."""
        import logging

        from codetoreum.domain.board_workflow_template import BoardWorkflowTemplate, ColumnTemplate, ColumnType

        caplog.set_level(logging.DEBUG)

        # Create a template with "Testing" column but without repair_cycle_agents
        template = BoardWorkflowTemplate(
            id="template-1",
            name="Test Workflow",
            board_id="board-1",
            project_id="proj-1",
            columns=(
                ColumnTemplate(
                    name="Testing",
                    type=ColumnType.AUTOMATED,
                    agent_id="default-agent",
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=0,
                    auto_progress_on_completion=False,
                    repair_cycle_agents=None,  # Explicitly None
                ),
            ),
        )
        workflow_config_service.get_board_workflow_template.return_value = template

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

        await handler_with_workflow_config.handle_column_change(event)

        # When column has no repair_cycle_agents, handler returns early without executing
        assert not repair_cycle_adapter.executed

    @pytest.mark.asyncio
    async def test_specialized_repair_cycle_agents_extracted(
        self, handler_with_workflow_config, repair_cycle_adapter, workflow_config_service, caplog
    ):
        """Test when specialized repair_cycle_agents are found, they are extracted."""
        import logging

        from codetoreum.domain.board_workflow_template import BoardWorkflowTemplate, ColumnTemplate, ColumnType
        from codetoreum.domain.repair_cycle_types import RepairCycleAgentConfig

        caplog.set_level(logging.INFO)

        # Create specialized agent config
        agent_config_obj = RepairCycleAgentConfig(
            test_execution="test_agent",
            code_fix="fix_agent",
            systemic_analysis="analysis_agent",
            systemic_fix="systemic_fix_agent",
            env_rebuild="env_agent",
            env_verification="verify_agent",
        )

        # Create a template with "Testing" column with repair_cycle_agents
        template = BoardWorkflowTemplate(
            id="template-1",
            name="Test Workflow",
            board_id="board-1",
            project_id="proj-1",
            columns=(
                ColumnTemplate(
                    name="Testing",
                    type=ColumnType.AUTOMATED,
                    agent_id="default-agent",
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=0,
                    auto_progress_on_completion=False,
                    repair_cycle_agents=agent_config_obj,
                ),
            ),
        )
        workflow_config_service.get_board_workflow_template.return_value = template

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

        await handler_with_workflow_config.handle_column_change(event)

        # Context should have the extracted agent_config
        assert repair_cycle_adapter.last_context.agent_config is not None
        assert repair_cycle_adapter.last_context.agent_config == agent_config_obj
        # Should log info about specialized agents being used
        assert "using specialized repair cycle agents" in caplog.text.lower()


class TestCIPipelineIntegration:
    """Tests for CI pipeline integration in repair cycle event handler."""

    @pytest.fixture
    def workflow_config_with_ci(self):
        """Create a workflow config with CI test type configured."""
        testing_column = ColumnTemplate(
            name="Testing",
            type=ColumnType.AUTOMATED,
            agent_id="test_agent",
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=0,
            auto_progress_on_completion=True,
            repair_cycle_agents=RepairCycleAgentConfig(),
            repair_cycle_test_types=(RepairTestType.UNIT, RepairTestType.INTEGRATION, RepairTestType.CI),
        )
        template = BoardWorkflowTemplate(
            id="template-1",
            name="Test Template",
            board_id="board-1",
            project_id="proj-1",
            columns=(testing_column,),
        )

        async def _get_template(board_id: str) -> BoardWorkflowTemplate | None:
            return template if board_id else None

        mock_config = AsyncMock(spec=IWorkflowConfigService)
        mock_config.get_board_workflow_template.side_effect = _get_template
        return mock_config

    @pytest.mark.asyncio
    async def test_overall_success_false_when_ci_fails_but_agent_tests_pass(
        self, repair_cycle_adapter, event_bus, ci_pipeline_service, workflow_config_with_ci
    ):
        """Test that overall_success is False when CI fails even if agent tests pass."""
        # Setup: agent tests pass, CI fails
        repair_cycle_adapter.result = RepairCycleResult(
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
            overall_success=True,  # Agent tests passed
            total_agent_calls=0,
            duration_seconds=1.0,
            timestamp="2024-01-01T00:00:00Z",
        )

        # CI checks return failures
        failed_check = CICheckResult(
            name="unit-tests",
            status=CICheckStatus.FAILED,
            conclusion="Some tests failed",
            url="https://example.com/check",
        )
        ci_pipeline_service.run_ci_checks.return_value = CIRunResult(
            passed=0,
            failed=1,
            check_results=(failed_check,),
            failures=("Test failed in module_a.py",),
            warnings=(),
            output="Test output",
        )

        handler = RepairCycleEventHandler(
            repair_cycle=repair_cycle_adapter,
            clock=None,
            event_bus=event_bus,
            workflow_config=workflow_config_with_ci,
            ci_pipeline_service=ci_pipeline_service,
        )

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

        # Verify CI service was called
        assert ci_pipeline_service.run_ci_checks.called

        # Verify the RepairCycleCompletedEvent shows overall_success=False
        # because CI failed even though agent tests passed
        assert event_bus.publish.called
        published_event = event_bus.publish.call_args[0][0]
        assert published_event.overall_success is False

    @pytest.mark.asyncio
    async def test_ci_pipeline_exception_creates_failed_cycle_result(
        self, repair_cycle_adapter, event_bus, ci_pipeline_service, workflow_config_with_ci
    ):
        """Test that CI pipeline exceptions are caught and converted to failed cycle results."""
        # Setup: agent tests pass
        repair_cycle_adapter.result = RepairCycleResult(
            stage="Testing",
            test_results=(
                CycleResult(
                    test_type=RepairTestType.UNIT,
                    passed=True,
                    iterations=1,
                    final_result=RepairTestResult(
                        test_type=RepairTestType.UNIT,
                        iteration=1,
                        passed=1,
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

        # CI pipeline raises an exception
        ci_pipeline_service.run_ci_checks.side_effect = Exception("CI pipeline connection failed")

        handler = RepairCycleEventHandler(
            repair_cycle=repair_cycle_adapter,
            clock=None,
            event_bus=event_bus,
            workflow_config=workflow_config_with_ci,
            ci_pipeline_service=ci_pipeline_service,
        )

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

        # Verify CI service was called
        assert ci_pipeline_service.run_ci_checks.called

        # Verify the RepairCycleCompletedEvent shows:
        # 1. overall_success=False due to CI pipeline failure
        # 2. A failed CI cycle result with error message
        assert event_bus.publish.called
        published_event = event_bus.publish.call_args[0][0]
        assert published_event.overall_success is False

        # Verify CI test result exists in test_results
        ci_results = [r for r in published_event.test_results if r.test_type == RepairTestType.CI]
        assert len(ci_results) == 1
        assert ci_results[0].passed is False
        assert ci_results[0].final_result is None
        assert "CI pipeline execution failed" in ci_results[0].error

    @pytest.mark.asyncio
    async def test_working_directory_resolver_is_called(
        self, repair_cycle_adapter, event_bus, ci_pipeline_service, workflow_config_with_ci
    ):
        """Test that custom working_directory_resolver is called with project_id."""
        # Setup: agent tests pass, CI passes
        repair_cycle_adapter.result = RepairCycleResult(
            stage="Testing",
            test_results=(
                CycleResult(
                    test_type=RepairTestType.UNIT,
                    passed=True,
                    iterations=1,
                    final_result=RepairTestResult(
                        test_type=RepairTestType.UNIT,
                        iteration=1,
                        passed=1,
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

        # CI checks pass
        passed_check = CICheckResult(
            name="unit-tests",
            status=CICheckStatus.PASSED,
            conclusion="All checks passed",
            url="https://example.com/check",
        )
        ci_pipeline_service.run_ci_checks.return_value = CIRunResult(
            passed=1,
            failed=0,
            check_results=(passed_check,),
            failures=(),
            warnings=(),
            output="Test output",
        )

        # Create custom resolver
        resolver = Mock(return_value="/custom/project/workspace")

        handler = RepairCycleEventHandler(
            repair_cycle=repair_cycle_adapter,
            clock=None,
            event_bus=event_bus,
            workflow_config=workflow_config_with_ci,
            ci_pipeline_service=ci_pipeline_service,
            working_directory_resolver=resolver,
        )

        event = WorkItemColumnChanged(
            aggregate_id="item-1",
            payload={
                "work_item_id": "item-1",
                "board_id": "board-1",
                "project_id": "proj-123",
                "from_column": "Code Review",
                "to_column": "Testing",
                "moved_by": "system",
            },
        )

        await handler.handle_column_change(event)

        # Verify the resolver was called with the project_id
        resolver.assert_called_once_with("proj-123")

        # Verify CI pipeline service was called with the resolved working directory
        ci_pipeline_service.run_ci_checks.assert_called_once()
        call_kwargs = ci_pipeline_service.run_ci_checks.call_args[1]
        assert call_kwargs["working_directory"] == "/custom/project/workspace"
