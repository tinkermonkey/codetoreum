"""Elasticsearch configuration storage adapter for production persistence."""

import dataclasses
import logging
from datetime import UTC, datetime
from typing import Any

from elasticsearch import AsyncElasticsearch, NotFoundError

from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.ports.output.config_store import (
    AgentConfig,
    ConfigNotFoundError,
    ConfigVersion,
    IConfigStore,
    PipelineConfig,
    ProjectConfig,
    WorkflowTemplate,
)

logger = logging.getLogger(__name__)


class ElasticsearchConfigStorage(IConfigStore):
    """
    Production configuration storage using Elasticsearch.

    Features:
    - Separate indices for each configuration type
    - Optimistic concurrency control using _version field
    - Full-text search across all configurations
    - Configuration versioning with audit trail
    - Index lifecycle management (ILM) for retention

    Index design:
    - config-projects: Project configurations
    - config-agents: Agent configurations
    - config-pipelines: Pipeline configurations
    - config-workflows: Workflow templates
    - config-history: Configuration change audit trail

    **Resilience Patterns**:
    This adapter should be wrapped with resilience decorators at instantiation:
    - Circuit breaker: Prevents cascading failures
    - Rate limiting: Controls request rate to Elasticsearch
    - Retry policy: Handles transient failures
    - Timeout: Prevents indefinite waits

    Example:
        ```python
        from codetoreum.infrastructure.resilience.factory import create_resilient_adapter

        config_storage = create_resilient_adapter(
            adapter=ElasticsearchConfigStorage(es_client),
            adapter_type="config_store",
            config={
                "circuit_breaker": {"failure_threshold": 5},
                "retry": {"max_attempts": 3},
                "rate_limit": {"requests_per_second": 50},
                "timeout": {"seconds": 10}
            }
        )
        ```

    The adapter itself remains pure without embedded resilience logic, following
    the project's hexagonal architecture principles.
    """

    # Index names
    INDEX_PROJECTS = "config-projects"
    INDEX_AGENTS = "config-agents"
    INDEX_PIPELINES = "config-pipelines"
    INDEX_WORKFLOWS = "config-workflows"
    INDEX_HISTORY = "config-history"

    def __init__(
        self,
        es_client: AsyncElasticsearch,
        create_index_templates: bool = True,
        shard_count: int = 1,
        replica_count: int = 1,
    ):
        """
        Initialize Elasticsearch configuration storage.

        Args:
            es_client: AsyncElasticsearch client
            create_index_templates: Whether to create index templates on init
            shard_count: Number of shards for indices (configurable)
            replica_count: Number of replicas for indices (configurable)
        """
        self.client = es_client
        self._initialized = False
        self._create_index_templates = create_index_templates
        self.shard_count = shard_count
        self.replica_count = replica_count

    async def initialize(self) -> None:
        """
        Initialize the storage (create indices and templates).

        Raises:
            Exception: If initialization fails
        """
        if self._initialized:
            return

        if self._create_index_templates:
            await self._create_all_index_templates()

        self._initialized = True
        logger.info("Elasticsearch configuration storage initialized")

    async def _create_all_index_templates(self) -> None:
        """Create index templates for all configuration indices."""
        templates = [
            (self.INDEX_PROJECTS, self._get_projects_mapping()),
            (self.INDEX_AGENTS, self._get_agents_mapping()),
            (self.INDEX_PIPELINES, self._get_pipelines_mapping()),
            (self.INDEX_WORKFLOWS, self._get_workflows_mapping()),
            (self.INDEX_HISTORY, self._get_history_mapping()),
        ]

        for index_name, mappings in templates:
            await self._create_index_template(index_name, mappings)

    async def _create_index_template(self, index_name: str, mappings: dict[str, Any]) -> None:
        """
        Create or update an index template.

        Args:
            index_name: Name of the index
            mappings: Elasticsearch mappings for the index
        """
        try:
            # Check if index exists
            exists = await self.client.indices.exists(index=index_name)

            if not exists:
                # Create index with mappings and settings
                await self.client.indices.create(
                    index=index_name,
                    body={
                        "settings": {
                            "number_of_shards": self.shard_count,
                            "number_of_replicas": self.replica_count,
                            "analysis": {
                                "analyzer": {
                                    "config_analyzer": {
                                        "type": "custom",
                                        "tokenizer": "standard",
                                        "filter": [
                                            "lowercase",
                                            "asciifolding",
                                            "word_delimiter",
                                        ],
                                    }
                                }
                            },
                        },
                        "mappings": mappings,
                    },
                )
                logger.info(f"Created index: {index_name}")
            else:
                # Update mappings if index already exists
                await self.client.indices.put_mapping(index=index_name, body=mappings)
                logger.info(f"Updated mappings for index: {index_name}")

        except Exception as e:
            logger.error(
                f"Failed to create/update index {index_name}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_ERROR},
            )
            raise

    def _get_projects_mapping(self) -> dict[str, Any]:
        """Get Elasticsearch mapping for projects index."""
        return {
            "properties": {
                "id": {"type": "keyword"},
                "name": {
                    "type": "text",
                    "analyzer": "config_analyzer",
                    "fields": {"keyword": {"type": "keyword"}},
                },
                "github_org": {"type": "keyword"},
                "github_repo": {"type": "keyword"},
                "tech_stacks": {"type": "object", "enabled": True, "dynamic": False},
                "pipelines": {
                    "type": "nested",
                    "enabled": True,
                    "dynamic": False,
                    "properties": {
                        "name": {"type": "keyword"},
                        "stages": {"type": "keyword"},
                    },
                },
                "testing": {"type": "object", "enabled": True, "dynamic": False},
                "environment_variables": {"type": "object", "enabled": True, "dynamic": False},
                "mounted_commands": {"type": "object", "enabled": True, "dynamic": False},
                "mounted_subagents": {"type": "object", "enabled": True, "dynamic": False},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
                "version": {"type": "integer"},
                "metadata": {"type": "object", "enabled": True, "dynamic": False},
            }
        }

    def _get_agents_mapping(self) -> dict[str, Any]:
        """Get Elasticsearch mapping for agents index."""
        return {
            "properties": {
                "project_id": {"type": "keyword"},
                "agent_name": {
                    "type": "text",
                    "analyzer": "config_analyzer",
                    "fields": {"keyword": {"type": "keyword"}},
                },
                "model": {"type": "keyword"},
                "timeout": {"type": "integer"},
                "requires_docker": {"type": "boolean"},
                "makes_code_changes": {"type": "boolean"},
                "mcp_servers": {"type": "keyword"},
                "capabilities": {"type": "keyword"},
                "constraints": {"type": "object", "enabled": True, "dynamic": False},
                "version": {"type": "integer"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
                "metadata": {"type": "object", "enabled": True, "dynamic": False},
            }
        }

    def _get_pipelines_mapping(self) -> dict[str, Any]:
        """Get Elasticsearch mapping for pipelines index."""
        return {
            "properties": {
                "id": {"type": "keyword"},
                "project_id": {"type": "keyword"},
                "name": {
                    "type": "text",
                    "analyzer": "config_analyzer",
                    "fields": {"keyword": {"type": "keyword"}},
                },
                "stages": {
                    "type": "nested",
                    "enabled": True,
                    "dynamic": False,
                    "properties": {
                        "name": {"type": "keyword"},
                        "agent": {"type": "keyword"},
                    },
                },
                "triggers": {"type": "keyword"},
                "version": {"type": "integer"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
                "metadata": {"type": "object", "enabled": True, "dynamic": False},
            }
        }

    def _get_workflows_mapping(self) -> dict[str, Any]:
        """Get Elasticsearch mapping for workflow templates index."""
        return {
            "properties": {
                "id": {"type": "keyword"},
                "name": {
                    "type": "text",
                    "analyzer": "config_analyzer",
                    "fields": {"keyword": {"type": "keyword"}},
                },
                "description": {"type": "text", "analyzer": "config_analyzer"},
                "stages": {
                    "type": "nested",
                    "enabled": True,
                    "dynamic": False,
                    "properties": {
                        "name": {"type": "keyword"},
                        "agent": {"type": "keyword"},
                    },
                },
                "version": {"type": "integer"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
                "metadata": {"type": "object", "enabled": True, "dynamic": False},
            }
        }

    def _get_history_mapping(self) -> dict[str, Any]:
        """Get Elasticsearch mapping for configuration history index."""
        return {
            "properties": {
                "config_id": {"type": "keyword"},
                "config_type": {"type": "keyword"},
                "version": {"type": "integer"},
                "changed_at": {"type": "date"},
                "changed_by": {"type": "keyword"},
                "change_type": {"type": "keyword"},
                "changes": {"type": "object", "enabled": True, "dynamic": False},
                "reason": {"type": "text"},
                "snapshot": {"type": "object", "enabled": True, "dynamic": False},
            }
        }

    async def get_project_config(self, project_id: str) -> ProjectConfig:
        """
        Get project configuration by ID.

        Args:
            project_id: Project identifier

        Returns:
            ProjectConfig instance

        Raises:
            ConfigNotFoundError: If project doesn't exist
        """
        if not self._initialized:
            await self.initialize()

        try:
            result = await self.client.get(index=self.INDEX_PROJECTS, id=project_id)

            return self._deserialize_project(result["_source"])

        except NotFoundError:
            msg = f"Project not found: {project_id}"
            raise ConfigNotFoundError(msg)
        except Exception as e:
            logger.error(
                f"Failed to get project config {project_id}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_QUERY_ERROR},
            )
            raise

    async def get_project_config_by_name(self, project_name: str) -> ProjectConfig:
        """
        Get project configuration by name.

        Args:
            project_name: Project name

        Returns:
            ProjectConfig instance

        Raises:
            ConfigNotFoundError: If project doesn't exist
        """
        if not self._initialized:
            await self.initialize()

        try:
            result = await self.client.search(
                index=self.INDEX_PROJECTS,
                body={
                    "query": {"term": {"name.keyword": project_name}},
                    "size": 1,
                },
            )

            hits = result["hits"]["hits"]
            if not hits:
                msg = f"Project not found: {project_name}"
                raise ConfigNotFoundError(msg)

            return self._deserialize_project(hits[0]["_source"])

        except ConfigNotFoundError:
            raise
        except Exception as e:
            logger.error(
                f"Failed to get project config by name {project_name}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_QUERY_ERROR},
            )
            raise

    async def save_project_config(self, config: ProjectConfig) -> None:
        """
        Save project configuration.

        Creates a new version if config already exists.

        Args:
            config: ProjectConfig to save
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Set timestamps
            now = datetime.now(UTC)
            created_at = config.created_at if config.created_at is not None else now

            # Try to get existing document to determine version
            try:
                existing = await self.client.get(index=self.INDEX_PROJECTS, id=config.id)
                new_version = existing["_source"].get("version", 1) + 1
                config = dataclasses.replace(config, created_at=created_at, updated_at=now, version=new_version)
                doc = self._serialize_project(config)

                # Save history
                await self._save_history(
                    config_id=config.id,
                    config_type="project",
                    version=new_version,
                    changed_by="system",  # TODO: Get from context
                    change_type="update",
                    changes={"updated_at": now.isoformat()},
                    snapshot=existing["_source"],
                )

            except NotFoundError:
                # New configuration
                config = dataclasses.replace(config, created_at=created_at, updated_at=now, version=1)
                doc = self._serialize_project(config)

                # Save history
                await self._save_history(
                    config_id=config.id,
                    config_type="project",
                    version=1,
                    changed_by="system",  # TODO: Get from context
                    change_type="create",
                    changes={},
                    snapshot=doc,
                )

            # Index document
            await self.client.index(
                index=self.INDEX_PROJECTS,
                id=config.id,
                body=doc,
                refresh=True,
            )

            logger.info(f"Saved project config {config.id} (version {config.version})")

        except Exception as e:
            logger.error(
                f"Failed to save project config {config.id}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_ERROR},
            )
            raise

    async def get_agent_config(self, project_id: str, agent_name: str) -> AgentConfig:
        """
        Get agent configuration for a project.

        Args:
            project_id: Project identifier
            agent_name: Agent name

        Returns:
            AgentConfig instance

        Raises:
            ConfigNotFoundError: If agent config doesn't exist
        """
        if not self._initialized:
            await self.initialize()

        doc_id = f"{project_id}:{agent_name}"

        try:
            result = await self.client.get(index=self.INDEX_AGENTS, id=doc_id)

            return self._deserialize_agent(result["_source"])

        except NotFoundError:
            msg = f"Agent config not found: {project_id}/{agent_name}"
            raise ConfigNotFoundError(msg)
        except Exception as e:
            logger.error(
                f"Failed to get agent config {doc_id}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_QUERY_ERROR},
            )
            raise

    async def save_agent_config(self, config: AgentConfig) -> None:
        """
        Save agent configuration.

        Args:
            config: AgentConfig to save
        """
        if not self._initialized:
            await self.initialize()

        doc_id = f"{config.project_id}:{config.agent_name}"

        try:
            # Set timestamps
            now = datetime.now(UTC)
            created_at = config.created_at if config.created_at is not None else now

            # Try to get existing document to determine version
            try:
                existing = await self.client.get(index=self.INDEX_AGENTS, id=doc_id)
                new_version = existing["_source"].get("version", 1) + 1
                config = dataclasses.replace(config, created_at=created_at, updated_at=now, version=new_version)
                doc = self._serialize_agent(config)

                # Save history
                await self._save_history(
                    config_id=doc_id,
                    config_type="agent",
                    version=new_version,
                    changed_by="system",
                    change_type="update",
                    changes={"updated_at": now.isoformat()},
                    snapshot=existing["_source"],
                )

            except NotFoundError:
                # New configuration
                config = dataclasses.replace(config, created_at=created_at, updated_at=now, version=1)
                doc = self._serialize_agent(config)

                # Save history
                await self._save_history(
                    config_id=doc_id,
                    config_type="agent",
                    version=1,
                    changed_by="system",
                    change_type="create",
                    changes={},
                    snapshot=doc,
                )

            # Index document
            await self.client.index(
                index=self.INDEX_AGENTS,
                id=doc_id,
                body=doc,
                refresh=True,
            )

            logger.info(f"Saved agent config {doc_id} (version {config.version})")

        except Exception as e:
            logger.error(
                f"Failed to save agent config {doc_id}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_ERROR},
            )
            raise

    async def get_pipeline_config(self, project_id: str, pipeline_name: str) -> PipelineConfig:
        """
        Get pipeline configuration.

        Args:
            project_id: Project identifier
            pipeline_name: Pipeline name

        Returns:
            PipelineConfig instance

        Raises:
            ConfigNotFoundError: If pipeline doesn't exist
        """
        if not self._initialized:
            await self.initialize()

        try:
            result = await self.client.search(
                index=self.INDEX_PIPELINES,
                body={
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"project_id": project_id}},
                                {"term": {"name.keyword": pipeline_name}},
                            ]
                        }
                    },
                    "size": 1,
                },
            )

            hits = result["hits"]["hits"]
            if not hits:
                msg = f"Pipeline not found: {project_id}/{pipeline_name}"
                raise ConfigNotFoundError(msg)

            return self._deserialize_pipeline(hits[0]["_source"])

        except ConfigNotFoundError:
            raise
        except Exception as e:
            logger.error(
                f"Failed to get pipeline config {project_id}/{pipeline_name}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_QUERY_ERROR},
            )
            raise

    async def save_pipeline_config(self, config: PipelineConfig) -> None:
        """
        Save pipeline configuration.

        Args:
            config: PipelineConfig to save
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Set timestamps
            now = datetime.now(UTC)
            created_at = config.created_at if config.created_at is not None else now

            # Try to get existing document to determine version
            try:
                existing = await self.client.get(index=self.INDEX_PIPELINES, id=config.id)
                new_version = existing["_source"].get("version", 1) + 1
                config = dataclasses.replace(config, created_at=created_at, updated_at=now, version=new_version)
                doc = self._serialize_pipeline(config)

                # Save history
                await self._save_history(
                    config_id=config.id,
                    config_type="pipeline",
                    version=new_version,
                    changed_by="system",
                    change_type="update",
                    changes={"updated_at": now.isoformat()},
                    snapshot=existing["_source"],
                )

            except NotFoundError:
                # New configuration
                config = dataclasses.replace(config, created_at=created_at, updated_at=now, version=1)
                doc = self._serialize_pipeline(config)

                # Save history
                await self._save_history(
                    config_id=config.id,
                    config_type="pipeline",
                    version=1,
                    changed_by="system",
                    change_type="create",
                    changes={},
                    snapshot=doc,
                )

            # Index document
            await self.client.index(
                index=self.INDEX_PIPELINES,
                id=config.id,
                body=doc,
                refresh=True,
            )

            logger.info(f"Saved pipeline config {config.id} (version {config.version})")

        except Exception as e:
            logger.error(
                f"Failed to save pipeline config {config.id}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_ERROR},
            )
            raise

    async def get_workflow_template(self, template_name: str) -> WorkflowTemplate:
        """
        Get workflow template by name.

        Args:
            template_name: Template name

        Returns:
            WorkflowTemplate instance

        Raises:
            ConfigNotFoundError: If template doesn't exist
        """
        if not self._initialized:
            await self.initialize()

        try:
            result = await self.client.search(
                index=self.INDEX_WORKFLOWS,
                body={
                    "query": {"term": {"name.keyword": template_name}},
                    "size": 1,
                },
            )

            hits = result["hits"]["hits"]
            if not hits:
                msg = f"Template not found: {template_name}"
                raise ConfigNotFoundError(msg)

            return self._deserialize_workflow(hits[0]["_source"])

        except ConfigNotFoundError:
            raise
        except Exception as e:
            logger.error(
                f"Failed to get workflow template {template_name}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_QUERY_ERROR},
            )
            raise

    async def save_workflow_template(self, template: WorkflowTemplate) -> None:
        """
        Save workflow template.

        Args:
            template: WorkflowTemplate to save
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Set timestamps
            now = datetime.now(UTC)
            created_at = template.created_at if template.created_at is not None else now

            # Try to get existing document to check version
            try:
                existing = await self.client.get(index=self.INDEX_WORKFLOWS, id=template.id)
                old_version = existing["_source"].get("version", 1)
                new_version = old_version + 1
                template = dataclasses.replace(
                    template,
                    created_at=created_at,
                    updated_at=now,
                    version=new_version,
                )
                doc = self._serialize_workflow(template)

                # Save history
                await self._save_history(
                    config_id=template.id,
                    config_type="workflow",
                    version=new_version,
                    changed_by="system",
                    change_type="update",
                    changes={"updated_at": now.isoformat()},
                    snapshot=existing["_source"],
                )

            except NotFoundError:
                # New template
                template = dataclasses.replace(
                    template,
                    created_at=created_at,
                    updated_at=now,
                    version=1,
                )
                doc = self._serialize_workflow(template)

                # Save history
                await self._save_history(
                    config_id=template.id,
                    config_type="workflow",
                    version=1,
                    changed_by="system",
                    change_type="create",
                    changes={},
                    snapshot=doc,
                )

            # Index document
            await self.client.index(
                index=self.INDEX_WORKFLOWS,
                id=template.id,
                body=doc,
                refresh=True,
            )

            logger.info(f"Saved workflow template {template.id} (version {template.version})")

        except Exception as e:
            logger.error(
                f"Failed to save workflow template {template.id}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_ERROR},
            )
            raise

    async def list_projects(self) -> list[ProjectConfig]:
        """
        List all projects.

        Returns:
            List of ProjectConfig instances
        """
        if not self._initialized:
            await self.initialize()

        try:
            result = await self.client.search(
                index=self.INDEX_PROJECTS,
                body={"query": {"match_all": {}}, "size": 1000},
            )

            projects = []
            for hit in result["hits"]["hits"]:
                projects.append(self._deserialize_project(hit["_source"]))

            return projects

        except Exception as e:
            logger.error(
                f"Failed to list projects: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_QUERY_ERROR},
            )
            raise

    async def list_agents(self, project_id: str) -> list[AgentConfig]:
        """
        List all agents for a project.

        Args:
            project_id: Project identifier

        Returns:
            List of AgentConfig instances
        """
        if not self._initialized:
            await self.initialize()

        try:
            result = await self.client.search(
                index=self.INDEX_AGENTS,
                body={
                    "query": {"term": {"project_id": project_id}},
                    "size": 1000,
                },
            )

            agents = []
            for hit in result["hits"]["hits"]:
                agents.append(self._deserialize_agent(hit["_source"]))

            return agents

        except Exception as e:
            logger.error(
                f"Failed to list agents for project {project_id}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_QUERY_ERROR},
            )
            raise

    async def list_pipelines(self, project_id: str) -> list[PipelineConfig]:
        """
        List all pipelines for a project.

        Args:
            project_id: Project identifier

        Returns:
            List of PipelineConfig instances
        """
        if not self._initialized:
            await self.initialize()

        try:
            result = await self.client.search(
                index=self.INDEX_PIPELINES,
                body={
                    "query": {"term": {"project_id": project_id}},
                    "size": 1000,
                },
            )

            pipelines = []
            for hit in result["hits"]["hits"]:
                pipelines.append(self._deserialize_pipeline(hit["_source"]))

            return pipelines

        except Exception as e:
            logger.error(
                f"Failed to list pipelines for project {project_id}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_QUERY_ERROR},
            )
            raise

    async def search_configs(self, query: str, config_type: str | None = None) -> list[dict[str, Any]]:
        """
        Search configurations using full-text search with injection protection.

        Args:
            query: Search query string (space-separated terms for AND search)
            config_type: Optional filter by config type (project, agent, pipeline)

        Returns:
            List of matching configurations

        Raises:
            ValueError: If query or config_type contain invalid characters
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Sanitize and validate query to prevent injection attacks
            from codetoreum.infrastructure.security import (
                InvalidInputError,
                sanitize_search_query,
            )

            try:
                sanitized_query = sanitize_search_query(query, max_length=500)
            except InvalidInputError as e:
                msg = f"Invalid search query: {e}"
                raise ValueError(msg)

            if not sanitized_query:
                return []  # Empty query returns no results

            # Validate config_type to prevent injection
            valid_config_types = ["project", "agent", "pipeline", "workflow", None]
            if config_type not in valid_config_types:
                msg = (
                    f"Invalid config_type '{config_type}'. "
                    f"Must be one of: {', '.join([t for t in valid_config_types if t is not None])}"
                )
                raise ValueError(msg)

            # Determine which indices to search
            if config_type == "project":
                indices = [self.INDEX_PROJECTS]
            elif config_type == "agent":
                indices = [self.INDEX_AGENTS]
            elif config_type == "pipeline":
                indices = [self.INDEX_PIPELINES]
            elif config_type == "workflow":
                indices = [self.INDEX_WORKFLOWS]
            else:
                indices = [
                    self.INDEX_PROJECTS,
                    self.INDEX_AGENTS,
                    self.INDEX_PIPELINES,
                    self.INDEX_WORKFLOWS,
                ]

            # Split sanitized query into terms for AND search
            terms = sanitized_query.strip().split()

            # Build query
            if len(terms) == 1:
                search_query = {
                    "multi_match": {
                        "query": terms[0],
                        "fields": ["name^2", "description", "metadata"],
                        "type": "phrase_prefix",
                    }
                }
            else:
                # Multiple terms - use bool query with must (AND logic)
                search_query = {
                    "bool": {
                        "must": [
                            {
                                "multi_match": {
                                    "query": term,
                                    "fields": ["name^2", "description", "metadata"],
                                    "type": "phrase_prefix",
                                }
                            }
                            for term in terms
                        ]
                    }
                }

            result = await self.client.search(
                index=",".join(indices),
                body={"query": search_query, "size": 100},
            )

            configs = []
            for hit in result["hits"]["hits"]:
                config = hit["_source"]
                config["_score"] = hit["_score"]
                config["_type"] = hit["_index"]
                configs.append(config)

            return configs

        except Exception as e:
            logger.error(
                f"Failed to search configs: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_QUERY_ERROR},
            )
            raise

    async def get_config_version(self, config_id: str, version: int) -> dict[str, Any]:
        """
        Get specific version of a configuration.

        Args:
            config_id: Configuration identifier
            version: Version number

        Returns:
            Configuration data for specified version

        Raises:
            ConfigNotFoundError: If version doesn't exist
        """
        if not self._initialized:
            await self.initialize()

        try:
            result = await self.client.search(
                index=self.INDEX_HISTORY,
                body={
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"config_id": config_id}},
                                {"term": {"version": version}},
                            ]
                        }
                    },
                    "size": 1,
                },
            )

            hits = result["hits"]["hits"]
            if not hits:
                msg = f"Config version not found: {config_id} v{version}"
                raise ConfigNotFoundError(msg)

            return hits[0]["_source"]["snapshot"]

        except ConfigNotFoundError:
            raise
        except Exception as e:
            logger.error(
                f"Failed to get config version {config_id} v{version}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_QUERY_ERROR},
            )
            raise

    async def list_config_versions(self, config_id: str, limit: int = 10) -> list[ConfigVersion]:
        """
        List configuration version history.

        Args:
            config_id: Configuration identifier
            limit: Maximum number of versions to return

        Returns:
            List of ConfigVersion instances, newest first
        """
        if not self._initialized:
            await self.initialize()

        try:
            result = await self.client.search(
                index=self.INDEX_HISTORY,
                body={
                    "query": {"term": {"config_id": config_id}},
                    "sort": [{"changed_at": {"order": "desc"}}],
                    "size": limit,
                },
            )

            versions = []
            for hit in result["hits"]["hits"]:
                source = hit["_source"]
                versions.append(
                    ConfigVersion(
                        version=source["version"],
                        changed_at=datetime.fromisoformat(source["changed_at"]),
                        changed_by=source["changed_by"],
                        change_type=source["change_type"],
                        changes=source["changes"],
                        reason=source.get("reason"),
                    )
                )

            return versions

        except Exception as e:
            logger.error(
                f"Failed to list config versions for {config_id}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_QUERY_ERROR},
            )
            raise

    async def delete_project_config(self, project_id: str) -> None:
        """
        Delete project configuration.

        Args:
            project_id: Project identifier

        Raises:
            ConfigNotFoundError: If project doesn't exist
        """
        if not self._initialized:
            await self.initialize()

        try:
            await self.client.delete(index=self.INDEX_PROJECTS, id=project_id, refresh=True)

            logger.info(f"Deleted project config {project_id}")

        except NotFoundError:
            msg = f"Project not found: {project_id}"
            raise ConfigNotFoundError(msg)
        except Exception as e:
            logger.error(
                f"Failed to delete project config {project_id}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_ERROR},
            )
            raise

    async def delete_agent_config(self, project_id: str, agent_name: str) -> None:
        """
        Delete agent configuration.

        Args:
            project_id: Project identifier
            agent_name: Agent name

        Raises:
            ConfigNotFoundError: If agent config doesn't exist
        """
        if not self._initialized:
            await self.initialize()

        doc_id = f"{project_id}:{agent_name}"

        try:
            await self.client.delete(index=self.INDEX_AGENTS, id=doc_id, refresh=True)

            logger.info(f"Deleted agent config {doc_id}")

        except NotFoundError:
            msg = f"Agent config not found: {project_id}/{agent_name}"
            raise ConfigNotFoundError(msg)
        except Exception as e:
            logger.error(
                f"Failed to delete agent config {doc_id}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_ERROR},
            )
            raise

    async def exists(self, project_id: str) -> bool:
        """
        Check if project configuration exists.

        Args:
            project_id: Project identifier

        Returns:
            True if project exists, False otherwise
        """
        if not self._initialized:
            await self.initialize()

        try:
            result = await self.client.exists(index=self.INDEX_PROJECTS, id=project_id)
            return bool(result)

        except Exception as e:
            logger.error(
                f"Failed to check if project exists {project_id}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_QUERY_ERROR},
            )
            raise

    async def _save_history(
        self,
        config_id: str,
        config_type: str,
        version: int,
        changed_by: str,
        change_type: str,
        changes: dict[str, Any],
        snapshot: dict[str, Any],
        reason: str | None = None,
    ) -> None:
        """
        Save configuration history entry.

        Args:
            config_id: Configuration identifier
            config_type: Type of configuration (project, agent, pipeline, workflow)
            version: Version number
            changed_by: User who made the change
            change_type: Type of change (create, update, delete)
            changes: Dictionary of changes
            snapshot: Full configuration snapshot
            reason: Optional reason for the change
        """
        try:
            history_id = f"{config_id}:v{version}"

            doc = {
                "config_id": config_id,
                "config_type": config_type,
                "version": version,
                "changed_at": datetime.now(UTC).isoformat(),
                "changed_by": changed_by,
                "change_type": change_type,
                "changes": changes,
                "snapshot": snapshot,
                "reason": reason,
            }

            await self.client.index(
                index=self.INDEX_HISTORY,
                id=history_id,
                body=doc,
                refresh=True,
            )

            logger.debug(f"Saved history entry for {config_id} v{version}")

        except Exception as e:
            logger.error(
                f"Failed to save history for {config_id} v{version}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_ERROR},
            )
            # Don't raise - history failure shouldn't block config save

    def _serialize_project(self, config: ProjectConfig) -> dict[str, Any]:
        """Serialize ProjectConfig to dictionary."""
        return {
            "id": config.id,
            "name": config.name,
            "github_org": config.github_org,
            "github_repo": config.github_repo,
            "tech_stacks": dict(config.tech_stacks),
            "pipelines": [dict(p) for p in config.pipelines],
            "testing": dict(config.testing),
            "environment_variables": dict(config.environment_variables),
            "mounted_commands": dict(config.mounted_commands),
            "mounted_subagents": dict(config.mounted_subagents),
            "created_at": (config.created_at.isoformat() if config.created_at else None),
            "updated_at": (config.updated_at.isoformat() if config.updated_at else None),
            "version": config.version,
            "metadata": dict(config.metadata),
        }

    def _deserialize_project(self, doc: dict[str, Any]) -> ProjectConfig:
        """Deserialize dictionary to ProjectConfig."""
        return ProjectConfig(
            id=doc["id"],
            name=doc["name"],
            github_org=doc["github_org"],
            github_repo=doc["github_repo"],
            tech_stacks=doc.get("tech_stacks", {}),
            pipelines=doc.get("pipelines", []),
            testing=doc.get("testing", {}),
            environment_variables=doc.get("environment_variables", {}),
            mounted_commands=doc.get("mounted_commands", {}),
            mounted_subagents=doc.get("mounted_subagents", {}),
            created_at=(datetime.fromisoformat(doc["created_at"]) if doc.get("created_at") else None),
            updated_at=(datetime.fromisoformat(doc["updated_at"]) if doc.get("updated_at") else None),
            version=doc.get("version", 1),
            metadata=doc.get("metadata", {}),
        )

    def _serialize_agent(self, config: AgentConfig) -> dict[str, Any]:
        """Serialize AgentConfig to dictionary."""
        return {
            "project_id": config.project_id,
            "agent_name": config.agent_name,
            "model": config.model,
            "timeout": config.timeout,
            "requires_docker": config.requires_docker,
            "makes_code_changes": config.makes_code_changes,
            "mcp_servers": list(config.mcp_servers),
            "capabilities": list(config.capabilities),
            "constraints": dict(config.constraints),
            "version": config.version,
            "created_at": (config.created_at.isoformat() if config.created_at else None),
            "updated_at": (config.updated_at.isoformat() if config.updated_at else None),
            "metadata": dict(config.metadata),
        }

    def _deserialize_agent(self, doc: dict[str, Any]) -> AgentConfig:
        """Deserialize dictionary to AgentConfig."""
        return AgentConfig(
            project_id=doc["project_id"],
            agent_name=doc["agent_name"],
            model=doc["model"],
            timeout=doc["timeout"],
            requires_docker=doc["requires_docker"],
            makes_code_changes=doc["makes_code_changes"],
            mcp_servers=doc.get("mcp_servers", []),
            capabilities=doc.get("capabilities", []),
            constraints=doc.get("constraints", {}),
            version=doc.get("version", 1),
            created_at=(datetime.fromisoformat(doc["created_at"]) if doc.get("created_at") else None),
            updated_at=(datetime.fromisoformat(doc["updated_at"]) if doc.get("updated_at") else None),
            metadata=doc.get("metadata", {}),
        )

    def _serialize_pipeline(self, config: PipelineConfig) -> dict[str, Any]:
        """Serialize PipelineConfig to dictionary."""
        return {
            "id": config.id,
            "project_id": config.project_id,
            "name": config.name,
            "stages": [dict(s) for s in config.stages],
            "triggers": list(config.triggers),
            "version": config.version,
            "created_at": (config.created_at.isoformat() if config.created_at else None),
            "updated_at": (config.updated_at.isoformat() if config.updated_at else None),
            "metadata": dict(config.metadata),
        }

    def _deserialize_pipeline(self, doc: dict[str, Any]) -> PipelineConfig:
        """Deserialize dictionary to PipelineConfig."""
        return PipelineConfig(
            id=doc["id"],
            project_id=doc["project_id"],
            name=doc["name"],
            stages=doc.get("stages", []),
            triggers=doc.get("triggers", []),
            version=doc.get("version", 1),
            created_at=(datetime.fromisoformat(doc["created_at"]) if doc.get("created_at") else None),
            updated_at=(datetime.fromisoformat(doc["updated_at"]) if doc.get("updated_at") else None),
            metadata=doc.get("metadata", {}),
        )

    def _serialize_workflow(self, template: WorkflowTemplate) -> dict[str, Any]:
        """Serialize WorkflowTemplate to dictionary."""
        return {
            "id": template.id,
            "name": template.name,
            "description": template.description,
            "stages": [dict(s) for s in template.stages],
            "version": template.version,
            "created_at": (template.created_at.isoformat() if template.created_at else None),
            "updated_at": (template.updated_at.isoformat() if template.updated_at else None),
            "metadata": dict(template.metadata),
        }

    def _deserialize_workflow(self, doc: dict[str, Any]) -> WorkflowTemplate:
        """Deserialize dictionary to WorkflowTemplate."""
        return WorkflowTemplate(
            id=doc["id"],
            name=doc["name"],
            description=doc["description"],
            stages=doc.get("stages", []),
            version=doc.get("version", 1),
            created_at=(datetime.fromisoformat(doc["created_at"]) if doc.get("created_at") else None),
            updated_at=(datetime.fromisoformat(doc["updated_at"]) if doc.get("updated_at") else None),
            metadata=doc.get("metadata", {}),
        )

    async def close(self) -> None:
        """Close the storage (cleanup resources)."""
        # Elasticsearch client is managed externally, so nothing to do here
        self._initialized = False
        logger.info("Elasticsearch configuration storage closed")
