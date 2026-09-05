"""
Standardized error handling for REST API.
"""

from enum import Enum

from fastapi import HTTPException, status
from pydantic import BaseModel, Field


class ErrorCode(str, Enum):
    """Standardized error codes for the API."""

    # Client errors (4xx)
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    BAD_REQUEST = "BAD_REQUEST"

    # Server errors (5xx)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


class ErrorResponse(BaseModel):
    """Standardized error response format."""

    error_code: ErrorCode = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: dict | None = Field(None, description="Additional error details")


def create_error_response(
    status_code: int,
    error_code: ErrorCode,
    message: str,
    details: dict | None = None,
) -> HTTPException:
    """
    Create a standardized HTTP exception with error response.

    Args: status_code: HTTP status code
        error_code: Machine-readable error code
        message: Human-readable error message
        details: Optional additional error details

    Returns: HTTPException with standardized error response
    """
    error_response = ErrorResponse(error_code=error_code, message=message, details=details)
    return HTTPException(status_code=status_code, detail=error_response.model_dump())


def not_found_error(resource: str, resource_id: str) -> HTTPException:
    """Create a 404 Not Found error."""
    return create_error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        error_code=ErrorCode.NOT_FOUND,
        message=f"{resource} not found",
        details={"resource": resource, "id": resource_id},
    )


def conflict_error(message: str, details: dict | None = None) -> HTTPException:
    """Create a 409 Conflict error."""
    return create_error_response(
        status_code=status.HTTP_409_CONFLICT,
        error_code=ErrorCode.CONFLICT,
        message=message,
        details=details,
    )


def validation_error(message: str, details: dict | None = None) -> HTTPException:
    """Create a 400 Validation error."""
    return create_error_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        error_code=ErrorCode.VALIDATION_ERROR,
        message=message,
        details=details,
    )


def unauthorized_error(message: str = "Authentication required") -> HTTPException:
    """Create a 401 Unauthorized error."""
    return create_error_response(
        status_code=status.HTTP_401_UNAUTHORIZED, error_code=ErrorCode.UNAUTHORIZED, message=message
    )


def forbidden_error(message: str = "Access forbidden") -> HTTPException:
    """Create a 403 Forbidden error."""
    return create_error_response(status_code=status.HTTP_403_FORBIDDEN, error_code=ErrorCode.FORBIDDEN, message=message)
