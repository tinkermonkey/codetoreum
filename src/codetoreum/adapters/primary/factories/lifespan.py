"""
Application Lifespan Management

Handles application startup and shutdown events.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from codetoreum.config import DEFAULT_API_PORT
from codetoreum.infrastructure.auth import SimpleTokenAuthManager


def create_lifespan(app: FastAPI):
    """
    Create an application lifespan context manager.

    This context manager handles startup and shutdown events for the FastAPI
    application, including printing authentication information if an auth
    manager is configured.

    Args:
        app: The FastAPI application instance

    Returns:
        Async context manager for application lifespan
    """
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """
        Application lifespan context manager.
        Handles startup and shutdown events.
        """
        # Startup
        print("Starting Codetoreum API Server...")

        # Print authentication info if auth manager exists
        if hasattr(app.state, "auth_manager"):
            auth_manager: SimpleTokenAuthManager = app.state.auth_manager
            host = os.getenv("API_HOST", "localhost")
            port = int(os.getenv("API_PORT", str(DEFAULT_API_PORT)))
            use_https = os.getenv("API_USE_HTTPS", "false").lower() == "true"
            auth_manager.print_auth_info(host=host, port=port, use_https=use_https)

        yield

        # Shutdown
        print("Shutting down Codetoreum API Server...")

    return lifespan
