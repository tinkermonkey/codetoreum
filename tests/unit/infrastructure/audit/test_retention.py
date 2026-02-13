"""
Tests for Audit Retention Policy

Tests the retention policy manager and cleanup functionality.
"""

import pytest
from datetime import datetime, timedelta, timezone

from codetoreum.infrastructure.audit.stores import InMemoryAuditStore
from codetoreum.infrastructure.audit.retention import (
    RetentionPolicy,
    RetentionPolicyManager,
)


class TestRetentionPolicy:
    """Tests for RetentionPolicy configuration."""

    def test_default_retention_policy(self):
        """Test default retention policy values."""
        policy = RetentionPolicy()

        assert policy.default_retention_days == 90
        assert policy.authentication_events_days == 30
        assert policy.configuration_events_days == 365
        assert policy.execution_events_days == 60
        assert policy.security_events_days == 365
        assert policy.cleanup_interval_hours == 24
        assert policy.min_retention_days == 7

    def test_custom_retention_policy(self):
        """Test creating custom retention policy."""
        policy = RetentionPolicy(
            default_retention_days=180,
            authentication_events_days=60,
            cleanup_interval_hours=12,
        )

        assert policy.default_retention_days == 180
        assert policy.authentication_events_days == 60
        assert policy.cleanup_interval_hours == 12


@pytest.mark.asyncio
class TestRetentionPolicyManager:
    """Tests for RetentionPolicyManager."""

    async def test_manager_initialization(self):
        """Test initializing retention policy manager."""
        store = InMemoryAuditStore()
        policy = RetentionPolicy(default_retention_days=90)
        manager = RetentionPolicyManager(store, policy)

        assert manager.audit_store is store
        assert manager.policy is policy
        assert manager._cleanup_task is None

    async def test_cleanup_old_events(self):
        """Test cleaning up old events."""
        store = InMemoryAuditStore()
        policy = RetentionPolicy(default_retention_days=90)
        manager = RetentionPolicyManager(store, policy)

        # Add old events
        now = datetime.now(timezone.utc)
        old_date = now - timedelta(days=100)

        for i in range(5):
            await store.store_event(
                timestamp=old_date,
                event_type="agent_created",
                resource_type="agent",
                resource_id=f"agent-{i}",
                action="create",
                user_id="user-1",
                correlation_id=None,
                metadata={},
                success=True,
            )

        # Add recent events
        for i in range(3):
            await store.store_event(
                timestamp=now,
                event_type="agent_created",
                resource_type="agent",
                resource_id=f"agent-new-{i}",
                action="create",
                user_id="user-1",
                correlation_id=None,
                metadata={},
                success=True,
            )

        # Run cleanup
        stats = await manager.cleanup_old_events(dry_run=False)

        assert stats["events_deleted"] == 5
        assert stats["dry_run"] is False
        assert len(stats["errors"]) == 0

        # Verify only recent events remain
        from codetoreum.infrastructure.audit.interfaces import AuditQueryFilters

        filters = AuditQueryFilters(limit=100)
        remaining_events = await store.query_events(filters)
        assert len(remaining_events) == 3

    async def test_cleanup_dry_run(self):
        """Test dry run mode (no actual deletion)."""
        store = InMemoryAuditStore()
        policy = RetentionPolicy(default_retention_days=90)
        manager = RetentionPolicyManager(store, policy)

        # Add old events
        now = datetime.now(timezone.utc)
        old_date = now - timedelta(days=100)

        for i in range(5):
            await store.store_event(
                timestamp=old_date,
                event_type="agent_created",
                resource_type="agent",
                resource_id=f"agent-{i}",
                action="create",
                user_id="user-1",
                correlation_id=None,
                metadata={},
                success=True,
            )

        # Run dry run
        stats = await manager.cleanup_old_events(dry_run=True)

        assert stats["dry_run"] is True
        assert stats["events_to_delete"] == 5
        # events_deleted may be 0 in dry run mode
        assert stats.get("events_deleted", 0) == 0

        # Verify events are NOT deleted
        from codetoreum.infrastructure.audit.interfaces import AuditQueryFilters

        filters = AuditQueryFilters(limit=100)
        remaining_events = await store.query_events(filters)
        assert len(remaining_events) == 5

    async def test_get_retention_info(self):
        """Test getting retention policy information."""
        store = InMemoryAuditStore()
        policy = RetentionPolicy(
            default_retention_days=90,
            authentication_events_days=30,
        )
        manager = RetentionPolicyManager(store, policy)

        info = manager.get_retention_info()

        assert info["default_retention_days"] == 90
        assert info["authentication_events_days"] == 30
        assert info["periodic_cleanup_running"] is False

    async def test_cleanup_with_no_old_events(self):
        """Test cleanup when there are no old events."""
        store = InMemoryAuditStore()
        policy = RetentionPolicy(default_retention_days=90)
        manager = RetentionPolicyManager(store, policy)

        # Add only recent events
        now = datetime.now(timezone.utc)
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

        # Run cleanup
        stats = await manager.cleanup_old_events(dry_run=False)

        assert stats["events_deleted"] == 0

        # Verify all events remain
        from codetoreum.infrastructure.audit.interfaces import AuditQueryFilters

        filters = AuditQueryFilters(limit=100)
        remaining_events = await store.query_events(filters)
        assert len(remaining_events) == 3

    async def test_cleanup_with_different_retention_periods(self):
        """Test cleanup with different retention periods."""
        store = InMemoryAuditStore()
        manager30 = RetentionPolicyManager(
            store, RetentionPolicy(default_retention_days=30)
        )
        manager90 = RetentionPolicyManager(
            store, RetentionPolicy(default_retention_days=90)
        )

        # Add events at different ages
        now = datetime.now(timezone.utc)
        date_40_days_ago = now - timedelta(days=40)
        date_100_days_ago = now - timedelta(days=100)

        await store.store_event(
            timestamp=date_100_days_ago,
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
            timestamp=date_40_days_ago,
            event_type="agent_created",
            resource_type="agent",
            resource_id="agent-medium",
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

        # Test 30-day retention (should delete 2 events)
        stats = await manager30.cleanup_old_events(dry_run=True)
        assert stats["events_to_delete"] == 2

        # Test 90-day retention (should delete 1 event)
        stats = await manager90.cleanup_old_events(dry_run=True)
        assert stats["events_to_delete"] == 1
