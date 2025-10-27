"""Mock notifier adapter for testing."""

import asyncio
import re
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from codetoreum.ports.exceptions import (
    ResourceNotFoundError,
    ValidationError,
)
from codetoreum.ports.output.notifier import (
    DeliveryStatus,
    INotifier,
    Notification,
    NotificationChannel,
    NotificationPriority,
    NotificationResult,
    RichContent,
)


class MockNotifierAdapter(INotifier):
    """
    Mock notifier for testing.

    Captures all notifications in memory without actually sending them.
    Useful for verifying notification behavior in tests.

    This adapter is thread-safe for concurrent test execution. All shared
    state modifications are protected by a lock.

    Attributes:
        _send_delay: Simulated send delay in seconds
        _simulate_failures: Whether to simulate random failures
        _failure_rate: Rate of simulated failures (0.0 to 1.0)
    """

    def __init__(
        self,
        send_delay: float = 0.0,
        simulate_failures: bool = False,
        failure_rate: float = 0.0,
    ):
        """
        Initialize the mock notifier adapter.

        Args:
            send_delay: Simulated send delay in seconds
            simulate_failures: Whether to simulate failures
            failure_rate: Rate of simulated failures (0.0 to 1.0)

        Raises:
            ValidationError: If parameters are invalid
        """
        if send_delay < 0:
            raise ValidationError("Send delay cannot be negative")
        if not 0.0 <= failure_rate <= 1.0:
            raise ValidationError("Failure rate must be between 0.0 and 1.0")

        self._send_delay = send_delay
        self._simulate_failures = simulate_failures
        self._failure_rate = failure_rate

        # Notification storage
        self._notifications: Dict[str, Dict[str, Any]] = {}
        self._templates: Dict[str, Dict[str, Any]] = {}

        # Notification history
        self._history: List[Dict[str, Any]] = []

        # Channel configuration
        self._channel_config: Dict[NotificationChannel, Dict[str, Any]] = {}

        # Statistics
        self._stats = {
            "total_sent": 0,
            "total_failed": 0,
            "by_channel": {},
        }

        # Thread safety
        self._lock = threading.Lock()
        self._failure_counter = 0

    def _should_fail(self) -> bool:
        """
        Determine if the current operation should fail.

        Returns:
            bool: True if should fail based on failure rate
        """
        if not self._simulate_failures:
            return False

        with self._lock:
            self._failure_counter += 1
            # Deterministic failure based on counter and rate
            return (self._failure_counter % max(1, int(1.0 / self._failure_rate))) == 0

    def _validate_recipient(self, channel: NotificationChannel, recipient: str) -> None:
        """
        Validate recipient format for channel.

        Args:
            channel: Notification channel
            recipient: Recipient identifier

        Raises:
            ValidationError: If recipient format is invalid
        """
        if not recipient or not recipient.strip():
            raise ValidationError("Recipient cannot be empty")

        if channel == NotificationChannel.EMAIL:
            # Basic email validation
            if "@" not in recipient or "." not in recipient:
                raise ValidationError(f"Invalid email address: {recipient}")
        elif channel == NotificationChannel.SLACK:
            # Slack channel or user ID
            if not (recipient.startswith("#") or recipient.startswith("@") or recipient.startswith("U")):
                raise ValidationError(f"Invalid Slack recipient: {recipient}")
        elif channel == NotificationChannel.SMS:
            # Basic phone number validation
            if not re.match(r'^\+?[0-9]{10,15}$', recipient.replace("-", "").replace(" ", "")):
                raise ValidationError(f"Invalid phone number: {recipient}")

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
            recipient: Recipient identifier
            subject: Notification subject
            message: Notification message
            priority: Notification priority
            metadata: Additional metadata

        Returns:
            NotificationResult: Send result

        Raises:
            ValidationError: Invalid recipient or message
        """
        self._validate_recipient(channel, recipient)

        if not subject or not subject.strip():
            raise ValidationError("Subject cannot be empty")

        if not message or not message.strip():
            raise ValidationError("Message cannot be empty")

        # Simulate delay
        if self._send_delay > 0:
            await asyncio.sleep(self._send_delay)

        # Check if should fail
        if self._should_fail():
            notification_id = str(uuid4())
            timestamp = datetime.now(timezone.utc)

            with self._lock:
                self._stats["total_failed"] += 1
                channel_name = channel.value
                if channel_name not in self._stats["by_channel"]:
                    self._stats["by_channel"][channel_name] = {"sent": 0, "failed": 0}
                self._stats["by_channel"][channel_name]["failed"] += 1

            return NotificationResult(
                success=False,
                notification_id=notification_id,
                error="Simulated failure",
                timestamp=timestamp,
            )

        # Create notification record
        notification_id = str(uuid4())
        timestamp = datetime.now(timezone.utc)

        notification_record = {
            "id": notification_id,
            "channel": channel,
            "recipient": recipient,
            "subject": subject,
            "message": message,
            "priority": priority,
            "metadata": metadata or {},
            "status": DeliveryStatus.SENT,
            "created_at": timestamp,
            "sent_at": timestamp,
        }

        with self._lock:
            self._notifications[notification_id] = notification_record
            self._history.append(notification_record.copy())

            # Update stats
            self._stats["total_sent"] += 1
            channel_name = channel.value
            if channel_name not in self._stats["by_channel"]:
                self._stats["by_channel"][channel_name] = {"sent": 0, "failed": 0}
            self._stats["by_channel"][channel_name]["sent"] += 1

        return NotificationResult(
            success=True,
            notification_id=notification_id,
            error=None,
            timestamp=timestamp,
        )

    async def send_rich(
        self,
        channel: NotificationChannel,
        recipient: str,
        content: RichContent,
        priority: NotificationPriority = NotificationPriority.NORMAL,
    ) -> NotificationResult:
        """
        Send rich content notification.

        Args:
            channel: Notification channel
            recipient: Recipient identifier
            content: Rich content
            priority: Notification priority

        Returns:
            NotificationResult: Send result

        Raises:
            ValidationError: Invalid content
        """
        self._validate_recipient(channel, recipient)

        if not content.title:
            raise ValidationError("Rich content title cannot be empty")

        if not content.body:
            raise ValidationError("Rich content body cannot be empty")

        # Use standard send with rich content converted to message
        message = f"{content.body}"
        if content.footer:
            message += f"\n\n{content.footer}"

        metadata = {
            "rich_content": True,
            "attachments_count": len(content.attachments),
            "actions_count": len(content.actions),
            "color": content.color,
            "thumbnail_url": content.thumbnail_url,
            "image_url": content.image_url,
        }

        return await self.send(
            channel=channel,
            recipient=recipient,
            subject=content.title,
            message=message,
            priority=priority,
            metadata=metadata,
        )

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
        """
        if not notifications:
            raise ValidationError("Notifications list cannot be empty")

        results = []
        for notification in notifications:
            result = await self.send(
                channel=notification.channel,
                recipient=notification.recipient,
                subject=notification.subject,
                message=notification.message,
                priority=notification.priority,
                metadata=notification.metadata,
            )
            results.append(result)

        return results

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
        """
        with self._lock:
            if template_id not in self._templates:
                raise ResourceNotFoundError("Template", template_id)

            template = self._templates[template_id]

            # Check channel matches
            if template["channel"] != channel:
                raise ValidationError(
                    f"Template '{template_id}' is for {template['channel'].value}, "
                    f"not {channel.value}"
                )

        # Simple variable substitution
        message = template["template"]
        subject = template.get("subject_template", "Notification")

        for key, value in variables.items():
            placeholder = f"{{{key}}}"
            message = message.replace(placeholder, str(value))
            subject = subject.replace(placeholder, str(value))

        # Check if any variables were not substituted
        if "{" in message or "{" in subject:
            raise ValidationError("Not all template variables were provided")

        return await self.send(
            channel=channel,
            recipient=recipient,
            subject=subject,
            message=message,
            priority=priority,
            metadata={"template_id": template_id, "variables": variables},
        )

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
        """
        with self._lock:
            if notification_id not in self._notifications:
                raise ResourceNotFoundError("Notification", notification_id)

            return self._notifications[notification_id]["status"]

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
        """
        if limit <= 0:
            raise ValidationError("Limit must be positive")

        with self._lock:
            history = list(self._history)

        # Apply filters
        if recipient:
            history = [n for n in history if n["recipient"] == recipient]

        if channel:
            history = [n for n in history if n["channel"] == channel]

        if since:
            history = [n for n in history if n["created_at"] >= since]

        # Sort by timestamp descending
        history.sort(key=lambda n: n["created_at"], reverse=True)

        return history[:limit]

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
        """
        with self._lock:
            if notification_id not in self._notifications:
                raise ResourceNotFoundError("Notification", notification_id)

            notification = self._notifications[notification_id]

            if notification["status"] == DeliveryStatus.PENDING:
                notification["status"] = DeliveryStatus.FAILED
                return True

            return False

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
        """
        if not template_id or not template_id.strip():
            raise ValidationError("Template ID cannot be empty")

        if not template or not template.strip():
            raise ValidationError("Template cannot be empty")

        with self._lock:
            self._templates[template_id] = {
                "id": template_id,
                "channel": channel,
                "template": template,
                "subject_template": subject_template or "Notification",
                "metadata": metadata or {},
                "created_at": datetime.now(timezone.utc),
            }

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
        """
        with self._lock:
            if template_id not in self._templates:
                raise ResourceNotFoundError("Template", template_id)

            del self._templates[template_id]

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
        """
        with self._lock:
            templates = list(self._templates.values())

        if channel:
            templates = [t for t in templates if t["channel"] == channel]

        return templates

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
        """
        try:
            self._validate_recipient(channel, recipient)
            return True
        except ValidationError:
            return False

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
        """
        with self._lock:
            if not since and not channel:
                return dict(self._stats)

            # Filter history
            history = list(self._history)

            if since:
                history = [n for n in history if n["created_at"] >= since]

            if channel:
                history = [n for n in history if n["channel"] == channel]

            # Calculate stats
            sent = len([n for n in history if n["status"] == DeliveryStatus.SENT])
            failed = len([n for n in history if n["status"] == DeliveryStatus.FAILED])

            return {
                "total_sent": sent,
                "total_failed": failed,
                "total": len(history),
            }

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
        """
        if not configuration:
            raise ValidationError("Configuration cannot be empty")

        with self._lock:
            self._channel_config[channel] = configuration.copy()

    async def health_check(self) -> Dict[NotificationChannel, bool]:
        """
        Check health of all configured channels.

        Returns:
            Dict[NotificationChannel, bool]: Channel health status
        """
        # All mock channels are always healthy
        return {
            NotificationChannel.EMAIL: True,
            NotificationChannel.SLACK: True,
            NotificationChannel.WEBHOOK: True,
            NotificationChannel.SMS: True,
        }

    # Helper methods for testing

    def clear(self) -> None:
        """Clear all notifications and history."""
        with self._lock:
            self._notifications.clear()
            self._history.clear()
            self._templates.clear()
            self._channel_config.clear()
            self._stats = {
                "total_sent": 0,
                "total_failed": 0,
                "by_channel": {},
            }
            self._failure_counter = 0

    def get_sent_notifications(
        self,
        recipient: Optional[str] = None,
        channel: Optional[NotificationChannel] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get all sent notifications.

        Args:
            recipient: Optional recipient filter
            channel: Optional channel filter

        Returns:
            List of notification records
        """
        with self._lock:
            notifications = list(self._notifications.values())

        if recipient:
            notifications = [n for n in notifications if n["recipient"] == recipient]

        if channel:
            notifications = [n for n in notifications if n["channel"] == channel]

        return notifications

    def get_notification_count(self) -> int:
        """
        Get total number of notifications.

        Returns:
            Total notification count
        """
        with self._lock:
            return len(self._notifications)

    def get_last_notification(self) -> Optional[Dict[str, Any]]:
        """
        Get the most recent notification.

        Returns:
            Last notification or None if no notifications
        """
        with self._lock:
            if not self._history:
                return None
            return self._history[-1].copy()

    def assert_notification_sent(
        self,
        recipient: str,
        subject_contains: Optional[str] = None,
        message_contains: Optional[str] = None,
    ) -> bool:
        """
        Assert that a notification was sent matching criteria.

        Args:
            recipient: Expected recipient
            subject_contains: Optional substring in subject
            message_contains: Optional substring in message

        Returns:
            bool: True if matching notification found
        """
        notifications = self.get_sent_notifications(recipient=recipient)

        for notification in notifications:
            if subject_contains and subject_contains not in notification["subject"]:
                continue
            if message_contains and message_contains not in notification["message"]:
                continue
            return True

        return False
