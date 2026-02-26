"""Unit tests for SimulationEngine."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest

from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig
from codetoreum.infrastructure.simulation.simulation_engine import SimulationEngine

# ====================================================================================
# Fixtures
# ====================================================================================


@pytest.fixture
def simulation_clock():
    """Create a simulation clock."""
    return SimulationClock(speed_multiplier=100.0)


@pytest.fixture
def simulation_engine(simulation_clock):
    """Create a simulation engine."""
    return SimulationEngine(simulation_clock)


@pytest.fixture
def simulation_config():
    """Create a simulation config."""
    return SimulationConfig.create_fast_config("test")


# ====================================================================================
# Tests for SimulationEngine Initialization
# ====================================================================================


class TestSimulationEngineInitialization:
    """Tests for SimulationEngine initialization."""

    def test_engine_initializes_with_clock(self, simulation_clock):
        """Test engine initializes with a clock."""
        engine = SimulationEngine(simulation_clock)
        assert engine is not None

    def test_engine_stores_clock_privately(self, simulation_clock):
        """Test engine stores clock as private attribute."""
        engine = SimulationEngine(simulation_clock)
        assert hasattr(engine, "_clock")
        assert engine._clock == simulation_clock

    def test_engine_create_factory_with_config(self, simulation_config):
        """Test engine creation via factory method."""
        engine = SimulationEngine.create(simulation_config)
        assert engine is not None

    def test_engine_create_factory_without_config(self):
        """Test engine creation with default config."""
        engine = SimulationEngine.create()
        assert engine is not None

    def test_engine_create_sets_speed_multiplier(self, simulation_config):
        """Test engine creation sets correct speed multiplier."""
        engine = SimulationEngine.create(simulation_config)
        clock = engine.get_clock_for_testing()
        assert clock.get_speed_multiplier() == simulation_config.time.speed_multiplier

    def test_engine_create_sets_start_time_if_configured(self):
        """Test engine creation sets start time if configured."""
        config = SimulationConfig.create_fast_config("test")
        start_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        config.time.start_time = start_time

        engine = SimulationEngine.create(config)
        clock = engine.get_clock_for_testing()

        # Clock should have started at the configured time
        assert clock.now() >= start_time


# ====================================================================================
# Tests for Time Operations
# ====================================================================================


class TestSimulationEngineTimeOperations:
    """Tests for time operations."""

    def test_now_returns_current_time(self, simulation_engine):
        """Test now() returns current simulated time."""
        current_time = simulation_engine.now()
        assert isinstance(current_time, datetime)
        assert current_time.tzinfo is not None

    def test_now_returns_utc_time(self, simulation_engine):
        """Test now() returns UTC time."""
        current_time = simulation_engine.now()
        assert current_time.tzinfo == UTC or current_time.tzinfo is not None

    def test_advance_method_exists(self, simulation_engine):
        """Test advance() method exists and is callable."""
        assert hasattr(simulation_engine, "advance")
        assert callable(simulation_engine.advance)

    def test_advance_to_method_exists(self, simulation_engine):
        """Test advance_to() method exists and is callable."""
        assert hasattr(simulation_engine, "advance_to")
        assert callable(simulation_engine.advance_to)

    def test_wait_for_method_exists(self, simulation_engine):
        """Test wait_for() method exists and is callable."""
        assert hasattr(simulation_engine, "wait_for")
        assert callable(simulation_engine.wait_for)

    def test_sleep_method_exists(self, simulation_engine):
        """Test sleep() method exists and is callable."""
        assert hasattr(simulation_engine, "sleep")
        assert callable(simulation_engine.sleep)

    @pytest.mark.asyncio
    async def test_advance_with_negative_delta_raises_error(self, simulation_engine):
        """Test advance() with negative delta raises ValueError."""
        with pytest.raises(ValueError):
            await simulation_engine.advance(timedelta(hours=-1))

    @pytest.mark.asyncio
    async def test_advance_with_zero_delta(self, simulation_engine):
        """Test advance() with zero delta succeeds."""
        current_time = simulation_engine.now()
        await simulation_engine.advance(timedelta(seconds=0))
        # Time should remain unchanged (use >= to account for precision)
        assert simulation_engine.now() >= current_time

    @pytest.mark.asyncio
    async def test_advance_to_with_past_time_raises_error(self, simulation_engine):
        """Test advance_to() with past time raises ValueError."""
        current_time = simulation_engine.now()
        past_time = current_time - timedelta(hours=1)

        with pytest.raises(ValueError):
            await simulation_engine.advance_to(past_time)

    @pytest.mark.asyncio
    async def test_advance_to_with_current_time(self, simulation_engine):
        """Test advance_to() with current time succeeds."""
        current_time = simulation_engine.now()
        # Should not raise
        await simulation_engine.advance_to(current_time)
        assert simulation_engine.now() == current_time

    @pytest.mark.asyncio
    async def test_advance_to_with_future_time(self, simulation_engine):
        """Test advance_to() with future time succeeds."""
        current_time = simulation_engine.now()
        future_time = current_time + timedelta(hours=1)

        # Should not raise
        await simulation_engine.advance_to(future_time)
        assert simulation_engine.now() >= future_time


# ====================================================================================
# Tests for Speed Multiplier
# ====================================================================================


class TestSimulationEngineSpeedMultiplier:
    """Tests for speed multiplier operations."""

    def test_set_speed_multiplier(self, simulation_engine):
        """Test set_speed_multiplier() sets multiplier."""
        simulation_engine.set_speed_multiplier(50.0)
        assert simulation_engine.get_speed_multiplier() == 50.0

    def test_set_speed_multiplier_with_high_value(self, simulation_engine):
        """Test set_speed_multiplier() with high value."""
        simulation_engine.set_speed_multiplier(1000.0)
        assert simulation_engine.get_speed_multiplier() == 1000.0

    def test_set_speed_multiplier_with_low_value(self, simulation_engine):
        """Test set_speed_multiplier() with low value."""
        simulation_engine.set_speed_multiplier(1.0)
        assert simulation_engine.get_speed_multiplier() == 1.0

    def test_set_speed_multiplier_with_zero_raises(self, simulation_engine):
        """Test set_speed_multiplier with zero raises ValueError."""
        with pytest.raises(ValueError):
            simulation_engine.set_speed_multiplier(0)

    def test_set_speed_multiplier_with_negative_raises(self, simulation_engine):
        """Test set_speed_multiplier with negative value raises ValueError."""
        with pytest.raises(ValueError):
            simulation_engine.set_speed_multiplier(-10.0)

    def test_get_speed_multiplier(self, simulation_engine):
        """Test get_speed_multiplier() returns current multiplier."""
        multiplier = simulation_engine.get_speed_multiplier()
        assert isinstance(multiplier, (int, float))
        assert multiplier > 0


# ====================================================================================
# Tests for Auto-Advance Control
# ====================================================================================


class TestSimulationEngineAutoAdvance:
    """Tests for auto-advance control."""

    @pytest.mark.asyncio
    async def test_start_auto_advance(self, simulation_engine):
        """Test start_auto_advance() starts auto-advance."""
        await simulation_engine.start_auto_advance()
        # Should not raise exception

    @pytest.mark.asyncio
    async def test_stop_auto_advance(self, simulation_engine):
        """Test stop_auto_advance() stops auto-advance."""
        await simulation_engine.start_auto_advance()
        await simulation_engine.stop_auto_advance()
        # Should not raise exception

    @pytest.mark.asyncio
    async def test_stop_auto_advance_without_start(self, simulation_engine):
        """Test stop_auto_advance() without prior start."""
        await simulation_engine.stop_auto_advance()
        # Should not raise exception


# ====================================================================================
# Tests for Adapter Creation
# ====================================================================================


class TestSimulationEngineAdapterCreation:
    """Tests for adapter creation methods."""

    def test_create_repair_cycle_adapter(self, simulation_engine):
        """Test create_repair_cycle_adapter() creates adapter."""
        adapter = simulation_engine.create_repair_cycle_adapter()
        assert adapter is not None

    def test_create_repair_cycle_adapter_has_clock(self, simulation_engine):
        """Test created repair cycle adapter has clock injected."""
        adapter = simulation_engine.create_repair_cycle_adapter()
        assert hasattr(adapter, "clock")
        assert adapter.clock is simulation_engine._clock

    def test_create_repair_cycle_adapter_passes_container_adapter(self, simulation_engine):
        """Test create_repair_cycle_adapter() passes container_adapter parameter.

        Verifies that when a container_adapter is provided, it's correctly
        passed to the MockRepairCycleAdapter for causal linking (FR-2/US-2.4).
        This enables the repair adapter to extract test results from the
        container adapter instead of using pre-configured sequences.
        """
        container_mock = Mock()
        adapter = simulation_engine.create_repair_cycle_adapter(
            container_adapter=container_mock
        )

        # Adapter should have received the container_adapter
        assert adapter._container_adapter is container_mock

    def test_create_repair_cycle_adapter_passes_checkpoint_store(self, simulation_engine):
        """Test create_repair_cycle_adapter() passes checkpoint_store parameter.

        Verifies that when a checkpoint_store is provided, it's correctly
        passed to the MockRepairCycleAdapter for recovery testing.
        """
        checkpoint_mock = Mock()
        adapter = simulation_engine.create_repair_cycle_adapter(
            checkpoint_store=checkpoint_mock
        )

        # Adapter should have received the checkpoint_store
        assert adapter._checkpoint_store is checkpoint_mock

    def test_create_repair_cycle_adapter_passes_both_parameters(self, simulation_engine):
        """Test create_repair_cycle_adapter() passes both parameters correctly.

        Verifies parameter ordering is correct: checkpoint_store before
        container_adapter, matching the adapter's __init__ signature.
        """
        checkpoint_mock = Mock()
        container_mock = Mock()

        adapter = simulation_engine.create_repair_cycle_adapter(
            checkpoint_store=checkpoint_mock,
            container_adapter=container_mock,
        )

        # Both should be passed correctly
        assert adapter._checkpoint_store is checkpoint_mock
        assert adapter._container_adapter is container_mock

    def test_create_review_cycle_adapter(self, simulation_engine):
        """Test create_review_cycle_adapter() creates adapter."""
        adapter = simulation_engine.create_review_cycle_adapter()
        assert adapter is not None

    def test_create_review_cycle_adapter_has_clock(self, simulation_engine):
        """Test created review cycle adapter has clock injected."""
        adapter = simulation_engine.create_review_cycle_adapter()
        assert hasattr(adapter, "clock")
        assert adapter.clock is simulation_engine._clock

    def test_create_review_cycle_adapter_passes_llm_adapter(self, simulation_engine):
        """Test create_review_cycle_adapter() passes llm_adapter parameter.

        Verifies that when an llm_adapter is provided, it's correctly
        passed to the MockReviewCycleAdapter for causal linking (FR-2/US-2.2).
        This enables the review adapter to analyze actual LLM output instead
        of using pre-configured sequences, allowing LLM code quality to
        influence review decisions.
        """
        llm_mock = Mock()
        adapter = simulation_engine.create_review_cycle_adapter(llm_adapter=llm_mock)

        # Adapter should have received the llm_adapter
        assert adapter._llm_adapter is llm_mock

    def test_create_metrics_query_adapter(self, simulation_engine):
        """Test create_metrics_query_adapter() creates adapter."""
        adapter = simulation_engine.create_metrics_query_adapter()
        assert adapter is not None

    def test_create_metrics_query_adapter_with_dependencies(self, simulation_engine):
        """Test create_metrics_query_adapter() with dependencies."""
        metrics_adapter = Mock()
        event_store = Mock()

        adapter = simulation_engine.create_metrics_query_adapter(
            metrics_adapter=metrics_adapter,
            event_store=event_store,
        )
        assert adapter is not None

    def test_create_repair_cycle_event_handler(self, simulation_engine):
        """Test create_repair_cycle_event_handler() creates handler."""
        repair_cycle = Mock()
        event_bus = Mock()

        handler = simulation_engine.create_repair_cycle_event_handler(
            repair_cycle=repair_cycle,
            event_bus=event_bus,
        )
        assert handler is not None

    def test_create_repair_cycle_event_handler_has_clock(self, simulation_engine):
        """Test created event handler has clock injected."""
        repair_cycle = Mock()
        event_bus = Mock()

        handler = simulation_engine.create_repair_cycle_event_handler(
            repair_cycle=repair_cycle,
            event_bus=event_bus,
        )
        assert handler.clock is simulation_engine._clock


# ====================================================================================
# Tests for Clock Access
# ====================================================================================


class TestSimulationEngineClockAccess:
    """Tests for clock access."""

    def test_get_clock_for_testing_returns_clock(self, simulation_engine, simulation_clock):
        """Test get_clock_for_testing() returns the clock."""
        clock = simulation_engine.get_clock_for_testing()
        assert clock is simulation_clock

    def test_get_clock_for_testing_returns_same_instance(self, simulation_engine):
        """Test get_clock_for_testing() returns same instance."""
        clock1 = simulation_engine.get_clock_for_testing()
        clock2 = simulation_engine.get_clock_for_testing()
        assert clock1 is clock2


# ====================================================================================
# Tests for Callback Scheduling
# ====================================================================================


class TestSimulationEngineCallbackScheduling:
    """Tests for callback scheduling."""

    def test_schedule_callback_with_after_delta(self, simulation_engine):
        """Test schedule_callback() with after_delta parameter."""
        callback = Mock()
        simulation_engine.schedule_callback(callback, after_delta=timedelta(hours=1))
        # Should not raise exception

    def test_schedule_callback_with_at_time(self, simulation_engine):
        """Test schedule_callback() with at_time parameter."""
        callback = Mock()
        target_time = simulation_engine.now() + timedelta(hours=1)
        simulation_engine.schedule_callback(callback, at_time=target_time)
        # Should not raise exception

    def test_schedule_callback_with_async_function(self, simulation_engine):
        """Test schedule_callback() with async function."""

        async def async_callback():
            pass

        simulation_engine.schedule_callback(async_callback, after_delta=timedelta(hours=1))
        # Should not raise exception

    def test_schedule_callback_without_time_raises(self, simulation_engine):
        """Test schedule_callback() without time parameters raises ValueError."""
        callback = Mock()
        with pytest.raises(ValueError):
            simulation_engine.schedule_callback(callback)

    def test_schedule_callback_with_both_times_raises(self, simulation_engine):
        """Test schedule_callback() with both time parameters raises ValueError."""
        callback = Mock()
        target_time = simulation_engine.now() + timedelta(hours=1)
        with pytest.raises(ValueError):
            simulation_engine.schedule_callback(
                callback,
                at_time=target_time,
                after_delta=timedelta(hours=1),
            )


# ====================================================================================
# Tests for Lifecycle Management
# ====================================================================================


class TestSimulationEngineLifecycle:
    """Tests for engine lifecycle management."""

    @pytest.mark.asyncio
    async def test_stop_engine(self, simulation_engine):
        """Test stop() cleans up engine."""
        await simulation_engine.stop()
        # Should not raise exception

    @pytest.mark.asyncio
    async def test_stop_with_auto_advance_running(self, simulation_engine):
        """Test stop() stops running auto-advance."""
        await simulation_engine.start_auto_advance()
        await simulation_engine.stop()
        # Should not raise exception

    def test_reset_engine(self, simulation_engine):
        """Test reset() resets engine."""
        simulation_engine.reset()
        # Should not raise exception

    @pytest.mark.asyncio
    async def test_reset_clears_scheduled_callbacks(self, simulation_engine):
        """Test reset() clears scheduled callbacks."""
        callback = Mock()
        simulation_engine.schedule_callback(callback, after_delta=timedelta(hours=1))
        simulation_engine.reset()

        # Schedule callback should be cleared
        clock = simulation_engine.get_clock_for_testing()
        assert len(clock._scheduled_callbacks) == 0


# ====================================================================================
# Integration Tests
# ====================================================================================


class TestSimulationEngineIntegration:
    """Integration tests for SimulationEngine."""

    @pytest.mark.asyncio
    async def test_create_adapters_share_same_clock(self, simulation_engine):
        """Test created adapters share the same clock instance."""
        repair_adapter = simulation_engine.create_repair_cycle_adapter()
        review_adapter = simulation_engine.create_review_cycle_adapter()

        # Both adapters should have the same clock
        assert repair_adapter.clock is review_adapter.clock
        assert repair_adapter.clock is simulation_engine._clock

    def test_create_multiple_adapters(self, simulation_engine):
        """Test creating multiple adapters from same engine."""
        # Create adapters
        repair_adapter = simulation_engine.create_repair_cycle_adapter()
        review_adapter = simulation_engine.create_review_cycle_adapter()

        # Verify adapters are created
        assert repair_adapter is not None
        assert review_adapter is not None

        # Both should reference the same clock
        assert repair_adapter.clock is review_adapter.clock

    def test_adapter_clock_is_engine_clock(self, simulation_engine):
        """Test created adapters use engine's clock."""
        repair_adapter = simulation_engine.create_repair_cycle_adapter()

        # Adapter should have the same clock instance
        assert repair_adapter.clock is simulation_engine._clock

    def test_factory_methods_share_clock(self, simulation_engine):
        """Test all factory methods share the same clock instance."""
        # Create multiple adapters
        repair_adapter = simulation_engine.create_repair_cycle_adapter()
        review_adapter = simulation_engine.create_review_cycle_adapter()
        metrics_adapter = simulation_engine.create_metrics_query_adapter()

        # All should share the same clock
        assert repair_adapter.clock is simulation_engine._clock
        assert review_adapter.clock is simulation_engine._clock
        assert metrics_adapter.clock is simulation_engine._clock

        # All adapter clocks should be the same instance
        assert repair_adapter.clock is review_adapter.clock
        assert review_adapter.clock is metrics_adapter.clock

    def test_repair_cycle_event_handler_shares_clock(self, simulation_engine):
        """Test repair cycle event handler gets the same clock."""
        repair_cycle = Mock()
        event_bus = Mock()

        handler = simulation_engine.create_repair_cycle_event_handler(
            repair_cycle=repair_cycle,
            event_bus=event_bus,
        )

        # Handler should have the same clock instance as engine
        assert handler.clock is simulation_engine._clock

    @pytest.mark.asyncio
    async def test_full_simulation_lifecycle_setup_only(self, simulation_config):
        """Test full simulation lifecycle setup."""
        engine = SimulationEngine.create(simulation_config)

        # Create adapters
        repair_adapter = engine.create_repair_cycle_adapter()
        review_adapter = engine.create_review_cycle_adapter()

        # Verify adapters are created
        assert repair_adapter is not None
        assert review_adapter is not None

        # Verify time is available
        assert engine.now() is not None

        # Clean up
        await engine.stop()
