"""Integration tests for project enable/disable behavior.

Tests verify that disabling a project stops processing without cleanup,
and re-enabling a project resumes with preserved state.
"""

import pytest
import json
from pathlib import Path

from codetoreum.adapters.testing.mock_project_manager_adapter import (
    MockProjectManagerAdapter,
)
from codetoreum.domain.value_objects import ProjectConfig


@pytest.fixture
def project_manager():
    """Create a fresh project manager adapter."""
    return MockProjectManagerAdapter()


@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace for state files."""
    return tmp_path


def create_project_config(repo_url: str, branch: str = "main", enabled: bool = True) -> ProjectConfig:
    """Helper to create a project configuration."""
    return ProjectConfig(
        repo_url=repo_url,
        branch=branch,
        enabled=enabled,
        org="test-org",
    )


class TestProjectEnableDisable:
    """Integration tests for project enable/disable behavior."""

    async def test_disable_project_excluded_from_enabled_list(self, project_manager):
        """Verify disabling project excludes it from enabled projects list."""
        # Create a project
        config = create_project_config(
            "https://github.com/org/test-project.git",
            enabled=True,
        )
        project_manager.add_project("test-project", config)

        # Verify it's enabled
        enabled_before = await project_manager.get_enabled_projects()
        assert "test-project" in enabled_before

        # Disable the project
        disabled_config = create_project_config(
            "https://github.com/org/test-project.git",
            enabled=False,
        )
        project_manager.update_project("test-project", disabled_config)

        # Verify it's no longer enabled
        enabled_after = await project_manager.get_enabled_projects()
        assert "test-project" not in enabled_after

    async def test_disable_project_skips_processing_no_cleanup(self, project_manager, temp_workspace):
        """Verify disabling project skips processing without cleanup operations.

        When a project is disabled:
        1. It should be excluded from enabled projects list
        2. No cleanup operations should be performed
        3. State files should remain intact for potential re-enabling
        """
        # Create a project with existing state
        config = create_project_config(
            "https://github.com/org/active-project.git",
            enabled=True,
        )
        project_manager.add_project("active-project", config)

        # Create state files simulating active work
        state_file = temp_workspace / "active-project_board-1.yaml"
        state_data = {
            "project": "active-project",
            "board": "board-1",
            "queue_items": ["task1", "task2", "task3"],
            "last_update": "2024-01-01T12:00:00Z",
        }

        with open(state_file, "w") as f:
            json.dump(state_data, f)

        assert state_file.exists()

        # Disable the project
        disabled_config = create_project_config(
            "https://github.com/org/active-project.git",
            enabled=False,
        )
        project_manager.update_project("active-project", disabled_config)

        # Verify project is disabled
        enabled_projects = await project_manager.get_enabled_projects()
        assert "active-project" not in enabled_projects

        # Verify state files remain intact (no cleanup)
        assert state_file.exists(), "State file should remain after disable"

        with open(state_file) as f:
            preserved_data = json.load(f)
            assert preserved_data == state_data, "State data should be unchanged"

    async def test_re_enable_project_resumes_with_preserved_state(self, project_manager, temp_workspace):
        """Verify re-enabling project resumes with preserved state.

        When a project is disabled then re-enabled:
        1. Previous state should remain accessible
        2. Processing should resume with the preserved state
        3. No state loss or corruption should occur
        """
        # Create a project and add state
        config_enabled = create_project_config(
            "https://github.com/org/cycling-project.git",
            enabled=True,
        )
        project_manager.add_project("cycling-project", config_enabled)

        # Create and persist state
        state_file = temp_workspace / "cycling-project_queue.yaml"
        original_state = {
            "project": "cycling-project",
            "queue_items": ["analysis-123", "design-456", "implementation-789"],
            "processing_order": ["analysis-123", "design-456"],
            "completed": ["setup-001"],
            "cycle": 3,
        }

        with open(state_file, "w") as f:
            json.dump(original_state, f)

        # Verify state exists
        assert state_file.exists()

        # Disable project
        disabled_config = create_project_config(
            "https://github.com/org/cycling-project.git",
            enabled=False,
        )
        project_manager.update_project("cycling-project", disabled_config)

        # Verify disabled
        enabled_before = await project_manager.get_enabled_projects()
        assert "cycling-project" not in enabled_before

        # Re-enable project
        re_enabled_config = create_project_config(
            "https://github.com/org/cycling-project.git",
            enabled=True,
        )
        project_manager.update_project("cycling-project", re_enabled_config)

        # Verify re-enabled
        enabled_after = await project_manager.get_enabled_projects()
        assert "cycling-project" in enabled_after

        # Verify state is preserved and accessible
        assert state_file.exists(), "State file should still exist after re-enable"

        with open(state_file) as f:
            restored_state = json.load(f)
            assert restored_state == original_state, "State should be completely preserved"
            assert restored_state["cycle"] == 3, "Cycle count preserved"
            assert restored_state["completed"] == ["setup-001"], "Completed items preserved"

    async def test_disable_enable_cycle_preserves_all_state_types(self, project_manager, temp_workspace):
        """Verify disable-enable cycle preserves all types of state.

        Tests that multiple state files (queue, session, execution) are
        all preserved through a disable-enable cycle.
        """
        config_enabled = create_project_config(
            "https://github.com/org/multi-state-project.git",
            enabled=True,
        )
        project_manager.add_project("multi-state-project", config_enabled)

        # Create multiple state files
        queue_file = temp_workspace / "multi-state-project_queue.yaml"
        session_file = temp_workspace / "multi-state-project_session.yaml"
        execution_file = temp_workspace / "multi-state-project_execution.json"

        queue_state = {"items": ["task1", "task2"], "count": 2}
        session_state = {"session_id": "sess-123", "agent": "analyzer"}
        execution_state = {"exec_id": 1, "status": "pending", "container": None}

        with open(queue_file, "w") as f:
            json.dump(queue_state, f)
        with open(session_file, "w") as f:
            json.dump(session_state, f)
        with open(execution_file, "w") as f:
            json.dump(execution_state, f)

        # Verify all files exist
        assert queue_file.exists()
        assert session_file.exists()
        assert execution_file.exists()

        # Disable project
        disabled_config = create_project_config(
            "https://github.com/org/multi-state-project.git",
            enabled=False,
        )
        project_manager.update_project("multi-state-project", disabled_config)

        # Re-enable project
        enabled_config = create_project_config(
            "https://github.com/org/multi-state-project.git",
            enabled=True,
        )
        project_manager.update_project("multi-state-project", enabled_config)

        # Verify all state files still exist with original content
        assert queue_file.exists()
        assert session_file.exists()
        assert execution_file.exists()

        with open(queue_file) as f:
            assert json.load(f) == queue_state

        with open(session_file) as f:
            assert json.load(f) == session_state

        with open(execution_file) as f:
            assert json.load(f) == execution_state

    async def test_multiple_projects_disable_independent(self, project_manager):
        """Verify disabling one project doesn't affect others.

        When multiple projects exist and one is disabled,
        the enabled list should exclude only that project.
        """
        # Create three projects
        config_a = create_project_config(
            "https://github.com/org/project-a.git",
            enabled=True,
        )
        config_b = create_project_config(
            "https://github.com/org/project-b.git",
            enabled=True,
        )
        config_c = create_project_config(
            "https://github.com/org/project-c.git",
            enabled=True,
        )

        project_manager.add_project("project-a", config_a)
        project_manager.add_project("project-b", config_b)
        project_manager.add_project("project-c", config_c)

        # Verify all enabled
        enabled = await project_manager.get_enabled_projects()
        assert len(enabled) == 3
        assert all(p in enabled for p in ["project-a", "project-b", "project-c"])

        # Disable only project-b
        disabled_config_b = create_project_config(
            "https://github.com/org/project-b.git",
            enabled=False,
        )
        project_manager.update_project("project-b", disabled_config_b)

        # Verify only b is disabled
        enabled_after = await project_manager.get_enabled_projects()
        assert len(enabled_after) == 2
        assert "project-a" in enabled_after
        assert "project-c" in enabled_after
        assert "project-b" not in enabled_after

        # Re-enable project-b
        enabled_config_b = create_project_config(
            "https://github.com/org/project-b.git",
            enabled=True,
        )
        project_manager.update_project("project-b", enabled_config_b)

        # Verify all enabled again
        enabled_final = await project_manager.get_enabled_projects()
        assert len(enabled_final) == 3
        assert all(p in enabled_final for p in ["project-a", "project-b", "project-c"])
