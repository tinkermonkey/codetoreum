"""
Phase D2: Agent Pipeline Workflow Configuration Tests

Tests for configuring workflow templates for the "In Progress" stage:
- Agent type (coding agent)
- Model selection (Claude Sonnet)
- Context file mounting
- Agent prompt template
- Git identity for commits
- Verification that no credentials are passed to container

This test suite verifies the requirements for Phase D2.
"""

from datetime import UTC, datetime
from types import MappingProxyType

import pytest

from codetoreum.adapters.testing.in_memory_config_store import InMemoryConfigStore
from codetoreum.adapters.testing.in_memory_event_store import InMemoryEventStore
from codetoreum.application.configuration_service import ConfigurationService
from codetoreum.application.workspace_router import WorkspaceRouter
from codetoreum.domain.agent import Agent, AgentType
from codetoreum.domain.project_context import ProjectContext
from codetoreum.domain.workspace_context import WorkspaceContext, WorkspaceType
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.input.config_command import UpdatePipelineConfigCommand
from codetoreum.ports.output.config_store import (
    ConfigNotFoundError,
    ProjectConfig,
)


@pytest.fixture
async def config_store():
    """Create in-memory config store."""
    store = InMemoryConfigStore()
    yield store
    store.clear()


@pytest.fixture
async def event_bus():
    """Create event bus."""
    return EventBus()


@pytest.fixture
async def config_service(config_store, event_bus):
    """Create configuration service."""
    return ConfigurationService(config_store, event_bus)


@pytest.fixture
async def sample_project(config_store):
    """Create sample project configuration."""
    project = ProjectConfig(
        id="codetoreum:codetoreum",
        name="codetoreum/codetoreum",
        github_org="codetoreum",
        github_repo="codetoreum",
        tech_stacks={},
        pipelines=[],
        testing={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await config_store.save_project_config(project)
    return project


class TestPhaseD2WorkflowConfiguration:
    """Tests for Phase D2 workflow configuration."""

    @pytest.mark.asyncio
    async def test_configure_in_progress_stage_with_coding_agent(self, config_service, config_store, sample_project):
        """Test configuring 'In Progress' stage with coding agent.

        Verifies:
        - Pipeline template stored for "In Progress" stage
        - Agent type set to "coding agent"
        - Model set to Claude Sonnet
        - Context files configured (issue.md, repo_summary.md, previous_stage.txt)
        - Agent prompt template included
        """
        command = UpdatePipelineConfigCommand(
            project_name="codetoreum/codetoreum",
            pipeline_name="default",
            updates={
                "stages": [
                    {
                        "name": "In Progress",
                        "agent_type": "coding agent",
                        "model": "claude-sonnet-4-5",
                        "context_files": [
                            {
                                "path": "/context/issue.md",
                                "description": "Work item title, description, and labels",
                            },
                            {
                                "path": "/context/repo_summary.md",
                                "description": "Repository structure summary (top-level dirs, key files)",
                            },
                            {
                                "path": "/context/previous_stage.txt",
                                "description": "Empty for first stage",
                            },
                        ],
                        "prompt_template": (
                            "You are a coding assistant. Your task is to implement the issue "
                            "described in /context/issue.md. "
                            "Write tests for your implementation. "
                            "Output a summary of changes made."
                        ),
                        "git_author_name": "Codetoreum Agent",
                        "git_author_email": "agent@codetoreum.dev",
                    }
                ],
                "triggers": ["column:In Progress"],
            },
            user_id="test-user",
        )

        result = await config_service.update_pipeline_config(command)

        assert result.success
        assert result.config_version == 2

        # Read back and verify
        pipeline = await config_store.get_pipeline_config(sample_project.id, "default")
        assert len(pipeline.stages) == 1

        stage = dict(pipeline.stages[0])
        assert stage["name"] == "In Progress"
        assert stage["agent_type"] == "coding agent"
        assert stage["model"] == "claude-sonnet-4-5"
        assert len(stage["context_files"]) == 3
        assert stage["context_files"][0]["path"] == "/context/issue.md"
        assert stage["git_author_name"] == "Codetoreum Agent"
        assert stage["git_author_email"] == "agent@codetoreum.dev"

    @pytest.mark.asyncio
    async def test_workflow_template_smoke_test(self, config_service, config_store, sample_project):
        """Smoke test: configure and read back workflow template.

        Verifies that ConfigurationService correctly persists and retrieves
        a complete workflow template for the "In Progress" stage.
        """
        # Configure the pipeline
        command = UpdatePipelineConfigCommand(
            project_name="codetoreum/codetoreum",
            pipeline_name="default",
            updates={
                "stages": [
                    {
                        "name": "In Progress",
                        "agent_type": "coding agent",
                        "model": "claude-sonnet-4-5",
                        "context_files": [
                            {
                                "path": "/context/issue.md",
                                "description": "Work item title, description, and labels",
                            },
                            {
                                "path": "/context/repo_summary.md",
                                "description": "Repository structure summary",
                            },
                            {
                                "path": "/context/previous_stage.txt",
                                "description": "Empty for first stage",
                            },
                        ],
                        "prompt_template": "Implement the issue described in /context/issue.md",
                        "git_author_name": "Codetoreum Agent",
                        "git_author_email": "agent@codetoreum.dev",
                    }
                ]
            },
            user_id="test-user",
        )

        result = await config_service.update_pipeline_config(command)
        assert result.success

        # Read back and verify all fields present and correct
        pipeline = await config_store.get_pipeline_config(sample_project.id, "default")

        assert pipeline.name == "default"
        assert len(pipeline.stages) == 1

        stage = dict(pipeline.stages[0])

        # Verify all fields
        expected_fields = [
            "name",
            "agent_type",
            "model",
            "context_files",
            "prompt_template",
            "git_author_name",
            "git_author_email",
        ]
        for field in expected_fields:
            assert field in stage, f"Stage missing field: {field}"

        # Verify field values
        assert stage["name"] == "In Progress"
        assert stage["agent_type"] == "coding agent"
        assert stage["model"] == "claude-sonnet-4-5"
        assert stage["prompt_template"] == "Implement the issue described in /context/issue.md"
        assert stage["git_author_name"] == "Codetoreum Agent"
        assert stage["git_author_email"] == "agent@codetoreum.dev"

        # Verify context files
        context_files = stage["context_files"]
        assert len(context_files) == 3
        paths = [f["path"] for f in context_files]
        assert "/context/issue.md" in paths
        assert "/context/repo_summary.md" in paths
        assert "/context/previous_stage.txt" in paths

    @pytest.mark.asyncio
    async def test_container_environment_no_credentials_leaked(self):
        """Verify that prepare_container_environment() does NOT pass credentials to container.

        Audits environment variables to ensure:
        - CLAUDE_CODE_OAUTH_TOKEN is NOT passed
        - GITHUB_TOKEN is NOT passed
        - No other credential-related env vars are passed
        """
        router = WorkspaceRouter()

        # Create test context
        context = WorkspaceContext.for_issue(
            project_id="test-project",
            work_item_id="item-1",
            branch_name="feature/test",
            create_pr=True,
        )

        # Create test project
        project = ProjectContext.create(
            name="test-repo",
            display_name="Test Repository",
            repository_url="https://github.com/test/test-repo",
            default_branch="main",
        )

        # Create test agent
        from codetoreum.domain.agent import AgentCapability

        agent = Agent.create(
            name="test-agent",
            display_name="Test Agent",
            agent_type=AgentType.DEVELOPER,
            role_description="Test agent for Phase D2",
            model="claude-sonnet-4-5",
            capabilities={"testing": AgentCapability(skill="testing", proficiency=1.0)},
            makes_code_changes=True,
        )

        # Prepare environment
        env_vars = await router.prepare_container_environment(context, project, agent)

        # Verify expected variables are present
        expected_vars = [
            "CODETOREUM_PROJECT_ID",
            "CODETOREUM_WORK_ITEM_ID",
            "CODETOREUM_WORKSPACE_TYPE",
            "CODETOREUM_ALLOW_CODE_CHANGES",
            "CODETOREUM_AGENT_ID",
            "CODETOREUM_AGENT_TYPE",
            "GIT_AUTHOR_NAME",
            "GIT_AUTHOR_EMAIL",
            "GIT_COMMITTER_NAME",
            "GIT_COMMITTER_EMAIL",
            "CODETOREUM_BRANCH_NAME",
        ]

        for var in expected_vars:
            assert var in env_vars, f"Expected environment variable '{var}' not found"

        # Verify NO credentials are passed
        forbidden_vars = [
            "CLAUDE_CODE_OAUTH_TOKEN",
            "GITHUB_TOKEN",
            "GIT_CREDENTIALS",
            "SSH_KEY",
            "PRIVATE_KEY",
        ]

        for var in forbidden_vars:
            assert var not in env_vars, f"SECURITY ISSUE: Credential variable '{var}' should NOT be passed to container"

        # Document injected environment variables
        print("\n" + "=" * 70)
        print("AUDIT: Environment Variables Passed to Container")
        print("=" * 70)
        for var, value in sorted(env_vars.items()):
            # Redact actual values for security
            if any(secret in var.lower() for secret in ["password", "token", "key", "secret"]):
                print(f"  {var}: <REDACTED>")
            elif var in ["GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"] or var in ["GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"]:
                print(f"  {var}: {value}")
            else:
                print(f"  {var}: {value}")
        print("=" * 70)
        print("✓ No credential environment variables leaked")
        print("=" * 70 + "\n")

    @pytest.mark.asyncio
    async def test_git_identity_configuration(self, config_service, config_store, sample_project):
        """Test git identity configuration for agent commits.

        Verifies:
        - Git author name stored in pipeline config
        - Git author email stored in pipeline config
        - Values match Codetoreum conventions
        """
        command = UpdatePipelineConfigCommand(
            project_name="codetoreum/codetoreum",
            pipeline_name="default",
            updates={
                "stages": [
                    {
                        "name": "In Progress",
                        "agent_type": "coding agent",
                        "model": "claude-sonnet-4-5",
                        "git_author_name": "Codetoreum Agent",
                        "git_author_email": "agent@codetoreum.dev",
                    }
                ]
            },
            user_id="test-user",
        )

        result = await config_service.update_pipeline_config(command)
        assert result.success

        # Verify git identity
        pipeline = await config_store.get_pipeline_config(sample_project.id, "default")
        stage = dict(pipeline.stages[0])

        assert stage["git_author_name"] == "Codetoreum Agent"
        assert stage["git_author_email"] == "agent@codetoreum.dev"

    @pytest.mark.asyncio
    async def test_context_files_configuration_structure(self, config_service, config_store, sample_project):
        """Test context files configuration structure.

        Verifies:
        - Context files are a list of dicts
        - Each dict has 'path' and 'description' fields
        - Paths are correct for the mounted files
        """
        context_files = [
            {
                "path": "/context/issue.md",
                "description": "Work item title, description, and labels",
            },
            {
                "path": "/context/repo_summary.md",
                "description": "Repository structure summary (top-level dirs, key files)",
            },
            {
                "path": "/context/previous_stage.txt",
                "description": "Empty for first stage",
            },
        ]

        command = UpdatePipelineConfigCommand(
            project_name="codetoreum/codetoreum",
            pipeline_name="default",
            updates={
                "stages": [
                    {
                        "name": "In Progress",
                        "agent_type": "coding agent",
                        "model": "claude-sonnet-4-5",
                        "context_files": context_files,
                    }
                ]
            },
            user_id="test-user",
        )

        result = await config_service.update_pipeline_config(command)
        assert result.success

        # Verify context files structure
        pipeline = await config_store.get_pipeline_config(sample_project.id, "default")
        stage = dict(pipeline.stages[0])

        assert "context_files" in stage
        stored_files = stage["context_files"]
        assert len(stored_files) == 3

        for i, expected in enumerate(context_files):
            assert stored_files[i]["path"] == expected["path"]
            assert stored_files[i]["description"] == expected["description"]
