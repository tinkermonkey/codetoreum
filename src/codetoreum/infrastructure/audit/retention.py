"""
Audit Log Retention Policy

Implements configurable retention policies for audit logs with automatic cleanup.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from codetoreum.infrastructure.audit.interfaces import IAuditStore

logger = logging.getLogger(__name__)


@dataclass
class RetentionPolicy:
    """
    Audit log retention policy configuration.

    Defines how long different types of audit events should be retained.
    """

    # Default retention period (days)
    default_retention_days: int = 90  # 3 months

    # Retention periods for specific event types
    authentication_events_days: int = 30  # 1 month
    configuration_events_days: int = 365  # 1 year
    execution_events_days: int = 60  # 2 months
    security_events_days: int = 365  # 1 year (keep security events longer)

    # Cleanup schedule
    cleanup_interval_hours: int = 24  # Run daily

    # Safety limits
    min_retention_days: int = 7  # Never delete events < 7 days old
    max_batch_size: int = 1000  # Delete in batches to avoid DB locks


class RetentionPolicyManager:
    """
    Manages audit log retention and cleanup.

    This manager:
    - Applies retention policies to audit logs
    - Runs periodic cleanup tasks
    - Provides manual cleanup capabilities
    - Logs cleanup statistics
    """

    def __init__(
        self,
        audit_store: IAuditStore,
        policy: Optional[RetentionPolicy] = None,
    ):
        """
        Initialize retention policy manager.

        Args:
            audit_store: Audit store to manage
            policy: Retention policy configuration
        """
        self.audit_store = audit_store
        self.policy = policy or RetentionPolicy()
        self._cleanup_task: Optional[asyncio.Task] = None

    async def cleanup_old_events(self, dry_run: bool = False) -> dict:
        """
        Clean up old audit events according to retention policy.

        Args:
            dry_run: If True, only count events to be deleted without deleting

        Returns:
            Dictionary with cleanup statistics
        """
        logger.info(
            f"Starting audit log cleanup (dry_run={dry_run}, "
            f"retention={self.policy.default_retention_days} days)"
        )

        stats = {
            "start_time": datetime.utcnow().isoformat(),
            "dry_run": dry_run,
            "events_deleted": 0,
            "errors": [],
        }

        try:
            if dry_run:
                # Count events that would be deleted
                from codetoreum.infrastructure.audit.interfaces import (
                    AuditQueryFilters,
                )

                cutoff_date = datetime.utcnow() - timedelta(
                    days=self.policy.default_retention_days
                )
                filters = AuditQueryFilters(
                    end_time=cutoff_date, limit=1000000  # Get all for counting
                )
                deleted_count = await self.audit_store.count_events(filters)
                stats["events_to_delete"] = deleted_count
                logger.info(
                    f"DRY RUN: Would delete {deleted_count} events older than {cutoff_date}"
                )
            else:
                # Actually delete old events
                deleted_count = await self.audit_store.cleanup_old_events(
                    retention_days=self.policy.default_retention_days
                )
                stats["events_deleted"] = deleted_count
                logger.info(f"Deleted {deleted_count} old audit events")

        except Exception as e:
            error_msg = f"Failed to cleanup audit events: {e}"
            logger.error(error_msg,
                extra={"error_id": ErrorRegistry.ErrorRegistry.ERR_INTERNAL_ERROR}
            )

        stats["end_time"] = datetime.utcnow().isoformat()
        return stats

    async def start_periodic_cleanup(self) -> None:
        """
        Start periodic cleanup task.

        This runs in the background and performs cleanup at regular intervals.
        """
        if self._cleanup_task and not self._cleanup_task.done():
            logger.warning("Periodic cleanup already running")
            return

        logger.info(
            f"Starting periodic audit log cleanup (every {self.policy.cleanup_interval_hours} hours)"
        )
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_periodic_cleanup(self) -> None:
        """Stop periodic cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            logger.info("Stopping periodic audit log cleanup")
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def _cleanup_loop(self) -> None:
        """Background cleanup loop."""
        while True:
            try:
                # Wait for next cleanup interval
                await asyncio.sleep(self.policy.cleanup_interval_hours * 3600)

                # Run cleanup
                await self.cleanup_old_events(dry_run=False)

            except asyncio.CancelledError:
                logger.info("Audit log cleanup loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in audit log cleanup loop: {e}",
                    extra={"error_id": ErrorRegistry.ErrorRegistry.ERR_AUDIT_ERROR}
            )
                await asyncio.sleep(60)  # Wait 1 minute before retrying

    def get_retention_info(self) -> dict:
        """
        Get information about current retention policy.

        Returns:
            Dictionary with retention policy details
        """
        return {
            "default_retention_days": self.policy.default_retention_days,
            "authentication_events_days": self.policy.authentication_events_days,
            "configuration_events_days": self.policy.configuration_events_days,
            "execution_events_days": self.policy.execution_events_days,
            "security_events_days": self.policy.security_events_days,
            "cleanup_interval_hours": self.policy.cleanup_interval_hours,
            "min_retention_days": self.policy.min_retention_days,
            "periodic_cleanup_running": self._cleanup_task is not None
            and not self._cleanup_task.done(),
        }


# Example usage:
#
# from codetoreum.infrastructure.audit.stores import InMemoryAuditStore
# from codetoreum.infrastructure.audit.retention import RetentionPolicy, RetentionPolicyManager
from codetoreum.infrastructure.error_ids import ErrorRegistry
#
# # Create audit store
# audit_store = InMemoryAuditStore()
#
# # Create retention policy
# policy = RetentionPolicy(
#     default_retention_days=90,
#     authentication_events_days=30,
# )
#
# # Create manager
# manager = RetentionPolicyManager(audit_store, policy)
#
# # Run cleanup
# stats = await manager.cleanup_old_events(dry_run=False)
# print(f"Deleted {stats['events_deleted']} events")
#
# # Start periodic cleanup
# await manager.start_periodic_cleanup()
