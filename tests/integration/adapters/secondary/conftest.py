"""Shared fixtures for GitHub discussion adapter integration tests."""

import pytest
from unittest.mock import Mock
from typing import List, Optional

from codetoreum.adapters.secondary.github_discussion_adapter import (
    GitHubDiscussionConfig,
    GitHubDiscussionAdapter,
)
from codetoreum.ports.output.discussion_adapter import DiscussionMonitoringConfig
from codetoreum.domain.events.discussion_events import Comment


class MockIdentityService:
    """Mock identity service for consistent bot identification in tests."""

    def __init__(self, bot_usernames: Optional[List[str]] = None):
        """Initialize with list of bot usernames.

        Args:
            bot_usernames: List of usernames to identify as bots
        """
        self.bot_usernames = bot_usernames or [
            "dependabot",
            "renovate",
            "codetoreum-bot",
            "codecov",
            "github-actions",
        ]
        self.configured_bot = "codetoreum-bot"

    def is_bot_user(self, username: str) -> bool:
        """Check if username is a bot."""
        return username in self.bot_usernames

    def get_bot_username(self) -> str:
        """Get configured bot username."""
        return self.configured_bot

    def get_human_users(self, usernames: List[str]) -> List[str]:
        """Filter list to only human users."""
        return [u for u in usernames if not self.is_bot_user(u)]

    def configure(self, config) -> None:
        """Update configuration."""
        pass


@pytest.fixture
def mock_identity_service():
    """Provide mock identity service."""
    return MockIdentityService()


@pytest.fixture
def github_config():
    """Provide standard GitHub configuration for testing."""
    return GitHubDiscussionConfig(
        token="test-token-12345",
        organization="test-org",
        repository="test-repo",
        api_base_url="https://api.github.com",
        webhook_enabled=True,
        polling_interval_seconds=1,
    )


@pytest.fixture
def github_adapter(github_config, mock_identity_service):
    """Provide GitHub discussion adapter."""
    return GitHubDiscussionAdapter(github_config, mock_identity_service)


@pytest.fixture
def polling_adapter(github_config, mock_identity_service):
    """Provide GitHub adapter with polling enabled (webhook disabled)."""
    config = GitHubDiscussionConfig(
        token=github_config.token,
        organization=github_config.organization,
        repository=github_config.repository,
        webhook_enabled=False,  # Polling only
        polling_interval_seconds=1,
    )
    return GitHubDiscussionAdapter(config, mock_identity_service)


@pytest.fixture
def monitoring_config():
    """Provide standard monitoring configuration."""
    return DiscussionMonitoringConfig(
        project_id="proj-12345",
    )


@pytest.fixture
def sample_comments():
    """Provide sample comments for testing."""
    return [
        Comment(
            id="1",
            author="alice",
            body="First comment on the issue",
            created_at="2025-01-08T10:00:00Z",
        ),
        Comment(
            id="2",
            author="dependabot",
            body="Automated dependency update",
            created_at="2025-01-08T10:01:00Z",
            is_bot=True,
        ),
        Comment(
            id="3",
            author="bob",
            body="Second human comment",
            created_at="2025-01-08T10:02:00Z",
        ),
    ]


@pytest.fixture
def mock_github_issue_comments_response():
    """Provide mock GitHub REST API response for issue comments."""

    def _create_response(comments: List[dict]):
        response = Mock()
        response.status_code = 200
        response.json.return_value = comments
        return response

    return _create_response


@pytest.fixture
def mock_github_create_comment_response():
    """Provide mock GitHub REST API response for creating comment."""

    def _create_response(comment_id: int, author: str, body: str):
        response = Mock()
        response.status_code = 201
        response.json.return_value = {
            "id": comment_id,
            "user": {"login": author},
            "body": body,
            "created_at": "2025-01-08T10:00:00Z",
        }
        return response

    return _create_response


@pytest.fixture
def mock_github_webhook_payload():
    """Provide template for GitHub webhook payload."""

    def _create_payload(
        action: str = "created",
        issue_number: int = 123,
        comment_id: int = 456,
        author: str = "alice",
        body: str = "Test comment",
    ):
        return {
            "action": action,
            "issue": {"number": issue_number},
            "comment": {
                "id": comment_id,
                "user": {"login": author},
                "body": body,
                "created_at": "2025-01-08T10:00:00Z",
            },
        }

    return _create_payload
