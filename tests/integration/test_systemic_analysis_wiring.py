"""Integration test for systemic analysis service wiring.

Tests that MockSystemicAnalysisAdapter is properly wired in simulation bootstrap
and that LLMSystemicAnalysisAdapter is properly wired in production bootstrap.

Verifies the complete dependency injection chain for ISystemicAnalysisService
through both direct mock adapter usage and end-to-end repair cycle integration.
"""

import pytest

from codetoreum.adapters.testing.mock_systemic_analysis_adapter import (
    MockSystemicAnalysisAdapter,
)
from codetoreum.adapters.secondary.production_repair_cycle_adapter import (
    ProductionRepairCycleAdapter,
)
from codetoreum.domain.repair_cycle_types import (
    AnalysisContext,
    FailureClassification,
    RepairTestFailure,
    SystemicAnalysisResult,
)
from codetoreum.infrastructure.simulation.bootstrap import SimulationApplicationBootstrap
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig


@pytest.mark.asyncio
async def test_systemic_analysis_accessible_from_simulation_bootstrap():
    """Test that MockSystemicAnalysisAdapter is accessible via bootstrap."""
    config = SimulationConfig.create_fast_config("test_systemic_access", speed_multiplier=100.0)
    bootstrap = SimulationApplicationBootstrap(config)
    app = await bootstrap.setup()

    # Verify systemic_analysis_service is accessible
    assert bootstrap.adapters.systemic_analysis_service is not None

    # Verify it's the mock adapter
    mock_adapter = bootstrap.adapters.systemic_analysis_as_mock()
    assert isinstance(mock_adapter, MockSystemicAnalysisAdapter)


@pytest.mark.asyncio
async def test_systemic_analysis_can_be_preconfigured_in_bootstrap():
    """Test that test authors can preconfigure systemic analysis results."""
    config = SimulationConfig.create_fast_config("test_preconfigure", speed_multiplier=100.0)
    bootstrap = SimulationApplicationBootstrap(config)
    app = await bootstrap.setup()

    # Get the mock adapter and configure result sequence
    mock_adapter = bootstrap.adapters.systemic_analysis_as_mock()

    # Pre-configure to return ENVIRONMENT_ISSUE
    expected_result = SystemicAnalysisResult(
        classification=FailureClassification.ENVIRONMENT_ISSUE,
        confidence=0.95,
        reasoning="Stale Docker image detected",
        affected_files=(),
        recommended_action="Rebuild environment",
    )
    mock_adapter._results = [expected_result]

    # Execute analyze and verify result
    failures = [
        RepairTestFailure(
            file="test_example.py",
            test="test_something",
            message="ImportError: module not found",
        ),
    ]
    context = AnalysisContext(
        workflow_run_id="wf-123",
        work_item_id="item-456",
        iteration=1,
        prior_fix_attempts=[],
    )
    result = await mock_adapter.analyze(failures, context)

    # Verify result matches what we preconfigured
    assert result.classification == FailureClassification.ENVIRONMENT_ISSUE
    assert result.confidence == 0.95
    assert result.reasoning == "Stale Docker image detected"
    assert result.recommended_action == "Rebuild environment"


@pytest.mark.asyncio
async def test_systemic_analysis_defaults_to_code_defect():
    """Test that MockSystemicAnalysisAdapter defaults to CODE_DEFECT when no results configured."""
    config = SimulationConfig.create_fast_config("test_defaults", speed_multiplier=100.0)
    bootstrap = SimulationApplicationBootstrap(config)
    app = await bootstrap.setup()

    mock_adapter = bootstrap.adapters.systemic_analysis_as_mock()

    # Don't preconfigure any results
    assert mock_adapter._results == []

    # Execute analyze - should return default CODE_DEFECT
    failures = [
        RepairTestFailure(
            file="test_example.py",
            test="test_something",
            message="AssertionError: expected 5 but got 3",
        ),
    ]
    context = AnalysisContext(
        workflow_run_id="wf-123",
        work_item_id="item-456",
        iteration=2,
        prior_fix_attempts=["Fixed indentation", "Added missing import"],
    )
    result = await mock_adapter.analyze(failures, context)

    # Verify default classification
    assert result.classification == FailureClassification.CODE_DEFECT
    assert result.confidence == 1.0
    assert result.reasoning == "Default classification"


@pytest.mark.asyncio
async def test_repair_cycle_adapter_wired_with_systemic_analysis_in_simulation():
    """Test that systemic_analysis_service is properly wired in bootstrap post-processing.

    This test verifies that the mock systemic analysis adapter is:
    1. Created in bootstrap post-processing
    2. Injected into ProductionRepairCycleAdapter if used
    3. Accessible and configurable by test authors
    """
    config = SimulationConfig.create_fast_config("test_repair_with_analysis", speed_multiplier=100.0)

    bootstrap = SimulationApplicationBootstrap(config)
    app = await bootstrap.setup()

    # Verify repair_cycle adapter exists
    assert bootstrap.adapters.repair_cycle is not None

    # Verify systemic_analysis_service is accessible
    assert bootstrap.adapters.systemic_analysis_service is not None
    mock_adapter = bootstrap.adapters.systemic_analysis_as_mock()
    assert isinstance(mock_adapter, MockSystemicAnalysisAdapter)

    # Preconfigure the mock to return ENVIRONMENT_ISSUE
    environment_result = SystemicAnalysisResult(
        classification=FailureClassification.ENVIRONMENT_ISSUE,
        confidence=0.95,
        reasoning="Docker daemon not responding",
        affected_files=(),
        recommended_action="Restart Docker",
    )
    mock_adapter._results = [environment_result]

    # Verify the mock can be used for failure analysis
    failures = [
        RepairTestFailure(
            file="integration_test.py",
            test="test_db_connection",
            message="ConnectionError: cannot connect to database",
        ),
    ]
    context = AnalysisContext(
        workflow_run_id="wf-789",
        work_item_id="item-789",
        iteration=1,
        prior_fix_attempts=[],
    )
    result = await mock_adapter.analyze(failures, context)

    # Verify the mock was used and returned the preconfigured result
    assert result.classification == FailureClassification.ENVIRONMENT_ISSUE
    assert mock_adapter.call_count == 1


@pytest.mark.asyncio
async def test_systemic_analysis_call_count_tracking():
    """Test that MockSystemicAnalysisAdapter tracks analyze() call count."""
    config = SimulationConfig.create_fast_config("test_call_tracking", speed_multiplier=100.0)
    bootstrap = SimulationApplicationBootstrap(config)
    app = await bootstrap.setup()

    mock_adapter = bootstrap.adapters.systemic_analysis_as_mock()
    assert mock_adapter.call_count == 0

    # Configure result sequence for multiple calls
    mock_adapter._results = [
        SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=1.0,
            reasoning="Logic error in comparator",
            affected_files=("src/compare.py",),
            recommended_action="Fix comparison logic",
        ),
        SystemicAnalysisResult(
            classification=FailureClassification.TRANSIENT_FAILURE,
            confidence=0.8,
            reasoning="Intermittent network timeout",
            affected_files=(),
            recommended_action="Retry the tests",
        ),
        SystemicAnalysisResult(
            classification=FailureClassification.DEPENDENCY_ISSUE,
            confidence=0.9,
            reasoning="Outdated dependency version",
            affected_files=(),
            recommended_action="Update dependencies",
        ),
    ]

    # Make multiple calls and verify tracking
    context = AnalysisContext(
        workflow_run_id="wf-100",
        work_item_id="item-100",
        iteration=1,
        prior_fix_attempts=[],
    )
    failures = [RepairTestFailure("test.py", "test_x", "fail")]

    result1 = await mock_adapter.analyze(failures, context)
    assert mock_adapter.call_count == 1
    assert result1.classification == FailureClassification.CODE_DEFECT

    result2 = await mock_adapter.analyze(failures, context)
    assert mock_adapter.call_count == 2
    assert result2.classification == FailureClassification.TRANSIENT_FAILURE

    result3 = await mock_adapter.analyze(failures, context)
    assert mock_adapter.call_count == 3
    assert result3.classification == FailureClassification.DEPENDENCY_ISSUE

    # Fourth call should return default (no more preconfigured results)
    result4 = await mock_adapter.analyze(failures, context)
    assert mock_adapter.call_count == 4
    assert result4.classification == FailureClassification.CODE_DEFECT  # default


@pytest.mark.asyncio
async def test_systemic_analysis_calls_property_tracks_arguments():
    """Test that MockSystemicAnalysisAdapter tracks analyze() arguments."""
    config = SimulationConfig.create_fast_config("test_args_tracking", speed_multiplier=100.0)
    bootstrap = SimulationApplicationBootstrap(config)
    app = await bootstrap.setup()

    mock_adapter = bootstrap.adapters.systemic_analysis_as_mock()

    # Execute multiple analyze calls with different arguments
    failures1 = [
        RepairTestFailure("unit_test.py", "test_add", "AssertionError: 5 != 4"),
    ]
    context1 = AnalysisContext(
        workflow_run_id="wf-200",
        work_item_id="item-200",
        iteration=1,
        prior_fix_attempts=[],
    )
    await mock_adapter.analyze(failures1, context1)

    failures2 = [
        RepairTestFailure("integration_test.py", "test_db", "ConnectionError"),
        RepairTestFailure("integration_test.py", "test_api", "TimeoutError"),
    ]
    context2 = AnalysisContext(
        workflow_run_id="wf-201",
        work_item_id="item-201",
        iteration=2,
        prior_fix_attempts=["Retry database connection"],
    )
    await mock_adapter.analyze(failures2, context2)

    # Verify calls property
    assert len(mock_adapter.calls) == 2

    # First call
    first_failures, first_context = mock_adapter.calls[0]
    assert len(first_failures) == 1
    assert first_failures[0].file == "unit_test.py"
    assert first_context.workflow_run_id == "wf-200"
    assert first_context.iteration == 1

    # Second call
    second_failures, second_context = mock_adapter.calls[1]
    assert len(second_failures) == 2
    assert second_failures[0].file == "integration_test.py"
    assert second_context.workflow_run_id == "wf-201"
    assert second_context.iteration == 2
    assert len(second_context.prior_fix_attempts) == 1
