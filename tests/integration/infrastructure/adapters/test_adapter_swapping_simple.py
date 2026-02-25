"""
Simplified integration tests for adapter swapping.

Tests the ability to swap adapter implementations at runtime.
"""

import pytest

from codetoreum.adapters.testing import (
    FakeContainerAdapter,
    InMemoryRepositoryAdapter,
    InMemoryTicketAdapter,
    MockLLMAdapter,
)
from codetoreum.infrastructure.adapters import AdapterFactory, AdapterFactoryConfig
from codetoreum.infrastructure.resilience import OperationMode
from codetoreum.ports.output.container import IContainer
from codetoreum.ports.output.event_store import IEventStore
from codetoreum.ports.output.llm_provider import ILLMProvider
from codetoreum.ports.output.repository import IRepository
from codetoreum.ports.output.ticket_system import ITicketSystem


@pytest.fixture
def factory():
    """Create a factory for testing."""
    return AdapterFactory()


@pytest.fixture
def simulation_factory():
    """Create a factory in simulation mode."""
    config = AdapterFactoryConfig(operation_mode=OperationMode.SIMULATION)
    return AdapterFactory(config)


class TestTicketSystemSwapping:
    """Test swapping ticket system adapters."""

    @pytest.mark.asyncio
    async def test_in_memory_adapter_isolation(self, factory: AdapterFactory):
        """Test that in-memory adapters are isolated."""
        adapter1 = factory.create_ticket_system(adapter_name="in_memory")
        adapter2 = factory.create_ticket_system(adapter_name="in_memory")

        # They should be different instances
        assert adapter1 is not adapter2


class TestLLMProviderSwapping:
    """Test swapping LLM provider adapters."""

    @pytest.mark.asyncio
    async def test_mock_adapter_creation(self, factory: AdapterFactory):
        """Test creating mock LLM adapter."""
        # Disable resilience to get direct adapter instance
        factory.enable_resilience(False)
        adapter = factory.create_llm_provider(adapter_name="mock")

        # Verify we got a mock adapter
        assert isinstance(adapter, MockLLMAdapter)


class TestContainerSwapping:
    """Test swapping container adapters."""

    @pytest.mark.asyncio
    async def test_fake_container_operations(self, factory: AdapterFactory):
        """Test fake container adapter operations."""
        adapter = factory.create_container(adapter_name="fake")

        # Create container
        container_id = await adapter.create(
            image="python:3.11",
            command=["python", "--version"],
            name="test-container"
        )

        assert container_id is not None

        # Start container
        await adapter.start(container_id)

        # Check status
        status = await adapter.status(container_id)
        assert status is not None

        # Stop container
        await adapter.stop(container_id)

        # Remove container
        await adapter.remove(container_id)


class TestRepositorySwapping:
    """Test swapping repository adapters."""

    @pytest.mark.asyncio
    async def test_in_memory_repository_creation(self, factory: AdapterFactory):
        """Test creating in-memory repository adapter."""
        adapter = factory.create_repository(adapter_name="in_memory")

        # Verify adapter created
        assert isinstance(adapter, InMemoryRepositoryAdapter)


class TestModeBasedSwapping:
    """Test swapping adapters based on operation mode."""

    @pytest.mark.asyncio
    async def test_production_mode_adapters(self):
        """Test adapter selection in production mode."""
        config = AdapterFactoryConfig(
            operation_mode=OperationMode.PRODUCTION,
            enable_resilience=True
        )
        factory = AdapterFactory(config)

        # Get default adapters (would be production adapters)
        ticket_system = factory.create_ticket_system(adapter_name="in_memory")
        llm_provider = factory.create_llm_provider(adapter_name="mock")
        container = factory.create_container(adapter_name="fake")
        repository = factory.create_repository(adapter_name="in_memory")

        # Verify they're the right type
        assert isinstance(ticket_system, ITicketSystem)
        assert isinstance(llm_provider, ILLMProvider)
        assert isinstance(container, IContainer)
        assert isinstance(repository, IRepository)

    @pytest.mark.asyncio
    async def test_simulation_mode_adapters(self):
        """Test adapter selection in simulation mode."""
        config = AdapterFactoryConfig(
            operation_mode=OperationMode.SIMULATION,
            enable_resilience=False  # Disable to get unwrapped instances
        )
        factory = AdapterFactory(config)

        # Use mock/in-memory adapters for simulation
        ticket_system = factory.create_ticket_system(adapter_name="in_memory")
        llm_provider = factory.create_llm_provider(adapter_name="mock")
        container = factory.create_container(adapter_name="fake")
        repository = factory.create_repository(adapter_name="in_memory")

        # Verify they're the mock implementations
        assert isinstance(ticket_system, InMemoryTicketAdapter)
        assert isinstance(llm_provider, MockLLMAdapter)
        assert isinstance(container, FakeContainerAdapter)
        assert isinstance(repository, InMemoryRepositoryAdapter)


class TestRuntimeAdapterSwapping:
    """Test swapping adapters at runtime."""

    @pytest.mark.asyncio
    async def test_mode_change_during_execution(self):
        """Test changing operation mode during execution."""
        factory = AdapterFactory()

        # Create adapter in production mode
        assert factory.get_operation_mode() == OperationMode.PRODUCTION
        adapter1 = factory.create_ticket_system(adapter_name="in_memory")

        # Change to simulation mode
        factory.set_operation_mode(OperationMode.SIMULATION)
        assert factory.get_operation_mode() == OperationMode.SIMULATION

        # Create new adapter in simulation mode
        adapter2 = factory.create_ticket_system(adapter_name="in_memory")

        # Both should work but be independent
        assert isinstance(adapter1, ITicketSystem)
        assert isinstance(adapter2, ITicketSystem)


class TestMultipleAdapterTypes:
    """Test using multiple adapter types simultaneously."""

    @pytest.mark.asyncio
    async def test_multiple_adapters_simultaneously(self, factory: AdapterFactory):
        """Test using multiple adapter types at the same time."""
        # Create all adapter types
        ticket_system = factory.create_ticket_system(adapter_name="in_memory")
        llm_provider = factory.create_llm_provider(adapter_name="mock")
        container = factory.create_container(adapter_name="fake")
        repository = factory.create_repository(adapter_name="in_memory")
        event_store = factory.create_event_store(adapter_name="in_memory")

        # Verify all created
        assert isinstance(ticket_system, ITicketSystem)
        assert isinstance(llm_provider, ILLMProvider)
        assert isinstance(container, IContainer)
        assert isinstance(repository, IRepository)
        assert isinstance(event_store, IEventStore)


class TestRegistryModification:
    """Test modifying registries and swapping custom adapters."""

    @pytest.mark.asyncio
    async def test_register_custom_adapter(self, factory: AdapterFactory):
        """Test registering and using custom adapter."""
        # Register custom adapter
        factory.ticket_system_registry.register(
            name="custom_in_memory",
            adapter_type=InMemoryTicketAdapter,
            description="Custom in-memory adapter",
            tags=["custom", "testing"]
        )

        # Create instance
        adapter = factory.create_ticket_system(adapter_name="custom_in_memory")
        assert isinstance(adapter, ITicketSystem)

    @pytest.mark.asyncio
    async def test_swap_to_custom_adapter(self, factory: AdapterFactory):
        """Test swapping to custom registered adapter."""
        # Start with default
        adapter1 = factory.create_ticket_system(adapter_name="in_memory")

        # Register custom
        factory.ticket_system_registry.register(
            name="custom",
            adapter_type=InMemoryTicketAdapter,
            description="Custom adapter",
            tags=["custom"]
        )

        # Swap to custom
        adapter2 = factory.create_ticket_system(adapter_name="custom")

        # Both should work
        assert isinstance(adapter1, ITicketSystem)
        assert isinstance(adapter2, ITicketSystem)

    @pytest.mark.asyncio
    async def test_unregister_and_swap(self, factory: AdapterFactory):
        """Test unregistering adapter affects future swaps."""
        # Register custom
        factory.ticket_system_registry.register(
            name="temp",
            adapter_type=InMemoryTicketAdapter,
            description="Temporary adapter"
        )

        # Create instance
        adapter1 = factory.create_ticket_system(adapter_name="temp")
        assert isinstance(adapter1, ITicketSystem)

        # Unregister
        factory.ticket_system_registry.unregister("temp")

        # Should no longer be available
        with pytest.raises(KeyError):
            factory.create_ticket_system(adapter_name="temp")
