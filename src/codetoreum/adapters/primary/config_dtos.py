"""
Configuration Management DTOs

Data Transfer Objects for configuration management API endpoints.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from codetoreum.infrastructure.security import InvalidInputError, validate_env_var_name

# ============================================================================
# Request DTOs
# ============================================================================


class UpdateProjectConfigRequest(BaseModel):
    """Request to update project configuration"""
    updates: dict[str, Any] = Field(..., description="Partial configuration updates")
    reason: str | None = Field(None, description="Reason for update (for audit trail)")

    @field_validator("updates")
    @classmethod
    def validate_updates(cls, v):
        if not v:
            msg = "Updates cannot be empty"
            raise ValueError(msg)
        return v


class UpdateAgentConfigRequest(BaseModel):
    """Request to update agent configuration"""
    updates: dict[str, Any] = Field(..., description="Partial agent configuration updates")
    reason: str | None = Field(None, description="Reason for update")

    @field_validator("updates")
    @classmethod
    def validate_updates(cls, v):
        if not v:
            msg = "Updates cannot be empty"
            raise ValueError(msg)
        return v


class UpdatePipelineConfigRequest(BaseModel):
    """Request to update pipeline configuration"""
    updates: dict[str, Any] = Field(..., description="Partial pipeline configuration updates")
    reason: str | None = Field(None, description="Reason for update")

    @field_validator("updates")
    @classmethod
    def validate_updates(cls, v):
        if not v:
            msg = "Updates cannot be empty"
            raise ValueError(msg)
        return v


class AddEnvironmentVariableRequest(BaseModel):
    """Request to add/update environment variable"""
    variable_name: str = Field(..., min_length=1, max_length=255, description="Variable name")
    # Increased limit to 100k to accommodate base64-encoded certificates, JSON configs, and multi-line scripts
    variable_value: str = Field(..., max_length=100000, description="Variable value")
    is_secret: bool = Field(False, description="Whether this is a secret (will be encrypted)")
    description: str | None = Field(None, max_length=500, description="Variable description")

    @field_validator("variable_name")
    @classmethod
    def validate_variable_name(cls, v):
        # Use centralized validation for environment variable names
        try:
            return validate_env_var_name(v)
        except InvalidInputError as e:
            raise ValueError(str(e))

    @field_validator("variable_value")
    @classmethod
    def validate_variable_value(cls, v):
        # Sanitize value - strip leading/trailing whitespace
        # Don't allow null bytes or other control characters except tabs and newlines
        if "\x00" in v:
            msg = "Variable value cannot contain null bytes"
            raise ValueError(msg)

        # Check for suspicious patterns that might indicate injection attempts
        suspicious_patterns = ["$(", "`", "${", "\r"]
        for pattern in suspicious_patterns:
            if pattern in v:
                msg = (
                    f"Variable value contains potentially unsafe pattern: '{pattern}'. "
                    "If this is intentional, please escape properly."
                )
                raise ValueError(
                    msg
                )

        return v


class SearchConfigsRequest(BaseModel):
    """Request to search configurations"""
    query: str = Field(..., min_length=1, description="Search query string")
    config_type: str | None = Field(None, description="Filter by type (project, agent, pipeline)")
    project_id: str | None = Field(None, description="Filter by project")
    limit: int = Field(20, ge=1, le=100, description="Maximum results to return")

    @field_validator("config_type")
    @classmethod
    def validate_config_type(cls, v):
        if v and v not in ["project", "agent", "pipeline"]:
            msg = "config_type must be one of: project, agent, pipeline"
            raise ValueError(msg)
        return v


# ============================================================================
# Response DTOs
# ============================================================================


class EnvironmentVariableInfo(BaseModel):
    """Environment variable information"""
    name: str
    value: str  # Masked if secret
    is_secret: bool
    description: str | None


class MountedCommandInfo(BaseModel):
    """Mounted command information"""
    command_name: str
    command_path: str
    description: str | None


class MountedSubAgentInfo(BaseModel):
    """Mounted sub-agent information"""
    subagent_name: str
    config: dict[str, Any]
    description: str | None


class ProjectConfigResponse(BaseModel):
    """Project configuration response"""
    id: str
    name: str
    description: str | None
    github_org: str | None
    github_repo: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    environment_variables: list[EnvironmentVariableInfo]
    mounted_commands: list[MountedCommandInfo]
    mounted_subagents: list[MountedSubAgentInfo]
    metadata: dict[str, Any]


class MCPServerInfo(BaseModel):
    """MCP server configuration"""
    server_name: str
    command: str
    args: list[str]
    env: dict[str, str]


class AgentConfigResponse(BaseModel):
    """Agent configuration response"""
    project_id: str
    agent_name: str
    display_name: str | None
    model: str
    timeout_seconds: int
    max_retries: int
    requires_docker: bool
    requires_dev_container: bool
    makes_code_changes: bool
    filesystem_write_allowed: bool
    version: int
    created_at: datetime
    updated_at: datetime
    mcp_servers: list[MCPServerInfo]
    capabilities: dict[str, Any]
    metadata: dict[str, Any]


class PipelineStageInfo(BaseModel):
    """Pipeline stage information"""
    name: str
    agent_name: str
    timeout_seconds: int
    retry_count: int
    entry_conditions: list[dict[str, Any]]
    metadata: dict[str, Any]


class PipelineConfigResponse(BaseModel):
    """Pipeline configuration response"""
    id: str
    project_id: str
    name: str
    description: str | None
    version: int
    stages: list[PipelineStageInfo]
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any]


class ConfigVersionHistoryItem(BaseModel):
    """Configuration version history entry"""
    version: int
    created_at: datetime
    created_by: str | None
    changes: dict[str, Any]
    reason: str | None


class ConfigVersionHistoryResponse(BaseModel):
    """Configuration version history response"""
    config_id: str
    config_type: str
    current_version: int
    history: list[ConfigVersionHistoryItem]
    total_versions: int


class ConfigSearchResultItem(BaseModel):
    """Configuration search result item"""
    config_id: str
    config_type: str
    name: str
    description: str | None
    matched_fields: list[str]
    score: float


class ConfigSearchResponse(BaseModel):
    """Configuration search response"""
    results: list[ConfigSearchResultItem]
    total_count: int
    query: str
    filters: dict[str, Any]


class ConfigurationCommandResponse(BaseModel):
    """Configuration command result"""
    success: bool
    config_version: int
    message: str
    changes_applied: dict[str, Any]
    errors: list[str] | None = None


class ProjectListResponse(BaseModel):
    """List of projects"""
    projects: list[ProjectConfigResponse]
    total_count: int


class AgentListResponse(BaseModel):
    """List of agents"""
    agents: list[AgentConfigResponse]
    total_count: int


class PipelineListResponse(BaseModel):
    """List of pipelines"""
    pipelines: list[PipelineConfigResponse]
    total_count: int
