"""
Error Handling Middleware

Provides centralized error handling for the FastAPI application with
standardized error responses and correlation IDs for request tracking.
"""

import traceback
from typing import Callable
from uuid import uuid4

from fastapi import Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError

from codetoreum.adapters.primary.api_models import ErrorCode, ErrorDetail, ErrorResponse


async def error_handling_middleware(request: Request, call_next: Callable):
    """
    Error handling middleware for FastAPI.

    Catches all exceptions and returns standardized error responses with
    correlation IDs for tracking.

    Args:
        request: FastAPI request
        call_next: Next middleware/handler in chain

    Returns:
        Response (either successful or error)
    """
    # Generate correlation ID for this request
    correlation_id = str(uuid4())
    request.state.correlation_id = correlation_id

    try:
        # Call next middleware/handler
        response = await call_next(request)
        return response

    except PydanticValidationError as exc:
        # Pydantic validation errors (request body validation)
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
        # Log the full traceback for debugging
        print(f"Unhandled exception [{correlation_id}]:")
        print(traceback.format_exc())

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
#
# app = FastAPI()
#
# # Add error handling middleware
# app.middleware("http")(error_handling_middleware)
#
# # Or use as middleware class:
# app.add_middleware(BaseHTTPMiddleware, dispatch=error_handling_middleware)
