"""Test configuration and shared fixtures."""

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
