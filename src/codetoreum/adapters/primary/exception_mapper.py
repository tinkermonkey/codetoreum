"""
Exception Mapper

Maps domain and port layer exceptions to appropriate HTTP status codes and responses.
This provides a centralized mapping from business logic exceptions to HTTP exceptions.

Design:
- Follows hexagonal architecture principles
- Primary adapter concerns (HTTP status codes) separated from domain concerns
- Type-safe exception handling (no string matching)
- Single responsibility: translate exceptions to HTTP responses
"""

from typing import Optional

from fastapi import HTTPException, status

from codetoreum.domain.exceptions import (
    AgentNotFoundError,
    ConfigNotFoundError,
    DomainError,
    ExecutionNotFoundError,
    InvalidStateError,
    PipelineNotFoundError,
    WorkItemNotFoundError as DomainWorkItemNotFoundError,
    WorkspaceNotFoundError,
)
from codetoreum.infrastructure.logging import get_logger
from codetoreum.ports.exceptions import (
    AuthenticationError,
    ConcurrencyConflictError,
    EmptyAgentResponseError,
    ExternalServiceError,
    PortError,
    RateLimitError,
    ResourceNotFoundError,
    TimeoutError,
    ValidationError as PortValidationError,
)
from codetoreum.ports.input.exceptions import (
from codetoreum.infrastructure.error_ids import ErrorRegistry
    AgentExecutionNotFoundError,
    AgentNotFoundError as InputPortAgentNotFoundError,
    ArtifactNotFoundError,
    CommandFileNotFoundError,
    CommandNotFoundError,
    PermissionError as InputPortPermissionError,
    PipelineNotFoundError as InputPortPipelineNotFoundError,
    PortException,
    ProjectNotFoundError,
    StageNotFoundError,
    SubAgentNotFoundError,
    ValidationError as InputPortValidationError,
    VariableNotFoundError,
    WorkflowNotActiveError,
    WorkflowNotFoundError,
    WorkflowNotPausedError,
    WorkItemNotFoundError as InputPortWorkItemNotFoundError,
)

logger = get_logger(__name__)


def map_exception_to_http(exc: Exception, default_detail: Optional[str] = None) -> HTTPException:
    """
    Map domain, port, and input port exceptions to HTTP exceptions.

    This function provides centralized exception mapping following hexagonal architecture:
    - Domain exceptions: Business rule violations
    - Port exceptions: Infrastructure/external service errors
    - Input port exceptions: Command/query execution errors

    Args:
        exc: The exception to map
        default_detail: Optional default detail message if exception message is empty

    Returns:
        HTTPException with appropriate status code and detail message

    Design Notes:
        - Type-safe: Uses isinstance checks instead of string matching
        - Layered: Handles exceptions from all architectural layers
        - Extensible: Easy to add new exception types
        - Consistent: All HTTP responses follow same pattern
    """
    detail = str(exc) if str(exc) else default_detail or "An error occurred"

    # ========================================================================
    # Domain Layer Exceptions
    # ========================================================================

    # Not Found (404)
    if isinstance(exc, (
        AgentNotFoundError,
        ConfigNotFoundError,
        ExecutionNotFoundError,
        DomainWorkItemNotFoundError,
        WorkspaceNotFoundError,
        PipelineNotFoundError,
    )):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
        )

    # Invalid State / Business Rule Violations (400 or 409)
    if isinstance(exc, InvalidStateError):
        # Most state errors are client errors (invalid input/state)
        # Some could be conflicts (e.g., concurrent modification)
        # For now, treat as bad request
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )

    # ========================================================================
    # Input Port Layer Exceptions
    # ========================================================================

    # Not Found (404)
    if isinstance(exc, (
        InputPortAgentNotFoundError,
        AgentExecutionNotFoundError,
        ArtifactNotFoundError,
        CommandFileNotFoundError,
        CommandNotFoundError,
        InputPortPipelineNotFoundError,
        ProjectNotFoundError,
        StageNotFoundError,
        SubAgentNotFoundError,
        VariableNotFoundError,
        WorkflowNotFoundError,
        InputPortWorkItemNotFoundError,
    )):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
        )

    # Validation Errors (400)
    if isinstance(exc, InputPortValidationError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )

    # State Transition Errors (409 Conflict)
    if isinstance(exc, (WorkflowNotActiveError, WorkflowNotPausedError)):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )

    # Permission Errors (403)
    if isinstance(exc, InputPortPermissionError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )

    # ========================================================================
    # Port Layer Exceptions (External Services)
    # ========================================================================

    # Not Found (404)
    if isinstance(exc, ResourceNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
        )

    # Validation Errors (400)
    if isinstance(exc, PortValidationError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )

    # Empty Agent Response (502) - External LLM provider returned invalid response
    if isinstance(exc, EmptyAgentResponseError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        )

    # Authentication Errors (401)
    if isinstance(exc, AuthenticationError):
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Concurrency Conflicts (409)
    if isinstance(exc, ConcurrencyConflictError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )

    # Rate Limiting (429)
    if isinstance(exc, RateLimitError):
        headers = {}
        if exc.retry_after:
            headers["Retry-After"] = str(exc.retry_after)
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers=headers if headers else None,
        )

    # Timeouts (504)
    if isinstance(exc, TimeoutError):
        return HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=detail,
        )

    # External Service Errors (502)
    if isinstance(exc, ExternalServiceError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        )

    # Generic Port Errors (502) - external system issues
    if isinstance(exc, PortError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        )

    # Generic Input Port Errors (500) - command/query execution issues
    if isinstance(exc, PortException):
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
        )

    # Generic Domain Errors (500) - unexpected business logic errors
    if isinstance(exc, DomainError):
        logger.error(f"Unhandled domain error: {type(exc).__name__}: {exc}", extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR})
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
        )

    # ========================================================================
    # Unknown Exception (500)
    # ========================================================================

    # For any other exception, log and return generic 500
    logger.exception(f"Unhandled exception: {type(exc).__name__}", exc_info=exc, extra={"error_id": "ERR_UNHANDLED_EXCEPTION"})
    # For unknown exceptions, use default_detail if provided, otherwise use generic message
    # We don't expose the exception message for unknown exceptions (security concern)
    final_detail = default_detail if default_detail else "An internal error occurred"
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=final_detail,
    )


# Convenience decorator for router handlers
def with_exception_mapping(func):
    """
    Decorator to automatically map exceptions in route handlers.

    Usage:
        @router.get("/items/{item_id}")
        @with_exception_mapping
        async def get_item(item_id: str):
            return await service.get_item(item_id)

    Note: This is optional. You can also call map_exception_to_http directly.
    """
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except (DomainError, PortError, PortException) as e:
            raise map_exception_to_http(e)

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper
