"""
Agent DTOs (Data Transfer Objects)

Defines request and response models for agent REST API endpoints.
These models decouple the API contract from domain models.
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from codetoreum.infrastructure.security import (
    InvalidInputError,
    validate_agent_name,
)

# Constants for validation
MAX_ROLE_DESCRIPTION_LENGTH = 2000
MAX_CAPABILITIES_COUNT = 50

# ============================================================================
# Request Models
# ============================================================================


class AgentCapabilityDTO(BaseModel):
    """Agent capability DTO."""

    skill: str = Field(..., description="Skill/capability name", max_length=200)
    proficiency: float = Field(..., description="Proficiency level (0.0 to 1.0)", ge=0.0, le=1.0)
    description: str | None = Field(None, description="Optional capability description", max_length=500)


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
        description=(
            "Agent type (maker, reviewer, specialized, requirements_analyst, architect, developer, tester, devops)"
        ),
    )
    role_description: str = Field(..., description="Description of agent's role")
    model: str = Field(..., description="LLM model to use", max_length=100)
    capabilities: dict[str, AgentCapabilityDTO] = Field(
        ..., description="Agent capabilities (skill -> capability mapping)"
    )
    timeout_seconds: int = Field(300, description="Execution timeout in seconds", ge=1, le=7200)
    max_retries: int = Field(3, description="Maximum retry attempts", ge=0, le=10)
    requires_docker: bool = Field(True, description="Whether agent requires Docker")
    requires_dev_container: bool = Field(False, description="Whether agent requires dev container")
    makes_code_changes: bool = Field(False, description="Whether agent makes code changes")
    filesystem_write_allowed: bool = Field(True, description="Whether agent can write to filesystem")
    mcp_servers: list[str] | None = Field(None, description="Optional list of MCP server names")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate agent name using centralized validation."""
        try:
            return validate_agent_name(v)
        except InvalidInputError as e:
            raise ValueError(str(e)) from e

    @field_validator("agent_type")
    @classmethod
    def validate_agent_type(cls, v: str) -> str:
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
            msg = f"Agent type must be one of: {', '.join(valid_types)}"
            raise ValueError(msg)
        return v.lower()

    @field_validator("role_description")
    @classmethod
    def validate_role_description(cls, v: str) -> str:
        """Validate role description length."""
        if len(v) > MAX_ROLE_DESCRIPTION_LENGTH:
            msg = f"Role description too long (max {MAX_ROLE_DESCRIPTION_LENGTH} characters)"
            raise ValueError(msg)
        if len(v.strip()) == 0:
            msg = "Role description cannot be empty"
            raise ValueError(msg)
        return v.strip()

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, v: dict[str, AgentCapabilityDTO]) -> dict[str, AgentCapabilityDTO]:
        """Validate capabilities dictionary."""
        if not v:
            msg = "At least one capability is required"
            raise ValueError(msg)
        if len(v) > MAX_CAPABILITIES_COUNT:
            msg = f"Too many capabilities (max {MAX_CAPABILITIES_COUNT})"
            raise ValueError(msg)
        return v


class UpdateAgentRequest(BaseModel):
    """Request to update an existing agent."""

    display_name: str | None = Field(None, description="Updated display name", max_length=200)
    role_description: str | None = Field(None, description="Updated role description")
    model: str | None = Field(None, description="Updated LLM model", max_length=100)
    timeout_seconds: int | None = Field(None, description="Updated timeout in seconds", ge=1, le=7200)
    max_retries: int | None = Field(None, description="Updated max retries", ge=0, le=10)
    requires_docker: bool | None = Field(None, description="Updated Docker requirement")
    requires_dev_container: bool | None = Field(None, description="Updated dev container requirement")
    makes_code_changes: bool | None = Field(None, description="Updated code changes flag")
    filesystem_write_allowed: bool | None = Field(None, description="Updated filesystem write permission")


class AddCapabilityRequest(BaseModel):
    """Request to add a capability to an agent."""

    capability: AgentCapabilityDTO = Field(..., description="Capability to add")


class UpdateCapabilityRequest(BaseModel):
    """Request to update capability proficiency."""

    proficiency: float = Field(..., description="New proficiency level (0.0 to 1.0)", ge=0.0, le=1.0)


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
    average_duration_seconds: float | None
    last_execution_at: datetime | None


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
    mcp_servers: list[str]
    capabilities: dict[str, float]  # skill -> proficiency mapping
    environment_variables: dict[str, str] | None = Field(
        None, description="Environment variables (sensitive values masked)"
    )
    created_at: datetime
    updated_at: datetime
    execution_stats: AgentExecutionStatsDTO | None = None


class AgentSummaryResponse(BaseModel):
    """Agent summary response (for list views)."""

    id: str
    name: str
    display_name: str
    agent_type: str
    model: str
    capabilities: list[str]  # Just skill names
    total_executions: int = 0
    successful_executions: int = 0
    created_at: datetime
    updated_at: datetime


class AgentListResponse(BaseModel):
    """Agent list response with pagination."""

    agents: list[AgentSummaryResponse]
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
    errors: list[str] | None = None
