"""RedisContainerRecoveryTrackingStore — persistence-grade IContainerRecoveryTrackingStore.

Provides storage for container re-registration tracking and repair cycle
result scanning without being the source of truth. Used during recovery
operations to track container state and detect orphaned repair results.

Wire format
-----------
- Keys follow patterns:
  - ``execution:state:{project}:{work_item_id}`` (4h TTL) — Execution state hint
  - ``agent:container:{container_name}`` (2h TTL) — Container re-registration
  - ``repair_cycle:result:{project}:{work_item_id}:{run_id}`` (24h TTL) — Repair results
- Values are JSON-encoded dictionaries
- Pattern-based scanning supported via Redis SCAN with glob patterns

INV-11: no retry/circuit-breaker logic embedded.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import redis.asyncio as aioredis

from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.ports.exceptions import StorageError
from codetoreum.ports.output.container_recovery_tracking_store import (
    IContainerRecoveryTrackingStore,
)

logger = logging.getLogger(__name__)

_DEFAULT_TTL_SECONDS = 60 * 60 * 24  # 24 hours


class RedisContainerRecoveryTrackingStore(IContainerRecoveryTrackingStore):
    """Redis-backed store for container recovery tracking and result scanning."""

    def __init__(
        self,
        redis_client: aioredis.Redis,
        default_ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        self._redis = redis_client
        self._default_ttl_seconds = default_ttl_seconds

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Store a value with optional TTL.

        Stores a value in the tracking store with an optional time-to-live
        duration for automatic cleanup.

        Args:
            key: Storage key
            value: Value to store (will be serialized to JSON)
            ttl: Optional time-to-live in seconds. If None, uses default TTL.

        Returns:
            None (void operation)

        Raises:
            StorageError: If storage write fails
            ValueError: If key or value is invalid

        Contract:
            - Value is persisted atomically
            - Multiple sets of same key overwrite previous value
            - TTL starts from set time
            - Keys without TTL use storage-specific default
        """
        if not key:
            raise ValueError("Key cannot be empty")

        try:
            payload = json.dumps(value)
            effective_ttl = ttl if ttl is not None else self._default_ttl_seconds
            await self._redis.set(key, payload, ex=effective_ttl)
        except ValueError:
            raise
        except Exception as e:
            logger.error(
                f"Failed to set key={key} in container recovery tracking store",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
            )
            raise StorageError(f"Failed to set key in tracking store: {e}") from e

    async def get(self, key: str) -> Any | None:
        """Retrieve a stored value.

        Retrieves the value stored at the given key. Returns None if the
        key does not exist or the value has expired.

        Args:
            key: Storage key

        Returns:
            Stored value if found and not expired, None otherwise

        Raises:
            StorageError: If storage read fails

        Contract:
            - Returns None for missing keys (no error)
            - Returns None for expired keys (no error)
            - Returned value is deserialized exactly as stored
            - Multiple reads return identical value
        """
        try:
            raw = await self._redis.get(key)
            if raw is None:
                return None
            return self._decode(raw, key)
        except Exception as e:
            logger.error(
                f"Failed to get key={key} from container recovery tracking store",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
            )
            raise StorageError(f"Failed to get key from tracking store: {e}") from e

    async def scan(self, pattern: str) -> list[str]:
        """Scan for keys matching a pattern.

        Performs pattern-based key scanning to discover all keys matching
        the given pattern (using glob-style wildcards).

        Args:
            pattern: Glob pattern to match keys (e.g. "repair_cycle:result:*")

        Returns:
            List of keys matching the pattern (may be empty if no matches)

        Raises:
            StorageError: If storage scan fails

        Contract:
            - Returns empty list if no keys match (no error)
            - Pattern matching is glob-style (*, ?, [...])
            - All matching keys are returned
            - Expired keys are not returned
            - Order of results is undefined
        """
        try:
            results = []
            async for key in self._redis.scan_iter(match=pattern):
                key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                results.append(key_str)
            return results
        except Exception as e:
            logger.error(
                f"Failed to scan keys with pattern={pattern} in container recovery tracking store",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
            )
            raise StorageError(f"Failed to scan keys in tracking store: {e}") from e

    @staticmethod
    def _decode(raw: bytes | str, key: str) -> Any | None:
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            data = json.loads(raw)
            return data
        except Exception:
            logger.error(
                f"Corrupt JSON in container recovery tracking store for key={key}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
            )
            return None


__all__ = ["RedisContainerRecoveryTrackingStore"]
