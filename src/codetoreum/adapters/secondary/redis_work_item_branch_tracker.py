"""RedisWorkItemBranchTracker — persistence-grade IWorkItemBranchTracker.

Replaces ``InMemoryWorkItemBranchTracker`` for production. The in-memory
implementation loses every work_item -> branch mapping on restart, so a
restart mid-execution forces the orchestrator to re-derive (or guess) the
branch a work item was being processed on. Persisting the mapping in Redis
closes that gap and lets the orchestrator resume cleanly.

Wire format
-----------
- Key: ``codetoreum:wibt:{work_item_id}`` — UTF-8 branch name string.
- TTL: 2 hours by default, matching the pipeline lock and active-run TTLs so
  the three persistence-grade adapters age out together. A work item that
  takes longer than the TTL will simply re-record its branch on the next
  ``set_branch`` call; ``get_branch`` returning ``None`` after TTL expiry is
  the same semantics the in-memory variant produced after a restart.

INV-11: no retry/circuit-breaker logic embedded.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis.asyncio as aioredis

from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.ports.output.work_item_branch_tracker import IWorkItemBranchTracker

logger = logging.getLogger(__name__)

_DEFAULT_TTL_SECONDS = 60 * 60 * 2  # 2 hours
_KEY_PREFIX = "codetoreum:wibt"


class RedisWorkItemBranchTracker(IWorkItemBranchTracker):
    """Redis-backed implementation of :class:`IWorkItemBranchTracker`.

    Stores work_item_id -> branch_name as a single ``SET`` operation with a
    safety TTL. Matches the in-memory port semantics exactly: ``get_branch``
    returns ``None`` when nothing is recorded; ``clear`` is idempotent.
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
        key_prefix: str = _KEY_PREFIX,
    ) -> None:
        self._redis = redis_client
        self._ttl_seconds = ttl_seconds
        self._key_prefix = key_prefix

    def _key(self, work_item_id: str) -> str:
        return f"{self._key_prefix}:{work_item_id}"

    async def set_branch(self, work_item_id: str, branch_name: str) -> None:
        """Record that ``work_item_id`` is being processed on ``branch_name``.

        Overwrites any prior mapping. TTL is refreshed on every write.
        """
        try:
            await self._redis.set(self._key(work_item_id), branch_name, ex=self._ttl_seconds)
        except Exception:
            logger.error(
                f"Failed to set branch for work_item_id={work_item_id}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
            )
            raise

    async def get_branch(self, work_item_id: str) -> str | None:
        """Return the branch recorded for ``work_item_id``, or ``None``."""
        raw = await self._redis.get(self._key(work_item_id))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            return raw.decode("utf-8")
        return str(raw)

    async def clear(self, work_item_id: str) -> None:
        """Remove the branch mapping for ``work_item_id``. Idempotent."""
        await self._redis.delete(self._key(work_item_id))
