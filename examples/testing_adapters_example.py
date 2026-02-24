"""Example usage of testing adapters for Codetoreum.

This module demonstrates how to use the in-memory and mock adapters
for testing without external dependencies.
"""

import asyncio
from pathlib import Path

from codetoreum.adapters.testing import (
    FakeContainerAdapter,
    InMemoryEventStore,
    InMemoryRepositoryAdapter,
    InMemoryTicketAdapter,
    MockLLMAdapter,
)
from codetoreum.domain.events import WorkItemCreated
from codetoreum.domain.types import BranchName, ProjectId, UserId, WorkItemId
from codetoreum.domain.work_item import WorkItemPriority


async def example_ticket_adapter() -> None:
    """Demonstrate InMemoryTicketAdapter usage."""
    print("\n=== InMemoryTicketAdapter Example ===")

    adapter = InMemoryTicketAdapter()

    # Create work item
    work_item = await adapter.create_work_item(
        title="Implement user authentication",
        description="Add OAuth2 authentication flow",
        project_id=ProjectId("project-123"),
        labels=["feature", "security"],
        priority=WorkItemPriority.HIGH,
    )
    print(f"Created work item: {work_item.title} (ID: {work_item.id})")

    # Add comment
    comment = await adapter.add_comment(
        WorkItemId(work_item.id),
        "Starting implementation today",
        author=UserId("developer-1"),
    )
    print(f"Added comment: {comment.body}")

    # Search work items
    results = await adapter.search_work_items("authentication")
    print(f"Search found {len(results)} items")

    # Clear for next test
    adapter.clear()
    print("Adapter cleared")


async def example_mock_llm_adapter() -> None:
    """Demonstrate MockLLMAdapter usage."""
    print("\n=== MockLLMAdapter Example ===")

    adapter = MockLLMAdapter(default_response="I'm a helpful assistant")

    # Add pattern-based responses
    adapter.add_response_pattern(r"calculate.*\d+", "The answer is 42")
    adapter.add_response_pattern(r"hello", "Hello! How can I help you today?")

    # Execute with pattern match
    result = await adapter.execute("Hello there!")
    print(f"Response: {result.content}")

    # Execute with calculation pattern
    result = await adapter.execute("Please calculate 2 + 2")
    print(f"Response: {result.content}")

    # Stream completion
    print("Streaming response:")
    async for chunk in adapter.stream_completion("Tell me about AI"):
        print(f"  Chunk: {chunk.content}", end="")
    print()

    # Get usage stats
    stats = await adapter.get_usage_stats()
    print(f"Total requests: {stats.total_requests}")
    print(f"Total tokens: {stats.total_tokens}")


async def example_fake_container_adapter() -> None:
    """Demonstrate FakeContainerAdapter usage."""
    print("\n=== FakeContainerAdapter Example ===")

    adapter = FakeContainerAdapter()

    # Set predefined results
    adapter.set_command_result(
        "pytest",
        exit_code=0,
        stdout="===== 100 passed in 2.34s =====",
    )

    adapter.set_command_result(
        "npm",
        exit_code=0,
        stdout="Packages installed successfully",
    )

    # Run commands
    result = await adapter.run(
        image="python:3.11",
        command=["pytest", "tests/"],
        volumes={},
        environment={},
    )
    print(f"pytest exit code: {result.exit_code}")
    print(f"pytest output: {result.stdout}")

    result = await adapter.run(
        image="node:18",
        command=["npm", "install"],
        volumes={},
        environment={},
    )
    print(f"npm exit code: {result.exit_code}")

    # Check execution history
    history = adapter.get_execution_history()
    print(f"Total executions: {len(history)}")


async def example_repository_adapter() -> None:
    """Demonstrate InMemoryRepositoryAdapter usage."""
    print("\n=== InMemoryRepositoryAdapter Example ===")

    adapter = InMemoryRepositoryAdapter()

    # Clone repository
    repo_id = await adapter.clone(
        "https://github.com/user/repo.git",
        Path("/tmp/test-repo"),
        branch=BranchName("main"),
    )
    print(f"Cloned repository: {repo_id}")

    # Create branch
    await adapter.create_branch(
        Path("/tmp/test-repo"),
        BranchName("feature/new-feature"),
    )
    print("Created feature branch")

    # Checkout branch
    await adapter.checkout(
        Path("/tmp/test-repo"),
        BranchName("feature/new-feature"),
    )
    print("Checked out feature branch")

    # Make commit
    commit_sha = await adapter.commit(
        Path("/tmp/test-repo"),
        message="Add new feature",
        author_name="Developer",
        author_email="dev@example.com",
    )
    print(f"Created commit: {commit_sha}")

    # Get status
    status = await adapter.status(Path("/tmp/test-repo"))
    print(f"Current branch: {status.current_branch}")

    # List branches
    branches = await adapter.list_branches(Path("/tmp/test-repo"))
    print(f"Branches: {', '.join(branches)}")


async def example_event_store() -> None:
    """Demonstrate InMemoryEventStore usage."""
    print("\n=== InMemoryEventStore Example ===")

    store = InMemoryEventStore()

    # Create events
    events = [
        WorkItemCreated(
            aggregate_id="work-item-123",
            payload={
                "title": "Test Issue",
                "description": "Test description",
                "project_id": "project-1",
                "labels": ["bug"],
                "priority": 2,
            },
        ),
    ]

    # Append events
    await store.append("work-item-123", events)
    print(f"Appended {len(events)} events to stream")

    # Get events
    retrieved = await store.get_events("work-item-123")
    print(f"Retrieved {len(retrieved)} events")

    # Get statistics
    stats = await store.get_statistics()
    print(f"Total events: {stats['total_events']}")
    print(f"Total streams: {stats['total_streams']}")

    # Replay events
    print("Replaying events:")
    async for event in store.replay_events("work-item-123"):
        print(f"  Event: {event.event_type}")


async def main() -> None:
    """Run all examples."""
    print("=== Testing Adapters Examples ===")

    await example_ticket_adapter()
    await example_mock_llm_adapter()
    await example_fake_container_adapter()
    await example_repository_adapter()
    await example_event_store()

    print("\n=== All examples completed successfully! ===")


if __name__ == "__main__":
    asyncio.run(main())
