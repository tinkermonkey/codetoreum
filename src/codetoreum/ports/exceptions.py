"""Port layer exceptions."""


class PortError(Exception):
    """Base exception for port operations."""


class ResourceNotFoundError(PortError):
    """Resource doesn't exist."""

    def __init__(self, resource_type: str, resource_id: str):
        """
        Initialize ResourceNotFoundError.

        Args: resource_type: Type of resource (WorkItem, Agent, etc.)
            resource_id: Resource identifier
        """
        super().__init__(f"{resource_type} not found: {resource_id}")
        self.resource_type = resource_type
        self.resource_id = resource_id


class ValidationError(PortError):
    """Invalid input or configuration."""


class ExternalServiceError(PortError):
    """External service failure."""

    def __init__(self, *, service: str, message: str):
        """
        Initialize ExternalServiceError.

        Args: service: Name of external service (keyword-only)
            message: Error message (keyword-only)

        Raises:
            TypeError: If positional arguments are used instead of keyword arguments
        """
        super().__init__(f"{service} error: {message}")
        self.service = service


class AuthenticationError(PortError):
    """Authentication failure."""


class PermissionError(PortError):
    """Permission denied."""


class ConcurrencyConflictError(PortError):
    """Concurrent modification detected."""


class RateLimitError(PortError):
    """Rate limit exceeded."""

    def __init__(self, retry_after: int | None = None):
        """
        Initialize RateLimitError.

        Args: retry_after: Seconds to wait before retrying (optional)
        """
        super().__init__(f"Rate limit exceeded, retry after {retry_after}s")
        self.retry_after = retry_after


class TimeoutError(PortError):
    """Operation timed out."""


# Ticket System Errors


class TicketSystemError(PortError):
    """Ticket system operation failed."""


class WorkItemNotFoundError(TicketSystemError):
    """Work item doesn't exist."""


class ColumnNotFoundError(TicketSystemError):
    """Column doesn't exist."""


class ProjectNotFoundError(TicketSystemError):
    """Project doesn't exist."""


# LLM Provider Errors


class LLMProviderError(PortError):
    """LLM provider operation failed."""


class PromptTooLongError(LLMProviderError):
    """Prompt exceeds token limit."""

    def __init__(self, token_count: int, max_tokens: int):
        """
        Initialize PromptTooLongError.

        Args: token_count: Actual token count
            max_tokens: Maximum allowed tokens
        """
        super().__init__(f"Prompt too long: {token_count} > {max_tokens}")
        self.token_count = token_count
        self.max_tokens = max_tokens


class ToolExecutionError(LLMProviderError):
    """Tool execution failed."""


class UnsupportedFeatureError(LLMProviderError):
    """Provider doesn't support requested feature."""


class StreamingError(LLMProviderError):
    """Streaming operation failed."""


class ConversationNotFoundError(LLMProviderError):
    """Conversation doesn't exist."""


class ConversationExpiredError(LLMProviderError):
    """Conversation has expired."""


class EmptyAgentResponseError(LLMProviderError):
    """Agent returned an empty response."""

    def __init__(self, work_item_id: str):
        """
        Initialize EmptyAgentResponseError.

        Args: work_item_id: ID of the work item the agent was responding to
        """
        super().__init__(f"Agent returned empty response for work item: {work_item_id}")
        self.work_item_id = work_item_id


# Repository Errors


class RepositoryError(PortError):
    """Repository operation failed."""


class MergeConflictError(RepositoryError):
    """Merge conflict detected."""


# Container Errors


class ContainerError(PortError):
    """Container operation failed."""


class ContainerExecutionError(ContainerError):
    """Container execution failed."""


class ContainerTimeoutError(ContainerError):
    """Container execution timed out."""


class ImageNotFoundError(ContainerError):
    """Container image doesn't exist."""


class ContainerNotRunningError(ContainerError):
    """Container is not running."""


# Event Store Errors


class EventStoreError(PortError):
    """Event store operation failed."""


class StreamNotFoundError(EventStoreError):
    """Event stream doesn't exist."""


class SnapshotNotFoundError(EventStoreError):
    """Snapshot doesn't exist."""


# Storage Errors


class StorageError(PortError):
    """Storage operation failed."""


# Metrics Errors


class MetricsError(PortError):
    """Metrics operation failed."""


# Notifier Errors


class NotificationError(PortError):
    """Notification operation failed."""


class UnsupportedChannelError(NotificationError):
    """Notification channel not supported."""


class ChannelNotFoundError(NotificationError):
    """Notification channel doesn't exist."""


class TemplateNotFoundError(NotificationError):
    """Notification template doesn't exist."""


class MetricNotFoundError(MetricsError):
    """Metric doesn't exist."""

    def __init__(self, metric_name: str):
        """
        Initialize MetricNotFoundError.

        Args: metric_name: Name of metric
        """
        super().__init__(f"Metric not found: {metric_name}")
        self.metric_name = metric_name


class ComponentNotFoundError(MetricsError):
    """Component doesn't exist."""

    def __init__(self, component_name: str):
        """
        Initialize ComponentNotFoundError.

        Args: component_name: Name of component
        """
        super().__init__(f"Component not found: {component_name}")
        self.component_name = component_name


class ConfigurationError(PortError):
    """Raised when adapter or service configuration is invalid or incomplete."""


class BoardStructureDriftError(PortError):
    """Board structure has unsafe drift that cannot be auto-corrected.

    Raised when board reconciliation detects structural changes that would
    require manual intervention to resolve safely (e.g., renaming a column
    that already contains work items with ambiguous mapping).
    """

    def __init__(self, board_id: str, drift_description: str):
        """
        Initialize BoardStructureDriftError.

        Args:
            board_id: ID of the board with drift
            drift_description: Description of the detected drift
        """
        super().__init__(f"Board structure drift detected on board {board_id}: {drift_description}")
        self.board_id = board_id
        self.drift_description = drift_description
