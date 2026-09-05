"""Unit tests for project lifecycle domain events.

Tests validation, serialization, and deserialization of all project events.
"""

import pytest

from codetoreum.domain.events.project_events import (
    ProjectClonedEvent,
    ProjectCloneFailedEvent,
    ProjectDisabledEvent,
    ProjectEnabledEvent,
)


class TestProjectClonedEvent:
    """Tests for ProjectClonedEvent validation and serialization."""

    def test_valid_project_cloned_event(self):
        """Create a valid ProjectClonedEvent."""
        event = ProjectClonedEvent(
            type="project.cloned",
            timestamp="2025-02-08T10:30:00+00:00",
            source="project_manager",
            project_name="api-service",
            repo_url="https://github.com/acme/api-service.git",
            workspace_path="/workspace/api-service",
            branch="main",
        )
        assert event.project_name == "api-service"
        assert event.repo_url == "https://github.com/acme/api-service.git"
        assert event.workspace_path == "/workspace/api-service"
        assert event.branch == "main"

    def test_project_cloned_event_missing_project_name(self):
        """Fail when project_name is missing."""
        with pytest.raises(ValueError, match="project_name is required"):
            ProjectClonedEvent(
                type="project.cloned",
                timestamp="2025-02-08T10:30:00+00:00",
                source="project_manager",
                project_name="",  # Empty
                repo_url="https://github.com/acme/api-service.git",
                workspace_path="/workspace/api-service",
                branch="main",
            )

    def test_project_cloned_event_missing_repo_url(self):
        """Fail when repo_url is missing."""
        with pytest.raises(ValueError, match="repo_url is required"):
            ProjectClonedEvent(
                type="project.cloned",
                timestamp="2025-02-08T10:30:00+00:00",
                source="project_manager",
                project_name="api-service",
                repo_url="",  # Empty
                workspace_path="/workspace/api-service",
                branch="main",
            )

    def test_project_cloned_event_missing_workspace_path(self):
        """Fail when workspace_path is missing."""
        with pytest.raises(ValueError, match="workspace_path is required"):
            ProjectClonedEvent(
                type="project.cloned",
                timestamp="2025-02-08T10:30:00+00:00",
                source="project_manager",
                project_name="api-service",
                repo_url="https://github.com/acme/api-service.git",
                workspace_path="",  # Empty
                branch="main",
            )

    def test_project_cloned_event_missing_branch(self):
        """Fail when branch is missing."""
        with pytest.raises(ValueError, match="branch is required"):
            ProjectClonedEvent(
                type="project.cloned",
                timestamp="2025-02-08T10:30:00+00:00",
                source="project_manager",
                project_name="api-service",
                repo_url="https://github.com/acme/api-service.git",
                workspace_path="/workspace/api-service",
                branch="",  # Empty
            )

    def test_project_cloned_event_serialization(self):
        """Serialize ProjectClonedEvent to dict."""
        event = ProjectClonedEvent(
            type="project.cloned",
            timestamp="2025-02-08T10:30:00+00:00",
            source="project_manager",
            project_name="api-service",
            repo_url="https://github.com/acme/api-service.git",
            workspace_path="/workspace/api-service",
            branch="main",
        )
        data = event.to_dict()

        assert data["type"] == "project.cloned"
        assert data["project_name"] == "api-service"
        assert data["repo_url"] == "https://github.com/acme/api-service.git"
        assert data["workspace_path"] == "/workspace/api-service"
        assert data["branch"] == "main"

    def test_project_cloned_event_deserialization(self):
        """Deserialize ProjectClonedEvent from dict."""
        data = {
            "type": "project.cloned",
            "timestamp": "2025-02-08T10:30:00+00:00",
            "source": "project_manager",
            "project_name": "api-service",
            "repo_url": "https://github.com/acme/api-service.git",
            "workspace_path": "/workspace/api-service",
            "branch": "main",
        }
        event = ProjectClonedEvent.from_dict(data)

        assert event.project_name == "api-service"
        assert event.repo_url == "https://github.com/acme/api-service.git"
        assert event.workspace_path == "/workspace/api-service"
        assert event.branch == "main"

    def test_project_cloned_event_round_trip(self):
        """Verify serialization round-trip."""
        original = ProjectClonedEvent(
            type="project.cloned",
            timestamp="2025-02-08T10:30:00+00:00",
            source="project_manager",
            project_name="api-service",
            repo_url="https://github.com/acme/api-service.git",
            workspace_path="/workspace/api-service",
            branch="main",
        )

        # Serialize and deserialize
        data = original.to_dict()
        restored = ProjectClonedEvent.from_dict(data)

        assert restored.project_name == original.project_name
        assert restored.repo_url == original.repo_url
        assert restored.workspace_path == original.workspace_path
        assert restored.branch == original.branch


class TestProjectCloneFailedEvent:
    """Tests for ProjectCloneFailedEvent validation and serialization."""

    def test_valid_project_clone_failed_event(self):
        """Create a valid ProjectCloneFailedEvent."""
        event = ProjectCloneFailedEvent(
            type="project.clone_failed",
            timestamp="2025-02-08T10:30:00+00:00",
            source="project_manager",
            project_name="api-service",
            repo_url="https://github.com/acme/api-service.git",
            error_message="Connection timeout: Could not reach github.com",
            will_retry=True,
        )
        assert event.project_name == "api-service"
        assert event.repo_url == "https://github.com/acme/api-service.git"
        assert event.will_retry is True

    def test_project_clone_failed_event_missing_project_name(self):
        """Fail when project_name is missing."""
        with pytest.raises(ValueError, match="project_name is required"):
            ProjectCloneFailedEvent(
                type="project.clone_failed",
                timestamp="2025-02-08T10:30:00+00:00",
                source="project_manager",
                project_name="",  # Empty
                repo_url="https://github.com/acme/api-service.git",
                error_message="Connection timeout",
                will_retry=True,
            )

    def test_project_clone_failed_event_missing_repo_url(self):
        """Fail when repo_url is missing."""
        with pytest.raises(ValueError, match="repo_url is required"):
            ProjectCloneFailedEvent(
                type="project.clone_failed",
                timestamp="2025-02-08T10:30:00+00:00",
                source="project_manager",
                project_name="api-service",
                repo_url="",  # Empty
                error_message="Connection timeout",
                will_retry=True,
            )

    def test_project_clone_failed_event_missing_error_message(self):
        """Fail when error_message is missing."""
        with pytest.raises(ValueError, match="error_message is required"):
            ProjectCloneFailedEvent(
                type="project.clone_failed",
                timestamp="2025-02-08T10:30:00+00:00",
                source="project_manager",
                project_name="api-service",
                repo_url="https://github.com/acme/api-service.git",
                error_message="",  # Empty
                will_retry=True,
            )

    def test_project_clone_failed_event_serialization(self):
        """Serialize ProjectCloneFailedEvent to dict."""
        event = ProjectCloneFailedEvent(
            type="project.clone_failed",
            timestamp="2025-02-08T10:30:00+00:00",
            source="project_manager",
            project_name="api-service",
            repo_url="https://github.com/acme/api-service.git",
            error_message="Connection timeout",
            will_retry=True,
        )
        data = event.to_dict()

        assert data["type"] == "project.clone_failed"
        assert data["project_name"] == "api-service"
        assert data["error_message"] == "Connection timeout"
        assert data["will_retry"] is True

    def test_project_clone_failed_event_round_trip(self):
        """Verify serialization round-trip."""
        original = ProjectCloneFailedEvent(
            type="project.clone_failed",
            timestamp="2025-02-08T10:30:00+00:00",
            source="project_manager",
            project_name="api-service",
            repo_url="https://github.com/acme/api-service.git",
            error_message="Connection timeout",
            will_retry=True,
        )

        data = original.to_dict()
        restored = ProjectCloneFailedEvent.from_dict(data)

        assert restored.project_name == original.project_name
        assert restored.repo_url == original.repo_url
        assert restored.error_message == original.error_message
        assert restored.will_retry == original.will_retry


class TestProjectEnabledEvent:
    """Tests for ProjectEnabledEvent validation and serialization."""

    def test_valid_project_enabled_event(self):
        """Create a valid ProjectEnabledEvent."""
        event = ProjectEnabledEvent(
            type="project.enabled",
            timestamp="2025-02-08T10:30:00+00:00",
            source="project_manager",
            project_name="api-service",
        )
        assert event.project_name == "api-service"

    def test_project_enabled_event_missing_project_name(self):
        """Fail when project_name is missing."""
        with pytest.raises(ValueError, match="project_name is required"):
            ProjectEnabledEvent(
                type="project.enabled",
                timestamp="2025-02-08T10:30:00+00:00",
                source="project_manager",
                project_name="",  # Empty
            )

    def test_project_enabled_event_serialization(self):
        """Serialize ProjectEnabledEvent to dict."""
        event = ProjectEnabledEvent(
            type="project.enabled",
            timestamp="2025-02-08T10:30:00+00:00",
            source="project_manager",
            project_name="api-service",
        )
        data = event.to_dict()

        assert data["type"] == "project.enabled"
        assert data["project_name"] == "api-service"

    def test_project_enabled_event_deserialization(self):
        """Deserialize ProjectEnabledEvent from dict."""
        data = {
            "type": "project.enabled",
            "timestamp": "2025-02-08T10:30:00+00:00",
            "source": "project_manager",
            "project_name": "api-service",
        }
        event = ProjectEnabledEvent.from_dict(data)

        assert event.project_name == "api-service"

    def test_project_enabled_event_round_trip(self):
        """Verify serialization round-trip."""
        original = ProjectEnabledEvent(
            type="project.enabled",
            timestamp="2025-02-08T10:30:00+00:00",
            source="project_manager",
            project_name="api-service",
        )

        data = original.to_dict()
        restored = ProjectEnabledEvent.from_dict(data)

        assert restored.project_name == original.project_name


class TestProjectDisabledEvent:
    """Tests for ProjectDisabledEvent validation and serialization."""

    def test_valid_project_disabled_event(self):
        """Create a valid ProjectDisabledEvent."""
        event = ProjectDisabledEvent(
            type="project.disabled",
            timestamp="2025-02-08T10:30:00+00:00",
            source="project_manager",
            project_name="deprecated-service",
        )
        assert event.project_name == "deprecated-service"

    def test_project_disabled_event_missing_project_name(self):
        """Fail when project_name is missing."""
        with pytest.raises(ValueError, match="project_name is required"):
            ProjectDisabledEvent(
                type="project.disabled",
                timestamp="2025-02-08T10:30:00+00:00",
                source="project_manager",
                project_name="",  # Empty
            )

    def test_project_disabled_event_serialization(self):
        """Serialize ProjectDisabledEvent to dict."""
        event = ProjectDisabledEvent(
            type="project.disabled",
            timestamp="2025-02-08T10:30:00+00:00",
            source="project_manager",
            project_name="deprecated-service",
        )
        data = event.to_dict()

        assert data["type"] == "project.disabled"
        assert data["project_name"] == "deprecated-service"

    def test_project_disabled_event_deserialization(self):
        """Deserialize ProjectDisabledEvent from dict."""
        data = {
            "type": "project.disabled",
            "timestamp": "2025-02-08T10:30:00+00:00",
            "source": "project_manager",
            "project_name": "deprecated-service",
        }
        event = ProjectDisabledEvent.from_dict(data)

        assert event.project_name == "deprecated-service"

    def test_project_disabled_event_round_trip(self):
        """Verify serialization round-trip."""
        original = ProjectDisabledEvent(
            type="project.disabled",
            timestamp="2025-02-08T10:30:00+00:00",
            source="project_manager",
            project_name="deprecated-service",
        )

        data = original.to_dict()
        restored = ProjectDisabledEvent.from_dict(data)

        assert restored.project_name == original.project_name


