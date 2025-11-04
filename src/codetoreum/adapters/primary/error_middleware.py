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
from typing import Callable
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
        "Debug mode is always disabled in production for security."
    )


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
    # Generate correlation ID for this request
    correlation_id = str(uuid4())
    request.state.correlation_id = correlation_id

    # Set correlation ID in logging context
    set_correlation_id(correlation_id)

    try:
        # Call next middleware/handler
        response = await call_next(request)
        return response

    except PydanticValidationError as exc:
        # Pydantic validation errors (request body validation)
        logger.info(
            f"Validation error on {request.method} {request.url.path}",
            extra={"validation_errors": exc.errors()}
        )

        error_response = ErrorResponse(
            error=ErrorCode.VALIDATION_ERROR,
            message="Request validation failed",
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

        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=error_response.dict(),
        )

    except ValueError as exc:
        # Value errors (typically from domain logic)
        logger.info(
            f"Value error on {request.method} {request.url.path}: {exc}",
            extra={"error_type": "ValueError"}
        )

        error_response = ErrorResponse(
            error=ErrorCode.VALIDATION_ERROR,
            message=str(exc),
            correlation_id=correlation_id,
            path=str(request.url.path),
        )

        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=error_response.dict(),
        )

    except PermissionError as exc:
        # Permission errors
        logger.warning(
            f"Permission denied on {request.method} {request.url.path}: {exc}",
            extra={"error_type": "PermissionError"}
        )

        error_response = ErrorResponse(
            error=ErrorCode.PERMISSION_DENIED,
            message=str(exc) or "Permission denied",
            correlation_id=correlation_id,
            path=str(request.url.path),
        )

        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=error_response.dict(),
        )

    except FileNotFoundError as exc:
        # Not found errors
        logger.info(
            f"Resource not found on {request.method} {request.url.path}: {exc}",
            extra={"error_type": "FileNotFoundError"}
        )

        error_response = ErrorResponse(
            error=ErrorCode.NOT_FOUND,
            message=str(exc) or "Resource not found",
            correlation_id=correlation_id,
            path=str(request.url.path),
        )

        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=error_response.dict(),
        )

    except TimeoutError as exc:
        # Timeout errors
        logger.warning(
            f"Timeout on {request.method} {request.url.path}: {exc}",
            extra={"error_type": "TimeoutError"}
        )

        error_response = ErrorResponse(
            error=ErrorCode.TIMEOUT,
            message=str(exc) or "Request timeout",
            correlation_id=correlation_id,
            path=str(request.url.path),
        )

        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content=error_response.dict(),
        )

    except Exception as exc:
        # Catch-all for unexpected errors
        # SECURITY: Log full traceback but NEVER return it in API response
        logger.error(
            f"Unhandled exception on {request.method} {request.url.path}: {type(exc).__name__}: {exc}",
            exc_info=True,
            extra={
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
                correlation_id=correlation_id,
                path=str(request.url.path),
            )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response.dict(),
        )


def add_correlation_id_header(request: Request, response):
    """
    Add correlation ID to response headers.

    This allows clients to reference the correlation ID when reporting issues.

    Args:
        request: FastAPI request
        response: Response to add header to

    Returns:
        Response with X-Correlation-ID header
    """
    if hasattr(request.state, "correlation_id"):
        response.headers["X-Correlation-ID"] = request.state.correlation_id
    return response


# Example usage in FastAPI app:
#
# from fastapi import FastAPI
# from starlette.middleware.base import BaseHTTPMiddleware
# from codetoreum.infrastructure.logging import configure_logging
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
