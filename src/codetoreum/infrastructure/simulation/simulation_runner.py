"""Simulation runner for orchestrating test scenarios."""

import asyncio
import logging
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, TypeVar

logger = logging.getLogger(__name__)

from codetoreum.adapters.testing.fake_container_adapter import FakeContainerAdapter
from codetoreum.adapters.testing.in_memory_metrics_adapter import (
    InMemoryMetricsAdapter,
)
from codetoreum.adapters.testing.mock_llm_adapter import MockLLMAdapter
from codetoreum.adapters.testing.mock_notifier_adapter import MockNotifierAdapter
from codetoreum.domain.events import DomainEvent
from codetoreum.infrastructure.simulation.mock_tracer import (
    MockTracer,
    SpanKind,
    TraceContextValidator,
)
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig
from codetoreum.infrastructure.simulation.simulation_engine import SimulationEngine

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
    spans_captured: int = 0
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
            "spans_captured": self.spans_captured,
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

    def __init__(self, config: SimulationConfig, engine: Optional[SimulationEngine] = None):
        """
        Initialize simulation runner.

        Args:
            config: Simulation configuration
            engine: Optional SimulationEngine instance. If provided, uses the engine's
                    public API for time operations instead of creating a new clock.
                    This allows runners to work with a bootstrap's encapsulated engine.

        Note:
            If engine is provided, the config.time settings are ignored (the engine
            already has its clock configured). Use this when running scenarios that
            use SimulationApplicationBootstrap.
        """
        self.config = config
        self.engine = engine

        # When engine is provided, we'll use its public API (advance, now, etc.)
        # Otherwise create a new clock for standalone scenarios
        if not engine:
            # Create simulation clock
            self.clock = SimulationClock(
                speed_multiplier=config.time.speed_multiplier,
                auto_advance=config.time.auto_advance,
            )

            if config.time.start_time:
                self.clock.start_at(config.time.start_time)
        else:
            self.clock = None

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

        # Create mock tracer
        self.mock_tracer = MockTracer(service_name=config.scenario_name)
        self.trace_validator = TraceContextValidator(self.mock_tracer)

        # Configure adapters based on config
        self._configure_adapters()

        # Captured events
        self.captured_events: List[DomainEvent] = []

        # Assertions
        self.assertions: List[AssertionResult] = []

        # Start and end times
        self._start_time: Optional[datetime] = None
        self._end_time: Optional[datetime] = None

    def _get_clock_now(self) -> datetime:
        """Get current simulated time from engine or clock."""
        if self.engine:
            return self.engine.now()
        else:
            return self.clock.now()

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
        simulated_start_time = self._get_clock_now()

        errors = []

        try:
            # Run the scenario
            if asyncio.iscoroutinefunction(scenario_func):
                await scenario_func(self)
            else:
                scenario_func(self)

        except Exception as e:
            error_msg = f"Scenario execution failed: {str(e)}"
            error_traceback = traceback.format_exc()
            errors.append(f"{error_msg}\n{error_traceback}")
            logger.error(error_msg, exc_info=True)

        self._end_time = datetime.now(timezone.utc)
        simulated_end_time = self._get_clock_now()

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
            spans_captured=len(self.mock_tracer.get_spans()),
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
            timestamp=self._get_clock_now(),
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

    def assert_span_exists(
        self,
        span_name: str,
        assertion_name: Optional[str] = None,
    ) -> None:
        """
        Assert a span with given name exists.

        Args:
            span_name: Name of span to look for
            assertion_name: Name of the assertion
        """
        assertion_name = assertion_name or f"Span {span_name} exists"
        spans = self.mock_tracer.get_spans_by_name(span_name)

        self.assert_true(
            len(spans) > 0,
            assertion_name,
            f"No span found with name: {span_name}",
        )

    def assert_span_kind(
        self,
        span_name: str,
        expected_kind: SpanKind,
        assertion_name: Optional[str] = None,
    ) -> None:
        """
        Assert a span has a specific kind.

        Args:
            span_name: Name of span
            expected_kind: Expected SpanKind
            assertion_name: Name of the assertion
        """
        assertion_name = assertion_name or f"Span {span_name} kind is {expected_kind.value}"
        spans = self.mock_tracer.get_spans_by_name(span_name)

        if not spans:
            self.assert_true(False, assertion_name, f"No span found: {span_name}")
            return

        span = spans[0]
        self.assert_equal(
            span.kind.value,
            expected_kind.value,
            assertion_name,
            f"Span {span_name} has kind {span.kind.value}",
        )

    def assert_span_attribute(
        self,
        span_name: str,
        attr_key: str,
        attr_value: Optional[any] = None,
        assertion_name: Optional[str] = None,
    ) -> None:
        """
        Assert a span has an attribute.

        Args:
            span_name: Name of span
            attr_key: Attribute key
            attr_value: Optional expected value
            assertion_name: Name of the assertion
        """
        assertion_name = assertion_name or f"Span {span_name} has attribute {attr_key}"
        spans = self.mock_tracer.get_spans_by_name(span_name)

        if not spans:
            self.assert_true(False, assertion_name, f"No span found: {span_name}")
            return

        span = spans[0]
        has_attr = attr_key in span.attributes
        self.assert_true(
            has_attr,
            assertion_name,
            f"Span {span_name} missing attribute: {attr_key}",
        )

        if has_attr and attr_value is not None:
            actual_value = span.attributes[attr_key]
            self.assert_equal(
                actual_value,
                attr_value,
                f"{assertion_name} (value check)",
                f"Attribute {attr_key}={actual_value}, expected {attr_value}",
            )

    def assert_span_context_injected(
        self,
        span_name: str,
        assertion_name: Optional[str] = None,
    ) -> None:
        """
        Assert trace context was injected for a span.

        Args:
            span_name: Name of span
            assertion_name: Name of the assertion
        """
        assertion_name = assertion_name or f"Span {span_name} injected trace context"
        spans = self.mock_tracer.get_spans_by_name(span_name)

        if not spans:
            self.assert_true(False, assertion_name, f"No span found: {span_name}")
            return

        span = spans[0]
        self.assert_true(
            span.span_context_injected,
            assertion_name,
            f"Span {span_name} did not inject trace context",
        )

    def assert_span_count(
        self,
        expected_count: int,
        assertion_name: Optional[str] = None,
    ) -> None:
        """
        Assert total span count.

        Args:
            expected_count: Expected number of spans
            assertion_name: Name of the assertion
        """
        assertion_name = assertion_name or f"Span count = {expected_count}"
        actual_count = len(self.mock_tracer.get_spans())

        self.assert_equal(
            actual_count,
            expected_count,
            assertion_name,
            f"Expected {expected_count} spans, got {actual_count}",
        )

    async def advance_time(self, delta: timedelta) -> None:
        """
        Advance simulation time.

        Args:
            delta: Amount of time to advance
        """
        if self.engine:
            await self.engine.advance(delta)
        else:
            await self.clock.advance(delta)

    async def advance_to(self, target_time: datetime) -> None:
        """
        Advance simulation time to a specific time.

        Args:
            target_time: Target time
        """
        if self.engine:
            await self.engine.advance_to(target_time)
        else:
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
        """Clear all captured events, metrics, notifications, and spans."""
        self.captured_events.clear()
        self.assertions.clear()
        self.metrics_adapter.clear()
        self.notifier_adapter.clear()
        self.llm_adapter.clear_conversations()
        self.container_adapter.clear()
        self.mock_tracer.clear()

    def print_summary(self) -> None:
        """Print a summary of the simulation run."""
        if not self._start_time or not self._end_time:
            print("Simulation has not been run yet")
            return

        print(f"\n=== Simulation Summary: {self.config.scenario_name} ===")
        print(f"Real time elapsed: {(self._end_time - self._start_time).total_seconds():.2f}s")
        print(f"Simulated time: {(self._get_clock_now() - (self.config.time.start_time or self._start_time)).total_seconds():.2f}s")
        print(f"Speed multiplier: {self.config.time.speed_multiplier}x")
        print(f"\nEvents captured: {len(self.captured_events)}")
        print(f"Metrics recorded: {sum(len(m) for m in self.metrics_adapter.get_all_metrics().values())}")
        print(f"Notifications sent: {self.notifier_adapter.get_notification_count()}")
        print(f"Spans captured: {len(self.mock_tracer.get_spans())}")
        print(f"\nAssertions passed: {sum(1 for a in self.assertions if a.passed)}")
        print(f"Assertions failed: {sum(1 for a in self.assertions if not a.passed)}")

        if any(not a.passed for a in self.assertions):
            print("\nFailed assertions:")
            for assertion in self.assertions:
                if not assertion.passed:
                    print(f"  - {assertion.assertion_name}: {assertion.message}")

        print("=" * 60)

    def print_spans(self) -> None:
        """Print all captured spans for debugging."""
        self.mock_tracer.print_spans()
