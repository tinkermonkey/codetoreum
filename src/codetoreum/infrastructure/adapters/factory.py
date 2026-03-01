"""
Adapter factory for creating fully configured adapter instances.

Provides:
- Configuration-driven adapter instantiation
- Automatic resilience decorator application
- Dependency injection support
- Registry integration
"""

import logging
import threading
from dataclasses import dataclass
from typing import Any, TypeVar

# Import production adapters
from codetoreum.adapters.secondary import (
    ClaudeCodeAdapter,
    DockerContainerAdapter,
    GitHubTicketAdapter,
    GitRepositoryAdapter,
)

# Import testing adapters
from codetoreum.adapters.testing import (
    FakeContainerAdapter,
    InMemoryEventStore,
    InMemoryRepositoryAdapter,
    InMemoryTicketAdapter,
    MockLLMAdapter,
)
from codetoreum.infrastructure.adapters.registries import (
    ContainerRegistry,
    EventStoreRegistry,
    LLMProviderRegistry,
    RepositoryRegistry,
    TicketSystemRegistry,
)
from codetoreum.infrastructure.resilience import (
    CLAUDE_RESILIENCE_CONFIG,
    CONTAINER_RESILIENCE_CONFIG,
    GITHUB_RESILIENCE_CONFIG,
    REPOSITORY_RESILIENCE_CONFIG,
    OperationMode,
    ResilienceFactory,
    ServiceResilienceConfig,
)
from codetoreum.ports.output.container import IContainer
from codetoreum.ports.output.event_store import IEventStore
from codetoreum.ports.output.llm_provider import ILLMProvider
from codetoreum.ports.output.repository import IRepository
from codetoreum.ports.output.ticket_system import ITicketSystem

logger = logging.getLogger(__name__)


T = TypeVar("T")


@dataclass
class AdapterFactoryConfig:
    """Configuration for the adapter factory."""

    operation_mode: OperationMode = OperationMode.PRODUCTION
    enable_resilience: bool = True
    custom_resilience_configs: dict[str, ServiceResilienceConfig] | None = None


class AdapterFactory:
    """
    Factory for creating fully configured adapter instances.

    Handles:
    - Adapter instantiation from registries
    - Configuration management
    - Resilience decorator application
    - Dependency injection

    Thread-safe for concurrent adapter creation and configuration changes.
    """

    def __init__(self, config: AdapterFactoryConfig | None = None):
        """
        Initialize the adapter factory.

        Args:
            config: Factory configuration
        """
        self._config = config or AdapterFactoryConfig()
        self._resilience_factory = ResilienceFactory(mode=self._config.operation_mode)

        # Thread safety lock
        self._lock = threading.RLock()

        # Initialize registries
        self._ticket_system_registry = TicketSystemRegistry()
        self._llm_provider_registry = LLMProviderRegistry()
        self._container_registry = ContainerRegistry()
        self._repository_registry = RepositoryRegistry()
        self._event_store_registry = EventStoreRegistry()

        # Dependency injection container
        self._dependencies: dict[str, Any] = {}

        # Register default adapters
        self._register_default_adapters()

    def _register_default_adapters(self) -> None:
        """Register default adapter implementations."""
        # Ticket System Adapters
        self._ticket_system_registry.register(
            name="github",
            adapter_type=GitHubTicketAdapter,
            description="GitHub Issues and Projects integration",
            version="1.0.0",
            tags=["production", "github", "issues"],
            set_as_default=True,
        )
        self._ticket_system_registry.register(
            name="in_memory",
            adapter_type=InMemoryTicketAdapter,
            description="In-memory ticket system for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
        )

        # LLM Provider Adapters
        self._llm_provider_registry.register(
            name="claude_code",
            adapter_type=ClaudeCodeAdapter,
            description="Claude Code CLI integration",
            version="1.0.0",
            tags=["production", "claude", "anthropic"],
            set_as_default=True,
        )
        self._llm_provider_registry.register(
            name="mock",
            adapter_type=MockLLMAdapter,
            description="Mock LLM provider for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
        )

        # Container Adapters
        self._container_registry.register(
            name="docker",
            adapter_type=DockerContainerAdapter,
            description="Docker container runtime",
            version="1.0.0",
            tags=["production", "docker"],
            set_as_default=True,
        )
        self._container_registry.register(
            name="fake",
            adapter_type=FakeContainerAdapter,
            description="Fake container adapter for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
        )

        # Repository Adapters
        self._repository_registry.register(
            name="git",
            adapter_type=GitRepositoryAdapter,
            description="Git repository operations",
            version="1.0.0",
            tags=["production", "git"],
            set_as_default=True,
        )
        self._repository_registry.register(
            name="in_memory",
            adapter_type=InMemoryRepositoryAdapter,
            description="In-memory repository for testing",
            version="1.0.0",
            tags=["testing", "simulation", "mock"],
        )

        # Event Store Adapters
        self._event_store_registry.register(
            name="in_memory",
            adapter_type=InMemoryEventStore,
            description="In-memory event store",
            version="1.0.0",
            tags=["testing", "simulation", "production"],
            set_as_default=True,
        )

    # Registry access methods

    @property
    def ticket_system_registry(self) -> TicketSystemRegistry:
        """Get the ticket system registry."""
        return self._ticket_system_registry

    @property
    def llm_provider_registry(self) -> LLMProviderRegistry:
        """Get the LLM provider registry."""
        return self._llm_provider_registry

    @property
    def container_registry(self) -> ContainerRegistry:
        """Get the container registry."""
        return self._container_registry

    @property
    def repository_registry(self) -> RepositoryRegistry:
        """Get the repository registry."""
        return self._repository_registry

    @property
    def event_store_registry(self) -> EventStoreRegistry:
        """Get the event store registry."""
        return self._event_store_registry

    # Dependency injection methods

    def register_dependency(self, name: str, instance: Any) -> None:
        """
        Register a dependency for injection.

        Args:
            name: Dependency name
            instance: Dependency instance
        """
        with self._lock:
            self._dependencies[name] = instance
            logger.debug(f"Registered dependency: {name}")

    def get_dependency(self, name: str) -> Any:
        """
        Get a registered dependency.

        Args:
            name: Dependency name

        Returns:
            The dependency instance

        Raises:
            KeyError: If dependency is not registered
        """
        with self._lock:
            if name not in self._dependencies:
                message = f"Dependency '{name}' is not registered"
                raise KeyError(message)
            return self._dependencies[name]

    def has_dependency(self, name: str) -> bool:
        """
        Check if a dependency is registered.

        Args:
            name: Dependency name

        Returns:
            True if dependency is registered
        """
        with self._lock:
            return name in self._dependencies

    # Adapter creation methods

    def create_ticket_system(
        self,
        adapter_name: str | None = None,
        adapter_config: Any | None = None,
        resilience_config: ServiceResilienceConfig | None = None,
        **kwargs,
    ) -> ITicketSystem:
        """
        Create a ticket system adapter instance.

        Args:
            adapter_name: Name of adapter to use (default: registry default)
            adapter_config: Configuration for the adapter
            resilience_config: Custom resilience configuration
            **kwargs: Additional arguments for adapter constructor

        Returns:
            Configured ticket system adapter with resilience applied

        Raises:
            KeyError: If adapter is not registered
        """
        # Determine adapter name
        if adapter_name is None:
            adapter_name = self._ticket_system_registry.get_default_name()
            if adapter_name is None:
                message = "No default ticket system adapter configured"
                raise ValueError(message)

        logger.info(f"Creating ticket system adapter: {adapter_name}")

        # Create base adapter instance
        if adapter_config is not None:
            kwargs["config"] = adapter_config

        adapter = self._ticket_system_registry.create_instance(adapter_name, **kwargs)

        # Apply resilience if enabled
        if self._config.enable_resilience:
            # Convert ServiceResilienceConfig to service_config dict
            service_config = None
            try:
                if resilience_config:
                    if hasattr(resilience_config, "to_dict"):
                        service_config = resilience_config.to_dict()
                    else:
                        message = f"resilience_config must have to_dict() method, got {type(resilience_config)}"
                        raise TypeError(message)
                else:
                    default_config = self._get_resilience_config("ticket_system", GITHUB_RESILIENCE_CONFIG)
                    if hasattr(default_config, "to_dict"):
                        service_config = default_config.to_dict()
                    else:
                        service_config = None

                adapter = self._resilience_factory.create_resilient_ticket_system(
                    adapter, service_config=service_config
                )
            except Exception as e:
                logger.error(
                    f"Failed to apply resilience to ticket system adapter: {e}",
                    extra={"error_id": "ERR_CONFIGURATION_ERROR"},
                )
                raise

        return adapter

    def create_llm_provider(
        self,
        adapter_name: str | None = None,
        adapter_config: Any | None = None,
        resilience_config: ServiceResilienceConfig | None = None,
        **kwargs,
    ) -> ILLMProvider:
        """
        Create an LLM provider adapter instance.

        Args:
            adapter_name: Name of adapter to use (default: registry default)
            adapter_config: Configuration for the adapter
            resilience_config: Custom resilience configuration
            **kwargs: Additional arguments for adapter constructor

        Returns:
            Configured LLM provider adapter with resilience applied

        Raises:
            KeyError: If adapter is not registered
        """
        # Determine adapter name
        if adapter_name is None:
            adapter_name = self._llm_provider_registry.get_default_name()
            if adapter_name is None:
                message = "No default LLM provider adapter configured"
                raise ValueError(message)

        logger.info(f"Creating LLM provider adapter: {adapter_name}")

        # Create base adapter instance
        if adapter_config is not None:
            kwargs["config"] = adapter_config

        adapter = self._llm_provider_registry.create_instance(adapter_name, **kwargs)

        # Apply resilience if enabled
        if self._config.enable_resilience:
            # Convert ServiceResilienceConfig to service_config dict
            service_config = None
            try:
                if resilience_config:
                    if hasattr(resilience_config, "to_dict"):
                        service_config = resilience_config.to_dict()
                    else:
                        message = f"resilience_config must have to_dict() method, got {type(resilience_config)}"
                        raise TypeError(message)
                else:
                    default_config = self._get_resilience_config("llm_provider", CLAUDE_RESILIENCE_CONFIG)
                    if hasattr(default_config, "to_dict"):
                        service_config = default_config.to_dict()
                    else:
                        service_config = None

                adapter = self._resilience_factory.create_resilient_llm_provider(adapter, service_config=service_config)
            except Exception as e:
                logger.error(
                    f"Failed to apply resilience to LLM provider adapter: {e}",
                    extra={"error_id": "ERR_CONFIGURATION_ERROR"},
                )
                raise

        return adapter

    def create_container(
        self,
        adapter_name: str | None = None,
        adapter_config: Any | None = None,
        resilience_config: ServiceResilienceConfig | None = None,
        **kwargs,
    ) -> IContainer:
        """
        Create a container adapter instance.

        Args:
            adapter_name: Name of adapter to use (default: registry default)
            adapter_config: Configuration for the adapter
            resilience_config: Custom resilience configuration
            **kwargs: Additional arguments for adapter constructor

        Returns:
            Configured container adapter with resilience applied

        Raises:
            KeyError: If adapter is not registered
        """
        # Determine adapter name
        if adapter_name is None:
            adapter_name = self._container_registry.get_default_name()
            if adapter_name is None:
                message = "No default container adapter configured"
                raise ValueError(message)

        logger.info(f"Creating container adapter: {adapter_name}")

        # Create base adapter instance
        if adapter_config is not None:
            kwargs["config"] = adapter_config

        adapter = self._container_registry.create_instance(adapter_name, **kwargs)

        # Apply resilience if enabled
        if self._config.enable_resilience:
            # Convert ServiceResilienceConfig to service_config dict
            service_config = None
            try:
                if resilience_config:
                    if hasattr(resilience_config, "to_dict"):
                        service_config = resilience_config.to_dict()
                    else:
                        message = f"resilience_config must have to_dict() method, got {type(resilience_config)}"
                        raise TypeError(message)
                else:
                    default_config = self._get_resilience_config("container", CONTAINER_RESILIENCE_CONFIG)
                    if hasattr(default_config, "to_dict"):
                        service_config = default_config.to_dict()
                    else:
                        service_config = None

                adapter = self._resilience_factory.create_resilient_container(adapter, service_config=service_config)
            except Exception as e:
                logger.error(
                    f"Failed to apply resilience to container adapter: {e}",
                    extra={"error_id": "ERR_CONFIGURATION_ERROR"},
                )
                raise

        return adapter

    def create_repository(
        self,
        adapter_name: str | None = None,
        adapter_config: Any | None = None,
        resilience_config: ServiceResilienceConfig | None = None,
        **kwargs,
    ) -> IRepository:
        """
        Create a repository adapter instance.

        Args:
            adapter_name: Name of adapter to use (default: registry default)
            adapter_config: Configuration for the adapter
            resilience_config: Custom resilience configuration
            **kwargs: Additional arguments for adapter constructor

        Returns:
            Configured repository adapter with resilience applied

        Raises:
            KeyError: If adapter is not registered
        """
        # Determine adapter name
        if adapter_name is None:
            adapter_name = self._repository_registry.get_default_name()
            if adapter_name is None:
                message = "No default repository adapter configured"
                raise ValueError(message)

        logger.info(f"Creating repository adapter: {adapter_name}")

        # Create base adapter instance
        if adapter_config is not None:
            kwargs["config"] = adapter_config

        adapter = self._repository_registry.create_instance(adapter_name, **kwargs)

        # Apply resilience if enabled
        if self._config.enable_resilience:
            # Convert ServiceResilienceConfig to service_config dict
            service_config = None
            try:
                if resilience_config:
                    if hasattr(resilience_config, "to_dict"):
                        service_config = resilience_config.to_dict()
                    else:
                        message = f"resilience_config must have to_dict() method, got {type(resilience_config)}"
                        raise TypeError(message)
                else:
                    default_config = self._get_resilience_config("repository", REPOSITORY_RESILIENCE_CONFIG)
                    if hasattr(default_config, "to_dict"):
                        service_config = default_config.to_dict()
                    else:
                        service_config = None

                adapter = self._resilience_factory.create_resilient_repository(adapter, service_config=service_config)
            except Exception as e:
                logger.error(
                    f"Failed to apply resilience to repository adapter: {e}",
                    extra={"error_id": "ERR_CONFIGURATION_ERROR"},
                )
                raise

        return adapter

    def create_event_store(self, adapter_name: str | None = None, **kwargs) -> IEventStore:
        """
        Create an event store adapter instance.

        Note: Event stores do not have resilience decorators applied because they
        are internal infrastructure components with different reliability requirements.
        Event stores should implement their own internal retry logic and persistence
        guarantees. Applying external resilience patterns like circuit breakers could
        interfere with event sourcing semantics (e.g., event ordering, causality).

        Args:
            adapter_name: Name of adapter to use (default: registry default)
            **kwargs: Additional arguments for adapter constructor

        Returns:
            Configured event store adapter (without resilience decorators)

        Raises:
            KeyError: If adapter is not registered
            ValueError: If no default adapter is configured
        """
        # Determine adapter name
        if adapter_name is None:
            adapter_name = self._event_store_registry.get_default_name()
            if adapter_name is None:
                message = "No default event store adapter configured"
                raise ValueError(message)

        logger.info(f"Creating event store adapter: {adapter_name}")

        # Create adapter instance (no resilience applied)
        adapter = self._event_store_registry.create_instance(adapter_name, **kwargs)

        return adapter

    def _get_resilience_config(
        self, service_type: str, default_config: ServiceResilienceConfig
    ) -> ServiceResilienceConfig:
        """
        Get resilience configuration for a service type.

        Args:
            service_type: Type of service
            default_config: Default configuration

        Returns:
            Resilience configuration
        """
        if self._config.custom_resilience_configs and service_type in self._config.custom_resilience_configs:
            return self._config.custom_resilience_configs[service_type]
        return default_config

    def set_operation_mode(self, mode: OperationMode) -> None:
        """
        Set the operation mode for the factory.

        This affects which resilience components are used.
        Thread-safe operation.

        Args:
            mode: Operation mode
        """
        with self._lock:
            self._config.operation_mode = mode
            self._resilience_factory = ResilienceFactory(mode=mode)
            logger.info(f"Set operation mode to: {mode.value}")

    def get_operation_mode(self) -> OperationMode:
        """
        Get the current operation mode.

        Returns:
            Current operation mode
        """
        with self._lock:
            return self._config.operation_mode

    def enable_resilience(self, enable: bool = True) -> None:
        """
        Enable or disable resilience decorator application.

        Thread-safe operation.

        Args:
            enable: Whether to enable resilience
        """
        with self._lock:
            self._config.enable_resilience = enable
            logger.info(f"Resilience {'enabled' if enable else 'disabled'}")

    def is_resilience_enabled(self) -> bool:
        """
        Check if resilience is enabled.

        Returns:
            True if resilience is enabled
        """
        with self._lock:
            return self._config.enable_resilience
