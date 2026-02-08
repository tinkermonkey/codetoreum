"""Testing adapters for simulation and unit testing."""

from codetoreum.adapters.testing.in_memory_event_store import InMemoryEventStore
from codetoreum.adapters.testing.in_memory_repository_adapter import (
    InMemoryRepositoryAdapter,
)
from codetoreum.adapters.testing.in_memory_ticket_adapter import InMemoryTicketAdapter
from codetoreum.adapters.testing.fake_container_adapter import FakeContainerAdapter
from codetoreum.adapters.testing.mock_llm_adapter import MockLLMAdapter
from codetoreum.adapters.testing.in_memory_metrics_adapter import InMemoryMetricsAdapter
from codetoreum.adapters.testing.mock_notifier_adapter import MockNotifierAdapter
from codetoreum.adapters.testing.simple_encryption_adapter import SimpleEncryptionAdapter
from codetoreum.adapters.testing.mock_board_adapter import MockBoardAdapter, MovementEvent
from codetoreum.adapters.testing.in_memory_queue_service import InMemoryQueueService
from codetoreum.adapters.testing.mock_repair_cycle_adapter import (
    MockRepairCycleAdapter,
    CircuitBreakerTripped,
)
from codetoreum.adapters.testing.mock_container_recovery_adapter import (
    MockContainerRecoveryAdapter,
)
from codetoreum.adapters.testing.mock_project_manager_adapter import (
    MockProjectManagerAdapter,
)
from codetoreum.adapters.testing.mock_event_emitter import MockEventEmitter

__all__ = [
    "InMemoryEventStore",
    "InMemoryRepositoryAdapter",
    "InMemoryTicketAdapter",
    "FakeContainerAdapter",
    "MockLLMAdapter",
    "InMemoryMetricsAdapter",
    "MockNotifierAdapter",
    "SimpleEncryptionAdapter",
    "MockBoardAdapter",
    "MovementEvent",
    "InMemoryQueueService",
    "MockRepairCycleAdapter",
    "CircuitBreakerTripped",
    "MockContainerRecoveryAdapter",
    "MockProjectManagerAdapter",
    "MockEventEmitter",
]
