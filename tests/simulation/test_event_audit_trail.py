"""Phase 6: Full Observability Audit Trail Test.

Verifies that the complete event chain is visible in the EventStore after a full
cascade: human move → event bridge → handler → agent execution → completion →
auto-progress → repeat, ending at the Done column.

Also verifies adapter-tier events captured by CapturingMockEventEmitter.
"""

import asyncio
from typing import cast

import pytest

from codetoreum.infrastructure.event_serialization import infer_aggregate_id_and_type
from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationAdapters,
    SimulationApplicationBootstrap,
)
from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder
from codetoreum.ports.output.board_service import MovedByType
from tests.conftest import assert_condition
from tests.simulation.helpers import filter_events_by_aggregate, get_aggregate_id, wait_for_column


@pytest.mark.asyncio
async def test_full_workflow_event_audit_trail(
    simulation_bootstrap: SimulationApplicationBootstrap,
    simulation_seeder: SimulationDataSeeder,
) -> None:
    """Assert complete event chain is visible in EventStore after full cascade.

    The cascade should produce the following workflow lifecycle events in order:
    WorkflowCreated → WorkflowStarted → WorkflowStageAdvanced (x3) → WorkflowCompleted

    Additionally, adapter-tier events should be captured by CapturingMockEventEmitter.
    """
    # Setup
    adapters = cast("SimulationAdapters", simulation_bootstrap.adapters)
    if adapters.agent_executor is not None:
        adapters.agent_executor._execution_delay = 0.1
    await simulation_seeder.seed_default_scenario()

    board = adapters.board
    work_item_id = simulation_seeder.created_items.work_items[0]

    # Trigger cascade: human moves item from Backlog to Ready (pipeline trigger)
    await board.move_item_to_column(work_item_id, "Ready", MovedByType.HUMAN)

    # Wait for cascade to reach Done
    reached_done = await wait_for_column(board, work_item_id, "Done", timeout=10.0)
    assert reached_done, (
        f"Item did not reach 'Done' within timeout. "
        f"Current position: {(await board.get_item_position(work_item_id)).column_name}"
    )

    # Wait for async event handlers (e.g. _complete_workflow_run) to finish
    async def workflow_events_ready():
        event_store = adapters.event_store
        all_events = event_store.get_all_events_list()
        # Wait for WorkflowCompleted event
        return any(
            e.event_type == "WorkflowCompletedEvent" and infer_aggregate_id_and_type(e)[1] == "Workflow"
            for e in all_events
        )

    await assert_condition(
        workflow_events_ready, timeout=2.0, poll_interval=0.05, message="WorkflowCompleted event should be recorded"
    )

    # -------------------------------------------------------------------------
    # Assert EventStore contains the full workflow lifecycle
    # -------------------------------------------------------------------------
    event_store = adapters.event_store
    all_events = event_store.get_all_events_list()

    # Step 1: Locate any Workflow-aggregate event that references this work item.
    # WorkflowCreated / WorkflowStarted / WorkflowCompleted all carry work_item_id
    # in their payload.  WorkflowStageAdvanced events share the same aggregate_id
    # (workflow_run_id) but may not repeat work_item_id in their own payload.
    seed_events = filter_events_by_aggregate(all_events, "Workflow", work_item_id)
    assert len(seed_events) > 0, (
        f"No workflow events found in EventStore for work_item_id={work_item_id}. "
        f"Total events in store: {len(all_events)}. "
        f"Event types present: {list({e.event_type for e in all_events})}"
    )

    # Step 2: Retrieve ALL events for this workflow run using the shared aggregate_id
    workflow_run_id = get_aggregate_id(seed_events[0])
    workflow_events = [e for e in all_events if get_aggregate_id(e) == workflow_run_id]

    event_types_in_order = [e.event_type for e in workflow_events]

    # Must have all lifecycle events
    assert (
        "WorkflowCreatedEvent" in event_types_in_order
    ), f"WorkflowCreated missing. Events found: {event_types_in_order}"
    assert (
        "WorkflowStartedEvent" in event_types_in_order
    ), f"WorkflowStarted missing. Events found: {event_types_in_order}"
    assert (
        "WorkflowCompletedEvent" in event_types_in_order
    ), f"WorkflowCompleted missing. Events found: {event_types_in_order}"

    # Stage advances — one per agent (architect, coder, tester = 3)
    stage_advances = [e for e in workflow_events if e.event_type == "WorkflowStageAdvancedEvent"]
    assert len(stage_advances) == 3, (
        f"Expected 3 WorkflowStageAdvanced events (one per agent), "
        f"got {len(stage_advances)}. All events: {event_types_in_order}"
    )

    # Chronological ordering: events must be non-decreasing in time
    for i in range(1, len(workflow_events)):
        assert workflow_events[i].occurred_at >= workflow_events[i - 1].occurred_at, (
            f"Events out of order at index {i}: "
            f"{workflow_events[i - 1].event_type} (occurred_at={workflow_events[i - 1].occurred_at}) "
            f"→ {workflow_events[i].event_type} (occurred_at={workflow_events[i].occurred_at})"
        )

    # WorkflowCreated must be first
    assert event_types_in_order[0] == "WorkflowCreatedEvent", (
        f"Expected WorkflowCreated as first event, got {event_types_in_order[0]}. "
        f"Full sequence: {event_types_in_order}"
    )

    # WorkflowCompleted must be last
    assert event_types_in_order[-1] == "WorkflowCompletedEvent", (
        f"Expected WorkflowCompleted as last event, got {event_types_in_order[-1]}. "
        f"Full sequence: {event_types_in_order}"
    )

    # -------------------------------------------------------------------------
    # Assert adapter-tier events in CapturingMockEventEmitter
    # -------------------------------------------------------------------------
    emitter = adapters.event_emitter
    # CapturingMockEventEmitter exposes get_events() to retrieve all captured events
    emitted_events = emitter.get_events()

    assert len(emitted_events) > 0, (
        "No events captured by CapturingMockEventEmitter. "
        "The board adapter and other adapters should emit events when state changes."
    )


@pytest.mark.asyncio
async def test_event_store_chronological_across_all_streams(
    simulation_bootstrap: SimulationApplicationBootstrap,
    simulation_seeder: SimulationDataSeeder,
) -> None:
    """Assert that every event written to the EventStore has a valid timestamp.

    This verifies the time-ordering guarantee: events appended later have
    timestamps >= events appended earlier within the same aggregate stream.
    """
    adapters = cast("SimulationAdapters", simulation_bootstrap.adapters)
    if adapters.agent_executor is not None:
        adapters.agent_executor._execution_delay = 0.1
    await simulation_seeder.seed_default_scenario()

    board = adapters.board
    work_item_id = simulation_seeder.created_items.work_items[0]

    # Trigger the cascade
    await board.move_item_to_column(work_item_id, "Ready", MovedByType.HUMAN)
    reached_done = await wait_for_column(board, work_item_id, "Done", timeout=10.0)
    assert reached_done, "Item did not reach Done"

    # Wait for event store to capture all events
    async def events_captured():
        event_store = adapters.event_store
        all_events = event_store.get_all_events_list()
        return len(all_events) > 0

    await assert_condition(
        events_captured, timeout=2.0, poll_interval=0.05, message="EventStore should have events after cascade"
    )

    event_store = adapters.event_store
    all_events = event_store.get_all_events_list()

    # Every event must have a valid timestamp
    assert len(all_events) > 0, "EventStore should have events after cascade"
    for event in all_events:
        assert (
            event.occurred_at is not None
        ), f"Event {event.event_type} (id={event.event_id}) has no occurred_at timestamp"

    # Within each aggregate stream, events should be in non-decreasing order
    # Group events by aggregate_id (stream)
    streams: dict[str, list] = {}
    for event in all_events:
        streams.setdefault(get_aggregate_id(event), []).append(event)

    for stream_id, stream_events in streams.items():
        for i in range(1, len(stream_events)):
            assert stream_events[i].occurred_at >= stream_events[i - 1].occurred_at, (
                f"Events out of order in stream {stream_id}: "
                f"{stream_events[i - 1].event_type} → {stream_events[i].event_type}"
            )


@pytest.mark.asyncio
async def test_event_emitter_captures_column_change_events(
    simulation_bootstrap: SimulationApplicationBootstrap,
    simulation_seeder: SimulationDataSeeder,
) -> None:
    """Assert CapturingMockEventEmitter captures events when board columns change.

    When the board adapter moves a work item, it should emit adapter-tier events
    via the CapturingMockEventEmitter.
    """
    adapters = cast("SimulationAdapters", simulation_bootstrap.adapters)
    if adapters.agent_executor is not None:
        adapters.agent_executor._execution_delay = 0.1
    await simulation_seeder.seed_default_scenario()

    board = adapters.board
    emitter = adapters.event_emitter
    work_item_id = simulation_seeder.created_items.work_items[0]

    # Clear any events from seeding
    emitter.clear_events()

    # Trigger cascade
    await board.move_item_to_column(work_item_id, "Ready", MovedByType.HUMAN)
    reached_done = await wait_for_column(board, work_item_id, "Done", timeout=10.0)
    assert reached_done, "Item did not reach Done"

    # Wait for event emitter to capture all events
    async def events_emitted():
        return emitter.get_event_count() > 0

    await assert_condition(
        events_emitted,
        timeout=2.0,
        poll_interval=0.05,
        message="CapturingMockEventEmitter should capture events during cascade",
    )

    # After the cascade, the emitter should have captured events
    emitted_events = emitter.get_events()
    event_count = emitter.get_event_count()

    assert event_count > 0, (
        "CapturingMockEventEmitter captured no events during full cascade. "
        "Expected board/adapter events to be emitted."
    )
    assert len(emitted_events) == event_count, "get_events() count mismatch with get_event_count()"
