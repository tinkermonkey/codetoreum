"""Container recovery tracking store port interface.

Provides storage for container re-registration tracking and repair cycle
result scanning without being the source of truth. Used during recovery
operations to track container state and detect orphaned repair results.
"""

from abc import ABC, abstractmethod
from typing import Any


class IContainerRecoveryTrackingStore(ABC):
    """Interface for container recovery tracking and result scanning.

    Scoped to actual purpose (container re-registration and repair-result
    scanning). Provides fast lookup and pattern-based scanning for recovery
    operations.

    Key features:
    - Key-value storage with optional TTL
    - Pattern-based scanning for result discovery
    - Atomic operations
    - Variable TTL support per use case

    Key patterns:
    - `agent:container:{container_name}` (2h TTL) — Container re-registration
    - `repair_cycle:result:{project}:{work_item_id}:{run_id}` (24h TTL) — Repair results

    Example:
        # Store container re-registration
        await store.set(
            "agent:container:myagent-123",
            {"project": "myproject", "work_item_id": "item-456"},
            ttl=7200  # 2 hours
        )

        # Retrieve container data
        container_data = await store.get("agent:container:myagent-123")

        # Scan for orphaned repair results
        result_keys = await store.scan("repair_cycle:result:*")
        for key in result_keys:
            result = await store.get(key)
            # Process completed repair cycle
    """

    @abstractmethod
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

    @abstractmethod
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

    @abstractmethod
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
