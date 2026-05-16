import logging
from datetime import UTC, datetime

from codetoreum.adapters.testing import (
    MockEnvironmentRepairAdapter,
    MockPRReviewCycleAdapter,
    MockRepairCycleAdapter,
    MockReviewCycleAdapter,
    MockSystemicAnalysisAdapter,
)

logger = logging.getLogger(__name__)


class ProductionClockStub:
    """Minimal clock returning system time."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def advance(self, delta):
        pass


class ProductionEngineStub:
    """Minimal engine stub for production bootstrap."""

    def __init__(self):
        self._clock = ProductionClockStub()

    def get_clock_for_testing(self) -> ProductionClockStub:
        return self._clock

    def create_review_cycle_adapter(self, llm_adapter=None):
        logger.debug("Creating MockReviewCycleAdapter for production (non-critical path)")
        return MockReviewCycleAdapter(clock=None, llm_adapter=llm_adapter)

    def create_pr_review_cycle_adapter(self):
        logger.debug("Creating MockPRReviewCycleAdapter for production (non-critical path)")
        return MockPRReviewCycleAdapter(clock=None)

    def create_repair_cycle_adapter(self, llm_factory=None, checkpoint_store=None, container_adapter=None):
        logger.debug("Creating MockRepairCycleAdapter for production (non-critical path)")
        return MockRepairCycleAdapter(clock=None)

    def create_systemic_analysis_adapter(self, llm_adapter=None):
        logger.debug("Creating MockSystemicAnalysisAdapter for production (non-critical path)")
        return MockSystemicAnalysisAdapter(clock=None, llm_adapter=llm_adapter)

    def create_environment_repair_adapter(self, llm_adapter=None):
        logger.debug("Creating MockEnvironmentRepairAdapter for production (non-critical path)")
        return MockEnvironmentRepairAdapter(clock=None, llm_adapter=llm_adapter)
