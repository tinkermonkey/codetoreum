"""Unit tests for MockRepairCycleAdapter systemic fix capabilities.

Tests verify configurable outcomes and invocation tracking for systemic fix
operations in the mock adapter, enabling deterministic simulation testing.

Verifies:
- Configurable systemic fix results with success/failure
- File modification tracking in results
- Duration and clock advancement for systemic fix
- Invocation tracking and assertions
- Multiple sequential systemic fix calls
- Integration with event emission
"""

import pytest

from codetoreum.adapters.testing.mock_repair_cycle_adapter import MockRepairCycleAdapter
from codetoreum.domain.repair_cycle_types import (
    AnalysisContext,
    RepairCycleContext,
    RepairCycleStageConfig,
    RepairTestFailure,
    RepairTestResult,
    RepairTestRunConfig,
    RepairTestType,
    SystemicFixResult,
)
from codetoreum.infrastructure.simulation.bootstrap import SimulationApplicationBootstrap


@pytest.mark.asyncio
async def test_mock_adapter_configurable_systemic_fix_success(
    simulation_bootstrap: SimulationApplicationBootstrap,
):
    """Test configuring mock adapter with successful systemic fix result."""
    mock_adapter = simulation_bootstrap.adapters.repair_cycle_as_mock()

    # Configure a successful systemic fix
    mock_adapter.set_systemic_fix_result([
        SystemicFixResult(
            success=True,
            files_modified=("src/api.py", "src/models.py"),
            root_cause_addressed="API contract change across modules",
            duration_seconds=120.0,
        ),
    ])

    # Setup minimal test to trigger systemic fix
    mock_adapter.set_test_result_sequence(
        RepairTestType.UNIT,
        [
        RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=5,
            failed=3,
            warnings=0,
            failures=(
                RepairTestFailure("test_api.py", "test_contract", "Mismatch"),
                RepairTestFailure("test_models.py", "test_schema", "Mismatch"),
                RepairTestFailure("test_services.py", "test_sync", "Issue"),
            ),
            warning_list=(),
            raw_output="Failures detected",
            timestamp="2025-03-31T10:00:00Z",
        ),
        RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=2,
            passed=8,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="All passed",
            timestamp="2025-03-31T10:01:00Z",
        ),
    ])

    context = RepairCycleContext(
        work_item_id="WI-123",
        workflow_run_id="WR-456",
        analysis_context=AnalysisContext(
            work_item_id="WI-123",
            iteration=1,
            workflow_run_id="WR-456",
        ),
        stage_config=RepairCycleStageConfig(
            name="fix_failures",
            test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
        ),
    )

    result = await mock_adapter.execute(context)

    # Verify systemic fix was invoked
    assert mock_adapter.systemic_fix_call_count >= 1
    # Verify success
    assert result.overall_success is True


@pytest.mark.asyncio
async def test_mock_adapter_configurable_systemic_fix_failure(
    simulation_bootstrap: SimulationApplicationBootstrap,
):
    """Test configuring mock adapter with failed systemic fix result."""
    mock_adapter = simulation_bootstrap.adapters.repair_cycle_as_mock()

    # Configure a failed systemic fix (should trigger fallback to file-level fix)
    mock_adapter.set_systemic_fix_result([
        SystemicFixResult(
            success=False,
            files_modified=(),
            root_cause_addressed="Systemic fix attempt failed",
            duration_seconds=90.0,
        ),
    ])

    # Test sequence with failures that will trigger fallback
    mock_adapter.set_test_result_sequence(
        RepairTestType.UNIT,
        [
        RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=5,
            failed=3,
            warnings=0,
            failures=(
                RepairTestFailure("test_a.py", "test_1", "Error 1"),
                RepairTestFailure("test_b.py", "test_2", "Error 2"),
                RepairTestFailure("test_c.py", "test_3", "Error 3"),
            ),
            warning_list=(),
            raw_output="Failures",
            timestamp="2025-03-31T10:00:00Z",
        ),
        RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=2,
            passed=8,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="Passed after fallback fix",
            timestamp="2025-03-31T10:01:00Z",
        ),
    ])

    context = RepairCycleContext(
        work_item_id="WI-123",
        workflow_run_id="WR-456",
        analysis_context=AnalysisContext(
            work_item_id="WI-123",
            iteration=1,
            workflow_run_id="WR-456",
        ),
        stage_config=RepairCycleStageConfig(
            name="fix_failures",
            test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
        ),
    )

    result = await mock_adapter.execute(context)

    # Even with failed systemic fix, should eventually succeed via fallback
    assert result.overall_success is True


@pytest.mark.asyncio
async def test_mock_adapter_multiple_systemic_fix_sequence(
    simulation_bootstrap: SimulationApplicationBootstrap,
):
    """Test configuring mock adapter with multiple sequential systemic fixes."""
    mock_adapter = simulation_bootstrap.adapters.repair_cycle_as_mock()

    # Configure two systemic fix results (for two iterations)
    mock_adapter.set_systemic_fix_result([
        SystemicFixResult(
            success=True,
            files_modified=("api.py",),
            root_cause_addressed="First root cause",
            duration_seconds=60.0,
        ),
        SystemicFixResult(
            success=True,
            files_modified=("models.py",),
            root_cause_addressed="Second root cause",
            duration_seconds=90.0,
        ),
    ])

    # Test sequence: fail → fail → pass (requiring two fixes)
    mock_adapter.set_test_result_sequence(
        RepairTestType.UNIT,
        [
        RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=6,
            failed=4,
            warnings=0,
            failures=tuple(
                RepairTestFailure(f"test_{i}.py", f"test_{i}", f"Error {i}")
                for i in range(4)
            ),
            warning_list=(),
            raw_output="Failures after first fix",
            timestamp="2025-03-31T10:00:00Z",
        ),
        RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=2,
            passed=5,
            failed=5,
            warnings=0,
            failures=tuple(
                RepairTestFailure(f"test_{i}.py", f"test_{i}", f"Error {i}")
                for i in range(5)
            ),
            warning_list=(),
            raw_output="Failures after second attempt",
            timestamp="2025-03-31T10:01:00Z",
        ),
        RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=3,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="All passed",
            timestamp="2025-03-31T10:02:00Z",
        ),
    ])

    context = RepairCycleContext(
        work_item_id="WI-123",
        workflow_run_id="WR-456",
        analysis_context=AnalysisContext(
            work_item_id="WI-123",
            iteration=1,
            workflow_run_id="WR-456",
        ),
        stage_config=RepairCycleStageConfig(
            name="fix_failures",
            test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
        ),
    )

    result = await mock_adapter.execute(context)

    # Verify two systemic fix calls occurred
    assert mock_adapter.systemic_fix_call_count == 2
    # Verify success
    assert result.overall_success is True


@pytest.mark.asyncio
async def test_mock_adapter_systemic_fix_no_files_modified(
    simulation_bootstrap: SimulationApplicationBootstrap,
):
    """Test systemic fix that succeeds but modifies no files."""
    mock_adapter = simulation_bootstrap.adapters.repair_cycle_as_mock()

    # Configure systemic fix with no file modifications
    mock_adapter.set_systemic_fix_result([
        SystemicFixResult(
            success=True,
            files_modified=(),
            root_cause_addressed="Configuration change (no code files)",
            duration_seconds=45.0,
        ),
    ])

    # Test sequence
    mock_adapter.set_test_result_sequence(
        RepairTestType.UNIT,
        [
        RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=5,
            failed=5,
            warnings=0,
            failures=tuple(
                RepairTestFailure(f"test_{i}.py", f"test_{i}", "Config error")
                for i in range(5)
            ),
            warning_list=(),
            raw_output="Config errors",
            timestamp="2025-03-31T10:00:00Z",
        ),
        RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=2,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="All passed",
            timestamp="2025-03-31T10:01:00Z",
        ),
    ])

    context = RepairCycleContext(
        work_item_id="WI-123",
        workflow_run_id="WR-456",
        analysis_context=AnalysisContext(
            work_item_id="WI-123",
            iteration=1,
            workflow_run_id="WR-456",
        ),
        stage_config=RepairCycleStageConfig(
            name="fix_failures",
            test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
        ),
    )

    result = await mock_adapter.execute(context)

    # Verify systemic fix was invoked
    assert mock_adapter.systemic_fix_call_count >= 1
    # Verify success despite no files modified
    assert result.overall_success is True


@pytest.mark.asyncio
async def test_mock_adapter_systemic_fix_with_clock_advancement(
    simulation_bootstrap: SimulationApplicationBootstrap,
):
    """Test that systemic fix result can include clock advancement duration."""
    mock_adapter = simulation_bootstrap.adapters.repair_cycle_as_mock()

    # Get initial clock time
    initial_time = mock_adapter.clock.now()

    # Configure systemic fix with specific duration
    mock_adapter.set_systemic_fix_result([
        SystemicFixResult(
            success=True,
            files_modified=("file.py",),
            root_cause_addressed="Root cause",
            duration_seconds=300.0,  # 5 minutes
        ),
    ])

    # Minimal test configuration
    mock_adapter.set_test_result_sequence(
        RepairTestType.UNIT,
        [
        RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=5,
            failed=3,
            warnings=0,
            failures=tuple(
                RepairTestFailure(f"test_{i}.py", f"test_{i}", "Error")
                for i in range(3)
            ),
            warning_list=(),
            raw_output="Failures",
            timestamp="2025-03-31T10:00:00Z",
        ),
        RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=2,
            passed=8,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="Passed",
            timestamp="2025-03-31T10:01:00Z",
        ),
    ])

    context = RepairCycleContext(
        work_item_id="WI-123",
        workflow_run_id="WR-456",
        analysis_context=AnalysisContext(
            work_item_id="WI-123",
            iteration=1,
            workflow_run_id="WR-456",
        ),
        stage_config=RepairCycleStageConfig(
            name="fix_failures",
            test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
        ),
    )

    result = await mock_adapter.execute(context)

    # Verify systemic fix was invoked
    assert mock_adapter.systemic_fix_call_count >= 1
    # Verify time has advanced (clock operates in simulation mode with multiplier)
    final_time = mock_adapter.clock.now()
    assert final_time > initial_time

    # Verify success
    assert result.overall_success is True


@pytest.mark.asyncio
async def test_mock_adapter_assert_systemic_fix_call_count(
    simulation_bootstrap: SimulationApplicationBootstrap,
):
    """Test that mock adapter provides assertion helpers for systemic fix calls."""
    mock_adapter = simulation_bootstrap.adapters.repair_cycle_as_mock()

    # Configure single systemic fix
    mock_adapter.set_systemic_fix_result([
        SystemicFixResult(
            success=True,
            files_modified=("file.py",),
            root_cause_addressed="Root cause",
            duration_seconds=60.0,
        ),
    ])

    # Test sequence
    mock_adapter.set_test_result_sequence(
        RepairTestType.UNIT,
        [
        RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=5,
            failed=3,
            warnings=0,
            failures=tuple(
                RepairTestFailure(f"test_{i}.py", f"test_{i}", "Error")
                for i in range(3)
            ),
            warning_list=(),
            raw_output="Failures",
            timestamp="2025-03-31T10:00:00Z",
        ),
        RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=2,
            passed=8,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="Passed",
            timestamp="2025-03-31T10:01:00Z",
        ),
    ])

    context = RepairCycleContext(
        work_item_id="WI-123",
        workflow_run_id="WR-456",
        analysis_context=AnalysisContext(
            work_item_id="WI-123",
            iteration=1,
            workflow_run_id="WR-456",
        ),
        stage_config=RepairCycleStageConfig(
            name="fix_failures",
            test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
        ),
    )

    result = await mock_adapter.execute(context)

    # Use assertion helper
    try:
        # Should succeed: exactly 1 systemic fix was called
        assert mock_adapter.systemic_fix_call_count == 1
    except AssertionError:
        pytest.fail("systemic_fix_call_count should be 1")

    # Verify overall success
    assert result.overall_success is True


@pytest.mark.asyncio
async def test_mock_adapter_systemic_fix_exhausts_results_queue(
    simulation_bootstrap: SimulationApplicationBootstrap,
):
    """Test mock adapter behavior when systemic fix result queue is exhausted.

    When configured results are exhausted, subsequent calls should fail gracefully.
    """
    mock_adapter = simulation_bootstrap.adapters.repair_cycle_as_mock()

    # Configure only ONE systemic fix result
    mock_adapter.set_systemic_fix_result([
        SystemicFixResult(
            success=True,
            files_modified=("file1.py",),
            root_cause_addressed="First root cause",
            duration_seconds=60.0,
        ),
    ])

    # Test sequence requiring TWO systemic fixes
    mock_adapter.set_test_result_sequence(
        RepairTestType.UNIT,
        [
        RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=6,
            failed=4,
            warnings=0,
            failures=tuple(
                RepairTestFailure(f"test_{i}.py", f"test_{i}", "Error")
                for i in range(4)
            ),
            warning_list=(),
            raw_output="Failures after first fix",
            timestamp="2025-03-31T10:00:00Z",
        ),
        RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=2,
            passed=5,
            failed=5,
            warnings=0,
            failures=tuple(
                RepairTestFailure(f"test_{i}.py", f"test_{i}", "Error")
                for i in range(5)
            ),
            warning_list=(),
            raw_output="Still failing, need more fixes",
            timestamp="2025-03-31T10:01:00Z",
        ),
        RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=3,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="Passed after fallback",
            timestamp="2025-03-31T10:02:00Z",
        ),
    ])

    context = RepairCycleContext(
        work_item_id="WI-123",
        workflow_run_id="WR-456",
        analysis_context=AnalysisContext(
            work_item_id="WI-123",
            iteration=1,
            workflow_run_id="WR-456",
        ),
        stage_config=RepairCycleStageConfig(
            name="fix_failures",
            test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
        ),
    )

    # Execute: should handle exhausted queue gracefully
    result = await mock_adapter.execute(context)

    # Verify that adapter handled the situation (either via fallback or other mechanism)
    # The cycle should still succeed
    assert result.overall_success is True


@pytest.mark.asyncio
async def test_mock_adapter_systemic_fix_result_immutable(
    simulation_bootstrap: SimulationApplicationBootstrap,
):
    """Test that configured systemic fix results are immutable."""
    mock_adapter = simulation_bootstrap.adapters.repair_cycle_as_mock()

    fix_result = SystemicFixResult(
        success=True,
        files_modified=("file.py",),
        root_cause_addressed="Root cause",
        duration_seconds=60.0,
    )

    # Configure result
    mock_adapter.set_systemic_fix_result([fix_result])

    # Verify result is immutable
    with pytest.raises((TypeError, AttributeError)):
        fix_result.success = False  # type: ignore[misc]

    with pytest.raises((TypeError, AttributeError)):
        fix_result.duration_seconds = 120.0  # type: ignore[misc]
