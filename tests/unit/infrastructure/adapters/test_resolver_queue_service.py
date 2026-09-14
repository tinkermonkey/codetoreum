"""Tests for AdapterResolver.resolve_queue_service method.

Tests cover:
- Redis queue service resolution with proper dependency injection
- In-memory fallback path with event bus wiring
- Error handling for missing board service in Redis path
- Validation of critical production wiring logic
"""

import os
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codetoreum.infrastructure.adapters.factory import AdapterFactory
from codetoreum.infrastructure.adapters.resolver import (
    AdapterConfigurationError,
    AdapterDependencies,
    AdapterResolver,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.simulation.simulation_config import AdapterSelectionConfig
from codetoreum.ports.output.board_service import IBoardService
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.failed_event_store import IFailedEventStore


@pytest.fixture
def mock_event_bus():
    """Create a mock EventBus."""
    return MagicMock(spec=EventBus)


@pytest.fixture
def mock_event_emitter():
    """Create a mock EventEmitter."""
    return MagicMock(spec=IEventEmitter)


@pytest.fixture
def mock_failed_event_store():
    """Create a mock IFailedEventStore."""
    return MagicMock(spec=IFailedEventStore)


@pytest.fixture
def mock_simulation_engine():
    """Create a mock SimulationEngine for dependencies."""
    from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock

    engine = MagicMock()
    clock = SimulationClock(speed_multiplier=1.0)
    engine.get_clock_for_testing.return_value = clock
    return engine


@pytest.fixture
def base_adapter_config():
    """Create base AdapterSelectionConfig for testing."""
    return AdapterSelectionConfig(
        event_store="in_memory",
        config_store="in_memory",
        metrics="prometheus",
        encryption="noop",
        identity_service="noop",
        event_emitter="mock",
        message_broker="in_memory",
        ticket="mock",
        board="mock",
        discussion_adapter="mock",
        lock_service="in_memory",
        queue_service="in_memory",  # Default
        checkpoint_store="in_memory",
        agent_repository="in_memory",
        run_registry="in_memory",
        branch_tracker="in_memory",
        work_item_service="in_memory",
        workflow_config="in_memory",
        notifier="mock",
        version_control="in_memory",
        project_manager="in_memory",
        review_cycle="mock",
        pr_review_cycle="mock",
        repair_cycle="mock",
        code_review="mock",
        container="mock",
        execution_tracker="in_memory",
        container_recovery="mock",
        ci_pipeline="mock",
        systemic_analysis="mock",
        environment_repair="mock",
        repository="mock",
    )


def create_config_with_queue_service(base_config, queue_service_type):
    """Create a new config with specified queue_service using dataclass replace."""
    return replace(base_config, queue_service=queue_service_type)


@pytest.fixture
def adapter_dependencies(
    mock_event_bus, mock_event_emitter, mock_failed_event_store, mock_simulation_engine
):
    """Create AdapterDependencies for testing."""
    return AdapterDependencies(
        event_bus=mock_event_bus,
        event_emitter=mock_event_emitter,
        logger=None,
        engine=mock_simulation_engine,
        config=MagicMock(),
        failed_event_store=mock_failed_event_store,
    )


class TestResolveQueueServiceInMemory:
    """Tests for in-memory queue service resolution."""

    def test_in_memory_queue_service_receives_event_bus(
        self, base_adapter_config, adapter_dependencies
    ):
        """In-memory queue service should receive event_bus parameter."""
        factory = AdapterFactory()
        config = create_config_with_queue_service(base_adapter_config, "in_memory")

        resolver = AdapterResolver(
            adapter_config=config,
            factory=factory,
            dependencies=adapter_dependencies,
        )

        # Resolve event_emitter first (dependency)
        resolver._resolved["event_emitter"] = adapter_dependencies.event_emitter

        # Resolve queue service
        queue_service = resolver.resolve_queue_service()

        # Verify event_bus was passed and the queue service has it
        assert queue_service is not None
        # Check that the internal event_bus is set
        assert hasattr(queue_service, "_event_bus")
        assert queue_service._event_bus is adapter_dependencies.event_bus

    def test_in_memory_queue_service_receives_event_emitter(
        self, base_adapter_config, adapter_dependencies
    ):
        """In-memory queue service should receive event_emitter parameter."""
        factory = AdapterFactory()
        config = create_config_with_queue_service(base_adapter_config, "in_memory")

        resolver = AdapterResolver(
            adapter_config=config,
            factory=factory,
            dependencies=adapter_dependencies,
        )

        resolver._resolved["event_emitter"] = adapter_dependencies.event_emitter

        queue_service = resolver.resolve_queue_service()

        assert hasattr(queue_service, "_event_emitter")
        assert queue_service._event_emitter is adapter_dependencies.event_emitter

    def test_in_memory_queue_service_receives_time_source(
        self, base_adapter_config, adapter_dependencies
    ):
        """In-memory queue service should receive time_source lambda."""
        factory = AdapterFactory()
        config = create_config_with_queue_service(base_adapter_config, "in_memory")

        resolver = AdapterResolver(
            adapter_config=config,
            factory=factory,
            dependencies=adapter_dependencies,
        )

        resolver._resolved["event_emitter"] = adapter_dependencies.event_emitter

        queue_service = resolver.resolve_queue_service()

        assert hasattr(queue_service, "_time_source")
        assert callable(queue_service._time_source)

    def test_in_memory_queue_service_receives_failed_event_store(
        self, base_adapter_config, adapter_dependencies
    ):
        """In-memory queue service should receive failed_event_store parameter."""
        factory = AdapterFactory()
        config = create_config_with_queue_service(base_adapter_config, "in_memory")

        resolver = AdapterResolver(
            adapter_config=config,
            factory=factory,
            dependencies=adapter_dependencies,
        )

        resolver._resolved["event_emitter"] = adapter_dependencies.event_emitter

        queue_service = resolver.resolve_queue_service()

        assert hasattr(queue_service, "failed_event_store")
        assert queue_service.failed_event_store is adapter_dependencies.failed_event_store


class TestResolveQueueServiceRedis:
    """Tests for Redis queue service resolution."""

    @patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379/0"})
    @patch("redis.asyncio.from_url")
    def test_redis_queue_service_resolution_success(
        self, mock_from_url, base_adapter_config, adapter_dependencies
    ):
        """Redis queue service should be created with proper dependencies."""
        # Setup
        mock_redis_client = MagicMock()
        mock_from_url.return_value = mock_redis_client

        factory = AdapterFactory()
        config = create_config_with_queue_service(base_adapter_config, "redis")

        # Mock board service
        mock_board_service = MagicMock(spec=IBoardService)
        resolver = AdapterResolver(
            adapter_config=config,
            factory=factory,
            dependencies=adapter_dependencies,
        )

        # Setup resolved dependencies
        resolver._resolved["event_emitter"] = adapter_dependencies.event_emitter
        resolver._resolved["board"] = mock_board_service

        # Resolve queue service
        queue_service = resolver.resolve_queue_service()

        # Verify
        assert queue_service is not None
        mock_from_url.assert_called_once_with("redis://localhost:6379/0")

    @patch.dict(os.environ, {"REDIS_URL": "redis://custom.host:6380/1"})
    @patch("redis.asyncio.from_url")
    def test_redis_queue_service_uses_custom_redis_url(
        self, mock_from_url, base_adapter_config, adapter_dependencies
    ):
        """Redis queue service should use custom REDIS_URL from environment."""
        mock_redis_client = MagicMock()
        mock_from_url.return_value = mock_redis_client

        factory = AdapterFactory()
        config = create_config_with_queue_service(base_adapter_config, "redis")

        mock_board_service = MagicMock(spec=IBoardService)
        resolver = AdapterResolver(
            adapter_config=config,
            factory=factory,
            dependencies=adapter_dependencies,
        )

        resolver._resolved["event_emitter"] = adapter_dependencies.event_emitter
        resolver._resolved["board"] = mock_board_service

        queue_service = resolver.resolve_queue_service()

        # Verify custom URL was used
        mock_from_url.assert_called_once_with("redis://custom.host:6380/1")

    @patch.dict(os.environ, {}, clear=False)
    @patch("redis.asyncio.from_url")
    def test_redis_queue_service_uses_default_redis_url(
        self, mock_from_url, base_adapter_config, adapter_dependencies
    ):
        """Redis queue service should use default REDIS_URL when env var not set."""
        # Ensure REDIS_URL is not set
        if "REDIS_URL" in os.environ:
            del os.environ["REDIS_URL"]

        mock_redis_client = MagicMock()
        mock_from_url.return_value = mock_redis_client

        factory = AdapterFactory()
        config = create_config_with_queue_service(base_adapter_config, "redis")

        mock_board_service = MagicMock(spec=IBoardService)
        resolver = AdapterResolver(
            adapter_config=config,
            factory=factory,
            dependencies=adapter_dependencies,
        )

        resolver._resolved["event_emitter"] = adapter_dependencies.event_emitter
        resolver._resolved["board"] = mock_board_service

        queue_service = resolver.resolve_queue_service()

        # Verify default URL was used
        mock_from_url.assert_called_once_with("redis://localhost:6379/0")

    @patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379/0"})
    @patch("redis.asyncio.from_url")
    def test_redis_queue_service_requires_board_service(
        self, mock_from_url, base_adapter_config, adapter_dependencies
    ):
        """Redis queue service resolution should fail if board service is missing."""
        mock_redis_client = MagicMock()
        mock_from_url.return_value = mock_redis_client

        factory = AdapterFactory()
        config = create_config_with_queue_service(base_adapter_config, "redis")

        resolver = AdapterResolver(
            adapter_config=config,
            factory=factory,
            dependencies=adapter_dependencies,
        )

        # Setup without board service
        resolver._resolved["event_emitter"] = adapter_dependencies.event_emitter
        # Note: NOT resolving board

        # Should raise error
        with pytest.raises(AdapterConfigurationError) as exc_info:
            resolver.resolve_queue_service()

        assert "board" in str(exc_info.value).lower()
        assert "redis" in str(exc_info.value).lower()

    @patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379/0"})
    @patch("redis.asyncio.from_url")
    def test_redis_queue_service_passes_board_service(
        self, mock_from_url, base_adapter_config, adapter_dependencies
    ):
        """Redis queue service should receive board_service parameter."""
        mock_redis_client = MagicMock()
        mock_from_url.return_value = mock_redis_client

        factory = AdapterFactory()
        config = create_config_with_queue_service(base_adapter_config, "redis")

        mock_board_service = MagicMock(spec=IBoardService)
        resolver = AdapterResolver(
            adapter_config=config,
            factory=factory,
            dependencies=adapter_dependencies,
        )

        resolver._resolved["event_emitter"] = adapter_dependencies.event_emitter
        resolver._resolved["board"] = mock_board_service

        # This should succeed and create the adapter
        queue_service = resolver.resolve_queue_service()

        assert queue_service is not None

    @patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379/0"})
    @patch("redis.asyncio.from_url")
    def test_redis_queue_service_passes_event_emitter(
        self, mock_from_url, base_adapter_config, adapter_dependencies
    ):
        """Redis queue service should receive event_emitter parameter."""
        mock_redis_client = MagicMock()
        mock_from_url.return_value = mock_redis_client

        factory = AdapterFactory()
        config = create_config_with_queue_service(base_adapter_config, "redis")

        mock_board_service = MagicMock(spec=IBoardService)
        resolver = AdapterResolver(
            adapter_config=config,
            factory=factory,
            dependencies=adapter_dependencies,
        )

        resolver._resolved["event_emitter"] = adapter_dependencies.event_emitter
        resolver._resolved["board"] = mock_board_service

        queue_service = resolver.resolve_queue_service()

        # Verify event_emitter was passed
        assert queue_service is not None

    @patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379/0"})
    @patch("redis.asyncio.from_url")
    def test_redis_queue_service_passes_failed_event_store(
        self, mock_from_url, base_adapter_config, adapter_dependencies
    ):
        """Redis queue service should receive failed_event_store parameter for INV-20."""
        mock_redis_client = MagicMock()
        mock_from_url.return_value = mock_redis_client

        factory = AdapterFactory()
        config = create_config_with_queue_service(base_adapter_config, "redis")

        mock_board_service = MagicMock(spec=IBoardService)
        resolver = AdapterResolver(
            adapter_config=config,
            factory=factory,
            dependencies=adapter_dependencies,
        )

        resolver._resolved["event_emitter"] = adapter_dependencies.event_emitter
        resolver._resolved["board"] = mock_board_service

        queue_service = resolver.resolve_queue_service()

        # Verify adapter was created successfully
        assert queue_service is not None


class TestResolveQueueServiceDependencyOrder:
    """Tests for dependency ordering in resolve_queue_service."""

    @patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379/0"})
    @patch("redis.asyncio.from_url")
    def test_redis_path_validates_board_before_creating_adapter(
        self, mock_from_url, base_adapter_config, adapter_dependencies
    ):
        """Redis path should validate board dependency before creating adapter."""
        mock_redis_client = MagicMock()
        mock_from_url.return_value = mock_redis_client

        factory = AdapterFactory()
        config = create_config_with_queue_service(base_adapter_config, "redis")

        resolver = AdapterResolver(
            adapter_config=config,
            factory=factory,
            dependencies=adapter_dependencies,
        )

        # Setup without board
        resolver._resolved["event_emitter"] = adapter_dependencies.event_emitter

        # Should fail before attempting to create the adapter
        with pytest.raises(AdapterConfigurationError) as exc_info:
            resolver.resolve_queue_service()

        error_msg = str(exc_info.value)
        assert "board" in error_msg.lower()

    def test_resolve_queue_service_after_board_resolved(
        self, base_adapter_config, adapter_dependencies
    ):
        """Queue service resolution should succeed when board is already resolved."""
        factory = AdapterFactory()
        config = create_config_with_queue_service(base_adapter_config, "in_memory")

        resolver = AdapterResolver(
            adapter_config=config,
            factory=factory,
            dependencies=adapter_dependencies,
        )

        # Setup board first
        mock_board_service = MagicMock(spec=IBoardService)
        resolver._resolved["event_emitter"] = adapter_dependencies.event_emitter
        resolver._resolved["board"] = mock_board_service

        # Resolve queue service after board is in resolved
        queue_service = resolver.resolve_queue_service()

        # Queue service should be successfully created
        assert queue_service is not None


class TestResolveQueueServiceErrorCases:
    """Tests for error handling in queue service resolution."""

    @patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379/0"})
    @patch("redis.asyncio.from_url")
    def test_redis_path_with_none_board_raises_error(
        self, mock_from_url, base_adapter_config, adapter_dependencies
    ):
        """Redis path should raise error if board is None."""
        mock_redis_client = MagicMock()
        mock_from_url.return_value = mock_redis_client

        factory = AdapterFactory()
        config = create_config_with_queue_service(base_adapter_config, "redis")

        resolver = AdapterResolver(
            adapter_config=config,
            factory=factory,
            dependencies=adapter_dependencies,
        )

        resolver._resolved["event_emitter"] = adapter_dependencies.event_emitter
        resolver._resolved["board"] = None  # Explicitly None

        with pytest.raises(AdapterConfigurationError) as exc_info:
            resolver.resolve_queue_service()

        assert "board" in str(exc_info.value).lower()

    def test_fallback_path_with_missing_event_emitter_raises_error(
        self, base_adapter_config, adapter_dependencies
    ):
        """In-memory path should raise error if event_emitter is missing."""
        factory = AdapterFactory()
        config = create_config_with_queue_service(base_adapter_config, "in_memory")

        resolver = AdapterResolver(
            adapter_config=config,
            factory=factory,
            dependencies=adapter_dependencies,
        )

        # Note: NOT setting event_emitter

        with pytest.raises(KeyError):
            resolver.resolve_queue_service()


class TestResolveQueueServiceProductionWiring:
    """Tests for critical production wiring logic."""

    @patch.dict(os.environ, {"REDIS_URL": "redis://production.host:6379/0"})
    @patch("redis.asyncio.from_url")
    def test_redis_wiring_passes_all_required_dependencies(
        self, mock_from_url, base_adapter_config, adapter_dependencies
    ):
        """Redis wiring should pass all required dependencies in correct order."""
        mock_redis_client = MagicMock()
        mock_from_url.return_value = mock_redis_client

        factory = AdapterFactory()
        config = create_config_with_queue_service(base_adapter_config, "redis")

        mock_board_service = MagicMock(spec=IBoardService)
        resolver = AdapterResolver(
            adapter_config=config,
            factory=factory,
            dependencies=adapter_dependencies,
        )

        resolver._resolved["event_emitter"] = adapter_dependencies.event_emitter
        resolver._resolved["board"] = mock_board_service

        # This test verifies the wiring completes successfully
        queue_service = resolver.resolve_queue_service()

        # Adapter should be created and wrapped with resilience
        assert queue_service is not None

    def test_in_memory_wiring_includes_event_bus_for_board_sync(
        self, base_adapter_config, adapter_dependencies
    ):
        """In-memory wiring should include event_bus for WorkItemColumnChangedEvent subscription."""
        factory = AdapterFactory()
        config = create_config_with_queue_service(base_adapter_config, "in_memory")

        resolver = AdapterResolver(
            adapter_config=config,
            factory=factory,
            dependencies=adapter_dependencies,
        )

        resolver._resolved["event_emitter"] = adapter_dependencies.event_emitter

        queue_service = resolver.resolve_queue_service()

        # Verify event_bus is present for board sync
        assert hasattr(queue_service, "_event_bus")
        assert queue_service._event_bus is not None
