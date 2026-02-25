"""
Main Codetoreum client class
"""
from typing import Any, cast
from urllib.parse import urljoin

import requests

from .exceptions import AuthenticationError, CodetoreumError, RateLimitError
from .resources.agents import AgentsResource
from .resources.config import ConfigurationResource
from .resources.events import EventsResource
from .resources.executions import ExecutionsResource
from .resources.metrics import MetricsResource
from .resources.orchestrator import OrchestratorResource
from .resources.work_items import WorkItemsResource
from .resources.workflows import WorkflowsResource
from .resources.workspaces import WorkspacesResource


class CodetoreumClient:
    """
    Main client for interacting with the Codetoreum API.

    Args:
        base_url: Base URL of the Codetoreum API (default: http://localhost:8000)
        api_token: Authentication token (required)
        timeout: Request timeout in seconds (default: 30)
        verify_ssl: Verify SSL certificates (default: True)

    Example:
        >>> client = CodetoreumClient(
        ...     base_url="http://localhost:8000",
        ...     api_token="your_token_here"
        ... )
        >>> work_items = client.work_items.list(status="pending")
    """

    def __init__(
        self,
        api_token: str,
        base_url: str = "http://localhost:8000",
        timeout: int = 30,
        verify_ssl: bool = True,
    ) -> None:
        if not api_token:
            raise ValueError("api_token is required")

        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.timeout = timeout
        self.verify_ssl = verify_ssl

        # Create session with default headers
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "User-Agent": "codetoreum-python-sdk/2.0.0",
        })
        self.session.verify = verify_ssl

        # Initialize resource clients
        self.work_items = WorkItemsResource(self)
        self.agents = AgentsResource(self)
        self.workflows = WorkflowsResource(self)
        self.orchestrator = OrchestratorResource(self)
        self.executions = ExecutionsResource(self)
        self.config = ConfigurationResource(self)
        self.metrics = MetricsResource(self)
        self.workspaces = WorkspacesResource(self)
        self.events = EventsResource(self)

    def _build_url(self, path: str) -> str:
        """Build full URL from path."""
        return urljoin(self.base_url, path)

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> requests.Response:
        """
        Make HTTP request to API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, PATCH)
            path: API path (e.g., /api/v2/work-items/)
            params: Query parameters
            json: JSON body
            timeout: Request timeout (overrides default)

        Returns:
            Response object

        Raises:
            CodetoreumError: On API error
            AuthenticationError: On authentication error
            RateLimitError: On rate limit error
        """
        url = self._build_url(path)
        timeout = timeout or self.timeout

        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json,
                timeout=timeout,
            )

            # Handle errors
            if response.status_code == 401:
                raise AuthenticationError("Invalid or expired authentication token")
            if response.status_code == 429:
                raise RateLimitError("Rate limit exceeded")
            if response.status_code >= 400:
                try:
                    error_data = response.json()
                    error_message = error_data.get("detail", response.text)
                except (ValueError, requests.exceptions.JSONDecodeError):
                    # Handle non-JSON error responses
                    error_message = response.text or f"HTTP {response.status_code} error"

                raise CodetoreumError(
                    f"API error ({response.status_code}): {error_message}",
                    status_code=response.status_code,
                    response=response,
                )

            return response

        except requests.exceptions.Timeout as e:
            raise CodetoreumError(f"Request timeout after {timeout}s: {e!s}") from e
        except requests.exceptions.ConnectionError as e:
            raise CodetoreumError(f"Connection failed: {e!s}") from e
        except requests.exceptions.RequestException as e:
            raise CodetoreumError(f"Request failed: {e!s}") from e

    def get(self, path: str, params: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        """Make GET request and return JSON response."""
        response = self._request("GET", path, params=params, **kwargs)
        return cast("dict[str, Any]", response.json())

    def post(self, path: str, json: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        """Make POST request and return JSON response."""
        response = self._request("POST", path, json=json, **kwargs)
        return cast("dict[str, Any]", response.json() if response.text else {})

    def put(self, path: str, json: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        """Make PUT request and return JSON response."""
        response = self._request("PUT", path, json=json, **kwargs)
        return cast("dict[str, Any]", response.json())

    def patch(self, path: str, json: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        """Make PATCH request and return JSON response."""
        response = self._request("PATCH", path, json=json, **kwargs)
        return cast("dict[str, Any]", response.json())

    def delete(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """Make DELETE request and return JSON response."""
        response = self._request("DELETE", path, **kwargs)
        return cast("dict[str, Any]", response.json() if response.text else {})

    def health_check(self) -> dict[str, Any]:
        """
        Check API health status.

        Returns:
            Health status information
        """
        return self.get("/api/v2/health")

    def close(self) -> None:
        """Close the session."""
        self.session.close()

    def __enter__(self) -> "CodetoreumClient":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()
