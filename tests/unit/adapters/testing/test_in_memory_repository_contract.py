"""Contract test validation for InMemoryRepositoryAdapter.

This test class verifies that InMemoryRepositoryAdapter satisfies all
IRepository contract requirements.
"""

from codetoreum.adapters.testing.in_memory_repository_adapter import InMemoryRepositoryAdapter
from codetoreum.ports.output.repository import IRepository
from tests.unit.ports.output.test_repository_contract import TestRepositoryContract


class TestInMemoryRepositoryContract(TestRepositoryContract):
    """Verify InMemoryRepositoryAdapter satisfies IRepository contract."""

    async def create_repository(self) -> IRepository:
        """Create InMemoryRepositoryAdapter instance for contract testing."""
        return InMemoryRepositoryAdapter()
