"""Orphan Scan Registry — tracks results of lock cleanup scans."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OrphanScanResult:
    """Result of an orphan scan operation."""

    scan_id: str
    scanned_at: datetime
    locks_scanned: int
    orphaned_locks_found: int
    orphaned_locks_released: int
    errors: list[str]


class IOrphanScanRegistry(ABC):
    """Registry for tracking orphan scan results."""

    @abstractmethod
    async def record_scan(
        self,
        locks_scanned: int,
        orphaned_locks_found: int,
        orphaned_locks_released: int,
        errors: list[str] | None = None,
    ) -> OrphanScanResult:
        """Record the result of an orphan scan.

        Args:
            locks_scanned: Number of locks scanned
            orphaned_locks_found: Number of orphaned locks detected
            orphaned_locks_released: Number of locks successfully released
            errors: Optional list of error messages

        Returns:
            OrphanScanResult with scan metadata
        """

    @abstractmethod
    async def get_last_scan(self) -> OrphanScanResult | None:
        """Get the most recent orphan scan result.

        Returns:
            OrphanScanResult if a scan has been recorded, None otherwise
        """
