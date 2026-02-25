"""Unit tests for ContextBuilder."""

import json
from typing import Any

import pytest

from codetoreum.application.context_builder import (
    ContextBuilder,
    ContextFile,
)
from codetoreum.domain.agent import Agent, AgentCapability, AgentType
from codetoreum.domain.project_context import ProjectContext
from codetoreum.domain.value_objects import ExecutionContext
from codetoreum.domain.work_item import (
    WorkItem,
    WorkItemPriority,
)
from codetoreum.domain.workspace_context import WorkspaceContext

# Mock Adapters


class MockTicketSystem:
    """Mock ticket system for testing."""

    def __init__(self):
        self.work_items: dict[str, WorkItem] = {}

    async def get_work_item(self, work_item_id: str) -> WorkItem | None:
        """Get work item by ID."""
        return self.work_items.get(work_item_id)

    async def update_work_item(self, work_item_id: str, updates: dict[str, Any]) -> WorkItem | None:
        """Update work item."""
        work_item = self.work_items.get(work_item_id)
        if work_item:
            # Update fields
            for key, value in updates.items():
                if hasattr(work_item, key):
                    setattr(work_item, key, value)
        return work_item

    async def create_comment(self, work_item_id: str, body: str, reply_to: str | None = None) -> str:
        """Create comment on work item."""
        return f"comment-{work_item_id}"

    async def list_work_items(self, filters: dict[str, Any] | None = None) -> list[WorkItem]:
        """List work items."""
        return list(self.work_items.values())


class MockStorage:
    """Mock storage for testing."""

    def __init__(self):
        self.artifacts: dict[str, bytes] = {}

    async def store_artifact(self, artifact_id: str, data: bytes, metadata: dict[str, Any] | None = None) -> str:
        """Store artifact."""
        self.artifacts[artifact_id] = data
        return artifact_id

    async def retrieve_artifact(self, artifact_id: str) -> bytes | None:
        """Retrieve artifact."""
        return self.artifacts.get(artifact_id)

    async def list_artifacts(self, prefix: str | None = None) -> list[str]:
        """List artifacts."""
        if prefix:
            return [k for k in self.artifacts.keys() if k.startswith(prefix)]
        return list(self.artifacts.keys())

    async def delete_artifact(self, artifact_id: str) -> bool:
        """Delete artifact."""
        if artifact_id in self.artifacts:
            del self.artifacts[artifact_id]
            return True
        return False


# Fixtures


@pytest.fixture
def mock_ticket_system():
    """Create mock ticket system."""
    return MockTicketSystem()


@pytest.fixture
def mock_storage():
    """Create mock storage."""
    return MockStorage()


@pytest.fixture
def context_builder(mock_ticket_system, mock_storage, tmp_path):
    """Create context builder with mock adapters."""
    return ContextBuilder(
        ticket_system=mock_ticket_system,
        storage=mock_storage,
        workspace_base_path=tmp_path,
    )


@pytest.fixture
def sample_agent():
    """Create sample agent."""
    return Agent.create(
        name="test-agent",
        display_name="Test Agent",
        agent_type=AgentType.DEVELOPER,
        role_description="Develops and tests Python code",
        capabilities={
            "python": AgentCapability(
                skill="python",
                proficiency=0.9,
                description="Python development",
            )
        },
        model="claude-3-5-sonnet-20250219",
        makes_code_changes=True,
    )


@pytest.fixture
def sample_work_item():
    """Create sample work item."""
    work_item = WorkItem.create(
        title="Implement feature X",
        description="This feature should do X, Y, and Z",
        project_id="project-123",
        labels=["enhancement", "backend"],
        priority=WorkItemPriority.HIGH,
    )
    return work_item


@pytest.fixture
def sample_project():
    """Create sample project context."""
    project = ProjectContext.create(
        name="test-project",
        display_name="Test Project",
        repository_url="https://github.com/test/project",
        default_branch="main",
        primary_language="python",
        tech_stack=["python", "fastapi", "postgresql"],
    )
    project.update_test_configuration(
        test_command="pytest tests/",
        test_framework="pytest",
    )
    return project


@pytest.fixture
def sample_workspace(sample_work_item, sample_project):
    """Create sample workspace context."""
    return WorkspaceContext.for_issue(
        project_id=sample_project.id,
        work_item_id=sample_work_item.id,
        branch_name=f"feature/{sample_work_item.id}",
        create_pr=True,
    )


# Tests


@pytest.mark.asyncio
async def test_build_execution_context(
    context_builder,
    sample_agent,
    sample_work_item,
    sample_project,
    sample_workspace,
):
    """Test building execution context."""
    context = await context_builder.build_execution_context(
        work_item=sample_work_item,
        workflow_id="workflow-123",
        stage_name="development",
        agent=sample_agent,
        project=sample_project,
        workspace=sample_workspace,
    )

    assert isinstance(context, ExecutionContext)
    assert context.work_item_id == sample_work_item.id
    assert context.workflow_id == "workflow-123"
    assert context.stage_name == "development"
    assert context.agent_id == sample_agent.id
    assert context.project_id == sample_project.id
    assert context.filesystem_write_allowed
    assert context.can_make_commits


@pytest.mark.asyncio
async def test_build_execution_context_with_metadata(
    context_builder,
    sample_agent,
    sample_work_item,
    sample_project,
    sample_workspace,
):
    """Test building execution context with additional metadata."""
    additional_metadata = {"custom_field": "custom_value"}

    context = await context_builder.build_execution_context(
        work_item=sample_work_item,
        workflow_id="workflow-123",
        stage_name="development",
        agent=sample_agent,
        project=sample_project,
        workspace=sample_workspace,
        additional_metadata=additional_metadata,
    )

    assert context.metadata["custom_field"] == "custom_value"


@pytest.mark.asyncio
async def test_fetch_work_item_details(context_builder, mock_ticket_system):
    """Test fetching work item details."""
    work_item = WorkItem.create(
        title="Test Issue",
        description="Test description",
        project_id="proj-1",
        priority=WorkItemPriority.MEDIUM,
    )
    mock_ticket_system.work_items[work_item.id] = work_item

    result = await context_builder.fetch_work_item_details(work_item.id)

    assert result is not None
    assert result.id == work_item.id
    assert result.title == "Test Issue"


@pytest.mark.asyncio
async def test_fetch_work_item_not_found(context_builder):
    """Test fetching non-existent work item."""
    result = await context_builder.fetch_work_item_details("nonexistent")

    assert result is None


@pytest.mark.asyncio
async def test_build_workspace_context(
    context_builder,
    sample_agent,
    sample_work_item,
    sample_project,
    sample_workspace,
):
    """Test building workspace context."""
    result = await context_builder.build_workspace_context(
        work_item=sample_work_item,
        agent=sample_agent,
        project=sample_project,
        workspace=sample_workspace,
    )

    assert result.success
    assert len(result.context_files) > 0
    assert result.workspace_path is not None

    # Check for expected context files
    file_paths = [f.path for f in result.context_files]
    assert "/context/issue.txt" in file_paths
    assert "/context/project_info.json" in file_paths
    assert "/context/agent_config.json" in file_paths
    assert "/context/workspace_info.json" in file_paths


@pytest.mark.asyncio
async def test_build_workspace_context_with_previous_output(
    context_builder,
    sample_agent,
    sample_work_item,
    sample_project,
    sample_workspace,
):
    """Test building workspace context with previous output."""
    previous_output = "Output from previous stage"

    result = await context_builder.build_workspace_context(
        work_item=sample_work_item,
        agent=sample_agent,
        project=sample_project,
        workspace=sample_workspace,
        previous_output=previous_output,
    )

    assert result.success

    # Check that previous stage output is included
    file_paths = [f.path for f in result.context_files]
    assert "/context/previous_stage.txt" in file_paths

    # Verify content
    previous_file = next(f for f in result.context_files if f.path == "/context/previous_stage.txt")
    assert previous_file.content == previous_output


@pytest.mark.asyncio
async def test_write_context_files(context_builder, tmp_path):
    """Test writing context files to disk."""
    context_files = [
        ContextFile(
            path="/context/test1.txt",
            content="Content 1",
            description="Test file 1",
        ),
        ContextFile(
            path="/context/sub/test2.txt",
            content="Content 2",
            description="Test file 2",
        ),
    ]

    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()

    success = await context_builder.write_context_files(workspace_path, context_files)

    assert success

    # Verify files were written
    file1 = workspace_path / "context" / "test1.txt"
    file2 = workspace_path / "context" / "sub" / "test2.txt"

    assert file1.exists()
    assert file2.exists()
    assert file1.read_text() == "Content 1"
    assert file2.read_text() == "Content 2"


@pytest.mark.asyncio
async def test_cleanup_workspace(context_builder, tmp_path):
    """Test cleaning up workspace directory."""
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    (workspace_path / "test.txt").write_text("test")

    success = await context_builder.cleanup_workspace(workspace_path)

    assert success
    assert not workspace_path.exists()


@pytest.mark.asyncio
async def test_cleanup_nonexistent_workspace(context_builder, tmp_path):
    """Test cleaning up non-existent workspace."""
    workspace_path = tmp_path / "nonexistent"

    success = await context_builder.cleanup_workspace(workspace_path)

    assert success


def test_format_work_item_context(context_builder, sample_work_item):
    """Test formatting work item context."""
    content = context_builder._format_work_item_context(sample_work_item)

    assert "Implement feature X" in content
    assert "This feature should do X, Y, and Z" in content
    assert "enhancement" in content
    assert "backend" in content


def test_format_project_context(context_builder, sample_project):
    """Test formatting project context."""
    context = context_builder._format_project_context(sample_project)

    assert context["id"] == sample_project.id
    assert context["name"] == "test-project"
    assert context["primary_language"] == "python"
    assert "python" in context["tech_stack"]
    assert "fastapi" in context["tech_stack"]
    assert context["test_framework"] == "pytest"


def test_format_agent_context(context_builder, sample_agent):
    """Test formatting agent context."""
    context = context_builder._format_agent_context(sample_agent)

    assert context["id"] == sample_agent.id
    assert context["name"] == "test-agent"
    assert context["type"] == "developer"
    assert context["model"] == "claude-3-5-sonnet-20250219"
    assert context["makes_code_changes"]
    assert len(context["capabilities"]) > 0
    # Capabilities is a list of dicts created from the capabilities dict
    skill_names = [cap["skill"] for cap in context["capabilities"]]
    assert "python" in skill_names


def test_format_workspace_context(context_builder, sample_workspace, sample_work_item, sample_project):
    """Test formatting workspace context."""
    context = context_builder._format_workspace_context(sample_workspace)

    assert context["workspace_type"] == "issue"  # Note: enum value is "issue" not "issues"
    assert context["project_id"] == sample_project.id
    assert context["work_item_id"] == sample_work_item.id
    assert context["branch_name"] == f"feature/{sample_work_item.id}"
    assert context["create_commits"]


@pytest.mark.asyncio
async def test_gather_previous_stage_context(context_builder):
    """Test gathering previous stage context."""
    result = await context_builder.gather_previous_stage_context(
        workflow_id="workflow-123",
        current_stage="development",
    )

    # Currently returns None - placeholder for future implementation
    assert result is None


@pytest.mark.asyncio
async def test_context_file_structure(
    context_builder,
    sample_agent,
    sample_work_item,
    sample_project,
    sample_workspace,
):
    """Test context file structure and content."""
    result = await context_builder.build_workspace_context(
        work_item=sample_work_item,
        agent=sample_agent,
        project=sample_project,
        workspace=sample_workspace,
    )

    # Verify issue file content
    issue_file = next(f for f in result.context_files if f.path == "/context/issue.txt")
    assert sample_work_item.title in issue_file.content
    assert sample_work_item.description in issue_file.content

    # Verify project info can be parsed as JSON
    project_file = next(f for f in result.context_files if f.path == "/context/project_info.json")
    project_data = json.loads(project_file.content)
    assert project_data["id"] == sample_project.id
    assert project_data["name"] == sample_project.name

    # Verify agent config can be parsed as JSON
    agent_file = next(f for f in result.context_files if f.path == "/context/agent_config.json")
    agent_data = json.loads(agent_file.content)
    assert agent_data["id"] == sample_agent.id
    assert agent_data["name"] == sample_agent.name

    # Verify workspace info can be parsed as JSON
    workspace_file = next(f for f in result.context_files if f.path == "/context/workspace_info.json")
    workspace_data = json.loads(workspace_file.content)
    assert workspace_data["workspace_type"] == sample_workspace.workspace_type.value
