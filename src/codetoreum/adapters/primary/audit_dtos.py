"""
Audit Response Data Transfer Objects (DTOs)

DTOs for workflow run audit REST API endpoints. These provide comprehensive
audit information with sequence validation and stage grouping.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from codetoreum.adapters.primary.api_models import PaginatedResponse
from codetoreum.adapters.primary.workflow_run_dtos import (
    WorkflowRunSummaryResponse,
    WorkflowEventResponse,
)


# ============================================================================
# Validation Models
# ============================================================================


class OutOfOrderEvent(BaseModel):
    """Event that occurred out of expected sequence."""

    eventType: str = Field(..., description="Event type name", serialization_alias="eventType")
    timestamp: Optional[datetime] = Field(None, description="When event occurred (optional until out-of-order detection is fully implemented)")
    expectedPosition: int = Field(..., description="Expected position in sequence", serialization_alias="expectedPosition")
    actualPosition: int = Field(..., description="Actual position in sequence", serialization_alias="actualPosition")

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "eventType": "WorkflowStageAdvanced",
                "timestamp": "2025-11-08T10:15:00Z",
                "expectedPosition": 5,
                "actualPosition": 3
            }
        }
    )


class AuditValidationResult(BaseModel):
    """Validation results for event sequence."""

    sequenceValid: bool = Field(..., description="Whether event sequence is valid", serialization_alias="sequenceValid")
    expectedSequence: List[str] = Field(..., description="Expected event type names", serialization_alias="expectedSequence")
    actualSequence: List[str] = Field(..., description="Actual event type names", serialization_alias="actualSequence")
    missingEvents: List[str] = Field(..., description="Expected events that didn't occur", serialization_alias="missingEvents")
    unexpectedEvents: List[str] = Field(..., description="Events that shouldn't have occurred", serialization_alias="unexpectedEvents")
    outOfOrderEvents: List[OutOfOrderEvent] = Field(..., description="Events in wrong sequence", serialization_alias="outOfOrderEvents")

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "sequenceValid": False,
                "expectedSequence": ["WorkflowCreated", "WorkflowStarted", "WorkflowStageAdvanced", "WorkflowCompleted"],
                "actualSequence": ["WorkflowCreated", "WorkflowStageAdvanced", "WorkflowStarted", "WorkflowCompleted"],
                "missingEvents": [],
                "unexpectedEvents": [],
                "outOfOrderEvents": [
                    {
                        "eventType": "WorkflowStageAdvanced",
                        "timestamp": "2025-11-08T10:15:00Z",
                        "expectedPosition": 2,
                        "actualPosition": 1
                    }
                ]
            }
        }
    )


# ============================================================================
# Stage Grouping Models
# ============================================================================


class AuditStageInfo(BaseModel):
    """Stage-grouped events for audit."""

    name: str = Field(..., description="Stage name")
    status: str = Field(..., description="Stage status (pending, running, completed, failed)")
    startedAt: Optional[datetime] = Field(None, description="Stage start time", serialization_alias="startedAt")
    completedAt: Optional[datetime] = Field(None, description="Stage completion time", serialization_alias="completedAt")
    durationSeconds: Optional[float] = Field(None, description="Stage duration in seconds", serialization_alias="durationSeconds")
    events: List[WorkflowEventResponse] = Field(default_factory=list, description="Events for this stage")

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "name": "implementation",
                "status": "completed",
                "startedAt": "2025-11-08T10:00:00Z",
                "completedAt": "2025-11-08T10:15:00Z",
                "durationSeconds": 900.0,
                "events": [
                    {
                        "id": "evt-123",
                        "eventType": "ExecutionStarted",
                        "workflowRunId": "wfrun-123",
                        "timestamp": "2025-11-08T10:00:00Z",
                        "agentName": "developer_agent",
                        "stageName": "implementation",
                        "status": None,
                        "data": {}
                    }
                ]
            }
        }
    )


# ============================================================================
# Audit Response Models
# ============================================================================


class WorkflowRunAuditResponse(BaseModel):
    """Comprehensive audit response for workflow run."""

    workflowRun: WorkflowRunSummaryResponse = Field(..., description="Workflow run summary", serialization_alias="workflowRun")
    events: List[WorkflowEventResponse] = Field(..., description="All workflow events")
    stages: List[AuditStageInfo] = Field(..., description="Stage-grouped event information")
    validation: Optional[AuditValidationResult] = Field(None, description="Sequence validation results (optional, only included when include_validation=true)")
    totalEventCount: int = Field(..., description="Total number of events", serialization_alias="totalEventCount")
    offset: int = Field(..., description="Event list offset for pagination")
    limit: int = Field(..., description="Event list limit for pagination")
    hasNext: bool = Field(..., description="Whether more events are available", serialization_alias="hasNext")

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "workflowRun": {
                    "id": "wfrun-123",
                    "workItemId": "wi-456",
                    "workflowId": "wf-789",
                    "projectId": "proj-1",
                    "status": "completed",
                    "currentStageIndex": 2,
                    "currentStageName": "review",
                    "startedAt": "2025-11-08T10:00:00Z",
                    "completedAt": "2025-11-08T10:30:00Z",
                    "duration": 1800,
                    "issueTitle": "Fix authentication bug",
                    "issueNumber": 42,
                    "project": "codetoreum",
                    "triggeredBy": "github_webhook",
                    "priority": "high"
                },
                "events": [
                    {
                        "id": "evt-123",
                        "eventType": "WorkflowStarted",
                        "workflowRunId": "wfrun-123",
                        "timestamp": "2025-11-08T10:00:00Z",
                        "agentName": None,
                        "stageName": None,
                        "status": None,
                        "data": {}
                    }
                ],
                "stages": [
                    {
                        "name": "implementation",
                        "status": "completed",
                        "startedAt": "2025-11-08T10:00:00Z",
                        "completedAt": "2025-11-08T10:15:00Z",
                        "durationSeconds": 900.0,
                        "events": []
                    }
                ],
                "validation": {
                    "sequenceValid": True,
                    "expectedSequence": ["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"],
                    "actualSequence": ["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"],
                    "missingEvents": [],
                    "unexpectedEvents": [],
                    "outOfOrderEvents": []
                },
                "totalEventCount": 15,
                "offset": 0,
                "limit": 100,
                "hasNext": False
            }
        }
    )
