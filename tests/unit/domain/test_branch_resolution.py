"""Unit tests for BranchResolution value object and branch resolution events.

Tests cover:
- BranchResolution value object instantiation, immutability, and validation
- BranchResolvedEvent, BranchReusedEvent, BranchResolutionCreatedEvent serialization
- Field validation and error handling
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from codetoreum.domain.events.branch_events import (
    BranchResolutionCreatedEvent,
    BranchResolvedEvent,
    BranchReusedEvent,
)
from codetoreum.domain.exceptions import DomainError
from codetoreum.domain.value_objects import BranchResolution

# =============================================================================
# BranchResolution Value Object Tests
# =============================================================================


class TestBranchResolutionInstantiation:
    """Tests for BranchResolution instantiation."""

    def test_create_with_reuse_action(self):
        """Test creating resolution with reuse action."""
        resolution = BranchResolution(
            action="reuse",
            branch_name="feature/issue-123-fix-auth",
            confidence=0.95,
            reason="Exact match found for issue #123",
            resolution_strategy="exact_match",
            parent_issue_id=None,
        )

        assert resolution.action == "reuse"
        assert resolution.branch_name == "feature/issue-123-fix-auth"
        assert resolution.confidence == 0.95
        assert resolution.reason == "Exact match found for issue #123"
        assert resolution.parent_issue_id is None
        assert resolution.resolution_strategy == "exact_match"

    def test_create_with_create_action(self):
        """Test creating resolution with create action."""
        resolution = BranchResolution(
            action="create",
            branch_name="feature/issue-124-new-feature",
            confidence=1.0,
            reason="No existing branch found, creating new",
            resolution_strategy="new",
            parent_issue_id=None,
        )

        assert resolution.action == "create"
        assert resolution.branch_name == "feature/issue-124-new-feature"
        assert resolution.confidence == 1.0
        assert resolution.resolution_strategy == "new"

    def test_create_with_parent_issue(self):
        """Test creating resolution from parent issue."""
        resolution = BranchResolution(
            action="reuse",
            branch_name="feature/issue-100-parent-task",
            confidence=0.95,
            reason="Parent issue has existing branch",
            resolution_strategy="parent_issue",
            parent_issue_id="100",
        )

        assert resolution.parent_issue_id == "100"
        assert resolution.resolution_strategy == "parent_issue"

    def test_create_with_sibling_strategy(self):
        """Test creating resolution using sibling strategy."""
        resolution = BranchResolution(
            action="reuse",
            branch_name="feature/issue-101-sibling-task",
            confidence=0.9,
            reason="Sibling issue already has working branch",
            resolution_strategy="sibling",
            parent_issue_id="100",
        )

        assert resolution.resolution_strategy == "sibling"

    def test_create_with_fuzzy_strategy(self):
        """Test creating resolution using fuzzy matching."""
        resolution = BranchResolution(
            action="reuse",
            branch_name="feature/auth-improvements",
            confidence=0.65,
            reason="Fuzzy match on branch name keywords",
            resolution_strategy="fuzzy",
            parent_issue_id=None,
        )

        assert resolution.confidence == 0.65
        assert resolution.resolution_strategy == "fuzzy"

    def test_all_valid_actions(self):
        """Test that both valid actions are accepted."""
        # Test create
        resolution_create = BranchResolution(
            action="create",
            branch_name="feature/test",
            confidence=0.5,
            reason="test",
            resolution_strategy="new",
        )
        assert resolution_create.action == "create"

        # Test reuse
        resolution_reuse = BranchResolution(
            action="reuse",
            branch_name="feature/test",
            confidence=0.5,
            reason="test",
            resolution_strategy="exact_match",
        )
        assert resolution_reuse.action == "reuse"

    def test_empty_branch_name(self):
        """Test that empty branch_name raises DomainError."""
        with pytest.raises(DomainError, match="branch_name cannot be empty"):
            BranchResolution(
                action="create",
                branch_name="",
                confidence=0.5,
                reason="test",
                resolution_strategy="new",
            )

    def test_whitespace_only_branch_name(self):
        """Test that whitespace-only branch_name raises DomainError."""
        with pytest.raises(DomainError, match="branch_name cannot be empty"):
            BranchResolution(
                action="create",
                branch_name="   ",
                confidence=0.5,
                reason="test",
                resolution_strategy="new",
            )

    def test_confidence_below_range(self):
        """Test that confidence below 0.0 raises DomainError."""
        with pytest.raises(DomainError, match="confidence must be between 0.0 and 1.0"):
            BranchResolution(
                action="create",
                branch_name="feature/test",
                confidence=-0.1,
                reason="test",
                resolution_strategy="new",
            )

    def test_confidence_above_range(self):
        """Test that confidence above 1.0 raises DomainError."""
        with pytest.raises(DomainError, match="confidence must be between 0.0 and 1.0"):
            BranchResolution(
                action="create",
                branch_name="feature/test",
                confidence=1.1,
                reason="test",
                resolution_strategy="new",
            )

    def test_confidence_at_boundary_0(self):
        """Test that confidence at 0.0 is valid."""
        resolution = BranchResolution(
            action="create",
            branch_name="feature/test",
            confidence=0.0,
            reason="test",
            resolution_strategy="new",
        )
        assert resolution.confidence == 0.0

    def test_confidence_at_boundary_1(self):
        """Test that confidence at 1.0 is valid."""
        resolution = BranchResolution(
            action="create",
            branch_name="feature/test",
            confidence=1.0,
            reason="test",
            resolution_strategy="new",
        )
        assert resolution.confidence == 1.0

    def test_empty_reason(self):
        """Test that empty reason raises DomainError."""
        with pytest.raises(DomainError, match="reason cannot be empty"):
            BranchResolution(
                action="create",
                branch_name="feature/test",
                confidence=0.5,
                reason="",
                resolution_strategy="new",
            )

    def test_whitespace_only_reason(self):
        """Test that whitespace-only reason raises DomainError."""
        with pytest.raises(DomainError, match="reason cannot be empty"):
            BranchResolution(
                action="create",
                branch_name="feature/test",
                confidence=0.5,
                reason="   ",
                resolution_strategy="new",
            )

    def test_invalid_resolution_strategy(self):
        """Test that invalid resolution_strategy raises DomainError."""
        with pytest.raises(DomainError, match="resolution_strategy must be one of"):
            BranchResolution(
                action="create",
                branch_name="feature/test",
                confidence=0.5,
                reason="test",
                resolution_strategy="invalid",
            )

    def test_all_valid_resolution_strategies(self):
        """Test that all valid strategies are accepted with correct action."""
        # Test reuse strategies
        reuse_strategies = ["exact_match", "parent_issue", "sibling", "fuzzy"]
        for strategy in reuse_strategies:
            resolution = BranchResolution(
                action="reuse",
                branch_name="feature/test",
                confidence=0.5,
                reason="test",
                resolution_strategy=strategy,
            )
            assert resolution.resolution_strategy == strategy

        # Test create strategy
        resolution = BranchResolution(
            action="create",
            branch_name="feature/test",
            confidence=0.5,
            reason="test",
            resolution_strategy="new",
        )
        assert resolution.resolution_strategy == "new"


class TestBranchResolutionCrossFieldValidation:
    """Tests for cross-field validation between action and resolution_strategy."""

    def test_create_action_with_exact_match_fails(self):
        """Test that action='create' with resolution_strategy='exact_match' fails."""
        with pytest.raises(DomainError, match="action='create' requires resolution_strategy='new'"):
            BranchResolution(
                action="create",
                branch_name="feature/test",
                confidence=0.5,
                reason="test",
                resolution_strategy="exact_match",
            )

    def test_create_action_with_parent_issue_fails(self):
        """Test that action='create' with resolution_strategy='parent_issue' fails."""
        with pytest.raises(DomainError, match="action='create' requires resolution_strategy='new'"):
            BranchResolution(
                action="create",
                branch_name="feature/test",
                confidence=0.5,
                reason="test",
                resolution_strategy="parent_issue",
            )

    def test_create_action_with_sibling_fails(self):
        """Test that action='create' with resolution_strategy='sibling' fails."""
        with pytest.raises(DomainError, match="action='create' requires resolution_strategy='new'"):
            BranchResolution(
                action="create",
                branch_name="feature/test",
                confidence=0.5,
                reason="test",
                resolution_strategy="sibling",
            )

    def test_create_action_with_fuzzy_fails(self):
        """Test that action='create' with resolution_strategy='fuzzy' fails."""
        with pytest.raises(DomainError, match="action='create' requires resolution_strategy='new'"):
            BranchResolution(
                action="create",
                branch_name="feature/test",
                confidence=0.5,
                reason="test",
                resolution_strategy="fuzzy",
            )

    def test_reuse_action_with_new_fails(self):
        """Test that action='reuse' with resolution_strategy='new' fails."""
        with pytest.raises(DomainError, match="action='reuse' cannot use resolution_strategy='new'"):
            BranchResolution(
                action="reuse",
                branch_name="feature/test",
                confidence=0.5,
                reason="test",
                resolution_strategy="new",
            )

    def test_create_action_with_new_succeeds(self):
        """Test that action='create' with resolution_strategy='new' succeeds."""
        resolution = BranchResolution(
            action="create",
            branch_name="feature/test",
            confidence=0.5,
            reason="test",
            resolution_strategy="new",
        )
        assert resolution.action == "create"
        assert resolution.resolution_strategy == "new"

    def test_reuse_action_with_exact_match_succeeds(self):
        """Test that action='reuse' with resolution_strategy='exact_match' succeeds."""
        resolution = BranchResolution(
            action="reuse",
            branch_name="feature/test",
            confidence=0.5,
            reason="test",
            resolution_strategy="exact_match",
        )
        assert resolution.action == "reuse"
        assert resolution.resolution_strategy == "exact_match"

    def test_reuse_action_with_parent_issue_succeeds(self):
        """Test that action='reuse' with resolution_strategy='parent_issue' succeeds."""
        resolution = BranchResolution(
            action="reuse",
            branch_name="feature/test",
            confidence=0.5,
            reason="test",
            resolution_strategy="parent_issue",
        )
        assert resolution.action == "reuse"
        assert resolution.resolution_strategy == "parent_issue"

    def test_reuse_action_with_sibling_succeeds(self):
        """Test that action='reuse' with resolution_strategy='sibling' succeeds."""
        resolution = BranchResolution(
            action="reuse",
            branch_name="feature/test",
            confidence=0.5,
            reason="test",
            resolution_strategy="sibling",
        )
        assert resolution.action == "reuse"
        assert resolution.resolution_strategy == "sibling"

    def test_reuse_action_with_fuzzy_succeeds(self):
        """Test that action='reuse' with resolution_strategy='fuzzy' succeeds."""
        resolution = BranchResolution(
            action="reuse",
            branch_name="feature/test",
            confidence=0.5,
            reason="test",
            resolution_strategy="fuzzy",
        )
        assert resolution.action == "reuse"
        assert resolution.resolution_strategy == "fuzzy"


class TestBranchResolutionImmutability:
    """Tests for BranchResolution immutability (frozen dataclass)."""

    def test_immutable_action(self):
        """Test that action field cannot be modified."""
        resolution = BranchResolution(
            action="create",
            branch_name="feature/test",
            confidence=0.5,
            reason="test",
            resolution_strategy="new",
        )

        with pytest.raises(AttributeError):  # FrozenInstanceError for frozen dataclass
            resolution.action = "reuse"  # type: ignore

    def test_immutable_branch_name(self):
        """Test that branch_name field cannot be modified."""
        resolution = BranchResolution(
            action="create",
            branch_name="feature/test",
            confidence=0.5,
            reason="test",
            resolution_strategy="new",
        )

        with pytest.raises(AttributeError):
            resolution.branch_name = "feature/other"  # type: ignore

    def test_immutable_confidence(self):
        """Test that confidence field cannot be modified."""
        resolution = BranchResolution(
            action="create",
            branch_name="feature/test",
            confidence=0.5,
            reason="test",
            resolution_strategy="new",
        )

        with pytest.raises(AttributeError):
            resolution.confidence = 0.9  # type: ignore

    def test_immutable_reason(self):
        """Test that reason field cannot be modified."""
        resolution = BranchResolution(
            action="create",
            branch_name="feature/test",
            confidence=0.5,
            reason="test",
            resolution_strategy="new",
        )

        with pytest.raises(AttributeError):
            resolution.reason = "modified reason"  # type: ignore

    def test_immutable_parent_issue_id(self):
        """Test that parent_issue_id field cannot be modified."""
        resolution = BranchResolution(
            action="create",
            branch_name="feature/test",
            confidence=0.5,
            reason="test",
            resolution_strategy="new",
            parent_issue_id="123",
        )

        with pytest.raises(AttributeError):
            resolution.parent_issue_id = "456"  # type: ignore

    def test_immutable_resolution_strategy(self):
        """Test that resolution_strategy field cannot be modified."""
        resolution = BranchResolution(
            action="create",
            branch_name="feature/test",
            confidence=0.5,
            reason="test",
            resolution_strategy="new",
        )

        with pytest.raises(AttributeError):
            resolution.resolution_strategy = "exact_match"  # type: ignore


class TestBranchResolutionSerialization:
    """Tests for BranchResolution serialization/deserialization."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        resolution = BranchResolution(
            action="reuse",
            branch_name="feature/issue-123",
            confidence=0.95,
            reason="Exact match found",
            resolution_strategy="exact_match",
            parent_issue_id="100",
        )

        data = resolution.to_dict()

        assert data["action"] == "reuse"
        assert data["branch_name"] == "feature/issue-123"
        assert data["confidence"] == 0.95
        assert data["reason"] == "Exact match found"
        assert data["parent_issue_id"] == "100"
        assert data["resolution_strategy"] == "exact_match"

    def test_to_dict_with_none_parent_issue(self):
        """Test that None parent_issue_id is preserved in dict."""
        resolution = BranchResolution(
            action="create",
            branch_name="feature/test",
            confidence=1.0,
            reason="Creating new",
            resolution_strategy="new",
            parent_issue_id=None,
        )

        data = resolution.to_dict()
        assert data["parent_issue_id"] is None

    def test_from_dict_valid_data(self):
        """Test deserialization from valid dictionary."""
        data = {
            "action": "reuse",
            "branch_name": "feature/issue-123",
            "confidence": 0.95,
            "reason": "Exact match found",
            "parent_issue_id": "100",
            "resolution_strategy": "exact_match",
        }

        resolution = BranchResolution.from_dict(data)

        assert resolution.action == "reuse"
        assert resolution.branch_name == "feature/issue-123"
        assert resolution.confidence == 0.95
        assert resolution.reason == "Exact match found"
        assert resolution.parent_issue_id == "100"
        assert resolution.resolution_strategy == "exact_match"

    def test_from_dict_missing_action(self):
        """Test that missing action raises ValueError with exception chaining."""
        data = {
            "branch_name": "feature/test",
            "confidence": 0.5,
            "reason": "test",
            "resolution_strategy": "new",
        }

        with pytest.raises(ValueError, match="Missing required field") as exc_info:
            BranchResolution.from_dict(data)
        # Verify exception chaining is preserved
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, KeyError)

    def test_from_dict_missing_branch_name(self):
        """Test that missing branch_name raises ValueError."""
        data = {
            "action": "create",
            "confidence": 0.5,
            "reason": "test",
            "resolution_strategy": "new",
        }

        with pytest.raises(ValueError, match="Missing required field"):
            BranchResolution.from_dict(data)

    def test_from_dict_missing_confidence(self):
        """Test that missing confidence raises ValueError."""
        data = {
            "action": "create",
            "branch_name": "feature/test",
            "reason": "test",
            "resolution_strategy": "new",
        }

        with pytest.raises(ValueError, match="Missing required field"):
            BranchResolution.from_dict(data)

    def test_from_dict_missing_reason(self):
        """Test that missing reason raises ValueError."""
        data = {
            "action": "create",
            "branch_name": "feature/test",
            "confidence": 0.5,
            "resolution_strategy": "new",
        }

        with pytest.raises(ValueError, match="Missing required field"):
            BranchResolution.from_dict(data)

    def test_from_dict_missing_resolution_strategy(self):
        """Test that missing resolution_strategy raises ValueError."""
        data = {
            "action": "create",
            "branch_name": "feature/test",
            "confidence": 0.5,
            "reason": "test",
        }

        # This should fail since resolution_strategy is now required
        with pytest.raises(ValueError, match="resolution_strategy"):
            BranchResolution.from_dict(data)

    def test_from_dict_with_optional_parent_issue(self):
        """Test that optional parent_issue_id can be provided."""
        data = {
            "action": "create",
            "branch_name": "feature/test",
            "confidence": 0.5,
            "reason": "test",
            "parent_issue_id": "123",
            "resolution_strategy": "new",
        }

        resolution = BranchResolution.from_dict(data)
        assert resolution.parent_issue_id == "123"

    def test_from_dict_without_optional_parent_issue(self):
        """Test that missing parent_issue_id defaults to None."""
        data = {
            "action": "create",
            "branch_name": "feature/test",
            "confidence": 0.5,
            "reason": "test",
            "resolution_strategy": "new",
        }

        resolution = BranchResolution.from_dict(data)
        assert resolution.parent_issue_id is None

    def test_round_trip_serialization(self):
        """Test serialization and deserialization round-trip."""
        original = BranchResolution(
            action="reuse",
            branch_name="feature/issue-123-complex-fix",
            confidence=0.87,
            reason="Fuzzy keyword match on existing branch",
            resolution_strategy="fuzzy",
            parent_issue_id="100",
        )

        serialized = original.to_dict()
        deserialized = BranchResolution.from_dict(serialized)

        assert deserialized.action == original.action
        assert deserialized.branch_name == original.branch_name
        assert deserialized.confidence == original.confidence
        assert deserialized.reason == original.reason
        assert deserialized.parent_issue_id == original.parent_issue_id
        assert deserialized.resolution_strategy == original.resolution_strategy


# =============================================================================
# BranchResolvedEvent Tests
# =============================================================================


class TestBranchResolvedEventInstantiation:
    """Tests for BranchResolvedEvent instantiation."""

    def test_create_valid_event(self):
        """Test creating a valid BranchResolvedEvent."""
        event = BranchResolvedEvent(
            type="branch.resolved",
            timestamp=datetime.now(UTC).isoformat(),
            source="branch_resolution",
            project_id="proj-1",
            issue_id="123",
            action="reuse",
            branch_name="feature/issue-123",
            confidence=0.95,
            reason="Exact match",
            parent_issue_id=None,
            resolution_strategy="exact_match",
        )

        assert event.project_id == "proj-1"
        assert event.issue_id == "123"
        assert event.action == "reuse"
        assert event.branch_name == "feature/issue-123"
        assert event.confidence == 0.95

    def test_missing_project_id(self):
        """Test that missing project_id raises ValueError."""
        with pytest.raises(ValueError, match="project_id is required"):
            BranchResolvedEvent(
                type="branch.resolved",
                timestamp=datetime.now(UTC).isoformat(),
                source="branch_resolution",
                project_id="",
                issue_id="123",
                action="create",
                branch_name="feature/test",
                confidence=1.0,
                reason="test",
                resolution_strategy="new",
            )

    def test_missing_issue_id(self):
        """Test that missing issue_id raises ValueError."""
        with pytest.raises(ValueError, match="issue_id is required"):
            BranchResolvedEvent(
                type="branch.resolved",
                timestamp=datetime.now(UTC).isoformat(),
                source="branch_resolution",
                project_id="proj-1",
                issue_id="",
                action="create",
                branch_name="feature/test",
                confidence=1.0,
                reason="test",
                resolution_strategy="new",
            )

    def test_invalid_confidence(self):
        """Test that invalid confidence raises ValueError."""
        with pytest.raises(ValueError, match="confidence must be between 0.0 and 1.0"):
            BranchResolvedEvent(
                type="branch.resolved",
                timestamp=datetime.now(UTC).isoformat(),
                source="branch_resolution",
                project_id="proj-1",
                issue_id="123",
                action="create",
                branch_name="feature/test",
                confidence=1.5,
                reason="test",
                resolution_strategy="new",
            )


class TestBranchResolvedEventSerialization:
    """Tests for BranchResolvedEvent serialization/deserialization."""

    def test_to_dict(self):
        """Test event serialization to dictionary."""
        event = BranchResolvedEvent(
            type="branch.resolved",
            timestamp=datetime.now(UTC).isoformat(),
            source="branch_resolution",
            project_id="proj-1",
            issue_id="123",
            action="reuse",
            branch_name="feature/issue-123",
            confidence=0.95,
            reason="Exact match",
            parent_issue_id=None,
            resolution_strategy="exact_match",
        )

        data = event.to_dict()

        assert data["type"] == "branch.resolved"
        assert data["source"] == "branch_resolution"
        assert data["project_id"] == "proj-1"
        assert data["issue_id"] == "123"
        assert data["action"] == "reuse"
        assert data["branch_name"] == "feature/issue-123"
        assert data["confidence"] == 0.95
        assert data["reason"] == "Exact match"
        assert data["resolution_strategy"] == "exact_match"

    def test_from_dict_valid_data(self):
        """Test event deserialization from valid dictionary."""
        timestamp = datetime.now(UTC).isoformat()
        data = {
            "type": "branch.resolved",
            "timestamp": timestamp,
            "source": "branch_resolution",
            "project_id": "proj-1",
            "issue_id": "123",
            "action": "reuse",
            "branch_name": "feature/issue-123",
            "confidence": 0.95,
            "reason": "Exact match",
            "parent_issue_id": None,
            "resolution_strategy": "exact_match",
        }

        event = BranchResolvedEvent.from_dict(data)

        assert event.project_id == "proj-1"
        assert event.issue_id == "123"
        assert event.action == "reuse"
        assert event.branch_name == "feature/issue-123"
        assert event.confidence == 0.95

    def test_from_dict_missing_project_id(self):
        """Test that missing project_id raises KeyError."""
        data = {
            "type": "branch.resolved",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "branch_resolution",
            "issue_id": "123",
            "action": "create",
            "branch_name": "feature/test",
            "confidence": 1.0,
            "reason": "test",
            "resolution_strategy": "new",
        }

        with pytest.raises(KeyError):
            BranchResolvedEvent.from_dict(data)

    def test_round_trip_serialization(self):
        """Test serialization and deserialization round-trip."""
        timestamp = datetime.now(UTC).isoformat()
        original = BranchResolvedEvent(
            type="branch.resolved",
            timestamp=timestamp,
            source="branch_resolution",
            project_id="proj-1",
            issue_id="123",
            action="reuse",
            branch_name="feature/issue-123",
            confidence=0.95,
            reason="Exact match found",
            parent_issue_id="100",
            resolution_strategy="exact_match",
        )

        serialized = original.to_dict()
        deserialized = BranchResolvedEvent.from_dict(serialized)

        assert deserialized.project_id == original.project_id
        assert deserialized.issue_id == original.issue_id
        assert deserialized.action == original.action
        assert deserialized.branch_name == original.branch_name
        assert deserialized.confidence == original.confidence


# =============================================================================
# BranchReusedEvent Tests
# =============================================================================


class TestBranchReusedEventInstantiation:
    """Tests for BranchReusedEvent instantiation."""

    def test_create_valid_event(self):
        """Test creating a valid BranchReusedEvent."""
        event = BranchReusedEvent(
            type="branch.reused",
            timestamp=datetime.now(UTC).isoformat(),
            source="branch_resolution",
            project_id="proj-1",
            issue_id="123",
            branch_name="feature/issue-123",
            confidence=0.95,
            reason="Exact match",
            parent_issue_id=None,
            resolution_strategy="exact_match",
        )

        assert event.project_id == "proj-1"
        assert event.issue_id == "123"
        assert event.branch_name == "feature/issue-123"
        assert event.confidence == 0.95

    def test_invalid_resolution_strategy_for_reuse(self):
        """Test that 'new' strategy is not allowed for BranchReusedEvent."""
        with pytest.raises(ValueError, match="resolution_strategy must be one of"):
            BranchReusedEvent(
                type="branch.reused",
                timestamp=datetime.now(UTC).isoformat(),
                source="branch_resolution",
                project_id="proj-1",
                issue_id="123",
                branch_name="feature/test",
                confidence=1.0,
                reason="test",
                parent_issue_id=None,
                resolution_strategy="new",
            )


class TestBranchReusedEventSerialization:
    """Tests for BranchReusedEvent serialization/deserialization."""

    def test_to_dict(self):
        """Test event serialization to dictionary."""
        event = BranchReusedEvent(
            type="branch.reused",
            timestamp=datetime.now(UTC).isoformat(),
            source="branch_resolution",
            project_id="proj-1",
            issue_id="123",
            branch_name="feature/issue-123",
            confidence=0.95,
            reason="Exact match",
            parent_issue_id=None,
            resolution_strategy="exact_match",
        )

        data = event.to_dict()

        assert data["type"] == "branch.reused"
        assert "action" not in data  # BranchReusedEvent doesn't have action field
        assert data["branch_name"] == "feature/issue-123"

    def test_from_dict_valid_data(self):
        """Test event deserialization from valid dictionary."""
        timestamp = datetime.now(UTC).isoformat()
        data = {
            "type": "branch.reused",
            "timestamp": timestamp,
            "source": "branch_resolution",
            "project_id": "proj-1",
            "issue_id": "123",
            "branch_name": "feature/issue-123",
            "confidence": 0.95,
            "reason": "Exact match",
            "parent_issue_id": None,
            "resolution_strategy": "exact_match",
        }

        event = BranchReusedEvent.from_dict(data)

        assert event.project_id == "proj-1"
        assert event.issue_id == "123"
        assert event.branch_name == "feature/issue-123"
        assert event.confidence == 0.95


# =============================================================================
# BranchResolutionCreatedEvent Tests
# =============================================================================


class TestBranchResolutionCreatedEventInstantiation:
    """Tests for BranchResolutionCreatedEvent instantiation."""

    def test_create_valid_event(self):
        """Test creating a valid BranchResolutionCreatedEvent."""
        event = BranchResolutionCreatedEvent(
            type="branch.created",
            timestamp=datetime.now(UTC).isoformat(),
            source="branch_resolution",
            project_id="proj-1",
            issue_id="124",
            branch_name="feature/issue-124-new-feature",
            reason="No existing branch found, creating new",
        )

        assert event.project_id == "proj-1"
        assert event.issue_id == "124"
        assert event.branch_name == "feature/issue-124-new-feature"
        assert event.reason == "No existing branch found, creating new"

    def test_missing_branch_name(self):
        """Test that missing branch_name raises ValueError."""
        with pytest.raises(ValueError, match="branch_name is required"):
            BranchResolutionCreatedEvent(
                type="branch.created",
                timestamp=datetime.now(UTC).isoformat(),
                source="branch_resolution",
                project_id="proj-1",
                issue_id="124",
                branch_name="",
                reason="test",
            )

    def test_missing_reason(self):
        """Test that missing reason raises ValueError."""
        with pytest.raises(ValueError, match="reason is required"):
            BranchResolutionCreatedEvent(
                type="branch.created",
                timestamp=datetime.now(UTC).isoformat(),
                source="branch_resolution",
                project_id="proj-1",
                issue_id="124",
                branch_name="feature/test",
                reason="",
            )


class TestBranchResolutionCreatedEventSerialization:
    """Tests for BranchResolutionCreatedEvent serialization/deserialization."""

    def test_to_dict(self):
        """Test event serialization to dictionary."""
        event = BranchResolutionCreatedEvent(
            type="branch.created",
            timestamp=datetime.now(UTC).isoformat(),
            source="branch_resolution",
            project_id="proj-1",
            issue_id="124",
            branch_name="feature/issue-124-new",
            reason="No existing branch, creating new",
        )

        data = event.to_dict()

        assert data["type"] == "branch.created"
        assert data["project_id"] == "proj-1"
        assert data["issue_id"] == "124"
        assert data["branch_name"] == "feature/issue-124-new"
        assert data["confidence"] == 1.0
        assert data["reason"] == "No existing branch, creating new"
        assert data["resolution_strategy"] == "new"

    def test_from_dict_valid_data(self):
        """Test event deserialization from valid dictionary."""
        timestamp = datetime.now(UTC).isoformat()
        data = {
            "type": "branch.created",
            "timestamp": timestamp,
            "source": "branch_resolution",
            "project_id": "proj-1",
            "issue_id": "124",
            "branch_name": "feature/issue-124-new",
            "confidence": 1.0,
            "reason": "No existing branch, creating new",
            "resolution_strategy": "new",
        }

        event = BranchResolutionCreatedEvent.from_dict(data)

        assert event.project_id == "proj-1"
        assert event.issue_id == "124"
        assert event.branch_name == "feature/issue-124-new"
        assert event.confidence == 1.0
        assert event.reason == "No existing branch, creating new"
        assert event.resolution_strategy == "new"

    def test_from_dict_missing_project_id(self):
        """Test that missing project_id raises KeyError."""
        data = {
            "type": "branch.created",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "branch_resolution",
            "issue_id": "124",
            "branch_name": "feature/test",
            "reason": "test",
        }

        with pytest.raises(KeyError):
            BranchResolutionCreatedEvent.from_dict(data)

    def test_round_trip_serialization(self):
        """Test serialization and deserialization round-trip."""
        timestamp = datetime.now(UTC).isoformat()
        original = BranchResolutionCreatedEvent(
            type="branch.created",
            timestamp=timestamp,
            source="branch_resolution",
            project_id="proj-1",
            issue_id="124",
            branch_name="feature/issue-124-comprehensive-fix",
            reason="No matching branch found, created new branch",
        )

        serialized = original.to_dict()
        deserialized = BranchResolutionCreatedEvent.from_dict(serialized)

        assert deserialized.project_id == original.project_id
        assert deserialized.issue_id == original.issue_id
        assert deserialized.branch_name == original.branch_name
        assert deserialized.confidence == original.confidence
        assert deserialized.reason == original.reason
        assert deserialized.resolution_strategy == original.resolution_strategy
