"""Identity service port interface (query-only, no events).

This interface defines contracts for bot identity detection and user filtering.
The service answers questions about whether users are bots or humans, enabling
the orchestrator to distinguish between human feedback and bot responses.

Like IVersionControlService, this is a synchronous query-only interface
with no event emission.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from re import Pattern


@dataclass
class BotIdentityConfig:
    """Configuration for bot identity detection.

    Attributes:
        bot_usernames: Exact usernames to identify as bots
                      (e.g., ["dependabot", "renovate", "codecov"])
        bot_patterns: Regex patterns for matching bot usernames
                     (e.g., [re.compile("^bot-.*"), re.compile(".*-bot$")])
    """

    bot_usernames: list[str]
    bot_patterns: list[Pattern]


class IIdentityService(ABC):
    """Bot identity queries (no events).

    Provides mechanisms to identify bot vs. human users in the system.
    This is a simple query-only interface used to:
    1. Filter bot comments from human feedback
    2. Determine who created changes (human vs. bot)
    3. Apply different logic based on user identity

    Unlike event-emitting services, this has no monitoring or event
    emission. It's a simple lookup service configured at initialization.

    Configuration is typically set once during system setup, but can
    be updated dynamically via the configure() method.

    Bot Detection Rules:
        A user is considered a bot if their username:
        1. Matches an entry in bot_usernames (exact match), OR
        2. Matches a pattern in bot_patterns (regex match)

    Example:
        async with service as svc:
            # Configure bots
            config = BotIdentityConfig(
                bot_usernames=["dependabot", "renovate"],
                bot_patterns=[
                    re.compile("^codetoreum-"),
                    re.compile("-bot$")
                ]
            )
            svc.configure(config)

            # Query identity
            if await svc.is_bot_user("dependabot"):
                print("This is a bot")

            # Get bot username
            bot_name = svc.get_bot_username()

            # Filter users
            all_users = ["alice", "dependabot", "bob", "codetoreum-agent"]
            humans = svc.get_human_users(all_users)
            # Returns: ["alice", "bob"]
    """

    @abstractmethod
    def is_bot_user(self, username: str) -> bool:
        """Check if username belongs to a bot.

        Determines if the given username matches configured bot identifiers.

        Args:
            username: Username to check

        Returns:
            bool: True if username is identified as a bot, False if human
        """

    @abstractmethod
    def get_bot_username(self) -> str:
        """Get configured bot username for this system.

        Returns the primary bot username that represents the orchestrator itself.
        Used when posting comments or making changes on behalf of the system.

        Returns:
            str: Bot username for the orchestrator

        Raises:
            ConfigurationError: No bot username configured
        """

    @abstractmethod
    def get_human_users(self, usernames: list[str]) -> list[str]:
        """Filter list to only human users.

        Removes any bots from the provided list of usernames.

        Args:
            usernames: List of usernames to filter

        Returns:
            List[str]: Subset of input containing only human users

        Example:
            all_users = ["alice", "dependabot", "bob", "codetoreum-agent"]
            humans = service.get_human_users(all_users)
            # Returns: ["alice", "bob"]
        """

    @abstractmethod
    def configure(self, config: BotIdentityConfig) -> None:
        """Update bot identity configuration.

        Updates the list of usernames and patterns used to identify bots.
        Called during system initialization or when configuration changes.

        Args:
            config: New bot identity configuration

        Raises:
            ValidationError: Invalid configuration (empty bot_usernames
                            and bot_patterns, etc.)
        """
