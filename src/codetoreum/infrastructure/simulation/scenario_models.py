"""
Pydantic models for YAML scenario validation.

These models define the schema for declarative scenario configuration files.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ScenarioProjectModel(BaseModel):
    """Project configuration in scenario file."""

    name: str = Field(..., description="Project name (must be unique)")
    description: str = Field(default="", description="Project description")
    repository_url: str | None = Field(default=None, description="Repository URL (auto-generated if not provided)")
    default_branch: str = Field(default="main", description="Default branch name")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ScenarioStageModel(BaseModel):
    """Pipeline stage configuration in scenario file."""

    name: str = Field(..., description="Stage name")
    agent_type: str = Field(..., description="Agent type for this stage")
    description: str = Field(default="", description="Stage description")
    order: int = Field(..., description="Stage order (1-based)")
    entry_conditions: dict[str, Any] = Field(default_factory=dict, description="Entry conditions")
    exit_conditions: dict[str, Any] = Field(default_factory=dict, description="Exit conditions")
    max_retries: int = Field(default=3, description="Maximum retry attempts", ge=0)
    timeout_seconds: int = Field(default=3600, description="Stage timeout in seconds", ge=1)

    @field_validator("order")
    @classmethod
    def validate_order(cls, v: int) -> int:
        """Validate stage order is positive."""
        if v < 1:
            message = "Stage order must be >= 1"
            raise ValueError(message)
        return v


class ScenarioWorkflowModel(BaseModel):
    """Workflow configuration in scenario file."""

    name: str = Field(..., description="Workflow name")
    description: str = Field(default="", description="Workflow description")
    stages: list[ScenarioStageModel] = Field(default_factory=list, description="Pipeline stages")

    @field_validator("stages")
    @classmethod
    def validate_stages(cls, v: list[ScenarioStageModel]) -> list[ScenarioStageModel]:
        """Validate stages have unique names and sequential order."""
        if not v:
            return v

        stage_names = [s.name for s in v]
        if len(stage_names) != len(set(stage_names)):
            message = "Stage names must be unique"
            raise ValueError(message)

        stage_orders = [s.order for s in v]
        expected_orders = list(range(1, len(v) + 1))
        if sorted(stage_orders) != expected_orders:
            message = f"Stage orders must be sequential 1..{len(v)}"
            raise ValueError(message)

        return v


class ScenarioAgentModel(BaseModel):
    """Agent configuration in scenario file."""

    name: str = Field(..., description="Agent name")
    agent_type: str = Field(default="generic", description="Agent type")
    description: str = Field(default="", description="Agent description")
    capabilities: list[str] = Field(default_factory=lambda: ["code_generation"], description="Agent capabilities")
    llm_model: str = Field(default="claude-3-5-sonnet-20241022", description="LLM model to use")
    temperature: float = Field(default=0.7, description="LLM temperature", ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, description="Maximum tokens", ge=1)
    system_prompt: str = Field(default="", description="System prompt")
    enabled: bool = Field(default=True, description="Whether agent is enabled")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, v: list[str]) -> list[str]:
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
                message = f"Invalid capability: {cap}. Valid: {valid_capabilities}"
                raise ValueError(message)
        return v


class ScenarioBoardModel(BaseModel):
    """Board configuration in scenario file."""

    board_id: str = Field(..., description="Board ID")
    board_name: str = Field(..., description="Board display name")
    columns: list[str] = Field(..., description="Column names in order", min_length=1)
    sla_seconds_by_column: dict[str, int] = Field(
        default_factory=dict,
        description="Optional SLA thresholds in seconds for each column name. "
        "If not specified, automated columns default to 3600 seconds (1 hour).",
    )


class ScenarioBoardItemPlacementModel(BaseModel):
    """Board item placement in scenario file."""

    work_item_title: str = Field(..., description="Work item title prefix to match")
    column: str = Field(..., description="Column to place the item in")


class ScenarioWorkItemModel(BaseModel):
    """Work item configuration in scenario file."""

    title: str = Field(..., description="Work item title")
    description: str = Field(default="", description="Work item description")
    labels: list[str] = Field(default_factory=list, description="Labels")
    priority: str = Field(default="medium", description="Priority level")
    status: str = Field(default="new", description="Initial status")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        """Validate priority is valid."""
        valid_priorities = {"low", "medium", "high", "critical"}
        if v.lower() not in valid_priorities:
            message = f"Invalid priority: {v}. Valid: {valid_priorities}"
            raise ValueError(message)
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
            message = f"Invalid status: {v}. Valid: {valid_statuses}"
            raise ValueError(message)
        return v.lower()


class ScenarioModel(BaseModel):
    """
    Complete scenario configuration model.

    This is the root model for YAML scenario files.
    """

    name: str = Field(..., description="Scenario name")
    description: str = Field(default="", description="Scenario description")
    version: str = Field(default="1.0", description="Scenario version")
    created_at: datetime | None = Field(default=None, description="Scenario creation timestamp")

    # Simulation config
    speed_multiplier: float = Field(default=10.0, description="Time speed multiplier", gt=0)
    auto_advance: bool = Field(default=False, description="Auto-advance time")

    # Data definitions
    projects: list[ScenarioProjectModel] = Field(default_factory=list, description="Projects to create")
    workflows: list[ScenarioWorkflowModel] = Field(default_factory=list, description="Workflows to create")
    agents: list[ScenarioAgentModel] = Field(default_factory=list, description="Agents to create")
    work_items: list[ScenarioWorkItemModel] = Field(default_factory=list, description="Work items to create")
    boards: list[ScenarioBoardModel] = Field(default_factory=list, description="Boards to create")
    board_placements: list[ScenarioBoardItemPlacementModel] = Field(
        default_factory=list, description="Work item placements on boards"
    )

    # Additional metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional scenario metadata")

    @field_validator("projects")
    @classmethod
    def validate_projects(cls, v: list[ScenarioProjectModel]) -> list[ScenarioProjectModel]:
        """Validate project names are unique."""
        if not v:
            return v

        project_names = [p.name for p in v]
        if len(project_names) != len(set(project_names)):
            message = "Project names must be unique"
            raise ValueError(message)

        return v

    @field_validator("workflows")
    @classmethod
    def validate_workflows(cls, v: list[ScenarioWorkflowModel]) -> list[ScenarioWorkflowModel]:
        """Validate workflow names are unique."""
        if not v:
            return v

        workflow_names = [w.name for w in v]
        if len(workflow_names) != len(set(workflow_names)):
            message = "Workflow names must be unique"
            raise ValueError(message)

        return v

    @field_validator("agents")
    @classmethod
    def validate_agents(cls, v: list[ScenarioAgentModel]) -> list[ScenarioAgentModel]:
        """Validate agent names are unique."""
        if not v:
            return v

        agent_names = [a.name for a in v]
        if len(agent_names) != len(set(agent_names)):
            message = "Agent names must be unique"
            raise ValueError(message)

        return v

    model_config = ConfigDict(
        json_schema_extra={
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
    )
