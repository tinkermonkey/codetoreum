"""
Agent Capabilities Endpoints

Provides endpoints for managing agent capabilities.
"""

from fastapi import APIRouter, HTTPException, status

from codetoreum.adapters.primary.agent_dtos import (
    AddCapabilityRequest,
    AgentResponse,
    UpdateCapabilityRequest,
)
from codetoreum.adapters.primary.agent_mappers import AgentMapper
from codetoreum.domain.agent import AgentCapability
from codetoreum.ports.input.agent_command import (
    AddAgentCapabilityCommand,
    IAgentCommandPort,
    RemoveAgentCapabilityCommand,
    UpdateAgentCapabilityCommand,
)
from codetoreum.ports.input.agent_query import IAgentQueryPort


def register_capability_endpoints(
    router: APIRouter,
    command_port: IAgentCommandPort,
    query_port: IAgentQueryPort,
) -> None:
    """
    Register agent capability endpoints on the given router.

    Args:
        router: APIRouter to register endpoints on
        command_port: Agent command port for mutations
        query_port: Agent query port for data access
    """

    @router.post(
        "/{agent_id}/capabilities",
        response_model=AgentResponse,
        summary="Add capability to agent",
        response_description="Updated agent with new capability",
    )
    async def add_capability(
        agent_id: str,
        request: AddCapabilityRequest,
    ) -> AgentResponse:
        """
        Add a new capability to an agent.

        **Parameters:**
        - agent_id: Agent ID

        **Request Body:**
        - capability: Capability to add (skill, proficiency, description)

        **Returns:**
        - 200 OK: Capability added successfully
        - 400 Bad Request: Capability already exists or invalid proficiency
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Agent not found
        """
        try:
            # Convert DTO to domain model
            capability = AgentCapability(
                skill=request.capability.skill,
                proficiency=request.capability.proficiency,
                description=request.capability.description,
            )

            command = AddAgentCapabilityCommand(
                agent_id=agent_id,
                capability=capability,
            )

            # Execute command via port
            agent = await command_port.add_capability(command)

            # Retrieve updated agent
            agent_info = await query_port.get_agent(agent.id, include_stats=True)

            return AgentMapper.to_response(agent_info)

        except (ValueError, KeyError, AttributeError) as e:
            if "not found" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Agent not found: {str(e)}",
                )
            elif "already" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Capability already exists: {str(e)}",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to add capability: {str(e)}",
            )

    @router.delete(
        "/{agent_id}/capabilities/{skill}",
        response_model=AgentResponse,
        summary="Remove capability from agent",
        response_description="Updated agent without removed capability",
    )
    async def remove_capability(
        agent_id: str,
        skill: str,
    ) -> AgentResponse:
        """
        Remove a capability from an agent.

        **Parameters:**
        - agent_id: Agent ID
        - skill: Skill name to remove

        **Returns:**
        - 200 OK: Capability removed successfully
        - 400 Bad Request: Capability not found or it's the last capability
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Agent not found

        **Note:** Cannot remove the last capability from an agent.
        """
        try:
            command = RemoveAgentCapabilityCommand(
                agent_id=agent_id,
                skill=skill,
            )

            # Execute command via port
            agent = await command_port.remove_capability(command)

            # Retrieve updated agent
            agent_info = await query_port.get_agent(agent.id, include_stats=True)

            return AgentMapper.to_response(agent_info)

        except (ValueError, KeyError, AttributeError) as e:
            if "not found" in str(e).lower():
                if "agent" in str(e).lower():
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Agent not found: {str(e)}",
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Capability not found: {str(e)}",
                    )
            elif "last capability" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot remove last capability from agent",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to remove capability: {str(e)}",
            )

    @router.patch(
        "/{agent_id}/capabilities/{skill}",
        response_model=AgentResponse,
        summary="Update capability proficiency",
        response_description="Updated agent with modified capability",
    )
    async def update_capability(
        agent_id: str,
        skill: str,
        request: UpdateCapabilityRequest,
    ) -> AgentResponse:
        """
        Update the proficiency level of an agent's capability.

        **Parameters:**
        - agent_id: Agent ID
        - skill: Skill name to update

        **Request Body:**
        - proficiency: New proficiency level (0.0 to 1.0)

        **Returns:**
        - 200 OK: Proficiency updated successfully
        - 400 Bad Request: Capability not found or invalid proficiency
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Agent not found
        """
        try:
            command = UpdateAgentCapabilityCommand(
                agent_id=agent_id,
                skill=skill,
                proficiency=request.proficiency,
            )

            # Execute command via port
            agent = await command_port.update_capability(command)

            # Retrieve updated agent
            agent_info = await query_port.get_agent(agent.id, include_stats=True)

            return AgentMapper.to_response(agent_info)

        except (ValueError, KeyError, AttributeError) as e:
            if "not found" in str(e).lower():
                if "agent" in str(e).lower():
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Agent not found: {str(e)}",
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Capability not found: {str(e)}",
                    )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to update capability: {str(e)}",
            )
