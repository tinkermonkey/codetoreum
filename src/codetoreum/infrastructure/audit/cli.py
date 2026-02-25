"""
Audit Log CLI Tool

Command-line interface for querying and managing audit logs.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

import click

from codetoreum.infrastructure.audit.interfaces import AuditQueryFilters
from codetoreum.infrastructure.audit.retention import (
    RetentionPolicy,
    RetentionPolicyManager,
)
from codetoreum.infrastructure.audit.stores import FileAuditStore, InMemoryAuditStore


@click.group()
def audit_cli():
    """Audit log management CLI."""
    pass


@audit_cli.command()
@click.option(
    "--store-type",
    type=click.Choice(["file", "memory"]),
    default="file",
    help="Audit store type",
)
@click.option("--file-path", default="audit.log", help="Path to audit log file")
@click.option("--event-type", help="Filter by event type")
@click.option("--resource-type", help="Filter by resource type")
@click.option("--resource-id", help="Filter by resource ID")
@click.option("--user-id", help="Filter by user ID")
@click.option("--action", help="Filter by action")
@click.option("--success/--failure", default=None, help="Filter by success status")
@click.option("--days-ago", type=int, help="Filter events from N days ago")
@click.option("--limit", type=int, default=50, help="Maximum number of events to show")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"]),
    default="table",
    help="Output format",
)
def query(
    store_type: str,
    file_path: str,
    event_type: Optional[str],
    resource_type: Optional[str],
    resource_id: Optional[str],
    user_id: Optional[str],
    action: Optional[str],
    success: Optional[bool],
    days_ago: Optional[int],
    limit: int,
    output_format: str,
):
    """Query audit logs with filters."""

    async def _query():
        # Create audit store
        if store_type == "file":
            store = FileAuditStore(file_path)
        else:
            store = InMemoryAuditStore()

        # Build filters
        start_time = None
        if days_ago:
            start_time = datetime.now(timezone.utc) - timedelta(days=days_ago)

        filters = AuditQueryFilters(
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            action=action,
            success=success,
            start_time=start_time,
            limit=limit,
        )

        # Query events
        events = await store.query_events(filters)

        # Output results
        if output_format == "json":
            # Convert datetime objects to strings for JSON serialization
            serializable_events = []
            for event in events:
                serializable_event = event.copy()
                if isinstance(serializable_event.get("timestamp"), datetime):
                    serializable_event["timestamp"] = serializable_event[
                        "timestamp"
                    ].isoformat()
                serializable_events.append(serializable_event)
            click.echo(json.dumps(serializable_events, indent=2))
        else:
            # Table format
            if not events:
                click.echo("No audit events found matching filters")
                return

            click.echo(f"\nFound {len(events)} audit events:\n")
            click.echo("-" * 100)
            for event in events:
                timestamp = event["timestamp"]
                if isinstance(timestamp, datetime):
                    timestamp = timestamp.strftime("%Y-%m-%d %H:%M:%S")

                status = "✓" if event["success"] else "✗"
                click.echo(
                    f"{timestamp} | {status} | {event['event_type']:30} | "
                    f"{event['resource_type']:15} | {event['resource_id']:20} | "
                    f"user:{event['user_id']}"
                )

                if event.get("error_message"):
                    click.echo(f"  Error: {event['error_message']}")

                if event.get("metadata"):
                    click.echo(f"  Metadata: {json.dumps(event['metadata'])}")

                click.echo("-" * 100)

    asyncio.run(_query())


@audit_cli.command()
@click.option(
    "--store-type",
    type=click.Choice(["file", "memory"]),
    default="file",
    help="Audit store type",
)
@click.option("--file-path", default="audit.log", help="Path to audit log file")
@click.option(
    "--retention-days",
    type=int,
    default=90,
    help="Delete events older than N days",
)
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without deleting")
def cleanup(
    store_type: str, file_path: str, retention_days: int, dry_run: bool
):
    """Clean up old audit logs according to retention policy."""

    async def _cleanup():
        # Create audit store
        if store_type == "file":
            store = FileAuditStore(file_path)
        else:
            store = InMemoryAuditStore()

        # Create retention policy
        policy = RetentionPolicy(default_retention_days=retention_days)

        # Create manager
        manager = RetentionPolicyManager(store, policy)

        # Run cleanup
        click.echo(
            f"{'DRY RUN: ' if dry_run else ''}Cleaning up audit events older than {retention_days} days..."
        )
        stats = await manager.cleanup_old_events(dry_run=dry_run)

        # Show results
        if dry_run:
            click.echo(
                f"\nWould delete {stats.get('events_to_delete', 0)} audit events"
            )
        else:
            click.echo(f"\nDeleted {stats.get('events_deleted', 0)} audit events")

        if stats.get("errors"):
            click.echo("\nErrors:")
            for error in stats["errors"]:
                click.echo(f"  - {error}")

    asyncio.run(_cleanup())


@audit_cli.command()
@click.option(
    "--store-type",
    type=click.Choice(["file", "memory"]),
    default="file",
    help="Audit store type",
)
@click.option("--file-path", default="audit.log", help="Path to audit log file")
def stats(store_type: str, file_path: str):
    """Show audit log statistics."""

    async def _stats():
        # Create audit store
        if store_type == "file":
            store = FileAuditStore(file_path)
        else:
            store = InMemoryAuditStore()

        # Get total count
        filters = AuditQueryFilters(limit=1000000)
        total_events = await store.count_events(filters)

        click.echo(f"\nAudit Log Statistics:")
        click.echo(f"  Total events: {total_events}")

        # Count by success/failure
        success_filters = AuditQueryFilters(success=True, limit=1000000)
        success_count = await store.count_events(success_filters)

        failure_filters = AuditQueryFilters(success=False, limit=1000000)
        failure_count = await store.count_events(failure_filters)

        click.echo(f"  Successful: {success_count}")
        click.echo(f"  Failed: {failure_count}")

        # Count recent events (last 24 hours)
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        recent_filters = AuditQueryFilters(start_time=yesterday, limit=1000000)
        recent_count = await store.count_events(recent_filters)

        click.echo(f"  Last 24 hours: {recent_count}")

        # If memory store, show type breakdown
        if store_type == "memory" and hasattr(store, "get_stats"):
            store_stats = store.get_stats()
            click.echo(f"\n  Events by type:")
            for event_type, count in store_stats.get("events_by_type", {}).items():
                click.echo(f"    {event_type}: {count}")

    asyncio.run(_stats())


@audit_cli.command()
@click.argument("event_id")
@click.option(
    "--store-type",
    type=click.Choice(["file", "memory"]),
    default="file",
    help="Audit store type",
)
@click.option("--file-path", default="audit.log", help="Path to audit log file")
def get(event_id: str, store_type: str, file_path: str):
    """Get a specific audit event by ID."""

    async def _get():
        # Create audit store
        if store_type == "file":
            store = FileAuditStore(file_path)
        else:
            store = InMemoryAuditStore()

        # Get event
        event = await store.get_event_by_id(event_id)

        if not event:
            click.echo(f"Event {event_id} not found")
            return

        # Convert datetime for display
        if isinstance(event.get("timestamp"), datetime):
            event["timestamp"] = event["timestamp"].isoformat()

        # Display event
        click.echo(json.dumps(event, indent=2))

    asyncio.run(_get())


if __name__ == "__main__":
    audit_cli()
