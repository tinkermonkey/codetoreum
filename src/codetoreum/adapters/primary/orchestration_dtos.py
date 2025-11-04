"""
Orchestration Data Transfer Objects (DTOs)

DTOs for orchestration and scheduler REST API endpoints.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from codetoreum.adapters.primary.api_models import PaginatedResponse


# ============================================================================
# Orchestration Request Models
# ============================================================================


class StartWorkflowExecutionRequest(BaseModel):
    """Request to start workflow execution for a work item"""

    work_item_id: str = Field(..., description="Work item ID to execute workflow for")
    workflow_id: str = Field(..., description="Workflow definition ID to use")
    stage_name: Optional[str] = Field(None, description="Stage to start from (optional, defaults to first stage)")
    priority: str = Field("MEDIUM", description="Execution priority: LOW, MEDIUM, HIGH, CRITICAL")
    context: Dict[str, Any] = Field(default_factory=dict, description="Additional execution context")

    class Config:
        """Pydantic configuration"""

        json_schema_extra = {
            "example": {
                "work_item_id": "wi-123",
                "workflow_id": "wf-456",
                "stage_name": None,
                "priority": "HIGH",
                "context": {
                    "trigger": "manual",
                    "user": "developer@example.com"
                }
            }
        }


class CancelWorkflowExecutionRequest(BaseModel):
    """Request to cancel a workflow execution"""

    reason: str = Field(..., description="Reason for cancellation")
    force: bool = Field(False, description="Force immediate cancellation without cleanup")

    class Config:
        """Pydantic configuration"""

        json_schema_extra = {
            "example": {
                "reason": "User requested cancellation",
                "force": False
            }
        }


class PauseWorkflowExecutionRequest(BaseModel):
    """Request to pause a workflow execution"""

    reason: str = Field(..., description="Reason for pausing")

    class Config:
        """Pydantic configuration"""

        json_schema_extra = {
            "example": {
                "reason": "Waiting for external dependency"
            }
        }


class ResumeWorkflowExecutionRequest(BaseModel):
    """Request to resume a paused workflow execution"""

    from_stage: Optional[str] = Field(None, description="Stage to resume from (defaults to paused stage)")

    class Config:
        """Pydantic configuration"""

        json_schema_extra = {
            "example": {
                "from_stage": None
            }
        }


# ============================================================================
# Orchestration Response Models
# ============================================================================


class WorkflowExecutionResponse(BaseModel):
    """Response for workflow execution operations"""

    execution_id: str = Field(..., description="Unique execution ID")
    workflow_run_id: str = Field(..., description="Workflow run ID")
    work_item_id: str = Field(..., description="Work item ID")
    workflow_id: str = Field(..., description="Workflow definition ID")
    status: str = Field(..., description="Execution status")
    current_stage: Optional[str] = Field(None, description="Current stage name")
    started_at: Optional[datetime] = Field(None, description="Execution start time")
    message: str = Field(..., description="Status message")

    class Config:
        """Pydantic configuration"""

        json_encoders = {datetime: lambda v: v.isoformat()}
        json_schema_extra = {
            "example": {
                "execution_id": "exec-789",
                "workflow_run_id": "wr-123",
                "work_item_id": "wi-123",
                "workflow_id": "wf-456",
                "status": "STARTED",
                "current_stage": "development",
                "started_at": "2025-11-03T10:30:00Z",
                "message": "Workflow execution started successfully"
            }
        }


class StartWorkflowExecutionResponse(BaseModel):
    """Response for starting workflow execution"""

    execution_id: str = Field(..., description="Unique execution ID")
    workflow_run_id: str = Field(..., description="Workflow run ID")
    status: str = Field(..., description="Initial status (typically ACCEPTED or STARTED)")
    message: str = Field(..., description="Response message")
    started_at: datetime = Field(..., description="Start timestamp")

    class Config:
        """Pydantic configuration"""

        json_encoders = {datetime: lambda v: v.isoformat()}
        json_schema_extra = {
            "example": {
                "execution_id": "exec-789",
                "workflow_run_id": "wr-123",
                "status": "ACCEPTED",
                "message": "Workflow execution queued successfully",
                "started_at": "2025-11-03T10:30:00Z"
            }
        }


# ============================================================================
# Scheduler/Queue Response Models
# ============================================================================


class QueuedExecutionInfo(BaseModel):
    """Information about a queued or running execution"""

    execution_id: str = Field(..., description="Execution ID")
    workflow_run_id: str = Field(..., description="Workflow run ID")
    work_item_id: str = Field(..., description="Work item ID")
    work_item_title: str = Field(..., description="Work item title")
    workflow_name: str = Field(..., description="Workflow name")
    stage_name: str = Field(..., description="Current stage name")
    agent_name: str = Field(..., description="Agent name")
    status: str = Field(..., description="Execution status (QUEUED, RUNNING, etc.)")
    priority: str = Field(..., description="Execution priority")
    queued_at: datetime = Field(..., description="When execution was queued")
    started_at: Optional[datetime] = Field(None, description="When execution started (if running)")
    estimated_duration_seconds: Optional[int] = Field(None, description="Estimated duration")

    class Config:
        """Pydantic configuration"""

        json_encoders = {datetime: lambda v: v.isoformat()}
        json_schema_extra = {
            "example": {
                "execution_id": "exec-789",
                "workflow_run_id": "wr-123",
                "work_item_id": "wi-123",
                "work_item_title": "Implement user authentication",
                "workflow_name": "feature-development",
                "stage_name": "development",
                "agent_name": "software_engineer",
                "status": "RUNNING",
                "priority": "HIGH",
                "queued_at": "2025-11-03T10:30:00Z",
                "started_at": "2025-11-03T10:31:00Z",
                "estimated_duration_seconds": 1800
            }
        }


class ExecutionQueueResponse(PaginatedResponse):
    """Response with execution queue information"""

    executions: List[QueuedExecutionInfo] = Field(..., description="List of queued/running executions")
    queue_stats: Dict[str, int] = Field(
        default_factory=dict,
        description="Queue statistics (total_queued, total_running, by_priority, etc.)"
    )

    class Config:
        """Pydantic configuration"""

        json_encoders = {datetime: lambda v: v.isoformat()}
        json_schema_extra = {
            "example": {
                "executions": [
                    {
                        "execution_id": "exec-789",
                        "workflow_run_id": "wr-123",
                        "work_item_id": "wi-123",
                        "work_item_title": "Implement feature X",
                        "workflow_name": "feature-development",
                        "stage_name": "development",
                        "agent_name": "software_engineer",
                        "status": "RUNNING",
                        "priority": "HIGH",
                        "queued_at": "2025-11-03T10:30:00Z",
                        "started_at": "2025-11-03T10:31:00Z",
                        "estimated_duration_seconds": 1800
                    }
                ],
                "total_count": 5,
                "page": 1,
                "page_size": 50,
                "has_next": False,
                "queue_stats": {
                    "total_queued": 3,
                    "total_running": 2,
                    "critical_priority": 1,
                    "high_priority": 2,
                    "medium_priority": 1,
                    "low_priority": 1
                }
            }
        }


# ============================================================================
# Workflow Entry Condition Validation Models
# ============================================================================


class EntryConditionValidationRequest(BaseModel):
    """Request to validate workflow entry conditions"""

    work_item_id: str = Field(..., description="Work item ID to validate")
    workflow_id: str = Field(..., description="Workflow ID to validate against")
    stage_name: Optional[str] = Field(None, description="Specific stage to validate (optional)")

    class Config:
        """Pydantic configuration"""

        json_schema_extra = {
            "example": {
                "work_item_id": "wi-123",
                "workflow_id": "wf-456",
                "stage_name": "development"
            }
        }


class ConditionValidationResult(BaseModel):
    """Result of validating a single condition"""

    condition_type: str = Field(..., description="Type of condition")
    is_met: bool = Field(..., description="Whether condition is met")
    message: str = Field(..., description="Validation message")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional details")

    class Config:
        """Pydantic configuration"""

        json_schema_extra = {
            "example": {
                "condition_type": "work_item_status",
                "is_met": True,
                "message": "Work item status is 'in_progress'",
                "details": {"expected": "in_progress", "actual": "in_progress"}
            }
        }


class EntryConditionValidationResponse(BaseModel):
    """Response for entry condition validation"""

    can_start: bool = Field(..., description="Whether workflow can start")
    stage_name: str = Field(..., description="Stage being validated")
    condition_results: List[ConditionValidationResult] = Field(..., description="Results for each condition")
    blocking_conditions: List[str] = Field(default_factory=list, description="Conditions that are not met")

    class Config:
        """Pydantic configuration"""

        json_schema_extra = {
            "example": {
                "can_start": True,
                "stage_name": "development",
                "condition_results": [
                    {
                        "condition_type": "work_item_status",
                        "is_met": True,
                        "message": "Work item status is valid",
                        "details": {}
                    }
                ],
                "blocking_conditions": []
            }
        }
