"""Unit tests for AgentMatchingService."""

import pytest

from codetoreum.domain.agent import Agent, AgentCapability, AgentType
from codetoreum.domain.coding_agent_types import AgentInvocationConfig, InvocationMode
from codetoreum.domain.services.agent_matching_service import AgentMatchingService
from codetoreum.domain.value_objects import Requirement


def _test_inv(
    model: str = "claude-sonnet-4-5",
    timeout_seconds: int = 300,
    requires_docker: bool = True,
) -> AgentInvocationConfig:
    """Build an AgentInvocationConfig for tests (DEF-020 transitional helper)."""
    return AgentInvocationConfig(
        mode=InvocationMode.CONTAINERIZED if requires_docker else InvocationMode.HOST,
        model=model,
        timeout_seconds=timeout_seconds,
        mode_config={"image": "codetoreum-agent:latest"} if requires_docker else {},
    )


@pytest.fixture
def senior_engineer_agent():
    """Create a senior engineer agent."""
    return Agent.create(
        name="senior_engineer",
        display_name="Senior Engineer",
        agent_type=AgentType.MAKER,
        role_description="Experienced software engineer",
        capabilities={
            "python": AgentCapability("python", 0.9, "Expert Python programmer"),
            "testing": AgentCapability("testing", 0.8, "Strong testing skills"),
            "debugging": AgentCapability("debugging", 0.85, "Excellent debugger"),
        },
        invocation=_test_inv(model="claude-sonnet-4-5", timeout_seconds=300, requires_docker=True),
    )


@pytest.fixture
def junior_developer_agent():
    """Create a junior developer agent."""
    return Agent.create(
        name="junior_dev",
        display_name="Junior Developer",
        agent_type=AgentType.MAKER,
        role_description="Entry-level developer",
        capabilities={
            "python": AgentCapability("python", 0.5, "Basic Python knowledge"),
            "testing": AgentCapability("testing", 0.4, "Limited testing experience"),
        },
        invocation=_test_inv(model="claude-sonnet-4-5", timeout_seconds=300, requires_docker=True),
    )


@pytest.fixture
def specialized_agent():
    """Create a specialized agent."""
    return Agent.create(
        name="devops_specialist",
        display_name="DevOps Specialist",
        agent_type=AgentType.SPECIALIZED,
        role_description="Infrastructure and deployment expert",
        capabilities={
            "docker": AgentCapability("docker", 0.95, "Docker expert"),
            "kubernetes": AgentCapability("kubernetes", 0.9, "Kubernetes expert"),
            "ci_cd": AgentCapability("ci_cd", 0.85, "CI/CD expert"),
        },
        invocation=_test_inv(model="claude-sonnet-4-5", timeout_seconds=300, requires_docker=True),
    )


class TestCalculateMatchScore:
    """Tests for calculate_match_score method."""

    def test_perfect_match(self, senior_engineer_agent):
        """Test perfect match when agent exceeds all requirements."""
        requirements = [
            Requirement("python", 0.8, is_required=True),
            Requirement("testing", 0.7, is_required=True),
        ]

        score = AgentMatchingService.calculate_match_score(senior_engineer_agent, requirements)

        assert score > 0.9, "Should have very high score for perfect match"

    def test_no_requirements_returns_one(self, senior_engineer_agent):
        """Test that no requirements returns score of 1.0."""
        score = AgentMatchingService.calculate_match_score(senior_engineer_agent, [])
        assert score == 1.0

    def test_missing_required_skill_returns_zero(self, senior_engineer_agent):
        """Test that missing required skill returns 0.0."""
        requirements = [
            Requirement("python", 0.8, is_required=True),
            Requirement("rust", 0.7, is_required=True),  # Missing
        ]

        score = AgentMatchingService.calculate_match_score(senior_engineer_agent, requirements)

        assert score == 0.0, "Should return 0.0 when required skill is missing"

    def test_missing_optional_skill_not_zero(self, senior_engineer_agent):
        """Test that missing optional skill does not return 0.0."""
        requirements = [
            Requirement("python", 0.8, is_required=True),
            Requirement("rust", 0.7, is_required=False),  # Missing but optional
        ]

        score = AgentMatchingService.calculate_match_score(senior_engineer_agent, requirements)

        assert score > 0.0, "Should not return 0.0 when only optional skill is missing"
        assert score < 1.0, "Score should be reduced due to missing optional skill"

    def test_insufficient_proficiency_for_required_skill(self, junior_developer_agent):
        """Test that insufficient proficiency for required skill lowers score."""
        requirements = [
            Requirement("python", 0.8, is_required=True),  # Junior has 0.5
        ]

        score = AgentMatchingService.calculate_match_score(junior_developer_agent, requirements)

        # Score should be (0.5/0.8 = 0.625) * 0.7 (weight) + 1.0 * 0.3 = 0.7375
        assert 0.7 <= score <= 0.8, "Score should reflect insufficient proficiency"

    def test_weighted_average_required_vs_optional(self, senior_engineer_agent):
        """Test that required skills are weighted more heavily (70/30)."""
        # All required
        requirements_all_required = [
            Requirement("python", 0.8, is_required=True),
            Requirement("testing", 0.7, is_required=True),
        ]

        # Mixed required/optional
        requirements_mixed = [
            Requirement("python", 0.8, is_required=True),
            Requirement("debugging", 0.0, is_required=False),  # Perfect optional
        ]

        score_all_required = AgentMatchingService.calculate_match_score(
            senior_engineer_agent, requirements_all_required
        )
        score_mixed = AgentMatchingService.calculate_match_score(senior_engineer_agent, requirements_mixed)

        # Both should be high but different due to weighting
        assert score_all_required > 0.9
        assert score_mixed > 0.9

    def test_multiple_optional_skills(self, senior_engineer_agent):
        """Test scoring with multiple optional skills."""
        requirements = [
            Requirement("python", 0.8, is_required=True),
            Requirement("testing", 0.7, is_required=False),
            Requirement("debugging", 0.7, is_required=False),
        ]

        score = AgentMatchingService.calculate_match_score(senior_engineer_agent, requirements)

        assert score > 0.9, "Should have high score with all skills present"

    def test_no_match_specialist_vs_developer_requirements(self, specialized_agent):
        """Test that specialist agent gets zero score for developer requirements."""
        requirements = [
            Requirement("python", 0.7, is_required=True),  # DevOps doesn't have Python
        ]

        score = AgentMatchingService.calculate_match_score(specialized_agent, requirements)

        assert score == 0.0, "Should return 0.0 for completely unmatched required skills"


class TestFindBestMatch:
    """Tests for find_best_match method."""

    def test_finds_best_agent(self, senior_engineer_agent, junior_developer_agent):
        """Test that find_best_match selects the agent with highest score."""
        requirements = [
            Requirement("python", 0.8, is_required=True),
            Requirement("testing", 0.7, is_required=True),
        ]

        best_agent = AgentMatchingService.find_best_match([senior_engineer_agent, junior_developer_agent], requirements)

        assert best_agent == senior_engineer_agent

    def test_returns_none_below_min_score(self, junior_developer_agent):
        """Test that find_best_match returns None if no agent meets min score."""
        requirements = [
            Requirement("python", 0.9, is_required=True),  # Junior only has 0.5
        ]

        best_agent = AgentMatchingService.find_best_match([junior_developer_agent], requirements, min_score=0.8)

        assert best_agent is None

    def test_returns_none_for_empty_agent_list(self):
        """Test that find_best_match returns None for empty agent list."""
        requirements = [Requirement("python", 0.8, is_required=True)]

        best_agent = AgentMatchingService.find_best_match([], requirements)

        assert best_agent is None

    def test_finds_agent_with_exact_min_score(self, senior_engineer_agent):
        """Test that agent with exact min score is returned."""
        requirements = [Requirement("python", 0.8, is_required=True)]

        best_agent = AgentMatchingService.find_best_match([senior_engineer_agent], requirements, min_score=0.5)

        assert best_agent == senior_engineer_agent

    def test_specialist_vs_generalist(self, specialized_agent, senior_engineer_agent):
        """Test that specialist beats generalist for specialist requirements."""
        requirements = [
            Requirement("docker", 0.8, is_required=True),
            Requirement("kubernetes", 0.7, is_required=True),
        ]

        best_agent = AgentMatchingService.find_best_match([specialized_agent, senior_engineer_agent], requirements)

        assert best_agent == specialized_agent


class TestRankAgents:
    """Tests for rank_agents method."""

    def test_ranks_agents_by_score(self, senior_engineer_agent, junior_developer_agent, specialized_agent):
        """Test that rank_agents returns agents sorted by score descending."""
        requirements = [
            Requirement("python", 0.8, is_required=True),
            Requirement("testing", 0.7, is_required=True),
        ]

        ranked = AgentMatchingService.rank_agents(
            [junior_developer_agent, senior_engineer_agent, specialized_agent],
            requirements,
        )

        # Should be: senior (high score), junior (low score), specialist (0.0)
        assert len(ranked) == 3
        assert ranked[0][0] == senior_engineer_agent
        assert ranked[1][0] == junior_developer_agent
        assert ranked[2][0] == specialized_agent
        assert ranked[2][1] == 0.0  # Specialist has no Python skills

    def test_rank_empty_list_returns_empty(self):
        """Test that ranking empty list returns empty list."""
        requirements = [Requirement("python", 0.8, is_required=True)]

        ranked = AgentMatchingService.rank_agents([], requirements)

        assert ranked == []

    def test_rank_preserves_all_agents(self, senior_engineer_agent, junior_developer_agent):
        """Test that all agents are included in ranking."""
        requirements = [Requirement("python", 0.8, is_required=True)]

        ranked = AgentMatchingService.rank_agents([senior_engineer_agent, junior_developer_agent], requirements)

        assert len(ranked) == 2
        assert all(isinstance(item, tuple) and len(item) == 2 for item in ranked)

    def test_rank_includes_scores(self, senior_engineer_agent, junior_developer_agent):
        """Test that ranking includes scores."""
        requirements = [Requirement("python", 0.8, is_required=True)]

        ranked = AgentMatchingService.rank_agents([senior_engineer_agent, junior_developer_agent], requirements)

        # Verify scores are present and valid
        assert all(0.0 <= score <= 1.0 for _, score in ranked)
        # Senior should have higher score
        assert ranked[0][1] > ranked[1][1]
