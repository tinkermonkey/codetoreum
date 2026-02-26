"""
Database Migration Scripts for Audit Logging

Provides migration scripts for setting up audit event storage in PostgreSQL.
"""

import logging

logger = logging.getLogger(__name__)


CREATE_AUDIT_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS audit_events (
    id UUID PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100) NOT NULL,
    resource_id VARCHAR(255) NOT NULL,
    action VARCHAR(50) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    correlation_id UUID,
    metadata JSONB,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_events(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_events(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_correlation ON audit_events(correlation_id);
CREATE INDEX IF NOT EXISTS idx_audit_success ON audit_events(success);
"""

DROP_AUDIT_EVENTS_TABLE = """
DROP TABLE IF EXISTS audit_events CASCADE;
"""


async def run_migrations(connection_string: str) -> bool:
    """
    Run database migrations to create audit events table.

    Args:
        connection_string: PostgreSQL connection string
                          (e.g., "postgresql+asyncpg://user:pass@host/db")

    Returns:
        True if migrations succeeded, False otherwise
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(connection_string, echo=False)

    try:
        async with engine.begin() as conn:
            await conn.execute(text(CREATE_AUDIT_EVENTS_TABLE))
            logger.info("Successfully created audit_events table and indexes")
        return True

    except Exception as e:
        logger.error(
            f"Failed to run audit database migrations: {e}",
            exc_info=True,
            extra={"error_id": "ERR_AUDIT_MIGRATIONS_FAILED"},
        )
        return False

    finally:
        await engine.dispose()


async def rollback_migrations(connection_string: str) -> bool:
    """
    Rollback database migrations (drop audit events table).

    WARNING: This will delete all audit data!

    Args:
        connection_string: PostgreSQL connection string

    Returns:
        True if rollback succeeded, False otherwise
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(connection_string, echo=False)

    try:
        async with engine.begin() as conn:
            await conn.execute(text(DROP_AUDIT_EVENTS_TABLE))
            logger.info("Successfully dropped audit_events table")
        return True

    except Exception as e:
        logger.error(
            f"Failed to rollback audit database migrations: {e}",
            exc_info=True,
            extra={"error_id": "ERR_AUDIT_MIGRATIONS_ROLLBACK_FAILED"},
        )
        return False

    finally:
        await engine.dispose()


async def verify_schema(connection_string: str) -> bool:
    """
    Verify that the audit events schema is properly set up.

    Args:
        connection_string: PostgreSQL connection string

    Returns:
        True if schema is valid, False otherwise
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(connection_string, echo=False)

    try:
        async with engine.begin() as conn:
            # Check if table exists
            result = await conn.execute(
                text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'audit_events'
                    )
                    """)
            )
            table_exists = result.scalar()

            if not table_exists:
                logger.error(
                    "audit_events table does not exist",
                    extra={"error_id": "ERR_AUDIT_SCHEMA_VERIFY_TABLE_MISSING"},
                )
                return False

            # Check if required indexes exist
            required_indexes = [
                "idx_audit_timestamp",
                "idx_audit_event_type",
                "idx_audit_resource",
                "idx_audit_user",
            ]

            for index_name in required_indexes:
                result = await conn.execute(
                    text("""
                        SELECT EXISTS (
                            SELECT FROM pg_indexes
                            WHERE indexname = :index_name
                        )
                        """),
                    {"index_name": index_name},
                )
                index_exists = result.scalar()

                if not index_exists:
                    logger.warning(f"Index {index_name} does not exist")

            logger.info("Audit events schema verification passed")
            return True

    except Exception as e:
        logger.error(
            f"Failed to verify audit schema: {e}",
            exc_info=True,
            extra={"error_id": "ERR_AUDIT_SCHEMA_VERIFY_FAILED"},
        )
        return False

    finally:
        await engine.dispose()
