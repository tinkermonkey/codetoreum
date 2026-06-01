#!/usr/bin/env python3
"""Generate inventory of emitted-but-unsubscribed events.

This script discovers:
1. All domain event types defined in domain/events/
2. All event types subscribed to by event handlers
3. Reports any emitted events without subscribers
"""

import re
from pathlib import Path


def discover_domain_events() -> set[str]:
    """Discover all CodetoreumEvent subclasses defined in domain/events/."""
    events_dir = Path(__file__).parent.parent / "src" / "codetoreum" / "domain" / "events"
    events = set()

    for py_file in events_dir.glob("*.py"):
        if py_file.name.startswith("__"):
            continue

        with open(py_file) as f:
            content = f.read()

        # Find all class definitions that end with "Event"
        pattern = r"^class\s+(\w+Event)\s*\("
        for match in re.finditer(pattern, content, re.MULTILINE):
            event_name = match.group(1)
            # Skip base classes like CodetoreumEvent, DomainEvent, etc.
            if event_name not in ("CodetoreumEvent", "DomainEvent"):
                events.add(event_name)

    return events


def discover_subscribed_events() -> set[str]:
    """Discover all event types that have subscribers."""
    events_dir = Path(__file__).parent.parent / "src" / "codetoreum" / "application" / "event_handlers"
    subscribed = set()

    for py_file in events_dir.glob("*.py"):
        if py_file.name.startswith("__"):
            continue

        with open(py_file) as f:
            content = f.read()

        # Find @event_handler decorators
        pattern = r'@event_handler\((.*?)\)'
        for match in re.finditer(pattern, content, re.DOTALL):
            handler_events = match.group(1)
            # Extract quoted strings
            event_pattern = r'"([^"]+)"'
            for event_match in re.finditer(event_pattern, handler_events):
                event_name = event_match.group(1)
                subscribed.add(event_name)

    # Also check for manual subscriptions in WorkflowOrchestrator
    workflow_file = Path(__file__).parent.parent / "src" / "codetoreum" / "application" / "workflow_orchestrator.py"
    with open(workflow_file) as f:
        content = f.read()

    pattern = r'event_bus\.subscribe\("([^"]+)"'
    for match in re.finditer(pattern, content):
        event_name = match.group(1)
        subscribed.add(event_name)

    return subscribed


def discover_published_events() -> dict[str, list[str]]:
    """Discover where events are published in the codebase.

    Returns:
        Dict mapping event type to list of files where it's published
    """
    src_dir = Path(__file__).parent.parent / "src"
    published = {}

    for py_file in src_dir.rglob("*.py"):
        with open(py_file) as f:
            try:
                content = f.read()
            except UnicodeDecodeError:
                continue

        # Find event publications: await event_bus.publish(EventType(...))
        pattern = r"await\s+(?:self\.)?event_bus\.publish\s*\(\s*(\w+Event)\s*\("
        for match in re.finditer(pattern, content):
            event_name = match.group(1)
            rel_path = str(py_file.relative_to(src_dir))
            if event_name not in published:
                published[event_name] = []
            published[event_name].append(rel_path)

    return published


def main():
    """Generate and print the event inventory."""
    print("=== Codetoreum Event Inventory ===\n")

    domain_events = discover_domain_events()
    subscribed_events = discover_subscribed_events()
    published_events = discover_published_events()

    print(f"Total domain events defined: {len(domain_events)}")
    print(f"Total subscribed event types: {len(subscribed_events)}")
    print(f"Total published event types: {len(published_events)}\n")

    # Find unsubscribed events
    unsubscribed = domain_events - subscribed_events

    print("=== Emitted-but-Unsubscribed Events ===\n")
    print(f"Count: {len(unsubscribed)}\n")

    if unsubscribed:
        for event in sorted(unsubscribed):
            status = "PUBLISHED" if event in published_events else "DEFINED_ONLY"
            publication_info = f" (published in: {', '.join(published_events[event])})" if event in published_events else ""
            print(f"- {event}: {status}{publication_info}")
    else:
        print("None found!")

    print("\n=== Subscribed Events ===\n")
    for event in sorted(subscribed_events):
        publication_info = (
            f" (published in: {', '.join(published_events[event][:2])})"
            if event in published_events
            else " (NOT EMITTED)"
        )
        print(f"- {event}{publication_info}")

    # Generate PR description content
    print("\n=== PR Description Template ===\n")
    print("## Event Inventory\n")
    print(f"**Total emitted events:** {len(published_events)}")
    print(f"**Total subscribed events:** {len(subscribed_events)}")
    print(f"**Unsubscribed emitted events:** {len([e for e in unsubscribed if e in published_events])}\n")

    print("### Emitted-but-Unsubscribed Events\n")
    for event in sorted([e for e in unsubscribed if e in published_events]):
        print(f"- `{event}` (emitted in {len(published_events[event])} location(s))")
        print(f"  - **Disposition:** [wire now | delete | defer]")
        print(f"  - **Reason:** [provide reason for disposition decision]")
        print()

    # Special handling for WorkflowOrphanedEvent
    if "WorkflowOrphanedEvent" in unsubscribed:
        print("### Special Cases\n")
        print(
            "- `WorkflowOrphanedEvent`: Marked for deletion in Phase 5 (pipeline coordination). "
            "No handler needed at this time.\n"
        )


if __name__ == "__main__":
    main()
