"""
Execution DTOs (Data Transfer Objects)

Defines request and response models for execution REST API endpoints.
These models decouple the API contract from domain models.
"""

from datetime import datetime

from pydantic import BaseModel, Field

# ============================================================================
# Request Models
# ============================================================================


class TerminateExecutionRequest(BaseModel):
    """Request to terminate an execution."""

    reason: str | None = Field(None, description="Optional reason for termination", max_length=500)


# ============================================================================
# Response Models
# ============================================================================


class ContainerStatusDTO(BaseModel):
    """Container status information DTO."""

    container_id: str | None = None
    container_name: str | None = None
    last_known_status: str | None = None
    exit_code: int | None = None


class ExecutionErrorDetailDTO(BaseModel):
    """Execution error detail DTO."""

    error_type: str = Field(
        ...,
        description="Error type (CONTAINER_CRASHED, EXECUTION_TIMEOUT, AGENT_FAILURE, UNKNOWN)",
    )
    message: str = Field(..., description="Error message")
    container_status: ContainerStatusDTO | None = Field(
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
    container_name: str | None = None
    container_id: str | None = None
    output: str | None = None
    error_message: str | None = None
    error_detail: ExecutionErrorDetailDTO | None = None
    exit_code: int | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    duration_seconds: float | None = None
    initialized_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    elapsed_time_seconds: float | None = None
    current_stage: str | None = None


class ExecutionSummaryResponse(BaseModel):
    """Execution summary response (for list views)."""

    id: str
    agent_name: str
    work_item_id: str
    workflow_id: str
    stage_name: str
    status: str
    initialized_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    error_type: str | None = None


class ExecutionListResponse(BaseModel):
    """Execution list response with pagination."""

    executions: list[ExecutionSummaryResponse]
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
    stage: str | None = None


class ExecutionLogsResponse(BaseModel):
    """Execution logs response."""

    execution_id: str
    logs: list[LogEntryDTO]
    total_lines: int
    stage: str | None = None
    has_more: bool = False


class ExecutionHistoryEntryDTO(BaseModel):
    """Execution history entry DTO."""

    event_type: str
    occurred_at: datetime
    payload: dict


class ExecutionHistoryResponse(BaseModel):
    """Execution history response."""

    execution_id: str
    events: list[ExecutionHistoryEntryDTO]
    total_events: int


class ExecutionCommandResult(BaseModel):
    """Result from execution command operations."""

    success: bool
    execution_id: str
    message: str
    new_status: str | None = None
    errors: list[str] | None = None
