"""Test configuration and shared fixtures."""

import asyncio
import time
from collections.abc import Awaitable, Callable, Generator

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
            # Properly close all resources to avoid ResourceWarnings
            import gc
            try:
                if hasattr(client, 'api'):
                    api = client.api
                    # Close the API client's session and adapter connection pools
                    if hasattr(api, '_session') and api._session:
                        try:
                            api._session.close()
                        except Exception:
                            pass
                    if hasattr(api, '_adapters') and api._adapters:
                        try:
                            for adapter in api._adapters.values():
                                if hasattr(adapter, 'close'):
                                    adapter.close()
                        except Exception:
                            pass
                    if hasattr(api, 'close'):
                        try:
                            api.close()
                        except Exception:
                            pass
            except Exception:
                # Ignore cleanup errors
                pass
            try:
                client.close()
            except Exception:
                # Ignore cleanup errors
                pass
            # Force garbage collection multiple times to close any remaining sockets
            # The first gc.collect() might not be enough for some pools to release resources
            gc.collect()
            gc.collect()
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
        # Properly close all resources to avoid ResourceWarnings
        import gc
        try:
            if hasattr(client, 'api'):
                api = client.api
                # Close the API client's session and adapter connection pools
                if hasattr(api, '_session') and api._session:
                    try:
                        api._session.close()
                    except Exception:
                        pass
                if hasattr(api, '_adapters') and api._adapters:
                    try:
                        for adapter in api._adapters.values():
                            if hasattr(adapter, 'close'):
                                adapter.close()
                    except Exception:
                        pass
                if hasattr(api, 'close'):
                    try:
                        api.close()
                    except Exception:
                        pass
        except Exception:
            # Ignore cleanup errors
            pass
        try:
            client.close()
        except Exception:
            # Ignore cleanup errors
            pass
        # Force garbage collection multiple times to close any remaining sockets
        # The first gc.collect() might not be enough for some pools to release resources
        gc.collect()
        gc.collect()


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


@pytest.fixture(scope="function", autouse=True)
def _cleanup_event_loop() -> Generator[None, None, None]:
    """Ensure event loop is properly closed to prevent ResourceWarnings.

    With asyncio_default_fixture_loop_scope = "function", pytest-asyncio creates
    a new event loop for each test. This fixture ensures the loop is properly
    closed after the test completes to prevent ResourceWarnings from unclosed
    sockets in the event loop.

    This is a workaround for pytest-asyncio's automatic loop management which
    sometimes leaves loops in a state where they trigger ResourceWarnings during
    garbage collection.

    See: https://github.com/pytest-dev/pytest-asyncio/issues
    """
    yield

    # After test completes, ensure any event loop is properly closed
    try:
        loop = asyncio.get_event_loop()
        if loop and not loop.is_closed():
            # Cancel all pending tasks
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            # Run loop one more time to process cancellations
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            # Close the loop
            loop.close()
    except RuntimeError:
        # No event loop in current thread, which is fine
        pass


# ============================================================================
# Wait Helper Functions for Async Tests
# ============================================================================
# These helpers improve test reliability by replacing hardcoded sleep() calls
# with condition-based polling. This makes tests faster and less flaky.
# ============================================================================


async def wait_for_condition(
    check_fn: Callable[[], Awaitable[bool]] | Callable[[], bool],
    timeout: float = 5.0,
    poll_interval: float = 0.1,
    timeout_message: str = "Timeout waiting for condition"
) -> bool:
    """Wait for an async or sync condition to be true.

    Polls a condition function repeatedly until it returns True or timeout expires.
    This is preferred over asyncio.sleep() in tests because:
    - Tests run as fast as possible (not waiting for hardcoded delays)
    - Tests are more reliable (don't fail due to arbitrary timing)
    - Poll interval is configurable and can be very short

    Args:
        check_fn: Async or sync callable that returns bool. Called repeatedly.
        timeout: Maximum seconds to wait. Defaults to 5.0
        poll_interval: Seconds between checks. Defaults to 0.1
        timeout_message: Message for assertion error if timeout occurs

    Returns:
        True if condition became true before timeout
        False if timeout expired

    Raises:
        AssertionError if timeout expires (if check_fn doesn't handle it)

    Example:
        >>> # Wait for database connection
        >>> async def check_db():
        ...     try:
        ...         await db.ping()
        ...         return True
        ...     except Exception:
        ...         return False
        >>> result = await wait_for_condition(check_db, timeout=10.0)
        >>> assert result, "Database never connected"

        >>> # Wait with lambda for simple checks
        >>> async def is_cache_ready():
        ...     return cache.hit_count > 0
        >>> await wait_for_condition(is_cache_ready)

        >>> # Wait for list length
        >>> async def has_items():
        ...     items = await get_items()
        ...     return len(items) > 5
        >>> await wait_for_condition(has_items)
    """
    start = time.time()
    last_error = None

    while time.time() - start < timeout:
        try:
            # Call the check function - handle both async and sync
            if asyncio.iscoroutinefunction(check_fn):
                result = await check_fn()
            else:
                result = check_fn()

            if result:
                return True
        except Exception as e:
            # Store exception for debugging, continue polling
            last_error = e

        # Wait before next check (unless we're about to timeout)
        if time.time() - start < timeout:
            await asyncio.sleep(poll_interval)

    # Timeout expired
    error_msg = f"{timeout_message} (timeout after {timeout}s)"
    if last_error:
        error_msg += f": {last_error}"
    return False


async def assert_condition(
    check_fn: Callable[[], Awaitable[bool]] | Callable[[], bool],
    timeout: float = 5.0,
    poll_interval: float = 0.1,
    message: str = "Condition never became true"
) -> None:
    """Wait for condition and raise AssertionError if timeout.

    Convenience wrapper around wait_for_condition that raises AssertionError
    instead of returning False. Useful for test assertions.

    Args:
        check_fn: Async or sync callable that returns bool
        timeout: Maximum seconds to wait
        poll_interval: Seconds between checks
        message: Custom assertion message

    Raises:
        AssertionError: If condition doesn't become true within timeout

    Example:
        >>> await assert_condition(
        ...     lambda: cache.has_key("user:123"),
        ...     timeout=5.0,
        ...     message="User not found in cache"
        ... )
    """
    result = await wait_for_condition(check_fn, timeout, poll_interval, message)
    assert result, message


# Migration helpers for converting hardcoded sleeps to polling
# These are kept simple to support gradual migration

async def wait_for_cache_sync(
    check_fn: Callable[[], Awaitable[bool]],
    timeout: float = 5.0
) -> bool:
    """Wait for cache to sync. Replaces asyncio.sleep(1) in tests.

    Args:
        check_fn: Async function that checks if cache is ready
        timeout: Maximum seconds to wait

    Returns:
        True if cache synced, False if timeout
    """
    return await wait_for_condition(check_fn, timeout=timeout, poll_interval=0.1)


async def wait_for_storage(
    check_fn: Callable[[], Awaitable[bool]],
    timeout: float = 5.0
) -> bool:
    """Wait for storage operation. Replaces asyncio.sleep(1) in tests.

    Args:
        check_fn: Async function that checks if storage is ready
        timeout: Maximum seconds to wait

    Returns:
        True if storage ready, False if timeout
    """
    return await wait_for_condition(check_fn, timeout=timeout, poll_interval=0.1)


async def wait_for_elasticsearch_indexing(
    es_client,
    timeout: float = 5.0
) -> bool:
    """Wait for Elasticsearch indexing to complete.

    Replaces hardcoded asyncio.sleep(1) delays in Elasticsearch tests.
    Checks cluster health to ensure all shards are ready.

    Args:
        es_client: AsyncElasticsearch client
        timeout: Maximum seconds to wait

    Returns:
        True if indexing complete, False if timeout
    """
    async def is_ready():
        try:
            # Refresh to ensure all pending documents are indexed
            await es_client.indices.refresh(index="_all")
            health = await es_client.cluster.health()
            # All shards should be active (green status)
            return health.get("status") in ("green", "yellow")
        except Exception:
            return False

    return await wait_for_condition(is_ready, timeout=timeout, poll_interval=0.05)


async def wait_for_polling_cycle(
    event_list: list,
    expected_count: int = 1,
    timeout: float = 5.0
) -> bool:
    """Wait for polling adapter to detect events.

    Replaces hardcoded asyncio.sleep() when waiting for polling cycles.
    Polls rapidly instead of sleeping for a fixed duration.

    Args:
        event_list: List that events are appended to
        expected_count: Minimum number of events expected
        timeout: Maximum seconds to wait

    Returns:
        True if expected events detected, False if timeout
    """
    async def has_events():
        return len(event_list) >= expected_count

    return await wait_for_condition(has_events, timeout=timeout, poll_interval=0.05)
