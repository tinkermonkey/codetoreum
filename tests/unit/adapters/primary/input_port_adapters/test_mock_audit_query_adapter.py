"""Tests for MockAuditQueryAdapter.

Tests verify:
- Field validation (required fields must not be empty/missing)
- Default values (success defaults to False, not True)
- Filter mapping and application
- Pagination
- Event count queries
- Error handling for missing required timestamp and other fields
"""

from datetime import UTC, datetime

import pytest

from codetoreum.adapters.primary.input_port_adapters.mock.mock_audit_query_adapter import (
    MockAuditQueryAdapter,
)
from codetoreum.infrastructure.audit.stores import InMemoryAuditStore
from codetoreum.ports.input.audit_query import (
    AuditEventFilters,
    AuditEventPaginationParams,
)


class TestMockAuditQueryAdapterFieldValidation:
    """Test field validation and required field enforcement."""

    @pytest.mark.asyncio
    async def test_missing_timestamp_raises_error(self):
        """Test that missing timestamp raises RuntimeError for audit integrity."""
        store = InMemoryAuditStore()
        adapter = MockAuditQueryAdapter(store)

        # Store event directly in store (bypassing validation)
        # This simulates corrupted data
        store._events["test-event-1"] = {
            "id": "test-event-1",
            "timestamp": None,  # Missing timestamp
            "event_type": "agent_deleted",
            "resource_type": "agent",
            "resource_id": "agent-123",
            "action": "delete",
            "user_id": "user-1",
            "correlation_id": None,
            "metadata": {},
            "success": True,
            "error_message": None,
        }

        with pytest.raises(RuntimeError, match="missing required fields"):
            await adapter.query_audit_events()

    @pytest.mark.asyncio
    async def test_missing_required_fields_raises_error(self):
        """Test that missing required fields raise RuntimeError."""
        store = InMemoryAuditStore()
        adapter = MockAuditQueryAdapter(store)

        # Store event with missing id
        store._events["test-event-1"] = {
            "id": None,  # Missing id
            "timestamp": datetime.now(UTC),
            "event_type": "agent_deleted",
            "resource_type": "agent",
            "resource_id": "agent-123",
            "action": "delete",
            "user_id": "user-1",
            "correlation_id": None,
            "metadata": {},
            "success": True,
            "error_message": None,
        }

        with pytest.raises(RuntimeError, match="missing required fields"):
            await adapter.query_audit_events()

    @pytest.mark.asyncio
    async def test_empty_string_required_fields_raises_error(self):
        """Test that empty string required fields are treated as missing."""
        store = InMemoryAuditStore()
        adapter = MockAuditQueryAdapter(store)

        # Store event with empty event_type
        store._events["test-event-1"] = {
            "id": "test-event-1",
            "timestamp": datetime.now(UTC),
            "event_type": "",  # Empty string
            "resource_type": "agent",
            "resource_id": "agent-123",
            "action": "delete",
            "user_id": "user-1",
            "correlation_id": None,
            "metadata": {},
            "success": True,
            "error_message": None,
        }

        with pytest.raises(RuntimeError, match="missing required fields"):
            await adapter.query_audit_events()

    @pytest.mark.asyncio
    async def test_success_defaults_to_false(self):
        """Test that missing success field defaults to False, not True."""
        store = InMemoryAuditStore()
        adapter = MockAuditQueryAdapter(store)

        # Store event without success field (simulates incomplete data)
        now = datetime.now(UTC)
        store._events["test-event-1"] = {
            "id": "test-event-1",
            "timestamp": now,
            "event_type": "agent_deleted",
            "resource_type": "agent",
            "resource_id": "agent-123",
            "action": "delete",
            "user_id": "user-1",
            "correlation_id": None,
            "metadata": {},
            # success field missing!
            "error_message": None,
        }

        result = await adapter.query_audit_events()

        assert len(result.events) == 1
        event = result.events[0]
        # Critical: success should default to False, not True
        assert event.success is False

    @pytest.mark.asyncio
    async def test_success_explicit_true_is_preserved(self):
        """Test that explicit success=True is preserved."""
        store = InMemoryAuditStore()
        adapter = MockAuditQueryAdapter(store)

        now = datetime.now(UTC)
        store._events["test-event-1"] = {
            "id": "test-event-1",
            "timestamp": now,
            "event_type": "agent_deleted",
            "resource_type": "agent",
            "resource_id": "agent-123",
            "action": "delete",
            "user_id": "user-1",
            "correlation_id": None,
            "metadata": {},
            "success": True,  # Explicit True
            "error_message": None,
        }

        result = await adapter.query_audit_events()

        assert len(result.events) == 1
        assert result.events[0].success is True

    @pytest.mark.asyncio
    async def test_success_explicit_false_is_preserved(self):
        """Test that explicit success=False is preserved."""
        store = InMemoryAuditStore()
        adapter = MockAuditQueryAdapter(store)

        now = datetime.now(UTC)
        store._events["test-event-1"] = {
            "id": "test-event-1",
            "timestamp": now,
            "event_type": "agent_deleted",
            "resource_type": "agent",
            "resource_id": "agent-123",
            "action": "delete",
            "user_id": "user-1",
            "correlation_id": None,
            "metadata": {},
            "success": False,  # Explicit False
            "error_message": None,
        }

        result = await adapter.query_audit_events()

        assert len(result.events) == 1
        assert result.events[0].success is False


class TestMockAuditQueryAdapterFilters:
    """Test filter mapping and application."""

    @pytest.mark.asyncio
    async def test_filter_by_event_type(self):
        """Test filtering by event_type."""
        store = InMemoryAuditStore()
        adapter = MockAuditQueryAdapter(store)

        now = datetime.now(UTC)

        # Store events with different types
        await store.store_event(
            timestamp=now,
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
            event_type="agent_deleted",
            resource_type="agent",
            resource_id="agent-2",
            action="delete",
            user_id="user-1",
            correlation_id=None,
            metadata={},
            success=True,
        )

        # Query only deleted agents
        filters = AuditEventFilters(event_type="agent_deleted")
        result = await adapter.query_audit_events(filters=filters)

        assert len(result.events) == 1
        assert result.events[0].event_type == "agent_deleted"

    @pytest.mark.asyncio
    async def test_filter_by_resource_id(self):
        """Test filtering by resource_id."""
        store = InMemoryAuditStore()
        adapter = MockAuditQueryAdapter(store)

        now = datetime.now(UTC)

        # Store events for different resources
        await store.store_event(
            timestamp=now,
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
            event_type="agent_updated",
            resource_type="agent",
            resource_id="agent-1",
            action="update",
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

        # Query only events for agent-1
        filters = AuditEventFilters(resource_id="agent-1")
        result = await adapter.query_audit_events(filters=filters)

        assert len(result.events) == 2
        assert all(event.resource_id == "agent-1" for event in result.events)

    @pytest.mark.asyncio
    async def test_filter_by_success_status(self):
        """Test filtering by success status."""
        store = InMemoryAuditStore()
        adapter = MockAuditQueryAdapter(store)

        now = datetime.now(UTC)

        # Store successful and failed events
        await store.store_event(
            timestamp=now,
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
            user_id="user-2",
            correlation_id=None,
            metadata={},
            success=False,
            error_message="Permission denied",
        )

        # Query only failed events
        filters = AuditEventFilters(success=False)
        result = await adapter.query_audit_events(filters=filters)

        assert len(result.events) == 1
        assert result.events[0].success is False
        assert result.events[0].error_message == "Permission denied"

    @pytest.mark.asyncio
    async def test_filter_by_user_id(self):
        """Test filtering by user_id."""
        store = InMemoryAuditStore()
        adapter = MockAuditQueryAdapter(store)

        now = datetime.now(UTC)

        # Store events from different users
        await store.store_event(
            timestamp=now,
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
            event_type="agent_deleted",
            resource_type="agent",
            resource_id="agent-2",
            action="delete",
            user_id="user-2",
            correlation_id=None,
            metadata={},
            success=True,
        )

        # Query only user-1's events
        filters = AuditEventFilters(user_id="user-1")
        result = await adapter.query_audit_events(filters=filters)

        assert len(result.events) == 1
        assert result.events[0].user_id == "user-1"

    @pytest.mark.asyncio
    async def test_filter_by_action(self):
        """Test filtering by action."""
        store = InMemoryAuditStore()
        adapter = MockAuditQueryAdapter(store)

        now = datetime.now(UTC)

        # Store events with different actions
        await store.store_event(
            timestamp=now,
            event_type="agent_event",
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
            event_type="agent_event",
            resource_type="agent",
            resource_id="agent-1",
            action="update",
            user_id="user-1",
            correlation_id=None,
            metadata={},
            success=True,
        )

        # Query only create actions
        filters = AuditEventFilters(action="create")
        result = await adapter.query_audit_events(filters=filters)

        assert len(result.events) == 1
        assert result.events[0].action == "create"

    @pytest.mark.asyncio
    async def test_filter_by_time_range(self):
        """Test filtering by start_time and end_time."""
        store = InMemoryAuditStore()
        adapter = MockAuditQueryAdapter(store)

        now = datetime.now(UTC)
        from datetime import timedelta

        # Store events at different times
        await store.store_event(
            timestamp=now - timedelta(hours=2),
            event_type="agent_event",
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
            event_type="agent_event",
            resource_type="agent",
            resource_id="agent-2",
            action="create",
            user_id="user-1",
            correlation_id=None,
            metadata={},
            success=True,
        )

        await store.store_event(
            timestamp=now + timedelta(hours=2),
            event_type="agent_event",
            resource_type="agent",
            resource_id="agent-3",
            action="create",
            user_id="user-1",
            correlation_id=None,
            metadata={},
            success=True,
        )

        # Query events within one hour
        filters = AuditEventFilters(
            start_time=now - timedelta(minutes=30),
            end_time=now + timedelta(minutes=30),
        )
        result = await adapter.query_audit_events(filters=filters)

        assert len(result.events) == 1
        assert result.events[0].resource_id == "agent-2"

    @pytest.mark.asyncio
    async def test_multiple_filters_combined(self):
        """Test combining multiple filters."""
        store = InMemoryAuditStore()
        adapter = MockAuditQueryAdapter(store)

        now = datetime.now(UTC)

        # Store varied events
        await store.store_event(
            timestamp=now,
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
            user_id="user-2",
            correlation_id=None,
            metadata={},
            success=False,
        )

        await store.store_event(
            timestamp=now,
            event_type="agent_deleted",
            resource_type="agent",
            resource_id="agent-1",
            action="delete",
            user_id="user-1",
            correlation_id=None,
            metadata={},
            success=True,
        )

        # Query: user-1 AND agent-created events that succeeded
        filters = AuditEventFilters(
            user_id="user-1",
            event_type="agent_created",
            success=True,
        )
        result = await adapter.query_audit_events(filters=filters)

        assert len(result.events) == 1
        assert result.events[0].user_id == "user-1"
        assert result.events[0].event_type == "agent_created"
        assert result.events[0].success is True


class TestMockAuditQueryAdapterPagination:
    """Test pagination support."""

    @pytest.mark.asyncio
    async def test_pagination_offset_and_limit(self):
        """Test pagination with offset and limit."""
        store = InMemoryAuditStore()
        adapter = MockAuditQueryAdapter(store)

        now = datetime.now(UTC)

        # Store 5 events
        for i in range(5):
            await store.store_event(
                timestamp=now,
                event_type="agent_created",
                resource_type="agent",
                resource_id=f"agent-{i}",
                action="create",
                user_id="user-1",
                correlation_id=None,
                metadata={},
                success=True,
            )

        # Query with limit=2, offset=0
        pagination = AuditEventPaginationParams(offset=0, limit=2)
        result = await adapter.query_audit_events(pagination=pagination)

        assert len(result.events) == 2
        assert result.offset == 0
        assert result.limit == 2
        assert result.total_count == 5

    @pytest.mark.asyncio
    async def test_pagination_with_offset(self):
        """Test pagination with offset."""
        store = InMemoryAuditStore()
        adapter = MockAuditQueryAdapter(store)

        now = datetime.now(UTC)

        # Store 5 events
        for i in range(5):
            await store.store_event(
                timestamp=now,
                event_type="agent_created",
                resource_type="agent",
                resource_id=f"agent-{i}",
                action="create",
                user_id="user-1",
                correlation_id=None,
                metadata={},
                success=True,
            )

        # Query with offset=2
        pagination = AuditEventPaginationParams(offset=2, limit=2)
        result = await adapter.query_audit_events(pagination=pagination)

        assert len(result.events) == 2
        assert result.offset == 2
        assert result.total_count == 5

    @pytest.mark.asyncio
    async def test_pagination_beyond_results(self):
        """Test pagination beyond available results."""
        store = InMemoryAuditStore()
        adapter = MockAuditQueryAdapter(store)

        now = datetime.now(UTC)

        # Store 3 events
        for i in range(3):
            await store.store_event(
                timestamp=now,
                event_type="agent_created",
                resource_type="agent",
                resource_id=f"agent-{i}",
                action="create",
                user_id="user-1",
                correlation_id=None,
                metadata={},
                success=True,
            )

        # Query beyond available results
        pagination = AuditEventPaginationParams(offset=10, limit=10)
        result = await adapter.query_audit_events(pagination=pagination)

        assert len(result.events) == 0
        assert result.total_count == 3

    @pytest.mark.asyncio
    async def test_pagination_has_next_property(self):
        """Test pagination has_next property."""
        store = InMemoryAuditStore()
        adapter = MockAuditQueryAdapter(store)

        now = datetime.now(UTC)

        # Store 10 events
        for i in range(10):
            await store.store_event(
                timestamp=now,
                event_type="agent_created",
                resource_type="agent",
                resource_id=f"agent-{i}",
                action="create",
                user_id="user-1",
                correlation_id=None,
                metadata={},
                success=True,
            )

        # First page should have next
        pagination = AuditEventPaginationParams(offset=0, limit=5)
        result = await adapter.query_audit_events(pagination=pagination)
        assert result.has_next is True

        # Last page should not have next
        pagination = AuditEventPaginationParams(offset=5, limit=5)
        result = await adapter.query_audit_events(pagination=pagination)
        assert result.has_next is False


class TestMockAuditQueryAdapterEventCount:
    """Test event counting."""

    @pytest.mark.asyncio
    async def test_count_all_events(self):
        """Test counting all events."""
        store = InMemoryAuditStore()
        adapter = MockAuditQueryAdapter(store)

        now = datetime.now(UTC)

        # Store 5 events
        for i in range(5):
            await store.store_event(
                timestamp=now,
                event_type="agent_created",
                resource_type="agent",
                resource_id=f"agent-{i}",
                action="create",
                user_id="user-1",
                correlation_id=None,
                metadata={},
                success=True,
            )

        result = await adapter.query_audit_events()
        assert result.total_count == 5

    @pytest.mark.asyncio
    async def test_count_filtered_events(self):
        """Test counting filtered events."""
        store = InMemoryAuditStore()
        adapter = MockAuditQueryAdapter(store)

        now = datetime.now(UTC)

        # Store events with different types
        for i in range(3):
            await store.store_event(
                timestamp=now,
                event_type="agent_created",
                resource_type="agent",
                resource_id=f"agent-{i}",
                action="create",
                user_id="user-1",
                correlation_id=None,
                metadata={},
                success=True,
            )

        for i in range(2):
            await store.store_event(
                timestamp=now,
                event_type="agent_deleted",
                resource_type="agent",
                resource_id=f"agent-{i}",
                action="delete",
                user_id="user-1",
                correlation_id=None,
                metadata={},
                success=True,
            )

        # Count only created events
        filters = AuditEventFilters(event_type="agent_created")
        result = await adapter.query_audit_events(filters=filters)
        assert result.total_count == 3

    @pytest.mark.asyncio
    async def test_count_unaffected_by_pagination(self):
        """Test that total_count is not affected by pagination."""
        store = InMemoryAuditStore()
        adapter = MockAuditQueryAdapter(store)

        now = datetime.now(UTC)

        # Store 10 events
        for i in range(10):
            await store.store_event(
                timestamp=now,
                event_type="agent_created",
                resource_type="agent",
                resource_id=f"agent-{i}",
                action="create",
                user_id="user-1",
                correlation_id=None,
                metadata={},
                success=True,
            )

        # Query with small limit
        pagination = AuditEventPaginationParams(offset=0, limit=2)
        result = await adapter.query_audit_events(pagination=pagination)

        # Should only return 2 events but total_count should be 10
        assert len(result.events) == 2
        assert result.total_count == 10


class TestMockAuditQueryAdapterEventInfo:
    """Test AuditEventInfo field population."""

    @pytest.mark.asyncio
    async def test_optional_fields_preserved(self):
        """Test that optional fields (correlation_id, error_message) are preserved."""
        store = InMemoryAuditStore()
        adapter = MockAuditQueryAdapter(store)

        now = datetime.now(UTC)

        # Store event with optional fields
        await store.store_event(
            timestamp=now,
            event_type="agent_created",
            resource_type="agent",
            resource_id="agent-1",
            action="create",
            user_id="user-1",
            correlation_id="corr-123",
            metadata={"project_id": "proj-1"},
            success=False,
            error_message="Validation failed",
        )

        result = await adapter.query_audit_events()

        assert len(result.events) == 1
        event = result.events[0]
        assert event.correlation_id == "corr-123"
        assert event.error_message == "Validation failed"
        assert event.metadata["project_id"] == "proj-1"

    @pytest.mark.asyncio
    async def test_metadata_immutable_mapping(self):
        """Test that metadata is returned as immutable MappingProxyType."""
        store = InMemoryAuditStore()
        adapter = MockAuditQueryAdapter(store)

        now = datetime.now(UTC)

        await store.store_event(
            timestamp=now,
            event_type="agent_created",
            resource_type="agent",
            resource_id="agent-1",
            action="create",
            user_id="user-1",
            correlation_id=None,
            metadata={"key": "value"},
            success=True,
        )

        result = await adapter.query_audit_events()
        event = result.events[0]

        # Verify metadata is MappingProxyType (read-only)
        from types import MappingProxyType

        assert isinstance(event.metadata, MappingProxyType)
        assert event.metadata["key"] == "value"

        # Verify immutability
        with pytest.raises(TypeError):
            event.metadata["key"] = "new_value"

    @pytest.mark.asyncio
    async def test_all_required_fields_populated(self):
        """Test that all required fields are properly populated in AuditEventInfo."""
        store = InMemoryAuditStore()
        adapter = MockAuditQueryAdapter(store)

        now = datetime.now(UTC)

        event_id = await store.store_event(
            timestamp=now,
            event_type="agent_created",
            resource_type="agent",
            resource_id="agent-123",
            action="create",
            user_id="user-456",
            correlation_id=None,
            metadata={},
            success=True,
        )

        result = await adapter.query_audit_events()

        assert len(result.events) == 1
        event = result.events[0]

        # Verify all required fields are present and non-empty
        assert event.id == event_id
        assert event.timestamp == now
        assert event.event_type == "agent_created"
        assert event.resource_type == "agent"
        assert event.resource_id == "agent-123"
        assert event.action == "create"
        assert event.user_id == "user-456"
        assert event.success is True
