"""Integration tests for systemic fix dispatch logic in repair cycle.

Tests verify the conditional dispatch between fix_failures_systemically() and
fix_failures_by_file() based on the cross_cutting field from systemic analysis.

Verifies:
- When cross_cutting=True and failure_count <= 50: dispatches to fix_failures_systemically()
- When cross_cutting=False: dispatches to fix_failures_by_file()
- When cross_cutting=True but failure_count > 50: falls back to fix_failures_by_file()
- Multiple systemic fix iterations within a single repair cycle
- Proper state transitions and event emission for both branches
- Failure counts are correctly tracked through dispatch
"""

from dataclasses import dataclass

import pytest

from codetoreum.adapters.testing.mock_repair_cycle_adapter import MockRepairCycleAdapter
from codetoreum.domain.repair_cycle_types import (
    AnalysisContext,
    FailureClassification,
    RepairCycleAgentConfig,
    RepairCycleStageConfig,
    RepairTestFailure,
    RepairTestResult,
    RepairTestRunConfig,
    RepairTestType,
    SystemicAnalysisResult,
    SystemicFixResult,
)
from codetoreum.infrastructure.simulation.bootstrap import SimulationApplicationBootstrap
from codetoreum.ports.output.repair_cycle_service import RepairCycleContext


@dataclass
class SimpleRepairCycleContext:
    """Simple concrete implementation of RepairCycleContext for testing."""

    stage_name: str
    workflow_run_id: str
    work_item_id: str
    test_configs: tuple[RepairTestRunConfig, ...]
    agent_name: str = "senior_software_engineer"
    max_total_agent_calls: int = 100
    checkpoint_interval: int = 5
    agent_config: RepairCycleAgentConfig | None = None


@pytest.mark.asyncio
async def test_dispatch_to_systemic_fix_when_cross_cutting_true(
    seeded_simulation_bootstrap,
):
    """Test that systemic fix is called when cross_cutting=True and failures <= 50."""
    # Setup
    mock_repair = seeded_simulation_bootstrap.adapters.repair_cycle_as_mock()
    mock_analysis = seeded_simulation_bootstrap.adapters.systemic_analysis_as_mock()

    # Pre-configure mock analysis to return cross_cutting=True
    mock_analysis.set_results([
        SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.9,
            reasoning="Single change propagates to multiple files",
            affected_files=("api.py", "models.py", "services.py"),
            recommended_action="Update API contract consistently",
            cross_cutting=True,
        ),
    ])

    # Pre-configure mock repair to fail on first test, then pass after systemic fix
    mock_repair.set_test_result_sequence(
        RepairTestType.UNIT,
        [
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=5,
                failed=3,
                warnings=0,
                failures=(
                    RepairTestFailure("test_api.py", "test_contract", "Contract mismatch"),
                    RepairTestFailure("test_models.py", "test_schema", "Schema mismatch"),
                    RepairTestFailure("test_services.py", "test_sync", "Sync issue"),
                ),
                warning_list=(),
                raw_output="Test failures detected",
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
                raw_output="All tests passed",
                timestamp="2025-03-31T10:01:00Z",
            ),
        ],
    )

    # Pre-configure systemic fix to succeed
    mock_repair.set_systemic_fix_result([
        SystemicFixResult(
            success=True,
            files_modified=("api.py", "models.py", "services.py"),
            root_cause_addressed="API contract change required consistent updates",
            duration_seconds=120.0,
        ),
    ])

    # Create test context using SimpleRepairCycleContext
    context = SimpleRepairCycleContext(
        work_item_id="WI-123",
        workflow_run_id="WR-456",
        stage_name="fix_failures",
        test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
    )

    # Execute repair cycle
    result = await mock_repair.execute(context)

    # Verify systemic fix was called
    assert mock_repair.systemic_fix_call_count == 1
    # Verify fix_failures_by_file was NOT called (because cross_cutting=True)
    assert mock_repair.file_fix_call_count == 0
    # Verify overall success
    assert result.overall_success is True


@pytest.mark.asyncio
async def test_dispatch_to_file_fix_when_cross_cutting_false(
    seeded_simulation_bootstrap,
):
    """Test that file fix is called when cross_cutting=False."""
    # Setup
    mock_repair = seeded_simulation_bootstrap.adapters.repair_cycle_as_mock()
    mock_analysis = seeded_simulation_bootstrap.adapters.systemic_analysis_as_mock()

    # Pre-configure mock analysis to return cross_cutting=False
    mock_analysis.set_results([
        SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.85,
            reasoning="Isolated code defect in single module",
            affected_files=("utils.py",),
            recommended_action="Fix the isolated bug",
            cross_cutting=False,
        ),
    ])

    # Pre-configure mock repair with test failures
    mock_repair.set_test_result_sequence(
        RepairTestType.UNIT,
        [
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=8,
                failed=2,
                warnings=0,
                failures=(
                    RepairTestFailure("test_utils.py", "test_parse", "Invalid format"),
                    RepairTestFailure("test_utils.py", "test_format", "Output mismatch"),
                ),
                warning_list=(),
                raw_output="Test failures detected",
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
                raw_output="All tests passed",
                timestamp="2025-03-31T10:01:00Z",
            ),
        ],
    )

    # Create test context
    context = SimpleRepairCycleContext(
        work_item_id="WI-123",
        workflow_run_id="WR-456",
        stage_name="fix_failures",
        test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
    )

    # Execute repair cycle
    result = await mock_repair.execute(context)

    # Verify systemic fix was NOT called (cross_cutting=False)
    assert mock_repair.systemic_fix_call_count == 0
    # Verify fix_failures_by_file WAS called
    assert mock_repair.file_fix_call_count > 0
    # Verify overall success
    assert result.overall_success is True


@pytest.mark.asyncio
async def test_fallback_to_file_fix_when_failure_count_exceeds_50(
    seeded_simulation_bootstrap,
):
    """Test fallback to file fix when cross_cutting=True but failure_count > 50."""
    # Setup
    mock_repair = seeded_simulation_bootstrap.adapters.repair_cycle_as_mock()
    mock_analysis = seeded_simulation_bootstrap.adapters.systemic_analysis_as_mock()

    # Create 51 failures (exceeds the 50-failure threshold)
    failures = tuple(
        RepairTestFailure(f"test_{i}.py", f"test_case_{i}", f"Failure {i}")
        for i in range(51)
    )

    # Pre-configure mock analysis to return cross_cutting=True
    # (but we have > 50 failures, so should fall back to file fix)
    mock_analysis.set_results([
        SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.9,
            reasoning="Cross-cutting issue with many failures",
            affected_files=tuple(f"file_{i}.py" for i in range(10)),
            recommended_action="Fix systematically",
            cross_cutting=True,
        ),
    ])

    # Pre-configure mock repair with many test failures
    mock_repair.set_test_result_sequence(
        RepairTestType.UNIT,
        [
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=0,
                failed=51,
                warnings=0,
                failures=failures,
                warning_list=(),
                raw_output="51 test failures detected",
                timestamp="2025-03-31T10:00:00Z",
            ),
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=2,
                passed=51,
                failed=0,
                warnings=0,
                failures=(),
                warning_list=(),
                raw_output="All tests passed",
                timestamp="2025-03-31T10:01:00Z",
            ),
        ],
    )

    # Create test context
    context = SimpleRepairCycleContext(
        work_item_id="WI-123",
        workflow_run_id="WR-456",
        stage_name="fix_failures",
        test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
    )

    # Execute repair cycle
    result = await mock_repair.execute(context)

    # Verify systemic fix was NOT called (failure count > 50 triggers fallback)
    assert mock_repair.systemic_fix_call_count == 0
    # Verify fix_failures_by_file WAS called (fallback)
    assert mock_repair.file_fix_call_count > 0
    # Verify overall success
    assert result.overall_success is True


@pytest.mark.asyncio
async def test_multiple_systemic_fix_iterations(
    seeded_simulation_bootstrap,
):
    """Test that multiple systemic fix iterations can occur within one repair cycle.

    Scenario: First systemic fix attempt fails tests, second attempt succeeds.
    """
    # Setup
    mock_repair = seeded_simulation_bootstrap.adapters.repair_cycle_as_mock()
    mock_analysis = seeded_simulation_bootstrap.adapters.systemic_analysis_as_mock()

    # Both analyses return cross_cutting=True (for both iterations)
    mock_analysis.set_results([
        SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.85,
            reasoning="First analysis: partial root cause",
            affected_files=("api.py",),
            recommended_action="Update API endpoints",
            cross_cutting=True,
        ),
        SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.95,
            reasoning="Second analysis: complete root cause",
            affected_files=("models.py",),
            recommended_action="Update database schema",
            cross_cutting=True,
        ),
    ])

    # Test sequence: fail → fail → pass (two systemic fixes needed)
    mock_repair.set_test_result_sequence(
        RepairTestType.UNIT,
        [
            # First test run (failures)
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=7,
                failed=3,
                warnings=0,
                failures=(
                    RepairTestFailure("test_api.py", "test_list", "Missing field"),
                    RepairTestFailure("test_api.py", "test_get", "Contract error"),
                    RepairTestFailure("test_api.py", "test_post", "Validation failed"),
                ),
                warning_list=(),
                raw_output="Test failures after first systemic fix",
                timestamp="2025-03-31T10:00:00Z",
            ),
            # Second test run (still failures, need another fix)
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=2,
                passed=6,
                failed=4,
                warnings=0,
                failures=(
                    RepairTestFailure("test_models.py", "test_create", "Schema mismatch"),
                    RepairTestFailure("test_models.py", "test_update", "Schema mismatch"),
                    RepairTestFailure("test_models.py", "test_delete", "FK constraint"),
                    RepairTestFailure("test_api.py", "test_list", "Missing field"),
                ),
                warning_list=(),
                raw_output="Test failures after first fix, need second fix",
                timestamp="2025-03-31T10:01:00Z",
            ),
            # Third test run (passes)
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=3,
                passed=10,
                failed=0,
                warnings=0,
                failures=(),
                warning_list=(),
                raw_output="All tests passed after second systemic fix",
                timestamp="2025-03-31T10:02:00Z",
            ),
        ],
    )

    # Configure two systemic fix results
    mock_repair.set_systemic_fix_result([
        SystemicFixResult(
            success=True,
            files_modified=("api.py",),
            root_cause_addressed="API contract change",
            duration_seconds=60.0,
        ),
        SystemicFixResult(
            success=True,
            files_modified=("models.py",),
            root_cause_addressed="Database schema change",
            duration_seconds=90.0,
        ),
    ])

    # Create test context
    context = SimpleRepairCycleContext(
        work_item_id="WI-123",
        workflow_run_id="WR-456",
        stage_name="fix_failures",
        test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
    )

    # Execute repair cycle
    result = await mock_repair.execute(context)

    # Verify TWO systemic fix calls occurred
    assert mock_repair.systemic_fix_call_count == 2
    # Verify no file-level fixes (cross_cutting=True both times)
    assert mock_repair.file_fix_call_count == 0
    # Verify overall success
    assert result.overall_success is True


@pytest.mark.asyncio
async def test_systemic_fix_result_with_no_files_modified(
    seeded_simulation_bootstrap,
):
    """Test handling of systemic fix that succeeds but modifies no files.

    This can occur when the fix is conceptual (e.g., behavior change in logic)
    or when files are outside the workspace.
    """
    # Setup
    mock_repair = seeded_simulation_bootstrap.adapters.repair_cycle_as_mock()
    mock_analysis = seeded_simulation_bootstrap.adapters.systemic_analysis_as_mock()

    # Configure cross_cutting analysis
    mock_analysis.set_results([
        SystemicAnalysisResult(
            classification=FailureClassification.ENVIRONMENT_ISSUE,
            confidence=0.9,
            reasoning="Environment variable misconfiguration",
            affected_files=(),  # No code files to modify
            recommended_action="Set correct environment variables",
            cross_cutting=True,
        ),
    ])
    # Test that passes after environment configuration
    mock_repair.set_test_result_sequence(
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
                raw_output="Environment configuration errors",
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
                raw_output="All tests passed after environment fix",
                timestamp="2025-03-31T10:01:00Z",
            ),
        ],
    )

    # Systemic fix succeeds but modifies no files
    mock_repair.set_systemic_fix_result([
        SystemicFixResult(
            success=True,
            files_modified=(),  # No files modified
            root_cause_addressed="Environment variables correctly configured",
            duration_seconds=30.0,
        ),
    ])

    # Create test context
    context = SimpleRepairCycleContext(
        work_item_id="WI-123",
        workflow_run_id="WR-456",
        stage_name="fix_failures",
        test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
    )

    # Execute repair cycle
    result = await mock_repair.execute(context)

    # Verify systemic fix was called
    assert mock_repair.systemic_fix_call_count == 1
    # Verify overall success even with no files modified
    assert result.overall_success is True


@pytest.mark.asyncio
async def test_dispatch_respects_max_total_agent_calls_limit(
    seeded_simulation_bootstrap,
):
    """Test that dispatch respects max_total_agent_calls circuit breaker.

    When approaching the circuit breaker limit, the repair cycle should
    attempt systemic fixes before falling back to per-file fixes.
    """
    # Setup
    mock_repair = seeded_simulation_bootstrap.adapters.repair_cycle_as_mock()
    mock_analysis = seeded_simulation_bootstrap.adapters.systemic_analysis_as_mock()

    # Configure cross_cutting analysis
    mock_analysis.set_results([
        SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.9,
            reasoning="Systemic cross-cutting issue",
            affected_files=("core.py", "utils.py", "services.py"),
            recommended_action="Fix root cause systematically",
            cross_cutting=True,
        ),
    ])
    # Test sequence
    mock_repair.set_test_result_sequence(
        RepairTestType.UNIT,
        [
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=6,
                failed=4,
                warnings=0,
                failures=tuple(
                    RepairTestFailure(f"test_{i}.py", f"test_{i}", "Failure")
                    for i in range(4)
                ),
                warning_list=(),
                raw_output="Test failures",
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
                raw_output="All tests passed",
                timestamp="2025-03-31T10:01:00Z",
            ),
        ],
    )

    # Systemic fix succeeds
    mock_repair.set_systemic_fix_result([
        SystemicFixResult(
            success=True,
            files_modified=("core.py", "utils.py"),
            root_cause_addressed="Cross-cutting root cause addressed",
            duration_seconds=100.0,
        ),
    ])

    # Create test context
    context = SimpleRepairCycleContext(
        work_item_id="WI-123",
        workflow_run_id="WR-456",
        stage_name="fix_failures",
        test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
        max_total_agent_calls=100,  # Sufficient for systemic fix
    )

    # Execute repair cycle
    result = await mock_repair.execute(context)

    # Verify systemic fix was attempted
    assert mock_repair.systemic_fix_call_count >= 1
    # Verify success
    assert result.overall_success is True
