"""
Tests for Audit Stores

Tests the different audit store implementations (in-memory, file-based).
"""

import pytest
import tempfile
import os
from datetime import datetime, timedelta

from codetoreum.infrastructure.audit.stores import InMemoryAuditStore, FileAuditStore
from codetoreum.infrastructure.audit.interfaces import AuditQueryFilters


@pytest.mark.asyncio
class TestInMemoryAuditStore:
    """Tests for InMemoryAuditStore."""

    async def test_store_event(self):
        """Test storing an audit event."""
        store = InMemoryAuditStore()

        event_id = await store.store_event(
            timestamp=datetime.utcnow(),
            event_type="agent_created",
            resource_type="agent",
            resource_id="agent-123",
            action="create",
            user_id="user-456",
            correlation_id="corr-789",
            metadata={"agent_name": "test-agent"},
            success=True,
        )

        assert event_id is not None
        assert isinstance(event_id, str)

    async def test_get_event_by_id(self):
        """Test retrieving an event by ID."""
        store = InMemoryAuditStore()

        event_id = await store.store_event(
            timestamp=datetime.utcnow(),
            event_type="agent_created",
            resource_type="agent",
            resource_id="agent-123",
            action="create",
            user_id="user-456",
            correlation_id=None,
            metadata={},
            success=True,
        )

        event = await store.get_event_by_id(event_id)

        assert event is not None
        assert event["id"] == event_id
        assert event["event_type"] == "agent_created"
        assert event["resource_id"] == "agent-123"

    async def test_query_events_all(self):
        """Test querying all events."""
        store = InMemoryAuditStore()

        # Store multiple events
        for i in range(5):
            await store.store_event(
                timestamp=datetime.utcnow(),
                event_type="agent_created",
                resource_type="agent",
                resource_id=f"agent-{i}",
                action="create",
                user_id="user-456",
                correlation_id=None,
                metadata={},
                success=True,
            )

        filters = AuditQueryFilters(limit=10)
        events = await store.query_events(filters)

        assert len(events) == 5

    async def test_query_events_by_type(self):
        """Test querying events by event type."""
        store = InMemoryAuditStore()

        # Store different event types
        await store.store_event(
            timestamp=datetime.utcnow(),
            event_type="agent_created",
            resource_type="agent",
            resource_id="agent-1",
            action="create",
            user_id="user-456",
            correlation_id=None,
            metadata={},
            success=True,
        )

        await store.store_event(
            timestamp=datetime.utcnow(),
            event_type="agent_deleted",
            resource_type="agent",
            resource_id="agent-2",
            action="delete",
            user_id="user-456",
            correlation_id=None,
            metadata={},
            success=True,
        )

        filters = AuditQueryFilters(event_type="agent_created")
        events = await store.query_events(filters)

        assert len(events) == 1
        assert events[0]["event_type"] == "agent_created"

    async def test_query_events_by_user(self):
        """Test querying events by user."""
        store = InMemoryAuditStore()

        # Store events for different users
        await store.store_event(
            timestamp=datetime.utcnow(),
            event_type="agent_created",
            resource_type="agent",
            resource_id="agent-1",
            action="create",
            user_id="user-1",
            correlation_id=None,
            metadata={},
            success=True,
        )

        await store.store_event(
            timestamp=datetime.utcnow(),
            event_type="agent_created",
            resource_type="agent",
            resource_id="agent-2",
            action="create",
            user_id="user-2",
            correlation_id=None,
            metadata={},
            success=True,
        )

        filters = AuditQueryFilters(user_id="user-1")
        events = await store.query_events(filters)

        assert len(events) == 1
        assert events[0]["user_id"] == "user-1"

    async def test_query_events_by_success(self):
        """Test querying events by success status."""
        store = InMemoryAuditStore()

        # Store successful and failed events
        await store.store_event(
            timestamp=datetime.utcnow(),
            event_type="agent_created",
            resource_type="agent",
            resource_id="agent-1",
            action="create",
            user_id="user-1",
            correlation_id=None,
            metadata={},
            success=True,
        )

        await store.store_event(
            timestamp=datetime.utcnow(),
            event_type="agent_created",
            resource_type="agent",
            resource_id="agent-2",
            action="create",
            user_id="user-1",
            correlation_id=None,
            metadata={},
            success=False,
            error_message="Error",
        )

        # Query successful events
        filters = AuditQueryFilters(success=True)
        events = await store.query_events(filters)
        assert len(events) == 1
        assert events[0]["success"] is True

        # Query failed events
        filters = AuditQueryFilters(success=False)
        events = await store.query_events(filters)
        assert len(events) == 1
        assert events[0]["success"] is False

    async def test_query_events_with_time_range(self):
        """Test querying events within a time range."""
        store = InMemoryAuditStore()

        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        two_days_ago = now - timedelta(days=2)

        # Store events at different times
        await store.store_event(
            timestamp=two_days_ago,
            event_type="agent_created",
            resource_type="agent",
            resource_id="agent-1",
            action="create",
            user_id="user-1",
            correlation_id=None,
            metadata={},
            success=True,
        )

        await store.store_event(
            timestamp=now,
            event_type="agent_created",
            resource_type="agent",
            resource_id="agent-2",
            action="create",
            user_id="user-1",
            correlation_id=None,
            metadata={},
            success=True,
        )

        # Query events from yesterday onwards
        filters = AuditQueryFilters(start_time=yesterday)
        events = await store.query_events(filters)

        assert len(events) == 1
        assert events[0]["resource_id"] == "agent-2"

    async def test_count_events(self):
        """Test counting events."""
        store = InMemoryAuditStore()

        # Store multiple events
        for i in range(10):
            await store.store_event(
                timestamp=datetime.utcnow(),
                event_type="agent_created",
                resource_type="agent",
                resource_id=f"agent-{i}",
                action="create",
                user_id="user-1",
                correlation_id=None,
                metadata={},
                success=True,
            )

        filters = AuditQueryFilters()
        count = await store.count_events(filters)

        assert count == 10

    async def test_cleanup_old_events(self):
        """Test cleaning up old events."""
        store = InMemoryAuditStore()

        now = datetime.utcnow()
        old_date = now - timedelta(days=100)

        # Store old event
        await store.store_event(
            timestamp=old_date,
            event_type="agent_created",
            resource_type="agent",
            resource_id="agent-1",
            action="create",
            user_id="user-1",
            correlation_id=None,
            metadata={},
            success=True,
        )

        # Store recent event
        await store.store_event(
            timestamp=now,
            event_type="agent_created",
            resource_type="agent",
            resource_id="agent-2",
            action="create",
            user_id="user-1",
            correlation_id=None,
            metadata={},
            success=True,
        )

        # Cleanup events older than 90 days
        deleted_count = await store.cleanup_old_events(retention_days=90)

        assert deleted_count == 1

        # Verify only recent event remains
        filters = AuditQueryFilters()
        events = await store.query_events(filters)
        assert len(events) == 1
        assert events[0]["resource_id"] == "agent-2"

    async def test_pagination(self):
        """Test pagination of query results."""
        store = InMemoryAuditStore()

        # Store 10 events
        for i in range(10):
            await store.store_event(
                timestamp=datetime.utcnow(),
                event_type="agent_created",
                resource_type="agent",
                resource_id=f"agent-{i}",
                action="create",
                user_id="user-1",
                correlation_id=None,
                metadata={},
                success=True,
            )

        # Query first page
        filters = AuditQueryFilters(limit=5, offset=0)
        events = await store.query_events(filters)
        assert len(events) == 5

        # Query second page
        filters = AuditQueryFilters(limit=5, offset=5)
        events = await store.query_events(filters)
        assert len(events) == 5


@pytest.mark.asyncio
class TestFileAuditStore:
    """Tests for FileAuditStore."""

    async def test_store_event_to_file(self):
        """Test storing an event to file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            file_path = f.name

        try:
            store = FileAuditStore(file_path)

            event_id = await store.store_event(
                timestamp=datetime.utcnow(),
                event_type="agent_created",
                resource_type="agent",
                resource_id="agent-123",
                action="create",
                user_id="user-456",
                correlation_id=None,
                metadata={"test": "data"},
                success=True,
            )

            assert event_id is not None

            # Verify file exists and has content
            assert os.path.exists(file_path)
            with open(file_path, "r") as f:
                content = f.read()
                assert "agent_created" in content

        finally:
            if os.path.exists(file_path):
                os.unlink(file_path)

    async def test_query_events_from_file(self):
        """Test querying events from file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            file_path = f.name

        try:
            store = FileAuditStore(file_path)

            # Store multiple events
            for i in range(3):
                await store.store_event(
                    timestamp=datetime.utcnow(),
                    event_type="agent_created",
                    resource_type="agent",
                    resource_id=f"agent-{i}",
                    action="create",
                    user_id="user-1",
                    correlation_id=None,
                    metadata={},
                    success=True,
                )

            # Query events
            filters = AuditQueryFilters(limit=10)
            events = await store.query_events(filters)

            assert len(events) == 3

        finally:
            if os.path.exists(file_path):
                os.unlink(file_path)

    async def test_cleanup_old_events_in_file(self):
        """Test cleaning up old events in file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            file_path = f.name

        try:
            store = FileAuditStore(file_path)

            now = datetime.utcnow()
            old_date = now - timedelta(days=100)

            # Store old and new events
            await store.store_event(
                timestamp=old_date,
                event_type="agent_created",
                resource_type="agent",
                resource_id="agent-old",
                action="create",
                user_id="user-1",
                correlation_id=None,
                metadata={},
                success=True,
            )

            await store.store_event(
                timestamp=now,
                event_type="agent_created",
                resource_type="agent",
                resource_id="agent-new",
                action="create",
                user_id="user-1",
                correlation_id=None,
                metadata={},
                success=True,
            )

            # Cleanup
            deleted_count = await store.cleanup_old_events(retention_days=90)
            assert deleted_count == 1

            # Verify only new event remains
            filters = AuditQueryFilters()
            events = await store.query_events(filters)
            assert len(events) == 1
            assert events[0]["resource_id"] == "agent-new"

        finally:
            if os.path.exists(file_path):
                os.unlink(file_path)
