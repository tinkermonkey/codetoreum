"""
Codetoreum CLI - Main entry point for all CLI commands.

This module aggregates all CLI subcommands (simulation server, board watch, config import,
credential validation) into a unified Click group for centralized command-line interface management.

Usage:
    codetoreum simulation-server [options]
    codetoreum sim-watch --board BOARD_ID [options]
    codetoreum yaml-import import-config <yaml_file> [options]
    codetoreum yaml-import import-batch <config_dir> [options]
    codetoreum validate-credentials
"""

import asyncio
from importlib.metadata import PackageNotFoundError, version

import click

# Import subcommand groups and commands
from codetoreum.cli.sim_watch import sim_watch_command
from codetoreum.cli.simulation_server import main as simulation_server_main
from codetoreum.cli.smoke_test_docker import smoke_test_docker
from codetoreum.cli.trigger import main as trigger_main
from codetoreum.cli.validate_credentials import CredentialValidator

# Conditionally import yaml_import to handle import errors gracefully
try:
    from codetoreum.cli.yaml_import import cli as yaml_import_cli

    YAML_IMPORT_AVAILABLE = True
except ImportError:
    YAML_IMPORT_AVAILABLE = False
    yaml_import_cli = None


# Get version from package metadata, fallback to development version
try:
    _version = version("codetoreum")
except PackageNotFoundError:
    _version = "0.1.0+dev"


@click.group()
@click.version_option(version=_version, prog_name="codetoreum")
def cli() -> None:
    """
    Codetoreum - AI Agent Orchestration Platform CLI.

    A comprehensive command-line interface for managing simulations, monitoring
    board state, and importing configurations.

    Examples:

        # Start simulation server on port 8000
        codetoreum simulation-server

        # Start simulation with custom scenario and port
        codetoreum simulation-server --scenario demo --port 8080

        # Watch board state in real-time
        codetoreum sim-watch --board board-1

        # Import YAML configuration
        codetoreum yaml-import import-config config/projects/myproject.yaml

    For help on specific commands, use:

        codetoreum <command> --help
    """


# Register the simulation server command
# Note: simulation_server_main is already decorated with @click.command(),
# so we add it directly as "simulation-server"
cli.add_command(simulation_server_main, name="simulation-server")

# Register the sim-watch command
# Note: sim_watch_command is already decorated with @click.command(name="sim-watch")
# but we explicitly override the name in add_command for clarity
cli.add_command(sim_watch_command)

# Register the yaml-import group (which has its own subcommands: import-config, import-batch)
if YAML_IMPORT_AVAILABLE:
    cli.add_command(yaml_import_cli, name="yaml-import")


# Register the smoke-test-docker command
cli.add_command(smoke_test_docker, name="smoke-test-docker")

# Register the trigger command
cli.add_command(trigger_main, name="trigger")


@cli.command(name="validate-credentials")
def validate_credentials_command() -> None:
    """
    Validate production credentials for deployment.

    Performs pre-flight checks on all production adapters by attempting cheap,
    read-only API calls to verify credentials are valid and services are accessible.

    Exit codes:
        0 - All critical adapters passed validation
        1 - One or more critical adapters failed validation
        130 - Validation cancelled by user

    Example:

        # Validate credentials in .env.production
        codetoreum validate-credentials
    """
    validator = CredentialValidator()
    success = asyncio.run(validator.validate_all())
    validator.print_results()

    if success:
        raise SystemExit(0)
    raise SystemExit(1)


if __name__ == "__main__":
    cli()
