"""Unit tests for IRepairCycle port interface and RepairCycleContext Protocol.

Tests validate:
1. RepairCycleContext Protocol interface contract
2. IRepairCycle Protocol interface contract
3. Protocol can be implemented by concrete classes
4. All methods have correct signatures and return types
"""

from datetime import UTC, datetime

import pytest

from codetoreum.domain.repair_cycle_types import (
    CycleResult,
    RepairCycleResult,
    RepairTestFailure,
    RepairTestResult,
    RepairTestRunConfig,
    RepairTestType,
)
from codetoreum.ports.output import IRepairCycle, RepairCycleContext

# =============================================================================
# RepairCycleContext Protocol Tests
# =============================================================================


class MockRepairCycleContext:
    """Concrete implementation satisfying RepairCycleContext Protocol."""

    def __init__(
        self,
        stage_name: str = "fix_failures",
        workflow_run_id: str = "pipeline-123",
        work_item_id: str = "item-1",
        test_configs: tuple[RepairTestRunConfig, ...] = (),
        agent_name: str = "repair-agent",
        max_total_agent_calls: int = 100,
        checkpoint_interval: int = 5,
        agent_config=None,
    ):
        self.stage_name = stage_name
        self.workflow_run_id = workflow_run_id
        self.work_item_id = work_item_id
        self.test_configs = test_configs
        self.agent_name = agent_name
        self.max_total_agent_calls = max_total_agent_calls
        self.checkpoint_interval = checkpoint_interval
        self.agent_config = agent_config


class TestRepairCycleContextProtocol:
    """Tests for RepairCycleContext Protocol."""

    def test_context_has_required_attributes(self) -> None:
        """Test that RepairCycleContext Protocol has all required attributes."""
        ctx = MockRepairCycleContext()

        # All attributes should be accessible
        assert ctx.stage_name == "fix_failures"
        assert ctx.workflow_run_id == "pipeline-123"
        assert ctx.test_configs == ()
        assert ctx.agent_name == "repair-agent"
        assert ctx.max_total_agent_calls == 100
        assert ctx.checkpoint_interval == 5

    def test_context_with_test_configs(self) -> None:
        """Test RepairCycleContext with test configurations."""
        unit_config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=10,
        )
        configs = (unit_config,)

        ctx = MockRepairCycleContext(
            stage_name="test_phase",
            test_configs=configs,
        )

        assert ctx.stage_name == "test_phase"
        assert len(ctx.test_configs) == 1
        assert ctx.test_configs[0].test_type == RepairTestType.UNIT


# =============================================================================
# IRepairCycle Protocol Tests
# =============================================================================


class MockRepairCycle:
    """Concrete implementation satisfying IRepairCycle Protocol."""

    async def execute(self, context: RepairCycleContext) -> RepairCycleResult:
        """Execute complete repair cycle."""
        # Create a simple CycleResult for UNIT test type

        final_result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=5,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="All tests passed",
            timestamp=datetime.now(UTC).isoformat(),
        )

        cycle_result = CycleResult(
            test_type=RepairTestType.UNIT,
            passed=True,
            iterations=1,
            final_result=final_result,
            error=None,
            files_fixed=0,
            warnings_reviewed=0,
            duration_seconds=5.0,
        )

        return RepairCycleResult(
            stage="test_phase",
            test_results=(cycle_result,),
            overall_success=True,
            total_agent_calls=0,
            duration_seconds=5.0,
            timestamp=datetime.now(UTC).isoformat(),
        )

    async def run_tests(
        self,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> RepairTestResult:
        """Execute tests for a specific test type."""
        return RepairTestResult(
            test_type=config.test_type,
            iteration=1,
            passed=5,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="Tests completed successfully",
            timestamp=datetime.now(UTC).isoformat(),
        )

    async def fix_failures_by_file(
        self,
        grouped_failures: dict[str, tuple[RepairTestFailure, ...]],
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> int:
        """Fix test failures grouped by file."""
        return len(grouped_failures)

    async def handle_warnings(
        self,
        test_result: RepairTestResult,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> int:
        """Review and fix warnings from test execution."""
        return 0

    async def analyze_systemic_issues(
        self,
        failures: tuple[RepairTestFailure, ...],
    ) -> str:
        """Analyze failure root causes at systemic level."""
        return "No systemic issues detected"

    async def apply_systemic_fixes(
        self,
        classification,
        reasoning: str,
        test_result: RepairTestResult,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> bool:
        """Apply cross-cutting fixes based on systemic analysis."""
        return True

    async def fix_failures_systemically(
        self,
        failures: tuple[RepairTestFailure, ...],
        analysis_result,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ):
        """Apply a coordinated holistic fix addressing the root cause across all affected files."""
        from codetoreum.domain.repair_cycle_types import SystemicFixResult
        return SystemicFixResult(
            success=True,
            files_modified=(),
            root_cause_addressed="Root cause addressed by systemic fix",
            duration_seconds=5.0,
        )

    async def rebuild_environment(
        self,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> bool:
        """Rebuild test environment after systemic fixes."""
        return True

    async def verify_environment(
        self,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> bool:
        """Verify that rebuilt environment is ready for testing."""
        return True

    async def checkpoint(
        self,
        test_type: RepairTestType,
        iteration: int,
        context: RepairCycleContext,
    ) -> None:
        """Save repair cycle state for resume after failures."""
        return


class TestIRepairCycleProtocol:
    """Tests for IRepairCycle Protocol."""

    def test_protocol_has_execute_method(self) -> None:
        """Test that IRepairCycle Protocol has execute method."""
        assert hasattr(IRepairCycle, "execute")

    def test_protocol_has_run_tests_method(self) -> None:
        """Test that IRepairCycle Protocol has run_tests method."""
        assert hasattr(IRepairCycle, "run_tests")

    def test_protocol_has_fix_failures_by_file_method(self) -> None:
        """Test that IRepairCycle Protocol has fix_failures_by_file method."""
        assert hasattr(IRepairCycle, "fix_failures_by_file")

    def test_protocol_has_handle_warnings_method(self) -> None:
        """Test that IRepairCycle Protocol has handle_warnings method."""
        assert hasattr(IRepairCycle, "handle_warnings")

    def test_protocol_has_checkpoint_method(self) -> None:
        """Test that IRepairCycle Protocol has checkpoint method."""
        assert hasattr(IRepairCycle, "checkpoint")

    def test_protocol_has_analyze_systemic_issues_method(self) -> None:
        """Test that IRepairCycle Protocol has analyze_systemic_issues method."""
        assert hasattr(IRepairCycle, "analyze_systemic_issues")

    def test_protocol_has_expected_method_count(self) -> None:
        """Test that IRepairCycle Protocol has exactly 10 methods."""
        methods = [m for m in dir(IRepairCycle) if not m.startswith("_") and callable(getattr(IRepairCycle, m))]
        assert len(methods) == 10
        assert set(methods) == {
            "execute",
            "run_tests",
            "fix_failures_by_file",
            "handle_warnings",
            "analyze_systemic_issues",
            "apply_systemic_fixes",
            "fix_failures_systemically",
            "rebuild_environment",
            "verify_environment",
            "checkpoint",
        }

    @pytest.mark.asyncio
    async def test_concrete_implementation_satisfies_protocol(self) -> None:
        """Test that concrete implementation satisfies IRepairCycle Protocol."""
        impl: IRepairCycle = MockRepairCycle()

        ctx = MockRepairCycleContext()

        # All methods should be callable and return correct types
        result = await impl.execute(ctx)
        assert isinstance(result, RepairCycleResult)
        assert result.overall_success is True

    @pytest.mark.asyncio
    async def test_execute_returns_repair_cycle_result(self) -> None:
        """Test that execute returns RepairCycleResult."""
        impl = MockRepairCycle()
        ctx = MockRepairCycleContext()

        result = await impl.execute(ctx)

        assert isinstance(result, RepairCycleResult)
        assert hasattr(result, "stage")
        assert hasattr(result, "test_results")
        assert hasattr(result, "total_agent_calls")
        assert hasattr(result, "overall_success")
        assert hasattr(result, "duration_seconds")

    @pytest.mark.asyncio
    async def test_run_tests_returns_repair_test_result(self) -> None:
        """Test that run_tests returns RepairTestResult."""
        impl = MockRepairCycle()
        ctx = MockRepairCycleContext()
        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
        )

        result = await impl.run_tests(config, ctx)

        assert isinstance(result, RepairTestResult)
        assert result.test_type == RepairTestType.UNIT

    @pytest.mark.asyncio
    async def test_fix_failures_by_file_returns_int(self) -> None:
        """Test that fix_failures_by_file returns int."""
        impl = MockRepairCycle()
        ctx = MockRepairCycleContext()
        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
        )
        failures: dict[str, tuple[RepairTestFailure, ...]] = {
            "test_auth.py": (
                RepairTestFailure(
                    file="test_auth.py",
                    test="test_login",
                    message="Expected True",
                ),
            ),
        }

        result = await impl.fix_failures_by_file(failures, config, ctx)

        assert isinstance(result, int)
        assert result == 1

    @pytest.mark.asyncio
    async def test_handle_warnings_returns_int(self) -> None:
        """Test that handle_warnings returns int."""
        from codetoreum.domain.repair_cycle_types import RepairTestWarning

        impl = MockRepairCycle()
        ctx = MockRepairCycleContext()
        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
        )
        test_result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=5,
            failed=0,
            warnings=1,
            failures=(),
            warning_list=(
                RepairTestWarning(
                    file="test_auth.py",
                    message="DeprecationWarning: use new_method instead",
                ),
            ),
            raw_output="Test output with warnings",
            timestamp=datetime.now(UTC).isoformat(),
        )

        result = await impl.handle_warnings(test_result, config, ctx)

        assert isinstance(result, int)


# =============================================================================
# Integration Tests
# =============================================================================


class TestProtocolIntegration:
    """Integration tests for Protocol implementations."""

    @pytest.mark.asyncio
    async def test_full_repair_cycle_workflow(self) -> None:
        """Test full repair cycle workflow with Protocol implementation."""
        cycle_impl: IRepairCycle = MockRepairCycle()
        context = MockRepairCycleContext(
            stage_name="test_phase",
            workflow_run_id="pipeline-abc",
            agent_name="test-agent",
            max_total_agent_calls=50,
            checkpoint_interval=3,
        )

        # Execute full cycle
        result = await cycle_impl.execute(context)
        assert result.overall_success is True
        assert result.total_agent_calls == 0

        # Checkpoint at iteration 3
        await cycle_impl.checkpoint(RepairTestType.UNIT, 3, context)

        # Run tests
        unit_config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
        )
        test_result = await cycle_impl.run_tests(unit_config, context)
        assert isinstance(test_result, RepairTestResult)

    @pytest.mark.asyncio
    async def test_context_attributes_are_accessible(self) -> None:
        """Test that context attributes are accessible from implementation."""
        configs = (
            RepairTestRunConfig(test_type=RepairTestType.UNIT, timeout=900),
            RepairTestRunConfig(test_type=RepairTestType.INTEGRATION, timeout=1800),
        )
        context = MockRepairCycleContext(
            stage_name="validation",
            workflow_run_id="pipeline-xyz",
            test_configs=configs,
            agent_name="validator",
            max_total_agent_calls=200,
            checkpoint_interval=10,
        )

        # All attributes should be accessible
        assert context.stage_name == "validation"
        assert context.workflow_run_id == "pipeline-xyz"
        assert len(context.test_configs) == 2
        assert context.agent_name == "validator"
        assert context.max_total_agent_calls == 200
        assert context.checkpoint_interval == 10
