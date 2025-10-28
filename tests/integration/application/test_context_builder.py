"""Integration tests for ContextBuilder."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest

from codetoreum.application.context_builder import (
    ContextBuilder,
    ContextFile,
    WorkspaceContextResult,
)
from codetoreum.domain.agent import Agent, AgentCapability, AgentType
from codetoreum.domain.project_context import ProjectContext
from codetoreum.domain.value_objects import ExecutionContext
from codetoreum.domain.workspace_context import WorkspaceContext, WorkspaceType
from codetoreum.domain.work_item import (
    WorkItem,
    WorkItemPriority,
    WorkItemStatus,
)
from codetoreum.ports.output import IStorage, ITicketSystem


# Mock Adapters (same as unit tests, but with more realistic behavior)


class MockTicketSystem:
    """Mock ticket system with realistic behavior."""

    def __init__(self):
        self.work_items: Dict[str, WorkItem] = {}
        self.comments: Dict[str, List[Dict[str, Any]]] = {}

    async def get_work_item(self, work_item_id: str) -> Optional[WorkItem]:
        """Get work item by ID."""
        work_item = self.work_items.get(work_item_id)

        # Add comments to work item if available
        if work_item and work_item_id in self.comments:
            for comment in self.comments[work_item_id]:
                work_item.add_comment(
                    author=comment["author"],
                    body=comment["body"],
                    created_at=comment.get("created_at", "2025-01-01T00:00:00Z"),
                )

        return work_item

    async def update_work_item(
        self, work_item_id: str, updates: Dict[str, Any]
    ) -> WorkItem:
        """Update work item."""
        work_item = self.work_items.get(work_item_id)
        if work_item:
            for key, value in updates.items():
                if hasattr(work_item, key):
                    setattr(work_item, key, value)
        return work_item

    async def create_comment(
        self, work_item_id: str, body: str, reply_to: Optional[str] = None
    ) -> str:
        """Create comment on work item."""
        comment_id = f"comment-{len(self.comments.get(work_item_id, []))}"
        if work_item_id not in self.comments:
            self.comments[work_item_id] = []
        self.comments[work_item_id].append(
            {"id": comment_id, "author": "test-user", "body": body}
        )
        return comment_id

    async def list_work_items(self, filters: Optional[Dict[str, Any]] = None):
        """List work items."""
        items = list(self.work_items.values())
        if filters:
            # Simple filtering by status
            if "status" in filters:
                items = [i for i in items if i.status == filters["status"]]
        return items


class MockStorage:
    """Mock storage with realistic behavior."""

    def __init__(self):
        self.artifacts: Dict[str, tuple[bytes, Dict[str, Any]]] = {}

    async def store_artifact(
        self, artifact_id: str, data: bytes, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Store artifact with metadata."""
        self.artifacts[artifact_id] = (data, metadata or {})
        return artifact_id

    async def retrieve_artifact(self, artifact_id: str) -> Optional[bytes]:
        """Retrieve artifact."""
        if artifact_id in self.artifacts:
            return self.artifacts[artifact_id][0]
        return None

    async def list_artifacts(self, prefix: Optional[str] = None) -> List[str]:
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
    """Create sample agent with full configuration."""
    agent = Agent.create(
        name="python-developer",
        display_name="Python Developer Agent",
        agent_type=AgentType.DEVELOPER,
        capabilities=[
            AgentCapability(
                skill="python",
                proficiency=0.95,
                description="Expert Python development",
            ),
            AgentCapability(
                skill="testing",
                proficiency=0.85,
                description="Writing unit and integration tests",
            ),
        ],
        model="claude-3-5-sonnet-20250219",
        makes_code_changes=True,
        filesystem_write_allowed=True,
        requires_docker=True,
        timeout_seconds=600,
    )
    return agent


@pytest.fixture
def sample_work_item_with_comments():
    """Create sample work item with rich data."""
    work_item = WorkItem.create(
        id="issue-789",
        title="Implement user authentication",
        description="""
# User Authentication Feature

Implement JWT-based authentication for the API.

## Requirements
- Use JWT tokens for authentication
- Implement login and logout endpoints
- Add middleware for protected routes
- Store refresh tokens securely

## Technical Details
- Use FastAPI security utilities
- Store tokens in Redis
- Add rate limiting to auth endpoints
        """.strip(),
        priority=WorkItemPriority.HIGH,
    )

    work_item.add_acceptance_criterion("User can log in with email and password")
    work_item.add_acceptance_criterion("JWT tokens expire after 1 hour")
    work_item.add_acceptance_criterion("Refresh tokens work correctly")
    work_item.add_acceptance_criterion("Rate limiting prevents brute force")
    work_item.add_label("feature")
    work_item.add_label("authentication")
    work_item.add_label("security")

    return work_item


@pytest.fixture
def sample_project_full():
    """Create sample project with full configuration."""
    return ProjectContext.create(
        id="project-auth",
        name="auth-service",
        display_name="Authentication Service",
        repository_url="https://github.com/company/auth-service",
        default_branch="main",
        primary_language="python",
        tech_stack=["python", "fastapi", "postgresql", "redis", "docker"],
        test_framework="pytest",
        test_command="pytest tests/ -v --cov",
        has_ci_cd=True,
        has_dockerfile=True,
        requires_dev_container=True,
        mcp_servers=["filesystem", "git", "github"],
    )


@pytest.fixture
def sample_workspace_issues():
    """Create sample issues workspace."""
    return WorkspaceContext.create(
        workspace_type=WorkspaceType.ISSUES,
        project_id="project-auth",
        work_item_id="issue-789",
        branch_name="feature/issue-789-user-auth",
        create_commits=True,
        mounted_files=["/workspace/src", "/workspace/tests"],
        read_only_paths=["/workspace/.git"],
        environment_variables={
            "PYTHONPATH": "/workspace",
            "ENVIRONMENT": "development",
        },
    )


# Integration Tests


@pytest.mark.asyncio
async def test_full_context_building_workflow(
    context_builder,
    sample_agent,
    sample_work_item_with_comments,
    sample_project_full,
    sample_workspace_issues,
    mock_ticket_system,
):
    """Test full workflow: fetch work item, build context, write files."""
    # Setup: Add work item and comments to ticket system
    mock_ticket_system.work_items[sample_work_item_with_comments.id] = (
        sample_work_item_with_comments
    )
    await mock_ticket_system.create_comment(
        sample_work_item_with_comments.id,
        "Please ensure the implementation follows OWASP guidelines",
    )
    await mock_ticket_system.create_comment(
        sample_work_item_with_comments.id,
        "Also add documentation for the endpoints",
    )

    # Step 1: Fetch work item details
    work_item = await context_builder.fetch_work_item_details(
        sample_work_item_with_comments.id
    )
    assert work_item is not None
    assert work_item.id == sample_work_item_with_comments.id

    # Step 2: Build execution context
    execution_context = await context_builder.build_execution_context(
        work_item=work_item,
        workflow_id="workflow-auth-789",
        stage_name="implementation",
        agent=sample_agent,
        project=sample_project_full,
        workspace=sample_workspace_issues,
        additional_metadata={"sprint": "2025-Q1"},
    )

    assert execution_context.work_item_id == work_item.id
    assert execution_context.agent_id == sample_agent.id
    assert execution_context.project_id == sample_project_full.id
    assert execution_context.metadata["sprint"] == "2025-Q1"

    # Step 3: Build workspace context with previous output
    previous_output = "Previous stage analyzed requirements and created design doc"
    workspace_result = await context_builder.build_workspace_context(
        work_item=work_item,
        agent=sample_agent,
        project=sample_project_full,
        workspace=sample_workspace_issues,
        previous_output=previous_output,
    )

    assert workspace_result.success
    assert len(workspace_result.context_files) >= 5

    # Step 4: Write context files
    success = await context_builder.write_context_files(
        workspace_result.workspace_path,
        workspace_result.context_files,
    )

    assert success
    assert workspace_result.workspace_path.exists()

    # Verify file contents
    issue_file = workspace_result.workspace_path / "context" / "issue.txt"
    assert issue_file.exists()
    issue_content = issue_file.read_text()
    assert "Implement user authentication" in issue_content
    assert "JWT-based authentication" in issue_content
    assert "OWASP guidelines" in issue_content  # From comments

    project_file = workspace_result.workspace_path / "context" / "project_info.json"
    assert project_file.exists()
    project_data = json.loads(project_file.read_text())
    assert project_data["name"] == "auth-service"
    assert "redis" in project_data["tech_stack"]

    agent_file = workspace_result.workspace_path / "context" / "agent_config.json"
    assert agent_file.exists()
    agent_data = json.loads(agent_file.read_text())
    assert agent_data["name"] == "python-developer"
    assert agent_data["requires_docker"]

    previous_file = workspace_result.workspace_path / "context" / "previous_stage.txt"
    assert previous_file.exists()
    assert previous_file.read_text() == previous_output

    # Step 5: Cleanup
    cleanup_success = await context_builder.cleanup_workspace(
        workspace_result.workspace_path
    )
    assert cleanup_success
    assert not workspace_result.workspace_path.exists()


@pytest.mark.asyncio
async def test_context_files_mounted_correctly(
    context_builder,
    sample_agent,
    sample_work_item_with_comments,
    sample_project_full,
    sample_workspace_issues,
):
    """Test that context files are structured for container mounting."""
    workspace_result = await context_builder.build_workspace_context(
        work_item=sample_work_item_with_comments,
        agent=sample_agent,
        project=sample_project_full,
        workspace=sample_workspace_issues,
    )

    # Write files
    await context_builder.write_context_files(
        workspace_result.workspace_path,
        workspace_result.context_files,
    )

    # Verify structure is suitable for Docker mounting
    context_dir = workspace_result.workspace_path / "context"
    assert context_dir.exists()

    expected_files = [
        "issue.txt",
        "project_info.json",
        "agent_config.json",
        "workspace_info.json",
    ]

    for filename in expected_files:
        file_path = context_dir / filename
        assert file_path.exists(), f"{filename} should exist"
        assert file_path.stat().st_size > 0, f"{filename} should not be empty"


@pytest.mark.asyncio
async def test_context_builder_with_discussions_workspace(
    context_builder,
    sample_agent,
    sample_work_item_with_comments,
    sample_project_full,
):
    """Test context building with discussions workspace."""
    discussions_workspace = WorkspaceContext.create(
        workspace_type=WorkspaceType.DISCUSSIONS,
        project_id="project-auth",
        work_item_id=sample_work_item_with_comments.id,
        discussion_id="discussion-123",
        create_commits=False,
    )

    workspace_result = await context_builder.build_workspace_context(
        work_item=sample_work_item_with_comments,
        agent=sample_agent,
        project=sample_project_full,
        workspace=discussions_workspace,
    )

    assert workspace_result.success

    # Verify workspace info reflects discussions type
    workspace_file = next(
        f
        for f in workspace_result.context_files
        if f.path == "/context/workspace_info.json"
    )
    workspace_data = json.loads(workspace_file.content)
    assert workspace_data["workspace_type"] == "discussions"
    assert workspace_data["discussion_id"] == "discussion-123"
    assert not workspace_data["create_commits"]


@pytest.mark.asyncio
async def test_multiple_work_items_parallel(
    context_builder,
    sample_agent,
    sample_project_full,
    sample_workspace_issues,
    mock_ticket_system,
):
    """Test building contexts for multiple work items in parallel."""
    # Create multiple work items
    work_items = []
    for i in range(3):
        work_item = WorkItem.create(
            id=f"issue-{i}",
            title=f"Feature {i}",
            description=f"Implement feature {i}",
            priority=WorkItemPriority.MEDIUM,
        )
        mock_ticket_system.work_items[work_item.id] = work_item
        work_items.append(work_item)

    # Build contexts in parallel
    import asyncio

    tasks = []
    for work_item in work_items:
        workspace = WorkspaceContext.create(
            workspace_type=WorkspaceType.ISSUES,
            project_id=sample_project_full.id,
            work_item_id=work_item.id,
            branch_name=f"feature/{work_item.id}",
            create_commits=True,
        )

        task = context_builder.build_workspace_context(
            work_item=work_item,
            agent=sample_agent,
            project=sample_project_full,
            workspace=workspace,
        )
        tasks.append(task)

    results = await asyncio.gather(*tasks)

    # Verify all succeeded
    assert all(r.success for r in results)
    assert len(results) == 3

    # Verify each has unique workspace path
    workspace_paths = [r.workspace_path for r in results]
    assert len(set(workspace_paths)) == 3


@pytest.mark.asyncio
async def test_context_builder_error_handling(
    context_builder,
    sample_agent,
    sample_work_item_with_comments,
    sample_project_full,
    sample_workspace_issues,
):
    """Test error handling in context building."""
    # Test with invalid workspace path
    result = await context_builder.build_workspace_context(
        work_item=sample_work_item_with_comments,
        agent=sample_agent,
        project=sample_project_full,
        workspace=sample_workspace_issues,
    )

    # Even with potential errors, should return a result
    assert isinstance(result, WorkspaceContextResult)


@pytest.mark.asyncio
async def test_context_files_idempotent(
    context_builder,
    sample_agent,
    sample_work_item_with_comments,
    sample_project_full,
    sample_workspace_issues,
):
    """Test that writing context files is idempotent."""
    workspace_result = await context_builder.build_workspace_context(
        work_item=sample_work_item_with_comments,
        agent=sample_agent,
        project=sample_project_full,
        workspace=sample_workspace_issues,
    )

    # Write once
    success1 = await context_builder.write_context_files(
        workspace_result.workspace_path,
        workspace_result.context_files,
    )

    # Write again
    success2 = await context_builder.write_context_files(
        workspace_result.workspace_path,
        workspace_result.context_files,
    )

    assert success1
    assert success2

    # Verify files still correct
    issue_file = workspace_result.workspace_path / "context" / "issue.txt"
    assert issue_file.exists()
    content = issue_file.read_text()
    assert sample_work_item_with_comments.title in content
