"""In-memory container recovery tracking store for testing and simulation."""

from typing import Any

from codetoreum.ports.output.container_recovery_tracking_store import (
    IContainerRecoveryTrackingStore,
)


class InMemoryContainerRecoveryTrackingStore(IContainerRecoveryTrackingStore):
    """In-memory implementation of IContainerRecoveryTrackingStore for testing."""

    def __init__(self) -> None:
        """Initialize the in-memory container recovery tracking store."""
        self._store: dict[str, Any] = {}

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
        self._store[key] = value

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
        return self._store.get(key)

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
        import fnmatch

        results = []
        for key in self._store.keys():
            if fnmatch.fnmatch(key, pattern):
                results.append(key)
        return results
