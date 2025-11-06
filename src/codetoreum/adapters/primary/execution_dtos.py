"""
Execution DTOs (Data Transfer Objects)

Defines request and response models for execution REST API endpoints.
These models decouple the API contract from domain models.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ============================================================================
# Request Models
# ============================================================================


class TerminateExecutionRequest(BaseModel):
    """Request to terminate an execution."""

    reason: Optional[str] = Field(None, description="Optional reason for termination", max_length=500)


# ============================================================================
# Response Models
# ============================================================================


class ContainerStatusDTO(BaseModel):
    """Container status information DTO."""

    container_id: Optional[str] = None
    container_name: Optional[str] = None
    last_known_status: Optional[str] = None
    exit_code: Optional[int] = None


class ExecutionErrorDetailDTO(BaseModel):
    """Execution error detail DTO."""

    error_type: str = Field(
        ...,
        description="Error type (CONTAINER_CRASHED, EXECUTION_TIMEOUT, AGENT_FAILURE, UNKNOWN)",
    )
    message: str = Field(..., description="Error message")
    container_status: Optional[ContainerStatusDTO] = Field(
        None, description="Container status (for container crashes)"
    )
    partial_logs_available: bool = Field(
        False, description="Whether partial logs are available"
    )


class ExecutionResponse(BaseModel):
    """Execution response DTO."""

    id: str
    agent_id: str
    agent_name: str
    work_item_id: str
    workflow_id: str
    stage_name: str
    status: str
    container_name: Optional[str] = None
    container_id: Optional[str] = None
    output: Optional[str] = None
    error_message: Optional[str] = None
    error_detail: Optional[ExecutionErrorDetailDTO] = None
    exit_code: Optional[int] = None
    input_tokens: int = 0
    output_tokens: int = 0
    duration_seconds: Optional[float] = None
    initialized_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    elapsed_time_seconds: Optional[float] = None
    current_stage: Optional[str] = None


class ExecutionSummaryResponse(BaseModel):
    """Execution summary response (for list views)."""

    id: str
    agent_name: str
    work_item_id: str
    workflow_id: str
    stage_name: str
    status: str
    initialized_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error_type: Optional[str] = None


class ExecutionListResponse(BaseModel):
    """Execution list response with pagination."""

    executions: List[ExecutionSummaryResponse]
    total_count: int
    offset: int
    limit: int
    page: int = 1
    page_size: int = 20
    has_next: bool


class LogEntryDTO(BaseModel):
    """Log entry DTO."""

    timestamp: datetime
    level: str
    message: str
    stage: Optional[str] = None


class ExecutionLogsResponse(BaseModel):
    """Execution logs response."""

    execution_id: str
    logs: List[LogEntryDTO]
    total_lines: int
    stage: Optional[str] = None
    has_more: bool = False


class ExecutionHistoryEntryDTO(BaseModel):
    """Execution history entry DTO."""

    event_type: str
    occurred_at: datetime
    payload: dict


class ExecutionHistoryResponse(BaseModel):
    """Execution history response."""

    execution_id: str
    events: List[ExecutionHistoryEntryDTO]
    total_events: int


class ExecutionCommandResult(BaseModel):
    """Result from execution command operations."""

    success: bool
    execution_id: str
    message: str
    new_status: Optional[str] = None
    errors: Optional[List[str]] = None
