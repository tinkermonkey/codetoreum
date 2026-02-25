"""
Unit tests for adapter factory.

Tests configuration-driven instantiation, resilience application,
and dependency injection.
"""

import pytest

from codetoreum.adapters.secondary import (
    ClaudeCodeConfig,
    DockerConfig,
    GitConfig,
    GitHubConfig,
)
from codetoreum.adapters.testing import (
    FakeContainerAdapter,
    InMemoryEventStore,
    InMemoryRepositoryAdapter,
    InMemoryTicketAdapter,
)
from codetoreum.infrastructure.adapters import AdapterFactory, AdapterFactoryConfig
from codetoreum.infrastructure.resilience import (
    CircuitBreakerConfig,
    OperationMode,
    RateLimitConfig,
    RetryConfig,
    ServiceResilienceConfig,
    TimeoutConfig,
)
from codetoreum.ports.output.container import IContainer
from codetoreum.ports.output.event_store import IEventStore
from codetoreum.ports.output.llm_provider import ILLMProvider
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
        custom_resilience = {
            "ticket_system": ServiceResilienceConfig(
                service_name="ticket_system",
                rate_limit=RateLimitConfig(max_requests=100, window_seconds=60),
                circuit_breaker=CircuitBreakerConfig(failure_threshold=3),
                retry=RetryConfig(max_retries=2),
                timeout=TimeoutConfig(default_timeout_seconds=30),
            )
        }

        config = AdapterFactoryConfig(
            operation_mode=OperationMode.SIMULATION,
            enable_resilience=False,
            custom_resilience_configs=custom_resilience,
        )

        assert config.operation_mode == OperationMode.SIMULATION
        assert config.enable_resilience is False
        assert config.custom_resilience_configs == custom_resilience


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
        assert factory.llm_provider_registry is not None
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
        assert factory.llm_provider_registry.has_adapter("claude_code")
        assert factory.llm_provider_registry.has_adapter("mock")
        assert factory.llm_provider_registry.get_default_name() == "claude_code"

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


class TestTicketSystemCreation:
    """Test cases for ticket system adapter creation."""

    def test_create_default_ticket_system(self):
        """Test creating default ticket system adapter."""
        factory = AdapterFactory()

        github_config = GitHubConfig(token="test_token", organization="test_org", repository="test_repo")

        adapter = factory.create_ticket_system(adapter_config=github_config)
        assert isinstance(adapter, ITicketSystem)

    def test_create_specific_ticket_system(self):
        """Test creating specific ticket system adapter by name."""
        factory = AdapterFactory()

        adapter = factory.create_ticket_system(adapter_name="in_memory")
        # When resilience is enabled, returns decorated adapter
        assert isinstance(adapter, ITicketSystem)

    def test_create_ticket_system_with_resilience_disabled(self):
        """Test creating ticket system with resilience disabled."""
        config = AdapterFactoryConfig(enable_resilience=False)
        factory = AdapterFactory(config)

        adapter = factory.create_ticket_system(adapter_name="in_memory")
        assert isinstance(adapter, InMemoryTicketAdapter)

    def test_create_ticket_system_nonexistent_raises_error(self):
        """Test that creating nonexistent adapter raises error."""
        factory = AdapterFactory()

        with pytest.raises(KeyError):
            factory.create_ticket_system(adapter_name="nonexistent")

    def test_create_ticket_system_simulation_mode(self):
        """Test creating ticket system in simulation mode."""
        config = AdapterFactoryConfig(operation_mode=OperationMode.SIMULATION)
        factory = AdapterFactory(config)

        adapter = factory.create_ticket_system(adapter_name="in_memory")
        assert isinstance(adapter, ITicketSystem)


class TestLLMProviderCreation:
    """Test cases for LLM provider adapter creation."""

    def test_create_default_llm_provider(self):
        """Test creating default LLM provider adapter."""
        factory = AdapterFactory()

        claude_config = ClaudeCodeConfig(api_key_credential_name="ANTHROPIC_API_KEY", default_model="claude-sonnet-4")

        adapter = factory.create_llm_provider(adapter_config=claude_config)
        assert isinstance(adapter, ILLMProvider)

    def test_create_mock_llm_provider(self):
        """Test creating mock LLM provider."""
        factory = AdapterFactory()

        adapter = factory.create_llm_provider(adapter_name="mock")
        # When resilience is enabled, returns decorated adapter
        assert isinstance(adapter, ILLMProvider)

    def test_create_llm_provider_with_custom_resilience(self):
        """Test creating LLM provider with custom resilience config."""
        factory = AdapterFactory()

        custom_resilience = ServiceResilienceConfig(
            service_name="llm_provider",
            rate_limit=RateLimitConfig(max_requests=10, window_seconds=60),
            circuit_breaker=CircuitBreakerConfig(failure_threshold=2),
            retry=RetryConfig(max_retries=1),
            timeout=TimeoutConfig(default_timeout_seconds=60),
        )

        adapter = factory.create_llm_provider(adapter_name="mock", resilience_config=custom_resilience)
        assert isinstance(adapter, ILLMProvider)


class TestContainerCreation:
    """Test cases for container adapter creation."""

    def test_create_default_container(self):
        """Test creating default container adapter."""
        factory = AdapterFactory()

        docker_config = DockerConfig(docker_host="unix:///var/run/docker.sock")

        adapter = factory.create_container(adapter_config=docker_config)
        assert isinstance(adapter, IContainer)

    def test_create_fake_container(self):
        """Test creating fake container adapter."""
        factory = AdapterFactory()

        adapter = factory.create_container(adapter_name="fake")
        assert isinstance(adapter, FakeContainerAdapter)


class TestRepositoryCreation:
    """Test cases for repository adapter creation."""

    def test_create_default_repository(self):
        """Test creating default repository adapter."""
        factory = AdapterFactory()

        git_config = GitConfig(git_path="/usr/bin/git")

        adapter = factory.create_repository(adapter_config=git_config)
        assert isinstance(adapter, IRepository)

    def test_create_in_memory_repository(self):
        """Test creating in-memory repository adapter."""
        factory = AdapterFactory()

        adapter = factory.create_repository(adapter_name="in_memory")
        assert isinstance(adapter, InMemoryRepositoryAdapter)


class TestEventStoreCreation:
    """Test cases for event store adapter creation."""

    def test_create_default_event_store(self):
        """Test creating default event store adapter."""
        factory = AdapterFactory()

        adapter = factory.create_event_store()
        assert isinstance(adapter, InMemoryEventStore)

    def test_create_specific_event_store(self):
        """Test creating specific event store adapter."""
        factory = AdapterFactory()

        adapter = factory.create_event_store(adapter_name="in_memory")
        assert isinstance(adapter, InMemoryEventStore)


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

    def test_multiple_dependencies(self):
        """Test managing multiple dependencies."""
        factory = AdapterFactory()

        event_store = InMemoryEventStore()
        repository = InMemoryRepositoryAdapter()

        factory.register_dependency("event_store", event_store)
        factory.register_dependency("repository", repository)

        assert factory.has_dependency("event_store")
        assert factory.has_dependency("repository")
        assert factory.get_dependency("event_store") is event_store
        assert factory.get_dependency("repository") is repository


class TestOperationMode:
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

    def test_simulation_mode_workflow(self):
        """Test complete simulation mode workflow."""
        config = AdapterFactoryConfig(operation_mode=OperationMode.SIMULATION, enable_resilience=True)
        factory = AdapterFactory(config)

        # Create adapters for simulation
        ticket_system = factory.create_ticket_system(adapter_name="in_memory")
        llm_provider = factory.create_llm_provider(adapter_name="mock")
        container = factory.create_container(adapter_name="fake")

        # Verify all use simulation/mock implementations
        assert isinstance(ticket_system, ITicketSystem)
        assert isinstance(llm_provider, ILLMProvider)
        assert isinstance(container, IContainer)

    def test_production_mode_workflow(self):
        """Test production mode workflow with resilience."""
        config = AdapterFactoryConfig(operation_mode=OperationMode.PRODUCTION, enable_resilience=True)
        factory = AdapterFactory(config)

        # Create test adapters (using in-memory for test isolation)
        ticket_system = factory.create_ticket_system(adapter_name="in_memory")
        llm_provider = factory.create_llm_provider(adapter_name="mock")

        # Verify adapters created with resilience
        assert isinstance(ticket_system, ITicketSystem)
        assert isinstance(llm_provider, ILLMProvider)

    def test_switch_modes_at_runtime(self):
        """Test switching operation modes at runtime."""
        factory = AdapterFactory()

        # Start in production mode
        assert factory.get_operation_mode() == OperationMode.PRODUCTION

        # Create adapter in production mode
        adapter1 = factory.create_ticket_system(adapter_name="in_memory")
        assert isinstance(adapter1, ITicketSystem)

        # Switch to simulation mode
        factory.set_operation_mode(OperationMode.SIMULATION)
        assert factory.get_operation_mode() == OperationMode.SIMULATION

        # Create adapter in simulation mode
        adapter2 = factory.create_ticket_system(adapter_name="in_memory")
        assert isinstance(adapter2, ITicketSystem)

    def test_custom_resilience_config(self):
        """Test using custom resilience configurations."""
        custom_config = ServiceResilienceConfig(
            service_name="ticket_system",
            rate_limit=RateLimitConfig(max_requests=1000, window_seconds=3600),
            circuit_breaker=CircuitBreakerConfig(failure_threshold=10),
            retry=RetryConfig(max_retries=5),
            timeout=TimeoutConfig(default_timeout_seconds=120),
        )

        config = AdapterFactoryConfig(custom_resilience_configs={"ticket_system": custom_config})

        factory = AdapterFactory(config)

        adapter = factory.create_ticket_system(adapter_name="in_memory")
        assert isinstance(adapter, ITicketSystem)

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
        # When resilience is enabled, returns decorated adapter
        assert isinstance(adapter, ITicketSystem)
