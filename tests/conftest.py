"""Test configuration and shared fixtures."""

from typing import Generator

import docker
import pytest


def is_docker_available() -> bool:
    """Check if Docker is available and running.

    Returns:
        bool: True if Docker daemon is accessible, False otherwise
    """
    try:
        client = docker.from_env()
        try:
            client.ping()
            return True
        finally:
            client.close()
    except (docker.errors.DockerException, Exception):
        return False


# Create a global pytest marker for tests requiring Docker
docker_available = pytest.mark.skipif(
    not is_docker_available(),
    reason="Docker is not available or not running"
)


@pytest.fixture(scope="session")
def docker_client() -> Generator[docker.DockerClient, None, None]:
    """Shared Docker client for all tests in the session.

    This fixture creates a single Docker client that is reused across all tests
    in the session, reducing resource consumption and connection overhead.

    Yields:
        docker.DockerClient: Docker client instance
    """
    if not is_docker_available():
        pytest.skip("Docker is not available or not running")

    client = docker.from_env()
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def sample_work_item_data() -> dict[str, str]:
    """Sample work item data for testing.

    Returns:
        Dictionary containing sample work item data.
    """
    return {
        "id": "issue-1",
        "title": "Implement user authentication",
        "description": "Add OAuth2 authentication flow",
        "status": "pending",
    }


@pytest.fixture
def mock_event_store() -> dict[str, list[dict]]:
    """Mock event store for testing.

    Returns:
        Dictionary simulating an in-memory event store.
    """
    return {}
