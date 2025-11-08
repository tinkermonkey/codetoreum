"""
Mock Configuration Query Adapter

In-memory implementation of IConfigurationQueryPort for development and testing.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
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


class MockConfigQueryAdapter(IConfigurationQueryPort):
    """
    Mock implementation of IConfigurationQueryPort using in-memory storage.
    """

    def __init__(self):
        self._projects: Dict[str, ProjectConfigInfo] = {}
        self._projects_by_name: Dict[str, str] = {}  # name -> project_id
        self._agents: Dict[str, Dict[str, AgentConfigInfo]] = {}  # project_id -> {agent_name -> config}
        self._pipelines: Dict[str, Dict[str, PipelineConfigInfo]] = {}  # project_id -> {pipeline_name -> config}
        self._version_history: Dict[str, List[ConfigVersionInfo]] = {}  # config_id -> versions
        self._lock = RLock()

    async def get_project_config(
        self, project_id: str, include_secrets: bool = False
    ) -> ProjectConfigInfo:
        """Get project configuration by ID."""
        with self._lock:
            if project_id not in self._projects:
                raise ConfigNotFoundError(f"Project with ID {project_id} not found")
            return self._projects[project_id]

    async def get_project_config_by_name(
        self, project_name: str, include_secrets: bool = False
    ) -> ProjectConfigInfo:
        """Get project configuration by name."""
        with self._lock:
            if project_name not in self._projects_by_name:
                raise ConfigNotFoundError(f"Project with name '{project_name}' not found")
            project_id = self._projects_by_name[project_name]
            return self._projects[project_id]

    async def get_agent_config(
        self, project_id: str, agent_name: str
    ) -> AgentConfigInfo:
        """Get agent configuration."""
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
        with self._lock:
            if project_id not in self._pipelines:
                raise ProjectNotFoundError(f"Project with ID {project_id} not found")
            if pipeline_name not in self._pipelines[project_id]:
                raise PipelineNotFoundError(
                    f"Pipeline '{pipeline_name}' not found in project"
                )
            return self._pipelines[project_id][pipeline_name]

    async def list_projects(
        self, pagination: Optional[PaginationParams] = None
    ) -> List[ProjectConfigInfo]:
        """List all projects."""
        with self._lock:
            projects = list(self._projects.values())

            if pagination:
                offset = pagination.offset
                limit = pagination.limit
                projects = projects[offset : offset + limit]

            return projects

    async def list_agents(
        self, project_id: str, pagination: Optional[PaginationParams] = None
    ) -> List[AgentConfigInfo]:
        """List all agents for a project."""
        with self._lock:
            if project_id not in self._agents:
                raise ProjectNotFoundError(f"Project with ID {project_id} not found")

            agents = list(self._agents[project_id].values())

            if pagination:
                offset = pagination.offset
                limit = pagination.limit
                agents = agents[offset : offset + limit]

            return agents

    async def list_pipelines(
        self, project_id: str, pagination: Optional[PaginationParams] = None
    ) -> List[PipelineConfigInfo]:
        """List all pipelines for a project."""
        with self._lock:
            if project_id not in self._pipelines:
                raise ProjectNotFoundError(f"Project with ID {project_id} not found")

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
        with self._lock:
            count = 0
            if not config_type or config_type == "project":
                count += len(self._projects)
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

    def clear(self):
        """Clear all data (useful for testing)."""
        with self._lock:
            self._projects.clear()
            self._projects_by_name.clear()
            self._agents.clear()
            self._pipelines.clear()
            self._version_history.clear()
