"""
Mock Configuration Query Adapter

In-memory implementation of IConfigurationQueryPort for development and testing.

Supports optional backing store injection: when an InMemoryConfigStore is provided,
reads delegate to it (converting ProjectConfig -> ProjectConfigInfo on the fly).
When no backing store is provided (unit tests), the adapter uses its own internal
dictionaries.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from threading import RLock

from codetoreum.ports.input.config_query import (
    AgentConfigInfo,
    ConfigSearchResult,
    ConfigSearchResults,
    ConfigVersionInfo,
    IConfigurationQueryPort,
    PaginationParams,
    PipelineConfigInfo,
    ProjectConfigInfo,
)
from codetoreum.domain.exceptions import (
    AgentNotFoundError,
    PipelineNotFoundError,
    ConfigNotFoundError,
)

if TYPE_CHECKING:
    from codetoreum.adapters.testing.in_memory_config_store import InMemoryConfigStore


class MockConfigQueryAdapter(IConfigurationQueryPort):
    """
    Mock implementation of IConfigurationQueryPort using in-memory storage.

    When ``config_store`` is provided, query methods delegate to it and convert
    storage-layer objects (ProjectConfig, AgentConfig, PipelineConfig) into the
    corresponding port DTOs (ProjectConfigInfo, AgentConfigInfo, PipelineConfigInfo).
    This eliminates the need for dual-writes in simulation seeding.
    """

    def __init__(self, config_store: Optional["InMemoryConfigStore"] = None):
        self._config_store = config_store
        self._projects: Dict[str, ProjectConfigInfo] = {}
        self._projects_by_name: Dict[str, str] = {}  # name -> project_id
        self._agents: Dict[str, Dict[str, AgentConfigInfo]] = {}  # project_id -> {agent_name -> config}
        self._pipelines: Dict[str, Dict[str, PipelineConfigInfo]] = {}  # project_id -> {pipeline_name -> config}
        self._version_history: Dict[str, List[ConfigVersionInfo]] = {}  # config_id -> versions
        self._lock = RLock()

    # =========================================================================
    # Conversion helpers (storage-layer → port DTO)
    # =========================================================================

    @staticmethod
    def _project_config_to_info(cfg) -> ProjectConfigInfo:
        """Convert a storage-layer ProjectConfig to a port-layer ProjectConfigInfo."""
        return ProjectConfigInfo(
            id=cfg.id,
            name=cfg.name,
            description=cfg.metadata.get("description", ""),
            github_org=cfg.github_org,
            github_repo=cfg.github_repo,
            version=cfg.version,
            created_at=cfg.created_at or datetime.now(timezone.utc),
            updated_at=cfg.updated_at or datetime.now(timezone.utc),
            environment_variables={k: v for k, v in cfg.environment_variables.items()} if cfg.environment_variables else {},
            mounted_commands=list(cfg.mounted_commands.values()) if isinstance(cfg.mounted_commands, dict) else cfg.mounted_commands,
            mounted_subagents=list(cfg.mounted_subagents.values()) if isinstance(cfg.mounted_subagents, dict) else cfg.mounted_subagents,
            metadata=cfg.metadata,
        )

    @staticmethod
    def _agent_config_to_info(cfg) -> AgentConfigInfo:
        """Convert a storage-layer AgentConfig to a port-layer AgentConfigInfo."""
        return AgentConfigInfo(
            project_id=cfg.project_id,
            agent_name=cfg.agent_name,
            display_name=cfg.metadata.get("description", cfg.agent_name),
            model=cfg.model,
            timeout_seconds=cfg.timeout,
            max_retries=cfg.metadata.get("max_retries", 3),
            requires_docker=cfg.requires_docker,
            requires_dev_container=False,
            makes_code_changes=cfg.makes_code_changes,
            filesystem_write_allowed=True,
            version=cfg.version,
            created_at=cfg.created_at or datetime.now(timezone.utc),
            updated_at=cfg.updated_at or datetime.now(timezone.utc),
            mcp_servers=[{"name": s} for s in cfg.mcp_servers] if cfg.mcp_servers else [],
            capabilities={"capabilities": cfg.capabilities} if cfg.capabilities else {},
            metadata=cfg.metadata,
        )

    @staticmethod
    def _pipeline_config_to_info(cfg) -> PipelineConfigInfo:
        """Convert a storage-layer PipelineConfig to a port-layer PipelineConfigInfo."""
        return PipelineConfigInfo(
            id=cfg.id,
            project_id=cfg.project_id,
            name=cfg.name,
            description=cfg.metadata.get("description", ""),
            version=cfg.version,
            stages=cfg.stages,
            created_at=cfg.created_at or datetime.now(timezone.utc),
            updated_at=cfg.updated_at or datetime.now(timezone.utc),
            metadata=cfg.metadata,
        )

    # =========================================================================
    # Port interface methods
    # =========================================================================

    async def get_project_config(
        self, project_id: str, include_secrets: bool = False
    ) -> ProjectConfigInfo:
        """Get project configuration by ID."""
        if self._config_store:
            cfg = await self._config_store.get_project_config(project_id)
            return self._project_config_to_info(cfg)
        with self._lock:
            if project_id not in self._projects:
                raise ConfigNotFoundError(f"Project with ID {project_id} not found")
            return self._projects[project_id]

    async def get_project_config_by_name(
        self, project_name: str, include_secrets: bool = False
    ) -> ProjectConfigInfo:
        """Get project configuration by name."""
        if self._config_store:
            cfg = await self._config_store.get_project_config_by_name(project_name)
            return self._project_config_to_info(cfg)
        with self._lock:
            if project_name not in self._projects_by_name:
                raise ConfigNotFoundError(f"Project with name '{project_name}' not found")
            project_id = self._projects_by_name[project_name]
            return self._projects[project_id]

    async def get_agent_config(
        self, project_id: str, agent_name: str
    ) -> AgentConfigInfo:
        """Get agent configuration."""
        if self._config_store:
            cfg = await self._config_store.get_agent_config(project_id, agent_name)
            return self._agent_config_to_info(cfg)
        with self._lock:
            if project_id not in self._agents:
                raise ConfigNotFoundError(f"Project with ID {project_id} not found")
            if agent_name not in self._agents[project_id]:
                raise AgentNotFoundError(f"Agent '{agent_name}' not found in project")
            return self._agents[project_id][agent_name]

    async def get_pipeline_config(
        self, project_id: str, pipeline_name: str
    ) -> PipelineConfigInfo:
        """Get pipeline configuration."""
        if self._config_store:
            cfg = await self._config_store.get_pipeline_config(project_id, pipeline_name)
            return self._pipeline_config_to_info(cfg)
        with self._lock:
            if project_id not in self._pipelines:
                raise PipelineNotFoundError(f"Project with ID {project_id} not found")
            if pipeline_name not in self._pipelines[project_id]:
                raise PipelineNotFoundError(
                    f"Pipeline '{pipeline_name}' not found in project"
                )
            return self._pipelines[project_id][pipeline_name]

    async def list_projects(
        self, pagination: Optional[PaginationParams] = None
    ) -> List[ProjectConfigInfo]:
        """List all projects."""
        if self._config_store:
            configs = await self._config_store.list_projects()
            projects = [self._project_config_to_info(c) for c in configs]
            if pagination:
                projects = projects[pagination.offset : pagination.offset + pagination.limit]
            return projects
        with self._lock:
            projects = list(self._projects.values())

            if pagination:
                offset = pagination.offset
                limit = pagination.limit
                projects = projects[offset : offset + limit]

            return projects

    async def list_agents(
        self, project_id: Optional[str] = None, pagination: Optional[PaginationParams] = None
    ) -> List[AgentConfigInfo]:
        """List agents. When project_id is None, returns agents across all projects."""
        if self._config_store:
            if project_id is not None:
                agent_cfgs = await self._config_store.list_agents(project_id)
            else:
                # Gather agents across all projects
                agent_cfgs = []
                for pid in list(self._config_store.agents.keys()):
                    agent_cfgs.extend(await self._config_store.list_agents(pid))
            agents = [self._agent_config_to_info(c) for c in agent_cfgs]
            if pagination:
                agents = agents[pagination.offset : pagination.offset + pagination.limit]
            return agents
        with self._lock:
            if project_id is None:
                agents = [
                    agent
                    for project_agents in self._agents.values()
                    for agent in project_agents.values()
                ]
            else:
                if project_id not in self._agents:
                    return []
                agents = list(self._agents[project_id].values())

            if pagination:
                offset = pagination.offset
                limit = pagination.limit
                agents = agents[offset : offset + limit]

            return agents

    async def list_pipelines(
        self, project_id: Optional[str] = None, pagination: Optional[PaginationParams] = None
    ) -> List[PipelineConfigInfo]:
        """List pipelines. When project_id is None, returns pipelines across all projects."""
        if self._config_store:
            if project_id is not None:
                pipe_cfgs = await self._config_store.list_pipelines(project_id)
            else:
                pipe_cfgs = []
                for pid in list(self._config_store.pipelines.keys()):
                    pipe_cfgs.extend(await self._config_store.list_pipelines(pid))
            pipelines = [self._pipeline_config_to_info(c) for c in pipe_cfgs]
            if pagination:
                pipelines = pipelines[pagination.offset : pagination.offset + pagination.limit]
            return pipelines
        with self._lock:
            if project_id is None:
                pipelines = [
                    pipeline
                    for project_pipelines in self._pipelines.values()
                    for pipeline in project_pipelines.values()
                ]
            else:
                if project_id not in self._pipelines:
                    return []
                pipelines = list(self._pipelines[project_id].values())

            if pagination:
                offset = pagination.offset
                limit = pagination.limit
                pipelines = pipelines[offset : offset + limit]

            return pipelines

    async def search_configs(
        self,
        query: str,
        config_type: Optional[str] = None,
        project_id: Optional[str] = None,
        pagination: Optional[PaginationParams] = None,
    ) -> ConfigSearchResults:
        """Search across all configurations using full-text search."""
        with self._lock:
            results: List[ConfigSearchResult] = []
            query_lower = query.lower()

            # Search projects
            if not config_type or config_type == "project":
                for proj_id, proj in self._projects.items():
                    if project_id and proj_id != project_id:
                        continue
                    if (
                        query_lower in proj.name.lower()
                        or (proj.description and query_lower in proj.description.lower())
                    ):
                        results.append(
                            ConfigSearchResult(
                                config_id=proj.id,
                                config_type="project",
                                name=proj.name,
                                description=proj.description,
                                matched_fields=["name"],
                                score=1.0,
                            )
                        )

            # Simple pagination
            total_count = len(results)
            if pagination:
                offset = pagination.offset
                limit = pagination.limit
                results = results[offset : offset + limit]

            return ConfigSearchResults(
                results=results,
                total_count=total_count,
                query=query,
                filters={"config_type": config_type, "project_id": project_id},
            )

    async def get_config_version_history(
        self, config_id: str, config_type: str, limit: int = 10
    ) -> List[ConfigVersionInfo]:
        """Get version history for a configuration."""
        with self._lock:
            history = self._version_history.get(config_id, [])
            return history[-limit:]

    async def get_config_version(
        self, config_id: str, config_type: str, version: int
    ) -> Dict[str, Any]:
        """Get a specific version of a configuration."""
        with self._lock:
            # For mock, just return current version
            if config_id in self._projects:
                proj = self._projects[config_id]
                return {
                    "id": proj.id,
                    "name": proj.name,
                    "description": proj.description,
                    "version": version,
                }
            raise ConfigNotFoundError(f"Configuration with ID {config_id} not found")

    async def count_configs(
        self, config_type: Optional[str] = None, project_id: Optional[str] = None
    ) -> int:
        """Count configurations."""
        if self._config_store:
            count = 0
            if not config_type or config_type == "project":
                count += len(self._config_store.projects)
            if not config_type or config_type == "agent":
                if project_id:
                    count += len(self._config_store.agents.get(project_id, {}))
                else:
                    count += sum(len(agents) for agents in self._config_store.agents.values())
            if not config_type or config_type == "pipeline":
                if project_id:
                    count += len(self._config_store.pipelines.get(project_id, {}))
                else:
                    count += sum(len(pipes) for pipes in self._config_store.pipelines.values())
            return count
        with self._lock:
            count = 0
            if not config_type or config_type == "project":
                count += len(self._projects)
            if not config_type or config_type == "agent":
                if project_id:
                    count += len(self._agents.get(project_id, {}))
                else:
                    count += sum(len(agents) for agents in self._agents.values())
            if not config_type or config_type == "pipeline":
                if project_id:
                    count += len(self._pipelines.get(project_id, {}))
                else:
                    count += sum(len(pipelines) for pipelines in self._pipelines.values())
            return count

    def add_project_config(self, config: ProjectConfigInfo):
        """Helper method to add a project config (for testing)."""
        with self._lock:
            self._projects[config.id] = config
            self._projects_by_name[config.name] = config.id

    def add_agent_config(self, config: AgentConfigInfo):
        """Helper method to add an agent config (for testing)."""
        with self._lock:
            if config.project_id not in self._agents:
                self._agents[config.project_id] = {}
            self._agents[config.project_id][config.agent_name] = config

    def add_pipeline_config(self, config: PipelineConfigInfo):
        """Helper method to add a pipeline config (for testing)."""
        with self._lock:
            if config.project_id not in self._pipelines:
                self._pipelines[config.project_id] = {}
            self._pipelines[config.project_id][config.name] = config

    def add_version_history(self, config_id: str, entry: ConfigVersionInfo):
        """Helper method to add a version history entry (for testing)."""
        with self._lock:
            if config_id not in self._version_history:
                self._version_history[config_id] = []
            self._version_history[config_id].append(entry)

    def clear(self):
        """Clear all data (useful for testing)."""
        with self._lock:
            self._projects.clear()
            self._projects_by_name.clear()
            self._agents.clear()
            self._pipelines.clear()
            self._version_history.clear()
