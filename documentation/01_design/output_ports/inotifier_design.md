# INotifier Output Port Design

## Overview

The `INotifier` port provides an abstraction for sending notifications to external systems and users. This enables alerting, status updates, and communication through various channels.

## Port Interface

```python
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

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

class INotifier(ABC):
    """Interface for sending notifications."""

    @abstractmethod
    async def send(self,
                   channel: NotificationChannel,
                   recipient: str,
                   subject: str,
                   message: str,
                   priority: NotificationPriority = NotificationPriority.NORMAL,
                   metadata: Optional[Dict[str, Any]] = None) -> NotificationResult:
        """
        Send a notification.

        Args:
            channel: Notification channel
            recipient: Recipient identifier (email, channel ID, etc.)
            subject: Notification subject
            message: Notification message (supports markdown)
            priority: Notification priority
            metadata: Additional metadata

        Returns:
            NotificationResult: Send result

        Raises:
            NotificationError: Send failed
        """
        pass

    @abstractmethod
    async def send_rich(self,
                       channel: NotificationChannel,
                       recipient: str,
                       content: RichContent) -> NotificationResult:
        """Send rich content notification (attachments, embeds, etc.)."""
        pass

    @abstractmethod
    async def send_batch(self,
                        notifications: List[Notification]) -> List[NotificationResult]:
        """Send multiple notifications."""
        pass

    @abstractmethod
    async def get_delivery_status(self, notification_id: str) -> DeliveryStatus:
        """Get notification delivery status."""
        pass
```

## Data Models

```python
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
class RichContent:
    """Rich notification content."""
    title: str
    body: str
    attachments: List[Attachment]
    actions: List[Action]
    color: Optional[str]
```

## Adapter Implementations

### Slack Notifier

```python
class SlackNotifier(INotifier):
    """Slack notification implementation."""

    def __init__(self, webhook_url: str, default_channel: str):
        self.webhook_url = webhook_url
        self.default_channel = default_channel

    async def send(self,
                   channel: NotificationChannel,
                   recipient: str,
                   subject: str,
                   message: str,
                   priority: NotificationPriority = NotificationPriority.NORMAL,
                   metadata: Optional[Dict[str, Any]] = None) -> NotificationResult:
        """Send to Slack."""
        if channel != NotificationChannel.SLACK:
            raise NotificationError(f"Unsupported channel: {channel}")

        # Prepare Slack message
        slack_msg = {
            "channel": recipient or self.default_channel,
            "text": subject,
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": subject}
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": message}
                }
            ]
        }

        # Send to Slack
        async with aiohttp.ClientSession() as session:
            async with session.post(self.webhook_url, json=slack_msg) as resp:
                if resp.status == 200:
                    return NotificationResult(
                        success=True,
                        notification_id=str(uuid4()),
                        error=None,
                        timestamp=datetime.utcnow()
                    )
                else:
                    return NotificationResult(
                        success=False,
                        notification_id="",
                        error=f"Slack error: {resp.status}",
                        timestamp=datetime.utcnow()
                    )
```

### Email Notifier

```python
class EmailNotifier(INotifier):
    """Email notification implementation."""

    def __init__(self,
                 smtp_host: str,
                 smtp_port: int,
                 username: str,
                 password: str,
                 from_address: str):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_address = from_address

    async def send(self,
                   channel: NotificationChannel,
                   recipient: str,
                   subject: str,
                   message: str,
                   priority: NotificationPriority = NotificationPriority.NORMAL,
                   metadata: Optional[Dict[str, Any]] = None) -> NotificationResult:
        """Send email via SMTP."""
        # Implementation using aiosmtplib
        pass
```

### Mock Notifier (Testing)

```python
class MockNotifier(INotifier):
    """Mock notifier for testing."""

    def __init__(self):
        self.sent_notifications: List[Notification] = []

    async def send(self,
                   channel: NotificationChannel,
                   recipient: str,
                   subject: str,
                   message: str,
                   priority: NotificationPriority = NotificationPriority.NORMAL,
                   metadata: Optional[Dict[str, Any]] = None) -> NotificationResult:
        """Record notification."""
        notification = Notification(
            channel=channel,
            recipient=recipient,
            subject=subject,
            message=message,
            priority=priority,
            metadata=metadata or {}
        )
        self.sent_notifications.append(notification)

        return NotificationResult(
            success=True,
            notification_id=str(uuid4()),
            error=None,
            timestamp=datetime.utcnow()
        )
```

## Common Use Cases

### Alert Notifications
- Agent execution failures
- System errors and exceptions
- Resource limit warnings

### Status Updates
- Pipeline completion
- Review cycle results
- Deployment status

### User Notifications
- Work item assignments
- Review requests
- Feedback responses

## Integration Points

### Used By
- Alert Service
- Workflow Orchestrator
- Error Handler

### Dependencies
- None (standalone port)

## Implementation Notes

1. **Retry Logic**: Implement retry for transient failures
2. **Rate Limiting**: Respect channel rate limits
3. **Batching**: Batch notifications when possible
4. **Templates**: Use templates for consistent formatting
5. **Opt-out**: Support notification preferences/opt-out
