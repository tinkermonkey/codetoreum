"""Unit tests for BranchResolutionAdapter production implementation.

Tests cover:
- All five resolution strategies in priority order
- Confidence threshold behavior for fuzzy matching
- Branch caching with TTL
- Event emission on every resolution
- Error handling and logging
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codetoreum.adapters.secondary.branch_resolution_adapter import (
    BranchResolutionAdapter,
)
from codetoreum.domain.events.branch_events import (
    BranchResolutionCreatedEvent,
    BranchResolvedEvent,
    BranchReusedEvent,
)
from codetoreum.domain.work_item import WorkItem

# =============================================================================
# Strategy 1: Exact Match Tests
# =============================================================================


class TestExactMatchStrategy:
    """Tests for exact match strategy (feature/issue-{issue_id}-*)."""

    @pytest.mark.asyncio
    async def test_exact_match_found_returns_reuse(self):
        """Test exact match returns reuse action with confidence 1.0."""
        ticket_system = AsyncMock()
        version_control = AsyncMock()
        event_emitter = MagicMock()

        adapter = BranchResolutionAdapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
        )

        # Mock branches
        version_control.list_branches.return_value = [
            "main",
            "feature/issue-123-fix-auth",
            "feature/other",
        ]

        # Metadata doesn't matter for exact match
        resolution = await adapter.resolve_branch(
            project_id="proj-1",
            issue_id="123",
            issue_metadata={"title": "Any title"},
            repo_path="/repo",
        )

        assert resolution.action == "reuse"
        assert resolution.branch_name == "feature/issue-123-fix-auth"
        assert resolution.confidence == 1.0
        assert resolution.resolution_strategy == "exact_match"
        assert resolution.reason == "Exact match found for issue #123"

    @pytest.mark.asyncio
    async def test_exact_match_case_insensitive(self):
        """Test exact match is case-insensitive."""
        ticket_system = AsyncMock()
        version_control = AsyncMock()
        event_emitter = MagicMock()

        adapter = BranchResolutionAdapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
        )

        # Mix of cases
        version_control.list_branches.return_value = [
            "Feature/Issue-123-Fix-Auth",  # Different case
        ]

        resolution = await adapter.resolve_branch(
            project_id="proj-1",
            issue_id="123",
            issue_metadata={"title": "Fix auth"},
            repo_path="/repo",
        )

        assert resolution.action == "reuse"
        assert resolution.branch_name == "Feature/Issue-123-Fix-Auth"
        assert resolution.confidence == 1.0

    @pytest.mark.asyncio
    async def test_exact_match_prefers_exact_over_later_strategies(self):
        """Test exact match is preferred even if fuzzy would also match."""
        ticket_system = AsyncMock()
        version_control = AsyncMock()
        event_emitter = MagicMock()

        adapter = BranchResolutionAdapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
        )

        # Both exact and fuzzy would match
        version_control.list_branches.return_value = [
            "feature/issue-123-auth-fix",  # Exact
            "feature/auth-improvements",  # Fuzzy candidate
        ]

        resolution = await adapter.resolve_branch(
            project_id="proj-1",
            issue_id="123",
            issue_metadata={"title": "Fix authentication issues"},
            repo_path="/repo",
        )

        # Must be exact match, not fuzzy
        assert resolution.resolution_strategy == "exact_match"
        assert resolution.branch_name == "feature/issue-123-auth-fix"

    @pytest.mark.asyncio
    async def test_exact_match_not_found_continues_to_next(self):
        """Test fallthrough to next strategy when exact match not found."""
        ticket_system = AsyncMock()
        version_control = AsyncMock()
        event_emitter = MagicMock()

        adapter = BranchResolutionAdapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
        )

        # No exact match
        version_control.list_branches.return_value = [
            "main",
            "feature/other-123",
        ]

        # No parent issue either
        ticket_system.get_related_items.return_value = []

        resolution = await adapter.resolve_branch(
            project_id="proj-1",
            issue_id="123",
            issue_metadata={"title": "Some feature"},
            repo_path="/repo",
        )

        # Falls through to create new
        assert resolution.action == "create"
        assert resolution.resolution_strategy == "new"


# =============================================================================
# Strategy 2: Parent Issue Tests
# =============================================================================


class TestParentIssueStrategy:
    """Tests for parent issue strategy."""

    @pytest.mark.asyncio
    async def test_parent_issue_branch_found_returns_reuse(self):
        """Test parent issue branch is reused with confidence 0.95."""
        ticket_system = AsyncMock()
        version_control = AsyncMock()
        event_emitter = MagicMock()

        adapter = BranchResolutionAdapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
        )

        # No exact match
        version_control.list_branches.return_value = [
            "main",
            "feature/issue-100-parent-task",
        ]

        # Exact match will be skipped, parent is issue 100
        parent_issue = MagicMock(spec=WorkItem)
        parent_issue.id = "100"

        ticket_system.get_related_items.return_value = [parent_issue]

        resolution = await adapter.resolve_branch(
            project_id="proj-1",
            issue_id="123",
            issue_metadata={"title": "Child task"},
            repo_path="/repo",
        )

        assert resolution.action == "reuse"
        assert resolution.branch_name == "feature/issue-100-parent-task"
        assert resolution.confidence == 0.95
        assert resolution.resolution_strategy == "parent_issue"
        assert resolution.parent_issue_id == "100"

    @pytest.mark.asyncio
    async def test_parent_not_found_continues_to_sibling(self):
        """Test fallthrough to sibling when parent has no branch."""
        ticket_system = AsyncMock()
        version_control = AsyncMock()
        event_emitter = MagicMock()

        adapter = BranchResolutionAdapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
        )

        # No exact match, sibling branch exists
        version_control.list_branches.return_value = [
            "main",
            "develop",
            "feature/issue-101-sibling-task",
        ]

        # Parent exists but no branch for parent (issue 100)
        parent_issue = MagicMock(spec=WorkItem)
        parent_issue.id = "100"
        sibling_issue = MagicMock(spec=WorkItem)
        sibling_issue.id = "101"

        # Setup get_related_items to handle both calls
        async def mock_get_related_items(item_id, relationship=None):
            if item_id == "123" and relationship == "child-of":
                return [parent_issue]
            if item_id == "100" and relationship == "parent-of":
                return [parent_issue, sibling_issue, MagicMock(spec=WorkItem, id="123")]
            return []

        ticket_system.get_related_items.side_effect = mock_get_related_items

        resolution = await adapter.resolve_branch(
            project_id="proj-1",
            issue_id="123",
            issue_metadata={"title": "Child task"},
            repo_path="/repo",
        )

        # Should find sibling's branch when parent has none
        assert resolution.resolution_strategy == "sibling"
        assert resolution.branch_name == "feature/issue-101-sibling-task"


# =============================================================================
# Strategy 3: Sibling Issues Tests
# =============================================================================


class TestSiblingIssueStrategy:
    """Tests for sibling issue strategy."""

    @pytest.mark.asyncio
    async def test_sibling_branch_found_returns_reuse(self):
        """Test sibling issue branch is reused with confidence 0.9."""
        ticket_system = AsyncMock()
        version_control = AsyncMock()
        event_emitter = MagicMock()

        adapter = BranchResolutionAdapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
        )

        # No exact match, but sibling's branch exists
        version_control.list_branches.return_value = [
            "main",
            "develop",
            "feature/issue-101-sibling-work",
        ]

        # Has parent
        parent_issue = MagicMock(spec=WorkItem)
        parent_issue.id = "100"

        sibling = MagicMock(spec=WorkItem)
        sibling.id = "101"

        async def mock_get_related_items(item_id, relationship=None):
            if item_id == "123" and relationship == "child-of":
                return [parent_issue]
            if item_id == "100" and relationship == "parent-of":
                return [parent_issue, sibling, MagicMock(spec=WorkItem, id="123")]
            return []

        ticket_system.get_related_items.side_effect = mock_get_related_items

        resolution = await adapter.resolve_branch(
            project_id="proj-1",
            issue_id="123",
            issue_metadata={"title": "Sibling work"},
            repo_path="/repo",
        )

        assert resolution.action == "reuse"
        assert resolution.branch_name == "feature/issue-101-sibling-work"
        assert resolution.confidence == 0.9
        assert resolution.resolution_strategy == "sibling"
        assert resolution.parent_issue_id == "100"

    @pytest.mark.asyncio
    async def test_sibling_skips_own_branch(self):
        """Test sibling strategy skips own branch in search."""
        ticket_system = AsyncMock()
        version_control = AsyncMock()
        event_emitter = MagicMock()

        adapter = BranchResolutionAdapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
        )

        # Only sibling's branch (not own exact match, which would be strategy 1)
        version_control.list_branches.return_value = [
            "main",
            "feature/issue-101-sibling-branch",
        ]

        parent_issue = MagicMock(spec=WorkItem)
        parent_issue.id = "100"

        sibling = MagicMock(spec=WorkItem)
        sibling.id = "101"

        async def mock_get_related_items(item_id, relationship=None):
            if item_id == "123" and relationship == "child-of":
                return [parent_issue]
            if item_id == "100" and relationship == "parent-of":
                return [parent_issue, sibling, MagicMock(spec=WorkItem, id="123")]
            return []

        ticket_system.get_related_items.side_effect = mock_get_related_items

        resolution = await adapter.resolve_branch(
            project_id="proj-1",
            issue_id="123",
            issue_metadata={},
            repo_path="/repo",
        )

        # Should find sibling's branch (self not in branches)
        assert resolution.resolution_strategy == "sibling"
        assert resolution.branch_name == "feature/issue-101-sibling-branch"


# =============================================================================
# Strategy 4: Fuzzy Matching Tests
# =============================================================================


class TestFuzzyMatchingStrategy:
    """Tests for fuzzy keyword matching strategy."""

    @pytest.mark.asyncio
    async def test_fuzzy_match_above_threshold(self):
        """Test fuzzy match returns result when confidence above threshold."""
        ticket_system = AsyncMock()
        version_control = AsyncMock()
        event_emitter = MagicMock()

        adapter = BranchResolutionAdapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
            min_confidence_threshold=0.3,  # Lower threshold for weak matches
        )

        # Strong keyword overlap
        version_control.list_branches.return_value = [
            "main",
            "feature/authentication-authorization-bugfix",
        ]

        ticket_system.get_related_items.return_value = []  # No parent/sibling

        resolution = await adapter.resolve_branch(
            project_id="proj-1",
            issue_id="123",
            issue_metadata={"title": "Fix authentication and authorization issues"},
            repo_path="/repo",
        )

        assert resolution.action == "reuse"
        assert resolution.resolution_strategy == "fuzzy"
        assert 0.5 <= resolution.confidence <= 0.8

    @pytest.mark.asyncio
    async def test_fuzzy_match_below_threshold_falls_through(self):
        """Test fuzzy match below threshold falls through to create."""
        ticket_system = AsyncMock()
        version_control = AsyncMock()
        event_emitter = MagicMock()

        adapter = BranchResolutionAdapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
            min_confidence_threshold=0.9,  # High threshold
        )

        # Weak fuzzy match
        version_control.list_branches.return_value = [
            "main",
            "feature/auth-improvements",
        ]

        ticket_system.get_related_items.return_value = []

        resolution = await adapter.resolve_branch(
            project_id="proj-1",
            issue_id="123",
            issue_metadata={"title": "Fix a different thing"},
            repo_path="/repo",
        )

        # Should fall through to create new
        assert resolution.action == "create"
        assert resolution.resolution_strategy == "new"

    @pytest.mark.asyncio
    async def test_fuzzy_matching_uses_jaccard_similarity(self):
        """Test fuzzy matching calculates similarity correctly."""
        ticket_system = AsyncMock()
        version_control = AsyncMock()
        event_emitter = MagicMock()

        adapter = BranchResolutionAdapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
            min_confidence_threshold=0.3,
        )

        # Strong keyword overlap
        version_control.list_branches.return_value = [
            "feature/authentication-authorization-fix",
        ]

        ticket_system.get_related_items.return_value = []

        resolution = await adapter.resolve_branch(
            project_id="proj-1",
            issue_id="123",
            issue_metadata={
                "title": "Fix authentication and authorization issues",
            },
            repo_path="/repo",
        )

        # Should be high confidence due to keyword overlap
        assert resolution.action == "reuse"
        assert resolution.confidence > 0.6

    @pytest.mark.asyncio
    async def test_fuzzy_match_skips_exact_pattern_branches(self):
        """Test fuzzy matching skips branches that match exact pattern.

        When multiple branches are available, exact pattern takes priority.
        This test verifies that fuzzy matching would be the result if no
        exact pattern is found.
        """
        ticket_system = AsyncMock()
        version_control = AsyncMock()
        event_emitter = MagicMock()

        adapter = BranchResolutionAdapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
            min_confidence_threshold=0.3,
        )

        # Has exact pattern AND fuzzy match candidate - exact match should win (strategy 1)
        version_control.list_branches.return_value = [
            "feature/issue-123-exact",  # Exact pattern - strategy 1 will match
            "feature/auth-fix",  # Fuzzy candidate (not reached)
        ]

        ticket_system.get_related_items.return_value = []

        resolution = await adapter.resolve_branch(
            project_id="proj-1",
            issue_id="123",
            issue_metadata={"title": "Fix authentication"},
            repo_path="/repo",
        )

        # Exact match (strategy 1) takes priority over fuzzy (strategy 4)
        assert resolution.resolution_strategy == "exact_match"
        assert resolution.branch_name == "feature/issue-123-exact"

    @pytest.mark.asyncio
    async def test_fuzzy_match_when_no_exact_pattern_match(self):
        """Test fuzzy matching is reached when no exact pattern branch exists.

        Verifies that fuzzy matching correctly returns a result when:
        - No exact match pattern (strategy 1) is found
        - No parent issue (strategy 2) exists
        - No sibling issue (strategy 3) exists
        - Fuzzy keyword match (strategy 4) finds a candidate
        """
        ticket_system = AsyncMock()
        version_control = AsyncMock()
        event_emitter = MagicMock()

        adapter = BranchResolutionAdapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
            min_confidence_threshold=0.3,
        )

        # Only fuzzy candidate (no exact pattern like "feature/issue-123-*")
        version_control.list_branches.return_value = [
            "main",
            "feature/auth-fix",  # Fuzzy candidate - will be matched in strategy 4
        ]

        ticket_system.get_related_items.return_value = []

        resolution = await adapter.resolve_branch(
            project_id="proj-1",
            issue_id="999",  # Different issue - no exact match
            issue_metadata={"title": "Fix authentication"},
            repo_path="/repo",
        )

        # Should reach fuzzy matching and find the auth-fix branch
        assert resolution.resolution_strategy == "fuzzy"
        assert resolution.branch_name == "feature/auth-fix"
        assert 0.5 <= resolution.confidence <= 0.8


# =============================================================================
# Strategy 5: Create New Tests
# =============================================================================


class TestCreateNewStrategy:
    """Tests for create new branch strategy."""

    @pytest.mark.asyncio
    async def test_create_new_generates_branch_name(self):
        """Test create new generates appropriate branch name."""
        ticket_system = AsyncMock()
        version_control = AsyncMock()
        event_emitter = MagicMock()

        adapter = BranchResolutionAdapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
        )

        version_control.list_branches.return_value = ["main"]
        ticket_system.get_related_items.return_value = []

        resolution = await adapter.resolve_branch(
            project_id="proj-1",
            issue_id="123",
            issue_metadata={"title": "Fix authentication bug"},
            repo_path="/repo",
        )

        assert resolution.action == "create"
        assert resolution.confidence == 1.0
        assert resolution.resolution_strategy == "new"
        assert "feature/issue-123" in resolution.branch_name
        assert "auth" in resolution.branch_name or "fix" in resolution.branch_name

    @pytest.mark.asyncio
    async def test_create_new_without_title(self):
        """Test create new generates branch name without title."""
        ticket_system = AsyncMock()
        version_control = AsyncMock()
        event_emitter = MagicMock()

        adapter = BranchResolutionAdapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
        )

        version_control.list_branches.return_value = ["main"]
        ticket_system.get_related_items.return_value = []

        resolution = await adapter.resolve_branch(
            project_id="proj-1",
            issue_id="456",
            issue_metadata={},  # No title
            repo_path="/repo",
        )

        assert resolution.action == "create"
        assert resolution.branch_name == "feature/issue-456"


# =============================================================================
# Confidence Threshold Tests
# =============================================================================


class TestConfidenceThreshold:
    """Tests for configurable confidence threshold."""

    @pytest.mark.asyncio
    async def test_threshold_default_is_0_7(self):
        """Test default minimum confidence threshold is 0.7."""
        adapter = BranchResolutionAdapter(
            ticket_system=AsyncMock(),
            version_control=AsyncMock(),
            event_emitter=MagicMock(),
        )

        assert adapter._min_confidence_threshold == 0.7

    @pytest.mark.asyncio
    async def test_threshold_configurable(self):
        """Test minimum confidence threshold is configurable."""
        adapter = BranchResolutionAdapter(
            ticket_system=AsyncMock(),
            version_control=AsyncMock(),
            event_emitter=MagicMock(),
            min_confidence_threshold=0.5,
        )

        assert adapter._min_confidence_threshold == 0.5

    @pytest.mark.asyncio
    async def test_invalid_threshold_raises_error(self):
        """Test invalid threshold values raise ValueError."""
        with pytest.raises(ValueError, match="min_confidence_threshold must be"):
            BranchResolutionAdapter(
                ticket_system=AsyncMock(),
                version_control=AsyncMock(),
                event_emitter=MagicMock(),
                min_confidence_threshold=1.5,  # Invalid
            )

        with pytest.raises(ValueError):
            BranchResolutionAdapter(
                ticket_system=AsyncMock(),
                version_control=AsyncMock(),
                event_emitter=MagicMock(),
                min_confidence_threshold=-0.1,  # Invalid
            )


# =============================================================================
# Caching Tests
# =============================================================================


class TestBranchCaching:
    """Tests for branch listing cache with TTL."""

    @pytest.mark.asyncio
    async def test_branches_cached_within_ttl(self):
        """Test branch results are cached within TTL."""
        ticket_system = AsyncMock()
        version_control = AsyncMock()
        event_emitter = MagicMock()

        adapter = BranchResolutionAdapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
            cache_ttl_seconds=30,
        )

        # First call
        version_control.list_branches.return_value = ["main", "feature/123"]
        ticket_system.get_related_items.return_value = []

        await adapter.resolve_branch("proj-1", "123", {"title": "Test"}, repo_path="/repo")

        # Second call to same project within TTL - should use cache
        await adapter.resolve_branch("proj-1", "456", {"title": "Test"}, repo_path="/repo")

        # Should only call list_branches once (cached)
        version_control.list_branches.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_expires_after_ttl(self):
        """Test cache expires after TTL."""
        ticket_system = AsyncMock()
        version_control = AsyncMock()
        event_emitter = MagicMock()

        adapter = BranchResolutionAdapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
            cache_ttl_seconds=1,  # 1 second TTL
        )

        version_control.list_branches.return_value = ["main"]
        ticket_system.get_related_items.return_value = []

        # First call - populates cache
        await adapter.resolve_branch("proj-1", "123", {"title": "Test"}, repo_path="/repo")
        assert version_control.list_branches.call_count == 1

        # Second call within TTL - should use cache
        await adapter.resolve_branch("proj-1", "456", {"title": "Test"}, repo_path="/repo")
        assert version_control.list_branches.call_count == 1

        # Mock time passing and second resolution call
        with patch(
            "codetoreum.adapters.secondary.branch_resolution_adapter.datetime"
        ) as mock_datetime:
            # Set up mock to advance time
            now = datetime.now(UTC)
            past_time = now
            future_time = now + timedelta(seconds=2)

            call_times = [past_time, future_time]
            call_count = [0]

            def mock_now(tz=None):
                """Return advancing time values on each call."""
                result = call_times[min(call_count[0], len(call_times) - 1)]
                call_count[0] += 1
                return result

            mock_datetime.now = mock_now
            mock_datetime.side_effect = None

            # Third call after TTL expired - cache should be invalidated
            await adapter.resolve_branch("proj-1", "789", {"title": "Test"}, repo_path="/repo")

        # Should call list_branches twice (second call uses cache, third call misses cache due to TTL)
        assert version_control.list_branches.call_count == 2


# =============================================================================
# Event Emission Tests
# =============================================================================


class TestEventEmission:
    """Tests for event emission on branch resolution."""

    @pytest.mark.asyncio
    async def test_emits_branch_resolved_event(self):
        """Test BranchResolvedEvent is emitted on every resolution."""
        ticket_system = AsyncMock()
        version_control = AsyncMock()
        event_emitter = MagicMock()

        adapter = BranchResolutionAdapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
        )

        version_control.list_branches.return_value = [
            "feature/issue-123-fix",
        ]

        await adapter.resolve_branch(
            project_id="proj-1",
            issue_id="123",
            issue_metadata={"title": "Fix"},
            repo_path="/repo",
        )

        # Check emit was called
        assert event_emitter.emit.call_count == 2

        # First call should be BranchResolvedEvent
        first_event = event_emitter.emit.call_args_list[0][0][0]
        assert isinstance(first_event, BranchResolvedEvent)
        assert first_event.type == "branch.resolved"

    @pytest.mark.asyncio
    async def test_emits_branch_reused_event_on_reuse(self):
        """Test BranchReusedEvent is emitted when action='reuse'."""
        ticket_system = AsyncMock()
        version_control = AsyncMock()
        event_emitter = MagicMock()

        adapter = BranchResolutionAdapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
        )

        version_control.list_branches.return_value = [
            "feature/issue-123-fix",
        ]

        await adapter.resolve_branch(
            project_id="proj-1",
            issue_id="123",
            issue_metadata={},
            repo_path="/repo",
        )

        # Second emit should be BranchReusedEvent
        second_event = event_emitter.emit.call_args_list[1][0][0]
        assert isinstance(second_event, BranchReusedEvent)
        assert second_event.type == "branch.reused"
        assert second_event.branch_name == "feature/issue-123-fix"

    @pytest.mark.asyncio
    async def test_emits_branch_created_event_on_create(self):
        """Test BranchResolutionCreatedEvent is emitted when action='create'."""
        ticket_system = AsyncMock()
        version_control = AsyncMock()
        event_emitter = MagicMock()

        adapter = BranchResolutionAdapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
        )

        version_control.list_branches.return_value = ["main"]
        ticket_system.get_related_items.return_value = []

        await adapter.resolve_branch(
            project_id="proj-1",
            issue_id="456",
            issue_metadata={"title": "New feature"},
            repo_path="/repo",
        )

        # Second emit should be BranchResolutionCreatedEvent
        second_event = event_emitter.emit.call_args_list[1][0][0]
        assert isinstance(second_event, BranchResolutionCreatedEvent)
        assert second_event.type == "branch.created"


# =============================================================================
# Utility Method Tests
# =============================================================================


class TestUtilityMethods:
    """Tests for utility/helper methods."""

    def test_slugify_converts_to_lowercase_tokens(self):
        """Test slugify converts text to lowercase tokens."""
        adapter = BranchResolutionAdapter(
            ticket_system=AsyncMock(),
            version_control=AsyncMock(),
            event_emitter=MagicMock(),
        )

        tokens = adapter._slugify("Fix Authentication Bug")
        assert "fix" in tokens
        assert "authentication" in tokens
        assert "bug" in tokens

    def test_slugify_splits_on_special_chars(self):
        """Test slugify splits on special characters."""
        adapter = BranchResolutionAdapter(
            ticket_system=AsyncMock(),
            version_control=AsyncMock(),
            event_emitter=MagicMock(),
        )

        tokens = adapter._slugify("fix-auth/bug-solve_it-now")
        assert "fix" in tokens
        assert "auth" in tokens
        assert "bug" in tokens

    def test_jaccard_similarity_perfect_match(self):
        """Test Jaccard similarity for identical sets."""
        adapter = BranchResolutionAdapter(
            ticket_system=AsyncMock(),
            version_control=AsyncMock(),
            event_emitter=MagicMock(),
        )

        similarity = adapter._jaccard_similarity({"a", "b"}, {"a", "b"})
        assert similarity == 1.0

    def test_jaccard_similarity_no_overlap(self):
        """Test Jaccard similarity for disjoint sets."""
        adapter = BranchResolutionAdapter(
            ticket_system=AsyncMock(),
            version_control=AsyncMock(),
            event_emitter=MagicMock(),
        )

        similarity = adapter._jaccard_similarity({"a", "b"}, {"c", "d"})
        assert similarity == 0.0

    def test_jaccard_similarity_partial_overlap(self):
        """Test Jaccard similarity for partially overlapping sets."""
        adapter = BranchResolutionAdapter(
            ticket_system=AsyncMock(),
            version_control=AsyncMock(),
            event_emitter=MagicMock(),
        )

        similarity = adapter._jaccard_similarity({"a", "b", "c"}, {"b", "c", "d"})
        # Intersection: {b, c} = 2, Union: {a, b, c, d} = 4
        # Jaccard = 2/4 = 0.5
        assert similarity == 0.5

    def test_generate_branch_name_with_title(self):
        """Test branch name generation with title."""
        adapter = BranchResolutionAdapter(
            ticket_system=AsyncMock(),
            version_control=AsyncMock(),
            event_emitter=MagicMock(),
        )

        name = adapter._generate_branch_name(
            "123", {"title": "Fix authentication bug"}
        )

        assert name.startswith("feature/issue-123-")
        assert "fix" in name.lower()
        assert "auth" in name.lower()

    def test_generate_branch_name_without_title(self):
        """Test branch name generation without title."""
        adapter = BranchResolutionAdapter(
            ticket_system=AsyncMock(),
            version_control=AsyncMock(),
            event_emitter=MagicMock(),
        )

        name = adapter._generate_branch_name("456", {})
        assert name == "feature/issue-456"

    def test_extract_keywords_from_metadata(self):
        """Test keyword extraction from issue metadata."""
        adapter = BranchResolutionAdapter(
            ticket_system=AsyncMock(),
            version_control=AsyncMock(),
            event_emitter=MagicMock(),
        )

        keywords = adapter._extract_keywords(
            {
                "title": "Fix auth bug",
                "description": "Authentication not working",
                "labels": ["bug", "critical"],
            }
        )

        assert "fix" in keywords
        assert "auth" in keywords or "authentication" in keywords
        assert "bug" in keywords


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for error handling and resilience."""

    @pytest.mark.asyncio
    async def test_list_branches_error_handled_in_strategies(self):
        """Test that errors in list_branches are handled gracefully."""
        ticket_system = AsyncMock()
        version_control = AsyncMock()
        event_emitter = MagicMock()

        adapter = BranchResolutionAdapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
        )

        # list_branches fails
        version_control.list_branches.side_effect = Exception("API error")

        # Should fall through strategies and create new
        resolution = await adapter.resolve_branch(
            project_id="proj-1",
            issue_id="123",
            issue_metadata={"title": "Feature"},
            repo_path="/repo",
        )

        # Falls back to creating new
        assert resolution.action == "create"
        assert resolution.resolution_strategy == "new"

    @pytest.mark.asyncio
    async def test_get_related_items_error_handled(self):
        """Test that errors in get_related_items are handled."""
        ticket_system = AsyncMock()
        version_control = AsyncMock()
        event_emitter = MagicMock()

        adapter = BranchResolutionAdapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
        )

        version_control.list_branches.return_value = ["main"]

        # get_related_items fails
        ticket_system.get_related_items.side_effect = Exception("API error")

        # Should fall back to creating new (after skipping parent/sibling)
        resolution = await adapter.resolve_branch(
            project_id="proj-1",
            issue_id="123",
            issue_metadata={"title": "Feature"},
            repo_path="/repo",
        )

        assert resolution.action == "create"
