"""Contract tests for INotifier interface.

These tests verify the contract and data models for the INotifier interface.
"""

from datetime import UTC, datetime
from types import MappingProxyType
from uuid import uuid4

import pytest

from codetoreum.ports.output.notifier import (
    Action,
    Attachment,
    DeliveryStatus,
    Notification,
    NotificationChannel,
    NotificationPriority,
    NotificationResult,
    RichContent,
)


class TestNotificationDataModels:
    """Test validation and construction of notification data models."""

    def test_notification_valid(self) -> None:
        """Test creating a valid notification."""
        notification = Notification(
            channel=NotificationChannel.EMAIL,
            recipient="user@example.com",
            subject="Test Subject",
            message="Test Message",
            priority=NotificationPriority.NORMAL,
            metadata=MappingProxyType({"key": "value"}),
        )

        assert notification.channel == NotificationChannel.EMAIL
        assert notification.recipient == "user@example.com"
        assert notification.subject == "Test Subject"
        assert notification.message == "Test Message"
        assert notification.priority == NotificationPriority.NORMAL

    def test_notification_empty_recipient(self) -> None:
        """Test that empty recipient raises ValueError."""
        with pytest.raises(ValueError, match="recipient must be a non-empty string"):
            Notification(
                channel=NotificationChannel.EMAIL,
                recipient="",
                subject="Test",
                message="Message",
                priority=NotificationPriority.NORMAL,
                metadata=MappingProxyType({}),
            )

    def test_notification_empty_subject(self) -> None:
        """Test that empty subject raises ValueError."""
        with pytest.raises(ValueError, match="subject must be a non-empty string"):
            Notification(
                channel=NotificationChannel.EMAIL,
                recipient="user@example.com",
                subject="",
                message="Message",
                priority=NotificationPriority.NORMAL,
                metadata=MappingProxyType({}),
            )

    def test_notification_empty_message(self) -> None:
        """Test that empty message raises ValueError."""
        with pytest.raises(ValueError, match="message must be a non-empty string"):
            Notification(
                channel=NotificationChannel.EMAIL,
                recipient="user@example.com",
                subject="Test",
                message="",
                priority=NotificationPriority.NORMAL,
                metadata=MappingProxyType({}),
            )

    def test_notification_immutable(self) -> None:
        """Test that notification is immutable."""
        notification = Notification(
            channel=NotificationChannel.EMAIL,
            recipient="user@example.com",
            subject="Test",
            message="Message",
            priority=NotificationPriority.NORMAL,
            metadata=MappingProxyType({}),
        )

        with pytest.raises(AttributeError):
            notification.subject = "Modified"

    def test_notification_result_valid(self) -> None:
        """Test creating a valid notification result."""
        now = datetime.now(UTC)
        result = NotificationResult(
            success=True,
            notification_id=str(uuid4()),
            error=None,
            timestamp=now,
        )

        assert result.success is True
        assert result.error is None
        assert result.timestamp == now

    def test_notification_result_with_error(self) -> None:
        """Test creating a notification result with error."""
        now = datetime.now(UTC)
        result = NotificationResult(
            success=False,
            notification_id=str(uuid4()),
            error="Send failed",
            timestamp=now,
        )

        assert result.success is False
        assert result.error == "Send failed"

    def test_notification_result_empty_notification_id(self) -> None:
        """Test that empty notification_id raises ValueError."""
        with pytest.raises(ValueError, match="notification_id must be a non-empty string"):
            NotificationResult(
                success=True,
                notification_id="",
                error=None,
                timestamp=datetime.now(UTC),
            )

    def test_notification_result_invalid_error_type(self) -> None:
        """Test that invalid error type raises ValueError."""
        with pytest.raises(ValueError, match="error must be a non-empty string or None"):
            NotificationResult(
                success=False,
                notification_id=str(uuid4()),
                error="",
                timestamp=datetime.now(UTC),
            )

    def test_notification_result_invalid_timestamp(self) -> None:
        """Test that invalid timestamp raises ValueError."""
        with pytest.raises(ValueError, match="timestamp must be a datetime instance"):
            NotificationResult(
                success=True,
                notification_id=str(uuid4()),
                error=None,
                timestamp="2024-01-01",
            )

    def test_attachment_valid(self) -> None:
        """Test creating a valid attachment."""
        attachment = Attachment(
            filename="test.pdf",
            content=b"PDF content",
            content_type="application/pdf",
        )

        assert attachment.filename == "test.pdf"
        assert attachment.content == b"PDF content"
        assert attachment.content_type == "application/pdf"

    def test_attachment_empty_filename(self) -> None:
        """Test that empty filename raises ValueError."""
        with pytest.raises(ValueError, match="filename must be a non-empty string"):
            Attachment(
                filename="",
                content=b"content",
                content_type="text/plain",
            )

    def test_attachment_empty_content(self) -> None:
        """Test that empty content raises ValueError."""
        with pytest.raises(ValueError, match="content must be non-empty bytes"):
            Attachment(
                filename="test.txt",
                content=b"",
                content_type="text/plain",
            )

    def test_attachment_invalid_content_type(self) -> None:
        """Test that empty content_type raises ValueError."""
        with pytest.raises(ValueError, match="content_type must be a non-empty string"):
            Attachment(
                filename="test.txt",
                content=b"content",
                content_type="",
            )

    def test_action_valid(self) -> None:
        """Test creating a valid action."""
        action = Action(
            label="Click me",
            url="https://example.com",
            style="primary",
        )

        assert action.label == "Click me"
        assert action.url == "https://example.com"
        assert action.style == "primary"

    def test_action_without_style(self) -> None:
        """Test creating an action without style."""
        action = Action(
            label="Click me",
            url="https://example.com",
        )

        assert action.style is None

    def test_action_empty_label(self) -> None:
        """Test that empty label raises ValueError."""
        with pytest.raises(ValueError, match="label must be a non-empty string"):
            Action(
                label="",
                url="https://example.com",
            )

    def test_action_empty_url(self) -> None:
        """Test that empty url raises ValueError."""
        with pytest.raises(ValueError, match="url must be a non-empty string"):
            Action(
                label="Click me",
                url="",
            )

    def test_action_invalid_style(self) -> None:
        """Test that invalid style raises ValueError."""
        with pytest.raises(ValueError, match="style must be 'primary', 'danger', 'default', or None"):
            Action(
                label="Click me",
                url="https://example.com",
                style="invalid",
            )

    def test_rich_content_valid(self) -> None:
        """Test creating valid rich content."""
        action = Action(label="Button", url="https://example.com")
        attachment = Attachment(filename="file.pdf", content=b"content", content_type="application/pdf")

        content = RichContent(
            title="Title",
            body="Body text",
            attachments=(attachment,),
            actions=(action,),
            color="#FF0000",
            footer="Footer",
        )

        assert content.title == "Title"
        assert content.body == "Body text"
        assert len(content.attachments) == 1
        assert len(content.actions) == 1
        assert content.color == "#FF0000"

    def test_rich_content_empty_title(self) -> None:
        """Test that empty title raises ValueError."""
        with pytest.raises(ValueError, match="title must be a non-empty string"):
            RichContent(
                title="",
                body="Body",
                attachments=(),
                actions=(),
            )

    def test_rich_content_empty_body(self) -> None:
        """Test that empty body raises ValueError."""
        with pytest.raises(ValueError, match="body must be a non-empty string"):
            RichContent(
                title="Title",
                body="",
                attachments=(),
                actions=(),
            )

    def test_rich_content_invalid_attachments_type(self) -> None:
        """Test that invalid attachments type raises ValueError."""
        with pytest.raises(ValueError, match="attachments must be a tuple of Attachment instances"):
            RichContent(
                title="Title",
                body="Body",
                attachments=[],
                actions=(),
            )

    def test_rich_content_invalid_attachment_instance(self) -> None:
        """Test that invalid attachment instance raises ValueError."""
        with pytest.raises(ValueError, match="all attachments must be Attachment instances"):
            RichContent(
                title="Title",
                body="Body",
                attachments=("not_an_attachment",),
                actions=(),
            )

    def test_rich_content_invalid_actions_type(self) -> None:
        """Test that invalid actions type raises ValueError."""
        with pytest.raises(ValueError, match="actions must be a tuple of Action instances"):
            RichContent(
                title="Title",
                body="Body",
                attachments=(),
                actions=[],
            )

    def test_rich_content_invalid_action_instance(self) -> None:
        """Test that invalid action instance raises ValueError."""
        with pytest.raises(ValueError, match="all actions must be Action instances"):
            RichContent(
                title="Title",
                body="Body",
                attachments=(),
                actions=("not_an_action",),
            )

    def test_rich_content_empty_color(self) -> None:
        """Test that empty color raises ValueError."""
        with pytest.raises(ValueError, match="color must be a non-empty string or None"):
            RichContent(
                title="Title",
                body="Body",
                attachments=(),
                actions=(),
                color="",
            )

    def test_rich_content_empty_footer(self) -> None:
        """Test that empty footer raises ValueError."""
        with pytest.raises(ValueError, match="footer must be a non-empty string or None"):
            RichContent(
                title="Title",
                body="Body",
                attachments=(),
                actions=(),
                footer="",
            )

    def test_rich_content_empty_thumbnail_url(self) -> None:
        """Test that empty thumbnail_url raises ValueError."""
        with pytest.raises(ValueError, match="thumbnail_url must be a non-empty string or None"):
            RichContent(
                title="Title",
                body="Body",
                attachments=(),
                actions=(),
                thumbnail_url="",
            )

    def test_rich_content_empty_image_url(self) -> None:
        """Test that empty image_url raises ValueError."""
        with pytest.raises(ValueError, match="image_url must be a non-empty string or None"):
            RichContent(
                title="Title",
                body="Body",
                attachments=(),
                actions=(),
                image_url="",
            )


class TestNotificationChannelEnum:
    """Test NotificationChannel enum."""

    def test_slack_channel(self) -> None:
        """Test SLACK channel value."""
        assert NotificationChannel.SLACK.value == "slack"

    def test_email_channel(self) -> None:
        """Test EMAIL channel value."""
        assert NotificationChannel.EMAIL.value == "email"

    def test_webhook_channel(self) -> None:
        """Test WEBHOOK channel value."""
        assert NotificationChannel.WEBHOOK.value == "webhook"

    def test_sms_channel(self) -> None:
        """Test SMS channel value."""
        assert NotificationChannel.SMS.value == "sms"

    def test_all_channels(self) -> None:
        """Test that all channels are defined."""
        channels = {c.value for c in NotificationChannel}
        assert channels == {"slack", "email", "webhook", "sms"}


class TestNotificationPriorityEnum:
    """Test NotificationPriority enum."""

    def test_priority_values(self) -> None:
        """Test priority values."""
        assert NotificationPriority.LOW.value == 1
        assert NotificationPriority.NORMAL.value == 2
        assert NotificationPriority.HIGH.value == 3
        assert NotificationPriority.URGENT.value == 4

    def test_priority_ordering(self) -> None:
        """Test priority comparison."""
        assert NotificationPriority.LOW.value < NotificationPriority.NORMAL.value
        assert NotificationPriority.NORMAL.value < NotificationPriority.HIGH.value
        assert NotificationPriority.HIGH.value < NotificationPriority.URGENT.value


class TestDeliveryStatusEnum:
    """Test DeliveryStatus enum."""

    def test_delivery_status_values(self) -> None:
        """Test delivery status values."""
        assert DeliveryStatus.PENDING.value == "pending"
        assert DeliveryStatus.SENT.value == "sent"
        assert DeliveryStatus.DELIVERED.value == "delivered"
        assert DeliveryStatus.FAILED.value == "failed"
        assert DeliveryStatus.BOUNCED.value == "bounced"

    def test_all_statuses(self) -> None:
        """Test that all statuses are defined."""
        statuses = {s.value for s in DeliveryStatus}
        assert statuses == {"pending", "sent", "delivered", "failed", "bounced"}
