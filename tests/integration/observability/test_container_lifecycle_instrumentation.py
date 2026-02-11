"""Integration tests for Docker container lifecycle instrumentation.

Tests that OpenTelemetry spans are correctly created for all container
lifecycle operations in:
- DockerContainerAdapter
- DockerContainerRecoveryAdapter
- ContainerRecoveryService
"""

import asyncio
import logging
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry import trace

from codetoreum.adapters.secondary import DockerConfig, DockerContainerAdapter
from codetoreum.adapters.secondary.docker_container_recovery_adapter import (
    DockerContainerRecoveryAdapter,
)
from codetoreum.application.container_recovery_service import ContainerRecoveryService
from codetoreum.ports.output.container_recovery import ContainerMetadata
from codetoreum.domain.types import ContainerId


pytestmark = pytest.mark.integration


@pytest.fixture
def in_memory_exporter():
    """Create an in-memory span exporter for testing."""
    return InMemorySpanExporter()


@pytest.fixture
def tracer_provider(in_memory_exporter):
    """Create a tracer provider with in-memory exporter."""
    provider = TracerProvider()
    processor = SimpleSpanProcessor(in_memory_exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    return provider


@pytest.fixture
def docker_config():
    """Create Docker configuration."""
    return DockerConfig(
        default_timeout=10,
        remove_on_completion=True,
        memory_limit="256m",
        cpu_limit=0.5,
    )


class TestDockerContainerAdapterInstrumentation:
    """Test instrumentation of DockerContainerAdapter methods."""

    @pytest.mark.asyncio
    async def test_run_method_creates_span(self, docker_config, tracer_provider, in_memory_exporter):
        """Test that run() method creates a container.run span."""
        adapter = DockerContainerAdapter(docker_config)

        # Mock the Docker client to avoid actual Docker calls
        with patch.object(adapter, '_get_client') as mock_get_client:
            mock_client = MagicMock()
            mock_container = MagicMock()
            mock_container.logs.return_value = iter([b"test output\n"])
            mock_container.attrs = {"State": {"ExitCode": 0}}
            mock_container.short_id = "abc123"
            mock_container.id = "abc123def456"
            mock_client.images.get.return_value = True
            mock_client.containers.run.return_value = mock_container
            mock_get_client.return_value = mock_client

            try:
                await adapter.run(
                    image="alpine:latest",
                    command=["echo", "hello"],
                    volumes={},
                    environment={},
                    timeout=10,
                )
            except Exception:
                pass  # Ignore execution errors, we're testing instrumentation

            # Check that a span was created
            spans = in_memory_exporter.get_finished_spans()
            assert any(span.name == "container.run" for span in spans), \
                f"Expected 'container.run' span, but got: {[s.name for s in spans]}"

            # Check span attributes
            run_span = next(s for s in spans if s.name == "container.run")
            assert run_span.attributes.get("service") == "docker_container_adapter"
            assert run_span.attributes.get("operation") == "run"

    @pytest.mark.asyncio
    async def test_create_method_creates_span(self, docker_config, tracer_provider, in_memory_exporter):
        """Test that create() method creates a container.create span."""
        adapter = DockerContainerAdapter(docker_config)

        with patch.object(adapter, '_get_client') as mock_get_client:
            mock_client = MagicMock()
            mock_container = MagicMock()
            mock_container.id = "test_container_id"
            mock_client.images.get.return_value = True
            mock_client.containers.create.return_value = mock_container
            mock_get_client.return_value = mock_client

            try:
                await adapter.create(
                    image="alpine:latest",
                    name="test_container",
                )
            except Exception:
                pass

            spans = in_memory_exporter.get_finished_spans()
            assert any(span.name == "container.create" for span in spans)

    @pytest.mark.asyncio
    async def test_start_method_creates_span(self, docker_config, tracer_provider, in_memory_exporter):
        """Test that start() method creates a container.start span."""
        adapter = DockerContainerAdapter(docker_config)

        with patch.object(adapter, '_get_client') as mock_get_client:
            mock_client = MagicMock()
            mock_container = MagicMock()
            mock_client.containers.get.return_value = mock_container
            mock_get_client.return_value = mock_client

            try:
                await adapter.start("test_container_id")
            except Exception:
                pass

            spans = in_memory_exporter.get_finished_spans()
            assert any(span.name == "container.start" for span in spans)

            start_span = next(s for s in spans if s.name == "container.start")
            assert start_span.attributes.get("operation") == "start"

    @pytest.mark.asyncio
    async def test_stop_method_creates_span(self, docker_config, tracer_provider, in_memory_exporter):
        """Test that stop() method creates a container.stop span."""
        adapter = DockerContainerAdapter(docker_config)

        with patch.object(adapter, '_get_client') as mock_get_client:
            mock_client = MagicMock()
            mock_container = MagicMock()
            mock_client.containers.get.return_value = mock_container
            mock_get_client.return_value = mock_client

            try:
                await adapter.stop("test_container_id")
            except Exception:
                pass

            spans = in_memory_exporter.get_finished_spans()
            assert any(span.name == "container.stop" for span in spans)

    @pytest.mark.asyncio
    async def test_kill_method_creates_span(self, docker_config, tracer_provider, in_memory_exporter):
        """Test that kill() method creates a container.kill span."""
        adapter = DockerContainerAdapter(docker_config)

        with patch.object(adapter, '_get_client') as mock_get_client:
            mock_client = MagicMock()
            mock_container = MagicMock()
            mock_client.containers.get.return_value = mock_container
            mock_get_client.return_value = mock_client

            try:
                await adapter.kill("test_container_id")
            except Exception:
                pass

            spans = in_memory_exporter.get_finished_spans()
            assert any(span.name == "container.kill" for span in spans)

    @pytest.mark.asyncio
    async def test_remove_method_creates_span(self, docker_config, tracer_provider, in_memory_exporter):
        """Test that remove() method creates a container.remove span."""
        adapter = DockerContainerAdapter(docker_config)

        with patch.object(adapter, '_get_client') as mock_get_client:
            mock_client = MagicMock()
            mock_container = MagicMock()
            mock_client.containers.get.return_value = mock_container
            mock_get_client.return_value = mock_client

            try:
                await adapter.remove("test_container_id")
            except Exception:
                pass

            spans = in_memory_exporter.get_finished_spans()
            assert any(span.name == "container.remove" for span in spans)


class TestDockerContainerRecoveryAdapterInstrumentation:
    """Test instrumentation of DockerContainerRecoveryAdapter methods."""

    @pytest.mark.asyncio
    async def test_get_running_agent_containers_creates_span(
        self, tracer_provider, in_memory_exporter
    ):
        """Test that get_running_agent_containers() creates proper span."""
        mock_recovery_service = MagicMock()
        mock_storage = AsyncMock()

        adapter = DockerContainerRecoveryAdapter(mock_recovery_service, mock_storage)

        with patch.object(adapter, '_get_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.containers.list.return_value = []
            mock_get_client.return_value = mock_client

            try:
                await adapter.get_running_agent_containers()
            except Exception:
                pass

            spans = in_memory_exporter.get_finished_spans()
            assert any(
                span.name == "container_recovery.get_running_agent_containers"
                for span in spans
            )

    @pytest.mark.asyncio
    async def test_assess_container_creates_span(
        self, tracer_provider, in_memory_exporter
    ):
        """Test that assess_container() creates proper span."""
        mock_recovery_service = MagicMock()
        mock_storage = AsyncMock()
        mock_storage.load_state = AsyncMock(return_value=None)

        adapter = DockerContainerRecoveryAdapter(mock_recovery_service, mock_storage)

        metadata = ContainerMetadata(
            container_id=ContainerId("test_id"),
            container_type="agent",
            created_at=None,
            project="test_project",
            agent="test_agent",
            task_id="test_task",
            work_item_id="test_work_item",
            pipeline_run_id=None,
            execution_id="test_execution",
        )

        with patch.object(adapter, '_get_client') as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            try:
                await adapter.assess_container(metadata)
            except Exception:
                pass

            spans = in_memory_exporter.get_finished_spans()
            assert any(
                span.name == "container_recovery.assess_container"
                for span in spans
            )


class TestContainerRecoveryServiceInstrumentation:
    """Test instrumentation of ContainerRecoveryService methods."""

    @pytest.mark.asyncio
    async def test_recover_or_cleanup_containers_creates_span(
        self, tracer_provider, in_memory_exporter
    ):
        """Test that recover_or_cleanup_containers() creates proper span."""
        mock_recovery_adapter = AsyncMock()
        mock_recovery_adapter.process_orphaned_repair_results = AsyncMock(return_value=0)
        mock_recovery_adapter.get_running_repair_cycle_containers = AsyncMock(
            return_value=[]
        )
        mock_recovery_adapter.get_running_agent_containers = AsyncMock(
            return_value=[]
        )
        mock_recovery_adapter.assess_container = AsyncMock()
        mock_recovery_adapter.assess_repair_cycle_container = AsyncMock()
        mock_recovery_adapter.execute_recovery_action = AsyncMock()

        mock_state_tracker = MagicMock()
        mock_storage = AsyncMock()
        mock_event_emitter = AsyncMock()

        service = ContainerRecoveryService(
            container_recovery_service=mock_recovery_adapter,
            work_execution_state_tracker=mock_state_tracker,
            storage=mock_storage,
            event_emitter=mock_event_emitter,
        )

        try:
            await service.recover_or_cleanup_containers()
        except Exception:
            pass

        spans = in_memory_exporter.get_finished_spans()
        assert any(
            span.name == "container_recovery.recover_or_cleanup_containers"
            for span in spans
        ), f"Expected span not found. Spans: {[s.name for s in spans]}"

        recovery_span = next(
            (s for s in spans if s.name == "container_recovery.recover_or_cleanup_containers"),
            None
        )
        assert recovery_span is not None
        assert recovery_span.attributes.get("service") == "container_recovery_service"
        assert recovery_span.attributes.get("operation") == "full_recovery_cycle"
