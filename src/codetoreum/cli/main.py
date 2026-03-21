"""
Codetoreum CLI - Main entry point for all CLI commands.

This module aggregates all CLI subcommands (simulation server, board watch, config import)
into a unified Click group for centralized command-line interface management.

Usage:
    codetoreum simulation-server [options]
    codetoreum sim-watch --board BOARD_ID [options]
    codetoreum yaml-import import-config <yaml_file> [options]
    codetoreum yaml-import import-batch <config_dir> [options]
"""

import click

# Import subcommand groups and commands
from codetoreum.cli.sim_watch import sim_watch_command
from codetoreum.cli.simulation_server import main as simulation_server_main

# Conditionally import yaml_import to handle import errors gracefully
try:
    from codetoreum.cli.yaml_import import cli as yaml_import_cli
    YAML_IMPORT_AVAILABLE = True
except ImportError:
    YAML_IMPORT_AVAILABLE = False
    yaml_import_cli = None


@click.group()
@click.version_option(version="0.1.0", prog_name="codetoreum")
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
    cli.add_command(yaml_import_cli)


if __name__ == "__main__":
    cli()
