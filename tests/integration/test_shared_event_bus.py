"""Integration tests for shared event bus across CLI and server processes.

This test verifies that events published via CLI bootstrap reach the application
server when both use the same Elasticsearch event store. This is critical for
Phase E2 dogfooding verification.
"""

import asyncio

import pytest
from elasticsearch import AsyncElasticsearch

from codetoreum.domain.events.adapter_events import CodetoreumEvent, now_iso
from codetoreum.infrastructure.adapters.event_store_factory import (
    create_elasticsearch_event_store,
    initialize_event_store,
)
from codetoreum.infrastructure.bootstrap.cli_bootstrap import CLIBootstrap
from codetoreum.ports.output.event_store import IEventStore
from tests.conftest import docker_available

pytestmark = docker_available


@pytest.mark.asyncio
class TestSharedEventBus:
    """Tests for shared event bus functionality across processes."""

    @pytest.mark.timeout(30)
    async def test_cli_bootstrap_publishes_to_shared_event_store(
        self,
        elasticsearch_client: AsyncElasticsearch,
    ) -> None:
        """
        Verify that CLI bootstrap publishes to the same event store as the server.

        This test:
        1. Sets up CLI bootstrap with Elasticsearch event store
        2. Creates a server event store (same Elasticsearch backend)
        3. Publishes an event via CLI bootstrap event bus
        4. Retrieves the event from server event store
        5. Verifies event integrity across the boundary

        This is the core requirement for Phase 3.1: cross-process event propagation.
        """
        # Setup CLI bootstrap
        cli = CLIBootstrap()
        await cli.setup()

        try:
            # Create server event store (same Elasticsearch backend)
            server_event_store = create_elasticsearch_event_store(elasticsearch_client)
            await initialize_event_store(server_event_store)

            # Create a test event
            stream_id = "test-workflow-123"
            test_event = BoardEventForTesting(
                aggregate_id=stream_id,
                aggregate_type="Workflow",
                event_type="test.event",
                timestamp=now_iso(),
                source="test",
                old_value="column_a",
                new_value="column_b",
            )

            # Publish event via CLI event store
            assert cli.adapters is not None, "CLI adapters not initialized"
            await cli.adapters.event_store.append(stream_id, [test_event])

            # Give Elasticsearch time to index the event
            await asyncio.sleep(0.5)

            # Retrieve event from server event store
            retrieved_events = await server_event_store.get_events(stream_id)

            # Verify event was retrieved
            assert len(retrieved_events) == 1, f"Expected 1 event, got {len(retrieved_events)}"
            retrieved = retrieved_events[0]

            # Verify event integrity
            assert retrieved.aggregate_id == stream_id
            assert retrieved.event_type == "test.event"
            assert isinstance(retrieved, BoardEventForTesting)
            assert retrieved.old_value == "column_a"
            assert retrieved.new_value == "column_b"
        finally:
            await cli.teardown()

    @pytest.mark.timeout(30)
    async def test_multiple_events_propagate_across_processes(
        self,
        elasticsearch_client: AsyncElasticsearch,
    ) -> None:
        """
        Verify that multiple events published via CLI reach the server.

        Tests that events maintain order and integrity across process boundaries.
        """
        # Setup CLI bootstrap
        cli = CLIBootstrap()
        await cli.setup()

        try:
            # Create server event store
            server_event_store = create_elasticsearch_event_store(elasticsearch_client)
            await initialize_event_store(server_event_store)

            # Publish multiple events via CLI
            stream_id = "test-workflow-456"
            assert cli.adapters is not None, "CLI adapters not initialized"
            events = [
                BoardEventForTesting(
                    aggregate_id=stream_id,
                    aggregate_type="Workflow",
                    event_type="test.event",
                    timestamp=now_iso(),
                    source="test",
                    old_value=f"column_{i}",
                    new_value=f"column_{i+1}",
                )
                for i in range(3)
            ]

            await cli.adapters.event_store.append(stream_id, events)

            # Wait for indexing
            await asyncio.sleep(0.5)

            # Retrieve from server
            retrieved_events = await server_event_store.get_events(stream_id)

            assert len(retrieved_events) == 3
            for i, event in enumerate(retrieved_events):
                assert event.old_value == f"column_{i}"
                assert event.new_value == f"column_{i+1}"
        finally:
            await cli.teardown()

    @pytest.mark.timeout(30)
    async def test_event_isolation_across_streams(
        self,
        elasticsearch_client: AsyncElasticsearch,
    ) -> None:
        """
        Verify that events in different streams don't interfere.

        Tests that stream isolation is maintained across process boundaries.
        """
        # Setup CLI bootstrap
        cli = CLIBootstrap()
        await cli.setup()

        try:
            # Create server event store
            server_event_store = create_elasticsearch_event_store(elasticsearch_client)
            await initialize_event_store(server_event_store)

            # Publish events to different streams via CLI
            stream1_id = "workflow-stream-1"
            stream2_id = "workflow-stream-2"

            event1 = BoardEventForTesting(
                aggregate_id=stream1_id,
                aggregate_type="Workflow",
                event_type="test.event",
                timestamp=now_iso(),
                source="test",
                old_value="a",
                new_value="b",
            )

            event2 = BoardEventForTesting(
                aggregate_id=stream2_id,
                aggregate_type="Workflow",
                event_type="test.event",
                timestamp=now_iso(),
                source="test",
                old_value="x",
                new_value="y",
            )

            assert cli.adapters is not None, "CLI adapters not initialized"
            await cli.adapters.event_store.append(stream1_id, [event1])
            await cli.adapters.event_store.append(stream2_id, [event2])

            # Wait for indexing
            await asyncio.sleep(0.5)

            # Retrieve from server for each stream
            events1 = await server_event_store.get_events(stream1_id)
            events2 = await server_event_store.get_events(stream2_id)

            assert len(events1) == 1
            assert len(events2) == 1
            assert events1[0].old_value == "a"
            assert events2[0].old_value == "x"
        finally:
            await cli.teardown()


# Test event fixture
class BoardEventForTesting(CodetoreumEvent):
    """Test event for shared event bus testing."""

    old_value: str = ""
    new_value: str = ""


