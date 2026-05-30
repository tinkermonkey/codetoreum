"""Integration tests for systemic fix dispatch logic in repair cycle.

Tests verify the conditional dispatch between fix_failures_systemically() and
fix_failures_by_file() based on the cross_cutting field from systemic analysis.

Verifies:
- When cross_cutting=True: dispatches to fix_failures_systemically()
- When cross_cutting=False: dispatches to fix_failures_by_file()
- Multiple systemic fix iterations within a single repair cycle
- Proper state transitions and event emission for both branches
- Failure counts are correctly tracked through dispatch

NOTE: These tests use MockRepairCycleAdapter with mocked sub-dependencies.
The production adapter's dispatch logic is tested separately in unit tests
(tests/unit/adapters/secondary/test_production_repair_cycle_adapter.py).
These integration tests verify the mock adapter behavior and the overall dispatch
routing when integrated with other mocked services.
"""

from dataclasses import dataclass

import pytest

from codetoreum.adapters.testing.mock_repair_cycle_adapter import MockRepairCycleAdapter
from codetoreum.domain.repair_cycle_types import (
    AnalysisContext,
    EnvironmentRepairConfig,
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
    systemic_fix_failure_ceiling: int = 50
    iteration: int = 1
    prior_fix_attempts: tuple[str, ...] = ()
    prior_classifications: tuple = ()

    def __post_init__(self) -> None:
        """Initialize stage_config after dataclass initialization."""
        object.__setattr__(
            self,
            "stage_config",
            RepairCycleStageConfig(
                name=self.stage_name,
                test_configs=self.test_configs,
                agent_name=self.agent_name,
                max_total_agent_calls=self.max_total_agent_calls,
                checkpoint_interval=self.checkpoint_interval,
                agent_config=self.agent_config,
                systemic_fix_failure_ceiling=self.systemic_fix_failure_ceiling,
                environment_repair_config=EnvironmentRepairConfig(),
            ),
        )


@pytest.mark.asyncio
async def test_dispatch_to_systemic_fix_when_cross_cutting_true(
    seeded_simulation_bootstrap,
):
    """Test that systemic fix is called when cross_cutting=True and failures <= 50."""
    # Setup
    mock_repair = seeded_simulation_bootstrap.adapters.repair_cycle_as_mock()
    mock_analysis = seeded_simulation_bootstrap.adapters.systemic_analysis_as_mock()

    # Pre-configure mock analysis to return cross_cutting=True
    mock_analysis.set_results(
        [
            SystemicAnalysisResult(
                classification=FailureClassification.CODE_DEFECT,
                confidence=0.9,
                reasoning="Single change propagates to multiple files",
                affected_files=("api.py", "models.py", "services.py"),
                recommended_action="Update API contract consistently",
                cross_cutting=True,
            ),
        ]
    )

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
    mock_repair.set_systemic_fix_result(
        [
            SystemicFixResult(
                success=True,
                files_modified=("api.py", "models.py", "services.py"),
                root_cause_addressed="API contract change required consistent updates",
                duration_seconds=120.0,
            ),
        ]
    )

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
    mock_analysis.set_results(
        [
            SystemicAnalysisResult(
                classification=FailureClassification.CODE_DEFECT,
                confidence=0.85,
                reasoning="Isolated code defect in single module",
                affected_files=("utils.py",),
                recommended_action="Fix the isolated bug",
                cross_cutting=False,
            ),
        ]
    )

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
@pytest.mark.timeout(120)  # passes standalone in ~62s; needs headroom over suite-default 60s
async def test_systemic_fix_with_many_failures(
    seeded_simulation_bootstrap,
):
    """Test that failure count ceiling (50) is enforced for systemic fix.

    When failures exceed the ceiling, dispatcher falls back to file-level fixes
    even if cross_cutting=True. This prevents overwhelming the systemic fix agent.
    """
    # Setup
    mock_repair = seeded_simulation_bootstrap.adapters.repair_cycle_as_mock()
    mock_analysis = seeded_simulation_bootstrap.adapters.systemic_analysis_as_mock()

    # Create 51 failures (exceeds ceiling of 50)
    failures = tuple(RepairTestFailure(f"test_{i}.py", f"test_case_{i}", f"Failure {i}") for i in range(51))

    # Pre-configure mock analysis to return cross_cutting=True
    mock_analysis.set_results(
        [
            SystemicAnalysisResult(
                classification=FailureClassification.CODE_DEFECT,
                confidence=0.9,
                reasoning="Cross-cutting issue affecting many files",
                affected_files=tuple(f"file_{i}.py" for i in range(10)),
                recommended_action="Fix systematically",
                cross_cutting=True,
            ),
        ]
    )

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

    # Verify systemic fix was NOT called (exceeded ceiling of 50)
    assert (
        mock_repair.systemic_fix_call_count == 0
    ), "Failure count (51) exceeds ceiling (50), should fallback to file-level fixes"
    # Verify file fix WAS called (fallback behavior)
    assert mock_repair.file_fix_call_count > 0, "Should fallback to file-level fixes when failure count exceeds ceiling"
    # Verify overall success
    assert result.overall_success is True


@pytest.mark.asyncio
async def test_systemic_fix_at_failure_ceiling(
    seeded_simulation_bootstrap,
):
    """Test that systemic fix IS called when failures are at or below ceiling (50).

    Validates boundary condition: exactly 50 failures should dispatch to systemic fix.
    """
    # Setup
    mock_repair = seeded_simulation_bootstrap.adapters.repair_cycle_as_mock()
    mock_analysis = seeded_simulation_bootstrap.adapters.systemic_analysis_as_mock()

    # Create exactly 50 failures (at ceiling)
    failures = tuple(RepairTestFailure(f"test_{i}.py", f"test_case_{i}", f"Failure {i}") for i in range(50))

    # Pre-configure mock analysis to return cross_cutting=True
    mock_analysis.set_results(
        [
            SystemicAnalysisResult(
                classification=FailureClassification.CODE_DEFECT,
                confidence=0.9,
                reasoning="Cross-cutting issue affecting many files",
                affected_files=tuple(f"file_{i}.py" for i in range(10)),
                recommended_action="Fix systematically",
                cross_cutting=True,
            ),
        ]
    )

    # Pre-configure mock repair with 50 test failures
    mock_repair.set_test_result_sequence(
        RepairTestType.UNIT,
        [
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=0,
                failed=50,
                warnings=0,
                failures=failures,
                warning_list=(),
                raw_output="50 test failures detected",
                timestamp="2025-03-31T10:00:00Z",
            ),
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=2,
                passed=50,
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
    mock_repair.set_systemic_fix_result(
        [
            SystemicFixResult(
                success=True,
                files_modified=("api.py", "models.py", "services.py"),
                root_cause_addressed="Fixed cross-cutting issue",
                duration_seconds=120.0,
            ),
        ]
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

    # Verify systemic fix WAS called (at ceiling boundary)
    assert mock_repair.systemic_fix_call_count == 1, "50 failures at ceiling should dispatch to systemic fix"
    # Verify file fix was NOT called (systemic fix used)
    assert mock_repair.file_fix_call_count == 0, "Should use systemic fix when at ceiling"
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
    mock_analysis.set_results(
        [
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
        ]
    )

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
    mock_repair.set_systemic_fix_result(
        [
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
        ]
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

    # Configure CODE_DEFECT + cross_cutting (routes to systemic fix)
    mock_analysis.set_results(
        [
            SystemicAnalysisResult(
                classification=FailureClassification.CODE_DEFECT,
                confidence=0.9,
                reasoning="Cross-cutting logic issue affecting multiple modules",
                affected_files=(),  # No code files to modify (conceptual fix)
                recommended_action="Update internal logic",
                cross_cutting=True,
            ),
        ]
    )
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
                failures=tuple(RepairTestFailure(f"test_{i}.py", f"test_{i}", "Logic error") for i in range(5)),
                warning_list=(),
                raw_output="Cross-cutting logic errors",
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
                raw_output="All tests passed after systemic fix",
                timestamp="2025-03-31T10:01:00Z",
            ),
        ],
    )

    # Systemic fix succeeds but modifies no files (conceptual fix)
    mock_repair.set_systemic_fix_result(
        [
            SystemicFixResult(
                success=True,
                files_modified=(),  # No files modified
                root_cause_addressed="Logic fixed through code generation (no file changes)",
                duration_seconds=30.0,
            ),
        ]
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

    # Verify systemic fix was called
    assert mock_repair.systemic_fix_call_count == 1
    # Verify overall success even with no files modified
    assert result.overall_success is True


@pytest.mark.asyncio
async def test_dispatch_systemic_fix_with_sufficient_budget(
    seeded_simulation_bootstrap,
):
    """Test that systemic fixes are attempted when budget is sufficient.

    This test verifies the dispatch logic routes to systemic fix when:
    1. Analysis classifies as cross_cutting=True
    2. max_total_agent_calls budget is sufficient

    NOTE: Testing that the circuit breaker PREVENTS fixes when limit is
    reached requires production adapter integration tests with actual call
    counting. The mock adapter does not track call budgets, so this test
    only verifies the dispatch occurs with sufficient budget.
    """
    # Setup
    mock_repair = seeded_simulation_bootstrap.adapters.repair_cycle_as_mock()
    mock_analysis = seeded_simulation_bootstrap.adapters.systemic_analysis_as_mock()

    # Configure cross_cutting analysis
    mock_analysis.set_results(
        [
            SystemicAnalysisResult(
                classification=FailureClassification.CODE_DEFECT,
                confidence=0.9,
                reasoning="Systemic cross-cutting issue",
                affected_files=("core.py", "utils.py", "services.py"),
                recommended_action="Fix root cause systematically",
                cross_cutting=True,
            ),
        ]
    )
    # Test sequence: fail → pass
    mock_repair.set_test_result_sequence(
        RepairTestType.UNIT,
        [
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=6,
                failed=4,
                warnings=0,
                failures=tuple(RepairTestFailure(f"test_{i}.py", f"test_{i}", "Failure") for i in range(4)),
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
    mock_repair.set_systemic_fix_result(
        [
            SystemicFixResult(
                success=True,
                files_modified=("core.py", "utils.py"),
                root_cause_addressed="Cross-cutting root cause addressed",
                duration_seconds=100.0,
            ),
        ]
    )

    # Create test context with sufficient budget
    context = SimpleRepairCycleContext(
        work_item_id="WI-123",
        workflow_run_id="WR-456",
        stage_name="fix_failures",
        test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT),),
        max_total_agent_calls=100,  # Sufficient for systemic fix
    )

    # Execute repair cycle
    result = await mock_repair.execute(context)

    # Verify systemic fix was attempted (dispatch to systemic path works)
    assert mock_repair.systemic_fix_call_count == 1, "When cross_cutting=True, systemic fix should be attempted"
    # Verify success
    assert result.overall_success is True


@pytest.mark.asyncio
async def test_dispatch_transient_failure_without_escalation(
    seeded_simulation_bootstrap,
):
    """Test TRANSIENT_FAILURE dispatch when consecutive count <= threshold."""
    # Setup
    mock_repair = seeded_simulation_bootstrap.adapters.repair_cycle_as_mock()
    mock_analysis = seeded_simulation_bootstrap.adapters.systemic_analysis_as_mock()

    # Configure transient failure classification (first occurrence)
    mock_analysis.set_results(
        [
            SystemicAnalysisResult(
                classification=FailureClassification.TRANSIENT_FAILURE,
                confidence=0.95,
                reasoning="Intermittent network timeout in external service call",
                affected_files=("client.py",),
                recommended_action="Retry without code changes",
                cross_cutting=False,
            ),
        ]
    )

    # Test sequence: fail on iteration 1, pass on iteration 2 (retry succeeds)
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
                    RepairTestFailure("test_client.py", "test_fetch", "Timeout"),
                    RepairTestFailure("test_client.py", "test_stream", "Connection refused"),
                ),
                warning_list=(),
                raw_output="Network timeout failures",
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
                raw_output="All tests passed on retry",
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

    # Verify no fix was applied (just retry)
    assert mock_repair.systemic_fix_call_count == 0
    assert mock_repair.file_fix_call_count == 0
    # Verify success after retry
    assert result.overall_success is True


@pytest.mark.asyncio
async def test_dispatch_transient_failure_with_retries_only(
    seeded_simulation_bootstrap,
):
    """Test TRANSIENT_FAILURE behavior with retries (no escalation in mock).

    NOTE: Escalation behavior (TRANSIENT_FAILURE -> file-level fixes after max consecutive
    count) is implemented in the production adapter logic, NOT in the mock adapter. This test
    verifies that TRANSIENT_FAILURE classifications are retried without applying code fixes.

    The production adapter's escalation logic (consecutive_transient_failures > threshold)
    should be tested via production adapter unit tests or integration tests with production
    adapter initialization, not via mock adapter.

    This test documents the current mock behavior: TRANSIENT_FAILURE triggers retries only.
    """
    # Setup
    mock_repair = seeded_simulation_bootstrap.adapters.repair_cycle_as_mock()
    mock_analysis = seeded_simulation_bootstrap.adapters.systemic_analysis_as_mock()

    # Configure TRANSIENT classifications to verify retry behavior
    mock_analysis.set_results(
        [
            # All iterations classify as TRANSIENT
            SystemicAnalysisResult(
                classification=FailureClassification.TRANSIENT_FAILURE,
                confidence=0.9,
                reasoning="Transient network timeout",
                affected_files=("client.py",),
                recommended_action="Retry",
                cross_cutting=False,
            ),
            SystemicAnalysisResult(
                classification=FailureClassification.TRANSIENT_FAILURE,
                confidence=0.9,
                reasoning="Transient timeout again",
                affected_files=("client.py",),
                recommended_action="Retry",
                cross_cutting=False,
            ),
        ]
    )

    # Test sequence: fail → fail → pass (via retry success, not code fix)
    mock_repair.set_test_result_sequence(
        RepairTestType.UNIT,
        [
            # Iteration 1: First transient failure (retry only)
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=8,
                failed=2,
                warnings=0,
                failures=(
                    RepairTestFailure("test_client.py", "test_fetch", "Timeout"),
                    RepairTestFailure("test_client.py", "test_stream", "Connection reset"),
                ),
                warning_list=(),
                raw_output="Network timeout",
                timestamp="2025-03-31T10:00:00Z",
            ),
            # Iteration 2: Second transient failure (retry only)
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=2,
                passed=8,
                failed=2,
                warnings=0,
                failures=(
                    RepairTestFailure("test_client.py", "test_fetch", "Timeout"),
                    RepairTestFailure("test_client.py", "test_stream", "Connection reset"),
                ),
                warning_list=(),
                raw_output="Network timeout again",
                timestamp="2025-03-31T10:01:00Z",
            ),
            # Iteration 3: Transient failure resolved via retry
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=3,
                passed=10,
                failed=0,
                warnings=0,
                failures=(),
                warning_list=(),
                raw_output="All tests passed after retries",
                timestamp="2025-03-31T10:02:00Z",
            ),
        ],
    )

    # Create test context
    context = SimpleRepairCycleContext(
        work_item_id="WI-123",
        workflow_run_id="WR-456",
        stage_name="fix_failures",
        test_configs=(RepairTestRunConfig(test_type=RepairTestType.UNIT, max_iterations=5),),
    )

    # Execute repair cycle
    result = await mock_repair.execute(context)

    # Verify no systemic or file-level fixes were applied (pure retry behavior)
    assert mock_repair.systemic_fix_call_count == 0, "TRANSIENT_FAILURE should not trigger systemic fixes"
    assert (
        mock_repair.file_fix_call_count == 0
    ), "TRANSIENT_FAILURE should not trigger file-level fixes in mock (retries only)"

    # Verify success via retries
    assert result.overall_success is True, "Transient failures should resolve via retries"


@pytest.mark.asyncio
async def test_dispatch_dependency_issue(
    seeded_simulation_bootstrap,
):
    """Test DEPENDENCY_ISSUE dispatch applies systemic fixes."""
    # Setup
    mock_repair = seeded_simulation_bootstrap.adapters.repair_cycle_as_mock()
    mock_analysis = seeded_simulation_bootstrap.adapters.systemic_analysis_as_mock()

    # Configure dependency issue classification
    mock_analysis.set_results(
        [
            SystemicAnalysisResult(
                classification=FailureClassification.DEPENDENCY_ISSUE,
                confidence=0.92,
                reasoning="Transitive dependency version conflict: requests 2.25 incompatible with urllib3 1.24",
                affected_files=("requirements.txt", "setup.py"),
                recommended_action="Update dependency versions to compatible set",
                cross_cutting=False,
            ),
        ]
    )

    # Test sequence: fail on iteration 1, pass on iteration 2 (after dependency fix)
    mock_repair.set_test_result_sequence(
        RepairTestType.UNIT,
        [
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=6,
                failed=4,
                warnings=0,
                failures=(
                    RepairTestFailure("test_http.py", "test_get", "ImportError: no module urllib3"),
                    RepairTestFailure("test_http.py", "test_post", "AttributeError in requests"),
                    RepairTestFailure("test_http.py", "test_put", "ImportError: no module urllib3"),
                    RepairTestFailure("test_http.py", "test_delete", "AttributeError in requests"),
                ),
                warning_list=(),
                raw_output="Dependency version conflict",
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
                raw_output="All tests passed after dependency fix",
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

    # Verify fix_failures_systemically was NOT called (DEPENDENCY_ISSUE routes to apply_systemic_fixes, not fix_failures_systemically)
    assert (
        mock_repair.systemic_fix_call_count == 0
    ), "DEPENDENCY_ISSUE should route to apply_systemic_fixes(), not fix_failures_systemically()"
    # Verify file fix was NOT called (DEPENDENCY_ISSUE uses apply_systemic_fixes)
    assert mock_repair.file_fix_call_count == 0, "DEPENDENCY_ISSUE should not use file-level fixes"
    # Verify apply_systemic_fixes WAS called (positive path assertion)
    assert (
        mock_repair.apply_systemic_fixes_call_count == 1
    ), "apply_systemic_fixes() should be called once for DEPENDENCY_ISSUE"
    # Verify overall success
    assert result.overall_success is True
    # Verify tests completed
    assert len(result.test_results) > 0


@pytest.mark.asyncio
async def test_dispatch_configuration_issue(
    seeded_simulation_bootstrap,
):
    """Test CONFIGURATION_ISSUE dispatch applies systemic fixes."""
    # Setup
    mock_repair = seeded_simulation_bootstrap.adapters.repair_cycle_as_mock()
    mock_analysis = seeded_simulation_bootstrap.adapters.systemic_analysis_as_mock()

    # Configure configuration issue classification
    mock_analysis.set_results(
        [
            SystemicAnalysisResult(
                classification=FailureClassification.CONFIGURATION_ISSUE,
                confidence=0.88,
                reasoning="Database connection string malformed in config; missing credentials",
                affected_files=("config.yaml", ".env.example"),
                recommended_action="Update configuration files with correct connection string",
                cross_cutting=False,
            ),
        ]
    )

    # Test sequence: fail on iteration 1, pass on iteration 2 (after config fix)
    mock_repair.set_test_result_sequence(
        RepairTestType.UNIT,
        [
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=7,
                failed=3,
                warnings=0,
                failures=(
                    RepairTestFailure("test_db.py", "test_connect", "Connection refused: invalid URL"),
                    RepairTestFailure("test_db.py", "test_query", "Connection timeout"),
                    RepairTestFailure("test_db.py", "test_transaction", "Lost connection to database"),
                ),
                warning_list=(),
                raw_output="Database configuration errors",
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
                raw_output="All tests passed after configuration fix",
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

    # Verify fix_failures_systemically was NOT called (CONFIGURATION_ISSUE routes to apply_systemic_fixes, not fix_failures_systemically)
    assert (
        mock_repair.systemic_fix_call_count == 0
    ), "CONFIGURATION_ISSUE should route to apply_systemic_fixes(), not fix_failures_systemically()"
    # Verify file fix was NOT called (CONFIGURATION_ISSUE uses apply_systemic_fixes)
    assert mock_repair.file_fix_call_count == 0, "CONFIGURATION_ISSUE should not use file-level fixes"
    # Verify apply_systemic_fixes WAS called (positive path assertion)
    assert (
        mock_repair.apply_systemic_fixes_call_count == 1
    ), "apply_systemic_fixes() should be called once for CONFIGURATION_ISSUE"
    # Verify overall success
    assert result.overall_success is True
    # Verify tests completed
    assert len(result.test_results) > 0
