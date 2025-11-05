"""
Configuration Management DTOs

Data Transfer Objects for configuration management API endpoints.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from codetoreum.infrastructure.security import validate_env_var_name, InvalidInputError


# ============================================================================
# Request DTOs
# ============================================================================


class UpdateProjectConfigRequest(BaseModel):
    """Request to update project configuration"""
    updates: Dict[str, Any] = Field(..., description="Partial configuration updates")
    reason: Optional[str] = Field(None, description="Reason for update (for audit trail)")

    @field_validator("updates")
    @classmethod
    def validate_updates(cls, v):
        if not v:
            raise ValueError("Updates cannot be empty")
        return v


class UpdateAgentConfigRequest(BaseModel):
    """Request to update agent configuration"""
    updates: Dict[str, Any] = Field(..., description="Partial agent configuration updates")
    reason: Optional[str] = Field(None, description="Reason for update")

    @field_validator("updates")
    @classmethod
    def validate_updates(cls, v):
        if not v:
            raise ValueError("Updates cannot be empty")
        return v


class UpdatePipelineConfigRequest(BaseModel):
    """Request to update pipeline configuration"""
    updates: Dict[str, Any] = Field(..., description="Partial pipeline configuration updates")
    reason: Optional[str] = Field(None, description="Reason for update")

    @field_validator("updates")
    @classmethod
    def validate_updates(cls, v):
        if not v:
            raise ValueError("Updates cannot be empty")
        return v


class AddEnvironmentVariableRequest(BaseModel):
    """Request to add/update environment variable"""
    variable_name: str = Field(..., min_length=1, max_length=255, description="Variable name")
    variable_value: str = Field(..., max_length=10000, description="Variable value")  # Added max length
    is_secret: bool = Field(False, description="Whether this is a secret (will be encrypted)")
    description: Optional[str] = Field(None, max_length=500, description="Variable description")

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
        if '\x00' in v:
            raise ValueError("Variable value cannot contain null bytes")

        # Check for suspicious patterns that might indicate injection attempts
        suspicious_patterns = ['$(', '`', '${', '\r']
        for pattern in suspicious_patterns:
            if pattern in v:
                raise ValueError(
                    f"Variable value contains potentially unsafe pattern: '{pattern}'. "
                    "If this is intentional, please escape properly."
                )

        return v


class SearchConfigsRequest(BaseModel):
    """Request to search configurations"""
    query: str = Field(..., min_length=1, description="Search query string")
    config_type: Optional[str] = Field(None, description="Filter by type (project, agent, pipeline)")
    project_id: Optional[str] = Field(None, description="Filter by project")
    limit: int = Field(20, ge=1, le=100, description="Maximum results to return")

    @field_validator("config_type")
    @classmethod
    def validate_config_type(cls, v):
        if v and v not in ["project", "agent", "pipeline"]:
            raise ValueError("config_type must be one of: project, agent, pipeline")
        return v


# ============================================================================
# Response DTOs
# ============================================================================


class EnvironmentVariableInfo(BaseModel):
    """Environment variable information"""
    name: str
    value: str  # Masked if secret
    is_secret: bool
    description: Optional[str]


class MountedCommandInfo(BaseModel):
    """Mounted command information"""
    command_name: str
    command_path: str
    description: Optional[str]


class MountedSubAgentInfo(BaseModel):
    """Mounted sub-agent information"""
    subagent_name: str
    config: Dict[str, Any]
    description: Optional[str]


class ProjectConfigResponse(BaseModel):
    """Project configuration response"""
    id: str
    name: str
    description: Optional[str]
    github_org: Optional[str]
    github_repo: Optional[str]
    version: int
    created_at: datetime
    updated_at: datetime
    environment_variables: List[EnvironmentVariableInfo]
    mounted_commands: List[MountedCommandInfo]
    mounted_subagents: List[MountedSubAgentInfo]
    metadata: Dict[str, Any]


class MCPServerInfo(BaseModel):
    """MCP server configuration"""
    server_name: str
    command: str
    args: List[str]
    env: Dict[str, str]


class AgentConfigResponse(BaseModel):
    """Agent configuration response"""
    project_id: str
    agent_name: str
    display_name: Optional[str]
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
    mcp_servers: List[MCPServerInfo]
    capabilities: Dict[str, Any]
    metadata: Dict[str, Any]


class PipelineStageInfo(BaseModel):
    """Pipeline stage information"""
    name: str
    agent_name: str
    timeout_seconds: int
    retry_count: int
    entry_conditions: List[Dict[str, Any]]
    metadata: Dict[str, Any]


class PipelineConfigResponse(BaseModel):
    """Pipeline configuration response"""
    id: str
    project_id: str
    name: str
    description: Optional[str]
    version: int
    stages: List[PipelineStageInfo]
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any]


class ConfigVersionHistoryItem(BaseModel):
    """Configuration version history entry"""
    version: int
    created_at: datetime
    created_by: Optional[str]
    changes: Dict[str, Any]
    reason: Optional[str]


class ConfigVersionHistoryResponse(BaseModel):
    """Configuration version history response"""
    config_id: str
    config_type: str
    current_version: int
    history: List[ConfigVersionHistoryItem]
    total_versions: int


class ConfigSearchResultItem(BaseModel):
    """Configuration search result item"""
    config_id: str
    config_type: str
    name: str
    description: Optional[str]
    matched_fields: List[str]
    score: float


class ConfigSearchResponse(BaseModel):
    """Configuration search response"""
    results: List[ConfigSearchResultItem]
    total_count: int
    query: str
    filters: Dict[str, Any]


class ConfigurationCommandResponse(BaseModel):
    """Configuration command result"""
    success: bool
    config_version: int
    message: str
    changes_applied: Dict[str, Any]
    errors: Optional[List[str]] = None


class ProjectListResponse(BaseModel):
    """List of projects"""
    projects: List[ProjectConfigResponse]
    total_count: int


class AgentListResponse(BaseModel):
    """List of agents"""
    agents: List[AgentConfigResponse]
    total_count: int


class PipelineListResponse(BaseModel):
    """List of pipelines"""
    pipelines: List[PipelineConfigResponse]
    total_count: int
