"""Port layer exceptions."""

from typing import Optional


class PortError(Exception):
    """Base exception for port operations."""

    pass


class ResourceNotFoundError(PortError):
    """Resource doesn't exist."""

    def __init__(self, resource_type: str, resource_id: str):
        """
        Initialize ResourceNotFoundError.

        Args:
            resource_type: Type of resource (WorkItem, Agent, etc.)
            resource_id: Resource identifier
        """
        super().__init__(f"{resource_type} not found: {resource_id}")
        self.resource_type = resource_type
        self.resource_id = resource_id


class ValidationError(PortError):
    """Invalid input or configuration."""

    pass


class ExternalServiceError(PortError):
    """External service failure."""

    def __init__(self, service: str, message: str):
        """
        Initialize ExternalServiceError.

        Args:
            service: Name of external service
            message: Error message
        """
        super().__init__(f"{service} error: {message}")
        self.service = service


class AuthenticationError(PortError):
    """Authentication failure."""

    pass


class PermissionError(PortError):
    """Permission denied."""

    pass


class ConcurrencyConflictError(PortError):
    """Concurrent modification detected."""

    pass


class RateLimitError(PortError):
    """Rate limit exceeded."""

    def __init__(self, retry_after: Optional[int] = None):
        """
        Initialize RateLimitError.

        Args:
            retry_after: Seconds to wait before retrying (optional)
        """
        super().__init__(f"Rate limit exceeded, retry after {retry_after}s")
        self.retry_after = retry_after


class TimeoutError(PortError):
    """Operation timed out."""

    pass


# Ticket System Errors


class TicketSystemError(PortError):
    """Ticket system operation failed."""

    pass


class WorkItemNotFoundError(TicketSystemError):
    """Work item doesn't exist."""

    pass


class ColumnNotFoundError(TicketSystemError):
    """Column doesn't exist."""

    pass


class ProjectNotFoundError(TicketSystemError):
    """Project doesn't exist."""

    pass


# LLM Provider Errors


class LLMProviderError(PortError):
    """LLM provider operation failed."""

    pass


class PromptTooLongError(LLMProviderError):
    """Prompt exceeds token limit."""

    def __init__(self, token_count: int, max_tokens: int):
        """
        Initialize PromptTooLongError.

        Args:
            token_count: Actual token count
            max_tokens: Maximum allowed tokens
        """
        super().__init__(f"Prompt too long: {token_count} > {max_tokens}")
        self.token_count = token_count
        self.max_tokens = max_tokens


class ToolExecutionError(LLMProviderError):
    """Tool execution failed."""

    pass


class UnsupportedFeatureError(LLMProviderError):
    """Provider doesn't support requested feature."""

    pass


class StreamingError(LLMProviderError):
    """Streaming operation failed."""

    pass


class ConversationNotFoundError(LLMProviderError):
    """Conversation doesn't exist."""

    pass


class ConversationExpiredError(LLMProviderError):
    """Conversation has expired."""

    pass


class EmptyAgentResponseError(LLMProviderError):
    """Agent returned an empty response."""

    def __init__(self, work_item_id: str):
        """
        Initialize EmptyAgentResponseError.

        Args:
            work_item_id: ID of the work item the agent was responding to
        """
        super().__init__(
            f"Agent returned empty response for work item: {work_item_id}"
        )
        self.work_item_id = work_item_id


# Repository Errors


class RepositoryError(PortError):
    """Repository operation failed."""

    pass


class MergeConflictError(RepositoryError):
    """Merge conflict detected."""

    pass


# Container Errors


class ContainerError(PortError):
    """Container operation failed."""

    pass


class ContainerExecutionError(ContainerError):
    """Container execution failed."""

    pass


class ContainerTimeoutError(ContainerError):
    """Container execution timed out."""

    pass


class ImageNotFoundError(ContainerError):
    """Container image doesn't exist."""

    pass


class ContainerNotRunningError(ContainerError):
    """Container is not running."""

    pass


# Event Store Errors


class EventStoreError(PortError):
    """Event store operation failed."""

    pass


class StreamNotFoundError(EventStoreError):
    """Event stream doesn't exist."""

    pass


class SnapshotNotFoundError(EventStoreError):
    """Snapshot doesn't exist."""

    pass


# Storage Errors


class StorageError(PortError):
    """Storage operation failed."""

    pass


# Metrics Errors


class MetricsError(PortError):
    """Metrics operation failed."""

    pass


# Notifier Errors


class NotificationError(PortError):
    """Notification operation failed."""

    pass


class UnsupportedChannelError(NotificationError):
    """Notification channel not supported."""

    pass


class ChannelNotFoundError(NotificationError):
    """Notification channel doesn't exist."""

    pass


class TemplateNotFoundError(NotificationError):
    """Notification template doesn't exist."""

    pass


class MetricNotFoundError(MetricsError):
    """Metric doesn't exist."""

    def __init__(self, metric_name: str):
        """
        Initialize MetricNotFoundError.

        Args:
            metric_name: Name of metric
        """
        super().__init__(f"Metric not found: {metric_name}")
        self.metric_name = metric_name


class ComponentNotFoundError(MetricsError):
    """Component doesn't exist."""

    def __init__(self, component_name: str):
        """
        Initialize ComponentNotFoundError.

        Args:
            component_name: Name of component
        """
        super().__init__(f"Component not found: {component_name}")
        self.component_name = component_name
