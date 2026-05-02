"""Production server CLI entry point.

This module provides the CLI command to start the Codetoreum server in
production mode with real adapters and production integrations.

Distinct from simulation_server.py which runs in deterministic test mode.

Usage:
    python -m codetoreum.cli.production_server
    python -m codetoreum.cli.production_server --host 0.0.0.0 --port 8000

Environment Variables:
    CODETOREUM_AUTH_SECRET_KEY: JWT signing key (required)
    CODETOREUM_GITHUB_TOKEN: GitHub API token (required)
    CODETOREUM_CLAUDE_API_KEY: Claude API key (required)
    CODETOREUM_HOST: Server host (default: localhost)
    CODETOREUM_PORT: Server port (default: 8000)
    CODETOREUM_WORKERS: Number of worker processes (default: 4)
    CODETOREUM_ENV: Environment name (default: development)
"""

import asyncio
import logging
import os
import sys
from typing import Any

import click
import uvicorn

logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--host",
    default=None,
    help="Host to bind to (default: localhost)",
)
@click.option(
    "--port",
    type=int,
    default=None,
    help="Port to bind to (default: 8000)",
)
@click.option(
    "--workers",
    type=int,
    default=None,
    help="Number of worker processes (default: 4)",
)
@click.option(
    "--reload",
    is_flag=True,
    help="Enable auto-reload on code changes (development only)",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False),
    default="INFO",
    help="Logging level (default: INFO)",
)
def run_server(
    host: str | None,
    port: int | None,
    workers: int | None,
    reload: bool,
    log_level: str,
) -> None:
    """Start Codetoreum server in production mode.

    This command starts the server with production adapters, real external
    service integrations, and resilience decorators.

    Required environment variables:
    - CODETOREUM_AUTH_SECRET_KEY: JWT signing key

    Additional recommended environment variables:
    - CODETOREUM_GITHUB_TOKEN: GitHub API token
    - CODETOREUM_CLAUDE_API_KEY: Claude API key
    - Other service-specific credentials
    """
    # Set up logging
    logging.basicConfig(
        level=log_level.upper(),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Get configuration from environment or defaults
    host = host or os.getenv("CODETOREUM_HOST", "localhost")
    port = port or int(os.getenv("CODETOREUM_PORT", "8000"))
    workers = workers or int(os.getenv("CODETOREUM_WORKERS", "4"))

    # Determine if we're in development mode
    is_development = os.getenv("CODETOREUM_ENV", "development").lower() == "development"

    # In development, default to 1 worker and enable reload
    if is_development:
        workers = 1
        if not reload:
            logger.info("Development mode detected. Enable reload with --reload flag for auto-restart.")

    logger.info(
        "Starting Codetoreum server in production mode",
        extra={
            "host": host,
            "port": port,
            "workers": workers,
            "reload": reload,
            "log_level": log_level,
        },
    )

    # Configure uvicorn
    config = uvicorn.Config(
        app="codetoreum.cli.production_server:create_app_instance",
        host=host,
        port=port,
        workers=workers if not reload else 1,
        reload=reload,
        log_level=log_level.lower(),
        access_log=True,
        factory=True,
    )

    server = uvicorn.Server(config)

    try:
        # Run the server
        asyncio.run(server.serve())
    except KeyboardInterrupt:
        logger.info("Server shutdown requested by user")
        sys.exit(0)
    except Exception as e:
        logger.error(
            f"Server error: {e}",
            exc_info=True,
            extra={"error_type": type(e).__name__},
        )
        sys.exit(1)


def create_app_instance() -> Any:
    """
    Create and return FastAPI application instance.

    This is the factory function called by uvicorn when using factory mode.
    It bootstraps the production application and returns the FastAPI app.

    Returns:
        Configured FastAPI application

    Raises:
        ValueError: If required environment variables are missing
        AdapterConfigurationError: If adapter credentials are invalid
    """
    from codetoreum.infrastructure.bootstrap.production_bootstrap import ProductionApplicationBootstrap

    # Create bootstrap instance
    bootstrap = ProductionApplicationBootstrap()

    # Run async setup via asyncio.run() for proper event loop management
    # This handles loop creation correctly for both standalone and async contexts
    try:
        app = asyncio.run(bootstrap.setup())
        logger.info("Production bootstrap completed successfully")
        return app
    except Exception as e:
        logger.error(
            f"Production bootstrap failed: {e}",
            exc_info=True,
            extra={"error_type": type(e).__name__},
        )
        raise


if __name__ == "__main__":
    run_server()
