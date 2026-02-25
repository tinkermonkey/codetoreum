"""Unit tests for WorkspaceContext value object."""

import pytest

from codetoreum.domain.workspace_context import (
    WorkspaceContext,
    WorkspaceType,
)

try:
    from dataclasses import FrozenInstanceError
except ImportError:
    FrozenInstanceError = AttributeError  # type: ignore


class TestIssueWorkspace:
    """Tests for issue-based workspace context."""

    def test_create_issue_workspace(self):
        """Test creating issue workspace context."""
        context = WorkspaceContext.for_issue(
            project_id="proj-1", work_item_id="item-1", branch_name="feature/test-branch"
        )

        assert context.workspace_type == WorkspaceType.ISSUE
        assert context.project_id == "proj-1"
        assert context.work_item_id == "item-1"
        assert context.branch_name == "feature/test-branch"
        assert context.create_pr is True
        assert context.discussion_id is None
        assert context.allow_code_changes is True
        assert context.create_commits is True
        assert context.post_comments is True

    def test_create_issue_workspace_without_pr(self):
        """Test creating issue workspace without PR creation."""
        context = WorkspaceContext.for_issue(
            project_id="proj-1",
            work_item_id="item-1",
            branch_name="feature/test-branch",
            create_pr=False,
        )

        assert context.create_pr is False
        assert context.workspace_type == WorkspaceType.ISSUE

    def test_issue_workspace_query_methods(self):
        """Test query methods on issue workspace."""
        context = WorkspaceContext.for_issue(
            project_id="proj-1", work_item_id="item-1", branch_name="feature/test-branch"
        )

        assert context.is_issue_workspace() is True
        assert context.is_discussion_workspace() is False
        assert context.can_make_code_changes() is True
        assert context.should_create_branch() is True
        assert context.should_post_to_discussion() is False

    def test_issue_workspace_with_empty_branch_name_raises_error(self):
        """Test that creating issue workspace with empty branch name raises error."""
        with pytest.raises(ValueError, match="branch_name is required"):
            WorkspaceContext.for_issue(project_id="proj-1", work_item_id="item-1", branch_name="")

    def test_issue_workspace_with_empty_project_id_raises_error(self):
        """Test that creating issue workspace with empty project ID raises error."""
        with pytest.raises(ValueError, match="project_id cannot be empty"):
            WorkspaceContext.for_issue(project_id="", work_item_id="item-1", branch_name="feature/test")

    def test_issue_workspace_with_empty_work_item_id_raises_error(self):
        """Test that creating issue workspace with empty work item ID raises error."""
        with pytest.raises(ValueError, match="work_item_id cannot be empty"):
            WorkspaceContext.for_issue(project_id="proj-1", work_item_id="", branch_name="feature/test")


class TestDiscussionWorkspace:
    """Tests for discussion-based workspace context."""

    def test_create_discussion_workspace(self):
        """Test creating discussion workspace context."""
        context = WorkspaceContext.for_discussion(
            project_id="proj-1", work_item_id="item-1", discussion_id="discussion-123"
        )

        assert context.workspace_type == WorkspaceType.DISCUSSION
        assert context.project_id == "proj-1"
        assert context.work_item_id == "item-1"
        assert context.branch_name is None
        assert context.create_pr is False
        assert context.discussion_id == "discussion-123"
        assert context.allow_code_changes is False
        assert context.create_commits is False
        assert context.post_comments is True

    def test_discussion_workspace_query_methods(self):
        """Test query methods on discussion workspace."""
        context = WorkspaceContext.for_discussion(
            project_id="proj-1", work_item_id="item-1", discussion_id="discussion-123"
        )

        assert context.is_issue_workspace() is False
        assert context.is_discussion_workspace() is True
        assert context.can_make_code_changes() is False
        assert context.should_create_branch() is False
        assert context.should_post_to_discussion() is True

    def test_discussion_workspace_with_empty_discussion_id_raises_error(self):
        """Test that creating discussion workspace with empty discussion ID raises error."""
        with pytest.raises(ValueError, match="discussion_id is required"):
            WorkspaceContext.for_discussion(project_id="proj-1", work_item_id="item-1", discussion_id="")

    def test_discussion_workspace_with_empty_project_id_raises_error(self):
        """Test that creating discussion workspace with empty project ID raises error."""
        with pytest.raises(ValueError, match="project_id cannot be empty"):
            WorkspaceContext.for_discussion(project_id="", work_item_id="item-1", discussion_id="discussion-123")


class TestHybridWorkspace:
    """Tests for hybrid workspace context."""

    def test_create_hybrid_workspace(self):
        """Test creating hybrid workspace context."""
        context = WorkspaceContext.for_hybrid(
            project_id="proj-1",
            work_item_id="item-1",
            branch_name="feature/test-branch",
            discussion_id="discussion-123",
        )

        assert context.workspace_type == WorkspaceType.HYBRID
        assert context.project_id == "proj-1"
        assert context.work_item_id == "item-1"
        assert context.branch_name == "feature/test-branch"
        assert context.create_pr is True
        assert context.discussion_id == "discussion-123"
        assert context.allow_code_changes is True
        assert context.create_commits is True
        assert context.post_comments is True

    def test_hybrid_workspace_query_methods(self):
        """Test query methods on hybrid workspace."""
        context = WorkspaceContext.for_hybrid(
            project_id="proj-1",
            work_item_id="item-1",
            branch_name="feature/test-branch",
            discussion_id="discussion-123",
        )

        assert context.is_issue_workspace() is True
        assert context.is_discussion_workspace() is True
        assert context.can_make_code_changes() is True
        assert context.should_create_branch() is True
        assert context.should_post_to_discussion() is True

    def test_hybrid_workspace_with_empty_branch_name_raises_error(self):
        """Test that creating hybrid workspace with empty branch name raises error."""
        with pytest.raises(ValueError, match="branch_name is required"):
            WorkspaceContext.for_hybrid(
                project_id="proj-1",
                work_item_id="item-1",
                branch_name="",
                discussion_id="discussion-123",
            )

    def test_hybrid_workspace_with_empty_discussion_id_raises_error(self):
        """Test that creating hybrid workspace with empty discussion ID raises error."""
        with pytest.raises(ValueError, match="discussion_id is required"):
            WorkspaceContext.for_hybrid(
                project_id="proj-1",
                work_item_id="item-1",
                branch_name="feature/test",
                discussion_id="",
            )


class TestWorkspaceTypeEnum:
    """Tests for WorkspaceType enum."""

    def test_workspace_type_values(self):
        """Test WorkspaceType enum values."""
        assert WorkspaceType.ISSUE.value == "issue"
        assert WorkspaceType.DISCUSSION.value == "discussion"
        assert WorkspaceType.HYBRID.value == "hybrid"

    def test_workspace_type_comparison(self):
        """Test WorkspaceType enum comparison."""
        issue_type = WorkspaceType.ISSUE
        discussion_type = WorkspaceType.DISCUSSION
        assert issue_type == WorkspaceType.ISSUE
        assert issue_type != discussion_type


class TestImmutability:
    """Tests for value object immutability."""

    def test_workspace_context_is_immutable(self):
        """Test that WorkspaceContext is immutable (frozen)."""
        context = WorkspaceContext.for_issue(project_id="proj-1", work_item_id="item-1", branch_name="feature/test")

        # Attempting to modify frozen dataclass fields should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            object.__setattr__(context, "branch_name", "new-branch")

        with pytest.raises(FrozenInstanceError):
            object.__setattr__(context, "create_pr", False)

        with pytest.raises(FrozenInstanceError):
            object.__setattr__(context, "workspace_type", WorkspaceType.ISSUE)


class TestEquality:
    """Tests for value object equality."""

    def test_equal_workspaces_are_equal(self):
        """Test that workspaces with same values are equal."""
        context1 = WorkspaceContext.for_issue(
            project_id="proj-1", work_item_id="item-1", branch_name="feature/test", create_pr=True
        )
        context2 = WorkspaceContext.for_issue(
            project_id="proj-1", work_item_id="item-1", branch_name="feature/test", create_pr=True
        )

        assert context1 == context2
        assert hash(context1) == hash(context2)

    def test_different_workspaces_are_not_equal(self):
        """Test that workspaces with different values are not equal."""
        context1 = WorkspaceContext.for_issue(project_id="proj-1", work_item_id="item-1", branch_name="feature/test")
        context2 = WorkspaceContext.for_issue(project_id="proj-2", work_item_id="item-1", branch_name="feature/test")

        assert context1 != context2

    def test_issue_and_discussion_workspaces_are_not_equal(self):
        """Test that different workspace types are not equal."""
        issue_context = WorkspaceContext.for_issue(
            project_id="proj-1", work_item_id="item-1", branch_name="feature/test"
        )
        discussion_context = WorkspaceContext.for_discussion(
            project_id="proj-1", work_item_id="item-1", discussion_id="discussion-123"
        )

        assert issue_context != discussion_context


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_workspace_with_whitespace_only_project_id_raises_error(self):
        """Test that workspace with whitespace-only project ID raises error."""
        with pytest.raises(ValueError, match="project_id cannot be empty"):
            WorkspaceContext.for_issue(project_id="   ", work_item_id="item-1", branch_name="feature/test")

    def test_workspace_with_whitespace_only_work_item_id_raises_error(self):
        """Test that workspace with whitespace-only work item ID raises error."""
        with pytest.raises(ValueError, match="work_item_id cannot be empty"):
            WorkspaceContext.for_issue(project_id="proj-1", work_item_id="   ", branch_name="feature/test")

    def test_workspace_with_special_characters_in_branch_name(self):
        """Test workspace with special characters in branch name."""
        context = WorkspaceContext.for_issue(
            project_id="proj-1",
            work_item_id="item-1",
            branch_name="feature/issue-123-add-feature_with-underscores",
        )

        assert context.branch_name == "feature/issue-123-add-feature_with-underscores"

    def test_workspace_with_long_ids(self):
        """Test workspace with very long IDs."""
        long_id = "a" * 1000
        context = WorkspaceContext.for_issue(project_id=long_id, work_item_id=long_id, branch_name="feature/test")

        assert context.project_id == long_id
        assert context.work_item_id == long_id
