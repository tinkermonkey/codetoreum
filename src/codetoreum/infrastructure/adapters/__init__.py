"""
Adapter infrastructure module.

Provides:
- Adapter registries for each port interface
- Adapter factory with configuration-driven instantiation
- Dependency injection support
"""

from codetoreum.infrastructure.adapters.factory import (
    AdapterFactory,
    AdapterFactoryConfig,
)
from codetoreum.infrastructure.adapters.registries import (
    ContainerRegistry,
    EventStoreRegistry,
    LLMProviderRegistry,
    RepositoryRegistry,
    StorageRegistry,
    TicketSystemRegistry,
)
from codetoreum.infrastructure.adapters.registry_base import (
    AdapterMetadata,
    AdapterRegistry,
)

__all__ = [
    # Base registry
    "AdapterRegistry",
    "AdapterMetadata",
    # Specific registries
    "TicketSystemRegistry",
    "LLMProviderRegistry",
    "ContainerRegistry",
    "RepositoryRegistry",
    "EventStoreRegistry",
    "StorageRegistry",
    # Factory
    "AdapterFactory",
    "AdapterFactoryConfig",
]
