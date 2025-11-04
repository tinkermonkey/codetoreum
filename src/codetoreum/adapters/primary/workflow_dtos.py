"""
Workflow Data Transfer Objects (DTOs)

DTOs for Workflow REST API endpoints. These decouple the external API
contracts from the internal domain models, allowing independent evolution.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from codetoreum.adapters.primary.api_models import PaginatedResponse


# ============================================================================
# Workflow Stage Models
# ============================================================================


class StageTransition(BaseModel):
    """Transition between workflow stages"""

    from_stage: str = Field(..., description="Source stage name")
    to_stage: str = Field(..., description="Target stage name")
    condition: Optional[str] = Field(None, description="Transition condition (optional)")

    class Config:
        """Pydantic configuration"""

        json_schema_extra = {
            "example": {
                "from_stage": "development",
                "to_stage": "code_review",
                "condition": "tests_passed"
            }
        }


class StageEntryCondition(BaseModel):
    """Entry condition for a workflow stage"""

    condition_type: str = Field(..., description="Type of condition (status, label, approval, etc.)")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Condition parameters")

    class Config:
        """Pydantic configuration"""

        json_schema_extra = {
            "example": {
                "condition_type": "work_item_status",
                "parameters": {"status": "in_progress"}
            }
        }


class WorkflowStageResponse(BaseModel):
    """Workflow stage information"""

    name: str = Field(..., description="Stage name (unique within workflow)")
    agent_name: str = Field(..., description="Agent to execute this stage")
    timeout_seconds: Optional[int] = Field(None, description="Stage timeout in seconds")
    retry_count: int = Field(0, description="Number of retries on failure")
    entry_conditions: List[StageEntryCondition] = Field(
        default_factory=list,
        description="Conditions that must be met to enter this stage"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional stage metadata")

    class Config:
        """Pydantic configuration"""

        json_schema_extra = {
            "example": {
                "name": "development",
                "agent_name": "software_engineer",
                "timeout_seconds": 1800,
                "retry_count": 2,
                "entry_conditions": [
                    {
                        "condition_type": "work_item_status",
                        "parameters": {"status": "assigned"}
                    }
                ],
                "metadata": {
                    "requires_docker": True,
                    "makes_code_changes": True
                }
            }
        }


class WorkflowStageRequest(BaseModel):
    """Request to create/update a workflow stage"""

    name: str = Field(..., description="Stage name", min_length=1, max_length=100)
    agent_name: str = Field(..., description="Agent to execute this stage", min_length=1)
    timeout_seconds: Optional[int] = Field(None, ge=1, le=7200, description="Stage timeout (max 2 hours)")
    retry_count: int = Field(0, ge=0, le=5, description="Retry count (max 5)")
    entry_conditions: List[StageEntryCondition] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        """Pydantic configuration"""

        json_schema_extra = {
            "example": {
                "name": "development",
                "agent_name": "software_engineer",
                "timeout_seconds": 1800,
                "retry_count": 2,
                "entry_conditions": [],
                "metadata": {}
            }
        }


# ============================================================================
# Workflow Definition Models
# ============================================================================


class CreateWorkflowRequest(BaseModel):
    """Request to create a new workflow definition"""

    name: str = Field(..., description="Workflow name", min_length=1, max_length=200)
    description: str = Field(..., description="Workflow description")
    project_id: str = Field(..., description="Project ID this workflow belongs to")
    stages: List[WorkflowStageRequest] = Field(..., description="Workflow stages", min_items=1)
    transitions: List[StageTransition] = Field(default_factory=list, description="Stage transitions")
    work_item_types: Optional[List[str]] = Field(
        None,
        description="Work item types this workflow applies to (issue, pr, discussion)"
    )
    is_template: bool = Field(False, description="Whether this is a reusable template")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional workflow metadata")

    class Config:
        """Pydantic configuration"""

        json_schema_extra = {
            "example": {
                "name": "feature-development",
                "description": "Standard workflow for feature development",
                "project_id": "proj-123",
                "stages": [
                    {
                        "name": "development",
                        "agent_name": "software_engineer",
                        "timeout_seconds": 1800,
                        "retry_count": 2
                    },
                    {
                        "name": "code_review",
                        "agent_name": "code_reviewer",
                        "timeout_seconds": 900,
                        "retry_count": 1
                    }
                ],
                "transitions": [
                    {
                        "from_stage": "development",
                        "to_stage": "code_review",
                        "condition": "tests_passed"
                    }
                ],
                "work_item_types": ["issue", "feature"],
                "is_template": False,
                "metadata": {}
            }
        }


class UpdateWorkflowRequest(BaseModel):
    """Request to update an existing workflow definition"""

    name: Optional[str] = Field(None, description="Updated workflow name", min_length=1, max_length=200)
    description: Optional[str] = Field(None, description="Updated description")
    stages: Optional[List[WorkflowStageRequest]] = Field(None, description="Updated stages", min_items=1)
    transitions: Optional[List[StageTransition]] = Field(None, description="Updated transitions")
    work_item_types: Optional[List[str]] = Field(None, description="Updated work item types")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Updated metadata")

    class Config:
        """Pydantic configuration"""

        json_schema_extra = {
            "example": {
                "name": "feature-development-v2",
                "description": "Updated feature development workflow",
                "stages": [
                    {
                        "name": "development",
                        "agent_name": "software_engineer",
                        "timeout_seconds": 2400,
                        "retry_count": 3
                    }
                ]
            }
        }


class WorkflowResponse(BaseModel):
    """Response with workflow definition"""

    id: str = Field(..., description="Workflow ID")
    name: str = Field(..., description="Workflow name")
    description: str = Field(..., description="Workflow description")
    project_id: str = Field(..., description="Project ID")
    version: int = Field(..., description="Workflow version number")
    stages: List[WorkflowStageResponse] = Field(..., description="Workflow stages")
    transitions: List[StageTransition] = Field(default_factory=list, description="Stage transitions")
    work_item_types: List[str] = Field(default_factory=list, description="Applicable work item types")
    is_template: bool = Field(..., description="Whether this is a template")
    is_active: bool = Field(..., description="Whether workflow is active")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        """Pydantic configuration"""

        json_encoders = {datetime: lambda v: v.isoformat()}
        json_schema_extra = {
            "example": {
                "id": "wf-123",
                "name": "feature-development",
                "description": "Standard workflow for feature development",
                "project_id": "proj-123",
                "version": 1,
                "stages": [
                    {
                        "name": "development",
                        "agent_name": "software_engineer",
                        "timeout_seconds": 1800,
                        "retry_count": 2,
                        "entry_conditions": [],
                        "metadata": {}
                    }
                ],
                "transitions": [
                    {
                        "from_stage": "development",
                        "to_stage": "code_review",
                        "condition": None
                    }
                ],
                "work_item_types": ["issue", "feature"],
                "is_template": False,
                "is_active": True,
                "created_at": "2025-11-03T10:00:00Z",
                "updated_at": "2025-11-03T10:00:00Z",
                "metadata": {}
            }
        }


class WorkflowSummaryResponse(BaseModel):
    """Summary response for workflow list"""

    id: str = Field(..., description="Workflow ID")
    name: str = Field(..., description="Workflow name")
    description: str = Field(..., description="Workflow description")
    project_id: str = Field(..., description="Project ID")
    version: int = Field(..., description="Current version")
    stage_count: int = Field(..., description="Number of stages")
    work_item_types: List[str] = Field(default_factory=list, description="Applicable work item types")
    is_template: bool = Field(..., description="Whether this is a template")
    is_active: bool = Field(..., description="Whether workflow is active")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        """Pydantic configuration"""

        json_encoders = {datetime: lambda v: v.isoformat()}


class WorkflowListResponse(PaginatedResponse):
    """Response with list of workflows"""

    workflows: List[WorkflowSummaryResponse] = Field(..., description="List of workflows")

    class Config:
        """Pydantic configuration"""

        json_encoders = {datetime: lambda v: v.isoformat()}


class WorkflowVersionResponse(BaseModel):
    """Workflow version information"""

    version: int = Field(..., description="Version number")
    created_at: datetime = Field(..., description="When this version was created")
    created_by: Optional[str] = Field(None, description="Who created this version")
    changes_summary: str = Field(..., description="Summary of changes in this version")

    class Config:
        """Pydantic configuration"""

        json_encoders = {datetime: lambda v: v.isoformat()}


class WorkflowVersionListResponse(BaseModel):
    """Response with workflow version history"""

    workflow_id: str = Field(..., description="Workflow ID")
    versions: List[WorkflowVersionResponse] = Field(..., description="Version history")
    total_count: int = Field(..., description="Total version count")

    class Config:
        """Pydantic configuration"""

        json_encoders = {datetime: lambda v: v.isoformat()}


class WorkflowCommandResult(BaseModel):
    """Result of a workflow command operation"""

    success: bool = Field(..., description="Whether operation succeeded")
    workflow_id: str = Field(..., description="Workflow ID")
    version: Optional[int] = Field(None, description="New version number (for updates)")
    message: str = Field(..., description="Result message")
    errors: Optional[List[str]] = Field(None, description="Error messages if any")

    class Config:
        """Pydantic configuration"""

        json_schema_extra = {
            "example": {
                "success": True,
                "workflow_id": "wf-123",
                "version": 2,
                "message": "Workflow updated successfully",
                "errors": None
            }
        }


# ============================================================================
# Workflow Validation Models
# ============================================================================


class WorkflowValidationError(BaseModel):
    """Workflow validation error"""

    error_type: str = Field(..., description="Error type (circular_dependency, invalid_agent, etc.)")
    message: str = Field(..., description="Error message")
    stage_name: Optional[str] = Field(None, description="Stage that caused the error")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional error details")

    class Config:
        """Pydantic configuration"""

        json_schema_extra = {
            "example": {
                "error_type": "circular_dependency",
                "message": "Circular dependency detected in stage transitions",
                "stage_name": "development",
                "details": {
                    "cycle": ["development", "code_review", "development"]
                }
            }
        }


class WorkflowValidationResponse(BaseModel):
    """Workflow validation result"""

    is_valid: bool = Field(..., description="Whether workflow is valid")
    errors: List[WorkflowValidationError] = Field(default_factory=list, description="Validation errors")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings (non-blocking)")

    class Config:
        """Pydantic configuration"""

        json_schema_extra = {
            "example": {
                "is_valid": False,
                "errors": [
                    {
                        "error_type": "circular_dependency",
                        "message": "Circular dependency detected",
                        "stage_name": "development",
                        "details": {}
                    }
                ],
                "warnings": ["Stage 'testing' has no retry configured"]
            }
        }
