"""Unit tests for ProjectContext aggregate root."""

from datetime import datetime

import pytest

from codetoreum.domain.exceptions import DomainError
from codetoreum.domain.project_context import (
    ProjectContext,
    ProjectContextCreated,
    ProjectDockerConfigUpdated,
    ProjectTestConfigUpdated,
    ProjectWorkflowMappingAdded,
)


class TestProjectContextCreation:
    """Tests for ProjectContext creation."""

    def test_create_minimal_project_context(self):
        """Test creating project context with minimal required fields."""
        project = ProjectContext.create(
            name="test-project",
            display_name="Test Project",
            repository_url="https://github.com/test/repo"
        )

        assert project.id is not None
        assert project.name == "test-project"
        assert project.display_name == "Test Project"
        assert project.repository_url == "https://github.com/test/repo"
        assert project.default_branch == "main"
        assert project.branch_prefix == "feature/"
        assert project.tech_stack == []
        assert project.primary_language == "python"
        assert project.test_command is None
        assert project.test_framework is None
        assert project.has_ci_cd is False
        assert project.default_workflow_template_id == "default"
        assert project.custom_workflows == {}
        assert project.has_dockerfile is False
        assert project.dockerfile_path is None
        assert project.requires_dev_container is False
        assert project.environment_variables == {}
        assert project.secrets == []
        assert project.mcp_servers == []
        assert project.metadata == {}
        assert isinstance(project.created_at, datetime)
        assert isinstance(project.updated_at, datetime)

    def test_create_full_project_context(self):
        """Test creating project context with all optional fields."""
        project = ProjectContext.create(
            name="full-project",
            display_name="Full Project",
            repository_url="https://github.com/test/full",
            default_branch="develop",
            tech_stack=["python", "docker", "postgres"],
            primary_language="python",
            default_workflow_template_id="custom-default"
        )

        assert project.name == "full-project"
        assert project.default_branch == "develop"
        assert project.tech_stack == ["python", "docker", "postgres"]
        assert project.primary_language == "python"
        assert project.default_workflow_template_id == "custom-default"

    def test_create_emits_event(self):
        """Test that creation emits ProjectContextCreated event."""
        project = ProjectContext.create(
            name="test-project",
            display_name="Test Project",
            repository_url="https://github.com/test/repo"
        )

        events = project.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], ProjectContextCreated)
        assert events[0].aggregate_id == project.id
        assert events[0].aggregate_type == "ProjectContext"
        assert events[0].payload["name"] == "test-project"
        assert events[0].payload["repository_url"] == "https://github.com/test/repo"
        assert events[0].payload["default_branch"] == "main"

    def test_create_with_empty_name_raises_error(self):
        """Test that creating with empty name raises DomainError."""
        with pytest.raises(DomainError, match="must have a non-empty name"):
            ProjectContext.create(
                name="",
                display_name="Test",
                repository_url="https://github.com/test/repo"
            )

    def test_create_with_empty_repository_url_raises_error(self):
        """Test that creating with empty repository URL raises DomainError."""
        with pytest.raises(DomainError, match="must have a repository URL"):
            ProjectContext.create(
                name="test",
                display_name="Test",
                repository_url=""
            )

    def test_create_with_empty_default_branch_raises_error(self):
        """Test that creating with empty default branch raises DomainError."""
        with pytest.raises(DomainError, match="must have a default branch"):
            ProjectContext.create(
                name="test",
                display_name="Test",
                repository_url="https://github.com/test/repo",
                default_branch=""
            )


class TestTestConfiguration:
    """Tests for test configuration management."""

    def test_update_test_configuration(self):
        """Test updating test configuration."""
        project = ProjectContext.create(
            name="test-project",
            display_name="Test Project",
            repository_url="https://github.com/test/repo"
        )
        project.clear_events()

        project.update_test_configuration(
            test_command="pytest",
            test_framework="pytest"
        )

        assert project.test_command == "pytest"
        assert project.test_framework == "pytest"
        assert project._version == 1

        events = project.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], ProjectTestConfigUpdated)
        assert events[0].payload["test_command"] == "pytest"
        assert events[0].payload["test_framework"] == "pytest"

    def test_update_test_configuration_without_framework(self):
        """Test updating test configuration without specifying framework."""
        project = ProjectContext.create(
            name="test-project",
            display_name="Test Project",
            repository_url="https://github.com/test/repo"
        )

        project.update_test_configuration(test_command="npm test")

        assert project.test_command == "npm test"
        assert project.test_framework is None

    def test_update_test_configuration_with_empty_command_raises_error(self):
        """Test that updating with empty test command raises DomainError."""
        project = ProjectContext.create(
            name="test-project",
            display_name="Test Project",
            repository_url="https://github.com/test/repo"
        )

        with pytest.raises(DomainError, match="Test command cannot be empty"):
            project.update_test_configuration(test_command="")

    def test_update_test_configuration_updates_timestamp(self):
        """Test that updating test configuration updates timestamp."""
        project = ProjectContext.create(
            name="test-project",
            display_name="Test Project",
            repository_url="https://github.com/test/repo"
        )
        original_updated_at = project.updated_at

        project.update_test_configuration(test_command="pytest")

        assert project.updated_at > original_updated_at


class TestDockerConfiguration:
    """Tests for Docker configuration management."""

    def test_configure_docker_with_dockerfile(self):
        """Test configuring Docker with Dockerfile."""
        project = ProjectContext.create(
            name="test-project",
            display_name="Test Project",
            repository_url="https://github.com/test/repo"
        )
        project.clear_events()

        project.configure_docker(
            has_dockerfile=True,
            dockerfile_path="./Dockerfile",
            requires_dev_container=False
        )

        assert project.has_dockerfile is True
        assert project.dockerfile_path == "./Dockerfile"
        assert project.requires_dev_container is False
        assert project._version == 1

        events = project.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], ProjectDockerConfigUpdated)
        assert events[0].payload["has_dockerfile"] is True
        assert events[0].payload["dockerfile_path"] == "./Dockerfile"

    def test_configure_docker_without_dockerfile(self):
        """Test configuring Docker without Dockerfile."""
        project = ProjectContext.create(
            name="test-project",
            display_name="Test Project",
            repository_url="https://github.com/test/repo"
        )

        project.configure_docker(
            has_dockerfile=False,
            requires_dev_container=True
        )

        assert project.has_dockerfile is False
        assert project.dockerfile_path is None
        assert project.requires_dev_container is True

    def test_configure_docker_with_dev_container(self):
        """Test configuring Docker with dev container requirement."""
        project = ProjectContext.create(
            name="test-project",
            display_name="Test Project",
            repository_url="https://github.com/test/repo"
        )

        project.configure_docker(
            has_dockerfile=True,
            dockerfile_path=".devcontainer/Dockerfile",
            requires_dev_container=True
        )

        assert project.has_dockerfile is True
        assert project.dockerfile_path == ".devcontainer/Dockerfile"
        assert project.requires_dev_container is True

    def test_configure_docker_with_dockerfile_but_no_path_raises_error(self):
        """Test that configuring with dockerfile but no path raises error."""
        project = ProjectContext.create(
            name="test-project",
            display_name="Test Project",
            repository_url="https://github.com/test/repo"
        )

        with pytest.raises(DomainError, match="Dockerfile path required"):
            project.configure_docker(has_dockerfile=True)


class TestWorkflowMapping:
    """Tests for workflow template mapping."""

    def test_add_custom_workflow(self):
        """Test adding custom workflow mapping."""
        project = ProjectContext.create(
            name="test-project",
            display_name="Test Project",
            repository_url="https://github.com/test/repo"
        )
        project.clear_events()

        project.add_custom_workflow("hotfix", "hotfix-template")

        assert project.custom_workflows["hotfix"] == "hotfix-template"
        assert project._version == 1

        events = project.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], ProjectWorkflowMappingAdded)
        assert events[0].payload["label"] == "hotfix"
        assert events[0].payload["template_id"] == "hotfix-template"

    def test_add_multiple_custom_workflows(self):
        """Test adding multiple custom workflow mappings."""
        project = ProjectContext.create(
            name="test-project",
            display_name="Test Project",
            repository_url="https://github.com/test/repo"
        )

        project.add_custom_workflow("hotfix", "hotfix-template")
        project.add_custom_workflow("bugfix", "bugfix-template")
        project.add_custom_workflow("feature", "feature-template")

        assert len(project.custom_workflows) == 3
        assert project.custom_workflows["hotfix"] == "hotfix-template"
        assert project.custom_workflows["bugfix"] == "bugfix-template"
        assert project.custom_workflows["feature"] == "feature-template"

    def test_add_custom_workflow_with_empty_label_raises_error(self):
        """Test that adding workflow with empty label raises error."""
        project = ProjectContext.create(
            name="test-project",
            display_name="Test Project",
            repository_url="https://github.com/test/repo"
        )

        with pytest.raises(DomainError, match="Label cannot be empty"):
            project.add_custom_workflow("", "template")

    def test_add_custom_workflow_with_empty_template_id_raises_error(self):
        """Test that adding workflow with empty template ID raises error."""
        project = ProjectContext.create(
            name="test-project",
            display_name="Test Project",
            repository_url="https://github.com/test/repo"
        )

        with pytest.raises(DomainError, match="Template ID cannot be empty"):
            project.add_custom_workflow("label", "")

    def test_get_workflow_template_for_matching_label(self):
        """Test getting workflow template for matching label."""
        project = ProjectContext.create(
            name="test-project",
            display_name="Test Project",
            repository_url="https://github.com/test/repo"
        )
        project.add_custom_workflow("hotfix", "hotfix-template")
        project.add_custom_workflow("feature", "feature-template")

        template_id = project.get_workflow_template_for_labels(["hotfix", "urgent"])

        assert template_id == "hotfix-template"

    def test_get_workflow_template_for_no_matching_label(self):
        """Test getting workflow template when no label matches."""
        project = ProjectContext.create(
            name="test-project",
            display_name="Test Project",
            repository_url="https://github.com/test/repo"
        )
        project.add_custom_workflow("hotfix", "hotfix-template")

        template_id = project.get_workflow_template_for_labels(["feature", "enhancement"])

        assert template_id == "default"

    def test_get_workflow_template_for_empty_labels(self):
        """Test getting workflow template with empty labels list."""
        project = ProjectContext.create(
            name="test-project",
            display_name="Test Project",
            repository_url="https://github.com/test/repo"
        )
        project.add_custom_workflow("hotfix", "hotfix-template")

        template_id = project.get_workflow_template_for_labels([])

        assert template_id == "default"

    def test_get_workflow_template_uses_first_match(self):
        """Test that workflow template selection uses first matching label."""
        project = ProjectContext.create(
            name="test-project",
            display_name="Test Project",
            repository_url="https://github.com/test/repo"
        )
        project.add_custom_workflow("hotfix", "hotfix-template")
        project.add_custom_workflow("feature", "feature-template")

        # "feature" appears first in the list
        template_id = project.get_workflow_template_for_labels(["feature", "hotfix"])

        assert template_id == "feature-template"


class TestEventManagement:
    """Tests for event management."""

    def test_get_pending_events_returns_copy(self):
        """Test that get_pending_events returns a copy of events list."""
        project = ProjectContext.create(
            name="test-project",
            display_name="Test Project",
            repository_url="https://github.com/test/repo"
        )

        events1 = project.get_pending_events()
        events2 = project.get_pending_events()

        assert events1 is not events2
        assert events1 == events2

    def test_clear_events(self):
        """Test clearing pending events."""
        project = ProjectContext.create(
            name="test-project",
            display_name="Test Project",
            repository_url="https://github.com/test/repo"
        )

        assert len(project.get_pending_events()) == 1

        project.clear_events()

        assert len(project.get_pending_events()) == 0

    def test_multiple_operations_accumulate_events(self):
        """Test that multiple operations accumulate events."""
        project = ProjectContext.create(
            name="test-project",
            display_name="Test Project",
            repository_url="https://github.com/test/repo"
        )
        project.clear_events()

        project.update_test_configuration("pytest")
        project.configure_docker(has_dockerfile=True, dockerfile_path="./Dockerfile")
        project.add_custom_workflow("hotfix", "hotfix-template")

        events = project.get_pending_events()
        assert len(events) == 3
        assert isinstance(events[0], ProjectTestConfigUpdated)
        assert isinstance(events[1], ProjectDockerConfigUpdated)
        assert isinstance(events[2], ProjectWorkflowMappingAdded)


class TestVersioning:
    """Tests for aggregate versioning."""

    def test_initial_version_is_zero(self):
        """Test that initial version is 0."""
        project = ProjectContext.create(
            name="test-project",
            display_name="Test Project",
            repository_url="https://github.com/test/repo"
        )

        assert project._version == 0

    def test_version_increments_on_mutation(self):
        """Test that version increments on each mutation."""
        project = ProjectContext.create(
            name="test-project",
            display_name="Test Project",
            repository_url="https://github.com/test/repo"
        )

        project.update_test_configuration("pytest")
        assert project._version == 1

        project.configure_docker(has_dockerfile=False)
        assert project._version == 2

        project.add_custom_workflow("hotfix", "hotfix-template")
        assert project._version == 3
