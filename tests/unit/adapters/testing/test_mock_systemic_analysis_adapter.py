"""Unit tests for MockSystemicAnalysisAdapter.

Tests verify that:
1. Constructor accepts optional results sequence
2. Each call to analyze() returns the next result in sequence
3. After sequence exhausted, returns default result (CODE_DEFECT, confidence=1.0)
4. With no results configured, every call returns default result
5. call_count equals number of times analyze() was called
6. calls list contains all (failures, context) argument tuples in order
7. Sequence exhaustion behavior is deterministic
"""

import pytest

from codetoreum.adapters.testing.mock_systemic_analysis_adapter import (
    DEFAULT_RESULT,
    MockSystemicAnalysisAdapter,
)
from codetoreum.domain.repair_cycle_types import (
    AnalysisContext,
    FailureClassification,
    RepairTestFailure,
    SystemicAnalysisResult,
)


@pytest.mark.asyncio
class TestMockSystemicAnalysisAdapter:
    """Tests for MockSystemicAnalysisAdapter."""

    @pytest.fixture
    def sample_failures(self) -> list[RepairTestFailure]:
        """Create sample test failures for analysis."""
        return [
            RepairTestFailure(
                file="test_auth.py",
                test="test_login_success",
                message="Login failed due to connection error",
            ),
            RepairTestFailure(
                file="test_auth.py",
                test="test_logout_success",
                message="Logout returned 500 error",
            ),
        ]

    @pytest.fixture
    def sample_context(self) -> AnalysisContext:
        """Create sample analysis context."""
        return AnalysisContext(
            work_item_id="wi-123",
            iteration=1,
            workflow_run_id="workflow-456",
            prior_fix_attempts=(),
            prior_classifications=(),
        )

    async def test_default_result_with_no_sequence(
        self, sample_failures, sample_context
    ):
        """Test that calling analyze() with no sequence returns default result."""
        adapter = MockSystemicAnalysisAdapter()

        result = await adapter.analyze(sample_failures, sample_context)

        assert result.classification == FailureClassification.CODE_DEFECT
        assert result.confidence == 1.0
        assert result.reasoning == "Default classification"
        assert result.affected_files == ()
        assert result.recommended_action == "Fix code defects"

    async def test_default_result_equality(self, sample_failures, sample_context):
        """Test that returned default matches DEFAULT_RESULT constant."""
        adapter = MockSystemicAnalysisAdapter()

        result = await adapter.analyze(sample_failures, sample_context)

        assert result == DEFAULT_RESULT

    async def test_empty_sequence_returns_default(
        self, sample_failures, sample_context
    ):
        """Test that empty results list returns default on all calls."""
        adapter = MockSystemicAnalysisAdapter(results=[])

        result1 = await adapter.analyze(sample_failures, sample_context)
        result2 = await adapter.analyze(sample_failures, sample_context)

        assert result1 == DEFAULT_RESULT
        assert result2 == DEFAULT_RESULT

    async def test_single_element_sequence(self, sample_failures, sample_context):
        """Test sequence with single element."""
        custom_result = SystemicAnalysisResult(
            classification=FailureClassification.ENVIRONMENT_ISSUE,
            confidence=0.9,
            reasoning="Stale Docker image",
            affected_files=("Dockerfile",),
            recommended_action="Rebuild environment",
        )
        adapter = MockSystemicAnalysisAdapter(results=[custom_result])

        # First call returns custom result
        result1 = await adapter.analyze(sample_failures, sample_context)
        assert result1 == custom_result

        # Second call returns default (sequence exhausted)
        result2 = await adapter.analyze(sample_failures, sample_context)
        assert result2 == DEFAULT_RESULT

    async def test_two_element_sequence_exhaustion(
        self, sample_failures, sample_context
    ):
        """Test sequence with two elements and exhaustion."""
        result1_config = SystemicAnalysisResult(
            classification=FailureClassification.ENVIRONMENT_ISSUE,
            confidence=0.9,
            reasoning="Docker issue",
            affected_files=("Dockerfile",),
            recommended_action="Rebuild",
        )
        result2_config = SystemicAnalysisResult(
            classification=FailureClassification.DEPENDENCY_ISSUE,
            confidence=0.8,
            reasoning="Package version mismatch",
            affected_files=("requirements.txt",),
            recommended_action="Update dependencies",
        )
        adapter = MockSystemicAnalysisAdapter(results=[result1_config, result2_config])

        # First call returns first result
        result1 = await adapter.analyze(sample_failures, sample_context)
        assert result1 == result1_config

        # Second call returns second result
        result2 = await adapter.analyze(sample_failures, sample_context)
        assert result2 == result2_config

        # Third call returns default (sequence exhausted)
        result3 = await adapter.analyze(sample_failures, sample_context)
        assert result3 == DEFAULT_RESULT

        # Fourth call still returns default
        result4 = await adapter.analyze(sample_failures, sample_context)
        assert result4 == DEFAULT_RESULT

    async def test_call_count_increments(self, sample_failures, sample_context):
        """Test that call_count increments with each analyze() call."""
        adapter = MockSystemicAnalysisAdapter()

        assert adapter.call_count == 0

        await adapter.analyze(sample_failures, sample_context)
        assert adapter.call_count == 1

        await adapter.analyze(sample_failures, sample_context)
        assert adapter.call_count == 2

        await adapter.analyze(sample_failures, sample_context)
        assert adapter.call_count == 3

    async def test_calls_list_records_arguments(self, sample_failures, sample_context):
        """Test that calls list records all (failures, context) tuples."""
        adapter = MockSystemicAnalysisAdapter()

        # First call with original arguments
        await adapter.analyze(sample_failures, sample_context)

        # Second call with different context
        context2 = AnalysisContext(
            work_item_id="wi-789",
            iteration=2,
            workflow_run_id="workflow-789",
        )
        await adapter.analyze(sample_failures, context2)

        # Verify calls list
        assert len(adapter.calls) == 2
        assert adapter.calls[0] == (sample_failures, sample_context)
        assert adapter.calls[1] == (sample_failures, context2)

    async def test_calls_list_is_immutable_copy(self, sample_failures, sample_context):
        """Test that calls property returns a copy (is safe from external mutation)."""
        adapter = MockSystemicAnalysisAdapter()

        await adapter.analyze(sample_failures, sample_context)

        calls1 = adapter.calls
        calls2 = adapter.calls

        # Should be equal but not the same object
        assert calls1 == calls2
        assert calls1 is not calls2

    async def test_sequence_ordering_preserved(self, sample_failures, sample_context):
        """Test that sequence order is preserved."""
        results = [
            SystemicAnalysisResult(
                classification=FailureClassification.CODE_DEFECT,
                confidence=0.7,
                reasoning="First result",
                affected_files=(),
                recommended_action="Fix code",
            ),
            SystemicAnalysisResult(
                classification=FailureClassification.TRANSIENT_FAILURE,
                confidence=0.6,
                reasoning="Second result",
                affected_files=(),
                recommended_action="Retry",
            ),
            SystemicAnalysisResult(
                classification=FailureClassification.CONFIGURATION_ISSUE,
                confidence=0.8,
                reasoning="Third result",
                affected_files=("config.yaml",),
                recommended_action="Fix configuration",
            ),
        ]
        adapter = MockSystemicAnalysisAdapter(results=results)

        result1 = await adapter.analyze(sample_failures, sample_context)
        result2 = await adapter.analyze(sample_failures, sample_context)
        result3 = await adapter.analyze(sample_failures, sample_context)
        result4 = await adapter.analyze(sample_failures, sample_context)

        assert result1.reasoning == "First result"
        assert result2.reasoning == "Second result"
        assert result3.reasoning == "Third result"
        assert result4 == DEFAULT_RESULT

    async def test_multiple_calls_same_arguments(
        self, sample_failures, sample_context
    ):
        """Test multiple calls with same arguments are all recorded."""
        adapter = MockSystemicAnalysisAdapter()

        # Call multiple times with same arguments
        await adapter.analyze(sample_failures, sample_context)
        await adapter.analyze(sample_failures, sample_context)
        await adapter.analyze(sample_failures, sample_context)

        assert adapter.call_count == 3
        # All should be identical tuples
        for call in adapter.calls:
            assert call == (sample_failures, sample_context)

    async def test_different_failures_recorded(self, sample_context):
        """Test that different failure lists are recorded separately."""
        failures1 = [
            RepairTestFailure(
                file="test_a.py",
                test="test_1",
                message="Error 1",
            ),
        ]
        failures2 = [
            RepairTestFailure(
                file="test_b.py",
                test="test_2",
                message="Error 2",
            ),
        ]

        adapter = MockSystemicAnalysisAdapter()

        await adapter.analyze(failures1, sample_context)
        await adapter.analyze(failures2, sample_context)

        assert len(adapter.calls) == 2
        assert adapter.calls[0][0] == failures1
        assert adapter.calls[1][0] == failures2

    async def test_default_result_constants(self):
        """Test DEFAULT_RESULT has correct constant values."""
        assert DEFAULT_RESULT.classification == FailureClassification.CODE_DEFECT
        assert DEFAULT_RESULT.confidence == 1.0
        assert DEFAULT_RESULT.reasoning == "Default classification"
        assert DEFAULT_RESULT.affected_files == ()
        assert DEFAULT_RESULT.recommended_action == "Fix code defects"

    async def test_custom_result_properties(self, sample_failures, sample_context):
        """Test that custom result properties are preserved."""
        custom_result = SystemicAnalysisResult(
            classification=FailureClassification.DEPENDENCY_ISSUE,
            confidence=0.75,
            reasoning="Custom reasoning text",
            affected_files=("file1.py", "file2.py"),
            recommended_action="Update dependencies",
        )
        adapter = MockSystemicAnalysisAdapter(results=[custom_result])

        result = await adapter.analyze(sample_failures, sample_context)

        assert result.classification == FailureClassification.DEPENDENCY_ISSUE
        assert result.confidence == 0.75
        assert result.reasoning == "Custom reasoning text"
        assert result.affected_files == ("file1.py", "file2.py")
        assert result.recommended_action == "Update dependencies"
