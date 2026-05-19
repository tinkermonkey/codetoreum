"""Unit tests for PromptBuilder application service."""

from datetime import UTC, datetime

import pytest

from codetoreum.application.prompt_builder import PromptBuilder
from codetoreum.domain.agent import Agent, AgentCapability, AgentType
from codetoreum.domain.board_workflow_template import BoardWorkflowTemplate, ColumnTemplate, ColumnType
from codetoreum.domain.value_objects import CommitPolicy
from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus


@pytest.fixture
def sample_agent() -> Agent:
    """Create a sample agent for testing."""
    return Agent.create(
        name="test-agent",
        display_name="Test Agent",
        agent_type=AgentType.DEVELOPER,
        role_description="A test agent for development tasks.",
        model="claude-opus-4-7",
        capabilities={
            "python": AgentCapability("python", 0.9, "Expert in Python development"),
            "testing": AgentCapability("testing", 0.8, "Strong testing practices"),
        },
        temperature=0.7,
        max_tokens=4096,
        system_prompt="You are a senior software engineer focused on clean code and best practices.",
        timeout_seconds=3600,
        max_retries=3,
        requires_docker=True,
        requires_dev_container=False,
        makes_code_changes=True,
        filesystem_write_allowed=True,
        mcp_servers=["github", "filesystem"],
        commit_policy=CommitPolicy.ON_SUCCESS,
    )


@pytest.fixture
def sample_work_item() -> WorkItem:
    """Create a sample work item for testing."""
    return WorkItem.create(
        title="Implement user authentication",
        description=(
            "Implement OAuth2 authentication for the user management system.\n\n"
            "This should support:\n"
            "- GitHub OAuth\n"
            "- Google OAuth\n"
            "- Local username/password"
        ),
        project_id="proj-123",
        labels=["authentication", "security", "backend"],
        priority=WorkItemPriority.HIGH,
        external_id="123",
        external_url="https://github.com/example/repo/issues/123",
    )


@pytest.fixture
def sample_workflow_template() -> BoardWorkflowTemplate:
    """Create a sample workflow template."""
    columns = [
        ColumnTemplate(
            name="Backlog",
            type=ColumnType.MANUAL,
            agent_id=None,
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=0,
            auto_progress_on_completion=False,
        ),
        ColumnTemplate(
            name="In Development",
            type=ColumnType.AUTOMATED,
            agent_id="agent-dev",
            is_pipeline_trigger=True,
            is_exit_column=False,
            position=1,
            auto_progress_on_completion=True,
            execution_type="task_queue",
        ),
        ColumnTemplate(
            name="Code Review",
            type=ColumnType.MANUAL,
            agent_id=None,
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=2,
            auto_progress_on_completion=False,
        ),
        ColumnTemplate(
            name="Done",
            type=ColumnType.MANUAL,
            agent_id=None,
            is_pipeline_trigger=False,
            is_exit_column=True,
            position=3,
            auto_progress_on_completion=False,
        ),
    ]

    return BoardWorkflowTemplate(
        id="template-1",
        board_id="board-1",
        project_id="proj-123",
        name="Standard SDLC",
        columns=tuple(columns),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


class TestPromptBuilderBasic:
    """Test basic prompt building functionality."""

    def test_build_prompt_includes_agent_system_prompt(self, sample_agent: Agent, sample_work_item: WorkItem) -> None:
        """Verify agent system prompt is included in the prompt."""
        prompt = PromptBuilder.build_prompt(
            work_item=sample_work_item,
            agent=sample_agent,
            stage_name="In Development",
        )

        assert "System Prompt" in prompt
        assert sample_agent.system_prompt in prompt

    def test_build_prompt_includes_agent_role_description(
        self, sample_agent: Agent, sample_work_item: WorkItem
    ) -> None:
        """Verify agent role description is included."""
        prompt = PromptBuilder.build_prompt(
            work_item=sample_work_item,
            agent=sample_agent,
            stage_name="In Development",
        )

        assert "Your Role" in prompt
        assert sample_agent.role_description in prompt
        assert sample_agent.display_name in prompt

    def test_build_prompt_includes_agent_capabilities(self, sample_agent: Agent, sample_work_item: WorkItem) -> None:
        """Verify agent capabilities are listed."""
        prompt = PromptBuilder.build_prompt(
            work_item=sample_work_item,
            agent=sample_agent,
            stage_name="In Development",
        )

        assert "Capabilities" in prompt
        assert "python" in prompt
        assert "testing" in prompt
        assert "90% proficiency" in prompt  # 0.9 * 100

    def test_build_prompt_includes_work_item_title(self, sample_agent: Agent, sample_work_item: WorkItem) -> None:
        """Verify work item title is included."""
        prompt = PromptBuilder.build_prompt(
            work_item=sample_work_item,
            agent=sample_agent,
            stage_name="In Development",
        )

        assert "Work Item" in prompt
        assert sample_work_item.title in prompt

    def test_build_prompt_includes_work_item_description(self, sample_agent: Agent, sample_work_item: WorkItem) -> None:
        """Verify work item description is included."""
        prompt = PromptBuilder.build_prompt(
            work_item=sample_work_item,
            agent=sample_agent,
            stage_name="In Development",
        )

        assert sample_work_item.description in prompt
        assert "GitHub OAuth" in prompt
        assert "Google OAuth" in prompt

    def test_build_prompt_includes_work_item_metadata(self, sample_agent: Agent, sample_work_item: WorkItem) -> None:
        """Verify work item metadata (labels, priority, status) is included."""
        prompt = PromptBuilder.build_prompt(
            work_item=sample_work_item,
            agent=sample_agent,
            stage_name="In Development",
        )

        assert sample_work_item.status.value in prompt
        assert str(sample_work_item.priority.value) in prompt
        assert "authentication" in prompt
        assert "security" in prompt

    def test_build_prompt_includes_external_url(self, sample_agent: Agent, sample_work_item: WorkItem) -> None:
        """Verify external URL reference is included."""
        prompt = PromptBuilder.build_prompt(
            work_item=sample_work_item,
            agent=sample_agent,
            stage_name="In Development",
        )

        assert sample_work_item.external_url in prompt

    def test_build_prompt_includes_stage_name(self, sample_agent: Agent, sample_work_item: WorkItem) -> None:
        """Verify current stage name is included."""
        prompt = PromptBuilder.build_prompt(
            work_item=sample_work_item,
            agent=sample_agent,
            stage_name="In Development",
        )

        assert "Stage Instructions" in prompt
        assert "In Development" in prompt

    def test_build_prompt_includes_execution_constraints(self, sample_agent: Agent, sample_work_item: WorkItem) -> None:
        """Verify execution constraints are included."""
        prompt = PromptBuilder.build_prompt(
            work_item=sample_work_item,
            agent=sample_agent,
            stage_name="In Development",
        )

        assert "Execution Constraints" in prompt
        assert "code changes" in prompt.lower()
        assert "Container execution" in prompt

    def test_build_prompt_includes_mcp_servers(self, sample_agent: Agent, sample_work_item: WorkItem) -> None:
        """Verify available MCP servers are listed."""
        prompt = PromptBuilder.build_prompt(
            work_item=sample_work_item,
            agent=sample_agent,
            stage_name="In Development",
        )

        assert "MCP Servers" in prompt
        assert "github" in prompt
        assert "filesystem" in prompt

    def test_build_prompt_includes_timeout(self, sample_agent: Agent, sample_work_item: WorkItem) -> None:
        """Verify execution timeout is included."""
        prompt = PromptBuilder.build_prompt(
            work_item=sample_work_item,
            agent=sample_agent,
            stage_name="In Development",
        )

        assert "3600" in prompt
        assert "timeout" in prompt.lower()


class TestPromptBuilderWithWorkflowTemplate:
    """Test prompt building with workflow template."""

    def test_build_prompt_includes_stage_instructions(
        self, sample_agent: Agent, sample_work_item: WorkItem, sample_workflow_template: BoardWorkflowTemplate
    ) -> None:
        """Verify stage-specific instructions from workflow template are included."""
        prompt = PromptBuilder.build_prompt(
            work_item=sample_work_item,
            agent=sample_agent,
            stage_name="In Development",
            workflow_template=sample_workflow_template,
        )

        assert "execution mode" in prompt.lower()
        assert "task-oriented" in prompt.lower()
        assert "automatic advancement" in prompt.lower()

    def test_build_prompt_handles_missing_workflow_template(
        self, sample_agent: Agent, sample_work_item: WorkItem
    ) -> None:
        """Verify prompt is built successfully when workflow template is None."""
        prompt = PromptBuilder.build_prompt(
            work_item=sample_work_item,
            agent=sample_agent,
            stage_name="In Development",
            workflow_template=None,
        )

        assert prompt  # Not empty
        assert "Stage Instructions" in prompt
        assert "In Development" in prompt


class TestPromptBuilderWithPreviousOutput:
    """Test prompt building with previous stage output."""

    def test_build_prompt_includes_previous_output(self, sample_agent: Agent, sample_work_item: WorkItem) -> None:
        """Verify previous stage output is included in prompt."""
        previous_output = "Created user authentication module with OAuth2 support"

        prompt = PromptBuilder.build_prompt(
            work_item=sample_work_item,
            agent=sample_agent,
            stage_name="Code Review",
            previous_output=previous_output,
        )

        assert "Previous Stage Output" in prompt
        assert previous_output in prompt

    def test_build_prompt_without_previous_output(self, sample_agent: Agent, sample_work_item: WorkItem) -> None:
        """Verify prompt is valid when no previous output is provided."""
        prompt = PromptBuilder.build_prompt(
            work_item=sample_work_item,
            agent=sample_agent,
            stage_name="In Development",
            previous_output=None,
        )

        assert prompt  # Not empty
        assert "Previous Stage Output" not in prompt


class TestPromptBuilderAgentVariations:
    """Test prompt building with different agent types."""

    def test_build_prompt_for_reviewer_agent(self, sample_work_item: WorkItem) -> None:
        """Verify prompt for reviewer agent indicates read-only role."""
        reviewer = Agent.create(
            name="code-reviewer",
            display_name="Code Reviewer",
            agent_type=AgentType.REVIEWER,
            role_description="Reviews code for quality and correctness.",
            model="claude-opus-4-7",
            capabilities={"code_review": AgentCapability("code_review", 0.95)},
            makes_code_changes=False,
            filesystem_write_allowed=False,
            requires_docker=False,
        )

        prompt = PromptBuilder.build_prompt(
            work_item=sample_work_item,
            agent=reviewer,
            stage_name="Code Review",
        )

        assert "code changes" in prompt.lower()
        assert "may NOT" in prompt
        assert "analysis" in prompt.lower()

    def test_build_prompt_without_mcp_servers(self, sample_work_item: WorkItem) -> None:
        """Verify prompt handles agents with no MCP servers."""
        agent = Agent.create(
            name="test-agent",
            display_name="Test Agent",
            agent_type=AgentType.SPECIALIZED,
            role_description="A minimal test agent.",
            model="claude-opus-4-7",
            capabilities={"testing": AgentCapability("testing", 0.7)},
            mcp_servers=[],
        )

        prompt = PromptBuilder.build_prompt(
            work_item=sample_work_item,
            agent=agent,
            stage_name="Testing",
        )

        assert prompt  # Should not fail with empty MCP servers
        # Verify basic content is still there
        assert "Test Agent" in prompt
        assert sample_work_item.title in prompt

    def test_build_prompt_without_system_prompt(self, sample_work_item: WorkItem) -> None:
        """Verify prompt is valid when agent has no system prompt."""
        agent = Agent.create(
            name="test-agent",
            display_name="Test Agent",
            agent_type=AgentType.SPECIALIZED,
            role_description="A test agent without system prompt.",
            model="claude-opus-4-7",
            capabilities={"basic": AgentCapability("basic", 0.5)},
            system_prompt="",  # Empty system prompt
        )

        prompt = PromptBuilder.build_prompt(
            work_item=sample_work_item,
            agent=agent,
            stage_name="Testing",
        )

        assert prompt  # Should not fail with empty system prompt
        assert "Your Role" in prompt
        assert sample_work_item.title in prompt


class TestPromptBuilderStructure:
    """Test prompt structure and formatting."""

    def test_prompt_sections_are_separated(self, sample_agent: Agent, sample_work_item: WorkItem) -> None:
        """Verify prompt sections are clearly separated."""
        prompt = PromptBuilder.build_prompt(
            work_item=sample_work_item,
            agent=sample_agent,
            stage_name="In Development",
        )

        # Check for section separators
        assert "---" in prompt
        # Should have multiple sections
        section_count = prompt.count("---")
        assert section_count >= 2

    def test_prompt_sections_use_markdown_headers(self, sample_agent: Agent, sample_work_item: WorkItem) -> None:
        """Verify prompt uses markdown headers for structure."""
        prompt = PromptBuilder.build_prompt(
            work_item=sample_work_item,
            agent=sample_agent,
            stage_name="In Development",
        )

        assert "# System Prompt" in prompt or "# Your Role" in prompt
        assert "# Work Item" in prompt
        assert "# Stage Instructions" in prompt

    def test_prompt_length_is_reasonable(self, sample_agent: Agent, sample_work_item: WorkItem) -> None:
        """Verify prompt is substantial but not excessive."""
        prompt = PromptBuilder.build_prompt(
            work_item=sample_work_item,
            agent=sample_agent,
            stage_name="In Development",
        )

        # Prompt should be at least 500 characters (substantial)
        assert len(prompt) > 500
        # Prompt should be less than 50KB (reasonable)
        assert len(prompt) < 50000
