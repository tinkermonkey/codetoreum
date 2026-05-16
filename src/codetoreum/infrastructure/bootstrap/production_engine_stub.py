"""Minimal engine stub for production bootstrap.

Provides just enough simulation engine interface for the resolver to create
non-critical mock adapters without pulling in the full SimulationEngine.

This is used when resolving adapters like review_cycle that require a
SimulationEngine for time-aware mock creation.
"""

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


class ProductionClockStub:
    """Minimal clock implementation that returns system time."""

    def now(self) -> datetime:
        """Return current UTC time."""
        return datetime.now(UTC)

    def advance(self, delta):
        """No-op in production (not advancing time)."""


class ProductionEngineStub:
    """Minimal engine stub for production bootstrap.

    Provides just enough interface for the resolver to create mocks
    without pulling in the full SimulationEngine.
    """

    def __init__(self):
        """Initialize with a production clock stub."""
        self._clock = ProductionClockStub()

    def get_clock_for_testing(self) -> ProductionClockStub:
        """Return the clock stub for time-based operations."""
        return self._clock

    def create_review_cycle_adapter(self, llm_adapter=None):
        """Create a review cycle adapter for production.

        In production, create a basic mock without time-awareness.
        Post-MVP should integrate with real review system.
        """
        from codetoreum.adapters.testing import MockReviewCycleAdapter

        logger.debug("Creating MockReviewCycleAdapter for production (non-critical path)")
        return MockReviewCycleAdapter(clock=None, llm_adapter=llm_adapter)

    def create_pr_review_cycle_adapter(self):
        """Create a PR review cycle adapter for production.

        In production, create a basic mock without time-awareness.
        Post-MVP should integrate with real review system.
        """
        from codetoreum.adapters.testing import MockPRReviewCycleAdapter

        logger.debug("Creating MockPRReviewCycleAdapter for production (non-critical path)")
        return MockPRReviewCycleAdapter(clock=None)

    def create_repair_cycle_adapter(self, llm_factory=None, checkpoint_store=None, container_adapter=None):
        """Create a repair cycle adapter for production.

        In production, create a basic mock without time-awareness.
        Post-MVP should integrate with real repair system.
        """
        from codetoreum.adapters.testing import MockRepairCycleAdapter

        logger.debug("Creating MockRepairCycleAdapter for production (non-critical path)")
        return MockRepairCycleAdapter(clock=None)

    def create_systemic_analysis_adapter(self, llm_adapter=None):
        """Create a systemic analysis adapter for production.

        In production, create a basic mock without time-awareness.
        Post-MVP should integrate with real analysis system.
        """
        from codetoreum.adapters.testing import MockSystemicAnalysisAdapter

        logger.debug("Creating MockSystemicAnalysisAdapter for production (non-critical path)")
        return MockSystemicAnalysisAdapter(clock=None, llm_adapter=llm_adapter)

    def create_environment_repair_adapter(self, llm_adapter=None):
        """Create an environment repair adapter for production.

        In production, create a basic mock without time-awareness.
        Post-MVP should integrate with real repair system.
        """
        from codetoreum.adapters.testing import MockEnvironmentRepairAdapter

        logger.debug("Creating MockEnvironmentRepairAdapter for production (non-critical path)")
        return MockEnvironmentRepairAdapter(clock=None, llm_adapter=llm_adapter)
