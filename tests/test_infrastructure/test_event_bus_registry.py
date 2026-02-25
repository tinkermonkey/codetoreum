"""Unit tests for EventBusRegistry with repair cycle support."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from codetoreum.application.event_bus_wiring import (
    EventBusRegistry,
    EventBusWiringError,
    setup_event_bus,
)
from codetoreum.application.event_handlers.repair_cycle_event_handler import (
    RepairCycleEventHandler,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.output.repair_cycle_service import IRepairCycle

# ====================================================================================
# Mock Services and Adapters
# ====================================================================================


class MockRepairCycle(IRepairCycle):
    """Mock repair cycle adapter for testing."""

    def __init__(self):
        """Initialize mock repair cycle."""
        self.executed = False

    async def execute(self, context):
        """Mock execute method."""
        self.executed = True
        return Mock()


# ====================================================================================
# Fixtures
# ====================================================================================


@pytest.fixture
def event_bus():
    """Create an event bus."""
    return EventBus()


@pytest.fixture
def simulation_clock():
    """Create a simulation clock."""
    return SimulationClock(speed_multiplier=100.0)


@pytest.fixture
def mock_repair_cycle():
    """Create a mock repair cycle adapter."""
    return MockRepairCycle()


@pytest.fixture
def mock_orchestrator():
    """Create a mock workflow orchestrator."""
    return Mock()


@pytest.fixture
def mock_execution_service():
    """Create a mock execution service."""
    return Mock()


@pytest.fixture
def mock_review_service():
    """Create a mock review service."""
    return Mock()


@pytest.fixture
def registry(event_bus):
    """Create an EventBusRegistry."""
    return EventBusRegistry(event_bus)


# ====================================================================================
# Tests for EventBusRegistry Initialization
# ====================================================================================


class TestEventBusRegistryInitialization:
    """Tests for EventBusRegistry initialization."""

    def test_registry_initializes_with_event_bus(self, event_bus):
        """Test registry initializes with event bus."""
        registry = EventBusRegistry(event_bus)
        assert registry.event_bus == event_bus

    def test_registry_initializes_with_default_event_bus(self):
        """Test registry creates default event bus if none provided."""
        registry = EventBusRegistry()
        assert registry.event_bus is not None
        assert isinstance(registry.event_bus, EventBus)

    def test_registry_initializes_with_retry_settings(self):
        """Test registry initializes with custom retry settings."""
        registry = EventBusRegistry(
            max_retries=5,
            retry_delay_seconds=0.5,
        )
        assert registry.event_bus is not None

    def test_registry_initializes_empty_handlers(self, event_bus):
        """Test registry initializes with empty handlers dict."""
        registry = EventBusRegistry(event_bus)
        assert registry._handlers == {}

    def test_registry_initializes_empty_services(self, event_bus):
        """Test registry initializes with empty services dict."""
        registry = EventBusRegistry(event_bus)
        assert registry._services == {}


# ====================================================================================
# Tests for Service Registration
# ====================================================================================


class TestEventBusRegistryServiceRegistration:
    """Tests for service registration."""

    def test_register_services_with_repair_cycle(
        self,
        registry,
        mock_repair_cycle,
        simulation_clock,
    ):
        """Test register_services with repair_cycle and clock."""
        registry.register_services(
            repair_cycle=mock_repair_cycle,
            clock=simulation_clock,
        )

        assert registry._services["repair_cycle"] == mock_repair_cycle
        assert registry._services["clock"] == simulation_clock

    def test_register_services_stores_repair_cycle(self, registry, mock_repair_cycle):
        """Test register_services stores repair_cycle adapter."""
        registry.register_services(repair_cycle=mock_repair_cycle)
        assert registry._services["repair_cycle"] == mock_repair_cycle

    def test_register_services_stores_clock(self, registry, simulation_clock):
        """Test register_services stores simulation clock."""
        registry.register_services(clock=simulation_clock)
        assert registry._services["clock"] == simulation_clock

    def test_register_services_with_all_services(
        self,
        registry,
        mock_orchestrator,
        mock_execution_service,
        mock_review_service,
        mock_repair_cycle,
        simulation_clock,
    ):
        """Test register_services with all service types."""
        registry.register_services(
            workflow_orchestrator=mock_orchestrator,
            execution_service=mock_execution_service,
            review_service=mock_review_service,
            repair_cycle=mock_repair_cycle,
            clock=simulation_clock,
        )

        assert len(registry._services) == 5
        assert registry._services["workflow_orchestrator"] == mock_orchestrator
        assert registry._services["execution_service"] == mock_execution_service
        assert registry._services["review_service"] == mock_review_service
        assert registry._services["repair_cycle"] == mock_repair_cycle
        assert registry._services["clock"] == simulation_clock

    def test_register_services_with_no_arguments(self, registry):
        """Test register_services with no arguments (should be no-op)."""
        registry.register_services()
        assert registry._services == {}



# ====================================================================================
# Tests for Repair Cycle Handler Registration
# ====================================================================================


class TestEventBusRegistryRepairCycleHandler:
    """Tests for repair cycle handler registration."""

    def test_register_handlers_with_repair_cycle(
        self,
        registry,
        mock_repair_cycle,
        simulation_clock,
    ):
        """Test register_handlers with repair_cycle parameter."""
        registry.register_services(
            repair_cycle=mock_repair_cycle,
            clock=simulation_clock,
        )
        registry.register_handlers(register_repair_cycle=True)

        # Handler should be registered
        assert "repair_cycle" in registry._handlers
        handler = registry._handlers["repair_cycle"]
        assert isinstance(handler, RepairCycleEventHandler)
        assert handler.repair_cycle == mock_repair_cycle
        assert handler.clock == simulation_clock

    def test_register_handlers_repair_cycle_default_false(
        self,
        registry,
        mock_repair_cycle,
    ):
        """Test register_repair_cycle defaults to False."""
        registry.register_services(repair_cycle=mock_repair_cycle)
        registry.register_handlers(register_repair_cycle=False)

        # Handler should not be registered
        assert "repair_cycle" not in registry._handlers

    def test_register_handlers_skips_missing_repair_cycle_service(
        self,
        registry,
        caplog,
    ):
        """Test register_handlers skips when repair_cycle service missing."""
        # Register handlers without repair_cycle service
        registry.register_handlers(register_repair_cycle=True)

        # Handler should not be registered
        assert "repair_cycle" not in registry._handlers
        # Warning should be logged
        assert "not registered" in caplog.text.lower()

    def test_register_handlers_repair_cycle_with_clock(
        self,
        registry,
        mock_repair_cycle,
        simulation_clock,
    ):
        """Test repair cycle handler gets clock from services."""
        registry.register_services(
            repair_cycle=mock_repair_cycle,
            clock=simulation_clock,
        )
        registry.register_handlers(register_repair_cycle=True)

        handler = registry._handlers["repair_cycle"]
        assert handler.clock == simulation_clock

    def test_register_handlers_repair_cycle_without_clock(
        self,
        registry,
        mock_repair_cycle,
    ):
        """Test repair cycle handler works without clock."""
        registry.register_services(repair_cycle=mock_repair_cycle)
        registry.register_handlers(register_repair_cycle=True)

        handler = registry._handlers["repair_cycle"]
        assert handler.clock is None

    def test_register_handlers_repair_cycle_event_bus_passed(
        self,
        registry,
        mock_repair_cycle,
        event_bus,
    ):
        """Test repair cycle handler receives event bus."""
        registry.register_services(repair_cycle=mock_repair_cycle)
        registry.register_handlers(register_repair_cycle=True)

        handler = registry._handlers["repair_cycle"]
        assert handler.event_bus == event_bus


# ====================================================================================
# Tests for Handler Registration
# ====================================================================================


class TestEventBusRegistryHandlerRegistration:
    """Tests for handler registration."""

    def test_register_handlers_only_repair_cycle(
        self,
        registry,
        mock_repair_cycle,
    ):
        """Test register_handlers with only repair_cycle enabled."""
        registry.register_services(repair_cycle=mock_repair_cycle)
        registry.register_handlers(
            register_workflow=False,
            register_execution=False,
            register_review=False,
            register_repair_cycle=True,
        )

        # Only repair_cycle handler should be registered
        assert len(registry._handlers) == 1
        assert "repair_cycle" in registry._handlers

    def test_register_handlers_multiple_handlers(
        self,
        registry,
        mock_orchestrator,
        mock_execution_service,
        mock_review_service,
        mock_repair_cycle,
    ):
        """Test register_handlers with multiple handler types."""
        registry.register_services(
            workflow_orchestrator=mock_orchestrator,
            execution_service=mock_execution_service,
            review_service=mock_review_service,
            repair_cycle=mock_repair_cycle,
        )
        registry.register_handlers(
            register_workflow=True,
            register_execution=True,
            register_review=True,
            register_repair_cycle=True,
        )

        # All handlers should be registered
        assert len(registry._handlers) >= 4



# ====================================================================================
# Tests for setup_event_bus Function
# ====================================================================================


class TestSetupEventBusFunction:
    """Tests for setup_event_bus convenience function."""

    def test_setup_event_bus_creates_registry(self, mock_repair_cycle, simulation_clock):
        """Test setup_event_bus creates and returns EventBusRegistry."""
        registry = setup_event_bus(
            repair_cycle=mock_repair_cycle,
            clock=simulation_clock,
        )

        assert isinstance(registry, EventBusRegistry)

    def test_setup_event_bus_registers_services(self, mock_repair_cycle, simulation_clock):
        """Test setup_event_bus registers services."""
        registry = setup_event_bus(
            repair_cycle=mock_repair_cycle,
            clock=simulation_clock,
        )

        assert registry._services["repair_cycle"] == mock_repair_cycle
        assert registry._services["clock"] == simulation_clock

    def test_setup_event_bus_registers_handlers(self, mock_repair_cycle, simulation_clock):
        """Test setup_event_bus registers handlers for provided services."""
        registry = setup_event_bus(
            repair_cycle=mock_repair_cycle,
            clock=simulation_clock,
        )

        # Repair cycle handler should be registered
        assert "repair_cycle" in registry._handlers

    def test_setup_event_bus_with_all_services(
        self,
        mock_orchestrator,
        mock_execution_service,
        mock_review_service,
        mock_repair_cycle,
        simulation_clock,
    ):
        """Test setup_event_bus with all service types."""
        registry = setup_event_bus(
            workflow_orchestrator=mock_orchestrator,
            execution_service=mock_execution_service,
            review_service=mock_review_service,
            repair_cycle=mock_repair_cycle,
            clock=simulation_clock,
        )

        # All services should be registered
        assert len(registry._services) == 5
        # Handlers should be registered for non-None services
        assert len(registry._handlers) >= 1

    def test_setup_event_bus_with_custom_retry_settings(
        self,
        mock_repair_cycle,
        simulation_clock,
    ):
        """Test setup_event_bus with custom retry settings."""
        registry = setup_event_bus(
            repair_cycle=mock_repair_cycle,
            clock=simulation_clock,
            max_retries=5,
            retry_delay_seconds=2.0,
        )

        assert registry.event_bus is not None

    def test_setup_event_bus_without_repair_cycle(self):
        """Test setup_event_bus without repair_cycle."""
        registry = setup_event_bus()

        assert isinstance(registry, EventBusRegistry)
        assert "repair_cycle" not in registry._services

    def test_setup_event_bus_only_repair_cycle(self, mock_repair_cycle, simulation_clock):
        """Test setup_event_bus with only repair_cycle (no other services)."""
        registry = setup_event_bus(
            repair_cycle=mock_repair_cycle,
            clock=simulation_clock,
        )

        # Only repair_cycle and clock should be registered
        assert registry._services.get("repair_cycle") == mock_repair_cycle
        assert registry._services.get("clock") == simulation_clock



# ====================================================================================
# Tests for Handler Retrieval
# ====================================================================================


class TestEventBusRegistryHandlerRetrieval:
    """Tests for getting registered handlers."""

    def test_get_handler_returns_repair_cycle_handler(
        self,
        registry,
        mock_repair_cycle,
    ):
        """Test get_handler returns repair_cycle handler."""
        registry.register_services(repair_cycle=mock_repair_cycle)
        registry.register_handlers(register_repair_cycle=True)

        handler = registry.get_handler("repair_cycle")
        assert handler is not None
        assert isinstance(handler, RepairCycleEventHandler)

    def test_get_handler_returns_none_for_unregistered(self, registry):
        """Test get_handler returns None for unregistered handler."""
        handler = registry.get_handler("repair_cycle")
        assert handler is None

    def test_get_handler_with_different_names(
        self,
        registry,
        mock_repair_cycle,
    ):
        """Test get_handler with different handler names."""
        registry.register_services(repair_cycle=mock_repair_cycle)
        registry.register_handlers(register_repair_cycle=True)

        # Correct name should work
        assert registry.get_handler("repair_cycle") is not None

        # Wrong name should return None
        assert registry.get_handler("wrong_name") is None


# ====================================================================================
# Tests for Statistics
# ====================================================================================


class TestEventBusRegistryStatistics:
    """Tests for event bus statistics."""

    def test_get_statistics_returns_dict(self, registry):
        """Test get_statistics returns dictionary."""
        stats = registry.get_statistics()
        assert isinstance(stats, dict)

    def test_reset_statistics_clears_stats(self, registry):
        """Test reset_statistics clears statistics."""
        registry.reset_statistics()
        # Should not raise exception


# ====================================================================================
# Tests for Error Handling
# ====================================================================================


class TestEventBusRegistryErrorHandling:
    """Tests for error handling."""

    def test_register_services_with_invalid_clock(self, registry, mock_repair_cycle):
        """Test register_services handles invalid clock gracefully."""
        # Invalid clock (not a SimulationClock)
        invalid_clock = "not a clock"

        # Should not raise - just stores it
        registry.register_services(
            repair_cycle=mock_repair_cycle,
            clock=invalid_clock,
        )
        assert registry._services["clock"] == invalid_clock

    def test_unregister_handlers_succeeds(
        self,
        registry,
        mock_repair_cycle,
    ):
        """Test unregister_handlers clears registered handlers."""
        registry.register_services(repair_cycle=mock_repair_cycle)
        registry.register_handlers(register_repair_cycle=True)

        # Should have a handler
        assert len(registry._handlers) > 0

        # Unregister
        registry.unregister_handlers()

        # Handlers should be cleared
        assert len(registry._handlers) == 0
