"""
Work Item Data Transfer Objects (DTOs)

DTOs for Work Item REST API endpoints. These decouple the external API
contracts from the internal domain models, allowing independent evolution.

Note: Pydantic v2 automatically serializes datetime objects to ISO 8601 format,
so explicit json_encoders configuration is no longer needed.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from codetoreum.adapters.primary.api_models import PaginatedResponse
from codetoreum.config import (
    MAX_PROJECT_ID_LENGTH,
    MAX_TITLE_LENGTH,
    MIN_FIELD_LENGTH,
)

# ============================================================================
# Request Models
# ============================================================================


class CreateWorkItemRequest(BaseModel):
    """Request to create a new work item"""

    project_id: str = Field(
        ...,
        description="Project ID this work item belongs to",
        min_length=MIN_FIELD_LENGTH,
        max_length=MAX_PROJECT_ID_LENGTH,
    )
    title: str = Field(..., description="Work item title", min_length=MIN_FIELD_LENGTH, max_length=MAX_TITLE_LENGTH)
    description: str = Field(..., description="Work item description")
    labels: list[str] | None = Field(None, description="List of labels/tags")
    priority: str = Field("MEDIUM", description="Priority: LOW, MEDIUM, HIGH, CRITICAL")
    external_id: str | None = Field(None, description="External system ID (e.g., GitHub issue #)")
    external_url: str | None = Field(None, description="External system URL")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "proj-123",
                "title": "Implement user authentication",
                "description": "Add JWT-based authentication to the API",
                "labels": ["feature", "security"],
                "priority": "HIGH",
                "external_id": "42",
                "external_url": "https://github.com/org/repo/issues/42",
            }
        }
    )


class UpdateWorkItemRequest(BaseModel):
    """Request to update an existing work item"""

    title: str | None = Field(
        None, description="Updated title", min_length=MIN_FIELD_LENGTH, max_length=MAX_TITLE_LENGTH
    )
    description: str | None = Field(None, description="Updated description")
    labels: list[str] | None = Field(None, description="Updated labels")
    priority: str | None = Field(None, description="Updated priority: LOW, MEDIUM, HIGH, CRITICAL")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Implement user authentication (updated)",
                "labels": ["feature", "security", "high-priority"],
                "priority": "CRITICAL",
            }
        }
    )


# ============================================================================
# Response Models
# ============================================================================


class WorkItemResponse(BaseModel):
    """Response with work item details"""

    id: str = Field(..., description="Work item ID")
    project_id: str = Field(..., description="Project ID")
    title: str = Field(..., description="Work item title")
    description: str = Field(..., description="Work item description")
    status: str = Field(..., description="Current status (NEW, ASSIGNED, IN_PROGRESS, etc.)")
    priority: str = Field(..., description="Priority level")
    labels: list[str] = Field(default_factory=list, description="Labels/tags")
    external_id: str | None = Field(None, description="External system ID")
    external_url: str | None = Field(None, description="External system URL")
    assigned_agent_id: str | None = Field(None, description="Assigned agent ID")
    assigned_at: datetime | None = Field(None, description="Assignment timestamp")
    current_workflow_id: str | None = Field(None, description="Current workflow ID")
    current_stage: str | None = Field(None, description="Current workflow stage")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    completed_at: datetime | None = Field(None, description="Completion timestamp")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "wi-123",
                "project_id": "proj-123",
                "title": "Implement user authentication",
                "description": "Add JWT-based authentication to the API",
                "status": "IN_PROGRESS",
                "priority": "HIGH",
                "labels": ["feature", "security"],
                "external_id": "42",
                "external_url": "https://github.com/org/repo/issues/42",
                "assigned_agent_id": "agent-software_engineer",
                "assigned_at": "2025-11-03T10:00:00Z",
                "current_workflow_id": "wf-123",
                "current_stage": "development",
                "created_at": "2025-11-03T09:00:00Z",
                "updated_at": "2025-11-03T10:30:00Z",
                "completed_at": None,
            }
        }
    )


class WorkItemDetailResponse(WorkItemResponse):
    """Response with work item details including history"""

    history_event_count: int = Field(..., description="Number of historical events")
    recent_events: list[dict] = Field(default_factory=list, description="Recent domain events")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "wi-123",
                "project_id": "proj-123",
                "title": "Implement user authentication",
                "description": "Add JWT-based authentication to the API",
                "status": "IN_PROGRESS",
                "priority": "HIGH",
                "labels": ["feature", "security"],
                "external_id": "42",
                "external_url": "https://github.com/org/repo/issues/42",
                "assigned_agent_id": "agent-software_engineer",
                "assigned_at": "2025-11-03T10:00:00Z",
                "current_workflow_id": "wf-123",
                "current_stage": "development",
                "created_at": "2025-11-03T09:00:00Z",
                "updated_at": "2025-11-03T10:30:00Z",
                "completed_at": None,
                "history_event_count": 5,
                "recent_events": [
                    {
                        "event_type": "WorkItemStarted",
                        "occurred_at": "2025-11-03T10:15:00Z",
                        "payload": {"started_at": "2025-11-03T10:15:00Z"},
                    }
                ],
            }
        }
    )


class WorkItemListResponse(PaginatedResponse):
    """Response with list of work items"""

    work_items: list[WorkItemResponse] = Field(..., description="List of work items")

    model_config = ConfigDict()


class WorkItemCommandResult(BaseModel):
    """Result of a work item command operation"""

    success: bool = Field(..., description="Whether operation succeeded")
    work_item_id: str = Field(..., description="Work item ID")
    message: str = Field(..., description="Result message")
    errors: list[str] | None = Field(None, description="Error messages if any")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "work_item_id": "wi-123",
                "message": "Work item deleted successfully",
                "errors": None,
            }
        }
    )
