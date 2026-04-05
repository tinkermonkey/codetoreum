"""Common test fixtures and utilities for integration tests."""

import pytest

# Set default timeout for all integration tests to prevent hanging
pytestmark = pytest.mark.timeout(30)


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
    await simulation_seeder.create_agents([
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
    ])

    # Wire systemic analysis service to repair cycle adapter for dispatch logic
    repair_cycle = simulation_bootstrap.adapters.repair_cycle_as_mock()
    repair_cycle.systemic_analysis_service = simulation_bootstrap.adapters.systemic_analysis_service

    return simulation_bootstrap
