"""
Auto-Instrumentation for Third-Party Libraries

Automatically instruments common libraries used by Codetoreum:
- SQLAlchemy (database queries)
- Redis (cache operations)
- HTTP clients (requests, httpx)
- FastAPI (already handled in otel_setup.py)
"""

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .config import ObservabilityConfig

logger = logging.getLogger(__name__)


def setup_library_instrumentation(config: "ObservabilityConfig") -> None:
    """
    Set up automatic instrumentation for third-party libraries.

    This function conditionally instruments libraries based on configuration.
    Only instruments libraries that are actually installed.

    Args:
        config: Observability configuration

    Note:
        - Requires instrumentation packages to be installed
        - Gracefully handles missing packages
        - Only runs if config.auto_instrument_libraries is True
    """
    if not config.enabled or not config.traces_enabled:
        logger.info("Observability disabled, skipping library auto-instrumentation")
        return

    if not config.auto_instrument_libraries:
        logger.info("Library auto-instrumentation disabled (OTEL_AUTO_INSTRUMENT_LIBRARIES=false)")
        return

    logger.info("Setting up library auto-instrumentation...")

    # SQLAlchemy instrumentation
    _instrument_sqlalchemy()

    # Redis instrumentation
    _instrument_redis()

    # HTTP client instrumentation
    _instrument_http_clients()

    logger.info("Library auto-instrumentation complete")


def _instrument_sqlalchemy() -> None:
    """Instrument SQLAlchemy for database query tracing."""
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument()
        print("[OTEL]   ✓ SQLAlchemy auto-instrumentation enabled", flush=True)
        logger.info("✓ SQLAlchemy auto-instrumentation enabled")

    except ImportError:
        logger.debug("SQLAlchemy instrumentation not available (install: opentelemetry-instrumentation-sqlalchemy)")
    except Exception as e:
        logger.warning(f"Failed to instrument SQLAlchemy: {e}", exc_info=True)


def _instrument_redis() -> None:
    """Instrument Redis for cache operation tracing."""
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()
        print("[OTEL]   ✓ Redis auto-instrumentation enabled", flush=True)
        logger.info("✓ Redis auto-instrumentation enabled")

    except ImportError:
        logger.debug("Redis instrumentation not available (install: opentelemetry-instrumentation-redis)")
    except Exception as e:
        logger.warning(f"Failed to instrument Redis: {e}", exc_info=True)


def _instrument_http_clients() -> None:
    """Instrument HTTP clients (requests, httpx) for outbound request tracing."""
    # Requests library
    try:
        from opentelemetry.instrumentation.requests import RequestsInstrumentor

        RequestsInstrumentor().instrument()
        print("[OTEL]   ✓ Requests (HTTP client) auto-instrumentation enabled", flush=True)
        logger.info("✓ Requests (HTTP client) auto-instrumentation enabled")

    except ImportError:
        logger.debug("Requests instrumentation not available (install: opentelemetry-instrumentation-requests)")
    except Exception as e:
        logger.warning(f"Failed to instrument requests: {e}", exc_info=True)

    # HTTPX library (async HTTP client)
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
        print("[OTEL]   ✓ HTTPX (async HTTP client) auto-instrumentation enabled", flush=True)
        logger.info("✓ HTTPX (async HTTP client) auto-instrumentation enabled")

    except ImportError:
        logger.debug("HTTPX instrumentation not available (install: opentelemetry-instrumentation-httpx)")
    except Exception as e:
        logger.warning(f"Failed to instrument httpx: {e}", exc_info=True)


def instrument_sqlalchemy_engine(engine, config: Optional["ObservabilityConfig"] = None) -> None:
    """
    Instrument a specific SQLAlchemy engine.

    Useful for instrumenting engines created after app startup.

    Args:
        engine: SQLAlchemy engine instance
        config: Optional observability configuration

    Example:
        from sqlalchemy import create_engine
        engine = create_engine(DATABASE_URL)
        instrument_sqlalchemy_engine(engine)
    """
    if config and (not config.enabled or not config.auto_instrument_libraries):
        return

    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument(engine=engine)
        logger.debug(f"Instrumented SQLAlchemy engine: {engine}")

    except ImportError:
        logger.debug("SQLAlchemy instrumentation not available")
    except Exception as e:
        logger.warning(f"Failed to instrument SQLAlchemy engine: {e}", exc_info=True)
