"""
Unit tests for adapter registries.

Tests the registration, lookup, and management of adapter implementations.
"""

import pytest
from datetime import datetime

from codetoreum.infrastructure.adapters import (
    TicketSystemRegistry,
    LLMProviderRegistry,
    ContainerRegistry,
    RepositoryRegistry,
    EventStoreRegistry,
    StorageRegistry,
    AdapterMetadata
)
from codetoreum.adapters.secondary import (
    GitHubTicketAdapter,
    ClaudeCodeAdapter,
    DockerContainerAdapter,
    GitRepositoryAdapter
)
from codetoreum.adapters.testing import (
    InMemoryTicketAdapter,
    MockLLMAdapter,
    FakeContainerAdapter,
    InMemoryRepositoryAdapter,
    InMemoryEventStore
)


class TestTicketSystemRegistry:
    """Test cases for TicketSystemRegistry."""

    def test_initialization(self):
        """Test registry initialization."""
        registry = TicketSystemRegistry()
        assert len(registry) == 0
        assert registry.get_default() is None

    def test_register_adapter(self):
        """Test registering an adapter."""
        registry = TicketSystemRegistry()

        registry.register(
            name="github",
            adapter_type=GitHubTicketAdapter,
            description="GitHub Issues",
            version="1.0.0",
            tags=["production", "github"]
        )

        assert len(registry) == 1
        assert registry.has_adapter("github")
        assert registry.get("github") == GitHubTicketAdapter

    def test_register_duplicate_raises_error(self):
        """Test that registering duplicate name raises error."""
        registry = TicketSystemRegistry()

        registry.register(
            name="github",
            adapter_type=GitHubTicketAdapter,
            description="GitHub Issues"
        )

        with pytest.raises(ValueError, match="already registered"):
            registry.register(
                name="github",
                adapter_type=InMemoryTicketAdapter,
                description="In-memory"
            )

    def test_register_invalid_adapter_raises_error(self):
        """Test that registering invalid adapter raises error."""
        registry = TicketSystemRegistry()

        class InvalidAdapter:
            """Not a valid ITicketSystem implementation."""
            pass

        with pytest.raises(ValueError, match="does not implement"):
            registry.register(
                name="invalid",
                adapter_type=InvalidAdapter,
                description="Invalid"
            )

    def test_unregister_adapter(self):
        """Test unregistering an adapter."""
        registry = TicketSystemRegistry()

        registry.register(
            name="github",
            adapter_type=GitHubTicketAdapter,
            description="GitHub Issues"
        )

        assert len(registry) == 1
        registry.unregister("github")
        assert len(registry) == 0
        assert not registry.has_adapter("github")

    def test_unregister_nonexistent_raises_error(self):
        """Test that unregistering nonexistent adapter raises error."""
        registry = TicketSystemRegistry()

        with pytest.raises(KeyError, match="not registered"):
            registry.unregister("nonexistent")

    def test_get_nonexistent_raises_error(self):
        """Test that getting nonexistent adapter raises error."""
        registry = TicketSystemRegistry()

        with pytest.raises(KeyError, match="not registered"):
            registry.get("nonexistent")

    def test_set_default_adapter(self):
        """Test setting default adapter."""
        registry = TicketSystemRegistry()

        registry.register(
            name="github",
            adapter_type=GitHubTicketAdapter,
            description="GitHub Issues",
            set_as_default=True
        )

        assert registry.get_default() == GitHubTicketAdapter
        assert registry.get_default_name() == "github"

    def test_set_default_nonexistent_raises_error(self):
        """Test that setting nonexistent default raises error."""
        registry = TicketSystemRegistry()

        with pytest.raises(KeyError, match="not registered"):
            registry.set_default("nonexistent")

    def test_list_adapters(self):
        """Test listing adapters."""
        registry = TicketSystemRegistry()

        registry.register(
            name="github",
            adapter_type=GitHubTicketAdapter,
            description="GitHub"
        )
        registry.register(
            name="in_memory",
            adapter_type=InMemoryTicketAdapter,
            description="In-memory"
        )

        adapters = registry.list_adapters()
        assert len(adapters) == 2
        assert "github" in adapters
        assert "in_memory" in adapters

    def test_list_by_tags(self):
        """Test listing adapters by tags."""
        registry = TicketSystemRegistry()

        registry.register(
            name="github",
            adapter_type=GitHubTicketAdapter,
            description="GitHub",
            tags=["production", "github"]
        )
        registry.register(
            name="in_memory",
            adapter_type=InMemoryTicketAdapter,
            description="In-memory",
            tags=["testing", "simulation"]
        )

        production = registry.list_by_tags(["production"])
        assert production == ["github"]

        testing = registry.list_by_tags(["testing"])
        assert testing == ["in_memory"]

    def test_get_metadata(self):
        """Test getting adapter metadata."""
        registry = TicketSystemRegistry()

        registry.register(
            name="github",
            adapter_type=GitHubTicketAdapter,
            description="GitHub Issues",
            version="1.0.0",
            tags=["production"]
        )

        metadata = registry.get_metadata("github")
        assert isinstance(metadata, AdapterMetadata)
        assert metadata.name == "github"
        assert metadata.adapter_type == GitHubTicketAdapter
        assert metadata.description == "GitHub Issues"
        assert metadata.version == "1.0.0"
        assert metadata.tags == ["production"]
        assert isinstance(metadata.registered_at, datetime)

    def test_create_instance(self):
        """Test creating adapter instance."""
        registry = TicketSystemRegistry()

        # Register with factory
        def factory():
            return InMemoryTicketAdapter()

        registry.register(
            name="in_memory",
            adapter_type=InMemoryTicketAdapter,
            description="In-memory",
            factory=factory
        )

        instance = registry.create_instance("in_memory")
        assert isinstance(instance, InMemoryTicketAdapter)

    def test_clear_registry(self):
        """Test clearing registry."""
        registry = TicketSystemRegistry()

        registry.register(
            name="github",
            adapter_type=GitHubTicketAdapter,
            description="GitHub"
        )
        registry.register(
            name="in_memory",
            adapter_type=InMemoryTicketAdapter,
            description="In-memory"
        )

        assert len(registry) == 2
        registry.clear()
        assert len(registry) == 0

    def test_contains_operator(self):
        """Test 'in' operator."""
        registry = TicketSystemRegistry()

        registry.register(
            name="github",
            adapter_type=GitHubTicketAdapter,
            description="GitHub"
        )

        assert "github" in registry
        assert "nonexistent" not in registry

    def test_thread_safety(self):
        """Test thread-safe operations."""
        import threading

        registry = TicketSystemRegistry()

        def register_adapter(name: str):
            try:
                registry.register(
                    name=name,
                    adapter_type=InMemoryTicketAdapter,
                    description=f"Adapter {name}"
                )
            except ValueError:
                pass  # Duplicate registration expected

        threads = [
            threading.Thread(target=register_adapter, args=(f"adapter_{i}",))
            for i in range(10)
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Should have registered 10 unique adapters
        assert len(registry) == 10


class TestLLMProviderRegistry:
    """Test cases for LLMProviderRegistry."""

    def test_initialization(self):
        """Test registry initialization."""
        registry = LLMProviderRegistry()
        assert len(registry) == 0

    def test_register_valid_adapter(self):
        """Test registering valid LLM provider adapter."""
        registry = LLMProviderRegistry()

        registry.register(
            name="claude_code",
            adapter_type=ClaudeCodeAdapter,
            description="Claude Code"
        )

        assert registry.has_adapter("claude_code")
        assert registry.get("claude_code") == ClaudeCodeAdapter

    def test_register_mock_adapter(self):
        """Test registering mock adapter."""
        registry = LLMProviderRegistry()

        registry.register(
            name="mock",
            adapter_type=MockLLMAdapter,
            description="Mock LLM"
        )

        assert registry.has_adapter("mock")


class TestContainerRegistry:
    """Test cases for ContainerRegistry."""

    def test_initialization(self):
        """Test registry initialization."""
        registry = ContainerRegistry()
        assert len(registry) == 0

    def test_register_docker_adapter(self):
        """Test registering Docker adapter."""
        registry = ContainerRegistry()

        registry.register(
            name="docker",
            adapter_type=DockerContainerAdapter,
            description="Docker"
        )

        assert registry.has_adapter("docker")
        assert registry.get("docker") == DockerContainerAdapter

    def test_register_fake_adapter(self):
        """Test registering fake adapter."""
        registry = ContainerRegistry()

        registry.register(
            name="fake",
            adapter_type=FakeContainerAdapter,
            description="Fake container"
        )

        assert registry.has_adapter("fake")


class TestRepositoryRegistry:
    """Test cases for RepositoryRegistry."""

    def test_initialization(self):
        """Test registry initialization."""
        registry = RepositoryRegistry()
        assert len(registry) == 0

    def test_register_git_adapter(self):
        """Test registering Git adapter."""
        registry = RepositoryRegistry()

        registry.register(
            name="git",
            adapter_type=GitRepositoryAdapter,
            description="Git"
        )

        assert registry.has_adapter("git")
        assert registry.get("git") == GitRepositoryAdapter

    def test_register_in_memory_adapter(self):
        """Test registering in-memory adapter."""
        registry = RepositoryRegistry()

        registry.register(
            name="in_memory",
            adapter_type=InMemoryRepositoryAdapter,
            description="In-memory"
        )

        assert registry.has_adapter("in_memory")


class TestEventStoreRegistry:
    """Test cases for EventStoreRegistry."""

    def test_initialization(self):
        """Test registry initialization."""
        registry = EventStoreRegistry()
        assert len(registry) == 0

    def test_register_in_memory_event_store(self):
        """Test registering in-memory event store."""
        registry = EventStoreRegistry()

        registry.register(
            name="in_memory",
            adapter_type=InMemoryEventStore,
            description="In-memory event store"
        )

        assert registry.has_adapter("in_memory")
        assert registry.get("in_memory") == InMemoryEventStore


class TestStorageRegistry:
    """Test cases for StorageRegistry."""

    def test_initialization(self):
        """Test registry initialization."""
        registry = StorageRegistry()
        assert len(registry) == 0


class TestAdapterMetadata:
    """Test cases for AdapterMetadata."""

    def test_matches_tags(self):
        """Test tag matching."""
        metadata = AdapterMetadata(
            name="test",
            adapter_type=InMemoryTicketAdapter,
            description="Test",
            version="1.0.0",
            tags=["production", "github", "issues"],
            registered_at=datetime.utcnow()
        )

        assert metadata.matches_tags(["production"])
        assert metadata.matches_tags(["production", "github"])
        assert metadata.matches_tags(["production", "github", "issues"])
        assert not metadata.matches_tags(["testing"])
        assert not metadata.matches_tags(["production", "testing"])


class TestRegistryIntegration:
    """Integration tests across multiple registries."""

    def test_multiple_registries_independent(self):
        """Test that multiple registries are independent."""
        ticket_registry = TicketSystemRegistry()
        llm_registry = LLMProviderRegistry()

        ticket_registry.register(
            name="test",
            adapter_type=InMemoryTicketAdapter,
            description="Test"
        )

        llm_registry.register(
            name="test",
            adapter_type=MockLLMAdapter,
            description="Test"
        )

        # Same name but different registries
        assert len(ticket_registry) == 1
        assert len(llm_registry) == 1
        assert ticket_registry.get("test") == InMemoryTicketAdapter
        assert llm_registry.get("test") == MockLLMAdapter
