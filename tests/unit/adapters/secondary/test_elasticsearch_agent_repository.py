"""Unit tests for ElasticsearchAgentRepository using a mocked ES backend.

These tests do NOT spin up Elasticsearch.  They mock the
``ElasticsearchConfigStorage`` surface so the adapter's caching,
fallback-to-ES, and Agent <-> AgentConfig translation are validated in
isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

import pytest

from codetoreum.adapters.secondary.elasticsearch_agent_repository import (
    ElasticsearchAgentRepository,
    _agent_from_config,
    _agent_to_config,
)
from codetoreum.domain.agent import Agent, AgentCapability, AgentType
from codetoreum.domain.coding_agent_types import AgentInvocationConfig, InvocationMode
from codetoreum.domain.value_objects import CommitPolicy
from codetoreum.ports.exceptions import ResourceNotFoundError
from codetoreum.ports.output.config_store import AgentConfig, ConfigNotFoundError, ProjectConfig


def _test_inv(
    model: str = "claude-sonnet-4-5",
    timeout_seconds: int = 300,
    requires_docker: bool = True,
) -> AgentInvocationConfig:
    """Build an AgentInvocationConfig for tests (DEF-020 transitional helper)."""
    return AgentInvocationConfig(
        mode=InvocationMode.CONTAINERIZED if requires_docker else InvocationMode.HOST,
        model=model,
        timeout_seconds=timeout_seconds,
        mode_config={"image": "codetoreum-agent:latest"} if requires_docker else {},
    )


class _FakeConfigStore:
    """Minimal stand-in for ElasticsearchConfigStorage."""

    def __init__(self) -> None:
        self.agents: dict[tuple[str, str], AgentConfig] = {}
        self.projects: list[ProjectConfig] = []

    async def save_agent_config(self, config: AgentConfig) -> None:
        self.agents[(config.project_id, config.agent_name)] = config

    async def get_agent_config(self, project_id: str, agent_name: str) -> AgentConfig:
        try:
            return self.agents[(project_id, agent_name)]
        except KeyError:
            raise ConfigNotFoundError(f"{project_id}/{agent_name}")

    async def list_agents(self, project_id: str) -> list[AgentConfig]:
        return [a for (p, _name), a in self.agents.items() if p == project_id]

    async def list_projects(self) -> list[ProjectConfig]:
        return list(self.projects)


def _make_agent(name: str = "claude-code-agent") -> Agent:
    now = datetime.now(UTC)
    return Agent(
        id=name,
        name=name,
        display_name=f"Display {name}",
        agent_type=AgentType.MAKER,
        capabilities={
            "code_generation": AgentCapability(skill="code_generation", proficiency=0.9, description="Generates code")
        },
        role_description="Implements features",
        max_retries=2,
        requires_dev_container=False,
        makes_code_changes=True,
        filesystem_write_allowed=True,
        mcp_servers=[],
        metadata={"custom_tag": "alpha"},
        created_at=now,
        updated_at=now,
        temperature=0.5,
        max_tokens=8192,
        system_prompt="You are a helpful agent.",
        commit_policy=CommitPolicy.ON_SUCCESS,
        invocation=_test_inv(model="claude-sonnet-4-6", timeout_seconds=600, requires_docker=True),
        coding_agent="",
    )


@pytest.fixture
def store() -> _FakeConfigStore:
    return _FakeConfigStore()


@pytest.fixture
def repo(store: _FakeConfigStore) -> ElasticsearchAgentRepository:
    return ElasticsearchAgentRepository(config_storage=store, cache_ttl_seconds=60)  # type: ignore[arg-type]


class TestAgentConfigRoundTrip:
    def test_agent_round_trip_preserves_core_fields(self) -> None:
        agent = _make_agent()
        cfg = _agent_to_config(agent, project_id="proj-1")
        restored = _agent_from_config(cfg)
        assert restored.name == agent.name
        assert restored.invocation.model == agent.invocation.model
        assert restored.invocation.timeout_seconds == agent.invocation.timeout_seconds
        assert restored.invocation.mode == InvocationMode.CONTAINERIZED
        assert restored.makes_code_changes is True
        assert restored.temperature == pytest.approx(0.5)
        assert restored.max_tokens == 8192
        assert restored.system_prompt == "You are a helpful agent."
        assert restored.commit_policy == CommitPolicy.ON_SUCCESS
        assert restored.agent_type == AgentType.MAKER
        assert restored.max_retries == 2
        assert "code_generation" in restored.capabilities
        cap = restored.capabilities["code_generation"]
        assert cap.proficiency == pytest.approx(0.9)
        assert cap.description == "Generates code"

    def test_agent_metadata_extras_survive_round_trip(self) -> None:
        agent = _make_agent()
        cfg = _agent_to_config(agent, project_id="proj-1")
        restored = _agent_from_config(cfg)
        # Custom metadata key was not consumed by translation; it remains.
        assert restored.metadata.get("custom_tag") == "alpha"


class TestElasticsearchAgentRepositorySave:
    @pytest.mark.asyncio
    async def test_save_persists_to_es_and_caches(
        self, repo: ElasticsearchAgentRepository, store: _FakeConfigStore
    ) -> None:
        agent = _make_agent()
        await repo.save(agent, project_id="proj-1")
        assert ("proj-1", agent.name) in store.agents
        # Cached, so sync access works without round-tripping.
        assert repo.get_by_name_sync(agent.name).name == agent.name
        assert [a.name for a in repo.get_all_sync()] == [agent.name]

    @pytest.mark.asyncio
    async def test_save_requires_project_id(self, repo: ElasticsearchAgentRepository) -> None:
        with pytest.raises(ValueError):
            await repo.save(_make_agent(), project_id=None)


class TestElasticsearchAgentRepositoryRead:
    @pytest.mark.asyncio
    async def test_get_by_name_hits_cache_after_save(self, repo: ElasticsearchAgentRepository) -> None:
        agent = _make_agent()
        await repo.save(agent, project_id="proj-1")
        result = await repo.get_by_name(agent.name)
        assert result.name == agent.name

    @pytest.mark.asyncio
    async def test_get_by_name_misses_cache_and_fetches_from_es(
        self,
        repo: ElasticsearchAgentRepository,
        store: _FakeConfigStore,
    ) -> None:
        # Pre-populate ES without using repo.save() so the cache is cold.
        agent = _make_agent("standalone-agent")
        cfg = _agent_to_config(agent, project_id="proj-9")
        await store.save_agent_config(cfg)
        store.projects = [
            ProjectConfig(
                id="proj-9",
                name="proj-9",
                github_org="o",
                github_repo="r",
            ),
        ]
        # Cold cache, fetched on demand.
        result = await repo.get_by_name(agent.name)
        assert result.name == agent.name
        # And now it's cached.
        assert repo.get_by_name_sync(agent.name).name == agent.name

    @pytest.mark.asyncio
    async def test_get_by_name_missing_raises_resource_not_found(
        self,
        repo: ElasticsearchAgentRepository,
        store: _FakeConfigStore,
    ) -> None:
        store.projects = [
            ProjectConfig(
                id="proj-x",
                name="proj-x",
                github_org="o",
                github_repo="r",
            ),
        ]
        with pytest.raises(ResourceNotFoundError):
            await repo.get_by_name("does-not-exist")

    @pytest.mark.asyncio
    async def test_list_by_project_returns_persisted_agents(
        self,
        repo: ElasticsearchAgentRepository,
    ) -> None:
        await repo.save(_make_agent("agent-1"), project_id="proj-1")
        await repo.save(_make_agent("agent-2"), project_id="proj-1")
        await repo.save(_make_agent("agent-3"), project_id="proj-2")
        agents = await repo.list_by_project("proj-1")
        assert sorted(a.name for a in agents) == ["agent-1", "agent-2"]

    @pytest.mark.asyncio
    async def test_get_all_walks_projects(self, repo: ElasticsearchAgentRepository, store: _FakeConfigStore) -> None:
        store.projects = [
            ProjectConfig(id="proj-1", name="p1", github_org="o", github_repo="r1"),
            ProjectConfig(id="proj-2", name="p2", github_org="o", github_repo="r2"),
        ]
        await repo.save(_make_agent("a1"), project_id="proj-1")
        await repo.save(_make_agent("a2"), project_id="proj-2")
        all_agents = await repo.get_all()
        assert sorted(a.name for a in all_agents) == ["a1", "a2"]


class TestSyncAccessors:
    @pytest.mark.asyncio
    async def test_get_by_name_sync_missing_raises(self, repo: ElasticsearchAgentRepository) -> None:
        with pytest.raises(ResourceNotFoundError):
            repo.get_by_name_sync("nope")

    @pytest.mark.asyncio
    async def test_get_all_sync_returns_only_cached(self, repo: ElasticsearchAgentRepository) -> None:
        assert repo.get_all_sync() == []
        await repo.save(_make_agent("a"), project_id="proj-1")
        assert [a.name for a in repo.get_all_sync()] == ["a"]
