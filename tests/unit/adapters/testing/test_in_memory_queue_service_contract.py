"""Contract test validation for InMemoryQueueService.

This test class verifies that InMemoryQueueService satisfies all
IPipelineQueueService contract requirements.
"""


from codetoreum.adapters.testing.in_memory_queue_service import InMemoryQueueService
from tests.unit.ports.output.test_pipeline_queue_service_contract import (
    TestPipelineQueueServiceContract,
)


class TestInMemoryQueueServiceContract(TestPipelineQueueServiceContract):
    """Verify InMemoryQueueService satisfies IPipelineQueueService contract."""

    async def create_service(self) -> InMemoryQueueService:
        """Create InMemoryQueueService instance for contract testing."""
        return InMemoryQueueService()
