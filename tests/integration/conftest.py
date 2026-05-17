"""Common test fixtures and utilities for integration tests."""

import os

import pytest
from elasticsearch import AsyncElasticsearch

from tests.conftest import ModernElasticsearchContainer, docker_available

# Set default timeout for all integration tests to prevent hanging
pytestmark = pytest.mark.timeout(30)


@pytest.fixture(scope="module")
def elasticsearch_container():
    """Start an Elasticsearch 8.17.0 container for integration tests.

    Uses ModernElasticsearchContainer (testcontainers) so tests don't need
    a pre-running Elasticsearch instance. The container is shared across all
    tests in the module for efficiency.

    Sets ELASTICSEARCH_URL so CLIBootstrap and other components that read
    from the environment pick up the container's dynamic port.
    """
    container = ModernElasticsearchContainer("elasticsearch:8.17.0")
    container.with_env("ES_JAVA_OPTS", "-Xms512m -Xmx512m")
    container.start()

    url = container.get_url()
    old_url = os.environ.get("ELASTICSEARCH_URL")
    os.environ["ELASTICSEARCH_URL"] = url

    yield container

    if old_url is None:
        os.environ.pop("ELASTICSEARCH_URL", None)
    else:
        os.environ["ELASTICSEARCH_URL"] = old_url

    container.stop()


@pytest.fixture
async def elasticsearch_client(elasticsearch_container) -> AsyncElasticsearch:
    """Provide an AsyncElasticsearch client connected to the testcontainer.

    Depends on elasticsearch_container so the container is guaranteed to be
    running. Tests that use this fixture are automatically skipped when Docker
    is unavailable (via the docker_available marker on the container fixture).
    """
    url = elasticsearch_container.get_url()
    client = AsyncElasticsearch(
        [url],
        verify_certs=False,
        request_timeout=30,
    )
    try:
        info = await client.info()
        assert info is not None, "Failed to connect to Elasticsearch"
        yield client
    finally:
        await client.close()


@pytest.fixture
async def seeded_simulation_bootstrap(simulation_bootstrap, simulation_seeder):
    """
    Provide a simulation bootstrap with pre-seeded repair cycle agents.

    This fixture extends simulation_bootstrap by automatically seeding the
    agents required for repair cycle tests (senior_software_engineer, etc)
    and wiring the systemic analysis service to the repair cycle adapter.

    Yields:
        SimulationApplicationBootstrap instance with agents seeded and services wired
    """
    # Seed default project and agents required for repair cycles
    await simulation_seeder.create_project("repair-cycle-test")
    await simulation_seeder.create_agents(
        [
            {
                "name": "senior_software_engineer",
                "description": "Senior Software Engineer",
                "capabilities": ["code_generation", "testing", "debugging"],
                "agent_type": "maker",
            },
            {
                "name": "code_reviewer",
                "description": "Code Reviewer",
                "capabilities": ["review", "analysis"],
                "agent_type": "reviewer",
            },
        ]
    )

    # Wire systemic analysis service to repair cycle adapter for dispatch logic
    repair_cycle = simulation_bootstrap.adapters.repair_cycle_as_mock()
    repair_cycle.systemic_analysis_service = simulation_bootstrap.adapters.systemic_analysis_service

    return simulation_bootstrap
