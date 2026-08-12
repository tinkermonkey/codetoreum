"""Test configuration and shared fixtures."""

import asyncio
import os
import time
from collections.abc import AsyncGenerator, Awaitable, Callable, Generator
from dataclasses import dataclass

import docker
import pytest
from testcontainers.core.container import DockerContainer

# Wait strategies may not be available in all testcontainers versions
# These are only used in integration tests, so we can import them conditionally
try:
    from testcontainers.core.wait_strategies import HttpWaitStrategy, PortWaitStrategy, WaitStrategy
except ImportError:
    # Fallback for testcontainers versions without wait_strategies module
    # These will be replaced with stubs if needed
    class WaitStrategy:  # type: ignore
        """Stub for missing WaitStrategy."""
        def __init__(self) -> None:
            self._startup_timeout = 60
            self._poll_interval = 0.1

    class HttpWaitStrategy(WaitStrategy):  # type: ignore
        """Stub for missing HttpWaitStrategy."""
        def __init__(self, port: int = 80) -> None:
            super().__init__()
            self.port = port

        def for_status_code(self, status_code: int) -> "HttpWaitStrategy":
            return self

    class PortWaitStrategy(WaitStrategy):  # type: ignore
        """Stub for missing PortWaitStrategy."""
        def __init__(self, port: int = 80) -> None:
            super().__init__()
            self.port = port

# Disable OpenTelemetry for tests to prevent daemon threads from hanging event loops
# This must happen before any codetoreum imports that trigger fastapi_app import
os.environ.setdefault("OTEL_ENABLED", "false")
os.environ.setdefault("OTEL_TRACES_ENABLED", "false")

# Configure testcontainers to handle Docker socket properly
# This is important for systems with Docker socket proxies or unusual network configs
os.environ.setdefault("TESTCONTAINERS_RYUK_PRIVILEGED", "true")
os.environ.setdefault("TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE", "/var/run/docker.sock")

# Patch testcontainers Reaper to handle connection failures gracefully
# Must be done before importing DockerContainer from testcontainers
# This prevents testcontainers from failing when Reaper can't connect
try:
    from testcontainers.core.container import Reaper

    # Store original methods
    _original_reaper_get_instance = Reaper.get_instance
    _original_reaper_init = Reaper.__init__

    # Create a NullReaper for handling Reaper connection failures
    class _NullReaper:
        """No-op Reaper for environments where Reaper can't connect."""
        def __init__(self):
            self.socket = None

        def delete_containers(self, *args, **kwargs):
            """No-op cleanup."""
            pass

    # Patch get_instance to catch connection errors
    @classmethod
    def _patched_get_instance(cls):
        """Get or create Reaper instance, falling back to NullReaper on connection failure."""
        if cls._instance is not None:
            return cls._instance

        try:
            # Try to create the real Reaper
            return _original_reaper_get_instance()
        except ConnectionRefusedError as e:
            # Reaper connection failed, use NullReaper instead
            import logging
            logging.warning(f"Testcontainers Reaper connection failed ({e}), using no-op Reaper for cleanup")
            cls._instance = _NullReaper()
            return cls._instance
        except Exception:
            # Other exceptions should still fail
            raise

    # Apply the patch
    Reaper.get_instance = _patched_get_instance

except ImportError:
    # testcontainers not available yet, will be imported later
    pass

from codetoreum.adapters.testing.fake_container_adapter import FakeContainerAdapter
from codetoreum.adapters.testing.in_memory_event_store import InMemoryEventStore
from codetoreum.adapters.testing.in_memory_ticket_adapter import InMemoryTicketAdapter
from codetoreum.domain.events import CodetoreumEvent, now_iso
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.simulation import SimulationConfig
from codetoreum.infrastructure.simulation.bootstrap import SimulationApplicationBootstrap

# ============================================================================
# TestEvent Fixture for Adapter Tests
# ============================================================================


@dataclass(frozen=True)
class TestEvent(CodetoreumEvent):
    """Minimal compliant event for adapter contract testing.

    This frozen dataclass fixture provides a lightweight CodetoreumEvent
    subclass for use in adapter unit tests that need a simple event instance
    without the domain-specific fields of production events.

    Attributes:
        detail: Optional detail string for test-specific information.
    """

    detail: str = ""


@pytest.fixture
def test_event() -> TestEvent:
    """Create a test event instance for adapter testing.

    Returns:
        TestEvent instance with default values.

    Example:
        >>> @pytest.mark.asyncio
        >>> async def test_event_store(test_event):
        ...     await event_store.append("stream-1", [test_event])
        ...     events = await event_store.retrieve("stream-1")
        ...     assert len(events) == 1
    """
    return TestEvent(
        type="test.event",
        timestamp=now_iso(),
        source="test",
        detail="test event",
    )


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
                if hasattr(client, "api"):
                    api = client.api
                    # Close the API client's session and adapter connection pools
                    if hasattr(api, "_session") and api._session:
                        try:
                            api._session.close()
                        except Exception:
                            pass
                    if hasattr(api, "_adapters") and api._adapters:
                        try:
                            for adapter in api._adapters.values():
                                if hasattr(adapter, "close"):
                                    adapter.close()
                        except Exception:
                            pass
                    if hasattr(api, "close"):
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
docker_available = pytest.mark.skipif(not is_docker_available(), reason="Docker is not available or not running")


ALPINE_IMAGE = "alpine:latest"


@pytest.fixture(scope="session")
def ensure_alpine_image() -> None:
    """Ensure alpine:latest is available so Docker integration tests can run.

    Session-scoped: runs once per test session. Skips if Docker is unavailable.
    Checks for a local image first, then tries to pull. Skips dependent tests
    with a clear message if the image cannot be obtained.
    """
    if not is_docker_available():
        return

    client = docker.from_env()
    try:
        try:
            client.images.get(ALPINE_IMAGE)
            return
        except docker.errors.ImageNotFound:
            pass

        try:
            client.images.pull("alpine", tag="latest")
        except Exception:
            pytest.skip(
                f"{ALPINE_IMAGE} is not available locally and could not be pulled. "
                "Ensure the Docker daemon has network access or pre-load the image."
            )
    finally:
        client.close()


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
            if hasattr(client, "api"):
                api = client.api
                # Close the API client's session and adapter connection pools
                if hasattr(api, "_session") and api._session:
                    try:
                        api._session.close()
                    except Exception:
                        pass
                if hasattr(api, "_adapters") and api._adapters:
                    try:
                        for adapter in api._adapters.values():
                            if hasattr(adapter, "close"):
                                adapter.close()
                    except Exception:
                        pass
                if hasattr(api, "close"):
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
def container_adapter() -> Generator[FakeContainerAdapter, None, None]:
    """Create fake container adapter with automatic cleanup.

    Yields:
        FakeContainerAdapter instance
    """
    adapter = FakeContainerAdapter()
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
    the DeprecationWarning from @wait_container_is_ready decorator.

    Example:
        >>> container = ModernElasticsearchContainer("elasticsearch:8.17.0")
        >>> container.start()
        >>> url = container.get_url()
        >>> # ... use Elasticsearch ...
        >>> container.stop()
    """

    def __init__(self, image: str = "elasticsearch:8.17.0", port: int = 9200) -> None:
        """Initialize Elasticsearch container.

        Args:
            image: Docker image name (must include version). Defaults to "elasticsearch:8.17.0"
            port: Container port to expose. Defaults to 9200
        """
        super().__init__(image)
        self.port = port
        self.with_exposed_ports(self.port)
        self.with_env("transport.host", "127.0.0.1")
        self.with_env("http.host", "0.0.0.0")
        self.with_env("xpack.security.enabled", "false")
        self.with_env("discovery.type", "single-node")

    def get_url(self) -> str:
        """Get the URL to access Elasticsearch.

        Returns:
            Full URL to Elasticsearch instance (http://host:port)
        """
        host = self.get_container_host_ip()
        port = self.get_exposed_port(self.port)
        return f"http://{host}:{port}"

    def start(self) -> "ModernElasticsearchContainer":
        """Start container and wait for Elasticsearch to be ready.

        Overrides parent start() to add explicit wait for Elasticsearch readiness
        via HTTP health check, since testcontainers' wait strategies may not work
        reliably with Elasticsearch.

        Returns:
            Self for method chaining
        """
        super().start()
        self._wait_for_elasticsearch()
        return self

    def _wait_for_elasticsearch(self) -> None:
        """Wait for Elasticsearch to respond to HTTP requests.

        Polls the Elasticsearch health endpoint until it responds with 200,
        indicating the cluster is ready to accept queries.

        Raises:
            TimeoutError if Elasticsearch doesn't respond within 60 seconds
        """
        import socket

        host = self.get_container_host_ip()
        port = int(self.get_exposed_port(self.port))
        deadline = time.monotonic() + 60.0
        last_error = None

        while time.monotonic() < deadline:
            try:
                with socket.create_connection((host, port), timeout=2.0) as sock:
                    sock.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
                    response = sock.recv(4096)
                    # Check if we got a 200 response from Elasticsearch
                    if b"HTTP/1.1 200" in response or b"HTTP/2 200" in response:
                        return
                    last_error = f"Got unexpected response: {response[:100]}"
            except (OSError, socket.error) as e:
                last_error = str(e)
            time.sleep(0.1)

        raise TimeoutError(
            f"Elasticsearch on {host}:{port} did not respond within 60s. "
            f"Last error: {last_error}"
        )


class _RedisPingWaitStrategy(WaitStrategy):  # type: ignore
    """Wait strategy that verifies Redis is ready by issuing a PING command.

    PortWaitStrategy only checks that the TCP port accepts connections, which can
    succeed before Redis has finished initializing and is ready to process commands.
    This strategy connects via raw socket and sends a Redis PING, retrying until
    Redis responds with +PONG.
    """

    def __init__(self, port: int = 6379) -> None:
        super().__init__()
        self.port = port

    def wait_until_ready(self, container: "DockerContainer") -> None:
        import socket

        host = container.get_container_host_ip()
        mapped_port = int(container.get_exposed_port(self.port))
        deadline = time.monotonic() + self._startup_timeout
        while time.monotonic() < deadline:
            try:
                with socket.create_connection((host, mapped_port), timeout=1.0) as sock:
                    sock.sendall(b"PING\r\n")
                    response = sock.recv(16)
                    if response.startswith(b"+PONG"):
                        return
            except OSError:
                pass
            time.sleep(self._poll_interval)
        raise TimeoutError(f"Redis on {host}:{mapped_port} did not respond to PING within {self._startup_timeout}s")


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
        # Use PING-based wait strategy to ensure Redis is fully ready (not just TCP-open)
        # Note: waiting_for() method may not be available in all testcontainers versions
        if hasattr(self, "waiting_for"):
            self.waiting_for(_RedisPingWaitStrategy(self.port))


@pytest.fixture(scope="function", autouse=True)
def _cleanup_opentelemetry() -> Generator[None, None, None]:
    """Ensure OpenTelemetry BatchSpanProcessor daemon threads are shut down after each test.

    BatchSpanProcessor starts a background thread with threading.Event() that waits
    indefinitely. If not properly shut down, this thread prevents the event loop from
    closing and causes pytest-timeout to hang.

    This fixture forces shutdown of all TracerProvider and LoggerProvider instances
    by calling force_flush() and shutdown() on their span/log processors.
    """
    yield

    # After test completes, shut down OpenTelemetry processors
    try:
        from opentelemetry import trace
        from opentelemetry._logs import get_logger_provider
        from opentelemetry.sdk._logs import LoggerProvider
        from opentelemetry.sdk.trace import TracerProvider

        # Shut down the global TracerProvider
        try:
            tracer_provider = trace.get_tracer_provider()
            # Check if it's a real TracerProvider (not a Proxy)
            if isinstance(tracer_provider, TracerProvider):
                tracer_provider.force_flush(timeout_millis=1000)
                tracer_provider.shutdown()
        except Exception:
            pass

        # Shut down the global LoggerProvider
        try:
            logger_provider = get_logger_provider()
            # Check if it's a real LoggerProvider (not a Proxy)
            if isinstance(logger_provider, LoggerProvider):
                logger_provider.force_flush(timeout_millis=1000)
                logger_provider.shutdown()
        except Exception:
            pass
    except ImportError:
        # OpenTelemetry not installed, nothing to clean up
        pass
    except Exception:
        # Ignore any errors during cleanup
        pass


@pytest.fixture(scope="function", autouse=True)
def _cleanup_dead_letter_queues() -> Generator[None, None, None]:
    """Ensure all DeadLetterQueue retry processors are stopped after each test.

    DeadLetterQueue instances start a background _retry_loop task when
    start_retry_processor() is called. This fixture ensures all such tasks
    are properly stopped to prevent them from hanging indefinitely and
    blocking test completion.

    This is particularly important because the _retry_loop runs in an infinite
    loop (while self._running), and if not stopped before the event loop
    closes, it can cause timeouts and prevent tests from completing.

    Uses a registry-based approach instead of gc.get_objects() to avoid
    O(n) scans that cause exponential slowdown with hundreds of tests.
    """
    yield

    # After test completes, stop all DeadLetterQueue instances
    try:
        loop = asyncio.get_event_loop()
        if loop and not loop.is_closed():
            # Import here to avoid circular imports
            from codetoreum.infrastructure.dead_letter_queue import get_active_dead_letter_queues

            # Get all running DeadLetterQueue instances from the registry
            # This is O(1) instead of O(n) where n = total objects in memory
            for dlq in get_active_dead_letter_queues():
                # Stop the retry processor
                try:
                    loop.run_until_complete(dlq.stop_retry_processor())
                except Exception:
                    # If loop is already closed, set flag directly
                    dlq._running = False
                    if dlq._retry_task:
                        dlq._retry_task.cancel()
    except Exception:
        # Ignore any errors during cleanup
        pass


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
    timeout_message: str = "Timeout waiting for condition",
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
    message: str = "Condition never became true",
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


async def wait_for_cache_sync(check_fn: Callable[[], Awaitable[bool]], timeout: float = 5.0) -> bool:
    """Wait for cache to sync. Replaces asyncio.sleep(1) in tests.

    Args:
        check_fn: Async function that checks if cache is ready
        timeout: Maximum seconds to wait

    Returns:
        True if cache synced, False if timeout
    """
    return await wait_for_condition(check_fn, timeout=timeout, poll_interval=0.1)


async def wait_for_storage(check_fn: Callable[[], Awaitable[bool]], timeout: float = 5.0) -> bool:
    """Wait for storage operation. Replaces asyncio.sleep(1) in tests.

    Args:
        check_fn: Async function that checks if storage is ready
        timeout: Maximum seconds to wait

    Returns:
        True if storage ready, False if timeout
    """
    return await wait_for_condition(check_fn, timeout=timeout, poll_interval=0.1)


async def wait_for_elasticsearch_indexing(es_client, timeout: float = 5.0) -> bool:
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


async def wait_for_polling_cycle(event_list: list, expected_count: int = 1, timeout: float = 5.0) -> bool:
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


# ====================================================================================
# Simulation Bootstrap Fixtures (Available to all test directories)
# ====================================================================================


@pytest.fixture
def fast_simulation_config() -> SimulationConfig:
    """
    Provide a fast simulation configuration.

    Returns:
        SimulationConfig optimized for speed (100x multiplier)
    """
    return SimulationConfig.create_fast_config(
        scenario_name="test_scenario",
        speed_multiplier=100.0,
    )


@pytest.fixture
async def simulation_bootstrap(
    fast_simulation_config: SimulationConfig,
) -> AsyncGenerator[SimulationApplicationBootstrap, None]:
    """
    Provide a fully set up simulation bootstrap.

    Args:
        fast_simulation_config: Fast simulation configuration fixture

    Yields:
        SimulationApplicationBootstrap instance with app ready for testing

    Cleanup:
        Tears down all resources after test
    """
    bootstrap = SimulationApplicationBootstrap(fast_simulation_config)
    await bootstrap.setup()
    yield bootstrap
    await bootstrap.teardown()


@pytest.fixture
async def simulation_seeder(
    simulation_bootstrap: SimulationApplicationBootstrap,
) -> AsyncGenerator:
    """
    Provide a simulation data seeder for E2E tests.

    This seeder populates domain objects (Agent, WorkItem) required for
    ExecutionServiceAgentExecutor to function properly in end-to-end tests.

    Args:
        simulation_bootstrap: Bootstrap fixture

    Yields:
        SimulationDataSeeder instance ready for seeding test data

    Cleanup:
        Clears seeded data after test
    """
    from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder

    adapters = simulation_bootstrap.adapters
    seeder = SimulationDataSeeder(
        simulation_bootstrap,
        track_items=True,
        agent_repository=adapters.agent_repository,
        work_item_service=adapters.work_item_service,
    )
    yield seeder
    # Cleanup tracked items
    seeder.created_items.clear()
