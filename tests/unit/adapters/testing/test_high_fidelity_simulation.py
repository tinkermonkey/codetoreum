"""Unit tests for HIGH fidelity simulation features."""

import pytest

from codetoreum.adapters.testing import (
    FakeContainerAdapter,
    InMemoryEventStore,
    MockLLMAdapter,
)
from codetoreum.domain.events import WorkItemCreatedEvent
from codetoreum.domain.events.adapter_events import now_iso
from codetoreum.infrastructure.simulation.simulation_config import (
    FidelityLevel,
    SimulationConfig,
)
from codetoreum.ports.exceptions import RateLimitError


@pytest.mark.asyncio
class TestHighFidelityFakeContainerAdapter:
    """Tests for HIGH fidelity timing and probabilistic failures in FakeContainerAdapter."""

    @pytest.fixture
    def high_fidelity_config(self):
        """Create HIGH fidelity config."""
        return SimulationConfig.create_high_fidelity_config(
            scenario_name="test_high_fidelity",
            speed_multiplier=5.0,
            ms_per_file_operation=10.0,
        )

    @pytest.fixture
    def medium_fidelity_config(self):
        """Create MEDIUM fidelity config for comparison."""
        return SimulationConfig.create_realistic_config(
            scenario_name="test_medium_fidelity",
            fidelity_level=FidelityLevel.MEDIUM,
        )

    async def test_high_fidelity_container_jitter(self, high_fidelity_config):
        """Test that HIGH fidelity calculates delay with jitter."""
        adapter = FakeContainerAdapter(
            config=high_fidelity_config,
        )

        # Test the delay calculation method directly
        # Run multiple times to see variance from jitter
        delays = []
        for _ in range(5):
            delay = adapter._calculate_delay_seconds("pytest tests/unit")
            delays.append(delay)

        # Check that delays vary (jitter is applied)
        # With HIGH fidelity, should see variance from ±20% jitter
        delays_unique = len({round(d, 4) for d in delays})
        assert delays_unique > 1, "HIGH fidelity should add variance with jitter"

    async def test_high_fidelity_container_probabilistic_failure(self, high_fidelity_config):
        """Test that HIGH fidelity produces probabilistic container failures."""
        adapter = FakeContainerAdapter(
            default_exit_code=0,
            config=high_fidelity_config,
        )

        # Run 20 commands to trigger at least one failure
        failures = 0
        successes = 0
        for _ in range(20):
            result = await adapter.run(
                image="python:3.11",
                command=["echo", "test"],
                volumes={},
                environment={},
            )
            if result.exit_code != 0:
                failures += 1
            else:
                successes += 1

        # Deterministic counter: fail every 20th execution
        # So with 20 runs, we should get exactly 1 failure
        assert failures == 1, f"Expected 1 failure (every 20th), got {failures}"
        assert successes == 19

    async def test_medium_fidelity_container_no_jitter(self, medium_fidelity_config):
        """Test that MEDIUM fidelity has no jitter."""
        adapter = FakeContainerAdapter(
            config=medium_fidelity_config,
        )

        # Same command should have consistent delay in MEDIUM fidelity
        delays = []
        for _ in range(3):
            delay = adapter._calculate_delay_seconds("pytest tests/unit")
            delays.append(delay)

        # MEDIUM fidelity should not have jitter
        # All delays should be identical (no randomness)
        assert delays[0] == delays[1] == delays[2], "MEDIUM should have no jitter"
        assert delays[0] > 0, "MEDIUM should have proportional delay"

    async def test_low_fidelity_container_no_delay(self):
        """Test that LOW fidelity has no delay."""
        config = SimulationConfig.create_fast_config(
            scenario_name="test_low_fidelity",
            fidelity_level=FidelityLevel.LOW,
        )
        adapter = FakeContainerAdapter(config=config)

        # LOW fidelity should return 0 delay
        delay = adapter._calculate_delay_seconds("echo test")
        assert delay == 0.0, "LOW fidelity should have zero delay"


@pytest.mark.asyncio
class TestHighFidelityMockLLMAdapter:
    """Tests for HIGH fidelity timing and probabilistic failures in MockLLMAdapter."""

    @pytest.fixture
    def high_fidelity_config(self):
        """Create HIGH fidelity config."""
        return SimulationConfig.create_high_fidelity_config(
            scenario_name="test_high_fidelity_llm",
            speed_multiplier=5.0,
            ms_per_token=50.0,
        )

    @pytest.fixture
    def medium_fidelity_config(self):
        """Create MEDIUM fidelity config."""
        return SimulationConfig.create_realistic_config(
            scenario_name="test_medium_fidelity_llm",
            fidelity_level=FidelityLevel.MEDIUM,
        )

    async def test_high_fidelity_llm_jitter(self, high_fidelity_config):
        """Test that HIGH fidelity adds timing jitter to LLM execution."""
        adapter = MockLLMAdapter(
            default_response="Test response",
            config=high_fidelity_config,
        )

        # Test the delay calculation directly
        prompt = "Test prompt " * 40
        response = "Test response " * 20
        delays = []
        for _ in range(5):
            delay = adapter._calculate_delay_seconds(prompt, response)
            delays.append(delay)

        # Check that delays vary (jitter is applied)
        delays_unique = len({round(d, 4) for d in delays})
        assert delays_unique > 1, "HIGH fidelity should add variance with jitter"

    async def test_high_fidelity_llm_probabilistic_failure(self, high_fidelity_config):
        """Test that HIGH fidelity produces probabilistic LLM failures."""
        adapter = MockLLMAdapter(
            default_response="Test response",
            config=high_fidelity_config,
        )

        # Run 25 prompts; expect failure on 25th execution
        failures = 0
        successes = 0
        for i in range(25):
            prompt = f"Prompt {i}"
            try:
                await adapter.execute(prompt)
                successes += 1
            except RateLimitError:
                failures += 1

        # Deterministic counter: fail every 25th execution
        # So with 25 runs, we should get exactly 1 failure
        assert failures == 1, f"Expected 1 failure (every 25th), got {failures}"
        assert successes == 24

    async def test_medium_fidelity_llm_no_jitter(self, medium_fidelity_config):
        """Test that MEDIUM fidelity has no jitter."""
        adapter = MockLLMAdapter(
            default_response="Test response",
            config=medium_fidelity_config,
        )

        # Same prompt/response should have consistent delay
        prompt = "Test prompt " * 40
        response = "Test response " * 20
        delays = []
        for _ in range(3):
            delay = adapter._calculate_delay_seconds(prompt, response)
            delays.append(delay)

        # MEDIUM should be consistent (no jitter)
        assert delays[0] == delays[1] == delays[2], "MEDIUM should have no jitter"
        assert delays[0] > 0, "MEDIUM should have proportional delay"

    async def test_low_fidelity_llm_no_delay(self):
        """Test that LOW fidelity has no delay."""
        config = SimulationConfig.create_fast_config(
            scenario_name="test_low_fidelity_llm",
            fidelity_level=FidelityLevel.LOW,
        )
        adapter = MockLLMAdapter(
            default_response="Test response",
            config=config,
        )

        # LOW fidelity should return 0 delay
        delay = adapter._calculate_delay_seconds("Test prompt", "Test response")
        assert delay == 0.0, "LOW fidelity should have zero delay"


@pytest.mark.asyncio
class TestHighFidelityInMemoryEventStore:
    """Tests for HIGH fidelity timing in InMemoryEventStore."""

    @pytest.fixture
    def high_fidelity_config(self):
        """Create HIGH fidelity config."""
        return SimulationConfig.create_high_fidelity_config(
            scenario_name="test_high_fidelity_events",
            speed_multiplier=5.0,
            ms_per_event=1.0,
        )

    @pytest.fixture
    def medium_fidelity_config(self):
        """Create MEDIUM fidelity config."""
        return SimulationConfig.create_realistic_config(
            scenario_name="test_medium_fidelity_events",
            fidelity_level=FidelityLevel.MEDIUM,
        )

    @pytest.fixture
    async def store_with_events_high(self, high_fidelity_config):
        """Create store with events using HIGH fidelity."""
        store = InMemoryEventStore(config=high_fidelity_config)
        events = [
            WorkItemCreatedEvent(
                type="workitem.created",
                timestamp=now_iso(),
                source="test",
                work_item_id=f"work-item-{i}",
                project_id="proj-1",
                title=f"Item {i}",
            )
            for i in range(5)
        ]
        await store.append("stream-1", events)
        return store

    @pytest.fixture
    async def store_with_events_medium(self, medium_fidelity_config):
        """Create store with events using MEDIUM fidelity."""
        store = InMemoryEventStore(config=medium_fidelity_config)
        events = [
            WorkItemCreatedEvent(
                type="workitem.created",
                timestamp=now_iso(),
                source="test",
                work_item_id=f"work-item-{i}",
                project_id="proj-1",
                title=f"Item {i}",
            )
            for i in range(5)
        ]
        await store.append("stream-1", events)
        return store

    async def test_high_fidelity_stream_events_uses_config(self, store_with_events_high, high_fidelity_config):
        """Test that HIGH fidelity streaming uses config."""
        store = store_with_events_high
        assert store._config == high_fidelity_config
        delay = await store._get_event_delay_seconds()
        # HIGH should have jitter, so we can't predict exact value
        # But it should be based on ms_per_event (1.0ms)
        assert 0.0 < delay <= 0.0015, f"HIGH fidelity delay should be ~1ms with jitter, got {delay}"

    async def test_medium_fidelity_stream_events_consistent(self, store_with_events_medium, medium_fidelity_config):
        """Test that MEDIUM fidelity streaming is consistent."""
        store = store_with_events_medium
        assert store._config == medium_fidelity_config

        # Multiple calls should return same delay (no jitter)
        delay1 = await store._get_event_delay_seconds()
        delay2 = await store._get_event_delay_seconds()

        assert delay1 == delay2, "MEDIUM should have consistent delay (no jitter)"
        assert delay1 == 0.001, "MEDIUM should use ms_per_event (1.0ms)"

    async def test_low_fidelity_stream_events_no_delay(self):
        """Test that LOW fidelity has no streaming delay."""
        config = SimulationConfig.create_fast_config(
            scenario_name="test_low_fidelity_events",
            fidelity_level=FidelityLevel.LOW,
        )
        store = InMemoryEventStore(config=config)

        delay = await store._get_event_delay_seconds()
        assert delay == 0.0, "LOW fidelity should have zero delay"

    async def test_high_fidelity_replay_has_jitter(self, high_fidelity_config):
        """Test that HIGH fidelity replay delay has jitter."""
        store = InMemoryEventStore(config=high_fidelity_config)

        delays = []
        for _ in range(5):
            delay = await store._get_event_delay_seconds()
            delays.append(delay)

        # Check variance from jitter
        delays_unique = len({round(d, 5) for d in delays})
        assert delays_unique > 1, "HIGH fidelity should add jitter variance"


class TestCreateHighFidelityConfig:
    """Tests for create_high_fidelity_config factory method."""

    def test_create_high_fidelity_config_defaults(self):
        """Test HIGH fidelity config creation with defaults."""
        config = SimulationConfig.create_high_fidelity_config(scenario_name="test_scenario")

        assert config.scenario_name == "test_scenario"
        assert config.fidelity_level == FidelityLevel.HIGH
        assert config.time.speed_multiplier == 5.0
        assert config.ms_per_token == 50.0
        assert config.ms_per_file_operation == 10.0
        assert config.ms_per_event == 1.0
        assert config.container.execution_delay == 1.0
        assert config.notifications.simulate_failures is True
        assert config.notifications.failure_rate == 0.05

    def test_create_high_fidelity_config_custom_params(self):
        """Test HIGH fidelity config creation with custom parameters."""
        config = SimulationConfig.create_high_fidelity_config(
            scenario_name="test_custom",
            speed_multiplier=10.0,
            ms_per_token=100.0,
            ms_per_file_operation=20.0,
            ms_per_event=2.0,
        )

        assert config.scenario_name == "test_custom"
        assert config.fidelity_level == FidelityLevel.HIGH
        assert config.time.speed_multiplier == 10.0
        assert config.ms_per_token == 100.0
        assert config.ms_per_file_operation == 20.0
        assert config.ms_per_event == 2.0

    def test_high_fidelity_vs_medium_fidelity(self):
        """Test that HIGH and MEDIUM have different characteristics."""
        high = SimulationConfig.create_high_fidelity_config(scenario_name="high")
        medium = SimulationConfig.create_realistic_config(scenario_name="medium")

        # Speed: HIGH should be slower (smaller multiplier)
        assert high.time.speed_multiplier < medium.time.speed_multiplier

        # Fidelity level
        assert high.fidelity_level == FidelityLevel.HIGH
        assert medium.fidelity_level == FidelityLevel.MEDIUM

        # Container execution delay
        assert high.container.execution_delay > medium.container.execution_delay

        # Notifications: HIGH should simulate failures
        assert high.notifications.simulate_failures is True
