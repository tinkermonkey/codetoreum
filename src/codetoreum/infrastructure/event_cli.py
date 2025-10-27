"""CLI tool for event inspection and debugging."""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import click
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from codetoreum.ports.output.event_store import IEventStore

console = Console()


class EventCLI:
    """
    CLI tool for inspecting events in the event store.

    Commands:
    - list: List events by stream, type, or time range
    - show: Show detailed event information
    - search: Search events by content
    - stats: Show event store statistics
    - replay: Replay events (dry-run mode)
    """

    def __init__(self, event_store: IEventStore):
        """
        Initialize CLI tool.

        Args:
            event_store: Event store to query
        """
        self.event_store = event_store

    async def list_events(
        self,
        stream_id: Optional[str] = None,
        event_type: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 50,
    ) -> None:
        """
        List events.

        Args:
            stream_id: Optional filter by stream ID
            event_type: Optional filter by event type
            since: Optional filter by timestamp
            limit: Maximum number of events to show
        """
        console.print("[bold]Event List[/bold]\n")

        try:
            # Get events based on filters
            if event_type:
                events = await self.event_store.get_events_by_type(
                    event_type=event_type,
                    since=since,
                    limit=limit,
                )
            elif stream_id:
                events = await self.event_store.get_events(stream_id=stream_id)
                events = events[:limit]
            elif since:
                events = await self.event_store.get_events_since(since=since)
                events = events[:limit]
            else:
                console.print(
                    "[yellow]Warning:[/yellow] Listing all events (limited to {})".format(
                        limit
                    )
                )
                # Get events from multiple streams
                stream_ids = await self.event_store.get_all_stream_ids()
                events = []
                for sid in stream_ids[:10]:  # Limit to first 10 streams
                    stream_events = await self.event_store.get_events(stream_id=sid)
                    events.extend(stream_events[:5])

                events = events[:limit]

            if not events:
                console.print("[yellow]No events found[/yellow]")
                return

            # Create table
            table = Table(title=f"Events (showing {len(events)})")
            table.add_column("Event ID", style="cyan", no_wrap=True)
            table.add_column("Type", style="green")
            table.add_column("Aggregate", style="magenta")
            table.add_column("Version", justify="right")
            table.add_column("Timestamp", style="blue")

            for event in events:
                table.add_row(
                    str(event.event_id)[:8] + "...",
                    event.event_type,
                    f"{event.aggregate_type}/{event.aggregate_id[:8]}...",
                    str(getattr(event, "stream_version", "?")),
                    event.occurred_at.strftime("%Y-%m-%d %H:%M:%S"),
                )

            console.print(table)

        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")

    async def show_event(self, event_id: str) -> None:
        """
        Show detailed information about a specific event.

        Args:
            event_id: Event ID to show
        """
        console.print(f"[bold]Event Details: {event_id}[/bold]\n")

        try:
            # Search for event across all streams
            # (In production, would have an index for event_id lookup)
            stream_ids = await self.event_store.get_all_stream_ids()

            event = None
            for stream_id in stream_ids:
                events = await self.event_store.get_events(stream_id=stream_id)
                for e in events:
                    if str(e.event_id) == event_id or str(e.event_id).startswith(
                        event_id
                    ):
                        event = e
                        break
                if event:
                    break

            if not event:
                console.print(f"[red]Event not found:[/red] {event_id}")
                return

            # Display event details
            tree = Tree(f"[bold]{event.event_type}[/bold]")

            # Metadata
            metadata_branch = tree.add("[cyan]Metadata[/cyan]")
            metadata_branch.add(f"Event ID: {event.event_id}")
            metadata_branch.add(f"Event Type: {event.event_type}")
            metadata_branch.add(f"Event Version: {event.event_version}")
            metadata_branch.add(f"Aggregate ID: {event.aggregate_id}")
            metadata_branch.add(f"Aggregate Type: {event.aggregate_type}")
            metadata_branch.add(f"Occurred At: {event.occurred_at.isoformat()}")
            metadata_branch.add(f"Correlation ID: {event.correlation_id}")
            metadata_branch.add(f"Causation ID: {event.causation_id}")
            metadata_branch.add(f"User ID: {event.user_id}")

            # Payload
            payload_branch = tree.add("[green]Payload[/green]")
            payload_json = json.dumps(event.payload, indent=2)
            for line in payload_json.split("\n"):
                payload_branch.add(line)

            # Metadata
            if event.metadata:
                meta_branch = tree.add("[yellow]Event Metadata[/yellow]")
                meta_json = json.dumps(event.metadata, indent=2)
                for line in meta_json.split("\n"):
                    meta_branch.add(line)

            console.print(tree)

        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")

    async def show_stream(self, stream_id: str) -> None:
        """
        Show all events in a stream.

        Args:
            stream_id: Stream ID to show
        """
        console.print(f"[bold]Stream: {stream_id}[/bold]\n")

        try:
            # Get stream version
            version = await self.event_store.get_stream_version(stream_id)
            console.print(f"Current version: [green]{version}[/green]\n")

            # Get events
            events = await self.event_store.get_events(stream_id=stream_id)

            if not events:
                console.print("[yellow]No events in stream[/yellow]")
                return

            # Create table
            table = Table(title=f"Stream Events ({len(events)} total)")
            table.add_column("Version", justify="right", style="cyan")
            table.add_column("Event Type", style="green")
            table.add_column("Timestamp", style="blue")
            table.add_column("Payload Summary", style="white")

            for event in events:
                # Summarize payload
                payload_summary = str(event.payload)[:50]
                if len(str(event.payload)) > 50:
                    payload_summary += "..."

                table.add_row(
                    str(getattr(event, "stream_version", "?")),
                    event.event_type,
                    event.occurred_at.strftime("%Y-%m-%d %H:%M:%S"),
                    payload_summary,
                )

            console.print(table)

        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")

    async def show_statistics(self) -> None:
        """Show event store statistics."""
        console.print("[bold]Event Store Statistics[/bold]\n")

        try:
            stats = await self.event_store.get_statistics()

            # Display stats
            tree = Tree("[bold cyan]Statistics[/bold cyan]")

            tree.add(f"Total Events: [green]{stats.get('total_events', 0):,}[/green]")
            tree.add(f"Total Streams: [green]{stats.get('total_streams', 0):,}[/green]")

            # Events by type
            events_by_type = stats.get("events_by_type", {})
            if events_by_type:
                type_branch = tree.add("[yellow]Events by Type[/yellow]")
                for event_type, count in sorted(
                    events_by_type.items(), key=lambda x: x[1], reverse=True
                )[:10]:
                    type_branch.add(f"{event_type}: {count:,}")

            console.print(tree)

        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")

    async def search_events(self, query: str, limit: int = 50) -> None:
        """
        Search events by content using Elasticsearch full-text search.

        Args:
            query: Search query
            limit: Maximum number of results
        """
        console.print(f"[bold]Search Results for: '{query}'[/bold]\n")

        try:
            # Use Elasticsearch's full-text search if the event store supports it
            # Check if the event store has a search method
            if hasattr(self.event_store, 'client'):
                # Use Elasticsearch query_string for full-text search
                from elasticsearch import AsyncElasticsearch

                # Get the index prefix from the event store
                index_prefix = getattr(self.event_store, 'index_prefix', 'events')

                # Perform full-text search across event data
                response = await self.event_store.client.search(
                    index=f"{index_prefix}-*",
                    query={
                        "query_string": {
                            "query": query,
                            "fields": ["event_type^2", "data.*", "aggregate_type", "user_id"]
                        }
                    },
                    sort=[{"timestamp": "desc"}],
                    size=limit,
                )

                hits = response["hits"]["hits"]

                if not hits:
                    console.print("[yellow]No matching events found[/yellow]")
                    return

                # Convert to domain events
                from codetoreum.infrastructure.event_serialization import EventSerializer
                matching_events = [EventSerializer.from_dict(hit["_source"]) for hit in hits]

            else:
                # Fallback to in-memory search for non-Elasticsearch stores
                stream_ids = await self.event_store.get_all_stream_ids()

                matching_events = []
                for stream_id in stream_ids:
                    events = await self.event_store.get_events(stream_id=stream_id)
                    for event in events:
                        # Search in event type and payload
                        if query.lower() in event.event_type.lower():
                            matching_events.append(event)
                        elif query.lower() in str(event.payload).lower():
                            matching_events.append(event)

                        if len(matching_events) >= limit:
                            break

                    if len(matching_events) >= limit:
                        break

            if not matching_events:
                console.print("[yellow]No matching events found[/yellow]")
                return

            # Display results
            table = Table(title=f"Search Results ({len(matching_events)} found)")
            table.add_column("Event ID", style="cyan", no_wrap=True)
            table.add_column("Type", style="green")
            table.add_column("Aggregate", style="magenta")
            table.add_column("Timestamp", style="blue")

            for event in matching_events:
                table.add_row(
                    str(event.event_id)[:8] + "...",
                    event.event_type,
                    f"{event.aggregate_type}/{event.aggregate_id[:8]}...",
                    event.occurred_at.strftime("%Y-%m-%d %H:%M:%S"),
                )

            console.print(table)

        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")


# Click CLI commands

@click.group()
@click.pass_context
def cli(ctx):
    """Event Store CLI tool."""
    # Context would be initialized with event store connection
    pass


@cli.command()
@click.option("--stream-id", help="Filter by stream ID")
@click.option("--event-type", help="Filter by event type")
@click.option("--since", help="Filter by timestamp (ISO format)")
@click.option("--limit", default=50, help="Maximum number of events to show")
@click.pass_context
def list_events(ctx: click.Context, stream_id: Optional[str], event_type: Optional[str], since: Optional[str], limit: int) -> None:
    """List events."""
    # Get event store from context
    event_store = ctx.obj.get("event_store") if ctx.obj else None
    if not event_store:
        click.echo("Error: Event store not initialized")
        return

    # Parse timestamp
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError:
            click.echo(f"Error: Invalid timestamp format: {since}")
            return

    # Create CLI and run
    event_cli = EventCLI(event_store)
    asyncio.run(event_cli.list_events(stream_id=stream_id, event_type=event_type, since=since_dt, limit=limit))


@cli.command()
@click.argument("event_id")
@click.pass_context
def show(ctx: click.Context, event_id: str) -> None:
    """Show detailed event information."""
    event_store = ctx.obj.get("event_store") if ctx.obj else None
    if not event_store:
        click.echo("Error: Event store not initialized")
        return

    event_cli = EventCLI(event_store)
    asyncio.run(event_cli.show_event(event_id))


@cli.command()
@click.argument("stream_id")
@click.pass_context
def stream(ctx: click.Context, stream_id: str) -> None:
    """Show all events in a stream."""
    event_store = ctx.obj.get("event_store") if ctx.obj else None
    if not event_store:
        click.echo("Error: Event store not initialized")
        return

    event_cli = EventCLI(event_store)
    asyncio.run(event_cli.show_stream(stream_id))


@cli.command()
@click.pass_context
def stats(ctx: click.Context) -> None:
    """Show event store statistics."""
    event_store = ctx.obj.get("event_store") if ctx.obj else None
    if not event_store:
        click.echo("Error: Event store not initialized")
        return

    event_cli = EventCLI(event_store)
    asyncio.run(event_cli.show_statistics())


@cli.command()
@click.argument("query")
@click.option("--limit", default=50, help="Maximum number of results")
@click.pass_context
def search(ctx: click.Context, query: str, limit: int) -> None:
    """Search events by content."""
    event_store = ctx.obj.get("event_store") if ctx.obj else None
    if not event_store:
        click.echo("Error: Event store not initialized")
        return

    event_cli = EventCLI(event_store)
    asyncio.run(event_cli.search_events(query, limit))


if __name__ == "__main__":
    cli()
