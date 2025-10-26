# IConfigStore Output Port Design

## Overview

The `IConfigStore` port provides an abstraction for configuration storage and retrieval. This replaces the legacy YAML-based configuration with database-backed, web-editable configuration.

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

### Elasticsearch Config Store

```python
class ElasticsearchConfigStore(IConfigStore):
    """Elasticsearch-based configuration storage."""

    def __init__(self, es_client, index_prefix: str = "config"):
        self.es = es_client
        self.index_prefix = index_prefix

    async def get_project_config(self, project_id: str) -> ProjectConfig:
        """Get from Elasticsearch."""
        result = await self.es.get(
            index=f"{self.index_prefix}-projects",
            id=project_id
        )
        return ProjectConfig(**result['_source'])
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
