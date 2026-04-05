"""Branch resolution events for intelligent branch reuse decisions.

Events track branch resolution decisions, including when branches are reused
from existing branches or created anew, along with the reasoning behind the
decision (exact match, parent issue detection, sibling reuse, fuzzy matching, etc.).
"""

from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from .adapter_events import CodetoreumEvent

# Valid strategies for branch resolution
VALID_RESOLUTION_STRATEGIES = {"exact_match", "parent_issue", "sibling", "fuzzy", "new"}
VALID_REUSE_STRATEGIES = {"exact_match", "parent_issue", "sibling", "fuzzy"}


@dataclass(frozen=True)
class BranchResolvedEvent(CodetoreumEvent):
    """Emitted when a branch resolution is made (primary audit event).

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    This is the primary audit event emitted on every branch resolution attempt,
    regardless of outcome. Downstream handlers can filter by action (create vs.
    reuse) or subscribe to outcome-specific events (BranchReusedEvent or
    BranchResolutionCreatedEvent) for more specific handling.

    Attributes:
        type (str): Fixed to "branch.resolved"
        project_id (str): ID of the project
        issue_id (str): ID of the work item/issue for which branch was resolved
        action (Literal["create", "reuse"]): Whether to create a new branch or
               reuse an existing one
        branch_name (str): The name of the resolved branch
        confidence (float): Confidence level of the resolution (0.0-1.0)
        reason (str): Human-readable explanation of the resolution
        parent_issue_id (str | None): ID of parent issue if resolution was via
               parent issue relationship
        resolution_strategy (str): Strategy used to reach decision
               (exact_match, parent_issue, sibling, fuzzy, new)

    Example:
        >>> event = BranchResolvedEvent(
        ...     type="branch.resolved",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="branch_resolution",
        ...     project_id="proj-1",
        ...     issue_id="123",
        ...     action="reuse",
        ...     branch_name="feature/issue-123-fix-auth",
        ...     confidence=0.95,
        ...     reason="Exact match found for issue #123",
        ...     parent_issue_id=None,
        ...     resolution_strategy="exact_match"
        ... )
        >>> event.action = "create"  # ❌ Raises FrozenInstanceError
    """

    project_id: str = ""
    issue_id: str = ""
    action: Literal["create", "reuse"] = "create"
    branch_name: str = ""
    confidence: float = 0.0
    reason: str = ""
    parent_issue_id: str | None = None
    resolution_strategy: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        if not self.issue_id:
            msg = "issue_id is required"
            raise ValueError(msg)
        if not self.branch_name:
            msg = "branch_name is required"
            raise ValueError(msg)
        if not 0.0 <= self.confidence <= 1.0:
            msg = "confidence must be between 0.0 and 1.0"
            raise ValueError(msg)
        if not self.reason:
            msg = "reason is required"
            raise ValueError(msg)
        if self.resolution_strategy not in VALID_RESOLUTION_STRATEGIES:
            msg = f"resolution_strategy must be one of {VALID_RESOLUTION_STRATEGIES}, got {self.resolution_strategy}"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "project_id": self.project_id,
                "issue_id": self.issue_id,
                "action": self.action,
                "branch_name": self.branch_name,
                "confidence": self.confidence,
                "reason": self.reason,
                "parent_issue_id": self.parent_issue_id,
                "resolution_strategy": self.resolution_strategy,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "BranchResolvedEvent":
        """Deserialize from dictionary.

        Raises:
            KeyError: If required fields are missing.
        """
        return cls(
            type=data.get("type", "branch.resolved"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            project_id=data["project_id"],
            issue_id=data["issue_id"],
            action=data["action"],
            branch_name=data["branch_name"],
            confidence=data["confidence"],
            reason=data["reason"],
            parent_issue_id=data.get("parent_issue_id"),
            resolution_strategy=data["resolution_strategy"],
        )


@dataclass(frozen=True)
class BranchReusedEvent(CodetoreumEvent):
    """Emitted when an existing branch is selected (outcome-specific event).

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    This outcome-specific event is emitted when the resolution result indicates
    an existing branch should be reused. Handlers can subscribe to this event
    for actions specific to branch reuse (e.g., metrics, notifications).

    Attributes:
        type (str): Fixed to "branch.reused"
        project_id (str): ID of the project
        issue_id (str): ID of the work item/issue
        branch_name (str): Name of the branch being reused
        confidence (float): Confidence level of the decision (0.0-1.0)
        reason (str): Human-readable explanation
        parent_issue_id (str | None): ID of parent issue if resolved via parent
        resolution_strategy (str): Strategy used (exact_match, parent_issue,
               sibling, or fuzzy)

    Example:
        >>> event = BranchReusedEvent(
        ...     type="branch.reused",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="branch_resolution",
        ...     project_id="proj-1",
        ...     issue_id="123",
        ...     branch_name="feature/issue-123-fix-auth",
        ...     confidence=0.95,
        ...     reason="Exact match found for issue #123",
        ...     parent_issue_id=None,
        ...     resolution_strategy="exact_match"
        ... )
        >>> event.branch_name = "other-branch"  # ❌ Raises FrozenInstanceError
    """

    project_id: str = ""
    issue_id: str = ""
    branch_name: str = ""
    confidence: float = 0.0
    reason: str = ""
    parent_issue_id: str | None = None
    resolution_strategy: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        if not self.issue_id:
            msg = "issue_id is required"
            raise ValueError(msg)
        if not self.branch_name:
            msg = "branch_name is required"
            raise ValueError(msg)
        if not 0.0 <= self.confidence <= 1.0:
            msg = "confidence must be between 0.0 and 1.0"
            raise ValueError(msg)
        if not self.reason:
            msg = "reason is required"
            raise ValueError(msg)
        if self.resolution_strategy not in VALID_REUSE_STRATEGIES:
            msg = f"resolution_strategy must be one of {VALID_REUSE_STRATEGIES}, got {self.resolution_strategy}"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "project_id": self.project_id,
                "issue_id": self.issue_id,
                "branch_name": self.branch_name,
                "confidence": self.confidence,
                "reason": self.reason,
                "parent_issue_id": self.parent_issue_id,
                "resolution_strategy": self.resolution_strategy,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "BranchReusedEvent":
        """Deserialize from dictionary.

        Raises:
            KeyError: If required fields are missing.
        """
        return cls(
            type=data.get("type", "branch.reused"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            project_id=data["project_id"],
            issue_id=data["issue_id"],
            branch_name=data["branch_name"],
            confidence=data["confidence"],
            reason=data["reason"],
            parent_issue_id=data.get("parent_issue_id"),
            resolution_strategy=data["resolution_strategy"],
        )


@dataclass(frozen=True)
class BranchResolutionCreatedEvent(CodetoreumEvent):
    """Emitted when a new branch is created (outcome-specific event).

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    This outcome-specific event is emitted when the resolution result indicates
    a new branch should be created. Handlers can subscribe to this event for
    actions specific to branch creation (e.g., metrics, notifications).

    Attributes:
        type (str): Fixed to "branch.created"
        project_id (str): ID of the project
        issue_id (str): ID of the work item/issue for which branch was created
        branch_name (str): Name of the newly created branch
        reason (str): Human-readable explanation of why new branch was created

    Example:
        >>> event = BranchResolutionCreatedEvent(
        ...     type="branch.created",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="branch_resolution",
        ...     project_id="proj-1",
        ...     issue_id="124",
        ...     branch_name="feature/issue-124-new-feature",
        ...     reason="No existing branch found, creating new"
        ... )
        >>> event.branch_name = "other-branch"  # ❌ Raises FrozenInstanceError
    """

    project_id: str = ""
    issue_id: str = ""
    branch_name: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        if not self.issue_id:
            msg = "issue_id is required"
            raise ValueError(msg)
        if not self.branch_name:
            msg = "branch_name is required"
            raise ValueError(msg)
        if not self.reason:
            msg = "reason is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "project_id": self.project_id,
                "issue_id": self.issue_id,
                "branch_name": self.branch_name,
                "reason": self.reason,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "BranchResolutionCreatedEvent":
        """Deserialize from dictionary.

        Raises:
            KeyError: If required fields are missing.
        """
        return cls(
            type=data.get("type", "branch.created"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            project_id=data["project_id"],
            issue_id=data["issue_id"],
            branch_name=data["branch_name"],
            reason=data["reason"],
        )
