"""Unit tests for ExecutionContextBuilder."""

import pytest

from codetoreum.domain.agent import Agent, AgentCapability, AgentType
from codetoreum.domain.exceptions import DomainError
from codetoreum.domain.project_context import ProjectContext
from codetoreum.domain.services.execution_context_builder import (
    ExecutionContextBuilder,
)
from codetoreum.domain.value_objects import ExecutionContext
from codetoreum.domain.work_item import WorkItem, WorkItemPriority
from codetoreum.domain.workspace_context import WorkspaceContext, WorkspaceType


@pytest.fixture
def project_context():
    """Create a test project context."""
    project = ProjectContext.create(
        name="test_project",
        display_name="Test Project",
        repository_url="https://github.com/test/repo",
        default_branch="main",
        tech_stack=["python", "docker"],
        primary_language="python",
    )
    project.configure_docker(has_dockerfile=True, dockerfile_path="Dockerfile")
    project.update_test_configuration("pytest", "pytest")
    return project


@pytest.fixture
def work_item(project_context):
    """Create a test work item."""
    return WorkItem.create(
        title="Implement feature",
        description="Add new feature",
        project_id=project_context.id,
        priority=WorkItemPriority.HIGH,
        external_id="ISSUE-123",
        external_url="https://github.com/test/repo/issues/123",
    )


@pytest.fixture
def workspace_context(work_item, project_context):
    """Create a test workspace context."""
    return WorkspaceContext.for_issue(
        project_id=project_context.id,
        work_item_id=work_item.id,
        branch_name="feature/issue-123",
        create_pr=True,
    )


@pytest.fixture
def developer_agent():
    """Create a developer agent."""
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
        filesystem_write_allowed=True,
    )


@pytest.fixture
def reviewer_agent():
    """Create a reviewer agent."""
    return Agent.create(
        name="reviewer",
        display_name="Code Reviewer",
        agent_type=AgentType.REVIEWER,
        role_description="Code reviewer",
        model="claude-sonnet-4-5",
        capabilities={
            "code_review": AgentCapability("code_review", 0.95),
        },
        makes_code_changes=False,
        filesystem_write_allowed=False,
    )


class TestBuildContext:
    """Tests for build_context method."""

    def test_builds_complete_context(self, work_item, developer_agent, project_context, workspace_context):
        """Test building complete execution context."""
        context = ExecutionContextBuilder.build_context(
            work_item=work_item,
            workflow_id="workflow-123",
            stage_name="implementation",
            agent=developer_agent,
            project=project_context,
            workspace=workspace_context,
        )

        assert isinstance(context, ExecutionContext)
        assert context.work_item_id == work_item.id
        assert context.workflow_id == "workflow-123"
        assert context.stage_name == "implementation"
        assert context.agent_id == developer_agent.id
        assert context.model == developer_agent.model
        assert context.timeout_seconds == developer_agent.timeout_seconds

    def test_sets_workspace_details(self, work_item, developer_agent, project_context, workspace_context):
        """Test that workspace details are set correctly."""
        context = ExecutionContextBuilder.build_context(
            work_item=work_item,
            workflow_id="workflow-123",
            stage_name="implementation",
            agent=developer_agent,
            project=project_context,
            workspace=workspace_context,
        )

        assert context.workspace_type == WorkspaceType.ISSUE.value
        assert context.branch_name == "feature/issue-123"
        assert context.discussion_id is None

    def test_sets_project_details(self, work_item, developer_agent, project_context, workspace_context):
        """Test that project details are set correctly."""
        context = ExecutionContextBuilder.build_context(
            work_item=work_item,
            workflow_id="workflow-123",
            stage_name="implementation",
            agent=developer_agent,
            project=project_context,
            workspace=workspace_context,
        )

        assert context.project_id == project_context.id
        assert context.repository_url == project_context.repository_url
        assert context.tech_stack == ["python", "docker"]

    def test_sets_permissions_for_code_agent(self, work_item, developer_agent, project_context, workspace_context):
        """Test that permissions are set correctly for code-making agent."""
        context = ExecutionContextBuilder.build_context(
            work_item=work_item,
            workflow_id="workflow-123",
            stage_name="implementation",
            agent=developer_agent,
            project=project_context,
            workspace=workspace_context,
        )

        assert context.filesystem_write_allowed is True
        assert context.can_make_commits is True
        assert context.requires_docker is True

    def test_sets_permissions_for_reviewer_agent(self, work_item, reviewer_agent, project_context, workspace_context):
        """Test that permissions are set correctly for reviewer agent."""
        context = ExecutionContextBuilder.build_context(
            work_item=work_item,
            workflow_id="workflow-123",
            stage_name="review",
            agent=reviewer_agent,
            project=project_context,
            workspace=workspace_context,
        )

        assert context.filesystem_write_allowed is False
        assert context.can_make_commits is False

    def test_sets_permissions_for_discussion_workspace(self, work_item, developer_agent, project_context):
        """Test that permissions respect workspace type."""
        discussion_workspace = WorkspaceContext.for_discussion(
            project_id=project_context.id,
            work_item_id=work_item.id,
            discussion_id="123",
        )

        context = ExecutionContextBuilder.build_context(
            work_item=work_item,
            workflow_id="workflow-123",
            stage_name="implementation",
            agent=developer_agent,
            project=project_context,
            workspace=discussion_workspace,
        )

        # Even though agent can make changes, workspace doesn't allow it
        assert context.filesystem_write_allowed is False
        assert context.can_make_commits is False

    def test_includes_previous_session_id(self, work_item, developer_agent, project_context, workspace_context):
        """Test that previous session ID is included."""
        context = ExecutionContextBuilder.build_context(
            work_item=work_item,
            workflow_id="workflow-123",
            stage_name="implementation",
            agent=developer_agent,
            project=project_context,
            workspace=workspace_context,
            previous_session_id="session-456",
        )

        assert context.previous_session_id == "session-456"

    def test_merges_additional_metadata(self, work_item, developer_agent, project_context, workspace_context):
        """Test that additional metadata is merged."""
        additional = {"custom_key": "custom_value", "stage_config": {"timeout": 600}}

        context = ExecutionContextBuilder.build_context(
            work_item=work_item,
            workflow_id="workflow-123",
            stage_name="implementation",
            agent=developer_agent,
            project=project_context,
            workspace=workspace_context,
            additional_metadata=additional,
        )

        assert context.metadata["custom_key"] == "custom_value"
        assert context.metadata["stage_config"] == {"timeout": 600}

    def test_validates_workflow_id(self, work_item, developer_agent, project_context, workspace_context):
        """Test validation of workflow ID."""
        with pytest.raises(DomainError, match="Workflow ID cannot be empty"):
            ExecutionContextBuilder.build_context(
                work_item=work_item,
                workflow_id="",
                stage_name="implementation",
                agent=developer_agent,
                project=project_context,
                workspace=workspace_context,
            )

    def test_validates_stage_name(self, work_item, developer_agent, project_context, workspace_context):
        """Test validation of stage name."""
        with pytest.raises(DomainError, match="Stage name cannot be empty"):
            ExecutionContextBuilder.build_context(
                work_item=work_item,
                workflow_id="workflow-123",
                stage_name="",
                agent=developer_agent,
                project=project_context,
                workspace=workspace_context,
            )

    def test_validates_workspace_work_item_id_match(self, work_item, developer_agent, project_context):
        """Test validation that workspace and work item IDs match."""
        # Create workspace with different work item ID
        mismatched_workspace = WorkspaceContext.for_issue(
            project_id=project_context.id,
            work_item_id="different-id",
            branch_name="feature/test",
        )

        with pytest.raises(DomainError, match="does not match work item ID"):
            ExecutionContextBuilder.build_context(
                work_item=work_item,
                workflow_id="workflow-123",
                stage_name="implementation",
                agent=developer_agent,
                project=project_context,
                workspace=mismatched_workspace,
            )

    def test_validates_workspace_project_id_match(self, work_item, developer_agent, project_context):
        """Test validation that workspace and project IDs match."""
        # Create workspace with different project ID
        mismatched_workspace = WorkspaceContext.for_issue(
            project_id="different-project-id",
            work_item_id=work_item.id,
            branch_name="feature/test",
        )

        with pytest.raises(DomainError, match="does not match project ID"):
            ExecutionContextBuilder.build_context(
                work_item=work_item,
                workflow_id="workflow-123",
                stage_name="implementation",
                agent=developer_agent,
                project=project_context,
                workspace=mismatched_workspace,
            )

    def test_validates_dev_container_requirement(self, work_item, project_context, workspace_context):
        """Test validation when agent requires dev container but project doesn't have one."""
        dev_container_agent = Agent.create(
            name="special_agent",
            display_name="Special Agent",
            agent_type=AgentType.SPECIALIZED,
            role_description="Requires dev container",
            model="claude-sonnet-4-5",
            capabilities={"special": AgentCapability("special", 0.9)},
            requires_dev_container=True,
        )

        with pytest.raises(DomainError, match="requires dev container"):
            ExecutionContextBuilder.build_context(
                work_item=work_item,
                workflow_id="workflow-123",
                stage_name="implementation",
                agent=dev_container_agent,
                project=project_context,
                workspace=workspace_context,
            )


class TestBuildMetadata:
    """Tests for _build_metadata method."""

    def test_includes_work_item_metadata(self, work_item, developer_agent, project_context, workspace_context):
        """Test that work item metadata is included."""
        metadata = ExecutionContextBuilder._build_metadata(
            work_item, developer_agent, project_context, workspace_context, {}
        )

        assert metadata["work_item_title"] == work_item.title
        assert metadata["work_item_status"] == work_item.status.value
        assert metadata["work_item_priority"] == work_item.priority.value
        assert metadata["work_item_labels"] == work_item.labels

    def test_includes_agent_metadata(self, work_item, developer_agent, project_context, workspace_context):
        """Test that agent metadata is included."""
        metadata = ExecutionContextBuilder._build_metadata(
            work_item, developer_agent, project_context, workspace_context, {}
        )

        assert metadata["agent_name"] == developer_agent.name
        assert metadata["agent_display_name"] == developer_agent.display_name
        assert metadata["agent_type"] == developer_agent.agent_type.value

    def test_includes_project_metadata(self, work_item, developer_agent, project_context, workspace_context):
        """Test that project metadata is included."""
        metadata = ExecutionContextBuilder._build_metadata(
            work_item, developer_agent, project_context, workspace_context, {}
        )

        assert metadata["project_name"] == project_context.name
        assert metadata["project_display_name"] == project_context.display_name
        assert metadata["default_branch"] == project_context.default_branch
        assert metadata["primary_language"] == project_context.primary_language
        assert metadata["test_command"] == "pytest"
        assert metadata["test_framework"] == "pytest"

    def test_additional_metadata_overrides_defaults(
        self, work_item, developer_agent, project_context, workspace_context
    ):
        """Test that additional metadata overrides defaults."""
        additional = {"work_item_title": "Override Title", "custom_field": "value"}

        metadata = ExecutionContextBuilder._build_metadata(
            work_item, developer_agent, project_context, workspace_context, additional
        )

        assert metadata["work_item_title"] == "Override Title"
        assert metadata["custom_field"] == "value"


class TestMergeMcpServers:
    """Tests for _merge_mcp_servers method."""

    def test_merges_agent_and_project_servers(self, project_context):
        """Test that agent and project MCP servers are merged."""
        agent = Agent.create(
            name="agent",
            display_name="Agent",
            agent_type=AgentType.MAKER,
            role_description="Test agent",
            model="claude-sonnet-4-5",
            capabilities={"test": AgentCapability("test", 0.9)},
            mcp_servers=["agent_server_1", "agent_server_2"],
        )

        project_context.mcp_servers = ["project_server_1", "project_server_2"]

        servers = ExecutionContextBuilder._merge_mcp_servers(agent, project_context)

        assert "agent_server_1" in servers
        assert "agent_server_2" in servers
        assert "project_server_1" in servers
        assert "project_server_2" in servers

    def test_removes_duplicates(self, project_context):
        """Test that duplicate servers are removed."""
        agent = Agent.create(
            name="agent",
            display_name="Agent",
            agent_type=AgentType.MAKER,
            role_description="Test agent",
            model="claude-sonnet-4-5",
            capabilities={"test": AgentCapability("test", 0.9)},
            mcp_servers=["shared_server", "agent_server"],
        )

        project_context.mcp_servers = ["shared_server", "project_server"]

        servers = ExecutionContextBuilder._merge_mcp_servers(agent, project_context)

        # Should have 3 unique servers
        assert len(servers) == 3
        assert servers.count("shared_server") == 1

    def test_agent_servers_come_first(self, project_context):
        """Test that agent servers are prioritized (come first)."""
        agent = Agent.create(
            name="agent",
            display_name="Agent",
            agent_type=AgentType.MAKER,
            role_description="Test agent",
            model="claude-sonnet-4-5",
            capabilities={"test": AgentCapability("test", 0.9)},
            mcp_servers=["agent_first", "agent_second"],
        )

        project_context.mcp_servers = ["project_first"]

        servers = ExecutionContextBuilder._merge_mcp_servers(agent, project_context)

        assert servers[0] == "agent_first"
        assert servers[1] == "agent_second"
        assert servers[2] == "project_first"


class TestBuildContextForStage:
    """Tests for build_context_for_stage method."""

    def test_builds_context_with_agent_lookup(self, work_item, developer_agent, project_context, workspace_context):
        """Test building context with agent lookup."""
        agents = [developer_agent]

        context = ExecutionContextBuilder.build_context_for_stage(
            work_item=work_item,
            workflow_id="workflow-123",
            stage_name="implementation",
            agents=agents,
            agent_id=developer_agent.id,
            project=project_context,
            workspace=workspace_context,
        )

        assert context.agent_id == developer_agent.id

    def test_raises_error_when_agent_not_found(self, work_item, developer_agent, project_context, workspace_context):
        """Test error when agent not found in list."""
        agents = [developer_agent]

        with pytest.raises(DomainError, match="Agent .* not found"):
            ExecutionContextBuilder.build_context_for_stage(
                work_item=work_item,
                workflow_id="workflow-123",
                stage_name="implementation",
                agents=agents,
                agent_id="nonexistent-agent-id",
                project=project_context,
                workspace=workspace_context,
            )

    def test_includes_previous_session_id(self, work_item, developer_agent, project_context, workspace_context):
        """Test that previous session ID is passed through."""
        agents = [developer_agent]

        context = ExecutionContextBuilder.build_context_for_stage(
            work_item=work_item,
            workflow_id="workflow-123",
            stage_name="implementation",
            agents=agents,
            agent_id=developer_agent.id,
            project=project_context,
            workspace=workspace_context,
            previous_session_id="session-789",
        )

        assert context.previous_session_id == "session-789"
