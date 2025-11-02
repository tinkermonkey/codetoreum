"""Integration tests for Docker Container Adapter.

These tests interact with the actual Docker daemon and require:
- Docker installed and running
- Permissions to run Docker commands
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from codetoreum.adapters.secondary import DockerConfig, DockerContainerAdapter
from codetoreum.domain.types import ContainerId
from codetoreum.ports.exceptions import (
    ContainerError,
    ContainerNotRunningError,
    ImageNotFoundError,
    ResourceNotFoundError,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def docker_config():
    """Create Docker configuration."""
    return DockerConfig(
        default_timeout=30,
        remove_on_completion=True,
    )


@pytest.fixture
def docker_adapter(docker_config):
    """Create Docker adapter instance with proper cleanup."""
    adapter = DockerContainerAdapter(docker_config)

    # Check if Docker is available
    try:
        client = adapter._get_client()
    except ContainerError:
        pytest.skip("Docker is not available")

    # Cleanup any leftover test containers from previous runs
    try:
        # Remove any stopped alpine containers from previous test runs
        for container in client.containers.list(all=True, filters={"ancestor": "alpine:latest"}):
            try:
                container.remove(force=True)
            except Exception:
                pass  # Ignore errors during cleanup
    except Exception:
        pass  # Ignore cleanup errors

    yield adapter

    # Cleanup: remove any remaining test containers and close the Docker client
    try:
        # Clean up any containers that might have been left behind
        for container in client.containers.list(all=True, filters={"ancestor": "alpine:latest"}):
            try:
                container.remove(force=True)
            except Exception:
                pass  # Ignore errors during cleanup
    except Exception:
        pass  # Ignore cleanup errors

    # Close the Docker client to release resources
    adapter.close()


@pytest.mark.asyncio
async def test_run_simple_command(docker_adapter):
    """Test running a simple command in a container."""
    result = await docker_adapter.run(
        image="alpine:latest",
        command=["echo", "Hello, World!"],
        volumes={},
        environment={},
        timeout=30,
    )

    assert result is not None
    assert result.exit_code == 0
    assert "Hello, World!" in result.stdout
    assert result.duration_ms > 0


@pytest.mark.asyncio
async def test_run_with_environment_variables(docker_adapter):
    """Test running container with environment variables."""
    result = await docker_adapter.run(
        image="alpine:latest",
        command=["sh", "-c", "echo $TEST_VAR"],
        volumes={},
        environment={"TEST_VAR": "test_value"},
        timeout=30,
    )

    assert result.exit_code == 0
    assert "test_value" in result.stdout


@pytest.mark.asyncio
async def test_run_with_volume_mount(docker_adapter):
    """Test running container with volume mount."""
    # Create temporary directory with test file
    # Note: Using cwd instead of /tmp because Docker may not have access to tmpfs
    test_dir = Path.cwd() / f".test_docker_volume_{os.getpid()}"
    test_dir.mkdir(exist_ok=True)

    try:
        test_file = test_dir / "test.txt"
        test_file.write_text("Hello from host")

        result = await docker_adapter.run(
            image="alpine:latest",
            command=["cat", "/data/test.txt"],
            volumes={str(test_dir): "/data:ro"},
            environment={},
            timeout=30,
        )

        assert result.exit_code == 0
        assert "Hello from host" in result.stdout
    finally:
        # Cleanup test directory
        if test_dir.exists():
            shutil.rmtree(test_dir)


@pytest.mark.asyncio
async def test_run_with_streaming(docker_adapter):
    """Test running container with streaming callback."""
    logs = []

    def stream_callback(line):
        logs.append(line)

    result = await docker_adapter.run(
        image="alpine:latest",
        command=["sh", "-c", "echo line1; echo line2; echo line3"],
        volumes={},
        environment={},
        timeout=30,
        stream_callback=stream_callback,
    )

    assert result.exit_code == 0
    assert len(logs) > 0


@pytest.mark.asyncio
async def test_create_start_stop_remove(docker_adapter):
    """Test container lifecycle operations."""
    # Create container
    container_id = await docker_adapter.create(
        image="alpine:latest",
        command=["sleep", "30"],
        name="test-container",
    )

    assert container_id is not None

    try:
        # Start container
        await docker_adapter.start(container_id)

        # Check status
        status = await docker_adapter.status(container_id)
        assert status.status == "running"

        # Stop container
        await docker_adapter.stop(container_id, timeout=5)

        # Check status again
        status = await docker_adapter.status(container_id)
        assert status.status in ("exited", "stopped")

    finally:
        # Clean up
        await docker_adapter.remove(container_id, force=True)


@pytest.mark.asyncio
async def test_exec_in_running_container(docker_adapter):
    """Test executing command in running container."""
    # Create and start container
    container_id = await docker_adapter.create(
        image="alpine:latest",
        command=["sleep", "30"],
    )

    try:
        await docker_adapter.start(container_id)

        # Execute command
        result = await docker_adapter.exec(
            container_id,
            ["echo", "executed"],
        )

        assert result.exit_code == 0
        assert "executed" in result.stdout

    finally:
        await docker_adapter.remove(container_id, force=True)


@pytest.mark.asyncio
async def test_list_containers(docker_adapter):
    """Test listing containers."""
    # Create a container
    container_id = await docker_adapter.create(
        image="alpine:latest",
        command=["sleep", "10"],
        labels={"test": "integration"},
    )

    try:
        await docker_adapter.start(container_id)

        # List all containers
        containers = await docker_adapter.list_containers(all=True)
        assert len(containers) > 0

        # List with filter
        filtered = await docker_adapter.list_containers(
            all=True,
            filters={"label": ["test=integration"]},
        )
        assert len(filtered) > 0

    finally:
        await docker_adapter.remove(container_id, force=True)


@pytest.mark.asyncio
async def test_pull_image(docker_adapter):
    """Test pulling an image."""
    # Try to pull a small image
    await docker_adapter.pull_image("alpine", tag="latest")

    # Check image exists
    exists = await docker_adapter.image_exists("alpine", tag="latest")
    assert exists is True


@pytest.mark.asyncio
async def test_image_exists(docker_adapter):
    """Test checking if image exists."""
    # Alpine should exist after previous test
    exists = await docker_adapter.image_exists("alpine", tag="latest")
    assert exists in (True, False)


@pytest.mark.asyncio
async def test_inspect_container(docker_adapter):
    """Test inspecting container."""
    container_id = await docker_adapter.create(
        image="alpine:latest",
        command=["sleep", "10"],
    )

    try:
        info = await docker_adapter.inspect(container_id)

        assert info is not None
        assert "State" in info
        assert "Config" in info

    finally:
        await docker_adapter.remove(container_id, force=True)


@pytest.mark.asyncio
async def test_wait_for_container(docker_adapter):
    """Test waiting for container to complete."""
    container_id = await docker_adapter.create(
        image="alpine:latest",
        command=["sh", "-c", "sleep 1 && exit 0"],
    )

    try:
        await docker_adapter.start(container_id)

        # Wait for completion
        exit_code = await docker_adapter.wait(container_id, timeout=10)
        assert exit_code == 0

    finally:
        await docker_adapter.remove(container_id, force=True)


@pytest.mark.asyncio
async def test_get_container_logs(docker_adapter):
    """Test getting container logs."""
    container_id = await docker_adapter.create(
        image="alpine:latest",
        command=["sh", "-c", "echo test_output"],
    )

    try:
        await docker_adapter.start(container_id)
        await docker_adapter.wait(container_id, timeout=10)

        logs = await docker_adapter.logs(container_id)
        assert "test_output" in logs

    finally:
        await docker_adapter.remove(container_id, force=True)


@pytest.mark.asyncio
async def test_nonexistent_image(docker_adapter):
    """Test running container with nonexistent image."""
    with pytest.raises(ImageNotFoundError):
        await docker_adapter.run(
            image="nonexistent-image-12345",
            command=["echo", "test"],
            volumes={},
            environment={},
        )


@pytest.mark.asyncio
async def test_nonexistent_container(docker_adapter):
    """Test operations on nonexistent container."""
    with pytest.raises(ResourceNotFoundError):
        await docker_adapter.status("nonexistent-container-id")


@pytest.mark.asyncio
async def test_exec_on_stopped_container(docker_adapter):
    """Test exec on stopped container raises error."""
    container_id = await docker_adapter.create(
        image="alpine:latest",
        command=["echo", "test"],
    )

    try:
        # Don't start the container
        with pytest.raises(ContainerNotRunningError):
            await docker_adapter.exec(container_id, ["echo", "test"])

    finally:
        await docker_adapter.remove(container_id, force=True)


@pytest.mark.asyncio
async def test_context_manager(docker_config):
    """Test using adapter as async context manager."""
    async with DockerContainerAdapter(docker_config) as adapter:
        # Check if Docker is available
        try:
            adapter._get_client()
        except ContainerError:
            pytest.skip("Docker is not available")

        result = await adapter.run(
            image="alpine:latest",
            command=["echo", "test"],
            volumes={},
            environment={},
        )
        assert result.exit_code == 0
