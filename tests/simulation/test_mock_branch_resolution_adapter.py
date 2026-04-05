"""Simulation tests for MockBranchResolutionAdapter.

Tests the mock branch resolution adapter for all five resolution strategies:
- exact_match: Direct issue ID match
- parent_issue: Parent issue relationship
- sibling: Sibling issue relationship
- fuzzy: Fuzzy matching on title/description
- new: Create new branch
"""

import pytest

from codetoreum.adapters.testing import MockBranchResolutionAdapter
from codetoreum.domain.value_objects import BranchResolution


class TestMockBranchResolutionAdapter:
    """Tests for MockBranchResolutionAdapter."""

    @pytest.mark.asyncio
    async def test_default_behavior_returns_create_action(self):
        """Test default behavior returns action='create' with resolution_strategy='new'."""
        adapter = MockBranchResolutionAdapter()

        result = await adapter.resolve_branch("proj-1", "123", {}, "/repo")

        assert result.action == "create"
        assert result.resolution_strategy == "new"
        assert result.branch_name == "feature/default-branch"

    @pytest.mark.asyncio
    async def test_configured_resolution_is_returned(self):
        """Test configured resolution is returned for matching project/issue pair."""
        adapter = MockBranchResolutionAdapter()

        configured = BranchResolution(
            action="reuse",
            branch_name="feature/issue-123-auth-fix",
            confidence=0.95,
            reason="Exact match found",
            resolution_strategy="exact_match",
        )
        adapter.configure_resolution("proj-1", "123", configured)

        result = await adapter.resolve_branch("proj-1", "123", {}, "/repo")

        assert result.action == "reuse"
        assert result.branch_name == "feature/issue-123-auth-fix"
        assert result.resolution_strategy == "exact_match"

    @pytest.mark.asyncio
    async def test_different_issues_get_different_resolutions(self):
        """Test different issues can have different configured resolutions."""
        adapter = MockBranchResolutionAdapter()

        config1 = BranchResolution(
            action="reuse",
            branch_name="feature/issue-1-fix",
            confidence=0.9,
            reason="Issue 1",
            resolution_strategy="exact_match",
        )
        config2 = BranchResolution(
            action="create",
            branch_name="feature/issue-2-new",
            confidence=1.0,
            reason="Issue 2",
            resolution_strategy="new",
        )

        adapter.configure_resolution("proj-1", "1", config1)
        adapter.configure_resolution("proj-1", "2", config2)

        result1 = await adapter.resolve_branch("proj-1", "1", {}, "/repo")
        result2 = await adapter.resolve_branch("proj-1", "2", {}, "/repo")

        assert result1.branch_name == "feature/issue-1-fix"
        assert result2.branch_name == "feature/issue-2-new"

    # =========================================================================
    # Test All Five Resolution Strategies
    # =========================================================================

    @pytest.mark.asyncio
    async def test_exact_match_strategy(self):
        """Test exact_match resolution strategy."""
        adapter = MockBranchResolutionAdapter()

        resolution = BranchResolution(
            action="reuse",
            branch_name="feature/issue-100-fix-auth",
            confidence=1.0,
            reason="Exact match on issue #100",
            resolution_strategy="exact_match",
        )
        adapter.configure_resolution("proj-1", "100", resolution)

        result = await adapter.resolve_branch("proj-1", "100", {}, "/repo")

        assert result.action == "reuse"
        assert result.resolution_strategy == "exact_match"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_parent_issue_strategy(self):
        """Test parent_issue resolution strategy."""
        adapter = MockBranchResolutionAdapter()

        resolution = BranchResolution(
            action="reuse",
            branch_name="feature/parent-200-child-issues",
            confidence=0.85,
            reason="Reusing parent issue branch",
            resolution_strategy="parent_issue",
            parent_issue_id="200",
        )
        adapter.configure_resolution("proj-1", "201", resolution)

        result = await adapter.resolve_branch("proj-1", "201", {}, "/repo")

        assert result.action == "reuse"
        assert result.resolution_strategy == "parent_issue"
        assert result.parent_issue_id == "200"

    @pytest.mark.asyncio
    async def test_sibling_strategy(self):
        """Test sibling resolution strategy."""
        adapter = MockBranchResolutionAdapter()

        resolution = BranchResolution(
            action="reuse",
            branch_name="feature/sibling-300-related-work",
            confidence=0.70,
            reason="Reusing sibling issue branch",
            resolution_strategy="sibling",
        )
        adapter.configure_resolution("proj-1", "302", resolution)

        result = await adapter.resolve_branch("proj-1", "302", {}, "/repo")

        assert result.action == "reuse"
        assert result.resolution_strategy == "sibling"
        assert result.confidence == 0.70

    @pytest.mark.asyncio
    async def test_fuzzy_strategy(self):
        """Test fuzzy resolution strategy."""
        adapter = MockBranchResolutionAdapter()

        resolution = BranchResolution(
            action="reuse",
            branch_name="feature/similar-title-fix-api",
            confidence=0.60,
            reason="Fuzzy match on title similarity",
            resolution_strategy="fuzzy",
        )
        adapter.configure_resolution("proj-1", "400", resolution)

        result = await adapter.resolve_branch("proj-1", "400", {}, "/repo")

        assert result.action == "reuse"
        assert result.resolution_strategy == "fuzzy"
        assert result.confidence == 0.60

    @pytest.mark.asyncio
    async def test_new_strategy(self):
        """Test new (create new branch) resolution strategy."""
        adapter = MockBranchResolutionAdapter()

        resolution = BranchResolution(
            action="create",
            branch_name="feature/issue-500-new-feature",
            confidence=1.0,
            reason="No matching branch found, creating new",
            resolution_strategy="new",
        )
        adapter.configure_resolution("proj-1", "500", resolution)

        result = await adapter.resolve_branch("proj-1", "500", {}, "/repo")

        assert result.action == "create"
        assert result.resolution_strategy == "new"
        assert result.confidence == 1.0

    # =========================================================================
    # Event Emission Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_emits_branch_resolved_event(self):
        """Test BranchResolvedEvent is emitted on resolve_branch call."""
        adapter = MockBranchResolutionAdapter()
        events = []

        adapter.on("branch.resolved", events.append)

        resolution = BranchResolution(
            action="reuse",
            branch_name="feature/issue-600",
            confidence=0.95,
            reason="Test",
            resolution_strategy="exact_match",
        )
        adapter.configure_resolution("proj-1", "600", resolution)

        await adapter.resolve_branch("proj-1", "600", {}, "/repo")

        assert len(events) == 1
        assert events[0].type == "branch.resolved"
        assert events[0].project_id == "proj-1"
        assert events[0].issue_id == "600"

    @pytest.mark.asyncio
    async def test_emits_branch_reused_event_on_reuse(self):
        """Test BranchReusedEvent is emitted when action is 'reuse'."""
        adapter = MockBranchResolutionAdapter()
        events = []

        adapter.on("branch.reused", events.append)

        resolution = BranchResolution(
            action="reuse",
            branch_name="feature/reuse-700",
            confidence=0.9,
            reason="Reusing existing",
            resolution_strategy="exact_match",
        )
        adapter.configure_resolution("proj-1", "700", resolution)

        await adapter.resolve_branch("proj-1", "700", {}, "/repo")

        assert len(events) == 1
        assert events[0].type == "branch.reused"
        assert events[0].branch_name == "feature/reuse-700"

    @pytest.mark.asyncio
    async def test_emits_branch_created_event_on_create(self):
        """Test BranchCreatedEvent is emitted when action is 'create'."""
        adapter = MockBranchResolutionAdapter()
        events = []

        adapter.on("branch.created", events.append)

        resolution = BranchResolution(
            action="create",
            branch_name="feature/new-800",
            confidence=1.0,
            reason="Creating new branch",
            resolution_strategy="new",
        )
        adapter.configure_resolution("proj-1", "800", resolution)

        await adapter.resolve_branch("proj-1", "800", {}, "/repo")

        assert len(events) == 1
        assert events[0].type == "branch.created"
        assert events[0].branch_name == "feature/new-800"

    # =========================================================================
    # Test Helper Methods
    # =========================================================================

    @pytest.mark.asyncio
    async def test_clear_configurations(self):
        """Test clearing all configurations."""
        adapter = MockBranchResolutionAdapter()

        resolution = BranchResolution(
            action="reuse",
            branch_name="feature/test",
            confidence=0.9,
            reason="Test",
            resolution_strategy="exact_match",
        )
        adapter.configure_resolution("proj-1", "900", resolution)

        assert adapter.get_configured_count() == 1

        adapter.clear_configurations()

        assert adapter.get_configured_count() == 0

        # Should now return default
        result = await adapter.resolve_branch("proj-1", "900", {}, "/repo")
        assert result.action == "create"

    @pytest.mark.asyncio
    async def test_set_default_resolution(self):
        """Test setting custom default resolution."""
        adapter = MockBranchResolutionAdapter()

        custom_default = BranchResolution(
            action="reuse",
            branch_name="feature/custom-default",
            confidence=0.8,
            reason="Custom default",
            resolution_strategy="fuzzy",
        )
        adapter.set_default_resolution(custom_default)

        # Request for unconfigured pair should return custom default
        result = await adapter.resolve_branch("proj-1", "999", {}, "/repo")

        assert result.action == "reuse"
        assert result.branch_name == "feature/custom-default"
        assert result.resolution_strategy == "fuzzy"

    # =========================================================================
    # Error Handling Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_empty_project_id_raises_error(self):
        """Test empty project_id raises ValueError."""
        adapter = MockBranchResolutionAdapter()

        with pytest.raises(ValueError, match="project_id cannot be empty"):
            await adapter.resolve_branch("", "123", {}, "/repo")

    @pytest.mark.asyncio
    async def test_empty_issue_id_raises_error(self):
        """Test empty issue_id raises ValueError."""
        adapter = MockBranchResolutionAdapter()

        with pytest.raises(ValueError, match="issue_id cannot be empty"):
            await adapter.resolve_branch("proj-1", "", {}, "/repo")

    def test_configure_with_empty_project_id_raises_error(self):
        """Test configure_resolution with empty project_id raises ValueError."""
        adapter = MockBranchResolutionAdapter()
        resolution = BranchResolution(
            action="create",
            branch_name="test",
            confidence=1.0,
            reason="test",
            resolution_strategy="new",
        )

        with pytest.raises(ValueError, match="project_id cannot be empty"):
            adapter.configure_resolution("", "123", resolution)

    def test_configure_with_empty_issue_id_raises_error(self):
        """Test configure_resolution with empty issue_id raises ValueError."""
        adapter = MockBranchResolutionAdapter()
        resolution = BranchResolution(
            action="create",
            branch_name="test",
            confidence=1.0,
            reason="test",
            resolution_strategy="new",
        )

        with pytest.raises(ValueError, match="issue_id cannot be empty"):
            adapter.configure_resolution("proj-1", "", resolution)

    # =========================================================================
    # Multiple Calls Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_multiple_calls_with_same_config(self):
        """Test multiple calls to resolve_branch with same config."""
        adapter = MockBranchResolutionAdapter()

        resolution = BranchResolution(
            action="reuse",
            branch_name="feature/multi",
            confidence=0.9,
            reason="Multi call test",
            resolution_strategy="exact_match",
        )
        adapter.configure_resolution("proj-1", "1000", resolution)

        result1 = await adapter.resolve_branch("proj-1", "1000", {}, "/repo")
        result2 = await adapter.resolve_branch("proj-1", "1000", {}, "/repo")

        assert result1.branch_name == result2.branch_name
        assert result1.action == result2.action

    @pytest.mark.asyncio
    async def test_multiple_resolutions_in_sequence(self):
        """Test resolving multiple different issues in sequence."""
        adapter = MockBranchResolutionAdapter()

        resolutions = []
        for i in range(5):
            res = BranchResolution(
                action="reuse" if i % 2 == 0 else "create",
                branch_name=f"feature/issue-{i}",
                confidence=0.9,
                reason=f"Issue {i}",
                resolution_strategy="exact_match" if i % 2 == 0 else "new",
            )
            adapter.configure_resolution("proj-1", str(i), res)
            resolutions.append(res)

        for i in range(5):
            result = await adapter.resolve_branch("proj-1", str(i), {}, "/repo")
            assert result.branch_name == resolutions[i].branch_name
            assert result.action == resolutions[i].action
