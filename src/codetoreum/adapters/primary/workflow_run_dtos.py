"""
Workflow Run Data Transfer Objects (DTOs)

DTOs for Workflow Run REST API endpoints. These decouple the external API
contracts from the internal domain models.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from codetoreum.adapters.primary.api_models import PaginatedResponse


# ============================================================================
# Workflow Run Models
# ============================================================================


class WorkflowRunStageResponse(BaseModel):
    """Workflow run stage information"""

    name: str = Field(..., description="Stage name")
    agentName: str = Field(..., description="Agent executing this stage", serialization_alias="agentName")
    status: str = Field(..., description="Stage status (pending, running, completed, failed)")
    startedAt: Optional[datetime] = Field(None, description="Stage start time", serialization_alias="startedAt")
    completedAt: Optional[datetime] = Field(None, description="Stage completion time", serialization_alias="completedAt")
    executionId: Optional[str] = Field(None, description="Execution ID for this stage", serialization_alias="executionId")
    output: Optional[str] = Field(None, description="Stage output content")
    errorMessage: Optional[str] = Field(None, description="Error message if stage failed", serialization_alias="errorMessage")
    metadata: dict = Field(default_factory=dict, description="Additional stage metadata")

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "name": "implementation",
                "agentName": "developer_agent",
                "status": "completed",
                "startedAt": "2026-02-20T10:00:00Z",
                "completedAt": "2026-02-20T10:15:00Z",
                "executionId": "exec-111",
                "output": "Implementation completed successfully",
                "errorMessage": None,
                "metadata": {}
            }
        }
    )


class WorkflowRunSummaryResponse(BaseModel):
    """Summary response for workflow run list"""

    id: str = Field(..., description="Workflow run ID")
    workItemId: str = Field(..., description="Work item ID", serialization_alias="workItemId")
    workflowId: str = Field(..., description="Workflow template ID", serialization_alias="workflowId")
    projectId: str = Field(..., description="Project ID", serialization_alias="projectId")
    status: str = Field(..., description="Run status")
    currentStageIndex: int = Field(..., description="Current stage index", serialization_alias="currentStageIndex")
    currentStageName: Optional[str] = Field(None, description="Current stage name", serialization_alias="currentStageName")
    startedAt: Optional[datetime] = Field(None, description="Run start time", serialization_alias="startedAt")
    completedAt: Optional[datetime] = Field(None, description="Run completion time", serialization_alias="completedAt")
    duration: Optional[int] = Field(None, description="Duration in seconds")
    issueTitle: Optional[str] = Field(None, description="Associated issue title", serialization_alias="issueTitle")
    issueNumber: Optional[int] = Field(None, description="Associated issue number", serialization_alias="issueNumber")
    project: Optional[str] = Field(None, description="Project name")
    triggeredBy: Optional[str] = Field(None, description="Trigger source", serialization_alias="triggeredBy")
    priority: Optional[str] = Field(None, description="Priority level")

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "id": "wfrun-123",
                "workItemId": "wi-456",
                "workflowId": "wf-789",
                "projectId": "proj-1",
                "status": "running",
                "currentStageIndex": 2,
                "currentStageName": "review",
                "startedAt": "2026-02-20T10:00:00Z",
                "completedAt": None,
                "duration": None,
                "issueTitle": "Fix authentication bug",
                "issueNumber": 42,
                "project": "codetoreum",
                "triggeredBy": "github_webhook",
                "priority": "high"
            }
        }
    )


class WorkflowRunResponse(BaseModel):
    """Detailed workflow run response"""

    id: str = Field(..., description="Workflow run ID")
    workItemId: str = Field(..., description="Work item ID", serialization_alias="workItemId")
    workflowId: str = Field(..., description="Workflow template ID", serialization_alias="workflowId")
    projectId: str = Field(..., description="Project ID", serialization_alias="projectId")
    status: str = Field(..., description="Run status")
    stages: List[WorkflowRunStageResponse] = Field(..., description="Workflow stages")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "id": "wfrun-123",
                "workItemId": "wi-456",
                "workflowId": "wf-789",
                "projectId": "proj-1",
                "status": "running",
                "stages": [
                    {
                        "name": "implementation",
                        "agentName": "developer_agent",
                        "status": "completed",
                        "startedAt": "2026-02-20T10:00:00Z",
                        "completedAt": "2026-02-20T10:15:00Z",
                        "executionId": "exec-111"
                    },
                    {
                        "name": "review",
                        "agentName": "reviewer_agent",
                        "status": "running",
                        "startedAt": "2026-02-20T10:15:00Z",
                        "completedAt": None,
                        "executionId": "exec-222"
                    }
                ],
                "metadata": {}
            }
        }
    )


class WorkflowRunListResponse(PaginatedResponse):
    """Response with list of workflow runs"""

    runs: List[WorkflowRunSummaryResponse] = Field(..., description="List of workflow runs")

    model_config = ConfigDict(populate_by_name=True)


# ============================================================================
# Workflow Events Models
# ============================================================================


class WorkflowEventResponse(BaseModel):
    """Workflow event information"""

    id: str = Field(..., description="Event ID")
    eventType: str = Field(..., description="Event type", serialization_alias="eventType")
    workflowRunId: str = Field(..., description="Workflow run ID", serialization_alias="workflowRunId")
    timestamp: datetime = Field(..., description="Event timestamp")
    agentName: Optional[str] = Field(None, description="Agent name (if applicable)", serialization_alias="agentName")
    stageName: Optional[str] = Field(None, description="Stage name (if applicable)", serialization_alias="stageName")
    status: Optional[str] = Field(None, description="Status (if applicable)")
    data: Dict[str, Any] = Field(default_factory=dict, description="Event data")

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "id": "evt-123",
                "eventType": "WorkflowStarted",
                "workflowRunId": "wfrun-123",
                "timestamp": "2026-02-20T10:00:00Z",
                "agentName": None,
                "stageName": "implementation",
                "status": None,
                "data": {
                    "workItemId": "wi-456",
                    "triggeredBy": "github_webhook"
                }
            }
        }
    )


class WorkflowEventsListResponse(PaginatedResponse):
    """Response with list of workflow events"""

    events: List[WorkflowEventResponse] = Field(..., description="List of events")

    model_config = ConfigDict(populate_by_name=True)
