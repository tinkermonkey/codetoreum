"""Test helpers and utilities for simulation testing."""

from datetime import datetime, timedelta
from typing import Any

from codetoreum.domain.events import DomainEvent
from codetoreum.infrastructure.simulation import SimulationRunner


class EventBuilder:
    """Builder for creating domain events in tests."""

    def __init__(self):
        """Initialize event builder."""
        self.aggregate_id = "test-aggregate"
        self.aggregate_type = "TestAggregate"
        self.event_type = "TestEvent"
        self.payload: dict[str, Any] = {}

    def with_aggregate_id(self, aggregate_id: str) -> "EventBuilder":
        """Set aggregate ID."""
        self.aggregate_id = aggregate_id
        return self

    def with_aggregate_type(self, aggregate_type: str) -> "EventBuilder":
        """Set aggregate type."""
        self.aggregate_type = aggregate_type
        return self

    def with_event_type(self, event_type: str) -> "EventBuilder":
        """Set event type."""
        self.event_type = event_type
        return self

    def with_payload(self, payload: dict[str, Any]) -> "EventBuilder":
        """Set payload."""
        self.payload = payload
        return self

    def with_payload_item(self, key: str, value: Any) -> "EventBuilder":
        """Add item to payload."""
        self.payload[key] = value
        return self

    def build(self) -> DomainEvent:
        """Build the event."""
        event = DomainEvent(
            aggregate_id=self.aggregate_id,
            aggregate_type=self.aggregate_type,
            payload=self.payload,
        )
        event.event_type = self.event_type
        return event


class AssertionHelpers:
    """Helper methods for common assertions in simulation tests."""

    @staticmethod
    def assert_workflow_completed(
        runner: SimulationRunner,
        work_item_id: str,
        expected_stages: int | None = None,
    ) -> None:
        """
        Assert that a workflow completed successfully.

        Args:
            runner: Simulation runner
            work_item_id: Work item ID
            expected_stages: Expected number of stages (optional)
        """
        # Check workflow started
        runner.assert_event_occurred(
            "WorkflowStarted",
            work_item_id,
            f"workflow_{work_item_id}_started",
        )

        # Check workflow completed
        runner.assert_event_occurred(
            "WorkflowCompleted",
            work_item_id,
            f"workflow_{work_item_id}_completed",
        )

        # If stages specified, check execution count
        if expected_stages is not None:
            events = runner.get_events_by_aggregate(work_item_id)
            execution_events = [
                e for e in events if e.event_type in ["AgentExecutionStarted", "AgentExecutionCompleted"]
            ]
            runner.assert_true(
                len(execution_events) >= expected_stages,
                f"workflow_{work_item_id}_stages",
                f"Expected at least {expected_stages} execution events",
            )

    @staticmethod
    def assert_agent_executed(
        runner: SimulationRunner,
        agent_id: str,
        work_item_id: str | None = None,
    ) -> None:
        """
        Assert that an agent executed.

        Args:
            runner: Simulation runner
            agent_id: Agent ID
            work_item_id: Work item ID (optional filter)
        """
        events = runner.get_events_by_type("AgentExecutionCompleted")

        matching = [
            e
            for e in events
            if e.payload.get("agent_id") == agent_id
            and (work_item_id is None or e.payload.get("work_item_id") == work_item_id)
        ]

        runner.assert_true(
            len(matching) > 0,
            f"agent_{agent_id}_executed",
            f"Agent {agent_id} did not execute",
        )

    @staticmethod
    def assert_execution_sequence(
        runner: SimulationRunner,
        expected_sequence: list[str],
    ) -> None:
        """
        Assert events occurred in a specific sequence.

        Args:
            runner: Simulation runner
            expected_sequence: List of event types in expected order
        """
        actual_sequence = [e.event_type for e in runner.captured_events]

        # Check each expected event appears in order
        last_index = -1
        for event_type in expected_sequence:
            try:
                index = actual_sequence.index(event_type, last_index + 1)
                last_index = index
            except ValueError:
                runner.assert_true(
                    False,
                    f"sequence_check_{event_type}",
                    f"Event {event_type} not found in expected sequence",
                )
                return

        runner.assert_true(
            True,
            "sequence_check_complete",
            "All events occurred in expected sequence",
        )

    @staticmethod
    def assert_time_elapsed(
        runner: SimulationRunner,
        min_seconds: float,
        max_seconds: float | None = None,
    ) -> None:
        """
        Assert that simulated time elapsed within range.

        Args:
            runner: Simulation runner
            min_seconds: Minimum expected seconds
            max_seconds: Maximum expected seconds (optional)
        """
        if not runner.captured_events:
            runner.assert_true(
                False,
                "time_elapsed_check",
                "No events captured to check time",
            )
            return

        start_time = runner.captured_events[0].occurred_at
        end_time = runner.captured_events[-1].occurred_at
        elapsed = (end_time - start_time).total_seconds()

        runner.assert_true(
            elapsed >= min_seconds,
            "time_elapsed_min",
            f"Expected at least {min_seconds}s, got {elapsed}s",
        )

        if max_seconds is not None:
            runner.assert_true(
                elapsed <= max_seconds,
                "time_elapsed_max",
                f"Expected at most {max_seconds}s, got {elapsed}s",
            )


class ScenarioHelpers:
    """Helper methods for common scenario patterns."""

    @staticmethod
    async def simulate_workflow_execution(
        runner: SimulationRunner,
        work_item_id: str,
        stages: list[dict[str, Any]],
    ) -> None:
        """
        Simulate a complete workflow execution.

        Args:
            runner: Simulation runner
            work_item_id: Work item ID
            stages: List of stage configurations
                    Each stage: {"agent_id": str, "duration_minutes": int}
        """
        # Start workflow
        event = (
            EventBuilder()
            .with_aggregate_id(work_item_id)
            .with_aggregate_type("WorkItem")
            .with_event_type("WorkflowStarted")
            .with_payload_item("workflow_id", "test-workflow")
            .build()
        )
        runner.capture_event(event)

        # Execute each stage
        for i, stage in enumerate(stages):
            agent_id = stage["agent_id"]
            duration = timedelta(minutes=stage.get("duration_minutes", 5))

            # Start execution
            await runner.advance_time(timedelta(minutes=1))

            exec_id = f"exec-{i + 1}"
            event = (
                EventBuilder()
                .with_aggregate_id(exec_id)
                .with_aggregate_type("AgentExecution")
                .with_event_type("AgentExecutionStarted")
                .with_payload_item("agent_id", agent_id)
                .with_payload_item("work_item_id", work_item_id)
                .build()
            )
            runner.capture_event(event)

            # Complete execution
            await runner.advance_time(duration)

            event = (
                EventBuilder()
                .with_aggregate_id(exec_id)
                .with_aggregate_type("AgentExecution")
                .with_event_type("AgentExecutionCompleted")
                .with_payload_item("agent_id", agent_id)
                .with_payload_item("status", "completed")
                .build()
            )
            runner.capture_event(event)

        # Complete workflow
        event = (
            EventBuilder()
            .with_aggregate_id(work_item_id)
            .with_aggregate_type("WorkItem")
            .with_event_type("WorkflowCompleted")
            .with_payload_item("total_stages", len(stages))
            .build()
        )
        runner.capture_event(event)

    @staticmethod
    async def simulate_review_cycle(
        runner: SimulationRunner,
        work_item_id: str,
        review_id: str,
        approved: bool,
        feedback: str | None = None,
    ) -> None:
        """
        Simulate a review cycle.

        Args:
            runner: Simulation runner
            work_item_id: Work item ID
            review_id: Review ID
            approved: Whether review is approved
            feedback: Optional feedback message
        """
        await runner.advance_time(timedelta(minutes=2))

        event_type = "ReviewApproved" if approved else "ReviewRejected"
        payload = {
            "work_item_id": work_item_id,
            "decision": "approved" if approved else "rejected",
        }

        if feedback:
            payload["feedback"] = feedback

        event = (
            EventBuilder()
            .with_aggregate_id(review_id)
            .with_aggregate_type("ReviewCycle")
            .with_event_type(event_type)
            .with_payload(payload)
            .build()
        )

        runner.capture_event(event)


def print_event_timeline(runner: SimulationRunner) -> None:
    """
    Print a timeline of captured events.

    Supports both DomainEvent (with occurred_at) and CodetoreumEvent (with timestamp).

    Args:
        runner: Simulation runner
    """

    print("\n=== Event Timeline ===")

    if not runner.captured_events:
        print("No events captured")
        return

    # Get start time from first event (handle both event types)
    first_event = runner.captured_events[0]
    if hasattr(first_event, "occurred_at"):
        start_time = first_event.occurred_at
    elif hasattr(first_event, "timestamp"):
        start_time = datetime.fromisoformat(first_event.timestamp.replace("Z", "+00:00"))
    else:
        print("Unknown event type - no timestamp found")
        return

    for i, event in enumerate(runner.captured_events, 1):
        # Extract timestamp from event (handle both types)
        if hasattr(event, "occurred_at"):
            event_time = event.occurred_at
        elif hasattr(event, "timestamp"):
            event_time = datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
        else:
            event_time = start_time

        elapsed = (event_time - start_time).total_seconds()

        # Extract event type (handle both types)
        event_type = getattr(event, "event_type", getattr(event, "type", "Unknown"))
        aggregate_type = getattr(event, "aggregate_type", "Unknown")
        aggregate_id = getattr(event, "aggregate_id", "Unknown")

        print(f"{i:2d}. [{elapsed:6.1f}s] {event_type:30s} | {aggregate_type}:{aggregate_id}")

    print("=" * 80)


def print_metrics_summary(runner: SimulationRunner) -> None:
    """
    Print a summary of captured metrics.

    Args:
        runner: Simulation runner
    """
    print("\n=== Metrics Summary ===")

    all_metrics = runner.metrics_adapter.get_all_metrics()

    if not all_metrics:
        print("No metrics captured")
        return

    for metric_name, data_points in all_metrics.items():
        values = [dp.value for dp in data_points]
        print(f"\n{metric_name}:")
        print(f"  Count: {len(values)}")
        print(f"  Min:   {min(values):.2f}")
        print(f"  Max:   {max(values):.2f}")
        print(f"  Avg:   {sum(values) / len(values):.2f}")

    print("=" * 80)


def print_notifications_summary(runner: SimulationRunner) -> None:
    """
    Print a summary of sent notifications.

    Args:
        runner: Simulation runner
    """
    print("\n=== Notifications Summary ===")

    notifications = runner.notifier_adapter.get_sent_notifications()

    if not notifications:
        print("No notifications sent")
        return

    for notif in notifications:
        print(f"- {notif['channel'].value:10s} | {notif['recipient']:30s} | {notif['subject']}")

    print(f"\nTotal: {len(notifications)} notifications")
    print("=" * 80)
