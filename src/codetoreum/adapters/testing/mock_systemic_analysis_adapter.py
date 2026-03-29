"""Mock adapter for systemic analysis service in simulation testing.

Provides deterministic test behavior for classifying test failures
by root cause without calling an LLM or external service.

Implements ISystemicAnalysisService for deterministic scenario testing.
"""

from codetoreum.domain.repair_cycle_types import (
    AnalysisContext,
    FailureClassification,
    RepairTestFailure,
    SystemicAnalysisResult,
)
from codetoreum.ports.output.systemic_analysis_service import ISystemicAnalysisService


DEFAULT_RESULT = SystemicAnalysisResult(
    classification=FailureClassification.CODE_DEFECT,
    confidence=1.0,
    reasoning="Default classification",
    affected_files=(),
    recommended_action="Fix code defects",
)


class MockSystemicAnalysisAdapter(ISystemicAnalysisService):
    """Mock implementation of ISystemicAnalysisService for deterministic testing.

    Supports a configurable sequence of results for deterministic test scenarios.
    Each call to analyze() returns the next result in the configured sequence,
    advancing an internal index. When the sequence is exhausted or no sequence
    is configured, returns a default classification (CODE_DEFECT, confidence=1.0).

    Example:
        # Configure to return environment_issue on first call
        mock = MockSystemicAnalysisAdapter(results=[
            SystemicAnalysisResult(
                classification=FailureClassification.ENVIRONMENT_ISSUE,
                confidence=0.9,
                reasoning="Stale Docker image",
                affected_files=(),
                recommended_action="Rebuild environment",
            ),
        ])

        # Execute analysis
        result = await mock.analyze(failures, context)
        assert result.classification == FailureClassification.ENVIRONMENT_ISSUE

        # Second call returns default since sequence exhausted
        result2 = await mock.analyze(failures, context)
        assert result2.classification == FailureClassification.CODE_DEFECT

        # Verify calls were recorded
        assert mock.call_count == 2
        assert len(mock.calls) == 2
    """

    def __init__(self, results: list[SystemicAnalysisResult] | None = None) -> None:
        """Initialize mock adapter with optional result sequence.

        Args:
            results: List of SystemicAnalysisResult objects to return in sequence.
                    If None or empty, all calls return the default result.
        """
        self._results: list[SystemicAnalysisResult] = list(results) if results else []
        self._call_index: int = 0
        self._calls: list[tuple[list[RepairTestFailure], AnalysisContext]] = []

    @property
    def call_count(self) -> int:
        """Return number of times analyze() was called."""
        return len(self._calls)

    @property
    def calls(self) -> list[tuple[list[RepairTestFailure], AnalysisContext]]:
        """Return list of all (failures, context) argument tuples in order."""
        return list(self._calls)

    async def analyze(
        self,
        failures: list[RepairTestFailure],
        context: AnalysisContext,
    ) -> SystemicAnalysisResult:
        """Classify failures by returning next result in sequence or default.

        Records all arguments for test inspection via call_count and calls properties.

        Args:
            failures: List of test failures to classify.
            context: Context including work item id, iteration count, etc.

        Returns:
            Next SystemicAnalysisResult in configured sequence, or DEFAULT_RESULT
            if sequence is exhausted or empty.
        """
        self._calls.append((failures, context))

        if self._call_index < len(self._results):
            result = self._results[self._call_index]
            self._call_index += 1
            return result

        return DEFAULT_RESULT
