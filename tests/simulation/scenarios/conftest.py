"""Conftest for simulation scenario tests.

Seeds standard agents into InMemoryAgentRepository so repair cycle
adapter can resolve agent names without a full scenario seed.
"""

import pytest

from codetoreum.domain.agent import Agent, AgentCapability, AgentType
from codetoreum.infrastructure.simulation.bootstrap import SimulationApplicationBootstrap

_STANDARD_AGENTS = [
    ("senior_software_engineer", AgentType.DEVELOPER, "Implements features and applies repair cycle code fixes"),
    ("qa_engineer", AgentType.TESTER, "Runs tests; drives repair cycle test_execution and env_verification"),
    ("devops_engineer", AgentType.DEVOPS, "Rebuilds Docker environment during repair cycle env_rebuild sub-task"),
    ("code_reviewer", AgentType.REVIEWER, "Reviews code quality; routes failures back to Development"),
]


@pytest.fixture(autouse=True)
async def seed_standard_agents(
    simulation_bootstrap: SimulationApplicationBootstrap,
) -> None:
    """Seed standard agents into the InMemoryAgentRepository.

    Required so MockRepairCycleAdapter._resolve_and_record_agent() can
    look up agents by name without a full scenario YAML seed.
    """
    agent_repo = simulation_bootstrap.adapters.agent_repository
    for name, agent_type, description in _STANDARD_AGENTS:
        agent = Agent.create(
            name=name,
            display_name=name.replace("_", " ").title(),
            agent_type=agent_type,
            role_description=description,
            model="claude-sonnet-4-6",
            capabilities={"general": AgentCapability(skill="general", proficiency=1.0)},
        )
        await agent_repo.save(agent)
