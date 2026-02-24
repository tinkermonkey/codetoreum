"""Configuration resource client"""
from typing import Any, Optional, TYPE_CHECKING, cast
from ..exceptions import CodetoreumError

if TYPE_CHECKING:
    from ..client import CodetoreumClient


class ConfigurationResource:
    """Client for configuration endpoints."""

    def __init__(self, client: "CodetoreumClient") -> None:
        self.client = client

    def get_project(self, project_id: str) -> dict[str, Any]:
        """
        Get project configuration by ID.

        Args:
            project_id: Project ID

        Returns:
            Project configuration dictionary

        Raises:
            ValueError: If project_id is empty
            CodetoreumError: If project not found or request fails

        Example:
            >>> config = client.config.get_project("my-project")
            >>> print(f"Repository: {config['repository_url']}")
        """
        if not project_id or not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("project_id must be a non-empty string")

        return self.client.get(f"/api/v2/config/projects/{project_id}")

    def list_projects(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """
        List all project configurations.

        Args:
            limit: Maximum number of results (default: 100)
            offset: Number of results to skip (default: 0)

        Returns:
            Dictionary with 'projects' list and pagination info

        Example:
            >>> result = client.config.list_projects(limit=50)
            >>> for project in result['projects']:
            ...     print(f"{project['id']}: {project['name']}")
        """
        params = {"limit": limit, "offset": offset}
        data = self.client.get("/api/v2/config/projects", params=params)
        return data

    def create_project(
        self,
        project_id: str,
        name: str,
        repository_url: str,
        branch: str = "main",
        **config: Any
    ) -> dict[str, Any]:
        """
        Create a new project configuration.

        Args:
            project_id: Unique project identifier
            name: Project display name
            repository_url: Git repository URL
            branch: Default branch (default: "main")
            **config: Additional configuration options

        Returns:
            Created project configuration

        Raises:
            ValueError: If required parameters are missing or invalid
            CodetoreumError: If API request fails

        Example:
            >>> project = client.config.create_project(
            ...     project_id="my-api",
            ...     name="My API Project",
            ...     repository_url="https://github.com/user/my-api",
            ...     branch="main",
            ...     default_workflow_id="workflow_123"
            ... )
        """
        if not project_id or not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("project_id must be a non-empty string")
        if not name or not isinstance(name, str) or not name.strip():
            raise ValueError("name must be a non-empty string")
        if not repository_url or not isinstance(repository_url, str) or not repository_url.strip():
            raise ValueError("repository_url must be a non-empty string")

        payload = {
            "project_id": project_id.strip(),
            "name": name.strip(),
            "repository_url": repository_url.strip(),
            "branch": branch,
        }
        payload.update(config)

        return self.client.post("/api/v2/config/projects", json=payload)

    def update_project(
        self,
        project_id: str,
        name: Optional[str] = None,
        repository_url: Optional[str] = None,
        branch: Optional[str] = None,
        **updates: Any
    ) -> dict[str, Any]:
        """
        Update project configuration.

        Args:
            project_id: Project ID
            name: New project name (optional)
            repository_url: New repository URL (optional)
            branch: New default branch (optional)
            **updates: Additional fields to update

        Returns:
            Updated project configuration

        Raises:
            ValueError: If project_id is empty or parameters are invalid
            CodetoreumError: If project not found or request fails

        Example:
            >>> config = client.config.update_project(
            ...     "my-project",
            ...     name="Updated Project Name",
            ...     branch="develop"
            ... )
        """
        if not project_id or not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("project_id must be a non-empty string")

        payload = {}

        if name is not None:
            if not isinstance(name, str) or not name.strip():
                raise ValueError("name must be a non-empty string")
            payload["name"] = name.strip()

        if repository_url is not None:
            if not isinstance(repository_url, str) or not repository_url.strip():
                raise ValueError("repository_url must be a non-empty string")
            payload["repository_url"] = repository_url.strip()

        if branch is not None:
            if not isinstance(branch, str) or not branch.strip():
                raise ValueError("branch must be a non-empty string")
            payload["branch"] = branch.strip()

        payload.update(updates)

        if not payload:
            raise ValueError("At least one field must be provided for update")

        return self.client.patch(f"/api/v2/config/projects/{project_id}", json=payload)

    def delete_project(self, project_id: str) -> dict[str, Any]:
        """
        Delete a project configuration.

        Args:
            project_id: Project ID

        Returns:
            Deletion confirmation

        Raises:
            ValueError: If project_id is empty
            CodetoreumError: If project not found or request fails

        Example:
            >>> result = client.config.delete_project("my-project")
            >>> print(result["message"])
        """
        if not project_id or not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("project_id must be a non-empty string")

        return self.client.delete(f"/api/v2/config/projects/{project_id}")

    def get_env_vars(self, project_id: str) -> list[dict[str, Any]]:
        """
        Get environment variables for a project.

        Args:
            project_id: Project ID

        Returns:
            List of environment variable configurations

        Raises:
            ValueError: If project_id is empty
            CodetoreumError: If project not found or request fails

        Example:
            >>> env_vars = client.config.get_env_vars("my-project")
            >>> for var in env_vars:
            ...     print(f"{var['name']}: {'*' * len(var.get('value', ''))}")
        """
        if not project_id or not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("project_id must be a non-empty string")

        data = self.client.get(f"/api/v2/config/projects/{project_id}/env-vars")
        return cast(list[dict[str, Any]], data.get("env_vars", []))

    def set_env_var(
        self,
        project_id: str,
        name: str,
        value: str,
        is_secret: bool = False
    ) -> dict[str, Any]:
        """
        Set an environment variable for a project.

        Args:
            project_id: Project ID
            name: Environment variable name
            value: Environment variable value
            is_secret: Whether this is a secret value (will be masked in logs)

        Returns:
            Created/updated environment variable configuration

        Raises:
            ValueError: If required parameters are missing or invalid
            CodetoreumError: If API request fails

        Example:
            >>> client.config.set_env_var(
            ...     "my-project",
            ...     "API_KEY",
            ...     "secret_key_value",
            ...     is_secret=True
            ... )
        """
        if not project_id or not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("project_id must be a non-empty string")
        if not name or not isinstance(name, str) or not name.strip():
            raise ValueError("name must be a non-empty string")
        if not isinstance(value, str):
            raise ValueError("value must be a string")

        payload = {
            "name": name.strip(),
            "value": value,
            "is_secret": is_secret
        }

        return self.client.post(
            f"/api/v2/config/projects/{project_id}/env-vars",
            json=payload
        )

    def delete_env_var(self, project_id: str, name: str) -> dict[str, Any]:
        """
        Delete an environment variable from a project.

        Args:
            project_id: Project ID
            name: Environment variable name

        Returns:
            Deletion confirmation

        Raises:
            ValueError: If required parameters are empty
            CodetoreumError: If project/variable not found or request fails

        Example:
            >>> result = client.config.delete_env_var("my-project", "OLD_API_KEY")
            >>> print(result["message"])
        """
        if not project_id or not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("project_id must be a non-empty string")
        if not name or not isinstance(name, str) or not name.strip():
            raise ValueError("name must be a non-empty string")

        return self.client.delete(f"/api/v2/config/projects/{project_id}/env-vars/{name}")
