"""
Simulation Server CLI

Start the full Codetoreum application server in simulation mode with mock adapters,
enabling interactive manual testing, demos, and development without external dependencies.

Usage:
    python -m codetoreum.cli.simulation_server
    python -m codetoreum.cli.simulation_server --port 8080 --scenario demo
    python -m codetoreum.cli.simulation_server --scenario-file scenarios/custom.yaml --debug
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

import click
import uvicorn
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationApplicationBootstrap,
)
from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig

console = Console()
logger = logging.getLogger(__name__)

# Constants for validation
MAX_PORT = 65535
MIN_PORT = 1
MAX_YAML_FILE_SIZE_MB = 10
MAX_YAML_DEPTH = 50
MAX_YAML_NODES = 10000


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


def validate_speed_multiplier(speed: float) -> None:
    """
    Validate speed multiplier.

    Args:
        speed: Speed multiplier to validate

    Raises:
        click.BadParameter: If speed multiplier is invalid
    """
    if speed <= 0:
        msg = f"Speed multiplier must be positive, got {speed}"
        raise click.BadParameter(msg)


def validate_yaml_file(file_path: Path) -> None:
    """
    Validate YAML file before parsing.

    Args:
        file_path: Path to YAML file

    Raises:
        click.FileError: If file is invalid
    """
    # Check file size
    file_size_mb = file_path.stat().st_size / (1024 * 1024)
    if file_size_mb > MAX_YAML_FILE_SIZE_MB:
        raise click.FileError(
            str(file_path),
            f"File too large ({file_size_mb:.1f}MB). Maximum allowed: {MAX_YAML_FILE_SIZE_MB}MB",
        )

    # Validate YAML structure
    try:
        with open(file_path) as f:
            # Use safe_load with limits
            yaml_content = yaml.safe_load(f)

            # Check depth and node count
            def count_depth_and_nodes(obj, depth=0):
                """Count depth and number of nodes in YAML structure."""
                if depth > MAX_YAML_DEPTH:
                    msg = f"YAML depth exceeds maximum of {MAX_YAML_DEPTH}"
                    raise ValueError(msg)

                node_count = 1
                if isinstance(obj, dict):
                    for value in obj.values():
                        node_count += count_depth_and_nodes(value, depth + 1)
                elif isinstance(obj, list):
                    for item in obj:
                        node_count += count_depth_and_nodes(item, depth + 1)

                if node_count > MAX_YAML_NODES:
                    msg = f"YAML node count exceeds maximum of {MAX_YAML_NODES}"
                    raise ValueError(msg)

                return node_count

            count_depth_and_nodes(yaml_content)

    except yaml.YAMLError as e:
        raise click.FileError(str(file_path), f"Invalid YAML: {e}")
    except ValueError as e:
        raise click.FileError(str(file_path), str(e))
    except Exception as e:
        raise click.FileError(str(file_path), f"Error reading file: {e}")


def setup_logging(debug: bool = False) -> None:
    """
    Configure logging for the simulation server.

    Args:
        debug: Enable debug logging
    """
    log_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Reduce noise from uvicorn
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_scenario_file_path(scenario: str) -> Path:
    """
    Get the path to a built-in scenario file.

    Args:
        scenario: Scenario name (default, demo, stress_test, review_cycle, failure_recovery)

    Returns:
        Path to scenario file

    Raises:
        FileNotFoundError: If scenario file doesn't exist
    """
    # Look in the workspace scenarios directory
    scenarios_dir = Path(__file__).parent.parent.parent.parent / "scenarios"
    scenario_file = scenarios_dir / f"{scenario}.yaml"

    if not scenario_file.exists():
        msg = (
            f"Scenario '{scenario}' not found at {scenario_file}. "
            f"Available scenarios: default, demo, stress_test, review_cycle, failure_recovery"
        )
        raise FileNotFoundError(msg)

    return scenario_file


async def bootstrap_application(
    scenario: str,
    scenario_file: Path | None,
    speed_multiplier: float,
) -> SimulationApplicationBootstrap:
    """
    Bootstrap the application in simulation mode.

    Args:
        scenario: Scenario name
        scenario_file: Optional custom scenario file path
        speed_multiplier: Time speed multiplier

    Returns:
        Configured SimulationApplicationBootstrap instance

    Raises:
        click.FileError: If scenario file cannot be read
        RuntimeError: If bootstrap fails
    """
    console.print("\n[bold cyan]Loading Configuration[/bold cyan]")

    # Create simulation config
    try:
        if scenario_file:
            console.print(f"Loading configuration from: {scenario_file}")
            validate_yaml_file(scenario_file)
            sim_config = SimulationConfig.from_yaml(scenario_file)
            # Override speed multiplier if provided
            if speed_multiplier != 1.0:
                sim_config.time.speed_multiplier = speed_multiplier
        else:
            # Use built-in scenario (config-only)
            console.print(f"Using built-in scenario: {scenario}")
            sim_config = SimulationConfig.create_fast_config(
                scenario_name=scenario,
                speed_multiplier=speed_multiplier,
            )
    except PermissionError as e:
        msg = f"Permission denied: {e}"
        raise click.FileError(str(scenario_file), msg)
    except Exception as e:
        msg = f"Failed to load configuration: {e}"
        raise RuntimeError(msg)

    console.print(f"[dim]Speed multiplier: {sim_config.time.speed_multiplier}x[/dim]")

    console.print("\n[bold cyan]Bootstrapping Application[/bold cyan]")

    # Create and setup bootstrap
    try:
        bootstrap = SimulationApplicationBootstrap(sim_config)
        await bootstrap.setup()
    except Exception as e:
        msg = f"Bootstrap failed: {e}"
        raise RuntimeError(msg)

    console.print("[green]✓ Application bootstrapped successfully[/green]")

    return bootstrap


async def seed_data(
    bootstrap: SimulationApplicationBootstrap,
    scenario: str,
    scenario_file: Path | None,
    no_seed: bool,
) -> dict:
    """
    Seed simulation data from scenario.

    Args:
        bootstrap: Configured bootstrap instance
        scenario: Scenario name
        scenario_file: Optional custom scenario file path
        no_seed: Skip seeding if True

    Returns:
        Dictionary with seeded data counts

    Raises:
        click.FileError: If scenario file cannot be read
        RuntimeError: If seeding fails
    """
    console.print("\n[bold cyan]Seeding Test Data[/bold cyan]")

    if no_seed:
        console.print("[yellow]Skipping data seeding (--no-seed flag)[/yellow]")
        return {
            "projects": 0,
            "workflows": 0,
            "agents": 0,
            "work_items": 0,
        }

    seeder = SimulationDataSeeder(bootstrap)

    # Determine which scenario to seed
    try:
        if scenario_file:
            # Load from custom YAML file
            console.print(f"Seeding from file: {scenario_file}")
            validate_yaml_file(scenario_file)
            await seeder.seed_from_yaml(scenario_file)
        else:
            # Use built-in scenario by name
            file_path = get_scenario_file_path(scenario)
            console.print(f"Seeding from built-in scenario: {scenario}")
            await seeder.seed_from_yaml(file_path)
    except PermissionError as e:
        msg = f"Permission denied: {e}"
        raise click.FileError(str(scenario_file or scenario), msg)
    except Exception as e:
        msg = f"Seeding failed: {e}"
        raise RuntimeError(msg)

    # Get seeded data counts
    created = seeder.get_created_items()
    counts = {
        "projects": len(created.projects),
        "workflows": len(created.workflows),
        "agents": len(created.agents),
        "work_items": len(created.work_items),
    }

    console.print("[green]✓ Data seeded successfully[/green]")
    console.print(
        f"[dim]  Projects: {counts['projects']}, "
        f"Workflows: {counts['workflows']}, "
        f"Agents: {counts['agents']}, "
        f"Work Items: {counts['work_items']}[/dim]"
    )

    return counts


def display_startup_info(
    host: str,
    port: int,
    scenario: str,
    scenario_file: Path | None,
    speed_multiplier: float,
    debug: bool,
    seeded_data: dict,
    full_execution: bool = False,
) -> None:
    """
    Display startup information.

    Args:
        host: Server host
        port: Server port
        scenario: Scenario name
        scenario_file: Optional custom scenario file
        speed_multiplier: Time speed multiplier
        debug: Debug mode enabled
        seeded_data: Seeded data counts
        full_execution: Whether full ExecutionServiceAgentExecutor chain is active
    """
    console.print("\n")

    # Create info table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Item", style="bold cyan")
    table.add_column("Value", style="white")

    table.add_row("Host", host)
    table.add_row("Port", str(port))
    table.add_row("Scenario", scenario if not scenario_file else str(scenario_file))
    table.add_row("Speed Multiplier", f"{speed_multiplier}x")
    table.add_row("Debug Mode", "Enabled" if debug else "Disabled")
    executor_label = (
        "[green]Full (ExecutionServiceAgentExecutor)[/green]"
        if full_execution
        else "[yellow]Mock (MockAgentExecutor)[/yellow]"
    )
    table.add_row("Executor", executor_label)

    # Add seeded data counts
    table.add_row("", "")
    table.add_row("Seeded Projects", str(seeded_data["projects"]))
    table.add_row("Seeded Workflows", str(seeded_data["workflows"]))
    table.add_row("Seeded Agents", str(seeded_data["agents"]))
    table.add_row("Seeded Work Items", str(seeded_data["work_items"]))

    # Display in a panel
    panel = Panel(
        table,
        title="[bold green]Simulation Server Started[/bold green]",
        subtitle="[dim]Press Ctrl+C to stop[/dim]",
        border_style="green",
    )
    console.print(panel)

    # Display URLs
    console.print("\n[bold cyan]URLs:[/bold cyan]")
    console.print(f"  API Docs:      http://{host}:{port}/api/docs")
    console.print(f"  Health Check:  http://{host}:{port}/api/v2/health")
    console.print(f"  WebSocket:     ws://{host}:{port}/api/v2/events/stream")

    console.print("\n[bold yellow]NOTE:[/bold yellow] Server running in SIMULATION MODE")
    console.print("[dim]All data is in-memory and will be lost on shutdown[/dim]\n")


async def run_server(
    bootstrap: SimulationApplicationBootstrap,
    host: str,
    port: int,
    debug: bool,
) -> None:
    """
    Run the Uvicorn server.

    Args:
        bootstrap: Configured bootstrap instance
        host: Server host
        port: Server port
        debug: Debug mode enabled

    Raises:
        OSError: If port is already in use
        RuntimeError: If server fails to start
    """
    console.print("\n[bold cyan]Starting Server[/bold cyan]")

    # Configure Uvicorn
    try:
        uvicorn_config = uvicorn.Config(
            app=bootstrap.app,
            host=host,
            port=port,
            log_level="debug" if debug else "info",
            access_log=debug,
        )

        server = uvicorn.Server(uvicorn_config)

        # Run server (blocking)
        await server.serve()

    except OSError as e:
        if "Address already in use" in str(e) or e.errno == 98:
            msg = f"Port {port} is already in use. Try a different port with --port"
            raise OSError(msg)
        if "Permission denied" in str(e) or e.errno == 13:
            msg = f"Permission denied to bind to port {port}. Try a port > 1024 or run with elevated privileges"
            raise OSError(msg)
        raise
    except Exception as e:
        msg = f"Server failed to start: {e}"
        raise RuntimeError(msg)


async def main_async(
    host: str,
    port: int,
    scenario: str,
    scenario_file: Path | None,
    speed_multiplier: float,
    no_seed: bool,
    debug: bool,
    full_execution: bool = False,
) -> None:
    """
    Main async entry point for simulation server.

    Args:
        host: Server host
        port: Server port
        scenario: Scenario name
        scenario_file: Optional custom scenario file
        speed_multiplier: Time speed multiplier
        no_seed: Skip seeding if True
        debug: Debug mode enabled
        full_execution: Enable full ExecutionServiceAgentExecutor chain
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
        # Bootstrap application
        bootstrap = await bootstrap_application(scenario, scenario_file, speed_multiplier)

        if shutdown_requested:
            return

        # Enable full execution chain if requested
        if full_execution:
            console.print("\n[bold cyan]Enabling Full Execution Chain[/bold cyan]")
            bootstrap.enable_execution_service_executor()
            console.print("[green]✓ ExecutionServiceAgentExecutor active (full LLM → VCS chain)[/green]")
        else:
            console.print("\n[dim]Using MockAgentExecutor (pass --full-execution for full chain)[/dim]")

        # Seed data
        seeded_data = await seed_data(bootstrap, scenario, scenario_file, no_seed)

        if shutdown_requested:
            return

        # Display startup info
        display_startup_info(host, port, scenario, scenario_file, speed_multiplier, debug, seeded_data, full_execution)

        # Run server (blocking)
        await run_server(bootstrap, host, port, debug)

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except click.FileError as e:
        console.print(f"\n[bold red]File error:[/bold red] {e}")
        logger.error(f"File error: {e}", exc_info=True, extra={"error_id": ErrorRegistry.ERR_FILE_READ_ERROR})
        sys.exit(1)
    except OSError as e:
        console.print(f"\n[bold red]Server error:[/bold red] {e}")
        logger.error(f"Server error: {e}", exc_info=True, extra={"error_id": "ERR_SERVICE_UNAVAILABLE"})
        sys.exit(1)
    except RuntimeError as e:
        console.print(f"\n[bold red]Runtime error:[/bold red] {e}")
        logger.exception(
            "Runtime error in simulation server",
            extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
        )
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]Unexpected error:[/bold red] {e}")
        logger.exception("Unexpected error in simulation server", extra={"error_id": "ERR_UNHANDLED_EXCEPTION"})
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
                    extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
                )


@click.command()
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
    help="Server port (1-65535)",
    show_default=True,
)
@click.option(
    "--scenario",
    default="default",
    help="Pre-built scenario name (default, demo, stress_test, review_cycle, failure_recovery)",
    show_default=True,
)
@click.option(
    "--scenario-file",
    type=click.Path(exists=True, path_type=Path),
    help="Path to custom YAML scenario file (overrides --scenario)",
)
@click.option(
    "--speed-multiplier",
    default=1.0,
    type=float,
    help="Time speed multiplier (must be positive, e.g., 10 = 10x faster)",
    show_default=True,
)
@click.option(
    "--no-seed",
    is_flag=True,
    help="Skip seeding test data (start with empty state)",
)
@click.option(
    "--debug",
    is_flag=True,
    help="Enable debug logging",
)
@click.option(
    "--full-execution",
    is_flag=True,
    help="Use full ExecutionServiceAgentExecutor (LLM → WorkspaceRouter → VCS chain) instead of MockAgentExecutor",
)
def main(
    host: str,
    port: int,
    scenario: str,
    scenario_file: Path | None,
    speed_multiplier: float,
    no_seed: bool,
    debug: bool,
    full_execution: bool,
) -> None:
    """
    Start the Codetoreum simulation server.

    This starts a full FastAPI application server in simulation mode with mock adapters.
    All data is in-memory and no external services are required.

    Examples:

        # Start with default scenario
        python -m codetoreum.cli.simulation_server

        # Start with demo scenario on custom port
        python -m codetoreum.cli.simulation_server --port 8080 --scenario demo

        # Start with custom scenario file
        python -m codetoreum.cli.simulation_server --scenario-file my_scenario.yaml

        # Start with 10x time acceleration
        python -m codetoreum.cli.simulation_server --speed-multiplier 10.0

        # Start without seeding data
        python -m codetoreum.cli.simulation_server --no-seed

        # Start with full execution chain (LLM + VCS events)
        python -m codetoreum.cli.simulation_server --scenario demo --full-execution
    """
    # Validate inputs
    try:
        validate_port(port)
        validate_speed_multiplier(speed_multiplier)
        if scenario_file:
            validate_yaml_file(scenario_file)
    except (click.BadParameter, click.FileError) as e:
        console.print(f"\n[bold red]Validation error:[/bold red] {e}")
        sys.exit(1)

    # Setup logging
    setup_logging(debug)

    # Display banner
    console.print("\n[bold cyan]═══════════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]   Codetoreum Simulation Server   [/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════════[/bold cyan]\n")

    # Run async main
    try:
        asyncio.run(main_async(host, port, scenario, scenario_file, speed_multiplier, no_seed, debug, full_execution))
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped by user[/yellow]")
    except Exception as e:
        console.print(f"\n[bold red]Fatal error:[/bold red] {e}")
        logger.exception("Fatal error in simulation server", extra={"error_id": "ERR_UNHANDLED_EXCEPTION"})
        sys.exit(1)


if __name__ == "__main__":
    main()
