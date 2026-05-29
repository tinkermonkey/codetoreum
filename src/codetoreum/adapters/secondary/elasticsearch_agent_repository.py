"""ElasticsearchAgentRepository — persistence-grade IAgentRepository.

Replaces ``InMemoryAgentRepository`` for production.  The in-memory
implementation lost every registered agent on server restart, forcing
operators to re-run ``register_project.py`` and the full bootstrap
loader each time.  This adapter stores agents in Elasticsearch (via
``ElasticsearchConfigStorage.save_agent_config`` and ``list_agents``)
so the agent catalog survives restart and is the same one served to
multi-instance deployments.

Design notes
------------
- The in-memory cache mirrors what ``InMemoryAgentRepository`` exposed
  via ``get_all_sync`` / ``get_by_name_sync`` (relied on by
  ``AdapterResolver._create_agent_llm_factory`` and
  ``ProductionApplicationBootstrap._create_ports`` line ~924).  The
  cache is populated three ways:
    1. Eagerly on ``save()`` — every persisted agent is added.
    2. Eagerly on first async lookup miss — the agent is fetched from
       ES and cached.
    3. Refreshed when the per-project / global TTL expires (default
       300s); subsequent reads re-hydrate from ES.
- INV-11: no retry/circuit-breaker logic embedded — wrap the inner
  ``ElasticsearchConfigStorage`` with the resilience decorators if
  desired.
- INV-09: explicit inheritance from ``IAgentRepository``.
- INV-12: this adapter lives in ``adapters/secondary`` so the domain
  layer remains import-free of Elasticsearch.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from codetoreum.domain.agent import Agent, AgentCapability, AgentType, CommitPolicy
from codetoreum.ports.exceptions import ResourceNotFoundError
from codetoreum.ports.output.agent_repository import IAgentRepository
from codetoreum.ports.output.config_store import AgentConfig, ConfigNotFoundError

if TYPE_CHECKING:
    from codetoreum.adapters.secondary.elasticsearch_config_storage import ElasticsearchConfigStorage

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_TTL_SECONDS = 300  # 5 minutes


class ElasticsearchAgentRepository(IAgentRepository):
    """Read-through cache on ElasticsearchConfigStorage for Agent domain objects.

    The repository accepts a configured ``ElasticsearchConfigStorage`` (the
    same instance used by ``IConfigStore``) and exposes the
    ``IAgentRepository`` surface on top of its ``save_agent_config`` /
    ``get_agent_config`` / ``list_agents`` methods.

    Cache semantics
    ---------------
    - ``get_all_sync`` / ``get_by_name_sync`` read from the local cache
      only.  They never touch ES.  The cache is populated by ``save()``
      and by async fetches, so any code path that has gone through one
      of those before calling the sync accessor sees the agent.
    - Async accessors check the cache first; on miss they call ES,
      cache the result, and return it.
    - Each cache entry tracks insertion time; entries older than
      ``cache_ttl_seconds`` are treated as missing on next async lookup.
    """

    def __init__(
        self,
        config_storage: ElasticsearchConfigStorage,
        cache_ttl_seconds: int = _DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        """Initialize the adapter.

        Args:
            config_storage: Backing ``ElasticsearchConfigStorage`` instance.
            cache_ttl_seconds: How long cached agents are considered fresh.
                Defaults to 300s (5 minutes).
        """
        self._config = config_storage
        self._cache_ttl_seconds = cache_ttl_seconds
        self._agents_by_id: dict[str, Agent] = {}
        self._agents_by_name: dict[str, Agent] = {}
        self._project_agents: dict[str, set[str]] = {}
        self._inserted_at: dict[str, float] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # IAgentRepository
    # ------------------------------------------------------------------

    async def get_by_id(self, agent_id: str) -> Agent:
        """Get agent by ID."""
        cached = self._cached_by_id(agent_id)
        if cached is not None:
            return cached
        # ES is project- and name-keyed (not id-keyed), so the only way to
        # hydrate by id without an exhaustive scan is to walk every
        # project's agents.  In practice agent.id == agent.name in the
        # bootstrap loader, so fall through to name lookup.
        try:
            return await self.get_by_name(agent_id)
        except ResourceNotFoundError as e:
            raise ResourceNotFoundError("Agent", agent_id) from e

    async def get_by_name(self, name: str) -> Agent:
        """Get agent by name; refreshes from ES on cache miss / stale."""
        cached = self._cached_by_name(name)
        if cached is not None:
            return cached

        # Scan persisted projects until we find a matching agent.
        try:
            projects = await self._config.list_projects()
        except Exception as e:
            logger.error(
                f"Failed to list projects while looking up agent '{name}': {e}",
                exc_info=True,
            )
            raise

        for project in projects:
            try:
                cfg = await self._config.get_agent_config(project.id, name)
            except ConfigNotFoundError:
                continue
            except Exception as e:
                logger.error(
                    f"Failed to fetch agent config project_id={project.id} name={name}: {e}",
                    exc_info=True,
                )
                raise
            agent = _agent_from_config(cfg)
            self._cache_put(agent, project_id=project.id)
            return agent

        raise ResourceNotFoundError("Agent", name)

    async def save(self, agent: Agent, project_id: str | None = None) -> None:
        """Persist an agent to Elasticsearch and refresh the cache."""
        if project_id is None:
            msg = "ElasticsearchAgentRepository.save requires a project_id"
            raise ValueError(msg)

        cfg = _agent_to_config(agent, project_id)
        try:
            await self._config.save_agent_config(cfg)
        except Exception as e:
            logger.error(
                f"Failed to persist agent '{agent.name}' to ES: {e}",
                exc_info=True,
            )
            raise
        self._cache_put(agent, project_id=project_id)

    async def list_by_project(self, project_id: str) -> list[Agent]:
        """List all agents for a project (re-fetched from ES)."""
        try:
            configs = await self._config.list_agents(project_id)
        except Exception as e:
            logger.error(
                f"Failed to list agents for project '{project_id}': {e}",
                exc_info=True,
            )
            raise
        agents = [_agent_from_config(c) for c in configs]
        for a in agents:
            self._cache_put(a, project_id=project_id)
        return agents

    async def get_all(self) -> list[Agent]:
        """Get all agents across all projects (re-fetched from ES)."""
        try:
            projects = await self._config.list_projects()
        except Exception as e:
            logger.error(
                f"Failed to list projects while fetching all agents: {e}",
                exc_info=True,
            )
            raise

        out: list[Agent] = []
        seen_ids: set[str] = set()
        for project in projects:
            for agent in await self.list_by_project(project.id):
                if agent.id in seen_ids:
                    continue
                seen_ids.add(agent.id)
                out.append(agent)
        return out

    # ------------------------------------------------------------------
    # Sync helpers (used by resolver._create_agent_llm_factory and Phase 6)
    # ------------------------------------------------------------------

    def get_all_sync(self) -> list[Agent]:
        """Return cached agents synchronously.

        This mirrors ``InMemoryAgentRepository.get_all_sync``.  It only
        ever returns what has been cached so far — populate the cache
        via ``save()`` (called by the bootstrap loader) or by an async
        accessor before relying on the sync view.
        """
        with self._lock:
            self._evict_stale()
            return list(self._agents_by_id.values())

    def get_by_name_sync(self, name: str) -> Agent:
        """Get agent by name from the local cache only.

        Raises:
            ResourceNotFoundError: If the agent is not in the cache.
        """
        cached = self._cached_by_name(name)
        if cached is None:
            raise ResourceNotFoundError("Agent", name)
        return cached

    async def save_for_project(self, project_id: str, agent: Agent) -> None:
        """Compatibility helper mirroring InMemoryAgentRepository."""
        await self.save(agent, project_id)

    # ------------------------------------------------------------------
    # Cache plumbing
    # ------------------------------------------------------------------

    def _cache_put(self, agent: Agent, project_id: str) -> None:
        with self._lock:
            self._agents_by_id[agent.id] = agent
            self._agents_by_name[agent.name] = agent
            self._project_agents.setdefault(project_id, set()).add(agent.id)
            self._inserted_at[agent.id] = time.monotonic()

    def _cached_by_id(self, agent_id: str) -> Agent | None:
        with self._lock:
            self._evict_stale()
            return self._agents_by_id.get(agent_id)

    def _cached_by_name(self, name: str) -> Agent | None:
        with self._lock:
            self._evict_stale()
            return self._agents_by_name.get(name)

    def _evict_stale(self) -> None:
        """Drop cache entries older than the TTL.  Caller must hold _lock."""
        if self._cache_ttl_seconds <= 0:
            return
        now = time.monotonic()
        stale_ids = [aid for aid, inserted in self._inserted_at.items() if now - inserted > self._cache_ttl_seconds]
        for aid in stale_ids:
            agent = self._agents_by_id.pop(aid, None)
            if agent is not None:
                self._agents_by_name.pop(agent.name, None)
            self._inserted_at.pop(aid, None)
            for ids in self._project_agents.values():
                ids.discard(aid)


# ----------------------------------------------------------------------
# Agent <-> AgentConfig translation
# ----------------------------------------------------------------------


_DEFAULT_CAPABILITY = "code_generation"


def _agent_to_config(agent: Agent, project_id: str) -> AgentConfig:
    """Convert a domain Agent to a persistable AgentConfig.

    AgentConfig is the wire-level representation used by
    ``ElasticsearchConfigStorage``; not every field of the rich Agent
    aggregate round-trips through it.  The fields that do not survive
    the round trip (capabilities are reduced to skill names, display
    name / role description / temperature / max_tokens / system_prompt
    / commit_policy / type) are stored in ``metadata`` so we can
    reconstruct the Agent on read.
    """
    metadata = dict(agent.metadata)
    metadata.update(
        {
            "id": agent.id,
            "display_name": agent.display_name,
            "agent_type": agent.agent_type.value if hasattr(agent.agent_type, "value") else str(agent.agent_type),
            "role_description": agent.role_description,
            "temperature": str(agent.temperature),
            "max_tokens": str(agent.max_tokens),
            "system_prompt": agent.system_prompt,
            "commit_policy": (
                agent.commit_policy.value if hasattr(agent.commit_policy, "value") else str(agent.commit_policy)
            ),
            "max_retries": str(agent.max_retries),
            "requires_dev_container": str(agent.requires_dev_container),
            "filesystem_write_allowed": str(agent.filesystem_write_allowed),
        }
    )
    # Capability proficiency + descriptions stored alongside skill names.
    metadata["capability_proficiency"] = ";".join(f"{c.skill}={c.proficiency}" for c in agent.capabilities.values())
    metadata["capability_descriptions"] = ";".join(
        f"{c.skill}={c.description or ''}" for c in agent.capabilities.values()
    )

    return AgentConfig(
        project_id=project_id,
        agent_name=agent.name,
        model=agent.model,
        timeout=agent.timeout_seconds,
        requires_docker=agent.requires_docker,
        makes_code_changes=agent.makes_code_changes,
        mcp_servers=tuple(agent.mcp_servers),
        capabilities=tuple(agent.capabilities.keys()),
        version=1,
        metadata=metadata,
    )


def _agent_from_config(cfg: AgentConfig) -> Agent:
    """Reverse of ``_agent_to_config``.

    Reads metadata fields written by ``_agent_to_config`` and falls
    back to safe defaults when persisted by a non-Codetoreum writer
    (e.g. the future admin UI may save a minimal AgentConfig with no
    metadata at all).
    """
    metadata = dict(cfg.metadata) if cfg.metadata is not None else {}
    proficiency_map: dict[str, float] = {}
    description_map: dict[str, str] = {}
    raw_prof = metadata.pop("capability_proficiency", "")
    for token in str(raw_prof).split(";"):
        if "=" in token:
            skill, value = token.split("=", 1)
            try:
                proficiency_map[skill.strip()] = float(value)
            except ValueError:
                continue
    raw_desc = metadata.pop("capability_descriptions", "")
    for token in str(raw_desc).split(";"):
        if "=" in token:
            skill, value = token.split("=", 1)
            description_map[skill.strip()] = value or None  # type: ignore[assignment]

    capabilities: dict[str, AgentCapability] = {}
    for skill in cfg.capabilities or (_DEFAULT_CAPABILITY,):
        capabilities[skill] = AgentCapability(
            skill=skill,
            proficiency=proficiency_map.get(skill, 1.0),
            description=description_map.get(skill),
        )

    try:
        agent_type = AgentType(metadata.pop("agent_type", AgentType.MAKER.value))
    except ValueError:
        agent_type = AgentType.MAKER

    try:
        commit_policy = CommitPolicy(metadata.pop("commit_policy", CommitPolicy.ON_SUCCESS.value))
    except ValueError:
        commit_policy = CommitPolicy.ON_SUCCESS

    now = cfg.updated_at or cfg.created_at or datetime.now(UTC)
    created_at = cfg.created_at or now

    return Agent(
        id=metadata.pop("id", cfg.agent_name),
        name=cfg.agent_name,
        display_name=metadata.pop("display_name", cfg.agent_name),
        agent_type=agent_type,
        capabilities=capabilities,
        role_description=metadata.pop("role_description", ""),
        model=cfg.model,
        timeout_seconds=cfg.timeout,
        max_retries=int(metadata.pop("max_retries", "3") or 3),
        requires_docker=cfg.requires_docker,
        requires_dev_container=_to_bool(metadata.pop("requires_dev_container", "False")),
        makes_code_changes=cfg.makes_code_changes,
        filesystem_write_allowed=_to_bool(metadata.pop("filesystem_write_allowed", "True")),
        mcp_servers=list(cfg.mcp_servers),
        metadata=metadata,
        created_at=created_at,
        updated_at=now,
        temperature=float(metadata.pop("temperature", "0.7") or 0.7),
        max_tokens=int(metadata.pop("max_tokens", "4096") or 4096),
        system_prompt=metadata.pop("system_prompt", ""),
        commit_policy=commit_policy,
    )


def _to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return bool(value)
