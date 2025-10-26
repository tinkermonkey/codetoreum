# IConfigStore Output Port Design

## Overview

The `IConfigStore` port provides an abstraction for configuration storage and retrieval. This replaces the legacy YAML-based configuration with Elasticsearch-backed, web-editable configuration.

**Storage Architecture**: Elasticsearch with Redis caching:
```
Application → IConfigStore → Redis Cache (read) → Elasticsearch (source of truth)
                          ↓
                    Write-through to both Redis & Elasticsearch
```

**Production Implementation**: `ElasticsearchConfigStore` with `RedisConfigCache`
**Testing Implementation**: `InMemoryConfigStore`

**Key Features**:
- **Versioning**: All configuration changes create new versions
- **History**: Complete audit trail of configuration changes
- **Search**: Full-text search across all configurations
- **Caching**: Hot configurations cached for sub-millisecond access

## Port Interface

```python
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

class IConfigStore(ABC):
    """Interface for configuration storage."""

    @abstractmethod
    async def get_project_config(self, project_id: str) -> ProjectConfig:
        """Get project configuration."""
        pass

    @abstractmethod
    async def save_project_config(self, config: ProjectConfig) -> None:
        """Save project configuration."""
        pass

    @abstractmethod
    async def get_agent_config(self,
                               project_id: str,
                               agent_name: str) -> AgentConfig:
        """Get agent configuration for a project."""
        pass

    @abstractmethod
    async def save_agent_config(self, config: AgentConfig) -> None:
        """Save agent configuration."""
        pass

    @abstractmethod
    async def get_workflow_template(self, template_name: str) -> WorkflowTemplate:
        """Get workflow template."""
        pass

    @abstractmethod
    async def list_projects(self) -> List[ProjectConfig]:
        """List all projects."""
        pass

    @abstractmethod
    async def search_configs(self,
                            query: str,
                            config_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search configurations."""
        pass

    @abstractmethod
    async def get_config_version(self,
                                 config_id: str,
                                 version: int) -> Dict[str, Any]:
        """Get specific version of configuration."""
        pass

    @abstractmethod
    async def list_config_versions(self, config_id: str) -> List[ConfigVersion]:
        """List all versions of a configuration."""
        pass
```

## Data Models

```python
@dataclass
class ProjectConfig:
    """Project configuration."""
    id: str
    name: str
    github_org: str
    github_repo: str
    tech_stacks: Dict[str, str]
    pipelines: List[PipelineConfig]
    testing: TestConfig
    created_at: datetime
    updated_at: datetime
    version: int

@dataclass
class AgentConfig:
    """Agent configuration."""
    project_id: str
    agent_name: str
    model: str
    timeout: int
    requires_docker: bool
    makes_code_changes: bool
    mcp_servers: List[str]
    version: int
```

## Adapter Implementations

### Elasticsearch Config Store with Redis Caching (Production)

The production implementation uses **Elasticsearch for persistence** with **Redis for caching**:

```python
class ElasticsearchConfigStore(IConfigStore):
    """
    Production config store using Elasticsearch with Redis caching.

    Architecture:
    - Write-through cache: Writes go to both Elasticsearch and Redis
    - Read strategy: Check Redis first, fall back to Elasticsearch
    - Cache invalidation: Pub/sub pattern for distributed cache invalidation
    - Versioning: New writes create new document versions in Elasticsearch

    This provides:
    - Fast reads (Redis cache: < 1ms)
    - Durable storage (Elasticsearch persistence)
    - Full-text search (Elasticsearch capabilities)
    - Configuration history (versioned documents)
    """

    def __init__(
        self,
        es_client,
        redis_client,
        index_prefix: str = "config",
        cache_ttl: int = 3600
    ):
        self.es = es_client
        self.redis = redis_client
        self.index_prefix = index_prefix
        self.cache_ttl = cache_ttl

    async def get_project_config(self, project_id: str) -> ProjectConfig:
        """
        Get project config with caching.

        Flow:
        1. Check Redis cache
        2. On cache miss, query Elasticsearch
        3. Populate cache for future reads
        """
        # Check cache first
        cache_key = f"config:project:{project_id}"
        cached = await self.redis.get(cache_key)

        if cached:
            return ProjectConfig(**json.loads(cached))

        # Cache miss - query Elasticsearch
        query = {
            "bool": {
                "must": [
                    {"term": {"project_id": project_id}},
                    {"term": {"is_active": True}}
                ]
            }
        }

        response = await self.es.search(
            index=f"{self.index_prefix}-projects",
            query=query,
            sort=[{"version": "desc"}],
            size=1
        )

        if not response["hits"]["hits"]:
            raise ConfigNotFoundError(f"Project {project_id} not found")

        doc = response["hits"]["hits"][0]["_source"]
        config = ProjectConfig(**doc)

        # Populate cache
        await self.redis.setex(
            cache_key,
            self.cache_ttl,
            json.dumps(config.to_dict())
        )

        return config

    async def save_project_config(self, config: ProjectConfig) -> None:
        """
        Save project config with write-through caching.

        Flow:
        1. Write to Elasticsearch (create new version)
        2. Update Redis cache
        3. Publish cache invalidation event
        """
        # Get current version
        current = await self._get_latest_version(
            "projects",
            config.project_id
        )

        # Increment version
        config.version = (current.version + 1) if current else 1
        config.updated_at = datetime.utcnow()

        # Write to Elasticsearch (source of truth)
        doc_id = f"{config.project_id}-v{config.version}"
        await self.es.index(
            index=f"{self.index_prefix}-projects",
            id=doc_id,
            document=config.to_dict()
        )

        # Record change in history
        await self._record_config_change(
            "project",
            config.project_id,
            config.version,
            config.updated_by
        )

        # Update cache (write-through)
        cache_key = f"config:project:{config.project_id}"
        await self.redis.setex(
            cache_key,
            self.cache_ttl,
            json.dumps(config.to_dict())
        )

        # Broadcast cache invalidation to other nodes
        await self.redis.publish(
            "config:invalidate",
            json.dumps({
                "type": "project",
                "id": config.project_id
            })
        )

    async def search_configs(
        self,
        query: str,
        config_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Full-text search across configurations.

        Uses Elasticsearch query_string syntax for powerful searches:
        - "agent:reviewer AND status:active"
        - "workflow AND (python OR javascript)"
        - name:*test*
        """
        indices = []
        if config_type:
            indices = [f"{self.index_prefix}-{config_type}"]
        else:
            indices = [f"{self.index_prefix}-*"]

        es_query = {
            "bool": {
                "must": [
                    {"query_string": {"query": query}},
                    {"term": {"is_active": True}}
                ]
            }
        }

        response = await self.es.search(
            index=indices,
            query=es_query,
            size=100,
            sort=[{"updated_at": "desc"}]
        )

        return [hit["_source"] for hit in response["hits"]["hits"]]

    async def get_config_history(
        self,
        config_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get configuration change history."""
        query = {"term": {"config_id": config_id}}

        response = await self.es.search(
            index=f"{self.index_prefix}-history",
            query=query,
            sort=[{"changed_at": "desc"}],
            size=limit
        )

        return [hit["_source"] for hit in response["hits"]["hits"]]

    async def rollback_config(
        self,
        config_id: str,
        to_version: int
    ) -> None:
        """
        Rollback configuration to a previous version.

        Strategy:
        1. Fetch specified historical version from Elasticsearch
        2. Create new version with historical data
        3. Mark as rollback in metadata
        """
        # Get historical version
        doc_id = f"{config_id}-v{to_version}"
        result = await self.es.get(
            index=f"{self.index_prefix}-*",
            id=doc_id
        )

        historical_config = result["_source"]

        # Create new version with historical data
        # (versioning handled in save_project_config)
        config = ProjectConfig(**historical_config)
        config.metadata = {
            **config.metadata,
            "rollback": True,
            "rollback_from_version": to_version
        }

        await self.save_project_config(config)

    async def _record_config_change(
        self,
        config_type: str,
        config_id: str,
        new_version: int,
        changed_by: str
    ) -> None:
        """Record configuration change in history index."""
        await self.es.index(
            index=f"{self.index_prefix}-history",
            document={
                "config_type": config_type,
                "config_id": config_id,
                "new_version": new_version,
                "changed_by": changed_by,
                "changed_at": datetime.utcnow().isoformat()
            }
        )
```

**Cache Invalidation Subscriber** (runs in each application instance):
```python
class ConfigCacheInvalidationSubscriber:
    """
    Listens for cache invalidation events and updates local cache.

    Ensures cache consistency across multiple application instances.
    """

    def __init__(self, redis_client):
        self.redis = redis_client

    async def subscribe_and_invalidate(self):
        """Subscribe to invalidation channel."""
        pubsub = self.redis.pubsub()
        await pubsub.subscribe("config:invalidate")

        async for message in pubsub.listen():
            if message["type"] == "message":
                data = json.loads(message["data"])
                config_type = data["type"]
                config_id = data["id"]

                # Invalidate local cache
                cache_key = f"config:{config_type}:{config_id}"
                await self.redis.delete(cache_key)

                logger.info(f"Invalidated cache for {config_type}:{config_id}")
```

### In-Memory Config Store (Testing)

```python
class InMemoryConfigStore(IConfigStore):
    """In-memory configuration for testing."""

    def __init__(self):
        self.projects: Dict[str, ProjectConfig] = {}
        self.agents: Dict[str, Dict[str, AgentConfig]] = {}

    async def get_project_config(self, project_id: str) -> ProjectConfig:
        """Get from memory."""
        if project_id not in self.projects:
            raise ConfigNotFoundError(project_id)
        return self.projects[project_id]
```

## Integration Points

### Used By
- All Application Services
- Configuration Management UI
- Migration Tools

### Dependencies
- None (standalone port)

## Implementation Notes

1. **Versioning**: Track all configuration changes
2. **Validation**: Validate configurations against schemas
3. **Migration**: Support migration from YAML to database
4. **Caching**: Cache frequently accessed configurations
5. **Audit**: Log all configuration changes
