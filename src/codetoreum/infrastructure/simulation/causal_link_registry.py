"""Registry for managing causal dependencies between components in simulation mode.

A CausalLinkRegistry centralizes the management of causal dependencies between
adapters and other components. It enables:

- Registering dependencies between component types
- Validating link consistency (no cycles, orphaned links)
- Tracking data flows between adapters
- Ensuring all dependencies are properly wired

Causal linking allows simulation mode to use actual component outputs to inform
downstream decisions:
  - Container adapter test results → Repair cycle decisions
  - LLM adapter code quality → Review cycle decisions
  - Event bus subscriptions → Multiple adapter consumers

Example:
    registry = CausalLinkRegistry()

    # Register that repair cycle depends on container test results
    registry.register_dependency(
        source="ContainerAdapter",
        target="MockRepairCycleAdapter",
        link_type="test_results",
    )

    # Register event subscription
    registry.register_event_subscription(
        publisher="EventBus",
        subscriber="MockReviewCycleAdapter",
        event_type="CodeReviewStartedEvent",
    )

    # Validate consistency
    registry.validate_consistency()

    # Query dependencies
    repair_links = registry.get_links(target="MockRepairCycleAdapter")
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class LinkType(Enum):
    """Types of causal links between components."""

    TEST_RESULTS = "test_results"  # Container test output → Repair cycle
    CODE_QUALITY = "code_quality_metrics"  # LLM output → Review cycle
    DOMAIN_EVENTS = "domain_events"  # Event bus → Event subscribers
    STATE_UPDATES = "state_updates"  # State changes → Dependent components
    CUSTOM = "custom"  # Application-specific linking


@dataclass
class CausalLink:
    """Represents a causal dependency between two components."""

    source: str  # Component providing data/events
    target: str  # Component consuming data/events
    link_type: LinkType  # Type of dependency
    metadata: dict = field(default_factory=dict)  # Additional context

    def __hash__(self) -> int:
        """Allow links to be used in sets/dicts."""
        return hash((self.source, self.target, self.link_type))

    def __eq__(self, other: object) -> bool:
        """Compare links by their core identity."""
        if not isinstance(other, CausalLink):
            return False
        return (
            self.source == other.source
            and self.target == other.target
            and self.link_type == other.link_type
        )


@dataclass
class EventSubscription:
    """Represents an event subscription between publisher and subscriber."""

    publisher: str  # Component publishing events
    subscriber: str  # Component subscribing to events
    event_type: str  # Type of event (e.g., "CodeReviewStartedEvent")
    metadata: dict = field(default_factory=dict)  # Additional context

    def __hash__(self) -> int:
        """Allow subscriptions to be used in sets/dicts."""
        return hash((self.publisher, self.subscriber, self.event_type))

    def __eq__(self, other: object) -> bool:
        """Compare subscriptions by their core identity."""
        if not isinstance(other, EventSubscription):
            return False
        return (
            self.publisher == other.publisher
            and self.subscriber == other.subscriber
            and self.event_type == other.event_type
        )


class CausalLinkConsistencyError(Exception):
    """Raised when causal links violate consistency rules."""

    pass


class CausalLinkRegistry:
    """Centralized registry for causal dependencies between components.

    Manages the wiring of causal links and validates that the dependency
    graph remains consistent (no cycles, no orphaned links).
    """

    def __init__(self) -> None:
        """Initialize the registry."""
        self._links: set[CausalLink] = set()
        self._subscriptions: set[EventSubscription] = set()

    def register_dependency(
        self,
        source: str,
        target: str,
        link_type: LinkType | str,
        metadata: Optional[dict] = None,
    ) -> None:
        """Register a causal dependency between two components.

        Args:
            source: Component providing data/events
            target: Component consuming data/events
            link_type: Type of dependency (LinkType enum or string)
            metadata: Optional additional context about the link

        Raises:
            ValueError: If source and target are the same
        """
        if source == target:
            raise ValueError(
                f"Causal link cannot point to itself: {source}"
            )

        if isinstance(link_type, str):
            try:
                link_type = LinkType[link_type.upper()]
            except KeyError:
                link_type = LinkType.CUSTOM

        link = CausalLink(
            source=source,
            target=target,
            link_type=link_type,
            metadata=metadata or {},
        )
        self._links.add(link)

    def register_event_subscription(
        self,
        publisher: str,
        subscriber: str,
        event_type: str,
        metadata: Optional[dict] = None,
    ) -> None:
        """Register an event subscription.

        Args:
            publisher: Component publishing events
            subscriber: Component subscribing to events
            event_type: Type of event being subscribed to
            metadata: Optional additional context

        Raises:
            ValueError: If publisher and subscriber are the same
        """
        if publisher == subscriber:
            raise ValueError(
                f"Event subscription cannot be self-referential: {publisher}"
            )

        subscription = EventSubscription(
            publisher=publisher,
            subscriber=subscriber,
            event_type=event_type,
            metadata=metadata or {},
        )
        self._subscriptions.add(subscription)

    def get_links(
        self,
        source: Optional[str] = None,
        target: Optional[str] = None,
        link_type: Optional[LinkType] = None,
    ) -> list[CausalLink]:
        """Query causal links by filtering criteria.

        Args:
            source: Filter by source component (optional)
            target: Filter by target component (optional)
            link_type: Filter by link type (optional)

        Returns:
            List of matching links
        """
        results = []
        for link in self._links:
            if source is not None and link.source != source:
                continue
            if target is not None and link.target != target:
                continue
            if link_type is not None and link.link_type != link_type:
                continue
            results.append(link)
        return results

    def get_subscriptions(
        self,
        publisher: Optional[str] = None,
        subscriber: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> list[EventSubscription]:
        """Query event subscriptions by filtering criteria.

        Args:
            publisher: Filter by publisher component (optional)
            subscriber: Filter by subscriber component (optional)
            event_type: Filter by event type (optional)

        Returns:
            List of matching subscriptions
        """
        results = []
        for sub in self._subscriptions:
            if publisher is not None and sub.publisher != publisher:
                continue
            if subscriber is not None and sub.subscriber != subscriber:
                continue
            if event_type is not None and sub.event_type != event_type:
                continue
            results.append(sub)
        return results

    def get_all_links(self) -> list[CausalLink]:
        """Get all registered causal links."""
        return list(self._links)

    def get_all_subscriptions(self) -> list[EventSubscription]:
        """Get all registered event subscriptions."""
        return list(self._subscriptions)

    def validate_consistency(self) -> None:
        """Validate that the causal link graph is consistent.

        Checks for:
        - Cycles in dependency graph
        - Orphaned links (source or target doesn't exist)

        Raises:
            CausalLinkConsistencyError: If validation fails
        """
        # Build set of all components mentioned in links
        components = set()
        for link in self._links:
            components.add(link.source)
            components.add(link.target)

        # Check for cycles using DFS
        visited = set()
        rec_stack = set()

        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)

            # Find all outgoing edges from this node
            for link in self._links:
                if link.source == node:
                    if link.target not in visited:
                        if has_cycle(link.target):
                            return True
                    elif link.target in rec_stack:
                        return True

            rec_stack.remove(node)
            return False

        for component in components:
            if component not in visited:
                if has_cycle(component):
                    raise CausalLinkConsistencyError(
                        f"Cycle detected in causal link graph involving {component}"
                    )

    def clear(self) -> None:
        """Clear all registered links and subscriptions."""
        self._links.clear()
        self._subscriptions.clear()

    def __repr__(self) -> str:
        """String representation of the registry."""
        return (
            f"CausalLinkRegistry("
            f"links={len(self._links)}, "
            f"subscriptions={len(self._subscriptions)})"
        )
