"""INotifier output port interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from codetoreum.domain.types import ChannelId, NotificationId, TemplateId, UserId


# ============================================================================
# Enums
# ============================================================================


class NotificationChannel(Enum):
    """Notification channels."""

    SLACK = "slack"
    EMAIL = "email"
    WEBHOOK = "webhook"
    SMS = "sms"


class NotificationPriority(Enum):
    """Notification priority levels."""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


class DeliveryStatus(Enum):
    """Notification delivery status."""

    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    BOUNCED = "bounced"


# ============================================================================
# Data Models
# ============================================================================


@dataclass
class Notification:
    """Notification data."""

    channel: NotificationChannel
    recipient: str
    subject: str
    message: str
    priority: NotificationPriority
    metadata: Dict[str, Any]


@dataclass
class NotificationResult:
    """Notification send result."""

    success: bool
    notification_id: str
    error: Optional[str]
    timestamp: datetime


@dataclass
class Attachment:
    """File attachment for notifications."""

    filename: str
    content: bytes
    content_type: str


@dataclass
class Action:
    """Action button for rich notifications."""

    label: str
    url: str
    style: Optional[str] = None  # primary, danger, default


@dataclass
class RichContent:
    """Rich notification content."""

    title: str
    body: str
    attachments: List[Attachment]
    actions: List[Action]
    color: Optional[str] = None
    footer: Optional[str] = None
    thumbnail_url: Optional[str] = None
    image_url: Optional[str] = None


# ============================================================================
# Port Interface
# ============================================================================


class INotifier(ABC):
    """Interface for sending notifications."""

    @abstractmethod
    async def send(
        self,
        channel: NotificationChannel,
        recipient: str,
        subject: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> NotificationResult:
        """
        Send a notification.

        Args:
            channel: Notification channel
            recipient: Recipient identifier (email, channel ID, phone, etc.)
            subject: Notification subject
            message: Notification message (supports markdown)
            priority: Notification priority
            metadata: Additional metadata

        Returns:
            NotificationResult: Send result

        Raises:
            ValidationError: Invalid recipient or message
            UnsupportedChannelError: Channel not supported
            NotificationError: Send failed
        """
        pass

    @abstractmethod
    async def send_rich(
        self,
        channel: NotificationChannel,
        recipient: str,
        content: RichContent,
        priority: NotificationPriority = NotificationPriority.NORMAL,
    ) -> NotificationResult:
        """
        Send rich content notification (attachments, embeds, etc.).

        Args:
            channel: Notification channel
            recipient: Recipient identifier
            content: Rich content
            priority: Notification priority

        Returns:
            NotificationResult: Send result

        Raises:
            ValidationError: Invalid content
            UnsupportedChannelError: Channel doesn't support rich content
            NotificationError: Send failed
        """
        pass

    @abstractmethod
    async def send_batch(
        self,
        notifications: List[Notification],
    ) -> List[NotificationResult]:
        """
        Send multiple notifications.

        Args:
            notifications: List of notifications to send

        Returns:
            List[NotificationResult]: Results for each notification

        Raises:
            ValidationError: Invalid notification data
            NotificationError: Batch send failed
        """
        pass

    @abstractmethod
    async def send_template(
        self,
        channel: NotificationChannel,
        recipient: str,
        template_id: str,
        variables: Dict[str, Any],
        priority: NotificationPriority = NotificationPriority.NORMAL,
    ) -> NotificationResult:
        """
        Send notification using a template.

        Args:
            channel: Notification channel
            recipient: Recipient identifier
            template_id: Template identifier
            variables: Template variables
            priority: Notification priority

        Returns:
            NotificationResult: Send result

        Raises:
            ResourceNotFoundError: Template doesn't exist
            ValidationError: Invalid template variables
            NotificationError: Send failed
        """
        pass

    @abstractmethod
    async def get_delivery_status(
        self,
        notification_id: str,
    ) -> DeliveryStatus:
        """
        Get notification delivery status.

        Args:
            notification_id: Notification identifier

        Returns:
            DeliveryStatus: Current delivery status

        Raises:
            ResourceNotFoundError: Notification doesn't exist
            NotificationError: Status check failed
        """
        pass

    @abstractmethod
    async def get_notification_history(
        self,
        recipient: Optional[str] = None,
        channel: Optional[NotificationChannel] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get notification history.

        Args:
            recipient: Optional recipient filter
            channel: Optional channel filter
            since: Optional time filter
            limit: Maximum number of results

        Returns:
            List[Dict[str, Any]]: List of notification records

        Raises:
            NotificationError: Query failed
        """
        pass

    @abstractmethod
    async def cancel_notification(
        self,
        notification_id: str,
    ) -> bool:
        """
        Cancel a pending notification.

        Args:
            notification_id: Notification identifier

        Returns:
            bool: True if cancelled, False if already sent

        Raises:
            ResourceNotFoundError: Notification doesn't exist
            NotificationError: Cancel failed
        """
        pass

    @abstractmethod
    async def register_template(
        self,
        template_id: str,
        channel: NotificationChannel,
        template: str,
        subject_template: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Register a notification template.

        Args:
            template_id: Unique template identifier
            channel: Channel this template is for
            template: Template string with variable placeholders
            subject_template: Optional subject template
            metadata: Optional template metadata

        Raises:
            ValidationError: Invalid template
            NotificationError: Registration failed
        """
        pass

    @abstractmethod
    async def unregister_template(
        self,
        template_id: str,
    ) -> None:
        """
        Unregister a notification template.

        Args:
            template_id: Template identifier

        Raises:
            ResourceNotFoundError: Template doesn't exist
            NotificationError: Unregistration failed
        """
        pass

    @abstractmethod
    async def list_templates(
        self,
        channel: Optional[NotificationChannel] = None,
    ) -> List[Dict[str, Any]]:
        """
        List registered templates.

        Args:
            channel: Optional channel filter

        Returns:
            List[Dict[str, Any]]: List of template information

        Raises:
            NotificationError: Query failed
        """
        pass

    @abstractmethod
    async def test_channel(
        self,
        channel: NotificationChannel,
        recipient: str,
    ) -> bool:
        """
        Test if a channel is properly configured.

        Args:
            channel: Channel to test
            recipient: Test recipient

        Returns:
            bool: True if test successful

        Raises:
            NotificationError: Test failed
        """
        pass

    @abstractmethod
    async def get_statistics(
        self,
        since: Optional[datetime] = None,
        channel: Optional[NotificationChannel] = None,
    ) -> Dict[str, Any]:
        """
        Get notification statistics.

        Args:
            since: Optional time filter
            channel: Optional channel filter

        Returns:
            Dict[str, Any]: Statistics (sent count, failed count, etc.)

        Raises:
            NotificationError: Query failed
        """
        pass

    @abstractmethod
    async def configure_channel(
        self,
        channel: NotificationChannel,
        configuration: Dict[str, Any],
    ) -> None:
        """
        Configure a notification channel.

        Args:
            channel: Channel to configure
            configuration: Channel-specific configuration

        Raises:
            ValidationError: Invalid configuration
            NotificationError: Configuration failed
        """
        pass

    @abstractmethod
    async def health_check(self) -> Dict[NotificationChannel, bool]:
        """
        Check health of all configured channels.

        Returns:
            Dict[NotificationChannel, bool]: Channel health status

        Raises:
            NotificationError: Health check failed
        """
        pass
