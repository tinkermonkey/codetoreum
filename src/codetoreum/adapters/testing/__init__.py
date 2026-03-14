"""Testing adapters for simulation and unit testing."""

# Re-export ConfigurableIdentityService from secondary package
# This adapter is used in simulation and testing contexts for configurable identity verification
from codetoreum.adapters.secondary.configurable_identity_service import (
    ConfigurableIdentityService,
)
from codetoreum.adapters.testing.capturing_mock_event_emitter import (
    CapturingMockEventEmitter,
)
from codetoreum.adapters.testing.fake_container_adapter import FakeContainerAdapter
from codetoreum.adapters.testing.in_memory_active_workflow_run_registry import (
    InMemoryActiveWorkflowRunRegistry,
)
from codetoreum.adapters.testing.in_memory_agent_repository import (
    InMemoryAgentRepository,
)
from codetoreum.adapters.testing.in_memory_checkpoint_store import InMemoryCheckpointStore
from codetoreum.adapters.testing.in_memory_config_store import InMemoryConfigStore
from codetoreum.adapters.testing.in_memory_event_store import InMemoryEventStore
from codetoreum.adapters.testing.in_memory_message_broker import InMemoryMessageBroker
from codetoreum.adapters.testing.in_memory_metrics_adapter import InMemoryMetricsAdapter
from codetoreum.adapters.testing.in_memory_queue_service import InMemoryQueueService
from codetoreum.adapters.testing.in_memory_repository_adapter import (
    InMemoryRepositoryAdapter,
)
from codetoreum.adapters.testing.in_memory_storage_adapter import InMemoryStorageAdapter
from codetoreum.adapters.testing.in_memory_ticket_adapter import InMemoryTicketAdapter
from codetoreum.adapters.testing.in_memory_version_control_service import (
    InMemoryVersionControlService,
)
from codetoreum.adapters.testing.in_memory_work_item_branch_tracker import (
    InMemoryWorkItemBranchTracker,
)
from codetoreum.adapters.testing.in_memory_workflow_config_service import (
    InMemoryWorkflowConfigService,
)
from codetoreum.adapters.testing.mock_agent_executor import MockAgentExecutor
from codetoreum.adapters.testing.mock_board_adapter import (
    MockBoardAdapter,
    MovementEvent,
)
from codetoreum.adapters.testing.mock_container_recovery_adapter import (
    MockContainerRecoveryAdapter,
)
from codetoreum.adapters.testing.mock_discussion_adapter import MockDiscussionAdapter
from codetoreum.adapters.testing.mock_llm_adapter import MockLLMAdapter
from codetoreum.adapters.testing.mock_notifier_adapter import MockNotifierAdapter
from codetoreum.adapters.testing.mock_project_manager_adapter import (
    MockProjectManagerAdapter,
)
from codetoreum.adapters.testing.mock_repair_cycle_adapter import (
    CircuitBreakerTripped,
    MockRepairCycleAdapter,
)
from codetoreum.adapters.testing.mock_review_cycle_adapter import MockReviewCycleAdapter
from codetoreum.adapters.testing.mock_work_item_service import MockWorkItemService
from codetoreum.adapters.testing.simple_encryption_adapter import (
    SimpleEncryptionAdapter,
)

__all__ = [
    "CapturingMockEventEmitter",
    "InMemoryActiveWorkflowRunRegistry",
    "InMemoryAgentRepository",
    "InMemoryWorkItemBranchTracker",
    "CircuitBreakerTripped",
    "ConfigurableIdentityService",
    "FakeContainerAdapter",
    "InMemoryCheckpointStore",
    "InMemoryConfigStore",
    "InMemoryEventStore",
    "InMemoryMessageBroker",
    "InMemoryMetricsAdapter",
    "InMemoryQueueService",
    "InMemoryRepositoryAdapter",
    "InMemoryStorageAdapter",
    "InMemoryTicketAdapter",
    "InMemoryVersionControlService",
    "InMemoryWorkflowConfigService",
    "MockAgentExecutor",
    "MockBoardAdapter",
    "MockContainerRecoveryAdapter",
    "MockDiscussionAdapter",
    "MockLLMAdapter",
    "MockNotifierAdapter",
    "MockProjectManagerAdapter",
    "MockReviewCycleAdapter",
    "MockRepairCycleAdapter",
    "MockWorkItemService",
    "MovementEvent",
    "SimpleEncryptionAdapter",
]
