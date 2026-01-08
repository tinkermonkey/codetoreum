"""GitHub GraphQL API client for Projects v2 integration.

Provides thin wrapper around GitHub's GraphQL API with authentication,
error handling, and rate limit tracking for Projects v2 operations.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

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
        self._http_client: Optional[httpx.AsyncClient] = None
        self._rate_limit_remaining: Optional[int] = None
        self._rate_limit_reset: Optional[int] = None

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
        variables: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
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
                self._rate_limit_remaining = int(
                    response.headers["x-ratelimit-remaining"]
                )
            if "x-ratelimit-reset" in response.headers:
                self._rate_limit_reset = int(
                    response.headers["x-ratelimit-reset"]
                )

            # Check for authentication errors
            if response.status_code == 401:
                raise AuthenticationError("GitHub authentication failed")

            # Check for rate limiting
            if response.status_code == 403:
                raise ExternalServiceError(
                    f"GitHub rate limit exceeded. Reset at: {self._rate_limit_reset}"
                )

            if response.status_code >= 400:
                raise ExternalServiceError(
                    f"GitHub GraphQL API error: {response.status_code}"
                )

            data = response.json()

            # Check for GraphQL errors in response
            if "errors" in data and data["errors"]:
                error_messages = [
                    str(e.get("message", "Unknown error"))
                    for e in data["errors"]
                ]
                raise ExternalServiceError(
                    f"GraphQL errors: {'; '.join(error_messages)}"
                )

            return data.get("data", {})

        except httpx.RequestError as e:
            raise ExternalServiceError(f"GitHub API request failed: {str(e)}")

    def get_rate_limit_status(self) -> Dict[str, Optional[int]]:
        """Get current rate limit status.

        Returns:
            Dictionary with remaining requests and reset time
        """
        return {
            "remaining": self._rate_limit_remaining,
            "reset": self._rate_limit_reset,
        }
