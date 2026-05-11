"""
CLI entry point for the codetoreum package.

Enables running the CLI via: python -m codetoreum.cli

Or via the installed command: codetoreum
"""

from codetoreum.cli.main import cli

if __name__ == "__main__":
    cli()
