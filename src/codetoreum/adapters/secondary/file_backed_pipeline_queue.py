"""File-backed pipeline queue implementation for local dev and testing.

Uses JSONL files for persistence with fsync for durability. Single-process
guard via PID lockfile prevents concurrent access from multiple processes.

Suitable for local development and bootstrap harness testing. Not recommended
for production multi-instance deployments.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from codetoreum.ports.output.pipeline_queue import (
    EnqueueResult,
    IPipelineQueue,
    QueueEntry,
)

if TYPE_CHECKING:
    from codetoreum.infrastructure.event_bus import EventBus

logger = logging.getLogger(__name__)


class FileBackedPipelineQueue(IPipelineQueue):
    """File-backed implementation of IPipelineQueue.

    Persists queue state to JSONL files with fsync for durability. Single-process
    access is enforced via PID lockfile to prevent concurrent mutations.

    File format (JSONL, one entry per line):
        {"type": "enqueued", "queue_key": "...", "work_item_id": "...", "stage_name": "...", "board_position": ..., "enqueued_at": "...", "metadata": {...}}
        {"type": "dequeued", "queue_key": "...", "work_item_id": "..."}
        ...

    Constructor reads the file on startup and replays all entries to reconstruct
    current queue state. Mutations append to the file then fsync.
    """

    def __init__(
        self,
        file_path: str | None = None,
        event_bus: "EventBus | None" = None,
    ) -> None:
        """Initialize the file-backed queue.

        Args:
            file_path: Path to the JSONL file. Defaults to /tmp/codetoreum/pipeline_queue.jsonl
            event_bus: Optional EventBus for emitting queue lifecycle events
        """
        if file_path is None:
            base_dir = Path("/tmp/codetoreum")
            base_dir.mkdir(parents=True, exist_ok=True)
            file_path = str(base_dir / "pipeline_queue.jsonl")

        self._file_path = Path(file_path)
        self._lock_file_path = Path(f"{file_path}.lock")
        self._event_bus = event_bus
        self._lock = asyncio.Lock()

        # State: maps queue_key -> list of QueueEntry objects in FIFO order
        self._queues: dict[str, list[QueueEntry]] = {}

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
                                f"File-backed queue already in use by process {other_pid}. "
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
        except Exception as e:
            logger.error("Failed to acquire single-process guard", exc_info=True)
            raise

    def _load_from_file(self) -> None:
        """Load queue state from file by replaying all entries."""
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

                    if entry_type == "enqueued":
                        queue_key = entry["queue_key"]
                        work_item_id = entry["work_item_id"]
                        stage_name = entry["stage_name"]
                        board_position = entry["board_position"]
                        enqueued_at = datetime.fromisoformat(entry["enqueued_at"])
                        metadata = entry.get("metadata", {})

                        if queue_key not in self._queues:
                            self._queues[queue_key] = []

                        # Skip if already in queue
                        if not any(e.work_item_id == work_item_id for e in self._queues[queue_key]):
                            queue_entry = QueueEntry(
                                work_item_id=work_item_id,
                                stage_name=stage_name,
                                board_position=board_position,
                                enqueued_at=enqueued_at,
                                metadata=metadata,
                            )
                            self._queues[queue_key].append(queue_entry)

                    elif entry_type == "dequeued":
                        queue_key = entry["queue_key"]
                        work_item_id = entry["work_item_id"]

                        if queue_key in self._queues:
                            # Remove first match (FIFO)
                            self._queues[queue_key] = [
                                e for e in self._queues[queue_key] if e.work_item_id != work_item_id
                            ]
                            # Clean up empty queues
                            if not self._queues[queue_key]:
                                del self._queues[queue_key]

        except Exception as e:
            logger.error(f"Failed to load queue state from {self._file_path}", exc_info=True)
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
        except Exception as e:
            logger.error(f"Failed to write queue entry to {self._file_path}", exc_info=True)
            raise

    async def enqueue(
        self,
        queue_key: str,
        entry: QueueEntry,
    ) -> EnqueueResult:
        """Add an entry to the back of the queue.

        Idempotent on (queue_key, entry.work_item_id).

        Args:
            queue_key: The queue key.
            entry: QueueEntry to add.

        Returns:
            EnqueueResult with position and already_present flag.
        """
        async with self._lock:
            if queue_key not in self._queues:
                self._queues[queue_key] = []

            # Check if already present
            queue = self._queues[queue_key]
            for i, e in enumerate(queue):
                if e.work_item_id == entry.work_item_id:
                    return EnqueueResult(position=i, already_present=True)

            # Add to queue
            queue.append(entry)
            position = len(queue) - 1

            # Persist to file
            file_entry = {
                "type": "enqueued",
                "queue_key": queue_key,
                "work_item_id": entry.work_item_id,
                "stage_name": entry.stage_name,
                "board_position": entry.board_position,
                "enqueued_at": entry.enqueued_at.isoformat(),
                "metadata": entry.metadata,
            }
            self._append_entry(file_entry)

            # Emit event if event bus available
            if self._event_bus:
                try:
                    from codetoreum.domain.events.queue_events import WorkItemQueuedEvent

                    event = WorkItemQueuedEvent(
                        type="queue.item_queued",
                        timestamp=datetime.now().isoformat(),
                        source="file_backed_pipeline_queue",
                        queue_key=queue_key,
                        work_item_id=entry.work_item_id,
                        position=position,
                        metadata=entry.metadata,
                    )
                    await self._event_bus.publish(event)
                except Exception:
                    logger.error(
                        f"Failed to emit WorkItemQueuedEvent for queue_key={queue_key}, work_item_id={entry.work_item_id}",
                        exc_info=True,
                    )

            return EnqueueResult(position=position, already_present=False)

    async def peek(self, queue_key: str) -> QueueEntry | None:
        """Return the head entry without removing. None if empty.

        Args:
            queue_key: The queue key to peek at.

        Returns:
            QueueEntry at head, or None if empty.
        """
        async with self._lock:
            queue = self._queues.get(queue_key, [])
            return queue[0] if queue else None

    async def pop(self, queue_key: str) -> QueueEntry | None:
        """Atomically remove and return the head entry. None if empty.

        Args:
            queue_key: The queue key to pop from.

        Returns:
            QueueEntry at head, or None if empty.
        """
        async with self._lock:
            queue = self._queues.get(queue_key)
            if not queue:
                return None

            entry = queue.pop(0)

            # Clean up empty queues
            if not queue:
                del self._queues[queue_key]

            # Persist to file
            file_entry = {
                "type": "dequeued",
                "queue_key": queue_key,
                "work_item_id": entry.work_item_id,
            }
            self._append_entry(file_entry)

            # Emit event if event bus available
            if self._event_bus:
                try:
                    from codetoreum.domain.events.queue_events import WorkItemDequeuedEvent

                    event = WorkItemDequeuedEvent(
                        type="queue.item_dequeued",
                        timestamp=datetime.now().isoformat(),
                        source="file_backed_pipeline_queue",
                        queue_key=queue_key,
                        work_item_id=entry.work_item_id,
                        reason="popped",
                    )
                    await self._event_bus.publish(event)
                except Exception:
                    logger.error(
                        f"Failed to emit WorkItemDequeuedEvent for queue_key={queue_key}, work_item_id={entry.work_item_id}",
                        exc_info=True,
                    )

            return entry

    async def contains(self, queue_key: str, work_item_id: str) -> bool:
        """Check whether a work item is in the queue.

        Args:
            queue_key: The queue key to check.
            work_item_id: The work item to search for.

        Returns:
            True if found, False otherwise.
        """
        async with self._lock:
            queue = self._queues.get(queue_key, [])
            return any(e.work_item_id == work_item_id for e in queue)

    async def remove(self, queue_key: str, work_item_id: str) -> bool:
        """Remove a specific entry by work_item_id.

        Returns True if removed, False if not present.

        Args:
            queue_key: The queue key to remove from.
            work_item_id: The work item to remove.

        Returns:
            True if removed, False if not found.
        """
        async with self._lock:
            queue = self._queues.get(queue_key)
            if not queue:
                return False

            for i, e in enumerate(queue):
                if e.work_item_id == work_item_id:
                    queue.pop(i)

                    # Clean up empty queues
                    if not queue:
                        del self._queues[queue_key]

                    # Persist to file
                    file_entry = {
                        "type": "dequeued",
                        "queue_key": queue_key,
                        "work_item_id": work_item_id,
                    }
                    self._append_entry(file_entry)

                    # Emit event if event bus available
                    if self._event_bus:
                        try:
                            from codetoreum.domain.events.queue_events import WorkItemDequeuedEvent

                            event = WorkItemDequeuedEvent(
                                type="queue.item_dequeued",
                                timestamp=datetime.now().isoformat(),
                                source="file_backed_pipeline_queue",
                                queue_key=queue_key,
                                work_item_id=work_item_id,
                                reason="removed",
                            )
                            await self._event_bus.publish(event)
                        except Exception:
                            logger.error(
                                f"Failed to emit WorkItemDequeuedEvent for queue_key={queue_key}, work_item_id={work_item_id}",
                                exc_info=True,
                            )

                    return True

            return False

    async def length(self, queue_key: str) -> int:
        """Return queue depth.

        Args:
            queue_key: The queue key to check.

        Returns:
            Number of entries in the queue.
        """
        async with self._lock:
            queue = self._queues.get(queue_key, [])
            return len(queue)

    async def list(self, queue_key: str) -> list[QueueEntry]:
        """Return all entries in FIFO order.

        Args:
            queue_key: The queue key to list.

        Returns:
            List of QueueEntry objects in FIFO order.
        """
        async with self._lock:
            queue = self._queues.get(queue_key, [])
            return list(queue)

    async def position_of(self, queue_key: str, work_item_id: str) -> int | None:
        """Return 0-indexed position of work_item_id, or None if not present.

        Args:
            queue_key: The queue key to search in.
            work_item_id: The work item to find.

        Returns:
            0-indexed position, or None if not found.
        """
        async with self._lock:
            queue = self._queues.get(queue_key, [])
            for i, e in enumerate(queue):
                if e.work_item_id == work_item_id:
                    return i
            return None

    def __del__(self) -> None:
        """Clean up PID lockfile on shutdown."""
        try:
            if hasattr(self, "_lock_file_path") and self._lock_file_path.exists():
                self._lock_file_path.unlink()
        except Exception:
            pass
