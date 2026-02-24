"""Common test fixtures and utilities for integration tests."""

import pytest
from typing import Any, Dict, List, Optional
from codetoreum.ports.output.config_store import (
    IConfigStore,
    ProjectConfig,
    AgentConfig,
    PipelineConfig,
    WorkflowTemplate,
    ConfigVersion,
    ConfigNotFoundError,
)

# Set default timeout for all integration tests to prevent hanging
pytestmark = pytest.mark.timeout(30)


class MockConfigService(IConfigStore):
    """Mock configuration service for testing."""

    async def get_project_config(self, project_id: str) -> ProjectConfig:
        return None

    async def get_project_config_by_name(self, project_name: str) -> ProjectConfig:
        return None

    async def save_project_config(self, config: ProjectConfig) -> None:
        pass

    async def get_agent_config(self, project_id: str, agent_name: str) -> AgentConfig:
        return None

    async def save_agent_config(self, config: AgentConfig) -> None:
        pass

    async def get_pipeline_config(self, project_id: str, pipeline_name: str) -> PipelineConfig:
        return None

    async def save_pipeline_config(self, config: PipelineConfig) -> None:
        pass

    async def get_workflow_template(self, template_name: str) -> WorkflowTemplate:
        raise ConfigNotFoundError(f"Workflow template '{template_name}' not found")

    async def save_workflow_template(self, template: WorkflowTemplate) -> None:
        pass

    async def list_projects(self) -> List[ProjectConfig]:
        return []

    async def list_agents(self, project_id: str) -> List[AgentConfig]:
        return []

    async def list_pipelines(self, project_id: str) -> List[PipelineConfig]:
        return []

    async def search_configs(self, query: str, config_type: Optional[str] = None) -> List[Dict[str, Any]]:
        return []

    async def get_config_version(self, config_id: str, version: int) -> Dict[str, Any]:
        return {}

    async def list_config_versions(self, config_id: str, limit: int = 10) -> List[ConfigVersion]:
        return []

    async def delete_project_config(self, project_id: str) -> None:
        pass

    async def delete_agent_config(self, project_id: str, agent_name: str) -> None:
        pass

    async def exists(self, project_id: str) -> bool:
        return False
