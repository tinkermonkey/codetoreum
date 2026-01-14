"""Test configuration and shared fixtures."""

from typing import Generator

import docker
import pytest
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import HttpWaitStrategy, PortWaitStrategy

from codetoreum.adapters.testing.in_memory_event_store import InMemoryEventStore
from codetoreum.adapters.testing.in_memory_ticket_adapter import InMemoryTicketAdapter
from codetoreum.adapters.testing.mock_llm_adapter import MockLLMAdapter
from codetoreum.adapters.testing.fake_container_adapter import FakeContainerAdapter
from codetoreum.adapters.testing.in_memory_storage_adapter import InMemoryStorageAdapter
from codetoreum.infrastructure.event_bus import EventBus


def is_docker_available() -> bool:
    """Check if Docker is available and running.

    Returns:
        bool: True if Docker daemon is accessible, False otherwise
    """
    try:
        client = docker.from_env()
        try:
            client.ping()
            return True
        finally:
            client.close()
    except (docker.errors.DockerException, Exception):
        return False


# Create a global pytest marker for tests requiring Docker
docker_available = pytest.mark.skipif(
    not is_docker_available(),
    reason="Docker is not available or not running"
)


@pytest.fixture(scope="session")
def docker_client() -> Generator[docker.DockerClient, None, None]:
    """Shared Docker client for all tests in the session.

    This fixture creates a single Docker client that is reused across all tests
    in the session, reducing resource consumption and connection overhead.

    Yields:
        docker.DockerClient: Docker client instance
    """
    if not is_docker_available():
        pytest.skip("Docker is not available or not running")

    client = docker.from_env()
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def sample_work_item_data() -> dict[str, str]:
    """Sample work item data for testing.

    Returns:
        Dictionary containing sample work item data.
    """
    return {
        "id": "issue-1",
        "title": "Implement user authentication",
        "description": "Add OAuth2 authentication flow",
        "status": "pending",
    }


@pytest.fixture
def mock_event_store() -> dict[str, list[dict]]:
    """Mock event store for testing.

    Returns:
        Dictionary simulating an in-memory event store.
    """
    return {}


# Shared fixtures with automatic cleanup for memory management


@pytest.fixture
def event_store() -> Generator[InMemoryEventStore, None, None]:
    """Create in-memory event store with automatic cleanup.

    This fixture ensures that all events are cleared after each test
    to prevent memory accumulation across test runs.

    Yields:
        InMemoryEventStore instance
    """
    store = InMemoryEventStore()
    yield store
    store.clear()


@pytest.fixture
def ticket_system() -> Generator[InMemoryTicketAdapter, None, None]:
    """Create in-memory ticket system with automatic cleanup.

    This fixture ensures that all work items, comments, and webhooks
    are cleared after each test to prevent memory accumulation.

    Yields:
        InMemoryTicketAdapter instance
    """
    adapter = InMemoryTicketAdapter()
    yield adapter
    adapter.clear()


@pytest.fixture
def llm_provider() -> Generator[MockLLMAdapter, None, None]:
    """Create mock LLM provider with automatic cleanup.

    Yields:
        MockLLMAdapter instance
    """
    adapter = MockLLMAdapter()
    yield adapter
    adapter.clear_conversations()
    adapter.reset_stats()


@pytest.fixture
def container_adapter() -> Generator[FakeContainerAdapter, None, None]:
    """Create fake container adapter with automatic cleanup.

    Yields:
        FakeContainerAdapter instance
    """
    adapter = FakeContainerAdapter()
    yield adapter
    adapter.clear()


@pytest.fixture
def storage_adapter() -> Generator[InMemoryStorageAdapter, None, None]:
    """Create in-memory storage adapter with automatic cleanup.

    Yields:
        InMemoryStorageAdapter instance
    """
    adapter = InMemoryStorageAdapter()
    yield adapter
    adapter.clear()


@pytest.fixture
def event_bus() -> Generator[EventBus, None, None]:
    """Create event bus with automatic cleanup.

    This fixture ensures that all handlers are unregistered and
    statistics are reset after each test.

    Yields:
        EventBus instance
    """
    bus = EventBus(max_retries=3, retry_delay_seconds=0.1)
    yield bus
    # Unregister all handlers to prevent memory leaks
    for handlers in list(bus._handlers.values()):
        for handler in list(handlers):
            bus.unregister_handler(handler)
    for handler in list(bus._wildcard_handlers):
        bus.unregister_handler(handler)
    bus.reset_statistics()


class ModernElasticsearchContainer(DockerContainer):
    """Elasticsearch container using modern wait strategy API.

    This class replaces testcontainers.elasticsearch.ElasticSearchContainer to avoid
    the DeprecationWarning from @wait_container_is_ready decorator. Uses structured
    wait strategies (HttpWaitStrategy) instead of the deprecated decorator approach.

    Example:
        >>> container = ModernElasticsearchContainer("elasticsearch:8.11.0")
        >>> container.start()
        >>> url = container.get_url()
        >>> # ... use Elasticsearch ...
        >>> container.stop()
    """

    def __init__(self, image: str = "elasticsearch:8.11.0", port: int = 9200) -> None:
        """Initialize Elasticsearch container.

        Args:
            image: Docker image name (must include version). Defaults to "elasticsearch:8.11.0"
            port: Container port to expose. Defaults to 9200
        """
        super().__init__(image)
        self.port = port
        self.with_exposed_ports(self.port)
        self.with_env("transport.host", "127.0.0.1")
        self.with_env("http.host", "0.0.0.0")
        self.with_env("xpack.security.enabled", "false")
        self.with_env("discovery.type", "single-node")
        # Use HttpWaitStrategy instead of deprecated @wait_container_is_ready decorator
        self.waiting_for(HttpWaitStrategy(port=self.port).for_status_code(200))

    def get_url(self) -> str:
        """Get the URL to access Elasticsearch.

        Returns:
            Full URL to Elasticsearch instance (http://host:port)
        """
        host = self.get_container_host_ip()
        port = self.get_exposed_port(self.port)
        return f"http://{host}:{port}"


class ModernRedisContainer(DockerContainer):
    """Redis container using modern wait strategy API.

    This class replaces testcontainers.redis.RedisContainer to avoid
    the DeprecationWarning from @wait_container_is_ready decorator. Uses structured
    wait strategies (PortWaitStrategy) instead of the deprecated decorator approach.

    Example:
        >>> container = ModernRedisContainer("redis:7-alpine")
        >>> container.start()
        >>> host = container.get_container_host_ip()
        >>> port = container.get_exposed_port(6379)
        >>> # ... use Redis ...
        >>> container.stop()
    """

    def __init__(self, image: str = "redis:latest", port: int = 6379, password: str | None = None) -> None:
        """Initialize Redis container.

        Args:
            image: Docker image name. Defaults to "redis:latest"
            port: Container port to expose. Defaults to 6379
            password: Optional Redis password. If provided, starts Redis with requirepass
        """
        super().__init__(image)
        self.port = port
        self.password = password
        self.with_exposed_ports(self.port)
        if self.password:
            self.with_command(f"redis-server --requirepass {self.password}")
        # Use PortWaitStrategy instead of deprecated @wait_container_is_ready decorator
        self.waiting_for(PortWaitStrategy(self.port))
