"""
Specific adapter registries for each port interface.

Provides registries for managing implementations of all 26+ adapter slots
including ticket systems, LLM providers, containers, repositories, event stores,
board services, code review services, and more.
"""

import inspect

from codetoreum.application.pipeline_lock_service import IQueuedPipelineLockService
from codetoreum.infrastructure.adapters.registry_base import AdapterRegistry
from codetoreum.ports.output.active_workflow_run_registry import IActiveWorkflowRunRegistry
from codetoreum.ports.output.agent_executor import IAgentExecutor
from codetoreum.ports.output.agent_repository import IAgentRepository
from codetoreum.ports.output.board_service import IBoardService
from codetoreum.ports.output.code_review_service import ICodeReviewService
from codetoreum.ports.output.config_store import IConfigStore
from codetoreum.ports.output.container import IContainer
from codetoreum.ports.output.container_recovery import IAgentContainerRecoveryService
from codetoreum.ports.output.discussion_adapter import IDiscussionAdapter
from codetoreum.ports.output.encryption_service import IEncryptionService
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.event_store import IEventStore
from codetoreum.ports.output.identity_service import IIdentityService
from codetoreum.ports.output.llm_provider import ILLMProvider
from codetoreum.ports.output.message_broker import IMessageBroker
from codetoreum.ports.output.metrics import IMetrics
from codetoreum.ports.output.notifier import INotifier
from codetoreum.ports.output.pipeline_lock_service import IPipelineLockService
from codetoreum.ports.output.pipeline_queue_service import IPipelineQueueService
from codetoreum.ports.output.project_manager_service import IProjectManagerService
from codetoreum.ports.output.repair_cycle_checkpoint_store import IRepairCycleCheckpointStore
from codetoreum.ports.output.repair_cycle_service import IRepairCycle
from codetoreum.ports.output.repository import IRepository
from codetoreum.ports.output.review_cycle_service import IReviewCycle
from codetoreum.ports.output.storage import IStorage
from codetoreum.ports.output.ticket_system import ITicketSystem
from codetoreum.ports.output.version_control_service import IVersionControlService
from codetoreum.ports.output.work_item_branch_tracker import IWorkItemBranchTracker
from codetoreum.ports.output.work_item_service import IWorkItemService
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService


def _get_interface_methods(interface_class: type) -> set[str]:
    """
    Extract all abstract method names from a port interface.

    Args:
        interface_class: The port interface class

    Returns:
        Set of method names defined in the interface
    """
    methods = set()
    for name, method in inspect.getmembers(interface_class, predicate=inspect.isfunction):
        # Skip private methods and special methods
        if not name.startswith("_"):
            # Check if it's an abstract method
            if hasattr(method, "__isabstractmethod__") and method.__isabstractmethod__:
                methods.add(name)
    return methods


def _validate_adapter_implements_interface(adapter_type: type, interface_class: type) -> bool:
    """
    Validate that an adapter implements all required methods from interface.

    Uses dynamic introspection of the interface to discover required methods.

    Args:
        adapter_type: The adapter class to validate
        interface_class: The port interface class

    Returns:
        True if adapter implements all interface methods
    """
    # Get required methods from interface
    required_methods = _get_interface_methods(interface_class)

    # Get methods implemented by adapter
    adapter_methods = {
        name for name, _ in inspect.getmembers(adapter_type, predicate=inspect.isfunction) if not name.startswith("_")
    }

    # Check that all required methods are implemented
    return required_methods.issubset(adapter_methods)


class TicketSystemRegistry(AdapterRegistry[ITicketSystem]):
    """Registry for ITicketSystem adapter implementations."""

    def __init__(self):
        """Initialize the ticket system registry."""
        super().__init__(ITicketSystem)

    def _is_valid_adapter(self, adapter_type: type[ITicketSystem]) -> bool:
        """
        Validate that an adapter implements ITicketSystem.

        Uses dynamic introspection to check that the adapter class implements
        all required methods from the ITicketSystem interface.

        Args:
            adapter_type: The adapter class to validate

        Returns:
            True if adapter implements all ITicketSystem methods
        """
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class LLMProviderRegistry(AdapterRegistry[ILLMProvider]):
    """Registry for ILLMProvider adapter implementations."""

    def __init__(self):
        """Initialize the LLM provider registry."""
        super().__init__(ILLMProvider)

    def _is_valid_adapter(self, adapter_type: type[ILLMProvider]) -> bool:
        """
        Validate that an adapter implements ILLMProvider.

        Uses dynamic introspection to check that the adapter class implements
        all required methods from the ILLMProvider interface.

        Args:
            adapter_type: The adapter class to validate

        Returns:
            True if adapter implements all ILLMProvider methods
        """
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class ContainerRegistry(AdapterRegistry[IContainer]):
    """Registry for IContainer adapter implementations."""

    def __init__(self):
        """Initialize the container registry."""
        super().__init__(IContainer)

    def _is_valid_adapter(self, adapter_type: type[IContainer]) -> bool:
        """
        Validate that an adapter implements IContainer.

        Uses dynamic introspection to check that the adapter class implements
        all required methods from the IContainer interface.

        Args:
            adapter_type: The adapter class to validate

        Returns:
            True if adapter implements all IContainer methods
        """
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class RepositoryRegistry(AdapterRegistry[IRepository]):
    """Registry for IRepository adapter implementations."""

    def __init__(self):
        """Initialize the repository registry."""
        super().__init__(IRepository)

    def _is_valid_adapter(self, adapter_type: type[IRepository]) -> bool:
        """
        Validate that an adapter implements IRepository.

        Uses dynamic introspection to check that the adapter class implements
        all required methods from the IRepository interface.

        Args:
            adapter_type: The adapter class to validate

        Returns:
            True if adapter implements all IRepository methods
        """
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class EventStoreRegistry(AdapterRegistry[IEventStore]):
    """Registry for IEventStore adapter implementations."""

    def __init__(self):
        """Initialize the event store registry."""
        super().__init__(IEventStore)

    def _is_valid_adapter(self, adapter_type: type[IEventStore]) -> bool:
        """
        Validate that an adapter implements IEventStore.

        Uses dynamic introspection to check that the adapter class implements
        all required methods from the IEventStore interface.

        Args:
            adapter_type: The adapter class to validate

        Returns:
            True if adapter implements all IEventStore methods
        """
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class StorageRegistry(AdapterRegistry[IStorage]):
    """Registry for IStorage adapter implementations."""

    def __init__(self):
        """Initialize the storage registry."""
        super().__init__(IStorage)

    def _is_valid_adapter(self, adapter_type: type[IStorage]) -> bool:
        """
        Validate that an adapter implements IStorage.

        Uses dynamic introspection to check that the adapter class implements
        all required methods from the IStorage interface.

        Args:
            adapter_type: The adapter class to validate

        Returns:
            True if adapter implements all IStorage methods
        """
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class BoardServiceRegistry(AdapterRegistry[IBoardService]):
    """Registry for IBoardService adapter implementations."""

    def __init__(self):
        """Initialize the board service registry."""
        super().__init__(IBoardService)

    def _is_valid_adapter(self, adapter_type: type[IBoardService]) -> bool:
        """Validate that an adapter implements IBoardService."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class CodeReviewServiceRegistry(AdapterRegistry[ICodeReviewService]):
    """Registry for ICodeReviewService adapter implementations."""

    def __init__(self):
        """Initialize the code review service registry."""
        super().__init__(ICodeReviewService)

    def _is_valid_adapter(self, adapter_type: type[ICodeReviewService]) -> bool:
        """Validate that an adapter implements ICodeReviewService."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class DiscussionAdapterRegistry(AdapterRegistry[IDiscussionAdapter]):
    """Registry for IDiscussionAdapter adapter implementations."""

    def __init__(self):
        """Initialize the discussion adapter registry."""
        super().__init__(IDiscussionAdapter)

    def _is_valid_adapter(self, adapter_type: type[IDiscussionAdapter]) -> bool:
        """Validate that an adapter implements IDiscussionAdapter."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class VersionControlServiceRegistry(AdapterRegistry[IVersionControlService]):
    """Registry for IVersionControlService adapter implementations."""

    def __init__(self):
        """Initialize the version control service registry."""
        super().__init__(IVersionControlService)

    def _is_valid_adapter(self, adapter_type: type[IVersionControlService]) -> bool:
        """Validate that an adapter implements IVersionControlService."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class MetricsAdapterRegistry(AdapterRegistry[IMetrics]):
    """Registry for IMetrics adapter implementations."""

    def __init__(self):
        """Initialize the metrics adapter registry."""
        super().__init__(IMetrics)

    def _is_valid_adapter(self, adapter_type: type[IMetrics]) -> bool:
        """Validate that an adapter implements IMetrics."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class NotifierRegistry(AdapterRegistry[INotifier]):
    """Registry for INotifier adapter implementations."""

    def __init__(self):
        """Initialize the notifier registry."""
        super().__init__(INotifier)

    def _is_valid_adapter(self, adapter_type: type[INotifier]) -> bool:
        """Validate that an adapter implements INotifier."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class MessageBrokerRegistry(AdapterRegistry[IMessageBroker]):
    """Registry for IMessageBroker adapter implementations."""

    def __init__(self):
        """Initialize the message broker registry."""
        super().__init__(IMessageBroker)

    def _is_valid_adapter(self, adapter_type: type[IMessageBroker]) -> bool:
        """Validate that an adapter implements IMessageBroker."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class ConfigStoreRegistry(AdapterRegistry[IConfigStore]):
    """Registry for IConfigStore adapter implementations."""

    def __init__(self):
        """Initialize the config store registry."""
        super().__init__(IConfigStore)

    def _is_valid_adapter(self, adapter_type: type[IConfigStore]) -> bool:
        """Validate that an adapter implements IConfigStore."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class RepairCycleRegistry(AdapterRegistry[IRepairCycle]):
    """Registry for IRepairCycle adapter implementations."""

    def __init__(self):
        """Initialize the repair cycle registry."""
        super().__init__(IRepairCycle)

    def _is_valid_adapter(self, adapter_type: type[IRepairCycle]) -> bool:
        """Validate that an adapter implements IRepairCycle."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class ReviewCycleServiceRegistry(AdapterRegistry[IReviewCycle]):
    """Registry for IReviewCycle adapter implementations."""

    def __init__(self):
        """Initialize the review cycle service registry."""
        super().__init__(IReviewCycle)

    def _is_valid_adapter(self, adapter_type: type[IReviewCycle]) -> bool:
        """Validate that an adapter implements IReviewCycle."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class ContainerRecoveryRegistry(AdapterRegistry[IAgentContainerRecoveryService]):
    """Registry for IAgentContainerRecoveryService adapter implementations."""

    def __init__(self):
        """Initialize the container recovery registry."""
        super().__init__(IAgentContainerRecoveryService)

    def _is_valid_adapter(self, adapter_type: type[IAgentContainerRecoveryService]) -> bool:
        """Validate that an adapter implements IAgentContainerRecoveryService."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class EncryptionRegistry(AdapterRegistry[IEncryptionService]):
    """Registry for IEncryptionService adapter implementations."""

    def __init__(self):
        """Initialize the encryption service registry."""
        super().__init__(IEncryptionService)

    def _is_valid_adapter(self, adapter_type: type[IEncryptionService]) -> bool:
        """Validate that an adapter implements IEncryptionService."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class PipelineLockServiceRegistry(AdapterRegistry[IPipelineLockService]):
    """Registry for IPipelineLockService adapter implementations.

    This registry accepts adapters that implement either:
    - IPipelineLockService (port interface, 3-parameter lock methods)
    - IQueuedPipelineLockService (application interface, 4-parameter lock methods with position-based queue)
    """

    def __init__(self):
        """Initialize the pipeline lock service registry."""
        super().__init__(IPipelineLockService)

    def _is_valid_adapter(self, adapter_type: type[IPipelineLockService]) -> bool:
        """Validate that an adapter implements IPipelineLockService or IQueuedPipelineLockService."""
        # Check if implements port interface
        if _validate_adapter_implements_interface(adapter_type, self._port_interface):
            return True
        # Also accept adapters that implement IQueuedPipelineLockService (application interface)
        return _validate_adapter_implements_interface(adapter_type, IQueuedPipelineLockService)


class PipelineQueueServiceRegistry(AdapterRegistry[IPipelineQueueService]):
    """Registry for IPipelineQueueService adapter implementations."""

    def __init__(self):
        """Initialize the pipeline queue service registry."""
        super().__init__(IPipelineQueueService)

    def _is_valid_adapter(self, adapter_type: type[IPipelineQueueService]) -> bool:
        """Validate that an adapter implements IPipelineQueueService."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class ProjectManagerServiceRegistry(AdapterRegistry[IProjectManagerService]):
    """Registry for IProjectManagerService adapter implementations."""

    def __init__(self):
        """Initialize the project manager service registry."""
        super().__init__(IProjectManagerService)

    def _is_valid_adapter(self, adapter_type: type[IProjectManagerService]) -> bool:
        """Validate that an adapter implements IProjectManagerService."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class WorkflowConfigServiceRegistry(AdapterRegistry[IWorkflowConfigService]):
    """Registry for IWorkflowConfigService adapter implementations."""

    def __init__(self):
        """Initialize the workflow config service registry."""
        super().__init__(IWorkflowConfigService)

    def _is_valid_adapter(self, adapter_type: type[IWorkflowConfigService]) -> bool:
        """Validate that an adapter implements IWorkflowConfigService."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class EventEmitterRegistry(AdapterRegistry[IEventEmitter]):
    """Registry for IEventEmitter adapter implementations."""

    def __init__(self):
        """Initialize the event emitter registry."""
        super().__init__(IEventEmitter)

    def _is_valid_adapter(self, adapter_type: type[IEventEmitter]) -> bool:
        """Validate that an adapter implements IEventEmitter."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class IdentityServiceRegistry(AdapterRegistry[IIdentityService]):
    """Registry for IIdentityService adapter implementations."""

    def __init__(self):
        """Initialize the identity service registry."""
        super().__init__(IIdentityService)

    def _is_valid_adapter(self, adapter_type: type[IIdentityService]) -> bool:
        """Validate that an adapter implements IIdentityService."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class AgentExecutorRegistry(AdapterRegistry[IAgentExecutor]):
    """Registry for IAgentExecutor adapter implementations."""

    def __init__(self):
        """Initialize the agent executor registry."""
        super().__init__(IAgentExecutor)

    def _is_valid_adapter(self, adapter_type: type[IAgentExecutor]) -> bool:
        """Validate that an adapter implements IAgentExecutor."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class AgentRepositoryRegistry(AdapterRegistry[IAgentRepository]):
    """Registry for IAgentRepository adapter implementations."""

    def __init__(self):
        """Initialize the agent repository registry."""
        super().__init__(IAgentRepository)

    def _is_valid_adapter(self, adapter_type: type[IAgentRepository]) -> bool:
        """Validate that an adapter implements IAgentRepository."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class WorkItemBranchTrackerRegistry(AdapterRegistry[IWorkItemBranchTracker]):
    """Registry for IWorkItemBranchTracker adapter implementations."""

    def __init__(self):
        """Initialize the work item branch tracker registry."""
        super().__init__(IWorkItemBranchTracker)

    def _is_valid_adapter(self, adapter_type: type[IWorkItemBranchTracker]) -> bool:
        """Validate that an adapter implements IWorkItemBranchTracker."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class WorkItemServiceRegistry(AdapterRegistry[IWorkItemService]):
    """Registry for IWorkItemService adapter implementations."""

    def __init__(self):
        """Initialize the work item service registry."""
        super().__init__(IWorkItemService)

    def _is_valid_adapter(self, adapter_type: type[IWorkItemService]) -> bool:
        """Validate that an adapter implements IWorkItemService."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class RepairCycleCheckpointStoreRegistry(AdapterRegistry[IRepairCycleCheckpointStore]):
    """Registry for IRepairCycleCheckpointStore adapter implementations."""

    def __init__(self):
        """Initialize the repair cycle checkpoint store registry."""
        super().__init__(IRepairCycleCheckpointStore)

    def _is_valid_adapter(self, adapter_type: type[IRepairCycleCheckpointStore]) -> bool:
        """Validate that an adapter implements IRepairCycleCheckpointStore."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class ActiveWorkflowRunRegistryRegistry(AdapterRegistry[IActiveWorkflowRunRegistry]):
    """Registry for IActiveWorkflowRunRegistry adapter implementations."""

    def __init__(self):
        """Initialize the active workflow run registry."""
        super().__init__(IActiveWorkflowRunRegistry)

    def _is_valid_adapter(self, adapter_type: type[IActiveWorkflowRunRegistry]) -> bool:
        """Validate that an adapter implements IActiveWorkflowRunRegistry."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)
