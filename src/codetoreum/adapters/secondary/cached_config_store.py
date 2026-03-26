"""Cached configuration store combining Elasticsearch storage with Redis caching."""

import logging
from typing import Any

from codetoreum.infrastructure.redis_config_cache import RedisConfigCache
from codetoreum.ports.output.config_store import (
    AgentConfig,
    ConfigVersion,
    IConfigStore,
    PipelineConfig,
    ProjectConfig,
    WorkflowTemplate,
)

logger = logging.getLogger(__name__)


class CachedConfigStore(IConfigStore):
    """
    Write-through cache decorator for configuration storage.

    Architecture:
        Application → CachedConfigStore → Redis Cache → Elasticsearch
                                              ↓
                                        (on cache miss)

    Features:
    - Read-through: Check cache first, fall back to storage on miss
    - Write-through: Write to storage first, then update cache
    - Cache invalidation: Invalidate cache on updates
    - Transparent to application: Implements IConfigStore interface

    This decorator wraps any IConfigStore implementation (typically
    ElasticsearchConfigStorage) and adds Redis caching on top.
    """

    def __init__(
        self,
        storage: IConfigStore,
        cache: RedisConfigCache,
    ):
        """
        Initialize cached configuration store.

        Args:
            storage: Underlying storage implementation (e.g., ElasticsearchConfigStorage)
            cache: Redis cache for fast reads
        """
        self.storage = storage
        self.cache = cache

    async def get_project_config(self, project_id: str) -> ProjectConfig:
        """
        Get project configuration (cache-first).

        Args:
            project_id: Project identifier

        Returns:
            ProjectConfig instance

        Raises:
            ConfigNotFoundError: If project doesn't exist
        """
        # Try cache first
        cached = await self.cache.get_project_config(project_id)
        if cached:
            logger.debug(f"Project config cache hit: {project_id}")
            return cached

        # Cache miss - get from storage
        logger.debug(f"Project config cache miss: {project_id}")
        config = await self.storage.get_project_config(project_id)

        # Update cache
        await self.cache.set_project_config(config)

        return config

    async def get_project_config_by_name(self, project_name: str) -> ProjectConfig:
        """
        Get project configuration by name (cache-first).

        Args:
            project_name: Project name

        Returns:
            ProjectConfig instance

        Raises:
            ConfigNotFoundError: If project doesn't exist
        """
        # Try cache first
        cached = await self.cache.get_project_config_by_name(project_name)
        if cached:
            logger.debug(f"Project config cache hit (by name): {project_name}")
            return cached

        # Cache miss - get from storage
        logger.debug(f"Project config cache miss (by name): {project_name}")
        config = await self.storage.get_project_config_by_name(project_name)

        # Update cache
        await self.cache.set_project_config(config)

        return config

    async def save_project_config(self, config: ProjectConfig) -> None:
        """
        Save project configuration (write-through).

        Args:
            config: ProjectConfig to save
        """
        # Write to storage first (storage assigns version/timestamps)
        await self.storage.save_project_config(config)

        # Fetch the stored version (with updated version/timestamps) for the cache
        stored = await self.storage.get_project_config(config.id)
        await self.cache.set_project_config(stored)

        logger.debug(f"Saved project config to storage and cache: {config.id}")

    async def get_agent_config(self, project_id: str, agent_name: str) -> AgentConfig:
        """
        Get agent configuration (cache-first).

        Args:
            project_id: Project identifier
            agent_name: Agent name

        Returns:
            AgentConfig instance

        Raises:
            ConfigNotFoundError: If agent config doesn't exist
        """
        # Try cache first
        cached = await self.cache.get_agent_config(project_id, agent_name)
        if cached:
            logger.debug(f"Agent config cache hit: {project_id}/{agent_name}")
            return cached

        # Cache miss - get from storage
        logger.debug(f"Agent config cache miss: {project_id}/{agent_name}")
        config = await self.storage.get_agent_config(project_id, agent_name)

        # Update cache
        await self.cache.set_agent_config(config)

        return config

    async def save_agent_config(self, config: AgentConfig) -> None:
        """
        Save agent configuration (write-through).

        Args:
            config: AgentConfig to save
        """
        # Write to storage first
        await self.storage.save_agent_config(config)

        # Update cache
        await self.cache.set_agent_config(config)

        logger.debug(f"Saved agent config to storage and cache: {config.project_id}/{config.agent_name}")

    async def get_pipeline_config(self, project_id: str, pipeline_name: str) -> PipelineConfig:
        """
        Get pipeline configuration (cache-first).

        Args:
            project_id: Project identifier
            pipeline_name: Pipeline name

        Returns:
            PipelineConfig instance

        Raises:
            ConfigNotFoundError: If pipeline doesn't exist
        """
        # Try cache first
        cached = await self.cache.get_pipeline_config(project_id, pipeline_name)
        if cached:
            logger.debug(f"Pipeline config cache hit: {project_id}/{pipeline_name}")
            return cached

        # Cache miss - get from storage
        logger.debug(f"Pipeline config cache miss: {project_id}/{pipeline_name}")
        config = await self.storage.get_pipeline_config(project_id, pipeline_name)

        # Update cache
        await self.cache.set_pipeline_config(config)

        return config

    async def save_pipeline_config(self, config: PipelineConfig) -> None:
        """
        Save pipeline configuration (write-through).

        Args:
            config: PipelineConfig to save
        """
        # Write to storage first
        await self.storage.save_pipeline_config(config)

        # Update cache
        await self.cache.set_pipeline_config(config)

        logger.debug(f"Saved pipeline config to storage and cache: {config.project_id}/{config.name}")

    async def get_workflow_template(self, template_name: str) -> WorkflowTemplate:
        """
        Get workflow template (cache-first).

        Args:
            template_name: Template name

        Returns:
            WorkflowTemplate instance

        Raises:
            ConfigNotFoundError: If template doesn't exist
        """
        # Try cache first
        cached = await self.cache.get_workflow_template(template_name)
        if cached:
            logger.debug(f"Workflow template cache hit: {template_name}")
            return cached

        # Cache miss - get from storage
        logger.debug(f"Workflow template cache miss: {template_name}")
        template = await self.storage.get_workflow_template(template_name)

        # Update cache
        await self.cache.set_workflow_template(template)

        return template

    async def save_workflow_template(self, template: WorkflowTemplate) -> None:
        """
        Save workflow template (write-through).

        Args:
            template: WorkflowTemplate to save
        """
        # Write to storage first
        await self.storage.save_workflow_template(template)

        # Update cache
        await self.cache.set_workflow_template(template)

        logger.debug(f"Saved workflow template to storage and cache: {template.name}")

    async def list_projects(self) -> list[ProjectConfig]:
        """
        List all projects (storage-only, no caching for lists).

        Returns:
            List of ProjectConfig instances
        """
        # Lists are not cached (too complex to invalidate correctly)
        return await self.storage.list_projects()

    async def list_agents(self, project_id: str) -> list[AgentConfig]:
        """
        List all agents for a project (storage-only, no caching for lists).

        Args:
            project_id: Project identifier

        Returns:
            List of AgentConfig instances
        """
        # Lists are not cached (too complex to invalidate correctly)
        return await self.storage.list_agents(project_id)

    async def list_pipelines(self, project_id: str) -> list[PipelineConfig]:
        """
        List all pipelines for a project (storage-only, no caching for lists).

        Args:
            project_id: Project identifier

        Returns:
            List of PipelineConfig instances
        """
        # Lists are not cached (too complex to invalidate correctly)
        return await self.storage.list_pipelines(project_id)

    async def search_configs(self, query: str, config_type: str | None = None) -> list[dict[str, Any]]:
        """
        Search configurations (storage-only, no caching for searches).

        Args:
            query: Search query string
            config_type: Optional filter by config type

        Returns:
            List of matching configurations
        """
        # Searches are not cached (results depend on query)
        return await self.storage.search_configs(query, config_type)

    async def get_config_version(self, config_id: str, version: int) -> dict[str, Any]:
        """
        Get specific version of a configuration (storage-only).

        Args:
            config_id: Configuration identifier
            version: Version number

        Returns:
            Configuration data for specified version

        Raises:
            ConfigNotFoundError: If version doesn't exist
        """
        # Historical versions are not cached
        return await self.storage.get_config_version(config_id, version)

    async def list_config_versions(self, config_id: str, limit: int = 10) -> list[ConfigVersion]:
        """
        List configuration version history (storage-only).

        Args:
            config_id: Configuration identifier
            limit: Maximum number of versions to return

        Returns:
            List of ConfigVersion instances, newest first
        """
        # Version history is not cached
        return await self.storage.list_config_versions(config_id, limit)

    async def delete_project_config(self, project_id: str) -> None:
        """
        Delete project configuration (write-through with cache invalidation).

        Args:
            project_id: Project identifier

        Raises:
            ConfigNotFoundError: If project doesn't exist
        """
        # Delete from storage first
        await self.storage.delete_project_config(project_id)

        # Invalidate cache
        await self.cache.invalidate_project(project_id)

        logger.debug(f"Deleted project config and invalidated cache: {project_id}")

    async def delete_agent_config(self, project_id: str, agent_name: str) -> None:
        """
        Delete agent configuration (write-through with cache invalidation).

        Args:
            project_id: Project identifier
            agent_name: Agent name

        Raises:
            ConfigNotFoundError: If agent config doesn't exist
        """
        # Delete from storage first
        await self.storage.delete_agent_config(project_id, agent_name)

        # Invalidate cache
        await self.cache.invalidate_agent(project_id, agent_name)

        logger.debug(f"Deleted agent config and invalidated cache: {project_id}/{agent_name}")

    async def exists(self, project_id: str) -> bool:
        """
        Check if project configuration exists (storage-only).

        Args:
            project_id: Project identifier

        Returns:
            True if project exists, False otherwise
        """
        # Existence checks go directly to storage (avoid cache false negatives)
        return await self.storage.exists(project_id)
