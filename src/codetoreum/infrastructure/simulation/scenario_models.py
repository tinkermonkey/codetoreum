"""
Pydantic models for YAML scenario validation.

These models define the schema for declarative scenario configuration files.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class ScenarioProjectModel(BaseModel):
    """Project configuration in scenario file."""

    name: str = Field(..., description="Project name (must be unique)")
    description: str = Field(default="", description="Project description")
    repository_url: Optional[str] = Field(
        None, description="Repository URL (auto-generated if not provided)"
    )
    default_branch: str = Field(default="main", description="Default branch name")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ScenarioStageModel(BaseModel):
    """Pipeline stage configuration in scenario file."""

    name: str = Field(..., description="Stage name")
    agent_type: str = Field(..., description="Agent type for this stage")
    description: str = Field(default="", description="Stage description")
    order: int = Field(..., description="Stage order (1-based)")
    entry_conditions: Dict[str, Any] = Field(
        default_factory=dict, description="Entry conditions"
    )
    exit_conditions: Dict[str, Any] = Field(
        default_factory=dict, description="Exit conditions"
    )
    max_retries: int = Field(default=3, description="Maximum retry attempts", ge=0)
    timeout_seconds: int = Field(
        default=3600, description="Stage timeout in seconds", ge=1
    )

    @field_validator("order")
    @classmethod
    def validate_order(cls, v: int) -> int:
        """Validate stage order is positive."""
        if v < 1:
            raise ValueError("Stage order must be >= 1")
        return v


class ScenarioWorkflowModel(BaseModel):
    """Workflow configuration in scenario file."""

    name: str = Field(..., description="Workflow name")
    description: str = Field(default="", description="Workflow description")
    stages: List[ScenarioStageModel] = Field(
        default_factory=list, description="Pipeline stages"
    )

    @field_validator("stages")
    @classmethod
    def validate_stages(cls, v: List[ScenarioStageModel]) -> List[ScenarioStageModel]:
        """Validate stages have unique names and sequential order."""
        if not v:
            return v

        stage_names = [s.name for s in v]
        if len(stage_names) != len(set(stage_names)):
            raise ValueError("Stage names must be unique")

        stage_orders = [s.order for s in v]
        expected_orders = list(range(1, len(v) + 1))
        if sorted(stage_orders) != expected_orders:
            raise ValueError(f"Stage orders must be sequential 1..{len(v)}")

        return v


class ScenarioAgentModel(BaseModel):
    """Agent configuration in scenario file."""

    name: str = Field(..., description="Agent name")
    agent_type: str = Field(default="generic", description="Agent type")
    description: str = Field(default="", description="Agent description")
    capabilities: List[str] = Field(
        default_factory=lambda: ["code_generation"], description="Agent capabilities"
    )
    llm_model: str = Field(
        default="claude-3-5-sonnet-20241022", description="LLM model to use"
    )
    temperature: float = Field(
        default=0.7, description="LLM temperature", ge=0.0, le=2.0
    )
    max_tokens: int = Field(default=4096, description="Maximum tokens", ge=1)
    system_prompt: str = Field(default="", description="System prompt")
    enabled: bool = Field(default=True, description="Whether agent is enabled")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, v: List[str]) -> List[str]:
        """Validate capabilities are valid."""
        valid_capabilities = {
            "code_generation",
            "code_review",
            "testing",
            "documentation",
            "security_analysis",
            "performance_analysis",
        }
        for cap in v:
            if cap not in valid_capabilities:
                raise ValueError(
                    f"Invalid capability: {cap}. Valid: {valid_capabilities}"
                )
        return v


class ScenarioWorkItemModel(BaseModel):
    """Work item configuration in scenario file."""

    title: str = Field(..., description="Work item title")
    description: str = Field(default="", description="Work item description")
    labels: List[str] = Field(default_factory=list, description="Labels")
    priority: str = Field(default="medium", description="Priority level")
    status: str = Field(default="new", description="Initial status")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        """Validate priority is valid."""
        valid_priorities = {"low", "medium", "high", "critical"}
        if v.lower() not in valid_priorities:
            raise ValueError(f"Invalid priority: {v}. Valid: {valid_priorities}")
        return v.lower()

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate status is valid."""
        valid_statuses = {
            "new",
            "assigned",
            "in_progress",
            "under_review",
            "completed",
            "failed",
            "blocked",
        }
        if v.lower() not in valid_statuses:
            raise ValueError(f"Invalid status: {v}. Valid: {valid_statuses}")
        return v.lower()


class ScenarioModel(BaseModel):
    """
    Complete scenario configuration model.

    This is the root model for YAML scenario files.
    """

    name: str = Field(..., description="Scenario name")
    description: str = Field(default="", description="Scenario description")
    version: str = Field(default="1.0", description="Scenario version")
    created_at: Optional[datetime] = Field(
        None, description="Scenario creation timestamp"
    )

    # Simulation config
    speed_multiplier: float = Field(
        default=10.0, description="Time speed multiplier", gt=0
    )
    auto_advance: bool = Field(
        default=False, description="Auto-advance time"
    )

    # Data definitions
    projects: List[ScenarioProjectModel] = Field(
        default_factory=list, description="Projects to create"
    )
    workflows: List[ScenarioWorkflowModel] = Field(
        default_factory=list, description="Workflows to create"
    )
    agents: List[ScenarioAgentModel] = Field(
        default_factory=list, description="Agents to create"
    )
    work_items: List[ScenarioWorkItemModel] = Field(
        default_factory=list, description="Work items to create"
    )

    # Additional metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional scenario metadata"
    )

    @field_validator("projects")
    @classmethod
    def validate_projects(cls, v: List[ScenarioProjectModel]) -> List[ScenarioProjectModel]:
        """Validate project names are unique."""
        if not v:
            return v

        project_names = [p.name for p in v]
        if len(project_names) != len(set(project_names)):
            raise ValueError("Project names must be unique")

        return v

    @field_validator("workflows")
    @classmethod
    def validate_workflows(cls, v: List[ScenarioWorkflowModel]) -> List[ScenarioWorkflowModel]:
        """Validate workflow names are unique."""
        if not v:
            return v

        workflow_names = [w.name for w in v]
        if len(workflow_names) != len(set(workflow_names)):
            raise ValueError("Workflow names must be unique")

        return v

    @field_validator("agents")
    @classmethod
    def validate_agents(cls, v: List[ScenarioAgentModel]) -> List[ScenarioAgentModel]:
        """Validate agent names are unique."""
        if not v:
            return v

        agent_names = [a.name for a in v]
        if len(agent_names) != len(set(agent_names)):
            raise ValueError("Agent names must be unique")

        return v

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "name": "Example Scenario",
                "description": "An example scenario for testing",
                "version": "1.0",
                "speed_multiplier": 10.0,
                "projects": [
                    {
                        "name": "test-project",
                        "description": "Test project",
                    }
                ],
                "workflows": [
                    {
                        "name": "simple-workflow",
                        "stages": [
                            {
                                "name": "design",
                                "agent_type": "architect",
                                "order": 1,
                            }
                        ],
                    }
                ],
                "agents": [
                    {
                        "name": "architect",
                        "agent_type": "architect",
                        "capabilities": ["code_generation"],
                    }
                ],
                "work_items": [
                    {
                        "title": "Test task",
                        "priority": "medium",
                    }
                ],
            }
        }
