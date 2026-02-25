"""
Specific adapter registries for each port interface.

Provides registries for managing implementations of:
- ITicketSystem
- ILLMProvider
- IContainer
- IRepository
- IEventStore
- IStorage
"""

import inspect

from codetoreum.infrastructure.adapters.registry_base import AdapterRegistry
from codetoreum.ports.output.container import IContainer
from codetoreum.ports.output.event_store import IEventStore
from codetoreum.ports.output.llm_provider import ILLMProvider
from codetoreum.ports.output.repository import IRepository
from codetoreum.ports.output.storage import IStorage
from codetoreum.ports.output.ticket_system import ITicketSystem


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


def _validate_adapter_implements_interface(
    adapter_type: type,
    interface_class: type
) -> bool:
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
        name for name, _ in inspect.getmembers(adapter_type, predicate=inspect.isfunction)
        if not name.startswith("_")
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
