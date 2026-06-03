"""Contract tests for InMemoryDistributedLock implementation.

Tests that InMemoryDistributedLock conforms to the IDistributedLock contract,
ensuring it can safely be used as a drop-in replacement for production or
Redis implementations in tests and simulation environments.
"""

import pytest

from codetoreum.adapters.testing import InMemoryDistributedLock
from tests.unit.ports.output.test_distributed_lock_contract import TestDistributedLockContract


class TestInMemoryDistributedLockContract(TestDistributedLockContract):
    """Contract test suite for InMemoryDistributedLock.

    Verifies that the in-memory implementation satisfies all requirements
    of the IDistributedLock interface.
    """

    async def create_lock(self) -> InMemoryDistributedLock:
        """Create a fresh InMemoryDistributedLock instance for each test."""
        return InMemoryDistributedLock()
