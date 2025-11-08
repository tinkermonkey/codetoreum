"""Mock Configuration Service Interface Adapter for FastAPI.

This adapter wraps the ConfigurationService to provide the specific interface
expected by the FastAPI application layer.
"""


class MockConfigServiceAdapter:
    """
    Mock configuration service interface adapter.

    Wraps ConfigurationService to provide the interface expected by FastAPI,
    delegating all calls to the underlying service.
    """

    def __init__(self, config_service):
        """
        Initialize adapter with configuration service.

        Args:
            config_service: ConfigurationService instance to wrap
        """
        self._config_service = config_service

    async def get_project_config(self, project_id: str):
        """Get project configuration by ID."""
        return await self._config_service.get_project_config(project_id)

    async def get_project_config_by_name(self, project_name: str):
        """Get project configuration by name."""
        return await self._config_service.get_project_config_by_name(project_name)

    async def save_project_config(self, config) -> None:
        """Save project configuration."""
        await self._config_service.save_project_config(config)

    async def get_agent_config(self, project_id: str, agent_name: str):
        """Get agent configuration."""
        return await self._config_service.get_agent_config(project_id, agent_name)

    async def save_agent_config(self, config) -> None:
        """Save agent configuration."""
        await self._config_service.save_agent_config(config)

    async def get_pipeline_config(self, project_id: str, pipeline_name: str):
        """Get pipeline configuration."""
        return await self._config_service.get_pipeline_config(
            project_id, pipeline_name
        )

    async def save_pipeline_config(self, config) -> None:
        """Save pipeline configuration."""
        await self._config_service.save_pipeline_config(config)

    async def exists(self, project_id: str) -> bool:
        """Check if project configuration exists."""
        return await self._config_service.exists(project_id)
