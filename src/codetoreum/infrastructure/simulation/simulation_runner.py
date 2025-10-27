"""Simulation runner for orchestrating test scenarios."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, TypeVar

from codetoreum.adapters.testing.fake_container_adapter import FakeContainerAdapter
from codetoreum.adapters.testing.in_memory_metrics_adapter import (
    InMemoryMetricsAdapter,
)
from codetoreum.adapters.testing.mock_llm_adapter import MockLLMAdapter
from codetoreum.adapters.testing.mock_notifier_adapter import MockNotifierAdapter
from codetoreum.domain.events import DomainEvent
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig

T = TypeVar("T")


@dataclass
class SimulationResult:
    """Result of a simulation run."""

    scenario_name: str
    success: bool
    duration_seconds: float
    simulated_duration_seconds: float
    events_captured: int
    metrics_captured: int
    notifications_sent: int
    assertions_passed: int
    assertions_failed: int
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def speed_multiplier(self) -> float:
        """Calculate actual speed multiplier achieved."""
        if self.duration_seconds == 0:
            return 0.0
        return self.simulated_duration_seconds / self.duration_seconds

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "scenario_name": self.scenario_name,
            "success": self.success,
            "duration_seconds": self.duration_seconds,
            "simulated_duration_seconds": self.simulated_duration_seconds,
            "speed_multiplier": self.speed_multiplier,
            "events_captured": self.events_captured,
            "metrics_captured": self.metrics_captured,
            "notifications_sent": self.notifications_sent,
            "assertions_passed": self.assertions_passed,
            "assertions_failed": self.assertions_failed,
            "errors": self.errors,
            "metadata": self.metadata,
        }


@dataclass
class AssertionResult:
    """Result of an assertion."""

    assertion_name: str
    passed: bool
    message: str
    timestamp: datetime


class SimulationRunner:
    """
    Orchestrates simulation scenarios.

    Sets up all mock adapters, manages the simulation clock, runs scenario
    events, and verifies outcomes.

    Example:
        >>> config = SimulationConfig.create_fast_config("test_scenario")
        >>> runner = SimulationRunner(config)
        >>> result = await runner.run(scenario_func)
        >>> assert result.success
    """

    def __init__(self, config: SimulationConfig):
        """
        Initialize simulation runner.

        Args:
            config: Simulation configuration
        """
        self.config = config

        # Create simulation clock
        self.clock = SimulationClock(
            speed_multiplier=config.time.speed_multiplier,
            auto_advance=config.time.auto_advance,
        )

        if config.time.start_time:
            self.clock.start_at(config.time.start_time)

        # Create mock adapters
        self.llm_adapter = MockLLMAdapter(
            delay_seconds=0.0,  # We control timing with the clock
        )

        self.container_adapter = FakeContainerAdapter(
            execution_delay=config.container.execution_delay,
            default_exit_code=config.container.default_exit_code,
        )

        self.metrics_adapter = InMemoryMetricsAdapter()

        self.notifier_adapter = MockNotifierAdapter(
            send_delay=config.notifications.send_delay,
            simulate_failures=config.notifications.simulate_failures,
            failure_rate=config.notifications.failure_rate,
        )

        # Configure adapters based on config
        self._configure_adapters()

        # Captured events
        self.captured_events: List[DomainEvent] = []

        # Assertions
        self.assertions: List[AssertionResult] = []

        # Start and end times
        self._start_time: Optional[datetime] = None
        self._end_time: Optional[datetime] = None

    def _configure_adapters(self) -> None:
        """Configure adapters based on simulation config."""
        # Configure LLM adapter with agent-specific patterns
        for agent_id, agent_config in self.config.agents.items():
            for pattern, response in agent_config.response_patterns.items():
                self.llm_adapter.add_response_pattern(pattern, response)

        # Configure container adapter with command results
        for command, exit_code in self.config.container.command_exit_codes.items():
            outputs = self.config.container.command_outputs.get(command, {})
            self.container_adapter.set_command_result(
                command_pattern=command,
                exit_code=exit_code,
                stdout=outputs.get("stdout", ""),
                stderr=outputs.get("stderr", ""),
            )

    async def run(
        self,
        scenario_func: Callable[["SimulationRunner"], Any],
    ) -> SimulationResult:
        """
        Run a simulation scenario.

        Args:
            scenario_func: Async function that executes the scenario.
                           Receives the SimulationRunner as an argument.

        Returns:
            SimulationResult with outcome and statistics
        """
        self._start_time = datetime.now(timezone.utc)
        simulated_start_time = self.clock.now()

        errors = []

        try:
            # Run the scenario
            if asyncio.iscoroutinefunction(scenario_func):
                await scenario_func(self)
            else:
                scenario_func(self)

        except Exception as e:
            errors.append(f"Scenario execution failed: {str(e)}")

        self._end_time = datetime.now(timezone.utc)
        simulated_end_time = self.clock.now()

        # Calculate durations
        real_duration = (self._end_time - self._start_time).total_seconds()
        simulated_duration = (simulated_end_time - simulated_start_time).total_seconds()

        # Count assertions
        passed = sum(1 for a in self.assertions if a.passed)
        failed = sum(1 for a in self.assertions if not a.passed)

        # Collect failures
        for assertion in self.assertions:
            if not assertion.passed:
                errors.append(f"Assertion failed: {assertion.assertion_name} - {assertion.message}")

        return SimulationResult(
            scenario_name=self.config.scenario_name,
            success=len(errors) == 0,
            duration_seconds=real_duration,
            simulated_duration_seconds=simulated_duration,
            events_captured=len(self.captured_events),
            metrics_captured=sum(
                len(metrics) for metrics in self.metrics_adapter.get_all_metrics().values()
            ),
            notifications_sent=self.notifier_adapter.get_notification_count(),
            assertions_passed=passed,
            assertions_failed=failed,
            errors=errors,
            metadata=self.config.metadata,
        )

    def capture_event(self, event: DomainEvent) -> None:
        """
        Capture a domain event.

        Args:
            event: Domain event to capture
        """
        self.captured_events.append(event)

    def assert_true(
        self,
        condition: bool,
        assertion_name: str,
        message: str = "",
    ) -> None:
        """
        Assert a condition is true.

        Args:
            condition: Condition to check
            assertion_name: Name of the assertion
            message: Optional message
        """
        result = AssertionResult(
            assertion_name=assertion_name,
            passed=condition,
            message=message if not condition else "Passed",
            timestamp=self.clock.now(),
        )
        self.assertions.append(result)

    def assert_false(
        self,
        condition: bool,
        assertion_name: str,
        message: str = "",
    ) -> None:
        """
        Assert a condition is false.

        Args:
            condition: Condition to check
            assertion_name: Name of the assertion
            message: Optional message
        """
        self.assert_true(not condition, assertion_name, message)

    def assert_equal(
        self,
        actual: Any,
        expected: Any,
        assertion_name: str,
        message: str = "",
    ) -> None:
        """
        Assert two values are equal.

        Args:
            actual: Actual value
            expected: Expected value
            assertion_name: Name of the assertion
            message: Optional message
        """
        passed = actual == expected
        full_message = message or f"Expected {expected}, got {actual}"
        self.assert_true(passed, assertion_name, full_message)

    def assert_event_occurred(
        self,
        event_type: str,
        aggregate_id: Optional[str] = None,
        assertion_name: Optional[str] = None,
    ) -> None:
        """
        Assert an event of a specific type occurred.

        Args:
            event_type: Type of event to look for
            aggregate_id: Optional aggregate ID filter
            assertion_name: Name of the assertion
        """
        assertion_name = assertion_name or f"Event {event_type} occurred"

        matching_events = [
            e for e in self.captured_events
            if e.event_type == event_type
            and (aggregate_id is None or e.aggregate_id == aggregate_id)
        ]

        self.assert_true(
            len(matching_events) > 0,
            assertion_name,
            f"No events of type {event_type} found",
        )

    def assert_event_count(
        self,
        event_type: str,
        expected_count: int,
        assertion_name: Optional[str] = None,
    ) -> None:
        """
        Assert the number of events of a specific type.

        Args:
            event_type: Type of event to count
            expected_count: Expected number of events
            assertion_name: Name of the assertion
        """
        assertion_name = assertion_name or f"Event {event_type} count = {expected_count}"

        actual_count = sum(1 for e in self.captured_events if e.event_type == event_type)

        self.assert_equal(
            actual_count,
            expected_count,
            assertion_name,
            f"Expected {expected_count} events of type {event_type}, got {actual_count}",
        )

    def assert_metric_recorded(
        self,
        metric_name: str,
        assertion_name: Optional[str] = None,
    ) -> None:
        """
        Assert a metric was recorded.

        Args:
            metric_name: Name of the metric
            assertion_name: Name of the assertion
        """
        assertion_name = assertion_name or f"Metric {metric_name} recorded"

        metric_count = self.metrics_adapter.get_metric_count(metric_name)

        self.assert_true(
            metric_count > 0,
            assertion_name,
            f"Metric {metric_name} was not recorded",
        )

    def assert_notification_sent(
        self,
        recipient: str,
        subject_contains: Optional[str] = None,
        assertion_name: Optional[str] = None,
    ) -> None:
        """
        Assert a notification was sent.

        Args:
            recipient: Expected recipient
            subject_contains: Optional substring in subject
            assertion_name: Name of the assertion
        """
        assertion_name = assertion_name or f"Notification sent to {recipient}"

        sent = self.notifier_adapter.assert_notification_sent(
            recipient=recipient,
            subject_contains=subject_contains,
        )

        self.assert_true(
            sent,
            assertion_name,
            f"No notification sent to {recipient}",
        )

    async def advance_time(self, delta: timedelta) -> None:
        """
        Advance simulation time.

        Args:
            delta: Amount of time to advance
        """
        await self.clock.advance(delta)

    async def advance_to(self, target_time: datetime) -> None:
        """
        Advance simulation time to a specific time.

        Args:
            target_time: Target time
        """
        await self.clock.advance_to(target_time)

    def get_events_by_type(self, event_type: str) -> List[DomainEvent]:
        """
        Get all captured events of a specific type.

        Args:
            event_type: Type of event

        Returns:
            List of matching events
        """
        return [e for e in self.captured_events if e.event_type == event_type]

    def get_events_by_aggregate(self, aggregate_id: str) -> List[DomainEvent]:
        """
        Get all captured events for a specific aggregate.

        Args:
            aggregate_id: Aggregate ID

        Returns:
            List of matching events
        """
        return [e for e in self.captured_events if e.aggregate_id == aggregate_id]

    def clear_captured_data(self) -> None:
        """Clear all captured events, metrics, and notifications."""
        self.captured_events.clear()
        self.assertions.clear()
        self.metrics_adapter.clear()
        self.notifier_adapter.clear()
        self.llm_adapter.clear_conversations()
        self.container_adapter.clear()

    def print_summary(self) -> None:
        """Print a summary of the simulation run."""
        if not self._start_time or not self._end_time:
            print("Simulation has not been run yet")
            return

        print(f"\n=== Simulation Summary: {self.config.scenario_name} ===")
        print(f"Real time elapsed: {(self._end_time - self._start_time).total_seconds():.2f}s")
        print(f"Simulated time: {(self.clock.now() - (self.config.time.start_time or self._start_time)).total_seconds():.2f}s")
        print(f"Speed multiplier: {self.config.time.speed_multiplier}x")
        print(f"\nEvents captured: {len(self.captured_events)}")
        print(f"Metrics recorded: {sum(len(m) for m in self.metrics_adapter.get_all_metrics().values())}")
        print(f"Notifications sent: {self.notifier_adapter.get_notification_count()}")
        print(f"\nAssertions passed: {sum(1 for a in self.assertions if a.passed)}")
        print(f"Assertions failed: {sum(1 for a in self.assertions if not a.passed)}")

        if any(not a.passed for a in self.assertions):
            print("\nFailed assertions:")
            for assertion in self.assertions:
                if not assertion.passed:
                    print(f"  - {assertion.assertion_name}: {assertion.message}")

        print("=" * 60)
