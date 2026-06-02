"""File-backed distributed lock implementation for local dev and testing.

Uses JSONL files for persistence with fsync for durability. Single-process
guard via PID lockfile prevents concurrent access from multiple processes.

Suitable for local development and bootstrap harness testing. Not recommended
for production multi-instance deployments.
"""

import asyncio
import json
import logging
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from codetoreum.ports.output.distributed_lock import (
    AcquireResult,
    AcquireStatus,
    IDistributedLock,
    LockHolder,
    ReleaseReason,
    ReleaseResult,
)

logger = logging.getLogger(__name__)


class FileBackedDistributedLock(IDistributedLock):
    """File-backed implementation of IDistributedLock.

    Persists lock state to JSONL files with fsync for durability. Single-process
    access is enforced via PID lockfile to prevent concurrent mutations.

    File format (JSONL, one entry per line):
        {"type": "lock_acquired", "lock_key": "...", "holder_id": "...", "acquired_at": "...", "ttl_seconds": ..., "holder_metadata": {...}}
        {"type": "lock_released", "lock_key": "...", "holder_id": "..."}
        ...

    Constructor reads the file on startup and replays all entries to reconstruct
    current state. Mutations append to the file then fsync.
    """

    def __init__(
        self,
        file_path: str | None = None,
    ) -> None:
        """Initialize the file-backed lock.

        Args:
            file_path: Path to the JSONL file. Defaults to /tmp/codetoreum/distributed_lock.jsonl

        Note:
            This adapter does not emit domain events because it operates at the distributed lock
            primitive level and lacks sufficient context (project_id, board_id, etc.) to create
            meaningful domain events. Event emission is the caller's responsibility.
        """
        if file_path is None:
            base_dir = Path("/tmp/codetoreum")
            base_dir.mkdir(parents=True, exist_ok=True)
            file_path = str(base_dir / "distributed_lock.jsonl")

        self._file_path = Path(file_path)
        self._lock_file_path = Path(f"{file_path}.lock")
        self._lock = asyncio.Lock()

        # State: maps lock_key -> (holder_id, acquired_at, ttl_seconds, expires_at, holder_metadata)
        self._locks: dict[str, tuple[str, datetime, int, datetime, dict[str, str]]] = {}

        # Single-process guard: write our PID to lockfile
        self._ensure_single_process()

        # Load existing state from file
        self._load_from_file()

    def _ensure_single_process(self) -> None:
        """Ensure only one process is using this file at a time.

        Raises:
            RuntimeError: If another process already holds the lock.
        """
        try:
            if self._lock_file_path.exists():
                with open(self._lock_file_path, "r") as f:
                    pid_str = f.read().strip()
                    try:
                        other_pid = int(pid_str)
                        # Check if process still exists
                        try:
                            os.kill(other_pid, 0)  # Signal 0 just checks if process exists
                            msg = (
                                f"File-backed lock already in use by process {other_pid}. "
                                f"Lock file: {self._lock_file_path}"
                            )
                            raise RuntimeError(msg)
                        except ProcessLookupError:
                            # Process no longer exists, safe to take over
                            pass
                    except ValueError:
                        # Couldn't parse PID, remove stale lockfile
                        self._lock_file_path.unlink()

            # Write our PID
            current_pid = os.getpid()
            with open(self._lock_file_path, "w") as f:
                f.write(str(current_pid))
                os.fsync(f.fileno())
        except Exception:
            logger.error("Failed to acquire single-process guard", exc_info=True)
            raise

    def _load_from_file(self) -> None:
        """Load lock state from file by replaying all entries."""
        if not self._file_path.exists():
            return

        try:
            with open(self._file_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    entry = json.loads(line)
                    entry_type = entry.get("type")

                    if entry_type == "lock_acquired":
                        lock_key = entry["lock_key"]
                        holder_id = entry["holder_id"]
                        acquired_at = datetime.fromisoformat(entry["acquired_at"])
                        ttl_seconds = entry["ttl_seconds"]
                        holder_metadata = entry.get("holder_metadata", {})
                        expires_at = acquired_at + timedelta(seconds=ttl_seconds)

                        self._locks[lock_key] = (holder_id, acquired_at, ttl_seconds, expires_at, holder_metadata)

                    elif entry_type == "lock_released":
                        lock_key = entry["lock_key"]
                        self._locks.pop(lock_key, None)

                    elif entry_type == "lock_renewed":
                        lock_key = entry["lock_key"]
                        if lock_key in self._locks:
                            holder_id, acquired_at, _, _, holder_metadata = self._locks[lock_key]
                            ttl_seconds = entry["ttl_seconds"]
                            renewed_at = datetime.fromisoformat(entry["renewed_at"])
                            expires_at = renewed_at + timedelta(seconds=ttl_seconds)
                            self._locks[lock_key] = (holder_id, acquired_at, ttl_seconds, expires_at, holder_metadata)

        except Exception:
            logger.error(f"Failed to load lock state from {self._file_path}", exc_info=True)
            raise

    def _append_entry(self, entry: dict) -> None:
        """Append an entry to the JSONL file with fsync.

        Args:
            entry: Dict to serialize as JSON and append.
        """
        try:
            # Ensure directory exists
            self._file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self._file_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
                os.fsync(f.fileno())
        except Exception:
            logger.error(f"Failed to write lock entry to {self._file_path}", exc_info=True)
            raise

    async def try_acquire(
        self,
        lock_key: str,
        holder_id: str,
        ttl_seconds: int = 7200,
        holder_metadata: dict[str, str] | None = None,
    ) -> AcquireResult:
        """Attempt to acquire the lock.

        Args:
            lock_key: Opaque lock identifier.
            holder_id: Opaque holder identity.
            ttl_seconds: Time-to-live in seconds.
            holder_metadata: Optional metadata dict.

        Returns:
            AcquireResult with status and acquired_at if ACQUIRED.
        """
        if holder_metadata is None:
            holder_metadata = {}

        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=ttl_seconds)

        async with self._lock:
            if lock_key in self._locks:
                current_holder_id, _, _, _, _ = self._locks[lock_key]
                if current_holder_id == holder_id:
                    return AcquireResult(
                        status=AcquireStatus.ALREADY_HELD_BY_SELF,
                        lock_key=lock_key,
                        holder_id=holder_id,
                        acquired_at=None,
                    )
                else:
                    return AcquireResult(
                        status=AcquireStatus.ALREADY_HELD_BY_OTHER,
                        lock_key=lock_key,
                        holder_id=current_holder_id,
                        acquired_at=None,
                    )

            # Acquire the lock
            self._locks[lock_key] = (holder_id, now, ttl_seconds, expires_at, holder_metadata)

            # Persist to file
            entry = {
                "type": "lock_acquired",
                "lock_key": lock_key,
                "holder_id": holder_id,
                "acquired_at": now.isoformat(),
                "ttl_seconds": ttl_seconds,
                "holder_metadata": holder_metadata,
            }
            self._append_entry(entry)

            return AcquireResult(
                status=AcquireStatus.ACQUIRED,
                lock_key=lock_key,
                holder_id=holder_id,
                acquired_at=now,
            )

    async def release(
        self,
        lock_key: str,
        holder_id: str,
    ) -> ReleaseResult:
        """Release the lock if held by the given holder.

        Args:
            lock_key: The lock key to release.
            holder_id: The holder ID that must match.

        Returns:
            ReleaseResult with released=True on success.
        """
        now = datetime.now(UTC)

        async with self._lock:
            if lock_key not in self._locks:
                return ReleaseResult(
                    released=False,
                    reason=ReleaseReason.NOT_HELD,
                    lock_key=lock_key,
                )

            current_holder_id, _, _, _, _ = self._locks[lock_key]
            if current_holder_id != holder_id:
                return ReleaseResult(
                    released=False,
                    reason=ReleaseReason.HELD_BY_OTHER,
                    lock_key=lock_key,
                )

            # Release the lock
            del self._locks[lock_key]

            # Persist to file
            entry = {
                "type": "lock_released",
                "lock_key": lock_key,
                "holder_id": holder_id,
            }
            self._append_entry(entry)

            return ReleaseResult(
                released=True,
                reason=None,
                lock_key=lock_key,
            )

    async def get_holder(self, lock_key: str) -> LockHolder | None:
        """Get the current lock holder.

        Args:
            lock_key: The lock key to check.

        Returns:
            LockHolder if locked, None otherwise.
        """
        async with self._lock:
            if lock_key not in self._locks:
                return None

            holder_id, acquired_at, ttl_seconds, expires_at, holder_metadata = self._locks[lock_key]
            return LockHolder(
                lock_key=lock_key,
                holder_id=holder_id,
                acquired_at=acquired_at,
                ttl_seconds=ttl_seconds,
                expires_at=expires_at,
                holder_metadata=holder_metadata,
            )

    async def get_all_holders(self) -> list[LockHolder]:
        """Get all currently held locks.

        Returns:
            List of LockHolder objects.
        """
        async with self._lock:
            holders = []
            for lock_key, (holder_id, acquired_at, ttl_seconds, expires_at, holder_metadata) in self._locks.items():
                holders.append(
                    LockHolder(
                        lock_key=lock_key,
                        holder_id=holder_id,
                        acquired_at=acquired_at,
                        ttl_seconds=ttl_seconds,
                        expires_at=expires_at,
                        holder_metadata=holder_metadata,
                    )
                )
            return holders

    async def renew(
        self,
        lock_key: str,
        holder_id: str,
        ttl_seconds: int,
    ) -> bool:
        """Extend the TTL on a held lock.

        Args:
            lock_key: The lock key to renew.
            holder_id: The holder ID that must match.
            ttl_seconds: The new TTL in seconds.

        Returns:
            True if renewed, False if not held by this holder.
        """
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=ttl_seconds)

        async with self._lock:
            if lock_key not in self._locks:
                return False

            current_holder_id, acquired_at, _, _, holder_metadata = self._locks[lock_key]
            if current_holder_id != holder_id:
                return False

            # Update the lock, preserving original acquired_at
            self._locks[lock_key] = (holder_id, acquired_at, ttl_seconds, expires_at, holder_metadata)

            # Persist to file
            entry = {
                "type": "lock_renewed",
                "lock_key": lock_key,
                "holder_id": holder_id,
                "renewed_at": now.isoformat(),
                "ttl_seconds": ttl_seconds,
            }
            self._append_entry(entry)

            return True

    def __del__(self) -> None:
        """Clean up PID lockfile on shutdown."""
        try:
            if hasattr(self, "_lock_file_path") and self._lock_file_path.exists():
                self._lock_file_path.unlink()
        except Exception:
            pass
