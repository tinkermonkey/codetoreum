"""Test helpers and utilities for simulation testing."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from codetoreum.adapters.testing.mock_board_adapter import MockBoardAdapter
from codetoreum.domain.events import CodetoreumEvent, now_iso
from codetoreum.infrastructure.event_serialization import infer_aggregate_id_and_type
from codetoreum.infrastructure.simulation import SimulationRunner


@dataclass(frozen=True)
class SimTestEvent(CodetoreumEvent):
    """Test event for simulation testing."""

    detail: str = ""


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
            "WorkflowStartedEvent",
            work_item_id,
            f"workflow_{work_item_id}_started",
        )

        # Check workflow completed
        runner.assert_event_occurred(
            "WorkflowCompletedEvent",
            work_item_id,
            f"workflow_{work_item_id}_completed",
        )

        # If stages specified, check execution count
        if expected_stages is not None:
            events = runner.get_events_by_aggregate(work_item_id)
            execution_events = [
                e for e in events if e.event_type in ["ExecutionStartedEvent", "ExecutionCompletedEvent"]
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
        events = runner.get_events_by_type("ExecutionCompletedEvent")

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
    """Helper methods for common scenario patterns.

    NOTE: simulate_workflow_execution() and simulate_review_cycle() were
    removed in the transition from DomainEvent to CodetoreumEvent. These
    methods used EventBuilder which is incompatible with immutable frozen
    dataclasses. They can be rewritten using real domain events from the
    catalog (e.g., WorkflowStartedEvent, ExecutionCompletedEvent) if needed.
    """


def print_event_timeline(runner: SimulationRunner) -> None:
    """
    Print a timeline of captured events.

    Supports CodetoreumEvent instances with timestamp field.

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


def filter_events_by_aggregate(
    events: list[CodetoreumEvent],
    aggregate_type: str,
    work_item_id: str | None = None,
) -> list[CodetoreumEvent]:
    """Filter events from InMemoryEventStore.get_all_events_list() by aggregate type.

    CodetoreumEvent does not carry aggregate_type or aggregate_id attributes directly;
    those are inferred by the event store via infer_aggregate_id_and_type(). This
    helper centralises that inference so test code doesn't need to import it directly.

    Args:
        events: List of CodetoreumEvent instances from get_all_events_list().
        aggregate_type: Aggregate type to filter on (e.g. "Workflow", "AgentExecution").
        work_item_id: Optional secondary filter on the event's work_item_id field.

    Returns:
        Filtered list of events whose inferred aggregate_type matches.
    """
    result = []
    for e in events:
        agg_id, agg_type = infer_aggregate_id_and_type(e)
        if agg_type != aggregate_type:
            continue
        if work_item_id is not None and getattr(e, "work_item_id", None) != work_item_id:
            continue
        result.append(e)
    return result


def get_aggregate_id(event: CodetoreumEvent) -> str:
    """Return the inferred aggregate_id for an event from get_all_events_list()."""
    agg_id, _ = infer_aggregate_id_and_type(event)
    return str(agg_id)


async def wait_for_column(
    board: MockBoardAdapter,
    work_item_id: str,
    target_column: str,
    timeout: float = 5.0,
) -> bool:
    """Poll item position until it reaches target column or timeout.

    Args:
        board: MockBoardAdapter to poll
        work_item_id: ID of the work item to track
        target_column: Column name to wait for
        timeout: Maximum seconds to wait (default 5.0)

    Returns:
        True if item reached target column within timeout, False otherwise
    """
    elapsed = 0.0
    interval = 0.05
    while elapsed < timeout:
        await asyncio.sleep(interval)
        elapsed += interval
        pos = await board.get_item_position(work_item_id)
        if pos.column_name == target_column:
            return True
    return False
