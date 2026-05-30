"""Redis configuration cache for fast access to frequently used configurations."""

import asyncio
import json
import logging
from typing import Any

from redis import asyncio as aioredis

from codetoreum.ports.output.config_store import (
    AgentConfig,
    PipelineConfig,
    ProjectConfig,
    WorkflowTemplate,
)

logger = logging.getLogger(__name__)


class RedisConfigCacheError(Exception):
    """Raised when Redis config cache operations fail."""


class RedisConfigCache:
    """
    Redis-backed cache for configuration storage.

    Provides:
    - Write-through caching for configuration updates
    - Cache invalidation on updates (pub/sub pattern)
    - TTL-based expiration with automatic refresh
    - Monitoring of cache hit rates
    - Buffering layer between application and Elasticsearch

    Architecture:
        Application → Redis Cache → Elasticsearch (on cache miss)
                          ↓
                    Pub/Sub for invalidation notifications

    Cache keys pattern:
    - config:project:{project_id}
    - config:project:name:{project_name}
    - config:agent:{project_id}:{agent_name}
    - config:pipeline:{project_id}:{pipeline_name}
    - config:workflow:{template_name}
    - config:list:projects
    - config:list:agents:{project_id}
    - config:list:pipelines:{project_id}
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        key_prefix: str = "config",
        default_ttl: int = 3600,  # 1 hour default TTL
        invalidation_channel: str = "config:invalidation",
    ):
        """
        Initialize Redis configuration cache.

        Args:
            redis_client: Redis async client
            key_prefix: Prefix for all cache keys
            default_ttl: Default TTL for cached configurations in seconds
            invalidation_channel: Redis pub/sub channel for cache invalidation
        """
        self.redis = redis_client
        self.key_prefix = key_prefix
        self.default_ttl = default_ttl
        self.invalidation_channel = invalidation_channel

        self._pubsub: aioredis.client.PubSub | None = None
        self._listener_task: asyncio.Task | None = None
        self._initialized = False
        self._init_lock = asyncio.Lock()  # Prevent concurrent initialization
        self._listener_healthy = True  # Health flag for invalidation listener
        self._listener_error_count = 0  # Track consecutive errors
        self._stats = {
            "hits": 0,
            "misses": 0,
            "writes": 0,
            "invalidations": 0,
        }
        self._stats_lock = asyncio.Lock()  # Thread-safe statistics

    async def initialize(self) -> None:
        """
        Initialize the cache (set up pub/sub listener).

        This method is safe to call concurrently - only one initialization will occur.

        Raises:
            RedisConfigCacheError: If initialization fails
        """
        # Use lock to prevent concurrent initialization
        async with self._init_lock:
            if self._initialized:
                return

            try:
                # Set up pub/sub for cache invalidation
                self._pubsub = self.redis.pubsub()
                await self._pubsub.subscribe(self.invalidation_channel)

                # Start listener task
                self._listener_task = asyncio.create_task(self._listen_for_invalidations())

                self._initialized = True
                logger.info("Redis configuration cache initialized")

            except Exception as e:
                message = f"Failed to initialize cache: {e}"
                raise RedisConfigCacheError(message) from e

    async def _listen_for_invalidations(self) -> None:
        """Listen for cache invalidation messages with automatic recovery."""
        retry_delay = 1.0
        max_retry_delay = 60.0
        consecutive_errors = 0

        try:
            while self._initialized:
                try:
                    message = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if message and message["type"] == "message":
                        key_pattern = message["data"].decode("utf-8")
                        await self._handle_invalidation(key_pattern)

                    # Reset error tracking on successful message processing
                    if message:
                        consecutive_errors = 0
                        retry_delay = 1.0
                        if not self._listener_healthy:
                            self._listener_healthy = True
                            self._listener_error_count = 0
                            logger.info(
                                "Cache invalidation listener recovered", extra={"error_id": "INFO_LISTENER_RECOVERED"}
                            )

                except Exception as e:
                    consecutive_errors += 1
                    self._listener_error_count = consecutive_errors
                    self._listener_healthy = False

                    logger.error(
                        f"Error in cache invalidation listener (attempt {consecutive_errors}): {e}",
                        exc_info=True,
                        extra={
                            "error_id": "ERR_CACHE_INVALIDATION_LISTENER_FAILED",
                            "attempt": consecutive_errors,
                        },
                    )

                    # Wait with exponential backoff before retrying
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2.0, max_retry_delay)

        except asyncio.CancelledError:
            logger.info("Cache invalidation listener cancelled")
        finally:
            self._listener_healthy = False

    async def _handle_invalidation(self, key_pattern: str) -> None:
        """
        Handle cache invalidation message.

        Args:
            key_pattern: Pattern of keys to invalidate (supports wildcards)
        """
        try:
            # Delete keys matching pattern
            if "*" in key_pattern:
                # Use SCAN to find keys matching pattern
                cursor = 0
                while True:
                    cursor, keys = await self.redis.scan(cursor=cursor, match=key_pattern, count=100)
                    if keys:
                        await self.redis.delete(*keys)
                        logger.debug(f"Invalidated {len(keys)} keys matching {key_pattern}")
                    if cursor == 0:
                        break
            else:
                # Delete single key
                await self.redis.delete(key_pattern)
                logger.debug(f"Invalidated key: {key_pattern}")

            async with self._stats_lock:
                self._stats["invalidations"] += 1

        except Exception as e:
            logger.error(
                f"Failed to invalidate cache for {key_pattern}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_CACHE_INVALIDATION_FAILED", "key_pattern": key_pattern},
            )

    def _make_key(self, *parts: str) -> str:
        """Create cache key from parts."""
        return ":".join([self.key_prefix] + list(parts))

    async def get_project_config(self, project_id: str) -> ProjectConfig | None:
        """
        Get project configuration from cache.

        Args:
            project_id: Project identifier

        Returns:
            ProjectConfig if found in cache, None otherwise
        """
        if not self._initialized:
            await self.initialize()

        try:
            key = self._make_key("project", project_id)
            data = await self.redis.get(key)

            if data:
                async with self._stats_lock:
                    self._stats["hits"] += 1
                config_dict = json.loads(data)
                return self._deserialize_project(config_dict)

            async with self._stats_lock:
                self._stats["misses"] += 1
            return None

        except Exception as e:
            logger.warning(
                f"Failed to get project config from cache: {e}",
                exc_info=True,
                extra={"error_id": "WARN_GET_PROJECT_CONFIG_FAILED"},
            )
            async with self._stats_lock:
                self._stats["misses"] += 1
            return None

    async def get_project_config_by_name(self, project_name: str) -> ProjectConfig | None:
        """
        Get project configuration from cache by name.

        Args:
            project_name: Project name

        Returns:
            ProjectConfig if found in cache, None otherwise
        """
        if not self._initialized:
            await self.initialize()

        try:
            key = self._make_key("project", "name", project_name)
            data = await self.redis.get(key)

            if data:
                async with self._stats_lock:
                    self._stats["hits"] += 1
                config_dict = json.loads(data)
                return self._deserialize_project(config_dict)

            async with self._stats_lock:
                self._stats["misses"] += 1
            return None

        except Exception as e:
            logger.warning(
                f"Failed to get project config by name from cache: {e}",
                exc_info=True,
                extra={"error_id": "WARN_GET_PROJECT_CONFIG_BY_NAME_FAILED"},
            )
            async with self._stats_lock:
                self._stats["misses"] += 1
            return None

    async def set_project_config(self, config: ProjectConfig, ttl: int | None = None) -> None:
        """
        Set project configuration in cache.

        Args:
            config: ProjectConfig to cache
            ttl: Time-to-live in seconds (uses default if not provided)
        """
        if not self._initialized:
            await self.initialize()

        try:
            ttl = ttl or self.default_ttl
            config_dict = self._serialize_project(config)
            data = json.dumps(config_dict)

            # Cache by ID
            key_id = self._make_key("project", config.id)
            await self.redis.setex(key_id, ttl, data)

            # Cache by name
            key_name = self._make_key("project", "name", config.name)
            await self.redis.setex(key_name, ttl, data)

            async with self._stats_lock:
                self._stats["writes"] += 1
            logger.debug(f"Cached project config: {config.id}")

        except Exception as e:
            logger.warning(
                f"Failed to cache project config: {e}",
                exc_info=True,
                extra={"error_id": "WARN_SET_PROJECT_CONFIG_FAILED"},
            )

    async def get_agent_config(self, project_id: str, agent_name: str) -> AgentConfig | None:
        """
        Get agent configuration from cache.

        Args:
            project_id: Project identifier
            agent_name: Agent name

        Returns:
            AgentConfig if found in cache, None otherwise
        """
        if not self._initialized:
            await self.initialize()

        try:
            key = self._make_key("agent", project_id, agent_name)
            data = await self.redis.get(key)

            if data:
                async with self._stats_lock:
                    self._stats["hits"] += 1
                config_dict = json.loads(data)
                return self._deserialize_agent(config_dict)

            async with self._stats_lock:
                self._stats["misses"] += 1
            return None

        except Exception as e:
            logger.warning(
                f"Failed to get agent config from cache: {e}",
                exc_info=True,
                extra={"error_id": "WARN_GET_AGENT_CONFIG_FAILED"},
            )
            async with self._stats_lock:
                self._stats["misses"] += 1
            return None

    async def set_agent_config(self, config: AgentConfig, ttl: int | None = None) -> None:
        """
        Set agent configuration in cache.

        Args:
            config: AgentConfig to cache
            ttl: Time-to-live in seconds (uses default if not provided)
        """
        if not self._initialized:
            await self.initialize()

        try:
            ttl = ttl or self.default_ttl
            config_dict = self._serialize_agent(config)
            data = json.dumps(config_dict)

            key = self._make_key("agent", config.project_id, config.agent_name)
            await self.redis.setex(key, ttl, data)

            async with self._stats_lock:
                self._stats["writes"] += 1
            logger.debug(f"Cached agent config: {config.project_id}/{config.agent_name}")

        except Exception as e:
            logger.warning(
                f"Failed to cache agent config: {e}",
                exc_info=True,
                extra={"error_id": "WARN_SET_AGENT_CONFIG_FAILED"},
            )

    async def get_pipeline_config(self, project_id: str, pipeline_name: str) -> PipelineConfig | None:
        """
        Get pipeline configuration from cache.

        Args:
            project_id: Project identifier
            pipeline_name: Pipeline name

        Returns:
            PipelineConfig if found in cache, None otherwise
        """
        if not self._initialized:
            await self.initialize()

        try:
            key = self._make_key("pipeline", project_id, pipeline_name)
            data = await self.redis.get(key)

            if data:
                async with self._stats_lock:
                    self._stats["hits"] += 1
                config_dict = json.loads(data)
                return self._deserialize_pipeline(config_dict)

            async with self._stats_lock:
                self._stats["misses"] += 1
            return None

        except Exception as e:
            logger.warning(
                f"Failed to get pipeline config from cache: {e}",
                exc_info=True,
                extra={"error_id": "WARN_GET_PIPELINE_CONFIG_FAILED"},
            )
            async with self._stats_lock:
                self._stats["misses"] += 1
            return None

    async def set_pipeline_config(self, config: PipelineConfig, ttl: int | None = None) -> None:
        """
        Set pipeline configuration in cache.

        Args:
            config: PipelineConfig to cache
            ttl: Time-to-live in seconds (uses default if not provided)
        """
        if not self._initialized:
            await self.initialize()

        try:
            ttl = ttl or self.default_ttl
            config_dict = self._serialize_pipeline(config)
            data = json.dumps(config_dict)

            key = self._make_key("pipeline", config.project_id, config.name)
            await self.redis.setex(key, ttl, data)

            async with self._stats_lock:
                self._stats["writes"] += 1
            logger.debug(f"Cached pipeline config: {config.project_id}/{config.name}")

        except Exception as e:
            logger.warning(
                f"Failed to cache pipeline config: {e}",
                exc_info=True,
                extra={"error_id": "WARN_SET_PIPELINE_CONFIG_FAILED"},
            )

    async def get_workflow_template(self, template_name: str) -> WorkflowTemplate | None:
        """
        Get workflow template from cache.

        Args:
            template_name: Template name

        Returns:
            WorkflowTemplate if found in cache, None otherwise
        """
        if not self._initialized:
            await self.initialize()

        try:
            key = self._make_key("workflow", template_name)
            data = await self.redis.get(key)

            if data:
                async with self._stats_lock:
                    self._stats["hits"] += 1
                config_dict = json.loads(data)
                return self._deserialize_workflow(config_dict)

            async with self._stats_lock:
                self._stats["misses"] += 1
            return None

        except Exception as e:
            logger.warning(
                f"Failed to get workflow template from cache: {e}",
                exc_info=True,
                extra={"error_id": "WARN_GET_WORKFLOW_TEMPLATE_FAILED"},
            )
            async with self._stats_lock:
                self._stats["misses"] += 1
            return None

    async def set_workflow_template(self, template: WorkflowTemplate, ttl: int | None = None) -> None:
        """
        Set workflow template in cache.

        Args:
            template: WorkflowTemplate to cache
            ttl: Time-to-live in seconds (uses default if not provided)
        """
        if not self._initialized:
            await self.initialize()

        try:
            ttl = ttl or self.default_ttl
            config_dict = self._serialize_workflow(template)
            data = json.dumps(config_dict)

            key = self._make_key("workflow", template.name)
            await self.redis.setex(key, ttl, data)

            async with self._stats_lock:
                self._stats["writes"] += 1
            logger.debug(f"Cached workflow template: {template.name}")

        except Exception as e:
            logger.warning(
                f"Failed to cache workflow template: {e}",
                exc_info=True,
                extra={"error_id": "WARN_SET_WORKFLOW_TEMPLATE_FAILED"},
            )

    async def invalidate_project(self, project_id: str) -> None:
        """
        Invalidate project configuration cache.

        Args:
            project_id: Project identifier
        """
        try:
            key_pattern = self._make_key("project", project_id)
            key_pattern_name = self._make_key("project", "name", "*")
            key_pattern_list = self._make_key("list", "projects")

            await self._handle_invalidation(key_pattern)
            await self._handle_invalidation(key_pattern_name)
            await self._handle_invalidation(key_pattern_list)

            await self.redis.publish(self.invalidation_channel, key_pattern)
            await self.redis.publish(self.invalidation_channel, key_pattern_name)
            await self.redis.publish(self.invalidation_channel, key_pattern_list)

            logger.debug(f"Invalidated project cache: {project_id}")

        except Exception as e:
            logger.warning(
                f"Failed to invalidate project cache: {e}",
                exc_info=True,
                extra={"error_id": "WARN_INVALIDATE_PROJECT_FAILED"},
            )

    async def invalidate_agent(self, project_id: str, agent_name: str) -> None:
        """
        Invalidate agent configuration cache.

        Args:
            project_id: Project identifier
            agent_name: Agent name
        """
        try:
            key_pattern = self._make_key("agent", project_id, agent_name)
            key_pattern_list = self._make_key("list", "agents", project_id)

            await self._handle_invalidation(key_pattern)
            await self._handle_invalidation(key_pattern_list)

            await self.redis.publish(self.invalidation_channel, key_pattern)
            await self.redis.publish(self.invalidation_channel, key_pattern_list)

            logger.debug(f"Invalidated agent cache: {project_id}/{agent_name}")

        except Exception as e:
            logger.warning(
                f"Failed to invalidate agent cache: {e}",
                exc_info=True,
                extra={"error_id": "WARN_INVALIDATE_AGENT_FAILED"},
            )

    async def invalidate_pipeline(self, project_id: str, pipeline_name: str) -> None:
        """
        Invalidate pipeline configuration cache.

        Args:
            project_id: Project identifier
            pipeline_name: Pipeline name
        """
        try:
            key_pattern = self._make_key("pipeline", project_id, pipeline_name)
            key_pattern_list = self._make_key("list", "pipelines", project_id)

            await self._handle_invalidation(key_pattern)
            await self._handle_invalidation(key_pattern_list)

            await self.redis.publish(self.invalidation_channel, key_pattern)
            await self.redis.publish(self.invalidation_channel, key_pattern_list)

            logger.debug(f"Invalidated pipeline cache: {project_id}/{pipeline_name}")

        except Exception as e:
            logger.warning(
                f"Failed to invalidate pipeline cache: {e}",
                exc_info=True,
                extra={"error_id": "WARN_INVALIDATE_PIPELINE_FAILED"},
            )

    async def invalidate_workflow(self, template_name: str) -> None:
        """
        Invalidate workflow template cache.

        Args:
            template_name: Template name
        """
        try:
            key_pattern = self._make_key("workflow", template_name)

            await self._handle_invalidation(key_pattern)
            await self.redis.publish(self.invalidation_channel, key_pattern)

            logger.debug(f"Invalidated workflow template cache: {template_name}")

        except Exception as e:
            logger.warning(
                f"Failed to invalidate workflow template cache: {e}",
                exc_info=True,
                extra={"error_id": "WARN_INVALIDATE_WORKFLOW_FAILED"},
            )

    async def invalidate_all(self) -> None:
        """Invalidate all configuration cache entries."""
        try:
            key_pattern = self._make_key("*")

            await self._handle_invalidation(key_pattern)
            await self.redis.publish(self.invalidation_channel, key_pattern)

            logger.info("Invalidated all configuration cache")

        except Exception as e:
            logger.warning(
                f"Failed to invalidate all cache: {e}",
                exc_info=True,
                extra={"error_id": "WARN_INVALIDATE_ALL_FAILED"},
            )

    async def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics and health status
        """
        total_requests = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total_requests if total_requests > 0 else 0.0

        return {
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "writes": self._stats["writes"],
            "invalidations": self._stats["invalidations"],
            "total_requests": total_requests,
            "hit_rate": hit_rate,
            "miss_rate": 1.0 - hit_rate,
            "listener_healthy": self._listener_healthy,
            "listener_error_count": self._listener_error_count,
        }

    async def reset_stats(self) -> None:
        """Reset cache statistics."""
        self._stats = {
            "hits": 0,
            "misses": 0,
            "writes": 0,
            "invalidations": 0,
        }
        logger.info("Cache statistics reset")

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
        from datetime import datetime

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
        """Serialize AgentConfig to dictionary.

        DEF-020: legacy flat fields are no longer written. Read paths
        tolerate legacy cached documents so a rolling restart does not
        lose hits.
        """
        return {
            "project_id": config.project_id,
            "agent_name": config.agent_name,
            "makes_code_changes": config.makes_code_changes,
            "mcp_servers": list(config.mcp_servers),
            "capabilities": list(config.capabilities),
            "constraints": dict(config.constraints),
            "version": config.version,
            "created_at": (config.created_at.isoformat() if config.created_at else None),
            "updated_at": (config.updated_at.isoformat() if config.updated_at else None),
            "metadata": dict(config.metadata),
            "coding_agent": config.coding_agent,
            "invocation": {
                "mode": config.invocation.mode.value,
                "model": config.invocation.model,
                "timeout_seconds": config.invocation.timeout_seconds,
                "mode_config": dict(config.invocation.mode_config),
                "cost_limit_usd": (
                    str(config.invocation.cost_limit_usd) if config.invocation.cost_limit_usd is not None else None
                ),
            },
        }

    def _deserialize_agent(self, doc: dict[str, Any]) -> AgentConfig:
        """Deserialize dictionary to AgentConfig.

        DEF-020: cached documents written before the cleanup still have
        the legacy flat fields and no ``invocation`` block. Translate
        them on read; subsequent writes use the new shape.
        """
        from datetime import datetime
        from decimal import Decimal

        from codetoreum.domain.coding_agent_types import AgentInvocationConfig, InvocationMode

        inv_doc = doc.get("invocation")
        invocation: AgentInvocationConfig
        if isinstance(inv_doc, dict):
            cost_raw = inv_doc.get("cost_limit_usd")
            invocation = AgentInvocationConfig(
                mode=InvocationMode(inv_doc["mode"]),
                model=inv_doc["model"],
                timeout_seconds=int(inv_doc["timeout_seconds"]),
                mode_config=dict(inv_doc.get("mode_config", {})),
                cost_limit_usd=Decimal(cost_raw) if cost_raw is not None else None,
            )
        else:
            legacy_requires_docker = bool(doc.get("requires_docker", True))
            invocation = AgentInvocationConfig(
                mode=(InvocationMode.CONTAINERIZED if legacy_requires_docker else InvocationMode.HOST),
                model=str(doc.get("model", "claude-sonnet-4-6")),
                timeout_seconds=int(doc.get("timeout", 3600)),
                mode_config=({"image": "codetoreum-agent:latest"} if legacy_requires_docker else {}),
                cost_limit_usd=None,
            )

        return AgentConfig(
            project_id=doc["project_id"],
            agent_name=doc["agent_name"],
            makes_code_changes=doc["makes_code_changes"],
            mcp_servers=doc.get("mcp_servers", []),
            capabilities=doc.get("capabilities", []),
            constraints=doc.get("constraints", {}),
            version=doc.get("version", 1),
            created_at=(datetime.fromisoformat(doc["created_at"]) if doc.get("created_at") else None),
            updated_at=(datetime.fromisoformat(doc["updated_at"]) if doc.get("updated_at") else None),
            metadata=doc.get("metadata", {}),
            coding_agent=doc.get("coding_agent", ""),
            invocation=invocation,
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
        from datetime import datetime

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
        from datetime import datetime

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
        """Close the cache (cleanup resources)."""
        self._initialized = False

        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

        if self._pubsub:
            await self._pubsub.unsubscribe(self.invalidation_channel)
            await self._pubsub.close()
            self._pubsub = None

        logger.info("Redis configuration cache closed")
