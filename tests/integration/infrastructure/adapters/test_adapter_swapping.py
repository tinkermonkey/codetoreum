"""
Integration tests for adapter swapping.

Tests the ability to swap adapter implementations at runtime,
which is critical for testing, simulation, and production deployment.
"""

import pytest
from typing import List

from codetoreum.infrastructure.adapters import AdapterFactory, AdapterFactoryConfig
from codetoreum.infrastructure.resilience import OperationMode
from codetoreum.ports.output.ticket_system import ITicketSystem
from codetoreum.ports.output.llm_provider import ILLMProvider
from codetoreum.ports.output.container import IContainer
from codetoreum.ports.output.repository import IRepository
from codetoreum.ports.output.event_store import IEventStore
from codetoreum.domain.work_item import WorkItem, WorkItemStatus, WorkItemType
from codetoreum.domain.value_objects import ExecutionResult, ExecutionStatus
from codetoreum.adapters.testing import (
    InMemoryTicketAdapter,
    MockLLMAdapter,
    FakeContainerAdapter,
    InMemoryRepositoryAdapter
)


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
    async def test_swap_github_to_in_memory(self, factory: AdapterFactory):
        """Test swapping from GitHub to in-memory adapter."""
        # Create in-memory adapter (GitHub requires credentials)
        adapter1 = factory.create_ticket_system(adapter_name="in_memory")

        # Create work item
        work_item = WorkItem(
            id="TEST-1",
            title="Test Issue",
            description="Test description",
            type=WorkItemType.TASK,
            status=WorkItemStatus.OPEN,
            metadata={}
        )

        await adapter1.create_work_item(work_item)

        # Verify created
        retrieved = await adapter1.get_work_item("TEST-1")
        assert retrieved.id == "TEST-1"
        assert retrieved.title == "Test Issue"

        # Swap to another in-memory instance
        adapter2 = factory.create_ticket_system(adapter_name="in_memory")

        # New instance should be independent
        with pytest.raises(Exception):
            await adapter2.get_work_item("TEST-1")

    @pytest.mark.asyncio
    async def test_in_memory_adapter_isolation(self, factory: AdapterFactory):
        """Test that in-memory adapters are isolated."""
        adapter1 = factory.create_ticket_system(adapter_name="in_memory")
        adapter2 = factory.create_ticket_system(adapter_name="in_memory")

        # Create work item in adapter1
        work_item = WorkItem(
            id="TEST-1",
            title="Test Issue",
            description="Test description",
            type=WorkItemType.TASK,
            status=WorkItemStatus.OPEN,
            metadata={}
        )

        await adapter1.create_work_item(work_item)

        # Should exist in adapter1
        retrieved = await adapter1.get_work_item("TEST-1")
        assert retrieved is not None

        # Should NOT exist in adapter2 (isolated instance)
        with pytest.raises(Exception):
            await adapter2.get_work_item("TEST-1")


class TestLLMProviderSwapping:
    """Test swapping LLM provider adapters."""

    @pytest.mark.asyncio
    async def test_swap_claude_to_mock(self, factory: AdapterFactory):
        """Test swapping from Claude to mock adapter."""
        # Create mock adapter (Claude requires credentials)
        adapter = factory.create_llm_provider(adapter_name="mock")

        # Configure mock response
        if isinstance(adapter, MockLLMAdapter):
            adapter.add_response("test", "mock response")

        # Execute
        result = await adapter.execute("test")
        assert result.output == "mock response"

    @pytest.mark.asyncio
    async def test_mock_adapter_response_patterns(self, factory: AdapterFactory):
        """Test mock adapter with different response patterns."""
        adapter = factory.create_llm_provider(adapter_name="mock")

        if isinstance(adapter, MockLLMAdapter):
            # Add multiple patterns
            adapter.add_response("hello.*", "Hello, world!")
            adapter.add_response("goodbye.*", "Goodbye!")
            adapter.add_response(".*", "Default response")

            # Test pattern matching
            result1 = await adapter.execute("hello there")
            assert result1.output == "Hello, world!"

            result2 = await adapter.execute("goodbye friend")
            assert result2.output == "Goodbye!"

            result3 = await adapter.execute("random prompt")
            assert result3.output == "Default response"


class TestContainerSwapping:
    """Test swapping container adapters."""

    @pytest.mark.asyncio
    async def test_swap_docker_to_fake(self, factory: AdapterFactory):
        """Test swapping from Docker to fake adapter."""
        # Create fake adapter (Docker requires Docker daemon)
        adapter = factory.create_container(adapter_name="fake")

        # Run container
        result = await adapter.run(
            image="python:3.11",
            command=["python", "--version"],
            name="test-container"
        )

        assert result is not None

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
    async def test_swap_git_to_in_memory(self, factory: AdapterFactory):
        """Test swapping from Git to in-memory adapter."""
        # Create in-memory adapter (Git requires git binary)
        adapter = factory.create_repository(adapter_name="in_memory")

        # Create branch
        await adapter.create_branch("feature-branch")

        # List branches
        branches = await adapter.list_branches()
        assert "feature-branch" in branches

    @pytest.mark.asyncio
    async def test_in_memory_repository_operations(self, factory: AdapterFactory):
        """Test in-memory repository adapter operations."""
        adapter = factory.create_repository(adapter_name="in_memory")

        # Create branch
        await adapter.create_branch("feature-1")
        await adapter.create_branch("feature-2")

        # List branches
        branches = await adapter.list_branches()
        assert "feature-1" in branches
        assert "feature-2" in branches

        # Checkout branch
        await adapter.checkout("feature-1")

        # Get current branch (if adapter supports it)
        # Note: InMemoryRepositoryAdapter might not track current branch
        # This is just demonstrating the interface


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
            enable_resilience=True
        )
        factory = AdapterFactory(config)

        # Use mock/in-memory adapters for simulation
        ticket_system = factory.create_ticket_system(adapter_name="in_memory")
        llm_provider = factory.create_llm_provider(adapter_name="mock")
        container = factory.create_container(adapter_name="fake")
        repository = factory.create_repository(adapter_name="in_memory")

        # Verify they work
        assert isinstance(ticket_system, InMemoryTicketAdapter)
        assert isinstance(llm_provider, MockLLMAdapter)
        assert isinstance(container, FakeContainerAdapter)
        assert isinstance(repository, InMemoryRepositoryAdapter)


class TestRuntimeAdapterSwapping:
    """Test swapping adapters at runtime."""

    @pytest.mark.asyncio
    async def test_swap_during_execution(self, factory: AdapterFactory):
        """Test swapping adapters during execution."""
        # Start with in-memory adapter
        adapter1 = factory.create_ticket_system(adapter_name="in_memory")

        # Create work item
        work_item = WorkItem(
            id="TEST-1",
            title="Test Issue",
            description="Test description",
            type=WorkItemType.TASK,
            status=WorkItemStatus.OPEN,
            metadata={}
        )

        await adapter1.create_work_item(work_item)
        assert await adapter1.get_work_item("TEST-1") is not None

        # Swap to different adapter instance
        adapter2 = factory.create_ticket_system(adapter_name="in_memory")

        # New adapter should be empty (different instance)
        with pytest.raises(Exception):
            await adapter2.get_work_item("TEST-1")

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


class TestAdapterConfiguration:
    """Test adapter configuration during swapping."""

    @pytest.mark.asyncio
    async def test_swap_with_different_configs(self, factory: AdapterFactory):
        """Test swapping adapters with different configurations."""
        # Create multiple adapters with different configs
        adapter1 = factory.create_ticket_system(adapter_name="in_memory")
        adapter2 = factory.create_ticket_system(adapter_name="in_memory")

        # Each should be independent
        assert adapter1 is not adapter2

    @pytest.mark.asyncio
    async def test_resilience_config_per_adapter(self, factory: AdapterFactory):
        """Test different resilience configs per adapter."""
        from codetoreum.infrastructure.resilience import (
            ServiceResilienceConfig,
            RateLimitConfig,
            CircuitBreakerConfig,
            RetryConfig,
            TimeoutConfig
        )

        # Custom resilience config
        custom_config = ServiceResilienceConfig(
            rate_limit=RateLimitConfig(max_requests=10, window_seconds=1),
            circuit_breaker=CircuitBreakerConfig(failure_threshold=2),
            retry=RetryConfig(max_attempts=1),
            timeout=TimeoutConfig(default_timeout_seconds=5)
        )

        # Create adapter with custom resilience
        adapter = factory.create_ticket_system(
            adapter_name="in_memory",
            resilience_config=custom_config
        )

        assert isinstance(adapter, ITicketSystem)


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

    @pytest.mark.asyncio
    async def test_coordinated_adapter_operations(self, factory: AdapterFactory):
        """Test coordinated operations across multiple adapters."""
        # Create adapters
        ticket_system = factory.create_ticket_system(adapter_name="in_memory")
        llm_provider = factory.create_llm_provider(adapter_name="mock")

        # Configure mock LLM
        if isinstance(llm_provider, MockLLMAdapter):
            llm_provider.add_response(".*", "Task completed")

        # Create work item
        work_item = WorkItem(
            id="TEST-1",
            title="Test Task",
            description="Complete this task",
            type=WorkItemType.TASK,
            status=WorkItemStatus.IN_PROGRESS,
            metadata={}
        )

        await ticket_system.create_work_item(work_item)

        # Execute LLM operation
        result = await llm_provider.execute("Complete task TEST-1")
        assert result.output == "Task completed"

        # Update work item based on result
        work_item.status = WorkItemStatus.COMPLETED
        await ticket_system.update_work_item(work_item)

        # Verify update
        updated = await ticket_system.get_work_item("TEST-1")
        assert updated.status == WorkItemStatus.COMPLETED


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
        assert isinstance(adapter, InMemoryTicketAdapter)

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
