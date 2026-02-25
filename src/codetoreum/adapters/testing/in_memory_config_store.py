"""
In-Memory Configuration Store

Mock adapter for testing configuration service without external dependencies.
"""

from datetime import UTC, datetime
from typing import Any

from codetoreum.ports.output.config_store import (
    AgentConfig,
    ConfigNotFoundError,
    ConfigVersion,
    IConfigStore,
    PipelineConfig,
    ProjectConfig,
    WorkflowTemplate,
)


class InMemoryConfigStore(IConfigStore):
    """
    In-memory configuration store for testing.

    Implements all IConfigStore operations using dictionaries for storage.
    Thread-safe for testing purposes.
    """

    def __init__(self):
        """Initialize in-memory storage."""
        self.projects: dict[str, ProjectConfig] = {}
        self.projects_by_name: dict[str, str] = {}  # name -> id mapping
        self.agents: dict[str, dict[str, AgentConfig]] = {}  # project_id -> {agent_name -> config}
        self.pipelines: dict[str, dict[str, PipelineConfig]] = {}  # project_id -> {pipeline_name -> config}
        self.workflow_templates: dict[str, WorkflowTemplate] = {}
        self.history: dict[str, list[ConfigVersion]] = {}  # config_id -> versions

    async def get_project_config(self, project_id: str) -> ProjectConfig:
        """Get project configuration by ID."""
        if project_id not in self.projects:
            raise ConfigNotFoundError(f"Project with ID '{project_id}' not found")
        return self.projects[project_id]

    async def get_project_config_by_name(self, project_name: str) -> ProjectConfig:
        """Get project configuration by name."""
        if project_name not in self.projects_by_name:
            raise ConfigNotFoundError(f"Project '{project_name}' not found")
        project_id = self.projects_by_name[project_name]
        return self.projects[project_id]

    async def save_project_config(self, config: ProjectConfig) -> None:
        """Save project configuration."""
        # Record version history
        if config.id in self.projects:
            # Updating existing config
            old_config = self.projects[config.id]
            version = ConfigVersion(
                version=config.version,
                changed_at=config.updated_at or datetime.now(UTC),
                changed_by=config.metadata.get("updated_by", "system"),
                change_type="update_project",
                changes=config.metadata.get("changes", {}),
                reason=config.metadata.get("update_reason"),
            )
            if config.id not in self.history:
                self.history[config.id] = []
            self.history[config.id].insert(0, version)

        # Save config
        self.projects[config.id] = config
        self.projects_by_name[config.name] = config.id

    async def get_agent_config(
        self,
        project_id: str,
        agent_name: str
    ) -> AgentConfig:
        """Get agent configuration for a project."""
        if project_id not in self.agents:
            raise ConfigNotFoundError(
                f"No agents configured for project '{project_id}'"
            )
        if agent_name not in self.agents[project_id]:
            raise ConfigNotFoundError(
                f"Agent '{agent_name}' not found in project '{project_id}'"
            )
        return self.agents[project_id][agent_name]

    async def save_agent_config(self, config: AgentConfig) -> None:
        """Save agent configuration."""
        if config.project_id not in self.agents:
            self.agents[config.project_id] = {}

        # Record version history
        agent_id = f"{config.project_id}:{config.agent_name}"
        if config.agent_name in self.agents[config.project_id]:
            version = ConfigVersion(
                version=config.version,
                changed_at=config.updated_at or datetime.now(UTC),
                changed_by=config.metadata.get("updated_by", "system"),
                change_type="update_agent",
                changes=config.metadata.get("changes", {}),
                reason=config.metadata.get("update_reason"),
            )
            if agent_id not in self.history:
                self.history[agent_id] = []
            self.history[agent_id].insert(0, version)

        self.agents[config.project_id][config.agent_name] = config

    async def get_pipeline_config(
        self,
        project_id: str,
        pipeline_name: str
    ) -> PipelineConfig:
        """Get pipeline configuration."""
        if project_id not in self.pipelines:
            raise ConfigNotFoundError(
                f"No pipelines configured for project '{project_id}'"
            )
        if pipeline_name not in self.pipelines[project_id]:
            raise ConfigNotFoundError(
                f"Pipeline '{pipeline_name}' not found in project '{project_id}'"
            )
        return self.pipelines[project_id][pipeline_name]

    async def save_pipeline_config(self, config: PipelineConfig) -> None:
        """Save pipeline configuration."""
        if config.project_id not in self.pipelines:
            self.pipelines[config.project_id] = {}

        # Record version history
        pipeline_id = f"{config.project_id}:{config.name}"
        if config.name in self.pipelines[config.project_id]:
            version = ConfigVersion(
                version=config.version,
                changed_at=config.updated_at or datetime.now(UTC),
                changed_by=config.metadata.get("updated_by", "system"),
                change_type="update_pipeline",
                changes=config.metadata.get("changes", {}),
                reason=config.metadata.get("update_reason"),
            )
            if pipeline_id not in self.history:
                self.history[pipeline_id] = []
            self.history[pipeline_id].insert(0, version)

        self.pipelines[config.project_id][config.name] = config

    async def get_workflow_template(self, template_name: str) -> WorkflowTemplate:
        """Get workflow template by name."""
        if template_name not in self.workflow_templates:
            raise ConfigNotFoundError(f"Workflow template '{template_name}' not found")
        return self.workflow_templates[template_name]

    async def save_workflow_template(self, template: WorkflowTemplate) -> None:
        """Save workflow template."""
        self.workflow_templates[template.name] = template

    async def list_projects(self) -> list[ProjectConfig]:
        """List all projects."""
        return list(self.projects.values())

    async def list_agents(self, project_id: str) -> list[AgentConfig]:
        """List all agents for a project."""
        if project_id not in self.agents:
            return []
        return list(self.agents[project_id].values())

    async def list_pipelines(self, project_id: str) -> list[PipelineConfig]:
        """List all pipelines for a project."""
        if project_id not in self.pipelines:
            return []
        return list(self.pipelines[project_id].values())

    async def search_configs(
        self,
        query: str,
        config_type: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Search configurations using simple substring matching.

        Search behavior:
        - Case-insensitive
        - Space-separated terms treated as AND search
        - Searches across all text fields

        This is a simplified implementation for testing. Production
        implementation would use Elasticsearch full-text search.
        """
        results = []

        # Split query into terms (AND search)
        terms = [term.lower() for term in query.split() if term]

        def matches_all_terms(text: str) -> bool:
            """Check if text contains all search terms."""
            text_lower = text.lower()
            return all(term in text_lower for term in terms)

        def config_matches(config) -> bool:
            """Check if config matches all search terms."""
            # Build searchable text from all fields
            searchable_fields = [
                str(getattr(config, "name", "")),
                str(getattr(config, "github_org", "")),
                str(getattr(config, "github_repo", "")),
                str(getattr(config, "agent_name", "")),
                str(getattr(config, "model", "")),
                str(getattr(config, "metadata", {})),
                str(getattr(config, "tech_stacks", {})),
            ]
            combined_text = " ".join(searchable_fields)
            return matches_all_terms(combined_text)

        # Search projects
        if not config_type or config_type == "project":
            for config in self.projects.values():
                if config_matches(config):
                    results.append({
                        "type": "project",
                        "id": config.id,
                        "name": config.name,
                        "config": config,
                    })

        # Search agents
        if not config_type or config_type == "agent":
            for project_agents in self.agents.values():
                for config in project_agents.values():
                    if config_matches(config):
                        results.append({
                            "type": "agent",
                            "id": f"{config.project_id}:{config.agent_name}",
                            "name": config.agent_name,
                            "config": config,
                        })

        # Search pipelines
        if not config_type or config_type == "pipeline":
            for project_pipelines in self.pipelines.values():
                for config in project_pipelines.values():
                    if config_matches(config):
                        results.append({
                            "type": "pipeline",
                            "id": config.id,
                            "name": config.name,
                            "config": config,
                        })

        return results

    async def get_config_version(
        self,
        config_id: str,
        version: int
    ) -> dict[str, Any]:
        """Get specific version of a configuration."""
        if config_id not in self.history:
            raise ConfigNotFoundError(f"No history found for config '{config_id}'")

        for v in self.history[config_id]:
            if v.version == version:
                return {
                    "version": v.version,
                    "changed_at": v.changed_at.isoformat(),
                    "changed_by": v.changed_by,
                    "change_type": v.change_type,
                    "changes": v.changes,
                    "reason": v.reason,
                }

        raise ConfigNotFoundError(
            f"Version {version} not found for config '{config_id}'"
        )

    async def list_config_versions(
        self,
        config_id: str,
        limit: int = 10
    ) -> list[ConfigVersion]:
        """List configuration version history."""
        if config_id not in self.history:
            return []

        return self.history[config_id][:limit]

    async def delete_project_config(self, project_id: str) -> None:
        """Delete project configuration."""
        if project_id not in self.projects:
            raise ConfigNotFoundError(f"Project '{project_id}' not found")

        config = self.projects[project_id]
        del self.projects[project_id]
        del self.projects_by_name[config.name]

        # Clean up related configs
        if project_id in self.agents:
            del self.agents[project_id]
        if project_id in self.pipelines:
            del self.pipelines[project_id]
        if project_id in self.history:
            del self.history[project_id]

    async def delete_agent_config(
        self,
        project_id: str,
        agent_name: str
    ) -> None:
        """Delete agent configuration."""
        if project_id not in self.agents:
            raise ConfigNotFoundError(
                f"No agents configured for project '{project_id}'"
            )
        if agent_name not in self.agents[project_id]:
            raise ConfigNotFoundError(
                f"Agent '{agent_name}' not found in project '{project_id}'"
            )

        del self.agents[project_id][agent_name]
        agent_id = f"{project_id}:{agent_name}"
        if agent_id in self.history:
            del self.history[agent_id]

    async def exists(self, project_id: str) -> bool:
        """Check if project configuration exists."""
        return project_id in self.projects

    # Helper methods for testing

    def clear(self) -> None:
        """Clear all stored configurations."""
        self.projects.clear()
        self.projects_by_name.clear()
        self.agents.clear()
        self.pipelines.clear()
        self.workflow_templates.clear()
        self.history.clear()

    def get_history_count(self, config_id: str) -> int:
        """Get number of versions in history."""
        return len(self.history.get(config_id, []))
