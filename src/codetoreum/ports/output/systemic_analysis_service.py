"""Systemic analysis service port interface.

Defines the contract for classifying test failure root causes
before dispatching to the appropriate fix strategy.
"""

from abc import ABC, abstractmethod

from codetoreum.domain.repair_cycle_types import (
    AnalysisContext,
    RepairTestFailure,
    SystemicAnalysisResult,
)


class ISystemicAnalysisService(ABC):
    """Analyzes test failures to determine root cause classification.

    Secondary port interface — implementations may delegate to an LLM,
    a rule-based classifier, or a mock for testing.
    """

    @abstractmethod
    async def analyze(
        self,
        failures: list[RepairTestFailure],
        context: AnalysisContext,
    ) -> SystemicAnalysisResult:
        """Classify failures by root cause.

        Args:
            failures: List of test failures to classify.
            context: Context including work item id, iteration count,
                     and prior fix attempt history.

        Returns:
            SystemicAnalysisResult with classification, confidence,
            reasoning, affected files, and recommended action.
        """
        ...
