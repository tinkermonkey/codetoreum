"""
Simplified unit tests for adapter factory.

Tests configuration-driven instantiation and registry integration.
"""

import pytest

from codetoreum.adapters.testing import (
    InMemoryEventStore,
    InMemoryTicketAdapter,
)
from codetoreum.infrastructure.adapters import AdapterFactory, AdapterFactoryConfig
from codetoreum.infrastructure.resilience import OperationMode
from codetoreum.ports.output.container import IContainer
from codetoreum.ports.output.event_store import IEventStore
from codetoreum.ports.output.repository import IRepository
from codetoreum.ports.output.ticket_system import ITicketSystem


class TestAdapterFactoryConfig:
    """Test cases for AdapterFactoryConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = AdapterFactoryConfig()
        assert config.operation_mode == OperationMode.PRODUCTION
        assert config.enable_resilience is True
        assert config.custom_resilience_configs is None

    def test_custom_config(self):
        """Test custom configuration."""
        config = AdapterFactoryConfig(operation_mode=OperationMode.SIMULATION, enable_resilience=False)

        assert config.operation_mode == OperationMode.SIMULATION
        assert config.enable_resilience is False


class TestAdapterFactory:
    """Test cases for AdapterFactory."""

    def test_initialization(self):
        """Test factory initialization."""
        factory = AdapterFactory()
        assert factory.get_operation_mode() == OperationMode.PRODUCTION
        assert factory.is_resilience_enabled() is True

    def test_initialization_with_config(self):
        """Test factory initialization with custom config."""
        config = AdapterFactoryConfig(operation_mode=OperationMode.SIMULATION, enable_resilience=False)

        factory = AdapterFactory(config)
        assert factory.get_operation_mode() == OperationMode.SIMULATION
        assert factory.is_resilience_enabled() is False

    def test_registries_initialized(self):
        """Test that all registries are initialized."""
        factory = AdapterFactory()

        assert factory.ticket_system_registry is not None
        assert factory.container_registry is not None
        assert factory.repository_registry is not None
        assert factory.event_store_registry is not None

    def test_default_adapters_registered(self):
        """Test that default adapters are registered."""
        factory = AdapterFactory()

        # Check ticket system adapters
        assert factory.ticket_system_registry.has_adapter("github")
        assert factory.ticket_system_registry.has_adapter("in_memory")
        assert factory.ticket_system_registry.get_default_name() == "github"

        # Check LLM provider adapters

        # Check container adapters
        assert factory.container_registry.has_adapter("docker")
        assert factory.container_registry.has_adapter("fake")
        assert factory.container_registry.get_default_name() == "docker"

        # Check repository adapters
        assert factory.repository_registry.has_adapter("git")
        assert factory.repository_registry.has_adapter("in_memory")
        assert factory.repository_registry.get_default_name() == "git"

        # Check event store adapters
        assert factory.event_store_registry.has_adapter("in_memory")
        assert factory.event_store_registry.get_default_name() == "in_memory"


class TestAdapterCreation:
    """Test cases for adapter creation."""

    def test_create_in_memory_ticket_system(self):
        """Test creating in-memory ticket system adapter."""
        factory = AdapterFactory()

        adapter = factory.create_ticket_system(adapter_name="in_memory")
        assert isinstance(adapter, ITicketSystem)

    def test_create_fake_container(self):
        """Test creating fake container adapter."""
        factory = AdapterFactory()

        adapter = factory.create_container(adapter_name="fake")
        assert isinstance(adapter, IContainer)

    def test_create_in_memory_repository(self):
        """Test creating in-memory repository adapter."""
        factory = AdapterFactory()

        adapter = factory.create_repository(adapter_name="in_memory")
        assert isinstance(adapter, IRepository)

    def test_create_event_store(self):
        """Test creating event store adapter."""
        factory = AdapterFactory()

        adapter = factory.create_event_store()
        assert isinstance(adapter, InMemoryEventStore)

    def test_create_nonexistent_raises_error(self):
        """Test that creating nonexistent adapter raises error."""
        factory = AdapterFactory()

        with pytest.raises(KeyError):
            factory.create_ticket_system(adapter_name="nonexistent")


class TestResilienceIntegration:
    """Test resilience integration."""

    def test_create_with_resilience_disabled(self):
        """Test creating adapter with resilience disabled."""
        config = AdapterFactoryConfig(enable_resilience=False)
        factory = AdapterFactory(config)

        adapter = factory.create_ticket_system(adapter_name="in_memory")
        # Adapter should be unwrapped (direct instance)
        assert isinstance(adapter, InMemoryTicketAdapter)

    def test_create_in_simulation_mode(self):
        """Test creating adapter in simulation mode."""
        config = AdapterFactoryConfig(operation_mode=OperationMode.SIMULATION)
        factory = AdapterFactory(config)

        adapter = factory.create_ticket_system(adapter_name="in_memory")
        assert isinstance(adapter, ITicketSystem)


class TestDependencyInjection:
    """Test cases for dependency injection."""

    def test_register_dependency(self):
        """Test registering a dependency."""
        factory = AdapterFactory()

        event_store = InMemoryEventStore()
        factory.register_dependency("event_store", event_store)

        assert factory.has_dependency("event_store")
        assert factory.get_dependency("event_store") is event_store

    def test_get_nonexistent_dependency_raises_error(self):
        """Test that getting nonexistent dependency raises error."""
        factory = AdapterFactory()

        with pytest.raises(KeyError, match="not registered"):
            factory.get_dependency("nonexistent")

    def test_has_dependency(self):
        """Test checking if dependency exists."""
        factory = AdapterFactory()

        assert not factory.has_dependency("test")

        factory.register_dependency("test", "value")
        assert factory.has_dependency("test")


class TestOperationModeControl:
    """Test cases for operation mode management."""

    def test_get_operation_mode(self):
        """Test getting operation mode."""
        factory = AdapterFactory()
        assert factory.get_operation_mode() == OperationMode.PRODUCTION

    def test_set_operation_mode(self):
        """Test setting operation mode."""
        factory = AdapterFactory()

        factory.set_operation_mode(OperationMode.SIMULATION)
        assert factory.get_operation_mode() == OperationMode.SIMULATION

        factory.set_operation_mode(OperationMode.INTEGRATION_TEST)
        assert factory.get_operation_mode() == OperationMode.INTEGRATION_TEST


class TestResilienceControl:
    """Test cases for resilience control."""

    def test_is_resilience_enabled(self):
        """Test checking if resilience is enabled."""
        factory = AdapterFactory()
        assert factory.is_resilience_enabled() is True

    def test_enable_resilience(self):
        """Test enabling resilience."""
        config = AdapterFactoryConfig(enable_resilience=False)
        factory = AdapterFactory(config)

        assert factory.is_resilience_enabled() is False

        factory.enable_resilience(True)
        assert factory.is_resilience_enabled() is True

    def test_disable_resilience(self):
        """Test disabling resilience."""
        factory = AdapterFactory()

        assert factory.is_resilience_enabled() is True

        factory.enable_resilience(False)
        assert factory.is_resilience_enabled() is False


class TestFactoryIntegration:
    """Integration tests for adapter factory."""

    def test_create_full_adapter_suite(self):
        """Test creating a full suite of adapters."""
        factory = AdapterFactory()

        # Create all adapters
        ticket_system = factory.create_ticket_system(adapter_name="in_memory")
        container = factory.create_container(adapter_name="fake")
        repository = factory.create_repository(adapter_name="in_memory")
        event_store = factory.create_event_store(adapter_name="in_memory")

        # Verify all created
        assert isinstance(ticket_system, ITicketSystem)
        assert isinstance(container, IContainer)
        assert isinstance(repository, IRepository)
        assert isinstance(event_store, IEventStore)

    def test_registry_modification(self):
        """Test modifying registries after factory creation."""
        factory = AdapterFactory()

        # Register custom adapter
        factory.ticket_system_registry.register(
            name="custom",
            adapter_type=InMemoryTicketAdapter,
            description="Custom adapter",
            tags=["custom"],
        )

        # Create instance of custom adapter
        adapter = factory.create_ticket_system(adapter_name="custom")
        assert isinstance(adapter, ITicketSystem)
