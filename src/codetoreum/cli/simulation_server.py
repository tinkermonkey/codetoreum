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
from typing import Optional

import click
import uvicorn
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from codetoreum.infrastructure.simulation.bootstrap import SimulationApplicationBootstrap
from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig

console = Console()
logger = logging.getLogger(__name__)


# Global reference for graceful shutdown
_bootstrap: Optional[SimulationApplicationBootstrap] = None


class SimulationServerConfig:
    """Configuration for simulation server."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8000,
        scenario: str = "default",
        scenario_file: Optional[Path] = None,
        speed_multiplier: float = 1.0,
        no_seed: bool = False,
        debug: bool = False,
    ):
        self.host = host
        self.port = port
        self.scenario = scenario
        self.scenario_file = scenario_file
        self.speed_multiplier = speed_multiplier
        self.no_seed = no_seed
        self.debug = debug


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
        raise FileNotFoundError(
            f"Scenario '{scenario}' not found at {scenario_file}. "
            f"Available scenarios: default, demo, stress_test, review_cycle, failure_recovery"
        )

    return scenario_file


async def bootstrap_application(
    config: SimulationServerConfig,
) -> SimulationApplicationBootstrap:
    """
    Bootstrap the application in simulation mode.

    Args:
        config: Server configuration

    Returns:
        Configured SimulationApplicationBootstrap instance
    """
    console.print("\n[bold cyan]Phase 1: Bootstrap Application[/bold cyan]")

    # Create simulation config
    if config.scenario_file:
        console.print(f"Loading configuration from: {config.scenario_file}")
        sim_config = SimulationConfig.from_yaml(config.scenario_file)
        # Override speed multiplier if provided
        if config.speed_multiplier != 1.0:
            sim_config.time.speed_multiplier = config.speed_multiplier
    else:
        # Use built-in scenario (config-only)
        console.print(f"Using built-in scenario: {config.scenario}")
        sim_config = SimulationConfig.create_fast_config(
            scenario_name=config.scenario,
            speed_multiplier=config.speed_multiplier,
        )

    console.print(f"[dim]Speed multiplier: {sim_config.time.speed_multiplier}x[/dim]")

    # Create and setup bootstrap
    bootstrap = SimulationApplicationBootstrap(sim_config)
    await bootstrap.setup()

    console.print("[green]✓ Application bootstrapped successfully[/green]")

    return bootstrap


async def seed_data(
    bootstrap: SimulationApplicationBootstrap,
    config: SimulationServerConfig,
) -> dict:
    """
    Seed simulation data from scenario.

    Args:
        bootstrap: Configured bootstrap instance
        config: Server configuration

    Returns:
        Dictionary with seeded data counts
    """
    console.print("\n[bold cyan]Phase 2: Seed Data[/bold cyan]")

    if config.no_seed:
        console.print("[yellow]Skipping data seeding (--no-seed flag)[/yellow]")
        return {
            "projects": 0,
            "workflows": 0,
            "agents": 0,
            "work_items": 0,
        }

    seeder = SimulationDataSeeder(bootstrap)

    # Determine which scenario to seed
    if config.scenario_file:
        # Load from custom YAML file
        console.print(f"Seeding from file: {config.scenario_file}")
        await seeder.seed_from_yaml(config.scenario_file)
    else:
        # Use built-in scenario by name
        scenario_file = get_scenario_file_path(config.scenario)
        console.print(f"Seeding from built-in scenario: {config.scenario}")
        await seeder.seed_from_yaml(scenario_file)

    # Get seeded data counts
    created = seeder.get_created_items()
    counts = {
        "projects": len(created.projects),
        "workflows": len(created.workflows),
        "agents": len(created.agents),
        "work_items": len(created.work_items),
    }

    console.print(f"[green]✓ Data seeded successfully[/green]")
    console.print(f"[dim]  Projects: {counts['projects']}, "
                  f"Workflows: {counts['workflows']}, "
                  f"Agents: {counts['agents']}, "
                  f"Work Items: {counts['work_items']}[/dim]")

    return counts


def display_startup_info(
    config: SimulationServerConfig,
    seeded_data: dict,
) -> None:
    """
    Display startup information.

    Args:
        config: Server configuration
        seeded_data: Seeded data counts
    """
    console.print("\n")

    # Create info table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Item", style="bold cyan")
    table.add_column("Value", style="white")

    table.add_row("Host", config.host)
    table.add_row("Port", str(config.port))
    table.add_row("Scenario", config.scenario if not config.scenario_file else str(config.scenario_file))
    table.add_row("Speed Multiplier", f"{config.speed_multiplier}x")
    table.add_row("Debug Mode", "Enabled" if config.debug else "Disabled")

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
    console.print(f"  API Docs:      http://{config.host}:{config.port}/docs")
    console.print(f"  Health Check:  http://{config.host}:{config.port}/api/health")
    console.print(f"  WebSocket:     ws://{config.host}:{config.port}/ws")

    console.print("\n[bold yellow]NOTE:[/bold yellow] Server running in SIMULATION MODE")
    console.print("[dim]All data is in-memory and will be lost on shutdown[/dim]\n")


async def run_server(
    bootstrap: SimulationApplicationBootstrap,
    config: SimulationServerConfig,
) -> None:
    """
    Run the Uvicorn server.

    Args:
        bootstrap: Configured bootstrap instance
        config: Server configuration
    """
    console.print("[bold cyan]Phase 3: Starting Server[/bold cyan]")

    # Configure Uvicorn
    uvicorn_config = uvicorn.Config(
        app=bootstrap.app,
        host=config.host,
        port=config.port,
        log_level="debug" if config.debug else "info",
        access_log=config.debug,
    )

    server = uvicorn.Server(uvicorn_config)

    # Run server (blocking)
    await server.serve()


async def shutdown_handler(signal_num: int) -> None:
    """
    Handle shutdown signals gracefully.

    Args:
        signal_num: Signal number
    """
    global _bootstrap

    signal_name = signal.Signals(signal_num).name
    console.print(f"\n\n[yellow]Received {signal_name}, shutting down gracefully...[/yellow]")

    if _bootstrap:
        try:
            await _bootstrap.teardown()
            console.print("[green]✓ Cleanup completed successfully[/green]")
        except Exception as e:
            console.print(f"[red]Error during cleanup: {e}[/red]")
            logger.exception("Error during shutdown")

    sys.exit(0)


async def main_async(config: SimulationServerConfig) -> None:
    """
    Main async entry point for simulation server.

    Args:
        config: Server configuration
    """
    global _bootstrap

    try:
        # Setup signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(shutdown_handler(s))
            )

        # Bootstrap application
        _bootstrap = await bootstrap_application(config)

        # Seed data
        seeded_data = await seed_data(_bootstrap, config)

        # Display startup info
        display_startup_info(config, seeded_data)

        # Run server (blocking)
        await run_server(_bootstrap, config)

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n[bold red]Error starting server:[/bold red] {e}")
        logger.exception("Error starting simulation server")
        sys.exit(1)
    finally:
        # Cleanup
        if _bootstrap:
            try:
                await _bootstrap.teardown()
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")


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
    help="Server port",
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
    help="Time speed multiplier (e.g., 10 = 10x faster)",
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
def main(
    host: str,
    port: int,
    scenario: str,
    scenario_file: Optional[Path],
    speed_multiplier: float,
    no_seed: bool,
    debug: bool,
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
    """
    # Setup logging
    setup_logging(debug)

    # Display banner
    console.print("\n[bold cyan]═══════════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]   Codetoreum Simulation Server   [/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════════[/bold cyan]\n")

    # Create config
    config = SimulationServerConfig(
        host=host,
        port=port,
        scenario=scenario,
        scenario_file=scenario_file,
        speed_multiplier=speed_multiplier,
        no_seed=no_seed,
        debug=debug,
    )

    # Run async main
    try:
        asyncio.run(main_async(config))
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped by user[/yellow]")
    except Exception as e:
        console.print(f"\n[bold red]Fatal error:[/bold red] {e}")
        logger.exception("Fatal error in simulation server")
        sys.exit(1)


if __name__ == "__main__":
    main()
