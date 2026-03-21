"""
Simulation Board Watch CLI Command

Connects to a running simulation server and displays a live terminal view of the board state.
Updates in real-time as SSE events arrive and polls board state every 2 seconds.

Usage:
    python -m codetoreum.cli.sim_watch --board board-1
    python -m codetoreum.cli.sim_watch --host localhost --port 8000 --board board-1
"""

import asyncio
import json
import logging
import sys
from collections.abc import Awaitable, Callable
from datetime import datetime

import click
import httpx
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()
logger = logging.getLogger(__name__)

# Status color mapping
STATUS_COLORS = {
    "running": "yellow",
    "completed": "green",
    "review": "blue",
    "failed": "red",
    None: "white",
}


def build_board_display(board_state: dict) -> Panel:
    """
    Build a rich panel displaying the current board state.

    Args:
        board_state: Board state response from API

    Returns:
        A rich Panel containing the board columns and work items
    """
    if not board_state or "columns" not in board_state:
        return Panel("No board state available", title="Board")

    columns = board_state.get("columns", [])
    snapshot_time = board_state.get("snapshot_time", "unknown")

    # Create a table for the board layout
    board_table = Table(title="Board Overview", show_lines=True, expand=True)

    # Add a column for each board column
    for column in columns:
        board_table.add_column(column.get("name", "Unknown"), style="cyan")

    # Find the max number of items in any column
    max_items = max((len(column.get("items", [])) for column in columns), default=0)

    # Add rows for each item position
    for row_idx in range(max_items):
        cells = []
        for column in columns:
            items = column.get("items", [])
            if row_idx < len(items):
                item = items[row_idx]
                work_item_id = item.get("work_item_id", "unknown")
                title = item.get("title", work_item_id)
                status = item.get("execution_status")
                assigned_agent = item.get("assigned_agent")

                # Build item text with color coding
                color = STATUS_COLORS.get(status, "white")
                item_text = f"[{color}]{work_item_id}[/{color}]\n"

                if title and title != work_item_id:
                    item_text += f"[dim]{title[:30]}[/dim]\n" if len(title) > 30 else f"[dim]{title}[/dim]\n"

                if status:
                    item_text += f"[{color}]{status}[/{color}]\n"

                if assigned_agent:
                    item_text += f"[magenta]{assigned_agent}[/magenta]"

                cells.append(Text.from_markup(item_text.strip()))
            else:
                cells.append(Text(""))

        board_table.add_row(*cells)

    # Format the snapshot time
    time_str = ""
    try:
        if isinstance(snapshot_time, str):
            dt = datetime.fromisoformat(snapshot_time.replace("Z", "+00:00"))
            time_str = dt.strftime("%H:%M:%S")
        else:
            time_str = str(snapshot_time)
    except Exception:
        time_str = str(snapshot_time)

    board_panel = Panel(
        board_table,
        title=f"Board: {board_state.get('board_name', board_state.get('board_id', 'unknown'))}",
        subtitle=f"Updated: {time_str}",
        expand=True,
    )

    return board_panel


def build_status_display(connected: bool, last_event: str | None, event_count: int, error_message: str | None) -> Panel:
    """
    Build a status panel showing connection and event information.

    Args:
        connected: Whether SSE connection is active
        last_event: Last event type received
        event_count: Total events received
        error_message: Any error message to display

    Returns:
        A rich Panel with status information
    """
    status_table = Table(show_header=False, box=None)

    # Connection status
    conn_status = "[green]✓ Connected[/green]" if connected else "[red]✗ Disconnected[/red]"
    status_table.add_row("Connection:", conn_status)

    # Event count
    status_table.add_row("Events Received:", f"[cyan]{event_count}[/cyan]")

    # Last event
    if last_event:
        status_table.add_row("Last Event:", f"[cyan]{last_event}[/cyan]")

    # Error message
    if error_message:
        status_table.add_row("Error:", f"[red]{error_message}[/red]")

    return Panel(status_table, title="Status", expand=False)


async def stream_events(host: str, port: int, board_id: str, update_callback: Callable[..., Awaitable[None]]) -> None:
    """
    Stream SSE events from the simulation server with automatic reconnection.

    Args:
        host: Server host
        port: Server port
        board_id: Board ID to filter events (used for display)
        update_callback: Callback function to call when events arrive
    """
    sse_url = f"http://{host}:{port}/api/v2/sim/stream"
    reconnect_delay = 3  # Initial reconnection delay in seconds
    max_reconnect_delay = 30  # Maximum reconnection delay in seconds

    while True:
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream("GET", sse_url, timeout=None) as response:
                    if response.status_code != 200:
                        await update_callback(
                            connected=False,
                            error_message=f"Failed to connect: HTTP {response.status_code}",
                        )
                        await asyncio.sleep(reconnect_delay)
                        reconnect_delay = min(reconnect_delay * 1.5, max_reconnect_delay)
                        continue

                    await update_callback(connected=True, error_message=None)
                    # Reset delay on successful connection
                    reconnect_delay = 3

                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            try:
                                payload = json.loads(line[5:].strip())
                                event_type = payload.get("event_type", "unknown")
                                await update_callback(
                                    connected=True,
                                    last_event=event_type,
                                    error_message=None,
                                )
                            except json.JSONDecodeError:
                                pass  # Ignore malformed events
        except asyncio.CancelledError:
            # Normal shutdown
            await update_callback(connected=False)
            raise
        except (httpx.RequestError, httpx.HTTPError) as e:
            # Connection error, attempt to reconnect
            await update_callback(
                connected=False,
                error_message=f"Connection lost: {str(e)[:50]}",
            )
            logger.warning(f"SSE connection failed: {e}. Retrying in {reconnect_delay}s...")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 1.5, max_reconnect_delay)
        except Exception as e:
            # Unexpected error, attempt to reconnect
            await update_callback(
                connected=False,
                error_message=f"Error: {str(e)[:50]}",
            )
            logger.exception("Unexpected error in SSE listener")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 1.5, max_reconnect_delay)


async def poll_board_state(
    host: str, port: int, board_id: str, update_callback: Callable[..., Awaitable[None]]
) -> None:
    """
    Poll board state every 2 seconds.

    Args:
        host: Server host
        port: Server port
        board_id: Board ID to fetch
        update_callback: Callback function to call with board state
    """
    board_url = f"http://{host}:{port}/api/v2/sim/boards/{board_id}/state"

    try:
        async with httpx.AsyncClient() as client:
            while True:
                try:
                    response = await client.get(board_url, timeout=5.0)
                    if response.status_code == 200:
                        board_state = response.json()
                        await update_callback(board_state=board_state)
                    elif response.status_code == 404:
                        await update_callback(
                            error_message=f"Board '{board_id}' not found",
                        )
                except httpx.RequestError as e:
                    await update_callback(
                        error_message=f"Request failed: {e}",
                    )

                # Wait 2 seconds before next poll
                await asyncio.sleep(2)
    except asyncio.CancelledError:
        pass  # Normal shutdown
    except Exception as e:
        await update_callback(
            error_message=f"Poll error: {e}",
        )


async def _run_watch(host: str, port: int, board_id: str) -> None:
    """
    Main watch loop.

    Args:
        host: Server host
        port: Server port
        board_id: Board ID to display
    """
    # State management with lock for thread-safe mutations
    state = {
        "board_state": None,
        "connected": False,
        "last_event": None,
        "event_count": 0,
        "error_message": None,
    }
    state_lock = asyncio.Lock()

    async def update_display(
        board_state: dict | None = None,
        connected: bool | None = None,
        last_event: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update the display state with thread-safe locking."""
        nonlocal state

        async with state_lock:
            if board_state is not None:
                state["board_state"] = board_state
            if connected is not None:
                state["connected"] = connected
            if last_event is not None:
                state["last_event"] = last_event
                state["event_count"] += 1
            if error_message is not None:
                state["error_message"] = error_message

    try:
        # Run SSE listener and board poller concurrently
        sse_task = asyncio.create_task(stream_events(host, port, board_id, update_display))
        poll_task = asyncio.create_task(poll_board_state(host, port, board_id, update_display))

        # Render with Live
        with Live(refresh_per_second=2, console=console) as live:
            try:
                while True:
                    # Build layout
                    layout = Layout()
                    layout.split_column(
                        Layout(
                            build_board_display(state["board_state"]),
                            name="board",
                        ),
                        Layout(
                            build_status_display(
                                state["connected"],
                                state["last_event"],
                                state["event_count"],
                                state["error_message"],
                            ),
                            name="status",
                            size=6,
                        ),
                    )

                    live.update(layout)
                    await asyncio.sleep(0.5)
            except KeyboardInterrupt:
                pass  # Exit gracefully
            finally:
                sse_task.cancel()
                poll_task.cancel()
                try:
                    await sse_task
                except asyncio.CancelledError:
                    pass
                try:
                    await poll_task
                except asyncio.CancelledError:
                    pass

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        logger.exception("Error in sim-watch")
        sys.exit(1)


@click.command("sim-watch")
@click.option(
    "--host",
    default="localhost",
    help="Server host address",
    show_default=True,
)
@click.option(
    "--port",
    default=8000,
    type=int,
    help="Server port",
    show_default=True,
)
@click.option(
    "--board",
    "board_id",
    required=True,
    help="Board ID to display",
)
def sim_watch_command(host: str, port: int, board_id: str) -> None:
    """
    Connect to simulation server and display live board state.

    Connects to the simulation server via SSE streaming and board state polling
    to display a live terminal view of the board columns and work items.

    Examples:

        # Watch board-1 on default server
        python -m codetoreum.cli.sim_watch --board board-1

        # Watch on custom host and port
        python -m codetoreum.cli.sim_watch --host 127.0.0.1 --port 8080 --board board-1
    """
    try:
        console.print(f"[bold cyan]Connecting to {host}:{port}...[/bold cyan]")
        asyncio.run(_run_watch(host, port, board_id))
        console.print("\n[yellow]Disconnected[/yellow]")
    except KeyboardInterrupt:
        console.print("\n[yellow]Exited by user[/yellow]")
    except Exception as e:
        console.print(f"\n[bold red]Fatal error:[/bold red] {e}")
        logger.exception("Fatal error in sim-watch")
        sys.exit(1)


if __name__ == "__main__":
    sim_watch_command()
