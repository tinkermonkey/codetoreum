"""Contract tests for IIdentityService interface.

These abstract tests verify that all IIdentityService implementations
follow the contract correctly for bot identity detection and filtering.

Note: This is a query-only interface with NO event emission.
"""

import re
from abc import ABC, abstractmethod

import pytest

from codetoreum.ports.exceptions import ValidationError
from codetoreum.ports.output.identity_service import (
    BotIdentityConfig,
    IIdentityService,
)


class TestIdentityServiceContract(ABC):
    """Abstract contract tests for IIdentityService implementations.

    Subclasses must implement create_service() to provide a concrete
    IIdentityService implementation to test.
    """

    @abstractmethod
    def create_service(self) -> IIdentityService:
        """Create and return an IIdentityService instance for testing."""
        pass

    # Bot Detection Tests

    def test_is_bot_user_detects_configured_bots(self):
        """Should identify users in bot_usernames list as bots."""
        service = self.create_service()

        config = BotIdentityConfig(
            bot_usernames=["dependabot", "renovate", "codecov"],
            bot_patterns=[]
        )
        service.configure(config)

        assert service.is_bot_user("dependabot") is True
        assert service.is_bot_user("renovate") is True
        assert service.is_bot_user("codecov") is True

    def test_is_bot_user_detects_pattern_matches(self):
        """Should identify users matching bot_patterns as bots."""
        service = self.create_service()

        config = BotIdentityConfig(
            bot_usernames=[],
            bot_patterns=[
                re.compile("^bot-"),
                re.compile("-bot$"),
                re.compile(".*-ci$"),
            ]
        )
        service.configure(config)

        assert service.is_bot_user("bot-agent") is True
        assert service.is_bot_user("myservice-bot") is True
        assert service.is_bot_user("github-ci") is True

    def test_is_bot_user_identifies_humans(self):
        """Should return False for non-bot users."""
        service = self.create_service()

        config = BotIdentityConfig(
            bot_usernames=["dependabot"],
            bot_patterns=[re.compile("^bot-")]
        )
        service.configure(config)

        assert service.is_bot_user("alice") is False
        assert service.is_bot_user("bob") is False
        assert service.is_bot_user("charlie") is False

    def test_is_bot_user_case_sensitive(self):
        """Bot detection should be case-sensitive for usernames."""
        service = self.create_service()

        config = BotIdentityConfig(
            bot_usernames=["dependabot"],
            bot_patterns=[]
        )
        service.configure(config)

        assert service.is_bot_user("dependabot") is True
        # Case-sensitive check
        assert service.is_bot_user("Dependabot") is False
        assert service.is_bot_user("DEPENDABOT") is False

    # Bot Username Tests

    def test_get_bot_username_returns_configured_name(self):
        """Should return the configured bot username."""
        service = self.create_service()

        config = BotIdentityConfig(
            bot_usernames=["codetoreum-bot"],
            bot_patterns=[]
        )
        service.configure(config)

        bot_name = service.get_bot_username()

        assert isinstance(bot_name, str)
        assert len(bot_name) > 0
        assert bot_name == "codetoreum-bot"

    def test_get_bot_username_without_configuration_raises(self):
        """Should raise ValidationError if no bot username configured."""
        service = self.create_service()

        # Create config with no bot_usernames
        config = BotIdentityConfig(
            bot_usernames=[],
            bot_patterns=[]
        )
        service.configure(config)

        with pytest.raises(ValidationError):
            service.get_bot_username()

    # User Filtering Tests

    def test_get_human_users_filters_bots(self):
        """Should filter out bots from user list."""
        service = self.create_service()

        config = BotIdentityConfig(
            bot_usernames=["dependabot", "renovate"],
            bot_patterns=[]
        )
        service.configure(config)

        all_users = ["alice", "dependabot", "bob", "renovate", "charlie"]
        humans = service.get_human_users(all_users)

        assert isinstance(humans, list)
        assert "alice" in humans
        assert "bob" in humans
        assert "charlie" in humans
        assert "dependabot" not in humans
        assert "renovate" not in humans

    def test_get_human_users_with_patterns(self):
        """Should filter based on bot patterns too."""
        service = self.create_service()

        config = BotIdentityConfig(
            bot_usernames=["dependabot"],
            bot_patterns=[re.compile("^bot-")]
        )
        service.configure(config)

        all_users = ["alice", "bot-agent", "bob", "dependabot", "bot-service"]
        humans = service.get_human_users(all_users)

        assert "alice" in humans
        assert "bob" in humans
        assert "dependabot" not in humans
        assert "bot-agent" not in humans
        assert "bot-service" not in humans

    def test_get_human_users_preserves_order(self):
        """Should maintain order of filtered users."""
        service = self.create_service()

        config = BotIdentityConfig(
            bot_usernames=["bot"],
            bot_patterns=[]
        )
        service.configure(config)

        all_users = ["alice", "bot", "bob", "charlie"]
        humans = service.get_human_users(all_users)

        assert humans == ["alice", "bob", "charlie"]

    def test_get_human_users_empty_list(self):
        """Should handle empty user list."""
        service = self.create_service()

        config = BotIdentityConfig(
            bot_usernames=["bot"],
            bot_patterns=[]
        )
        service.configure(config)

        humans = service.get_human_users([])

        assert isinstance(humans, list)
        assert len(humans) == 0

    def test_get_human_users_all_bots(self):
        """Should return empty list if all users are bots."""
        service = self.create_service()

        config = BotIdentityConfig(
            bot_usernames=["bot1", "bot2"],
            bot_patterns=[]
        )
        service.configure(config)

        all_users = ["bot1", "bot2"]
        humans = service.get_human_users(all_users)

        assert len(humans) == 0

    # Configuration Tests

    def test_configure_updates_settings(self):
        """Configure should update bot detection settings."""
        service = self.create_service()

        # First config
        config1 = BotIdentityConfig(
            bot_usernames=["bot1"],
            bot_patterns=[]
        )
        service.configure(config1)
        assert service.is_bot_user("bot1") is True
        assert service.is_bot_user("bot2") is False

        # Update config
        config2 = BotIdentityConfig(
            bot_usernames=["bot2", "bot3"],
            bot_patterns=[]
        )
        service.configure(config2)
        assert service.is_bot_user("bot1") is False
        assert service.is_bot_user("bot2") is True
        assert service.is_bot_user("bot3") is True

    def test_configure_empty_config_raises(self):
        """Configure with no bots should raise ValidationError."""
        service = self.create_service()

        config = BotIdentityConfig(
            bot_usernames=[],
            bot_patterns=[]
        )

        with pytest.raises(ValidationError):
            service.configure(config)

    def test_configure_with_both_usernames_and_patterns(self):
        """Configure should support both usernames and patterns."""
        service = self.create_service()

        config = BotIdentityConfig(
            bot_usernames=["dependabot"],
            bot_patterns=[re.compile("^bot-"), re.compile("-bot$")]
        )
        service.configure(config)

        # Both should work
        assert service.is_bot_user("dependabot") is True
        assert service.is_bot_user("bot-agent") is True
        assert service.is_bot_user("service-bot") is True
        assert service.is_bot_user("alice") is False

    # Event Tests

    def test_service_has_no_event_methods(self):
        """IIdentityService should NOT have event methods."""
        service = self.create_service()

        # Should not have event methods (no event emission)
        assert not hasattr(service, "on")
        assert not hasattr(service, "off")
        assert not hasattr(service, "emit")

    def test_service_has_no_monitoring_methods(self):
        """IIdentityService should NOT have monitoring methods."""
        service = self.create_service()

        # Should not have monitoring methods
        assert not hasattr(service, "start_monitoring")
        assert not hasattr(service, "stop_monitoring")
        assert not hasattr(service, "get_monitoring_status")
