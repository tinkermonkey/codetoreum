"""Agent matching service for calculating agent-requirement match scores."""

from typing import List, Optional

from codetoreum.domain.agent import Agent
from codetoreum.domain.value_objects import Requirement


class AgentMatchingService:
    """
    Service for matching agents to requirements.

    Pure calculation service with no side effects.
    """

    @staticmethod
    def calculate_match_score(agent: Agent, requirements: List[Requirement]) -> float:
        """
        Calculate match score between agent and requirements.

        Returns score from 0.0 (no match) to 1.0 (perfect match).

        Algorithm:
        1. For each requirement, calculate capability ratio
        2. Required skills must be present (0.0 if missing)
        3. Optional skills contribute to score
        4. Average all scores with weighted average (70% required, 30% optional)

        Args:
            agent: Agent to evaluate
            requirements: List of skill requirements

        Returns:
            Match score from 0.0 to 1.0
        """
        if not requirements:
            return 1.0

        required_scores = []
        optional_scores = []

        for requirement in requirements:
            if agent.has_capability(requirement.skill):
                capability_score = agent.get_capability_score(requirement.skill)

                # Handle edge case where min_proficiency is 0.0
                if requirement.min_proficiency == 0.0:
                    requirement_ratio = 1.0  # Any proficiency satisfies 0.0 requirement
                else:
                    requirement_ratio = min(
                        capability_score / requirement.min_proficiency, 1.0
                    )

                if requirement.is_required:
                    required_scores.append(requirement_ratio)
                else:
                    optional_scores.append(requirement_ratio)
            else:
                # Missing capability
                if requirement.is_required:
                    return 0.0  # Cannot satisfy required skill
                else:
                    optional_scores.append(0.0)

        # Calculate weighted average
        if not required_scores:
            required_scores = [1.0]  # No required skills

        required_avg = sum(required_scores) / len(required_scores)
        optional_avg = (
            sum(optional_scores) / len(optional_scores) if optional_scores else 1.0
        )

        # Weight required skills more heavily (70/30)
        return 0.7 * required_avg + 0.3 * optional_avg

    @staticmethod
    def find_best_match(
        agents: List[Agent],
        requirements: List[Requirement],
        min_score: float = 0.5,
    ) -> Optional[Agent]:
        """
        Find agent with highest match score above threshold.

        Returns None if no agent meets minimum score.

        Args:
            agents: List of agents to evaluate
            requirements: List of skill requirements
            min_score: Minimum acceptable score (default: 0.5)

        Returns:
            Best matching agent or None
        """
        if not agents:
            return None

        best_agent = None
        best_score = 0.0

        for agent in agents:
            score = AgentMatchingService.calculate_match_score(agent, requirements)

            if score > best_score:
                best_score = score
                best_agent = agent

        return best_agent if best_score >= min_score else None

    @staticmethod
    def rank_agents(
        agents: List[Agent], requirements: List[Requirement]
    ) -> List[tuple[Agent, float]]:
        """
        Rank all agents by match score.

        Returns list of (agent, score) tuples sorted by score descending.

        Args:
            agents: List of agents to rank
            requirements: List of skill requirements

        Returns:
            List of (agent, score) tuples sorted by score (highest first)
        """
        scored_agents = [
            (agent, AgentMatchingService.calculate_match_score(agent, requirements))
            for agent in agents
        ]

        return sorted(scored_agents, key=lambda x: x[1], reverse=True)
