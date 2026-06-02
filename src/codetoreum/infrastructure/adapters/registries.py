"""
Specific adapter registries for each port interface.

Provides registries for managing implementations of all 32 adapter slots
including ticket systems, LLM providers, containers, repositories, event stores,
board services, code review services, CI pipeline services, and more.
"""

import inspect
import logging

logger = logging.getLogger(__name__)

# from codetoreum.application.pipeline_lock_service import IQueuedPipelineLockService  # REMOVED: Port discontinued in Phase 5
from codetoreum.infrastructure.adapters.registry_base import AdapterRegistry
from codetoreum.ports.output.active_workflow_run_registry import IActiveWorkflowRunRegistry
from codetoreum.ports.output.agent_executor import IAgentExecutor
from codetoreum.ports.output.agent_repository import IAgentRepository
from codetoreum.ports.output.board_service import IBoardService
from codetoreum.ports.output.ci_pipeline_service import ICIPipelineService
from codetoreum.ports.output.code_review_service import ICodeReviewService
from codetoreum.ports.output.config_store import IConfigStore
from codetoreum.ports.output.container import IContainer
from codetoreum.ports.output.container_recovery import IAgentContainerRecoveryService
from codetoreum.ports.output.discussion_adapter import IDiscussionAdapter
from codetoreum.ports.output.encryption_service import IEncryptionService
from codetoreum.ports.output.environment_repair_service import IEnvironmentRepairService
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.event_store import IEventStore
from codetoreum.ports.output.identity_service import IIdentityService
from codetoreum.ports.output.message_broker import IMessageBroker
from codetoreum.ports.output.metrics import IMetrics
from codetoreum.ports.output.notifier import INotifier
from codetoreum.ports.output.pipeline_queue_service import IPipelineQueueService
from codetoreum.ports.output.pr_review_cycle_service import IPRReviewCycle
from codetoreum.ports.output.project_manager_service import IProjectManagerService
from codetoreum.ports.output.repair_cycle_checkpoint_store import IRepairCycleCheckpointStore
from codetoreum.ports.output.repair_cycle_service import IRepairCycle
from codetoreum.ports.output.repository import IRepository
from codetoreum.ports.output.review_cycle_service import IReviewCycle
from codetoreum.ports.output.systemic_analysis_service import ISystemicAnalysisService
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


def _get_interface_signature(interface_class: type, method_name: str) -> inspect.Signature:
    """
    Extract the signature of an interface method.

    Args:
        interface_class: The port interface class
        method_name: The method name to extract signature for

    Returns:
        The method's signature

    Raises:
        ValueError: If method not found in interface
    """
    method = getattr(interface_class, method_name, None)
    if method is None:
        raise ValueError(f"Method {method_name} not found in {interface_class.__name__}")
    return inspect.signature(method)


def _is_mock_or_test_adapter(adapter_type: type) -> bool:
    """
    Check if adapter is a mock/test adapter (subject to strict validation).

    Args:
        adapter_type: The adapter class to check

    Returns:
        True if adapter is from testing/mock modules
    """
    module_name = adapter_type.__module__
    return "testing" in module_name or "mock" in module_name.lower() or "in_memory" in module_name


def _get_return_type_name(ret_annotation) -> str:
    """
    Extract canonical type name from return annotation.

    Handles string forward refs, generic types, and class objects consistently.

    Args:
        ret_annotation: The return annotation to extract name from

    Returns:
        The canonical type name
    """
    if isinstance(ret_annotation, str):
        # String forward ref - extract class name
        return ret_annotation.split("[")[0]  # Handle generics like "list[str]" -> "list"
    # Handle actual types
    if hasattr(ret_annotation, "__origin__"):
        # Generic type - use origin
        return getattr(
            ret_annotation.__origin__,
            "__name__",
            str(ret_annotation).split("'")[1] if "'" in str(ret_annotation) else str(ret_annotation),
        )
    # Regular class
    if hasattr(ret_annotation, "__name__"):
        return ret_annotation.__name__
    # Fallback to string representation, extracting the class name
    ret_str = str(ret_annotation)
    if "'" in ret_str:
        # Extract from format like "<class 'ModuleName.ClassName'>"
        return ret_str.split("'")[1].rsplit(".", maxsplit=1)[-1]
    return ret_str


def _validate_adapter_implements_interface(adapter_type: type, interface_class: type) -> bool:
    """
    Validate that an adapter implements all required methods from interface with matching signatures.

    Uses dynamic introspection of the interface to discover required methods and verify:
    - Method names are present
    - Parameter counts match (excluding 'self')
    - Parameter names match
    - Parameter types match (if annotated, lenient for production adapters)
    - Return types match (if annotated, lenient for production adapters)

    Strict signature validation applies to mock/test adapters. Production adapters
    use lenient validation to allow legacy implementations to transition gradually.

    Args:
        adapter_type: The adapter class to validate
        interface_class: The port interface class

    Returns:
        True if adapter implements all interface methods with matching signatures

    Raises:
        ValueError: If signature validation fails (with helpful error message)
    """
    # Get required methods from interface
    required_methods = _get_interface_methods(interface_class)

    # Get methods implemented by adapter
    adapter_methods = {
        name: method
        for name, method in inspect.getmembers(adapter_type, predicate=inspect.isfunction)
        if not name.startswith("_")
    }

    # Check that all required methods are implemented
    if not required_methods.issubset(adapter_methods.keys()):
        missing = required_methods - adapter_methods.keys()
        raise ValueError(f"{adapter_type.__name__} missing methods: {missing}")

    # Determine validation strictness
    is_strict = _is_mock_or_test_adapter(adapter_type)

    # Validate each method's signature
    for method_name in required_methods:
        try:
            interface_sig = _get_interface_signature(interface_class, method_name)
            adapter_sig = inspect.signature(adapter_methods[method_name])

            # Get parameters (exclude 'self')
            interface_params = list(interface_sig.parameters.values())[1:]
            adapter_params = list(adapter_sig.parameters.values())[1:]

            # Check parameter count (always strict)
            if len(interface_params) != len(adapter_params):
                raise ValueError(
                    f"{adapter_type.__name__}.{method_name}: expected {len(interface_params)} parameters "
                    f"(excluding self), got {len(adapter_params)}"
                )

            # Check parameter names (always strict)
            for iface_param, adapt_param in zip(interface_params, adapter_params, strict=True):
                if iface_param.name != adapt_param.name:
                    raise ValueError(
                        f"{adapter_type.__name__}.{method_name}: parameter '{iface_param.name}' "
                        f"expected, got '{adapt_param.name}'"
                    )

                # Validate parameter type hints (strict for mock/test, lenient for production)
                if (
                    is_strict
                    and iface_param.annotation != inspect.Parameter.empty
                    and adapt_param.annotation != inspect.Parameter.empty
                ):
                    # Skip type validation if adapter uses `Any` (allows for flexible implementations)
                    adapt_type_name = getattr(adapt_param.annotation, "__name__", str(adapt_param.annotation))
                    if adapt_type_name == "Any":
                        continue  # Allow `Any` to match any interface type

                    # Extract class name for comparison (handles forward refs like 'BoardConfig' vs BoardConfig)
                    iface_type_name = (
                        iface_param.annotation
                        if isinstance(iface_param.annotation, str)
                        else getattr(iface_param.annotation, "__name__", str(iface_param.annotation))
                    )
                    if iface_type_name != adapt_type_name:
                        raise ValueError(
                            f"{adapter_type.__name__}.{method_name}: parameter '{iface_param.name}' "
                            f"type {iface_type_name} expected, got {adapt_type_name}"
                        )

            # Check return type (strict for mock/test, lenient for production)
            if (
                is_strict
                and interface_sig.return_annotation != inspect.Signature.empty
                and adapter_sig.return_annotation != inspect.Signature.empty
            ):
                # Skip type validation if adapter uses `Any` (allows for flexible implementations)
                adapt_ret_type_name = getattr(
                    adapter_sig.return_annotation, "__name__", str(adapter_sig.return_annotation)
                )
                if adapt_ret_type_name != "Any":
                    iface_ret_name = _get_return_type_name(interface_sig.return_annotation)
                    adapt_ret_name = _get_return_type_name(adapter_sig.return_annotation)

                    if iface_ret_name != adapt_ret_name:
                        raise ValueError(
                            f"{adapter_type.__name__}.{method_name}: return type "
                            f"{iface_ret_name} expected, got {adapt_ret_name}"
                        )

            # Check async compatibility (coroutines and async generators both count as async)
            # Note: Async compatibility is checked but mismatches are logged as warnings
            # rather than errors to allow adapters in transition to async
            _iface_method = getattr(interface_class, method_name)
            is_interface_async = inspect.iscoroutinefunction(_iface_method) or inspect.isasyncgenfunction(_iface_method)
            _adapter_method = adapter_methods[method_name]
            is_adapter_async = inspect.iscoroutinefunction(_adapter_method) or inspect.isasyncgenfunction(
                _adapter_method
            )
            if is_interface_async != is_adapter_async:
                logger.warning(
                    f"{adapter_type.__name__}.{method_name}: async/sync mismatch - "
                    f"interface is {'async' if is_interface_async else 'sync'}, "
                    f"adapter is {'async' if is_adapter_async else 'sync'}"
                )

        except ValueError as e:
            raise ValueError(str(e)) from e

    return True


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


class SystemicAnalysisRegistry(AdapterRegistry[ISystemicAnalysisService]):
    """Registry for ISystemicAnalysisService adapter implementations."""

    def __init__(self):
        """Initialize the systemic analysis service registry."""
        super().__init__(ISystemicAnalysisService)

    def _is_valid_adapter(self, adapter_type: type[ISystemicAnalysisService]) -> bool:
        """Validate that an adapter implements ISystemicAnalysisService."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class EnvironmentRepairRegistry(AdapterRegistry[IEnvironmentRepairService]):
    """Registry for IEnvironmentRepairService adapter implementations."""

    def __init__(self):
        """Initialize the environment repair service registry."""
        super().__init__(IEnvironmentRepairService)

    def _is_valid_adapter(self, adapter_type: type[IEnvironmentRepairService]) -> bool:
        """Validate that an adapter implements IEnvironmentRepairService."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class CIPipelineServiceRegistry(AdapterRegistry[ICIPipelineService]):
    """Registry for ICIPipelineService adapter implementations."""

    def __init__(self):
        """Initialize the CI pipeline service registry."""
        super().__init__(ICIPipelineService)

    def _is_valid_adapter(self, adapter_type: type[ICIPipelineService]) -> bool:
        """Validate that an adapter implements ICIPipelineService."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)


class PRReviewCycleServiceRegistry(AdapterRegistry[IPRReviewCycle]):
    """Registry for IPRReviewCycle adapter implementations."""

    def __init__(self):
        """Initialize the PR review cycle service registry."""
        super().__init__(IPRReviewCycle)

    def _is_valid_adapter(self, adapter_type: type[IPRReviewCycle]) -> bool:
        """Validate that an adapter implements IPRReviewCycle."""
        return _validate_adapter_implements_interface(adapter_type, self._port_interface)
