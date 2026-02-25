"""IMessageBroker output port interface."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from codetoreum.domain.events import DomainEvent

# ============================================================================
# Port Interface
# ============================================================================


class IMessageBroker(ABC):
    """
    Interface for pub/sub message broker for distributed event distribution.

    This port enables horizontal scalability by distributing messages across
    multiple application instances using a pub/sub messaging system.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the message broker connection and subscriptions.

        Raises:
            MessageBrokerError: If initialization fails
        """

    @abstractmethod
    async def publish_event(self, event: DomainEvent) -> None:
        """
        Publish a domain event to all subscribers across all instances.

        Args:
            event: Domain event to publish

        Raises:
            MessageBrokerError: If publish fails
        """

    @abstractmethod
    async def publish_control_message(
        self, message_type: str, data: dict[str, Any]
    ) -> None:
        """
        Publish a control message to all subscribers.

        Control messages are used for coordination between instances
        (e.g., disconnect client, update connection state).

        Args:
            message_type: Type of control message
            data: Control message data

        Raises:
            MessageBrokerError: If publish fails
        """

    @abstractmethod
    async def subscribe(self, channel: str, callback: Callable) -> None:
        """
        Subscribe to a message channel with a callback.

        Args:
            channel: Channel name to subscribe to
            callback: Async or sync callback function to handle messages
                     Signature: callback(message: Dict[str, Any]) -> None

        Raises:
            MessageBrokerError: If subscription fails
        """

    @abstractmethod
    async def unsubscribe(self, channel: str, callback: Callable) -> None:
        """
        Unsubscribe from a message channel.

        Args:
            channel: Channel name to unsubscribe from
            callback: Callback to remove

        Raises:
            MessageBrokerError: If unsubscription fails
        """

    @abstractmethod
    def get_stats(self) -> dict[str, Any]:
        """
        Get message broker statistics.

        Returns:
            Dictionary with statistics (messages published/received, errors, etc.)
        """

    @abstractmethod
    def reset_stats(self) -> None:
        """Reset message broker statistics."""

    @abstractmethod
    async def close(self) -> None:
        """Close message broker connection and cleanup resources."""
