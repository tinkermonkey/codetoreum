"""
API Data Transfer Objects (DTOs)

Base classes and common DTOs for API requests and responses.
These decouple external API contracts from internal domain models.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_serializer
from codetoreum.infrastructure.error_ids import ErrorRegistry


# ============================================================================
# Base Response Models
# ============================================================================


class BaseResponse(BaseModel):
    """Base class for all API responses"""

    model_config = ConfigDict()


class SuccessResponse(BaseResponse):
    """Generic success response"""

    success: bool = Field(True, description="Whether the operation succeeded")
    message: str = Field(..., description="Success message")
    data: Optional[Dict[str, Any]] = Field(None, description="Optional response data")

    model_config = ConfigDict()


class ErrorDetail(BaseModel):
    """Detailed error information"""

    field: Optional[str] = Field(None, description="Field that caused the error")
    message: str = Field(..., description="Error message")
    code: Optional[str] = Field(None, description="Error code")

    model_config = ConfigDict()


class ErrorResponse(BaseResponse):
    """Standardized error response"""

    error: str = Field(..., description="Error type/category")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[List[ErrorDetail]] = Field(
        None, description="Detailed error information"
    )
    error_id: Optional[str] = Field(
        None, description="Error ID for Sentry tracking and issue categorization"
    )
    correlation_id: str = Field(
        default_factory=lambda: str(uuid4()), description="Request correlation ID"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Error timestamp"
    )
    path: Optional[str] = Field(None, description="Request path that caused the error")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": "VALIDATION_ERROR",
                "message": "Invalid request parameters",
                "error_id": ErrorRegistry.ErrorRegistry.ERR_VALIDATION_FAILED,
                "details": [
                    {
                        "field": "work_item_id",
                        "message": "Field is required",
                        "code": "REQUIRED",
                    }
                ],
                "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                "timestamp": "2025-11-03T10:30:00Z",
                "path": "/api/v2/workflows",
            }
        }
    )


# ============================================================================
# Health Check Models
# ============================================================================


class HealthCheckResponse(BaseResponse):
    """Health check response"""

    status: str = Field(..., description="Health status (healthy, degraded, unhealthy)")
    service: str = Field("codetoreum-api", description="Service name")
    version: str = Field(..., description="API version")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Check timestamp"
    )

    model_config = ConfigDict()


class ReadinessCheckResponse(BaseResponse):
    """Readiness check response"""

    status: str = Field(..., description="Readiness status (ready, not-ready)")
    service: str = Field("codetoreum-api", description="Service name")
    dependencies: Dict[str, str] = Field(
        default_factory=dict, description="Dependency statuses"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Check timestamp"
    )

    model_config = ConfigDict()


# ============================================================================
# Authentication Models (Simple Token)
# ============================================================================


class TokenInfoResponse(BaseResponse):
    """Token information response (for debugging/monitoring)"""

    issued_at: str = Field(..., description="Token issuance timestamp")
    expires_at: str = Field(..., description="Token expiration timestamp")
    subject: str = Field(..., description="Token subject")
    is_valid: bool = Field(..., description="Whether token is currently valid")

    model_config = ConfigDict()


# ============================================================================
# Pagination Models
# ============================================================================


class PaginationParams(BaseModel):
    """Standard pagination parameters"""

    page: int = Field(1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(50, ge=1, le=100, description="Items per page (max: 100)")

    model_config = ConfigDict()


class PaginatedResponse(BaseResponse):
    """Base class for paginated responses"""

    total_count: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
    has_next: bool = Field(..., description="Whether there are more pages")

    model_config = ConfigDict(populate_by_name=True)


# ============================================================================
# Common Field Types
# ============================================================================


class TimestampFields(BaseModel):
    """Common timestamp fields"""

    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = ConfigDict()


class AuditFields(TimestampFields):
    """Common audit fields"""

    created_by: Optional[str] = Field(None, description="Creator identifier")
    updated_by: Optional[str] = Field(None, description="Last updater identifier")

    model_config = ConfigDict()


# ============================================================================
# Error Codes
# ============================================================================


class ErrorCode:
    """Standard error codes"""

    # Client errors (4xx)
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    INVALID_TOKEN = "INVALID_TOKEN"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"

    # Server errors (5xx)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"

    # Domain errors
    WORKFLOW_ERROR = "WORKFLOW_ERROR"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"

    # Container errors
    CONTAINER_CRASHED = "CONTAINER_CRASHED"
    CONTAINER_TIMEOUT = "CONTAINER_TIMEOUT"
    CONTAINER_OOM = "CONTAINER_OOM"


# Example usage:
#
# from fastapi import HTTPException
#
# # Success response:
# return SuccessResponse(
#     success=True,
#     message="Workflow started successfully",
#     data={"workflow_run_id": "wf-123"}
# )
#
# # Error response:
# raise HTTPException(
#     status_code=400,
#     detail=ErrorResponse(
#         error=ErrorCode.VALIDATION_ERROR,
#         message="Invalid request parameters",
#         details=[
#             ErrorDetail(
#                 field="work_item_id",
#                 message="Field is required",
#                 code="REQUIRED"
#             )
#         ],
#         path="/api/v2/workflows"
#     ).dict()
# )
