"""
Agent Mappers

Converts between domain models and API DTOs for agents.
"""

from codetoreum.adapters.primary.agent_dtos import (
    AgentCommandResult,
    AgentExecutionStatsDTO,
    AgentListResponse,
    AgentResponse,
    AgentSummaryResponse,
    CreateAgentRequest,
    UpdateAgentRequest,
)
from codetoreum.domain.agent import AgentCapability, AgentType
from codetoreum.ports.input.agent_command import (
    AgentCommandResult as PortAgentCommandResult,
)
from codetoreum.ports.input.agent_command import (
    CreateAgentCommand,
    UpdateAgentCommand,
)
from codetoreum.ports.input.agent_query import AgentInfo, AgentListResult


class AgentMapper:
    """Maps between Agent domain models and API DTOs."""

    # Sensitive key patterns that should be masked
    SENSITIVE_PATTERNS = ["key", "token", "secret", "password", "credential", "auth", "api_key"]

    @staticmethod
    def _mask_sensitive_values(env_vars: dict[str, str] | None) -> dict[str, str] | None:
        """
        Mask sensitive environment variable values.

        Args:
            env_vars: Environment variables dict

        Returns:
            Dict with sensitive values masked
        """
        if not env_vars:
            return None

        masked = {}
        for key, value in env_vars.items():
            # Check if key contains sensitive patterns
            key_lower = key.lower()
            is_sensitive = any(pattern in key_lower for pattern in AgentMapper.SENSITIVE_PATTERNS)

            if is_sensitive:
                masked[key] = "***"
            else:
                masked[key] = value

        return masked

    @staticmethod
    def to_response(agent_info: AgentInfo) -> AgentResponse:
        """
        Convert AgentInfo (from port) to AgentResponse DTO.

        Args:
            agent_info: AgentInfo from query port

        Returns:
            AgentResponse DTO
        """
        # Convert execution stats if present
        execution_stats = None
        if agent_info.execution_stats:
            execution_stats = AgentExecutionStatsDTO(
                total_executions=agent_info.execution_stats.total_executions,
                successful_executions=agent_info.execution_stats.successful_executions,
                failed_executions=agent_info.execution_stats.failed_executions,
                timeout_executions=agent_info.execution_stats.timeout_executions,
                average_duration_seconds=agent_info.execution_stats.average_duration_seconds,
                last_execution_at=agent_info.execution_stats.last_execution_at,
            )

        # Mask sensitive environment variable values
        masked_env_vars = AgentMapper._mask_sensitive_values(agent_info.environment_variables)

        return AgentResponse(
            id=agent_info.id,
            name=agent_info.name,
            display_name=agent_info.display_name,
            agent_type=agent_info.agent_type,
            role_description=agent_info.role_description,
            model=agent_info.model,
            timeout_seconds=agent_info.timeout_seconds,
            max_retries=agent_info.max_retries,
            requires_docker=agent_info.requires_docker,
            requires_dev_container=agent_info.requires_dev_container,
            makes_code_changes=agent_info.makes_code_changes,
            filesystem_write_allowed=agent_info.filesystem_write_allowed,
            mcp_servers=agent_info.mcp_servers,
            capabilities=agent_info.capabilities,  # Already dict[str, float]
            environment_variables=masked_env_vars,
            created_at=agent_info.created_at,
            updated_at=agent_info.updated_at,
            execution_stats=execution_stats,
        )

    @staticmethod
    def to_summary_response(agent_info: AgentInfo) -> AgentSummaryResponse:
        """
        Convert AgentInfo to AgentSummaryResponse (for list views).

        Args:
            agent_info: AgentInfo from query port

        Returns:
            AgentSummaryResponse DTO
        """
        # Extract execution stats for counts
        total_execs = 0
        successful_execs = 0
        if agent_info.execution_stats:
            total_execs = agent_info.execution_stats.total_executions
            successful_execs = agent_info.execution_stats.successful_executions

        return AgentSummaryResponse(
            id=agent_info.id,
            name=agent_info.name,
            display_name=agent_info.display_name,
            agent_type=agent_info.agent_type,
            model=agent_info.model,
            capabilities=list(agent_info.capabilities.keys()),  # Just skill names
            total_executions=total_execs,
            successful_executions=successful_execs,
            created_at=agent_info.created_at,
            updated_at=agent_info.updated_at,
        )

    @staticmethod
    def to_list_response(result: AgentListResult) -> AgentListResponse:
        """
        Convert AgentListResult to AgentListResponse DTO.

        Args:
            result: AgentListResult from query port

        Returns:
            AgentListResponse DTO
        """
        agents = [AgentMapper.to_summary_response(agent) for agent in result.agents]

        return AgentListResponse(
            agents=agents,
            total_count=result.total_count,
            offset=result.offset,
            limit=result.limit,
            has_next=result.has_next,
        )

    @staticmethod
    def to_create_command(request: CreateAgentRequest) -> CreateAgentCommand:
        """
        Convert CreateAgentRequest DTO to CreateAgentCommand.

        Args:
            request: CreateAgentRequest DTO

        Returns:
            CreateAgentCommand for port
        """
        # Convert capabilities from DTO to domain model
        capabilities = {}
        for skill, cap_dto in request.capabilities.items():
            capabilities[skill] = AgentCapability(
                skill=cap_dto.skill,
                proficiency=cap_dto.proficiency,
                description=cap_dto.description,
            )

        # Convert agent_type string to enum
        agent_type = AgentType(request.agent_type.lower())

        return CreateAgentCommand(
            name=request.name,
            display_name=request.display_name,
            agent_type=agent_type,
            role_description=request.role_description,
            model=request.model,
            capabilities=capabilities,
            timeout_seconds=request.timeout_seconds,
            max_retries=request.max_retries,
            requires_docker=request.requires_docker,
            requires_dev_container=request.requires_dev_container,
            makes_code_changes=request.makes_code_changes,
            filesystem_write_allowed=request.filesystem_write_allowed,
            mcp_servers=request.mcp_servers,
        )

    @staticmethod
    def to_update_command(agent_id: str, request: UpdateAgentRequest) -> UpdateAgentCommand:
        """
        Convert UpdateAgentRequest DTO to UpdateAgentCommand.

        Args:
            agent_id: Agent ID
            request: UpdateAgentRequest DTO

        Returns:
            UpdateAgentCommand for port
        """
        return UpdateAgentCommand(
            agent_id=agent_id,
            display_name=request.display_name,
            role_description=request.role_description,
            model=request.model,
            timeout_seconds=request.timeout_seconds,
            max_retries=request.max_retries,
            requires_docker=request.requires_docker,
            requires_dev_container=request.requires_dev_container,
            makes_code_changes=request.makes_code_changes,
            filesystem_write_allowed=request.filesystem_write_allowed,
        )

    @staticmethod
    def to_command_result(result: PortAgentCommandResult) -> AgentCommandResult:
        """
        Convert port AgentCommandResult to API AgentCommandResult DTO.

        Args:
            result: AgentCommandResult from port

        Returns:
            AgentCommandResult DTO
        """
        return AgentCommandResult(
            success=result.success,
            agent_id=result.agent_id,
            message=result.message,
            version=result.version,
            errors=result.errors,
        )
