"""Work assignment service for assigning work items to agents."""

from dataclasses import dataclass

from codetoreum.domain.agent import Agent
from codetoreum.domain.exceptions import DomainError
from codetoreum.domain.services.agent_matching_service import AgentMatchingService
from codetoreum.domain.value_objects import Requirement
from codetoreum.domain.work_item import WorkItem


@dataclass
class AssignmentResult:
    """Result of work assignment."""

    agent_id: str
    match_score: float
    reason: str


class WorkAssignmentService:
    """
    Service for assigning work items to agents.

    Coordinates between WorkItem and Agent aggregates.
    """

    def __init__(self, agent_matching_service: AgentMatchingService):
        """
        Initialize work assignment service.

        Args:
            agent_matching_service: Service for calculating agent match scores
        """
        self.agent_matching = agent_matching_service

    def assign_work(
        self,
        work_item: WorkItem,
        available_agents: list[Agent],
        requirements: list[Requirement],
        min_score: float = 0.5,
    ) -> AssignmentResult:
        """
        Assign work item to best available agent.

        Business logic:
        1. Find agents that can execute in required environment
        2. Calculate match scores for each agent
        3. Select agent with highest score
        4. Assign to work item

        Returns assignment result with agent ID and reasoning.

        Args:
            work_item: Work item to assign
            available_agents: List of available agents
            requirements: List of skill requirements
            min_score: Minimum acceptable match score (default: 0.5)

        Returns:
            Assignment result with agent ID, score, and reasoning

        Raises:
            DomainError: If no capable agents available or no suitable agent found
        """
        # Filter by environment requirements
        capable_agents = [agent for agent in available_agents if self._can_handle_work_item(agent, work_item)]

        if not capable_agents:
            msg = "No capable agents available"
            raise DomainError(msg)

        # Calculate match scores
        best_agent = None
        best_score = 0.0

        for agent in capable_agents:
            score = self.agent_matching.calculate_match_score(agent, requirements)

            if score > best_score:
                best_score = score
                best_agent = agent

        if not best_agent or best_score < min_score:
            msg = f"No suitable agent found (best score: {best_score:.2f}, min required: {min_score:.2f})"
            raise DomainError(msg)

        # Assign to work item
        reason = self._generate_assignment_reason(best_agent, best_score, requirements)
        work_item.assign_agent(best_agent.id, reason)

        return AssignmentResult(agent_id=best_agent.id, match_score=best_score, reason=reason)

    def _can_handle_work_item(self, agent: Agent, work_item: WorkItem) -> bool:
        """
        Check if agent can handle work item.

        Args:
            agent: Agent to check
            work_item: Work item to handle

        Returns:
            True if agent can handle the work item
        """
        # For now, all agents can handle all work items
        # In the future, this could check work item labels or other criteria
        # to determine if agent has required permissions
        return True

    def _generate_assignment_reason(self, agent: Agent, score: float, requirements: list[Requirement]) -> str:
        """
        Generate human-readable assignment reasoning.

        Args:
            agent: Assigned agent
            score: Match score
            requirements: List of requirements

        Returns:
            Human-readable reason for assignment
        """
        matched_skills = [req.skill for req in requirements if agent.has_capability(req.skill, req.min_proficiency)]

        skills_text = ", ".join(matched_skills) if matched_skills else "general capabilities"

        return f"Assigned {agent.display_name} (match score: {score:.2f}) with matching capabilities: {skills_text}"
