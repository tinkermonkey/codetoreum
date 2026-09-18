"""
Regression tests for MockConfigQueryAdapter when backed by an IConfigStore.

Covers the cross-project aggregation paths (list_agents/list_pipelines with
project_id=None, and count_configs across all types) after the refactor from
reaching into InMemoryConfigStore's internal dict attributes to calling the
IConfigStore port's async methods (list_projects/list_agents/list_pipelines).
These paths introduced `await` inside loops (now `asyncio.gather`), so they
need direct coverage rather than relying on the single-project code path.
"""

from datetime import UTC, datetime

import pytest

from codetoreum.adapters.primary.input_port_adapters.mock.mock_config_query_adapter import (
    MockConfigQueryAdapter,
)
from codetoreum.adapters.testing.in_memory_config_store import InMemoryConfigStore
from codetoreum.domain.coding_agent_types import AgentInvocationConfig, InvocationMode
from codetoreum.ports.output.config_store import AgentConfig, PipelineConfig, ProjectConfig


def _invocation() -> AgentInvocationConfig:
    return AgentInvocationConfig(
        mode=InvocationMode.HOST,
        model="claude-sonnet-4-5",
        timeout_seconds=300,
    )


@pytest.fixture
async def seeded_store() -> InMemoryConfigStore:
    """A store with two projects, each with one agent and one pipeline."""
    store = InMemoryConfigStore()
    now = datetime.now(UTC)

    for i in (1, 2):
        await store.save_project_config(
            ProjectConfig(
                id=f"proj-{i}",
                name=f"project-{i}",
                github_org="test",
                github_repo=f"repo-{i}",
                created_at=now,
                updated_at=now,
            )
        )
        await store.save_agent_config(
            AgentConfig(
                project_id=f"proj-{i}",
                agent_name=f"agent-{i}",
                makes_code_changes=True,
                coding_agent="claude",
                invocation=_invocation(),
                created_at=now,
                updated_at=now,
            )
        )
        await store.save_pipeline_config(
            PipelineConfig(
                id=f"pipe-{i}",
                project_id=f"proj-{i}",
                name=f"pipeline-{i}",
                created_at=now,
                updated_at=now,
            )
        )

    return store


@pytest.mark.asyncio
async def test_list_agents_across_all_projects(seeded_store):
    adapter = MockConfigQueryAdapter(config_store=seeded_store)

    agents = await adapter.list_agents(project_id=None)

    assert {a.agent_name for a in agents} == {"agent-1", "agent-2"}


@pytest.mark.asyncio
async def test_list_pipelines_across_all_projects(seeded_store):
    adapter = MockConfigQueryAdapter(config_store=seeded_store)

    pipelines = await adapter.list_pipelines(project_id=None)

    assert {p.name for p in pipelines} == {"pipeline-1", "pipeline-2"}


@pytest.mark.asyncio
async def test_count_configs_across_all_types_and_projects(seeded_store):
    adapter = MockConfigQueryAdapter(config_store=seeded_store)

    assert await adapter.count_configs() == 6  # 2 projects + 2 agents + 2 pipelines
    assert await adapter.count_configs(config_type="project") == 2
    assert await adapter.count_configs(config_type="agent") == 2
    assert await adapter.count_configs(config_type="pipeline") == 2


@pytest.mark.asyncio
async def test_count_configs_scoped_to_single_project(seeded_store):
    adapter = MockConfigQueryAdapter(config_store=seeded_store)

    assert await adapter.count_configs(config_type="agent", project_id="proj-1") == 1
    assert await adapter.count_configs(config_type="pipeline", project_id="proj-1") == 1


@pytest.mark.asyncio
async def test_project_ids_from_store_requires_config_store():
    adapter = MockConfigQueryAdapter(config_store=None)

    with pytest.raises(ValueError):
        await adapter._project_ids_from_store()
