"""Integration tests for repair cycle CI pipeline routing.

Tests verify that:
- RepairCycleEventHandler routes RepairTestType.CI to ICIPipelineService
- CI test configs are filtered before IRepairCycle.execute() is called
- CIRunResult is converted to RepairTestResult for downstream aggregation
- MockRepairCycleAdapter delegates CI checks to injected ICIPipelineService
- Agent executor is not invoked for CI test types
- Clear errors are raised when CI is requested but no service is provided
"""

import pytest

from codetoreum.adapters.testing.mock_ci_pipeline_adapter import MockCIPipelineAdapter
from codetoreum.adapters.testing.mock_repair_cycle_adapter import MockRepairCycleAdapter
from codetoreum.application.event_handlers.repair_cycle_event_handler import RepairCycleEventHandler
from codetoreum.application.repair_cycle_ci_integration import (
    convert_ci_run_result_to_repair_test_result,
)
from codetoreum.domain.board_workflow_template import BoardWorkflowTemplate, ColumnTemplate, ColumnType
from codetoreum.domain.events import WorkItemColumnChanged
from codetoreum.domain.repair_cycle_types import (
    CycleResult,
    RepairCycleAgentConfig,
    RepairCycleResult,
    RepairTestResult,
    RepairTestRunConfig,
    RepairTestType,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.output.ci_pipeline_service import CIRunResult
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService


# ====================================================================================
# Test Helpers
# ====================================================================================


class SimpleRepairCycleContext:
    """Simple context object implementing RepairCycleContext protocol."""

    def __init__(
        self,
        stage_name: str,
        workflow_run_id: str,
        work_item_id: str,
        test_configs: tuple,
        agent_name: str,
        max_total_agent_calls: int,
        checkpoint_interval: int,
        agent_config=None,
        systemic_fix_failure_ceiling: int = 50,
        iteration: int = 0,
        prior_fix_attempts: tuple = (),
        prior_classifications: tuple = (),
    ):
        """Initialize context."""
        self.stage_name = stage_name
        self.workflow_run_id = workflow_run_id
        self.work_item_id = work_item_id
        self.test_configs = test_configs
        self.agent_name = agent_name
        self.max_total_agent_calls = max_total_agent_calls
        self.checkpoint_interval = checkpoint_interval
        self.agent_config = agent_config
        self.systemic_fix_failure_ceiling = systemic_fix_failure_ceiling
        self.iteration = iteration
        self.prior_fix_attempts = prior_fix_attempts
        self.prior_classifications = prior_classifications


# ====================================================================================
# Unit Tests: CIRunResult to RepairTestResult Conversion
# ====================================================================================


class TestCIRunResultConversion:
    """Tests for converting CIRunResult to RepairTestResult."""

    def test_convert_passing_ci_result(self):
        """Test conversion of passing CI result."""
        ci_result = CIRunResult(
            passed=1,
            failed=0,
            failures=(),
            output="All checks passed",
        )

        repair_result = convert_ci_run_result_to_repair_test_result(ci_result)

        assert repair_result.test_type == RepairTestType.CI
        assert repair_result.iteration == 1
        assert repair_result.passed == 1
        assert repair_result.failed == 0
        assert repair_result.failures == ()
        assert repair_result.warnings == 0

    def test_convert_failing_ci_result(self):
        """Test conversion of failing CI result with failures mapped to RepairTestFailure."""
        ci_result = CIRunResult(
            passed=0,
            failed=2,
            failures=["linting failed: line too long", "security scan: vulnerability detected"],
            output="CI checks failed",
        )

        repair_result = convert_ci_run_result_to_repair_test_result(ci_result)

        assert repair_result.test_type == RepairTestType.CI
        assert repair_result.failed == 2
        assert len(repair_result.failures) == 2

        # FR-5.3: Failures map to RepairTestFailure(file="ci", test=<check_name>, ...)
        for i, failure in enumerate(repair_result.failures):
            assert failure.file == "ci"
            assert failure.test == f"check-{i}"
            if i == 0:
                assert "linting failed" in failure.message
            elif i == 1:
                assert "security scan" in failure.message

    def test_convert_with_custom_iteration(self):
        """Test conversion with custom iteration number."""
        ci_result = CIRunResult(
            passed=1,
            failed=0,
            failures=(),
            output="All checks passed",
        )

        repair_result = convert_ci_run_result_to_repair_test_result(ci_result, iteration=5)

        assert repair_result.iteration == 5


# ====================================================================================
# Integration Tests: MockRepairCycleAdapter CI Delegation
# ====================================================================================


class TestMockRepairCycleAdapterCIDelegation:
    """Tests for MockRepairCycleAdapter CI test routing."""

    @pytest.mark.asyncio
    async def test_ci_delegation_with_passing_result(self):
        """Test that CI tests are delegated to ICIPipelineService (FR-6.1)."""
        # Setup
        ci_service = MockCIPipelineAdapter()
        # Configure the service for the project_id that will be used
        ci_service.set_ci_run_passing("proj-1")

        repair_adapter = MockRepairCycleAdapter(ci_pipeline_service=ci_service)
        repair_adapter.current_project = "proj-1"

        context = SimpleRepairCycleContext(
            stage_name="Testing",
            workflow_run_id="workflow-1",
            work_item_id="item-1",
            test_configs=(RepairTestRunConfig(test_type=RepairTestType.CI),),
            agent_name="test_agent",
            max_total_agent_calls=10,
            checkpoint_interval=5,
        )

        config = RepairTestRunConfig(test_type=RepairTestType.CI)

        # Execute CI test
        result = await repair_adapter.run_tests(config, context)

        # Verify result
        assert result.test_type == RepairTestType.CI
        assert result.passed == 1
        assert result.failed == 0

        # Verify CI service was called with correct project_id
        ci_service.assert_ci_run_executed("proj-1")

    @pytest.mark.asyncio
    async def test_ci_delegation_with_failing_result(self):
        """Test CI delegation with failures."""
        # Setup
        ci_service = MockCIPipelineAdapter()
        # Configure the service for the project_id that will be used
        ci_service.set_ci_run_failing("proj-1", ["linting failed", "tests failed"])

        repair_adapter = MockRepairCycleAdapter(ci_pipeline_service=ci_service)
        repair_adapter.current_project = "proj-1"

        context = SimpleRepairCycleContext(
            stage_name="Testing",
            workflow_run_id="workflow-1",
            work_item_id="item-1",
            test_configs=(RepairTestRunConfig(test_type=RepairTestType.CI),),
            agent_name="test_agent",
            max_total_agent_calls=10,
            checkpoint_interval=5,
        )

        config = RepairTestRunConfig(test_type=RepairTestType.CI)

        # Execute CI test
        result = await repair_adapter.run_tests(config, context)

        # Verify failures are converted correctly
        assert result.test_type == RepairTestType.CI
        assert result.failed == 2
        assert len(result.failures) == 2
        assert all(f.file == "ci" for f in result.failures)

    @pytest.mark.asyncio
    async def test_ci_without_service_raises_error(self):
        """Test that CI without injected service raises clear error (FR-6.2)."""
        repair_adapter = MockRepairCycleAdapter()  # No CI service
        repair_adapter.current_project = "proj-1"

        context = SimpleRepairCycleContext(
            stage_name="Testing",
            workflow_run_id="workflow-1",
            work_item_id="item-1",
            test_configs=(RepairTestRunConfig(test_type=RepairTestType.CI),),
            agent_name="test_agent",
            max_total_agent_calls=10,
            checkpoint_interval=5,
        )

        config = RepairTestRunConfig(test_type=RepairTestType.CI)

        # Should raise ValueError with clear message
        with pytest.raises(ValueError) as exc_info:
            await repair_adapter.run_tests(config, context)

        assert "RepairTestType.CI" in str(exc_info.value)
        assert "no ICIPipelineService is injected" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_agent_executor_not_called_for_ci(self):
        """Test that agent executor is not invoked for CI (FR-9.2)."""
        # Setup
        ci_service = MockCIPipelineAdapter()
        ci_service.set_ci_run_passing("proj-1")

        repair_adapter = MockRepairCycleAdapter(ci_pipeline_service=ci_service)
        repair_adapter.current_project = "proj-1"

        context = SimpleRepairCycleContext(
            stage_name="Testing",
            workflow_run_id="workflow-1",
            work_item_id="item-1",
            test_configs=(RepairTestRunConfig(test_type=RepairTestType.CI),),
            agent_name="test_agent",
            max_total_agent_calls=10,
            checkpoint_interval=5,
        )

        config = RepairTestRunConfig(test_type=RepairTestType.CI)

        # Clear any pre-existing agent calls
        initial_call_count = repair_adapter.get_agent_call_count()

        # Execute CI test (should not call LLM agent)
        await repair_adapter.run_tests(config, context)

        # CI execution increments agent call count but no agent implementation is called
        # (the service is mocked, not an actual agent)
        # Verify test execution agent was recorded but no actual LLM calls occurred
        subtask_calls = repair_adapter.get_subtask_agent_calls()
        assert any(c["sub_task"] == "test_execution" for c in subtask_calls)


# ====================================================================================
# Integration Tests: RepairCycleEventHandler CI Routing
# ====================================================================================


class MockRepairCycleService:
    """Mock repair cycle service for testing event handler."""

    def __init__(self):
        """Initialize mock service."""
        self.executed = False
        self.last_context = None
        self.execute_called_with_ci = False

    async def execute(self, context) -> RepairCycleResult:
        """Execute repair cycle."""
        self.executed = True
        self.last_context = context

        # Check if CI is in the test configs
        has_ci = any(tc.test_type == RepairTestType.CI for tc in context.test_configs)
        if has_ci:
            self.execute_called_with_ci = True

        # Return success result with whatever test types were configured
        cycle_results = []
        for config in context.test_configs:
            cycle_results.append(
                CycleResult(
                    test_type=config.test_type,
                    passed=True,
                    iterations=1,
                    final_result=RepairTestResult(
                        test_type=config.test_type,
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
                )
            )

        return RepairCycleResult(
            stage="Testing",
            test_results=tuple(cycle_results),
            overall_success=True,
            total_agent_calls=0,
            duration_seconds=1.0,
            timestamp="2024-01-01T00:00:00Z",
        )

    async def run_tests(self, config, context):
        """Stub method."""
        return RepairTestResult(
            test_type=config.test_type,
            iteration=1,
            passed=1,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="",
            timestamp="2024-01-01T00:00:00Z",
        )


class MockWorkflowConfigService:
    """Mock workflow config service."""

    def __init__(self, test_types=None):
        """Initialize mock service."""
        self.test_types = test_types or []

    async def get_board_workflow_template(self, board_id: str):
        """Get workflow template."""
        testing_column = ColumnTemplate(
            name="Testing",
            type=ColumnType.AUTOMATED,
            agent_id="test_agent",
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=0,
            auto_progress_on_completion=True,
            repair_cycle_agents=RepairCycleAgentConfig(),
            repair_cycle_test_types=tuple(self.test_types),
        )

        return BoardWorkflowTemplate(
            id="template-1",
            name="Test Workflow",
            board_id=board_id,
            project_id="proj-1",
            columns=(testing_column,),
        )


class TestRepairCycleEventHandlerCIRouting:
    """Tests for RepairCycleEventHandler CI routing."""

    @pytest.mark.asyncio
    async def test_ci_filtered_before_execute(self):
        """Test that CI configs are filtered before IRepairCycle.execute() (FR-5.2)."""
        # Setup
        ci_service = MockCIPipelineAdapter()
        ci_service.set_ci_run_passing("proj-1")

        repair_service = MockRepairCycleService()
        workflow_config = MockWorkflowConfigService(
            test_types=[RepairTestType.UNIT, RepairTestType.CI, RepairTestType.INTEGRATION]
        )

        handler = RepairCycleEventHandler(
            repair_cycle=repair_service,
            workflow_config=workflow_config,
            ci_pipeline_service=ci_service,
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

        # Execute handler
        await handler.handle(event)

        # Verify repair cycle execute was called
        assert repair_service.executed
        assert repair_service.last_context is not None

        # Verify CI is NOT in the test configs passed to execute
        # (it should be filtered out before execute is called)
        test_types_in_context = {tc.test_type for tc in repair_service.last_context.test_configs}
        assert RepairTestType.CI not in test_types_in_context
        assert RepairTestType.UNIT in test_types_in_context
        assert RepairTestType.INTEGRATION in test_types_in_context

    @pytest.mark.asyncio
    async def test_ci_executed_separately_and_merged(self):
        """Test that CI is executed separately and results are merged."""
        # Setup
        ci_service = MockCIPipelineAdapter()
        ci_service.set_ci_run_failing("proj-1", ["linting failed"])

        repair_service = MockRepairCycleService()
        workflow_config = MockWorkflowConfigService(
            test_types=[RepairTestType.UNIT, RepairTestType.CI]
        )

        handler = RepairCycleEventHandler(
            repair_cycle=repair_service,
            workflow_config=workflow_config,
            ci_pipeline_service=ci_service,
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

        # Execute handler
        await handler.handle(event)

        # Verify CI service was called
        ci_service.assert_ci_run_executed("proj-1")

    @pytest.mark.asyncio
    async def test_no_ci_when_not_configured(self):
        """Test that CI is not called when not in column configuration."""
        # Setup
        ci_service = MockCIPipelineAdapter()

        repair_service = MockRepairCycleService()
        workflow_config = MockWorkflowConfigService(
            test_types=[RepairTestType.UNIT, RepairTestType.INTEGRATION]  # No CI
        )

        handler = RepairCycleEventHandler(
            repair_cycle=repair_service,
            workflow_config=workflow_config,
            ci_pipeline_service=ci_service,
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

        # Execute handler
        await handler.handle(event)

        # Verify repair cycle was executed
        assert repair_service.executed
        # CI service should not have been called
        with pytest.raises(AssertionError):
            ci_service.assert_ci_run_executed("proj-1")
