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
from typing import Type

from codetoreum.infrastructure.adapters.registry_base import AdapterRegistry
from codetoreum.ports.output.ticket_system import ITicketSystem
from codetoreum.ports.output.llm_provider import ILLMProvider
from codetoreum.ports.output.container import IContainer
from codetoreum.ports.output.repository import IRepository
from codetoreum.ports.output.event_store import IEventStore
from codetoreum.ports.output.storage import IStorage


class TicketSystemRegistry(AdapterRegistry[ITicketSystem]):
    """Registry for ITicketSystem adapter implementations."""

    def __init__(self):
        """Initialize the ticket system registry."""
        super().__init__(ITicketSystem)

    def _is_valid_adapter(self, adapter_type: Type[ITicketSystem]) -> bool:
        """
        Validate that an adapter implements ITicketSystem.

        Checks that the adapter class implements all required methods
        from the ITicketSystem interface.

        Args:
            adapter_type: The adapter class to validate

        Returns:
            True if adapter implements all ITicketSystem methods
        """
        required_methods = {
            'get_work_item',
            'create_work_item',
            'update_work_item',
            'list_work_items',
            'search_work_items',
            'get_work_item_stream',
            'add_comment',
            'get_comments',
            'link_work_items',
            'register_webhook',
            'unregister_webhook'
        }

        adapter_methods = {
            name for name, _ in inspect.getmembers(adapter_type, predicate=inspect.isfunction)
        }

        return required_methods.issubset(adapter_methods)


class LLMProviderRegistry(AdapterRegistry[ILLMProvider]):
    """Registry for ILLMProvider adapter implementations."""

    def __init__(self):
        """Initialize the LLM provider registry."""
        super().__init__(ILLMProvider)

    def _is_valid_adapter(self, adapter_type: Type[ILLMProvider]) -> bool:
        """
        Validate that an adapter implements ILLMProvider.

        Checks that the adapter class implements all required methods
        from the ILLMProvider interface.

        Args:
            adapter_type: The adapter class to validate

        Returns:
            True if adapter implements all ILLMProvider methods
        """
        required_methods = {
            'execute',
            'execute_with_tools',
            'stream_completion',
            'create_conversation',
            'continue_conversation',
            'get_model_info',
            'list_available_models',
            'count_tokens',
            'get_usage_stats'
        }

        adapter_methods = {
            name for name, _ in inspect.getmembers(adapter_type, predicate=inspect.isfunction)
        }

        return required_methods.issubset(adapter_methods)


class ContainerRegistry(AdapterRegistry[IContainer]):
    """Registry for IContainer adapter implementations."""

    def __init__(self):
        """Initialize the container registry."""
        super().__init__(IContainer)

    def _is_valid_adapter(self, adapter_type: Type[IContainer]) -> bool:
        """
        Validate that an adapter implements IContainer.

        Checks that the adapter class implements all required methods
        from the IContainer interface.

        Args:
            adapter_type: The adapter class to validate

        Returns:
            True if adapter implements all IContainer methods
        """
        required_methods = {
            'run',
            'create',
            'start',
            'stop',
            'remove',
            'kill',
            'logs',
            'status',
            'exec',
            'list_containers',
            'pull_image',
            'image_exists',
            'inspect',
            'wait',
            'copy_to_container',
            'copy_from_container'
        }

        adapter_methods = {
            name for name, _ in inspect.getmembers(adapter_type, predicate=inspect.isfunction)
        }

        return required_methods.issubset(adapter_methods)


class RepositoryRegistry(AdapterRegistry[IRepository]):
    """Registry for IRepository adapter implementations."""

    def __init__(self):
        """Initialize the repository registry."""
        super().__init__(IRepository)

    def _is_valid_adapter(self, adapter_type: Type[IRepository]) -> bool:
        """
        Validate that an adapter implements IRepository.

        Checks that the adapter class implements all required methods
        from the IRepository interface.

        Args:
            adapter_type: The adapter class to validate

        Returns:
            True if adapter implements all IRepository methods
        """
        required_methods = {
            'clone',
            'checkout',
            'create_branch',
            'commit',
            'push',
            'pull',
            'fetch',
            'diff',
            'status',
            'list_branches',
            'merge',
            'get_file_content',
            'get_commit_info',
            'get_commit_history',
            'add_remote',
            'remove_remote'
        }

        adapter_methods = {
            name for name, _ in inspect.getmembers(adapter_type, predicate=inspect.isfunction)
        }

        return required_methods.issubset(adapter_methods)


class EventStoreRegistry(AdapterRegistry[IEventStore]):
    """Registry for IEventStore adapter implementations."""

    def __init__(self):
        """Initialize the event store registry."""
        super().__init__(IEventStore)

    def _is_valid_adapter(self, adapter_type: Type[IEventStore]) -> bool:
        """
        Validate that an adapter implements IEventStore.

        Checks that the adapter class implements all required methods
        from the IEventStore interface.

        Args:
            adapter_type: The adapter class to validate

        Returns:
            True if adapter implements all IEventStore methods
        """
        required_methods = {
            'append',
            'get_events',
            'get_events_since',
            'stream_events',
            'get_stream_version',
            'stream_exists',
            'save_snapshot',
            'get_latest_snapshot',
            'delete_stream',
            'get_all_stream_ids',
            'get_events_by_type',
            'get_events_by_correlation_id',
            'replay_events',
            'get_statistics'
        }

        adapter_methods = {
            name for name, _ in inspect.getmembers(adapter_type, predicate=inspect.isfunction)
        }

        return required_methods.issubset(adapter_methods)


class StorageRegistry(AdapterRegistry[IStorage]):
    """Registry for IStorage adapter implementations."""

    def __init__(self):
        """Initialize the storage registry."""
        super().__init__(IStorage)

    def _is_valid_adapter(self, adapter_type: Type[IStorage]) -> bool:
        """
        Validate that an adapter implements IStorage.

        Checks that the adapter class implements all required methods
        from the IStorage interface.

        Args:
            adapter_type: The adapter class to validate

        Returns:
            True if adapter implements all IStorage methods
        """
        required_methods = {
            'upload',
            'upload_from_file',
            'download',
            'download_to_file',
            'delete',
            'delete_many',
            'list_files',
            'exists',
            'get_metadata',
            'update_metadata',
            'copy',
            'move',
            'generate_presigned_url',
            'get_size',
            'get_content_type',
            'list_prefixes',
            'get_storage_info'
        }

        adapter_methods = {
            name for name, _ in inspect.getmembers(adapter_type, predicate=inspect.isfunction)
        }

        return required_methods.issubset(adapter_methods)
