"""
Base adapter registry implementation.

Provides generic registry functionality for managing adapter implementations.
Thread-safe for concurrent registration and lookup operations.
"""

import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

T = TypeVar("T")  # Port interface type


@dataclass
class AdapterMetadata:
    """Metadata about a registered adapter."""

    name: str
    adapter_type: type
    description: str
    version: str
    tags: list[str]
    registered_at: datetime
    config_schema: dict[str, Any] | None = None

    def matches_tags(self, tags: list[str]) -> bool:
        """Check if adapter has all specified tags."""
        return all(tag in self.tags for tag in tags)


class AdapterRegistry(ABC, Generic[T]):
    """
    Base adapter registry for managing adapter implementations.

    Provides thread-safe registration, lookup, and listing of adapters
    that implement a specific port interface.

    Type parameter T represents the port interface type (e.g., ITicketSystem).
    """

    def __init__(self, port_interface: type[T]):
        """
        Initialize the adapter registry.

        Args:
            port_interface: The port interface class this registry manages
        """
        self._port_interface: type[T] = port_interface
        self._adapters: dict[str, type[T]] = {}
        self._metadata: dict[str, AdapterMetadata] = {}
        self._factories: dict[str, Callable[..., T]] = {}
        self._lock: threading.RLock = threading.RLock()
        self._default_adapter: str | None = None

    @property
    def port_interface(self) -> type[T]:
        """Get the port interface this registry manages."""
        return self._port_interface

    def register(
        self,
        name: str,
        adapter_type: type[T],
        description: str = "",
        version: str = "1.0.0",
        tags: list[str] | None = None,
        config_schema: dict[str, Any] | None = None,
        factory: Callable[..., T] | None = None,
        set_as_default: bool = False,
    ) -> None:
        """
        Register an adapter implementation.

        Args:
            name: Unique name for the adapter
            adapter_type: The adapter class
            description: Human-readable description
            version: Semantic version string
            tags: Optional list of tags (e.g., ["production", "github"])
            config_schema: Optional JSON schema for adapter configuration
            factory: Optional factory function for creating instances
            set_as_default: Whether to set this as the default adapter

        Raises:
            ValueError: If name is already registered or adapter doesn't implement interface
        """
        with self._lock:
            if name in self._adapters:
                message = f"Adapter '{name}' is already registered"
                raise ValueError(message)

            # Verify adapter implements the port interface
            if not self._is_valid_adapter(adapter_type):
                message = f"Adapter {adapter_type.__name__} does not implement {self._port_interface.__name__}"
                raise ValueError(message)

            self._adapters[name] = adapter_type
            self._metadata[name] = AdapterMetadata(
                name=name,
                adapter_type=adapter_type,
                description=description,
                version=version,
                tags=tags or [],
                registered_at=datetime.now(UTC),
                config_schema=config_schema,
            )

            if factory:
                self._factories[name] = factory

            if set_as_default or self._default_adapter is None:
                self._default_adapter = name

    def unregister(self, name: str) -> None:
        """
        Unregister an adapter.

        Args:
            name: Name of the adapter to unregister

        Raises:
            KeyError: If adapter is not registered
        """
        with self._lock:
            if name not in self._adapters:
                message = f"Adapter '{name}' is not registered"
                raise KeyError(message)

            del self._adapters[name]
            del self._metadata[name]
            if name in self._factories:
                del self._factories[name]

            # Clear default if it was this adapter
            if self._default_adapter == name:
                self._default_adapter = None

    def get(self, name: str) -> type[T]:
        """
        Get a registered adapter class by name.

        Args:
            name: Name of the adapter

        Returns:
            The adapter class

        Raises:
            KeyError: If adapter is not registered
        """
        with self._lock:
            if name not in self._adapters:
                message = f"Adapter '{name}' is not registered"
                raise KeyError(message)
            return self._adapters[name]

    def get_default(self) -> type[T] | None:
        """
        Get the default adapter class.

        Returns:
            The default adapter class, or None if no default is set
        """
        with self._lock:
            if self._default_adapter is None:
                return None
            return self._adapters.get(self._default_adapter)

    def get_default_name(self) -> str | None:
        """
        Get the name of the default adapter.

        Returns:
            The default adapter name, or None if no default is set
        """
        with self._lock:
            return self._default_adapter

    def set_default(self, name: str) -> None:
        """
        Set the default adapter.

        Args:
            name: Name of the adapter to set as default

        Raises:
            KeyError: If adapter is not registered
        """
        with self._lock:
            if name not in self._adapters:
                message = f"Adapter '{name}' is not registered"
                raise KeyError(message)
            self._default_adapter = name

    def get_metadata(self, name: str) -> AdapterMetadata:
        """
        Get metadata for a registered adapter.

        Args:
            name: Name of the adapter

        Returns:
            Adapter metadata

        Raises:
            KeyError: If adapter is not registered
        """
        with self._lock:
            if name not in self._metadata:
                message = f"Adapter '{name}' is not registered"
                raise KeyError(message)
            return self._metadata[name]

    def list_adapters(self) -> list[str]:
        """
        List all registered adapter names.

        Returns:
            List of adapter names
        """
        with self._lock:
            return list(self._adapters.keys())

    def list_by_tags(self, tags: list[str]) -> list[str]:
        """
        List adapters that match all specified tags.

        Args:
            tags: List of tags to match

        Returns:
            List of matching adapter names
        """
        with self._lock:
            return [name for name, metadata in self._metadata.items() if metadata.matches_tags(tags)]

    def has_adapter(self, name: str) -> bool:
        """
        Check if an adapter is registered.

        Args:
            name: Name of the adapter

        Returns:
            True if adapter is registered
        """
        with self._lock:
            return name in self._adapters

    def create_instance(self, name: str, *args, **kwargs) -> T:
        """
        Create an instance of a registered adapter.

        Uses the registered factory if available, otherwise calls the
        adapter class constructor.

        Args:
            name: Name of the adapter
            *args: Positional arguments for adapter constructor/factory
            **kwargs: Keyword arguments for adapter constructor/factory

        Returns:
            Adapter instance

        Raises:
            KeyError: If adapter is not registered
        """
        with self._lock:
            if name not in self._adapters:
                message = f"Adapter '{name}' is not registered"
                raise KeyError(message)

            if name in self._factories:
                return self._factories[name](*args, **kwargs)
            return self._adapters[name](*args, **kwargs)

    def clear(self) -> None:
        """Clear all registered adapters."""
        with self._lock:
            self._adapters.clear()
            self._metadata.clear()
            self._factories.clear()
            self._default_adapter = None

    @abstractmethod
    def _is_valid_adapter(self, adapter_type: type[T]) -> bool:
        """
        Validate that an adapter implements the port interface.

        Args:
            adapter_type: The adapter class to validate

        Returns:
            True if adapter is valid
        """

    def __len__(self) -> int:
        """Get the number of registered adapters."""
        with self._lock:
            return len(self._adapters)

    def __contains__(self, name: str) -> bool:
        """Check if an adapter is registered."""
        return self.has_adapter(name)

    def __repr__(self) -> str:
        """String representation of the registry."""
        with self._lock:
            count = len(self._adapters)
            default = self._default_adapter or "None"
            return (
                f"{self.__class__.__name__}(port={self._port_interface.__name__}, adapters={count}, default={default})"
            )
