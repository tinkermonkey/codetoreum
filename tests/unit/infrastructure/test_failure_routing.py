"""Tests for INV-20 critical adapter failure routing enforcement."""

import pytest

from codetoreum.adapters.secondary.docker_container_adapter import DockerConfig, DockerContainerAdapter
from codetoreum.adapters.secondary.github_board_adapter import GitHubBoardAdapter
from codetoreum.adapters.secondary.github_code_review_adapter import GitHubCodeReviewAdapter
from codetoreum.adapters.secondary.github_ticket_adapter import GitHubConfig, GitHubTicketAdapter
from codetoreum.adapters.secondary.github_version_control_adapter import GitHubVersionControlAdapter
from codetoreum.adapters.testing import InMemoryFailedEventStore


class TestCriticalAdapterFailureRouting:
    """Test that critical adapters accept and store IFailedEventStore."""

    def test_github_ticket_adapter_requires_failed_event_store(self):
        """Test that GitHubTicketAdapter accepts failed_event_store parameter."""
        failed_event_store = InMemoryFailedEventStore()
        config = GitHubConfig(token="test", organization="test-org")

        adapter = GitHubTicketAdapter(config=config, failed_event_store=failed_event_store)
        assert adapter.failed_event_store is failed_event_store

    def test_github_ticket_adapter_defaults_to_none_failed_event_store(self):
        """Test that GitHubTicketAdapter can be created without failed_event_store (for backward compat in tests)."""
        config = GitHubConfig(token="test", organization="test-org")
        adapter = GitHubTicketAdapter(config=config)
        assert adapter.failed_event_store is None

    def test_github_board_adapter_requires_failed_event_store(self):
        """Test that GitHubBoardAdapter accepts failed_event_store parameter."""
        failed_event_store = InMemoryFailedEventStore()
        adapter = GitHubBoardAdapter(failed_event_store=failed_event_store)
        assert adapter.failed_event_store is failed_event_store

    def test_github_version_control_adapter_requires_failed_event_store(self):
        """Test that GitHubVersionControlAdapter accepts failed_event_store parameter."""
        failed_event_store = InMemoryFailedEventStore()
        adapter = GitHubVersionControlAdapter(failed_event_store=failed_event_store)
        assert adapter.failed_event_store is failed_event_store

    def test_docker_container_adapter_requires_failed_event_store(self):
        """Test that DockerContainerAdapter accepts failed_event_store parameter."""
        failed_event_store = InMemoryFailedEventStore()
        config = DockerConfig()
        adapter = DockerContainerAdapter(config=config, failed_event_store=failed_event_store)
        assert adapter.failed_event_store is failed_event_store

    def test_github_code_review_adapter_requires_failed_event_store(self):
        """Test that GitHubCodeReviewAdapter accepts failed_event_store parameter."""
        failed_event_store = InMemoryFailedEventStore()
        adapter = GitHubCodeReviewAdapter(
            ticket_adapter=None,
            graphql_client=None,
            failed_event_store=failed_event_store,
        )
        assert adapter.failed_event_store is failed_event_store

    def test_multiple_adapters_can_share_failed_event_store(self):
        """Test that multiple critical adapters can share the same failed_event_store."""
        shared_store = InMemoryFailedEventStore()

        ticket_config = GitHubConfig(token="test", organization="test-org")
        ticket_adapter = GitHubTicketAdapter(config=ticket_config, failed_event_store=shared_store)

        board_adapter = GitHubBoardAdapter(failed_event_store=shared_store)

        assert ticket_adapter.failed_event_store is shared_store
        assert board_adapter.failed_event_store is shared_store
        assert ticket_adapter.failed_event_store is board_adapter.failed_event_store
