"""Acceptance test: Kill-a-container with real infrastructure.

This test proves end-to-end container recovery with real infrastructure:
- Real Docker container with Codetoreum labels
- Real Redis-backed tracking storage
- Real DockerContainerRecoveryAdapter
- Real execution state tracker
- No mocks on the tested path

Acceptance Criteria:
1. Starts a real labeled Docker container representing an agent execution
2. Uses real Docker SDK queries via DockerContainerRecoveryAdapter
3. Uses Redis-backed execution_tracker and tracking_storage
4. Kills the container
5. Verifies correct recovery action via decision tree (reconnect vs kill)
6. No component on the tested path is mocked
"""

import json
from datetime import UTC, datetime, timedelta
from typing import AsyncGenerator

import docker
import pytest
from redis import asyncio as aioredis

from codetoreum.adapters.secondary.docker_container_recovery_adapter import (
    DockerContainerRecoveryAdapter,
)
from codetoreum.adapters.secondary.mock_event_emitter import MockEventEmitter
from codetoreum.adapters.secondary.redis_container_recovery_tracking_store import (
    RedisContainerRecoveryTrackingStore,
)
from codetoreum.adapters.secondary.redis_execution_state_tracker import (
    RedisExecutionStateTracker,
)
from codetoreum.application.container_recovery_service import (
    ContainerRecoveryService,
)
from codetoreum.domain.events.adapter_events import CodetoreumEvent
from codetoreum.domain.events.container_recovery_events import (
    ContainerKilledEvent,
    ContainerRecoveredEvent,
)
from codetoreum.domain.types import (
    CONTAINER_LABEL_AGENT,
    CONTAINER_LABEL_EXECUTION_ID,
    CONTAINER_LABEL_PROJECT,
    CONTAINER_LABEL_TASK_ID,
    CONTAINER_LABEL_TYPE,
    CONTAINER_LABEL_WORK_ITEM_ID,
    CONTAINER_TYPE_AGENT,
)
from tests.conftest import ModernRedisContainer, docker_available

pytestmark = docker_available


class EventCollector(MockEventEmitter):
    """Event emitter that collects events for testing.

    Extends MockEventEmitter to add event collection capability,
    allowing tests to verify events were emitted.
    """

    def __init__(self) -> None:
        """Initialize the event collector."""
        super().__init__()
        self.events: list[CodetoreumEvent] = []

    def emit(self, event: CodetoreumEvent) -> None:
        """Emit an event and collect it for testing.

        Args:
            event: CodetoreumEvent instance to emit
        """
        self.events.append(event)
        super().emit(event)


@pytest.fixture(scope="function")
def redis_container():
    """Redis test container for tracking storage."""
    container = ModernRedisContainer(image="redis:7-alpine")
    try:
        container.start()
    except Exception:
        try:
            container.stop()
        except Exception:
            pass
        raise
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="function")
async def redis_client(redis_container) -> AsyncGenerator[aioredis.Redis, None]:
    """Redis async client connected to test container."""
    url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}"
    client = aioredis.from_url(url, decode_responses=True)

    try:
        await client.ping()
        yield client
    finally:
        await client.close()


@pytest.fixture(scope="function")
async def execution_tracker(redis_client) -> AsyncGenerator[RedisExecutionStateTracker, None]:
    """Redis-backed execution state tracker."""
    tracker = RedisExecutionStateTracker(redis_client)
    yield tracker


@pytest.fixture(scope="function")
async def tracking_storage(redis_client) -> AsyncGenerator[RedisContainerRecoveryTrackingStore, None]:
    """Redis-backed container recovery tracking storage."""
    storage = RedisContainerRecoveryTrackingStore(redis_client, default_ttl_seconds=3600)
    yield storage


@pytest.fixture(scope="function")
def docker_client():
    """Shared Docker client for test container creation."""
    client = docker.from_env()
    try:
        yield client
    finally:
        client.close()


class TestContainerRecoveryAcceptance:
    """Acceptance tests for container recovery with real infrastructure."""

    @pytest.mark.asyncio
    async def test_detect_and_recover_running_container_reconnect_path(
        self,
        docker_client,
        execution_tracker,
        tracking_storage,
    ):
        """
        Acceptance test: Detect and recover a running container (reconnect path).

        This test verifies the decision tree reconnect path with real infrastructure:
        1. Create a running container with valid execution state in storage
        2. Leave the container running (simulating orchestrator restart)
        3. Run recovery via real DockerContainerRecoveryAdapter
        4. Verify the service detects the running container via Docker API
        5. Verify correct assessment (reconnect with monitoring)
        6. Verify container is re-registered in tracking storage
        """
        # Test identifiers
        project_id = "test-project-recovery"
        work_item_id = "issue-1001"
        agent_id = "senior_software_engineer"
        task_id = "code-generation"
        execution_id = "exec-recovery-001"
        container_name = f"codetoreum-agent-{execution_id}"

        # Step 1: Set up execution state in tracker (pre-recovery state)
        # This simulates an execution that was in_progress when orchestrator crashed
        # The execution tracker uses a specific key format: codetoreum:execution:state:{project}:{work_item_id}
        execution_state = {
            "project": project_id,
            "work_item_id": work_item_id,
            "agent": agent_id,
            "outcome": "in_progress",
            "started_at": datetime.now(UTC).isoformat(),
        }
        state_key = f"codetoreum:execution:state:{project_id}:{work_item_id}"
        await execution_tracker._redis.set(state_key, json.dumps(execution_state), ex=14400)

        # Step 2: Start a real Docker container with Codetoreum labels
        container_labels = {
            CONTAINER_LABEL_TYPE: CONTAINER_TYPE_AGENT,
            CONTAINER_LABEL_PROJECT: project_id,
            CONTAINER_LABEL_AGENT: agent_id,
            CONTAINER_LABEL_WORK_ITEM_ID: work_item_id,
            CONTAINER_LABEL_TASK_ID: task_id,
            CONTAINER_LABEL_EXECUTION_ID: execution_id,
        }

        container = docker_client.containers.run(
            "alpine:latest",
            command=["sleep", "3600"],  # Run for 1 hour
            name=container_name,
            labels=container_labels,
            detach=True,
            remove=False,  # Manual cleanup
        )

        try:
            # Verify container is running (simulating orchestrator detecting running container on restart)
            container.reload()
            assert container.status == "running"
            created_at = datetime.fromisoformat(
                container.attrs["Created"].replace("Z", "+00:00")
            )

            # Step 3: Create adapters and recovery service
            # (This simulates orchestrator startup with container recovery enabled)
            event_emitter = EventCollector()
            recovery_adapter = DockerContainerRecoveryAdapter(
                execution_tracker=execution_tracker,
                tracking_storage=tracking_storage,
                container_timeout_hours=2,
            )

            service = ContainerRecoveryService(
                recovery_adapter=recovery_adapter,
                event_emitter=event_emitter,
                container_timeout_hours=2,
            )

            # Step 4: Run recovery cycle (orchestrator startup recovery)
            result = await service.recover_or_cleanup_containers()

            # Step 5: Verify results - should have recovered 1, killed 0
            assert result.recovered == 1, f"Expected 1 recovered, got {result.recovered}"
            assert result.killed == 0, f"Expected 0 killed, got {result.killed}"
            assert result.errors == 0, f"Expected 0 errors, got {result.errors}"

            # Step 6: Verify events emitted
            recovered_events = [
                e for e in event_emitter.events
                if isinstance(e, ContainerRecoveredEvent)
            ]
            assert len(recovered_events) == 1, f"Expected 1 recovery event, got {len(recovered_events)}"

            recovery_event = recovered_events[0]
            assert recovery_event.container_id == container.id
            assert recovery_event.container_name == container_name
            assert recovery_event.project_id == project_id
            assert recovery_event.agent_id == agent_id
            assert recovery_event.work_item_id == work_item_id
            assert recovery_event.recovery_action == "reconnect_with_monitoring"
            assert recovery_event.execution_id == execution_id

            # Step 7: Verify container was re-registered in tracking storage
            registered_key = f"agent:container:{container_name}"
            registered_info = await tracking_storage.get(registered_key)
            assert registered_info is not None
            assert registered_info["containerName"] == container_name
            assert registered_info["recovered"] == "true"
            assert registered_info["project"] == project_id

        finally:
            # Cleanup: Remove container
            try:
                container.kill()
                container.remove(force=True)
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_kill_old_running_container_timeout_path(
        self,
        docker_client,
        execution_tracker,
        tracking_storage,
    ):
        """
        Acceptance test: Kill an old running container (age-check path).

        This test verifies the container age-check decision tree path:
        1. Create a running container
        2. Set recovery service timeout very low (forcing age-based kill)
        3. Run recovery via real DockerContainerRecoveryAdapter
        4. Verify correct assessment (kill due to timeout)
        5. Verify kill action executed via real Docker API
        """
        # Test identifiers
        project_id = "test-project-timeout"
        work_item_id = "issue-1002"
        agent_id = "code_reviewer"
        task_id = "review"
        execution_id = "exec-timeout-001"
        container_name = f"codetoreum-agent-timeout-{execution_id}"

        # Step 1: Start a running container
        container_labels = {
            CONTAINER_LABEL_TYPE: CONTAINER_TYPE_AGENT,
            CONTAINER_LABEL_PROJECT: project_id,
            CONTAINER_LABEL_AGENT: agent_id,
            CONTAINER_LABEL_WORK_ITEM_ID: work_item_id,
            CONTAINER_LABEL_TASK_ID: task_id,
            CONTAINER_LABEL_EXECUTION_ID: execution_id,
        }

        container = docker_client.containers.run(
            "alpine:latest",
            command=["sleep", "3600"],
            name=container_name,
            labels=container_labels,
            detach=True,
            remove=False,
        )

        try:
            container.reload()
            assert container.status == "running"

            # Step 2: Wait to ensure container is old enough
            # 0.001 hours = 3.6 seconds, so we need to wait > 3.6 seconds
            import asyncio
            await asyncio.sleep(5)

            # Step 3: Create recovery service with very short timeout (0.001 hours)
            # This forces the container to be considered old and killed
            event_emitter = EventCollector()
            recovery_adapter = DockerContainerRecoveryAdapter(
                execution_tracker=execution_tracker,
                tracking_storage=tracking_storage,
                container_timeout_hours=0.001,  # ~3.6 seconds - container will now exceed this
            )

            service = ContainerRecoveryService(
                recovery_adapter=recovery_adapter,
                event_emitter=event_emitter,
                container_timeout_hours=0.001,
            )

            # Step 4: Run recovery cycle
            result = await service.recover_or_cleanup_containers()

            # Step 5: Verify results - should have killed 1 due to timeout
            assert result.recovered == 0, f"Expected 0 recovered, got {result.recovered}"
            assert result.killed == 1, f"Expected 1 killed, got {result.killed}"
            assert result.errors == 0, f"Expected 0 errors, got {result.errors}"

            # Step 6: Verify kill event was emitted with correct reason
            killed_events = [
                e for e in event_emitter.events
                if isinstance(e, ContainerKilledEvent)
            ]
            assert len(killed_events) == 1, f"Expected 1 kill event, got {len(killed_events)}"

            kill_event = killed_events[0]
            assert kill_event.container_id == container.id
            assert kill_event.container_name == container_name
            assert kill_event.kill_reason == "container_timeout"

            # Step 7: Verify container was actually killed (no longer running)
            try:
                container.reload()
                # If we got here, container might still exist but should be exited
                assert container.status != "running"
            except docker.errors.NotFound:
                # Container was removed, which is expected
                pass

        finally:
            # Cleanup: Try to remove container if it still exists
            try:
                container.remove(force=True)
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_kill_orphaned_running_container_no_execution_path(
        self,
        docker_client,
        execution_tracker,
        tracking_storage,
    ):
        """
        Acceptance test: Kill orphaned running container (no execution state).

        This test verifies the no-execution-found decision tree path:
        1. Create a running container without execution state in storage
        2. Run recovery via real DockerContainerRecoveryAdapter
        3. Verify correct assessment (kill due to orphaned status)
        4. Verify kill action executed via real Docker API
        """
        # Test identifiers
        project_id = "test-project-no-exec"
        work_item_id = "issue-1003"
        agent_id = "qa_engineer"
        task_id = "testing"
        execution_id = "exec-no-exec-001"
        container_name = f"codetoreum-agent-no-exec-{execution_id}"

        # Note: We explicitly do NOT set execution state in storage
        # This simulates an orphaned container with no matching execution

        # Step 1: Start a running container
        container_labels = {
            CONTAINER_LABEL_TYPE: CONTAINER_TYPE_AGENT,
            CONTAINER_LABEL_PROJECT: project_id,
            CONTAINER_LABEL_AGENT: agent_id,
            CONTAINER_LABEL_WORK_ITEM_ID: work_item_id,
            CONTAINER_LABEL_TASK_ID: task_id,
            CONTAINER_LABEL_EXECUTION_ID: execution_id,
        }

        container = docker_client.containers.run(
            "alpine:latest",
            command=["sleep", "3600"],
            name=container_name,
            labels=container_labels,
            detach=True,
            remove=False,
        )

        try:
            container.reload()
            assert container.status == "running"

            # Step 2: Create recovery service
            event_emitter = EventCollector()
            recovery_adapter = DockerContainerRecoveryAdapter(
                execution_tracker=execution_tracker,
                tracking_storage=tracking_storage,
                container_timeout_hours=2,
            )

            service = ContainerRecoveryService(
                recovery_adapter=recovery_adapter,
                event_emitter=event_emitter,
                container_timeout_hours=2,
            )

            # Step 3: Run recovery cycle
            result = await service.recover_or_cleanup_containers()

            # Step 4: Verify results - should have killed 1 (no execution found)
            assert result.recovered == 0, f"Expected 0 recovered, got {result.recovered}"
            assert result.killed == 1, f"Expected 1 killed, got {result.killed}"
            assert result.errors == 0, f"Expected 0 errors, got {result.errors}"

            # Step 5: Verify kill event was emitted with correct reason
            killed_events = [
                e for e in event_emitter.events
                if isinstance(e, ContainerKilledEvent)
            ]
            assert len(killed_events) == 1, f"Expected 1 kill event, got {len(killed_events)}"

            kill_event = killed_events[0]
            assert kill_event.container_id == container.id
            assert kill_event.kill_reason == "no_execution_found"

            # Step 6: Verify container was actually killed
            try:
                container.reload()
                assert container.status != "running"
            except docker.errors.NotFound:
                # Container was removed, which is expected
                pass

        finally:
            # Cleanup: Try to remove container if it still exists
            try:
                container.remove(force=True)
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_multiple_containers_mixed_recovery_and_kill_actions(
        self,
        docker_client,
        execution_tracker,
        tracking_storage,
    ):
        """
        Acceptance test: Recover/kill multiple running containers with different reasons.

        This test verifies the full recovery cycle with multiple running containers:
        1. Container A: Valid execution (in_progress) → Reconnect with monitoring
        2. Container B: No execution state (orphaned) → Kill
        3. Run recovery cycle
        4. Verify correct mixed actions for each container via real Docker API
        """
        containers_to_clean = []

        try:
            # Container A: Valid execution (reconnect path)
            project_a = "test-project-mixed-a"
            work_item_a = "issue-2001"
            agent_a = "software_engineer"
            execution_id_a = "exec-mixed-a"
            container_name_a = f"codetoreum-agent-mixed-a-{execution_id_a}"

            execution_state_a = {
                "project": project_a,
                "work_item_id": work_item_a,
                "agent": agent_a,
                "outcome": "in_progress",
                "started_at": datetime.now(UTC).isoformat(),
            }
            state_key_a = f"codetoreum:execution:state:{project_a}:{work_item_a}"
            await execution_tracker._redis.set(state_key_a, json.dumps(execution_state_a), ex=14400)

            container_a = docker_client.containers.run(
                "alpine:latest",
                command=["sleep", "3600"],
                name=container_name_a,
                labels={
                    CONTAINER_LABEL_TYPE: CONTAINER_TYPE_AGENT,
                    CONTAINER_LABEL_PROJECT: project_a,
                    CONTAINER_LABEL_AGENT: agent_a,
                    CONTAINER_LABEL_WORK_ITEM_ID: work_item_a,
                    CONTAINER_LABEL_TASK_ID: "task-a",
                    CONTAINER_LABEL_EXECUTION_ID: execution_id_a,
                },
                detach=True,
                remove=False,
            )
            containers_to_clean.append(container_a)

            # Container B: No execution (kill path)
            project_b = "test-project-mixed-b"
            work_item_b = "issue-2002"
            agent_b = "reviewer"
            execution_id_b = "exec-mixed-b"
            container_name_b = f"codetoreum-agent-mixed-b-{execution_id_b}"

            # Don't set execution state for this one

            container_b = docker_client.containers.run(
                "alpine:latest",
                command=["sleep", "3600"],
                name=container_name_b,
                labels={
                    CONTAINER_LABEL_TYPE: CONTAINER_TYPE_AGENT,
                    CONTAINER_LABEL_PROJECT: project_b,
                    CONTAINER_LABEL_AGENT: agent_b,
                    CONTAINER_LABEL_WORK_ITEM_ID: work_item_b,
                    CONTAINER_LABEL_TASK_ID: "task-b",
                    CONTAINER_LABEL_EXECUTION_ID: execution_id_b,
                },
                detach=True,
                remove=False,
            )
            containers_to_clean.append(container_b)

            # Run recovery with normal timeout
            event_emitter = EventCollector()
            recovery_adapter = DockerContainerRecoveryAdapter(
                execution_tracker=execution_tracker,
                tracking_storage=tracking_storage,
                container_timeout_hours=2,  # Normal 2-hour timeout
            )

            service = ContainerRecoveryService(
                recovery_adapter=recovery_adapter,
                event_emitter=event_emitter,
                container_timeout_hours=2,
            )

            # Run recovery
            result = await service.recover_or_cleanup_containers()

            # Verify overall counts
            assert result.recovered == 1, f"Expected 1 recovered, got {result.recovered}"
            assert result.killed == 1, f"Expected 1 killed, got {result.killed}"
            assert result.errors == 0, f"Expected 0 errors, got {result.errors}"

            # Verify individual events
            recovered_events = [
                e for e in event_emitter.events
                if isinstance(e, ContainerRecoveredEvent)
            ]
            killed_events = [
                e for e in event_emitter.events
                if isinstance(e, ContainerKilledEvent)
            ]

            assert len(recovered_events) == 1, f"Expected 1 recovery event, got {len(recovered_events)}"
            assert len(killed_events) == 1, f"Expected 1 kill event, got {len(killed_events)}"

            # Container A should be recovered
            recovery_event_a = recovered_events[0]
            assert recovery_event_a.container_id == container_a.id
            assert recovery_event_a.recovery_action == "reconnect_with_monitoring"

            # Container B should be killed
            kill_event_b = killed_events[0]
            assert kill_event_b.kill_reason == "no_execution_found"

        finally:
            # Cleanup: Force remove all containers
            for container in containers_to_clean:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
