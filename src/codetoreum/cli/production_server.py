"""
Production Server CLI

Start the Codetoreum application server in production mode with real adapters.

Usage:
    codetoreum-server
    codetoreum-server --port 8080
    codetoreum-server --host 0.0.0.0 --port 8000
"""

import asyncio
import logging
import signal
import sys

import click
import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from codetoreum.infrastructure.bootstrap.production_bootstrap import (
    ProductionApplicationBootstrap,
)
from codetoreum.infrastructure.error_ids import ErrorRegistry

console = Console()
logger = logging.getLogger(__name__)

# Constants for validation
MAX_PORT = 65535
MIN_PORT = 1


def validate_port(port: int) -> None:
    """
    Validate port number.

    Args:
        port: Port number to validate

    Raises:
        click.BadParameter: If port is invalid
    """
    if not (MIN_PORT <= port <= MAX_PORT):
        msg = f"Port must be between {MIN_PORT} and {MAX_PORT}, got {port}"
        raise click.BadParameter(msg)


def setup_logging(log_level: str) -> None:
    """
    Configure structured logging for the production server.

    Args:
        log_level: Log level (debug/info/warning/error)
    """
    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }
    log_level_int = level_map.get(log_level.lower(), logging.INFO)

    logging.basicConfig(
        level=log_level_int,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Reduce noise from uvicorn
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


async def bootstrap_application() -> ProductionApplicationBootstrap:
    """
    Bootstrap the application in production mode.

    Returns:
        Configured ProductionApplicationBootstrap instance

    Raises:
        RuntimeError: If bootstrap fails
    """
    console.print("\n[bold cyan]Loading Configuration[/bold cyan]")
    console.print("[dim]Instantiating ProductionApplicationBootstrap...[/dim]")

    try:
        # Create bootstrap with production defaults
        bootstrap = ProductionApplicationBootstrap()

        console.print("[bold cyan]Setting up Application[/bold cyan]")
        console.print("[dim]Running bootstrap phases (credential validation, adapter resolution, services)...[/dim]")

        # Run setup - this validates credentials, resolves adapters, and wires services
        await bootstrap.setup()

        console.print("[green]✓ Application setup completed successfully[/green]")

        return bootstrap

    except RuntimeError as e:
        # Bootstrap setup failed - log consolidated errors and exit
        console.print(f"\n[bold red]Setup Failed:[/bold red] {e}")
        logger.error(
            f"Bootstrap setup failed: {e}",
            exc_info=True,
            extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
        )
        raise
    except Exception as e:
        console.print(f"\n[bold red]Unexpected Error:[/bold red] {e}")
        logger.error(
            f"Unexpected error during bootstrap: {e}",
            exc_info=True,
            extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
        )
        raise


def display_adapter_summary(bootstrap: ProductionApplicationBootstrap) -> None:
    """
    Display adapter configuration summary.

    Args:
        bootstrap: Configured bootstrap instance
    """
    console.print("\n[bold cyan]Adapter Configuration[/bold cyan]")

    table = Table(show_header=True, box=None, padding=(0, 2))
    table.add_column("Slot", style="cyan")
    table.add_column("Implementation", style="white")

    slot_info = bootstrap.get_adapter_slot_info()
    for slot_name in sorted(slot_info.keys()):
        impl_name = slot_info[slot_name]
        table.add_row(slot_name, impl_name)

    console.print(table)


def display_startup_info(
    host: str,
    port: int,
    log_level: str,
    bootstrap: ProductionApplicationBootstrap,
) -> None:
    """
    Display startup information.

    Args:
        host: Server host
        port: Server port
        log_level: Log level
        bootstrap: Configured bootstrap instance
    """
    console.print("\n")

    # Create info table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Item", style="bold cyan")
    table.add_column("Value", style="white")

    table.add_row("Host", host)
    table.add_row("Port", str(port))
    table.add_row("Log Level", log_level)
    table.add_row("Mode", "[green]PRODUCTION[/green]")

    # Display in a panel
    panel = Panel(
        table,
        title="[bold green]Production Server Started[/bold green]",
        subtitle="[dim]Press Ctrl+C to stop[/dim]",
        border_style="green",
    )
    console.print(panel)

    # Display adapter configuration
    display_adapter_summary(bootstrap)

    # Display URLs
    console.print("\n[bold cyan]URLs:[/bold cyan]")
    console.print(f"  API Docs:      http://{host}:{port}/api/docs")
    console.print(f"  Health Check:  http://{host}:{port}/api/v2/health")
    console.print(f"  WebSocket:     ws://{host}:{port}/api/v2/events/stream")


async def run_server(
    bootstrap: ProductionApplicationBootstrap,
    host: str,
    port: int,
    log_level: str,
) -> None:
    """
    Run the Uvicorn server.

    Args:
        bootstrap: Configured bootstrap instance
        host: Server host
        port: Server port
        log_level: Log level

    Raises:
        OSError: If port is already in use
        RuntimeError: If server fails to start
    """
    console.print("\n[bold cyan]Starting Server[/bold cyan]")

    try:
        uvicorn_config = uvicorn.Config(
            app=bootstrap.app,
            host=host,
            port=port,
            log_level=log_level.lower(),
            access_log=False,  # Disable access logs in production
        )

        server = uvicorn.Server(uvicorn_config)

        # Run server (blocking)
        await server.serve()

    except OSError as e:
        if "Address already in use" in str(e) or e.errno == 98:
            msg = f"Port {port} is already in use. Try a different port with --port"
            raise OSError(msg) from e
        if "Permission denied" in str(e) or e.errno == 13:
            msg = f"Permission denied to bind to port {port}. Try a port > 1024 or run with elevated privileges"
            raise OSError(msg) from e
        raise
    except Exception as e:
        msg = f"Server failed to start: {e}"
        raise RuntimeError(msg) from e


async def main_async(
    host: str,
    port: int,
    log_level: str,
) -> None:
    """
    Main async entry point for production server.

    Args:
        host: Server host
        port: Server port
        log_level: Log level
    """
    bootstrap = None
    shutdown_requested = False

    def shutdown_handler_sync(signum, frame):
        """Synchronous signal handler."""
        nonlocal shutdown_requested
        shutdown_requested = True
        signal_name = signal.Signals(signum).name
        console.print(f"\n\n[yellow]Received {signal_name}, shutting down gracefully...[/yellow]")

    # Setup signal handlers (synchronous)
    signal.signal(signal.SIGINT, shutdown_handler_sync)
    signal.signal(signal.SIGTERM, shutdown_handler_sync)

    try:
        # Bootstrap application (Phase 1-7)
        bootstrap = await bootstrap_application()

        if shutdown_requested:
            return

        # Display startup info
        display_startup_info(host, port, log_level, bootstrap)

        # Run server (blocking)
        await run_server(bootstrap, host, port, log_level)

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except OSError as e:
        console.print(f"\n[bold red]Server error:[/bold red] {e}")
        logger.error(
            f"Server error: {e}",
            exc_info=True,
            extra={"error_id": ErrorRegistry.ERR_SERVICE_UNAVAILABLE},
        )
        sys.exit(1)
    except RuntimeError as e:
        console.print(f"\n[bold red]Runtime error:[/bold red] {e}")
        logger.exception(
            "Runtime error in production server",
            extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
        )
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]Unexpected error:[/bold red] {e}")
        logger.exception(
            "Unexpected error in production server",
            extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
        )
        sys.exit(1)
    finally:
        # Cleanup
        if bootstrap:
            try:
                console.print("\n[dim]Cleaning up resources...[/dim]")
                await bootstrap.teardown()
                console.print("[green]✓ Cleanup completed successfully[/green]")
            except Exception as e:
                console.print(f"[red]Error during cleanup: {e}[/red]")
                logger.error(
                    f"Error during cleanup: {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
                )


@click.command()
@click.option(
    "--host",
    default="0.0.0.0",
    help="Bind host",
    show_default=True,
)
@click.option(
    "--port",
    default=8000,
    type=int,
    help="Bind port (1-65535)",
    show_default=True,
)
@click.option(
    "--log-level",
    default="info",
    type=click.Choice(["debug", "info", "warning", "error"], case_sensitive=False),
    help="Log level",
    show_default=True,
)
def main(
    host: str,
    port: int,
    log_level: str,
) -> None:
    """
    Start the Codetoreum production server.

    This starts the FastAPI application with production adapters connecting to
    real external services (GitHub, Docker, Claude Code API, etc.).

    Critical credentials are validated at startup. If any required credential is
    missing or invalid, the server will exit with an error message and non-zero exit code.

    Horizontal scaling is handled at the orchestration layer (Docker, Kubernetes, etc.)
    by running multiple container instances. Each instance runs a single-process server.

    Examples:

        # Start with default settings (localhost:8000)
        codetoreum-server

        # Start on all interfaces with custom port
        codetoreum-server --host 0.0.0.0 --port 8080

        # Start with debug logging
        codetoreum-server --log-level debug
    """
    # Validate inputs
    try:
        validate_port(port)
    except click.BadParameter as e:
        console.print(f"\n[bold red]Validation error:[/bold red] {e}")
        sys.exit(1)

    # Setup logging
    setup_logging(log_level)

    # Display banner
    console.print("\n[bold cyan]═══════════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]   Codetoreum Production Server   [/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════════[/bold cyan]\n")

    # Run async main
    try:
        asyncio.run(
            main_async(
                host,
                port,
                log_level,
            )
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped by user[/yellow]")
    except Exception as e:
        console.print(f"\n[bold red]Fatal error:[/bold red] {e}")
        logger.exception(
            "Fatal error in production server",
            extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
