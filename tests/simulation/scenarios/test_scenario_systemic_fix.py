"""Simulation Scenario: Systemic Fix Flow (Test-Analyze-Fix-Validate).

Tests the complete systemic fix workflow:
1. Tests fail with multiple failures
2. Systemic analysis classifies as cross-cutting root cause
3. Systemic fix is applied to address root cause
4. Tests are re-run and pass

Comprehensive scenarios cover:
1. Happy path: systemic fix immediately resolves all failures
2. Multiple iterations: systemic fix fails, fallback to file-level fixes
3. Cross-cutting analysis with correct dispatch
4. Non-cross-cutting analysis dispatches to per-file fixes
5. Failure count > 50 triggers fallback despite cross_cutting=True
6. Full event emission and audit trail
"""

import pytest

from codetoreum.adapters.testing.mock_llm_adapter import MockLLMAdapter
from codetoreum.adapters.testing.mock_repair_cycle_adapter import MockRepairCycleAdapter
from codetoreum.adapters.testing.mock_systemic_analysis_adapter import (
    MockSystemicAnalysisAdapter,
)
from codetoreum.domain.events import (
    SystemicAnalysisCompletedEvent,
    SystemicFixCompletedEvent,
    SystemicFixStartedEvent,
)
from codetoreum.domain.repair_cycle_types import (
    AnalysisContext,
    FailureClassification,
    RepairCycleStageConfig,
    RepairTestFailure,
    RepairTestResult,
    RepairTestRunConfig,
    RepairTestType,
    SystemicAnalysisResult,
    SystemicFixResult,
)
from codetoreum.infrastructure.simulation.bootstrap import SimulationApplicationBootstrap
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig
from codetoreum.infrastructure.simulation.simulation_runner import SimulationRunner


def create_config(scenario_name: str = "scenario_systemic_fix") -> SimulationConfig:
    """Create configuration for systemic fix scenario."""
    config = SimulationConfig.create_fast_config(
        scenario_name=scenario_name,
        speed_multiplier=100.0,
    )
    config.scenario_description = (
        "Systemic fix test-analyze-fix-validate loop with cross-cutting "
        "root cause analysis and conditional dispatch"
    )
    return config


@pytest.mark.asyncio
async def test_scenario_systemic_fix_happy_path(
    simulation_bootstrap: SimulationApplicationBootstrap,
):
    """Test systemic fix with immediate success (cross-cutting root cause).

    Workflow:
    1. Tests fail with cross-cutting issue
    2. Analysis correctly identifies cross_cutting=True
    3. Systemic fix immediately resolves all failures
    4. Retest passes
    """
    # Setup adapters
    mock_repair = simulation_bootstrap.adapters.repair_cycle_as_mock()
    mock_analysis = simulation_bootstrap.adapters.systemic_analysis_as_mock()
    event_store = simulation_bootstrap.adapters.event_store_as_in_memory()

    # Configure systemic analysis to report cross-cutting issue
    mock_analysis._results = [
        SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.95,
            reasoning="API contract change propagates through multiple modules",
            affected_files=("src/api.py", "src/models.py", "src/services.py"),
            recommended_action="Update API contract consistently across modules",
            cross_cutting=True,
        ),
    ]

    # Configure test failures and recovery
    mock_repair.set_test_result_sequence(
        RepairTestType.UNIT,
        [
        # Initial test run: failures
        RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=7,
            failed=3,
            warnings=0,
            failures=(
                RepairTestFailure("test_api.py", "test_contract_v2", "API mismatch"),
                RepairTestFailure("test_models.py", "test_schema", "Schema mismatch"),
                RepairTestFailure("test_services.py", "test_sync", "Data sync issue"),
            ),
            warning_list=(),
            raw_output="Contract mismatch across modules",
            timestamp="2025-03-31T10:00:00Z",
        ),
        # After systemic fix: all pass
        RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=2,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="All tests passed after systemic fix",
            timestamp="2025-03-31T10:01:00Z",
        ),
    ])

    # Configure systemic fix to succeed
    mock_repair.set_systemic_fix_result([
        SystemicFixResult(
            success=True,
            files_modified=("src/api.py", "src/models.py", "src/services.py"),
            root_cause_addressed="API contract updated consistently across all modules",
            duration_seconds=120.0,
        ),
    ])

    # Execute repair cycle
    context = AnalysisContext(
        work_item_id="WI-456",
        iteration=1,
        workflow_run_id="WR-789",
    )

    config = RepairCycleStageConfig(
        name="fix_failures",
        test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
    )

    result = await mock_repair.execute(context, config)

    # Verify outcomes
    assert result.overall_success is True
    assert mock_repair.systemic_fix_call_count == 1
    assert mock_repair.file_fix_call_count == 0

    # Verify events were emitted
    systemic_fix_started = event_store.find_events_by_type(
        "repair_cycle.systemic_fix_started"
    )
    systemic_fix_completed = event_store.find_events_by_type(
        "repair_cycle.systemic_fix_completed"
    )

    assert len(systemic_fix_started) >= 1
    assert len(systemic_fix_completed) >= 1


@pytest.mark.asyncio
async def test_scenario_systemic_fix_non_cross_cutting_dispatches_to_files(
    simulation_bootstrap: SimulationApplicationBootstrap,
):
    """Test non-cross-cutting analysis dispatches to per-file fixes.

    Workflow:
    1. Tests fail with isolated issue
    2. Analysis identifies cross_cutting=False
    3. Per-file fix is applied
    4. Retest passes
    """
    # Setup adapters
    mock_repair = simulation_bootstrap.adapters.repair_cycle_as_mock()
    mock_analysis = simulation_bootstrap.adapters.systemic_analysis_as_mock()

    # Configure systemic analysis to report isolated issue
    mock_analysis._results = [
        SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.9,
            reasoning="Isolated bug in single module",
            affected_files=("src/utils.py",),
            recommended_action="Fix the isolated parsing bug",
            cross_cutting=False,
        ),
    ]

    # Configure test failures and recovery
    mock_repair.set_test_result_sequence(
        RepairTestType.UNIT,
        [
        # Initial test run: failures
        RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=8,
            failed=2,
            warnings=0,
            failures=(
                RepairTestFailure("test_utils.py", "test_parse", "ValueError"),
                RepairTestFailure("test_utils.py", "test_format", "AssertionError"),
            ),
            warning_list=(),
            raw_output="Parsing errors in utils module",
            timestamp="2025-03-31T10:00:00Z",
        ),
        # After file-level fix: all pass
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
    ])

    # Execute repair cycle
    context = AnalysisContext(
        work_item_id="WI-456",
        iteration=1,
        workflow_run_id="WR-789",
    )

    config = RepairCycleStageConfig(
        name="fix_failures",
        test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
    )

    result = await mock_repair.execute(context, config)

    # Verify outcomes
    assert result.overall_success is True
    # Should NOT call systemic fix (cross_cutting=False)
    assert mock_repair.systemic_fix_call_count == 0
    # Should call file-level fix instead
    assert mock_repair.file_fix_call_count > 0


@pytest.mark.asyncio
async def test_scenario_systemic_fix_multiple_iterations(
    simulation_bootstrap: SimulationApplicationBootstrap,
):
    """Test systemic fix with multiple iterations (second attempt succeeds).

    Workflow:
    1. First test run fails
    2. First systemic fix fails, retesting still fails
    3. Second systemic fix succeeds
    4. Final test run passes
    """
    # Setup adapters
    mock_repair = simulation_bootstrap.adapters.repair_cycle_as_mock()
    mock_analysis = simulation_bootstrap.adapters.systemic_analysis_as_mock()

    # Configure two systemic analyses (one for each iteration)
    mock_analysis._results = [
        SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.7,
            reasoning="Initial analysis: partial root cause",
            affected_files=("src/api.py",),
            recommended_action="Update API layer",
            cross_cutting=True,
        ),
        SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.95,
            reasoning="Second analysis: complete root cause",
            affected_files=("src/models.py", "src/database.py"),
            recommended_action="Update models and database layer",
            cross_cutting=True,
        ),
    ]

    # Configure test sequence: fail → fail → pass
    mock_repair.set_test_result_sequence(
        RepairTestType.UNIT,
        [
        # Initial failures
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
            raw_output="Initial failures",
            timestamp="2025-03-31T10:00:00Z",
        ),
        # Still failing after first systemic fix
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
            raw_output="Still failing after first fix",
            timestamp="2025-03-31T10:01:00Z",
        ),
        # Passing after second systemic fix
        RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=3,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="All tests passed",
            timestamp="2025-03-31T10:02:00Z",
        ),
    ])

    # Configure two systemic fix results
    mock_repair.set_systemic_fix_result([
        SystemicFixResult(
            success=True,
            files_modified=("src/api.py",),
            root_cause_addressed="API layer updated",
            duration_seconds=60.0,
        ),
        SystemicFixResult(
            success=True,
            files_modified=("src/models.py", "src/database.py"),
            root_cause_addressed="Models and database schema updated",
            duration_seconds=90.0,
        ),
    ])

    # Execute repair cycle
    context = AnalysisContext(
        work_item_id="WI-456",
        iteration=1,
        workflow_run_id="WR-789",
    )

    config = RepairCycleStageConfig(
        name="fix_failures",
        test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
    )

    result = await mock_repair.execute(context, config)

    # Verify outcomes
    assert result.overall_success is True
    # Should call systemic fix twice
    assert mock_repair.systemic_fix_call_count == 2
    # Should not call file-level fix (both are cross_cutting)
    assert mock_repair.file_fix_call_count == 0


@pytest.mark.asyncio
async def test_scenario_systemic_fix_large_failure_count_fallback(
    simulation_bootstrap: SimulationApplicationBootstrap,
):
    """Test fallback to file fixes when failure count exceeds threshold.

    Even though analysis reports cross_cutting=True,
    failure count > 50 triggers fallback to per-file fixes.
    """
    # Setup adapters
    mock_repair = simulation_bootstrap.adapters.repair_cycle_as_mock()
    mock_analysis = simulation_bootstrap.adapters.systemic_analysis_as_mock()

    # Create 60 failures (exceeds 50-failure threshold)
    failures = tuple(
        RepairTestFailure(f"test_{i}.py", f"test_{i}", f"Failure {i}")
        for i in range(60)
    )

    # Configure systemic analysis with cross_cutting=True
    # (but we have > 50 failures, so should fall back anyway)
    mock_analysis._results = [
        SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.9,
            reasoning="Cross-cutting issue with many failures",
            affected_files=tuple(f"file_{i}.py" for i in range(10)),
            recommended_action="Fix systematically",
            cross_cutting=True,
        ),
    ]

    # Configure test sequence
    mock_repair.set_test_result_sequence(
        RepairTestType.UNIT,
        [
        # Initial: many failures
        RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=0,
            failed=60,
            warnings=0,
            failures=failures,
            warning_list=(),
            raw_output="60 failures detected",
            timestamp="2025-03-31T10:00:00Z",
        ),
        # After per-file fixes: pass
        RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=2,
            passed=60,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="All passed after file fixes",
            timestamp="2025-03-31T10:01:00Z",
        ),
    ])

    # Execute repair cycle
    context = AnalysisContext(
        work_item_id="WI-456",
        iteration=1,
        workflow_run_id="WR-789",
    )

    config = RepairCycleStageConfig(
        name="fix_failures",
        test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
    )

    result = await mock_repair.execute(context, config)

    # Verify outcomes
    assert result.overall_success is True
    # Should NOT call systemic fix (failure count > 50 triggers fallback)
    assert mock_repair.systemic_fix_call_count == 0
    # Should call file-level fix instead
    assert mock_repair.file_fix_call_count > 0


@pytest.mark.asyncio
async def test_scenario_systemic_fix_with_event_emission(
    simulation_bootstrap: SimulationApplicationBootstrap,
):
    """Test that systemic fix emits proper events to event store.

    Verifies audit trail: SystemicAnalysisCompletedEvent → SystemicFixStartedEvent →
    SystemicFixCompletedEvent.
    """
    # Setup adapters
    mock_repair = simulation_bootstrap.adapters.repair_cycle_as_mock()
    mock_analysis = simulation_bootstrap.adapters.systemic_analysis_as_mock()
    event_store = simulation_bootstrap.adapters.event_store_as_in_memory()

    # Configure systemic analysis
    mock_analysis._results = [
        SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.9,
            reasoning="Cross-cutting code defect",
            affected_files=("src/api.py", "src/models.py"),
            recommended_action="Update contract",
            cross_cutting=True,
        ),
    ]

    # Configure test sequence
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
                RepairTestFailure("test_api.py", "test_1", "Error"),
                RepairTestFailure("test_models.py", "test_2", "Error"),
            ),
            warning_list=(),
            raw_output="Failures",
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

    # Configure systemic fix
    mock_repair.set_systemic_fix_result([
        SystemicFixResult(
            success=True,
            files_modified=("src/api.py", "src/models.py"),
            root_cause_addressed="Contract updated across modules",
            duration_seconds=120.0,
        ),
    ])

    # Execute repair cycle
    context = AnalysisContext(
        work_item_id="WI-456",
        iteration=1,
        workflow_run_id="WR-789",
    )

    config = RepairCycleStageConfig(
        name="fix_failures",
        test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
    )

    result = await mock_repair.execute(context, config)

    # Verify overall success
    assert result.overall_success is True

    # Verify events in event store
    analysis_events = event_store.find_events_by_type(
        "repair_cycle.systemic_analysis_completed"
    )
    fix_started = event_store.find_events_by_type("repair_cycle.systemic_fix_started")
    fix_completed = event_store.find_events_by_type(
        "repair_cycle.systemic_fix_completed"
    )

    # Should have events
    assert len(analysis_events) >= 1
    assert len(fix_started) >= 1
    assert len(fix_completed) >= 1

    # Verify event properties
    if fix_completed:
        completed_event = fix_completed[0]
        assert completed_event.data["success"] is True
