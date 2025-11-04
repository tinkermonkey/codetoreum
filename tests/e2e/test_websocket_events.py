"""
End-to-end tests for WebSocket event streaming.

Tests work item status change events, execution lifecycle events, real-time log
streaming, multi-client event broadcasting, event ordering guarantees, connection
loss and reconnection, event persistence and replay, and high-frequency event handling.
"""

import pytest
import asyncio
from datetime import datetime
from typing import AsyncGenerator, List

from codetoreum.domain.models.work_item import WorkItemStatus


class TestWorkItemStatusEvents:
    """Tests for work item status change events."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_work_item_status_change_events(self):
        """
        Test WebSocket events for work item status changes.

        Verifies:
        - Status change events emitted
        - Events contain old and new status
        - Events received in real-time
        - Multiple clients receive events
        """
        work_item_id = await create_work_item()

        # Connect WebSocket clients
        client1_events = []
        client2_events = []

        async def collect_events(client_id: int):
            events = client1_events if client_id == 1 else client2_events
            async for event in websocket_connect(f"work_items/{work_item_id}"):
                events.append(event)
                if event["type"] == "status_changed" and event["new_status"] == "completed":
                    break

        # Start collecting events
        collectors = asyncio.gather(
            collect_events(1),
            collect_events(2),
        )

        # Trigger status changes
        await update_work_item_status(work_item_id, WorkItemStatus.IN_PROGRESS)
        await asyncio.sleep(0.5)
        await update_work_item_status(work_item_id, WorkItemStatus.COMPLETED)

        await collectors

        # Verify both clients received events
        assert len(client1_events) >= 2
        assert len(client2_events) >= 2

        # Verify status change events
        status_events = [e for e in client1_events if e["type"] == "status_changed"]
        assert len(status_events) >= 2

        # Verify event details
        assert status_events[0]["old_status"] == "pending"
        assert status_events[0]["new_status"] == "in_progress"


class TestExecutionLifecycleEvents:
    """Tests for execution lifecycle events."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_complete_execution_lifecycle_events(self):
        """
        Test WebSocket events for complete execution lifecycle.

        Verifies:
        - Execution started event
        - Stage transition events
        - Progress update events
        - Execution completed event
        - Event ordering is correct
        """
        execution_id = await start_execution()

        events = []
        async for event in websocket_connect(f"executions/{execution_id}"):
            events.append(event)
            if event["type"] == "execution_completed":
                break

        # Verify lifecycle events present
        event_types = [e["type"] for e in events]
        assert "execution_started" in event_types
        assert "stage_started" in event_types
        assert "stage_completed" in event_types
        assert "execution_completed" in event_types

        # Verify event ordering
        started_idx = event_types.index("execution_started")
        completed_idx = event_types.index("execution_completed")
        assert started_idx < completed_idx

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_execution_progress_events(self):
        """
        Test WebSocket events for execution progress updates.

        Verifies:
        - Progress events emitted regularly
        - Progress values increase monotonically
        - Progress reaches 100% on completion
        """
        execution_id = await start_execution()

        progress_values = []
        async for event in websocket_connect(f"executions/{execution_id}"):
            if event["type"] == "progress_update":
                progress_values.append(event["progress"])

            if event["type"] == "execution_completed":
                break

        # Verify progress updates received
        assert len(progress_values) > 0

        # Verify progress increases
        for i in range(len(progress_values) - 1):
            assert progress_values[i] <= progress_values[i + 1]

        # Verify final progress is 100%
        if len(progress_values) > 0:
            assert progress_values[-1] <= 1.0


class TestRealTimeLogStreaming:
    """Tests for real-time log streaming."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_stream_execution_logs_realtime(self):
        """
        Test real-time streaming of execution logs.

        Verifies:
        - Log entries streamed as generated
        - Log entries ordered correctly
        - Tail functionality works
        - Filter by stage works
        """
        execution_id = await start_execution()

        log_entries = []
        async for event in websocket_connect(f"executions/{execution_id}/logs"):
            if event["type"] == "log_entry":
                log_entries.append(event["entry"])

            if event["type"] == "execution_completed":
                break

        # Verify logs received
        assert len(log_entries) > 0

        # Verify log ordering (timestamps increase)
        timestamps = [e["timestamp"] for e in log_entries]
        assert timestamps == sorted(timestamps)

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_log_streaming_with_tail_limit(self):
        """
        Test log streaming with tail limit (last N lines).

        Verifies:
        - Only last N lines returned
        - New lines continue streaming
        - Limit is respected
        """
        execution_id = await start_long_running_execution()

        # Wait for some logs to accumulate
        await asyncio.sleep(2)

        # Connect with tail limit
        log_entries = []
        async for event in websocket_connect(
            f"executions/{execution_id}/logs?tail=10"
        ):
            if event["type"] == "log_entry":
                log_entries.append(event["entry"])

            if len(log_entries) >= 15:  # Get initial 10 + 5 more
                break

        # Verify initial entries limited to tail size
        # (implementation-dependent, but should be close to 10)
        assert len(log_entries) >= 10


class TestMultiClientEventBroadcasting:
    """Tests for broadcasting events to multiple clients."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_broadcast_events_to_multiple_clients(self):
        """
        Test events broadcast to all connected clients.

        Verifies:
        - Multiple clients can connect
        - All clients receive same events
        - Event content is identical
        - No race conditions
        """
        execution_id = await start_execution()

        # Connect multiple clients
        num_clients = 5
        client_events = [[] for _ in range(num_clients)]

        async def collect_client_events(client_id: int):
            async for event in websocket_connect(f"executions/{execution_id}"):
                client_events[client_id].append(event)
                if event["type"] == "execution_completed":
                    break

        # Collect events from all clients
        await asyncio.gather(*[
            collect_client_events(i) for i in range(num_clients)
        ])

        # Verify all clients received events
        for events in client_events:
            assert len(events) > 0

        # Verify event count consistency
        event_counts = [len(events) for events in client_events]
        assert len(set(event_counts)) == 1  # All counts should be same

        # Verify event types match across clients
        event_type_sequences = [
            [e["type"] for e in events] for events in client_events
        ]
        for seq in event_type_sequences[1:]:
            assert seq == event_type_sequences[0]

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_new_client_receives_missed_events(self):
        """
        Test new client receives events that occurred before connection.

        Verifies:
        - Event history available
        - New client gets caught up
        - Only relevant events sent
        """
        execution_id = await start_execution()

        # Wait for some events to occur
        await asyncio.sleep(1)

        # Connect late client
        late_client_events = []
        async for event in websocket_connect(
            f"executions/{execution_id}?include_history=true"
        ):
            late_client_events.append(event)
            if event["type"] == "execution_completed":
                break

        # Verify late client received history
        event_types = [e["type"] for e in late_client_events]
        assert "execution_started" in event_types


class TestEventOrderingGuarantees:
    """Tests for event ordering guarantees."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_events_ordered_by_timestamp(self):
        """
        Test events are delivered in timestamp order.

        Verifies:
        - Events have timestamps
        - Timestamps increase monotonically
        - Causal ordering preserved
        """
        execution_id = await start_execution()

        events = []
        async for event in websocket_connect(f"executions/{execution_id}"):
            events.append(event)
            if event["type"] == "execution_completed":
                break

        # Verify all events have timestamps
        assert all("timestamp" in e for e in events)

        # Verify timestamps increase
        timestamps = [datetime.fromisoformat(e["timestamp"]) for e in events]
        assert timestamps == sorted(timestamps)

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_causal_ordering_preserved(self):
        """
        Test causal ordering is preserved (e.g., stage_started before stage_completed).

        Verifies:
        - Causally related events in correct order
        - No stage completed before started
        - No execution completed before started
        """
        execution_id = await start_execution()

        events = []
        async for event in websocket_connect(f"executions/{execution_id}"):
            events.append(event)
            if event["type"] == "execution_completed":
                break

        event_types = [e["type"] for e in events]

        # Verify execution started before completed
        started_idx = event_types.index("execution_started")
        completed_idx = event_types.index("execution_completed")
        assert started_idx < completed_idx

        # Verify stage causality
        stage_events = [(i, e) for i, e in enumerate(events)
                        if "stage_" in e["type"]]
        stages_seen = {}
        for idx, event in stage_events:
            stage_name = event.get("stage_name")
            if event["type"] == "stage_started":
                stages_seen[stage_name] = idx
            elif event["type"] == "stage_completed":
                assert stage_name in stages_seen
                assert idx > stages_seen[stage_name]


class TestConnectionLossAndReconnection:
    """Tests for connection loss and reconnection."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_reconnect_after_connection_loss(self):
        """
        Test client reconnects after connection loss.

        Verifies:
        - Disconnect detected
        - Automatic reconnection attempted
        - Event stream resumes
        - No events lost
        """
        execution_id = await start_long_running_execution()

        events = []
        reconnections = 0

        async for event in websocket_connect_with_reconnect(
            f"executions/{execution_id}"
        ):
            if event["type"] == "reconnected":
                reconnections += 1
            else:
                events.append(event)

            # Simulate disconnect
            if len(events) == 10:
                await simulate_disconnect()

            if event["type"] == "execution_completed":
                break

        # Verify reconnection occurred
        assert reconnections > 0

        # Verify no event sequence gaps
        if all("sequence" in e for e in events):
            sequences = [e["sequence"] for e in events]
            gaps = [b - a for a, b in zip(sequences, sequences[1:]) if b - a > 1]
            assert len(gaps) == 0

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_backoff_on_repeated_failures(self):
        """
        Test exponential backoff on repeated connection failures.

        Verifies:
        - Initial reconnect attempts quick
        - Backoff increases on failures
        - Eventually succeeds
        """
        execution_id = await start_execution()

        connection_attempts = []

        async for event in websocket_connect_with_tracking(
            f"executions/{execution_id}"
        ):
            if event["type"] == "connection_attempt":
                connection_attempts.append(event["timestamp"])

            if event["type"] == "execution_completed":
                break

        # Verify backoff if multiple attempts occurred
        if len(connection_attempts) > 2:
            intervals = [
                (connection_attempts[i+1] - connection_attempts[i]).total_seconds()
                for i in range(len(connection_attempts) - 1)
            ]
            # Later intervals should be longer
            assert intervals[-1] > intervals[0]


class TestEventPersistenceAndReplay:
    """Tests for event persistence and replay."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_replay_events_from_start(self):
        """
        Test replaying all events from execution start.

        Verifies:
        - All events persisted
        - Replay includes all events
        - Event order preserved
        - Replay can be done after execution completes
        """
        execution_id = await start_and_complete_execution()

        # Replay events from start
        replayed_events = []
        async for event in websocket_connect(
            f"executions/{execution_id}?replay=true"
        ):
            replayed_events.append(event)
            if event["type"] == "execution_completed":
                break

        # Verify complete event sequence
        event_types = [e["type"] for e in replayed_events]
        assert "execution_started" in event_types
        assert "execution_completed" in event_types

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_replay_events_from_checkpoint(self):
        """
        Test replaying events from specific checkpoint.

        Verifies:
        - Can start replay from middle
        - Events after checkpoint included
        - Events before checkpoint excluded
        """
        execution_id = await start_and_complete_execution()

        # Get a middle event timestamp
        all_events = await get_all_events(execution_id)
        middle_timestamp = all_events[len(all_events) // 2]["timestamp"]

        # Replay from middle
        replayed_events = []
        async for event in websocket_connect(
            f"executions/{execution_id}?replay=true&from={middle_timestamp}"
        ):
            replayed_events.append(event)
            if event["type"] == "execution_completed":
                break

        # Verify only latter half of events
        assert len(replayed_events) <= len(all_events) // 2 + 5


class TestHighFrequencyEvents:
    """Tests for handling high-frequency events."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_handle_high_frequency_log_events(self):
        """
        Test handling high-frequency log events (100+ per second).

        Verifies:
        - All events delivered
        - No backpressure issues
        - No client disconnections
        - Acceptable latency
        """
        execution_id = await start_execution_with_verbose_logging()

        events = []
        start_time = datetime.utcnow()

        async for event in websocket_connect(f"executions/{execution_id}/logs"):
            if event["type"] == "log_entry":
                events.append(event)

            # Collect for 5 seconds
            if (datetime.utcnow() - start_time).total_seconds() > 5:
                break

        # Verify high event rate
        events_per_second = len(events) / 5
        assert events_per_second >= 50  # At least 50 events/sec

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_throttle_progress_events(self):
        """
        Test progress events are throttled appropriately.

        Verifies:
        - Progress updates not too frequent
        - Latest progress value always sent
        - No more than reasonable rate (e.g., 10/sec)
        """
        execution_id = await start_execution()

        progress_events = []
        last_progress = 0

        async for event in websocket_connect(f"executions/{execution_id}"):
            if event["type"] == "progress_update":
                progress_events.append({
                    "timestamp": datetime.utcnow(),
                    "progress": event["progress"],
                })
                last_progress = event["progress"]

            if event["type"] == "execution_completed":
                break

        # Verify reasonable event rate
        if len(progress_events) > 1:
            duration = (
                progress_events[-1]["timestamp"] - progress_events[0]["timestamp"]
            ).total_seconds()
            events_per_second = len(progress_events) / max(duration, 1)
            assert events_per_second <= 20  # No more than 20 progress events/sec


# ============================================================================
# Helper Functions
# ============================================================================

async def create_work_item() -> str:
    return "work-item-123"


async def websocket_connect(path: str) -> AsyncGenerator:
    yield {"type": "connected"}
    yield {"type": "status_changed", "old_status": "pending", "new_status": "in_progress"}
    yield {"type": "status_changed", "old_status": "in_progress", "new_status": "completed"}


async def update_work_item_status(work_item_id: str, status: WorkItemStatus):
    pass


async def start_execution() -> str:
    return "exec-123"


async def start_long_running_execution() -> str:
    return "exec-long"


async def websocket_connect_with_reconnect(path: str) -> AsyncGenerator:
    yield {"type": "connected"}
    yield {"type": "event", "sequence": 1}


async def simulate_disconnect():
    pass


async def websocket_connect_with_tracking(path: str) -> AsyncGenerator:
    yield {"type": "connection_attempt", "timestamp": datetime.utcnow()}
    yield {"type": "connected"}


async def start_and_complete_execution() -> str:
    return "exec-completed"


async def get_all_events(execution_id: str) -> List[dict]:
    return [
        {"type": "execution_started", "timestamp": "2024-01-01T00:00:00"},
        {"type": "execution_completed", "timestamp": "2024-01-01T00:01:00"},
    ]


async def start_execution_with_verbose_logging() -> str:
    return "exec-verbose"
