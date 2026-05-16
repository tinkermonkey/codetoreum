"""Integration tests for shared event bus across CLI and server processes.

This test verifies that events published via CLI bootstrap reach the application
server when both use the same Elasticsearch event store. This is critical for
Phase E2 dogfooding verification.
"""

import asyncio
from datetime import UTC, datetime

import pytest
from elasticsearch import AsyncElasticsearch

from codetoreum.domain.events.board_events import WorkItemColumnChangedEvent
from codetoreum.infrastructure.adapters.event_store_factory import (
    create_elasticsearch_event_store,
    initialize_event_store,
)
from codetoreum.infrastructure.bootstrap.cli_bootstrap import CLIBootstrap
from codetoreum.infrastructure.event_serialization import EventSerializer
from tests.conftest import docker_available

# Register event types for deserialization
EventSerializer.register_event_type(WorkItemColumnChangedEvent)

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

            # Create a test event using the correct API
            work_item_id = "WI-123"
            test_event = WorkItemColumnChangedEvent(
                type="workitem.column_changed",
                timestamp=datetime.now(UTC).isoformat(),
                source="test",
                work_item_id=work_item_id,
                project_id="test-project",
                board_id="test-board",
                from_column="Backlog",
                to_column="In Progress",
                moved_by="human",
            )

            # Publish event via CLI event store
            assert cli.adapters is not None, "CLI adapters not initialized"
            await cli.adapters.event_store.append(work_item_id, [test_event])

            # Refresh Elasticsearch indices to make events immediately searchable
            await elasticsearch_client.indices.refresh(index="events-*")

            # Retrieve event from server event store
            retrieved_events = await server_event_store.get_events(work_item_id)

            # Verify event was retrieved
            assert len(retrieved_events) == 1, f"Expected 1 event, got {len(retrieved_events)}"
            retrieved = retrieved_events[0]

            # Verify event integrity
            assert retrieved.type == "workitem.column_changed"
            assert isinstance(retrieved, WorkItemColumnChangedEvent)
            assert retrieved.work_item_id == work_item_id
            assert retrieved.from_column == "Backlog"
            assert retrieved.to_column == "In Progress"
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
            work_item_id = "WI-456"
            assert cli.adapters is not None, "CLI adapters not initialized"
            events = [
                WorkItemColumnChangedEvent(
                    type="workitem.column_changed",
                    timestamp=datetime.now(UTC).isoformat(),
                    source="test",
                    work_item_id=work_item_id,
                    project_id="test-project",
                    board_id="test-board",
                    from_column=f"column_{i}",
                    to_column=f"column_{i+1}",
                    moved_by="human",
                )
                for i in range(3)
            ]

            await cli.adapters.event_store.append(work_item_id, events)

            # Refresh Elasticsearch indices to make events immediately searchable
            await elasticsearch_client.indices.refresh(index="events-*")

            # Retrieve from server
            retrieved_events = await server_event_store.get_events(work_item_id)

            assert len(retrieved_events) == 3
            for i, event in enumerate(retrieved_events):
                assert event.from_column == f"column_{i}"
                assert event.to_column == f"column_{i+1}"
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
            stream1_id = "WI-stream-1"
            stream2_id = "WI-stream-2"

            event1 = WorkItemColumnChangedEvent(
                type="workitem.column_changed",
                timestamp=datetime.now(UTC).isoformat(),
                source="test",
                work_item_id=stream1_id,
                project_id="test-project",
                board_id="test-board",
                from_column="a",
                to_column="b",
                moved_by="human",
            )

            event2 = WorkItemColumnChangedEvent(
                type="workitem.column_changed",
                timestamp=datetime.now(UTC).isoformat(),
                source="test",
                work_item_id=stream2_id,
                project_id="test-project",
                board_id="test-board",
                from_column="x",
                to_column="y",
                moved_by="human",
            )

            assert cli.adapters is not None, "CLI adapters not initialized"
            await cli.adapters.event_store.append(stream1_id, [event1])
            await cli.adapters.event_store.append(stream2_id, [event2])

            # Refresh Elasticsearch indices to make events immediately searchable
            await elasticsearch_client.indices.refresh(index="events-*")

            # Retrieve from server for each stream
            events1 = await server_event_store.get_events(stream1_id)
            events2 = await server_event_store.get_events(stream2_id)

            assert len(events1) == 1
            assert len(events2) == 1
            assert events1[0].from_column == "a"
            assert events2[0].from_column == "x"
        finally:
            await cli.teardown()
