"""
FastAPI Application Integration Example

This example shows how to properly integrate the secure logging infrastructure
and error handling middleware into a FastAPI application.
"""

import uvicorn
from fastapi import FastAPI

from codetoreum.adapters.primary.error_middleware import (
    DEBUG_MODE,
    IS_PRODUCTION,
    error_handling_middleware,
)
from codetoreum.infrastructure.logging import configure_logging, get_logger

# Configure logging at application startup BEFORE creating the FastAPI app
# This ensures all logs are properly formatted and secured from the start
configure_logging(
    json_format=IS_PRODUCTION,  # Use JSON format in production for log aggregation
    scrub_sensitive=True,  # Always scrub sensitive data (should never be False)
)

# Get logger for this module
logger = get_logger(__name__)

# Log application startup
logger.info(
    f"Starting Codetoreum application in {'PRODUCTION' if IS_PRODUCTION else 'DEVELOPMENT'} mode",
    extra={
        "debug_mode": DEBUG_MODE,
        "environment": "production" if IS_PRODUCTION else "development",
    },
)

# Create FastAPI application
app = FastAPI(
    title="Codetoreum API",
    description="AI Agent Orchestration Platform",
    version="2.0.0",
    # In production, disable docs for security
    docs_url="/docs" if not IS_PRODUCTION else None,
    redoc_url="/redoc" if not IS_PRODUCTION else None,
)

# Add error handling middleware
# This MUST be added before any routes are registered to catch all errors
app.middleware("http")(error_handling_middleware)


# Example route
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Codetoreum API",
        "version": "2.0.0",
        "environment": "production" if IS_PRODUCTION else "development",
    }


if __name__ == "__main__":
    # Run the application
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        # Use uvicorn's logging config that respects our logging setup
        log_config=None,
    )
