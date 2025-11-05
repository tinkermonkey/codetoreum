"""Configuration resource client"""


class ConfigurationResource:
    """Client for configuration endpoints."""

    def __init__(self, client):
        self.client = client

    def get_project(self, project_id: str) -> dict:
        """Get project configuration."""
        return self.client.get(f"/api/v2/config/projects/{project_id}")

    def list_projects(self) -> list:
        """List all project configurations."""
        data = self.client.get("/api/v2/config/projects")
        return data.get("projects", [])

    def update_project(self, project_id: str, **updates) -> dict:
        """Update project configuration."""
        return self.client.patch(f"/api/v2/config/projects/{project_id}", json=updates)
