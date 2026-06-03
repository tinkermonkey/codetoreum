"""Contract tests for InMemoryPipelineQueue implementation.

Tests that InMemoryPipelineQueue conforms to the IPipelineQueue contract,
ensuring it can safely be used as a drop-in replacement for production or
Redis implementations in tests and simulation environments.
"""

import pytest

from codetoreum.adapters.testing import InMemoryPipelineQueue
from tests.unit.ports.output.test_pipeline_queue_contract import TestPipelineQueueContract


class TestInMemoryPipelineQueueContract(TestPipelineQueueContract):
    """Contract test suite for InMemoryPipelineQueue.

    Verifies that the in-memory implementation satisfies all requirements
    of the IPipelineQueue interface.
    """

    async def create_queue(self) -> InMemoryPipelineQueue:
        """Create a fresh InMemoryPipelineQueue instance for each test."""
        return InMemoryPipelineQueue()
