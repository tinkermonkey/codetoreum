"""
Agent CRUD Endpoints

Provides endpoints for creating, updating, and deleting agents.
"""

from fastapi import APIRouter, HTTPException, status

from codetoreum.adapters.primary.agent_dtos import (
    AgentCommandResult,
    AgentResponse,
    CreateAgentRequest,
    UpdateAgentRequest,
)
from codetoreum.adapters.primary.agent_mappers import AgentMapper
from codetoreum.infrastructure.audit import AuditEventType, get_audit_logger
from codetoreum.ports.input.agent_command import IAgentCommandPort
from codetoreum.ports.input.agent_query import IAgentQueryPort


def register_crud_endpoints(
    router: APIRouter,
    command_port: IAgentCommandPort,
    query_port: IAgentQueryPort,
) -> None:
    """
    Register agent CRUD endpoints on the given router.

    Args:
        router: APIRouter to register endpoints on
        command_port: Agent command port for mutations
        query_port: Agent query port for data access
    """

    @router.post(
        "",
        response_model=AgentResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Create a new agent",
        response_description="Created agent",
        responses={
            201: {"description": "Agent created successfully"},
            400: {"description": "Bad Request - Invalid parameters or agent already exists", "content": {"application/json": {"example": {"detail": "Agent with name 'test-agent' already exists"}}}},
            401: {"description": "Unauthorized - Authentication required", "content": {"application/json": {"example": {"detail": "Not authenticated"}}}},
        },
    )
    async def create_agent(request: CreateAgentRequest) -> AgentResponse:
        """
        Create a new agent definition.

        **Request Body:**
        - name: Agent name/identifier (required, lowercase alphanumeric + underscore)
        - display_name: Human-readable name (required)
        - agent_type: Type of agent (maker, reviewer, specialized, etc.)
        - role_description: Description of agent's role (required)
        - model: LLM model to use (required)
        - capabilities: Dictionary of skills with proficiency levels (required)
        - timeout_seconds: Execution timeout (default: 300, max: 7200)
        - max_retries: Maximum retries (default: 3, max: 10)
        - requires_docker: Docker requirement (default: true)
        - requires_dev_container: Dev container requirement (default: false)
        - makes_code_changes: Whether agent modifies code (default: false)
        - filesystem_write_allowed: Filesystem write permission (default: true)
        - mcp_servers: Optional list of MCP server names

        **Returns:**
        - 201 Created: Agent created successfully
        - 400 Bad Request: Invalid request parameters or agent name already exists
        - 401 Unauthorized: Authentication required

        **Validation:**
        - Agent name must be unique
        - At least one capability required
        - Proficiency levels must be between 0.0 and 1.0
        """
        audit_logger = get_audit_logger()

        try:
            # Convert DTO to command
            command = AgentMapper.to_create_command(request)

            # Execute command via port
            agent = await command_port.create_agent(command)

            # Retrieve created agent with stats
            agent_info = await query_port.get_agent(agent.id, include_stats=True)

            # Log successful agent creation
            audit_logger.log_agent_created(
                agent_id=agent.id,
                user_id="api-user",
                metadata={
                    "agent_name": request.name,
                    "display_name": request.display_name,
                    "agent_type": str(request.agent_type),
                    "model": request.model,
                    "capabilities": list(request.capabilities.keys()),
                },
            )

            # Convert to response DTO
            return AgentMapper.to_response(agent_info)

        except (ValueError, KeyError, AttributeError) as e:
            # Log failed agent creation
            audit_logger.log_event(
                event_type=AuditEventType.AGENT_CREATION_FAILED,
                resource_type="agent",
                resource_id=request.name,
                action="create",
                user_id="api-user",
                success=False,
                error_message=str(e),
                metadata={"agent_name": request.name},
            )

            # Invalid enum values or validation errors
            if "already exists" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Agent with name '{request.name}' already exists",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request: {e!s}",
            )

    @router.put(
        "/{agent_id}",
        response_model=AgentResponse,
        summary="Update agent configuration",
        response_description="Updated agent",
    )
    async def update_agent(
        agent_id: str,
        request: UpdateAgentRequest,
    ) -> AgentResponse:
        """
        Update an existing agent's configuration.

        **Parameters:**
        - agent_id: Agent ID

        **Request Body:**
        - display_name: Updated display name (optional)
        - role_description: Updated role description (optional)
        - model: Updated LLM model (optional)
        - timeout_seconds: Updated timeout (optional, max: 7200)
        - max_retries: Updated max retries (optional, max: 10)
        - requires_docker: Updated Docker requirement (optional)
        - requires_dev_container: Updated dev container requirement (optional)
        - makes_code_changes: Updated code changes flag (optional)
        - filesystem_write_allowed: Updated filesystem write permission (optional)

        **Returns:**
        - 200 OK: Agent updated successfully
        - 400 Bad Request: Invalid request parameters
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Agent not found

        **Note:**
        - Only provided fields will be updated
        - Emits domain event for audit trail
        - Increments agent version
        """
        audit_logger = get_audit_logger()

        try:
            # Convert DTO to command
            command = AgentMapper.to_update_command(agent_id, request)

            # Execute command via port
            agent = await command_port.update_agent(command)

            # Retrieve updated agent with stats
            agent_info = await query_port.get_agent(agent.id, include_stats=True)

            # Build changes dict for audit log
            changes = {}
            if request.display_name is not None:
                changes["display_name"] = request.display_name
            if request.role_description is not None:
                changes["role_description"] = request.role_description
            if request.model is not None:
                changes["model"] = request.model
            if request.timeout_seconds is not None:
                changes["timeout_seconds"] = request.timeout_seconds
            if request.max_retries is not None:
                changes["max_retries"] = request.max_retries

            # Log successful agent update
            audit_logger.log_agent_updated(
                agent_id=agent_id,
                user_id="api-user",
                changes=changes,
            )

            # Convert to response DTO
            return AgentMapper.to_response(agent_info)

        except (ValueError, KeyError, AttributeError) as e:
            # Log failed agent update
            audit_logger.log_event(
                event_type=AuditEventType.AGENT_UPDATE_FAILED,
                resource_type="agent",
                resource_id=agent_id,
                action="update",
                user_id="api-user",
                success=False,
                error_message=str(e),
            )

            # Invalid enum values, validation errors, or domain errors
            if "not found" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Agent not found: {e!s}",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to update agent: {e!s}",
            )

    @router.delete(
        "/{agent_id}",
        response_model=AgentCommandResult,
        summary="Delete agent (soft delete)",
        response_description="Deletion result",
    )
    async def delete_agent(agent_id: str) -> AgentCommandResult:
        """
        Delete an agent (soft delete).

        **Parameters:**
        - agent_id: Agent ID

        **Returns:**
        - 200 OK: Agent deleted successfully
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Agent not found

        **Note:**
        - This is a soft delete - agent is marked as deleted but preserved in event store
        - Agent will not appear in list queries after deletion
        - Event history is preserved for audit trail
        """
        audit_logger = get_audit_logger()

        try:
            # Execute command via port
            result = await command_port.delete_agent(agent_id)

            # Log successful agent deletion
            audit_logger.log_agent_deleted(
                agent_id=agent_id,
                user_id="api-user",
                success=True,
            )

            # Convert to response DTO
            return AgentMapper.to_command_result(result)

        except (ValueError, KeyError, AttributeError) as e:
            # Log failed agent deletion
            audit_logger.log_agent_deleted(
                agent_id=agent_id,
                user_id="api-user",
                success=False,
                error_message=str(e),
            )

            if "not found" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Agent not found: {e!s}",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to delete agent: {e!s}",
            )
