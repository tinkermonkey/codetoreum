"""In-memory implementation of IOrphanScanRegistry for testing."""

import uuid
from datetime import UTC, datetime

from codetoreum.ports.output.orphan_scan_registry import (
    IOrphanScanRegistry,
    OrphanScanResult,
)


class InMemoryOrphanScanRegistry(IOrphanScanRegistry):
    """In-memory orphan scan registry for testing and development."""

    def __init__(self):
        """Initialize the registry."""
        self._last_scan: OrphanScanResult | None = None

    async def record_scan(
        self,
        locks_scanned: int,
        orphaned_locks_found: int,
        orphaned_locks_released: int,
        errors: list[str] | None = None,
    ) -> OrphanScanResult:
        """Record an orphan scan result."""
        result = OrphanScanResult(
            scan_id=f"scan-{uuid.uuid4().hex[:12]}",
            scanned_at=datetime.now(UTC),
            locks_scanned=locks_scanned,
            orphaned_locks_found=orphaned_locks_found,
            orphaned_locks_released=orphaned_locks_released,
            errors=errors or [],
        )
        self._last_scan = result
        return result

    async def get_last_scan(self) -> OrphanScanResult | None:
        """Get the last recorded scan result."""
        return self._last_scan
