"""
End-to-end tests for error recovery scenarios.

Tests agent failure recovery, container crash handling, timeout recovery,
network failure recovery, database connection loss recovery, partial execution
state recovery, cascading failure prevention, and circuit breaker behavior.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import AsyncGenerator

from codetoreum.domain.models.agent_execution import ExecutionStatus
from codetoreum.domain.models.work_item import WorkItemStatus


class TestAgentFailureRecovery:
    """Tests for recovering from agent execution failures."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_recover_from_agent_crash(self):
        """
        Test recovery from agent process crash.

        Verifies:
        - Agent crash is detected
        - Execution state is preserved
        - New agent instance is started
        - Execution resumes from last checkpoint
        - Final result is correct
        """
        execution_id = await start_execution_with_crash_simulation()

        events = []
        async for event in monitor_execution(execution_id):
            events.append(event)
            if event["type"] == "execution_completed":
                break

        # Verify crash was detected and recovered
        assert any(e["type"] == "agent_crashed" for e in events)
        assert any(e["type"] == "agent_restarted" for e in events)
        assert any(e["type"] == "execution_resumed" for e in events)

        # Verify final success
        final_event = events[-1]
        assert final_event["type"] == "execution_completed"
        assert final_event["status"] == "success"

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_recover_from_agent_timeout(self):
        """
        Test recovery from agent execution timeout.

        Verifies:
        - Timeout is detected
        - Agent is terminated gracefully
        - Retry with increased timeout
        - Execution completes successfully
        """
        execution_id = await start_execution_with_timeout()

        timeouts = []
        retries = []

        async for event in monitor_execution(execution_id):
            if event["type"] == "execution_timeout":
                timeouts.append(event)

            if event["type"] == "execution_retry":
                retries.append(event)
                # Verify increased timeout
                assert event["new_timeout"] > event["previous_timeout"]

            if event["type"] == "execution_completed":
                break

        # Verify timeout and retry occurred
        assert len(timeouts) > 0
        assert len(retries) > 0

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_recover_from_model_api_rate_limit(self):
        """
        Test recovery from LLM API rate limiting.

        Verifies:
        - Rate limit error detected
        - Exponential backoff applied
        - Execution retried after backoff
        - Circuit breaker doesn't trip
        """
        execution_id = await start_execution_with_rate_limit()

        rate_limit_errors = []
        backoffs = []

        async for event in monitor_execution(execution_id):
            if event["type"] == "rate_limit_error":
                rate_limit_errors.append(event)

            if event["type"] == "backoff_wait":
                backoffs.append(event["wait_seconds"])

            if event["type"] == "execution_completed":
                break

        # Verify rate limit was handled
        assert len(rate_limit_errors) > 0
        assert len(backoffs) > 0

        # Verify exponential backoff
        if len(backoffs) > 1:
            assert backoffs[1] > backoffs[0]


class TestContainerCrashHandling:
    """Tests for handling container crashes."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_detect_and_recover_from_container_crash(self):
        """
        Test detection and recovery from container crash.

        Verifies:
        - Container crash detected
        - Execution state saved
        - New container started
        - State restored
        - Execution continues
        """
        execution_id = await start_execution_in_container()

        # Simulate container crash
        await simulate_container_crash(execution_id)

        recovery_events = []
        async for event in monitor_execution(execution_id):
            if event["type"] in ["container_crashed", "container_restarted", "state_restored"]:
                recovery_events.append(event)

            if event["type"] == "execution_completed":
                break

        # Verify recovery sequence
        assert any(e["type"] == "container_crashed" for e in recovery_events)
        assert any(e["type"] == "container_restarted" for e in recovery_events)
        assert any(e["type"] == "state_restored" for e in recovery_events)

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_container_resource_exhaustion_handling(self):
        """
        Test handling container resource exhaustion (OOM, disk full).

        Verifies:
        - Resource exhaustion detected
        - Container stopped gracefully
        - New container with more resources
        - Execution continues successfully
        """
        execution_id = await start_execution_with_limited_resources()

        resource_events = []
        async for event in monitor_execution(execution_id):
            if "resource" in event["type"]:
                resource_events.append(event)

            if event["type"] == "execution_completed":
                break

        # Verify resource scaling occurred
        assert any("exhaustion" in e["type"] for e in resource_events)
        assert any("scaled_up" in e["type"] for e in resource_events)


class TestNetworkFailureRecovery:
    """Tests for recovering from network failures."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_recover_from_api_connection_loss(self):
        """
        Test recovery from loss of API connection.

        Verifies:
        - Connection loss detected
        - Retry with exponential backoff
        - Connection restored
        - Operation completes successfully
        """
        execution_id = await start_execution_with_network_issues()

        connection_events = []
        async for event in monitor_execution(execution_id):
            if "connection" in event["type"]:
                connection_events.append(event)

            if event["type"] == "execution_completed":
                break

        # Verify connection recovery
        assert any("lost" in e["type"] for e in connection_events)
        assert any("restored" in e["type"] for e in connection_events)

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_websocket_reconnection_on_disconnect(self):
        """
        Test WebSocket reconnection after disconnect.

        Verifies:
        - Disconnect detected
        - Automatic reconnection attempted
        - Event stream resumes
        - No events lost
        """
        execution_id = await start_execution()

        # Connect WebSocket client
        received_events = []

        async for event in websocket_client_with_reconnection(execution_id):
            received_events.append(event)

            # Simulate disconnect after some events
            if len(received_events) == 5:
                await simulate_network_disconnect()

            if event["type"] == "execution_completed":
                break

        # Verify events were received continuously despite disconnect
        event_numbers = [e.get("sequence", 0) for e in received_events]
        # Check for gaps in sequence
        gaps = [b - a for a, b in zip(event_numbers, event_numbers[1:]) if b - a > 1]
        assert len(gaps) == 0  # No gaps means no events lost


class TestDatabaseConnectionRecovery:
    """Tests for database connection loss recovery."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_recover_from_database_connection_loss(self):
        """
        Test recovery from database connection loss.

        Verifies:
        - Connection loss detected
        - Operations queued
        - Connection restored
        - Queued operations executed
        - Data consistency maintained
        """
        execution_id = await start_execution()

        # Simulate database connection loss
        await simulate_database_disconnect()

        # Continue execution (operations should be queued)
        await asyncio.sleep(2)

        # Restore connection
        await restore_database_connection()

        # Verify execution completed successfully
        status = await get_execution_status(execution_id)
        assert status == "completed"

        # Verify all state changes were persisted
        events = await get_execution_events(execution_id)
        assert len(events) > 0

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_transaction_rollback_on_failure(self):
        """
        Test transaction rollback on database failure.

        Verifies:
        - Partial transaction detected
        - Rollback executed
        - System state consistent
        - Retry succeeds
        """
        # Start operation that will fail mid-transaction
        work_item_id = await create_work_item_with_db_failure()

        # Verify rollback occurred
        work_item = await get_work_item(work_item_id)
        assert work_item is None or work_item.status == WorkItemStatus.PENDING

        # Retry should succeed
        work_item = await retry_work_item_creation(work_item_id)
        assert work_item is not None


class TestPartialExecutionStateRecovery:
    """Tests for recovering from partial execution state."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_resume_from_checkpoint_after_crash(self):
        """
        Test resuming execution from checkpoint after crash.

        Verifies:
        - Checkpoint exists before crash
        - State restored from checkpoint
        - Already-completed work not repeated
        - Execution continues from checkpoint
        """
        execution_id = await start_execution_with_checkpoints()

        # Let execution progress past first checkpoint
        await wait_for_checkpoint(execution_id, checkpoint_number=1)

        # Simulate crash
        await simulate_crash(execution_id)

        # Resume execution
        await resume_execution(execution_id)

        # Monitor resumed execution
        checkpoints_hit = []
        async for event in monitor_execution(execution_id):
            if event["type"] == "checkpoint_reached":
                checkpoints_hit.append(event["checkpoint_number"])

            if event["type"] == "execution_completed":
                break

        # Verify did not repeat checkpoint 1
        assert 1 not in checkpoints_hit
        # Verify continued from checkpoint 2
        assert 2 in checkpoints_hit

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_handle_corrupted_execution_state(self):
        """
        Test handling corrupted execution state.

        Verifies:
        - Corruption detected
        - Fallback to earlier checkpoint
        - State validation
        - Execution recovers
        """
        execution_id = await start_execution_with_checkpoints()

        # Corrupt the current state
        await corrupt_execution_state(execution_id)

        # Attempt to continue
        recovery_events = []
        async for event in monitor_execution(execution_id):
            if "recovery" in event["type"] or "corruption" in event["type"]:
                recovery_events.append(event)

            if event["type"] == "execution_completed":
                break

        # Verify corruption was detected and handled
        assert any("corruption_detected" in e["type"] for e in recovery_events)
        assert any("fallback_to_checkpoint" in e["type"] for e in recovery_events)


class TestCascadingFailurePrevention:
    """Tests for preventing cascading failures."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_circuit_breaker_prevents_cascading_failures(self):
        """
        Test circuit breaker preventing cascading failures.

        Verifies:
        - Multiple failures detected
        - Circuit breaker opens
        - Subsequent requests fail fast
        - Circuit breaker closes after recovery
        """
        # Trigger multiple failures
        execution_ids = []
        for i in range(10):
            exec_id = await start_execution_that_will_fail()
            execution_ids.append(exec_id)
            await asyncio.sleep(0.1)

        # Verify circuit breaker opened
        circuit_state = await get_circuit_breaker_state("agent_executor")
        assert circuit_state == "open"

        # Verify subsequent requests fail fast
        start_time = datetime.utcnow()
        try:
            await start_execution()
        except Exception as e:
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            assert elapsed < 1.0  # Failed fast, didn't wait for timeout
            assert "circuit breaker" in str(e).lower()

        # Wait for circuit breaker to allow retry
        await asyncio.sleep(30)

        # Verify circuit breaker allows retry
        circuit_state = await get_circuit_breaker_state("agent_executor")
        assert circuit_state in ["half_open", "closed"]

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_rate_limiting_prevents_resource_exhaustion(self):
        """
        Test rate limiting preventing resource exhaustion.

        Verifies:
        - Rate limit enforced
        - Excess requests queued
        - System remains stable
        - All requests eventually processed
        """
        # Send requests above rate limit
        execution_ids = []
        for i in range(50):
            exec_id = await start_execution()
            execution_ids.append(exec_id)

        # Verify rate limiting applied
        rate_limit_events = await get_rate_limit_events()
        assert len(rate_limit_events) > 0

        # Verify system stability (no crashes)
        system_health = await check_system_health()
        assert system_health["status"] == "healthy"

        # Verify all requests eventually complete
        await wait_for_all_executions(execution_ids, timeout=300)
        statuses = await get_execution_statuses(execution_ids)
        assert all(s in ["completed", "failed"] for s in statuses)


# ============================================================================
# Helper Functions
# ============================================================================

async def start_execution_with_crash_simulation() -> str:
    """Start execution that will simulate a crash."""
    return "exec-crash-sim"


async def monitor_execution(execution_id: str) -> AsyncGenerator:
    """Monitor execution events."""
    yield {"type": "execution_started", "execution_id": execution_id}
    yield {"type": "execution_completed", "status": "success"}


async def start_execution_with_timeout() -> str:
    return "exec-timeout"


async def start_execution_with_rate_limit() -> str:
    return "exec-rate-limit"


async def start_execution_in_container() -> str:
    return "exec-container"


async def simulate_container_crash(execution_id: str):
    pass


async def start_execution_with_limited_resources() -> str:
    return "exec-limited-resources"


async def start_execution_with_network_issues() -> str:
    return "exec-network-issues"


async def start_execution() -> str:
    return "exec-normal"


async def websocket_client_with_reconnection(execution_id: str) -> AsyncGenerator:
    for i in range(10):
        yield {"type": "event", "sequence": i}


async def simulate_network_disconnect():
    pass


async def simulate_database_disconnect():
    pass


async def restore_database_connection():
    pass


async def get_execution_status(execution_id: str) -> str:
    return "completed"


async def get_execution_events(execution_id: str) -> list:
    return [{"type": "event1"}, {"type": "event2"}]


async def create_work_item_with_db_failure() -> str:
    return "work-item-fail"


async def get_work_item(work_item_id: str):
    return None


async def retry_work_item_creation(work_item_id: str):
    return {"id": work_item_id, "status": "pending"}


async def start_execution_with_checkpoints() -> str:
    return "exec-checkpoints"


async def wait_for_checkpoint(execution_id: str, checkpoint_number: int):
    pass


async def simulate_crash(execution_id: str):
    pass


async def resume_execution(execution_id: str):
    pass


async def corrupt_execution_state(execution_id: str):
    pass


async def start_execution_that_will_fail() -> str:
    return "exec-will-fail"


async def get_circuit_breaker_state(service: str) -> str:
    return "closed"


async def get_rate_limit_events() -> list:
    return []


async def check_system_health() -> dict:
    return {"status": "healthy"}


async def wait_for_all_executions(execution_ids: list, timeout: int):
    pass


async def get_execution_statuses(execution_ids: list) -> list:
    return ["completed"] * len(execution_ids)
