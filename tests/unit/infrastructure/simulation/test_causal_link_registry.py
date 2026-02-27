"""Tests for CausalLinkRegistry."""

import pytest

from codetoreum.infrastructure.simulation.causal_link_registry import (
    CausalLink,
    CausalLinkConsistencyError,
    CausalLinkRegistry,
    EventSubscription,
    LinkType,
)


class TestCausalLinkRegistry:
    """Test suite for CausalLinkRegistry."""

    def test_register_dependency(self) -> None:
        """Test registering a basic dependency."""
        registry = CausalLinkRegistry()
        registry.register_dependency(
            source="ContainerAdapter",
            target="RepairCycleAdapter",
            link_type=LinkType.TEST_RESULTS,
        )

        links = registry.get_links(source="ContainerAdapter")
        assert len(links) == 1
        assert links[0].source == "ContainerAdapter"
        assert links[0].target == "RepairCycleAdapter"
        assert links[0].link_type == LinkType.TEST_RESULTS

    def test_register_dependency_with_string_link_type(self) -> None:
        """Test registering dependency with string link type."""
        registry = CausalLinkRegistry()
        registry.register_dependency(
            source="SourceA",
            target="TargetA",
            link_type="test_results",
        )

        links = registry.get_all_links()
        assert len(links) == 1
        assert links[0].link_type == LinkType.TEST_RESULTS

    def test_register_dependency_with_invalid_string_link_type(self) -> None:
        """Test registering with invalid string link type defaults to CUSTOM."""
        registry = CausalLinkRegistry()
        registry.register_dependency(
            source="SourceA",
            target="TargetA",
            link_type="unknown_type",
        )

        links = registry.get_all_links()
        assert links[0].link_type == LinkType.CUSTOM

    def test_register_dependency_with_metadata(self) -> None:
        """Test registering dependency with metadata."""
        registry = CausalLinkRegistry()
        registry.register_dependency(
            source="Adapter1",
            target="Adapter2",
            link_type=LinkType.STATE_UPDATES,
            metadata={"version": "1.0", "priority": "high"},
        )

        links = registry.get_all_links()
        assert links[0].metadata == {"version": "1.0", "priority": "high"}

    def test_register_dependency_self_referential_raises(self) -> None:
        """Test that self-referential links raise ValueError."""
        registry = CausalLinkRegistry()
        with pytest.raises(ValueError, match="cannot point to itself"):
            registry.register_dependency(
                source="SameAdapter",
                target="SameAdapter",
                link_type=LinkType.TEST_RESULTS,
            )

    def test_register_event_subscription(self) -> None:
        """Test registering event subscription."""
        registry = CausalLinkRegistry()
        registry.register_event_subscription(
            publisher="EventBus",
            subscriber="ReviewAdapter",
            event_type="CodeReviewStartedEvent",
        )

        subs = registry.get_subscriptions(publisher="EventBus")
        assert len(subs) == 1
        assert subs[0].publisher == "EventBus"
        assert subs[0].subscriber == "ReviewAdapter"
        assert subs[0].event_type == "CodeReviewStartedEvent"

    def test_register_event_subscription_with_metadata(self) -> None:
        """Test registering subscription with metadata."""
        registry = CausalLinkRegistry()
        registry.register_event_subscription(
            publisher="EventBus",
            subscriber="Adapter",
            event_type="SomeEvent",
            metadata={"priority": "critical"},
        )

        subs = registry.get_all_subscriptions()
        assert subs[0].metadata == {"priority": "critical"}

    def test_register_event_subscription_self_referential_raises(self) -> None:
        """Test that self-referential subscriptions raise ValueError."""
        registry = CausalLinkRegistry()
        with pytest.raises(ValueError, match="cannot be self-referential"):
            registry.register_event_subscription(
                publisher="SameAdapter",
                subscriber="SameAdapter",
                event_type="SomeEvent",
            )

    def test_get_links_by_source(self) -> None:
        """Test filtering links by source."""
        registry = CausalLinkRegistry()
        registry.register_dependency("SourceA", "TargetA", LinkType.TEST_RESULTS)
        registry.register_dependency("SourceA", "TargetB", LinkType.CODE_QUALITY)
        registry.register_dependency("SourceB", "TargetC", LinkType.STATE_UPDATES)

        links = registry.get_links(source="SourceA")
        assert len(links) == 2
        assert all(link.source == "SourceA" for link in links)

    def test_get_links_by_target(self) -> None:
        """Test filtering links by target."""
        registry = CausalLinkRegistry()
        registry.register_dependency("SourceA", "TargetX", LinkType.TEST_RESULTS)
        registry.register_dependency("SourceB", "TargetX", LinkType.CODE_QUALITY)
        registry.register_dependency("SourceC", "TargetY", LinkType.STATE_UPDATES)

        links = registry.get_links(target="TargetX")
        assert len(links) == 2
        assert all(link.target == "TargetX" for link in links)

    def test_get_links_by_link_type(self) -> None:
        """Test filtering links by type."""
        registry = CausalLinkRegistry()
        registry.register_dependency("A1", "B1", LinkType.TEST_RESULTS)
        registry.register_dependency("A2", "B2", LinkType.TEST_RESULTS)
        registry.register_dependency("A3", "B3", LinkType.CODE_QUALITY)

        links = registry.get_links(link_type=LinkType.TEST_RESULTS)
        assert len(links) == 2
        assert all(link.link_type == LinkType.TEST_RESULTS for link in links)

    def test_get_subscriptions_by_publisher(self) -> None:
        """Test filtering subscriptions by publisher."""
        registry = CausalLinkRegistry()
        registry.register_event_subscription("PubA", "SubA", "EventA")
        registry.register_event_subscription("PubA", "SubB", "EventB")
        registry.register_event_subscription("PubB", "SubC", "EventC")

        subs = registry.get_subscriptions(publisher="PubA")
        assert len(subs) == 2
        assert all(sub.publisher == "PubA" for sub in subs)

    def test_get_subscriptions_by_subscriber(self) -> None:
        """Test filtering subscriptions by subscriber."""
        registry = CausalLinkRegistry()
        registry.register_event_subscription("PubA", "SubX", "EventA")
        registry.register_event_subscription("PubB", "SubX", "EventB")
        registry.register_event_subscription("PubC", "SubY", "EventC")

        subs = registry.get_subscriptions(subscriber="SubX")
        assert len(subs) == 2
        assert all(sub.subscriber == "SubX" for sub in subs)

    def test_get_subscriptions_by_event_type(self) -> None:
        """Test filtering subscriptions by event type."""
        registry = CausalLinkRegistry()
        registry.register_event_subscription("PubA", "SubA", "EventX")
        registry.register_event_subscription("PubB", "SubB", "EventX")
        registry.register_event_subscription("PubC", "SubC", "EventY")

        subs = registry.get_subscriptions(event_type="EventX")
        assert len(subs) == 2
        assert all(sub.event_type == "EventX" for sub in subs)

    def test_validate_consistency_no_cycles(self) -> None:
        """Test that validation passes with no cycles."""
        registry = CausalLinkRegistry()
        registry.register_dependency("A", "B", LinkType.TEST_RESULTS)
        registry.register_dependency("B", "C", LinkType.STATE_UPDATES)
        registry.register_dependency("C", "D", LinkType.CODE_QUALITY)

        # Should not raise
        registry.validate_consistency()

    def test_validate_consistency_detects_cycles(self) -> None:
        """Test that validation detects cycles."""
        registry = CausalLinkRegistry()
        registry.register_dependency("A", "B", LinkType.TEST_RESULTS)
        registry.register_dependency("B", "C", LinkType.STATE_UPDATES)
        registry.register_dependency("C", "A", LinkType.CODE_QUALITY)  # Creates cycle

        with pytest.raises(CausalLinkConsistencyError, match="Cycle detected"):
            registry.validate_consistency()

    def test_validate_consistency_self_cycle(self) -> None:
        """Test that validation catches self-cycles (prevented by design)."""
        registry = CausalLinkRegistry()
        # Self-cycles are prevented at registration time
        with pytest.raises(ValueError):
            registry.register_dependency("A", "A", LinkType.TEST_RESULTS)

    def test_clear_removes_all_links(self) -> None:
        """Test that clear removes all registered links."""
        registry = CausalLinkRegistry()
        registry.register_dependency("A", "B", LinkType.TEST_RESULTS)
        registry.register_dependency("C", "D", LinkType.CODE_QUALITY)
        registry.register_event_subscription("E", "F", "EventA")

        assert len(registry.get_all_links()) == 2
        assert len(registry.get_all_subscriptions()) == 1

        registry.clear()

        assert len(registry.get_all_links()) == 0
        assert len(registry.get_all_subscriptions()) == 0

    def test_causal_link_equality(self) -> None:
        """Test that CausalLink equality works correctly."""
        link1 = CausalLink("A", "B", LinkType.TEST_RESULTS)
        link2 = CausalLink("A", "B", LinkType.TEST_RESULTS)
        link3 = CausalLink("A", "B", LinkType.CODE_QUALITY)

        assert link1 == link2
        assert link1 != link3

    def test_causal_link_hashing(self) -> None:
        """Test that CausalLink can be used in sets."""
        link1 = CausalLink("A", "B", LinkType.TEST_RESULTS)
        link2 = CausalLink("A", "B", LinkType.TEST_RESULTS)
        link3 = CausalLink("C", "D", LinkType.CODE_QUALITY)

        link_set = {link1, link2, link3}
        assert len(link_set) == 2  # link1 and link2 are equal

    def test_event_subscription_equality(self) -> None:
        """Test that EventSubscription equality works correctly."""
        sub1 = EventSubscription("PubA", "SubA", "EventA")
        sub2 = EventSubscription("PubA", "SubA", "EventA")
        sub3 = EventSubscription("PubA", "SubA", "EventB")

        assert sub1 == sub2
        assert sub1 != sub3

    def test_event_subscription_hashing(self) -> None:
        """Test that EventSubscription can be used in sets."""
        sub1 = EventSubscription("PubA", "SubA", "EventA")
        sub2 = EventSubscription("PubA", "SubA", "EventA")
        sub3 = EventSubscription("PubB", "SubB", "EventB")

        sub_set = {sub1, sub2, sub3}
        assert len(sub_set) == 2  # sub1 and sub2 are equal

    def test_registry_repr(self) -> None:
        """Test string representation of registry."""
        registry = CausalLinkRegistry()
        registry.register_dependency("A", "B", LinkType.TEST_RESULTS)
        registry.register_event_subscription("C", "D", "EventA")

        repr_str = repr(registry)
        assert "CausalLinkRegistry" in repr_str
        assert "links=1" in repr_str
        assert "subscriptions=1" in repr_str
