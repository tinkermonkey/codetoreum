"""Unit tests for WorkAssignmentService."""

import pytest

from codetoreum.domain.agent import Agent, AgentCapability, AgentType
from codetoreum.domain.exceptions import DomainError
from codetoreum.domain.services.agent_matching_service import AgentMatchingService
from codetoreum.domain.services.work_assignment_service import (
    AssignmentResult,
    WorkAssignmentService,
)
from codetoreum.domain.value_objects import Requirement
from codetoreum.domain.work_item import WorkItem, WorkItemPriority


@pytest.fixture
def work_assignment_service():
    """Create work assignment service."""
    return WorkAssignmentService(AgentMatchingService())


@pytest.fixture
def code_work_item():
    """Create work item that requires code changes."""
    return WorkItem.create(
        title="Implement user authentication",
        description="Add user login and registration",
        project_id="test-project-1",
        priority=WorkItemPriority.HIGH,
        external_id="ISSUE-123",
        external_url="https://github.com/test/repo/issues/123",
    )


@pytest.fixture
def discussion_work_item():
    """Create work item that doesn't require code changes."""
    return WorkItem.create(
        title="Discuss architecture approach",
        description="Evaluate different architecture patterns",
        project_id="test-project-1",
        priority=WorkItemPriority.MEDIUM,
        external_id="ISSUE-456",
        external_url="https://github.com/test/repo/issues/456",
    )


@pytest.fixture
def developer_agent():
    """Create a developer agent that makes code changes."""
    return Agent.create(
        name="developer",
        display_name="Developer Agent",
        agent_type=AgentType.DEVELOPER,
        role_description="Software developer",
        model="claude-sonnet-4-5",
        capabilities={
            "python": AgentCapability("python", 0.9),
            "testing": AgentCapability("testing", 0.8),
        },
        makes_code_changes=True,
    )


@pytest.fixture
def reviewer_agent():
    """Create a reviewer agent that doesn't make code changes."""
    return Agent.create(
        name="reviewer",
        display_name="Code Reviewer",
        agent_type=AgentType.REVIEWER,
        role_description="Code reviewer",
        model="claude-sonnet-4-5",
        capabilities={
            "python": AgentCapability("python", 0.9),
            "code_review": AgentCapability("code_review", 0.95),
        },
        makes_code_changes=False,
    )


@pytest.fixture
def architect_agent():
    """Create an architect agent."""
    return Agent.create(
        name="architect",
        display_name="Software Architect",
        agent_type=AgentType.ARCHITECT,
        role_description="System architect",
        model="claude-sonnet-4-5",
        capabilities={
            "architecture": AgentCapability("architecture", 0.95),
            "python": AgentCapability("python", 0.8),
        },
        makes_code_changes=False,
    )


class TestAssignWork:
    """Tests for assign_work method."""

    def test_successful_assignment(
        self, work_assignment_service, code_work_item, developer_agent
    ):
        """Test successful work assignment."""
        requirements = [
            Requirement("python", 0.8, is_required=True),
        ]

        result = work_assignment_service.assign_work(
            code_work_item, [developer_agent], requirements
        )

        assert isinstance(result, AssignmentResult)
        assert result.agent_id == developer_agent.id
        assert result.match_score > 0.5
        assert "Developer Agent" in result.reason
        assert code_work_item.assigned_agent_id == developer_agent.id

    def test_selects_higher_scoring_agent(
        self,
        work_assignment_service,
        code_work_item,
        developer_agent,
        reviewer_agent,
    ):
        """Test that higher scoring agent is selected."""
        # Reviewer has higher code_review skill but developer has python
        requirements = [
            Requirement("python", 0.8, is_required=True),
        ]

        result = work_assignment_service.assign_work(
            code_work_item, [developer_agent, reviewer_agent], requirements
        )

        # Should assign to developer who has python skill
        assert result.agent_id == developer_agent.id

    def test_allows_non_code_agent_for_discussion_work(
        self,
        work_assignment_service,
        discussion_work_item,
        architect_agent,
    ):
        """Test that non-code agents can be assigned to discussion work."""
        requirements = [
            Requirement("architecture", 0.9, is_required=True),
        ]

        result = work_assignment_service.assign_work(
            discussion_work_item, [architect_agent], requirements
        )

        assert result.agent_id == architect_agent.id
        assert discussion_work_item.assigned_agent_id == architect_agent.id

    def test_raises_error_when_no_agent_meets_requirements(
        self, work_assignment_service, code_work_item
    ):
        """Test error when no agent meets skill requirements."""
        # Create agent without python skill
        non_python_agent = Agent.create(
            name="no_python",
            display_name="Non-Python Agent",
            agent_type=AgentType.SPECIALIZED,
            role_description="Non-Python specialist",
            model="claude-sonnet-4-5",
            capabilities={
                "java": AgentCapability("java", 0.9),
            },
        )

        requirements = [
            Requirement("python", 0.8, is_required=True),  # Required skill agent doesn't have
        ]

        # Agent doesn't have required python skill
        with pytest.raises(DomainError, match="No suitable agent found"):
            work_assignment_service.assign_work(
                code_work_item, [non_python_agent], requirements
            )

    def test_raises_error_when_no_suitable_agent(
        self, work_assignment_service, code_work_item, developer_agent
    ):
        """Test error when no agent meets minimum score."""
        requirements = [
            Requirement("rust", 0.9, is_required=True),  # Developer doesn't have Rust
        ]

        with pytest.raises(DomainError, match="No suitable agent found"):
            work_assignment_service.assign_work(
                code_work_item, [developer_agent], requirements
            )

    def test_custom_minimum_score(
        self, work_assignment_service, code_work_item, developer_agent
    ):
        """Test custom minimum score threshold."""
        requirements = [
            Requirement("python", 0.8, is_required=True),
        ]

        # Should succeed with low min_score
        result = work_assignment_service.assign_work(
            code_work_item, [developer_agent], requirements, min_score=0.3
        )
        assert result.agent_id == developer_agent.id

        # Create junior agent with low score
        junior_agent = Agent.create(
            name="junior",
            display_name="Junior Agent",
            agent_type=AgentType.DEVELOPER,
            role_description="Junior developer",
            model="claude-sonnet-4-5",
            capabilities={
                "python": AgentCapability("python", 0.4),  # Low proficiency
            },
        )

        # Create new work item for second test
        code_work_item2 = WorkItem.create(
            title="Another task",
            description="Test task",
            project_id="test-project-1",
            priority=WorkItemPriority.HIGH,
            external_id="ISSUE-789",
        )

        # Should fail with very high min_score (junior agent has low score of ~0.65)
        with pytest.raises(DomainError, match="No suitable agent found"):
            work_assignment_service.assign_work(
                code_work_item2, [junior_agent], requirements, min_score=0.7
            )

    def test_selects_best_agent_among_multiple(
        self,
        work_assignment_service,
        code_work_item,
        developer_agent,
    ):
        """Test that best agent is selected from multiple candidates."""
        # Create a junior developer with lower scores
        junior_dev = Agent.create(
            name="junior_dev",
            display_name="Junior Developer",
            agent_type=AgentType.DEVELOPER,
            role_description="Junior developer",
            model="claude-sonnet-4-5",
            capabilities={
                "python": AgentCapability("python", 0.5),
            },
            makes_code_changes=True,
        )

        requirements = [
            Requirement("python", 0.8, is_required=True),
        ]

        result = work_assignment_service.assign_work(
            code_work_item, [developer_agent, junior_dev], requirements
        )

        # Should select the senior developer (higher proficiency)
        assert result.agent_id == developer_agent.id

    def test_assignment_reason_includes_skills(
        self, work_assignment_service, code_work_item, developer_agent
    ):
        """Test that assignment reason includes matched skills."""
        requirements = [
            Requirement("python", 0.8, is_required=True),
            Requirement("testing", 0.7, is_required=True),
        ]

        result = work_assignment_service.assign_work(
            code_work_item, [developer_agent], requirements
        )

        assert "python" in result.reason
        assert "testing" in result.reason
        assert "match score" in result.reason

    def test_empty_agent_list_raises_error(
        self, work_assignment_service, code_work_item
    ):
        """Test that empty agent list raises error."""
        requirements = [Requirement("python", 0.8, is_required=True)]

        with pytest.raises(DomainError, match="No capable agents available"):
            work_assignment_service.assign_work(code_work_item, [], requirements)


class TestCanHandleWorkItem:
    """Tests for _can_handle_work_item method."""

    def test_all_agents_can_handle_work_items(
        self, work_assignment_service, code_work_item, developer_agent, reviewer_agent
    ):
        """Test that all agents can handle work items (no filtering)."""
        # Both developer and reviewer can handle work
        assert work_assignment_service._can_handle_work_item(
            developer_agent, code_work_item
        )
        assert work_assignment_service._can_handle_work_item(
            reviewer_agent, code_work_item
        )

    def test_discussion_work_allows_any_agent(
        self,
        work_assignment_service,
        discussion_work_item,
        developer_agent,
        reviewer_agent,
    ):
        """Test that discussion work allows any agent."""
        assert work_assignment_service._can_handle_work_item(
            developer_agent, discussion_work_item
        )
        assert work_assignment_service._can_handle_work_item(
            reviewer_agent, discussion_work_item
        )


class TestGenerateAssignmentReason:
    """Tests for _generate_assignment_reason method."""

    def test_generates_reason_with_matched_skills(
        self, work_assignment_service, developer_agent
    ):
        """Test reason generation with matched skills."""
        requirements = [
            Requirement("python", 0.8, is_required=True),
            Requirement("testing", 0.7, is_required=True),
        ]

        reason = work_assignment_service._generate_assignment_reason(
            developer_agent, 0.92, requirements
        )

        assert "Developer Agent" in reason
        assert "0.92" in reason
        assert "python" in reason
        assert "testing" in reason

    def test_generates_reason_with_no_matched_skills(
        self, work_assignment_service, developer_agent
    ):
        """Test reason generation when no skills match."""
        requirements = [
            Requirement("rust", 0.8, is_required=True),
        ]

        reason = work_assignment_service._generate_assignment_reason(
            developer_agent, 0.0, requirements
        )

        assert "Developer Agent" in reason
        assert "0.00" in reason
        assert "general capabilities" in reason

    def test_generates_reason_with_partial_match(
        self, work_assignment_service, developer_agent
    ):
        """Test reason generation with partial skill match."""
        requirements = [
            Requirement("python", 0.8, is_required=True),
            Requirement("rust", 0.7, is_required=False),  # Not matched
        ]

        reason = work_assignment_service._generate_assignment_reason(
            developer_agent, 0.75, requirements
        )

        assert "python" in reason
        assert "rust" not in reason  # Not matched, so not included
