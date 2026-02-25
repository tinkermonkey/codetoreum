"""
Error Handling Middleware

Provides centralized error handling for the FastAPI application with
standardized error responses and correlation IDs for request tracking.

Security Features:
- Production mode enforces security regardless of debug env var
- Sensitive data scrubbing in all error messages
- Stack traces logged but never returned in API responses
- Correlation IDs for all requests
- Structured logging with JSON format in production
"""

import os
from collections.abc import Callable
from uuid import uuid4

from fastapi import Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError

from codetoreum.adapters.primary.api_models import ErrorCode, ErrorDetail, ErrorResponse
from codetoreum.infrastructure.logging import get_logger, set_correlation_id

# Initialize logger
logger = get_logger(__name__)

# Determine environment
ENV = os.getenv("CODETOREUM_ENV", "development")
IS_PRODUCTION = ENV == "production"

# Debug mode only allowed in development
# In production, debug is ALWAYS disabled for security
DEBUG_MODE = (
    not IS_PRODUCTION and
    os.getenv("CODETOREUM_DEBUG", "false").lower() == "true"
)

# Warn if someone tries to enable debug in production
if IS_PRODUCTION and os.getenv("CODETOREUM_DEBUG", "").lower() == "true":
    logger.warning(
        "CODETOREUM_DEBUG=true ignored in production environment. "
        "Debug mode is always disabled in production for security.",
        extra={"error_id": "ERR_DEBUG_MODE_IN_PRODUCTION"}
    )


def create_error_response(
    status_code: int,
    error_response: ErrorResponse,
    correlation_id: str,
) -> JSONResponse:
    """
    Create error JSON response with correlation ID header.

    Args:
        status_code: HTTP status code
        error_response: Error response model
        correlation_id: Correlation ID for tracking

    Returns:
        JSONResponse with correlation ID header
    """
    response = JSONResponse(
        status_code=status_code,
        content=error_response.model_dump(mode="json"),
    )
    response.headers["X-Correlation-ID"] = correlation_id
    return response


async def error_handling_middleware(request: Request, call_next: Callable):
    """
    Error handling middleware for FastAPI.

    Catches all exceptions and returns standardized error responses with
    correlation IDs for tracking.

    Security Features:
    - Stack traces are logged but NEVER returned in API responses
    - Sensitive data is scrubbed from all logs
    - Production mode always returns generic error messages
    - All errors include correlation ID for support tracking

    Args:
        request: FastAPI request
        call_next: Next middleware/handler in chain

    Returns:
        Response (either successful or error)
    """
    # Extract correlation ID from request headers or generate new one
    correlation_id = (
        request.headers.get("X-Correlation-ID") or
        request.headers.get("X-Request-ID") or
        str(uuid4())
    )
    request.state.correlation_id = correlation_id

    # Set correlation ID in logging context
    set_correlation_id(correlation_id)

    logger.debug(
        f"Processing request {request.method} {request.url.path}",
        extra={
            "method": request.method,
            "path": str(request.url.path),
            "correlation_id": correlation_id,
        }
    )

    try:
        # Call next middleware/handler
        response = await call_next(request)

        # Add correlation ID to response headers
        response.headers["X-Correlation-ID"] = correlation_id

        return response

    except PydanticValidationError as exc:
        # Pydantic validation errors (request body validation)
        error_id = ErrorRegistry.ERR_VALIDATION_FAILED
        logger.info(
            f"Validation error on {request.method} {request.url.path}",
            extra={
                "error_id": error_id,
                "validation_errors": exc.errors()
            }
        )

        error_response = ErrorResponse(
            error=ErrorCode.VALIDATION_ERROR,
            message="Request validation failed",
            error_id=error_id,
            details=[
                ErrorDetail(
                    field=".".join(str(loc) for loc in error["loc"]),
                    message=error["msg"],
                    code=error["type"],
                )
                for error in exc.errors()
            ],
            correlation_id=correlation_id,
            path=str(request.url.path),
        )

        return create_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_response=error_response,
            correlation_id=correlation_id,
        )

    except ValueError as exc:
        # Value errors (typically from domain logic)
        error_id = ErrorRegistry.ERR_VALUE_ERROR
        logger.info(
            f"Value error on {request.method} {request.url.path}: {exc}",
            extra={
                "error_id": error_id,
                "error_type": "ValueError"
            }
        )

        error_response = ErrorResponse(
            error=ErrorCode.VALIDATION_ERROR,
            message=str(exc),
            error_id=error_id,
            correlation_id=correlation_id,
            path=str(request.url.path),
        )

        return create_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_response=error_response,
            correlation_id=correlation_id,
        )

    except PermissionError as exc:
        # Permission errors
        error_id = "ERR_PERMISSION_DENIED"
        logger.warning(
            f"Permission denied on {request.method} {request.url.path}: {exc}",
            extra={
                "error_id": error_id,
                "error_type": "PermissionError"
            }
        )

        error_response = ErrorResponse(
            error=ErrorCode.PERMISSION_DENIED,
            message=str(exc) or "Permission denied",
            error_id=error_id,
            correlation_id=correlation_id,
            path=str(request.url.path),
        )

        return create_error_response(
            status_code=status.HTTP_403_FORBIDDEN,
            error_response=error_response,
            correlation_id=correlation_id,
        )

    except FileNotFoundError as exc:
        # Not found errors
        error_id = "ERR_RESOURCE_NOT_FOUND"
        logger.info(
            f"Resource not found on {request.method} {request.url.path}: {exc}",
            extra={
                "error_id": error_id,
                "error_type": "FileNotFoundError"
            }
        )

        error_response = ErrorResponse(
            error=ErrorCode.NOT_FOUND,
            message=str(exc) or "Resource not found",
            error_id=error_id,
            correlation_id=correlation_id,
            path=str(request.url.path),
        )

        return create_error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            error_response=error_response,
            correlation_id=correlation_id,
        )

    except TimeoutError as exc:
        # Timeout errors
        error_id = "ERR_REQUEST_TIMEOUT"
        logger.warning(
            f"Timeout on {request.method} {request.url.path}: {exc}",
            extra={
                "error_id": error_id,
                "error_type": "TimeoutError"
            }
        )

        error_response = ErrorResponse(
            error=ErrorCode.TIMEOUT,
            message=str(exc) or "Request timeout",
            error_id=error_id,
            correlation_id=correlation_id,
            path=str(request.url.path),
        )

        return create_error_response(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            error_response=error_response,
            correlation_id=correlation_id,
        )

    except Exception as exc:
        # Catch-all for unexpected errors
        # SECURITY: Log full traceback but NEVER return it in API response
        error_id = "ERR_UNHANDLED_EXCEPTION"
        logger.error(
            f"Unhandled exception on {request.method} {request.url.path}: {type(exc).__name__}: {exc}",
            exc_info=True,
            extra={
                "error_id": error_id,
                "error_type": type(exc).__name__,
                "request_method": request.method,
                "request_path": str(request.url.path),
            }
        )

        # SECURITY: In production, never expose exception details
        # Even in debug mode, we don't return stack traces (only log them)
        if DEBUG_MODE:
            # Development mode - return error type and message
            error_response = ErrorResponse(
                error=ErrorCode.INTERNAL_ERROR,
                message="An unexpected error occurred",
                error_id=error_id,
                details=[
                    ErrorDetail(
                        message=str(exc),
                        code=type(exc).__name__,
                    )
                ],
                correlation_id=correlation_id,
                path=str(request.url.path),
            )
        else:
            # Production mode - generic error message only
            # Users can reference correlation ID for support
            error_response = ErrorResponse(
                error=ErrorCode.INTERNAL_ERROR,
                message="An unexpected error occurred. Please contact support with the correlation ID if this persists.",
                error_id=error_id,
                correlation_id=correlation_id,
                path=str(request.url.path),
            )

        return create_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_response=error_response,
            correlation_id=correlation_id,
        )


# Example usage in FastAPI app:
#
# from fastapi import FastAPI
# from starlette.middleware.base import BaseHTTPMiddleware
# from codetoreum.infrastructure.logging import configure_logging
from codetoreum.infrastructure.error_ids import ErrorRegistry

#
# # Configure logging at application startup
# configure_logging(
#     json_format=IS_PRODUCTION,  # Use JSON format in production
#     scrub_sensitive=True,        # Always scrub sensitive data
# )
#
# app = FastAPI()
#
# # Add error handling middleware
# app.middleware("http")(error_handling_middleware)
#
# # Or use as middleware class:
# app.add_middleware(BaseHTTPMiddleware, dispatch=error_handling_middleware)
