"""Acceptance test: Kill-a-container with real infrastructure.

This test proves end-to-end container recovery with real infrastructure:
- Real Docker container with Codetoreum labels
- Real Redis-backed tracking storage
- Real DockerContainerRecoveryAdapter
- Real execution state tracker
- No mocks on the tested path
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import AsyncGenerator

import docker
import pytest
from redis import asyncio as aioredis

from codetoreum.adapters.secondary.docker_container_recovery_adapter import (
    DockerContainerRecoveryAdapter,
)
from codetoreum.adapters.secondary.redis_container_recovery_tracking_store import (
    RedisContainerRecoveryTrackingStore,
)
from codetoreum.adapters.secondary.redis_execution_state_tracker import (
    RedisExecutionStateTracker,
)
from codetoreum.application.container_recovery_service import (
    ContainerRecoveryService,
)
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
from tests.conftest import EventCollector, ModernRedisContainer, docker_available

pytestmark = docker_available


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
        """Test reconnect path: valid execution state detected and recovered."""
        project_id = "test-project-recovery"
        work_item_id = "issue-1001"
        agent_id = "senior_software_engineer"
        task_id = "code-generation"
        execution_id = "exec-recovery-001"
        container_name = f"codetoreum-agent-{execution_id}"

        await execution_tracker.mark_execution_started(project_id, work_item_id, agent_id)

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

            result = await service.recover_or_cleanup_containers()

            assert result.recovered == 1
            assert result.killed == 0
            assert result.errors == 0

            recovered_events = event_emitter.get_events_by_type(ContainerRecoveredEvent)
            assert len(recovered_events) == 1

            recovery_event = recovered_events[0]
            assert recovery_event.container_id == container.id
            assert recovery_event.container_name == container_name
            assert recovery_event.project_id == project_id
            assert recovery_event.agent_id == agent_id
            assert recovery_event.work_item_id == work_item_id
            assert recovery_event.recovery_action == "reconnect_with_monitoring"
            assert recovery_event.execution_id == execution_id

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
        """Test kill path: container exceeds age timeout."""
        project_id = "test-project-timeout"
        work_item_id = "issue-1002"
        agent_id = "code_reviewer"
        task_id = "review"
        execution_id = "exec-timeout-001"
        container_name = f"codetoreum-agent-timeout-{execution_id}"

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

            # 0.001 hours = 3.6 seconds; wait longer so container is considered old
            await asyncio.sleep(5)

            event_emitter = EventCollector()
            recovery_adapter = DockerContainerRecoveryAdapter(
                execution_tracker=execution_tracker,
                tracking_storage=tracking_storage,
                container_timeout_hours=0.001,
            )

            service = ContainerRecoveryService(
                recovery_adapter=recovery_adapter,
                event_emitter=event_emitter,
                container_timeout_hours=0.001,
            )

            result = await service.recover_or_cleanup_containers()

            assert result.recovered == 0
            assert result.killed == 1
            assert result.errors == 0

            killed_events = event_emitter.get_events_by_type(ContainerKilledEvent)
            assert len(killed_events) == 1

            kill_event = killed_events[0]
            assert kill_event.container_id == container.id
            assert kill_event.container_name == container_name
            assert kill_event.kill_reason == "container_timeout"

            try:
                container.reload()
                assert container.status != "running"
            except docker.errors.NotFound:
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
        """Test kill path: no execution state found (orphaned container)."""
        project_id = "test-project-no-exec"
        work_item_id = "issue-1003"
        agent_id = "qa_engineer"
        task_id = "testing"
        execution_id = "exec-no-exec-001"
        container_name = f"codetoreum-agent-no-exec-{execution_id}"

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

            result = await service.recover_or_cleanup_containers()

            assert result.recovered == 0
            assert result.killed == 1
            assert result.errors == 0

            killed_events = event_emitter.get_events_by_type(ContainerKilledEvent)
            assert len(killed_events) == 1

            kill_event = killed_events[0]
            assert kill_event.container_id == container.id
            assert kill_event.kill_reason == "no_execution_found"

            try:
                container.reload()
                assert container.status != "running"
            except docker.errors.NotFound:
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
        """Test mixed paths: one container recovers, one is killed."""
        containers_to_clean = []

        try:
            # Container A: Valid execution (reconnect path)
            project_a = "test-project-mixed-a"
            work_item_a = "issue-2001"
            agent_a = "software_engineer"
            execution_id_a = "exec-mixed-a"
            container_name_a = f"codetoreum-agent-mixed-a-{execution_id_a}"

            await execution_tracker.mark_execution_started(project_a, work_item_a, agent_a)

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

            result = await service.recover_or_cleanup_containers()

            assert result.recovered == 1
            assert result.killed == 1
            assert result.errors == 0

            recovered_events = event_emitter.get_events_by_type(ContainerRecoveredEvent)
            killed_events = event_emitter.get_events_by_type(ContainerKilledEvent)

            assert len(recovered_events) == 1
            assert len(killed_events) == 1

            recovery_event_a = recovered_events[0]
            assert recovery_event_a.container_id == container_a.id
            assert recovery_event_a.recovery_action == "reconnect_with_monitoring"

            kill_event_b = killed_events[0]
            assert kill_event_b.kill_reason == "no_execution_found"

        finally:
            # Cleanup: Force remove all containers
            for container in containers_to_clean:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
