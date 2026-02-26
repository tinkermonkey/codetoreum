"""Contract test validation for InMemoryStorageAdapter.

This test class verifies that InMemoryStorageAdapter satisfies all
IStorage contract requirements.
"""

from codetoreum.adapters.testing.in_memory_storage_adapter import InMemoryStorageAdapter
from codetoreum.ports.output.storage import IStorage
from tests.unit.ports.output.test_storage_contract import TestStorageContract


class TestInMemoryStorageContract(TestStorageContract):
    """Verify InMemoryStorageAdapter satisfies IStorage contract."""

    async def create_storage(self) -> IStorage:
        """Create InMemoryStorageAdapter instance for contract testing."""
        return InMemoryStorageAdapter()
