"""
Audit Response Data Transfer Objects (DTOs)

DTOs for audit REST API endpoints. Provides:
- Workflow run audit information with sequence validation and stage grouping
- System-wide audit event logging with pagination and filtering
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from codetoreum.adapters.primary.workflow_run_dtos import (
    WorkflowEventResponse,
    WorkflowRunSummaryResponse,
)

# ============================================================================
# Validation Models
# ============================================================================


class OutOfOrderEvent(BaseModel):
    """Event that occurred out of expected sequence."""

    eventType: str = Field(..., description="Event type name", serialization_alias="eventType")
    timestamp: datetime | None = Field(
        None,
        description="When event occurred (optional until out-of-order detection is fully implemented)",
    )
    expectedPosition: int = Field(
        ..., description="Expected position in sequence", serialization_alias="expectedPosition"
    )
    actualPosition: int = Field(..., description="Actual position in sequence", serialization_alias="actualPosition")

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "eventType": "WorkflowStageAdvanced",
                "timestamp": "2026-02-20T10:15:00Z",
                "expectedPosition": 5,
                "actualPosition": 3,
            }
        },
    )


class AuditValidationResult(BaseModel):
    """Validation results for event sequence."""

    sequenceValid: bool = Field(..., description="Whether event sequence is valid", serialization_alias="sequenceValid")
    expectedSequence: list[str] = Field(
        ..., description="Expected event type names", serialization_alias="expectedSequence"
    )
    actualSequence: list[str] = Field(..., description="Actual event type names", serialization_alias="actualSequence")
    missingEvents: list[str] = Field(
        ..., description="Expected events that didn't occur", serialization_alias="missingEvents"
    )
    unexpectedEvents: list[str] = Field(
        ...,
        description="Events that shouldn't have occurred",
        serialization_alias="unexpectedEvents",
    )
    outOfOrderEvents: list[OutOfOrderEvent] = Field(
        ..., description="Events in wrong sequence", serialization_alias="outOfOrderEvents"
    )

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "sequenceValid": False,
                "expectedSequence": [
                    "WorkflowCreated",
                    "WorkflowStarted",
                    "WorkflowStageAdvanced",
                    "WorkflowCompleted",
                ],
                "actualSequence": [
                    "WorkflowCreated",
                    "WorkflowStageAdvanced",
                    "WorkflowStarted",
                    "WorkflowCompleted",
                ],
                "missingEvents": [],
                "unexpectedEvents": [],
                "outOfOrderEvents": [
                    {
                        "eventType": "WorkflowStageAdvanced",
                        "timestamp": "2026-02-20T10:15:00Z",
                        "expectedPosition": 2,
                        "actualPosition": 1,
                    }
                ],
            }
        },
    )

    @model_validator(mode="after")
    def validate_consistency(self) -> "AuditValidationResult":
        """
        Validate consistency between sequenceValid and error lists.

        If sequenceValid is True, then all error lists (missingEvents, unexpectedEvents,
        outOfOrderEvents) must be empty. If sequenceValid is False, at least one error
        list must be non-empty. Otherwise, the response is contradictory.

        Raises:
            ValueError: If validation state is inconsistent with error lists
        """
        if self.sequenceValid:
            # sequenceValid=True requires all error lists to be empty
            errors = []

            if self.missingEvents:
                errors.append(f"missingEvents is not empty: {self.missingEvents}")

            if self.unexpectedEvents:
                errors.append(f"unexpectedEvents is not empty: {self.unexpectedEvents}")

            if self.outOfOrderEvents:
                errors.append(f"outOfOrderEvents is not empty: {self.outOfOrderEvents}")

            if errors:
                msg = (
                    f"sequenceValid is True but error lists are not empty. "
                    f"This is a contradictory validation result. Errors: {'; '.join(errors)}"
                )
                raise ValueError(msg)
        # sequenceValid=False requires at least one error
        elif not (self.missingEvents or self.unexpectedEvents or self.outOfOrderEvents):
            msg = (
                "sequenceValid is False but all error lists are empty. "
                "At least one of missingEvents, unexpectedEvents, or outOfOrderEvents must be non-empty."
            )
            raise ValueError(msg)

        return self


# ============================================================================
# Stage Grouping Models
# ============================================================================


class AuditStageInfo(BaseModel):
    """Stage-grouped events for audit."""

    name: str = Field(..., description="Stage name")
    status: Literal["pending", "ready", "running", "completed", "failed", "skipped"] = Field(
        ..., description="Stage status"
    )
    startedAt: datetime | None = Field(None, description="Stage start time", serialization_alias="startedAt")
    completedAt: datetime | None = Field(None, description="Stage completion time", serialization_alias="completedAt")
    durationSeconds: float | None = Field(
        None, description="Stage duration in seconds", serialization_alias="durationSeconds"
    )
    events: list[WorkflowEventResponse] = Field(default_factory=list, description="Events for this stage")
    output: str | None = Field(None, description="Stage output content")
    errorMessage: str | None = Field(
        None, description="Error message if stage failed", serialization_alias="errorMessage"
    )
    metadata: dict = Field(default_factory=dict, description="Additional stage metadata")

    @model_validator(mode="after")
    def validate_temporal_consistency(self) -> "AuditStageInfo":
        """Ensure completedAt >= startedAt when both are present.

        Raises:
            ValueError: If completedAt < startedAt
        """
        if self.startedAt is not None and self.completedAt is not None:
            if self.completedAt < self.startedAt:
                msg = f"completedAt ({self.completedAt}) must be >= startedAt ({self.startedAt})"
                raise ValueError(msg)
        return self

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "name": "implementation",
                "status": "completed",
                "startedAt": "2026-02-20T10:00:00Z",
                "completedAt": "2026-02-20T10:15:00Z",
                "durationSeconds": 900.0,
                "events": [
                    {
                        "id": "evt-123",
                        "eventType": "ExecutionStarted",
                        "workflowRunId": "wfrun-123",
                        "timestamp": "2026-02-20T10:00:00Z",
                        "agentName": "developer_agent",
                        "stageName": "implementation",
                        "status": None,
                        "data": {},
                    }
                ],
            }
        },
    )


# ============================================================================
# Audit Response Models
# ============================================================================


class WorkflowRunAuditResponse(BaseModel):
    """Comprehensive audit response for workflow run."""

    workflowRun: WorkflowRunSummaryResponse = Field(
        ..., description="Workflow run summary", serialization_alias="workflowRun"
    )
    events: list[WorkflowEventResponse] = Field(..., description="All workflow events")
    stages: list[AuditStageInfo] = Field(..., description="Stage-grouped event information")
    validation: AuditValidationResult | None = Field(
        None,
        description="Sequence validation results (optional, only included when include_validation=true)",
    )
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
                    "startedAt": "2026-02-20T10:00:00Z",
                    "completedAt": "2026-02-20T10:30:00Z",
                    "duration": 1800,
                    "issueTitle": "Fix authentication bug",
                    "issueNumber": 42,
                    "project": "codetoreum",
                    "triggeredBy": "github_webhook",
                    "priority": "high",
                },
                "events": [
                    {
                        "id": "evt-123",
                        "eventType": "WorkflowStarted",
                        "workflowRunId": "wfrun-123",
                        "timestamp": "2026-02-20T10:00:00Z",
                        "agentName": None,
                        "stageName": None,
                        "status": None,
                        "data": {},
                    }
                ],
                "stages": [
                    {
                        "name": "implementation",
                        "status": "completed",
                        "startedAt": "2026-02-20T10:00:00Z",
                        "completedAt": "2026-02-20T10:15:00Z",
                        "durationSeconds": 900.0,
                        "events": [],
                    }
                ],
                "validation": {
                    "sequenceValid": True,
                    "expectedSequence": ["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"],
                    "actualSequence": ["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"],
                    "missingEvents": [],
                    "unexpectedEvents": [],
                    "outOfOrderEvents": [],
                },
                "totalEventCount": 15,
                "offset": 0,
                "limit": 100,
                "hasNext": False,
            }
        },
    )


# ============================================================================
# System Audit Event Models
# ============================================================================


class AuditEventResponse(BaseModel):
    """Single audit event response."""

    id: str = Field(..., description="Unique audit event ID")
    timestamp: datetime = Field(..., description="When the event occurred")
    eventType: str = Field(..., description="Type of audit event", serialization_alias="eventType")
    resourceType: str = Field(..., description="Type of resource being audited", serialization_alias="resourceType")
    resourceId: str = Field(..., description="ID of the resource", serialization_alias="resourceId")
    action: str = Field(..., description="Action performed (create, update, delete, etc.)")
    userId: str = Field(..., description="User or system ID performing the action", serialization_alias="userId")
    correlationId: str | None = Field(
        None, description="Request correlation ID for tracing", serialization_alias="correlationId"
    )
    success: bool = Field(..., description="Whether the action succeeded")
    errorMessage: str | None = Field(
        None, description="Error message if action failed", serialization_alias="errorMessage"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional event metadata")

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "id": "audit-evt-123",
                "timestamp": "2026-02-20T10:15:00Z",
                "eventType": "agent_created",
                "resourceType": "agent",
                "resourceId": "agent-456",
                "action": "create",
                "userId": "user-789",
                "correlationId": "req-abc123",
                "success": True,
                "errorMessage": None,
                "metadata": {
                    "agent_name": "developer_agent",
                    "capabilities": ["code_generation", "testing"],
                },
            }
        },
    )


class AuditEventsListResponse(BaseModel):
    """List of audit events with pagination."""

    events: list[AuditEventResponse] = Field(..., description="List of audit events")
    totalEventCount: int = Field(
        ..., description="Total number of matching events", serialization_alias="totalEventCount"
    )
    offset: int = Field(..., description="Pagination offset")
    limit: int = Field(..., description="Pagination limit")
    hasNext: bool = Field(..., description="Whether more events are available", serialization_alias="hasNext")

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "events": [
                    {
                        "id": "audit-evt-123",
                        "timestamp": "2026-02-20T10:15:00Z",
                        "eventType": "agent_created",
                        "resourceType": "agent",
                        "resourceId": "agent-456",
                        "action": "create",
                        "userId": "user-789",
                        "correlationId": "req-abc123",
                        "success": True,
                        "errorMessage": None,
                        "metadata": {
                            "agent_name": "developer_agent",
                            "capabilities": ["code_generation", "testing"],
                        },
                    }
                ],
                "totalEventCount": 42,
                "offset": 0,
                "limit": 20,
                "hasNext": True,
            }
        },
    )


# ============================================================================
# Causal Chain Models
# ============================================================================


class CausalChainEvent(BaseModel):
    """Event in a causal chain."""

    eventId: str = Field(..., description="Unique event ID", serialization_alias="eventId")
    eventType: str = Field(..., description="Type of event", serialization_alias="eventType")
    occurredAt: datetime = Field(..., description="When the event occurred", serialization_alias="occurredAt")
    causationId: str | None = Field(
        None, description="ID of the event that caused this event", serialization_alias="causationId"
    )
    payloadSummary: dict[str, Any] = Field(
        default_factory=dict, description="Subset of payload for readability", serialization_alias="payloadSummary"
    )

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "eventId": "evt-123",
                "eventType": "WorkItemColumnChanged",
                "occurredAt": "2026-02-20T10:15:00Z",
                "causationId": "evt-122",
                "payloadSummary": {
                    "work_item_id": "WI-456",
                    "from_column": "TODO",
                    "to_column": "IN_PROGRESS",
                },
            }
        },
    )


class CausalChainResponse(BaseModel):
    """Response for causal chain endpoint."""

    rootEventId: str = Field(
        ..., description="ID of the root event (oldest in chain)", serialization_alias="rootEventId"
    )
    chain: list[CausalChainEvent] = Field(
        ...,
        description="Events in causal chain, ordered from queried event back to root",
    )
    truncated: bool = Field(
        ..., description="True if chain was truncated at 100 hops limit", serialization_alias="truncated"
    )
    hopCount: int = Field(..., description="Number of hops in the chain", serialization_alias="hopCount")

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "rootEventId": "evt-120",
                "chain": [
                    {
                        "eventId": "evt-123",
                        "eventType": "WorkflowCompleted",
                        "occurredAt": "2026-02-20T10:30:00Z",
                        "causationId": "evt-122",
                        "payloadSummary": {
                            "workflow_id": "wf-123",
                            "status": "completed",
                        },
                    },
                    {
                        "eventId": "evt-122",
                        "eventType": "WorkflowStageAdvanced",
                        "occurredAt": "2026-02-20T10:20:00Z",
                        "causationId": "evt-121",
                        "payloadSummary": {
                            "workflow_id": "wf-123",
                            "stage": "review",
                        },
                    },
                    {
                        "eventId": "evt-120",
                        "eventType": "WorkItemColumnChanged",
                        "occurredAt": "2026-02-20T10:15:00Z",
                        "causationId": None,
                        "payloadSummary": {
                            "work_item_id": "WI-456",
                            "from_column": "TODO",
                            "to_column": "IN_PROGRESS",
                        },
                    },
                ],
                "truncated": False,
                "hopCount": 3,
            }
        },
    )
