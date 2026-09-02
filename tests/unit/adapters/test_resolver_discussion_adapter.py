"""Tests for AdapterResolver.resolve_discussion_adapter()

Tests for AdapterResolver.resolve_discussion_adapter() GitHub and mock variant resolution."""

import os
from unittest.mock import AsyncMock, Mock, patch

import pytest

from codetoreum.adapters.secondary.github_discussion_adapter import (
    GitHubDiscussionAdapter,
    GitHubDiscussionConfig,
)
from codetoreum.adapters.testing.mock_discussion_adapter import MockDiscussionAdapter
from codetoreum.infrastructure.adapters.factory import AdapterFactory, AdapterFactoryConfig
from codetoreum.infrastructure.adapters.resolver import (
    AdapterConfigurationError,
    AdapterDependencies,
    AdapterResolver,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.http.github_graphql_client import (
    GitHubGraphQLClient,
)
from codetoreum.infrastructure.resilience.decorators import (
    ResilientDiscussionAdapterDecorator,
)
from codetoreum.infrastructure.simulation.simulation_config import AdapterSelectionConfig
from codetoreum.ports.output.discussion_adapter import IDiscussionAdapter


@pytest.fixture
def event_bus():
    """Create an event bus for testing."""
    return EventBus()


@pytest.fixture
def mock_event_emitter():
    """Create a mock event emitter."""
    from codetoreum.adapters.secondary.mock_event_emitter import MockEventEmitter

    return MockEventEmitter()


@pytest.fixture
def mock_engine():
    """Create a mock simulation engine."""
    engine = Mock()
    engine.get_clock_for_testing.return_value.now.return_value = Mock()
    return engine


@pytest.fixture
def mock_config():
    """Create a mock simulation config."""
    config = Mock()
    config.metadata = {}
    return config


@pytest.fixture
def adapter_dependencies(event_bus, mock_event_emitter, mock_engine, mock_config):
    """Create adapter dependencies for testing."""
    return AdapterDependencies(
        event_bus=event_bus,
        event_emitter=mock_event_emitter,
        logger=Mock(),
        engine=mock_engine,
        config=mock_config,
        failed_event_store=None,
    )


@pytest.fixture
def adapter_factory():
    """Create an adapter factory for testing."""
    return AdapterFactory(config=AdapterFactoryConfig())


@pytest.fixture
def mock_identity_service():
    """Create a mock identity service."""
    service = Mock()
    service.get_bot_username.return_value = "test-bot"
    service.is_bot_user.return_value = False
    return service


class TestResolveDiscussionAdapterGithub:
    """Tests for GitHub discussion adapter resolution."""

    def test_github_variant_constructs_adapter_without_typename_error(
        self,
        adapter_factory,
        adapter_dependencies,
        mock_identity_service,
    ):
        """Test that selecting 'github' variant constructs GitHubDiscussionAdapter without TypeError."""
        # Setup
        config = AdapterSelectionConfig(discussion_adapter="github")
        resolver = AdapterResolver(
            adapter_config=config,
            factory=adapter_factory,
            dependencies=adapter_dependencies,
        )
        resolver._resolved = {"identity_service": mock_identity_service}

        # Set environment variables
        with patch.dict(os.environ, {"GITHUB_TOKEN": "test-token", "GITHUB_ORG": "test-org"}):
            # Act & Assert - should not raise TypeError
            adapter = resolver.resolve_discussion_adapter()

        # Verify adapter is wrapped in resilience decorator
        assert isinstance(adapter, ResilientDiscussionAdapterDecorator)
        assert isinstance(adapter._wrapped, GitHubDiscussionAdapter)

    def test_github_variant_constructs_github_discussion_config(
        self,
        adapter_factory,
        adapter_dependencies,
        mock_identity_service,
    ):
        """Test that GitHub variant constructs GitHubDiscussionConfig with correct parameters."""
        config = AdapterSelectionConfig(discussion_adapter="github")
        resolver = AdapterResolver(
            adapter_config=config,
            factory=adapter_factory,
            dependencies=adapter_dependencies,
        )
        resolver._resolved = {"identity_service": mock_identity_service}

        with patch.dict(
            os.environ,
            {"GITHUB_TOKEN": "ghp_test123", "GITHUB_ORG": "my-org"},
        ):
            adapter = resolver.resolve_discussion_adapter()

        # Verify the wrapped adapter has correct config
        wrapped_adapter = adapter._wrapped
        assert isinstance(wrapped_adapter, GitHubDiscussionAdapter)
        assert wrapped_adapter._config.token == "ghp_test123"
        assert wrapped_adapter._config.organization == "my-org"
        assert wrapped_adapter._config.repository == ""

    def test_github_variant_constructs_fresh_graphql_client(
        self,
        adapter_factory,
        adapter_dependencies,
        mock_identity_service,
    ):
        """Test that GitHub variant constructs a fresh GitHubGraphQLClient."""
        config = AdapterSelectionConfig(discussion_adapter="github")
        resolver = AdapterResolver(
            adapter_config=config,
            factory=adapter_factory,
            dependencies=adapter_dependencies,
        )
        resolver._resolved = {"identity_service": mock_identity_service}

        with patch.dict(
            os.environ,
            {"GITHUB_TOKEN": "ghp_test123", "GITHUB_ORG": "my-org"},
        ):
            adapter = resolver.resolve_discussion_adapter()

        # Verify the wrapped adapter has a GraphQL client
        wrapped_adapter = adapter._wrapped
        assert wrapped_adapter._config.graphql_client is not None
        assert isinstance(wrapped_adapter._config.graphql_client, GitHubGraphQLClient)

    def test_github_variant_passes_ticket_adapter_as_collaborator(
        self,
        adapter_factory,
        adapter_dependencies,
        mock_identity_service,
    ):
        """Test that GitHub variant passes resolved ticket adapter to discussion adapter."""
        mock_ticket_adapter = Mock()
        config = AdapterSelectionConfig(discussion_adapter="github")
        resolver = AdapterResolver(
            adapter_config=config,
            factory=adapter_factory,
            dependencies=adapter_dependencies,
        )
        resolver._resolved = {
            "identity_service": mock_identity_service,
            "ticket": mock_ticket_adapter,
        }

        with patch.dict(
            os.environ,
            {"GITHUB_TOKEN": "ghp_test123", "GITHUB_ORG": "my-org"},
        ):
            adapter = resolver.resolve_discussion_adapter()

        # Verify the wrapped adapter has the ticket adapter
        wrapped_adapter = adapter._wrapped
        assert wrapped_adapter._ticket_adapter is mock_ticket_adapter

    def test_github_variant_wraps_in_resilience_decorator(
        self,
        adapter_factory,
        adapter_dependencies,
        mock_identity_service,
    ):
        """Test that GitHub variant result is wrapped in ResilientDiscussionAdapterDecorator."""
        config = AdapterSelectionConfig(discussion_adapter="github")
        resolver = AdapterResolver(
            adapter_config=config,
            factory=adapter_factory,
            dependencies=adapter_dependencies,
        )
        resolver._resolved = {"identity_service": mock_identity_service}

        with patch.dict(
            os.environ,
            {"GITHUB_TOKEN": "ghp_test123", "GITHUB_ORG": "my-org"},
        ):
            adapter = resolver.resolve_discussion_adapter()

        assert isinstance(adapter, ResilientDiscussionAdapterDecorator)

    def test_github_variant_uses_credentials_when_available(
        self,
        adapter_factory,
        adapter_dependencies,
        mock_identity_service,
    ):
        """Test that GitHub variant uses injected credentials instead of os.environ."""
        from codetoreum.infrastructure.bootstrap.production_bootstrap import (
            ProductionCredentials,
        )

        mock_credentials = Mock(spec=ProductionCredentials)
        mock_credentials.github_token = "ghp_from_credentials"

        config = AdapterSelectionConfig(discussion_adapter="github")
        resolver = AdapterResolver(
            adapter_config=config,
            factory=adapter_factory,
            dependencies=adapter_dependencies,
            credentials=mock_credentials,
        )
        resolver._resolved = {"identity_service": mock_identity_service}

        with patch.dict(os.environ, {"GITHUB_ORG": "my-org"}):
            adapter = resolver.resolve_discussion_adapter()

        # Verify credentials from ProductionCredentials are used
        wrapped_adapter = adapter._wrapped
        assert wrapped_adapter._config.token == "ghp_from_credentials"


class TestResolveDiscussionAdapterMock:
    """Tests for mock discussion adapter resolution."""

    def test_mock_variant_uses_factory(
        self,
        adapter_factory,
        adapter_dependencies,
        mock_identity_service,
    ):
        """Test that selecting 'mock' variant uses factory to create adapter."""
        config = AdapterSelectionConfig(discussion_adapter="mock")
        resolver = AdapterResolver(
            adapter_config=config,
            factory=adapter_factory,
            dependencies=adapter_dependencies,
        )
        resolver._resolved = {"identity_service": mock_identity_service}

        adapter = resolver.resolve_discussion_adapter()

        # Verify adapter is wrapped and mock adapter is used
        assert isinstance(adapter, ResilientDiscussionAdapterDecorator)
        assert isinstance(adapter._wrapped, MockDiscussionAdapter)

    def test_mock_variant_passes_time_source(
        self,
        adapter_factory,
        adapter_dependencies,
        mock_identity_service,
    ):
        """Test that mock variant passes time_source to the adapter."""
        config = AdapterSelectionConfig(discussion_adapter="mock")
        resolver = AdapterResolver(
            adapter_config=config,
            factory=adapter_factory,
            dependencies=adapter_dependencies,
        )
        resolver._resolved = {"identity_service": mock_identity_service}

        adapter = resolver.resolve_discussion_adapter()

        # Verify the wrapped adapter is MockDiscussionAdapter with time_source
        wrapped_adapter = adapter._wrapped
        assert isinstance(wrapped_adapter, MockDiscussionAdapter)
        # MockDiscussionAdapter should have a time_source callable
        assert callable(wrapped_adapter._time_source)

    def test_mock_variant_wraps_in_resilience_decorator(
        self,
        adapter_factory,
        adapter_dependencies,
        mock_identity_service,
    ):
        """Test that mock variant result is wrapped in ResilientDiscussionAdapterDecorator."""
        config = AdapterSelectionConfig(discussion_adapter="mock")
        resolver = AdapterResolver(
            adapter_config=config,
            factory=adapter_factory,
            dependencies=adapter_dependencies,
        )
        resolver._resolved = {"identity_service": mock_identity_service}

        adapter = resolver.resolve_discussion_adapter()

        assert isinstance(adapter, ResilientDiscussionAdapterDecorator)


class TestResolveDiscussionAdapterIDiscussionAdapterContract:
    """Tests verifying resolved adapters implement IDiscussionAdapter."""

    def test_github_variant_is_discussion_adapter(
        self,
        adapter_factory,
        adapter_dependencies,
        mock_identity_service,
    ):
        """Test that GitHub variant resolves to IDiscussionAdapter."""
        config = AdapterSelectionConfig(discussion_adapter="github")
        resolver = AdapterResolver(
            adapter_config=config,
            factory=adapter_factory,
            dependencies=adapter_dependencies,
        )
        resolver._resolved = {"identity_service": mock_identity_service}

        with patch.dict(
            os.environ,
            {"GITHUB_TOKEN": "ghp_test", "GITHUB_ORG": "test-org"},
        ):
            adapter = resolver.resolve_discussion_adapter()

        assert isinstance(adapter, IDiscussionAdapter)

    def test_mock_variant_is_discussion_adapter(
        self,
        adapter_factory,
        adapter_dependencies,
        mock_identity_service,
    ):
        """Test that mock variant resolves to IDiscussionAdapter."""
        config = AdapterSelectionConfig(discussion_adapter="mock")
        resolver = AdapterResolver(
            adapter_config=config,
            factory=adapter_factory,
            dependencies=adapter_dependencies,
        )
        resolver._resolved = {"identity_service": mock_identity_service}

        adapter = resolver.resolve_discussion_adapter()

        assert isinstance(adapter, IDiscussionAdapter)


class TestResolveDiscussionAdapterValidation:
    """Tests for validation of required dependencies."""

    def test_github_variant_raises_when_identity_service_missing(
        self,
        adapter_factory,
        adapter_dependencies,
    ):
        """Test that GitHub variant raises error when identity_service is not resolved."""
        config = AdapterSelectionConfig(discussion_adapter="github")
        resolver = AdapterResolver(
            adapter_config=config,
            factory=adapter_factory,
            dependencies=adapter_dependencies,
        )
        resolver._resolved = {}  # No identity_service

        with patch.dict(
            os.environ,
            {"GITHUB_TOKEN": "ghp_test", "GITHUB_ORG": "test-org"},
        ):
            with pytest.raises(AdapterConfigurationError) as exc_info:
                resolver.resolve_discussion_adapter()

            assert "identity_service" in str(exc_info.value)
            assert "requires" in str(exc_info.value)

    def test_mock_variant_raises_when_identity_service_missing(
        self,
        adapter_factory,
        adapter_dependencies,
    ):
        """Test that mock variant raises error when identity_service is not resolved."""
        config = AdapterSelectionConfig(discussion_adapter="mock")
        resolver = AdapterResolver(
            adapter_config=config,
            factory=adapter_factory,
            dependencies=adapter_dependencies,
        )
        resolver._resolved = {}  # No identity_service

        with pytest.raises(AdapterConfigurationError) as exc_info:
            resolver.resolve_discussion_adapter()

        assert "identity_service" in str(exc_info.value)
        assert "requires" in str(exc_info.value)

    def test_github_variant_translates_validation_error_to_adapter_config_error(
        self,
        adapter_factory,
        adapter_dependencies,
        mock_identity_service,
    ):
        """Test that GitHubDiscussionConfig validation errors are translated to AdapterConfigurationError."""
        config = AdapterSelectionConfig(discussion_adapter="github")
        resolver = AdapterResolver(
            adapter_config=config,
            factory=adapter_factory,
            dependencies=adapter_dependencies,
        )
        resolver._resolved = {"identity_service": mock_identity_service}

        with patch.dict(
            os.environ,
            {"GITHUB_TOKEN": "ghp_test", "GITHUB_ORG": ""},
        ):
            with pytest.raises(AdapterConfigurationError) as exc_info:
                resolver.resolve_discussion_adapter()

            assert "organization is required" in str(exc_info.value)
