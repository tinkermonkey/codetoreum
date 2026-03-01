"""GitHub GraphQL API client for Projects v2 integration.

Provides thin wrapper around GitHub's GraphQL API with authentication,
error handling, and rate limit tracking for Projects v2 operations.
"""

from dataclasses import dataclass
from typing import Any

import httpx

from codetoreum.ports.exceptions import (
    AuthenticationError,
    ExternalServiceError,
)


@dataclass
class GitHubGraphQLConfig:
    """Configuration for GitHub GraphQL client."""

    token: str  # Personal Access Token or GitHub App token
    api_url: str = "https://api.github.com/graphql"
    timeout_seconds: int = 30


class GitHubGraphQLClient:
    """Client for GitHub GraphQL API operations.

    Handles authentication, request/response processing, rate limit tracking,
    and error mapping for GitHub Projects v2 queries and mutations.
    """

    def __init__(self, config: GitHubGraphQLConfig):
        """Initialize GraphQL client.

        Args:
            config: GitHub GraphQL configuration
        """
        self.config = config
        self._http_client: httpx.AsyncClient | None = None
        self._rate_limit_remaining: int | None = None
        self._rate_limit_reset: int | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            headers = {
                "Authorization": f"Bearer {self.config.token}",
                "Content-Type": "application/json",
            }

            self._http_client = httpx.AsyncClient(
                headers=headers,
                timeout=self.config.timeout_seconds,
            )

        return self._http_client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute GraphQL query or mutation.

        Args:
            query: GraphQL query/mutation string
            variables: Optional query variables

        Returns:
            Response data from GraphQL API

        Raises:
            AuthenticationError: Invalid or missing authentication
            ExternalServiceError: API call failed
        """
        client = await self._get_client()

        payload = {
            "query": query,
        }
        if variables:
            payload["variables"] = variables

        try:
            response = await client.post(
                self.config.api_url,
                json=payload,
            )

            # Track rate limits
            if "x-ratelimit-remaining" in response.headers:
                self._rate_limit_remaining = int(response.headers["x-ratelimit-remaining"])
            if "x-ratelimit-reset" in response.headers:
                self._rate_limit_reset = int(response.headers["x-ratelimit-reset"])

            # Check for authentication errors
            if response.status_code == 401:
                message = "GitHub authentication failed"
                raise AuthenticationError(message)

            # Check for rate limiting
            if response.status_code == 403:
                message = (
                    "GitHub",
                    f"GitHub rate limit exceeded. Reset at: {self._rate_limit_reset}",
                )
                raise ExternalServiceError(message)

            if response.status_code >= 400:
                message = "GitHub", f"GitHub GraphQL API error: {response.status_code}"
                raise ExternalServiceError(message)

            data = response.json()

            # Check for GraphQL errors in response
            if data.get("errors"):
                error_messages = [str(e.get("message", "Unknown error")) for e in data["errors"]]
                message = "GitHub", f"GraphQL errors: {'; '.join(error_messages)}"
                raise ExternalServiceError(message)

            return data.get("data", {})

        except httpx.RequestError as e:
            message = "GitHub"
            raise ExternalServiceError(message, f"GitHub API request failed: {e!s}")

    def get_rate_limit_status(self) -> dict[str, int | None]:
        """Get current rate limit status.

        Returns:
            Dictionary with remaining requests and reset time
        """
        return {
            "remaining": self._rate_limit_remaining,
            "reset": self._rate_limit_reset,
        }
