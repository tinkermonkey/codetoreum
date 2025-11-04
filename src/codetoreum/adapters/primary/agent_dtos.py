"""
Agent DTOs (Data Transfer Objects)

Defines request and response models for agent REST API endpoints.
These models decouple the API contract from domain models.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ============================================================================
# Request Models
# ============================================================================


class AgentCapabilityDTO(BaseModel):
    """Agent capability DTO."""

    skill: str = Field(..., description="Skill/capability name", max_length=200)
    proficiency: float = Field(
        ..., description="Proficiency level (0.0 to 1.0)", ge=0.0, le=1.0
    )
    description: Optional[str] = Field(
        None, description="Optional capability description", max_length=500
    )


class CreateAgentRequest(BaseModel):
    """Request to create a new agent."""

    name: str = Field(
        ...,
        description="Agent name (unique identifier)",
        max_length=200,
        pattern="^[a-z0-9_]+$",
    )
    display_name: str = Field(..., description="Human-readable agent name", max_length=200)
    agent_type: str = Field(
        ...,
        description="Agent type (maker, reviewer, specialized, requirements_analyst, architect, developer, tester, devops)",
    )
    role_description: str = Field(..., description="Description of agent's role")
    model: str = Field(..., description="LLM model to use", max_length=100)
    capabilities: Dict[str, AgentCapabilityDTO] = Field(
        ..., description="Agent capabilities (skill -> capability mapping)"
    )
    timeout_seconds: int = Field(
        300, description="Execution timeout in seconds", ge=1, le=7200
    )
    max_retries: int = Field(3, description="Maximum retry attempts", ge=0, le=10)
    requires_docker: bool = Field(True, description="Whether agent requires Docker")
    requires_dev_container: bool = Field(
        False, description="Whether agent requires dev container"
    )
    makes_code_changes: bool = Field(False, description="Whether agent makes code changes")
    filesystem_write_allowed: bool = Field(
        True, description="Whether agent can write to filesystem"
    )
    mcp_servers: Optional[List[str]] = Field(
        None, description="Optional list of MCP server names"
    )

    @field_validator("agent_type")
    @classmethod
    def validate_agent_type(cls, v):
        """Validate agent type is valid."""
        valid_types = [
            "maker",
            "reviewer",
            "specialized",
            "requirements_analyst",
            "architect",
            "developer",
            "tester",
            "devops",
        ]
        if v.lower() not in valid_types:
            raise ValueError(f"Agent type must be one of: {', '.join(valid_types)}")
        return v.lower()


class UpdateAgentRequest(BaseModel):
    """Request to update an existing agent."""

    display_name: Optional[str] = Field(None, description="Updated display name", max_length=200)
    role_description: Optional[str] = Field(None, description="Updated role description")
    model: Optional[str] = Field(None, description="Updated LLM model", max_length=100)
    timeout_seconds: Optional[int] = Field(
        None, description="Updated timeout in seconds", ge=1, le=7200
    )
    max_retries: Optional[int] = Field(
        None, description="Updated max retries", ge=0, le=10
    )
    requires_docker: Optional[bool] = Field(
        None, description="Updated Docker requirement"
    )
    requires_dev_container: Optional[bool] = Field(
        None, description="Updated dev container requirement"
    )
    makes_code_changes: Optional[bool] = Field(
        None, description="Updated code changes flag"
    )
    filesystem_write_allowed: Optional[bool] = Field(
        None, description="Updated filesystem write permission"
    )


class AddCapabilityRequest(BaseModel):
    """Request to add a capability to an agent."""

    capability: AgentCapabilityDTO = Field(..., description="Capability to add")


class UpdateCapabilityRequest(BaseModel):
    """Request to update capability proficiency."""

    proficiency: float = Field(
        ..., description="New proficiency level (0.0 to 1.0)", ge=0.0, le=1.0
    )


class AddMcpServerRequest(BaseModel):
    """Request to add an MCP server to agent."""

    server_name: str = Field(..., description="MCP server name", max_length=200)


# ============================================================================
# Response Models
# ============================================================================


class AgentExecutionStatsDTO(BaseModel):
    """Agent execution statistics DTO."""

    total_executions: int
    successful_executions: int
    failed_executions: int
    timeout_executions: int
    average_duration_seconds: Optional[float]
    last_execution_at: Optional[datetime]


class AgentResponse(BaseModel):
    """Agent response DTO."""

    id: str
    name: str
    display_name: str
    agent_type: str
    role_description: str
    model: str
    timeout_seconds: int
    max_retries: int
    requires_docker: bool
    requires_dev_container: bool
    makes_code_changes: bool
    filesystem_write_allowed: bool
    mcp_servers: List[str]
    capabilities: Dict[str, float]  # skill -> proficiency mapping
    environment_variables: Optional[Dict[str, str]] = Field(
        None, description="Environment variables (sensitive values masked)"
    )
    created_at: datetime
    updated_at: datetime
    execution_stats: Optional[AgentExecutionStatsDTO] = None


class AgentSummaryResponse(BaseModel):
    """Agent summary response (for list views)."""

    id: str
    name: str
    display_name: str
    agent_type: str
    model: str
    capabilities: List[str]  # Just skill names
    total_executions: int = 0
    successful_executions: int = 0
    created_at: datetime
    updated_at: datetime


class AgentListResponse(BaseModel):
    """Agent list response with pagination."""

    agents: List[AgentSummaryResponse]
    total_count: int
    offset: int
    limit: int
    page: int = 1
    has_next: bool


class AgentCommandResult(BaseModel):
    """Result from agent command operations."""

    success: bool
    agent_id: str
    message: str
    version: int
    errors: Optional[List[str]] = None
