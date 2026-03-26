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
import dataclasses
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

from codetoreum.infrastructure.adapters.factory import AdapterFactory, AdapterFactoryConfig
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.resilience import OperationMode
from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationApplicationBootstrap,
)
from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder
from codetoreum.infrastructure.simulation.simulation_config import (
    AdapterSelectionConfig,
    SimulationConfig,
)

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


def parse_adapter_override(override_str: str) -> tuple[str, str]:
    """
    Parse adapter override string in SLOT=IMPL format.

    Args:
        override_str: Override string in format "slot=impl"

    Returns:
        Tuple of (slot_name, impl_name)

    Raises:
        click.BadParameter: If format is invalid
    """
    if "=" not in override_str:
        msg = f"Invalid adapter override format: '{override_str}'. " "Expected format: slot=impl (e.g., 'board=github')"
        raise click.BadParameter(msg)

    parts = override_str.split("=", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        msg = f"Invalid adapter override format: '{override_str}'. " "Expected format: slot=impl (e.g., 'board=github')"
        raise click.BadParameter(msg)

    slot, impl = parts
    return slot.strip(), impl.strip()


def apply_adapter_overrides(
    config: SimulationConfig,
    overrides: tuple[str, ...],
    factory: AdapterFactory,
) -> SimulationConfig:
    """
    Apply adapter override flags to SimulationConfig.

    Validates that slot names and implementation names are registered before applying.

    Args:
        config: SimulationConfig to modify
        overrides: Tuple of override strings in "slot=impl" format from CLI --adapter flags
        factory: AdapterFactory for validation

    Returns:
        Modified SimulationConfig with overrides applied

    Raises:
        click.UsageError: If any slot or impl name is unknown
        click.BadParameter: If any override has invalid format
    """
    if not overrides:
        return config

    errors = []
    current = {f: getattr(config.adapters, f) for f in AdapterSelectionConfig.__dataclass_fields__}

    for override_str in overrides:
        # Parse SLOT=IMPL format
        try:
            slot, impl = parse_adapter_override(override_str)
        except click.BadParameter as e:
            errors.append(str(e))
            continue
        # Validate slot name
        if slot not in AdapterSelectionConfig.__dataclass_fields__:
            valid_slots = sorted(AdapterSelectionConfig.__dataclass_fields__)
            errors.append(f"Unknown adapter slot: '{slot}'. Valid slots: {', '.join(valid_slots)}")
            continue

        # Validate impl name for this slot
        try:
            registry = factory.get_registry(slot)
        except (KeyError, ValueError) as e:
            errors.append(f"Cannot find registry for slot '{slot}': {e}")
            continue

        if not registry.has_adapter(impl):
            available = registry.list_adapters()
            errors.append(f"Unknown implementation '{impl}' for slot '{slot}'. Available: {', '.join(available)}")
            continue

        current[slot] = impl

    if errors:
        raise click.UsageError("\n".join(errors))

    new_adapters = AdapterSelectionConfig(**current)
    return dataclasses.replace(config, adapters=new_adapters)


def display_adapter_summary(config: SimulationConfig, factory: AdapterFactory) -> None:
    """
    Display adapter configuration summary with simulation vs. real labels.

    Args:
        config: SimulationConfig to display
        factory: AdapterFactory for metadata lookup
    """
    console.print("\n[bold cyan]Adapter Configuration[/bold cyan]")

    # Create table
    table = Table(show_header=True, box=None, padding=(0, 2))
    table.add_column("Slot", style="cyan")
    table.add_column("Implementation", style="white")
    table.add_column("Type", style="dim")

    # Iterate over all slots in order
    for slot in sorted(AdapterSelectionConfig.__dataclass_fields__):
        impl = getattr(config.adapters, slot)
        try:
            registry = factory.get_registry(slot)
            if registry.has_adapter(impl):
                meta = registry.get_metadata(impl)
                # Check if "simulation" tag is present
                is_sim = "simulation" in (meta.tags or [])
                type_label = "[simulation]" if is_sim else "[REAL]"
            else:
                type_label = "[unknown]"
        except (KeyError, ValueError):
            logger.warning(f"Failed to resolve adapter metadata for slot '{slot}' with impl '{impl}'", exc_info=True)
            type_label = "[unknown]"

        table.add_row(slot, impl, type_label)

    console.print(table)


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
        raise click.FileError(str(file_path), f"Invalid YAML: {e}") from e
    except ValueError as e:
        raise click.FileError(str(file_path), str(e)) from e
    except Exception as e:
        raise click.FileError(str(file_path), f"Error reading file: {e}") from e


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
    Get the path to a built-in scenario directory.

    Scenarios are stored as scenarios/<name>/ directories containing one YAML file
    per adapter interface.  Both loaders (SimulationConfig.from_yaml and
    SimulationDataSeeder.seed_from_yaml) accept a directory and merge the files
    automatically.

    The legacy name "default" maps to "smoke", and "demo" maps to "sdlc_pipeline".

    Args:
        scenario: Scenario name (smoke, sdlc_pipeline, review_cycle, failure_recovery,
                  stress_test, mixed_github, mixed_full_github, mixed_full_real)
                  Aliases: default → smoke, demo → sdlc_pipeline,
                           mixed_github_real → mixed_github

    Returns:
        Path to scenario directory

    Raises:
        FileNotFoundError: If scenario directory doesn't exist
    """
    # Resolve legacy and alias names
    _aliases = {
        "default": "smoke",
        "demo": "sdlc_pipeline",
        "mixed_github_real": "mixed_github",
    }
    resolved = _aliases.get(scenario, scenario)

    # Look in the workspace scenarios directory
    scenarios_dir = Path(__file__).parent.parent.parent.parent / "scenarios"
    scenario_dir = scenarios_dir / resolved

    if not scenario_dir.is_dir():
        msg = (
            f"Scenario '{scenario}' not found at {scenario_dir}. "
            f"Available scenarios: smoke, sdlc_pipeline, review_cycle, failure_recovery, "
            f"stress_test, mixed_github, mixed_full_github, mixed_full_real"
        )
        raise FileNotFoundError(msg)

    return scenario_dir


async def bootstrap_application(
    scenario: str,
    scenario_file: Path | None,
    speed_multiplier: float | None,
    auto_advance: bool,
    adapter_overrides: tuple[str, ...] | None = None,
) -> tuple[SimulationApplicationBootstrap, AdapterFactory]:
    """
    Bootstrap the application in simulation mode.

    Args:
        scenario: Scenario name
        scenario_file: Optional custom scenario file path
        speed_multiplier: Time speed multiplier (None to use config file default or 1.0)
        auto_advance: Whether to automatically advance simulation clock
        adapter_overrides: Optional tuple of "slot=impl" adapter overrides from CLI

    Returns:
        Tuple of (configured SimulationApplicationBootstrap instance, AdapterFactory instance)

    Raises:
        click.FileError: If scenario file cannot be read
        click.UsageError: If adapter overrides are invalid
        RuntimeError: If bootstrap fails
    """
    console.print("\n[bold cyan]Loading Configuration[/bold cyan]")

    # Create simulation config
    try:
        if scenario_file:
            console.print(f"Loading configuration from: {scenario_file}")
            validate_yaml_file(scenario_file)
            sim_config = SimulationConfig.from_yaml(scenario_file)
            # Override speed multiplier if provided (CLI takes precedence)
            if speed_multiplier is not None:
                sim_config.time.speed_multiplier = speed_multiplier
        else:
            # Use built-in scenario (config-only)
            console.print(f"Using built-in scenario: {scenario}")
            kwargs = {"scenario_name": scenario}
            if speed_multiplier is not None:
                kwargs["speed_multiplier"] = speed_multiplier
            sim_config = SimulationConfig.create_fast_config(**kwargs)
    except PermissionError as e:
        msg = f"Permission denied: {e}"
        raise click.FileError(str(scenario_file), msg) from e
    except Exception as e:
        msg = f"Failed to load configuration: {e}"
        raise RuntimeError(msg) from e

    # Wire auto-advance flag into config (CLI override takes precedence)
    sim_config.time.auto_advance = auto_advance

    console.print(f"[dim]Speed multiplier: {sim_config.time.speed_multiplier}x[/dim]")
    console.print(f"[dim]Auto-advance: {'enabled' if auto_advance else 'disabled'}[/dim]")

    # Create factory for adapter overrides and display
    factory_config = AdapterFactoryConfig(
        operation_mode=OperationMode.SIMULATION,
        enable_resilience=False,
    )
    factory = AdapterFactory(factory_config)

    # Apply adapter overrides if provided
    if adapter_overrides:
        console.print("[dim]Applying adapter overrides...[/dim]")
        try:
            sim_config = apply_adapter_overrides(sim_config, adapter_overrides, factory)
            console.print(f"[dim]Applied {len(adapter_overrides)} adapter override(s)[/dim]")
        except click.UsageError:
            raise
        except Exception as e:
            msg = f"Failed to apply adapter overrides: {e}"
            raise RuntimeError(msg) from e

    console.print("\n[bold cyan]Bootstrapping Application[/bold cyan]")

    # Create and setup bootstrap
    try:
        bootstrap = SimulationApplicationBootstrap(sim_config)
        await bootstrap.setup()
    except Exception as e:
        msg = f"Bootstrap failed: {e}"
        raise RuntimeError(msg) from e

    console.print("[green]✓ Application bootstrapped successfully[/green]")

    return bootstrap, factory


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

    seeder = SimulationDataSeeder(
        bootstrap,
        work_item_service=bootstrap.adapters.work_item_service,
        agent_repository=bootstrap.adapters.agent_repository,
    )

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
        raise click.FileError(str(scenario_file or scenario), msg) from e
    except Exception as e:
        msg = f"Seeding failed: {e}"
        raise RuntimeError(msg) from e

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
    speed_multiplier: float | None,
    auto_advance: bool,
    debug: bool,
    seeded_data: dict,
    sim_config: SimulationConfig | None = None,
    factory: AdapterFactory | None = None,
) -> None:
    """
    Display startup information.

    Args:
        host: Server host
        port: Server port
        scenario: Scenario name
        scenario_file: Optional custom scenario file
        speed_multiplier: Time speed multiplier
        auto_advance: Whether auto-advance is enabled
        debug: Debug mode enabled
        seeded_data: Seeded data counts
        sim_config: Optional SimulationConfig for adapter display
        factory: Optional AdapterFactory for adapter metadata
    """
    console.print("\n")

    # Create info table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Item", style="bold cyan")
    table.add_column("Value", style="white")

    table.add_row("Host", host)
    table.add_row("Port", str(port))
    table.add_row("Scenario", scenario if not scenario_file else str(scenario_file))
    # Use resolved config speed multiplier if available, otherwise fall back to CLI parameter
    display_speed = sim_config.time.speed_multiplier if sim_config else speed_multiplier
    table.add_row("Speed Multiplier", f"{display_speed}x")
    table.add_row("Auto-advance", "Enabled" if auto_advance else "Disabled")
    table.add_row("Debug Mode", "Enabled" if debug else "Disabled")
    table.add_row("Executor", "[green]ExecutionServiceAgentExecutor[/green]")

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

    # Display adapter configuration if available
    if sim_config and factory:
        display_adapter_summary(sim_config, factory)

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
    scenario: str,
    scenario_file: Path | None,
    speed_multiplier: float | None,
    auto_advance: bool,
    no_seed: bool,
    debug: bool,
    adapter_overrides: tuple[str, ...] | None = None,
) -> None:
    """
    Main async entry point for simulation server.

    Args:
        host: Server host
        port: Server port
        scenario: Scenario name
        scenario_file: Optional custom scenario file
        speed_multiplier: Time speed multiplier (None to use config file default or 1.0)
        auto_advance: Whether to automatically advance simulation clock
        no_seed: Skip seeding if True
        debug: Debug mode enabled
        adapter_overrides: Optional tuple of "slot=impl" adapter overrides from CLI
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
        # Bootstrap application (returns both bootstrap and factory instances)
        bootstrap, factory = await bootstrap_application(
            scenario, scenario_file, speed_multiplier, auto_advance, adapter_overrides
        )

        if shutdown_requested:
            return

        # Seed data
        seeded_data = await seed_data(bootstrap, scenario, scenario_file, no_seed)

        if shutdown_requested:
            return

        # Display startup info with adapter configuration
        display_startup_info(
            host,
            port,
            scenario,
            scenario_file,
            speed_multiplier,
            auto_advance,
            debug,
            seeded_data,
            bootstrap.config,
            factory,
        )

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
                    exc_info=True,
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
    help="Pre-built scenario name (default, demo, stress_test, review_cycle, failure_recovery, mixed_full_github, mixed_full_real, mixed_github_real)",
    show_default=True,
)
@click.option(
    "--scenario-file",
    type=click.Path(exists=True, path_type=Path),
    help="Path to custom YAML scenario file (overrides --scenario)",
)
@click.option(
    "--speed-multiplier",
    default=None,
    type=float,
    help="Time speed multiplier (must be positive, e.g., 10 = 10x faster). If not provided, uses config file default or 1.0",
    show_default=False,
)
@click.option(
    "--auto-advance/--no-auto-advance",
    default=True,
    help="Automatically advance simulation clock in background (default: enabled)",
)
@click.option(
    "--no-seed",
    is_flag=True,
    help="Skip seeding test data (start with empty state)",
)
@click.option(
    "--adapter",
    "adapter_overrides",
    multiple=True,
    metavar="SLOT=IMPL",
    help="Override a single adapter: --adapter board=github. Repeatable.",
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
    scenario_file: Path | None,
    speed_multiplier: float | None,
    auto_advance: bool,
    no_seed: bool,
    adapter_overrides: tuple[str, ...],
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

        # Start with auto-advance disabled (manual clock control)
        python -m codetoreum.cli.simulation_server --no-auto-advance

        # Start without seeding data
        python -m codetoreum.cli.simulation_server --no-seed

        # Override adapters (repeatable)
        python -m codetoreum.cli.simulation_server --adapter board=github --adapter llm=mock

        # Override ticket system to use in_memory instead of mock
        python -m codetoreum.cli.simulation_server --adapter ticket=in_memory
    """
    # Validate inputs
    try:
        validate_port(port)
        if speed_multiplier is not None:
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
        asyncio.run(
            main_async(
                host,
                port,
                scenario,
                scenario_file,
                speed_multiplier,
                auto_advance,
                no_seed,
                debug,
                adapter_overrides,
            )
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped by user[/yellow]")
    except click.UsageError as e:
        console.print(f"\n[bold red]Configuration error:[/bold red] {e}")
        logger.error(f"Configuration error: {e}", exc_info=True)
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]Fatal error:[/bold red] {e}")
        logger.exception("Fatal error in simulation server", extra={"error_id": "ERR_UNHANDLED_EXCEPTION"})
        sys.exit(1)


if __name__ == "__main__":
    main()
