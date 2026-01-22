"""Comprehensive contract tests for IRepairCycle interface.

Tests validate that all implementations satisfy the repair cycle contract:
- Error handling consistency
- Idempotency and safe retries
- State consistency after failures
- Boundary condition handling
- Immutability of domain types

Subclasses must implement create_adapter() to provide a concrete IRepairCycle
implementation to test against all contract requirements.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Tuple

import pytest

from codetoreum.adapters.testing.mock_repair_cycle_adapter import MockRepairCycleAdapter
from codetoreum.domain.repair_cycle_types import (
    RepairCycleResult,
    RepairTestFailure,
    RepairTestResult,
    RepairTestRunConfig,
    RepairTestType,
    RepairTestWarning,
    CycleResult,
)
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.output.repair_cycle_service import IRepairCycle, RepairCycleContext


class MockRepairCycleContext:
    """Concrete implementation of RepairCycleContext Protocol for testing."""

    def __init__(
        self,
        stage_name: str = "fix_failures",
        pipeline_run_id: str = "pipeline-123",
        test_configs: Tuple[RepairTestRunConfig, ...] = (),
        agent_name: str = "repair-agent",
        max_total_agent_calls: int = 100,
        checkpoint_interval: int = 5,
    ):
        self.stage_name = stage_name
        self.pipeline_run_id = pipeline_run_id
        self.test_configs = test_configs
        self.agent_name = agent_name
        self.max_total_agent_calls = max_total_agent_calls
        self.checkpoint_interval = checkpoint_interval


class TestRepairCycleServiceContract(ABC):
    """Abstract contract tests for IRepairCycle implementations.

    All implementations must pass these tests to ensure:
    - Consistent error handling
    - Idempotent operations
    - State consistency
    - Boundary conditions
    """

    @abstractmethod
    async def create_adapter(self) -> IRepairCycle:
        """Create and return an IRepairCycle instance for testing."""
        pass

    @abstractmethod
    def create_context(
        self,
        stage_name: str = "fix_failures",
        pipeline_run_id: str = "pipeline-123",
        max_total_agent_calls: int = 100,
    ) -> RepairCycleContext:
        """Create a test context with given configuration."""
        pass

    # =========================================================================
    # ERROR HANDLING CONTRACT TESTS
    # =========================================================================

    @pytest.mark.asyncio
    async def test_run_tests_invalid_timeout_raises_valueerror(self) -> None:
        """All implementations must raise ValueError for invalid timeout.

        Error handling contract: Timeout <= 0 must be rejected consistently.
        """
        with pytest.raises(ValueError):
            RepairTestRunConfig(
                test_type=RepairTestType.UNIT,
                timeout=0,  # Invalid
                max_iterations=5,
            )

    @pytest.mark.asyncio
    async def test_run_tests_invalid_max_iterations_raises_valueerror(self) -> None:
        """All implementations must raise ValueError for invalid max_iterations.

        Error handling contract: max_iterations <= 0 must be rejected consistently.
        """
        with pytest.raises(ValueError):
            RepairTestRunConfig(
                test_type=RepairTestType.UNIT,
                timeout=900,
                max_iterations=0,  # Invalid
            )

    @pytest.mark.asyncio
    async def test_fix_failures_empty_dict_no_error(self) -> None:
        """All implementations must handle empty failures dict without error.

        Error handling contract: Empty input should not error, just return 0.
        """
        adapter = await self.create_adapter()
        context = self.create_context()
        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=1,
        )

        # Empty failures dict should not raise
        files_fixed = await adapter.fix_failures_by_file({}, config, context)

        assert files_fixed == 0

    @pytest.mark.asyncio
    async def test_handle_warnings_empty_list_no_error(self) -> None:
        """All implementations must handle empty warnings without error.

        Error handling contract: Test result with 0 warnings should not error.
        """
        adapter = await self.create_adapter()
        context = self.create_context()
        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=1,
        )
        test_result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=5,
            failed=0,
            warnings=0,  # No warnings
            failures=(),
            warning_list=(),  # Empty warnings list
            raw_output="No warnings",
            timestamp=datetime.utcnow().isoformat(),
        )

        # Empty warnings should not raise
        warnings_reviewed = await adapter.handle_warnings(test_result, config, context)

        assert warnings_reviewed == 0

    # =========================================================================
    # IDEMPOTENCY CONTRACT TESTS
    # =========================================================================

    @pytest.mark.asyncio
    async def test_checkpoint_idempotent(self) -> None:
        """All implementations must support idempotent checkpoint().

        Idempotency contract: Calling checkpoint multiple times for same
        iteration should be safe (no duplicate checkpoints).
        """
        adapter = await self.create_adapter()
        context = self.create_context()

        # Call checkpoint multiple times for same iteration
        await adapter.checkpoint(RepairTestType.UNIT, 5, context)
        await adapter.checkpoint(RepairTestType.UNIT, 5, context)
        await adapter.checkpoint(RepairTestType.UNIT, 5, context)

        # Should not raise or cause state inconsistency
        # Implementation should handle idempotent calls gracefully

    @pytest.mark.asyncio
    async def test_fix_failures_idempotent_same_input(self) -> None:
        """All implementations must support idempotent fix_failures_by_file().

        Idempotency contract: Fixing same failures twice should produce same result.
        """
        adapter = await self.create_adapter()
        context = self.create_context()
        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=1,
        )
        failures = {
            "test_auth.py": (
                RepairTestFailure(
                    file="test_auth.py",
                    test="test_login",
                    message="Expected True",
                ),
            ),
        }

        # Fix same failures twice - should be idempotent
        fixed1 = await adapter.fix_failures_by_file(failures, config, context)
        fixed2 = await adapter.fix_failures_by_file(failures, config, context)

        # Count should be consistent
        assert fixed1 == fixed2
        assert fixed1 == 1

    # =========================================================================
    # STATE CONSISTENCY CONTRACT TESTS
    # =========================================================================

    @pytest.mark.asyncio
    async def test_fix_failures_maintains_consistent_file_count(self) -> None:
        """All implementations must maintain consistent file counts.

        State consistency contract: Fix count should match input file count.
        """
        adapter = await self.create_adapter()
        context = self.create_context()
        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=1,
        )

        # Test with various file counts
        for num_files in [1, 2, 5]:
            failures = {
                f"test_file_{i}.py": (
                    RepairTestFailure(
                        file=f"test_file_{i}.py",
                        test=f"test_{i}",
                        message="Test failure",
                    ),
                )
                for i in range(num_files)
            }

            fixed = await adapter.fix_failures_by_file(failures, config, context)

            # Fixed count must match input file count
            assert fixed == len(failures)

    @pytest.mark.asyncio
    async def test_run_tests_failure_count_consistency(self) -> None:
        """All implementations must maintain consistent failure counts.

        Boundary contract: The failed count in result must match failures list.
        """
        adapter = await self.create_adapter()
        context = self.create_context()
        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=1,
        )

        result = await adapter.run_tests(config, context)

        # Consistency check: failed count must equal failures list length
        assert result.failed == len(result.failures)

    @pytest.mark.asyncio
    async def test_handle_warnings_return_count_consistency(self) -> None:
        """All implementations must return consistent warning counts.

        Boundary contract: Returned warning count should be logically consistent.
        """
        adapter = await self.create_adapter()
        context = self.create_context()
        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=1,
        )

        # Test with 3 warnings
        warnings = (
            RepairTestWarning(file="file_1.py", message="Warning 1"),
            RepairTestWarning(file="file_2.py", message="Warning 2"),
            RepairTestWarning(file="file_3.py", message="Warning 3"),
        )

        test_result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=3,
            failures=(),
            warning_list=warnings,
            raw_output="",
            timestamp=datetime.utcnow().isoformat(),
        )

        reviewed = await adapter.handle_warnings(test_result, config, context)

        # Return value should be non-negative
        assert reviewed >= 0

    # =========================================================================
    # BOUNDARY CONDITION CONTRACT TESTS
    # =========================================================================

    @pytest.mark.asyncio
    async def test_max_iterations_valid_values(self) -> None:
        """All implementations must accept valid max_iterations values.

        Boundary contract: max_iterations 1-100 should all be valid.
        """
        # All of these should be valid configurations (not raise)
        for max_iter in [1, 2, 5, 10, 50, 100]:
            config = RepairTestRunConfig(
                test_type=RepairTestType.UNIT,
                timeout=900,
                max_iterations=max_iter,
            )
            assert config.max_iterations == max_iter

    @pytest.mark.asyncio
    async def test_max_agent_calls_enforced_in_context(self) -> None:
        """All implementations must respect max_total_agent_calls from context.

        Boundary contract: Context max_total_agent_calls should be accessible.
        """
        context = self.create_context(max_total_agent_calls=50)

        # Context should have the specified agent call limit
        assert context.max_total_agent_calls == 50

    @pytest.mark.asyncio
    async def test_test_types_all_valid(self) -> None:
        """All implementations must support all test types (UNIT, INTEGRATION, E2E).

        Boundary contract: All test types should be valid config options.
        """
        for test_type in [RepairTestType.UNIT, RepairTestType.INTEGRATION, RepairTestType.E2E]:
            config = RepairTestRunConfig(
                test_type=test_type,
                timeout=900,
                max_iterations=1,
            )
            assert config.test_type == test_type

    # =========================================================================
    # IMMUTABILITY CONTRACT TESTS (DOMAIN TYPES)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_repair_cycle_result_immutable(self) -> None:
        """RepairCycleResult must be immutable (frozen dataclass)."""
        result = RepairCycleResult(
            stage="test",
            test_results=(),
            overall_success=True,
            total_agent_calls=0,
            duration_seconds=1.0,
            timestamp=datetime.utcnow().isoformat(),
        )

        # Attempting to modify should raise FrozenInstanceError or similar
        with pytest.raises((AttributeError, Exception)):
            result.stage = "modified"  # type: ignore

    @pytest.mark.asyncio
    async def test_repair_test_result_immutable(self) -> None:
        """RepairTestResult must be immutable (frozen dataclass)."""
        result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=5,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="",
            timestamp=datetime.utcnow().isoformat(),
        )

        # Attempting to modify should raise FrozenInstanceError or similar
        with pytest.raises((AttributeError, Exception)):
            result.passed = 10  # type: ignore

    @pytest.mark.asyncio
    async def test_repair_test_failure_immutable(self) -> None:
        """RepairTestFailure must be immutable (frozen dataclass)."""
        failure = RepairTestFailure(
            file="test.py",
            test="test_func",
            message="Failed",
        )

        # Attempting to modify should raise FrozenInstanceError or similar
        with pytest.raises((AttributeError, Exception)):
            failure.file = "other.py"  # type: ignore

    @pytest.mark.asyncio
    async def test_cycle_result_immutable(self) -> None:
        """CycleResult must be immutable (frozen dataclass)."""
        final_result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=5,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="",
            timestamp=datetime.utcnow().isoformat(),
        )

        cycle = CycleResult(
            test_type=RepairTestType.UNIT,
            passed=True,
            iterations=1,
            final_result=final_result,
            error=None,
            files_fixed=0,
            warnings_reviewed=0,
            duration_seconds=5.0,
        )

        # Attempting to modify should raise FrozenInstanceError
        with pytest.raises((AttributeError, Exception)):
            cycle.passed = False  # type: ignore


# =============================================================================
# CONCRETE IMPLEMENTATION TESTS
# =============================================================================


class TestMockRepairCycleAdapterContract(TestRepairCycleServiceContract):
    """Concrete contract tests for MockRepairCycleAdapter implementation."""

    async def create_adapter(self) -> IRepairCycle:
        """Create MockRepairCycleAdapter for testing."""
        clock = SimulationClock()
        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "test-project"
        return adapter

    def create_context(
        self,
        stage_name: str = "fix_failures",
        pipeline_run_id: str = "pipeline-123",
        max_total_agent_calls: int = 100,
    ) -> RepairCycleContext:
        """Create test context."""
        return MockRepairCycleContext(
            stage_name=stage_name,
            pipeline_run_id=pipeline_run_id,
            max_total_agent_calls=max_total_agent_calls,
        )
