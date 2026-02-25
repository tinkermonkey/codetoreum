"""Configurable bot identity service for testing.

This module provides an in-memory implementation of IIdentityService
with configurable bot detection for testing purposes.
"""

from re import Pattern

from codetoreum.ports.output.identity_service import BotIdentityConfig, IIdentityService


class ConfigurableIdentityService(IIdentityService):
    """Configurable bot identity service for testing.

    Provides a simple in-memory implementation of IIdentityService that
    uses configurable lists and regex patterns to identify bot users.

    Intended for testing and simulation where bot identity needs to be
    configured dynamically without connecting to external user systems.

    Example:
        # Setup
        service = ConfigurableIdentityService()
        config = BotIdentityConfig(
            bot_usernames=["dependabot", "renovate", "codetoreum-bot"],
            bot_patterns=[
                re.compile("^bot-.*"),
                re.compile(".*-bot$")
            ]
        )
        service.configure(config)

        # Query identity
        assert service.is_bot_user("dependabot")  # True (exact match)
        assert service.is_bot_user("bot-ci")  # True (pattern match)
        assert service.is_bot_user("alice")  # False (human)

        # Filter users
        humans = service.get_human_users(
            ["alice", "dependabot", "bob", "bot-agent"]
        )
        assert humans == ["alice", "bob"]
    """

    def __init__(self) -> None:
        """Initialize the identity service with default values."""
        self._bot_usernames: list[str] = []
        self._bot_patterns: list[Pattern] = []  # type: ignore
        self._system_bot_username: str = "codetoreum-bot"

    def is_bot_user(self, username: str) -> bool:
        """Check if username belongs to a bot.

        Determines if the given username matches configured bot identifiers
        using exact matching (bot_usernames) and regex patterns (bot_patterns).

        Args:
            username: Username to check

        Returns:
            bool: True if username is identified as a bot, False if human

        Raises:
            ValueError: If username is empty
        """
        if not username:
            msg = "username cannot be empty"
            raise ValueError(msg)

        # Check exact matches
        if username in self._bot_usernames:
            return True

        # Check regex patterns
        for pattern in self._bot_patterns:
            if pattern.match(username):
                return True

        return False

    def get_bot_username(self) -> str:
        """Get configured bot username for this system.

        Returns the primary bot username that represents the orchestrator itself.

        Returns:
            str: Bot username for the orchestrator

        Raises:
            ValueError: If no bot username configured
        """
        if not self._system_bot_username:
            msg = "No bot username configured"
            raise ValueError(msg)
        return self._system_bot_username

    def get_human_users(self, usernames: list[str]) -> list[str]:
        """Filter list to only human users.

        Removes any bots from the provided list of usernames,
        returning only those identified as human users.

        Args:
            usernames: List of usernames to filter

        Returns:
            List[str]: Subset of input containing only human users

        Example:
            all_users = ["alice", "dependabot", "bob", "codetoreum-agent"]
            humans = service.get_human_users(all_users)
            # Returns: ["alice", "bob"]
        """
        return [u for u in usernames if not self.is_bot_user(u)]

    def configure(self, config: BotIdentityConfig) -> None:
        """Update bot identity configuration.

        Updates the list of usernames and patterns used to identify bots.
        Can be called during system initialization or when configuration changes.

        Args:
            config: New bot identity configuration

        Raises:
            ValueError: If configuration is invalid (e.g., empty bot_usernames
                       and empty bot_patterns)
        """
        if not config.bot_usernames and not config.bot_patterns:
            msg = "At least one of bot_usernames or bot_patterns must be provided"
            raise ValueError(
                msg
            )

        self._bot_usernames = config.bot_usernames or []
        self._bot_patterns = config.bot_patterns or []

    def set_bot_username(self, username: str) -> None:
        """Set the system bot username.

        Allows test setup to configure the username that represents
        the orchestrator system itself.

        Args:
            username: Bot username for the orchestrator

        Raises:
            ValueError: If username is empty
        """
        if not username:
            msg = "username cannot be empty"
            raise ValueError(msg)
        self._system_bot_username = username
